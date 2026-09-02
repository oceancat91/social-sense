# 单平台舆情感知 Agent — Skill 设计文档

> **目标**：单 Agent 可调度的原子化 Skill；先形成可对齐的「时序 + 文本」数据源，再经多模态时序文本分析与严格校准，输出**单平台**标准化舆情包，供上层多平台对齐融合（本 Agent 不产出全局终裁结论）。
>
> **已落地平台**：B站 / 微博 / 抖音 / 小红书 / 知乎 / 快手（共 6 平台）。B站有完整爬虫脚本（`crawler/`）；其余 5 平台通过 `PlatformCrawler/adapters/` 统一适配器采集，复用同一套清洗 + Skill2–6。接口与指标 schema 按多平台可扩展约定设计。
>
> **数据集规范（主契约）**：详见 [`DATASET_SPEC.md`](./DATASET_SPEC.md)（`D_platform` / `D_text` / `D_ts` / `D_meta` 字段、口径、空窗与对齐规则）。

---

## 〇、Skill 总览与数据契约

| 序号 | Skill | 类型 | 角色 |
|------|--------|------|------|
| 1 | **PlatformCrawler**（含内置清洗） | 数据源 Skill | 采集 + 规范清洗 → 原始可用文本与互动字段 |
| 2 | **StanceProfiler** | 数据源 Skill | 立场/情绪/偏见画像 → 与 Skill1 共同整理出**时序+文本数据集** |
| 3 | **MultimodalTemporalAnalyzer** | 分析计算 | CrossAD 启发的多尺度时序–文本异常、等级与残差 |
| 4 | **KnowledgeAugmentor**（写入+检索一体） | 备用补充 | BM25 + LLMAD 启发的历史正常/异常正反例 |
| 5 | **ConclusionGen** | 生成 | 结构化观察、核验、复核与风险分级的初步结论 OT₀ |
| 6 | **ResidualCalibrator** | 校准 | **强制多检**、不达标不得输出 OT₁ |

**核心数据流（简化）**

```text
任务参数(平台/关键词/时段/粒度)
        │
        ▼
┌─────────────────── 数据源层 ───────────────────┐
│  Skill1 PlatformCrawler（采集+规范清洗）         │
│           +                                    │
│  Skill2 StanceProfiler（立场画像）               │
│           ↓                                    │
│  标准化「时序 + 文本」数据集 D_platform           │
└────────────────────────────────────────────────┘
        │
        ├─(主路径)→ Skill3 多模态时序文本分析 → 异常/隐特征/残差
        │
        └─(备用)→ Skill4 知识库写入/RAG 补充（上下文超限或证据不足时）
        │
        ▼
 Skill5 结论生成 OT₀  ──严格校准──►  Skill6 → OT₁
        │
        ▼
 单平台标准化舆情数据包 → 上层多平台对齐仲裁
```

---

## 一、核心 Skill 设计

### （一）数据源类

#### Skill 1. 平台定向采集与清洗 Skill（PlatformCrawler）

- **实现基座**：`bilibili-comment-crawler/`
  - 关键词/话题全站检索：`B站关键词搜索.py`
  - 视频/动态评论抓取：`B站评论爬虫.py`、`B站动态爬虫.py`
  - 鉴权：`auto_get_cookie.py` / `setup_cookie.py`（`bili_cookie.txt`）
- **功能**：按关键词/话题检索内容实体 → 抓取帖文/评论及互动量 → **在同一 Skill 内完成规范清洗与字段标准化**（清洗不再拆为独立 Skill）
- **输入**
  - `platform`：平台标识（首期固定 `bilibili`）
  - `keyword`：话题关键词
  - `time_range`：`[start, end]`
  - `granularity`：时序粒度 `hour` | `day`
  - `search_pages` / `max_videos` / `comment_pages`：检索与评论抓取配额
  - `recrawl_windows`（可选）：异常补爬时的加密时间窗
