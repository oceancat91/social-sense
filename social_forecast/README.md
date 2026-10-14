# social_forecast — 社交热度预测 + 事件归因

基于 `ŷ = T̂ + Ŝ + Ĉ + R̂` 分解模型，把社交帖文数据接入短期热度预测与异常归因。
**模型架构零改动**，只做数据与任务适配。

## 目录结构

```text
social_forecast/
├── models/            # 预测模型（架构不变）
├── layers/            # 分解 / 文本 / 冲击 / 残差 各层
├── utils/             # 文本模板 / 路由
├── checkpoint.py      # 训练后导出 / 加载权重包
├── inference.py       # 加载 checkpoint 后推理 API
├── checkpoints/       # *.pt 权重（默认导出目录）
├── test/              # 训练入口（test_event_response_e2e.py）
├── scripts/           # 数据处理与报告
│   ├── aggregate_social.py    # 原始帖文 → 日聚合
│   ├── anomaly_detect.py      # 异常检测 + 归因
│   ├── make_log_target.py     # 生成 log1p 目标
│   ├── llm_reporter.py        # DeepSeek / 模板报告
│   ├── export_smoke_checkpoint.py  # 轻量导出（验证加载）
│   └── run_workflow.py        # 转发到 social-sense 端到端工作流
├── data/
│   ├── SocialMedia.csv         # 模型输入（原始 OT）
│   ├── SocialMedia_log.csv     # 模型输入（log1p OT，推荐）
│   └── social/                 # 聚合 + 异常结果 + 图
├── language_model/    # 本地 GPT-2 编码器（目录联接）
├── results/           # 训练输出 + workflow/
├── MODEL.md           # 模型介绍
├── DIAGNOSIS.md       # MSE 尖峰根因
└── SAFE_RUN.md        # 防黑屏说明
```

## 环境

```text
Python 3.12+（本项目在 3.13 上验证通过；原作者环境为 Anaconda）
torch + transformers + sklearn + pandas + matplotlib + scipy + requests
GPU 可选；笔记本建议看 SAFE_RUN.md
```

这些包**不在** `backend/requirements.txt` 里（只有预测功能需要，不跑预测的部署不必装 torch 这类大依赖）。装法：

```bash
pip install -r social_forecast/requirements.txt
```

> **务必装在项目的虚拟环境里。** 本目录的命令都写作 `python -u …`，前提是虚拟环境已激活；
> 没激活时裸 `python` 会落到系统解释器上，那里通常没有 torch，报错信息也不容易指向真正的原因。
> Windows 不想激活就把 `python` 换成 `.venv\Scripts\python.exe`（相对仓库根目录）。

> ⚠️ **跑异常检测会覆盖已跟踪的产物文件。** `data/social/` 里既有**输入**（`*.csv`，含各平台日度数据）
> 也有**生成物**：`figures/*.png`（三张异常图）和 `report.md`。重跑异常检测/报告会把它们重写，
> 于是 `git status` 会变脏。
>
> 其中 `report.md` 是**用 DeepSeek 生成的那一份**（文件头写着 `生成模型：deepseek-chat`）。
> 用 `--template-llm` 跑会把这份 LLM 报告**降级覆盖成模板版**。只想验证链路、不想动仓库内容的话：
>
> ```bash
> git stash push -- social_forecast/data/social/     # 跑之前先收起来
> python -u workflow/forecast_ai/run_workflow.py --template-llm
> git checkout -- social_forecast/data/social/       # 跑完还原
> ```
>
> 数值结果是确定的：实测重跑后 `anomalies.csv` **一字未变**（15 个异常日完全一致），
> 变的只是图片的字节（matplotlib 版本渲染差异）和报告文本（LLM 版 ↔ 模板版）。

> **权重不在版本库。** `checkpoints/*.pt`（单个约 950 MB）已被 `.gitignore` 排除，新克隆的仓库没有权重。
> 加载器在找不到权重时会给出明确报错，可用 `python -u scripts/export_smoke_checkpoint.py`
> 导出一个轻量权重先把链路跑通。
>
> **密钥也不在版本库。** `social_forecast/.env`（`DEEPSEEK_API_KEY`）已被忽略；只有需要
> DeepSeek 归因报告时才自行创建，其余场景用 `--template-llm` 走模板即可。

## 一键全量实验（推荐）

异常检测 + 文本导出 + 报告 + 安全训练（防黑屏）：

```powershell
cd social_forecast
python -u scripts\run_full_experiment.py --capacity lite --template-llm
```

只要归因、不训模型：

```powershell
python -u scripts\run_full_experiment.py --skip-train --template-llm
```

结果见 `results/FULL_EXPERIMENT_SUMMARY.md`。

### 1. 数据准备（已含，重跑才需要）

```powershell
cd social_forecast

# 原始帖文 → 日聚合（需要原始 all_cleaned.csv）
python scripts\aggregate_social.py

# 异常检测 + 归因
python scripts\anomaly_detect.py

# 生成 log1p 目标（推荐，MSE 不会爆）
python scripts\make_log_target.py
```

### 2. 训练

