import math
from typing import List, Optional, Sequence, Tuple, Union

import torch
import torch.nn as nn


def _as_periods(periods: Union[int, Sequence[int]]) -> List[int]:
    if isinstance(periods, int):
        periods = [periods]
    periods = [int(p) for p in periods]
    if not periods or any(p <= 0 for p in periods):
        raise ValueError(f"periods must be positive ints, got {periods}")
    return periods


class SeasonalStdNorm(nn.Module):
    """Train-set std-only scaling for the seasonal branch.

    Mean is left untouched (seasonal ~ 0). Window-level norms (RevIN etc.)
    are intentionally unsupported — they would warp phase/amplitude.
    """

    def __init__(self, n_vars: int = 1, eps: float = 1e-5):
        super().__init__()
        self.eps = eps
        self.register_buffer('std', torch.ones(n_vars))
        self.register_buffer('is_fit', torch.tensor(False))

    @torch.no_grad()
    def fit(self, r1_train: torch.Tensor):
        """r1_train: [N, C] or [B, L, C] from the training split only."""
        if r1_train.dim() == 3:
            r1_train = r1_train.reshape(-1, r1_train.size(-1))
        std = r1_train.std(dim=0, unbiased=False).clamp_min(self.eps)
        self.std.copy_(std.to(self.std.device, self.std.dtype))
        self.is_fit.fill_(True)
        return self

    def normalize(self, x: torch.Tensor) -> torch.Tensor:
        return x / self.std.to(dtype=x.dtype)

    def denormalize(self, x: torch.Tensor) -> torch.Tensor:
        return x * self.std.to(dtype=x.dtype)


