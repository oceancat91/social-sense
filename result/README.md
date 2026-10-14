# 实验结果

这里放社交热度预测的**决策口径实验报告**和出图。完整叙述在 [MODEL_ANALYSIS.md](MODEL_ANALYSIS.md)。模型结构见 `social_forecast/MODEL.md`。

日期：2026-10-12。权重：`social_forecast/checkpoints/SocialMedia_log_lite_pl6_L28.pt`。数据：`SocialMedia_log`，1339 天，历史 28 天，预测 6 天。

## 先看这几个数

测试集后 20% 重算（纯数值推理，262 个窗口）。persist 是「明天还是今天」的平线。

| 指标 | 本模型 | persist |
|---|---:|---:|
| 方向命中率 | **64.3%** | 0.0% |
| 尖峰排名预警召回（预测涨幅前 66 名） | **39.4%** | — |
| 尖峰 AUC | **0.608** | 0.500 |

含事件文本、按方向/AUC 选通路的训练日志更高：方向命中 **66.8%**，尖峰 AUC **0.633**。用真实涨幅的绝对阈值去卡预测，召回只有约 3%，所以线上不用那个阈值。

线上尖峰阈值是历史预测涨幅的 75 分位 **0.477**（`checkpoints/*.spike_calib.json`，来源 `rank(calib)`）。异常检测是滚动 MAD 尖峰加上 PELT 水平跃迁，阈值 z>3，共 **40** 个异常日（尖峰 26 / 跃迁 12 / 兼具 2）。

## 目录

| 文件 | 内容 |
|---|---|
| [MODEL_ANALYSIS.md](MODEL_ANALYSIS.md) | 实验报告：方向、尖峰、窗口消融、四分量、log/原始对比、闭环 |
| [metrics.json](metrics.json) | 上表数字的机器可读版本，由 `build_report.py` 写出 |
| [figures/](figures/) | 报告里的 7 张图 |
| [build_report.py](build_report.py) | 加载 checkpoint，重算测试集并覆盖报告与图 |

图：

| 文件 | 图 |
|---|---|
| `figures/01_decision_metrics.png` | 方向命中、排名召回、AUC、排名 F1，对照 persist |
| `figures/02_window_ablation.png` | L=8 与 L=28 |
| `figures/03_forecast_product.png` | 最近 90 天 + 未来 6 日预测 |
| `figures/04_components.png` | T 主导的堆叠，以及 S/C/R 放大 |
| `figures/05_direction_scatter.png` | 预测变化对真实变化 |
| `figures/06_rolling_forecast.png` | 测试段滚动 6 日均值 |
| `figures/07_anomaly_timeline.png` | 异常日，按尖峰 / 跃迁 / 兼具着色 |

闭环产物不在本目录，在 `social_forecast/results/workflow/`：`forecast_summary.json`、`report.md`（DeepSeek）、`workflow_result.json`。

## 复现

在 `social-sense/` 下：

```powershell
python -u result\build_report.py
```

会重写 `MODEL_ANALYSIS.md`、`metrics.json` 和 `figures/`。异常图读的是已经跑完的 `social_forecast/data/social/anomalies.csv`。要连异常和归因一起重跑：

```powershell
python -u workflow/forecast_ai/run_workflow.py
python -u result\build_report.py
```

第一条会调 DeepSeek（`social_forecast/.env` 里的 key）。没有 key 时加 `--template-llm`，报告退回模板。

仪表盘：启动 backend 后打开 `/forecast`。
