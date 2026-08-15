"""
B站平台适配器：复用现有 crawler/ 脚本（关键词搜索 + 评论爬虫），
把 B站评论 CSV 映射为跨平台原始字段，交给 dataloader 复用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..dataloader.cleaner import map_bilibili_csv_row, load_bilibili_comment_csv
from .base import PlatformAdapter
from .registry import register


@register
class BilibiliAdapter(PlatformAdapter):
    platform = "bilibili"
    display_name = "B站"

    def search(self, keyword: str, *, since: str | None = None,
               until: str | None = None, pages: int = 1,
               order: str = "click", max_items: int = 20) -> list[dict[str, Any]]:
        """B站视频检索，返回统一 entity dict。"""
        from ..pipeline import run_search

        rank_by = "search" if order in ("pubdate",) else "play"
        videos = run_search(
            keyword,
            pages=pages,
            max_videos=max_items,
            order=order,
            rank_by=rank_by,
            since=since,
            until=until,
        )
        return [
            {
                "id": v.get("bvid") or v.get("aid"),
                "title": v.get("title") or "",
                "author": v.get("author") or "",
                "url": f"https://www.bilibili.com/video/{v.get('bvid')}",
                "published_ts": v.get("pubdate"),
                "like": self._f(v.get("like")),
                "comment": self._f(v.get("review")),
                "share": self._f(v.get("favorites")),
                "ext": dict(v),
            }
            for v in videos
        ]

    def fetch_posts(self, entities: list[dict[str, Any]], *,
                    since: str | None = None, until: str | None = None,
                    pages: int = 2, mode: str = "latest") -> list[dict[str, Any]]:
        """逐视频抓评论，返回跨平台原始字段记录。"""
        from ..pipeline import run_crawl_comments

        videos = [
            {"bvid": e["id"], "title": e.get("title"), **e.get("ext", {})}
            for e in entities if e.get("id")
        ]
        if not videos:
            return []

        csv_paths = run_crawl_comments(
            videos,
            comment_pages=pages,
            no_second=False,
            mode=mode,
            since=since,
            until=until,
        )
        records: list[dict[str, Any]] = []
        for p in csv_paths:
            records.extend(load_bilibili_comment_csv(p))
        return records


# 兼容旧导入路径：map 函数仍可从 cleaner 直接取
__all__ = ["BilibiliAdapter", "map_bilibili_csv_row", "load_bilibili_comment_csv"]
