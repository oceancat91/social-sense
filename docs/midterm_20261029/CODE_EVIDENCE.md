# 代码证据、指标口径与改写审计

审阅截止：2026-10-30。以下路径均相对仓库根目录；本次只生成中期材料及研究文档，没有替换业务代码、重新训练模型或将待做实验写成已完成。代码快照的哈希与 Git HEAD 见 `evidence/code_snapshot.json`。

## 1. 关键结论与实际实现

| 证据 ID | 结论及定位 | 能支持什么 | 不能支持什么 |
|---|---|---|---|
| C01 | `agent/agent/orchestrator.py`：`step_*`、`run_linear`、`build_langgraph`、`export_report` | 单平台编排、可选 LangGraph 与线性路径、报告导出 | 仅凭代码存在不能证明全部线上任务稳定成功 |
| C02 | `agent/MultimodalAnalyzer/text_tower.py`：`analyze_text_tower`、TF-IDF、jieba/字二元组 | 当前文本特征与桶间比较 | 名为 MultimodalAnalyzer 不等于图像/视频编码已经实现 |
| C03 | `agent/Conclusion/calib/gates.py`：`_check_g1` 至 `_check_g7` | 独立规则检查趋势、情绪、立场、引用 ID、数值边界、空窗与风险依据 | 规则通过不是事实正确或所有幻觉已消除的证明 |
| C04 | `multiagent/contract.py` 与 `multiagent/align.py` | PlatformReport、时间外连接、保留 None、平台内 z-score | 不是向量级同事件聚类，也不恢复漏采数据 |
| C05 | `multiagent/fuse.py:18`、`:34`、`:120` 附近 | JSD、情绪极差、Pearson 相关及加权差异分数 | 不能仅凭聚合分数证明回音室或真实传播因果 |
| C06 | `multiagent/master.py:163` 起 `_run_cx_gates` | CX1–CX5：平台覆盖、分歧表述、平台引用、断言绑定、空窗 | 平台绑定不等于每条断言内容已经获得证据支持 |
| C07 | `social_forecast/models/rep_moe.py:300` 起分解；`:470` 起预测路径 | T/S/C/R 分解，R=r2−C；EMA 含可学习参数 | 不能称 R 为频谱残差，也不能概括全部分解为无参数固定变换 |
| C08 | `social_forecast/layers/rep_fusion.py:286` 起 | 四路 T/S/C/R pooled 数值表征进入 router；默认 top-k=2 | 不是仅 T/S 路由，也不是文本直接驱动 router |
| C09 | `social_forecast/models/rep_moe.py:560` 起 | 主预测头含 d_base+d_res+d_text，可能叠加事件响应 | “文本绝不进入预测增量”与当前代码不符 |
| C10 | `social_forecast/layers/Mamba_block.py` | 轻量状态空间实现 | 不继承官方 Mamba 优化内核的吞吐或内存性能 |
| C11 | `social_forecast/layers/jump_pelt.py` 与事件特征调用 | 变点/冲击处理实现可查 | 仍需专门审计前缀特征不含未来信息；变点不等于新闻因果 |
| C12 | `social_forecast/scripts/verify_forecast_checkpoint.py` 及 `results/retrain_20261019/deployment_verification.json` | 指定 CPU 数值路径、等价性、切分与指标 | 不覆盖文本开启路径、目标服务器资源、跨话题泛化 |
| C13 | `frontend/src/archives-api.ts`、`frontend/src/archive-loop.ts`、`backend/app/routes/archives.py`、`backend/data/archives.snapshot.json` | 档案接口、交互、内置档案数据；本地前端截图 | 不证明线上抓取、预测和报告的完整链路成功 |
| C14 | `agent/KnowledgeAugmentor/`；编排 `_should_augment` / `step_augment` | 条件触发的知识补充 | 外部知识不应被当作本平台观测统计 |

代码中的文档注释、类名或早期说明若与实际运算不同，以当前调用和数据流为准。以上行号是本次快照的定位提示，代码后续修改时需重新核对。

## 2. 数值部署结果：唯一统一口径

原始记录：`social_forecast/results/retrain_20261019/deployment_verification.json`。本次读取并复核记录，未重新执行高成本训练。完整文本训练结果和早期 `MODEL_ANALYSIS.md` 不混入本次部署页。

