"""
多平台融合器：在 AlignedBundle 之上计算跨平台一致/分歧与「信息茧房」证据。

社会价值落点：打破平台私域的信息茧房 —— 用可量化的分歧指标
（立场分歧 / 情绪分歧 / 声量共振）暴露「同一话题在不同平台的舆论场分裂」，
并输出「茧房指数」供主控 Agent 与产品层引用。
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any

from .contract import CANONICAL_STANCE


def _js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """立场分布 Jensen-Shannon 散度（对称、有界 [0, ln2]）。"""
    keys = CANONICAL_STANCE
    m = {k: (float(p.get(k) or 0.0) + float(q.get(k) or 0.0)) / 2 for k in keys}

    def kl(a: dict[str, float], b: dict[str, float]) -> float:
        s = 0.0
        for k in keys:
            ak = max(float(a.get(k) or 0.0), 1e-9)
            bk = max(float(b.get(k) or 0.0), 1e-9)
            s += ak * math.log(ak / bk)
        return s

    return 0.5 * (kl(p, m) + kl(q, m))


def _pearson(x: list[float | None], y: list[float | None]) -> float | None:
    """仅用两端都有值的对齐点计算 Pearson 相关。"""
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    n = len(pairs)
    if n < 2:
        return None
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    cov = sum((a - mx) * (b - my) for a, b in pairs)
    vx = sum((a - mx) ** 2 for a, _ in pairs)
    vy = sum((b - my) ** 2 for _, b in pairs)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def fuse(aligned: dict[str, Any], reports: list[dict[str, Any]]) -> dict[str, Any]:
    """在对齐结果上计算跨平台融合指标。"""
    platforms: list[str] = aligned["platforms"]
    reports_by_platform = {str(r.get("platform")): r for r in reports}
    z_series = aligned.get("z_series") or {}

    # ---------- 全局立场 / 情绪分歧 ---------- #
    stance_dists = {p: (reports_by_platform[p].get("stance_dist") or {}) for p in platforms}
    sentiment_means = {
        p: (reports_by_platform[p].get("meta") or {}).get("sentiment_global_mean")
        for p in platforms
    }
    bias_scores = {
        p: (reports_by_platform[p].get("meta") or {}).get("bias_score") or 0.0
        for p in platforms
    }

    stance_divergence = 0.0
    stance_pairs: list[dict[str, Any]] = []
    if len(platforms) >= 2:
        vals = [
            _js_divergence(stance_dists[a], stance_dists[b])
            for a, b in combinations(platforms, 2)
        ]
        stance_divergence = sum(vals) / len(vals)
        for (a, b), v in zip(combinations(platforms, 2), vals):
            stance_pairs.append(
                {"pair": [a, b], "stance_js": round(v, 4)}
            )

    sent_vals = [v for v in sentiment_means.values() if v is not None]
    sentiment_divergence = (
        (max(sent_vals) - min(sent_vals)) if len(sent_vals) >= 2 else 0.0
    )

    # ---------- 声量共振（跨平台时间相关性） ---------- #
    temporal_corr: list[dict[str, Any]] = []
    corr_vals: list[float] = []
    if len(platforms) >= 2:
        for a, b in combinations(platforms, 2):
            r = _pearson(
                (z_series.get(a) or {}).get("volume") or [],
                (z_series.get(b) or {}).get("volume") or [],
            )
            temporal_corr.append({"pair": [a, b], "volume_corr": round(r, 4) if r is not None else None})
            if r is not None:
                corr_vals.append(r)

    mean_corr = sum(corr_vals) / len(corr_vals) if corr_vals else None

    # ---------- 主导立场与冲突 ---------- #
    dominant_stance: dict[str, str | None] = {}
    for p in platforms:
        d = stance_dists.get(p) or {}
        if d and any(v > 0 for v in d.values()):
            dominant_stance[p] = max(d, key=lambda k: d.get(k) or 0.0)
        else:
            dominant_stance[p] = None

    def _conflict_score() -> float:
        ds = [s for s in dominant_stance.values() if s]
        if len(ds) < 2:
            return 0.0
        opp_pairs = {("support", "oppose"), ("oppose", "support")}
        has_opp = any((a, b) in opp_pairs for a, b in combinations(ds, 2))
        if has_opp:
            return 1.0  # 主导立场正面对立：最强茧房信号
        if len(set(ds)) > 1:
            return 0.5  # 主导立场不一致但非正面对立
        return 0.0

    # ---------- 茧房指数 ---------- #
    # 分歧越大、共振越弱 → 信息茧房越强；归一化到 [0,1]
    stance_component = min(1.0, stance_divergence / 0.5)  # JS ~0.5 视为强分歧
    stance_component = max(stance_component, _conflict_score())
    sentiment_component = min(1.0, abs(sentiment_divergence) / 1.0)  # [-1,1] 极差
    corr_component = 1.0 - (mean_corr if mean_corr is not None else 1.0)  # 无共振=1
    echo_chamber = round(
        0.4 * stance_component + 0.3 * sentiment_component + 0.3 * corr_component, 4
    )

    # ---------- 分桶跨平台分歧（可选细粒度） ---------- #
    per_bucket: list[dict[str, Any]] = []
    time_axis = aligned["time_axis"]
    aligned_ts = aligned.get("aligned_ts") or {}
    for i, t in enumerate(time_axis):
        sent_bucket = []
        active = 0
        for p in platforms:
            b = (aligned_ts.get(p) or [None] * len(time_axis))[i]
            if b and not b.get("is_empty"):
                active += 1
                if b.get("sent_mean") is not None:
                    sent_bucket.append(float(b["sent_mean"]))
        if active >= 2 and len(sent_bucket) >= 2:
            per_bucket.append(
                {
                    "ts": t,
                    "active_platforms": active,
                    "sent_range": round(max(sent_bucket) - min(sent_bucket), 4),
                }
            )

    return {
        "platforms": platforms,
        "stance_dist": stance_dists,
        "dominant_stance": dominant_stance,
        "stance_divergence": round(stance_divergence, 4),
        "stance_pair_divergences": stance_pairs,
        "sentiment_divergence": round(sentiment_divergence, 4),
        "sentiment_means": {p: (round(v, 4) if v is not None else None) for p, v in sentiment_means.items()},
        "bias_scores": {p: round(v, 4) for p, v in bias_scores.items()},
        "temporal_corr": temporal_corr,
        "mean_volume_corr": round(mean_corr, 4) if mean_corr is not None else None,
        "echo_chamber_score": echo_chamber,
        "echo_chamber_components": {
            "stance": round(stance_component, 4),
            "sentiment": round(sentiment_component, 4),
            "corr": round(corr_component, 4),
        },
        "per_bucket_divergence": per_bucket,
    }