- **输出**
  - `raw_clean_bundle`：清洗后结构化记录集
  - `is_empty`：空数据标记（时段无内容时仍返回，保留时间轴占位）
  - `crawl_meta`：命中 BV/动态列表、配额消耗、失败重试摘要
- **触发场景**：任务初始化首采；Skill3 高置信异常回调补采

##### 1.1 内置规范清洗逻辑（必须执行，顺序固定）

清洗在采集后、写出 `raw_clean_bundle` 前完成；任一步失败须记入 `crawl_meta.clean_log`，不得静默丢弃整批时间轴。

| 步骤 | 规则 | 说明 |
|------|------|------|
| C1 字段映射 | 统一映射到跨平台字段 | `text, ts, like, reply_count, share_or_coin, author_id, content_id, parent_id, source_url, platform` |
| C2 空值与非法 | 丢弃无文本且无互动的空行；`ts` 无法解析则入 quarantine，不进主集 | 保证主集时间可排序 |
| C3 文本去噪 | 去除 HTML/`em` 高亮标签、多余空白、零宽字符；可选剥离纯表情/纯数字刷屏 | 保留原文语义，不做过度改写 |
| C4 规范化 | Unicode NFKC；统一换行；时间统一为 UTC+8 可解析 ISO 或 epoch | 多平台对齐前提 |
| C5 去重 | 主键：`platform + content_id`；无 id 时用 `hash(text\|ts\|author_id)` | 补爬合并时幂等 |
| C6 时间窗裁剪 | 仅保留 `time_range` 内样本；窗外样本标记 `out_of_range` 不进时序聚合 | 与任务时段严格一致 |
| C7 刷屏弱化 | 同作者短窗内高度相似文本降权或合并计数 | 防刷评扭曲热度 |
| C8 空窗占位 | 某粒度桶无样本 → 输出空桶标记，**不删时间轴** | 全局对齐不断档 |

- **空数据兼容**：整段无有效文本时，`is_empty=true`，输出空时序占位帧，流水线不中断。

---

#### Skill 2. 平台立场画像 Skill（StanceProfiler）

- **功能**：在 Skill1 清洗结果上，计算单平台话题舆论倾向、情绪分布、观点阵营与偏见强度；**与 Skill1 共同作为数据源 Skill**，整理输出标准化「时序 + 文本」数据集。
- **输入**：Skill1 的 `raw_clean_bundle` / 空数据标记
- **输出**
  - `stance_profile`：立场标签、情绪分布、偏见得分、核心关键词簇、置信度
  - **`D_platform`**：标准化时序+文本数据集（见 §1.2，多平台对齐主契约）
- **兼容逻辑**：空文本 → 中性空标签 + 空时序占位，`schema` 仍完整

##### 1.2 数据源联合产出：标准化数据集 `D_platform`（多平台舆情对齐契约）

Skill1 + Skill2 **必须**产出同一 schema，供跨平台对齐。指标紧扣多平台舆情分析主题：**声量、情绪、立场、争议、传播、可信样本**。

> **完整字段、计算公式、空窗规则、JSON 示例与校验清单**：见 [`DATASET_SPEC.md`](./DATASET_SPEC.md)。以下为摘要。

**A. 文本子集 `D_text`（样本级）**

| 字段 | 类型 | 舆情含义 |
|------|------|----------|
| `platform` | str | 平台来源，对齐键之一 |
| `content_id` | str | 平台内唯一内容 ID |
| `ts` | datetime | 发布时间 |
| `text` | str | 清洗后正文 |
| `like` / `reply_count` / `interact` | num | 互动量；`interact` 为平台归一化互动强度 |
| `stance_label` | enum | `support` / `oppose` / `neutral` / `mixed` / `unclear` |
| `sentiment_score` | float[-1,1] | 情绪极性 |
| `topic_tags` | list[str] | 观点/议题簇标签 |
| `evidence_weight` | float[0,1] | 样本作为结论证据的权重（反刷、置信） |
| `is_empty_placeholder` | bool | 是否为空窗占位（文本可空） |

