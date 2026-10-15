# checkpoints — 模型权重

**本目录下的权重不进版本库**（`.gitignore` 规则：`checkpoints/*.pt`），因为单个约 950 MB，
而且 GitHub 对单文件有 100 MB 硬限制。新克隆的仓库里只有下面的说明文件和元数据，没有权重。

权重缺失时加载器会给出明确报错；只想验证链路通不通，用 `scripts/export_smoke_checkpoint.py`
在本地生成一个轻量权重即可，不需要下载任何东西。

## 权重清单

| 文件 | 大小 | 说明 |
|---|---:|---|
| `SocialMedia_log_lite_pl6_L28.pt` | 954.6 MB | **主力权重**。log1p 目标，容量 lite，历史窗口 28、预测步长 6。`result/metrics.json` 与 `workflow/forecast_ai` 端到端默认读它。 |
| `SocialMedia_lite_pl6_L28.pt` | 954.6 MB | 非 log 版（原始 OT 尺度）。用于第 7 节的 log/原始对比；实测尖峰 AUC 0.451（反排序），仅作对照。 |
| `SocialMedia_log_lite_pl6_L28_dirgate_baseline.pt` | 954.6 MB | 方向门控基线。 |
| `SocialMedia_log_lite_pl6_L28_msegate_baseline.pt` | 954.6 MB | MSE 门控基线。 |
| `SocialMedia_log_lite_pl6_L28_smoke.pt` | 0.2 MB | 轻量权重（0.2 MB），只为验证「加载 → 推理」链路是否通，不具备预测能力。 |

## SHA256 指纹

权重不进仓库，所以从别处拷来一份后，可以用指纹核对是不是同一份：

```bash
cd social_forecast/checkpoints
sha256sum *.pt          # Linux / macOS
Get-FileHash *.pt -Algorithm SHA256   # Windows PowerShell
```

| 文件 | SHA256 |
|---|---|
| `SocialMedia_log_lite_pl6_L28.pt` | `95b0a5f5677d56cace313fe48a338611c895749e5701515765a4b8028c73d6ae` |
| `SocialMedia_lite_pl6_L28.pt` | `9eaa3a8b5f8cab82ed3080300660b7ff3b40219a0cd2d2766348f2806aaf91cf` |
| `SocialMedia_log_lite_pl6_L28_dirgate_baseline.pt` | `c49be83e3229bb3fdafd7ef9be808ccf24b6674530798a43e5244d8cda324645` |
| `SocialMedia_log_lite_pl6_L28_msegate_baseline.pt` | `5da28250d94841ebd5cf77b2f6e3f8074830a511b2bee1b04d6825c261c0c251` |
| `SocialMedia_log_lite_pl6_L28_smoke.pt` | `b3201229c2cd6c6f2944407abdb842451197fac6888a0ef606a37b58c5825036` |

## 元数据（这些在版本库里）

| 文件 | 内容 |
|---|---|
| `*.meta.json` | 每个权重的训练配置与协议（窗口长度、步长、容量、seed 等） |
| `SocialMedia_log_lite_pl6_L28.pt.spike_calib.json` | 生产尖峰阈值标定结果 `pred_gain_q75 = 0.477`，由 `scripts/calibrate_spike.py` 在历史序列上滚动预测得到 |

## 从零得到一份可用权重

```bash
# ① 只为验证链路（0.2 MB，秒级，不需要任何下载）
python -u social_forecast/scripts/export_smoke_checkpoint.py

# ② 完整训练（耗时长，需 GPU 更佳；见 social_forecast/README.md「一键全量实验」）
cd social_forecast
python -u scripts/run_full_experiment.py --capacity lite
```

## 内存提示

一个 954 MB 的权重文件里，实际只有约一半会被加载：

```
model_state    477.4 MB   ← 纯数值通路，服务实际加载
dssaa_state    477.1 MB   ← 文本语义编码器，with_text=False 时不加载
```

所以服务常驻内存约 0.8 GB（含 torch 运行时），`torch.load` 读整个文件的瞬间峰值约 1.5 GB。
部署到小内存服务器前请先确认这一点。
