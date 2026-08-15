"""
真实采集桥接：把 agent/PlatformCrawler 的 PlatformAdapter 接到后端 CrawlerService。

后端采集服务（CrawlerService）原本由 mock 数据源驱动；本模块把 agent/ 里已实现的
6 平台真实采集适配器（bilibili/weibo/douyin/xiaohongshu/zhihu/kuaishou）桥接进来，
让后端监控任务能采集真实舆情数据，最终流入 SentimentData 表供多 Agent 引擎消费。

设计要点：
  - 数据契约：adapter 输出「跨平台原始字段」，本模块映射为后端 record 格式
    （platform/content_type/content/author/url/published_at/like_count/comment_count/
    share_count），交给 PipelineService 的「清洗 → 情感分析 → 入库」复用。
  - 降级：无 cookie / 采集失败时抛 RealCrawlUnavailable，由 CrawlerService 回退 mock。
  - 路径：复用 agent_engine 的 AGENT_ROOT 环境变量定位 agent 代码目录。
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]   # backend/
REPO_ROOT = BACKEND_ROOT.parent                       # 仓库根（本地开发）

# 平台 -> 后端展示源名（与 mock_data_service.PLATFORM_PROFILES 对齐）
PLATFORM_SOURCE = {
    "bilibili": "哔哩哔哩",
    "weibo": "微博",
    "douyin": "抖音短视频",
    "xiaohongshu": "小红书",
    "zhihu": "知乎",
    "kuaishou": "快手",
}

_TZ_CN = timezone(timedelta(hours=8))


class RealCrawlUnavailable(RuntimeError):
    """真实采集不可用（缺 cookie / 采集失败），应由调用方回退 mock。"""


def agent_root() -> str:
    return os.getenv("AGENT_ROOT", str(REPO_ROOT / "agent"))


def _ensure_paths() -> None:
    """把 agent 目录加入 sys.path（幂等），供 `import PlatformCrawler`。"""
    root = agent_root()
    if root and root not in sys.path:
        sys.path.insert(0, root)


def is_available() -> bool:
    """agent PlatformCrawler 适配器目录是否齐备。"""
    return (Path(agent_root()) / "PlatformCrawler" / "adapters").exists()


def _parse_ts(value: Any) -> datetime | None:
    """解析 adapter 的 ts_raw（时间戳或字符串）为 UTC+8 aware datetime。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=_TZ_CN)
        except (OSError, OverflowError, ValueError):
            return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=_TZ_CN)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ_CN)
        return dt.astimezone(_TZ_CN)
    except ValueError:
        return None


def _author_of(row: dict[str, Any]) -> str:
    """优先取昵称，回退 author_id。"""
    ext = row.get("ext") or {}
    for key in ("uname", "nickname", "name", "screen_name", "author"):
        v = ext.get(key)
        if v:
            return str(v).strip()
    return str(row.get("author_id") or "").strip()


def _map_row(row: dict[str, Any], platform: str) -> dict[str, Any] | None:
    """跨平台原始字段 -> 后端 record（供 CleaningService.clean_batch 消费）。"""
    text = str(row.get("text") or "").strip()
    published_at = _parse_ts(row.get("ts_raw") or row.get("ts"))
    if not text or published_at is None:
        return None
    return {
        "platform": platform,
        "content_type": "comment" if row.get("parent_id") else "post",
        "content": text,
        "source": PLATFORM_SOURCE.get(platform, platform),
        "author": _author_of(row),
        "url": row.get("source_url"),
        "published_at": published_at,
        "like_count": int(float(row.get("like") or 0)),
        "comment_count": int(float(row.get("reply_count") or 0)),
        "share_count": int(float(row.get("share_or_coin") or 0)),
    }


def collect(
    keyword: str,
    platform: str,
    *,
    days: int = 14,
    max_entities: int = 5,
    comment_pages: int = 2,
    limit: int = 600,
) -> list[dict[str, Any]]:
    """真实采集：search 实体 + fetch_posts 评论，映射为后端 record 格式。

    任何失败抛 RealCrawlUnavailable，由调用方回退 mock。
    """
    if not is_available():
        raise RealCrawlUnavailable("agent PlatformCrawler 目录缺失")
    _ensure_paths()

    try:
        # pylint: disable=import-error
        from PlatformCrawler.adapters import get_adapter
        # pylint: enable=import-error
    except Exception as e:  # noqa: BLE001
        raise RealCrawlUnavailable(f"无法加载 PlatformCrawler.adapters: {e}") from e

    until = datetime.now().strftime("%Y-%m-%d")
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        adapter = get_adapter(platform)
    except Exception as e:  # noqa: BLE001
        raise RealCrawlUnavailable(f"不支持的平台 {platform!r}: {e}") from e

    # 显式检查 cookie（缺失即降级，不进入耗时搜索）
    try:
        adapter.get_cookie()
    except Exception as e:  # noqa: BLE001
        raise RealCrawlUnavailable(f"{platform} 未配置 cookie: {e}") from e

    try:
        entities = adapter.search(
            keyword, since=since, until=until, pages=1, max_items=max_entities
        )
        rows = adapter.fetch_posts(
            entities, since=since, until=until, pages=comment_pages, mode="latest"
        )
    except Exception as e:  # noqa: BLE001
        raise RealCrawlUnavailable(f"{platform} 真实采集失败: {e}") from e

    records: list[dict[str, Any]] = []
    for row in rows or []:
        mapped = _map_row(row, platform)
        if mapped:
            records.append(mapped)
        if len(records) >= limit:
            break

    logger.info(
        "真实采集完成: platform=%s keyword=%s entities=%d records=%d",
        platform, keyword, len(entities), len(records),
    )
    return records
