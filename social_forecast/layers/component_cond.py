"""Component-conditioned prediction heads for DS-SAA fusion.

Design (identity-preserving)
----------------------------
S — Phase from calendar/time; amplitude from text
    φ = phase_head(cal/time)   # steps; zero-init → φ=0
    Ŝ_phase = Fourier(t + φ)
    Ŝ = (1 + κ g tanh α) ⊙ Ŝ_phase + κ g β
    α,β from text H_S only.

C — legacy EventConditionedJump (see layers.event_response for 方案二)

R — see layers.spectral_residual (Mamba retired as default)

Gates g∈[0,1] scale the *incremental* text effect only.
"""
from __future__ import annotations

from typing import Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


def _pool_h(H: torch.Tensor) -> torch.Tensor:
    """H: [B,L,d] or [B,d] -> [B,d]."""
    return H.mean(dim=1) if H.dim() == 3 else H


class CalendarPhaseEncoder(nn.Module):
    """Map calendar / absolute-time features → seasonal phase shift (steps)."""

    def __init__(self, period: float = 12.0, hidden: int = 32, max_shift: float = 2.0):
        super().__init__()
        self.period = float(period)
        self.max_shift = float(max_shift)
        self.net = nn.Sequential(
            nn.Linear(6, hidden), nn.GELU(), nn.Linear(hidden, 1))
        nn.init.zeros_(self.net[-1].weight)
        nn.init.zeros_(self.net[-1].bias)

    def forward(self, t_origin: torch.Tensor) -> torch.Tensor:
        """t_origin [B] absolute time index at forecast origin → phase [B] in steps."""
        P = self.period
        ang = 2.0 * torch.pi * t_origin / P
        feat = torch.stack([
            torch.sin(ang), torch.cos(ang),
            torch.sin(2 * ang), torch.cos(2 * ang),
            torch.sin(ang / 2.0), torch.cos(ang / 2.0),
        ], dim=-1)
        return self.max_shift * torch.tanh(self.net(feat).squeeze(-1))


