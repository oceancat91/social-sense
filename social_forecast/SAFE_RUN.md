# 防黑屏 / 死机说明

## 原因

上次日志停在：

```text
---- text cache + DS-SAA ----
[text-cache] train: N=924 ...
  train 408/924
```

此时正在用 **GPT-2 对每条窗口编码文本**，显卡瞬时占用很高，容易触发驱动重置 → 黑屏。

数值骨干 stage1（纯时序）本身较轻，一般不会炸。

## 推荐：安全脚本

在 `social_forecast` 目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_safe.ps1
```

做了这些事：

| 设置 | 作用 |
|---|---|
| `ABLATION_GPU_FRAC=0.45` | 最多占约 45% 显存 |
| `TEXT_CACHE_BS=2` | 文本编码 batch 很小 |
| `--capacity lite` | batch=4，epoch 减半 |
| `--no_ctx` | 不用多层 GPT-2 隐状态，轻很多 |
| 编码后 `empty_cache` | 降低碎片堆积 |

## 仍不稳时

1. **关掉其他占 GPU 的程序**（浏览器硬件加速、游戏、另一个 PyTorch）。
2. 把 `TEXT_CACHE_BS` 改成 `1`（最慢但最稳）。
3. 临时只用数值骨干（不跑文本）：可自行改脚本跳过 stage2/3，或设 `--force_silent_C` 并后续再加「无文本」入口。
4. 训练时**不要同时开多个大模型 / 多标签页视频**。

## 手动等价命令

```powershell
cd social_forecast
$env:ABLATION_GPU_FRAC="0.45"
$env:TEXT_CACHE_BS="1"
python -u test\test_event_response_e2e.py SocialMedia `
  --pred_len 6 --calendar short --capacity lite --no_ctx `
  --out results\SocialMedia_lite.csv
```
