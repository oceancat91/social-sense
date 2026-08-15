# 数据集规范：`D_platform`（多平台舆情对齐契约）

> **版本**：`dataset_schema_v1`  
> **适用范围**：单平台数据源 Skill（PlatformCrawler + StanceProfiler）联合产出；上层多平台对齐、多模态时序文本模型、LLM 概括分析与校准门禁的统一输入。  
> **关联文档**：`README.md`（Skill 与 Pipeline）；清洗规则以 README Skill1「C1–C8」为准。  
> **首期平台**：`bilibili`（字段契约跨平台不变，平台差异仅进入 `ext`）。

---

## 1. 设计目标

1. **可对齐**：不同平台在同一 `keyword + time_range + granularity` 轴上可外连接，不因字段名/口径漂移导致无法融合。  
2. **可溯源**：每条文本、每个时序桶可回溯到平台原始 ID；结论侧引用必须落在本数据集内。  
3. **可空不断轴**：无数据时段保留占位帧，禁止删桶导致时间轴错位。  
4. **服务舆情主题**：核心指标覆盖 **声量、热度、情绪、立场、争议、传播代理、证据可信度**。  
5. **定量与定性分离**：`D_ts` 供模型计算；`D_text` 供语义与 LLM 概括；`D_meta` 供任务级对齐与门禁。

---

## 2. 顶层对象

```text
D_platform = {
  "schema_version": "dataset_schema_v1",
  "D_meta":  { ... },   // 任务与全局画像元数据
  "D_text":  [ ... ],   // 样本级文本记录（可空列表，但空任务须有占位策略，见 §7）
  "D_ts":    [ ... ]    // 粒度桶级时序记录（时间轴必须完整）
}
```

| 键 | 必填 | 说明 |
|----|------|------|
| `schema_version` | 是 | 固定字符串，升级须递增并写迁移说明 |
| `D_meta` | 是 | 见 §3 |
| `D_text` | 是 | 数组；允许 `[]`（整段无文本时） |
| `D_ts` | 是 | 数组；**不允许因无数据而省略桶**，须用空窗帧填满 `time_range` |

**序列化**：推荐 JSON（UTF-8）；大批量 `D_text` 可另存 `parquet/csv`，但须在 `D_meta.text_uri` 给出路径，且字段与本文一致。

---

## 3. 元数据 `D_meta`

### 3.1 字段表

| 字段 | 类型 | 必填 | 约束 / 说明 |
|------|------|------|-------------|
| `platform` | string | 是 | 枚举见 §8.1，如 `bilibili` |
| `keyword` | string | 是 | 任务话题词，与主控下发一致 |
| `time_range` | object | 是 | `{ "start": ISO8601, "end": ISO8601 }`，时区默认 `Asia/Shanghai` |
| `timezone` | string | 是 | 默认 `"Asia/Shanghai"` |
| `granularity` | string | 是 | `hour` \| `day` |
| `n_text` | int | 是 | 有效文本条数（不含纯占位、不含 quarantine） |
| `n_text_raw_in` | int | 否 | 清洗前入库条数，便于审计 |
| `n_buckets` | int | 是 | `D_ts` 长度，须等于理论桶数 |
| `empty_ratio` | float | 是 | `∈[0,1]`，空窗桶数 / `n_buckets` |
| `is_empty` | bool | 是 | 整任务无有效文本时为 `true` |
| `stance_global` | string | 是 | 全局主导立场，枚举同 `stance_label` |
| `bias_score` | float | 是 | `∈[0,1]`，平台偏见强度（口径见 §6.4） |
| `confidence` | float | 是 | `∈[0,1]`，画像与标注置信 |
| `sentiment_global_mean` | float | 否 | 全局加权情绪均值 `∈[-1,1]` |
| `clean_rule_version` | string | 是 | 如 `clean_c1c8_v1` |
| `source_skill_versions` | object | 是 | `{ "platform_crawler": "...", "stance_profiler": "..." }` |
| `text_uri` | string | 否 | 外置文本表路径 |
| `ext` | object | 否 | 平台扩展元数据，不对齐层强依赖 |

