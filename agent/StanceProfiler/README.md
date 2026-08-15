# StanceProfiler（平台立场画像 Skill）

吃进 PlatformCrawler 洗好的评论文本，给每条评论打上**立场 / 情绪 / 议题标签**，再汇总成平台级「舆论画像」，并**刷新**标准数据包 `D_platform`。

它是数据源层的 **Skill 2**，和 Skill 1（`PlatformCrawler`）一起，才算把「时序 + 文本」数据集做完整。  
字段口径以项目根目录 [`DATASET_SPEC.md`](../DATASET_SPEC.md) 为准。

> **状态**：已实现（默认 `lexicon` 标注器）。  
> 正式跑完后 `D_meta.ext.stance_provisional=false`，并可用 `--to-dataset` 归档到 [`dataset/`](../dataset/)。

---

## 它和 PlatformCrawler 怎么分工？

```text
PlatformCrawler（Skill1）
  · 搜索 / 爬评论 / 清洗 C1–C8
  · 先凑出一版 D_platform（立场可能是临时的）
        │
        ▼
StanceProfiler（Skill2）  ← 你在这里
  · 给每条有效文本标注立场、情绪、议题
  · 算平台偏见、阵营占比、关键词簇、置信度
  · 重算 D_ts 里依赖情绪/立场的指标
  · 写出 stance_profile + 刷新后的 D_platform
        │
        ▼
后面的异常分析 / LLM 总结，认这份「正式画像」后的数据
```

| | PlatformCrawler | StanceProfiler |
|--|-----------------|----------------|
| 主业 | 采集 + 清洗 + 时间轴 | 立场情绪画像 + 刷新数据集 |
| 输入 | 关键词、时间窗 | 已有 `D_platform` 或清洗后文本 |
| 输出 | 初版 `D_platform` | `stance_profile` + 正式版 `D_platform` |

---

## 它能干什么？

对**单平台、单话题、某一时间窗**回答这类问题：

1. **整体站哪边？** 支持 / 反对 / 中性 / 混杂（`stance_global`）  
2. **情绪偏暖还是偏冷？** 全局与分时段情绪均值  
3. **吵不吵？** 正反是否胶着（争议度、阵营占比）  
4. **偏不偏？** 相对中性的偏见强度（`bias_score`）  
5. **大家在聊什么点？** 核心关键词 / 议题簇  
6. **哪些评论适合当证据？** 提高或校正 `evidence_weight` 中的立场置信部分  

空数据时不报错：输出中性空画像 + 完整空时间轴（与规范一致）。

---

## 输入 / 输出（契约）

### 输入（任选一种）

1. **推荐**：Skill1 产出的 `D_platform.json`  
2. 或：Skill1 的 `raw_clean_bundle`（清洗后记录列表）+ 任务元信息（`platform/keyword/time_range/granularity`）

### 输出 1：`stance_profile`（画像摘要，给人看、也给 LLM 用）

```text
stance_global          # support | oppose | neutral | mixed | unclear
bias_score             # [0,1] 偏见强度
confidence             # [0,1] 画像置信
sentiment_global_mean  # [-1,1] 可选
sentiment_dist         # 情绪分布摘要，如 pos/neu/neg 占比
stance_ratios          # 各立场占比
keyword_clusters[]     # 核心关键词/议题簇（词 + 权重 + 代表评论 id）
n_labeled              # 成功标注条数
model_version          # 本 Skill 版本号
```

### 输出 2：刷新后的 `D_platform`

必须覆写 / 重算至少这些位置：

| 位置 | 字段 |
|------|------|
| `D_text` 每条 | `stance_label`, `sentiment_score`, `topic_tags`；并更新与立场置信相关的 `evidence_weight` |
| `D_ts` 各桶 | `sent_mean`, `sent_std`, 立场占比, `bias_proxy`, `controversy` |
| `D_meta` | `stance_global`, `bias_score`, `confidence`, `sentiment_global_mean` |
| `D_meta.source_skill_versions.stance_profiler` | 正式版本号，如 `stance_profiler_v1` |
| `D_meta.ext.stance_provisional` | 设为 `false` |

**不要改坏**：`content_id`、时间轴桶集合、`volume`/`heat` 的原始聚合口径（除非规范升级）。清洗规则版本保持 Skill1 的 `clean_rule_version`。

指标公式继续遵守 [`DATASET_SPEC.md`](../DATASET_SPEC.md) §6（`controversy=4pn`、`bias_proxy`、加权 `sent_mean` 等）。

---

## 人怎么用（实现后的目标命令）

仍在 **`pytorch` 根目录**执行。

### 最常用：给已有 D_platform「盖章」正式画像

```powershell
python -m StanceProfiler.pipeline --in PlatformCrawler\outputs\D_platform_xxx.json --out StanceProfiler\outputs\D_platform_xxx_stanced.json
```

可选同时导出画像摘要：

