"""Inference API on top of checkpoint.ForecastBundle.

Numeric path (default): ŷ = T̂+Ŝ+Ĉ+R̂ without text / DSSAA.
Text path: caller supplies H_* / exo_C (advanced; used by training eval).

Also exposes direction hit + spike-warning signals for the forecast narrative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import torch

from checkpoint import ForecastBundle, load_forecast_bundle


@dataclass
class PredictResult:
    """Structured prediction output for the AI workflow."""

    yhat_scaled: np.ndarray          # [P] or [B,P]
    yhat_raw: np.ndarray             # inverse-scaled (log space if trained on log)
    components: Dict[str, np.ndarray]  # T/S/C/R hats (scaled)
    origin_raw: float
    direction: str                   # up / down / flat
    direction_delta: float           # mean(yhat) - origin (scaled)
    spike_warning: bool
    spike_gain: float                # max(yhat) - origin (scaled)
    fire_prob: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "yhat_scaled": np.asarray(self.yhat_scaled).tolist(),
            "yhat_raw": np.asarray(self.yhat_raw).tolist(),
            "components": {k: np.asarray(v).tolist() for k, v in self.components.items()},
            "origin_raw": float(self.origin_raw),
            "direction": self.direction,
            "direction_delta": float(self.direction_delta),
            "spike_warning": bool(self.spike_warning),
            "spike_gain": float(self.spike_gain),
            "fire_prob": self.fire_prob,
            "meta": self.meta,
        }


def _predict_components(model, x, t, *, silent_C: bool = True):
    """Forward pass returning ŷ and component forecasts (numeric / gate-aware)."""
    T, S, r1, r2, R, C_hist = model.decompose(x, t=t)
    T_hat, _, _ = model.forecast_trend(x, H_T=None, gate_T=None)
    S_hat = model.forecast_seasonal(r1, t, S_hist=S, H_S=None, gate_S=None)
    if silent_C:
        C_hat = x.new_zeros(x.size(0), model.pred_len, x.size(-1))
        fire = None
    else:
        model._exo_C = None
        C_hat, info = model.forecast_jump(
            r2, C_hist, H_C=None, gate_C=None, exo_V=None, exo_mask=None)
        fire = None
        if isinstance(info, dict) and "p_fire" in info:
            fire = info["p_fire"]
    R_hat = model.forecast_residual(R, H_R=None, gate_R=None)
    yhat = T_hat + S_hat + C_hat + R_hat
    return yhat, {"T": T_hat, "S": S_hat, "C": C_hat, "R": R_hat}, fire


def _resolve_spike_threshold(bundle: ForecastBundle):
    """解析尖峰预警阈值，优先「排名口径」（预测涨幅的历史 75 分位）。

    之前用真实涨幅的 75 分位 ``spike_thr`` 做绝对阈值，模型预测涨幅被 MSE
    压扁后几乎永远够不到该值，召回仅 ~3%。排名口径改为对「模型预测涨幅」
    取 75 分位，警告预测涨幅最高的 ~25% 窗口，召回对齐到 ~39.4%。

    优先级：
      1. checkpoint metrics 里的 ``pred_gain_q75``（训练时验证集预测涨幅分位）
      2. 同名 sidecar ``<ckpt>.spike_calib.json``（calibrate_spike.py 产出，生产口径）
      3. ``gain90_pred`` 缩放兜底（90 分位 × 0.6 ≈ 75 分位）
      4. 旧绝对口径 ``spike_thr``（仅兜底）
      5. 0.5（最后兜底）
    """
    m = dict(bundle.metrics or {})

    if m.get("pred_gain_q75"):
        return float(m["pred_gain_q75"]), "rank(train)"

    sidecar = bundle.path.with_name(bundle.path.name + ".spike_calib.json")
    if sidecar.exists():
        try:
            import json as _json
            cal = _json.loads(sidecar.read_text(encoding="utf-8"))
            if cal.get("pred_gain_q75"):
                return float(cal["pred_gain_q75"]), "rank(calib)"
        except Exception:  # noqa: BLE001
            pass

    if m.get("gain90_pred"):
        return float(m["gain90_pred"]) * 0.6, "rank(gain90_scale)"

    if m.get("spike_thr") or (bundle.gate or {}).get("spike_thr"):
        return float(m.get("spike_thr") or (bundle.gate or {}).get("spike_thr")), "absolute(legacy)"

    return 0.5, "fallback"


@torch.no_grad()
def predict_window(
    bundle: ForecastBundle,
    window_raw: Sequence[float],
    *,
    t0: Optional[int] = None,
    spike_gain_threshold: Optional[float] = None,
    flat_eps: float = 1e-4,
) -> PredictResult:
    """Predict from one raw OT window of length ``seq_len``.

    ``window_raw`` is in the same space as training CSV OT
    (for SocialMedia_log that is already log1p).
    """
    model = bundle.model
    device = bundle.device
    seq_len = bundle.seq_len
    pred_len = bundle.pred_len
    silent_C = bool(bundle.gate.get("silent_C", True))

    arr = np.asarray(list(window_raw), dtype=np.float64).reshape(-1)
    if arr.size < seq_len:
        raise ValueError(f"窗口长度 {arr.size} < seq_len={seq_len}")
    arr = arr[-seq_len:]
    origin_raw = float(arr[-1])

    x_scaled = bundle.transform(arr).reshape(1, seq_len, 1)
    x = torch.from_numpy(x_scaled).to(device)
    if t0 is None:
        t0 = 0
    t = torch.arange(t0, t0 + seq_len, dtype=torch.float32, device=device).view(1, -1)

    model.eval()
    yhat, comps, fire = _predict_components(model, x, t, silent_C=silent_C)

    yhat_np = yhat[0, :, 0].detach().cpu().numpy()
    comps_np = {k: v[0, :, 0].detach().cpu().numpy() for k, v in comps.items()}
    yhat_raw = bundle.inverse_transform(yhat_np).reshape(-1)

    origin_s = float(bundle.transform([origin_raw]).reshape(-1)[0])
    delta = float(yhat_np.mean() - origin_s)
    gain = float(yhat_np.max() - origin_s)
    if abs(delta) < flat_eps:
        direction = "flat"
    elif delta > 0:
        direction = "up"
    else:
        direction = "down"

    # 排名口径预警阈值（预测涨幅 75 分位），显式传入则覆盖
    if spike_gain_threshold is None:
        spike_gain_threshold, spike_thr_src = _resolve_spike_threshold(bundle)
    else:
        spike_thr_src = "explicit"
    spike_warning = gain > spike_gain_threshold

    fire_prob = None
    if fire is not None:
        fire_prob = float(fire.view(-1)[0].detach().cpu())

    return PredictResult(
        yhat_scaled=yhat_np,
        yhat_raw=yhat_raw,
        components=comps_np,
        origin_raw=origin_raw,
        direction=direction,
        direction_delta=delta,
        spike_warning=spike_warning,
        spike_gain=gain,
        fire_prob=fire_prob,
        meta={
            "seq_len": seq_len,
            "pred_len": pred_len,
            "silent_C": silent_C,
            "t0": int(t0),
            "domain": bundle.domain,
            "spike_thr": spike_gain_threshold,
            "spike_thr_src": spike_thr_src,
        },
    )


@torch.no_grad()
def predict_series(
    bundle: ForecastBundle,
    series_raw: Sequence[float],
    *,
    stride: int = 1,
    max_windows: Optional[int] = None,
) -> List[PredictResult]:
    """Rolling windows over a longer series."""
    arr = np.asarray(list(series_raw), dtype=np.float64).reshape(-1)
    seq_len = bundle.seq_len
    outs: List[PredictResult] = []
    starts = list(range(0, max(arr.size - seq_len + 1, 0), stride))
    if max_windows is not None:
        starts = starts[:max_windows]
    for s in starts:
        outs.append(predict_window(bundle, arr[s:s + seq_len], t0=s))
    return outs


def load_and_predict(
    checkpoint: Union[str, Path],
    window_raw: Sequence[float],
    **kwargs,
) -> PredictResult:
    bundle = load_forecast_bundle(checkpoint, with_text=False)
    return predict_window(bundle, window_raw, **kwargs)
