# Forecast + AI 工作流

把 `social_forecast` 数值模型与 DeepSeek 归因接入 `social-sense` 主架构。

## 流水线

```text
输入 CSV / 日聚合
   → 异常检测 (anomaly_detect + export_events)
   → 加载 checkpoint 推理 (ŷ=T̂+Ŝ+Ĉ+R̂，方向/尖峰预警)
   → 结构化产物 (forecast_summary.json / events.jsonl)
   → LLM 归因报告 (llm_reporter + DeepSeek；失败→模板)
```

## 一键运行

在 `social-sense/` 根目录：

```powershell
# 1) 若还没有权重：冒烟导出（CPU，秒级）或完整训练
cd social_forecast
python -u scripts\export_smoke_checkpoint.py

# 2) 跑工作流（模板 LLM，不耗 API）
cd ..
python -u workflow\forecast_ai\run_workflow.py --template-llm

# 3) 接 DeepSeek（读 social_forecast/.env 的 DEEPSEEK_API_KEY）
python -u workflow\forecast_ai\run_workflow.py
```

从 `social_forecast/` 也可：

```powershell
python -u scripts\run_workflow.py --template-llm
```

## 产物

| 路径 | 说明 |
| --- | --- |
| `social_forecast/checkpoints/*.pt` | 训练/冒烟导出的权重包 |
| `social_forecast/results/workflow/forecast_summary.json` | 预测结构化摘要 |
| `social_forecast/results/workflow/report.md` | 归因报告副本 |
| `social_forecast/data/social/report.md` | LLM 主报告 |
| `social_forecast/results/events.jsonl` | 异常事件文本 |

## 主架构调用

```python
# Flask / 脚本侧
import sys
sys.path.insert(0, "backend")
from app.services.forecast_service import load_forecast_model, predict

svc = load_forecast_model()          # 自动找最新 checkpoint
out = predict(svc, window_ot_list)   # ŷ + T/S/C/R + direction + spike_warning
```

## 回退策略

| 失败 | 行为 |
| --- | --- |
| 无 checkpoint | 报错并打印训练/冒烟导出命令，`ok=False` |
| LLM / 网络失败 | 自动模板报告，流水线可继续 |
| 无 anomalies 原始表 | 跳过或沿用已有 `anomalies.csv` |

## 完整训练导出 checkpoint

```powershell
cd social_forecast
$env:ABLATION_GPU_FRAC="0.40"
$env:TEXT_CACHE_BS="1"
python -u test\test_event_response_e2e.py SocialMedia_log `
  --pred_len 6 --calendar short --capacity lite --no_ctx `
  --seq_len 28 --seasonal_period 7 --direction
# → checkpoints/SocialMedia_log_lite_pl6_L28.pt
```
