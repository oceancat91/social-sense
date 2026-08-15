"""
按 DATASET_SPEC 组装 D_platform。
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .metrics import (
    bias_proxy,
    controversy,
    evidence_weight,
    video_topic_heat,
    volume_weighted_bias,
    weighted_mean,
    weighted_std,
)
from .validate import validate_d_platform

TZ = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = "dataset_schema_v1"
CRAWLER_VERSION = "platform_crawler_v1"
STANCE_VERSION = "stance_lite_v1"  # 正式 StanceProfiler 接入后替换


def _parse_bound(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        if len(s) <= 10:
            dt = datetime.strptime(s, "%Y-%m-%d")
        else:
            try:
                dt = datetime.fromisoformat(s)
            except ValueError:
                dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def _floor_bucket(dt: datetime, granularity: str) -> datetime:
    dt = dt.astimezone(TZ)
    if granularity == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    if granularity == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unsupported granularity: {granularity}")


def _iter_buckets(start: datetime, end: datetime, granularity: str) -> list[datetime]:
    if end <= start:
        raise ValueError("time_range.end must be > start")
    cur = _floor_bucket(start, granularity)
    delta = timedelta(hours=1) if granularity == "hour" else timedelta(days=1)
    buckets: list[datetime] = []
    while cur < end:
        buckets.append(cur)
        cur = cur + delta
    if not buckets:
        buckets.append(_floor_bucket(start, granularity))
    return buckets


def _iso(dt: datetime) -> str:
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def _interact_quantiles(values: list[float]) -> list[float]:
    if not values:
        return []
    order = sorted(values)
    n = len(order)

    def q(v: float) -> float:
        cnt = sum(1 for x in order if x <= v)
        return cnt / n

    return [q(v) for v in values]


def _aggregate_topic_heat_by_bucket(
    videos: list[dict[str, Any]],
    *,
    bucket_iso: list[str],
    granularity: str,
) -> dict[str, dict[str, float]]:
    """
    按视频 pubdate 落入时间桶，汇总话题热度代理。
    返回: bucket_iso -> {topic_volume, topic_heat, topic_play_sum, topic_review_sum}
    """
    out: dict[str, dict[str, float]] = {
        b: {
            "topic_volume": 0.0,
            "topic_heat": 0.0,
            "topic_play_sum": 0.0,
            "topic_review_sum": 0.0,
        }
        for b in bucket_iso
    }
    bucket_set = set(bucket_iso)
    for v in videos:
        pub = v.get("pubdate")
        if not pub:
            continue
        try:
            dt = datetime.fromtimestamp(int(pub), tz=TZ)
        except (TypeError, ValueError, OSError):
            continue
        bts = _iso(_floor_bucket(dt, granularity))
        if bts not in bucket_set:
            continue
        play = float(v.get("play") or 0)
        review = float(v.get("review") or 0)
        favorites = float(v.get("favorites") or 0)
        danmaku = float(v.get("danmaku") or 0)
        cell = out[bts]
        cell["topic_volume"] += 1
        cell["topic_heat"] += video_topic_heat(play, review, favorites, danmaku)
        cell["topic_play_sum"] += play
        cell["topic_review_sum"] += review
    return out


def apply_topic_heat_series(
    d_platform: dict[str, Any],
    videos: list[dict[str, Any]] | None,
    *,
    heat_source: str = "search_pubdate",
) -> dict[str, Any]:
    """把搜索视频池注入 D_ts 的 topic_* 字段（评论 volume/heat 不变）。"""
    videos = videos or []
    meta = d_platform["D_meta"]
    series = d_platform["D_ts"]
    granularity = str(meta.get("granularity") or "day")
    bucket_iso = [str(b["ts"]) for b in series]
    agg = _aggregate_topic_heat_by_bucket(
        videos, bucket_iso=bucket_iso, granularity=granularity
    )

    for i, bucket in enumerate(series):
        cell = agg.get(str(bucket["ts"])) or {
            "topic_volume": 0.0,
            "topic_heat": 0.0,
            "topic_play_sum": 0.0,
            "topic_review_sum": 0.0,
        }
        tv = float(cell["topic_volume"])
        th = float(cell["topic_heat"])
        bucket["topic_volume"] = tv
        bucket["topic_heat"] = th
        bucket["topic_heat_delta"] = (
            None if i == 0 else th - float(series[i - 1].get("topic_heat") or 0.0)
        )
        ext = dict(bucket.get("ext") or {})
        ext["topic_play_sum"] = float(cell["topic_play_sum"])
        ext["topic_review_sum"] = float(cell["topic_review_sum"])
        ext["heat_source"] = heat_source
        bucket["ext"] = ext

    meta_ext = dict(meta.get("ext") or {})
    meta_ext["topic_heat_metric"] = "video_topic_heat_v1"
    meta_ext["topic_heat_source"] = heat_source
    meta_ext["n_heat_videos"] = len(videos)
    meta_ext["topic_heat_formula"] = (
        "sum_v log1p(play)+0.5*log1p(review)+0.25*log1p(favorites)+0.25*log1p(danmaku) "
        "by video pubdate bucket"
    )
    # 话题热度峰值摘要，便于 Agent / 结论引用
    if series:
        peak = max(series, key=lambda b: float(b.get("topic_heat") or 0.0))
        meta_ext["topic_heat_peak_ts"] = peak.get("ts")
        meta_ext["topic_heat_peak"] = float(peak.get("topic_heat") or 0.0)
        meta_ext["topic_volume_sum"] = sum(float(b.get("topic_volume") or 0) for b in series)
        meta_ext["topic_heat_sum"] = sum(float(b.get("topic_heat") or 0) for b in series)
    meta["ext"] = meta_ext
    return d_platform


def build_d_platform(
    clean_bundle: dict[str, Any],
    *,
    keyword: str,
    time_range: tuple[str | datetime, str | datetime],
    granularity: str = "day",
    platform: str = "bilibili",
    sample_topk: int = 5,
    stance_profiler_version: str | None = None,
    heat_videos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if granularity not in ("hour", "day"):
        raise ValueError("granularity must be hour|day")

    start = _parse_bound(time_range[0])
    end = _parse_bound(time_range[1])
    records = list(clean_bundle.get("records") or [])

    interacts = [float(r.get("interact") or 0.0) for r in records]
    quantiles = _interact_quantiles(interacts)
    for r, q in zip(records, quantiles):
        r["evidence_weight"] = evidence_weight(
            text=r.get("text") or "",
            interact_val=float(r.get("interact") or 0.0),
            interact_quantile=q,
            anti_spam=float(r.get("_anti_spam") or 1.0),
            stance_conf=float(r.get("_stance_conf") or 0.4),
        )

    buckets = _iter_buckets(start, end, granularity)
    bucket_iso = [_iso(b) for b in buckets]
    bucket_index = {b: i for i, b in enumerate(bucket_iso)}

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    d_text: list[dict[str, Any]] = []

    for r in records:
        dt = datetime.fromisoformat(r["ts"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        bts = _iso(_floor_bucket(dt.astimezone(TZ), granularity))
        if bts not in bucket_index:
            continue
        row = {
            "platform": platform,
            "content_id": str(r["content_id"]),
            "parent_id": r.get("parent_id"),
            "author_id": r.get("author_id"),
            "ts": r["ts"],
            "ts_unix": int(r.get("ts_unix") or dt.timestamp()),
            "text": r.get("text") or "",
            "like": float(r.get("like") or 0),
            "reply_count": float(r.get("reply_count") or 0),
            "share_or_coin": float(r.get("share_or_coin") or 0),
            "interact": float(r.get("interact") or 0),
            "source_url": r.get("source_url"),
            "stance_label": r.get("stance_label") or "unclear",
            "sentiment_score": float(r.get("sentiment_score") or 0.0),
            "topic_tags": list(r.get("topic_tags") or []),
            "evidence_weight": float(r.get("evidence_weight") or 0.0),
            "is_empty_placeholder": False,
            "bucket_ts": bts,
            "lang": r.get("lang") or "zh",
            "ext": r.get("ext") or {},
        }
        d_text.append(row)
        grouped[bts].append(row)

    d_ts: list[dict[str, Any]] = []
    for i, bts in enumerate(bucket_iso):
        items = grouped.get(bts, [])
        is_empty = len(items) == 0
        if is_empty:
            d_ts.append(
                {
                    "ts": bts,
                    "ts_unix": int(datetime.fromisoformat(bts).timestamp()),
                    "platform": platform,
                    "volume": 0,
                    "heat": 0.0,
                    "sent_mean": None,
                    "sent_std": None,
                    "stance_pos_ratio": 0.0,
                    "stance_neg_ratio": 0.0,
                    "stance_neu_ratio": 0.0,
                    "stance_mixed_ratio": 0.0,
                    "bias_proxy": None,
                    "controversy": None,
                    "volume_delta": None if i == 0 else 0 - d_ts[i - 1]["volume"],
                    "heat_delta": None if i == 0 else 0.0 - float(d_ts[i - 1]["heat"]),
                    "n_like_sum": 0,
                    "is_empty": True,
                    "sample_content_ids": [],
                    "topic_volume": 0.0,
                    "topic_heat": 0.0,
                    "topic_heat_delta": None,
                    "ext": {"sent_std_policy": "null_if_lt2"},
                }
            )
            continue

        volume = len(items)
        heat = sum(float(x["interact"]) for x in items)
        weights = [float(x["evidence_weight"]) for x in items]
        sents = [float(x["sentiment_score"]) for x in items]
        labels = [str(x["stance_label"]) for x in items]

        cnt = Counter(labels)
        pos = cnt.get("support", 0)
        neg = cnt.get("oppose", 0)
        mixed = cnt.get("mixed", 0)
        neu = cnt.get("neutral", 0) + cnt.get("unclear", 0)
        total = max(1, pos + neg + mixed + neu)
        pos_r = pos / total
        neg_r = neg / total
        neu_r = neu / total
        mixed_r = mixed / total

        samples = sorted(items, key=lambda x: x["evidence_weight"], reverse=True)[:sample_topk]
        d_ts.append(
            {
                "ts": bts,
                "ts_unix": int(datetime.fromisoformat(bts).timestamp()),
                "platform": platform,
                "volume": volume,
                "heat": heat,
                "sent_mean": weighted_mean(sents, weights),
                "sent_std": weighted_std(sents, weights),
                "stance_pos_ratio": pos_r,
                "stance_neg_ratio": neg_r,
                "stance_neu_ratio": neu_r,
                "stance_mixed_ratio": mixed_r,
                "bias_proxy": bias_proxy(weights, labels),
                "controversy": controversy(pos_r, neg_r),
                "volume_delta": None if i == 0 else volume - d_ts[i - 1]["volume"],
                "heat_delta": None if i == 0 else heat - float(d_ts[i - 1]["heat"]),
                "n_like_sum": sum(float(x["like"]) for x in items),
                "is_empty": False,
                "sample_content_ids": [x["content_id"] for x in samples],
                "topic_volume": 0.0,
                "topic_heat": 0.0,
                "topic_heat_delta": None,
                "ext": {"sent_std_policy": "null_if_lt2"},
            }
        )

    n_text = len(d_text)
    n_buckets = len(d_ts)
    empty_buckets = sum(1 for b in d_ts if b["is_empty"])
    empty_ratio = empty_buckets / n_buckets if n_buckets else 1.0
    is_empty = n_text == 0

    if is_empty:
        stance_global = "neutral"
        bias_score = 0.0
        confidence = 0.15
        sentiment_global_mean = None
    else:
        lab_cnt = Counter(x["stance_label"] for x in d_text)
        stance_global = lab_cnt.most_common(1)[0][0]
        bias_score = volume_weighted_bias(
            (float(b["volume"]), b["bias_proxy"]) for b in d_ts if not b["is_empty"]
        )
        confs = [float(r.get("_stance_conf") or 0.4) for r in records]
        confidence = sum(confs) / max(1, len(confs))
        sentiment_global_mean = weighted_mean(
            [float(x["sentiment_score"]) for x in d_text],
            [float(x["evidence_weight"]) for x in d_text],
        )

    for r in records:
        r.pop("_anti_spam", None)
        r.pop("_stance_conf", None)

    d_meta = {
        "platform": platform,
        "keyword": keyword,
        "time_range": {"start": _iso(start), "end": _iso(end)},
        "timezone": "Asia/Shanghai",
        "granularity": granularity,
        "n_text": n_text,
        "n_text_raw_in": int(clean_bundle.get("n_raw_in") or 0),
        "n_buckets": n_buckets,
        "empty_ratio": empty_ratio,
        "is_empty": is_empty,
        "stance_global": stance_global,
        "bias_score": bias_score,
        "confidence": float(confidence),
        "sentiment_global_mean": sentiment_global_mean,
        "clean_rule_version": clean_bundle.get("clean_rule_version") or "clean_c1c8_v1",
        "source_skill_versions": {
            "platform_crawler": CRAWLER_VERSION,
            "stance_profiler": stance_profiler_version or STANCE_VERSION,
        },
        "ext": {
            "metric_profile": "dataset_spec_v1_default",
            "merge_policy": "keep_higher_interact",
            "sent_std_policy": "null_if_lt2",
            "stance_provisional": stance_profiler_version is None,
            "clean_log": clean_bundle.get("clean_log") or [],
            "n_quarantine": len(clean_bundle.get("quarantine") or []),
            "n_out_of_range": len(clean_bundle.get("out_of_range") or []),
            "alpha_reply": 1.0,
            "beta_share": 1.0,
        },
    }

    d_platform = {
        "schema_version": SCHEMA_VERSION,
        "D_meta": d_meta,
        "D_text": d_text,
        "D_ts": d_ts,
    }
    apply_topic_heat_series(d_platform, heat_videos)
    validate_d_platform(d_platform)
    return d_platform


def save_d_platform(d_platform: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(d_platform, f, ensure_ascii=False, indent=2)
    return path


def build_from_comment_csvs(
    csv_paths: list[str | Path],
    *,
    keyword: str,
    time_range: tuple[str, str],
    granularity: str = "day",
    platform: str = "bilibili",
    out_path: str | Path | None = None,
    heat_videos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from .cleaner import clean_records, load_many_comment_csvs

    start = _parse_bound(time_range[0])
    end = _parse_bound(time_range[1])
    raw = load_many_comment_csvs(csv_paths)
    bundle = clean_records(raw, time_range=(start, end), platform=platform)
    d_platform = build_d_platform(
        bundle,
        keyword=keyword,
        time_range=(start, end),
        granularity=granularity,
        platform=platform,
        heat_videos=heat_videos,
    )
    if out_path:
        save_d_platform(d_platform, out_path)
        d_platform["D_meta"]["text_uri"] = str(Path(out_path).resolve())
        save_d_platform(d_platform, out_path)
    return d_platform
