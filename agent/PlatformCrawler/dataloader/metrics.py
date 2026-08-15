"""
规范指标口径（DATASET_SPEC §6）
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence


EPS = 1e-9
ALPHA_REPLY = 1.0
BETA_SHARE = 1.0


def clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def interact(like: float, reply_count: float, share_or_coin: float = 0.0) -> float:
    """interact = log(1 + like + α*reply + β*share)"""
    return math.log1p(
        max(0.0, like)
        + ALPHA_REPLY * max(0.0, reply_count)
        + BETA_SHARE * max(0.0, share_or_coin)
    )


def controversy(pos_ratio: float, neg_ratio: float) -> float:
    """controversy = 4 * p * n"""
    return 4.0 * float(pos_ratio) * float(neg_ratio)


def stance_to_signed(label: str) -> int:
    mapping = {
        "support": 1,
        "oppose": -1,
        "neutral": 0,
        "unclear": 0,
        "mixed": 0,
    }
    return mapping.get(label, 0)


def bias_proxy(weights: Sequence[float], labels: Sequence[str]) -> float | None:
    if not weights:
        return None
    num = 0.0
    den = 0.0
    for w, lab in zip(weights, labels):
        num += float(w) * stance_to_signed(lab)
        den += float(w)
    return abs(num / (den + EPS))


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float | None:
    if not values:
        return None
    num = sum(float(v) * float(w) for v, w in zip(values, weights))
    den = sum(float(w) for w in weights)
    if den <= 0:
        return None
    return num / den


def weighted_std(values: Sequence[float], weights: Sequence[float]) -> float | None:
    """空窗/单样本：返回 None（sent_std_policy=null_if_lt2）。"""
    if len(values) < 2:
        return None
    mean = weighted_mean(values, weights)
    if mean is None:
        return None
    den = sum(float(w) for w in weights)
    var = sum(float(w) * (float(v) - mean) ** 2 for v, w in zip(values, weights)) / (den + EPS)
    return math.sqrt(max(0.0, var))


def evidence_weight(
    text: str,
    interact_val: float,
    interact_quantile: float,
    anti_spam: float,
    stance_conf: float,
) -> float:
    """
    evidence_weight = clip(w_len * w_interact * w_anti_spam * w_stance_conf)
    interact_quantile: 该样本 interact 在批次中的分位 ∈[0,1]
    anti_spam / stance_conf ∈[0,1]
    """
    n = len(text.strip())
    if n <= 0:
        w_len = 0.0
    elif n < 4:
        w_len = 0.35
    elif n < 12:
        w_len = 0.7
    elif n <= 500:
        w_len = 1.0
    else:
        w_len = 0.85

    w_interact = 0.4 + 0.6 * clip01(interact_quantile)
    return clip01(w_len * w_interact * clip01(anti_spam) * clip01(stance_conf))


def volume_weighted_bias(bias_list: Iterable[tuple[float, float]]) -> float:
    """bias_list: (volume, bias_proxy) for non-empty buckets."""
    num = 0.0
    den = 0.0
    for vol, b in bias_list:
        if b is None:
            continue
        num += float(vol) * float(b)
        den += float(vol)
    if den <= 0:
        return 0.0
    return clip01(num / den)


def video_topic_heat(
    play: float,
    review: float = 0.0,
    favorites: float = 0.0,
    danmaku: float = 0.0,
) -> float:
    """
    话题热度（内容侧代理，非评论 heat）。
    按视频发布日落入桶后求和，反映「该日相关内容的综合热度」。
    heat_v = log1p(play) + 0.5*log1p(review) + 0.25*log1p(favorites) + 0.25*log1p(danmaku)
    """
    return (
        math.log1p(max(0.0, float(play)))
        + 0.5 * math.log1p(max(0.0, float(review)))
        + 0.25 * math.log1p(max(0.0, float(favorites)))
        + 0.25 * math.log1p(max(0.0, float(danmaku)))
    )

