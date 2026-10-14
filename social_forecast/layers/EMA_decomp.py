"""EMA trend extraction with adaptive alpha strategies.

Strategies
----------
fixed   : learnable scalar α (sigmoid), init from `init_alpha`
series  : set α from train-series persistence (high ACF1 → larger α to track level);
          optional fine-tune with small learnable residual in logit space
kama    : time-varying α via Kaufman efficiency ratio (fast in trends, slow in chop)
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import torch
import torch.nn as nn


def suggest_alpha_from_series(
    y: np.ndarray,
    alpha_min: float = 0.05,
    alpha_max: float = 0.45,
) -> float:
    """Persist-aware α suggestion.

    Agriculture-like (ACF1→1): need *larger* α so EMA tracks local level, not lag.
    Smooth / mean-reverting (ACF1 small): keep smaller α for stable trend.
    Also blends short/long volatility ratio.
    """
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    if y.size < 3:
        return 0.5 * (alpha_min + alpha_max)
    y0 = y - y.mean()
    v = float(np.dot(y0, y0) / y.size + 1e-12)
    acf1 = float(np.dot(y0[1:], y0[:-1]) / y.size / v)
    acf1 = float(np.clip(acf1, 0.0, 0.999))

    d = np.diff(y)
    sig_short = float(np.median(np.abs(d)) + 1e-8)
    # long-scale change over ~12 steps
    lag = min(12, max(2, y.size // 8))
    sig_long = float(np.median(np.abs(y[lag:] - y[:-lag])) / lag + 1e-8)
    vol_ratio = float(np.clip(sig_short / sig_long, 0.25, 4.0))
    # map: persist↑ & short-vol↑ → alpha↑
    score = 0.7 * acf1 + 0.3 * (np.log(vol_ratio) / np.log(4.0) * 0.5 + 0.5)
    score = float(np.clip(score, 0.0, 1.0))
    return float(alpha_min + (alpha_max - alpha_min) * score)


class EMA(nn.Module):
    """Scalar-α EMA (fixed or series-adapted init, learnable)."""

    def __init__(self, init_alpha: float = 0.3, learnable: bool = True):
        super().__init__()
        if not (0.0 < init_alpha < 1.0):
            raise ValueError(f"init_alpha must be in (0, 1), got {init_alpha}")
        logit = math.log(init_alpha / (1.0 - init_alpha))
        if learnable:
            self.alpha_logit = nn.Parameter(torch.tensor(logit, dtype=torch.float32))
        else:
            self.register_buffer('alpha_logit', torch.tensor(logit, dtype=torch.float32))
        self.learnable = learnable

    @property
    def alpha(self) -> torch.Tensor:
        return torch.sigmoid(self.alpha_logit)

    @torch.no_grad()
    def set_alpha(self, alpha: float):
        alpha = float(np.clip(alpha, 1e-4, 1 - 1e-4))
        logit = math.log(alpha / (1.0 - alpha))
        self.alpha_logit.copy_(torch.tensor(logit, dtype=self.alpha_logit.dtype))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() != 3:
            raise ValueError(f"EMA expects [B, L, C], got {tuple(x.shape)}")
        _, length, _ = x.shape
        if length == 0:
            return x
        a = self.alpha.to(dtype=x.dtype)
        beta = 1.0 - a
        idx = torch.arange(length, device=x.device, dtype=x.dtype)
        lag = idx[:, None] - idx[None, :]
        causal = lag >= 0
        lag_c = lag.clamp(min=0)
        w = torch.where(idx[None, :] == 0, beta ** lag_c, a * (beta ** lag_c))
        w = w * causal
        return torch.einsum('tl,blc->btc', w, x)


class KamaEMA(nn.Module):
    """Kaufman-style adaptive EMA: α_t from efficiency ratio.

    α_t = [ER_t * (α_fast - α_slow) + α_slow]^2
    ER_t = |x_t - x_{t-n}| / sum_{i=1}^{n} |Δx_{t-i+1}|
    """

    def __init__(
        self,
        er_window: int = 8,
        alpha_fast: float = 0.67,   # ~2/(3+1)
        alpha_slow: float = 0.0645, # ~2/(30+1)
    ):
        super().__init__()
        self.er_window = int(er_window)
        # mild learnable scales around defaults
        self.fast_logit = nn.Parameter(
            torch.tensor(math.log(alpha_fast / (1 - alpha_fast)), dtype=torch.float32))
        self.slow_logit = nn.Parameter(
            torch.tensor(math.log(alpha_slow / (1 - alpha_slow)), dtype=torch.float32))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() != 3:
            raise ValueError(f"KamaEMA expects [B, L, C], got {tuple(x.shape)}")
        B, L, C = x.shape
        if L == 0:
            return x
        a_fast = torch.sigmoid(self.fast_logit).to(dtype=x.dtype)
        a_slow = torch.sigmoid(self.slow_logit).to(dtype=x.dtype)
        # ensure fast > slow
        a_hi = torch.maximum(a_fast, a_slow)
        a_lo = torch.minimum(a_fast, a_slow)

        n = min(self.er_window, L - 1) if L > 1 else 1
        trend = x.new_zeros(B, L, C)
        trend[:, 0] = x[:, 0]
        for t in range(1, L):
            t0 = max(0, t - n)
            direction = (x[:, t] - x[:, t0]).abs()
            volatility = (x[:, t0 + 1:t + 1] - x[:, t0:t]).abs().sum(dim=1).clamp_min(1e-8)
            er = (direction / volatility).clamp(0.0, 1.0)
            sc = (er * (a_hi - a_lo) + a_lo) ** 2
            trend[:, t] = sc * x[:, t] + (1.0 - sc) * trend[:, t - 1]
        return trend


class series_decomp_ema(nn.Module):
    """EMA decomp with adaptive α.

    adapt:
      - 'fixed'  : classic learnable scalar
      - 'series' : fit α from train series, then (optionally) fine-tune
      - 'kama'   : time-varying Kaufman α
    """

    def __init__(
        self,
        init_alpha: float = 0.05,
        adapt: str = 'series',
        learnable: bool = True,
        er_window: int = 8,
    ):
        super().__init__()
        self.adapt = adapt
        if adapt == 'kama':
            self.ema = KamaEMA(er_window=er_window)
            self._scalar = None
        else:
            self.ema = EMA(init_alpha=init_alpha, learnable=learnable)
            self._scalar = self.ema

    @torch.no_grad()
    def fit_alpha(self, y_train: torch.Tensor, alpha_min: float = 0.05, alpha_max: float = 0.45):
        """Call once on train OT series [N] / [N,1] / [1,N,1]. Only for adapt='series'."""
        if self.adapt != 'series' or self._scalar is None:
            return float(self.alpha) if self._scalar is not None else float('nan')
        y = y_train.detach().cpu().numpy().reshape(-1)
        a = suggest_alpha_from_series(y, alpha_min=alpha_min, alpha_max=alpha_max)
        self._scalar.set_alpha(a)
        return a

    @property
    def alpha(self) -> torch.Tensor:
        if self._scalar is None:
            # report mid of kama range
            return 0.5 * (torch.sigmoid(self.ema.fast_logit) + torch.sigmoid(self.ema.slow_logit))
        return self._scalar.alpha

    def forward(self, x: torch.Tensor):
        trend = self.ema(x)
        return x - trend, trend