class FourierSeasonal(nn.Module):
    """Fourier seasonal: extract S / r2, and extrapolate Ŝ_t by plugging t.

    For slowly varying amplitude, use sliding-window LS to refresh (a, b).
    """

    def __init__(
        self,
        periods: Union[int, Sequence[int]] = 12,
        K: int = 3,
        n_vars: int = 1,
    ):
        super().__init__()
        self.periods = _as_periods(periods)
        self.K = int(K)
        self.n_vars = int(n_vars)
        if self.K < 1:
            raise ValueError(f"K must be >= 1, got {self.K}")

        M, C = len(self.periods), self.n_vars
        self.a = nn.Parameter(torch.zeros(M, self.K, C))
        self.b = nn.Parameter(torch.zeros(M, self.K, C))
        self.std_norm = SeasonalStdNorm(n_vars=C)

    def _normalize_t(self, t, length, batch, device, dtype):
        if t is None:
            t = torch.arange(length, device=device, dtype=dtype).unsqueeze(0).expand(batch, -1)
        else:
            t = t.to(device=device, dtype=dtype)
            if t.dim() == 1:
                t = t.unsqueeze(0).expand(batch, -1)
            if t.shape != (batch, length):
                raise ValueError(f"t shape {tuple(t.shape)} != {(batch, length)}")
        return t

    def basis(self, t: torch.Tensor) -> torch.Tensor:
        """t: [B, L] -> Phi: [B, L, 2*M*K]."""
        cols = []
        for P in self.periods:
            w = 2.0 * math.pi / P
            for k in range(1, self.K + 1):
                ang = (w * k) * t
                cols.append(torch.cos(ang))
                cols.append(torch.sin(ang))
        return torch.stack(cols, dim=-1)

    def seasonal_at(
        self,
        t: torch.Tensor,
        a: Optional[torch.Tensor] = None,
        b: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """Evaluate Fourier series at t. t: [B,L]|[L] -> S: [B,L,C]."""
        if t.dim() == 1:
            t = t.unsqueeze(0)
        a = self.a if a is None else a
        b = self.b if b is None else b
        B, L = t.shape
        S = t.new_zeros(B, L, self.n_vars)
        for m, P in enumerate(self.periods):
            w = 2.0 * math.pi / float(P)
            for k in range(1, self.K + 1):
                ang = (w * k) * t
                S = S + a[m, k - 1].to(dtype=t.dtype) * torch.cos(ang).unsqueeze(-1)
                S = S + b[m, k - 1].to(dtype=t.dtype) * torch.sin(ang).unsqueeze(-1)
        return S

    def _lstsq_coeffs(self, r: torch.Tensor, t: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """LS fit on one series r:[L,C], t:[L] -> a,b [M,K,C]."""
        Phi = self.basis(t.unsqueeze(0)).squeeze(0)          # [L, D]
        theta = torch.linalg.lstsq(Phi, r).solution          # [D, C]
        M, K, C = len(self.periods), self.K, self.n_vars
        a = r.new_zeros(M, K, C)
        b = r.new_zeros(M, K, C)
        idx = 0
        for m in range(M):
            for k in range(K):
                a[m, k] = theta[idx]
                b[m, k] = theta[idx + 1]
                idx += 2
        return a, b

    @torch.no_grad()
    def fit_least_squares(self, r1: torch.Tensor, t: Optional[torch.Tensor] = None):
        """Global LS on (optionally std-normalized) train residual."""
        if r1.dim() == 2:
            r1 = r1.unsqueeze(0)
        B, L, C = r1.shape
        if C != self.n_vars:
            raise ValueError(f"n_vars mismatch: C={C} vs {self.n_vars}")
        t = self._normalize_t(t, L, B, r1.device, r1.dtype)
        r = self.std_norm.normalize(r1).reshape(-1, C)
        tt = t.reshape(-1)
        a, b = self._lstsq_coeffs(r, tt)
        self.a.data.copy_(a)
        self.b.data.copy_(b)
        return self

    @torch.no_grad()
    def fit_window_ls(self, r1_win: torch.Tensor, t_win: torch.Tensor):
        """Per-sample sliding-window LS (no write to global params).

        r1_win: [B, W, C], t_win: [B, W] -> a,b each [B, M, K, C]
        """
        B, W, C = r1_win.shape
        r = self.std_norm.normalize(r1_win)
        As, Bs = [], []
        for i in range(B):
            a, b = self._lstsq_coeffs(r[i], t_win[i].to(dtype=r.dtype))
            As.append(a)
            Bs.append(b)
        return torch.stack(As, 0), torch.stack(Bs, 0)

    def forward(self, r1: torch.Tensor, t: Optional[torch.Tensor] = None):
        """r1 -> (r2, S) in original scale. Fitting lives in std-normalized space."""
        if r1.dim() != 3:
            raise ValueError(f"expect [B,L,C], got {tuple(r1.shape)}")
        B, L, C = r1.shape
        if C != self.n_vars:
            raise ValueError(f"n_vars mismatch: C={C} vs {self.n_vars}")
        t = self._normalize_t(t, L, B, r1.device, r1.dtype)
        # evaluate in normalized space then denorm -> preserves Fourier phase/amp
        S = self.std_norm.denormalize(self.seasonal_at(t))
        return r1 - S, S

    def forecast(self, t_future: torch.Tensor) -> torch.Tensor:
        """Static Ŝ_t: plug future t into fitted Fourier series, then denorm."""
        return self.std_norm.denormalize(self.seasonal_at(t_future))

    @torch.no_grad()
    def forecast_adaptive(
        self,
        r1_hist: torch.Tensor,
        t_hist: torch.Tensor,
        pred_len: int,
        win: Optional[int] = None,
    ) -> torch.Tensor:
        """Time-varying season: LS on last `win` points, then plug future t.

        r1_hist/t_hist: [B, L, C] / [B, L]  -> Ŝ: [B, pred_len, C]
        """
        B, L, _ = r1_hist.shape
        win = int(win or L)
        win = max(win, 2 * self.K * len(self.periods) + 1)  # need enough rows for LS
        win = min(win, L)
        r_win = r1_hist[:, -win:]
        t_win = t_hist[:, -win:]
        a, b = self.fit_window_ls(r_win, t_win)  # [B,M,K,C]

        steps = torch.arange(1, pred_len + 1, device=t_hist.device, dtype=t_hist.dtype)
        t_fut = t_hist[:, -1:] + steps.unsqueeze(0)  # [B, pred]

        # evaluate per sample with its own coeffs
        S_norm = []
        for i in range(B):
            S_norm.append(self.seasonal_at(t_fut[i], a=a[i], b=b[i]))
        S_norm = torch.cat(S_norm, dim=0)  # [B, pred, C]
        return self.std_norm.denormalize(S_norm)


class series_decomp_fourier(nn.Module):
    """Fourier seasonal decomp + static/adaptive forecast. No RevIN."""

    def __init__(
        self,
        periods: Union[int, Sequence[int]] = 12,
        K: int = 3,
        n_vars: int = 1,
    ):
        super().__init__()
        self.seasonal = FourierSeasonal(periods=periods, K=K, n_vars=n_vars)

    @property
    def std_norm(self) -> SeasonalStdNorm:
        return self.seasonal.std_norm

    def forward(self, r1: torch.Tensor, t: Optional[torch.Tensor] = None):
        return self.seasonal(r1, t=t)

    def fit_least_squares(self, r1: torch.Tensor, t: Optional[torch.Tensor] = None):
        return self.seasonal.fit_least_squares(r1, t=t)

    def fit_std(self, r1_train: torch.Tensor):
        return self.seasonal.std_norm.fit(r1_train)

    def forecast(self, t_future: torch.Tensor) -> torch.Tensor:
        return self.seasonal.forecast(t_future)

    def forecast_adaptive(self, r1_hist, t_hist, pred_len, win=None):
        return self.seasonal.forecast_adaptive(r1_hist, t_hist, pred_len, win=win)
