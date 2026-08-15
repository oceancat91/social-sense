"""
Skill3 核心：多模态时序–文本分析编排。

输入 D_platform → 时序塔 + 文本塔 → 融合 → anomalies / residual / baseline / hidden_states / need_recrawl。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .detectors import (
    RECRAWLABLE_TYPES,
    detect_cross_modal,
    detect_semantic_drift,
    detect_sentiment_flip,
    detect_spikes,
    detect_stance_shift,
)
from .temporal import (
    compute_baseline_residual,
    extract_series,
    residual_scale,
)
from .text_tower import analyze_text_tower

MODEL_VERSION = "multimodal_analyzer_v1"

SPIKE_METRICS = ("volume", "heat", "topic_heat", "topic_volume")

HIDDEN_FEATURES = [
    "z_volume",
    "z_heat",
    "z_topic_heat",
    "sent_mean",
    "controversy",
    "bias_proxy",
    "bucket_sentiment",
    "text_presence",
]


@dataclass
class AnalyzerConfig:
    tau: float = 3.0            # 稳健 z 阈值（尖峰）
    tau_flip: float = 0.35      # 情绪突变最小幅度
    tau_stance: float = 0.3     # 立场主导切换所需主导占比
    tau_cross: float = 0.15     # 跨模态反向最小幅度
    tau_drift: float = 0.10     # 语义漂移相似度下界（低于视为漂移）
    min_drift_volume: int = 5   # 语义漂移两侧最小样本量（稀疏桶不算）
    baseline_window: int | None = None  # None = 自适应
    enable_text_tower: bool = True
    hidden_dir: Path | None = None


def _adaptive_window(n_buckets: int) -> int:
    if n_buckets <= 3:
        return 3
    return max(3, min(31, round(n_buckets * 0.2) | 1))  # 奇数窗口


def _build_hidden_states(
    d_ts: list[dict[str, Any]],
    residual: dict[str, list[float | None]],
    scale: dict[str, float],
    text_tower: dict[str, Any],
) -> dict[str, Any]:
    """构造每桶融合特征（供 RAG/结论侧引用，不直接当结论）。"""
    bucket_sent = text_tower.get("bucket_sentiment") or []
    bucket_volume = text_tower.get("bucket_volume") or []
    per_bucket: dict[str, list[float | None]] = {}
    for i, b in enumerate(d_ts):
        def z(m: str) -> float | None:
            r = residual.get(m, [None] * len(d_ts))[i]
            s = scale.get(m, 1.0)
            return round(r / s, 4) if (r is not None and s > 0) else None

        feat: list[float | None] = [
            z("volume"),
            z("heat"),
            z("topic_heat"),
            (round(float(b.get("sent_mean")), 4) if b.get("sent_mean") is not None else None),
            (round(float(b.get("controversy")), 4) if b.get("controversy") is not None else None),
            (round(float(b.get("bias_proxy")), 4) if b.get("bias_proxy") is not None else None),
            (round(bucket_sent[i], 4) if i < len(bucket_sent) and bucket_sent[i] is not None else None),
            float(1 if (i < len(bucket_volume) and bucket_volume[i]) else 0),
        ]
        per_bucket[str(b["ts"])] = feat
    return {"feature_names": HIDDEN_FEATURES, "per_bucket": per_bucket}


def run_analysis(
    d_platform: dict[str, Any],
    config: AnalyzerConfig | None = None,
    *,
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    cfg = config or AnalyzerConfig()

    if not isinstance(d_platform, dict) or "D_ts" not in d_platform:
        raise ValueError("MultimodalAnalyzer 需要合法 D_platform（含 D_ts）")

    meta = d_platform.get("D_meta") or {}
    d_ts: list[dict[str, Any]] = d_platform["D_ts"]
    is_empty = bool(meta.get("is_empty"))

    # 空数据兼容：不报错，输出空结果
    if is_empty or not d_ts:
        return {
            "status": "no_anomaly_empty",
            "anomalies": [],
            "hidden_states": {"feature_names": HIDDEN_FEATURES, "per_bucket": {}},
            "residual": {},
            "baseline": {},
            "need_recrawl": False,
            "recrawl_windows": [],
            "model_version": MODEL_VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

    n = len(d_ts)
    window = cfg.baseline_window or _adaptive_window(n)
    series = extract_series(d_ts)
    baseline, residual = compute_baseline_residual(series, window)
    scale = residual_scale(residual)

    text_tower: dict[str, Any] = {}
    if cfg.enable_text_tower:
        text_tower = analyze_text_tower(d_platform)

    anomalies: list[dict[str, Any]] = []
    anomalies += detect_spikes(d_ts, residual, scale, cfg.tau, SPIKE_METRICS)
    anomalies += detect_sentiment_flip(d_ts, series, cfg.tau_flip)
    anomalies += detect_stance_shift(d_ts, cfg.tau_stance)
    if text_tower:
        anomalies += detect_cross_modal(d_ts, series, text_tower, cfg.tau_cross)
        anomalies += detect_semantic_drift(
            d_ts, text_tower, cfg.tau_drift, cfg.min_drift_volume
        )

    # 去重（同桶同类型保留最高分），按时间升序
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for a in anomalies:
        key = (a["ts"], a["type"])
        if key not in seen or a["score"] > seen[key]["score"]:
            seen[key] = a
    anomalies = sorted(seen.values(), key=lambda a: (a["ts"], a["type"]))

    need_recrawl = any(a["type"] in RECRAWLABLE_TYPES and a["score"] >= cfg.tau for a in anomalies)
    recrawl_windows = sorted({a["ts"] for a in anomalies if a["type"] in RECRAWLABLE_TYPES})

    hidden_states = _build_hidden_states(d_ts, residual, scale, text_tower)
    hidden_uri = None
    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        fname = f"hidden_states_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        (out / fname).write_text(
            json.dumps(hidden_states, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        hidden_uri = str((out / fname).resolve())
        hidden_states = {"uri": hidden_uri, **hidden_states}

    return {
        "status": "ok",
        "anomalies": anomalies,
        "hidden_states": hidden_states,
        "residual": residual,
        "baseline": baseline,
        "need_recrawl": need_recrawl,
        "recrawl_windows": recrawl_windows,
        "model_version": MODEL_VERSION,
        "config": {
            "tau": cfg.tau,
            "baseline_window": window,
            "enable_text_tower": cfg.enable_text_tower,
            "spike_metrics": list(SPIKE_METRICS),
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
