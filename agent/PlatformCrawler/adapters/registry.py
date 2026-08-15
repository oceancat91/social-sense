"""
平台适配器注册表：平台标识 → PlatformAdapter 实例。

上层（pipeline / orchestrator）通过 get_adapter(platform) 获取对应采集器。
"""

from __future__ import annotations

from typing import Any

from .base import AdapterError, PlatformAdapter

# 支持的平台标识（与 backend.constants.PLATFORMS 对齐）
SUPPORTED_PLATFORMS = ("bilibili", "weibo", "douyin", "xiaohongshu", "zhihu", "kuaishou")

_ADAPTERS: dict[str, type[PlatformAdapter]] = {}


def register(adapter_cls: type[PlatformAdapter]) -> type[PlatformAdapter]:
    """把 adapter 类注册进表（幂等）。"""
    platform = adapter_cls.platform
    if not platform:
        raise ValueError(f"{adapter_cls.__name__} 缺少 platform 标识")
    _ADAPTERS[platform] = adapter_cls
    return adapter_cls


def get_adapter(platform: str, **kwargs: Any) -> PlatformAdapter:
    """按平台标识实例化 adapter。"""
    platform = (platform or "").strip().lower()
    if platform not in _ADAPTERS:
        raise AdapterError(
            f"不支持的平台: {platform!r}。可用: {sorted(_ADAPTERS)}"
        )
    return _ADAPTERS[platform](**kwargs)


def available_platforms() -> list[str]:
    return sorted(_ADAPTERS)


def build_all_adapters(**kwargs: Any) -> dict[str, PlatformAdapter]:
    """实例化全部已注册 adapter（多平台批量采集用）。"""
    return {p: cls(**kwargs) for p, cls in _ADAPTERS.items()}


# 触发各 adapter 模块注册（延迟 import 避免循环依赖）
def _import_adapters() -> None:
    from . import (  # noqa: F401
        bilibili_adapter,
        douyin_adapter,
        kuaishou_adapter,
        weibo_adapter,
        xiaohongshu_adapter,
        zhihu_adapter,
    )


_import_adapters()