### 3.2 完整性约束

- `n_buckets == len(D_ts)`  
- `n_text ==` 满足「有效文本」定义的 `D_text` 条数（`is_empty_placeholder == false` 且 `text` 非空）  
- `is_empty == true` ⇒ `n_text == 0`，且 `stance_global == "neutral"`，`bias_score == 0`，`confidence` 建议 ≤ 0.2  
- `time_range.start < time_range.end`

---

## 4. 文本子集 `D_text`（样本级）

每一行表示一条清洗后的帖文/评论（或空窗占位样本）。

### 4.1 字段表

| 字段 | 类型 | 必填 | 约束 / 舆情含义 |
|------|------|------|-----------------|
| `platform` | string | 是 | 同 `D_meta.platform` |
| `content_id` | string | 是 | 平台内稳定唯一 ID；占位帧用 `placeholder:{platform}:{bucket_ts}` |
| `parent_id` | string \| null | 否 | 上级评论 ID；一级为 `null` 或 `"0"` |
| `author_id` | string \| null | 否 | 作者 ID；缺失为 `null` |
| `ts` | string | 是 | ISO8601 或可解析时间；必须落在所属桶或任务窗内 |
| `ts_unix` | int | 否 | 秒级 Unix，便于排序 |
| `text` | string | 条件必填 | 非占位时必填非空；占位允许 `""` |
| `like` | number | 是 | ≥0，原始点赞（或平台等价） |
| `reply_count` | number | 是 | ≥0，回复数 |
| `share_or_coin` | number | 否 | 转发/投币等，缺省 0 |
| `interact` | number | 是 | ≥0，**平台内归一化互动强度**（见 §6.1） |
| `source_url` | string \| null | 否 | 可回跳链接 |
| `stance_label` | string | 是 | 枚举见 §8.2 |
| `sentiment_score` | float | 是 | `∈[-1,1]` |
| `topic_tags` | string[] | 是 | 可 `[]` |
| `evidence_weight` | float | 是 | `∈[0,1]`，作结论证据权重（见 §6.5） |
| `is_empty_placeholder` | bool | 是 | 空窗占位为 `true` |
| `bucket_ts` | string | 是 | 所属时序桶左端点（与 `D_ts.ts` 对齐） |
| `lang` | string | 否 | 如 `zh` |
| `ext` | object | 否 | 平台原始字段快照（等级、IP 属地等），不对齐强依赖 |

### 4.2 主键与去重

- **主键**：`(platform, content_id)`  
- 补采合并：同主键保留 `evidence_weight` 更高者，或按 `ts` 最新者（须在 `D_meta.ext.merge_policy` 声明）  
- 无原生 ID 时：`content_id = "hash:" + sha1(text|ts|author_id)`（与清洗 C5 一致）

### 4.3 有效文本定义

同时满足：

- `is_empty_placeholder == false`  
- `len(strip(text)) > 0`  
- `ts` 在 `time_range` 内  

仅有效文本计入 `n_text`、进入时序聚合与 LLM 高权重抽样。

---

## 5. 时序子集 `D_ts`（粒度桶级）

### 5.1 时间轴生成规则

设 `granularity`：

- `hour`：桶宽 1 小时，桶标签为该小时 `[ts, ts+1h)` 的左闭右开左端点  
- `day`：桶宽 1 天（按 `timezone` 自然日），左端点为当日 `00:00:00`

从 `time_range.start` 向下取整到粒度边界，直到覆盖 `end`；**每一桶必须有一条 `D_ts` 记录**。

### 5.2 字段表