**B. 时序子集 `D_ts`（粒度桶级，`granularity` 对齐）**

| 指标 | 符号 | 舆情含义（多平台对齐） |
|------|------|------------------------|
| 声量 | `volume` | 桶内有效评/帖条数 |
| 热度 | `heat` | 归一化互动总量（跨平台需按平台基线缩放） |
| 情绪均值 | `sent_mean` | 桶内 `sentiment_score` 加权均值 |
| 情绪波动 | `sent_std` | 情绪分歧/极化程度 |
| 立场占比 | `stance_pos_ratio` / `stance_neg_ratio` / `stance_neu_ratio` | 阵营结构 |
| 偏见代理 | `bias_proxy` | 相对中性基线的偏离（与 Skill2 偏见得分一致口径） |
| 争议度 | `controversy` | 正负立场并存强度（如熵或 pos×neg） |
| 新增声量 | `volume_delta` | 相对上一桶增量，捕捉突发 |
| 空窗标记 | `is_empty` | 该桶无真实样本 |

**C. 数据集级元数据 `D_meta`**

- `platform`, `keyword`, `time_range`, `granularity`
- `n_text`, `n_buckets`, `empty_ratio`
- `stance_global`, `bias_score`, `confidence`
- `source_skill_versions`：Skill1/2 版本与清洗规则版本号

> **对齐原则**：上层多平台融合时，以 `keyword + time_range + granularity` 为轴，对各平台 `D_ts` 按时间戳外连接；缺失平台填空窗帧，禁止用邻平台插值冒充本平台观测。

---

### （二）分析计算类

#### Skill 3. 多模态时序–文本分析 Skill（MultimodalTemporalAnalyzer）

- **功能**：以 **多模态时序文本模型** 同时编码 `D_ts` 数值轨迹与 `D_text` 语义序列，检测舆情波动异常，输出中间隐特征与预测残差，作为后续 LLM 的**硬约束证据**。
- **当前模型形态**
  - **多尺度时序塔**：短/中/长窗口滑动中位数 + MAD 稳健 z-score
  - **文本塔**：对桶内加权文本（或代表性样本）编码语义漂移
  - **跨尺度头**：比较各尺度响应，检测 `cross_scale_inconsistency`
  - **融合头**：对齐时间步 → 异常分数、类型、等级、原因、残差向量
- **输入**：`D_platform`（`D_ts` + `D_text` + `D_meta`）/ 空时序占位帧
- **输出**
  - `anomalies[]`：`{ts, type, score, severity, confidence, reason, evidence_ids}`  
  - `multiscale`：各时间尺度窗口、z-score 与主尺度
  - `risk_summary`：最高风险等级及数量分布
  - `hidden_states`：模型中间隐层特征（供 RAG/结论侧引用，不直接当结论）
  - `residual`：预测值 − 真实值（分指标）
  - `baseline`：正常基线轨迹
  - `need_recrawl`：是否建议 Skill1 对高分异常窗补采
- **兼容逻辑**：空时序 → `anomalies=[]`，`status=no_anomaly_empty`，不阻断流水线
- **补采回调**：`score ≥ τ` 且 `type` 属于可补采集合 → 触发 Skill1 缩小粒度二次采集，再经 Skill2 刷新 `D_platform` 后重跑本 Skill（建议最多 1 轮，防循环）

---

### （三）知识库与检索类（备用补充，非主路径）

#### Skill 4. 知识增强 Skill（KnowledgeAugmentor）

将原「向量写入」与「本地 RAG」合并为**一个备用 Skill**，与数据源 Skill（Skill1/2 产出的 `D_platform`）绑定；**仅在主路径证据不足时启用**，不得替代 `D_ts`/`residual` 成为结论主依据。

