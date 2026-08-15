"""
OT₀ / OT₁ 结构化字段定义、归一化与最小校验。
"""

from __future__ import annotations

from typing import Any

TRENDS = {"up", "down", "flat", "unknown"}
STANCES = {"support", "oppose", "neutral", "mixed", "unclear"}
UNCERTAINTIES = {"high", "mid", "low"}

OT0_FIELDS = [
    "claim_trend",
    "claim_topic_trend",
    "claim_sentiment",
    "claim_stance",
    "risk_flags",
    "evidence_ids",
    "uncertainty",
    "summary_analysis",
    "cited_bucket_ids",
    "cited_content_ids",
]


def _enum(v: Any, allowed: set[str], default: str) -> str:
    s = str(v or "").strip().lower()
    return s if s in allowed else default


def _str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def normalize_ot0(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    claim_trend = _enum(raw.get("claim_trend"), TRENDS, "unknown")
    return {
        "claim_trend": claim_trend,
        "claim_topic_trend": _enum(raw.get("claim_topic_trend"), TRENDS, claim_trend),
        "claim_sentiment": _enum(raw.get("claim_sentiment"), TRENDS, "unknown"),
        "claim_stance": _enum(raw.get("claim_stance"), STANCES, "unclear"),
        "risk_flags": _str_list(raw.get("risk_flags")),
        "evidence_ids": _str_list(raw.get("evidence_ids")),
        "uncertainty": _enum(raw.get("uncertainty"), UNCERTAINTIES, "mid"),
        "summary_analysis": str(raw.get("summary_analysis") or "").strip(),
        "cited_bucket_ids": _str_list(raw.get("cited_bucket_ids")),
        "cited_content_ids": _str_list(raw.get("cited_content_ids")),
    }


def is_concrete(ot: dict[str, Any]) -> bool:
    """是否作出可被门禁校验的实指判断。"""
    return any(
        ot.get(k) not in ("unknown", None, "")
        for k in ("claim_trend", "claim_sentiment", "claim_stance")
    )
