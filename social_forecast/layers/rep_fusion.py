"""Representation encoders, path-wise fusion, and sparse MoE mixing.

Design (locked)
---------------
T — Linear stream + text regime scaling
S — Patch-CNN + FiLM
C — Sparse encode + trigger cross-attn (silent without exo)
R — Mamba + text cross-attn
Mix — Top-k gated experts (not a convex average of raw H_i)
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from layers.Mamba_block import MambaBlock

COMPONENTS = ("T", "S", "C", "R")


def _pool(h: torch.Tensor) -> torch.Tensor:
    """[B,L,d] or [B,d] -> [B,d]."""
    return h.mean(dim=1) if h.dim() == 3 else h


def _expand_text(h: torch.Tensor, L: int) -> torch.Tensor:
    """Broadcast [B,d] / [B,L,d] -> [B,L,d]."""
    if h.dim() == 2:
        return h.unsqueeze(1).expand(-1, L, -1)
    return h


# ---------------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------------

class LinearStreamEncoder(nn.Module):
    """DLinear / xPatch trend-style: map scalar series → d_model tokens."""

    def __init__(self, n_vars: int, d_model: int):
        super().__init__()
        self.proj = nn.Linear(n_vars, d_model)
        self.norm = nn.LayerNorm(d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B,L,C]
        return self.norm(self.proj(x))


class PatchCNNEncoder(nn.Module):
    """xPatch-style nonlinear stream for seasonal structure."""

    def __init__(
        self,
        n_vars: int,
        d_model: int,
        patch_len: int = 2,
        stride: int = 1,
        n_layers: int = 2,
    ):
        super().__init__()
        self.patch_len = int(patch_len)
        self.stride = int(stride)
        self.patch_proj = nn.Linear(patch_len * n_vars, d_model)
        layers = []
        for _ in range(n_layers):
            layers += [
                nn.Conv1d(d_model, d_model, kernel_size=3, padding=1, groups=1),
                nn.GELU(),
            ]
        self.cnn = nn.Sequential(*layers)
        self.norm = nn.LayerNorm(d_model)
        self.out = nn.Linear(d_model, d_model)

    def _patchify(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B,L,C] → [B,N,patch*C]
        B, L, C = x.shape
        if L < self.patch_len:
            x = F.pad(x, (0, 0, 0, self.patch_len - L))
            L = x.size(1)
        patches = x.unfold(1, self.patch_len, self.stride)  # [B,N,C,P]
        return patches.reshape(B, patches.size(1), -1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # return tokens aligned to original L by interpolate
        B, L, _ = x.shape
        p = self._patchify(x)
        h = self.patch_proj(p)                 # [B,N,d]
        h = self.cnn(h.transpose(1, 2)).transpose(1, 2)
        h = self.out(self.norm(h))
        if h.size(1) == L:
            return h
        # upsample patch tokens → L
        h = F.interpolate(
            h.transpose(1, 2), size=L, mode="linear", align_corners=False
        ).transpose(1, 2)
        return h


class SparseEventEncoder(nn.Module):
    """Encode sparse jump traces C (+ optional r2 energy)."""

    def __init__(self, n_vars: int, d_model: int):
        super().__init__()
        self.proj = nn.Linear(2 * n_vars, d_model)
        self.norm = nn.LayerNorm(d_model)

    def forward(self, C: torch.Tensor, r2: Optional[torch.Tensor] = None) -> torch.Tensor:
        if r2 is None:
            r2 = torch.zeros_like(C)
        return self.norm(self.proj(torch.cat([C, r2], dim=-1)))


class MambaEncoder(nn.Module):
    """Residual stream: project → Mamba blocks → tokens."""

    def __init__(
        self,
        n_vars: int,
        d_model: int,
        n_layers: int = 2,
        d_state: int = 16,
    ):
        super().__init__()
        self.in_proj = nn.Linear(n_vars, d_model)
        self.layers = nn.ModuleList(
            [MambaBlock(d_model, d_state=d_state) for _ in range(n_layers)]
        )
        self.norm = nn.LayerNorm(d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.in_proj(x)
        for layer in self.layers:
            h = layer(h)
        return self.norm(h)


# ---------------------------------------------------------------------------
# Path-wise fusion (four components play *different* roles, so each gets its
# own injection mechanism instead of one shared cross-attention):
#   T — concat & fine-tune the trend with the text trend vector
#   S — FiLM modulate the seasonal stream
#   C — event-triggered jump enhancement (silent without exo)
#   R — gentle scale modulation of the residual (noise) stream
# ---------------------------------------------------------------------------

class TrendConcatFusion(nn.Module):
    """T: concat(text-trend-vector, H_ts) → linear → additive fine-tune.

    Trend is the low-frequency baseline: the text *trend* semantic should
    enrich the raw trend tokens (concatenation) and then nudge them with a
    small residual (fine-tune), not re-scale them.  Small-init → near-identity
    at start; ``H_tx=None`` returns ``H_ts`` unchanged.
    """

    def __init__(self, d_model: int):
        super().__init__()
        self.tune = nn.Linear(2 * d_model, d_model)
        nn.init.normal_(self.tune.weight, std=0.02)
        nn.init.zeros_(self.tune.bias)
        self.norm = nn.LayerNorm(d_model)

    def forward(self, H_ts: torch.Tensor, H_tx: Optional[torch.Tensor]) -> torch.Tensor:
        if H_tx is None:
            return H_ts
        e = _expand_text(H_tx, H_ts.size(1))        # [B,L,d]
        z = torch.cat([H_ts, e], dim=-1)            # [B,L,2d] enriched trend
        return self.norm(H_ts + self.tune(z))       # residual fine-tune


class FiLMFusion(nn.Module):
    """S: γ⊙H_ts + β from text. Small-init → near-identity at start.

    See RegimeScaleFusion: small-random init keeps the text gradient channel
    open (zero-init would block it).
    """

    def __init__(self, d_model: int):
        super().__init__()
        self.to_gb = nn.Linear(d_model, 2 * d_model)
        nn.init.normal_(self.to_gb.weight, std=0.02)
        nn.init.zeros_(self.to_gb.bias)

    def forward(self, H_ts: torch.Tensor, H_tx: Optional[torch.Tensor]) -> torch.Tensor:
        if H_tx is None:
            return H_ts
        e = _pool(H_tx)                          # [B,d]
        gamma, beta = self.to_gb(e).chunk(2, dim=-1)
        return (1.0 + torch.tanh(gamma.unsqueeze(1))) * H_ts + beta.unsqueeze(1)


class EventJumpFusion(nn.Module):
    """C: event vector → amplify/shift the jump stream (silent without trigger).

    Jumps are sparse one-off shocks: the text *event* semantic should only
    *enhance* an existing jump (scale + shift) and stay silent when no exo
    event fires (gate=0).  No cross-attention — a single event vector is enough
    to steer the jump path, and it cannot overfit like full multi-head attention.
    """

    def __init__(self, d_model: int):
        super().__init__()
        self.to_ab = nn.Linear(d_model, 2 * d_model)
        nn.init.normal_(self.to_ab.weight, std=0.02)
        nn.init.zeros_(self.to_ab.bias)

    def forward(self, H_ts: torch.Tensor, H_tx: Optional[torch.Tensor],
                gate: Optional[torch.Tensor] = None) -> torch.Tensor:
        if H_tx is None:
            return H_ts
        if gate is not None and float(gate.detach().sum()) < 1e-6:
            return H_ts                                  # silent: no exo trigger
        e = _pool(H_tx)                                  # [B,d]
        a, b = self.to_ab(e).chunk(2, dim=-1)
        g = gate.view(-1, 1, 1) if gate is not None else 1.0
        return H_ts + g * (torch.tanh(a).unsqueeze(1) * H_ts + b.unsqueeze(1))


class ResidualScaleFusion(nn.Module):
    """R: gentle scale modulation of the residual (noise) stream.

    The residual is high-frequency noise with little text signal, so text only
    *scales* it (can damp/enhance volatility) rather than adding structure.
    """

    def __init__(self, d_model: int):
        super().__init__()
        self.scale = nn.Linear(d_model, d_model)
        nn.init.normal_(self.scale.weight, std=0.02)
        nn.init.zeros_(self.scale.bias)

    def forward(self, H_ts: torch.Tensor, H_tx: Optional[torch.Tensor]) -> torch.Tensor:
        if H_tx is None:
            return H_ts
        e = _pool(H_tx)
        s = torch.tanh(self.scale(e))
        return H_ts * (1.0 + s.unsqueeze(1))


# ---------------------------------------------------------------------------
# Cross-path mixing
# ---------------------------------------------------------------------------

class SparseMoEMixer(nn.Module):
    """Top-k gated experts over path representations.

    Router sees *time-series* pooled features only (not text), so text quality
    cannot hijack routing.  Path C can be hard-masked when ``c_trigger`` is 0.
    """

    def __init__(
        self,
        d_model: int,
        n_experts: int = 4,
        top_k: int = 2,
        hidden: int = 64,
    ):
        super().__init__()
        self.n_experts = int(n_experts)
        self.top_k = int(min(top_k, n_experts))
        self.experts = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Linear(d_model, hidden),
                    nn.GELU(),
                    nn.Linear(hidden, d_model),
                )
                for _ in range(n_experts)
            ]
        )
        # Small-random init the output layer of every expert (NOT zero).
        # A zero-init output layer would deadlock the whole MoE branch:
        #   expert W2=0 → mixed≈0 → head's mixed-column gradient≈0
        #   head mixed-column=0 → d loss/d mixed≈0 → expert W2 gradient≈0
        # both stay at 0 forever.  The zero-init "start at persistence"
        # guarantee is already provided by the zero-init *head*, so the expert
        # output layer must be non-zero for the 4-path + MoE branch to ever
        # receive gradient.  Keep it small (std=0.02) so the MoE contribution
        # stays gentle early on.
        for e in self.experts:
            nn.init.normal_(e[-1].weight, std=0.02)
            nn.init.zeros_(e[-1].bias)
        # router input: concat of 4 pooled TS reps → logits
        self.router = nn.Linear(d_model * n_experts, n_experts)
        self.norm = nn.LayerNorm(d_model)

    def forward(
        self,
        H: Dict[str, torch.Tensor],
        c_trigger: Optional[torch.Tensor] = None,
        H_router: Optional[Dict[str, torch.Tensor]] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        H:        dict T/S/C/R each [B,L,d]  (fused; consumed by experts)
        H_router: dict T/S/C/R each [B,L,d]  (time-series only; router reads
                  these, NOT the fused H — text must not hijack routing)
        c_trigger: [B] in {0,1} — hard mask expert C when 0
        returns (mixed [B,L,d], gates [B,4], L_balance [])
        """
        keys = COMPONENTS
        B, L, d = H[keys[0]].shape
        route_src = H_router if H_router is not None else H
        pools = [_pool(route_src[k]) for k in keys]         # each [B,d]
        raw_logits = self.router(torch.cat(pools, dim=-1))  # [B,4]

        # full-softmax routing prob (BEFORE masking) — carries gradient to all
        # experts, so load-balancing can revive a dead expert (top-k gates are
        # hard-thresholded and give no gradient to unselected experts).
        prob_full = F.softmax(raw_logits, dim=-1).mean(dim=0)   # [E]

        logits = raw_logits.clone()
        if c_trigger is not None:
            c_idx = keys.index("C")
            logits[:, c_idx] = torch.where(
                c_trigger > 0, logits[:, c_idx],
                logits.new_full((B,), -1e4),
            )

        # noisy top-k during train
        if self.training:
            logits = logits + 1e-2 * torch.randn_like(logits)

        topv, topi = torch.topk(logits, k=self.top_k, dim=-1)   # [B,k]
        gates = torch.zeros_like(logits)
        soft = F.softmax(topv, dim=-1)
        gates.scatter_(1, topi, soft)

        # ---- load-balance auxiliary (Switch-style, *differentiable*) ----
        # The classic form L = E·Σ f_i·P_i uses the HARD usage fraction f_i.
        # A dead expert has f_i = 0 → zero gradient → it can never revive under
        # top-k hard gating.  Use the full-softmax prob P_i (already carries
        # gradient to ALL experts) so an expert that fell out of the top-k is
        # still pulled back toward uniform.  L ∈ [1, E]; min at uniform P.
        L_balance = (prob_full ** 2).sum() * self.n_experts

        mixed = H[keys[0]].new_zeros(B, L, d)
        for i, k in enumerate(keys):
            g = gates[:, i].view(B, 1, 1)
            if float(g.detach().sum()) < 1e-8:
                continue
            mixed = mixed + g * self.experts[i](H[k])
        return self.norm(mixed), gates, L_balance
