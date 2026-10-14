"""Event-response C branch (方案二): templates + parametric curves.

Paradigm
--------
Do **not** predict *when* a jump occurs from the numeric series alone.
Offline: mine historical PELT breakpoints → response snippets → cluster into
K shape templates.  Online: exogenous text *triggers* a response; the head
only maps (intensity, soft type) → curve parameters / template mixture, then
aligns the curve onto the forecast horizon.

Default Ĉ ≡ 0 (silent) when no exo trigger passes the quality gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Response curve primitives
# ---------------------------------------------------------------------------

def parametric_response(
    horizon: int,
    amp: torch.Tensor,
    decay: torch.Tensor,
    delay: torch.Tensor,
) -> torch.Tensor:
    """Build Ĉ[τ] for τ=0..H-1.

    amp, decay, delay: broadcastable to [B] or [B,1]
    Shape: delayed exponential step
        Ĉ(τ) = amp · exp(-decay · max(τ-delay, 0)) · 1[τ ≥ delay]
    delay is soft (real-valued); we use a smooth gate around floor(delay).
    """
    if amp.dim() == 0:
        amp = amp.view(1)
    B = amp.shape[0]
    device, dtype = amp.device, amp.dtype
    tau = torch.arange(horizon, device=device, dtype=dtype).view(1, horizon)  # [1,H]
    delay = delay.view(B, 1).clamp(0.0, float(max(horizon - 1, 0)))
    decay = decay.view(B, 1).clamp_min(0.0)
    amp = amp.view(B, 1)
    # soft onset: sigmoid((τ - delay) / 0.5)
    onset = torch.sigmoid((tau - delay) / 0.5)
    curve = amp * torch.exp(-decay * F.relu(tau - delay)) * onset
    return curve  # [B,H]


def mix_templates(
    templates: torch.Tensor,
    weights: torch.Tensor,
    scale: torch.Tensor,
) -> torch.Tensor:
    """templates [K,H], weights [B,K] (softmax), scale [B] → [B,H]."""
    w = F.softmax(weights, dim=-1)                        # [B,K]
    base = torch.matmul(w, templates)                     # [B,H]
    return base * scale.view(-1, 1)


# ---------------------------------------------------------------------------
# Offline: mine + cluster response snippets
# ---------------------------------------------------------------------------

@dataclass
class ResponseSnippet:
    t_break: int
    pre: np.ndarray      # length pre_len
    post: np.ndarray     # length horizon (r2 relative to pre-mean)
    amp: float


def extract_response_snippets(
    r2: np.ndarray,
    breakpoints: Sequence[int],
    horizon: int = 6,
    pre_len: int = 3,
) -> List[ResponseSnippet]:
    """Around each BP: pre window level, post H steps as residual-to-pre-mean."""
    r2 = np.asarray(r2, dtype=np.float64).reshape(-1)
    n = r2.size
    out: List[ResponseSnippet] = []
    for b in breakpoints:
        b = int(b)
        if b < pre_len or b + horizon > n:
            continue
        pre = r2[b - pre_len:b].copy()
        level = float(pre.mean())
        post = r2[b:b + horizon] - level
        amp = float(post[0]) if horizon > 0 else 0.0
        if abs(amp) < 1e-8 and float(np.max(np.abs(post))) < 1e-8:
            continue
        out.append(ResponseSnippet(t_break=b, pre=pre, post=post.astype(np.float64), amp=amp))
    return out


def cluster_response_templates(
    snippets: Sequence[ResponseSnippet],
    K: int = 3,
    horizon: int = 6,
    seed: int = 0,
    max_iter: int = 50,
) -> Tuple[np.ndarray, np.ndarray]:
    """K-means on L2-normalized post responses.

    Returns
    -------
    templates : [K, H]  (mean curve in each cluster; not forced unit norm)
    centers  : [K, H]  (same, used for soft assignment of new curves)
    """
    if not snippets:
        # fallback canonical shapes
        t = np.arange(horizon, dtype=np.float64)
        step = np.ones(horizon)
        pulse = (t == 0).astype(np.float64)
        decay = np.exp(-0.5 * t)
        mats = [step, pulse, decay]
        while len(mats) < K:
            mats.append(decay * (0.5 ** len(mats)))
        templates = np.stack(mats[:K], axis=0)
        return templates, templates.copy()

    X = np.stack([s.post[:horizon] for s in snippets], axis=0)  # [N,H]
    # sign-align so positive-amp cluster doesn't split by sign
    signs = np.sign(X[:, 0] + 1e-12)
    X_aligned = X * signs[:, None]
    # normalize for shape clustering
    norms = np.linalg.norm(X_aligned, axis=1, keepdims=True) + 1e-8
    Xn = X_aligned / norms

    rng = np.random.default_rng(seed)
    K_eff = int(min(K, len(snippets)))
    idx = rng.choice(len(snippets), size=K_eff, replace=False)
    centers = Xn[idx].copy()

    for _ in range(max_iter):
        dist = ((Xn[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
        lab = dist.argmin(axis=1)
        new_c = centers.copy()
        for k in range(K_eff):
            m = lab == k
            if m.any():
                new_c[k] = Xn[m].mean(axis=0)
                nrm = np.linalg.norm(new_c[k]) + 1e-8
                new_c[k] /= nrm
        if np.allclose(new_c, centers, atol=1e-6):
            centers = new_c
            break
        centers = new_c

    # template = mean *unnormalized* signed curve in cluster (richer amp info)
    templates = np.zeros((K_eff, horizon), dtype=np.float64)
    for k in range(K_eff):
        m = lab == k
        if m.any():
            templates[k] = X_aligned[m].mean(axis=0)
        else:
            templates[k] = centers[k]
    # pad to K if needed
    if K_eff < K:
        pad = np.repeat(templates[-1:], K - K_eff, axis=0)
        templates = np.concatenate([templates, pad], axis=0)
        centers = np.concatenate([centers, np.repeat(centers[-1:], K - K_eff, axis=0)], axis=0)
    return templates.astype(np.float32), centers.astype(np.float32)


def fit_response_library(
    r2_train: np.ndarray,
    horizon: int = 6,
    pre_len: int = 3,
    K: int = 3,
    period: int = 12,
) -> Dict:
    """Detect jumps on train r2, build template library."""
    from layers.jump_pelt import detect_jumps
    C, bps, events = detect_jumps(r2_train, period=period, w_min=3)
    snippets = extract_response_snippets(r2_train, bps, horizon=horizon, pre_len=pre_len)
    templates, centers = cluster_response_templates(
        snippets, K=K, horizon=horizon)
    return {
        "C": C,
        "bps": bps,
        "events": events,
        "snippets": snippets,
        "templates": templates,   # [K,H]
        "centers": centers,       # [K,H]
        "K": int(templates.shape[0]),
        "horizon": horizon,
        "pre_len": pre_len,
    }


def fit_response_library_from_breakpoints(
    r2_train: np.ndarray,
    breakpoints: Sequence[int],
    horizon: int = 6,
    pre_len: int = 3,
    K: int = 3,
) -> Dict:
    """Build template library from externally given breakpoints (e.g. anomaly days).

    Used when PELT finds nothing on log-smoothed series, but anomaly detection
    already marked event days.  Builds a sparse C series that peaks at each BP.
    """
    r2 = np.asarray(r2_train, dtype=np.float64).reshape(-1)
    n = r2.size
    bps = sorted({int(b) for b in breakpoints if 0 <= int(b) < n})
    snippets = extract_response_snippets(r2, bps, horizon=horizon, pre_len=pre_len)
    templates, centers = cluster_response_templates(
        snippets, K=K, horizon=horizon)
    # sparse C: place each snippet's post curve at its breakpoint
    C = np.zeros(n, dtype=np.float64)
    for s in snippets:
        b = int(s.t_break)
        h = min(horizon, n - b)
        if h > 0:
            C[b:b + h] += np.asarray(s.post[:h], dtype=np.float64)
    return {
        "C": C,
        "bps": bps,
        "events": [{"t": b, "source": "anomaly"} for b in bps],
        "snippets": snippets,
        "templates": templates,
        "centers": centers,
        "K": int(templates.shape[0]),
        "horizon": horizon,
        "pre_len": pre_len,
    }


# ---------------------------------------------------------------------------
# Neural head: intensity / type → response on horizon
# ---------------------------------------------------------------------------

def _roll_templates(templates: torch.Tensor, delay: torch.Tensor) -> torch.Tensor:
    """Causal time-shift of templates: f_k(t - τ), 0 for t < τ.

    templates [K,H], delay [B] → [B,K,H]  (soft floor/ceil blend)
    """
    K, H = templates.shape
    B = delay.size(0)
    device, dtype = templates.device, templates.dtype
    d = delay.clamp(0.0, float(max(H - 1, 0)))
    d0 = d.floor().long().clamp(0, max(H - 1, 0))
    d1 = (d0 + 1).clamp(0, max(H - 1, 0))
    w1 = (d - d0.float()).view(B, 1, 1)
    w0 = 1.0 - w1
    t = torch.arange(H, device=device).view(1, 1, H)          # output time
    src = templates.view(1, K, H).expand(B, K, H)
    s0 = t - d0.view(B, 1, 1)
    s1 = t - d1.view(B, 1, 1)
    y0 = torch.gather(src, 2, s0.clamp(0, H - 1).expand(B, K, H))
    y1 = torch.gather(src, 2, s1.clamp(0, H - 1).expand(B, K, H))
    y0 = y0 * (s0 >= 0).to(dtype)
    y1 = y1 * (s1 >= 0).to(dtype)
    return w0 * y0 + w1 * y1


def _shift_templates_ext(templates_ext: torch.Tensor, shift: torch.Tensor,
                         horizon: int) -> torch.Tensor:
    """Phase-aligned read of extended templates.

    templates_ext [K,L_ext] (L_ext ≥ horizon), shift [B] real-valued:
      out[b,k,t] = f_k(t - shift_b)   (0 outside [0, L_ext))
    shift > 0 → onset delayed into the horizon; shift < 0 → event occurred
    |shift| steps before the origin and the horizon sees the template tail.
    """
    K, L = templates_ext.shape
    B = shift.size(0)
    device, dtype = templates_ext.device, templates_ext.dtype
    d0 = shift.floor()
    w1 = (shift - d0).view(B, 1, 1)
    w0 = 1.0 - w1
    d0 = d0.long()
    d1 = d0 + 1
    t = torch.arange(horizon, device=device).view(1, 1, horizon)
    src = templates_ext.view(1, K, L).expand(B, K, L)

    def _read(d):
        s = t - d.view(B, 1, 1)                                  # [B,1,H]
        ok = ((s >= 0) & (s < L)).to(dtype)
        y = torch.gather(src, 2, s.clamp(0, L - 1).expand(B, K, horizon))
        return y * ok

    return w0 * _read(d0) + w1 * _read(d1)


class EventResponseHead(nn.Module):
    """Text-marked event response (文本标记点过程视角).

    Ĉ(τ) = fire · s · Σ_k w_k · f_k(τ - shift),  shift = delay − lag

    * fire  = σ( logit(i_text) + g_txt(z) + g_num(φ(r2)) )   — conditional
      intensity: textual mark prior × numeric anomaly verification.
    * s     = sign(z, φ) · magnitude(z, φ, i_text)             — signed mark.
    * w     = softmax( 2·onehot(shape_hint) + Δ(z, φ) )        — parser prior
      with learned residual.
    * lag   = (L−1) − pos  : phase alignment; events already `lag` steps old
      contribute their template *tail* on the horizon.

    Shape templates f_k from PELT clustering (extended to 2H by exponential
    tail extrapolation).  Silent without exo.
    """

    def __init__(
        self,
        d_text: int,
        pred_len: int,
        K: int = 3,
        hidden: int = 64,
        n_vars: int = 1,
    ):
        super().__init__()
        self.pred_len = int(pred_len)
        self.K = int(K)
        self.n_vars = int(n_vars)
        self.register_buffer(
            "templates", torch.zeros(self.K, self.pred_len), persistent=True)
        self.register_buffer(
            "centers", torch.zeros(self.K, self.pred_len), persistent=True)
        self.register_buffer(
            "templates_ext", torch.zeros(self.K, 2 * self.pred_len),
            persistent=True)
        self.register_buffer("ready", torch.tensor(False))

        # ---- numeric anomaly evidence φ(r2): last-6 z-scores, |z| max, slope
        self.n_num = 8
        self.num_enc = nn.Sequential(nn.Linear(self.n_num, hidden), nn.GELU())
        self.fire_head = nn.Linear(2 * hidden + 1, 1)
        self.sign_head = nn.Linear(2 * hidden, 1)
        self.mag_head = nn.Linear(2 * hidden + 1, n_vars)
        self.shape_resid = nn.Linear(2 * hidden, self.K)
        nn.init.zeros_(self.fire_head.weight)
        with torch.no_grad():
            self.fire_head.weight[0, -1] = 1.0   # start from parser prior
        nn.init.zeros_(self.fire_head.bias)
        nn.init.zeros_(self.sign_head.weight)
        nn.init.constant_(self.sign_head.bias, 0.5)
        nn.init.zeros_(self.mag_head.weight)
        nn.init.constant_(self.mag_head.bias, -2.0)  # softplus(-2)≈0.13
        nn.init.zeros_(self.shape_resid.weight)
        nn.init.zeros_(self.shape_resid.bias)

        self.enc = nn.Sequential(
            nn.Linear(d_text, hidden), nn.GELU(),
            nn.Linear(hidden, hidden), nn.GELU(),
        )
        # semantic → mixture / scale / delay  (异质性核心)
        self.type_head = nn.Linear(hidden, self.K)       # w logits
        self.scale_head = nn.Linear(hidden, n_vars)      # s
        self.delay_head = nn.Linear(hidden, 1)           # τ
        self.trigger = nn.Linear(hidden, 1)

        nn.init.zeros_(self.scale_head.weight)
        nn.init.constant_(self.scale_head.bias, 0.1)
        nn.init.zeros_(self.delay_head.weight)
        nn.init.zeros_(self.delay_head.bias)
        nn.init.zeros_(self.trigger.weight)
        nn.init.constant_(self.trigger.bias, -0.5)

        self.theta = 0.5
        self.tau_fire = 0.3
        self.scale_from_intensity = nn.Linear(1, n_vars)
        nn.init.zeros_(self.scale_from_intensity.weight)
        nn.init.constant_(self.scale_from_intensity.bias, 0.1)

    @torch.no_grad()
    def load_library(self, templates: np.ndarray, centers: np.ndarray):
        t = torch.from_numpy(np.asarray(templates, dtype=np.float32))
        c = torch.from_numpy(np.asarray(centers, dtype=np.float32))
        K, H = t.shape
        if H != self.pred_len:
            # resize by linear interpolate
            t = F.interpolate(
                t.unsqueeze(0), size=self.pred_len, mode="linear", align_corners=True
            ).squeeze(0)
            c = F.interpolate(
                c.unsqueeze(0), size=self.pred_len, mode="linear", align_corners=True
            ).squeeze(0)
        if K != self.K:
            # pad / truncate
            if K < self.K:
                pad_t = t[-1:].repeat(self.K - K, 1)
                pad_c = c[-1:].repeat(self.K - K, 1)
                t = torch.cat([t, pad_t], 0)
                c = torch.cat([c, pad_c], 0)
            else:
                t, c = t[: self.K], c[: self.K]
        self.templates.copy_(t.to(self.templates.device))
        self.centers.copy_(c.to(self.centers.device))
        # extended tail: f_k(H-1)·exp(-0.3·k)  (used for phase alignment)
        H = self.pred_len
        k = torch.arange(1, H + 1, dtype=t.dtype).view(1, H)
        tail = t[:, -1:] * torch.exp(-0.3 * k)
        self.templates_ext.copy_(torch.cat([t, tail], dim=1).to(self.templates.device))
        self.ready.fill_(True)

    @staticmethod
    def numeric_evidence(r2_hist: Optional[torch.Tensor], B: int,
                         device, dtype) -> torch.Tensor:
        """φ(r2) [B,8]: last-6 window z-scores, max|z| of last 3, slope."""
        if r2_hist is None:
            return torch.zeros(B, 8, device=device, dtype=dtype)
        r = r2_hist[..., 0] if r2_hist.dim() == 3 else r2_hist      # [B,L]
        mu = r.mean(dim=1, keepdim=True)
        sd = r.std(dim=1, keepdim=True, unbiased=False).clamp_min(1e-6)
        z = (r - mu) / sd
        last6 = z[:, -6:]
        if last6.size(1) < 6:
            last6 = F.pad(last6, (6 - last6.size(1), 0))
        zmax3 = z[:, -3:].abs().max(dim=1).values
        slope = (r[:, -1] - r[:, -3]) / (2.0 * sd.squeeze(1))
        return torch.cat([last6, zmax3.unsqueeze(1), slope.unsqueeze(1)], dim=1)

    def _pool_events(
        self,
        V: torch.Tensor,
        mask: torch.Tensor,
        quality: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """V [B,E,d], mask/quality [B,E] → pooled [B,d], strength [B]."""
        w = mask * quality
        w = w / w.sum(dim=-1, keepdim=True).clamp_min(1e-6)
        pooled = (V * w.unsqueeze(-1)).sum(dim=1)
        strength = (mask * quality).sum(dim=-1) / mask.sum(dim=-1).clamp_min(1.0)
        strength = strength * (mask.sum(dim=-1) > 0).to(strength.dtype)
        return pooled, strength

    def forward(
        self,
        H_C: Optional[torch.Tensor] = None,
        exo_V: Optional[torch.Tensor] = None,
        exo_mask: Optional[torch.Tensor] = None,
        exo_quality: Optional[torch.Tensor] = None,
        gate: Optional[torch.Tensor] = None,
        force_silent: bool = False,
        target: Optional[torch.Tensor] = None,
        intensity: Optional[torch.Tensor] = None,
        duration: Optional[torch.Tensor] = None,
        shape: Optional[torch.Tensor] = None,
        confidence: Optional[torch.Tensor] = None,
        seq_len: Optional[int] = None,
        pos: Optional[torch.Tensor] = None,
        r2_hist: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        """
        Returns
        -------
        C_hat : [B, H, n_vars]
        info  : trigger probs, etc.
        """
        if force_silent:
            raise RuntimeError("use zeros from caller when force_silent")

        if H_C is None and exo_V is None:
            raise ValueError("EventResponseHead needs H_C or exo_V")

        if exo_V is not None:
            B = exo_V.size(0)
            device, dtype = exo_V.device, exo_V.dtype
            if exo_mask is None:
                exo_mask = torch.ones(B, exo_V.size(1), device=device, dtype=dtype)
            if exo_quality is None:
                exo_quality = exo_mask
            pooled, strength = self._pool_events(exo_V, exo_mask, exo_quality)
            # blend with H_C if present
            if H_C is not None:
                h_c = H_C.mean(dim=1) if H_C.dim() == 3 else H_C
                if h_c.size(-1) == pooled.size(-1):
                    pooled = pooled + h_c
                elif h_c.size(-1) < pooled.size(-1):
                    pooled = pooled.clone()
                    pooled[..., : h_c.size(-1)] = pooled[..., : h_c.size(-1)] + h_c
        else:
            h_c = H_C.mean(dim=1) if H_C.dim() == 3 else H_C
            B = h_c.size(0)
            device, dtype = h_c.device, h_c.dtype
            pooled = h_c
            strength = h_c.new_ones(B)

        z = self.enc(pooled)
        trig = torch.sigmoid(self.trigger(z).squeeze(-1))
        has = (strength > 1e-6).to(trig.dtype)
        trig = trig * has
        g = gate if gate is not None else trig.new_ones(B)
        fire = trig * g.view(B)
        if not self.training:
            fire = fire * (trig >= self.theta).to(fire.dtype)

        # Ĉ = s · Σ w_k f_k(· - τ)
        type_logits = self.type_head(z)                              # [B,K]
        w = F.softmax(type_logits, dim=-1)
        scale = self.scale_head(z)                                   # [B,n_vars]
        delay = torch.sigmoid(self.delay_head(z).squeeze(-1)) * float(
            max(self.pred_len - 1, 0))
        conf_w = trig.new_ones(B)
        p_fire = trig
        shift = delay

        # ---- Text-marked point process trigger (EventTuple + numeric evidence)
        if intensity is not None and exo_mask is not None:
            m = exo_mask
            is_jump = m
            if target is not None:
                is_jump = m * (target == 2).to(m.dtype)
            inten = intensity * is_jump
            if confidence is not None:
                inten = inten * confidence
            best = inten.argmax(dim=-1)
            b_idx = torch.arange(B, device=device)
            i_star = inten[b_idx, best]
            jump_ok = is_jump[b_idx, best] > 0

            # numeric anomaly verification φ(r2)
            phi = self.numeric_evidence(r2_hist, B, device, dtype)
            zn = self.num_enc(phi)
            zz = torch.cat([z, zn], dim=-1)
            prior_logit = torch.logit(i_star.clamp(1e-3, 1 - 1e-3))
            fire_logit = self.fire_head(
                torch.cat([zz, prior_logit.unsqueeze(-1)], dim=-1)).squeeze(-1)
            p_fire = torch.sigmoid(fire_logit) * jump_ok.to(dtype)
            fire = p_fire
            if not self.training:
                fire = fire * (p_fire >= self.theta).to(dtype)

            # shape: parser prior + learned residual
            if shape is not None:
                sh = shape[b_idx, best].clamp(min=0, max=self.K - 1)
                prior = 2.0 * F.one_hot(sh, num_classes=self.K).to(dtype)
            else:
                prior = torch.zeros(B, self.K, device=device, dtype=dtype)
            type_logits = prior + self.shape_resid(zz)
            w = F.softmax(type_logits, dim=-1)

            # signed magnitude mark
            sgn = torch.tanh(self.sign_head(zz))                          # [B,1]
            mag = F.softplus(self.mag_head(
                torch.cat([zz, i_star.unsqueeze(-1)], dim=-1)))           # [B,n]
            scale = sgn * mag * (0.5 + i_star.unsqueeze(-1))

            # phase alignment: lag = (L-1) - pos of the chosen doc
            if pos is not None and seq_len is not None:
                p_sel = pos[b_idx, best].clamp(min=0)
                lag = (float(seq_len - 1) - p_sel.to(dtype)).clamp_min(0.0)
            else:
                lag = torch.zeros(B, device=device, dtype=dtype)
            # learned onset delay only applies to origin-anchored docs
            shift = delay * (lag <= 0).to(dtype) - lag

        if intensity is None:
            shifted = _roll_templates(self.templates, delay)             # [B,K,H]
        else:
            shifted = _shift_templates_ext(self.templates_ext, shift, self.pred_len)
        curve = (w.unsqueeze(-1) * shifted).sum(dim=1)               # [B,H]
        curve = curve * scale[:, 0:1]
        C_hat = (curve * fire.view(B, 1)).unsqueeze(-1)
        if self.n_vars > 1:
            C_hat = C_hat.expand(B, self.pred_len, self.n_vars)

        info = {
            "trigger": p_fire,
            "p_fire": p_fire,
            "fire": fire,
            "type_logits": type_logits,
            "weights": w,
            "scale": scale,
            "delay": shift,
            "strength": strength,
            "curve": curve,
        }
        return C_hat, info

    def loss_on_snippets(
        self,
        embeddings: torch.Tensor,
        targets: torch.Tensor,
        strengths: Optional[torch.Tensor] = None,
        r2_hist: Optional[torch.Tensor] = None,
        seq_len: Optional[int] = None,
    ) -> torch.Tensor:
        """Curve MSE + shape alignment + trigger BCE (自监督断点响应).

        Runs the structured (text-marked) path: target=jump, intensity from
        strengths, numeric evidence from the pre-break r2 window, so the
        sign / magnitude / fire heads are fitted on real signed responses.
        """
        N = embeddings.size(0)
        if N == 0:
            return embeddings.new_zeros(())
        V = embeddings.unsqueeze(1)
        mask = torch.ones(N, 1, device=embeddings.device, dtype=embeddings.dtype)
        qual = strengths.view(N, 1) if strengths is not None else mask
        inten = qual.clamp(0.05, 1.0)
        target = torch.full((N, 1), 2, device=embeddings.device, dtype=torch.long)
        pos = None
        if seq_len is not None:
            pos = torch.full((N, 1), int(seq_len) - 1, device=embeddings.device,
                             dtype=torch.long)
        was = self.training
        self.train()
        C_hat, info = self.forward(
            exo_V=V, exo_mask=mask, exo_quality=qual,
            target=target, intensity=inten, confidence=mask,
            pos=pos, seq_len=seq_len, r2_hist=r2_hist)
        self.train(was)
        pred = C_hat.squeeze(-1)
        loss_curve = F.mse_loss(pred, targets)
        # shape loss: cosine to nearest template (after unit-norm)
        tgt_n = F.normalize(targets, dim=-1, eps=1e-6)
        tmpl_n = F.normalize(self.templates, dim=-1, eps=1e-6)  # [K,H]
        sim = torch.matmul(tgt_n, tmpl_n.t())                   # [N,K]
        best = sim.argmax(dim=-1)
        # push predicted mixture toward that soft assignment
        loss_shape = F.cross_entropy(info["type_logits"], best)
        # also align normalized curve shape
        pred_n = F.normalize(info["curve"], dim=-1, eps=1e-6)
        loss_cos = (1.0 - (pred_n * tgt_n).sum(dim=-1)).mean()
        loss_trig = F.binary_cross_entropy(
            info["trigger"].clamp(1e-4, 1 - 1e-4),
            torch.ones_like(info["trigger"]),
        )
        return loss_curve + 0.2 * loss_shape + 0.2 * loss_cos + 0.1 * loss_trig
