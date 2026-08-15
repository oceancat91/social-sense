# MultimodalAnalyzer（多模态时序–文本分析 Skill）

> **对应设计**：根目录 [`README.md`](../README.md) **Skill 3 · MultimodalTemporalAnalyzer**  
> **状态**：**留白占位**，目录与契约已定，实现尚未接入。  
> **上游**：Skill1 `PlatformCrawler` + Skill2 `StanceProfiler` 产出的 `D_platform`  
> **下游**：Skill5/6（`Conclusion/`）硬约束证据；可选触发 Skill1 补采、Skill4 RAG

---

## 一句话

吃进标准化「时序 + 文本」数据集，用**多模态模型**同时看数值轨迹和评论文本，检出异常、给出基线与残差——这些是后面 LLM 写结论时必须遵守的**硬证据**，不是可选项。

---

## 在流水线里的位置

```text
D_platform（Skill1+2）
        │
        ▼
MultimodalAnalyzer（Skill3）  ← 本包（待实现）
  · 时序塔：volume / heat / topic_heat / sent_mean / controversy …
  · 文本塔：桶内高权重样本语义
  · 融合 → anomalies / residual / baseline / hidden_states
        │
        ├─(主路径)→ Conclusion（OT₀ / 校准 OT₁）
        └─(可选)→ need_recrawl → Skill1 缩小窗补采 → Skill2 刷新 → 本 Skill 重跑（≤1 轮）
```

---

## 计划能力（实现后应回答）

1. **哪天声量/热度突变？**（含评论侧 `heat` 与内容侧 `topic_heat`）  
2. **情绪或立场是否翻转？**  
3. **文本语义与数值轨迹是否打架？**（`cross_modal_inconsistency`）  
4. **相对正常基线，残差有多大？**（供校准门禁 G1–G2）  
5. **要不要建议补采？**（`need_recrawl`）

空 `D_platform`（`is_empty=true`）时：不报错；`anomalies=[]`，`status=no_anomaly_empty`，流水线继续。

---

## 输入 / 输出契约（冻结）

### 输入

| 字段 | 说明 |
|------|------|
| `D_platform` | 必填；须含完整 `D_ts` 轴（含空窗）与有效/空 `D_text` |
| `D_meta` | 任务窗、粒度、`topic_heat` 峰值摘要等 |
| 配置 | 异常阈值 `τ`、是否启用文本塔、最大补采轮次（建议 1） |

字段口径见 [`DATASET_SPEC.md`](../DATASET_SPEC.md)。实现时须消费：

- 评论侧：`volume` / `heat` / `sent_*` / `stance_*` / `controversy`  
- 内容侧：`topic_volume` / `topic_heat`（长轴热度主信号）

### 输出（建议落盘 JSON）

```text
status                 # ok | no_anomaly_empty | error
anomalies[]            # {ts, type, score, modality_hint, evidence_ids?}
  type 示例:
    volume_spike | heat_spike | topic_heat_spike
    sentiment_flip | stance_shift | cross_modal_inconsistency
hidden_states          # 中间表征引用 / 外置路径（不直接当结论）
residual               # 分指标：pred - actual
baseline               # 正常基线轨迹（与 D_ts 对齐）
need_recrawl           # bool
recrawl_windows[]      # 可选，加密时间窗建议
model_version          # 本 Skill 版本号
```

---

## 模型形态（约定，实现时可替换）

| 模块 | 职责 |
|------|------|
| 时序塔 | 对多变量桶序列建模短期趋势与突变 |
| 文本塔 | 对桶内加权 / Top-K 文本编码语义漂移 |
| 融合头 | 时间步对齐 → 异常分数、类型、残差向量 |

**禁止**：用 LLM 重新「估」一套与残差冲突的热度/情绪曲线。本 Skill 负责「测得到」的定量证据。

---

## 建议目录（实现时）

```text
MultimodalAnalyzer/
├── README.md          ← 你在这里
├── __init__.py
├── pipeline.py        # 入口（待写）
├── models/            # 时序塔 / 文本塔 / 融合
├── detectors/         # 规则基线 + 模型异常
└── outputs/           # 本地调试产物
```

---

## 计划入口（尚未实现）

```powershell
# 预期用法（占位，跑起来会提示未实现）
python -m MultimodalAnalyzer --in dataset/events/<event_id>/D_platform.json
```

---

## 实现清单（留给后续）

- [ ] 读取并校验 `D_platform`  
- [ ] 时序特征矩阵（含 `topic_heat`）  
- [ ] 文本塔抽样策略（按 `evidence_weight`）  
- [ ] 异常类型枚举与阈值配置  
- [ ] `need_recrawl` 回调协议（对接 Agent / Skill1）  
- [ ] 空窗与超长轴（爆发→至今）性能策略（可日聚合后再检）  
- [ ] 单测：空包 / 仅 topic_heat 有峰 / 评论稀疏  

---

## 相关文档

- 总设计：[`README.md`](../README.md) §Skill3、§五（与 LLM 分工）  
- 数据契约：[`DATASET_SPEC.md`](../DATASET_SPEC.md)  
- 上游：[`PlatformCrawler/`](../PlatformCrawler/)、[`StanceProfiler/`](../StanceProfiler/)  
- 下游：[`Conclusion/`](../Conclusion/)、[`KnowledgeAugmentor/`](../KnowledgeAugmentor/)
