"""RepMoE: four-path dual-source representations → sparse MoE → forecast.

Locked design
-------------
decomp : EMA T → Fourier S → PELT C → R = r2 - C   (deterministic inputs)
encode : T Linear | S PatchCNN | C Sparse | R Mamba
fuse   : T regime-scale | S FiLM | C trigger-attn | R cross-attn
mix    : Top-k gated experts (router on TS pools only)
head   : Flatten → Linear → ŷ

Text enters *representations* via DS-SAA; it is never added as a prediction residual.
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import torch
import torch.nn as nn

from layers.EMA_decomp import series_decomp_ema
from layers.Fourier_seasonal import series_decomp_fourier
from layers.event_response import EventResponseHead
from layers.rep_fusion import (
    COMPONENTS,
    EventJumpFusion,
    FiLMFusion,
    LinearStreamEncoder,
    MambaEncoder,
    PatchCNNEncoder,
    ResidualScaleFusion,
    SparseEventEncoder,
    SparseMoEMixer,
    TrendConcatFusion,
)


class Model(nn.Module):
    def __init__(self, configs):
        super().__init__()
        self.task_name = configs.task_name
        self.seq_len = int(configs.seq_len)
        self.pred_len = int(configs.pred_len)
        self.n_vars = int(getattr(configs, "enc_in", 1))
        self.d_model = int(getattr(configs, "d_model", 64))
        self.use_ds_saa = bool(getattr(configs, "use_ds_saa", False))
        self.use_text_head = bool(getattr(configs, "use_text_head", False))
        self.dssaa = None
        self._dssaa_facts = None
        self._dssaa_dates = None
        self._exo_C = None
        self._last_gates = None

        # scale-aware head: RevIN two-end (normalise diffs by window scale in,
        # multiply the predicted shape back out) mixed with the ordinary
        # absolute-scale head through a *scale-OOD gate*.  Only the numeric
        # difference base is made equivariant; the MoE residual + text are
        # non-homogeneous corrections that get down-weighted as w→1.
        self.scale_aware = bool(getattr(configs, "scale_aware", True))
        self.text_scale_gate = bool(getattr(configs, "text_scale_gate", True))
        # trend_path=True: split the trend into its own scale-equivariant head
        # (detrended unified head for S/C/R).  Experimentally this HURTS vs the
        # baseline (raw-diff unified head already learns the trend via log_s),
        # so it defaults OFF.  Kept for ablation / the old-a.py reproduction.
        self.trend_path = bool(getattr(configs, "trend_path", False))
        self.register_buffer("scale_log_ref", torch.tensor(0.0))
        self.register_buffer("scale_tau", torch.tensor(1.0))
        self.register_buffer("scale_ready", torch.tensor(False))

        # deterministic decomposition (locked)
        self.decomp = series_decomp_ema(
            init_alpha=float(getattr(configs, "ema_alpha", 0.05)),
            adapt=str(getattr(configs, "ema_adapt", "series")),
            learnable=bool(getattr(configs, "ema_learnable", True)),
            er_window=int(max(4, self.seq_len)),
        )
        self.seasonal = series_decomp_fourier(
            periods=getattr(configs, "seasonal_periods", 12),
            K=int(getattr(configs, "fourier_K", 3)),
            n_vars=self.n_vars,
        )
        self.register_buffer("C_full", torch.zeros(1, self.n_vars))
        self.register_buffer("C_ready", torch.tensor(False))

        # ---- component encoders (locked) ----
        patch_len = int(getattr(configs, "patch_len", 2))
        stride = int(getattr(configs, "patch_stride", 1))
        # T: by default a per-timestep LinearStreamEncoder (zero receptive
        # field).  t_patch_len>1 switches it to a *window-level shape* encoder
        # (PatchCNN, e.g. patch_len=4 stride=2 → 3 half-overlapping trend
        # segments), so the trend path produces window-level shape tokens
        # instead of 8 isolated scalar tokens.  This is the PatchTST-patching
        # idea adapted to the short L=8 window (capture slope/curvature rather
        # than single steps).
        t_patch_len = int(getattr(configs, "t_patch_len", 0))
        if t_patch_len > 1:
            self.enc_T = PatchCNNEncoder(
                self.n_vars, self.d_model, patch_len=t_patch_len,
                stride=int(getattr(configs, "t_patch_stride", 2)))
        else:
            self.enc_T = LinearStreamEncoder(self.n_vars, self.d_model)
        self.enc_S = PatchCNNEncoder(
            self.n_vars, self.d_model, patch_len=patch_len, stride=stride)
        self.enc_C = SparseEventEncoder(self.n_vars, self.d_model)
        # ---- exogenous event-response head (C component, cf. old a.py §4) ----
        # Predicts the future C (jump/response) as a text-marked point process:
        #   Ĉ(τ) = fire · s · Σ_k w_k · f_k(τ − shift)
        # f_k are offline PELT-mined response templates; fire/intensity/shape
        # come from the routed exogenous event tuple + numeric anomaly evidence.
        # Silent (Ĉ ≡ 0) without a routed exo event.  This is the mechanism that
        # took Security from ~80 → ~63 in the old component-separated model; it
        # is added on TOP of the unified head (not through the MoE), so the C
        # component gets its own extrapolatable amplitude.
        self.use_event_resp = bool(getattr(configs, "use_event_resp", False))
        self.event_resp = None
        self._last_C_info = None
        if self.use_event_resp:
            self.event_resp = EventResponseHead(
                d_text=self.d_model, pred_len=self.pred_len,
                K=int(getattr(configs, "response_K", 3)),
                hidden=int(getattr(configs, "d_ff", 64)),
                n_vars=self.n_vars,
            )
        mamba_layers = int(getattr(configs, "mamba_layers", 2))
        mamba_state = int(getattr(configs, "mamba_d_state", 16))
        self.enc_R = MambaEncoder(
            self.n_vars, self.d_model, n_layers=mamba_layers, d_state=mamba_state)

        # ---- path-wise text fusion (four DIFFERENT roles) ----
        # T concat-tune | S FiLM | C event-jump | R gentle-scale
        self.fuse_T = TrendConcatFusion(self.d_model)
        self.fuse_S = FiLMFusion(self.d_model)
        self.fuse_C = EventJumpFusion(self.d_model)
        self.fuse_R = ResidualScaleFusion(self.d_model)

        # text projection (identity unless DS-SAA width differs)
        self.txt_proj = nn.ModuleDict({c: nn.Identity() for c in COMPONENTS})

        # ---- sparse MoE + head ----
        top_k = int(getattr(configs, "moe_top_k", 2))
        self.mixer = SparseMoEMixer(
            self.d_model, n_experts=4, top_k=top_k,
            hidden=int(getattr(configs, "d_ff", 64)),
        )
        # future calendar-phase features → the head can extrapolate a period
        # longer than seq_len (period 12 > seq_len 8); keeps "single head".
        raw_periods = getattr(configs, "seasonal_periods", 12)
        self.periods = [int(raw_periods)] if isinstance(raw_periods, (int, float)) \
            else [int(p) for p in raw_periods]
        self.K = int(getattr(configs, "fourier_K", 3))
        self.n_phase = self.pred_len * len(self.periods) * 2 * self.K
        # head sees: mixed representation + raw history differences (the
        # stationary signal that actually carries predictability, cf. DLinear's
        # diff/moving-average view) + future calendar phase.
        self.n_diff = (self.seq_len - 1) * self.n_vars
        # two-head: a stable DLinear-style *difference base* (raw diffs + log
        # window scale + future calendar phase) plus a *MoE residual* (the
        # fused 4-path representation).  The base is low-capacity and does not
        # overfit on tiny domains; the MoE residual can only refine it.  Both
        # are zero-init → ŷ = x_last (persistence) at start, and with no MoE
        # signal the model collapses to pure DLinear.
        self.head_base = nn.Linear(
            self.n_diff + self.n_vars + self.n_phase,
            self.pred_len * self.n_vars,
        )
        self.head_res = nn.Linear(
            self.seq_len * self.d_model,
            self.pred_len * self.n_vars,
        )
        # ---- scale-equivariant TREND head (component-wise, cf. old a.py §2) ----
        # The trend path T predicts its OWN future differences through a pair
        # of heads mixed by a scale-OOD gate:
        #   dT_plain = MLP(dT)                    (absolute scale, accurate in-range)
        #   dT_eq    = s·MLP(dT / s), s = std(dT) (positively homogeneous)
        #   w = σ((log s − log s_ref)/τ)          (scale-OOD gate)
        #   ΔT̂ = (1−w)·dT_plain + w·dT_eq
        # Unlike the global-RevIN attempt, equivariance sits on the *smoothed
        # trend diff* (low noise), so unit-scale learning is stable.  Both heads
        # are RANDOM-init and trained on their own EMA-continued trend target
        # (see the trainer), so they do NOT depend on the OOD gate for gradient;
        # the gate only selects plain vs. eq downstream.
        self.trend_hidden = int(getattr(configs, "d_ff", 64))
        self.head_trend = nn.Sequential(
            nn.Linear(self.n_diff, self.trend_hidden), nn.GELU(),
            nn.Linear(self.trend_hidden, self.pred_len * self.n_vars),
        )
        self.head_trend_eq = nn.Sequential(
            nn.Linear(self.n_diff, self.trend_hidden), nn.GELU(),
            nn.Linear(self.trend_hidden, self.pred_len * self.n_vars),
        )
        # ---- shape-amplitude decoupling (scale-equivariant head) ----
        # Split the forecast into a scale-INVARIANT shape and a scale-EQUIVARIANT
        # amplitude, gated by a scale-OOD gate.  The shape head sees unit-scale
        # diffs (d_x / s_win) and predicts a unit-scale future-diff shape; the
        # amplitude head outputs a *learned relative gain* exp(log_amp), which
        # multiplies the window scale s_win back in.  Under test-time amplitude
        # drift (Security ≈ 11×, SocialGood ≈ 1.8×) the amplitude scales
        # linearly with s_win, so the head extrapolates by construction rather
        # than by memorised absolute magnitude.  Both heads are zero-init so the
        # module is a no-op at start and trained via an auxiliary loss.
        self.shape_amp = bool(getattr(configs, "shape_amp", False))
        if self.shape_amp:
            self.head_shape = nn.Linear(
                self.n_diff + self.n_phase, self.pred_len * self.n_vars)
            self.head_amp = nn.Linear(
                self.n_diff + self.n_vars + self.n_phase, self.pred_len * self.n_vars)
            for h in (self.head_shape, self.head_amp):
                nn.init.zeros_(h.weight)
                nn.init.zeros_(h.bias)
        # ---- four independent text→delta heads (one per path) ----
        # Each head reads the DS-SAA semantic vector of ITS OWN component and
        # adds an independent Δ correction:  ŷ = ŷ_num + Δ_T + Δ_S + Δ_C + Δ_R.
        # This gives a clean four-way ablation (drop a head → that component's
        # text contribution vanishes) and lets each path's text signal be
        # measured separately.  Created in attach_dssaa once d_model is known.
        self.head_text = None   # nn.ModuleDict{c: LayerNorm→Linear(d_model→P*C)}
        # text paths to keep active (ablation).  Empty set = all active.
        self.text_ablate = set()
        # start near persistence: ŷ = x_last + Δ, Δ∼0 (trend heads stay random-
        # init like the old model; they get their own EMA-continued target)
        for h in (self.head_base, self.head_res):
            nn.init.zeros_(h.weight)
            nn.init.zeros_(h.bias)
        self.predict_residual = bool(getattr(configs, "predict_residual", True))

    # ------------------------------------------------------------------ API
    def attach_dssaa(self, dssaa_module):
        # Register DS-SAA as a *real* submodule so its parameters appear in
        # model.parameters()/state_dict().  A plain attribute assignment
        # silently dropped every DS-SAA param from the optimizers, which made
        # stage-2 a no-op (DS-SAA weights were frozen despite requires_grad).
        if getattr(self, "dssaa", None) is None:
            del self.dssaa  # drop the None placeholder first
        self.add_module("dssaa", dssaa_module)
        self.use_ds_saa = True
        # create the four independent text→delta heads once d_model is known.
        # Input is the DS-SAA semantic vector of each path (d_model wide),
        # LayerNorm-stabilised, small-random init (NOT zero) so the gradient
        # flows without a first-step explosion; a per-head low LR in stage 2
        # keeps the Δ small.
        if self.use_text_head and self.head_text is None:
            dev = next(self.parameters()).device  # follow the model's device
            d_in = self.d_model + self.seq_len     # component semantic + window prior
            self.head_text = nn.ModuleDict({
                c: nn.Sequential(
                    nn.LayerNorm(d_in),
                    nn.Linear(d_in, self.pred_len * self.n_vars),
                ) for c in COMPONENTS
            })
            for c in COMPONENTS:
                for m in self.head_text[c]:
                    if hasattr(m, "weight"):
                        nn.init.normal_(m.weight, std=1e-3)
                        if m.bias is not None:
                            nn.init.zeros_(m.bias)
            self.head_text.to(dev)
            # per-path adaptive gate: a learnable logit (init 0 → gate≈0.5, so
            # every path is active at start and the four-way ablation stays
            # meaningful).  Each path learns ITS OWN confidence, so text/prior
            # never bypass the TS backbone wholesale: an unreliable source is
            # damped, a trustworthy one is amplified — "never trust one source
            # alone" is enforced per component, not by a single global switch.
            self.text_gate = nn.ParameterDict({
                c: nn.Parameter(torch.zeros(1)) for c in COMPONENTS
            })
            self.text_gate.to(dev)
        # if DS-SAA width differs, install linear adapters
        d_saa = int(getattr(dssaa_module, "d_model", self.d_model))
        if d_saa != self.d_model:
            self.txt_proj = nn.ModuleDict({
                c: nn.Linear(d_saa, self.d_model, bias=False) for c in COMPONENTS
            })

    def set_text_batch(self, facts, window_dates=None, exo_C=None):
        self._dssaa_facts = facts
        self._dssaa_dates = window_dates
        self._exo_C = exo_C

    @torch.no_grad()
    def set_jump_series(self, C_full: torch.Tensor):
        if C_full.dim() == 1:
            C_full = C_full.unsqueeze(-1)
        self.C_full = C_full.to(device=self.C_full.device, dtype=self.C_full.dtype)
        self.C_ready.fill_(True)

    @torch.no_grad()
    def load_response_library(self, lib: dict):
        """Attach the offline PELT-mined response template library to the
        event-response head (cf. layers/event_response.fit_response_library)."""
        if self.event_resp is not None and lib is not None:
            self.event_resp.load_library(lib["templates"], lib["centers"])

    def gather_C(self, t: torch.Tensor) -> torch.Tensor:
        if not bool(self.C_ready.item()):
            return t.new_zeros(*t.shape, self.C_full.size(-1))
        idx = t.long().clamp(0, self.C_full.size(0) - 1)
        return self.C_full[idx]

    def gather_C_future(self, t: torch.Tensor) -> torch.Tensor:
        if not bool(self.C_ready.item()):
            return t.new_zeros(t.size(0), self.pred_len, self.C_full.size(-1))
        steps = torch.arange(1, self.pred_len + 1, device=t.device)
        t_fut = t[:, -1:].long() + steps.unsqueeze(0)
        t_fut = t_fut.clamp(0, self.C_full.size(0) - 1)
        return self.C_full[t_fut]

    def decompose(self, x, t=None, C=None):
        r1, T = self.decomp(x)
        r2, S = self.seasonal(r1, t=t)
        if C is None:
            C = self.gather_C(t) if t is not None else torch.zeros_like(r2)
        R = r2 - C
        return T, S, r1, r2, R, C

    # -------------------------------------------------------------- encode
    def encode_ts(
        self, T, S, r2, R, C,
    ) -> Dict[str, torch.Tensor]:
        """Encode the four deterministic components into learned per-path
        representations ``[B,L,d]`` (no text).  These also serve as the DS-SAA
        attention anchors (query + residual base), so text attention is built on
        the *learned* representations rather than hand-crafted differenced stats.
        """
        return {
            "T": self.enc_T(T),
            "S": self.enc_S(S),
            "C": self.enc_C(C, r2=r2),
            "R": self.enc_R(R),
        }

    def encode_paths(
        self,
        T, S, r2, R, C,
        H_tx: Optional[Dict[str, torch.Tensor]] = None,
        c_gate: Optional[torch.Tensor] = None,
        H_ts: Optional[Dict[str, torch.Tensor]] = None,
    ) -> Tuple[Dict[str, torch.Tensor], Dict[str, torch.Tensor]]:
        if H_ts is None:
            H_ts = self.encode_ts(T, S, r2, R, C)
        tx = {c: None for c in COMPONENTS}
        if H_tx is not None:
            for c in COMPONENTS:
                h = H_tx.get(c)
                if h is not None:
                    tx[c] = self.txt_proj[c](h)

        H = {
            "T": self.fuse_T(H_ts["T"], tx["T"]),
            "S": self.fuse_S(H_ts["S"], tx["S"]),
            "C": self.fuse_C(H_ts["C"], tx["C"], gate=c_gate),
            "R": self.fuse_R(H_ts["R"], tx["R"]),
        }
        return H, H_ts

    def _future_phase(self, t: torch.Tensor, B: int) -> torch.Tensor:
        """[B, P, 2KM] Fourier phase at future absolute times."""
        steps = torch.arange(1, self.pred_len + 1, device=t.device, dtype=t.dtype)
        t_fut = t[:, -1:].to(t.dtype) + steps.unsqueeze(0)   # [B,P]
        cols = []
        for P in self.periods:
            w = 2.0 * math.pi / float(P)
            for k in range(1, self.K + 1):
                ang = (w * k) * t_fut
                cols.append(torch.cos(ang))
                cols.append(torch.sin(ang))
        return torch.stack(cols, dim=-1)                      # [B,P,2KM]

    @torch.no_grad()
    def fit_scale_gate(self, x_windows: torch.Tensor, q: float = 0.95):
        """Fit the scale-OOD gate from the training TREND diffs (smoothed, so
        the scale estimate is clean).  s_ref = q-quantile of log trend-diff
        scale, τ = its std.  Windows whose trend scale sits above this range
        get w→1 (equivariant trend head).
        """
        if not self.scale_aware:
            return
        x_windows = x_windows.to(self.scale_log_ref.device)
        _, T = self.decomp(x_windows)                 # [N,L,C] trend (EMA)
        dT = T[:, 1:] - T[:, :-1]                     # [N,L-1,C]
        s = dT.std(dim=1, unbiased=False) + 1e-6      # [N,C]
        ls = torch.log(s).reshape(-1)                 # [N*C]
        if ls.numel() == 0:
            return
        self.scale_log_ref.fill_(float(torch.quantile(ls, q)))
        self.scale_tau.fill_(float(ls.std().clamp_min(1e-3)))
        self.scale_ready.fill_(True)

    def scale_gate(self, s: torch.Tensor) -> torch.Tensor:
        """w ∈ [0,1,1]: how far the window diff-scale exceeds the training range."""
        if not (self.scale_aware and bool(self.scale_ready.item())):
            return s.new_zeros(s.size(0), 1, 1)
        ls = torch.log(s).reshape(s.size(0), -1)[:, 0]   # [B]
        return torch.sigmoid((ls - self.scale_log_ref) / self.scale_tau).unsqueeze(-1).unsqueeze(-1)

    @torch.no_grad()
    def fit_scale_gate_diff(self, x_windows: torch.Tensor, q: float = 0.95):
        """Fit the scale-OOD gate from RAW window diff-scale (for shape_amp).

        Unlike fit_scale_gate (trend diffs), this uses the raw detrended-free
        window diffs so the gate tracks the *actual* prediction scale the
        unified head sees.
        """
        if not self.scale_aware:
            return
        x_windows = x_windows.to(self.scale_log_ref.device)
        d = x_windows[:, 1:] - x_windows[:, :-1]         # [N,L-1,C]
        s = d.std(dim=1, unbiased=False) + 1e-6          # [N,C]
        ls = torch.log(s).reshape(-1)
        if ls.numel() == 0:
            return
        self.scale_log_ref.fill_(float(torch.quantile(ls, q)))
        self.scale_tau.fill_(float(ls.std().clamp_min(1e-3)))
        self.scale_ready.fill_(True)

    @staticmethod
    def _prior_path_feat(prior: torch.Tensor, c: str, x: torch.Tensor) -> torch.Tensor:
        """Semantically assign the window prior to each path (NOT shared
        verbatim): each text head consumes the slice of the LLM historical
        knowledge that its component actually needs.
            S: full prior (historical seasonal mean — the primary knowledge)
            T: prior linear trend          (long-run direction)
            C: observed − prior            (shock vs. history → jump evidence)
            R: prior centred fluctuation   (residual volatility)
        All are ``[B, L]`` on the same scale as ``x``."""
        p = prior
        if p.dim() == 3:
            p = p.squeeze(-1)                     # [B,L]
        L = p.size(-1)
        t_idx = torch.arange(L, device=p.device, dtype=p.dtype)
        t_c = t_idx - t_idx.mean()
        denom = (t_c ** 2).sum() + 1e-6
        mu = p.mean(-1, keepdim=True)
        slope = ((t_c * (p - mu)).sum(-1) / denom).unsqueeze(-1)   # [B,1]
        trend = slope * t_c + mu                                  # [B,L]
        if c == "S":
            return p
        if c == "T":
            return trend
        if c == "C":
            return x[:, :, 0] - p
        return p - mu                                            # "R"

    def _text_from_dssaa(self, x, T, S, r2, R, H_ts=None):
        """Run DS-SAA and return per-path text tokens + C trigger."""
        if not self.use_ds_saa or self.dssaa is None or self._dssaa_facts is None:
            return None, None, x.new_zeros(x.size(0))
        B = x.size(0)
        windows = [x[i, :, 0].detach().cpu().numpy() for i in range(B)]
        out = self.dssaa.forward_from_raw(
            T, S, r2, R, windows, self._dssaa_facts,
            window_dates=self._dssaa_dates, device=x.device, H_ts=H_ts,
        )
        H_tx = {c: out.H_fusion[c] for c in COMPONENTS}
        # trigger: any routed C event with positive quality
        c_trig = x.new_zeros(B)
        if out.exo_routed and "C" in out.exo_routed:
            ev = out.exo_routed["C"]
            c_trig = ((ev.mask * ev.quality).sum(dim=-1) > 0).to(x.dtype)
            self._exo_C = ev
        elif out.gates is not None and "C" in out.gates:
            c_trig = (out.gates["C"] > 0.5).to(x.dtype)
        return H_tx, out, c_trig

    def forecast(self, x, t=None, H_tx=None, c_trigger=None, H_ts=None,
                 text_pool=None, H_text=None, prior=None, exo_C=None):
        B, L, _ = x.shape
        if t is None:
            t = torch.arange(L, device=x.device, dtype=x.dtype).expand(B, -1)

        T, S, r1, r2, R, C = self.decompose(x, t=t)

        # 数值跳变触发：窗口内 PELT 阶跃 C 非零即触发（纯数值信号，独立于文本）
        c_numeric = (C.abs().sum(dim=(1, 2)) > 1e-6).to(x.dtype)   # [B]

        dssaa_out = None
        if H_tx is None:
            if self.use_ds_saa and H_ts is None:
                H_ts = self.encode_ts(T, S, r2, R, C)
            H_tx, dssaa_out, c_auto = self._text_from_dssaa(x, T, S, r2, R, H_ts=H_ts)
            if c_trigger is None:
                c_trigger = c_auto
        if H_text is None and dssaa_out is not None:
            H_text = dssaa_out.H_exo_sem
        # 合并数值跳变与文本外生事件：二者独立地打开 C 专家
        if c_trigger is None:
            c_trigger = c_numeric
        else:
            c_trigger = torch.clamp(c_trigger + c_numeric, max=1.0)

        # ---- exogenous event-response head (independent C component) ----
        # Predicts the future C as a text-marked point process, added on TOP of
        # the unified-head forecast (not through the MoE).  Silent without a
        # routed exo event.  This gives the C component an extrapolatable
        # amplitude (Security ≈ 11× test drift) that the unified head cannot
        # capture.
        C_resp = None
        evC = exo_C if exo_C is not None else self._exo_C
        if self.event_resp is not None and evC is not None and \
                getattr(evC, "mask", None) is not None and evC.mask.sum() > 0:
            # exo_V is detached: the event-response head only does template
            # alignment + trigger; the point-process / C gradient must NOT flow
            # back into the DS-SAA exo projector (which already gets its signal
            # from the text-fusion path).  Otherwise the point-process loss
            # corrupts the text representation (Security 86 → 97).
            C_resp, c_info = self.event_resp(
                H_C=None,
                exo_V=evC.V.detach(), exo_mask=evC.mask, exo_quality=evC.quality,
                target=getattr(evC, "target", None),
                intensity=getattr(evC, "intensity", None),
                shape=getattr(evC, "shape", None),
                confidence=getattr(evC, "confidence", None),
                pos=getattr(evC, "pos", None),
                seq_len=self.seq_len, r2_hist=r2)
            self._last_C_info = c_info

        H, H_ts = self.encode_paths(T, S, r2, R, C, H_tx=H_tx, c_gate=c_trigger,
                                    H_ts=H_ts)
        mixed, gates, L_balance = self.mixer(
            H, c_trigger=c_trigger, H_router=H_ts)
        self._last_gates = gates.detach()
        # head conditioned on future calendar phase → extrapolate seasonality.
        # Predict in the *difference* domain then cumsum back to levels: the
        # difference series is stationary (mean-reverting / trend-stationary),
        # so the head learns an actual signal instead of re-deriving x_last.
        # With a zero-init head, Δ ≡ 0 → cumsum ≡ 0 → ŷ = x_last (persist).
        phi = self._future_phase(t, B)                       # [B,P,2KM]
        dT_hat = None
        if self.trend_path:
            # ---- trend component: scale-equivariant trend-diff heads ----
            # The trend path predicts its OWN future differences (NOT mixed
            # into the MoE head), so scale-equivariance lives on the smoothed
            # trend diff and extrapolates to unseen amplitude.
            dT = (T[:, 1:] - T[:, :-1])                     # [B,L-1,C]
            s_T = dT.std(dim=1, keepdim=True) + 1e-6        # [B,1,C]
            dT_flat = dT.reshape(B, -1)                     # [B,(L-1)C]
            dT_plain = self.head_trend(dT_flat)             # [B,P*C]
            dT_eq = self.head_trend_eq((dT / s_T).reshape(B, -1))
            dT_eq = dT_eq * s_T.repeat(1, self.pred_len, 1).reshape(B, -1)
            if self.scale_aware:
                w = self.scale_gate(s_T)                    # [B,1,1]
                dT_hat = ((1.0 - w) * dT_plain.view(B, self.pred_len, self.n_vars)
                          + w * dT_eq.view(B, self.pred_len, self.n_vars))
            else:
                dT_hat = dT_plain.view(B, self.pred_len, self.n_vars)
            # detrended remainder → unified head (S + C + R only)
            x_use = x - T
            dT_plain_v = dT_plain.view(B, self.pred_len, self.n_vars)
            dT_eq_v = dT_eq.view(B, self.pred_len, self.n_vars)
        else:
            x_use = x
            dT_plain_v = None
            dT_eq_v = None
        d_x = (x_use[:, 1:] - x_use[:, :-1]).reshape(B, -1)   # [B,(L-1)C]
        s_dt = d_x.view(B, self.seq_len - 1, self.n_vars).std(dim=1, keepdim=True) + 1e-6
        log_s = torch.log(s_dt).reshape(B, -1)             # [B,C] log window scale
        d_base = self.head_base(
            torch.cat([d_x, log_s, phi.reshape(B, -1)], dim=-1))
        d_res = self.head_res(mixed.reshape(B, -1))
        # four independent text→delta contributions (clean ablation):
        #   Δ_text = Σ_c σ(gate_c) · head_text[c]([H_text[c] ; prior_c])
        # Prior is *semantically assigned* per path (S↔full historical mean,
        # T↔trend, C↔observed−prior shock, R↔residual fluctuation) instead of
        # being shared verbatim.  Each path's delta is scaled by its OWN
        # learnable confidence gate σ(gate_c) — a per-component adaptive switch
        # so text/prior never bypasses the TS backbone wholesale, and no single
        # source (TS / text / prior) dominates all four paths.
        d_text = 0
        if self.head_text is not None and H_text is not None:
            for i, c in enumerate(COMPONENTS):
                if c in self.text_ablate:
                    continue
                h = H_text.get(c)
                if h is None:
                    continue
                if h.dim() == 3:
                    h = h.mean(dim=1)          # [B,L,d] -> [B,d]
                if prior is not None:
                    p_c = self._prior_path_feat(prior, c, x)   # [B,L]
                    h = torch.cat([h, p_c], dim=-1)            # [B, d+L]
                out_c = self.head_text[c](h)                   # [B,P*C]
                g = torch.sigmoid(self.text_gate[c])           # scalar adaptive gate
                d_text = d_text + g * out_c
        # ---- shape-amplitude decoupling ----
        # d_scale = amp ⊙ shape: scale-INVARIANT shape (unit-scale diffs) ×
        # scale-EQUIVARIANT amplitude (window scale × learned relative gain).
        # The plain head (d_base + d_res + d_text) stays the in-range predictor;
        # the OOD gate w blends in d_scale when the window diff-scale exceeds
        # the training range, so test-time amplitude drift extrapolates by
        # construction instead of by memorised magnitude.
        d_scale = None
        if self.shape_amp:
            s_win = d_x.view(B, self.seq_len - 1, self.n_vars).std(
                dim=1, keepdim=True) + 1e-6                    # [B,1,C]
            d_x_norm = d_x / s_win.repeat(1, self.seq_len - 1, 1).reshape(B, -1)
            # shape head: unit-scale diffs → bounded unit-scale future-diff shape
            d_shape = torch.tanh(self.head_shape(
                torch.cat([d_x_norm, phi.reshape(B, -1)], dim=-1)))   # [B,P*C] ∈ [-1,1]
            # amplitude head: learned relative gain, bounded to (1±tanh) so the
            # amplitude stays in [0, 2·s_win] — stable under test-time OOD (the
            # raw exp() exploded on Security where s_win grew ~11×).
            log_amp = torch.tanh(self.head_amp(
                torch.cat([d_x, log_s, phi.reshape(B, -1)], dim=-1)))  # [B,P*C] ∈ [-1,1]
            amp = s_win.repeat(1, self.pred_len, 1).reshape(B, -1) * (1.0 + log_amp)
            d_scale = (amp * d_shape).view(B, self.pred_len, self.n_vars)  # [B,P,C]
        # ---- assemble ----
        d_plain = (d_base + d_res + d_text).view(B, self.pred_len, self.n_vars)
        if self.shape_amp:
            w = self.scale_gate(d_x.view(B, self.seq_len - 1, self.n_vars).std(
                dim=1, keepdim=True) + 1e-6)                   # [B,1,1]
            d_rest = (1.0 - w) * d_plain + w * d_scale
        else:
            d_rest = d_plain
        if self.trend_path:
            delta = torch.cumsum(dT_hat, dim=1) + torch.cumsum(d_rest, dim=1)
        else:
            delta = torch.cumsum(d_rest, dim=1)
        if self.predict_residual:
            y = x[:, -1:, :] + delta
        else:
            y = delta
        if C_resp is not None:
            y = y + C_resp
        return y, {
            "T": T, "S": S, "C": C, "R": R, "gates": gates,
            "H": H, "dssaa": dssaa_out, "L_balance": L_balance,
            "dT_plain": dT_plain_v,
            "dT_eq": dT_eq_v,
            "d_scale": d_scale,
            "d_plain": d_plain,
            "C_resp": C_resp,
        }

    def forward(self, x_enc, x_mark_enc=None, x_dec=None, x_mark_dec=None,
                mask=None, t=None):
        if self.task_name not in ("long_term_forecast", "short_term_forecast"):
            raise NotImplementedError(self.task_name)
        y, _ = self.forecast(x_enc, t=t)
        return y
