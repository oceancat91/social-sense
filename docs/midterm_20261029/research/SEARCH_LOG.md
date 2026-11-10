# 文献检索与获取留痕

执行日期：2026-10-29 至 2026-10-30。范围：SocialSense 当前仓库的多平台差异、传播证据、分解预测、文本价值、检索与规则校准。本文记录实际访问结果，不把检索计划写成已经执行的结果。

## 指定入口

用户指定：[Google Scholar Labs 中文入口](https://scholar.google.com/scholar_labs/search?hl=zh-CN)。本次尝试遇到 HTTP 403 / Google 验证跳转；后续桌面内置浏览器访问超时。未绕过验证，未取得可用的 Scholar Labs 结果列表，因此**不能声称已完成该平台检索、排序或覆盖性筛选**。

为不中断已授权的材料制作，后续依据实际代码中的方法与研究缺口，从作者论文原始页面 / arXiv 获取全文。此轮属于有目标的文献研读，不是具有完整检索库、双人筛选、排除统计的系统综述。

## 待 Scholar 恢复后可复用的查询式（计划，未获得该入口结果）

| 研究问题 | 自然语言检索式 |
|---|---|
| 跨平台差异与回音室 | How can echo chambers be measured using polarization and interaction homophily across social media platforms? |
| 传播影响与观测缺失 | Cross-platform information diffusion URL events Hawkes processes missing observations influence estimation |
| 分解预测是否有益 | Time series forecasting seasonal trend decomposition linear baseline exponential moving average patch CNN |
| 突发信号如何处理 | Offline changepoint detection PELT penalty pruning online forecasting look-ahead leakage |
| 状态空间模型的有效条件 | Selective state space Mamba time series forecasting architecture efficient implementation |
| 文本分支是否贡献效果 | Large language models time series forecasting ablation reprogramming text usefulness |
| 如何约束生成结论 | Retrieval augmented generation reasoning acting evidence citation verification |

## 实际获取清单

| ID | 原始来源 | 本地文件 | 状态 |
|---|---|---|---|
| P01 | [arXiv:2004.09603](https://arxiv.org/abs/2004.09603) | `papers/P01_echo_chambers_preprint.pdf` | 2020 预印本，15 页；另一个 PNAS 版本的下载地址返回 403，未将两版混同 |
| P02 | [arXiv:1705.06947](https://arxiv.org/abs/1705.06947) | `papers/P02_web_centipede.pdf` | 已获取 14 页 |
| P03 | [arXiv:2205.13504](https://arxiv.org/abs/2205.13504) | `papers/P03_dlinear.pdf` | 已获取 15 页 |
| P04 | [arXiv:2412.17323](https://arxiv.org/abs/2412.17323) | `papers/P04_xpatch.pdf` | 已获取 25 页 |
| P05 | [arXiv:2312.00752](https://arxiv.org/abs/2312.00752) | `papers/P05_mamba.pdf` | 已获取 36 页 |
| P06 | [arXiv:1101.1438](https://arxiv.org/abs/1101.1438) | `papers/P06_pelt.pdf` | 已获取 25 页 |
| P07 | [arXiv:2005.11401](https://arxiv.org/abs/2005.11401) | `papers/P07_rag.pdf` | 已获取 19 页 |
| P08 | [arXiv:2310.01728](https://arxiv.org/abs/2310.01728) | `papers/P08_time_llm.pdf` | 已获取 24 页 |
| P09 | [arXiv:2406.16964](https://arxiv.org/abs/2406.16964) | `papers/P09_llm_ablation.pdf` | 已获取 28 页 |
| P10 | [arXiv:2210.03629](https://arxiv.org/abs/2210.03629) | `papers/P10_react.pdf` | 已获取 33 页 |

下载时间、URL、页数、SHA256 见 `acquisition.json`。全文提取保存在同名 `.txt`；重点段落在 `*_reading_excerpt.txt`、`*_method_extra.txt` 以及 `P02_hawkes_reading.txt`。`READING_NOTES.md` 标注实际重点研读页，未把保存全文等同逐字读完所有附录。

## 来源选择与保留边界

- 纳入：可定位原文，能直接解释当前代码或下一阶段验证路线；同一主题保留支持与质疑两类研究。
- 当前没有做：覆盖所有数据库、严格去重的检索结果计数、PRISMA 流程、引用量排名、最新工作完整性保证。
- 引用 P01 时使用实际获取的 2020 预印本标题和版本；不把 2021 PNAS 终稿结论补写进未读的版本。
- P08 与 P09 并列，避免只收集支持使用大模型的文献。P03、P09 指向简单基线与消融；它们不证明本项目一定失败，也不证明复杂方法普遍无效。
- 文献中的实验指标均属于各自任务，未转写为 SocialSense 的性能指标。

## 网页配图访问记录

尝试访问 [socialsense.cn](https://socialsense.cn/) 时出现连接关闭，见 `../evidence/web_capture.json`。本次使用仓库前端的本地实际运行页面作为配图，见 `../evidence/local_capture.json`。前端展示内置档案数据，未把该截图作为线上实时采集、后端完整联调或预测服务已上线的证明。
