"""
平台适配器抽象基类。

每个平台一个 adapter，职责：把「平台原始数据」采集出来，并映射为
「跨平台原始字段」（见 CROSS_PLATFORM_FIELDS），交给 dataloader.clean_records
与 build_d_platform 复用，从而无缝接入 Skill2–6 与跨平台主控层。

跨平台原始字段契约（adapter 输出 → clean_records 输入）：
    platform, content_id, parent_id, author_id, text, ts_raw,
    like, reply_count, share_or_coin, source_url, ext

设计原则：
  - 采集失败 / 未配置凭证时，adapter 必须可降级（返回空或抛明确错误），
    不阻塞上层；上层可用「契约注入」（标准记录 / CSV）替代真实采集。
  - 每个 adapter 自带 cookie / UA 管理，与 B站 bili_cookie.txt 的约定一致。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AdapterError(RuntimeError):
    """采集器不可用 / 采集失败。"""


class CredentialMissing(AdapterError):
    """缺少登录凭证（cookie 等），无法真实采集。"""


class PlatformAdapter(ABC):
    """单一社交平台采集适配器。"""

    platform: str = ""          # 平台标识（bilibili/weibo/...，全小写）
    display_name: str = ""      # 展示名（B站/微博/...）
    # 跨平台原始字段（adapter 输出契约）
    FIELDS = (
        "platform", "content_id", "parent_id", "author_id", "text",
        "ts_raw", "like", "reply_count", "share_or_coin", "source_url", "ext",
    )

    def __init__(self, *, cookie_path: str | Path | None = None,
                 ua: str | None = None, timeout: int = 20) -> None:
        # cookie 路径：未显式传入时，用平台约定默认路径（<adapter目录>/<platform>_cookie.txt）
        if cookie_path is None:
            cookie_path = self._default_cookie_path()
        self.cookie_path = Path(cookie_path) if cookie_path else None
        self.ua = ua or DEFAULT_UA
        self.timeout = timeout

    # ---- 子类须实现的抽象接口 ---- #

    @abstractmethod
    def search(self, keyword: str, *, since: str | None = None,
               until: str | None = None, pages: int = 1,
               order: str = "default", max_items: int = 20) -> list[dict[str, Any]]:
        """按关键词检索内容实体（视频/微博/笔记/回答/作品）。

        返回统一 entity dict：
            {id, title, author, url, published_ts, like, comment, share, ext}
        """

    @abstractmethod
    def fetch_posts(self, entities: list[dict[str, Any]], *,
                    since: str | None = None, until: str | None = None,
                    pages: int = 2, mode: str = "latest") -> list[dict[str, Any]]:
        """抓取每个实体的帖子/评论，返回「跨平台原始字段」记录列表。

        mode: latest=按时间倒序（最新优先），hot=按热度排序。
        """

    # ---- 公共方法（子类可覆写/复用） ---- #

    def get_cookie(self) -> str:
        """读取登录 cookie；缺失则抛 CredentialMissing。"""
        if not self.cookie_path or not self.cookie_path.is_file():
            raise CredentialMissing(
                f"{self.display_name} 未找到 Cookie，请先配置: {self.cookie_path}"
            )
        cookie = self.cookie_path.read_text(encoding="utf-8").strip()
        if not cookie:
            raise CredentialMissing(f"{self.display_name} Cookie 为空: {self.cookie_path}")
        return cookie

    def get_headers(self) -> dict[str, str]:
        """构造请求头（含 cookie + UA）。无 cookie 时仅返回 UA。"""
        headers = {"User-Agent": self.ua}
        try:
            headers["Cookie"] = self.get_cookie()
        except CredentialMissing:
            pass
        return headers

    def _default_cookie_path(self) -> Path | None:
        """平台约定 cookie 默认路径：<本适配器目录>/<platform>_cookie.txt。

        云部署时 agent/ 可能只读，可用 AGENT_ADAPTER_COOKIE_DIR 环境变量
        指向可写目录（如 /app/agent_outputs/cookies），优先于源码目录。
        """
        if ADAPTER_COOKIE_DIR:
            return Path(ADAPTER_COOKIE_DIR) / f"{self.platform}_cookie.txt"
        base = Path(__file__).resolve().parent
        return base / f"{self.platform}_cookie.txt"

    # ---- 工具 ---- #

    @staticmethod
    def _f(v: Any, default: float = 0.0) -> float:
        try:
            if v is None or v == "":
                return default
            return float(v)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _s(v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    def _row(self, *, content_id: str, parent_id: str | None, author_id: str | None,
             text: str, ts_raw: Any, like: float = 0.0, reply_count: float = 0.0,
             share_or_coin: float = 0.0, source_url: str | None = None,
             ext: dict[str, Any] | None = None) -> dict[str, Any]:
        """构造一条符合契约的跨平台原始记录。"""
        return {
            "platform": self.platform,
            "content_id": content_id or None,
            "parent_id": parent_id,
            "author_id": author_id,
            "text": text,
            "ts_raw": ts_raw,
            "like": float(like),
            "reply_count": float(reply_count),
            "share_or_coin": float(share_or_coin),
            "source_url": source_url,
            "ext": ext or {},
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} platform={self.platform!r}>"


# 各平台通用 UA（可被具体 adapter 覆写）
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
)

# 供 adapter 运行时环境变量覆盖 cookie 目录（云部署时避免写源码目录）
ADAPTER_COOKIE_DIR = os.getenv("AGENT_ADAPTER_COOKIE_DIR", "")
