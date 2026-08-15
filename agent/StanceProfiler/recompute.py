"""
按 DATASET_SPEC 在标注后重算 D_ts / D_meta / evidence_weight。
不改动 volume/heat 的样本归属与桶集合。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from PlatformCrawler.dataloader.metrics import (
    bias_proxy,
    controversy,
    evidence_weight,
    volume_weighted_bias,
    weighted_mean,
    weighted_std,
)

STANCE_PROFILER_VERSION = "stance_profiler_v1"


def _interact_quantiles(values: list[float]) -> list[float]:
    if not values:
        return []
    order = sorted(values)
    n = len(order)

    def q(v: float) -> float:
        return sum(1 for x in order if x <= v) / n

    return [q(v) for v in values]


def recompute_after_labeling(
    d_platform: dict[str, Any],
    *,
    stance_conf_by_id: dict[str, float],
    labeler_name: str,
    labeler_version: str,
    sample_topk: int = 5,
) -> dict[str, Any]:
    """原地刷新并返回 d_platform。"""
    meta = d_platform["D_meta"]
    texts = d_platform["D_text"]
    series = d_platform["D_ts"]
    platform = meta.get("platform") or "bilibili"

    # 刷新 evidence_weight（保留 interact 分位与文本长度逻辑；anti_spam 缺省 1）
    interacts = [float(t.get("interact") or 0.0) for t in texts]
    quantiles = _interact_quantiles(interacts)
    for t, q in zip(texts, quantiles):
        cid = str(t.get("content_id"))
        conf = float(stance_conf_by_id.get(cid, 0.4))
        t["evidence_weight"] = evidence_weight(
            text=t.get("text") or "",
            interact_val=float(t.get("interact") or 0.0),
            interact_quantile=q,
            anti_spam=1.0,
            stance_conf=conf,
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in texts:
        if t.get("is_empty_placeholder"):
            continue
        if not str(t.get("text") or "").strip():
            continue
        bts = str(t.get("bucket_ts"))
        grouped[bts].append(t)

    for bucket in series:
        bts = str(bucket.get("ts"))
        items = grouped.get(bts, [])
        if not items:
            bucket["sent_mean"] = None
            bucket["sent_std"] = None
            bucket["stance_pos_ratio"] = 0.0
            bucket["stance_neg_ratio"] = 0.0
            bucket["stance_neu_ratio"] = 0.0
            bucket["stance_mixed_ratio"] = 0.0
            bucket["bias_proxy"] = None
            bucket["controversy"] = None
            bucket["is_empty"] = True
            bucket["volume"] = 0
            # heat 保持 0；若旧包非空被掏空不应发生
            bucket["heat"] = 0.0
            bucket["sample_content_ids"] = []
            continue

        # 桶已有 volume/heat：按现有样本重算（与 texts 对齐）
        volume = len(items)
        heat = sum(float(x.get("interact") or 0.0) for x in items)
        weights = [float(x.get("evidence_weight") or 0.0) for x in items]
        sents = [float(x.get("sentiment_score") or 0.0) for x in items]
        labels = [str(x.get("stance_label") or "unclear") for x in items]

        cnt = Counter(labels)
        pos = cnt.get("support", 0)
        neg = cnt.get("oppose", 0)
        mixed = cnt.get("mixed", 0)
        neu = cnt.get("neutral", 0) + cnt.get("unclear", 0)
        total = max(1, pos + neg + mixed + neu)

        bucket["volume"] = volume
        bucket["heat"] = heat
        bucket["sent_mean"] = weighted_mean(sents, weights)
        bucket["sent_std"] = weighted_std(sents, weights)
        bucket["stance_pos_ratio"] = pos / total
        bucket["stance_neg_ratio"] = neg / total
        bucket["stance_neu_ratio"] = neu / total
        bucket["stance_mixed_ratio"] = mixed / total
        bucket["bias_proxy"] = bias_proxy(weights, labels)
        bucket["controversy"] = controversy(pos / total, neg / total)
        bucket["is_empty"] = False
        bucket["n_like_sum"] = sum(float(x.get("like") or 0.0) for x in items)
        samples = sorted(items, key=lambda x: float(x.get("evidence_weight") or 0), reverse=True)[
            :sample_topk
        ]
        bucket["sample_content_ids"] = [str(x["content_id"]) for x in samples]
        ext = dict(bucket.get("ext") or {})
        ext["sent_std_policy"] = "null_if_lt2"
        bucket["ext"] = ext

    # volume_delta / heat_delta / topic_heat_delta
    for i, bucket in enumerate(series):
        if i == 0:
            bucket["volume_delta"] = None
            bucket["heat_delta"] = None
            bucket["topic_heat_delta"] = None
        else:
            bucket["volume_delta"] = float(bucket["volume"]) - float(series[i - 1]["volume"])
            bucket["heat_delta"] = float(bucket["heat"]) - float(series[i - 1]["heat"])
            bucket["topic_heat_delta"] = float(bucket.get("topic_heat") or 0.0) - float(
                series[i - 1].get("topic_heat") or 0.0
            )

    effective = [
        t
        for t in texts
        if not t.get("is_empty_placeholder") and str(t.get("text") or "").strip()
    ]
    n_text = len(effective)
    n_buckets = len(series)
    empty_buckets = sum(1 for b in series if b.get("is_empty"))
    empty_ratio = empty_buckets / n_buckets if n_buckets else 1.0
    is_empty = n_text == 0

    if is_empty:
        stance_global = "neutral"
        bias_score = 0.0
        confidence = 0.15
        sentiment_global_mean = None
    else:
        lab_cnt = Counter(str(t.get("stance_label")) for t in effective)
        stance_global = lab_cnt.most_common(1)[0][0]
        bias_score = volume_weighted_bias(
            (float(b["volume"]), b.get("bias_proxy")) for b in series if not b.get("is_empty")
        )
        confs = [float(stance_conf_by_id.get(str(t["content_id"]), 0.4)) for t in effective]
        confidence = sum(confs) / max(1, len(confs))
        sentiment_global_mean = weighted_mean(
            [float(t.get("sentiment_score") or 0.0) for t in effective],
            [float(t.get("evidence_weight") or 0.0) for t in effective],
        )

    meta["n_text"] = n_text
    meta["n_buckets"] = n_buckets
    meta["empty_ratio"] = empty_ratio
    meta["is_empty"] = is_empty
    meta["stance_global"] = stance_global
    meta["bias_score"] = bias_score
    meta["confidence"] = float(confidence)
    meta["sentiment_global_mean"] = sentiment_global_mean

    versions = dict(meta.get("source_skill_versions") or {})
    versions["stance_profiler"] = STANCE_PROFILER_VERSION
    meta["source_skill_versions"] = versions

    ext = dict(meta.get("ext") or {})
    ext["stance_provisional"] = False
    ext["stance_labeler"] = f"{labeler_name}:{labeler_version}"
    ext["stance_profiler_version"] = STANCE_PROFILER_VERSION
    meta["ext"] = ext

    # 平台字段一致性
    for t in texts:
        t["platform"] = platform

    return d_platform
