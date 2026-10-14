"""Semantic Routing Sparse Attention (SRSA).

Two-step exo attention:
  1) Semantic pre-route mask from text embedding (LLM frozen, train W_route)
  2) Numeric anchor verification with log-p prior on attention logits

Corrected prior (not Softmax(score * p), which is invariant to positive scale):
  α = Softmax( QK^T/√d + log p_i )  with hard mask p_i < τ → −∞
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from layers.ds_saa_semantic import ExoEventBatch
from utils.text_route import ROUTE2IDX

COMPONENTS = ("T", "S", "C", "R")
COMP2IDX: Dict[str, int] = {c: i for i, c in enumerate(COMPONENTS)}
__all__ = [
    "COMPONENTS", "COMP2IDX", "ROUTE2IDX",
    "SemanticRouteHead", "SRSAExoAttention",
    "route_ce_loss", "mask_events_by_route",
]


class SemanticRouteHead(nn.Module):
    """p_route = Softmax(W h_text + b) over T/S/C/R."""

    def __init__(self, d_model: int, n_comp: int = 4):
        super().__init__()
        self.n_comp = int(n_comp)
        self.proj = nn.Linear(d_model, self.n_comp)

    def forward(
        self, V: torch.Tensor, mask: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        V: [B,E,d]  → logits [B,E,4], probs [B,E,4]
        """
        logits = self.proj(V)
        probs = F.softmax(logits, dim=-1)
        if mask is not None:
            m = mask.unsqueeze(-1)
            probs = probs * m
        return logits, probs


def route_ce_loss(
    logits: torch.Tensor,
    labels: torch.Tensor,
    mask: torch.Tensor,
) -> torch.Tensor:
    """CE on weakly labeled event slots; ignore_index=-1."""
    B, E, C = logits.shape
    flat_logits = logits.reshape(B * E, C)
    flat_y = labels.reshape(B * E).long()
    flat_m = mask.reshape(B * E) > 0
    # also ignore unlabeled
    valid = flat_m & (flat_y >= 0)
    if valid.sum() < 1:
        return logits.new_zeros(())
    return F.cross_entropy(flat_logits[valid], flat_y[valid])


class SRSAExoAttention(nn.Module):
    """Sparse time-anchored exo attn with semantic route mask + log-p prior."""

    def __init__(self, d_model: int, tau_route: float = 0.1):
        super().__init__()
        self.d_model = int(d_model)
        self.tau_route = float(tau_route)
        self.W_q = nn.Linear(d_model, d_model, bias=False)

    def forward(
        self,
        Q: torch.Tensor,
        events: ExoEventBatch,
        p_comp: torch.Tensor,
        gate: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Q: [B,L,d]
        events: shared exo pool
        p_comp: [B,E] route probability for this component
        returns A_exo [B,L,d]
        """
        B, L, d = Q.shape
        E = events.V.size(1)
        A = Q.new_zeros(B, L, d)
        if E == 0 or events.mask.sum() < 1:
            return A

        Qp = self.W_q(Q)
        scale = 1.0 / math.sqrt(d)
        pos = events.pos.clamp(0, L - 1)
        b_idx = torch.arange(B, device=Q.device).unsqueeze(1).expand(B, E)
        Q_e = Qp[b_idx, pos]
        score = (Q_e * events.V).sum(dim=-1) * scale
        # log-prior (safe)
        score = score + torch.log(p_comp.clamp_min(1e-6))
        route_ok = (p_comp >= self.tau_route) & (events.mask > 0)
        score = score.masked_fill(~route_ok, float("-inf"))

        alpha = torch.softmax(score, dim=-1)
        alpha = torch.nan_to_num(alpha, nan=0.0)
        alpha = alpha * events.mask * events.quality * p_comp
        if gate is not None:
            alpha = alpha * gate.unsqueeze(-1)

        contrib = alpha.unsqueeze(-1) * events.V
        A = A.scatter_add(1, pos.unsqueeze(-1).expand(B, E, d), contrib)
        self._last_alpha = alpha.detach()
        return A


def _copy_struct(events: ExoEventBatch, **kwargs) -> ExoEventBatch:
    base = dict(
        V=events.V, pos=events.pos, mask=events.mask, quality=events.quality,
        route_label=events.route_label, target=events.target,
        intensity=events.intensity, duration=events.duration,
        shape=events.shape, confidence=events.confidence,
    )
    base.update(kwargs)
    return ExoEventBatch(**base)


def mask_events_by_route(
    events: ExoEventBatch,
    p_comp: torch.Tensor,
    tau: float,
    hard_target: Optional[torch.Tensor] = None,
    hard_idx: Optional[int] = None,
) -> ExoEventBatch:
    """Route hard-mask. If parser ``target`` is set, it overrides p_comp."""
    if hard_target is not None and hard_idx is not None:
        parse_ok = hard_target == int(hard_idx)
        unlabeled = hard_target < 0
        route_ok = torch.where(unlabeled, p_comp >= tau, parse_ok)
    else:
        route_ok = p_comp >= tau
    new_mask = events.mask * route_ok.to(events.mask.dtype)
    new_q = events.quality * p_comp.clamp(0, 1)
    return _copy_struct(events, mask=new_mask, quality=new_q)


def consist_kl(
    p_route: torch.Tensor,
    alpha_stack: torch.Tensor,
    mask: torch.Tensor,
    eps: float = 1e-6,
) -> torch.Tensor:
    """KL(p_route || p_attn) over T/S/R (not C; C is trigger-only).

    p_route: [B,E,4], alpha_stack: [B,E,3] unnormalized mass on T/S/R,
    mask: [B,E]
    """
    valid = mask > 0
    if valid.sum() < 1:
        return p_route.new_zeros(())
    p = p_route[..., [0, 1, 3]].clamp_min(eps)
    p = p / p.sum(dim=-1, keepdim=True)
    q = alpha_stack.clamp_min(eps)
    q = q / q.sum(dim=-1, keepdim=True)
    kl = (p * (p.log() - q.log())).sum(dim=-1)
    return kl[valid].mean()
