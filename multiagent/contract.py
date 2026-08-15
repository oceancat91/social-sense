"""
跨平台消息契约：PlatformReport schema 与规范化工具。

单平台 Agent（如 B 站 `agent/`）跑完 Skill1→6 后，须产出一个符合本契约的
「平台报告」，才能进入多平台对齐 / 融合 / 主控层。

设计原则：
  - 只认 `D_platform` 标准化口径（`D_ts` 核心指标 + 立场分布），平台特有字段放 `ext`；
  - 跨平台不可比指标（热度/互动）在融合层做平台内 z-score / 分位归一，不直接比较原始值；
  - 缺失平台 = 空窗占位，禁止用邻平台插值冒充本平台观测。
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "platform_report_v1"

CANONICAL_STANCE = ("support", "oppose", "neutral", "mixed", "unclear")

# D_ts 中对齐/融合需要用到的时间序列指标（跨平台可比口径）
ALIGNED_METRICS = (
    "volume",
    "heat",
    "sent_mean",
    "sent_std",
    "stance_pos_ratio",
    "stance_neg_ratio",
    "stance_neu_ratio",
    "bias_proxy",
    "controversy",
)


def _num(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _norm_ts(ts: Any) -> str:
    """把桶起点归一化为可对齐键：去时区、取前 16 位（YYYY-MM-DDTHH:MM）。"""
    s = str(ts or "").strip()
    # 去掉末尾时区后缀（+08:00 / Z）
    if s.endswith("Z"):
        s = s[:-1]
    for tz in ("+08:00", "+0800", "-08:00", "-0800"):
        if s.endswith(tz):
            s = s[: -len(tz)]
            break
    return s[:16]  # 日粒度 => YYYY-MM-DDT00:00；小时粒度 => YYYY-MM-DDTHH:00


def normalize_report(raw: dict[str, Any]) -> dict[str, Any]:
    """把单平台产出（无论扁平还是嵌套）补全/规范化成 PlatformReport。

    容错：缺字段给默认值；未知字段不丢弃，塞进 `ext` 保底。
    """
    meta = raw.get("meta") or raw.get("D_meta") or {}
    ot1 = raw.get("OT1") or {}
    skill3 = raw.get("skill3") or {}
    tr = meta.get("time_range") or raw.get("time_range") or {}
    if isinstance(tr, dict):
        start = tr.get("start") or tr.get("since")
        end = tr.get("end") or tr.get("until")
    else:
        start, end = None, None

    # 立场分布：优先 stance_ratios，其次从 D_meta/raw 拼装
    stance_dist = dict(raw.get("stance_dist") or {})
    if not stance_dist:
        ratios = (raw.get("stance_profile") or {}).get("stance_ratios") or {}
        stance_dist = {
            s: float(ratios.get(s) or 0.0) for s in CANONICAL_STANCE
        }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "platform": meta.get("platform") or raw.get("platform"),
        "keyword": meta.get("keyword") or raw.get("keyword"),
        "time_range": {"start": start, "end": end},
        "granularity": meta.get("granularity") or raw.get("granularity") or "day",
        "meta": {
            "n_text": int(meta.get("n_text") or 0),
            "n_buckets": int(meta.get("n_buckets") or 0),
            "empty_ratio": _num(meta.get("empty_ratio"), 0.0) or 0.0,
            "is_empty": bool(meta.get("is_empty")),
            "stance_global": meta.get("stance_global") or raw.get("stance_global"),
            "bias_score": _num(meta.get("bias_score"), 0.0) or 0.0,
            "confidence": _num(meta.get("confidence"), 0.0) or 0.0,
            "sentiment_global_mean": _num(
                meta.get("sentiment_global_mean")
                or (raw.get("stance_profile") or {}).get("sentiment_global_mean"),
                None,
            ),
        },
        "D_ts": raw.get("D_ts") or [],
        "stance_dist": stance_dist,
        "top_tags": [
            (c.get("label") if isinstance(c, dict) else str(c))
            for c in ((raw.get("stance_profile") or {}).get("keyword_clusters") or [])
        ],
        "skill3": {
            "anomalies": skill3.get("anomalies")
            or raw.get("skill3_anomalies")
            or [],
            "need_recrawl": bool(skill3.get("need_recrawl") or raw.get("skill3_need_recrawl")),
        },
        "augment_used": bool(raw.get("augment_used")),
        "OT1": {
            "OT1_status": ot1.get("OT1_status") or raw.get("OT1_status"),
            "claim_trend": ot1.get("claim_trend") or raw.get("claim_trend"),
            "claim_sentiment": ot1.get("claim_sentiment") or raw.get("claim_sentiment"),
            "claim_stance": ot1.get("claim_stance") or raw.get("claim_stance"),
            "uncertainty": ot1.get("uncertainty") or raw.get("uncertainty"),
            "summary_analysis": ot1.get("summary_analysis") or raw.get("summary_analysis") or "",
            "risk_flags": ot1.get("risk_flags") or raw.get("risk_flags") or [],
            "evidence_ids": ot1.get("evidence_ids") or raw.get("evidence_ids") or [],
        },
        "generated_at": raw.get("generated_at"),
    }

    known_keys = set(report.keys())
    ext = {k: v for k, v in raw.items() if k not in known_keys and not k.startswith("_")}
    if ext:
        report["ext"] = ext
    return report


def bucket_metrics(bucket: dict[str, Any]) -> dict[str, float | None]:
    """从 D_ts 桶中抽取对齐指标。"""
    return {m: _num(bucket.get(m), None) for m in ALIGNED_METRICS}
