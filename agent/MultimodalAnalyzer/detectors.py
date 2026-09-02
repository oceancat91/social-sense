"""
异常检测规则：把时序塔残差与文本塔漂移融合成带类型的异常点。

类型枚举（与 README 一致）：
  volume_spike / heat_spike / topic_heat_spike / topic_volume_spike
  sentiment_flip / stance_shift / cross_modal_inconsistency / semantic_drift
  cross_scale_inconsistency
"""

from __future__ import annotations

from typing import Any

from .temporal import extract_series

# 会触发「补采」的异常类型（评论可加页补采）
RECRAWLABLE_TYPES = {
    "volume_spike",
    "heat_spike",
    "topic_heat_spike",
    "cross_modal_inconsistency",
    "cross_scale_inconsistency",
}

SEVERITY_RANK = {"none": 0, "warning": 1, "important": 2, "critical": 3}


def _z_at(residual: list[float | None], scale: float) -> list[float | None]:
    return [(r / scale) if (r is not None and scale > 0) else None for r in residual]


def detect_spikes(
    d_ts: list[dict[str, Any]],
    residual: dict[str, list[float | None]],
    scale: dict[str, float],
    tau: float,
    spike_metrics: tuple[str, ...],
    multiscale_z: dict[str, dict[str, list[float | None]]] | None = None,
) -> list[dict[str, Any]]:
    """对 volume/heat/topic_heat 等做稳健 z-score 尖峰检测。

    提供 multiscale_z 时，逐桶采用跨尺度最大正向 z，并记录主导尺度。
    """
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
        for i, single_z in enumerate(zs):
            scale_scores: dict[str, float] = {}
            for scale_name, by_metric in (multiscale_z or {}).items():
                values = by_metric.get(m) or []
                if i < len(values) and values[i] is not None:
                    scale_scores[scale_name] = round(float(values[i]), 4)
            if scale_scores:
                dominant_scale, z = max(scale_scores.items(), key=lambda item: item[1])
            else:
                dominant_scale, z = "single", single_z
            if z is None or z < tau:
                continue
            bucket = d_ts[i]
            anomaly = {
                "ts": bucket["ts"],
                "type": type_map.get(m, f"{m}_spike"),
                "score": round(float(z), 4),
                "modality_hint": "temporal" if m.startswith("topic_") else "comment",
                "evidence_ids": list(bucket.get("sample_content_ids") or []),
            }
            if scale_scores:
                anomaly["meta"] = {
                    "metric": m,
                    "dominant_scale": dominant_scale,
                    "scale_scores": scale_scores,
                }
            anomalies.append(anomaly)
    return anomalies


def detect_sentiment_flip(
    d_ts: list[dict[str, Any]], series: dict[str, list[float | None]], tau_flip: float
) -> list[dict[str, Any]]:
    sent = series.get("sent_mean") or []
    anomalies: list[dict[str, Any]] = []
    prev: float | None = None
    for i, v in enumerate(sent):
        if v is None:
            prev = None
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
    for b in d_ts:
        if b.get("is_empty"):
            prev_dom = None
            continue
        dom, ratio = _dominant(b)
        if prev_dom is not None and dom != prev_dom and ratio >= max(0.5, tau_stance):
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
        if (
            abs(ts_v) >= 0.15
            and abs(tx_v) >= 0.15
            and ts_v * tx_v < 0
            and abs(ts_v - tx_v) >= tau_cross
        ):
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


