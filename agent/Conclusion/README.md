# Conclusion（结论生成 + 残差校准）

> **对应设计**：根目录 [`README.md`](../README.md)  
> - **Skill 5 · ConclusionGen**（概括分析 → OT₀）  
> - **Skill 6 · ResidualCalibrator**（强制校准 → OT₁）  
> **状态**：**留白占位**，目录与契约已定，实现尚未接入。  
> **原则**：LLM 做**可读研判**；数字与趋势以 Skill3 残差 / `D_ts` / 立场为准，校准门禁可驳回。

---

## 一句话

在硬数据约束下，让 LLM 写出单平台舆情的**概括分析与结构化主张（OT₀）**，再经规则 + 可选改写的**严格校准**得到可提交的 OT₁；校准不通过就不能当「有效结论」交给上层多平台对齐。

---

## 在流水线里的位置

```text
D_platform + stance_profile
MultimodalAnalyzer → residual / anomalies / baseline
KnowledgeAugmentor → rag_chunks（可选，augment_used）
        │
        ▼
Conclusion /
  ├─ gen/     Skill5  ConclusionGen     → OT₀
  └─ calib/   Skill6  ResidualCalibrator → OT₁ 或 reject
        │
        ▼
单平台标准化舆情包（结论集）→ 上层对齐仲裁
```

本包 = Skill5 + Skill6 的代码落点；两者必须成对出现，**禁止跳过校准直接外发 OT₀**。

---

## Skill5 · 结论生成（OT₀）

### 职责

在约束下做分析性输出，而不是改数：

1. 要点概括（讨论焦点、高频议题）  
2. 声量 / 热度解读（评论 `heat` + 长轴 `topic_heat`）  
3. 立场与阵营叙述  
4. 争议与风险  
5. 对 Skill3 异常的可读解释（须引用 `evidence_ids`）  
6. 不确定与数据缺口（空窗、样本不足）

### Prompt 优先级（高 → 低，不可颠倒）

1. Skill3：`residual` + `anomalies` + `baseline`（硬约束，放 Prompt 首部）  
2. Skill2：`stance_profile` / `D_meta` 立场与偏见  
3. `D_ts` 关键桶摘要（含 `topic_heat` 峰值）  
4. Skill4：`rag_chunks`（仅 `augment_used=true`，标注「补充非主证」）  
5. `D_text` 高权重样本（条数上限可配）

### OT₀ 最小字段

```text
claim_trend          # up | down | flat | unknown   （可区分 comment_heat / topic_heat）
claim_sentiment      # 情绪走向
claim_stance         # 主导立场
risk_flags[]         # 争议 / 偏见 / 突变等
evidence_ids[]       # 桶 ts 或 content_id，必须落在本轮 D_platform
uncertainty          # high | mid | low
summary_analysis     # 自然语言概括分析
cited_bucket_ids[]   # 可选，与 evidence 对齐
cited_content_ids[]  # 可选
```

### 硬约束

- 不得与 `residual` 显著矛盾（例如残差显示未升温却写「热度暴涨」）  
- 每个实指判断至少一条 `evidence_ids`  
- `is_empty` / 高 `empty_ratio`：只允许「无观测 / 证据不足」，禁止臆测  

---

## Skill6 · 残差校准（OT₁）

### 职责

对照真实 `D_ts`、立场基准、Skill3 残差，对 OT₀ **纠偏 / 删幻觉 / 补引用 / 通过或驳回**。  
不从零重写整篇分析；通过后的 OT₁ 保留完整叙述，只去掉与数据冲突的部分。

### 门禁 G1–G7（须全部理解后再实现）

| 检查 | 规则 | 不通过 |
|------|------|--------|
| G1 趋势 | `claim_trend` 与 volume/heat/`topic_heat` 残差及异常类型一致 | 驳回重生或 `uncertainty=high` |
| G2 情绪 | 与 `sent_mean` 变化方向一致（容差可配） | 同上 |
| G3 立场 | 与全局/主导桶立场占比一致 | 同上 |
| G4 证据 | 每个实指 claim 的 ID 存在于本轮数据 | 删句或整单驳回 |
| G5 禁幻觉 | 不引用平台外未出现事实；RAG 与 D_ts 冲突时站 D_ts | 删冲突句 |
| G6 空窗 | 空数据禁止强结论 | 改写为证据不足 |
| G7 轮次 | 默认 1 轮，最多 `max_calib_rounds`（建议 ≤2） | `failed_calibration` |

**通过**：G1–G6 全过 → `OT₁_status=accepted`。  
否则不得进入上层「有效结论」通道（可保留失败包调试）。

### 输出

```text
deviation_report           # 逐条偏差说明
calibration_constraints    # 回写给重生 Prompt 的约束
OT1                        # 修订后的结论（结构同 OT₀ + status）
OT1_status                 # accepted | reject | failed_calibration
```

---

## 建议目录（实现时）

```text
Conclusion/
├── README.md              ← 你在这里
├── __init__.py
├── pipeline.py            # gen → calib 串联入口（待写）
├── gen/                   # Skill5 ConclusionGen
│   ├── prompts.py
│   └── schema.py          # OT₀ 结构化解析
├── calib/                 # Skill6 ResidualCalibrator
│   ├── gates.py           # G1–G7
│   └── rewrite.py         # 受限改写
└── outputs/
```

---

## 计划入口（尚未实现）

```powershell
# 预期：读入 D_platform + Skill3 产物（+ 可选 RAG）→ 写出 OT0/OT1
python -m Conclusion --d-platform path/to/D_platform.json --analysis path/to/skill3.json
```

---

## 实现清单（留给后续）

- [ ] OT₀ / OT₁ JSON Schema 与校验  
- [ ] Prompt 拼装严格按优先级  
- [ ] DeepSeek（或其它）调用与结构化解析  
- [ ] G1–G7 纯规则实现（不依赖 LLM「自评通过」）  
- [ ] 与 `topic_heat` / 评论 `heat` 双热度口径的 claim 拆分或标注  
- [ ] 空包 / 高空窗单测  
- [ ] 对接 Agent 状态机（校准失败可回写重生 1 次）  

---

## 相关文档

- 总设计：[`README.md`](../README.md) §Skill5、§Skill6、**§五（概括分析 ≠ 仅校准）**  
- 数据契约：[`DATASET_SPEC.md`](../DATASET_SPEC.md)  
- 上游：[`MultimodalAnalyzer/`](../MultimodalAnalyzer/)、[`KnowledgeAugmentor/`](../KnowledgeAugmentor/)、[`StanceProfiler/`](../StanceProfiler/)  
- Agent：[`Agent/`](../Agent/)（当前仅调度 Skill1+2，本包接入后由此串联）
