"""
多平台对齐器：把各平台的 PlatformReport 对齐到同一时间轴与可比口径。

输出 AlignedBundle：
  - time_axis：所有平台桶起点的并集（升序）
  - aligned_ts[platform]：按 time_axis 对齐后的桶序列（缺失为 None，不插值）
  - z_series[platform][metric]：平台内 z-score 归一序列（跨平台可比）
  - 缺失/空窗说明
"""

from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev
from typing import Any

from .contract import ALIGNED_METRICS, _norm_ts, bucket_metrics


def _zscore(values: list[float | None]) -> list[float | None]:
    """平台内 z-score；None 保持 None（空窗不参与，也不伪造）。"""
    nums = [v for v in values if v is not None]
    if len(nums) < 2:
        mu = nums[0] if nums else 0.0
        sd = 1.0
    else:
        mu = mean(nums)
        sd = pstdev(nums) or 1.0
    return [None if v is None else (v - mu) / sd for v in values]


def align(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """对齐多平台报告。reports 已是 normalize_report 后的契约对象。"""
    platforms: list[str] = []
    ts_maps: dict[str, dict[str, dict[str, Any]]] = {}
    all_ts: set[str] = set()

    for r in reports:
        p = str(r.get("platform"))
        if not p:
            continue
        platforms.append(p)
        m: dict[str, dict[str, Any]] = {}
        for b in r.get("D_ts") or []:
            key = _norm_ts(b.get("ts"))
            if not key:
                continue
            m[key] = b
            all_ts.add(key)
        ts_maps[p] = m

    time_axis = sorted(all_ts)

    aligned_ts: dict[str, list[dict[str, Any] | None]] = {}
    for p in platforms:
        m = ts_maps[p]
        aligned_ts[p] = [m.get(t) for t in time_axis]

    # 平台内 z-score 序列（仅对可计算指标）
    z_series: dict[str, dict[str, list[float | None]]] = {}
    for p in platforms:
        buckets = aligned_ts[p]
        series: dict[str, list[float | None]] = {m: [] for m in ALIGNED_METRICS}
        for b in buckets:
            mv = bucket_metrics(b) if b else {m: None for m in ALIGNED_METRICS}
            for m in ALIGNED_METRICS:
                series[m].append(mv[m])
        z_series[p] = {m: _zscore(series[m]) for m in ALIGNED_METRICS}

    return {
        "platforms": platforms,
        "time_axis": time_axis,
        "aligned_ts": aligned_ts,
        "z_series": z_series,
        "granularity": reports[0].get("granularity") if reports else None,
        "n_platforms": len(platforms),
        "n_buckets": len(time_axis),
    }