- **写入（被动）**：每轮 `D_platform` 更新后，将高 `evidence_weight` 文本 + 元数据 + 立场标签入库；`is_empty` 轮次跳过
- **案例库**：保存 Skill3 时序签名、异常类型与风险等级，标签明确标记为 `skill3_weak_label`
- **检索（按需）**：BM25 召回文本；多变量 z-normalized DTW 分别召回相似异常例和正常例
- **启用条件（满足任一）**
  1. `D_text` 总量超 LLM 上下文阈值
  2. Skill3 报跨模态/跨尺度异常或 `important` / `critical` 风险
  3. 主控显式要求历史对照
- **输出**：`rag_chunks[]`、`history_cases[]`、`anomaly_examples[]`、`normal_examples[]`、`augment_used`
- **约束**：RAG 内容在 Prompt 中的优先级**低于**时序残差与立场基准；与 `D_ts` 冲突时以数据源观测为准，并记入校准日志

---

### （四）生成与校准类（严格模式）

#### Skill 5. 单平台结论生成 Skill（ConclusionGen）

- **功能**：按**固定优先级**拼装结构化 Prompt，调用 LLM 完成**概括分析 + 结构化研判**，生成单平台初步结论 OT₀。  
  LLM 在此阶段的主业不是「改数」，而是在硬数据约束下做：**要点概括、观点聚类叙述、趋势解读、风险提示**等分析性输出（详见 **§五**）。
- **输入优先级（高 → 低，不可颠倒）**
  1. Skill3：`residual` + `anomalies` + `baseline`（硬约束段，必须置于 Prompt 首部）
  2. Skill2：`stance_profile` / `D_meta` 立场与偏见
  3. `D_ts` 关键桶摘要（声量/情绪/争议）
  4. Skill4：`rag_chunks` + 历史正反例（均为补充非主证）
  5. `D_text` 高权重样本（条数上限可配）
- **输出**：OT₀（结构化字段 + **自然语言分析摘要**）、核心观点摘要、`cited_bucket_ids` / `cited_content_ids`
- **内置硬约束**
  - 禁止输出与 `residual` 显著矛盾的趋势判断（如残差显示声量未升却写「热度暴涨」）
  - 每个观点句必须绑定至少一条 `cited_*`；无引用不得写实指性判断
  - 空数据任务只允许输出「无观测/证据不足」类结论，禁止臆测

**OT₀ 结构化最小字段**

```text
claim_trend        # 声量/热度趋势：up|down|flat|unknown
claim_sentiment    # 情绪走向
claim_stance       # 主导立场
risk_flags[]       # 争议/偏见/突变风险
risk_level         # none|warning|important|critical|unknown
anomaly_reasoning  # 全局观察/局部证据/跨模态核验/误报复核
evidence_ids[]     # 引用的桶或文本 ID
uncertainty        # high|mid|low
summary_analysis   # 自然语言概括分析（要点/阵营/争议焦点）
```

---

#### Skill 6. 残差反馈校准 Skill（ResidualCalibrator）**【严格】**

- **功能**：对照 OT₀ 与真实 `D_ts` / 立场基准 / Skill3 残差，做**可判定通过或驳回**的校准；并对分析表述做**纠偏改写**（删幻觉、改矛盾句、补证据引用）。  
  注意：校准是**守门与修正**，不替代 Skill5 的概括分析职责；通过后的 OT₁ 仍应保留完整分析叙述，仅消除与数据冲突的部分。
- **输入**：OT₀、`D_ts` 真实值、`stance_profile`、`residual`、`anomalies`、（可选）RAG 补充
- **输出**：`deviation_report`、`calibration_constraints`、`OT₁`（含修订后的 `summary_analysis`）或 `reject`
- **触发**：OT₀ 生成后**强制**调用，不可跳过

##### 6.1 严格校准门禁（须全部通过才可释放 OT₁）

