# 制作与复核脚本

这些脚本仅用于本次文档和演示稿；未修改项目业务功能。工作区为 `docs/midterm_20261029/`。脚本从自身位置定位工作区，因此从仓库根目录运行即可。

## 环境

本次使用 Windows PowerShell、已安装的 Word/PowerPoint、Poppler，以及 Codex 提供的 Python。Python 需包含 python-docx、python-pptx、pypdf、lxml、Pillow。ppt-master 为用户指定技能，实际目录是 `C:/Users/32002/.agents/skills/ppt-master`，版本 6.7.3。

```powershell
$midtermPython = 'C:/Users/32002/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$pptMasterDir = 'C:/Users/32002/.agents/skills/ppt-master'
$midtermRoot = 'docs/midterm_20261029'
```

以上为本次已验证环境路径，异机应替换为实际安装路径。原模板、已导入的 authoring 工作区与图像应保留；不要手改 `presentation/analysis` 或 native-payloads。

## 1. 汇报表

正文源为 `report_content.py`；表格排版在 `build_report.py`。从原始 DOCX 副本构建，不覆盖桌面原稿。

```powershell
& $midtermPython -X utf8 "$midtermRoot/scripts/build_report.py"
& "$midtermRoot/scripts/render_office.ps1" -InputPath "$midtermRoot/deliverables/2026年度中期汇报表_SocialSense_修订稿.docx" -OutputDir "$midtermRoot/build/report_final" -Kind docx
pdftoppm -scale-to 1400 -png "$midtermRoot/build/report_final/render.pdf" "$midtermRoot/build/report_final/page"
```

逐页查看 PNG，尤其检查标题是否跟随正文、成员行是否跨页。`build_report.py` 同时写出栏目字数与纯文字稿。

## 2. PPT 编辑与导出

本次已经完成用户方案确认与模板导入；重建同一批准方案不需要重新规划页序。`build_deck.py` 只改计划中的 slide-local 内容，保留来源身份和 Master/Layout；`write_notes.py` 写入 18 页备注及独立讲稿。

```powershell
& $midtermPython -X utf8 "$midtermRoot/scripts/build_deck.py"
& $midtermPython -X utf8 "$midtermRoot/scripts/write_notes.py"
& $midtermPython -X utf8 "$pptMasterDir/scripts/stamp_native_fallbacks.py" "$midtermRoot/presentation/authoring-svg-flat" --write
& $midtermPython -X utf8 "$pptMasterDir/scripts/svg_authoring_view.py" "$midtermRoot/presentation/authoring-svg-flat" --refresh-summary
& $midtermPython -X utf8 "$pptMasterDir/scripts/svg_quality_checker.py" "$midtermRoot/presentation" --roundtrip --json
& $midtermPython -X utf8 "$pptMasterDir/scripts/svg_to_pptx.py" "$midtermRoot/presentation" --roundtrip --native-charts-and-tables --primary-language zh-CN
```

图表/表格的 SVG 与 JSON 必须在同一修改中保持同步，再执行 stamp；哈希只绑定两者，不替代语义核对。插入完整截图时使用 plain image，不能保留冗余的 `viewBox="0 0 1 1"` crop wrapper。以上两点已纳入本次最终实现。

导出会打印新的确切路径。下列 `$midtermDeck` 是本次最终路径；重新导出后须替换为工具新打印的路径。

```powershell
$midtermDeck = "$midtermRoot/presentation/exports/presentation_20261030_015340_native_charts_tables.pptx"
& $midtermPython -X utf8 "$midtermRoot/scripts/manual_playback.py" $midtermDeck "$midtermRoot/presentation/exports/presentation_20261030_015340_native_charts_tables_manual.pptx" --skill-dir $pptMasterDir
$midtermDeck = "$midtermRoot/presentation/exports/presentation_20261030_015340_native_charts_tables_manual.pptx"
& $midtermPython -X utf8 "$pptMasterDir/scripts/pptx_delivery_check.py" $midtermDeck > "$midtermRoot/presentation/validation/final.delivery.json"
& $midtermPython -X utf8 "$pptMasterDir/scripts/source_to_md/ppt_to_md.py" $midtermDeck -o "$midtermRoot/presentation/validation/readback.md"
& "$midtermRoot/scripts/render_office.ps1" -InputPath $midtermDeck -OutputDir "$midtermRoot/build/deck_release" -Kind pptx
```

逐页核验原生渲染；检查器提示的接受理由记录在 `QA_REPORT.md`。如果后续内容变化，不应继续沿用原 QA 结论而不复核。

`manual_playback.py` 调用 ppt-master 的共享转场核心，保留原视觉转场与对象动画，移除源模板每页 3 秒的自动翻页并关闭 useTimings；它不手写转场 XML，也不修改母版或文字。

## 3. 证据与正式输出

```powershell
& $midtermPython -X utf8 "$midtermRoot/scripts/finalize_evidence.py" --pptx $midtermDeck --deck-pdf "$midtermRoot/build/deck_release/render.pdf" --report-pdf "$midtermRoot/build/report_final/render.pdf"
```

该脚本核对源文件、论文哈希、指标算术、合成范围诊断、页数、备注、原生图表/表格、Master/Layout 字节一致性；复制到正式中文文件名并更新交付哈希。不调用 LLM，不训练模型，不执行线上请求。

`acquire_papers.py`、`read_papers.py`、`intake.py` 与 `capture_web.cjs` 是本次获取/预处理的历史脚本，保留用于来源追踪。重取网页截图应使用当前可用且获授权的浏览器工具，并重新记录环境和数据范围；不要将历史访问成功当成现在的线上可用性。

## 范围

本次没有执行工作流中列出的新训练、消融、传播图实验、目标服务器测量或财务核账。历史模型验证命令和未来研究步骤在 `../RESEARCH_WORKFLOW.md`，不属于上述文档构建脚本的副作用。
