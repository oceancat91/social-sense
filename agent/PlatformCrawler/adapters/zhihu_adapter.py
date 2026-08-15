"""
知乎平台适配器（www.zhihu.com api，cookie 鉴权 + x-zse-96 签名）。

接口：
  - 搜索：GET /api/v4/search_v3?t=general&q=关键词
  - 评论：GET /api/v4/comment_v5/answers/{id}/root_comment
凭证：zhihu_cookie.txt（需含 z_c0、d_c0；无则匿名限流）。

说明：知乎 x-zse-96 签名由前端 JS 生成，存在失效风险；
本实现采用社区已知算法，若风控升级需更新 _x_zse_96。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any
from urllib.parse import urlparse

import requests

from .base import PlatformAdapter
from .registry import register

HTML_TAG_RE = None
try:
    import re as _re
    HTML_TAG_RE = _re.compile(r"<[^>]+>")
except Exception:  # pragma: no cover
    pass


def _strip_html(text: str) -> str:
    if HTML_TAG_RE:
        text = HTML_TAG_RE.sub("", text)
    return text.replace("&nbsp;", " ").strip()


def _x_zse_96(url: str, d_c0: str) -> str:
    """知乎 x-zse-96 签名（社区已知算法，版本 101_3_3.0）。"""
    # 固定前缀 + url + d_c0 组合后做 md5，再拼接固定尾巴
    source = "101_3_3.0+" + url + "+" + (d_c0 or "")
    digest = hashlib.md5(source.encode("utf-8")).hexdigest()
    return "2.0_" + digest


@register
class ZhihuAdapter(PlatformAdapter):
    platform = "zhihu"
    display_name = "知乎"

    BASE = "https://www.zhihu.com"

    def get_headers(self) -> dict[str, str]:
        headers = super().get_headers()
        headers.setdefault("Referer", "https://www.zhihu.com/")
        headers.setdefault("x-requested-with", "fetch")
        return headers

    def _signed_headers(self, url: str) -> dict[str, str]:
        headers = self.get_headers()
        try:
            cookie = self.get_cookie()
        except Exception:
            cookie = ""
        d_c0 = ""
        for part in cookie.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "d_c0":
                d_c0 = v
        headers["x-zse-96"] = _x_zse_96(url, d_c0)
        return headers

    def search(self, keyword: str, *, since: str | None = None,
               until: str | None = None, pages: int = 1,
               order: str = "default", max_items: int = 20) -> list[dict[str, Any]]:
        """知乎搜索，返回统一 entity dict（回答）。"""
        entities: list[dict[str, Any]] = []
        offset = 0
        limit = 20
        for _ in range(pages):
            if len(entities) >= max_items:
                break
            url = f"{self.BASE}/api/v4/search_v3"
            resp = requests.get(
                url,
                params={"t": "general", "q": keyword, "offset": offset, "limit": limit},
                headers=self._signed_headers(url), timeout=self.timeout,
            )
            data = (resp.json() or {}).get("data") or []
            if not data:
                break
            for obj in data:
                if obj.get("type") != "answer":
                    continue
                answer = obj.get("object") or {}
                aid = answer.get("id")
                if not aid:
                    continue
                author = answer.get("author") or {}
                question = answer.get("question") or {}
                entities.append({
                    "id": str(aid),
                    "title": _strip_html(answer.get("content") or "")[:80],
                    "author": author.get("name") or "",
                    "url": f"https://www.zhihu.com/question/{question.get('id')}/answer/{aid}",
                    "published_ts": answer.get("created_time"),
                    "like": self._f(answer.get("voteup_count")),
                    "comment": self._f(answer.get("comment_count")),
                    "share": 0.0,
                    "ext": {
                        "aid": aid, "qid": question.get("id"),
                        "author_id": author.get("id"),
                    },
                })
                if len(entities) >= max_items:
                    break
            offset += limit
            time.sleep(0.6)
        return entities

    def fetch_posts(self, entities: list[dict[str, Any]], *,
                    since: str | None = None, until: str | None = None,
                    pages: int = 2, mode: str = "latest") -> list[dict[str, Any]]:
        """抓取回答评论（含回答原文），返回跨平台原始字段。"""
        records: list[dict[str, Any]] = []
        for e in entities:
            aid = str(e.get("ext", {}).get("aid") or e.get("id") or "")
            if not aid:
                continue
            if e.get("title"):
                records.append(self._row(
                    content_id=f"zhihu:{aid}",
                    parent_id=None,
                    author_id=str(e.get("ext", {}).get("author_id") or ""),
                    text=e.get("title") or "",
                    ts_raw=e.get("published_ts"),
                    like=e.get("like") or 0,
                    reply_count=e.get("comment") or 0,
                    share_or_coin=0.0,
                    source_url=e.get("url"),
                    ext={"post_type": "answer", "aid": aid},
                ))
            records.extend(self._fetch_comments(aid, pages=pages))
            time.sleep(0.6)
        return records

    def _fetch_comments(self, aid: str, pages: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        offset = 0
        for _ in range(pages):
            url = f"{self.BASE}/api/v4/comment_v5/answers/{aid}/root_comment"
            try:
                resp = requests.get(
                    url,
                    params={"order_by": "score", "limit": 20, "offset": offset},
                    headers=self._signed_headers(url), timeout=self.timeout,
                )
                data = resp.json() or {}
                comments = data.get("data") or []
                paging = data.get("paging") or {}
            except Exception:
                break
            if not comments:
                break
            for c in comments:
                author = (c.get("author") or {}).get("member") or {}
                cid = str(c.get("id") or "")
                out.append(self._row(
                    content_id=f"zhihu:c:{cid}",
                    parent_id=str(c.get("root_comment_id") or "") or None,
                    author_id=str(author.get("id") or ""),
                    text=_strip_html(c.get("content") or ""),
                    ts_raw=c.get("created_time"),
                    like=self._f(c.get("like_count")),
                    reply_count=self._f(c.get("reply_comment_count")),
                    share_or_coin=0.0,
                    source_url=f"https://www.zhihu.com/question/0/answer/{aid}",
                    ext={"uname": author.get("name") or "", "aid": aid},
                ))
            if not paging.get("is_end", False):
                offset += len(comments)
                time.sleep(0.5)
            else:
                break
        return out


__all__ = ["ZhihuAdapter"]