| 检查项 | 规则 | 不通过处置 |
|--------|------|------------|
| G1 趋势一致性 | OT₀.`claim_trend` 与 `volume`/`heat` 的残差符号及异常类型一致 | 驳回并回写约束重生，或降级 `uncertainty=high` |
| G2 情绪一致性 | `claim_sentiment` 与 `sent_mean` 变化方向一致（容差 ε 可配） | 同上 |
| G3 立场一致性 | `claim_stance` 与全局/主导桶立场占比一致 | 同上 |
| G4 证据覆盖 | 每个实指 claim 均有 `evidence_ids`，且 ID 存在于本轮 `D_platform` | 删除无证据句或整单驳回 |
| G5 禁幻觉 | 不得引用未出现的平台外事实；RAG 与 `D_ts` 冲突时不得站 RAG | 删除冲突句 |
| G6 空窗诚实 | `empty_ratio` 高或 `is_empty` 时，禁止强结论 | 改写为证据不足 |
| G7 风险一致性 | `risk_level` 不得夸大 Skill3，且结构化观察/证据/复核完整 | 受限改写或 `failed_calibration` |

- **通过标准**：G1–G7 全过 → `OT₁_status=accepted`；校准仍限制最多 `max_calib_rounds` 轮。

---

## 二、单平台感知 Agent 全链路 Pipeline

**定位**：单一社交平台话题舆情全流程；输出标准化平台级数据包；**不**输出全局最终结论。

> **实现入口**：`python -m Agent.orchestrator --topic 话题词`
> 编排用 LangGraph 状态图（未安装 `langgraph` 时自动回退线性执行）；跑完 Skill1→6 后额外输出契约版 `platform_report_*.json`，供上层 `multiagent/` 消费。

1. **任务初始化**  
   接收主控参数：`platform`（首期 `bilibili`）、`keyword`、`time_range`、`granularity`；加载 `bilibili-comment-crawler` 鉴权与配额配置。

2. **数据源构建（Skill1 → Skill2，顺序执行、联合出品）**  
   - 调用 **Skill1 PlatformCrawler**：关键词检索 → 评论采集 → **规范清洗 C1–C8**  
   - 若 `is_empty` → 生成空 `D_platform` 占位，跳至步骤 6（仍走严格校准中的空窗规则）  
   - 调用 **Skill2 StanceProfiler**：立场/情绪/偏见 → 与 Skill1 结果合并为 **`D_platform = {D_text, D_ts, D_meta}`**

3. **多模态时序文本分析（Skill3）**  
   输入 `D_platform`，产出异常、隐特征、残差、基线；必要时回调 Skill1 补采并 **从步骤 2 局部刷新**（限轮次）。

4. **知识增强（Skill4，备用）**  
   写入本轮高权重样本；仅当启用条件满足时检索补充，且标记 `augment_used`。

5. **结论生成与严格校准（Skill5 → Skill6）**  
   - Skill5：按硬优先级生成 OT₀  
   - Skill6：执行 G1–G7 门禁 → 通过则 OT₁，否则驳回/降级

6. **标准化输出（提交对齐仲裁层）**
   - **元数据**：平台、关键词、时段、粒度、数据量、`empty_ratio`、空标记、Skill 版本
   - **数据源**：`D_platform` 摘要（或完整句柄）
   - **特征集**：立场画像、异常点、隐特征引用、残差、基线
   - **增强集**：`augment_used`、RAG 摘要（可空）
   - **结论集**：OT₁（或失败状态）、**概括分析** `summary_analysis`、观点摘要、证据 ID 列表、校准报告

---

## 三、与代码目录的对应关系（B 站首期）