```powershell
python -m StanceProfiler.pipeline --in ...\D_platform_xxx.json --out ...\D_platform_xxx_stanced.json --profile-out StanceProfiler\outputs\stance_profile_xxx.json
```

### 和采集串起来（推荐业务顺序）

```powershell
# 1) 先采集
python -m PlatformCrawler.pipeline 话题词 --since 2026-08-01 --until 2026-08-15 --max-videos 3

# 2) 再画像（把上一步生成的 json 路径填进来）
python -m StanceProfiler.pipeline --in PlatformCrawler\outputs\D_platform_话题词_....json --out StanceProfiler\outputs\D_platform_话题词_stanced.json
```

### 归档到 dataset/（单事件正式库）

```powershell
python -m StanceProfiler.pipeline --in PlatformCrawler\outputs\D_platform_xxx.json --to-dataset --event-title "事件可读名" --description "一句话说明"
```

会写入 `dataset/events/<event_id>/`（`meta.json` + `D_platform.json` + `stance_profile.json`），并更新 `dataset/INDEX.md`。详见 [`dataset/README.md`](../dataset/README.md)。

### 只看画像、不写文件

```powershell
python -m StanceProfiler.pipeline --in ...\D_platform_xxx.json --dry-run
```

---

## 目录规划（实现时按此落地）

```text
StanceProfiler/
├── README.md              ← 你正在看的说明
├── pipeline.py            ← 命令行入口：读入 D_platform → 画像 → 写出
├── profiler.py            ← 核心：逐条标注 + 汇总 stance_profile
├── labelers/              ← 可插拔标注器（规则 / 模型 / LLM）
│   ├── base.py
│   ├── lexicon.py         ← 增强词表（替换 stance_lite）
│   └── ...                ← 后续可接分类模型
├── recompute.py           ← 按 DATASET_SPEC 重算 D_ts / D_meta
├── validate_hook.py       ← 调用/复用规范校验
└── outputs/               ← 画像结果与刷新后的 D_platform
```

---

## 标注标签约定（必须统一）

| `stance_label` | 含义 |
|----------------|------|
| `support` | 支持 / 正向站队 |
| `oppose` | 反对 / 负向站队 |
| `neutral` | 中性陈述 |
| `mixed` | 同条内多立场混杂 |
| `unclear` | 无法判定 |

| `sentiment_score` | 含义 |
|-------------------|------|
| `+1` 附近 | 明显正向情绪 |
| `0` | 情绪平淡 |
| `-1` 附近 | 明显负向情绪 |

注意：**立场 ≠ 情绪**。  
例如「很失望地支持改革」可能 `support` + 负向情绪；实现时不要用情绪分数粗暴代替立场。

---

## 空数据与边界

| 情况 | 行为 |
|------|------|
| `D_meta.is_empty=true` 或 `D_text` 无有效文本 | `stance_global=neutral`，`bias_score=0`，低 `confidence`；不中断 |
| 单条无法判定 | `unclear`，低置信，仍保留文本 |
| 输入 JSON 缺字段 / schema 不对 | 应报错并提示先跑 PlatformCrawler 或校验规范 |

---

## 和下游怎么衔接

- **Skill3 多模态分析**：用刷新后的 `D_ts`（情绪/争议更可信）  
- **Skill5/6 LLM**：Prompt 里优先引用 `stance_profile` + `D_meta` 立场字段；分析叙述仍须引用 `evidence_ids`  
- **Skill4 RAG**：入库时带上正式 `stance_label`，便于按阵营检索  

---

## 实现原则（给后续写代码用）

1. **可插拔**：默认词表/规则可跑通；预留模型标注器接口，不把死规则写进 pipeline。  
2. **可复现**：同一输入 + 同一 `model_version` → 同一输出（随机性需固定种子）。  
3. **可审计**：`stance_profile` 与 `D_meta.ext` 记录版本、标注器名称、失败条数。  
4. **不破坏契约**：输出必须通过 `DATASET_SPEC` 校验（可复用 `PlatformCrawler.dataloader.validate`）。  
5. **替换临时标签**：明确清除 `stance_provisional`，避免下游误用 `stance_lite`。

---

## 常见误解

**「PlatformCrawler 已经出了立场，还要 StanceProfiler？」**  
采集里的是**占位**，保证流水线不断；正式舆情分析应以 StanceProfiler 结果为准。

**「StanceProfiler 会重新爬 B 站吗？」**  
不会。它只读本地 `D_platform`（或清洗结果），不负责登录和爬虫。

**「只跑 StanceProfiler、不跑采集行不行？」**  
可以，前提是你已有合规的 `D_platform.json`。

---

## 下一步

- 可替换/增加标注器（分类模型、LLM），保持 `BaseLabeler` 接口即可  
- 与 PlatformCrawler 一键串联（采集后自动画像并 `--to-dataset`）  
- 对空包 / 非空包持续做回归校验
