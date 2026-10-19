# 压缩包与仓库模型比对

比对日期：2026-10-19。仓库基线：`4402462`（本次重训修改之前）。

输入压缩包：`D:/HuaweiMoveData/Users/32002/Desktop/social-sense (2).zip`。
SHA-256：`6feff946fa07c789584813bc6e1650b74498e920193451755d2d902ea4ef7a3b`。

## 核心结论

压缩包不是新的模型实现。`social_forecast/models/`、`layers/`、原有 `test/` 训练代码、`utils/` 和 `data/` 共 43 个文件与仓库逐字节相同，训练数据、模型结构和原有训练算法均一致。

压缩包没有正式训练得到的 `.pt` 权重；唯一权重是 `SocialMedia_log_lite_pl6_L28_smoke.pt`（236,258 字节），仅用于测试加载链路。`.meta.json`、`.pt.spike_calib.json`、结果 CSV 和训练日志都不能替代正式权重。

本机工作区另有此前的四个正式/对照 checkpoint，均不在 Git 跟踪中；本次保留它们，新训练单独写入 `checkpoints/retrain_20261019/`。

## 模型相关差异

对 `social_forecast/`、`workflow/forecast_ai/` 和 `result/` 的安全文件比对共 101 项：85 项完全相同，14 项不同，1 项仅压缩包内存在的 PDF，1 项 smoke 二进制权重。忽略 Python 缓存、密钥配置和编译产物。

- 压缩包多个命令写死 `D:\Anaconda\python.exe`；仓库改成虚拟环境中的 `python`。实际执行变化仅在 `social_forecast/run_safe.ps1`；其他主要是说明文字和错误提示。
- 仓库 `social_forecast/README.md` 增加了独立依赖安装、虚拟环境、输出覆盖行为和权重不入库等说明。
- `workflow/forecast_ai/pipeline.py`、`run_workflow.py` 的预测流程没有算法差异，只是复现命令的解释器路径不同。
- `result/build_report.py`、`MODEL_ANALYSIS.md`、`README.md` 的差异也是复现命令路径；报告计算逻辑没有变化。
- 压缩包的 `results/workflow/` 保存了另一轮运行的路径、时间和报告产物，这些不是模型参数。
- 压缩包多了 `result/效果分析.pdf`；仓库额外提供 checkpoint 清单、预测依赖文件和可选依赖测试配置。

## 整体项目布局差异

压缩包还包含整个项目、`.git/` 和大量前端文件，并非只含模型源码。它沿用较早的根目录布局；当前仓库已将环境配置归入 `config/`，部署配置归入 `deploy/`，贡献说明和许可归入 `docs/`，测试配置归入 `tests/`。后端配置读取、部署脚本及部分页面也因此不同。没有使用压缩包覆盖当前项目。

压缩包包含 `.env` 和本地 LLM 配置。本次未读取其值，也未将它们覆盖到工作区。

## 本次重训约定

- 使用仓库现有正式训练入口，不运行会覆盖既有图表、事件和归因报告的全量工作流。
- 使用现有 1,339 天数据（2023-01-01 至 2026-08-31）；不声称已补齐 9、10 月数据。
- 按时间划分训练、验证和测试集，分别为 937、135、267 天；28 天输入、6 天预测对应 904、130、262 个窗口。
- 配置为 CPU、2 个计算线程、`lite`、batch 4、种子 2025、周周期 7、`--no_ctx`。包含完整数值、文本和联合训练阶段；`--no_ctx` 使用冻结 GPT-2 的词嵌入池化，不是跳过文本训练。
- 冻结编码器来自 `openai-community/gpt2`，固定 revision `607a30d783dfa663caf39e06633721c8d4cfcd7e`，不复用旧预测模型权重初始化新预测模型。
- 修正一处指标保存覆盖：生产 `pred_gain_q75` 保留数值验证集结果，测试集文本诊断阈值另存 `test_text_pred_gain_q75`。模型结构与训练损失不变。
- 重训记录见 `run_manifest.json`、`training.log` 和 `metrics.csv`；权重是否可用以导出后的独立加载、测试集推理与轻量导出等价校验为准。