| 字段 | 类型 | 必填 | 含义 |
|------|------|------|------|
| `ts` | string | 是 | 桶左端点 ISO8601 |
| `ts_unix` | int | 否 | 秒 |
| `platform` | string | 是 | 同 meta |
| `volume` | number | 是 | 桶内有效**评论**条数；空窗为 0 |
| `heat` | number | 是 | 评论互动热度 \(\sum interact\)；空窗为 0（§6.2） |
| `topic_volume` | number | 建议 | 桶内相关**内容发布**条数（如视频按 `pubdate` 入桶）；无搜索池时为 0 |
| `topic_heat` | number | 建议 | 话题热度代理（§6.2.1）；反映爆发→至今的内容侧热度形态 |
| `topic_heat_delta` | number \| null | 建议 | `topic_heat[t]-topic_heat[t-1]`；首桶 `null` |
| `sent_mean` | float \| null | 是 | 加权情绪均值；空窗为 `null` |
| `sent_std` | float \| null | 是 | 情绪标准差；空窗或单样本为 `null`/`0`（实现须固定一种，写入 `ext.sent_std_policy`） |
| `stance_pos_ratio` | float | 是 | `∈[0,1]`，支持向占比 |
| `stance_neg_ratio` | float | 是 | 反对向占比 |
| `stance_neu_ratio` | float | 是 | 中性向占比（含 `neutral`+可配置的 `unclear`） |
| `stance_mixed_ratio` | float | 否 | `mixed` 占比，默认并入争议计算 |
| `bias_proxy` | float \| null | 是 | 桶级偏见代理；空窗 `null`（§6.4） |
| `controversy` | float \| null | 是 | 争议度；空窗 `null`（§6.3） |
| `volume_delta` | number \| null | 是 | `volume[t]-volume[t-1]`；首桶 `null` |
| `heat_delta` | number \| null | 否 | 热度增量 |
| `n_like_sum` | number | 否 | 桶内点赞和（审计用） |
| `is_empty` | bool | 是 | 无有效文本则为 `true` |
| `sample_content_ids` | string[] | 否 | 桶内代表性样本 ID（按 `evidence_weight` Top-K） |
| `ext` | object | 否 | 扩展 |

### 5.3 桶级约束

- `is_empty == true` ⇒ `volume == 0`，`heat == 0`，立场占比可置 `0` 或中性 `stance_neu_ratio == 1`（**须全局统一**；推荐：空窗三比均为 `0`，由 `is_empty` 区分「无观测」与「全中性」）  
- `is_empty == false` ⇒  
  `stance_pos_ratio + stance_neg_ratio + stance_neu_ratio (+ stance_mixed_ratio) == 1`（容差 `1e-6`）  
- `D_ts` 按 `ts` **严格升序**，无重复桶

---

## 6. 指标口径（计算公式）

以下为 **v1 默认口径**；改公式必须升 `schema_version` 或在 `D_meta.ext.metric_profile` 显式声明。

### 6.1 样本互动 `interact`（平台内）

对单条样本：

\[
interact = \log(1 + like + \alpha\cdot reply\_count + \beta\cdot share\_or\_coin)
\]

B 站默认建议：`α=1.0`，`β=1.0`（投币/分享映射到 `share_or_coin`）。  
跨平台比较时**禁止**直接比原始 `like`，只用各自平台内的 `interact` 或分位数。

### 6.2 桶热度 `heat`（评论侧）

\[
heat_t = \sum_{i \in bucket_t} interact_i
\]

可选平台内标准化（对齐层推荐）：

\[
heat\_z_t = (heat_t - \mu_{platform}) / (\sigma_{platform} + \varepsilon)
\]

`heat_z` 放入 `ext`，不替换原始 `heat`。

### 6.2.1 话题热度 `topic_heat`（内容侧，爆发→至今主轴）

评论 `heat` 依赖评论可达性，长历史窗常稀疏。因此用**关键词搜索到的内容实体**（B 站视频）按 **发布时间** 入桶，构建话题热度时序：

对单条视频：

\[
heat\_v = \log(1+play) + 0.5\log(1+review) + 0.25\log(1+favorites) + 0.25\log(1+danmaku)
\]

\[
topic\_heat_t = \sum_{v:\ pubdate(v)\in bucket_t} heat\_v,\quad
topic\_volume_t = |\{v:\ pubdate(v)\in bucket_t\}|
\]

口径声明：`D_meta.ext.topic_heat_metric = "video_topic_heat_v1"`；峰值摘要见 `topic_heat_peak_ts` / `topic_heat_peak`。  
**注意**：`is_empty` 仍只表示「无有效评论」；允许 `is_empty=true` 且 `topic_heat>0`（有内容发布、无评论文本）。

