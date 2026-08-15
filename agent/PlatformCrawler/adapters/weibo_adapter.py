"""
微博平台适配器（m.weibo.cn 接口，cookie 鉴权）。

接口：
  - 搜索：GET m.weibo.cn/api/container/getIndex?containerid=100103type=1&q=关键词
  - 评论：GET m.weibo.cn/comments/hotflow?id=mid&mid=mid
凭证：weibo_cookie.txt（需含 SUB= 登录态；无则不可用）。
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from .base import PlatformAdapter
from .registry import register

TZ = None
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover
    pass

HTML_TAG = re.compile(r"<[^>]+>")
SPAN_URL = re.compile(r'<a href="([^"]+)".*?</a>')


def _parse_weibo_time(value: Any) -> int | None:
    """微博 created_at（'Fri Aug 15 12:00:00 +0800 2026'）→ unix 秒。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        return int(dt.timestamp())
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(s)
        return int(dt.timestamp())
    except ValueError:
        return None


def _strip_html(text: str) -> str:
    # 保留 <a> 的标题文本，去掉其余标签
    text = SPAN_URL.sub(r"\1", text)
    text = HTML_TAG.sub("", text)
    return text.strip()


@register
class WeiboAdapter(PlatformAdapter):
    platform = "weibo"
    display_name = "微博"

    BASE = "https://m.weibo.cn"

    def search(self, keyword: str, *, since: str | None = None,
               until: str | None = None, pages: int = 1,
               order: str = "default", max_items: int = 20) -> list[dict[str, Any]]:
        """微博综合搜索，返回统一 entity dict（微博原文）。"""
        headers = self.get_headers()
        headers.setdefault("Referer", "https://m.weibo.cn/")
        containerid = f"100103type=1&q={keyword}"
        entities: list[dict[str, Any]] = []
        for page in range(1, pages + 1):
            if len(entities) >= max_items:
                break
            resp = requests.get(
                f"{self.BASE}/api/container/getIndex",
                params={"containerid": containerid, "page_type": "searchall", "page": page},
                headers=headers, timeout=self.timeout,
            )
            data = (resp.json() or {}).get("data") or {}
            for card in data.get("cards") or []:
                mblog = card.get("mblog")
                if not mblog:
                    continue
                mid = mblog.get("mid") or mblog.get("id")
                if not mid:
                    continue
                user = mblog.get("user") or {}
                entities.append({
                    "id": str(mid),
                    "title": _strip_html(mblog.get("text") or "")[:80],
                    "author": user.get("screen_name") or "",
                    "url": f"https://weibo.com/{user.get('id')}/{mid}",
                    "published_ts": _parse_weibo_time(mblog.get("created_at")),
                    "like": self._f(mblog.get("attitudes_count")),
                    "comment": self._f(mblog.get("comments_count")),
                    "share": self._f(mblog.get("reposts_count")),
                    "ext": {"mid": mid, "uid": user.get("id")},
                })
                if len(entities) >= max_items:
                    break
            time.sleep(0.8)
        return entities

    def fetch_posts(self, entities: list[dict[str, Any]], *,
                    since: str | None = None, until: str | None = None,
                    pages: int = 2, mode: str = "latest") -> list[dict[str, Any]]:
        """抓取微博评论（含原文作为首条），返回跨平台原始字段。"""
        headers = self.get_headers()
        headers.setdefault("Referer", "https://m.weibo.cn/")
        records: list[dict[str, Any]] = []
        for e in entities:
            mid = str(e.get("id") or e.get("ext", {}).get("mid") or "")
            if not mid:
                continue
            # 原文作为一条记录（内容正文）
            if e.get("title"):
                records.append(self._row(
                    content_id=f"weibo:{mid}",
                    parent_id=None,
                    author_id=str(e.get("ext", {}).get("uid") or ""),
                    text=e.get("title") or "",
                    ts_raw=e.get("published_ts"),
                    like=e.get("like") or 0,
                    reply_count=e.get("comment") or 0,
                    share_or_coin=e.get("share") or 0,
                    source_url=e.get("url"),
                    ext={"post_type": "original", "mid": mid},
                ))
            # 评论
            records.extend(self._fetch_comments(mid, headers, pages=pages))
            time.sleep(0.8)
        return records

    def _fetch_comments(self, mid: str, headers: dict[str, str],
                        pages: int) -> list[dict[str, Any]]:
        """抓取单条微博评论（hotflow 接口）。"""
        out: list[dict[str, Any]] = []
        max_id = 0
        for _ in range(pages):
            try:
                resp = requests.get(
                    f"{self.BASE}/comments/hotflow",
                    params={"id": mid, "mid": mid, "max_id_type": 0, "max_id": max_id},
                    headers=headers, timeout=self.timeout,
                )
                data = (resp.json() or {}).get("data") or {}
                comments = data.get("data") or []
            except Exception:
                break
            if not comments:
                break
            for c in comments:
                user = c.get("user") or {}
                cid = str(c.get("id") or "")
                out.append(self._row(
                    content_id=f"weibo:c:{cid}",
                    parent_id=str(c.get("rootid") or "") or None,
                    author_id=str(user.get("id") or ""),
                    text=_strip_html(c.get("text") or ""),
                    ts_raw=_parse_weibo_time(c.get("created_at")),
                    like=self._f(c.get("like_count")),
                    reply_count=self._f(c.get("total_number")) - self._f(c.get("like_count")),
                    share_or_coin=0.0,
                    source_url=f"https://weibo.com/{user.get('id')}/{mid}",
                    ext={"uname": user.get("screen_name") or "", "mid": mid},
                ))
            # 下一页
            new_max = data.get("max_id")
            if not new_max or str(new_max) == str(max_id):
                break
            max_id = new_max
            time.sleep(0.5)
        return out


__all__ = ["WeiboAdapter"]
