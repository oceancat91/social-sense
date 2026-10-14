"""Lightweight selective SSM (Mamba-style) in pure PyTorch — no mamba_ssm CUDA dep."""
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class ResidualStdNorm(nn.Module):
    """Global StandardScaler for R (train mean/std only). No RevIN."""

    def __init__(self, n_vars: int = 1, eps: float = 1e-5):
        super().__init__()
        self.eps = eps
        self.register_buffer('mean', torch.zeros(n_vars))
        self.register_buffer('std', torch.ones(n_vars))
        self.register_buffer('is_fit', torch.tensor(False))

    @torch.no_grad()
    def fit(self, r_train: torch.Tensor):
        if r_train.dim() == 3:
            r_train = r_train.reshape(-1, r_train.size(-1))
        mean = r_train.mean(dim=0)
        std = r_train.std(dim=0, unbiased=False).clamp_min(self.eps)
        self.mean.copy_(mean.to(self.mean.dtype))
        self.std.copy_(std.to(self.std.dtype))
        self.is_fit.fill_(True)
        return self

    def normalize(self, x):
        return (x - self.mean.to(dtype=x.dtype)) / self.std.to(dtype=x.dtype)

    def denormalize(self, x):
        return x * self.std.to(dtype=x.dtype) + self.mean.to(dtype=x.dtype)


def ljung_box_is_white_noise(series: torch.Tensor, lags: int = 10, alpha: float = 0.05) -> bool:
    """True if Ljung-Box cannot reject H0 (white noise) at level alpha.

    Pure-numpy LB Q-stat (avoids broken statsmodels/pandas deprecations).
    series: [N] or [N, C] (flattened).
    """
    from math import erfc, sqrt

    x = series.detach().cpu().numpy().astype(np.float64).reshape(-1)
    n = x.size
    if n < lags + 5:
        return False
    x = x - x.mean()
    var = float(np.dot(x, x))
    if var < 1e-12:
        return True
    q = 0.0
    for k in range(1, lags + 1):
        rho = float(np.dot(x[k:], x[:-k]) / var)
        q += (rho * rho) / (n - k)
    q *= n * (n + 2)
    # chi2 survival approx via erfc for df=lags (Wilson–Hilferty-ish normal)
    # use incomplete-gamma via scipy if present, else normal approx
    try:
        from scipy.stats import chi2
        p = float(chi2.sf(q, lags))
    except Exception:
        # rough normal approx of chi2
        z = (q / lags) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * lags))
        z /= sqrt(2.0 / (9.0 * lags))
        p = 0.5 * erfc(z / sqrt(2.0))
    return p > alpha


class SelectiveSSM(nn.Module):
    """S6: input-dependent Δ, B, C with diagonal A; sequential scan."""

    def __init__(self, d_model: int, d_state: int = 16, dt_rank: Optional[int] = None):
        super().__init__()
        self.d_model = d_model
        self.d_state = d_state
        self.dt_rank = dt_rank or max(1, d_model // 16)

        self.A_log = nn.Parameter(torch.log(torch.arange(1, d_state + 1, dtype=torch.float32)
                                            .unsqueeze(0).expand(d_model, -1)))
        self.D = nn.Parameter(torch.ones(d_model))
        self.x_proj = nn.Linear(d_model, self.dt_rank + 2 * d_state, bias=False)
        self.dt_proj = nn.Linear(self.dt_rank, d_model)

    def forward(self, u: torch.Tensor) -> torch.Tensor:
        # u: [B, L, D]
        Bsz, L, D = u.shape
        x_dbl = self.x_proj(u)  # [B,L, dt_rank+2N]
        dt, B, C = torch.split(x_dbl, [self.dt_rank, self.d_state, self.d_state], dim=-1)
        dt = F.softplus(self.dt_proj(dt))           # [B,L,D]
        A = -torch.exp(self.A_log.float())          # [D,N]

        y = u.new_zeros(Bsz, L, D)
        h = u.new_zeros(Bsz, D, self.d_state)
        for t in range(L):
            # discretize: dA = exp(dt * A), dB = dt * B
            dt_t = dt[:, t]                         # [B,D]
            dA = torch.exp(dt_t.unsqueeze(-1) * A)  # [B,D,N]
            dB = dt_t.unsqueeze(-1) * B[:, t].unsqueeze(1)  # [B,D,N]
            h = dA * h + dB * u[:, t].unsqueeze(-1)
            y[:, t] = torch.einsum('bdn,bn->bd', h, C[:, t]) + self.D * u[:, t]
        return y


class MambaBlock(nn.Module):
    def __init__(self, d_model: int, d_state: int = 16, expand: int = 2, conv_kernel: int = 3):
        super().__init__()
        d_inner = d_model * expand
        self.in_proj = nn.Linear(d_model, 2 * d_inner, bias=False)
        self.conv1d = nn.Conv1d(d_inner, d_inner, conv_kernel, padding=conv_kernel - 1,
                                groups=d_inner)
        self.ssm = SelectiveSSM(d_inner, d_state=d_state)
        self.out_proj = nn.Linear(d_inner, d_model, bias=False)
        self.norm = nn.LayerNorm(d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B,L,D]
        residual = x
        x = self.norm(x)
        xz = self.in_proj(x)
        x, z = xz.chunk(2, dim=-1)
        x = self.conv1d(x.transpose(1, 2))[:, :, :x.size(1)].transpose(1, 2)
        x = F.silu(x)
        y = self.ssm(x) * F.silu(z)
        return residual + self.out_proj(y)


class MambaResidualHead(nn.Module):
    """Fluctuation branch: R = r2 - C (C=0 for now) -> Mamba -> R̂.

    White-noise degeneration: if Ljung-Box fails to reject H0, predict zeros.
    """

    def __init__(
        self,
        seq_len: int,
        pred_len: int,
        n_vars: int = 1,
        d_model: int = 64,
        n_layers: int = 2,
        d_state: int = 16,
    ):
        super().__init__()
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.n_vars = n_vars
        self.norm = ResidualStdNorm(n_vars)
        self.in_proj = nn.Linear(n_vars, d_model)
        self.layers = nn.ModuleList([
            MambaBlock(d_model, d_state=d_state) for _ in range(n_layers)
        ])
        self.head = nn.Linear(d_model * seq_len, pred_len * n_vars)
        # buffer flag: 1 = use Mamba, 0 = zero forecast (white noise)
        self.register_buffer('active', torch.tensor(1, dtype=torch.int32))

    @torch.no_grad()
    def fit_norm(self, r_train: torch.Tensor):
        return self.norm.fit(r_train)

    @torch.no_grad()
    def maybe_deactivate_white_noise(self, r_train: torch.Tensor, lags: int = 10, alpha: float = 0.05):
        flat = r_train.reshape(-1, r_train.size(-1))[:, 0]
        if ljung_box_is_white_noise(flat, lags=lags, alpha=alpha):
            self.active.fill_(0)
            return True
        self.active.fill_(1)
        return False

    def forward(self, r_hist: torch.Tensor) -> torch.Tensor:
        """r_hist: [B, L, C] -> R̂: [B, pred_len, C]"""
        B = r_hist.size(0)
        if int(self.active.item()) == 0:
            return r_hist.new_zeros(B, self.pred_len, self.n_vars)

        x = self.norm.normalize(r_hist)
        h = self.in_proj(x)
        for layer in self.layers:
            h = layer(h)
        out = self.head(h.reshape(B, -1)).view(B, self.pred_len, self.n_vars)
        return self.norm.denormalize(out)
