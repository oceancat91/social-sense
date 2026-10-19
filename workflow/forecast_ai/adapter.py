"""不依赖 Flask 的预测适配层（供 workflow / 脚本调用）。

与 ``backend.app.services.forecast_service`` API 对齐：
  load_forecast_model / predict / predict_series
Flask 服务启动后也可直接用 backend 侧同名模块。
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

logger = logging.getLogger(__name__)

_FORECAST = Path(__file__).resolve().parents[2] / "social_forecast"
_CKPT_DIR = _FORECAST / "checkpoints"


def _ensure_path() -> Path:
    s = str(_FORECAST)
    if s not in sys.path:
        sys.path.insert(0, s)
    return _FORECAST


def _explicit_checkpoint() -> Optional[Path]:
    """读取 FORECAST_CHECKPOINT。生产部署必须用它显式指定权重。

    未设置时返回 None（回落到自动扫描）。设为相对路径时按 social_forecast/ 解析。
    文件不存在时返回 None 并告警，不让服务因为配置笔误而崩掉。
    """
    raw = os.getenv("FORECAST_CHECKPOINT", "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = _FORECAST / p
    if p.is_file():
        return p
    logger.warning("FORECAST_CHECKPOINT 指向的权重不存在: %s（回落到自动扫描）", p)
    return None


def find_latest_checkpoint(ckpt_dir: Optional[Path] = None) -> Optional[Path]:
    """选权重。

    优先级：
      1. FORECAST_CHECKPOINT 环境变量（显式，生产必须用这个）
      2. checkpoints/ 下递归扫描到的 *_numeric.pt（约 242 KiB，数值路径与完整权重一致）
      3. 其余非 smoke 权重中修改时间最新的
    递归扫描是因为重训产物放在 checkpoints/retrain_<日期>/ 子目录里；
    优先 numeric 是因为完整权重大约 950 MB，按 mtime 选中会把小内存机器直接打满。
    """
    explicit = _explicit_checkpoint()
    if explicit is not None:
        logger.info("forecast: 使用 FORECAST_CHECKPOINT 指定的权重 %s", explicit)
        return explicit

    d = Path(ckpt_dir) if ckpt_dir else _CKPT_DIR
    if not d.is_dir():
        return None
    pts = sorted(d.rglob("*.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
    real = [p for p in pts if "_smoke" not in p.name]
    numeric = [p for p in real if p.stem.endswith("_numeric")]
    chosen = (numeric or real or pts or [None])[0]
    if chosen is not None:
        logger.info(
            "forecast: 自动选中权重 %s（未设置 FORECAST_CHECKPOINT，生产建议显式指定）", chosen
        )
    return chosen


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
