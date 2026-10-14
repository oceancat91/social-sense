"""Checkpoint save / load for the social forecast model (ŷ = T̂+Ŝ+Ĉ+R̂).

Does **not** change model architecture — only serializes weights + config needed
to rebuild an inference bundle.

Typical layout::

    checkpoints/
      SocialMedia_log_lite_pl6.pt   # torch package (dict)

Contents (keys):
  version, created_at, domain, metrics
  config          — model hyper-params (seq_len, pred_len, capacity, …)
  scaler          — {mean, scale} of StandardScaler fit on train OT
  gate            — {silent_C, drop, theta, support_gate, …}
  response_lib    — templates/centers summary (+ optional C series)
  model_state     — Model.state_dict()
  dssaa_state     — DSSAAModule.state_dict() (may be None)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import torch

CKPT_VERSION = "social_forecast_ckpt_v1"
DEFAULT_CKPT_DIR = Path(__file__).resolve().parent / "checkpoints"


def _to_numpy(x) -> Optional[np.ndarray]:
    if x is None:
        return None
    if isinstance(x, np.ndarray):
        return x
    if torch.is_tensor(x):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def _jsonable(obj: Any) -> Any:
    """Make nested structures JSON-serializable (for meta sidecar)."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if torch.is_tensor(obj):
        return obj.detach().cpu().tolist()
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def configs_to_dict(configs) -> Dict[str, Any]:
    """Convert SimpleNamespace / object configs to a plain dict."""
    if isinstance(configs, dict):
        d = dict(configs)
    else:
        d = {
            k: getattr(configs, k)
            for k in dir(configs)
            if not k.startswith("_") and not callable(getattr(configs, k, None))
        }
    # normalize seasonal_periods — FourierSeasonal expects int or list[int]
    sp = d.get("seasonal_periods", 12)
    if isinstance(sp, (list, tuple)):
        d["seasonal_periods"] = [int(x) for x in sp]
    elif sp is not None:
        d["seasonal_periods"] = int(sp)
    else:
        d["seasonal_periods"] = 12
    # torch/json may cast ints → float; coerce known int fields
    for k in ("seq_len", "pred_len", "enc_in", "d_ff", "ds_saa_dim",
              "jump_hidden", "response_K", "fourier_K", "resid_n_bands"):
        if k in d and d[k] is not None:
            d[k] = int(d[k])
    return d


def dict_to_configs(d: Dict[str, Any]) -> SimpleNamespace:
    cfg = dict(d)
    sp = cfg.get("seasonal_periods", 12)
    if isinstance(sp, (list, tuple)):
        cfg["seasonal_periods"] = [int(x) for x in sp]
    elif sp is not None:
        cfg["seasonal_periods"] = int(sp)
    for k in ("seq_len", "pred_len", "enc_in", "d_ff", "ds_saa_dim",
              "jump_hidden", "response_K", "fourier_K", "resid_n_bands"):
        if k in cfg and cfg[k] is not None:
            cfg[k] = int(cfg[k])
    return SimpleNamespace(**cfg)


def build_model(configs, device: Optional[torch.device] = None):
    """Instantiate ``models.a.Model`` from a config dict / namespace."""
    from models.a import Model

    cfg = configs if not isinstance(configs, dict) else dict_to_configs(configs)
    model = Model(cfg)
    if device is not None:
        model = model.to(device)
    return model


def build_dssaa(
    configs,
    encoder=None,
    calendar_mode: str = "short",
    max_events: int = 4,
    t_endo: bool = True,
    t_time_only: bool = False,
    device: Optional[torch.device] = None,
):
    """Build DSSAAModule (+ DualSourceSemanticSpace). Requires GPT-2 encoder."""
    from layers.ds_saa import DSSAAModule
    from layers.ds_saa_semantic import DualSourceSemanticSpace

    cfg = configs if not isinstance(configs, dict) else dict_to_configs(configs)
    d_saa = int(getattr(cfg, "ds_saa_dim", 64))
    seq_len = int(getattr(cfg, "seq_len", 28))
    pred_len = int(getattr(cfg, "pred_len", 6))
    if encoder is None:
        from layers.ds_saa_semantic import load_gpt2_encoder
        encoder = load_gpt2_encoder(device=device or "cpu", use_hidden=False)
    semantic = DualSourceSemanticSpace(
        encoder, proj_dim=d_saa, pred_len=pred_len, calendar_mode=calendar_mode
    )
    dssaa = DSSAAModule(
        d_model=d_saa, seq_len=seq_len, n_vars=1,
        semantic=semantic, max_events=max_events,
        t_endo=t_endo, t_time_only=t_time_only,
    )
    if device is not None:
        dssaa = dssaa.to(device)
    return dssaa


