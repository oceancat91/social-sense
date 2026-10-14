# 全量实验说明（异常检测 + 文本归因为主）

## 主叙事

1. **异常检测**：滚动中位数 + MAD 稳健 z（log1p 空间），阈值 3.0  
2. **文本归因**：每个异常日附带 top-k 帖文 + 平台分布 → `events.jsonl` / LLM 报告  
3. **模型适配**：架构不变；PELT 为空时用异常日回填冲击库，使 `Ĉ` + 文本路由能工作  
4. **预测**：log1p 目标，安全低负载训练（辅助，不是主交付）

## 安全设置

- `ABLATION_GPU_FRAC=0.40`
- `TEXT_CACHE_BS=1`
- `--capacity lite --no_ctx`

## 产出

| 文件 | 内容 |
|---|---|
| `data/social/anomalies.csv` | 逐日 z 分数 + 是否异常 |
| `results/events.jsonl` | 异常事件 + 完整 fact 文本 |
| `data/social/report.md` | 归因报告（模板/LLM） |
| `results/SocialMedia_log_lite_full.csv` | 训练指标 |
| `results/train_full_log.txt` | 训练日志 |
