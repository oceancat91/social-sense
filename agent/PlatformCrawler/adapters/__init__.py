"""
平台适配器包：每平台一个 adapter，产出「跨平台原始字段」，
复用 dataloader 的 clean_records / build_d_platform，无缝接入 Skill2–6。
"""

from .base import AdapterError, CredentialMissing, PlatformAdapter
from .registry import (
    SUPPORTED_PLATFORMS,
    available_platforms,
    build_all_adapters,
    get_adapter,
    register,
)

__all__ = [
    "PlatformAdapter",
    "AdapterError",
    "CredentialMissing",
    "SUPPORTED_PLATFORMS",
    "register",
    "get_adapter",
    "available_platforms",
    "build_all_adapters",
]
