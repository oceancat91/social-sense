"""DS-SAA §2.6.2–2.6.5 — component-anchored dual-source attention + residual fusion.

Builds on ``layers.ds_saa_semantic`` (§2.6.1):
  endogenous = historical-window Template (A)
  exogenous  = dataset ``fact`` column

Pipeline per component i ∈ {T,S,C,R}
------------------------------------
  1. Build time-series anchor Query Q_i from component-specific features
  2. Endo: sliding-window cross-attn over K/V expanded from H_i^endo
  3. Exo : sparse event-anchored attention over dated fact documents
  4. Fuse A = λ_endo A_endo + λ_exo A_exo
  5. Residual enhance H_fusion = H_time + g · A   (§2.6.3)
  6. Quality gate g from heuristic q (§2.6.4)
  7. Optional L_orth (§2.6.3) + three-stage freeze helpers (§2.6.5)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

import torch
import torch.nn as nn
import torch.nn.functional as F

from layers.ds_saa_semantic import (
    COMPONENTS,
    DualSourceSemanticSpace,
    ExoEventBatch,
    TextSemanticBundle,
    encode_exo_events,
)
from layers.srsa import (
    COMP2IDX,
    SRSAExoAttention,
    SemanticRouteHead,
    consist_kl,
    mask_events_by_route,
    route_ce_loss,
)

# trend largest window, jump smallest (relative to seq_len via clamp)
DEFAULT_WIN = {"T": 4, "S": 3, "R": 2, "C": 1}
# prior preference: T leans endo, C leans exo
DEFAULT_LAMBDA_ENDO = {"T": 0.7, "S": 0.55, "C": 0.35, "R": 0.5}


# ---------------------------------------------------------------------------
# §2.6.2.1  Query builders
# ---------------------------------------------------------------------------

class ComponentQueryBuilder(nn.Module):
    """Construct Q_i ∈ R^{B×L×d} from time-series component features."""

    def __init__(self, d_model: int, n_vars: int = 1, mamba_d: int = 64):
        super().__init__()
        self.d_model = d_model
        self.n_vars = n_vars
        # T: [slope, d2] per var → 2*C
        self.proj_T = nn.Linear(2 * n_vars, d_model)
        # S: [S, |a| summary broadcast, phase proxy] — use S and ΔS (2*C)
        self.proj_S = nn.Linear(2 * n_vars, d_model)
        # C: [mean-shift, var-shift] (2*C)
        self.proj_C = nn.Linear(2 * n_vars, d_model)
        # R: mamba hidden or raw R projected
        self.proj_R = nn.Linear(max(n_vars, mamba_d), d_model)
        self.mamba_d = mamba_d

    @staticmethod
    def _pad_left(x: torch.Tensor, n: int) -> torch.Tensor:
        if n <= 0:
            return x
        return F.pad(x, (0, 0, n, 0))

    def query_T(self, T: torch.Tensor) -> torch.Tensor:
        """T: [B,L,C] → Q [B,L,d] from slope + second difference."""
        d1 = T[:, 1:] - T[:, :-1]
        d2 = d1[:, 1:] - d1[:, :-1]
        d1 = self._pad_left(d1, 1)
        d2 = self._pad_left(d2, 2)
        feat = torch.cat([d1, d2], dim=-1)
        return self.proj_T(feat)

    def query_S(self, S: torch.Tensor) -> torch.Tensor:
        """S: [B,L,C] → phase/amplitude proxy via S and ΔS."""
        dS = S[:, 1:] - S[:, :-1]
        dS = self._pad_left(dS, 1)
        return self.proj_S(torch.cat([S, dS], dim=-1))

    def query_C(self, r2: torch.Tensor, win: int = 3) -> torch.Tensor:
        """r2: [B,L,C] → sliding mean-shift & variance-shift."""
        B, L, C = r2.shape
        w = max(2, min(win, L // 2 if L >= 4 else L))
        # causal rolling via cumsum
        csum = torch.cumsum(r2, dim=1)
        csum2 = torch.cumsum(r2 * r2, dim=1)
        idx = torch.arange(L, device=r2.device)
        left = (idx - w).clamp(min=-1)
        # mean over [t-w+1, t]
        def roll_mean(cs):
            # cs[:,t] - cs[:,t-w]  ; for t-w<0 use 0
            prev = torch.zeros_like(cs)
            prev[:, w:] = cs[:, :-w]
            n = (idx + 1).clamp(max=w).float().view(1, L, 1)
            return (cs - prev) / n

        mu = roll_mean(csum)
        m2 = roll_mean(csum2)
        var = (m2 - mu * mu).clamp_min(0.0)
        dmu = mu[:, 1:] - mu[:, :-1]
        dvar = var[:, 1:] - var[:, :-1]
        dmu = self._pad_left(dmu, 1)
        dvar = self._pad_left(dvar, 1)
        return self.proj_C(torch.cat([dmu, dvar], dim=-1))

    def query_R(self, R: torch.Tensor, R_hidden: Optional[torch.Tensor] = None
                ) -> torch.Tensor:
        """R [B,L,C] or Mamba hidden [B,L,Dm] → Q."""
        if R_hidden is not None:
            h = R_hidden
            if h.size(-1) != self.proj_R.in_features:
                # adaptive pad/truncate
                if h.size(-1) < self.proj_R.in_features:
                    h = F.pad(h, (0, self.proj_R.in_features - h.size(-1)))
                else:
                    h = h[..., : self.proj_R.in_features]
            return self.proj_R(h)
        h = R
        if h.size(-1) < self.proj_R.in_features:
            h = F.pad(h, (0, self.proj_R.in_features - h.size(-1)))
        else:
            h = h[..., : self.proj_R.in_features]
        return self.proj_R(h)

    def forward(
        self,
        T: torch.Tensor,
        S: torch.Tensor,
        r2: torch.Tensor,
        R: torch.Tensor,
        R_hidden: Optional[torch.Tensor] = None,
    ) -> Dict[str, torch.Tensor]:
        return {
            "T": self.query_T(T),
            "S": self.query_S(S),
            "C": self.query_C(r2),
            "R": self.query_R(R, R_hidden),
        }


# ---------------------------------------------------------------------------
# §2.6.2.2–3  Attention ops
# ---------------------------------------------------------------------------

def sliding_window_mask(L: int, w: int, device, dtype=torch.float32) -> torch.Tensor:
    """M_win [L,L]: 1 if |i-j| <= w."""
    idx = torch.arange(L, device=device)
    dist = (idx[:, None] - idx[None, :]).abs()
    return (dist <= w).to(dtype)


class EndoWindowCrossAttention(nn.Module):
    """Sliding-window cross-attn: Q_time × K/V from endogenous semantic vector."""

    def __init__(self, d_model: int, seq_len: int, win: int = 3):
        super().__init__()
        self.d_model = d_model
        self.seq_len = seq_len
        self.win = int(win)
        self.W_k = nn.Linear(d_model, d_model, bias=False)
        self.W_v = nn.Linear(d_model, d_model, bias=False)
        self.pos = nn.Parameter(torch.zeros(1, seq_len, d_model))
        nn.init.normal_(self.pos, std=0.02)

    def forward(self, Q: torch.Tensor, H_endo: torch.Tensor,
                quality: Optional[torch.Tensor] = None) -> torch.Tensor:
        """
        Q: [B,L,d], H_endo: [B,d] pooled endogenous embedding.
        quality: [B] or [B,L] gate in [0,1].
        """
        B, L, d = Q.shape
        # expand endo token along time with positional modulation
        tok = H_endo.unsqueeze(1) + self.pos[:, :L, :]
        K = self.W_k(tok)
        V = self.W_v(tok)
        scale = 1.0 / math.sqrt(d)
        logits = torch.matmul(Q, K.transpose(-1, -2)) * scale  # [B,L,L]
        M = sliding_window_mask(L, self.win, Q.device, logits.dtype)
        logits = logits.masked_fill(M.unsqueeze(0) == 0, float("-inf"))
        attn = torch.softmax(logits, dim=-1)
        attn = torch.nan_to_num(attn, nan=0.0)
        if quality is not None:
            if quality.dim() == 1:
                quality = quality.view(B, 1, 1)
            elif quality.dim() == 2:
                quality = quality.unsqueeze(-1)
            attn = attn * quality
        return torch.matmul(attn, V)


class ExoSparseEventAttention(nn.Module):
    """Time-anchored sparse attention over exogenous events (§2.6.2.3).

    A_{b,t} = Σ_e α_{b,e} V_{b,e}  if pos[b,e]==t else 0,
    with α = softmax_e ( ⟨Q_{b,t}, V_{b,e}⟩ / √d ) over events at that t
    (practically: gather events, score vs Q at their anchored step).
    """

    def __init__(self, d_model: int):
        super().__init__()
        self.d_model = d_model
        self.W_q = nn.Linear(d_model, d_model, bias=False)

    def forward(
        self,
        Q: torch.Tensor,
        events: ExoEventBatch,
        gate: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Q: [B,L,d]
        events.V [B,E,d], pos [B,E], mask [B,E], quality [B,E]
        gate: optional [B] extra sample gate (e.g. mask_exo)
        returns A_exo [B,L,d]
        """
        B, L, d = Q.shape
        E = events.V.size(1)
        A = Q.new_zeros(B, L, d)
        if E == 0 or events.mask.sum() < 1:
            return A

        Qp = self.W_q(Q)  # [B,L,d]
        scale = 1.0 / math.sqrt(d)
        # score each event against Q at its anchored position
        # gather Q_e: [B,E,d]
        pos = events.pos.clamp(0, L - 1)
        b_idx = torch.arange(B, device=Q.device).unsqueeze(1).expand(B, E)
        Q_e = Qp[b_idx, pos]  # [B,E,d]
        score = (Q_e * events.V).sum(dim=-1) * scale  # [B,E]
        score = score.masked_fill(events.mask == 0, float("-inf"))
        # softmax over events *per sample* (sparse set)
        alpha = torch.softmax(score, dim=-1)
        alpha = torch.nan_to_num(alpha, nan=0.0)
        alpha = alpha * events.mask * events.quality
        if gate is not None:
            alpha = alpha * gate.unsqueeze(-1)

        # scatter α_e * V_e onto time index pos
        contrib = alpha.unsqueeze(-1) * events.V  # [B,E,d]
        A = A.scatter_add(1, pos.unsqueeze(-1).expand(B, E, d), contrib)
        return A


