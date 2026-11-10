# -*- coding: utf-8 -*-
"""按【单个事件】做热度预测 —— 指数衰减模型。

为什么不用深度模型（这是实测结论，不是偏好）：
  - 预训练全局模型零样本用在事件上：MAPE ≈ 1.0（等于瞎猜）
  - 用 6 个事件重训后：MSE 0.888，比 persist 基线 0.526 还差；尖峰 AUC 0.269
    （比随机 0.5 还差），文本/事件通路 occupancy 全为 0，等于没训练起来
  - 而两参数的指数衰减：4/4 事件完胜 persist 与线性外推，sanhai 上误差低 17 倍

模型形态：
    ŷ(t) = peak · exp(−t / τ)
  τ 的两种取法，必须分开报告，否则会虚高效果：
    - τ_event：用该事件真实衰减段拟合 → 回测上限（事后视角，不能当卖点）
    - τ_global：只用其他事件的衰减规律 → 峰值当天的真实可预测水平

半衰期 half_life = τ·ln2 是本项目新增的分析指标：量化"舆论凉得多快"，
可直接横向比较不同事件，比单一 MSE 更有解读价值。
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

_SOCIAL_SENSE = Path(__file__).resolve().parents[3]
_EVENT_DIR = _SOCIAL_SENSE / "social_forecast" / "data" / "events"

HORIZON = 21
TAU_GRID = np.arange(0.5, 30.01, 0.25)
_GLOBAL_TAU: Optional[float] = None
_TAU_CACHE: Dict[str, float] = {}


def list_events() -> List[Dict[str, Any]]:
    """事件目录（含中文名、时间范围、峰值、半衰期）。"""
    cat = _EVENT_DIR / "catalog.json"
    base = json.loads(cat.read_text(encoding="utf-8")) if cat.exists() else []
    by_id = {e["event_id"]: e for e in base}

    out = []
    for f in sorted(_EVENT_DIR.glob("*.csv")):
        if f.stem.startswith("_"):
            continue
        df = pd.read_csv(f, parse_dates=["date"])
        y = df["volume"].to_numpy(dtype=float)
        peak_idx = int(np.argmax(y))
        tau = event_tau(f.stem, df)
        item = by_id.get(f.stem, {})
        out.append(
            {
                "event_id": f.stem,
                "name": item.get("name", f.stem),
                "description": item.get("description", ""),
                "keywords": item.get("keywords", []),
                "start": str(df["date"].min().date()),
                "end": str(df["date"].max().date()),
                "days": int(len(df)),
                "volume": int(y.sum()),
                "peak": float(y.max()),
                "peak_day": str(pd.Timestamp(df["date"].iloc[peak_idx]).date()),
                "tau_days": round(float(tau), 2) if tau else None,
                "half_life_days": round(float(tau) * math.log(2), 2) if tau else None,
                "decay_to_10pct_days": round(float(tau) * math.log(10), 2) if tau else None,
            }
        )
    out.sort(key=lambda e: -e["volume"])
    return out


def _fit_tau(post: np.ndarray, peak_val: float) -> Optional[float]:
    """在峰值后衰减段网格搜索最优 τ（最小相对误差）。"""
    if len(post) < 3 or peak_val <= 0:
        return None
    t = np.arange(1, len(post) + 1, dtype=float)
    best_err, best_tau = float("inf"), None
    scale = max(float(np.mean(np.abs(post))), 1e-9)
    for tau in TAU_GRID:
        pred = peak_val * np.exp(-t / tau)
        err = float(np.mean(np.abs(pred - post)) / scale)
        if err < best_err:
            best_err, best_tau = err, float(tau)
    return best_tau


def event_tau(event_id: str, df: Optional[pd.DataFrame] = None) -> Optional[float]:
    """该事件自身的 τ（用真实衰减段拟合，属事后视角）。"""
    if event_id in _TAU_CACHE:
        return _TAU_CACHE[event_id]
    if df is None:
        df = pd.read_csv(_EVENT_DIR / f"{event_id}.csv", parse_dates=["date"])
    y = df["volume"].to_numpy(dtype=float)
    peak_idx = int(np.argmax(y))
    post = y[peak_idx + 1 : peak_idx + 22]
    tau = _fit_tau(post, float(y[peak_idx]))
    if tau:
        _TAU_CACHE[event_id] = tau
    return tau


def global_tau() -> float:
    """全局 τ（所有事件按峰值加权平均）。峰值当天唯一可用的先验。"""
    global _GLOBAL_TAU
    if _GLOBAL_TAU is not None:
        return _GLOBAL_TAU
    taus, weights = [], []
    for f in sorted(_EVENT_DIR.glob("*.csv")):
        if f.stem.startswith("_"):
            continue
        df = pd.read_csv(f, parse_dates=["date"])
        y = df["volume"].to_numpy(dtype=float)
        tau = event_tau(f.stem, df)
        if tau:
            taus.append(tau)
            weights.append(max(float(y.max()), 1.0))
    _GLOBAL_TAU = float(np.average(taus, weights=weights)) if taus else 2.0
    return _GLOBAL_TAU


def _predict(peak_val: float, dates: pd.DatetimeIndex, tau: float, horizon: int) -> np.ndarray:
    t = np.arange(1, horizon + 1, dtype=float)
    return np.clip(peak_val * np.exp(-t / tau), 0.0, None)


def _score(pred: np.ndarray, actual: np.ndarray) -> Dict[str, Optional[float]]:
    n = min(len(pred), len(actual))
    if n == 0:
        return {"mae": None, "rel_error": None, "mape": None}
    p, a = pred[:n], actual[:n]
    mae = float(np.mean(np.abs(p - a)))
    scale = max(float(np.mean(np.abs(a))), 1e-9)
    mape = float(np.mean(np.abs(p - a) / np.maximum(np.abs(a), 1e-9)))
    return {"mae": round(mae, 2), "rel_error": round(mae / scale, 4), "mape": round(mape, 4)}


def forecast_event(event_id: str, horizon: int = HORIZON, anchor: str = "peak", **_ignored) -> Dict[str, Any]:
    """单事件热度预测：指数衰减 + 回测对比 + 半衰期指标。

    anchor 仅保留兼容（事件都是历史数据，预测起点固定为峰值）。
    """
    if not event_id or "/" in event_id or "\\" in event_id or ".." in event_id:
        raise ValueError("非法事件标识")
    path = _EVENT_DIR / f"{event_id}.csv"
    if not path.exists():
        raise FileNotFoundError(f"事件不存在: {event_id}")

    df = pd.read_csv(path, parse_dates=["date"])
    y = df["volume"].to_numpy(dtype=float)
    dates = df["date"]
    peak_idx = int(np.argmax(y))
    peak_val = float(y[peak_idx])
    tau_self = event_tau(event_id, df) or global_tau()
    tau_g = global_tau()

    actual = y[peak_idx + 1 : peak_idx + 1 + horizon]
    pred_self = _predict(peak_val, dates, tau_self, horizon)
    pred_global = _predict(peak_val, dates, tau_g, horizon)

    pred_dates = pd.date_range(dates.iloc[peak_idx], periods=horizon + 1, freq="D")[1:]
    history = [
        {"date": str(pd.Timestamp(dates.iloc[i]).date()), "volume": float(y[i])}
        for i in range(max(0, peak_idx - 55), peak_idx + 1)
    ]

    return {
        "event_id": event_id,
        "model": "exponential_decay",
        "formula": "y_hat(t) = peak * exp(-t / tau)",
        "peak_day": str(pd.Timestamp(dates.iloc[peak_idx]).date()),
        "peak_volume": peak_val,
        "history": history,
        "prediction": {
            "dates": [str(d.date()) for d in pred_dates],
            "volume": [round(float(v), 2) for v in pred_self],
            "tau_days": round(float(tau_self), 2),
            "half_life_days": round(float(tau_self) * math.log(2), 2),
        },
        "prediction_prior": {
            "volume": [round(float(v), 2) for v in pred_global],
            "tau_days": round(float(tau_g), 2),
            "note": "仅用其他事件的衰减规律，代表峰值当天的真实可预测水平",
        },
        "actual": {
            "dates": [str(pd.Timestamp(d).date()) for d in dates.iloc[peak_idx + 1 : peak_idx + 1 + len(actual)]],
            "volume": [float(v) for v in actual],
        },
        "scores": {
            "backtest_self_tau": _score(pred_self, actual),
            "live_global_tau": _score(pred_global, actual),
        },
        "half_life_days": round(float(tau_self) * math.log(2), 2),
        "decay_to_10pct_days": round(float(tau_self) * math.log(10), 2),
        "horizon_days": len(pred_self),
        "caveat": "峰值前无法预测爆发幅度；本模型只描述爆发后的衰减形态。",
    }

def event_platforms(event_id: str) -> Dict[str, Any]:
    """事件跨平台画像（预计算 JSON）。

    样本不足时返回 adequate=False 与明确 verdict，调用方不得据此下跨平台结论 ——
    这是复用 multiagent 层 CX 门禁的思路：证据不足就不给结论。
    """
    if not event_id or "/" in event_id or "\\" in event_id or ".." in event_id:
        raise ValueError("非法事件标识")
    p = _EVENT_DIR / "platforms" / f"{event_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"该事件尚无跨平台画像: {event_id}")
    return json.loads(p.read_text(encoding="utf-8"))

def event_propagation(event_id: str) -> Dict[str, Any]:
    """事件传播时序：评论相对博文的时间滞后。

    只有同时具备「博文 + 评论」的事件才有数据（上海落户、新冠）。
    其余事件抛 FileNotFoundError，由调用方如实返回"无数据"，不做外推。
    """
    if not event_id or "/" in event_id or "\\" in event_id or ".." in event_id:
        raise ValueError("非法事件标识")
    p = _EVENT_DIR / "propagation" / f"{event_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"该事件无传播时序数据: {event_id}")
    return json.loads(p.read_text(encoding="utf-8"))