| 项目 | 记录值 / 说明 |
|---|---|
| 日期范围与行数 | 2023-01-01 至 2026-08-31，1339 天 |
| 训练/验证/测试行数 | 937 / 135 / 267，按时间排序 |
| 训练/验证/测试窗口 | 904 / 130 / 262 |
| 输入 / 预测 | L=28、P=6；过去 28 天预测未来 6 天 |
| 数值空间 | log1p(OT) 后用仅训练段拟合的 StandardScaler 标准化 |
| 运行条件 | CPU、with_text=False、batch=1、threads=2 |
| MSE | 1.8885908127 |
| 持续值 MSE | 1.5246421099；模型高约 23.87% |
| 方向 | sign(未来均值−起点)；排除真实变化幅度最低 10% 的平坦窗 |
| 方向结果 | 0.6553191489，235 个有效窗口；不等于全部 262 窗口准确率 |
| 尖峰 AUC | 0.6100803958 |
| 尖峰标签 | 真实未来最大增量 > 测试集真实增量 q75=1.6921725273；回溯评价定义 |
| 报警阈值 | 预测未来最大增量 > 保存的验证集 q75=0.4693764448 |
| 混淆矩阵 | TP=26、FP=42、FN=40、TN=154；总计 262 |
| 精确率/召回率/F1 | 38.24% / 39.39% / 38.81% |
| 数值包 | 247981 bytes = 242.17 KiB；49373 个参数 |
| 完整检查点 | 500577024 bytes = 477.39 MiB |
| 等价性 | 全部 262 个测试窗口通过；最大标准化预测绝对差 0；容差 1e-6 |
| 未覆盖 | 重叠窗口不是独立样本；没有跨话题显著性、完整文本路径等价、服务器 RAM/延迟结论 |

尖峰标签的测试集分位数只是回溯定义，不得写成线上预先知道的报警标准。当前记录没有证明全部数据加工均不存在前视问题；后续仍需逐模块审计 PELT、文本发布时间与归一化。方向/AUC 不抵消 MSE 未优于持续值的结果。

## 3. 聚合差异指标的发现

`multiagent/fuse.py` 使用 `0.4×立场项 + 0.3×情绪项 + 0.3×(1−平均相关)`。有效相关系数为负时，最后一项可大于 1，公式总分理论上可到 1.3；没有最终 clamp。因此注释中的“归一化到 [0,1]”不构成实际范围保证。无可用相关时该项按 0 计，也不能解释为“完全一致”。

本次材料将其称作平台差异启发式，不将其量纲写成规范概率或回音室成立程度。后续工作应先澄清得分定义、缺失处理、阈值和敏感性，再决定是否修改实现；本次未悄悄更改评分代码。最小可复核诊断记录见 `evidence/metric_consistency.json`。

## 4. 汇报表的重要纠正

| 原稿/旧材料中的易误导表述 | 修订后的准确表达 |
|---|---|
| 完成多模态分析 | 当前为文本与时序特征分析；图像/视频路径未证实 |
| 跨平台语义聚类与传播图均完成 | 时间对齐和聚合差异已有实现；事件标注、语义对齐、传播图待完善 |
| 信息茧房指数证明传播因果 | 分数只提示平台差异，需互动网络与可追溯关系验证 |
| EMA 完全固定、R 为频谱残差 | EMA 参数可学习；R 为去除其他分量后的代数剩余 |
| router 只看 T/S、文本不进入预测增量 | router 看四路数值表征；完整模型存在门控文本增量 |
| 用完整训练指标描述数值部署包 | 仅使用独立数值验证 JSON；两条路径分开 |
| 数值包很小即服务器低内存 | 文件体积与运行资源分开；资源测量列为后续 |
| 经费建议已获批或已用完 | 7500 为申报预算；原稿调剂建议及实际报销待凭证 |
| 论文/软著已完成 | 无正式回执的内容按拟整理或拟提交表述 |

## 5. 资料与图像证据

- `sources/manifest.json`：用户源文件副本与哈希；原始文档保持不变。
- `evidence/web_capture.json`：官网连接失败记录。
- `evidence/local_archive.png`、`local_detail.png`：仓库前端本地实拍。档案界面中的数量与数据范围不是预测实验样本量。
- `research/acquisition.json`：论文原始来源与 PDF 哈希；重点阅读范围见研读笔记。
- `presentation/validation/readback.md`：导出 PPT 文字回读；以最终 PDF/PNG 视觉检查确认排版。
- `evidence/report_word_counts.json`、`notes_timing.json`：汇报表字数与主讲计时配置；360 秒为排练计划，并非实测演讲耗时。

本次研究与截图没有把用户数据上传到第三方论文或演示服务。仓库中的模型与资料仍保存在本地，未发布、未推送。