| 设计模块 | 代码位置 |
|----------|----------|
| Skill1 全流水线 | `PlatformCrawler/pipeline.py`（检索→评论→清洗→`D_platform`） |
| Skill1 检索/评论采集 | `PlatformCrawler/crawler/`（`B站关键词搜索.py`、`B站评论爬虫.py` 等） |
| Skill1 多平台适配器 | `PlatformCrawler/adapters/`（`base.py` / `registry.py` + 6 平台 adapter） |
| Skill1 鉴权 | `PlatformCrawler/crawler/auto_get_cookie.py`、`setup_cookie.py`、`bili_common.py` |
| Skill1 清洗 C1–C8 + 建库 | `PlatformCrawler/dataloader/`（`cleaner.py` / `builder.py` / `validate.py`） |
| Skill1 使用说明 | `PlatformCrawler/README.md` |
| Skill2 立场画像 | `StanceProfiler/`（`pipeline.py` / `profiler.py` / `labelers/`） |
| Skill2 使用说明 | `StanceProfiler/README.md` |
| Skill3 多模态时序文本分析 | `MultimodalAnalyzer/`（`temporal.py` / `text_tower.py` / `detectors.py` / `analyzer.py` / `pipeline.py`） |
| Skill4 知识增强 / RAG | `KnowledgeAugmentor/`（`store.py` 写入+BM25 检索 / `pipeline.py`） |
| Skill5+6 结论生成与校准 | `Conclusion/`（`gen/` 生成 OT₀ + `calib/` G1–G7 门禁 / `pipeline.py`） |
| 单事件正式数据集仓库 | `dataset/`（`README.md` / `events/<event_id>/`） |
| 数据集规范 | `DATASET_SPEC.md` |
| Agent 全链路编排 | `Agent/`（`agent.py` Skill1+2；`orchestrator.py` Skill1→6，LangGraph 状态图 + 线性兜底） |
| Skill 封装层 | `skills/`（`base.py` 抽象 + `registry.py` 注册表 + `impls.py` 六项实现） |
| Skill 验证工具 | `tools/evaluate_skills.py`（golden 立场标注 + 跨平台对齐 + Skill3 异常统计） |
| 多平台多 Agent 架构 | 仓库根 `multiagent/`（契约 + 对齐 + 融合 + 主控 Agent） |

**常用命令**

```bash
# 全流水线
python -m PlatformCrawler.pipeline 话题词 --since 2026-07-01 --until 2026-08-14 --max-videos 3 --comment-pages 2

# 仅清洗建库（已有评论 CSV）
python -m PlatformCrawler.dataloader.cli --csv a.csv b.csv --keyword 话题词 --since 2026-07-01 --until 2026-08-14 --out out.json
```

**Skill 封装与验证**

六项 Skill 已统一封装为 `skills/` 包（`Skill` 抽象 + `SkillContext` 状态载体 + `SkillRegistry` 注册表 + 六项实现），可独立调用或经 `run_pipeline` 串行执行：

```python
from skills import SkillContext, run_pipeline
ctx = SkillContext(platform="bilibili", keyword="科比去世")
run_pipeline(ctx)   # Skill1→6 串行执行，结果写入 ctx.d_platform/skill3/conclusion...
```

用历史数据验证 Skill 准确性（golden 立场标注 + 跨平台对齐覆盖度 + Skill3 异常统计）：

```bash
# 输出到 dataset/eval/evaluation_report.json
python -m tools.evaluate_skills
```

---

## 四、扩展约定（多平台）

- 新平台 = 新的 **Skill1 适配器**（采集+同一套清洗契约）+ 复用 Skill2–6。
- **适配器层已实现**：`PlatformCrawler/adapters/`，统一 `PlatformAdapter` 抽象基类 + 注册表。
  - `bilibili_adapter.py`：复用 `crawler/` 现有脚本。
  - `weibo_adapter.py`：m.weibo.cn 搜索 + 评论（`weibo_cookie.txt`）。
  - `zhihu_adapter.py`：api 搜索 + 回答评论（`zhihu_cookie.txt`，x-zse-96 签名）。
  - `douyin_adapter.py`：web 搜索 + 评论（`douyin_cookie.txt`，a_bogus 签名）。
  - `xiaohongshu_adapter.py`：web 搜索 + 笔记评论（`xiaohongshu_cookie.txt`，x-s 签名）。
  - `kuaishou_adapter.py`：graphql 搜索 + 评论（`kuaishou_cookie.txt`）。
  - 每个 adapter 产出「跨平台原始字段」，复用 `clean_records` + `build_d_platform`。