def save_checkpoint(
    path: Union[str, Path],
    *,
    model: torch.nn.Module,
    dssaa: Optional[torch.nn.Module] = None,
    configs=None,
    scaler_mean: Optional[Sequence[float]] = None,
    scaler_scale: Optional[Sequence[float]] = None,
    gate: Optional[Dict[str, Any]] = None,
    response_lib: Optional[Dict[str, Any]] = None,
    domain: str = "",
    capacity: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Path:
    """Serialize a reproducible inference package to ``path`` (.pt)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    cfg_dict = configs_to_dict(configs) if configs is not None else {}
    theta = None
    if hasattr(model, "event_resp"):
        theta = float(getattr(model.event_resp, "theta", 0.5))

    gate_out = dict(gate or {})
    if "theta" not in gate_out and theta is not None:
        gate_out["theta"] = theta

    lib_out: Dict[str, Any] = {}
    if response_lib:
        lib_out = {
            "n_bps": int(len(response_lib.get("bps") or [])),
            "n_snippets": int(len(response_lib.get("snippets") or [])),
            "K": int(response_lib.get("K") or 0),
            "templates": _to_numpy(response_lib.get("templates")),
            "centers": _to_numpy(response_lib.get("centers")),
        }
        if response_lib.get("C") is not None:
            lib_out["C"] = _to_numpy(response_lib["C"])

    payload = {
        "version": CKPT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "capacity": capacity,
        "config": cfg_dict,
        "scaler": {
            "mean": np.asarray(scaler_mean, dtype=np.float64).reshape(-1).tolist()
            if scaler_mean is not None else None,
            "scale": np.asarray(scaler_scale, dtype=np.float64).reshape(-1).tolist()
            if scaler_scale is not None else None,
        },
        "gate": gate_out,
        "response_lib": lib_out,
        "metrics": metrics or {},
        "model_state": {k: v.detach().cpu() for k, v in model.state_dict().items()},
        "dssaa_state": (
            {k: v.detach().cpu() for k, v in dssaa.state_dict().items()}
            if dssaa is not None else None
        ),
        "extra": extra or {},
    }
    torch.save(payload, path)

    # human-readable sidecar (no weights)
    meta_path = path.with_suffix(".meta.json")
    meta = {
        "version": payload["version"],
        "created_at": payload["created_at"],
        "domain": domain,
        "capacity": capacity,
        "config": cfg_dict,
        "scaler": payload["scaler"],
        "gate": gate_out,
        "response_lib": {
            k: v for k, v in lib_out.items()
            if k not in ("templates", "centers", "C")
        },
        "metrics": _jsonable(metrics or {}),
        "has_dssaa": dssaa is not None,
        "n_model_params": int(sum(p.numel() for p in model.parameters())),
        "ckpt_path": str(path),
    }
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load_checkpoint_raw(path: Union[str, Path]) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"checkpoint 不存在: {path}\n"
            "请先训练并导出，例如:\n"
            "  python test/test_event_response_e2e.py SocialMedia_log "
            "--capacity lite --seq_len 28 --seasonal_period 7 --no_ctx --direction"
        )
    try:
        payload = torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        payload = torch.load(path, map_location="cpu")
    if not isinstance(payload, dict) or "model_state" not in payload:
        raise ValueError(f"非法 checkpoint 格式: {path}")
    return payload


def load_forecast_bundle(
    path: Union[str, Path],
    *,
    device: Optional[Union[str, torch.device]] = None,
    with_text: bool = False,
    calendar_mode: str = "short",
    no_ctx: bool = True,
) -> "ForecastBundle":
    """Load checkpoint → rebuild Model (+ optional DSSAA) ready for predict."""
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(device)

    payload = load_checkpoint_raw(path)
    cfg = dict_to_configs(payload["config"])
    model = build_model(cfg, device=device)

    # C_full is a variable-length buffer (resized by set_jump_series during train).
    # Pop it before load_state_dict to avoid size-mismatch errors, then restore.
    state = dict(payload["model_state"])
    C_full_state = state.pop("C_full", None)
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing:
        print(f"[ckpt] model missing keys ({len(missing)}): {missing[:5]}...")
    if unexpected:
        print(f"[ckpt] model unexpected keys ({len(unexpected)}): {unexpected[:5]}...")

    gate = dict(payload.get("gate") or {})
    theta = float(gate.get("theta", 0.5))
    if hasattr(model, "event_resp"):
        model.event_resp.theta = theta

    # restore response library templates if present separately
    lib = payload.get("response_lib") or {}
    if lib.get("templates") is not None and lib.get("centers") is not None:
        try:
            model.load_response_library(lib)
        except Exception as e:  # noqa: BLE001
            print(f"[ckpt] response library reload skipped: {e}")

    if lib.get("C") is not None:
        C_t = torch.tensor(np.asarray(lib["C"]), dtype=torch.float32).view(-1, 1)
        model.set_jump_series(C_t.to(device))
    elif C_full_state is not None and torch.is_tensor(C_full_state):
        # restore jump series from model_state when not duplicated in response_lib
        ready = bool(getattr(model, "C_ready", torch.tensor(False)).item())
        if int(C_full_state.size(0)) > 1 or ready:
            model.set_jump_series(C_full_state.to(device))

    dssaa = None
    if with_text and payload.get("dssaa_state") is not None:
        from layers.ds_saa_semantic import load_gpt2_encoder

        encoder = load_gpt2_encoder(device=device, use_hidden=not no_ctx)
        max_events = int(payload.get("extra", {}).get("max_events", 4))
        t_endo = bool(payload.get("extra", {}).get("t_endo", True))
        t_time_only = bool(payload.get("extra", {}).get("t_time_only", False))
        dssaa = build_dssaa(
            cfg, encoder=encoder, calendar_mode=calendar_mode,
            max_events=max_events, t_endo=t_endo, t_time_only=t_time_only,
            device=device,
        )
        miss, unexp = dssaa.load_state_dict(payload["dssaa_state"], strict=False)
        if miss:
            print(f"[ckpt] dssaa missing keys ({len(miss)}): {miss[:5]}...")
        if unexp:
            print(f"[ckpt] dssaa unexpected keys ({len(unexp)}): {unexp[:5]}...")
        model.attach_dssaa(dssaa)

    model.eval()
    if dssaa is not None:
        dssaa.eval()

    scaler = payload.get("scaler") or {}
    return ForecastBundle(
        model=model,
        dssaa=dssaa,
        config=cfg,
        scaler_mean=np.asarray(scaler.get("mean") or [0.0], dtype=np.float64),
        scaler_scale=np.asarray(scaler.get("scale") or [1.0], dtype=np.float64),
        gate=gate,
        domain=str(payload.get("domain") or ""),
        capacity=str(payload.get("capacity") or ""),
        metrics=dict(payload.get("metrics") or {}),
        version=str(payload.get("version") or ""),
        path=Path(path),
        device=device,
    )


class ForecastBundle:
    """In-memory inference package returned by ``load_forecast_bundle``."""

    def __init__(
        self,
        *,
        model,
        dssaa,
        config,
        scaler_mean: np.ndarray,
        scaler_scale: np.ndarray,
        gate: Dict[str, Any],
        domain: str,
        capacity: str,
        metrics: Dict[str, Any],
        version: str,
        path: Path,
        device: torch.device,
    ):
        self.model = model
        self.dssaa = dssaa
        self.config = config
        self.scaler_mean = scaler_mean.reshape(-1)
        self.scaler_scale = scaler_scale.reshape(-1)
        self.gate = gate
        self.domain = domain
        self.capacity = capacity
        self.metrics = metrics
        self.version = version
        self.path = path
        self.device = device

    @property
    def seq_len(self) -> int:
        return int(self.config.seq_len)

    @property
    def pred_len(self) -> int:
        return int(self.config.pred_len)

    def transform(self, y_raw: np.ndarray) -> np.ndarray:
        y = np.asarray(y_raw, dtype=np.float64).reshape(-1, 1)
        return ((y - self.scaler_mean) / (self.scaler_scale + 1e-12)).astype(np.float32)

    def inverse_transform(self, y_scaled: np.ndarray) -> np.ndarray:
        y = np.asarray(y_scaled, dtype=np.float64).reshape(-1, 1)
        return (y * (self.scaler_scale + 1e-12) + self.scaler_mean).astype(np.float64)

    def summary(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "path": str(self.path),
            "domain": self.domain,
            "capacity": self.capacity,
            "seq_len": self.seq_len,
            "pred_len": self.pred_len,
            "gate": self.gate,
            "has_dssaa": self.dssaa is not None,
            "metrics": self.metrics,
        }


# aliases used by social-sense adapter
load_forecast_model = load_forecast_bundle
