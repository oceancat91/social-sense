"""Dual-branch jump forecast: event classification + amplitude regression."""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


def signed_log(c: torch.Tensor) -> torch.Tensor:
    return torch.sign(c) * torch.log(c.abs() + 1.0)


def signed_expm1(z: torch.Tensor) -> torch.Tensor:
    return torch.sign(z) * (torch.exp(z.abs()) - 1.0)


def window_stats(r: torch.Tensor) -> torch.Tensor:
    """r: [B, L, C] -> [B, 5*C] mean/std/skew/kurt/acf1."""
    B, L, C = r.shape
    x = r
    mean = x.mean(dim=1)
    std = x.std(dim=1, unbiased=False).clamp_min(1e-6)
    z = (x - mean.unsqueeze(1)) / std.unsqueeze(1)
    skew = (z ** 3).mean(dim=1)
    kurt = (z ** 4).mean(dim=1) - 3.0
    if L >= 2:
        x0, x1 = x[:, :-1] - mean.unsqueeze(1), x[:, 1:] - mean.unsqueeze(1)
        acf = (x0 * x1).mean(dim=1) / (std * std)
    else:
        acf = torch.zeros_like(mean)
    return torch.cat([mean, std, skew, kurt, acf], dim=-1)


def event_features(C: torch.Tensor) -> torch.Tensor:
    """C: [B, L, C] sparse jump hist -> [B, 4*C]
    last amp, steps since last, mean |amp|, jump count / L.
    """
    B, L, Ch = C.shape
    device, dtype = C.device, C.dtype
    last_amp = C.new_zeros(B, Ch)
    since = C.new_full((B, Ch), float(L))
    mean_abs = C.new_zeros(B, Ch)
    rate = C.new_zeros(B, Ch)
    for b in range(B):
        for c in range(Ch):
            idx = (C[b, :, c].abs() > 1e-8).nonzero(as_tuple=False).view(-1)
            if idx.numel() == 0:
                continue
            amps = C[b, idx, c]
            last_amp[b, c] = amps[-1]
            since[b, c] = float(L - 1 - int(idx[-1].item()))
            mean_abs[b, c] = amps.abs().mean()
            rate[b, c] = float(idx.numel()) / float(L)
    return torch.cat([last_amp, since, mean_abs, rate], dim=-1)


def drift_feature(r: torch.Tensor, win: int = 3) -> torch.Tensor:
    """Recent rolling-mean slope. r [B,L,C] -> [B,C]."""
    B, L, C = r.shape
    w = max(2, min(win, L // 2 if L >= 4 else L))
    if L < 2:
        return r.new_zeros(B, C)
    # slope of last 2w points via simple end-start / w
    left = r[:, -2 * w:-w].mean(dim=1) if L >= 2 * w else r[:, : L // 2].mean(dim=1)
    right = r[:, -w:].mean(dim=1)
    return (right - left) / float(w)


def build_jump_features(r2: torch.Tensor, C: torch.Tensor) -> torch.Tensor:
    """Concat window / event / drift features. [B, F]."""
    return torch.cat([window_stats(r2), event_features(C), drift_feature(r2)], dim=-1)


class TemporalConvEncoder(nn.Module):
    """Light TCN over residual window -> per-step hidden."""

    def __init__(self, n_vars: int = 1, hidden: int = 32, n_layers: int = 2):
        super().__init__()
        layers = []
        in_ch = n_vars
        for i in range(n_layers):
            dil = 2 ** i
            layers += [
                nn.Conv1d(in_ch, hidden, 3, padding=dil, dilation=dil),
                nn.GELU(),
            ]
            in_ch = hidden
        self.net = nn.Sequential(*layers)
        self.hidden = hidden

    def forward(self, r: torch.Tensor) -> torch.Tensor:
        # r: [B,L,C] -> [B,L,H]
        h = self.net(r.transpose(1, 2))
        return h[:, :, :r.size(1)].transpose(1, 2)


class JumpDualBranch(nn.Module):
    """Event cls (per future step) + amplitude regression (signed-log)."""

    def __init__(
        self,
        seq_len: int,
        pred_len: int,
        n_vars: int = 1,
        hidden: int = 32,
        theta: float = 0.5,
        pos_weight: float = 5.0,
    ):
        super().__init__()
        self.seq_len = seq_len
        self.pred_len = pred_len
        self.n_vars = n_vars
        self.theta = theta
        self.pos_weight = pos_weight

        feat_dim = 5 * n_vars + 4 * n_vars + n_vars  # stats + event + drift
        self.tcn = TemporalConvEncoder(n_vars, hidden=hidden)
        self.cls_head = nn.Sequential(
            nn.Linear(hidden + feat_dim, hidden),
            nn.GELU(),
            nn.Linear(hidden, pred_len * n_vars),
        )
        self.amp_head = nn.Sequential(
            nn.Linear(feat_dim + n_vars, hidden),
            nn.GELU(),
            nn.Linear(hidden, hidden),
            nn.GELU(),
            nn.Linear(hidden, pred_len * n_vars),
        )

    def freeze_cls_head(self, freeze: bool = True):
        for p in self.cls_head.parameters():
            p.requires_grad = not freeze

    def forward_probs_amps(self, r2_hist: torch.Tensor, C_hist: torch.Tensor):
        """Return p [B,P,C], amp_raw (signed-log) [B,P,C]."""
        B = r2_hist.size(0)
        feat = build_jump_features(r2_hist, C_hist)
        h = self.tcn(r2_hist)                       # [B,L,H]
        h_pool = h.mean(dim=1)                      # [B,H]
        logits = self.cls_head(torch.cat([h_pool, feat], dim=-1))
        p = torch.sigmoid(logits).view(B, self.pred_len, self.n_vars)
        # amp uses feat + last residual value
        amp_in = torch.cat([feat, r2_hist[:, -1, :]], dim=-1)
        amp_log = self.amp_head(amp_in).view(B, self.pred_len, self.n_vars)
        return p, amp_log

    def forecast(self, r2_hist: torch.Tensor, C_hist: torch.Tensor) -> torch.Tensor:
        """Sparse Ĉ: amp only where p > theta; clamp amp by hist scale."""
        p, amp_log = self.forward_probs_amps(r2_hist, C_hist)
        amp = signed_expm1(amp_log)
        # soft amp cap from historical |C| / |r2|
        scale = torch.maximum(
            C_hist.abs().amax(dim=1, keepdim=True),
            r2_hist.abs().amax(dim=1, keepdim=True),
        ).clamp_min(1e-3)
        amp = amp.clamp(-3.0 * scale, 3.0 * scale)
        mask = (p > self.theta).to(dtype=amp.dtype)
        return amp * mask, p

    def loss_cls(self, p: torch.Tensor, y_evt: torch.Tensor) -> torch.Tensor:
        """y_evt: [B,P,C] in {0,1}. Weighted BCE."""
        w = torch.where(y_evt > 0.5, self.pos_weight, 1.0)
        return F.binary_cross_entropy(p.clamp(1e-6, 1 - 1e-6), y_evt, weight=w)

    def loss_amp(self, amp_log: torch.Tensor, C_true: torch.Tensor, y_evt: torch.Tensor) -> torch.Tensor:
        """MSE in signed-log space, only on event steps."""
        tgt = signed_log(C_true)
        mask = (y_evt > 0.5).to(dtype=amp_log.dtype)
        if mask.sum() < 1:
            return amp_log.sum() * 0.0
        return ((amp_log - tgt) ** 2 * mask).sum() / mask.sum()
