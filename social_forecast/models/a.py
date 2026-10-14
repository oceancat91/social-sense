import torch
import torch.nn as nn

from layers.EMA_decomp import series_decomp_ema
from layers.Fourier_seasonal import series_decomp_fourier
from layers.jump_branch import JumpDualBranch
from layers.event_response import EventResponseHead
from layers.spectral_residual import SpectralResidualHead
from layers.rep_fusion import MambaEncoder, PatchCNNEncoder, LinearStreamEncoder
from layers.component_cond import (
    CalendarPhaseEncoder,
    EventConditionedJump,
    SeasonAmplitudeModulator,
)


class Model(nn.Module):
    """ŷ = T̂ + Ŝ + Ĉ + R̂,  R = r2 - C.

    Optional DS-SAA (§2.6): attach via ``attach_dssaa``.  Text fusion is wired
    into *all four* heads:
      T — ΔMLP concat pool(H_T)  (trend-routed exo only)
      S — calendar/time phase shift + text amplitude modulation
      C — semantic heterogeneous EventResponseHead (w,s,τ); silent without exo
      R — spectral / band-limited residual (+ optional text FiLM)
    Without text / zero-init, each head reduces to the pure-TS baseline.
    """

    def __init__(self, configs):
        super().__init__()
        self.task_name = configs.task_name
        self.seq_len = configs.seq_len
        self.pred_len = configs.pred_len
        n_vars = int(getattr(configs, 'enc_in', 1))
        self.use_ds_saa = bool(getattr(configs, 'use_ds_saa', False))
        self.dssaa = None
        self._dssaa_facts = None
        self._dssaa_dates = None
        self._exo_C = None  # optional ExoEventBatch for C trigger
        self.d_saa = int(getattr(configs, 'ds_saa_dim', 64))
        self.c_mode = str(getattr(configs, 'c_mode', 'response'))  # response | jump
        # 无外生事件时是否用数值 jump 头预测 C（让 C 参与纯数值预测）
        self.c_numeric = bool(getattr(configs, 'c_numeric', False))

        adapt = str(getattr(configs, 'ema_adapt', 'series'))
        self.decomp = series_decomp_ema(
            init_alpha=float(getattr(configs, 'ema_alpha', 0.05)),
            adapt=adapt,
            learnable=bool(getattr(configs, 'ema_learnable', True)),
            er_window=int(getattr(configs, 'ema_er_window', max(4, self.seq_len))),
        )
        self.seasonal = series_decomp_fourier(
            periods=getattr(configs, 'seasonal_periods', 12),
            K=int(getattr(configs, 'fourier_K', 3)),
            n_vars=n_vars,
        )
        self.seasonal_adaptive = bool(getattr(configs, 'seasonal_adaptive', False))
        self.seasonal_win = int(getattr(configs, 'seasonal_win', 0)) or None

        hidden = int(getattr(configs, 'd_ff', 128))
        self.t_hidden = hidden
        # Numeric Δ-head (stage1) + full-capacity text residual:
        #   ΔT̂ = ΔMLP(ΔT) + g_sup · MLP_txt([ΔT ; mean(H_T)])
        # Same expressivity as the replacement head behind Security 61 /
        # SocialGood 0.756, but zero-init (starts at TS parity) and scaled by
        # a support gate g_sup ∈ [0,1] (see fit_text_support).
        self.delta_mlp = nn.Sequential(
            nn.Linear(self.seq_len - 1, hidden),
            nn.GELU(),
            nn.Linear(hidden, self.pred_len),
        )
        self.delta_mlp_txt = nn.Sequential(
            nn.Linear(self.seq_len - 1 + self.d_saa, hidden),
            nn.GELU(),
            nn.Linear(hidden, self.pred_len),
        )
        # t_head: 'replace' → ΔT̂ = MLP_txt([ΔT;h])            (random init)
        #         'residual'→ ΔT̂ = ΔMLP(ΔT) + g·MLP_txt([ΔT;h]) (zero init)
        self.t_head = str(getattr(configs, 't_head', 'residual'))
        if self.t_head == 'residual':
            nn.init.zeros_(self.delta_mlp_txt[-1].weight)
            nn.init.zeros_(self.delta_mlp_txt[-1].bias)
        self.txt_film = self.delta_mlp_txt
        # Scale-equivariant trend head (numeric).  ΔT̂_eq = s · MLP(ΔT / s),
        # s = std_t(ΔT): positively homogeneous, so it extrapolates to
        # amplitude regimes never seen in training (Security test has
        # std(ΔT) ≈ 11× train).  The unconstrained ΔMLP is more accurate
        # in-range, so the two are mixed by a *scale-OOD* gate
        #   w = σ((log s − log s_ref) / τ),  s_ref = q95 of train log-scale,
        # i.e. non-homogeneous paths (ΔMLP, text residual) are trusted only
        # inside the training scale range.  fit_scale_gate() sets s_ref, τ.
        self.delta_mlp_eq = nn.Sequential(
            nn.Linear(self.seq_len - 1, hidden),
            nn.GELU(),
            nn.Linear(hidden, self.pred_len),
        )
        # ---- encoded-trend augmentation (RepMoE-style encoder on the trend) ----
        # The plain (in-range) head gets an extra Mamba-encoded trend branch:
        #   ΔT̂_plain = ΔMLP(ΔT) + ΔMLP_enc([ΔT ; pool(enc_T(T))])
        # The equivariant head stays PURELY scale-homogeneous (ΔT/s only), so
        # the scale-OOD extrapolation is not corrupted by the encoder.  This is
        # the minimal "separate-prediction + RepMoE encoder" fusion.
        self.use_enc_T = bool(getattr(configs, 'use_enc_T', False))
        self.enc_T = None
        self.delta_mlp_enc = None
        if self.use_enc_T:
            self.enc_T = MambaEncoder(
                n_vars, self.d_saa, n_layers=2, d_state=16)
            self.delta_mlp_enc = nn.Sequential(
                nn.Linear(self.seq_len - 1 + self.d_saa, hidden),
                nn.GELU(),
                nn.Linear(hidden, self.pred_len),
            )
            nn.init.zeros_(self.delta_mlp_enc[-1].weight)
            nn.init.zeros_(self.delta_mlp_enc[-1].bias)
        # ---- random shape reservoir INSIDE the equivariant head ----
        # ΔT̂_eq = s · MLP( out( Mamba( ΔT / s ) ) ), with Mamba FROZEN at
        # init (a random reservoir, see forecast_trend).  It projects the
        # normalized increments into a scale-invariant shape feature space;
        # only delta_mlp_eq is trained.  The head is positively homogeneous:
        #   f(k·ΔT) = k·f(ΔT).
        self.use_enc_eq = bool(getattr(configs, 'use_enc_eq', False))
        self.enc_T_eq = None
        self.enc_T_eq_out = None
        if self.use_enc_eq:
            self.enc_T_eq = MambaEncoder(
                n_vars, self.d_saa, n_layers=2, d_state=16)
            self.enc_T_eq_out = nn.Sequential(
                nn.LayerNorm(self.d_saa),
                nn.Linear(self.d_saa, n_vars),
            )
        self.register_buffer('scale_log_ref', torch.tensor(0.0))
        self.register_buffer('scale_tau', torch.tensor(1.0))
        self.register_buffer('scale_ready', torch.tensor(False))
        # trend_mode: 'mix' | 'plain' | 'eq'  (ablation of the scale-OOD mix)
        self.trend_mode = str(getattr(configs, 'trend_mode', 'mix'))
        # whether text residual is down-weighted by (1-w) under scale OOD
        self.text_scale_gate = bool(getattr(configs, 'text_scale_gate', True))
        self._T_hat_plain = None
        self._T_hat_eq = None
        self.delta_txt_resid = self.delta_mlp_txt
        self._trend_text_delta = None
        # Support model of the endogenous-T embedding on the *training* set.
        self.register_buffer('sup_mu', torch.zeros(self.d_saa))
        self.register_buffer('sup_istd', torch.ones(self.d_saa))
        self.register_buffer('sup_thr', torch.tensor(float('inf')))
        self.register_buffer('sup_scale', torch.tensor(1.0))
        self.register_buffer('sup_ready', torch.tensor(False))

        base_jump = JumpDualBranch(
            seq_len=self.seq_len,
            pred_len=self.pred_len,
            n_vars=n_vars,
            hidden=int(getattr(configs, 'jump_hidden', 32)),
            theta=float(getattr(configs, 'jump_theta', 0.5)),
            pos_weight=float(getattr(configs, 'jump_pos_weight', 5.0)),
        )
        self.jump = EventConditionedJump(base_jump, d_text=self.d_saa)
        self.event_resp = EventResponseHead(
            d_text=self.d_saa,
            pred_len=self.pred_len,
            K=int(getattr(configs, 'response_K', 3)),
            hidden=int(getattr(configs, 'jump_hidden', 32)),
            n_vars=n_vars,
        )
        self.register_buffer('C_full', torch.zeros(1, n_vars))
        self.register_buffer('C_ready', torch.tensor(False))

        # R: spectral residual (alias ``mamba`` kept for train-script compat)
        periods = getattr(configs, 'seasonal_periods', 12)
        period0 = float(periods[0] if isinstance(periods, (list, tuple)) else periods)
        self.phase_enc = CalendarPhaseEncoder(
            period=period0, hidden=32,
            max_shift=float(getattr(configs, 'season_max_phase', 2.0)))
        self.resid = SpectralResidualHead(
            seq_len=self.seq_len,
            pred_len=self.pred_len,
            n_vars=n_vars,
            n_bands=int(getattr(configs, 'resid_n_bands', 4)),
            hidden=int(getattr(configs, 'd_ff', 64)),
            d_text=self.d_saa,
        )
        self.mamba = self.resid  # backward-compatible attribute name

        self.season_mod = SeasonAmplitudeModulator(
            d_text=self.d_saa, n_vars=n_vars, hidden=hidden)

        self.register_buffer('_last_orth', torch.tensor(0.0))
        self._last_C_info = None

    def attach_dssaa(self, dssaa_module):
        self.dssaa = dssaa_module
        self.use_ds_saa = True

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
        """Attach offline template library to EventResponseHead."""
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

    def trend_trust_region(self):
        """No trust-region penalty on the T residual (it erases the T gain);
        out-of-support behaviour is handled by the support gate instead."""
        return self.delta_mlp[0].weight.new_zeros(())

    # ---- support gate: trust the text T-head only inside train support ----
    @torch.no_grad()
    def fit_text_support(self, E_train: torch.Tensor, q: float = 0.95):
        """E_train [N,d]: endogenous-T embeddings of the training windows.

        d(e) = RMS standardised distance to the train mean (diag Mahalanobis).
        gate(e) = exp(-relu(d - d_q) / s): 1 inside the q-quantile ball,
        decaying with distance outside (covariate-shift-aware trust).
        """
        E = E_train.to(self.sup_mu.device).float()
        mu = E.mean(dim=0)
        var = E.var(dim=0, unbiased=False)
        var = var + 0.1 * var.mean() + 1e-6                 # shrinkage
        self.sup_mu.copy_(mu)
        self.sup_istd.copy_(var.rsqrt())
        d = (((E - mu) * self.sup_istd) ** 2).mean(dim=-1).sqrt()
        self.sup_thr.copy_(torch.quantile(d, q))
        self.sup_scale.copy_(d.std(unbiased=False).clamp_min(1e-3))
        self.sup_ready.fill_(True)
        return d

    def text_support_dist(self, E: torch.Tensor) -> torch.Tensor:
        return (((E - self.sup_mu) * self.sup_istd) ** 2).mean(dim=-1).sqrt()

    def text_support_gate(self, E: torch.Tensor) -> torch.Tensor:
        if not bool(self.sup_ready.item()):
            return E.new_ones(E.size(0))
        d = self.text_support_dist(E)
        return torch.exp(-torch.relu(d - self.sup_thr) / self.sup_scale)

    @staticmethod
    def window_scale(dT):
        return dT.std(dim=1, keepdim=True) + 1e-6           # [B,1,C]

    @torch.no_grad()
    def fit_scale_gate(self, x, q=0.95):
        """Set the scale-OOD gate from training windows: s_ref = q-quantile,
        τ = std of log window-scale."""
        _, T = self.decomp(x)
        ls = torch.log(self.window_scale(T[:, 1:] - T[:, :-1])[:, 0, 0])
        self.scale_log_ref.fill_(float(torch.quantile(ls, q)))
        self.scale_tau.fill_(float(ls.std().clamp_min(1e-3)))
        self.scale_ready.fill_(True)

    def scale_gate(self, dT):
        """w ∈ [0,1]: how far the window scale lies above the training range."""
        if not bool(self.scale_ready):
            return dT.new_zeros(dT.size(0), 1, 1)
        ls = torch.log(self.window_scale(dT)[:, :1, 0])    # [B,1]
        return torch.sigmoid((ls - self.scale_log_ref) / self.scale_tau).unsqueeze(-1)

    def forecast_trend(self, x, H_T=None, gate_T=None):
        r1, T = self.decomp(x)
        dT = T[:, 1:] - T[:, :-1]                           # [B,L-1,C]
        dT_plain = self.delta_mlp(dT.permute(0, 2, 1)).permute(0, 2, 1)
        # encoded-trend augmentation (in-range only; keeps eq head homogeneous)
        if self.use_enc_T and self.enc_T is not None:
            h_enc = self.enc_T(T)                 # [B,L,d_saa]
            h_enc = h_enc.mean(dim=1)             # [B,d_saa]
            d_enc = []
            for c in range(dT.size(-1)):
                d_enc.append(self.delta_mlp_enc(
                    torch.cat([dT[:, :, c], h_enc], dim=-1)))
            dT_plain = dT_plain + torch.stack(d_enc, dim=-1)  # [B,P,C]
        s = self.window_scale(dT)
        x_norm = (dT / s).permute(0, 2, 1)                     # [B,C,L-1]
        dT_eq = self.delta_mlp_eq(x_norm).permute(0, 2, 1) * s
        if self.use_enc_eq and self.enc_T_eq is not None:
            # Random scale-invariant SHAPE RESERVOIR inside the homogeneous
            # head:
            #   ΔT̂_eq = s · MLP( out( Mamba( ΔT / s ) ) )
            # The Mamba reservoir is FROZEN (no_grad): it is a random
            # nonlinear projection of the *normalized* increments ΔT/s into a
            # scale-invariant shape feature space.  Only the outer
            # delta_mlp_eq is trained.  A random reservoir cannot overfit the
            # training scale, which is exactly why it extrapolates to OOD
            # scales (Security 11×) and complex shapes (SocialGood) better
            # than a *trained* encoder (a trained Mamba overfits on this
            # small data: SocialGood TS 0.737→0.982 when trained).  The whole
            # head stays positively homogeneous (f(k·ΔT) = k·f(ΔT)).
            with torch.no_grad():
                h = self.enc_T_eq(dT / s)                      # [B,L-1,d_saa]
                h = self.enc_T_eq_out(h)                       # [B,L-1,C]
            dT_eq = self.delta_mlp_eq(h.permute(0, 2, 1)).permute(0, 2, 1) * s
        self._T_hat_plain = T[:, -1:, :] + torch.cumsum(dT_plain, dim=1)
        w = self.scale_gate(dT)                             # [B,1,1]
        self._T_hat_eq = T[:, -1:, :] + torch.cumsum(dT_eq, dim=1)
        mode = getattr(self, 'trend_mode', 'mix')
        if mode == 'plain':
            dT_hat = dT_plain
            w = w * 0.0
        elif mode == 'eq':
            dT_hat = dT_eq
            w = w * 0.0 + 1.0
        else:
            dT_hat = (1 - w) * dT_plain + w * dT_eq
        self._trend_text_delta = None
        if H_T is not None and self.use_ds_saa:
            h = H_T.mean(dim=1) if H_T.dim() == 3 else H_T  # [B,d]
            outs = []
            for c in range(dT.size(-1)):
                inp = torch.cat([dT[:, :, c], h], dim=-1)
                outs.append(self.delta_mlp_txt(inp))
            d_txt = torch.tanh(torch.stack(outs, dim=-1))   # [B,P,C] bounded
            g = gate_T if gate_T is not None else h.new_ones(h.size(0))
            g = g.view(-1, 1, 1)
            # text path is not scale-equivariant → down-weight under scale OOD
            if getattr(self, 'text_scale_gate', True):
                g = g * (1 - w)
            if self.t_head == 'residual':
                d_txt = d_txt * g
                self._trend_text_delta = d_txt
                dT_hat = dT_hat + d_txt
            else:
                # gated replacement: g=1 → text head, g=0 → TS head
                self._trend_text_delta = d_txt - dT_hat
                dT_hat = dT_hat + g * (d_txt - dT_hat)
        T_hat = T[:, -1:, :] + torch.cumsum(dT_hat, dim=1)
        return T_hat, r1, T

    def forecast_seasonal(self, r1, t, S_hist=None, H_S=None, gate_S=None):
        # phase from calendar/time (numeric); amplitude from text
        steps = torch.arange(1, self.pred_len + 1, device=t.device, dtype=t.dtype)
        t_origin = t[:, -1]
        phase = self.phase_enc(t_origin)  # [B] steps; 0 at init
        t_fut = t_origin.unsqueeze(1) + steps.unsqueeze(0) + phase.unsqueeze(1)
        if self.seasonal_adaptive:
            # adaptive path: evaluate basis at phase-shifted future times
            S_base = self.seasonal.forecast(t_fut)
        else:
            S_base = self.seasonal.forecast(t_fut)
        if H_S is None or not self.use_ds_saa:
            return S_base
        return self.season_mod(S_base, S_hist=S_hist, H_S=H_S, gate=gate_S)

    def forecast_jump(self, r2_hist, C_hist, H_C=None, gate_C=None,
                      exo_V=None, exo_mask=None, exo_quality=None):
        """C prediction.

        c_mode='response' (方案二): Ĉ≡0 without exo/H_C; never predicts jump
        *time* from r2 alone.
        c_mode='jump': legacy dual-branch JumpDualBranch.
        """
        B = r2_hist.size(0)
        if self.c_mode == "response":
            V, m, q = exo_V, exo_mask, exo_quality
            if V is None and self._exo_C is not None:
                V = self._exo_C.V
                m = self._exo_C.mask
                q = self._exo_C.quality
            # 方案二: exogenous events only (no numeric jump-time prediction)
            if V is None:
                if getattr(self, 'c_numeric', False):
                    # 数值触发：无外生事件时，用 legacy jump 头从 r2/C_hist
                    # 预测冲击（让 C 分量参与纯数值预测）。
                    C_hat, p = self.jump.forecast(r2_hist, C_hist)
                    info = {"silent": False, "p_fire": p.amax(dim=1)}
                    self._last_C_info = info
                    return C_hat, info
                z = r2_hist.new_zeros(B, self.pred_len, r2_hist.size(-1))
                self._last_C_info = {"silent": True}
                return z, None
            if V.size(-1) != self.d_saa and self.dssaa is not None:
                if getattr(self.dssaa, "exo_proj", None) is not None:
                    V = self.dssaa.exo_proj["C"](V)
            extra = {}
            src = self._exo_C
            if src is not None:
                extra = dict(
                    target=getattr(src, "target", None),
                    intensity=getattr(src, "intensity", None),
                    duration=getattr(src, "duration", None),
                    shape=getattr(src, "shape", None),
                    confidence=getattr(src, "confidence", None),
                    pos=getattr(src, "pos", None),
                )
            C_hat, info = self.event_resp(
                H_C=None, exo_V=V, exo_mask=m, exo_quality=q, gate=None,
                seq_len=self.seq_len, r2_hist=r2_hist,
                **{k: v for k, v in extra.items() if v is not None})
            self._last_C_info = info
            return C_hat, info.get("trigger")
        return self.jump.forecast(r2_hist, C_hist, H_C=H_C, gate=gate_C)

    def forecast_residual(self, R_hist, H_R=None, gate_R=None):
        return self.resid(R_hist, H_R=H_R, gate=gate_R)

    def forward(self, x_enc, x_mark_enc=None, x_dec=None, x_mark_dec=None,
                mask=None, t=None):
        if self.task_name not in ('long_term_forecast', 'short_term_forecast'):
            raise NotImplementedError(self.task_name)
        B, L, _ = x_enc.shape
        if t is None:
            t = torch.arange(L, device=x_enc.device, dtype=x_enc.dtype).expand(B, -1)

        T, S, r1, r2, R, C_hist = self.decompose(x_enc, t=t)

        H_T = H_S = H_C = H_R = None
        gT = gS = gC = gR = None
        if self.use_ds_saa and self.dssaa is not None and self._dssaa_facts is not None:
            windows = [x_enc[i, :, 0].detach().cpu().numpy() for i in range(B)]
            out = self.dssaa.forward_from_raw(
                T, S, r2, R, windows, self._dssaa_facts,
                window_dates=self._dssaa_dates, device=x_enc.device,
            )
            H_T, H_S = out.H_fusion['T'], out.H_fusion['S']
            H_C, H_R = out.H_fusion['C'], out.H_fusion['R']
            gT, gS = out.gates['T'], out.gates['S']
            gC, gR = out.gates['C'], out.gates['R']
            self._last_orth = out.L_orth.detach()

        T_hat, r1, T = self.forecast_trend(x_enc, H_T=H_T)
        S_hat = self.forecast_seasonal(r1, t, S_hist=S, H_S=H_S, gate_S=gS)
        C_hat, _ = self.forecast_jump(r2, C_hist, H_C=H_C, gate_C=gC)
        R_hat = self.forecast_residual(R, H_R=H_R, gate_R=gR)
        return T_hat + S_hat + C_hat + R_hat
