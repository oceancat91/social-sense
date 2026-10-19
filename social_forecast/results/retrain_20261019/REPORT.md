# 模型比对、重训与部署权重验证

完成日期：2026-10-19。

## 交付结论

已完成真实的完整 `lite` 训练，包含数值骨干、响应头、文本和联合阶段；不是 smoke 初始化。CPU 单进程、2 个计算线程，训练耗时 500.93 秒（约 8 分 21 秒），种子 2025。

模型代码与数据来源为仓库当前实现。压缩包核心模型、层、训练入口、工具与数据共 43 个文件均与仓库相同；压缩包没有正式模型权重，只有一个 smoke 文件。详细比对见 [COMPARISON.md](COMPARISON.md)。

本机原有四个正式/对照权重和旧报告保留；新训练没有替换线上默认模型。

## 新权重

- 完整训练权重：[SocialMedia_log_lite_pl6_L28.pt](../../checkpoints/retrain_20261019/SocialMedia_log_lite_pl6_L28.pt)，500,577,024 字节，约 477.39 MiB。SHA-256：`5dcd5e92532f741e74196d020ce95b688f3192c1c89de48ff71d568e2d58fbc0`。
- 数值推理权重：[SocialMedia_log_lite_pl6_L28_numeric.pt](../../checkpoints/retrain_20261019/SocialMedia_log_lite_pl6_L28_numeric.pt)，247,981 字节，约 242.17 KiB。SHA-256：`445f2f975f350971683f562f53f0c4d1b97cde418fc0be0c3831184020e7e816`。
- 新数值包是从上面的正式训练权重导出，保留 49,373 个数值模型参数、归一化、门控、响应模板、历史缓存与预警校准；只移除数值推理不使用的文本模块。它与大小相近的旧 smoke 权重性质不同。
- CPU 保存时相同文本张量共享存储，因此完整文件比原来的约 955 MiB 包更小；不能仅按文件大小判断是否遗漏模型参数。

## 数据与评估协议

数据共 1,339 天，时间范围 2023-01-01 至 2026-08-31，没有补入 9、10 月数据。目标是 `log1p(OT)`；StandardScaler 仅在训练集拟合。按时间顺序划分训练 937 天、验证 135 天、测试 267 天。

输入窗口 28 天、预测 6 天，对应训练 904、验证 130、测试 262 个窗口。测试窗口互相重叠，不能视为独立样本。

预警使用数值验证集预测涨幅的 75 分位 `0.46937644481658936`，没有用测试集预测分位数替代生产阈值。本次修正了原训练脚本中同名测试诊断指标覆盖生产阈值的问题；模型结构和训练损失不变。

## 独立验证结果

完整权重和数值包均在 `device="cpu", with_text=False` 下重新加载。全部 262 个测试窗口上的 6 步预测、反归一化预测与 T/S/C/R 分量一致，最大标准化预测绝对误差为 **0.0**。数值包内预警阈值与重新计算的 130 个验证窗口分位数完全一致。

后端 `ForecastService` 使用新数值包成功加载并对数据末尾 28 天完成 6 步预测。在独立 Windows CPU 进程中，这次加载与单次预测的峰值工作集约 **265.27 MiB**，当前工作集约 **260.82 MiB**；这不是整套 Linux 服务或并发压力测试。正式 `tests/` 目录的 62 个回归测试通过，后端测试使用隔离内存数据库和离线分析器。

以下指标对应可部署的数值路径，不能与文本辅助训练指标混用：

- 测试集标准化 log 空间 MSE：**1.888591**。
- 最后观测值保持不变的 persist 基线 MSE：**1.524642**。本轮模型误差比该基线高约 **23.87%**，没有在点预测 MSE 上超过基线。
- 方向命中率：**65.53%**，评价 235 个有效窗口，按原协议排除真实变化绝对值最低的 10%。
- 尖峰 AUC：**0.6101**。
- 使用保存的验证集阈值时，尖峰召回率 **39.39%**、精确率 **38.24%**、F1 **0.3881**。
- 测试集 66 个尖峰窗口，发出 68 次预警；TP=26、FP=42、FN=40、TN=154。

尖峰标签按测试集真实未来涨幅的 75 分位定义，仅用于评估。该测试标签口径与生产预警阈值是两回事。旧 README、旧 PDF 和旧结果中的指标不能当作本次重训的实测结果。

文本辅助路径训练记录中的方向命中率为 67.66%、AUC 为 0.6316，MSE 为 1.959960；这些指标不代表轻量数值部署路径。

## 复现与检查

所有命令从仓库根目录执行，使用项目虚拟环境。已存在的 run-id 和导出目标会拒绝覆盖，重新运行请换新名称。

```powershell
.venv\Scripts\python.exe -u social_forecast/scripts/retrain_cpu.py --run-id retrain_20261019 --encoder-dir social_forecast/language_model/openai-community/gpt2 --encoder-revision 607a30d783dfa663caf39e06633721c8d4cfcd7e --seed 2025 --threads 2

.venv\Scripts\python.exe social_forecast/scripts/export_numeric_checkpoint.py --checkpoint social_forecast/checkpoints/retrain_20261019/SocialMedia_log_lite_pl6_L28.pt --output social_forecast/checkpoints/retrain_20261019/SocialMedia_log_lite_pl6_L28_numeric.pt

.venv\Scripts\python.exe social_forecast/scripts/verify_forecast_checkpoint.py --checkpoint social_forecast/checkpoints/retrain_20261019/SocialMedia_log_lite_pl6_L28.pt --numeric-checkpoint social_forecast/checkpoints/retrain_20261019/SocialMedia_log_lite_pl6_L28_numeric.pt --output social_forecast/results/retrain_20261019/deployment_verification.json --threads 2
```

冻结 GPT-2 编码器来自 `openai-community/gpt2` 的固定 revision，不复用旧预测模型参数初始化新预测模型。`--no_ctx` 与原 lite 配置一致，使用词嵌入池化；它并不是跳过文本训练阶段。

原始训练指标见 [metrics.csv](metrics.csv)，数据与源码指纹、配置和时间见 [run_manifest.json](run_manifest.json)，独立验证明细见 [deployment_verification.json](deployment_verification.json)。

## 2GB 服务器使用范围

建议上传数值包并显式指定 checkpoint 路径，CPU 单模型进程运行；不需要把 GPT-2 编码器上传到数值推理服务。示例：

```python
from app.services.forecast_service import ForecastService

service = ForecastService.load(
    "social_forecast/checkpoints/retrain_20261019/SocialMedia_log_lite_pl6_L28_numeric.pt",
    device="cpu",
    with_text=False,
)
```

模型包变小不代表整个服务只占 242 KiB 内存，还需计入 PyTorch、Python、数据库与 Web 服务。没有在目标 Linux 服务器上做峰值内存或并发实测，不能据此保证整套应用在 2GB 内稳定运行。完整文本模型仍保留在本机，数值包不提供完整文本编码能力。

本次没有部署、推送或自动替换生产模型。二进制权重及本地预训练编码器已由 `.gitignore` 排除，需通过独立文件传输交付。
