"""Social-sense Flask 侧预测适配层。

实现委托给 ``workflow.forecast_ai.adapter``（无 Flask 依赖），
在应用内可::

    from app.services.forecast_service import load_forecast_model, predict
    svc = load_forecast_model()
    out = predict(svc, window_ot)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

logger = logging.getLogger(__name__)

_SOCIAL_SENSE_ROOT = Path(__file__).resolve().parents[3]


def _load_adapter_module():
    """Import workflow adapter without requiring a full package install."""
    root = _SOCIAL_SENSE_ROOT
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from workflow.forecast_ai.adapter import (  # type: ignore
        ForecastAdapter,
        find_latest_checkpoint,
        load_forecast_model as _load,
        predict as _predict,
    )
    return ForecastAdapter, find_latest_checkpoint, _load, _predict


def default_checkpoint_dir() -> Path:
    return _SOCIAL_SENSE_ROOT / "social_forecast" / "checkpoints"


def find_latest_checkpoint(ckpt_dir: Optional[Path] = None):
    _, find, _, _ = _load_adapter_module()
    return find(ckpt_dir)


class ForecastService:
    """Thin wrapper kept for backend naming consistency."""

    def __init__(self, adapter):
        self._adapter = adapter
        self.bundle = adapter.bundle

    @classmethod
    def load(
        cls,
        checkpoint: Optional[Union[str, Path]] = None,
        *,
        device: Optional[str] = None,
        with_text: bool = False,
    ) -> "ForecastService":
        ForecastAdapter, _, _, _ = _load_adapter_module()
        adapter = ForecastAdapter.load(
            checkpoint, device=device, with_text=with_text
        )
        logger.info("ForecastService loaded via workflow adapter")
        return cls(adapter)

    def summary(self) -> Dict[str, Any]:
        return self._adapter.summary()

    def predict(self, window: Sequence[float], **kwargs) -> Dict[str, Any]:
        return self._adapter.predict(window, **kwargs)

    def predict_series(
        self, series: Sequence[float], **kwargs
    ) -> List[Dict[str, Any]]:
        return self._adapter.predict_series(series, **kwargs)


def load_forecast_model(checkpoint=None, **kwargs) -> ForecastService:
    return ForecastService.load(checkpoint, **kwargs)


def predict(service: ForecastService, window: Sequence[float], **kwargs) -> Dict[str, Any]:
    return service.predict(window, **kwargs)
