"""不依赖 Flask 的预测适配层（供 workflow / 脚本调用）。

与 ``backend.app.services.forecast_service`` API 对齐：
  load_forecast_model / predict / predict_series
Flask 服务启动后也可直接用 backend 侧同名模块。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

_FORECAST = Path(__file__).resolve().parents[2] / "social_forecast"
_CKPT_DIR = _FORECAST / "checkpoints"


def _ensure_path() -> Path:
    s = str(_FORECAST)
    if s not in sys.path:
        sys.path.insert(0, s)
    return _FORECAST


def find_latest_checkpoint(ckpt_dir: Optional[Path] = None) -> Optional[Path]:
    d = Path(ckpt_dir) if ckpt_dir else _CKPT_DIR
    if not d.is_dir():
        return None
    pts = sorted(d.glob("*.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
    real = [p for p in pts if "_smoke" not in p.name]
    return (real or pts or [None])[0]


class ForecastAdapter:
    def __init__(self, bundle):
        self.bundle = bundle

    @classmethod
    def load(
        cls,
        checkpoint: Optional[Union[str, Path]] = None,
        *,
        device: Optional[str] = None,
        with_text: bool = False,
    ) -> "ForecastAdapter":
        _ensure_path()
        from checkpoint import load_forecast_model

        path = Path(checkpoint) if checkpoint else find_latest_checkpoint()
        if path is None or not Path(path).exists():
            raise FileNotFoundError(
                "未找到可用 checkpoint。请先训练导出或运行 "
                "social_forecast/scripts/export_smoke_checkpoint.py"
            )
        return cls(load_forecast_model(path, device=device, with_text=with_text))

    def summary(self) -> Dict[str, Any]:
        return self.bundle.summary()

    def predict(self, window: Sequence[float], **kwargs) -> Dict[str, Any]:
        _ensure_path()
        from inference import predict_window
        return predict_window(self.bundle, window, **kwargs).to_dict()

    def predict_series(
        self, series: Sequence[float], **kwargs
    ) -> List[Dict[str, Any]]:
        _ensure_path()
        from inference import predict_series
        return [r.to_dict() for r in predict_series(self.bundle, series, **kwargs)]


def load_forecast_model(checkpoint=None, **kwargs) -> ForecastAdapter:
    return ForecastAdapter.load(checkpoint, **kwargs)


def predict(adapter: ForecastAdapter, window: Sequence[float], **kwargs) -> Dict[str, Any]:
    return adapter.predict(window, **kwargs)
