"""
Skill6 门禁 G1–G7（纯规则，不依赖 LLM「自评通过」）。

返回 deviation_report 与 status（pass / fail）；全部通过才可释放 OT₁。
"""

from __future__ import annotations

import re
from typing import Any

from ..schema import is_concrete


def _trend(values: list[float | None], eps_ratio: float = 0.05) -> str:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return "unknown"
    third = max(1, len(vals) // 3)
    head = vals[:third]
    tail = vals[-third:]
    h = sum(head) / len(head)
    t = sum(tail) / len(tail)
    rng = max(abs(h), abs(t), 1e-9)
    diff = t - h
    if diff > eps_ratio * rng:
        return "up"
    if diff < -eps_ratio * rng:
        return "down"
    return "flat"


def _all_buckets(d_ts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return d_ts or []


def _check_g1(ot: dict[str, Any], d_ts: list[dict[str, Any]]) -> str | None:
    buckets = _all_buckets(d_ts)
    vol = [float(b.get("volume") or 0) for b in buckets]
    comment_trend = _trend(vol)
    claim = ot.get("claim_trend")
    if claim != "unknown" and claim != comment_trend:
        return f"claim_trend={claim} 但评论声量实际走向为 {comment_trend}"

    topic = [float(b.get("topic_heat") or 0) for b in buckets]
    topic_trend = _trend(topic)
    claim_topic = ot.get("claim_topic_trend")
    if claim_topic != "unknown" and claim_topic != topic_trend:
        return f"claim_topic_trend={claim_topic} 但 topic_heat 实际走向为 {topic_trend}"
    return None


def _check_g2(ot: dict[str, Any], d_ts: list[dict[str, Any]]) -> str | None:
    sent = [b.get("sent_mean") for b in _all_buckets(d_ts)]
    actual = _trend([float(v) if v is not None else None for v in sent])
    claim = ot.get("claim_sentiment")
    if claim == "unknown":
        return None
    if actual == "unknown":
        return f"claim_sentiment={claim} 但情绪样本不足，无法支撑判断"
    if claim != actual:
        return f"claim_sentiment={claim} 但 sent_mean 实际走向为 {actual}"
    return None


def _check_g3(ot: dict[str, Any], d_platform: dict[str, Any]) -> str | None:
    gs = str((d_platform.get("D_meta") or {}).get("stance_global") or "unclear")
    cs = ot.get("claim_stance")
    if cs == "unclear":
        return None
    if gs == "neutral" and cs in ("support", "oppose"):
        return f"claim_stance={cs} 但全局主导立场为 neutral"
    if gs in ("support", "oppose") and cs == {"support": "oppose", "oppose": "support"}.get(gs):
        return f"claim_stance={cs} 与全局主导立场 {gs} 相反"
    return None


def _check_g4(ot: dict[str, Any], d_platform: dict[str, Any]) -> str | None:
    bucket_set = {str(b.get("ts")) for b in d_platform.get("D_ts") or []}
    content_set = {str(t.get("content_id")) for t in d_platform.get("D_text") or []}
    evidence = [str(x) for x in (ot.get("evidence_ids") or [])]
    cited_b = [str(x) for x in (ot.get("cited_bucket_ids") or [])]
    cited_c = [str(x) for x in (ot.get("cited_content_ids") or [])]

    if is_concrete(ot) and not evidence and not cited_b and not cited_c:
        return "存在实指判断但无任何 evidence_id 引用"

    for cid in cited_c:
        if cid not in content_set:
            return f"cited_content_ids 含不存在 ID：{cid}"
    for bid in cited_b:
        if bid not in bucket_set:
            return f"cited_bucket_ids 含不存在桶：{bid}"
    for eid in evidence:
        if eid not in bucket_set and eid not in content_set:
            return f"evidence_ids 含不存在 ID：{eid}"
    return None


def _check_g5(ot: dict[str, Any], d_platform: dict[str, Any]) -> str | None:
    """禁幻觉启发式：越界年份 / 越界百分比。"""
    summary = ot.get("summary_analysis") or ""
    tr = (d_platform.get("D_meta") or {}).get("time_range") or {}
    years = [int(y) for y in re.findall(r"(19\d{2}|20\d{2})", summary)]
    if tr.get("start"):
        sy = int(str(tr["start"])[:4])
        ey = int(str(tr["end"])[:4])
        lo, hi = min(sy, ey) - 1, max(sy, ey) + 1
        for y in years:
            if y < lo or y > hi:
                return f"summary 出现越界年份 {y}（数据窗 {lo}~{hi}）"
    for p in re.findall(r"(\d{1,3}(?:\.\d+)?)%", summary):
        if float(p) > 100:
            return f"summary 出现越界百分比 {p}%"
    return None


def _check_g6(ot: dict[str, Any], d_platform: dict[str, Any], empty_threshold: float) -> str | None:
    meta = d_platform.get("D_meta") or {}
    empty = bool(meta.get("is_empty")) or float(meta.get("empty_ratio") or 0) >= empty_threshold
    if not empty:
        return None
    if ot.get("uncertainty") != "high":
        return "高空窗/空数据下 uncertainty 必须为 high"
    summary = ot.get("summary_analysis") or ""
    if not any(k in summary for k in ("无观测", "证据不足", "数据不足", "样本不足", "缺少", "空窗")):
        return "空数据任务只允许输出「证据不足」类结论，禁止强结论"
    return None


def run_gates(
    ot0: dict[str, Any],
    d_platform: dict[str, Any],
    stance_profile: dict[str, Any] | None = None,
    skill3: dict[str, Any] | None = None,
    rag: dict[str, Any] | None = None,
    *,
    empty_threshold: float = 0.5,
) -> dict[str, Any]:
    d_ts = d_platform.get("D_ts") or []
    checks = [
        ("G1", _check_g1(ot0, d_ts)),
        ("G2", _check_g2(ot0, d_ts)),
        ("G3", _check_g3(ot0, d_platform)),
        ("G4", _check_g4(ot0, d_platform)),
        ("G5", _check_g5(ot0, d_platform)),
        ("G6", _check_g6(ot0, d_platform, empty_threshold)),
    ]
    deviations = [{"gate": g, "msg": m} for g, m in checks if m]
    return {
        "deviations": deviations,
        "status": "pass" if not deviations else "fail",
    }
