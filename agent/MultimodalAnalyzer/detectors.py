"""
异常检测规则：把时序塔残差与文本塔漂移融合成带类型的异常点。

类型枚举（与 README 一致）：
  volume_spike / heat_spike / topic_heat_spike / topic_volume_spike
  sentiment_flip / stance_shift / cross_modal_inconsistency / semantic_drift
"""

from __future__ import annotations

from typing import Any

from .temporal import extract_series

# 会触发「补采」的异常类型（评论可加页补采）
RECRAWLABLE_TYPES = {"volume_spike", "heat_spike", "topic_heat_spike", "cross_modal_inconsistency"}


def _z_at(residual: list[float | None], scale: float) -> list[float | None]:
    return [(r / scale) if (r is not None and scale > 0) else None for r in residual]


def detect_spikes(
    d_ts: list[dict[str, Any]],
    residual: dict[str, list[float | None]],
    scale: dict[str, float],
    tau: float,
    spike_metrics: tuple[str, ...],
) -> list[dict[str, Any]]:
    """对 volume/heat/topic_heat 等做稳健 z-score 尖峰检测。"""
    anomalies: list[dict[str, Any]] = []
    type_map = {
        "volume": "volume_spike",
        "heat": "heat_spike",
        "topic_heat": "topic_heat_spike",
        "topic_volume": "topic_volume_spike",
    }
    for m in spike_metrics:
        if m not in residual:
            continue
        zs = _z_at(residual[m], scale.get(m, 1.0))
        for i, z in enumerate(zs):
            if z is None or z < tau:
                continue
            bucket = d_ts[i]
            anomalies.append(
                {
                    "ts": bucket["ts"],
                    "type": type_map.get(m, f"{m}_spike"),
                    "score": round(float(z), 4),
                    "modality_hint": "temporal" if m.startswith("topic_") else "comment",
                    "evidence_ids": list(bucket.get("sample_content_ids") or []),
                }
            )
    return anomalies


def detect_sentiment_flip(
    d_ts: list[dict[str, Any]], series: dict[str, list[float | None]], tau_flip: float
) -> list[dict[str, Any]]:
    sent = series.get("sent_mean") or []
    anomalies: list[dict[str, Any]] = []
    prev: float | None = None
    prev_ts: str | None = None
    for i, v in enumerate(sent):
        if v is None:
            prev = None
            prev_ts = None
            continue
        if prev is not None and abs(v) >= 0.15 and abs(prev) >= 0.15:
            if (prev * v < 0) or abs(v - prev) >= tau_flip:
                anomalies.append(
                    {
                        "ts": d_ts[i]["ts"],
                        "type": "sentiment_flip",
                        "score": round(abs(v - prev), 4),
                        "modality_hint": "sentiment",
                        "evidence_ids": list(d_ts[i].get("sample_content_ids") or []),
                        "meta": {"from": round(prev, 4), "to": round(v, 4)},
                    }
                )
        prev = v
        prev_ts = d_ts[i]["ts"]
    return anomalies


def _dominant(b: dict[str, Any]) -> tuple[str, float]:
    pos = float(b.get("stance_pos_ratio") or 0)
    neg = float(b.get("stance_neg_ratio") or 0)
    neu = float(b.get("stance_neu_ratio") or 0)
    best = max(("support", pos), ("oppose", neg), ("neutral", neu), key=lambda x: x[1])
    return best


def detect_stance_shift(
    d_ts: list[dict[str, Any]], tau_stance: float
) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    prev_dom: str | None = None
    for i, b in enumerate(d_ts):
        if b.get("is_empty"):
            prev_dom = None
            continue
        dom, ratio = _dominant(b)
        if prev_dom is not None and dom != prev_dom and ratio >= 0.5:
            anomalies.append(
                {
                    "ts": b["ts"],
                    "type": "stance_shift",
                    "score": round(ratio, 4),
                    "modality_hint": "stance",
                    "evidence_ids": list(b.get("sample_content_ids") or []),
                    "meta": {"from": prev_dom, "to": dom},
                }
            )
        prev_dom = dom
    return anomalies


def detect_cross_modal(
    d_ts: list[dict[str, Any]],
    series: dict[str, list[float | None]],
    text_tower: dict[str, Any],
    tau_cross: float,
) -> list[dict[str, Any]]:
    """
    跨模态不一致：
      (a) 文本塔桶级情绪与 D_ts.sent_mean 显著反向；
      (b) 内容侧 topic_heat 尖峰、评论侧 volume 却无同步（爆发但评论未跟上）。
    """
    anomalies: list[dict[str, Any]] = []
    sent = series.get("sent_mean") or []
    bucket_sent = text_tower.get("bucket_sentiment") or []
    n = min(len(d_ts), len(sent), len(bucket_sent))
    for i in range(n):
        ts_v = sent[i]
        tx_v = bucket_sent[i]
        if ts_v is None or tx_v is None:
            continue
        if abs(ts_v) >= 0.15 and abs(tx_v) >= 0.15 and ts_v * tx_v < 0:
            anomalies.append(
                {
                    "ts": d_ts[i]["ts"],
                    "type": "cross_modal_inconsistency",
                    "score": round(abs(ts_v - tx_v), 4),
                    "modality_hint": "sentiment",
                    "evidence_ids": list(d_ts[i].get("sample_content_ids") or []),
                    "meta": {"D_ts_sent": round(ts_v, 4), "text_sent": round(tx_v, 4)},
                }
            )
    return anomalies


def detect_semantic_drift(
    d_ts: list[dict[str, Any]],
    text_tower: dict[str, Any],
    tau_drift: float,
    min_drift_volume: int = 5,
) -> list[dict[str, Any]]:
    drift = text_tower.get("drift_sim") or []
    bucket_volume = text_tower.get("bucket_volume") or []
    anomalies: list[dict[str, Any]] = []
    # drift_sim[i] 对应 d_ts[i+1]
    for i, sim in enumerate(drift):
        if sim is None:
            continue
        prev_vol = bucket_volume[i] if i < len(bucket_volume) else 0
        idx = i + 1
        cur_vol = bucket_volume[idx] if idx < len(bucket_volume) else 0
        # 稀疏桶间相似度噪声大，需两侧都有足够样本才算「真漂移」
        if prev_vol < min_drift_volume or cur_vol < min_drift_volume:
            continue
        if sim < tau_drift:
            anomalies.append(
                {
                    "ts": d_ts[idx]["ts"],
                    "type": "semantic_drift",
                    "score": round(1.0 - sim, 4),
                    "modality_hint": "text",
                    "evidence_ids": list(d_ts[idx].get("sample_content_ids") or []),
                    "meta": {
                        "similarity": round(sim, 4),
                        "prev_volume": prev_vol,
                        "cur_volume": cur_vol,
                    },
                }
            )
    return anomalies
