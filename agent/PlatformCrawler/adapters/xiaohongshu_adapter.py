"""
小红书平台适配器（edith.xiaohongshu.com web 接口）。

接口：
  - 搜索：GET /api/sns/web/v1/search/notes
  - 评论：GET /api/sns/web/v2/comment/page
凭证：xiaohongshu_cookie.txt（a1 / web_session 等）。

反爬说明：小红书接口依赖 x-s / x-t 签名（前端 JS 生成，AES 相关），
算法随版本更新易失效。本实现提供 JS 签名优先、纯 Python 占位降级；
字段映射与采集流程完整，签名失效时只需替换 _x_s / _x_t。
"""

from __future__ import annotations

import subprocess
import time
from typing import Any

import requests

from .base import PlatformAdapter
from .registry import register


def _x_s_js(url: str, data: str | None, cookie: str) -> str | None:
    import os
    script = os.getenv("XHS_SIGN_JS", "")
    if not script:
        return None
    try:
        proc = subprocess.run(
            ["node", script, url, data or "", cookie or ""],
            capture_output=True, text=True, timeout=15,
        )
        out = proc.stdout.strip()
        return out if out else None
    except Exception:
        return None


def _x_s_py(url: str, data: str | None, cookie: str) -> str:
    """x-s 纯 Python 占位（结构正确，可能被风控拦截）。"""
    import hashlib
    raw = f"{url}|{data or ''}|{cookie or ''}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:32]


def _x_t() -> str:
    return str(int(time.time() * 1000))


@register
class XiaohongshuAdapter(PlatformAdapter):
    platform = "xiaohongshu"
    display_name = "小红书"

    BASE = "https://edith.xiaohongshu.com"

    def get_headers(self) -> dict[str, str]:
        headers = super().get_headers()
        headers.setdefault("Origin", "https://www.xiaohongshu.com")
        headers.setdefault("Referer", "https://www.xiaohongshu.com/")
        headers.setdefault("Accept", "application/json, text/plain, */*")
        return headers

    def _signed(self, url: str, data: str | None = None) -> dict[str, str]:
        headers = self.get_headers()
        cookie = headers.get("Cookie", "")
        xs = _x_s_js(url, data, cookie) or _x_s_py(url, data, cookie)
        headers["x-s"] = xs
        headers["x-t"] = _x_t()
        return headers

    def search(self, keyword: str, *, since: str | None = None,
               until: str | None = None, pages: int = 1,
               order: str = "general", max_items: int = 20) -> list[dict[str, Any]]:
        """小红书搜索笔记，返回统一 entity dict。"""
        entities: list[dict[str, Any]] = []
        for page in range(1, pages + 1):
            if len(entities) >= max_items:
                break
            params = {
                "keyword": keyword, "page": page, "page_size": min(20, max_items),
                "search_id": _x_t(), "sort": order, "note_type": 0,
            }
            params_str = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{self.BASE}/api/sns/web/v1/search/notes?{params_str}"
            try:
                resp = requests.get(url, headers=self._signed(url), timeout=self.timeout)
                payload = resp.json() or {}
                items = payload.get("data", {}).get("items") or []
            except Exception:
                break
            if not items:
                break
            for it in items:
                if it.get("model_type") not in ("note", None):
                    continue
                note_id = it.get("id")
                if not note_id:
                    continue
                card = it.get("note_card") or {}
                user = card.get("user") or {}
                inter = card.get("interact_info") or {}
                xsec = it.get("xsec_token") or ""
                entities.append({
                    "id": str(note_id),
                    "title": (card.get("display_title") or "")[:80],
                    "author": user.get("nickname") or "",
                    "url": f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec}",
                    "published_ts": card.get("time"),
                    "like": self._f(inter.get("liked_count")),
                    "comment": self._f(inter.get("comment_count")),
                    "share": self._f(inter.get("share_count")),
                    "ext": {"note_id": note_id, "xsec_token": xsec,
                            "user_id": user.get("user_id")},
                })
                if len(entities) >= max_items:
                    break
            time.sleep(0.8)
        return entities

    def fetch_posts(self, entities: list[dict[str, Any]], *,
                    since: str | None = None, until: str | None = None,
                    pages: int = 2, mode: str = "latest") -> list[dict[str, Any]]:
        """抓取笔记评论（含笔记文案），返回跨平台原始字段。"""
        records: list[dict[str, Any]] = []
        for e in entities:
            note_id = str(e.get("ext", {}).get("note_id") or e.get("id") or "")
            if not note_id:
                continue
            if e.get("title"):
                records.append(self._row(
                    content_id=f"xhs:{note_id}",
                    parent_id=None,
                    author_id=str(e.get("ext", {}).get("user_id") or ""),
                    text=e.get("title") or "",
                    ts_raw=e.get("published_ts"),
                    like=e.get("like") or 0,
                    reply_count=e.get("comment") or 0,
                    share_or_coin=e.get("share") or 0,
                    source_url=e.get("url"),
                    ext={"post_type": "note", "note_id": note_id},
                ))
            records.extend(self._fetch_comments(note_id, e.get("ext", {}).get("xsec_token"), pages))
            time.sleep(0.8)
        return records

    def _fetch_comments(self, note_id: str, xsec_token: str | None,
                        pages: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(pages):
            params = {
                "note_id": note_id, "cursor": cursor, "top_comment_id": "",
                "image_formats": "jpg,webp,avif",
            }
            if xsec_token:
                params["xsec_token"] = xsec_token
            params_str = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{self.BASE}/api/sns/web/v2/comment/page?{params_str}"
            try:
                resp = requests.get(url, headers=self._signed(url), timeout=self.timeout)
                payload = resp.json() or {}
                comments = payload.get("data", {}).get("comments") or []
            except Exception:
                break
            if not comments:
                break
            for c in comments:
                user = c.get("user_info") or {}
                cid = str(c.get("id") or "")
                out.append(self._row(
                    content_id=f"xhs:c:{cid}",
                    parent_id=str(c.get("target_comment_id") or "") or None,
                    author_id=str(user.get("user_id") or ""),
                    text=(c.get("content") or "").strip(),
                    ts_raw=c.get("create_time"),
                    like=self._f(c.get("like_count")),
                    reply_count=self._f(c.get("sub_comment_count")),
                    share_or_coin=0.0,
                    source_url=f"https://www.xiaohongshu.com/explore/{note_id}",
                    ext={"uname": user.get("nickname") or "", "note_id": note_id},
                ))
            if not payload.get("data", {}).get("has_more"):
                break
            cursor = payload.get("data", {}).get("cursor") or ""
            time.sleep(0.5)
        return out


__all__ = ["XiaohongshuAdapter"]
