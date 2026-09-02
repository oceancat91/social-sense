# KnowledgeAugmentor（知识增强 Skill）

> **对应设计**：根目录 [`README.md`](../README.md) **Skill 4 · KnowledgeAugmentor**  
> **状态**：**已实现并接入 Agent 编排与后端 Agent Engine**。  
> **定位**：**备用补充**，不是主路径。不得用 RAG 结果覆盖 `D_ts` / Skill3 `residual`。

---

## 一句话

把本轮高权重舆情样本写入本地知识库；仅在主路径证据不够、上下文塞不下、或需要历史对照时，再检索补充片段给结论 Prompt——并且必须标明「补充非主证」。

---

## 在流水线里的位置

```text
Skill1+2 → D_platform
Skill3   → anomalies / residual
        │
        ├─(主路径，默认)──────────────────────► Conclusion
        │
        └─(仅当启用条件满足)→ KnowledgeAugmentor  ← 本包
                              · 写入高 evidence_weight 样本
                              · 按需检索 rag_chunks / history_cases
                              · 保存 Skill3 正常/异常弱标签案例
                              · 多变量 z-normalized DTW 召回正反例
                              · augment_used=true|false
                                      │
                                      ▼
                                 Conclusion（优先级最低一档）
```

---

## 何时启用（满足任一）

1. `D_text` 总量超过 LLM 上下文预算，需要压缩/召回代表片段  
2. Skill3 报跨模态/跨尺度异常，或出现 `important` / `critical` 风险  
3. 主控 / Agent **显式**要求历史对照、同类事件背景  

不满足时：`augment_used=false`，输出空列表即可，**不要**强行检索污染 Prompt。

---

## 输入 / 输出契约（冻结）

### 写入侧（被动，每轮 D_platform 更新后）

| 输入 | 说明 |
|------|------|
| `D_platform` | 取高 `evidence_weight` 的 `D_text` + `stance_label` + 元数据 |
| `Skill3` | 写入时序签名、异常类型、最高等级和证据 ID，形成分析案例 |
| 跳过条件 | `is_empty=true` 的轮次不写库 |

建议索引字段：`platform`、`keyword`、`content_id`、`ts`、`stance_label`、`bucket_ts`。

### 检索侧（按需）

| 输入 | 说明 |
|------|------|
| `query` | 主题 / 异常描述 / 结论草稿关键词 |
| `top_k` | 条数上限 |
| `time_range` | 可选时间过滤 |
| `filters` | 平台、立场等 |

### 输出

```text
augment_used           # true | false
rag_chunks[]           # {text, content_id, ts, score, source, stance_label?}
history_cases[]        # 同类事件摘要（可空）
anomaly_examples[]     # 最相似的 2 个 Skill3 异常弱标签案例
normal_examples[]      # 最相似的 1 个正常弱标签案例
retrieval_method       # multivariate_znorm_dtw
write_stats            # 本轮写入条数 / 跳过原因
index_uri              # 向量库或本地索引路径
skill_version
```

### 约束（实现时必须遵守）

- Prompt 优先级：**Skill3 残差/异常 > Skill2 立场 > D_ts > 本 Skill RAG > 原始长尾文本**  
- 与 `D_ts` 冲突时：**以数据源观测为准**，RAG 只能当背景，并记入校准日志  
- 禁止把外平台「通识」写成未引用的本平台事实  
- 分析案例的 `label_source=skill3_weak_label`，默认 `unreviewed`，不得当成人工金标  
- 检索当前事件前先召回历史案例，再写入当前案例，避免自匹配

---

## 目录

```text
KnowledgeAugmentor/
├── README.md           ← 你在这里
├── __init__.py
├── pipeline.py         # write + BM25 retrieve CLI
└── store.py            # JSONL、BM25、历史案例与 DTW 正反例检索
```

---

## 命令行入口

```powershell
# 写入
python -m KnowledgeAugmentor write --in path/to/D_platform.json

# 检索
python -m KnowledgeAugmentor retrieve --query "话题关键词" --top-k 8
```

---

## 实现清单

- [x] 本地 JSONL + BM25 内容检索  
- [x] 写入去重：主键 `(platform, content_id)`  
- [x] 启用条件判定器（对接 Agent 状态机）  
- [x] Skill3 正常/异常弱标签案例库  
- [x] 多变量 z-normalized DTW 正反例检索  
- [x] 与 `Conclusion` Prompt 的「补充非主证」标注约定  
- [x] 正反例检索单测  
- [ ] 人工审核案例标签与金标评测集

---

## 相关文档

- 总设计：[`README.md`](../README.md) §Skill4  
- 数据契约：[`DATASET_SPEC.md`](../DATASET_SPEC.md)  
- 上游：[`MultimodalAnalyzer/`](../MultimodalAnalyzer/)、[`StanceProfiler/`](../StanceProfiler/)  
- 下游：[`Conclusion/`](../Conclusion/)