- **立场词表按平台细分**：`StanceProfiler/labelers/platform_lexicons.py` 为 6 平台各配圈层用语（微博吃瓜 / 抖音家人 / 小红书种草 / 知乎论证 / 快手老铁 / B站弹幕），`LexiconLabeler` 按 `D_meta.platform` 自动合并词表。
- 跨平台对齐只认 `D_platform` schema；平台特有字段放入 `ext`，不得破坏 `D_ts` 核心指标。
- 热度/互动跨平台不可比时，对齐层使用**平台内 z-score / 分位数**，禁止直接比较原始 `like`。

**多平台采集命令**

```bash
# 单平台流水线（--platform 非 bilibili 走通用适配器）
python -m PlatformCrawler.pipeline 话题词 --platform weibo --since 2026-07-01 --until 2026-08-14

# 全链路编排（Skill1→6，--platform 分发）
python -m Agent.orchestrator --topic 话题词 --platform xiaohongshu
```

> 各平台真实采集需先配置对应 `*_cookie.txt`（详见各 adapter 文件头注释）；抖音/小红书/快手签名算法由平台前端 JS 生成，存在失效风险，失效时仅需替换 adapter 内签名函数，采集流程与字段映射不受影响。

---

## 五、LLM 职责说明：概括分析 ≠ 仅做校准

本系统中 LLM **同时承担两类任务**，不可把「生成与校准」理解成只做数值纠偏或句子改写。

### 5.1 任务二分

| 角色 | 主要落点 | 做什么 | 不做什么 |
|------|----------|--------|----------|
| **分析生成** | Skill5（ConclusionGen）为主；Skill6 仅在纠偏时保留/改写分析段 | 在数据约束下做舆情**概括、解读、归纳** | 不发明与 `D_ts`/残差矛盾的「事实」 |
| **校正守门** | Skill6（ResidualCalibrator）为主 | 对照残差与门禁 **纠偏、删幻觉、补引用、通过/驳回** | 不从零撰写整篇分析；不覆盖模型已给出的量化异常结论 |

### 5.2 分析生成侧（LLM 主产出）

在硬约束段（残差/异常/基线/立场）给定后，LLM 应输出可读的研判内容，至少覆盖：

1. **要点概括**：本时段本平台讨论焦点、高频议题（基于 `D_text` 高权重样本）  
2. **声量与情绪解读**：结合 `D_ts` 说明升温/降温、情绪走向（与 `claim_*` 字段一致）  
3. **立场与阵营叙述**：各方主要论点摘要，而非只给标签枚举  
4. **争议与风险分析**：争议焦点、可能误导点、偏见表现（对齐 `controversy` / `bias_score` / `risk_flags`）  
5. **异常事件说明**：对 Skill3 检出的异常点做**可读解释**（仍须引用 `anomalies`/`evidence_ids`）  
6. **不确定与缺口**：数据空窗、样本不足、需补采处明示  

上述内容写入 OT₀/OT₁ 的 `summary_analysis`（及观点摘要），作为提交对齐层的**叙事层**；结构化 `claim_*` 字段则是供程序对齐的**断言层**。

### 5.3 校正调整侧（LLM 辅助 + 规则门禁）

校准阶段可以再次调用 LLM，但目标收窄为：

- 根据 `deviation_report` **改写矛盾句**、删除无证据表述  
- 在不改变已通过的量化判断前提下，**润色并收束**分析段落  
- 输出是否满足 G1–G7 的判定由规则门禁最终裁决；LLM 建议「通过」不能凌驾于门禁之上  

### 5.4 与 Skill3 多模态模型的分工

- **Skill3（多模态时序文本模型）**：负责可计算的异常分数、隐特征、残差与基线——提供「测得到」的证据。  
- **LLM**：负责把证据组织成**人可读的概括分析与研判**，并在校准环中**守住不漂移**。  
- 二者关系：**模型定量 → LLM 定性概括 → 校准门禁验收**；禁止用 LLM 重新「估」一套与残差冲突的热度/情绪曲线。