安全低负载（防黑屏）：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_safe.ps1
```

等价手动命令（log 目标）：

```powershell
$env:ABLATION_GPU_FRAC="0.45"
$env:TEXT_CACHE_BS="2"
python -u test\test_event_response_e2e.py SocialMedia_log `
  --pred_len 6 --calendar short --capacity lite --no_ctx `
  --seq_len 28 --seasonal_period 7 --direction `
  --out results\SocialMedia_log_lite.csv
```

`--direction` 会额外输出预测线的两个核心口径（见下）：方向命中率 + 尖峰预警，无需 MSE 决胜。

结果写入 `results/`，并**自动导出** checkpoint 到 `checkpoints/`：

```text
checkpoints/SocialMedia_log_lite_pl6_L28.pt
checkpoints/SocialMedia_log_lite_pl6_L28.meta.json
```

包内含：`model` / `dssaa` state_dict、配置（seq_len/pred_len/capacity/…）、scaler 统计量、gate 决策、theta、response library 摘要、版本元信息。

禁用导出：`--no_ckpt`；改目录：`--ckpt_dir path`。

轻量冒烟（不完整训练，仅验证加载链路）：

```powershell
python -u scripts\export_smoke_checkpoint.py
```

### 3. 加载推理（可嵌入 social-sense）

```powershell
# 模块 API
python -c "
import sys; sys.path.insert(0, '.')
from checkpoint import load_forecast_model
from inference import predict_window
import pandas as pd
b = load_forecast_model('checkpoints/SocialMedia_log_lite_pl6_L28_smoke.pt')
ot = pd.read_csv('data/SocialMedia_log.csv')['OT'].values
print(predict_window(b, ot[-b.seq_len:]).to_dict())
"
```

主项目适配层：`../backend/app/services/forecast_service.py`（`load_forecast_model` / `predict`）。

端到端 AI 工作流（异常→预测→DeepSeek）：见 [`../workflow/forecast_ai/README.md`](../workflow/forecast_ai/README.md)。

```powershell
python -u scripts\run_workflow.py --template-llm
# 或接 DeepSeek（.env 中 DEEPSEEK_API_KEY，勿写入代码）
python -u scripts\run_workflow.py
```

### 4. 归因报告（可接你自己的 AI）

`scripts/llm_reporter.py` 支持两种后端，**不写死任何厂商、不要 SDK、只依赖 `requests`**：

| 后端 | 说明 | 要 key 吗 |
|---|---|---|
| `ollama` | 本地免费模型 | 否 |
| `openai` | 任意 OpenAI 兼容协议服务 | 看服务 |

**接自己的 AI**：复制 `llm_config.example.json` → `llm_config.json`，key 放进 `.env`（不要写进 json）。

当前默认已配 DeepSeek（`llm_config.json` + `.env` 里的 `DEEPSEEK_API_KEY`）：

```powershell
# 直接出 DeepSeek 归因报告
python scripts\llm_reporter.py --top 10
```

- 本地免费（Ollama）

```json
{ "backend": "ollama", "base_url": "http://127.0.0.1:11434", "model": "qwen2.5:0.5b", "api_key": "" }
```

- 本地免费（LM Studio / vLLM / llama.cpp server，都是 OpenAI 兼容）

```json
{ "backend": "openai", "base_url": "http://localhost:1234/v1", "model": "你的模型名", "api_key": "" }
```

- 云端（DeepSeek / 通义 / Kimi / GLM / OpenAI 官方等）

```json
{ "backend": "openai", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "api_key": "在这里填 key" }
```

也可以命令行速查（无需配置文件）：

```powershell
python scripts\llm_reporter.py --backend deepseek --model deepseek-chat
python scripts\llm_reporter.py --backend qwen --model qwen-plus
python scripts\llm_reporter.py --backend kimi --model moonshot-v1-8k
```

支持速查名：`ollama / lmstudio / vllm / llamacpp / deepseek / qwen / kimi / glm / openai`（映射见脚本内 `BACKEND_HINTS`）。

key 也可用环境变量 `LLM_API_KEY` 传入。

生成报告：

```powershell
python scripts\llm_reporter.py --top 10
```

输出 `data/social/report.md`。未接 LLM 时自动回退模板报告（`--template` 强制模板）。

> 关键：**数值预测/事件触发由本模型做，报告话术由你选的 LLM 做**。改 base_url + model 就能换任何一家，不用改代码。

## 关键说明

- **目标务必用 `SocialMedia_log.csv`**：原始 `OT` 是幂律长尾（max 25166 vs median 95），直接 MSE 会爆（persist MSE≈2842）。根因见 `DIAGNOSIS.md`。
- **叙事重点**：异常检测 + 事件归因；尖峰是信号不是噪声。
- **预测还原**：模型输出在 log 空间，`expm1(ŷ)` 得到原始热度。
- **预测口径**：社交热度高度自相关，persist 在点对点 MSE 下占便宜，因此预测线不拼 MSE，改看
  **方向命中率（65.1% vs persist 12.8%）+ 尖峰预警（recall 74.2% vs persist 0%）**。详见 `MODEL.md` 的「预测口径」。
