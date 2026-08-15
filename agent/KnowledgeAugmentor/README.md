# KnowledgeAugmentor（知识增强 Skill）

> **对应设计**：根目录 [`README.md`](../README.md) **Skill 4 · KnowledgeAugmentor**  
> **状态**：**留白占位**，目录与契约已定，实现尚未接入。  
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
        └─(仅当启用条件满足)→ KnowledgeAugmentor  ← 本包（待实现）
                              · 写入高 evidence_weight 样本
                              · 按需检索 rag_chunks / history_cases
                              · augment_used=true|false
                                      │
                                      ▼
                                 Conclusion（优先级最低一档）
```

---

## 何时启用（满足任一）

1. `D_text` 总量超过 LLM 上下文预算，需要压缩/召回代表片段  
2. Skill3 报 `cross_modal_inconsistency`，或结论侧证据覆盖不足  
3. 主控 / Agent **显式**要求历史对照、同类事件背景  

不满足时：`augment_used=false`，输出空列表即可，**不要**强行检索污染 Prompt。

---

## 输入 / 输出契约（冻结）

### 写入侧（被动，每轮 D_platform 更新后）

| 输入 | 说明 |
|------|------|
| `D_platform` | 取高 `evidence_weight` 的 `D_text` + `stance_label` + 元数据 |
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
write_stats            # 本轮写入条数 / 跳过原因
index_uri              # 向量库或本地索引路径
skill_version
```

### 约束（实现时必须遵守）

- Prompt 优先级：**Skill3 残差/异常 > Skill2 立场 > D_ts > 本 Skill RAG > 原始长尾文本**  
- 与 `D_ts` 冲突时：**以数据源观测为准**，RAG 只能当背景，并记入校准日志  
- 禁止把外平台「通识」写成未引用的本平台事实  

---

## 建议目录（实现时）

```text
KnowledgeAugmentor/
├── README.md           ← 你在这里
├── __init__.py
├── pipeline.py         # write + retrieve 入口（待写）
├── store/              # 向量库 / 本地 JSONL 索引
├── retriever/          # 检索与重排
└── outputs/
```

---

## 计划入口（尚未实现）

```powershell
# 写入
python -m KnowledgeAugmentor write --in path/to/D_platform.json

# 检索
python -m KnowledgeAugmentor retrieve --query "话题关键词" --top-k 8
```

---

## 实现清单（留给后续）

- [ ] 嵌入模型与索引后端选型（本地优先，可换）  
- [ ] 写入去重：主键 `(platform, content_id)`  
- [ ] 启用条件判定器（对接 Agent 状态机）  
- [ ] `rag_chunks` schema 校验  
- [ ] 与 `Conclusion` Prompt 的「补充非主证」标注约定  
- [ ] 单测：空包跳过写入 / 冲突时不覆盖 D_ts  

---

## 相关文档

- 总设计：[`README.md`](../README.md) §Skill4  
- 数据契约：[`DATASET_SPEC.md`](../DATASET_SPEC.md)  
- 上游：[`MultimodalAnalyzer/`](../MultimodalAnalyzer/)、[`StanceProfiler/`](../StanceProfiler/)  
- 下游：[`Conclusion/`](../Conclusion/)