class SeasonAmplitudeModulator(nn.Module):
    """Text-only amplitude / offset modulation of an already phase-aligned Ŝ.

    Phase is applied upstream (Fourier at t+φ).  This module must not move phase.
    """

    def __init__(self, d_text: int, n_vars: int = 1, hidden: int = 64, kappa: float = 0.5):
        super().__init__()
        self.n_vars = n_vars
        self.kappa = float(kappa)
        self.text_enc = nn.Sequential(
            nn.Linear(d_text, hidden),
            nn.GELU(),
            nn.Linear(hidden, hidden),
        )
        self.amp_head = nn.Linear(hidden, 2 * n_vars)  # α, β
        nn.init.zeros_(self.amp_head.weight)
        nn.init.zeros_(self.amp_head.bias)

    def forward(
        self,
        S_base: torch.Tensor,
        S_hist: torch.Tensor = None,  # unused; kept for API compat
        H_S: Optional[torch.Tensor] = None,
        gate: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        S_base: [B,P,C] phase-aligned Fourier forecast
        H_S:    text fusion (optional)
        gate:   [B] in [0,1]
        """
        B, P, C = S_base.shape
        if H_S is None:
            return S_base
        e_x = self.text_enc(_pool_h(H_S))
        g = gate if gate is not None else e_x.new_ones(B)
        g = g.view(B, 1, 1)
        alpha, beta = self.amp_head(e_x).chunk(2, dim=-1)
        scale = 1.0 + self.kappa * g * torch.tanh(alpha).unsqueeze(1)
        # tanh on beta too: the additive shift must be bounded, otherwise a
        # few high-magnitude text embeddings make Ŝ diverge in stage2 (the
        # forward-output explosion seen as SocialGood loss 0.28→233→1466).
        shift = self.kappa * g * torch.tanh(beta).unsqueeze(1)
        return S_base * scale + shift


class EventConditionedJump(nn.Module):
    """Wrap JumpDualBranch with optional event code from H_C (exo-heavy)."""

    def __init__(self, jump: nn.Module, d_text: int, hidden: Optional[int] = None):
        super().__init__()
        self.jump = jump
        h = int(hidden or jump.cls_head[0].in_features)
        # project text → same width as jump pooled temporal hidden
        self.d_jump_h = jump.tcn.hidden
        self.event_proj = nn.Linear(d_text, self.d_jump_h)
        nn.init.zeros_(self.event_proj.weight)
        nn.init.zeros_(self.event_proj.bias)
        # widen cls / amp first linear to accept + d_jump_h
        # instead of rewriting heads: add event bias into logits/amps via side heads
        self.cls_delta = nn.Linear(self.d_jump_h, jump.pred_len * jump.n_vars)
        self.amp_delta = nn.Linear(self.d_jump_h, jump.pred_len * jump.n_vars)
        nn.init.zeros_(self.cls_delta.weight)
        nn.init.zeros_(self.cls_delta.bias)
        nn.init.zeros_(self.amp_delta.weight)
        nn.init.zeros_(self.amp_delta.bias)

    def freeze_cls_head(self, freeze: bool = True):
        self.jump.freeze_cls_head(freeze)

    def forward_probs_amps(
        self,
        r2_hist: torch.Tensor,
        C_hist: torch.Tensor,
        H_C: Optional[torch.Tensor] = None,
        gate: Optional[torch.Tensor] = None,
    ):
        p, amp_log = self.jump.forward_probs_amps(r2_hist, C_hist)
        if H_C is None:
            return p, amp_log
        B = r2_hist.size(0)
        e = self.event_proj(_pool_h(H_C))
        g = (gate if gate is not None else e.new_ones(B)).view(B, 1, 1)
        dp = self.cls_delta(e).view(B, self.jump.pred_len, self.jump.n_vars)
        da = self.amp_delta(e).view(B, self.jump.pred_len, self.jump.n_vars)
        # gated event logits in prob space via logit shift
        logits = torch.logit(p.clamp(1e-4, 1 - 1e-4)) + g * dp
        p = torch.sigmoid(logits)
        amp_log = amp_log + g * da
        return p, amp_log

    def forecast(
        self,
        r2_hist: torch.Tensor,
        C_hist: torch.Tensor,
        H_C: Optional[torch.Tensor] = None,
        gate: Optional[torch.Tensor] = None,
    ):
        from layers.jump_branch import signed_expm1
        p, amp_log = self.forward_probs_amps(r2_hist, C_hist, H_C=H_C, gate=gate)
        amp = signed_expm1(amp_log)
        scale = torch.maximum(
            C_hist.abs().amax(dim=1, keepdim=True),
            r2_hist.abs().amax(dim=1, keepdim=True),
        ).clamp_min(1e-3)
        amp = amp.clamp(-3.0 * scale, 3.0 * scale)
        mask = (p > self.jump.theta).to(dtype=amp.dtype)
        return amp * mask, p

    def loss_cls(self, p, y_evt):
        return self.jump.loss_cls(p, y_evt)

    def loss_amp(self, amp_log, C_true, y_evt):
        return self.jump.loss_amp(amp_log, C_true, y_evt)

    @property
    def theta(self):
        return self.jump.theta

    @theta.setter
    def theta(self, v):
        self.jump.theta = v


class ConditionalMambaResidual(nn.Module):
    """FiLM-condition Mamba on [time-R encoding ‖ text H_R] + gated text residual."""

    def __init__(self, mamba: nn.Module, d_text: int, hidden: int = 64, kappa: float = 0.5):
        super().__init__()
        self.mamba = mamba
        self.kappa = float(kappa)
        d_model = mamba.in_proj.out_features
        n_vars = mamba.n_vars
        self.time_dim = 4 * n_vars
        self.time_enc = nn.Sequential(
            nn.Linear(self.time_dim, hidden), nn.GELU(), nn.Linear(hidden, hidden))
        self.text_enc = nn.Sequential(
            nn.Linear(d_text, hidden), nn.GELU(), nn.Linear(hidden, hidden))
        self.film = nn.Linear(hidden * 2, 2 * d_model)  # γ, β on channel
        nn.init.zeros_(self.film.weight)
        nn.init.zeros_(self.film.bias)
        # additive text residual on forecast
        self.text_head = nn.Sequential(
            nn.Linear(d_text, hidden), nn.GELU(),
            nn.Linear(hidden, mamba.pred_len * n_vars),
        )
        nn.init.zeros_(self.text_head[-1].weight)
        nn.init.zeros_(self.text_head[-1].bias)

    @property
    def active(self):
        return self.mamba.active

    def fit_norm(self, r_train):
        return self.mamba.fit_norm(r_train)

    def maybe_deactivate_white_noise(self, r_train, lags=10, alpha=0.05):
        return self.mamba.maybe_deactivate_white_noise(r_train, lags=lags, alpha=alpha)

    def encode_time(self, R_hist: torch.Tensor) -> torch.Tensor:
        mu = R_hist.mean(dim=1)
        sd = R_hist.std(dim=1, unbiased=False)
        last = R_hist[:, -1, :]
        mag = R_hist.abs().mean(dim=1)
        return self.time_enc(torch.cat([mu, sd, last, mag], dim=-1))

    def forward(
        self,
        r_hist: torch.Tensor,
        H_R: Optional[torch.Tensor] = None,
        gate: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        B = r_hist.size(0)
        if int(self.mamba.active.item()) == 0 and H_R is None:
            return r_hist.new_zeros(B, self.mamba.pred_len, self.mamba.n_vars)

        # --- conditional Mamba body (mirror MambaResidualHead.forward) ---
        if int(self.mamba.active.item()) == 1:
            x = self.mamba.norm.normalize(r_hist)
            h = self.mamba.in_proj(x)  # [B,L,D]
            e_t = self.encode_time(r_hist)
            if H_R is None:
                e_x = e_t.new_zeros(B, e_t.size(-1))
                g = e_t.new_zeros(B)
            else:
                e_x = self.text_enc(_pool_h(H_R))
                g = gate if gate is not None else e_t.new_ones(B)
            gb = self.film(torch.cat([e_t, e_x], dim=-1))
            gamma, beta = gb.chunk(2, dim=-1)  # [B,D]
            g = g.view(B, 1, 1)
            # FiLM incremental: h <- h * (1+κ g tanhγ) + κ g β
            h = h * (1.0 + self.kappa * g * torch.tanh(gamma).unsqueeze(1)) \
                + self.kappa * g * beta.unsqueeze(1)
            for layer in self.mamba.layers:
                h = layer(h)
            out = self.mamba.head(h.reshape(B, -1)).view(
                B, self.mamba.pred_len, self.mamba.n_vars)
            y = self.mamba.norm.denormalize(out)
        else:
            y = r_hist.new_zeros(B, self.mamba.pred_len, self.mamba.n_vars)
            g = gate if gate is not None else r_hist.new_zeros(B)
            g = g.view(B, 1, 1)

        if H_R is not None:
            add = self.text_head(_pool_h(H_R)).view(
                B, self.mamba.pred_len, self.mamba.n_vars)
            y = y + g * add
        return y