### 6.3 争议度 `controversy`

令 \(p=stance\_pos\_ratio\)，\(n=stance\_neg\_ratio\)（仅有效桶）：

**默认（乘积型）**：

\[
controversy = 4\cdot p\cdot n
\]

使得 \(p=n=0.5\) 时为 1。若使用熵型，须在 `metric_profile` 写明。

### 6.4 偏见 `bias_score` / `bias_proxy`

- 将立场映射到 \(s \in \{-1,0,+1\}\)：`oppose→-1`，`neutral/unclear→0`，`support→+1`，`mixed→0`（或拆分，须声明）  
- 桶级：

\[
bias\_proxy_t = \left| \frac{\sum_i evidence\_weight_i \cdot s_i}{\sum_i evidence\_weight_i + \varepsilon} \right|
\]

- 全局 `bias_score`：对非空桶按 `volume` 加权平均 `bias_proxy`，裁剪到 `[0,1]`。

### 6.5 证据权重 `evidence_weight`

建议乘性合成（各项 ∈[0,1]）：

\[
evidence\_weight = clip_{[0,1]}(w_{len}\cdot w_{interact}\cdot w_{anti\_spam}\cdot w_{stance\_conf})
\]

| 因子 | 含义 |
|------|------|
| `w_len` | 有效文本长度适中加分，过短降权 |
| `w_interact` | 由 `interact` 分位数映射 |
| `w_anti_spam` | 刷屏/重复降权（清洗 C7） |
| `w_stance_conf` | 立场/情绪模型置信 |

占位帧：`evidence_weight = 0`。

### 6.6 情绪聚合 `sent_mean`

\[
sent\_mean_t = \frac{\sum_i evidence\_weight_i \cdot sentiment\_score_i}{\sum_i evidence\_weight_i + \varepsilon}
\]

---

## 7. 空数据与占位规范

| 场景 | `D_meta.is_empty` | `D_text` | `D_ts` |
|------|-------------------|----------|--------|
| 整段无有效文本 | `true` | 允许 `[]`，或每空桶 1 条占位（二选一，推荐 `[]` + 全空 `D_ts`） | 全时间轴桶存在，`is_empty=true` |
| 部分时段无数据 | `false` | 仅真实样本 | 对应桶 `is_empty=true` |
| 清洗后全被丢弃 | `true` | `[]` | 同整段无文本 |

**禁止**：

- 删除空桶使轴变短  
- 用邻桶或邻平台插值填 `volume`/`heat` 冒充本平台观测  
- 空窗写虚假评论文本

---

## 8. 枚举与取值

### 8.1 `platform`

| 值 | 说明 |
|----|------|
| `bilibili` | B 站（首期） |
| `weibo` | 微博（预留） |
| `douyin` | 抖音（预留） |
| `xiaohongshu` | 小红书（预留） |

### 8.2 `stance_label` / `stance_global`

| 值 | 含义 |
|----|------|
| `support` | 支持 / 正向站队 |
| `oppose` | 反对 / 负向站队 |
| `neutral` | 中性陈述 |
| `mixed` | 同条内多立场混杂 |
| `unclear` | 无法判定 |

立场占比映射（默认）：

- `pos` ← `support`  
- `neg` ← `oppose`  
- `neu` ← `neutral` + `unclear`  
- `mixed` ← `mixed`（可单列或按 0.5/0.5 拆入 pos/neg，须声明）

### 8.3 `granularity`

`hour` | `day`

---

## 9. 多平台对齐规则

对齐键：

```text
align_key = (keyword, time_range, granularity, ts_bucket)
```

规则：

1. 各平台 `D_ts` 对 `ts` 做 **outer join**；缺失侧补空窗帧（`is_empty=true`，数值按 §7）。  
2. 不对齐原始 `like`；对齐 `heat` 的平台内分位数或 `heat_z`。  
3. `D_text` 不对齐合并成一张「假全网帖文表」冒充单源；跨平台文本仅可在上层分平台陈列或标注 `platform`。  
4. 全局终裁不在本规范内；本规范只保证单平台包可被仲裁层消费。

