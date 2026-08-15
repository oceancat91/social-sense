"""
多平台多 Agent 架构层：消息契约 → 对齐器 → 融合器 → 主控 Agent。
"""

from .contract import SCHEMA_VERSION, normalize_report
from .align import align
from .fuse import fuse
from .master import run_master

__all__ = [
    "SCHEMA_VERSION",
    "normalize_report",
    "align",
    "fuse",
    "run_master",
]
