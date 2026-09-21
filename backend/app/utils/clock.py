"""时间工具：统一生成 UTC 时间戳。

数据库列均为不带时区的 ``DateTime``（MySQL DATETIME / SQLite），
因此 ``utcnow()`` 返回 naive UTC，语义与历史 ``datetime.utcnow()`` 完全一致，
但改用带时区的 API 计算，避免 Python 3.12+ 的弃用告警。
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """当前 UTC 时间（naive，兼容不带时区的数据库列）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
