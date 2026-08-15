"""
快手平台适配器（www.kuaishou.com graphql 接口）。

接口：
  - 搜索：POST /graphql（operationName=visionSearchPhoto）
  - 评论：POST /graphql（operationName=commentListQuery）
凭证：kuaishou_cookie.txt（did、kuaishou.server.web_st 等）。

反爬说明：快手 graphql 的 query 字符串与字段会随前端版本更新，
需与当前 web 版对齐；本实现给出完整采集流程与字段映射。
"""

from __future__ import annotations

import time
from typing import Any

import requests

from .base import PlatformAdapter
from .registry import register

SEARCH_QUERY = """
query visionSearchPhoto($keyword: String, $pcursor: String, $searchSessionId: String, $page: String) {
  visionSearchPhoto(keyword: $keyword, pcursor: $pcursor, searchSessionId: $searchSessionId, page: $page) {
    result
    llsid
    webPageArea
    searchSessionId
    pcursor
    feeds {
      type
      author { id name following headerUrl }
      photo {
        id duration caption likeCount viewCount commentCount timestamp
        photoUrl workType
      }
    }
  }
}
"""

COMMENT_QUERY = """
query commentListQuery($photoId: String, $pcursor: String) {
  commentList(photoId: $photoId, pcursor: $pcursor) {
    commentCount
    pcursor
    comments {
      commentId content subCommentCount likeCount timestamp
      author { id name headerUrl }
    }
  }
}
"""


@register
class KuaishouAdapter(PlatformAdapter):
    platform = "kuaishou"
    display_name = "快手"

    BASE = "https://www.kuaishou.com"

    def get_headers(self) -> dict[str, str]:
        headers = super().get_headers()
        headers.setdefault("Referer", "https://www.kuaishou.com/")
        headers.setdefault("Content-Type", "application/json")
        return headers

    def _graphql(self, operation: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        resp = requests.post(
            f"{self.BASE}/graphql",
            json={"operationName": operation, "variables": variables, "query": query},
            headers=self.get_headers(), timeout=self.timeout,
        )
        return resp.json() or {}

    def search(self, keyword: str, *, since: str | None = None,
               until: str | None = None, pages: int = 1,
               order: str = "default", max_items: int = 20) -> list[dict[str, Any]]:
        """快手搜索作品，返回统一 entity dict。"""
        entities: list[dict[str, Any]] = []
        pcursor = ""
        session = ""
        for _ in range(pages):
            if len(entities) >= max_items:
                break
            variables = {
                "keyword": keyword, "pcursor": pcursor,
                "searchSessionId": session, "page": "search",
            }
            try:
                payload = self._graphql("visionSearchPhoto", SEARCH_QUERY, variables)
                result = payload.get("data", {}).get("visionSearchPhoto") or {}
                feeds = result.get("feeds") or []
            except Exception:
                break
            if not feeds:
                break
            for feed in feeds:
                photo = feed.get("photo") or {}
                author = feed.get("author") or {}
                pid = photo.get("id")
                if not pid:
                    continue
                entities.append({
                    "id": str(pid),
                    "title": (photo.get("caption") or "")[:80],
                    "author": author.get("name") or "",
                    "url": f"https://www.kuaishou.com/short-video/{pid}",
                    "published_ts": photo.get("timestamp"),
                    "like": self._f(photo.get("likeCount")),
                    "comment": self._f(photo.get("commentCount")),
                    "share": 0.0,
                    "ext": {"photo_id": pid, "author_id": author.get("id")},
                })
                if len(entities) >= max_items:
                    break
            pcursor = result.get("pcursor") or ""
            session = result.get("searchSessionId") or session
            if not pcursor:
                break
            time.sleep(0.8)
        return entities

    def fetch_posts(self, entities: list[dict[str, Any]], *,
                    since: str | None = None, until: str | None = None,
                    pages: int = 2, mode: str = "latest") -> list[dict[str, Any]]:
        """抓取作品评论（含作品文案），返回跨平台原始字段。"""
        records: list[dict[str, Any]] = []
        for e in entities:
            pid = str(e.get("ext", {}).get("photo_id") or e.get("id") or "")
            if not pid:
                continue
            if e.get("title"):
                records.append(self._row(
                    content_id=f"kuaishou:{pid}",
                    parent_id=None,
                    author_id=str(e.get("ext", {}).get("author_id") or ""),
                    text=e.get("title") or "",
                    ts_raw=e.get("published_ts"),
                    like=e.get("like") or 0,
                    reply_count=e.get("comment") or 0,
                    share_or_coin=0.0,
                    source_url=e.get("url"),
                    ext={"post_type": "video", "photo_id": pid},
                ))
            records.extend(self._fetch_comments(pid, pages=pages))
            time.sleep(0.8)
        return records

    def _fetch_comments(self, pid: str, pages: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        pcursor = ""
        for _ in range(pages):
            variables = {"photoId": pid, "pcursor": pcursor}
            try:
                payload = self._graphql("commentListQuery", COMMENT_QUERY, variables)
                result = payload.get("data", {}).get("commentList") or {}
                comments = result.get("comments") or []
            except Exception:
                break
            if not comments:
                break
            for c in comments:
                author = c.get("author") or {}
                cid = str(c.get("commentId") or "")
                out.append(self._row(
                    content_id=f"kuaishou:c:{cid}",
                    parent_id=None,
                    author_id=str(author.get("id") or ""),
                    text=(c.get("content") or "").strip(),
                    ts_raw=c.get("timestamp"),
                    like=self._f(c.get("likeCount")),
                    reply_count=self._f(c.get("subCommentCount")),
                    share_or_coin=0.0,
                    source_url=f"https://www.kuaishou.com/short-video/{pid}",
                    ext={"uname": author.get("name") or "", "photo_id": pid},
                ))
            pcursor = result.get("pcursor") or ""
            if not pcursor:
                break
            time.sleep(0.5)
        return out


__all__ = ["KuaishouAdapter"]