---

## 10. 下游消费约定

| 消费者 | 主要读取 | 要求 |
|--------|----------|------|
| Skill3 多模态模型 | `D_ts` 全量指标 + 分桶 `D_text`/`sample_content_ids` | 空窗可 mask，不得丢弃时间步 |
| Skill4 知识库 | 高 `evidence_weight` 的 `D_text` + `D_meta` | `is_empty` 轮次可跳过写入 |
| Skill5/6 LLM | `D_meta` + 关键 `D_ts` + Top-K `D_text` | 引用 ID 必须存在于本包 |
| 对齐仲裁层 | 多平台 `D_platform` | 遵守 §9 |

---

## 11. JSON 示例（节选）

```json
{
  "schema_version": "dataset_schema_v1",
  "D_meta": {
    "platform": "bilibili",
    "keyword": "示例话题",
    "time_range": {
      "start": "2026-08-01T00:00:00+08:00",
      "end": "2026-08-03T00:00:00+08:00"
    },
    "timezone": "Asia/Shanghai",
    "granularity": "day",
    "n_text": 2,
    "n_buckets": 2,
    "empty_ratio": 0.0,
    "is_empty": false,
    "stance_global": "mixed",
    "bias_score": 0.21,
    "confidence": 0.74,
    "clean_rule_version": "clean_c1c8_v1",
    "source_skill_versions": {
      "platform_crawler": "bili_crawler_v1",
      "stance_profiler": "stance_v1"
    }
  },
  "D_text": [
    {
      "platform": "bilibili",
      "content_id": "257920146673",
      "parent_id": null,
      "author_id": "2527270",
      "ts": "2026-08-01T12:30:00+08:00",
      "text": "清洗后的评论内容",
      "like": 10,
      "reply_count": 2,
      "share_or_coin": 0,
      "interact": 2.56,
      "stance_label": "support",
      "sentiment_score": 0.62,
      "topic_tags": ["演技", "情怀"],
      "evidence_weight": 0.81,
      "is_empty_placeholder": false,
      "bucket_ts": "2026-08-01T00:00:00+08:00"
    }
  ],
  "D_ts": [
    {
      "ts": "2026-08-01T00:00:00+08:00",
      "platform": "bilibili",
      "volume": 120,
      "heat": 845.2,
      "sent_mean": 0.12,
      "sent_std": 0.41,
      "stance_pos_ratio": 0.40,
      "stance_neg_ratio": 0.35,
      "stance_neu_ratio": 0.25,
      "bias_proxy": 0.08,
      "controversy": 0.56,
      "volume_delta": null,
      "is_empty": false,
      "sample_content_ids": ["257920146673"]
    },
    {
      "ts": "2026-08-02T00:00:00+08:00",
      "platform": "bilibili",
      "volume": 0,
      "heat": 0,
      "sent_mean": null,
      "sent_std": null,
      "stance_pos_ratio": 0,
      "stance_neg_ratio": 0,
      "stance_neu_ratio": 0,
      "bias_proxy": null,
      "controversy": null,
      "volume_delta": -120,
      "is_empty": true,
      "sample_content_ids": []
    }
  ]
}
```

---

## 12. 校验清单（发布前）

- [ ] `schema_version` 正确  
- [ ] `len(D_ts) == n_buckets` 且覆盖完整时间轴  
- [ ] 非空桶立场占比和为 1  
- [ ] `n_text` 与有效文本计数一致  
- [ ] 所有 `D_text.content_id` 唯一  
- [ ] `bucket_ts` 均能在 `D_ts.ts` 中找到  
- [ ] 空窗不含伪造正文  
- [ ] `clean_rule_version` / skill 版本已填写  

---

## 13. 版本演进

| 版本 | 变更 |
|------|------|
| `dataset_schema_v1` | 首版：D_meta / D_text / D_ts 与默认指标口径 |

变更字段名、枚举、默认公式 ⇒ **递增 schema 版本**，并保留旧版读取适配或迁移脚本说明。
