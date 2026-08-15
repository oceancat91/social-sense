# 多平台多 Agent 架构层

> **定位**：承接各平台单 Agent 产出的「平台报告」，完成 **对齐 → 融合 → 主控归纳**，输出跨平台终裁 CT。
>
> **三大创新落点**：
> - **工程创新**：主控 Agent + 平台 Agent 的层次化多 Agent 架构，靠统一「消息契约」解耦；
> - **学术创新**：平台内单个 Skill 的精准度（见 `agent/` 的 Skill1–6）；
> - **社会价值**：用可量化的「茧房指数」暴露同一话题在不同平台舆论场的分裂，打破平台私域信息茧房。

---

## 一、架构总览

```text
                         ┌────────────────────────────┐
                         │      主控 Agent (master)    │
                         │  跨平台归纳 + CX1–CX5 门禁   │
                         └────────────┬───────────────┘
                                      │ 融合指标 + 对齐结果
                          ┌───────────┴───────────┐
                          │      融合器 (fuse)      │
                          │ 分歧度量 + 茧房指数      │
                          └───────────┬───────────┘
                                      │ AlignedBundle
                          ┌───────────┴───────────┐
                          │      对齐器 (align)     │
                          │ 时间轴对齐 + z-score 归一 │
                          └───────────┬───────────┘
                                      │ PlatformReport × N
        ┌──────────────┬──────────────┼──────────────┬──────────────┐
        ▼              ▼              ▼              ▼
  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
  │ B站 Agent │   │ 微博 Agent│   │ 抖音 Agent│   │ 小红书 Agent│
  │ (Skill1–6)│   │ (Skill1–6)│   │ (Skill1–6)│   │ (Skill1–6)│
  └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

- **平台 Agent**：每个平台一套「Skill1–6」全链路（单平台编排见 `agent/agent/orchestrator.py`，支持 LangGraph），最终产出符合契约的 `PlatformReport`。
- **消息契约**：`contract.py` 定义 `PlatformReport` schema，是平台 Agent 与主控层之间**唯一**的数据接口。
- **对齐器**：把各平台时间轴对齐（外连接、缺失空窗、不插值），对不可比的互动/热度做**平台内 z-score** 归一。
- **融合器**：计算立场/情绪/声量共振的跨平台分歧，输出「茧房指数」。
- **主控 Agent**：汇总各平台 OT₁ + 融合指标，产出跨平台共识/分歧/风险的结构化终裁 CT，并执行 CX 门禁。

---

## 二、消息契约（PlatformReport）

单平台 Agent 跑完后用 `export_report()` 产出（见 `agent/agent/orchestrator.py`），字段如下：

| 字段 | 说明 |
|------|------|
| `schema_version` | `platform_report_v1` |
| `platform` / `keyword` / `time_range` / `granularity` | 任务标识（对齐轴） |
| `meta` | 平台级元信息（`n_text`、`empty_ratio`、`stance_global`、`bias_score`、`sentiment_global_mean`…） |
| `D_ts` | 粒度桶级时序（`volume/heat/sent_mean/stance_*_ratio/bias_proxy/controversy/is_empty`） |
| `stance_dist` | 全局立场分布 `{support, oppose, neutral, mixed, unclear}` |
| `top_tags` | 高频议题标签 |
| `skill3` | 异常点 + `need_recrawl` |
| `OT1` | 单平台严格校准后的结论（含 `summary_analysis` / `claim_*` / `risk_flags`） |

**对齐原则**：以 `keyword + time_range + granularity` 为轴；缺失平台填空窗帧，**禁止用邻平台插值冒充本平台观测**。

---

## 三、融合指标与「茧房指数」

| 指标 | 含义 |
|------|------|
| `stance_divergence` | 各平台立场分布的 Jensen-Shannon 散度 |
| `sentiment_divergence` | 各平台情绪均值的极差 |
| `mean_volume_corr` | 各平台声量时间序列的 Pearson 相关（共振强度） |
| `dominant_stance` | 各平台主导立场 |
| **`echo_chamber_score`** | **信息茧房指数 [0,1]**：主导立场对立、情绪分歧、声量无共振 → 越接近 1 |

```text
echo_chamber = 0.4·max(立场分歧, 主导立场冲突) + 0.3·情绪分歧 + 0.3·(1 − 声量共振)
```

**社会价值叙事**：当同一话题在不同平台出现「主导立场对立 + 情绪反向 + 声量不共振」时，即证明**平台私域各自形成回音室**，本层用硬指标把这一现象定量呈现，供上层做「破茧」干预（跨平台对照、风险提示）。

---

## 四、主控 Agent 输出（CT）

```text
CT_status     # accepted | single_platform | failed_calibration | failed
scope         # cross_platform | single_platform
platforms[]   # 参与平台
summary       # 跨平台归纳（自然语言）
claims[]      # 结构化断言，每条绑定 (platforms, evidence)
risk_flags[]  # 争议/偏见/茧房风险
echo_chamber  # 茧房指数与分量
calibration   # CX1–CX5 门禁结果
```

### 跨平台校准门禁（CX）

| 门禁 | 规则 |
|------|------|
| CX1 平台覆盖 | ≥2 平台才允许跨平台结论；否则降级 `single_platform` |
| CX2 分歧诚实 | 不得夸大（强断言 vs 低指数）或漏报（高指数却无分歧表述）茧房 |
| CX3 禁跨平台幻觉 | 断言引用的平台必须在报告集合内 |
| CX4 证据可溯源 | 每个断言须绑定 ≥1 平台证据 |
| CX5 空窗诚实 | 全平台空数据时不得出强结论 |

---

## 五、用法

```bash
# 各平台 Agent 先各自产出平台报告（B 站示例）
python -m agent.agent.orchestrator --topic 科比去世   # → agent/agent/outputs/platform_report_*.json

# 主控层：对齐 → 融合 → 归纳
python -m multiagent --reports bili.json weibo.json --out cross.json
python -m multiagent --reports-dir path/to/reports/ --no-llm   # 纯确定性归纳

# 编程调用
from multiagent import run_master
ct = run_master([bili_report, weibo_report], use_llm=True)
```

---

## 六、目录

| 文件 | 职责 |
|------|------|
| `contract.py` | PlatformReport 契约 + 规范化 |
| `align.py` | 时间轴对齐 + z-score 归一 |
| `fuse.py` | 跨平台分歧 + 茧房指数 |
| `master.py` | 主控 Agent：归纳 + CX 门禁 |
| `pipeline.py` / `__main__.py` | CLI 入口 |
| `llm.py` | DeepSeek 客户端（叙事层，可降级为确定性模板） |