# ---------------------------------------------------------------------------
# §2.6.3–2.6.4  Fusion, residual, quality, orth loss
# ---------------------------------------------------------------------------

class DualSourceFusion(nn.Module):
    """A = λ_endo A_endo + λ_exo A_exo with learnable per-component weights."""

    def __init__(self, init_endo: float = 0.5):
        super().__init__()
        # unconstrained logits; sigmoid → (0,1), renormalised to sum 1
        logit = math.log(max(init_endo, 1e-3) / max(1 - init_endo, 1e-3))
        self.lambda_endo_logit = nn.Parameter(torch.tensor(logit))

    def forward(self, A_endo: torch.Tensor, A_exo: torch.Tensor):
        le = torch.sigmoid(self.lambda_endo_logit)
        lx = 1.0 - le
        return le * A_endo + lx * A_exo, le, lx


def orth_loss(H_time: torch.Tensor, A: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    """Frobenius of cosine similarity between pooled time feat and text enhance.

    H_time, A: [B,L,d] or [B,d]
    """
    if H_time.dim() == 3:
        Ht = H_time.mean(dim=1)
    else:
        Ht = H_time
    if A.dim() == 3:
        At = A.mean(dim=1)
    else:
        At = A
    Ht = F.normalize(Ht, dim=-1, eps=eps)
    At = F.normalize(At, dim=-1, eps=eps)
    cos = (Ht * At).sum(dim=-1)  # [B]
    return (cos ** 2).mean()


class QualityGate(nn.Module):
    """g = σ(w_q · q + b_q); q=0 → g≈0 (transparent)."""

    def __init__(self):
        super().__init__()
        self.w_q = nn.Parameter(torch.tensor(4.0))
        self.b_q = nn.Parameter(torch.tensor(-2.0))

    def forward(self, q: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.w_q * q + self.b_q)


def heuristic_endo_quality(H_endo: torch.Tensor) -> torch.Tensor:
    """[B] quality from embedding energy (template always present → near 1)."""
    n = H_endo.norm(dim=-1)
    return (n / n.detach().mean().clamp_min(1e-3)).clamp(0.0, 1.0)


# ---------------------------------------------------------------------------
# Full DS-SAA block (§2.6.2–2.6.5)
# ---------------------------------------------------------------------------

@dataclass
class DSSAAOutput:
    H_fusion: Dict[str, torch.Tensor]   # [B,L,d] enhanced time features
    A: Dict[str, torch.Tensor]
    A_endo: Dict[str, torch.Tensor]
    A_exo: Dict[str, torch.Tensor]
    gates: Dict[str, torch.Tensor]
    lambdas: Dict[str, Tuple[torch.Tensor, torch.Tensor]]
    L_orth: torch.Tensor
    L_route: Optional[torch.Tensor] = None
    exo_routed: Optional[Dict[str, ExoEventBatch]] = None
    route_probs: Optional[torch.Tensor] = None  # [B,E,4]
    fact_pool: Optional[torch.Tensor] = None    # [B, d_enc] raw full-doc pool
    H_exo_sem: Optional[Dict[str, torch.Tensor]] = None  # [B,d] fact full-doc component semantics


class ComponentDSSAA(nn.Module):
    """One-component DS-SAA: attn + residual + quality gate."""

    def __init__(self, d_model: int, seq_len: int, component: str,
                 win: Optional[int] = None, init_lambda_endo: float = 0.5,
                 use_srsa: bool = True, tau_route: float = 0.1):
        super().__init__()
        self.component = component
        self.use_srsa = bool(use_srsa)
        w = DEFAULT_WIN.get(component, 2) if win is None else win
        self.endo_attn = EndoWindowCrossAttention(d_model, seq_len, win=w)
        if self.use_srsa:
            self.exo_attn = SRSAExoAttention(d_model, tau_route=tau_route)
        else:
            self.exo_attn = ExoSparseEventAttention(d_model)
        self.fuse = DualSourceFusion(init_endo=init_lambda_endo)
        self.gate = QualityGate()
        self.out_norm = nn.LayerNorm(d_model)

    def forward(
        self,
        H_time: torch.Tensor,
        Q: torch.Tensor,
        H_endo: torch.Tensor,
        exo_events: ExoEventBatch,
        q_endo: torch.Tensor,
        q_exo: torch.Tensor,
        mask_exo: Optional[torch.Tensor] = None,
        p_comp: Optional[torch.Tensor] = None,
        H_exo_lin: Optional[torch.Tensor] = None,
    ):
        """
        H_time / Q: [B,L,d]
        H_endo: [B,d]
        q_endo: [B], q_exo: [B] (sample-level aggregate quality)
        p_comp: [B,E] SRSA route prob for this component (required if use_srsa)
        H_exo_lin: [B,d] global linear anchor from the fact *full-document*
            pool (not the sparse events).  The ridge probe showed this pooled
            vector carries a strong linear signal that sparse event attention
            alone discards; adding it as a parallel anchor keeps that signal
            in the graph without going through the fragile cross-attention.
        """
        g_endo = self.gate(q_endo)
        g_exo = self.gate(q_exo)
        A_endo = self.endo_attn(Q, H_endo, quality=g_endo)
        g_ex = g_exo if mask_exo is None else g_exo * mask_exo
        if self.use_srsa:
            if p_comp is None:
                p_comp = exo_events.mask  # fallback: no semantic prior
            A_exo = self.exo_attn(Q, exo_events, p_comp=p_comp, gate=g_ex)
        else:
            A_exo = self.exo_attn(Q, exo_events, gate=g_ex)
        # global semantic shortcut: broadcast the full-document pool along time
        if H_exo_lin is not None:
            A_exo = A_exo + H_exo_lin.unsqueeze(1)
        A, le, lx = self.fuse(A_endo, A_exo)
        # separate gates: endo must not force-open exo (and vice versa)
        H_fusion = self.out_norm(
            H_time
            + g_endo.view(-1, 1, 1) * le * A_endo
            + g_ex.view(-1, 1, 1) * lx * A_exo
        )
        g_report = torch.maximum(g_endo, g_exo)
        return H_fusion, A, A_endo, A_exo, g_report, (le, lx)


class DSSAAModule(nn.Module):
    """Full dual-source semantic anchoring attention over four components.

    Embedding position (§2.6.5): between component feature extractors and
    prediction heads.  Call ``enhance(...)`` with time features + text.
    """

    def __init__(
        self,
        d_model: int,
        seq_len: int,
        n_vars: int = 1,
        mamba_d: int = 64,
        semantic: Optional[DualSourceSemanticSpace] = None,
        max_events: int = 8,
        use_srsa: bool = False,
        tau_route: float = 0.1,
        t_endo: bool = True,
        t_exo: bool = False,
        t_time_only: bool = False,
        use_exo_lin: bool = False,
    ):
        super().__init__()
        self.d_model = d_model
        self.seq_len = seq_len
        self.n_vars = n_vars
        self.max_events = max_events
        self.semantic = semantic
        self.use_srsa = bool(use_srsa)
        self.tau_route = float(tau_route)
        # Full-document global linear anchor (parallel to sparse events).
        # Off by default: the probe's linear signal is best served by a direct
        # text→delta head in the model, not by bending the attention residual.
        self.use_exo_lin = bool(use_exo_lin)
        # Endogenous window text into T. This is the path behind the Security
        # 61 / SocialGood 0.756 result. Set False to ablate it.
        self.t_endo = bool(t_endo)
        # Exo docs routed to T are rare in training (Agriculture 5% train vs
        # 65% test) → the T head never learns them and shifts at test time.
        # Default: T fusion is endogenous-only; exo stays on S/R and C.
        self.t_exo = bool(t_exo)
        # Diagnostic: H_T = out_norm(time_proj(T)) only (no text at all).
        # Tests whether the "text T gain" is really the numeric level path.
        self.t_time_only = bool(t_time_only)
        # semantic subspace → per-component text vector (DS-SAA core: the
        # component instructions decompose text into T/S/C/R meaning).  The
        # over-parameterised attention blocks are gone — the four fusion heads
        # in rep_fusion.py now inject these vectors with *different* mechanisms
        # (T concat-tune, S FiLM, C event-jump, R scale).
        if semantic is not None:
            self.endo_adapt = nn.ModuleDict({
                c: nn.Linear(semantic.d_out, d_model, bias=False) for c in COMPONENTS
            })
            self.exo_proj = nn.ModuleDict({
                c: nn.Linear(semantic.encoder.d_model, d_model, bias=False)
                for c in COMPONENTS
            })
            # project the full-doc component semantics to d_model for the
            # text→delta heads (identity-equivalent when d_out == d_model)
            self.exo_lin = nn.ModuleDict({
                c: nn.Linear(semantic.d_out, d_model, bias=False) for c in COMPONENTS
            })
        else:
            self.endo_adapt = None
            self.exo_proj = None
            self.exo_lin = None
        self.exo_proj_shared = None

    # ----- §2.6.5 freeze helpers -----
    def freeze_text_branch(self, freeze: bool = True):
        for p in self.parameters():
            p.requires_grad = not freeze
        # keep time_proj trainable? stage-1 freezes ALL text; time_proj is DS-SAA
        if freeze:
            for p in self.parameters():
                p.requires_grad = False

    def freeze_time_backbone_external(self, modules: Sequence[nn.Module], freeze: bool = True):
        for m in modules:
            for p in m.parameters():
                p.requires_grad = not freeze

    def ds_saa_parameters(self):
        return [p for p in self.parameters() if p.requires_grad]

    def enhance(
        self,
        T: torch.Tensor,
        S: torch.Tensor,
        r2: torch.Tensor,
        R: torch.Tensor,
        H_endo: Dict[str, torch.Tensor],
        exo_by_comp: Dict[str, ExoEventBatch],
        mask_exo: torch.Tensor,
        R_hidden: Optional[torch.Tensor] = None,
        zero_endo: bool = False,
        zero_exo: bool = False,
        H_ts: Optional[Dict[str, torch.Tensor]] = None,
        H_exo: Optional[Dict[str, torch.Tensor]] = None,
    ) -> DSSAAOutput:
        """Run §2.6.2–2.6.4 given precomputed text tensors.

        If ``use_srsa`` and ``exo_by_comp['ALL']`` is present, apply semantic
        pre-routing on the shared pool then per-component numeric verification.

        ``H_ts`` (optional): pre-encoded per-path time-series representations
        ``[B,L,d]``.  When provided they replace BOTH the hand-crafted query
        builder and the raw ``time_proj`` anchor, so text attention is anchored
        on the *learned* four-path representations (Mamba/PatchCNN/…) instead of
        low-order differenced statistics (slope / Δ² / rolling mean-var).  Falls
        back to the legacy ComponentQueryBuilder when omitted.

        ``H_exo`` (optional): full-document exogenous pool ``[B,d]`` per
        component.  (Unused in the vector path; kept for API compatibility.)
        """
        B = T.size(0)
        H_tx: Dict[str, torch.Tensor] = {}
        gates: Dict[str, torch.Tensor] = {}
        exo_routed: Dict[str, ExoEventBatch] = {}
        H_exo_sem: Dict[str, torch.Tensor] = {}
        for c in COMPONENTS:
            # ---- endogenous semantic (component template) → [B,d] ----
            He = H_endo[c]
            if self.endo_adapt is not None:
                He = self.endo_adapt[c](He)
            if (c == "T" and (not self.t_endo or self.t_time_only)) or zero_endo:
                He = torch.zeros_like(He)
            # ---- exogenous event pool → [B,d] ----
            ev = exo_by_comp.get(c)
            exo_pool = self._pool_events(ev, B, He)
            # ---- exogenous full-doc component semantics → [B,d] ----
            # (the *un-pooled* fact full text with component instruction; this
            # is the feature the ridge probe proved carries signal, and it is
            # kept separate from the sparse event pool for the text→delta heads)
            if H_exo is not None and H_exo.get(c) is not None:
                hx = H_exo[c]
                if self.exo_lin is not None:
                    hx = self.exo_lin[c](hx)
                H_exo_sem[c] = hx
            else:
                H_exo_sem[c] = He.new_zeros(B, self.d_model)
            # per-component source routing (different roles):
            #   T endo-only (trend from template stats), C exo-only (jump from
            #   external events), S/R both.
            use_exo = (c != "T") and (not zero_exo)
            g_exo = mask_exo if use_exo else T.new_zeros(B)
            if c == "C" and not self.t_endo:
                He = torch.zeros_like(He)   # jump is exo-driven
            H_tx[c] = He + exo_pool * g_exo.unsqueeze(-1)
            gates[c] = torch.clamp(g_exo, 0.0, 1.0)
            if c == "C" and ev is not None:
                exo_routed[c] = ev

        c_trigger = self._c_trigger(exo_by_comp, B, T)
        return DSSAAOutput(
            H_fusion=H_tx, A={}, A_endo={}, A_exo={},
            gates=gates, lambdas={},
            L_orth=T.new_zeros(()),
            L_route=None,
            exo_routed=exo_routed or None,
            route_probs=None,
            H_exo_sem=H_exo_sem,
        )

    def _pool_events(self, ev: Optional[ExoEventBatch], B: int,
                     ref: torch.Tensor) -> torch.Tensor:
        """Quality-weighted pool of a component's exo events → ``[B,d]``."""
        if ev is None or ev.V.size(1) == 0:
            return ref.new_zeros(B, self.d_model)
        w = ev.quality * ev.mask                      # [B,E]
        denom = w.sum(-1, keepdim=True).clamp_min(1.0)
        return (ev.V * w.unsqueeze(-1)).sum(-2) / denom   # [B,d]

    def _c_trigger(self, exo_by_comp: Dict[str, ExoEventBatch], B: int,
                   ref: torch.Tensor) -> torch.Tensor:
        """[B] 0/1 — whether any C exo event fires (opens the jump path)."""
        ev = exo_by_comp.get("C")
        if ev is None:
            return ref.new_zeros(B)
        return ((ev.mask * ev.quality).sum(-1) > 0).to(ref.dtype)

    def forward_from_raw(
        self,
        T: torch.Tensor,
        S: torch.Tensor,
        r2: torch.Tensor,
        R: torch.Tensor,
        windows: Sequence,
        facts: Sequence[Optional[str]],
        window_dates: Optional[Sequence[Sequence[Optional[str]]]] = None,
        R_hidden: Optional[torch.Tensor] = None,
        device: Optional[torch.device] = None,
        H_ts: Optional[Dict[str, torch.Tensor]] = None,
    ) -> DSSAAOutput:
        """Encode text via §2.6.1 semantic space then enhance."""
        if self.semantic is None:
            raise RuntimeError("DSSAAModule.semantic is None; pass DualSourceSemanticSpace")
        if device is None:
            device = T.device
        bundle: TextSemanticBundle = self.semantic(
            windows, facts, device=device, window_dates=window_dates)
        exo_by_comp = {}
        for c in COMPONENTS:
            # encode events in encoder width then project
            ev = encode_exo_events(
                self.semantic.encoder, facts, c, self.seq_len,
                window_dates=window_dates, max_events=self.max_events,
                proj=None, device=device,
                pred_len=int(getattr(self.semantic, "pred_len", 0)),
            )
            if self.exo_proj is not None:
                ev = ExoEventBatch(
                    V=self.exo_proj[c](ev.V),
                    pos=ev.pos, mask=ev.mask, quality=ev.quality,
                    route_label=ev.route_label, target=ev.target,
                    intensity=ev.intensity, duration=ev.duration,
                    shape=ev.shape, confidence=ev.confidence,
                )
            elif self.semantic.d_out != self.d_model:
                raise RuntimeError("exo dim mismatch: set proj_dim=d_model on semantic")
            exo_by_comp[c] = ev
        # (SRSA routing + shared ALL pool removed: the per-component event
        # vectors are consumed directly by the four differentiated fusion heads.)
        out = self.enhance(
            T, S, r2, R, bundle.H_endo, exo_by_comp, bundle.mask_exo,
            R_hidden=R_hidden, H_ts=H_ts, H_exo=bundle.H_exo,
        )
        # raw full-document pool (no component instruction): the linear-probe
        # feature that carries the global text→future signal directly
        out.fact_pool = self._encode_fact_pool(facts, device=device)
        return out

    def _encode_fact_pool(self, facts: Sequence, device=None) -> Optional[torch.Tensor]:
        """Raw full-document GPT2 pool ``[B, d_enc]`` (empty fact → 0).

        This is exactly the ridge-probe feature: the *un-instructed* pooled
        embedding of the aggregated fact text.  It feeds a direct linear
        text→delta head in the model, bypassing DS-SAA's attention so the
        global linear signal is not diluted by cross-attention noise.
        """
        if self.semantic is None:
            return None
        if device is None:
            device = next(self.semantic.encoder.llm.parameters()).device
        B = len(facts)
        d = self.semantic.encoder.d_model
        pool = torch.zeros(B, d, device=device)
        nz = [i for i, f in enumerate(facts) if f and str(f).strip()]
        if nz:
            emb = self.semantic.encoder.encode(
                [str(facts[i]) for i in nz], device=device)
            pool[nz] = emb.to(pool.dtype)
        return pool


# ---------------------------------------------------------------------------
# §2.6.5 prediction heads consuming enhanced features
# ---------------------------------------------------------------------------

class EnhancedTrendHead(nn.Module):
    """EMA Δ features (+ optional DS-SAA fusion) → pred_len deltas."""

    def __init__(self, seq_len: int, pred_len: int, d_model: int, n_vars: int = 1):
        super().__init__()
        self.pred_len = pred_len
        self.n_vars = n_vars
        self.fuse = nn.Linear(d_model + (seq_len - 1), pred_len)

    def forward(self, dT: torch.Tensor, H_T: Optional[torch.Tensor] = None):
        """dT: [B,L-1,C] ; H_T: [B,L,d] → delta [B,pred,C]"""
        B, Lm1, C = dT.shape
        # pool H over time; concat with flattened per-var dT
        outs = []
        for c in range(C):
            x = dT[:, :, c]  # [B,L-1]
            if H_T is not None:
                h = H_T.mean(dim=1)  # [B,d]
                x = torch.cat([x, h], dim=-1)
            outs.append(self.fuse(x))
        return torch.stack(outs, dim=-1)  # [B,pred,C]


def stage_train_flags(stage: int) -> Dict[str, bool]:
    """§2.6.5 three-stage schedule flags.

    stage 1: train TS backbone only (freeze DS-SAA)
    stage 2: freeze backbone, train DS-SAA on residual of backbone
    stage 3: e2e fine-tune both + L_orth
    """
    if stage == 1:
        return {"train_backbone": True, "train_dssaa": False, "use_orth": False,
                "fit_residual": False}
    if stage == 2:
        return {"train_backbone": False, "train_dssaa": True, "use_orth": True,
                "fit_residual": True}
    if stage == 3:
        return {"train_backbone": True, "train_dssaa": True, "use_orth": True,
                "fit_residual": False}
    raise ValueError(f"stage must be 1/2/3, got {stage}")
