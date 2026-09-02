# MultimodalAnalyzer（多模态时序–文本分析 Skill）

> **对应设计**：根目录 [`README.md`](../README.md) **Skill 3 · MultimodalTemporalAnalyzer**  
> **状态**：**已实现并接入 Skill1→6 与后端 Agent Engine**。  
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
MultimodalAnalyzer（Skill3）  ← 本包
  · 多尺度时序塔：短/中/长窗口稳健残差与尺度一致性
  · 文本塔：桶内高权重样本语义
  · 融合 → anomalies / severity / multiscale / residual / hidden_states
        │
        ├─(主路径)→ Conclusion（OT₀ / 校准 OT₁）
        └─(可选)→ need_recrawl → Skill1 缩小窗补采 → Skill2 刷新 → 本 Skill 重跑（≤1 轮）
```

---

## 已实现能力

1. **哪天声量/热度突变？**（含评论侧 `heat` 与内容侧 `topic_heat`）  
2. **情绪或立场是否翻转？**  
3. **文本语义与数值轨迹是否打架？**（`cross_modal_inconsistency`）  
4. **相对正常基线，残差有多大？**（供校准门禁 G1–G2）  
5. **要不要建议补采？**（`need_recrawl`）
6. **异常在哪个时间尺度最突出？**（`dominant_scale` / `scale_scores`）  
7. **短、中、长尺度是否互相矛盾？**（`cross_scale_inconsistency`）  
8. **风险等级与确定性原因是什么？**（`severity` / `confidence` / `reason`）

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
anomalies[]            # {ts, type, score, severity, confidence, reason, evidence_ids}
  type 示例:
    volume_spike | heat_spike | topic_heat_spike
    sentiment_flip | stance_shift | cross_modal_inconsistency
    semantic_drift | cross_scale_inconsistency
multiscale              # windows / primary_window / 各尺度 z_scores
risk_summary            # max_severity + severity_counts
hidden_states          # 中间表征引用 / 外置路径（不直接当结论）
residual               # 分指标：pred - actual
baseline               # 正常基线轨迹（与 D_ts 对齐）
need_recrawl           # bool
recrawl_windows[]      # 可选，加密时间窗建议
model_version          # 本 Skill 版本号
```

---

## 当前模型形态

| 模块 | 职责 |
|------|------|
| 时序塔 | 短/中/长尺度滑动中位数 + MAD 稳健 z-score |
| 文本塔 | 对桶内加权 / Top-K 文本编码语义漂移 |
| 跨尺度头 | 比较各尺度标准化残差，检测尺度关联不一致 |
| 融合头 | 时间步对齐 → 异常分数、类型、等级、残差向量 |

跨尺度部分借鉴 CrossAD，但采用无训练的轻量实现：不直接部署 Transformer
重构模型，而是用多尺度稳健残差近似“不同尺度对同一异常的响应差异”，适合当前
舆情数据规模与云端算力。

**禁止**：用 LLM 重新「估」一套与残差冲突的热度/情绪曲线。本 Skill 负责「测得到」的定量证据。

---

## 目录

```text
MultimodalAnalyzer/
├── README.md          ← 你在这里
├── __init__.py
├── pipeline.py        # CLI 入口
├── analyzer.py        # 编排与多尺度融合
├── temporal.py        # 稳健基线、多尺度统计
├── text_tower.py      # 桶级文本表征
├── detectors.py       # 异常规则、风险分级
└── outputs/           # 本地调试产物
```

---

## 命令行入口

```powershell
python -m MultimodalAnalyzer --in dataset/events/<event_id>/D_platform.json \
  --scale-windows 3,7,15 --tau-cross-scale 2.5
```

---

## 实现清单

- [x] 读取并校验 `D_platform`  
- [x] 时序特征矩阵（含 `topic_heat`）  
- [x] 文本塔抽样策略（按 `evidence_weight`）  
- [x] 异常类型枚举、阈值与风险等级  
- [x] CrossAD 启发的多尺度残差与尺度不一致检测  
- [x] `need_recrawl` 回调协议（对接 Agent / Skill1）  
- [x] 空数据兼容  
- [x] 多尺度与风险分级单测  

---

## 相关文档

- 总设计：[`README.md`](../README.md) §Skill3、§五（与 LLM 分工）  
- 数据契约：[`DATASET_SPEC.md`](../DATASET_SPEC.md)  
- 上游：[`PlatformCrawler/`](../PlatformCrawler/)、[`StanceProfiler/`](../StanceProfiler/)  
- 下游：[`Conclusion/`](../Conclusion/)、[`KnowledgeAugmentor/`](../KnowledgeAugmentor/)
