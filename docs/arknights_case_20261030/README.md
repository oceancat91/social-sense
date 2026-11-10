# SocialSense 答辩 PPT：案例融入版

2026-10-30，根据用户“只保留与项目紧密相关的部分，让答辩更直观”的要求，仅在原演示稿 **第 2、5、6 页**加入说明性案例。保留创新训练类、12 页主讲 + 6 页备份、6 分钟汇报 + 4 分钟问答安排。

## 使用文件

- [答辩 PPTX](deliverables/SocialSense_中期答辩_案例融入版.pptx)：可编辑，含 18 页备注，手动翻页。
- [PDF 预览](deliverables/SocialSense_中期答辩_案例融入版.pdf)：PowerPoint 原生渲染，18 页。
- [同步讲稿与问答](deliverables/六分钟讲稿与四分钟问答_案例融入版.md)：每页时间预算及案例相关追问。

## 案例如何服务技术介绍

| 页面 | 直观例子 | 对应项目内容 |
|---|---|---|
| 2 | 同一句梗跨平台传播，声量、语境和立场可能不同 | 统一 PlatformReport、时间对齐、平台差异比较及溯源边界 |
| 5 | “笑飞了”可能表达开心，也可能是反讽 | G1—G7 / CX1—CX5 的一致性校准、引用约束及人工复核 |
| 6 | 长期讨论、周期活跃、突然走红、其余波动 | T/S/C/R 四分量及稀疏专家融合，说明预测结构 |

案例来自用户提供的《方舟七年梗文化观察-文字整理.md》，仅作情境说明。没有将原文当作已采集的社交数据，也没有新增案例实验成绩。第 7 页仍使用原有数值路径实验。游戏发展史、玩法清单、运营策略、厂商与人物评价未加入答辩。

第 5 页不声称规则能够识别反讽或保证引用内容真实；第 6 页的类比不等于对真实热度成因的识别。TF-IDF 文本特征、时间对齐、G/CX 规则及四分量模型的代码依据见 [来源记录](evidence/case_provenance.json)，既有完整代码审计见 [CODE_EVIDENCE](../midterm_20261029/CODE_EVIDENCE.md)。

## 复核与复现

使用用户指定的 [ppt-master](https://github.com/hugohe3/ppt-master) 原生往返流程：重新导入已交付 PPT，仅改三页的 Slide-local 对象。来源 deck、材料副本、页面映射、工具回执和质量记录均保留。

- [页面方案](CASE_PLAN.md)
- [质量核验](QA_REPORT.md)
- [最终核验 JSON](evidence/final_verification.json)
- [文件哈希](evidence/deliverable_manifest.json)

制作入口为 `scripts/integrate_case.py`，它只更新三页及对应备注；之后运行 ppt-master 的 `svg_authoring_view.py --refresh-summary`、`svg_quality_checker.py --roundtrip --json`、`svg_to_pptx.py --roundtrip --primary-language zh-CN`。渲染使用原任务的 `../midterm_20261029/scripts/render_office.ps1`，同时将来源 PPT 渲染到 `build/source_rendered`。最后把导出器打印的确切 PPTX 路径传给 `scripts/finalize.py`。

本轮最终导出记录：`exports/arknights_case_20261030_20261030_130334.pptx`。正式使用以 `deliverables/` 下文件为准。上一版答辩 PPT 和中期汇报表保留在原交付目录。
