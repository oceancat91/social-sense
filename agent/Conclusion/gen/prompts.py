"""
Prompt 拼装（Skill5）：严格按优先级把硬证据 → 立场 → 时序 → RAG → 文本组织给 LLM。
"""

from __future__ import annotations

from typing import Any

DTS_COMPACT_FIELDS = [
    "ts",
    "volume",
    "heat",
    "topic_heat",
    "sent_mean",
    "controversy",
    "stance_pos_ratio",
    "stance_neg_ratio",
    "stance_neu_ratio",
    "is_empty",
]


def _clip(text: str, n: int = 120) -> str:
    t = str(text or "").strip().replace("\n", " ")
    return t if len(t) <= n else t[: n - 1] + "…"


def _compact_dts(d_ts: list[dict[str, Any]], max_buckets: int = 60) -> list[dict[str, Any]]:
    n = len(d_ts)
    if n <= max_buckets:
        idx = list(range(n))
    else:
        idx_set = set(range(3)) | set(range(n - 3, n))
        # topic_heat 峰值 ±2
        peak = max(range(n), key=lambda i: float(d_ts[i].get("topic_heat") or 0))
        idx_set |= set(range(max(0, peak - 2), min(n, peak + 3)))
        # 声量 Top-20 桶
        by_vol = sorted(range(n), key=lambda i: -float(d_ts[i].get("volume") or 0))[:20]
        idx_set |= set(by_vol)
        idx = sorted(idx_set)
        if len(idx) > max_buckets:
            idx = idx[:max_buckets]
    return [{k: d_ts[i].get(k) for k in DTS_COMPACT_FIELDS} for i in idx]


def _compact_residual(skill3: dict[str, Any] | None, d_ts: list[dict[str, Any]]) -> dict[str, Any]:
    if not skill3:
        return {"note": "无 Skill3 结果（未接入）"}
    residual = skill3.get("residual") or {}
    top: dict[str, list[dict[str, Any]]] = {}
    for metric, vals in residual.items():
        if not vals:
            continue
        ranked = sorted(
            ((i, v) for i, v in enumerate(vals) if v is not None),
            key=lambda x: -abs(x[1]),
        )[:5]
        top[metric] = [
            {"ts": d_ts[i]["ts"], "residual": round(v, 4)} for i, v in ranked
        ]
    return top


def build_evidence_package(
    d_platform: dict[str, Any],
    stance_profile: dict[str, Any] | None,
    skill3: dict[str, Any] | None,
    rag: dict[str, Any] | None = None,
    *,
    topk_text: int = 15,
    max_buckets: int = 60,
) -> dict[str, Any]:
    meta = d_platform.get("D_meta") or {}
    d_ts = d_platform.get("D_ts") or []
    d_text = d_platform.get("D_text") or []

    texts = [
        t
        for t in d_text
        if not t.get("is_empty_placeholder") and str(t.get("text") or "").strip()
    ]
    texts.sort(key=lambda t: -float(t.get("evidence_weight") or 0))
    top_texts = [
        {
            "content_id": str(t.get("content_id")),
            "ts": t.get("ts"),
            "stance": t.get("stance_label"),
            "sentiment": t.get("sentiment_score"),
            "text": _clip(t.get("text")),
        }
        for t in texts[:topk_text]
    ]

    stance = stance_profile or {}
    pkg: dict[str, Any] = {
        "task": {
            "platform": meta.get("platform"),
            "keyword": meta.get("keyword"),
            "time_range": meta.get("time_range"),
            "granularity": meta.get("granularity"),
            "n_text": meta.get("n_text"),
            "n_buckets": meta.get("n_buckets"),
            "empty_ratio": meta.get("empty_ratio"),
            "is_empty": meta.get("is_empty"),
        },
        # 优先级 1：Skill3 硬证据
        "skill3": {
            "status": (skill3 or {}).get("status"),
            "anomalies": (skill3 or {}).get("anomalies") or [],
            "residual_top": _compact_residual(skill3, d_ts),
            "need_recrawl": (skill3 or {}).get("need_recrawl", False),
            "model_version": (skill3 or {}).get("model_version"),
        },
        # 优先级 2：立场与偏见
        "stance": {
            "stance_global": meta.get("stance_global") or stance.get("stance_global"),
            "bias_score": meta.get("bias_score") or stance.get("bias_score"),
            "confidence": meta.get("confidence") or stance.get("confidence"),
            "stance_ratios": stance.get("stance_ratios"),
            "sentiment_global_mean": meta.get("sentiment_global_mean"),
            "keyword_clusters": stance.get("keyword_clusters"),
        },
        # 优先级 3：时序关键桶
        "D_ts_compact": _compact_dts(d_ts, max_buckets=max_buckets),
        "topic_heat_peak": (meta.get("ext") or {}).get("topic_heat_peak"),
        "topic_heat_peak_ts": (meta.get("ext") or {}).get("topic_heat_peak_ts"),
        # 优先级 4：RAG（补充非主证）
        "rag": {
            "augment_used": bool((rag or {}).get("augment_used")),
            "chunks": (rag or {}).get("rag_chunks") or [],
        },
        # 优先级 5：高权重文本
        "top_texts": top_texts,
    }
    return pkg


SYSTEM_PROMPT = """你是「单平台舆情感知」系统的结论生成模块（Skill5 ConclusionGen）。
你的职责不是「改数字」，而是在给定的硬数据约束下，产出**可读的舆情概括分析与结构化研判**。

硬约束（必须遵守）：
1. 数字与趋势只能来自 Skill3 残差/异常 与 D_ts，禁止臆造或与残差矛盾。
2. 每个实指判断（趋势/情绪/立场）必须绑定至少一个 evidence_id（桶 ts 或 content_id），且必须存在于给定数据中。
3. 空数据（is_empty=true 或 empty_ratio 很高）只允许输出「无观测/证据不足」，禁止臆测。
4. RAG 片段标注为「补充非主证」，与 D_ts 冲突时以 D_ts 为准。
5. summary_analysis 用中文撰写，覆盖：要点概括、声量与情绪解读、立场与阵营、争议与风险、异常说明、不确定与缺口。

只输出一个 JSON 对象，不要 Markdown。JSON schema：
{
  "claim_trend": "up|down|flat|unknown",      // 评论侧 volume/heat 走向
  "claim_topic_trend": "up|down|flat|unknown",// 内容侧 topic_heat 走向
  "claim_sentiment": "up|down|flat|unknown",  // 情绪走向
  "claim_stance": "support|oppose|neutral|mixed|unclear",
  "risk_flags": ["争议/偏见/突变等，中文短语"],
  "evidence_ids": ["桶 ts 或 content_id，必须来自给定数据"],
  "uncertainty": "high|mid|low",
  "summary_analysis": "中文概括分析，覆盖要点/阵营/争议/异常/缺口",
  "cited_bucket_ids": ["桶 ts"],
  "cited_content_ids": ["content_id"]
}"""


def build_user_prompt(pkg: dict[str, Any]) -> str:
    import json

    return "证据包（按优先级排列，硬证据优先）：\n" + json.dumps(pkg, ensure_ascii=False, indent=2)