def detect_cross_scale_inconsistency(
    d_ts: list[dict[str, Any]],
    multiscale_z: dict[str, dict[str, list[float | None]]],
    tau: float,
    metrics: tuple[str, ...],
) -> list[dict[str, Any]]:
    """检测同一指标在不同时间尺度上的异常响应差异。

    这是 CrossAD「跨尺度关联被破坏」的轻量、无训练近似：当短/中/长尺度
    标准化残差的跨度超过阈值，且至少一个尺度本身显著偏离时，记录异常。
    """
    anomalies: list[dict[str, Any]] = []
    for metric in metrics:
        for i, bucket in enumerate(d_ts):
            scores: dict[str, float] = {}
            for scale_name, by_metric in multiscale_z.items():
                values = by_metric.get(metric) or []
                if i < len(values) and values[i] is not None:
                    scores[scale_name] = float(values[i])
            if len(scores) < 2:
                continue
            score_values = list(scores.values())
            disagreement = max(score_values) - min(score_values)
            max_abs = max(abs(value) for value in score_values)
            if disagreement < tau or max_abs < tau:
                continue
            dominant_scale = max(scores, key=lambda name: abs(scores[name]))
            anomalies.append(
                {
                    "ts": bucket["ts"],
                    "type": "cross_scale_inconsistency",
                    "score": round(disagreement, 4),
                    "modality_hint": "temporal",
                    "evidence_ids": list(bucket.get("sample_content_ids") or []),
                    "meta": {
                        "metric": metric,
                        "dominant_scale": dominant_scale,
                        "scale_scores": {
                            name: round(value, 4) for name, value in scores.items()
                        },
                    },
                }
            )
    return anomalies


def _base_threshold(anomaly_type: str, thresholds: dict[str, float]) -> float:
    if anomaly_type.endswith("_spike"):
        return max(float(thresholds.get("spike") or 3.0), 1e-9)
    key_map = {
        "sentiment_flip": "sentiment_flip",
        "stance_shift": "stance_shift",
        "cross_modal_inconsistency": "cross_modal",
        "semantic_drift": "semantic_drift",
        "cross_scale_inconsistency": "cross_scale",
    }
    key = key_map.get(anomaly_type, "default")
    return max(float(thresholds.get(key) or 1.0), 1e-9)


def _reason(anomaly: dict[str, Any], threshold: float) -> str:
    anomaly_type = str(anomaly.get("type") or "")
    score = float(anomaly.get("score") or 0)
    meta = anomaly.get("meta") or {}
    if anomaly_type.endswith("_spike"):
        metric = meta.get("metric") or anomaly_type.removesuffix("_spike")
        scale = meta.get("dominant_scale") or "单"
        return f"{metric} 在 {scale} 尺度的稳健异常分数为 {score:.2f}，超过阈值 {threshold:.2f}"
    if anomaly_type == "cross_scale_inconsistency":
        return (
            f"{meta.get('metric') or '指标'} 在不同时间尺度的标准化残差跨度为 "
            f"{score:.2f}，超过阈值 {threshold:.2f}"
        )
    if anomaly_type == "sentiment_flip":
        return f"情绪由 {meta.get('from')} 变化到 {meta.get('to')}，幅度为 {score:.2f}"
    if anomaly_type == "stance_shift":
        return f"主导立场由 {meta.get('from')} 切换为 {meta.get('to')}，占比为 {score:.2f}"
    if anomaly_type == "cross_modal_inconsistency":
        return (
            f"聚合情绪 {meta.get('D_ts_sent')} 与文本情绪 {meta.get('text_sent')} "
            f"方向相反，差异为 {score:.2f}"
        )
    if anomaly_type == "semantic_drift":
        return f"相邻高样本量时间桶语义相似度降至 {meta.get('similarity')}，出现主题漂移"
    return f"异常分数 {score:.2f} 超过对应阈值 {threshold:.2f}"


def enrich_anomalies(
    anomalies: list[dict[str, Any]],
    thresholds: dict[str, float],
    *,
    empty_ratio: float = 0.0,
) -> list[dict[str, Any]]:
    """为异常补充 LLMAD 风格的确定性风险等级、置信度与可核验原因。"""
    enriched: list[dict[str, Any]] = []
    for raw in anomalies:
        anomaly = dict(raw)
        threshold = _base_threshold(str(anomaly.get("type") or ""), thresholds)
        ratio = float(anomaly.get("score") or 0) / threshold
        if ratio >= 2.0:
            severity = "critical"
        elif ratio >= 1.35:
            severity = "important"
        else:
            severity = "warning"
        evidence_ids = list(anomaly.get("evidence_ids") or [])
        if empty_ratio >= 0.5:
            severity = "warning"
            confidence = "low"
        elif not evidence_ids:
            confidence = "low"
        elif ratio >= 1.5:
            confidence = "high"
        else:
            confidence = "mid"
        anomaly["severity"] = severity
        anomaly["confidence"] = confidence
        anomaly["reason"] = _reason(anomaly, threshold)
        enriched.append(anomaly)
    return enriched
