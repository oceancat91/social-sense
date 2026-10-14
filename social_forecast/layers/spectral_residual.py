"""Spectral / band-limited residual head (replaces Mamba for R).

Keeps only salient frequency bands of the history residual R, then maps the
reconstructed band-limited series to the forecast horizon.  Optional text
FiLM on spectral magnitudes (zero-init → identity).
"""
from __future__ import annotations

from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from layers.Mamba_block import ResidualStdNorm, ljung_box_is_white_noise


class SpectralResidualHead(nn.Module):
    """R̂ from top-k spectral bands of R_hist (+ optional text FiLM)."""

    def __init__(
        self,
        seq_len: int,
        pred_len: int,
        n_vars: int = 1,
        n_bands: int = 4,
        hidden: int = 64,
        d_text: int = 64,
        kappa: float = 0.5,
    ):
        super().__init__()
        self.seq_len = int(seq_len)
        self.pred_len = int(pred_len)
        self.n_vars = int(n_vars)
        self.n_bands = int(n_bands)
        self.kappa = float(kappa)
        self.norm = ResidualStdNorm(n_vars=n_vars)
        self.register_buffer("active", torch.tensor(1))

        # rfft length
        self.n_freq = self.seq_len // 2 + 1
        # learnable soft mask over frequencies (init: prefer mid/high, damp DC)
        self.band_logit = nn.Parameter(torch.zeros(self.n_freq))
        with torch.no_grad():
            # gently suppress DC / very low
            if self.n_freq > 0:
                self.band_logit[0] = -2.0
            if self.n_freq > 1:
                self.band_logit[1] = -1.0

        self.head = nn.Sequential(
            nn.Linear(self.seq_len * n_vars, hidden),
            nn.GELU(),
            nn.Linear(hidden, pred_len * n_vars),
        )
        # text FiLM on frequency magnitudes
        self.text_enc = nn.Sequential(
            nn.Linear(d_text, hidden), nn.GELU(), nn.Linear(hidden, hidden))
        self.film = nn.Linear(hidden, 2 * self.n_freq)  # γ, β per freq
        nn.init.zeros_(self.film.weight)
        nn.init.zeros_(self.film.bias)
        self.text_head = nn.Sequential(
            nn.Linear(d_text, hidden), nn.GELU(),
            nn.Linear(hidden, pred_len * n_vars),
        )
        nn.init.zeros_(self.text_head[-1].weight)
        nn.init.zeros_(self.text_head[-1].bias)

    def fit_norm(self, r_train: torch.Tensor):
        return self.norm.fit(r_train)

    def maybe_deactivate_white_noise(self, r_train, lags=10, alpha=0.05):
        if ljung_box_is_white_noise(r_train, lags=lags, alpha=alpha):
            self.active.fill_(0)
            return True
        return False

    def _band_limit(self, r: torch.Tensor, H_R=None, gate=None) -> torch.Tensor:
        """r [B,L,C] → band-limited [B,L,C]."""
        B, L, C = r.shape
        # per-channel rfft
        outs = []
        mask = torch.sigmoid(self.band_logit)  # [F]
        # keep top-n_bands by soft mask * optional hard topk blend
        topk = min(self.n_bands, self.n_freq)
        _, idx = torch.topk(mask, k=topk)
        hard = torch.zeros_like(mask)
        hard[idx] = 1.0
        # straight-through-ish: use soft in train, soft*hard emphasis
        m = mask * (0.5 + 0.5 * hard)

        g = None
        if H_R is not None:
            h = H_R.mean(dim=1) if H_R.dim() == 3 else H_R
            e = self.text_enc(h)
            gb = self.film(e)
            gamma, beta = gb.chunk(2, dim=-1)  # [B,F]
            g = gate if gate is not None else h.new_ones(B)
            g = g.view(B, 1)
        for c in range(C):
            spec = torch.fft.rfft(r[:, :, c], n=L)  # [B,F] complex
            mag = spec.abs()
            phase = torch.angle(spec)
            if g is not None:
                mag = mag * (1.0 + self.kappa * g * torch.tanh(gamma)) \
                    + self.kappa * g * torch.tanh(beta)
            mag = mag * m.view(1, -1)
            spec2 = torch.polar(mag, phase)
            outs.append(torch.fft.irfft(spec2, n=L))
        return torch.stack(outs, dim=-1)

    def forward(
        self,
        r_hist: torch.Tensor,
        H_R: Optional[torch.Tensor] = None,
        gate: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        B = r_hist.size(0)
        if int(self.active.item()) == 0 and H_R is None:
            return r_hist.new_zeros(B, self.pred_len, self.n_vars)

        if int(self.active.item()) == 1:
            x = self.norm.normalize(r_hist)
            x_f = self._band_limit(x, H_R=H_R, gate=gate)
            y = self.head(x_f.reshape(B, -1)).view(B, self.pred_len, self.n_vars)
            y = self.norm.denormalize(y)
        else:
            y = r_hist.new_zeros(B, self.pred_len, self.n_vars)

        if H_R is not None:
            h = H_R.mean(dim=1) if H_R.dim() == 3 else H_R
            g = gate if gate is not None else h.new_ones(B)
            # bounded additive text increment (prevents forward explosion)
            add = torch.tanh(self.text_head(h)).view(B, self.pred_len, self.n_vars)
            y = y + g.view(B, 1, 1) * add
        return y
