"""
时序塔：从 D_ts 抽取多变量序列，计算稳健基线与残差。

只做「测得到」的定量证据，不依赖 LLM。缺失值（空窗 None）保留、不插值。
"""

from __future__ import annotations

from typing import Any


# 参与建模的数值指标：value_fn 对空窗/缺失返回 None，其余 float。
def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


METRICS: dict[str, Any] = {
    # 评论侧
    "volume": lambda b: _f(b.get("volume")),
    "heat": lambda b: _f(b.get("heat")),
    "sent_mean": lambda b: _f(b.get("sent_mean")),
    "sent_std": lambda b: _f(b.get("sent_std")),
    "controversy": lambda b: _f(b.get("controversy")),
    "bias_proxy": lambda b: _f(b.get("bias_proxy")),
    "stance_pos_ratio": lambda b: _f(b.get("stance_pos_ratio")),
    "stance_neg_ratio": lambda b: _f(b.get("stance_neg_ratio")),
    "stance_neu_ratio": lambda b: _f(b.get("stance_neu_ratio")),
    # 内容侧（爆发→至今主轴）
    "topic_volume": lambda b: _f(b.get("topic_volume")),
    "topic_heat": lambda b: _f(b.get("topic_heat")),
}


def extract_series(d_ts: list[dict[str, Any]]) -> dict[str, list[float | None]]:
    """返回 {metric: [value...]}，长度 == len(D_ts)，缺失为 None。"""
    series: dict[str, list[float | None]] = {m: [] for m in METRICS}
    for b in d_ts:
        for m, fn in METRICS.items():
            series[m].append(fn(b))
    return series


def median(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def mad(values: list[float | None], center: float | None = None) -> float | None:
    """中位绝对偏差（稳健尺度）。"""
    if center is None:
        center = median(values)
    if center is None:
        return None
    vals = [abs(v - center) for v in values if v is not None]
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def rolling_median(
    values: list[float | None], window: int, min_periods: int = 1
) -> list[float | None]:
    """滑动中位数基线（居中窗口），窗口内只统计非 None。"""
    out: list[float | None] = []
    half = window // 2
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        win = [v for v in values[lo:hi] if v is not None]
        if len(win) < min_periods:
            out.append(None)
        else:
            out.append(median(win))
    return out


def compute_baseline_residual(
    series: dict[str, list[float | None]], window: int
) -> tuple[dict[str, list[float | None]], dict[str, list[float | None]]]:
    """对每个指标算稳健基线（滑动中位数）与残差（真实 − 基线）。"""
    baseline: dict[str, list[float | None]] = {}
    residual: dict[str, list[float | None]] = {}
    for m, vals in series.items():
        base = rolling_median(vals, window)
        baseline[m] = base
        residual[m] = [
            (v - b) if (v is not None and b is not None) else None
            for v, b in zip(vals, base)
        ]
    return baseline, residual


def residual_scale(residual: dict[str, list[float | None]]) -> dict[str, float]:
    """每指标的残差稳健尺度 1.4826*MAD，供 z-score 归一。"""
    scale: dict[str, float] = {}
    for m, vals in residual.items():
        m_ = mad(vals, center=0.0)
        if m_ is None or m_ <= 0:
            scale[m] = 1.0  # 无变化 → 单位尺度，避免除零
        else:
            scale[m] = 1.4826 * m_
    return scale


def normalize_window(window: int, n_buckets: int) -> int:
    """把窗口归一为不小于 3 的奇数；短序列允许窗口覆盖全轴。"""
    w = max(3, int(window))
    if w % 2 == 0:
        w += 1
    if n_buckets >= 3 and w > n_buckets:
        w = n_buckets if n_buckets % 2 else n_buckets - 1
    return max(3, w)


def build_multiscale_windows(
    n_buckets: int,
    base_window: int,
    configured: tuple[int, ...] | None = None,
) -> list[int]:
    """构造短/中/长尺度窗口；显式配置时仅做合法化和去重。"""
    if configured:
        candidates = list(configured)
    else:
        base = normalize_window(base_window, n_buckets)
        candidates = [3, base, base * 2 + 1]
    return sorted({normalize_window(w, n_buckets) for w in candidates})


def compute_multiscale_statistics(
    series: dict[str, list[float | None]],
    windows: list[int],
) -> dict[str, dict[str, Any]]:
    """按多个时间尺度计算基线、残差、稳健尺度与标准化残差。"""
    result: dict[str, dict[str, Any]] = {}
    for window in windows:
        baseline, residual = compute_baseline_residual(series, window)
        scale = residual_scale(residual)
        z_scores = {
            metric: [
                (value / scale.get(metric, 1.0))
                if value is not None and scale.get(metric, 1.0) > 0
                else None
                for value in values
            ]
            for metric, values in residual.items()
        }
        result[str(window)] = {
            "window": window,
            "baseline": baseline,
            "residual": residual,
            "scale": scale,
            "z_scores": z_scores,
        }
    return result


def fuse_multiscale_z(
    multiscale: dict[str, dict[str, Any]],
) -> dict[str, list[float | None]]:
    """逐桶选择绝对值最大的尺度 z，保留方向，作为融合时序表征。"""
    if not multiscale:
        return {}
    first = next(iter(multiscale.values()))
    metrics = list((first.get("z_scores") or {}).keys())
    fused: dict[str, list[float | None]] = {}
    for metric in metrics:
        per_scale = [
            (stats.get("z_scores") or {}).get(metric) or []
            for stats in multiscale.values()
        ]
        n = max((len(values) for values in per_scale), default=0)
        values_out: list[float | None] = []
        for i in range(n):
            candidates = [
                values[i]
                for values in per_scale
                if i < len(values) and values[i] is not None
            ]
            values_out.append(
                max(candidates, key=lambda value: abs(float(value)))
                if candidates
                else None
            )
        fused[metric] = values_out
    return fused
