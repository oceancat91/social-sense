"""DS-SAA §2.6.1 — Dual-source component-level semantic spaces.

Definitions (project convention)
--------------------------------
* Endogenous text  : Template rendered from the *historical* window statistics
                     only (option A).  No future-window / oracle stats.
* Exogenous text   : the dataset ``fact`` column (external retrieved documents).

Both sources are mapped into four independent semantic subspaces
``{T, S, C, R}`` via zero-shot component instructions + a frozen LLM encoder,
so later attention stays inside the matching component space.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Union

import numpy as np
import torch
import torch.nn as nn

from utils.text_prompt import (
    NO_TEXT_TOKEN,
    build_calendar_block,
    build_event_date_tag,
    build_numeric_block,
    build_numeric_block_with_calendar,
    clean_text_block,
    is_empty_text,
    numeric_stats,
    split_documents,
)

_DATE_HEAD = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*:\s*(.*)$", re.S)

COMPONENTS = ("T", "S", "C", "R")

# Zero-shot instructions: force the encoder to attend to one physical meaning.
COMPONENT_INSTRUCTIONS = {
    "T": (
        "[Semantic subspace: TREND] Focus only on long-horizon baseline direction, "
        "level shifts of the mean path, and sustained drift. Ignore short spikes, "
        "calendar cycles, and idiosyncratic noise."
    ),
    "S": (
        "[Semantic subspace: SEASONAL] Focus only on periodic / calendar / repeating "
        "patterns (holiday-like cycles, phase and amplitude of seasonality). Ignore "
        "one-off shocks and residual chatter."
    ),
    "C": (
        "[Semantic subspace: JUMP/CHANGEPOINT] Focus only on abrupt structural breaks, "
        "regime switches, announcements, and discontinuous level jumps. Ignore smooth "
        "trend and regular seasonality."
    ),
    "R": (
        "[Semantic subspace: RESIDUAL FLUCTUATION] Focus only on short-term volatility, "
        "irregular perturbations, and leftover noise after trend/season/jump. Ignore "
        "baseline drift and periodic structure."
    ),
}

# Endogenous templates emphasise the stats that match each component (still A-only).
_ENDO_COMPONENT_TEMPLATE = {
    "T": (
        "Trend view of the observed window: start={start_value:.2f}, end={end_value:.2f}, "
        "linear slope={trend:.2f} per step, complete series={ot_values}."
    ),
    "S": (
        "Seasonal / cyclic view of the observed window: series={ot_values}, "
        "std={std:.2f}, start={start_value:.2f}, end={end_value:.2f}. "
        "Interpret repeating structure consistent with these window statistics only."
    ),
    "C": (
        "Jump / break view of the observed window: maximum absolute step change="
        "{max_delta:.2f} at local step {max_pos}, series={ot_values}."
    ),
    "R": (
        "Residual-volatility view of the observed window: std={std:.2f}, "
        "max step={max_delta:.2f}, series={ot_values}."
    ),
}


def build_endo_raw(window: Union[np.ndarray, torch.Tensor],
                   dates: Optional[Sequence[Optional[str]]] = None,
                   pred_len: int = 0,
                   calendar_mode: str = "short") -> str:
    """Historical-window numeric template (option A) + optional short calendar."""
    if isinstance(window, torch.Tensor):
        window = window.detach().cpu().numpy()
    w = np.asarray(window, dtype=float)
    if dates is None or calendar_mode == "off":
        return build_numeric_block(w)
    return build_numeric_block_with_calendar(
        w, dates=dates, pred_len=pred_len, mode=calendar_mode)


# "values": raw-series template (per-window fingerprint; memorisable)
# "regime": quantised qualitative descriptors only (finite regime vocabulary)
ENDO_MODE = "values"


def _q(x: float, edges: Sequence[float], labels: Sequence[str]) -> str:
    for e, lab in zip(edges, labels):
        if x < e:
            return lab
    return labels[-1]


def build_endo_regime_body(v: np.ndarray, component: str) -> str:
    """Scale-free regime descriptors of the observed window (no raw values).

    Every descriptor is a z-score / ratio quantised into a few words, so the
    endogenous text lives in a finite vocabulary of *regimes* instead of
    acting as a unique window fingerprint.
    """
    v = np.asarray(v, dtype=float).ravel()
    n = v.size
    sd = float(np.std(v)) + 1e-8
    t = np.arange(n)
    slope = float(np.polyfit(t, v, 1)[0]) * n / sd if n > 1 else 0.0  # Δ over window in σ
    d = np.diff(v) if n > 1 else np.zeros(1)
    dsd = float(np.std(d)) + 1e-8
    last_dev = float((v[-1] - v.mean()) / sd)
    recent = float(d[-3:].mean() / dsd) if n > 3 else 0.0
    curv = float((d[-3:].mean() - d[:3].mean()) / dsd) if n > 6 else 0.0
    max_step = float(np.max(np.abs(d)) / dsd)
    max_pos = int(np.argmax(np.abs(d)) + 1)
    rough = float(np.mean(np.abs(d)) / sd)
    half = n // 2
    vol_ratio = float((np.std(d[half:]) + 1e-8) / (np.std(d[:half]) + 1e-8)) if n > 4 else 1.0
    # dominant period (acf peak) as crude seasonality strength
    if n >= 8:
        x = v - v.mean()
        acf = np.correlate(x, x, "full")[n - 1:] / (np.dot(x, x) + 1e-8)
        hi = min(n * 2 // 3, 26)
        neg = np.where(acf[1:hi] < 0)[0]
        lo = int(neg[0] + 1) if neg.size else 2  # first zero crossing
        lag = int(np.argmax(acf[lo:hi]) + lo) if hi > lo else 0
        seas = float(acf[lag]) if lag else 0.0
    else:
        lag, seas = 0, 0.0

    dir_lab = _q(slope, [-2.0, -0.7, 0.7, 2.0],
                 ["strongly falling", "falling", "flat", "rising", "strongly rising"])
    curv_lab = _q(curv, [-1.0, -0.3, 0.3, 1.0],
                  ["decelerating sharply", "decelerating", "steady", "accelerating",
                   "accelerating sharply"])
    dev_lab = _q(last_dev, [-1.5, -0.5, 0.5, 1.5],
                 ["far below", "below", "near", "above", "far above"])
    mom_lab = _q(recent, [-1.0, -0.3, 0.3, 1.0],
                 ["strong down", "down", "neutral", "up", "strong up"])
    step_lab = _q(max_step, [2.0, 3.0, 4.5], ["none", "mild", "clear", "severe"])
    pos_lab = _q(max_pos / max(n, 1), [0.34, 0.67], ["early", "middle", "late"])
    rough_lab = _q(rough, [0.15, 0.35, 0.7], ["smooth", "moderate", "rough", "very rough"])
    vol_lab = _q(vol_ratio, [0.6, 1.5], ["calming", "stable", "intensifying"])
    seas_lab = _q(seas, [0.2, 0.45, 0.7], ["weak", "moderate", "strong", "very strong"])

    if component == "T":
        return (f"Trend regime: {dir_lab}, {curv_lab}; last value {dev_lab} the window "
                f"mean; recent momentum {mom_lab}.")
    if component == "S":
        return (f"Seasonal regime: periodicity {seas_lab}"
                f"{f' (dominant lag {lag})' if lag else ''}; volatility {vol_lab}; "
                f"last value {dev_lab} the window mean.")
    if component == "C":
        return (f"Break regime: largest step {step_lab} ({pos_lab} in window); "
                f"recent momentum {mom_lab}; volatility {vol_lab}.")
    return (f"Residual regime: texture {rough_lab}; volatility {vol_lab}; "
            f"largest step {step_lab}; last value {dev_lab} the window mean.")


def _trend_shape_descriptors(v: np.ndarray) -> str:
    """Scale-free qualitative description of the trend *shape*.

    The raw-values trend template (`start/end/slope/series`) is scale-bound:
    its absolute numbers change under an amplitude drift (Security test is 11×
    train), so a frozen GPT-2 reads a different fingerprint out-of-range.  These
    descriptors are all σ-normalised (drift, curvature, momentum, position,
    direction consistency) and therefore invariant to the amplitude of the
    window — the *shape* signature stays interpretable under scale OOD and for
    the complex shapes that dominate SocialGood.
    """
    v = np.asarray(v, dtype=float).ravel()
    n = v.size
    sd = float(np.std(v)) + 1e-8
    d = np.diff(v) if n > 1 else np.zeros(1)
    dsd = float(np.std(d)) + 1e-8
    # total drift over the window in units of σ
    drift = float((v[-1] - v[0]) / sd)
    # curvature: recent steps' acceleration vs early steps (σ of diffs)
    if n > 3:
        acc = float((d[-2:].mean() - d[:2].mean()) / dsd)
        mom = float((d[-2:].mean() - d.mean()) / dsd)
    else:
        acc = mom = 0.0
    last_dev = float((v[-1] - v.mean()) / sd)
    # monotonicity: fraction of steps in the dominant direction
    sign = 1 if drift > 0 else (-1 if drift < 0 else 0)
    frac_same = (float(np.mean(np.sign(d) == sign)) if (sign != 0 and d.size > 0)
                 else 0.0)

    dir_lab = _q(drift, [-1.5, -0.5, 0.5, 1.5],
                 ["strongly falling", "falling", "flat", "rising", "strongly rising"])
    curv_lab = _q(acc, [-1.0, -0.3, 0.3, 1.0],
                  ["decelerating sharply", "decelerating", "steady",
                   "accelerating", "accelerating sharply"])
    mom_lab = _q(mom, [-1.0, -0.3, 0.3, 1.0],
                 ["strong down", "down", "neutral", "up", "strong up"])
    pos_lab = _q(last_dev, [-1.5, -0.5, 0.5, 1.5],
                 ["far below", "below", "near", "above", "far above"])
    mono_lab = _q(frac_same, [0.5, 0.75, 0.9],
                  ["mixed", "mostly monotone", "highly monotone", "monotone"])
    return (f"Trend shape (scale-free): overall {dir_lab} "
            f"(drift {drift:+.1f} std), {curv_lab}; recent momentum {mom_lab}; "
            f"last value {pos_lab} the window mean; direction consistency {mono_lab}.")


def _seasonal_shape_descriptors(v: np.ndarray) -> str:
    """Scale-free periodicity signature for the S subspace."""
    v = np.asarray(v, dtype=float).ravel()
    n = v.size
    if n < 8:
        return "Seasonal shape (scale-free): window too short to resolve periodicity."
    sd = float(np.std(v)) + 1e-8
    x = v - v.mean()
    acf = np.correlate(x, x, "full")[n - 1:] / (np.dot(x, x) + 1e-8)
    hi = min(n * 2 // 3, 26)
    neg = np.where(acf[1:hi] < 0)[0]
    lo = int(neg[0] + 1) if neg.size else 2
    lag = int(np.argmax(acf[lo:hi]) + lo) if hi > lo else 0
    seas = float(acf[lag]) if lag else 0.0
    seas_lab = _q(seas, [0.2, 0.45, 0.7],
                  ["weak", "moderate", "strong", "very strong"])
    half = n // 2
    vol_ratio = float((np.std(np.diff(v[half:])) + 1e-8)
                      / (np.std(np.diff(v[:half])) + 1e-8)) if n > 4 else 1.0
    vol_lab = _q(vol_ratio, [0.6, 1.5], ["calming", "stable", "intensifying"])
    return (f"Seasonal shape (scale-free): periodicity {seas_lab}"
            f"{f' (dominant lag {lag})' if lag else ''}; volatility {vol_lab}.")


def build_endo_component_text(window: Union[np.ndarray, torch.Tensor],
                              component: str,
                              dates: Optional[Sequence[Optional[str]]] = None,
                              pred_len: int = 0,
                              calendar_mode: str = "short") -> str:
    """Component-focused endogenous text; calendar only on S (short mode)."""
    if component not in COMPONENTS:
        raise ValueError(f"unknown component {component}")
    if isinstance(window, torch.Tensor):
        window = window.detach().cpu().numpy()
    v = np.asarray(window, dtype=float).ravel()
    if ENDO_MODE == "regime":
        body = build_endo_regime_body(v, component)
    else:
        stats = numeric_stats(v)
        body = _ENDO_COMPONENT_TEMPLATE[component].format(
            ot_values=[f"{x:.2f}" for x in v], **stats)
        # append scale-free shape descriptors so the frozen GPT-2 also reads a
        # scale-invariant signature (T: direction/curvature/momentum; S: periodicity)
        if component == "T":
            body = body + " " + _trend_shape_descriptors(v)
        elif component == "S":
            body = body + " " + _seasonal_shape_descriptors(v)
    cal = build_calendar_block(
        dates, pred_len=pred_len, focus=component, mode=calendar_mode)
    parts = [
        COMPONENT_INSTRUCTIONS[component],
        "Source: endogenous-template",
        body,
    ]
    if cal:
        parts.append(cal)
    return "\n".join(parts)


def build_exo_raw(fact: Optional[str], char_budget: int = 900) -> str:
    """Cleaned exogenous ``fact`` cell; ``NO_TEXT_TOKEN`` if empty."""
    block, _ = clean_text_block(fact, char_budget=char_budget)
    return block


def build_exo_component_text(fact: Optional[str], component: str,
                             char_budget: int = 900,
                             dates: Optional[Sequence[Optional[str]]] = None,
                             pred_len: int = 0,
                             calendar_mode: str = "short") -> str:
    """Zero-shot + fact.  No long calendar essay (preserves event semantics)."""
    if component not in COMPONENTS:
        raise ValueError(f"unknown component {component}")
    raw = build_exo_raw(fact, char_budget=char_budget)
    # optional one-line origin for S only; T/C/R stay fact-pure
    cal = build_calendar_block(
        dates, pred_len=pred_len, focus=component, mode=calendar_mode)
    parts = [
        COMPONENT_INSTRUCTIONS[component],
        "Source: exogenous-fact",
    ]
    if cal:
        parts.append(cal)
    parts.append(f"Document:\n{raw}")
    return "\n".join(parts)


def wrap_zero_shot(text: str, component: str, source: str) -> str:
    """Generic zero-shot wrap (used when raw text is already prepared)."""
    if component not in COMPONENTS:
        raise ValueError(f"unknown component {component}")
    return (
        f"{COMPONENT_INSTRUCTIONS[component]}\n"
        f"Source: {source}\n"
        f"Document:\n{text}"
    )


@dataclass
class TextSemanticBundle:
    """Component-level embeddings for one dual-source batch.

    Shapes
    ------
    H_endo / H_exo : Dict[str, Tensor] with keys T/S/C/R, each ``[B, d]``
    mask_endo      : ``[B]`` ones (template always available)
    mask_exo       : ``[B]`` 1 if fact usable else 0
    endo_raw / exo_raw : python lists of length B (debug / logging)
    """
    H_endo: Dict[str, torch.Tensor]
    H_exo: Dict[str, torch.Tensor]
    mask_endo: torch.Tensor
    mask_exo: torch.Tensor
    endo_raw: List[str]
    exo_raw: List[str]

    def as_stacked(self, source: str = "endo") -> torch.Tensor:
        """Stack components -> ``[B, 4, d]`` in order T,S,C,R."""
        H = self.H_endo if source == "endo" else self.H_exo
        return torch.stack([H[c] for c in COMPONENTS], dim=1)


class FrozenLLMPoolEncoder(nn.Module):
    """Tokenize → (input embeddings | last hidden) → masked average pool.

    Matches the project's existing CLIP text path (avg-pool over token embeds).
    LLM weights stay frozen.
    """

    def __init__(
        self,
        llm_model: nn.Module,
        tokenizer,
        max_length: int = 256,
        pool: str = "avg",
        use_hidden: bool = False,
        layers: Optional[Sequence[int]] = None,
    ):
        super().__init__()
        self.llm = llm_model
        self.tokenizer = tokenizer
        self.max_length = int(max_length)
        self.pool = pool
        self.use_hidden = bool(use_hidden)
        # contextual multi-layer pooling (mid+late layers; last layer alone is
        # anisotropic for GPT-2).  None → last_hidden_state only.
        self.layers = tuple(int(l) for l in layers) if layers else None
        if getattr(self.tokenizer, "pad_token", None) is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        for p in self.llm.parameters():
            p.requires_grad = False
        self.llm.eval()
        # infer width
        emb = self.llm.get_input_embeddings()
        self.d_model = int(emb.embedding_dim)

    @torch.no_grad()
    def encode(self, texts: Sequence[str], device: Optional[torch.device] = None
               ) -> torch.Tensor:
        if device is None:
            device = next(self.llm.parameters()).device
        tok = self.tokenizer(
            list(texts),
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.max_length,
        )
        input_ids = tok["input_ids"].to(device)
        attn = tok["attention_mask"].to(device)
        if self.use_hidden:
            if self.layers:
                out = self.llm(input_ids=input_ids, attention_mask=attn,
                               output_hidden_states=True)
                hs = out.hidden_states  # tuple len n_layer+1
                idx = [min(max(l, 0), len(hs) - 1) for l in self.layers]
                hidden = torch.stack([hs[i] for i in idx], 0).mean(0)
            else:
                out = self.llm(input_ids=input_ids, attention_mask=attn)
                hidden = out.last_hidden_state  # [B,L,d]
        else:
            hidden = self.llm.get_input_embeddings()(input_ids)
        mask = attn.unsqueeze(-1).to(dtype=hidden.dtype)
        if self.pool == "avg":
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)
        elif self.pool == "max":
            pooled = hidden.masked_fill(mask == 0, float("-inf")).max(dim=1).values
            pooled = torch.nan_to_num(pooled, nan=0.0, posinf=0.0, neginf=0.0)
        else:
            raise ValueError(f"unknown pool={self.pool}")
        return pooled


class DualSourceSemanticSpace(nn.Module):
    """§2.6.1 builder: endogenous template + exogenous fact → H^{text}_{T,S,C,R}.

    Parameters
    ----------
    encoder : FrozenLLMPoolEncoder
        Frozen text encoder shared across components (instruction prefixes
        separate the subspaces).
    proj_dim : int or None
        Optional linear projection to a shared width (one Linear per component,
        no cross-talk).  ``None`` keeps raw LLM width.
    """

    def __init__(
        self,
        encoder: FrozenLLMPoolEncoder,
        proj_dim: Optional[int] = None,
        exo_char_budget: int = 900,
        pred_len: int = 0,
        calendar_mode: str = "short",
    ):
        super().__init__()
        self.encoder = encoder
        self.exo_char_budget = int(exo_char_budget)
        self.pred_len = int(pred_len)
        self.calendar_mode = str(calendar_mode)
        self.d_in = encoder.d_model
        self.d_out = int(proj_dim) if proj_dim is not None else self.d_in
        if proj_dim is not None:
            # independent projection per (source, component) — no shared matrix
            self.proj_endo = nn.ModuleDict({
                c: nn.Linear(self.d_in, self.d_out, bias=False) for c in COMPONENTS
            })
            self.proj_exo = nn.ModuleDict({
                c: nn.Linear(self.d_in, self.d_out, bias=False) for c in COMPONENTS
            })
        else:
            self.proj_endo = None
            self.proj_exo = None

    def _project(self, H: Dict[str, torch.Tensor], source: str) -> Dict[str, torch.Tensor]:
        projs = self.proj_endo if source == "endo" else self.proj_exo
        if projs is None:
            return H
        return {c: projs[c](H[c]) for c in COMPONENTS}

    def build_texts(
        self,
        windows: Sequence[Union[np.ndarray, torch.Tensor]],
        facts: Sequence[Optional[str]],
        window_dates: Optional[Sequence[Sequence[Optional[str]]]] = None,
    ):
        """Return parallel lists of 4 endo + 4 exo prompts, plus masks/raw."""
        B = len(windows)
        if len(facts) != B:
            raise ValueError(f"facts length {len(facts)} != windows length {B}")
        endo_raw, exo_raw = [], []
        endo_prompts = {c: [] for c in COMPONENTS}
        exo_prompts = {c: [] for c in COMPONENTS}
        mask_exo = []
        for i in range(B):
            w = windows[i]
            f = facts[i]
            dates_i = window_dates[i] if window_dates is not None else None
            endo_raw.append(build_endo_raw(
                w, dates=dates_i, pred_len=self.pred_len,
                calendar_mode=self.calendar_mode))
            exo = build_exo_raw(f, char_budget=self.exo_char_budget)
            exo_raw.append(exo)
            usable = (not is_empty_text(f)) and (exo != NO_TEXT_TOKEN)
            mask_exo.append(1.0 if usable else 0.0)
            for c in COMPONENTS:
                endo_prompts[c].append(build_endo_component_text(
                    w, c, dates=dates_i, pred_len=self.pred_len,
                    calendar_mode=self.calendar_mode))
                exo_prompts[c].append(build_exo_component_text(
                    f if usable else None, c,
                    char_budget=self.exo_char_budget,
                    dates=dates_i, pred_len=self.pred_len,
                    calendar_mode=self.calendar_mode))
        return endo_prompts, exo_prompts, endo_raw, exo_raw, mask_exo

    def forward(
        self,
        windows: Sequence[Union[np.ndarray, torch.Tensor]],
        facts: Sequence[Optional[str]],
        device: Optional[torch.device] = None,
        window_dates: Optional[Sequence[Sequence[Optional[str]]]] = None,
    ) -> TextSemanticBundle:
        """Encode a batch into dual-source component embeddings."""
        endo_p, exo_p, endo_raw, exo_raw, mask_exo_list = self.build_texts(
            windows, facts, window_dates=window_dates)
        B = len(windows)
        if device is None:
            device = next(self.encoder.llm.parameters()).device

        H_endo: Dict[str, torch.Tensor] = {}
        H_exo: Dict[str, torch.Tensor] = {}
        # encode per component (keeps instruction prefixes aligned in one batch)
        for c in COMPONENTS:
            H_endo[c] = self.encoder.encode(endo_p[c], device=device)
            H_exo[c] = self.encoder.encode(exo_p[c], device=device)

        H_endo = self._project(H_endo, "endo")
        H_exo = self._project(H_exo, "exo")

        mask_exo = torch.tensor(mask_exo_list, device=device, dtype=H_endo["T"].dtype)
        # zero-out empty exogenous embeddings (transparent when no fact)
        for c in COMPONENTS:
            H_exo[c] = H_exo[c] * mask_exo.unsqueeze(-1)

        mask_endo = torch.ones(B, device=device, dtype=H_endo["T"].dtype)
        return TextSemanticBundle(
            H_endo=H_endo,
            H_exo=H_exo,
            mask_endo=mask_endo,
            mask_exo=mask_exo,
            endo_raw=endo_raw,
            exo_raw=exo_raw,
        )


def parse_fact_documents(fact: Optional[str]) -> List[tuple]:
    """Split ``fact`` into ``(date_or_None, body)`` pairs."""
    out = []
    for doc in split_documents(fact):
        m = _DATE_HEAD.match(doc.strip())
        if m:
            out.append((m.group(1), m.group(2).strip()))
        else:
            body = doc.strip()
            if body:
                out.append((None, body))
    return out


@dataclass
class ExoEventBatch:
    """Padded per-document exogenous embeddings for sparse anchoring.

    V      : [B, E, d]  event value vectors (component-specific)
    pos    : [B, E]     local time index in [0, L-1]; -1 = invalid
    mask   : [B, E]     1 if event valid
    quality: [B, E]     heuristic quality in [0, 1]
    route_label : optional [B, E] long weak labels (0=T,1=S,2=C,3=R,-1=ignore)
    Structured EventTuple fields (optional, parser-filled):
      target, intensity, duration, shape, confidence
    """
    V: torch.Tensor
    pos: torch.Tensor
    mask: torch.Tensor
    quality: torch.Tensor
    route_label: Optional[torch.Tensor] = None
    target: Optional[torch.Tensor] = None      # [B,E] long, -1 ignore
    intensity: Optional[torch.Tensor] = None   # [B,E]
    duration: Optional[torch.Tensor] = None    # [B,E]
    shape: Optional[torch.Tensor] = None       # [B,E] long 0=step,1=pulse,2=decay
    confidence: Optional[torch.Tensor] = None  # [B,E]


def _doc_quality(date: Optional[str], body: str) -> float:
    if is_empty_text(body):
        return 0.0
    low = body.lower()
    if "no relevant" in low or low.strip() in ("na", "n/a", "none"):
        return 0.0
    # length / informativeness proxy
    n = len(body)
    q = min(1.0, n / 160.0)
    if date is None:
        q *= 0.7
    return float(q)


def load_gpt2_encoder(
    model_path: str = "language_model/openai-community/gpt2",
    max_length: int = 256,
    pool: str = "avg",
    use_hidden: bool = False,
    device: Optional[Union[str, torch.device]] = None,
    layers: Optional[Sequence[int]] = None,
) -> FrozenLLMPoolEncoder:
    """Convenience loader for the local GPT2 used elsewhere in this repo.

    ``use_hidden=True, layers=(6, 9, 12)`` → contextual multi-layer pooling.
    """
    from transformers import GPT2Model, GPT2Tokenizer

    tok = GPT2Tokenizer.from_pretrained(model_path, local_files_only=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    llm = GPT2Model.from_pretrained(model_path, local_files_only=True)
    if use_hidden and layers is None:
        layers = (6, 9, 12)
    enc = FrozenLLMPoolEncoder(
        llm, tok, max_length=max_length, pool=pool, use_hidden=use_hidden,
        layers=layers)
    if device is not None:
        enc.llm.to(device)
    return enc


def encode_exo_events(
    encoder: FrozenLLMPoolEncoder,
    facts: Sequence[Optional[str]],
    component: str,
    seq_len: int,
    window_dates: Optional[Sequence[Sequence[Optional[str]]]] = None,
    max_events: int = 8,
    proj: Optional[nn.Linear] = None,
    device: Optional[torch.device] = None,
    pred_len: int = 0,
    route_filter: Optional[str] = None,
) -> ExoEventBatch:
    """Encode dated ``fact`` documents for one component; map dates → local index.

    If a document date matches ``window_dates[b][ℓ]``, anchor at ℓ.
    Otherwise anchor at ``seq_len - 1`` (known at forecast origin; foresight cue).

    ``route_filter`` (方案二语义分流):
      - ``\"event\"``: only event-routed docs (for C)
      - ``\"trend\"``: only trend-routed docs (for T)
      - ``\"all\"``: all non-noise docs + weak route_label (for SRSA shared pool)
      - ``None``: component default (C→event, T→trend, S/R→all non-noise)
    """
    if component not in COMPONENTS and component != "ALL":
        raise ValueError(component)
    if device is None:
        device = next(encoder.llm.parameters()).device
    B = len(facts)
    E = int(max_events)
    d_enc = encoder.d_model

    # default route by component if not specified
    if route_filter is None and component == "C":
        route_filter = "event"
    elif route_filter is None and component == "T":
        route_filter = "trend"
    elif route_filter is None and component == "ALL":
        route_filter = "all"

    from layers.event_tuple import parse_event, tuples_to_tensors

    # instruction key for prompt (ALL uses neutral C instruction style)
    instr_key = component if component in COMPONENTS else "C"

    # collect prompts + bookkeeping
    prompts: List[str] = []
    owners: List[tuple] = []  # (b, e_slot)
    # bookkeeping on CPU; moved to ``device`` once at the end
    pos = torch.full((B, E), -1, dtype=torch.long)
    mask = torch.zeros(B, E)
    quality = torch.zeros(B, E)
    parsed: List[List] = [[] for _ in range(B)]

    for b, fact in enumerate(facts):
        docs = parse_fact_documents(fact)[:E]
        dates_b = window_dates[b] if window_dates is not None and b < len(window_dates) else None
        origin = dates_b[-1] if dates_b else None
        date2idx = {}
        if dates_b is not None:
            for ℓ, ds in enumerate(dates_b):
                if ds:
                    date2idx[str(ds)[:10]] = ℓ
        slot = 0
        for date, body in docs:
            if slot >= E:
                break
            q = _doc_quality(date, body)
            if q <= 0:
                continue
            tup = parse_event(body, date=date)
            if tup.target_component == "noise":
                continue
            lab = "event" if tup.is_jump else (
                "trend" if tup.target_component == "trend" else
                "seasonal" if tup.target_component == "seasonal" else "residual")
            if route_filter == "event" and not tup.is_jump:
                continue
            if route_filter == "trend" and tup.target_component != "trend":
                continue
            dtag = build_event_date_tag(date, origin_date=origin)
            text = (
                f"{COMPONENT_INSTRUCTIONS[instr_key]}\n"
                f"Source: exogenous-fact\nRoute: {lab}\nDocument:\n"
                f"{(dtag + ' ') if dtag else ''}"
                f"{(date + ': ') if date else ''}{body}"
            )
            prompts.append(text)
            owners.append((b, slot))
            if date is not None and date in date2idx:
                pos[b, slot] = int(date2idx[date])
            else:
                pos[b, slot] = seq_len - 1
            mask[b, slot] = 1.0
            quality[b, slot] = float(q) * float(tup.confidence)
            parsed[b].append(tup)
            slot += 1

    V = torch.zeros(B, E, d_enc, device=device)
    if prompts:
        emb = encoder.encode(prompts, device=device)  # [N, d_enc]
        bi = torch.tensor([b for b, _ in owners], device=device, dtype=torch.long)
        ei = torch.tensor([e for _, e in owners], device=device, dtype=torch.long)
        V[bi, ei] = emb.to(V.dtype)                   # single scatter
    if proj is not None:
        V = proj(V)
    fields = tuples_to_tensors(parsed, E, pred_len, device)
    return ExoEventBatch(
        V=V, pos=pos.to(device), mask=mask.to(device), quality=quality.to(device),
        route_label=fields["target"],
        target=fields["target"],
        intensity=fields["intensity"],
        duration=fields["duration"],
        shape=fields["shape"],
        confidence=fields["confidence"],
    )

