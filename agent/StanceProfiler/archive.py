"""
将单事件正式数据包归档到 dataset/events/<event_id>/
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "dataset"
EVENTS_ROOT = DATASET_ROOT / "events"
INDEX_PATH = DATASET_ROOT / "INDEX.md"
TZ = ZoneInfo("Asia/Shanghai")


def _safe_token(s: str, max_len: int = 24) -> str:
    s = re.sub(r"\s+", "", s)
    s = re.sub(r'[\\/:*?"<>|]+', "_", s)
    return (s or "event")[:max_len]


def make_event_id(platform: str, keyword: str, since: str, until: str) -> str:
    since_n = since.replace("-", "")[:8]
    until_n = until.replace("-", "")[:8]
    return f"{platform}_{_safe_token(keyword)}_{since_n}_{until_n}"


def _date_from_iso(iso: str | None) -> str:
    if not iso:
        return ""
    return str(iso)[:10]


def archive_event(
    d_platform: dict[str, Any],
    stance_profile: dict[str, Any],
    *,
    event_title: str | None = None,
    description: str = "",
    source_notes: str = "",
    event_id: str | None = None,
) -> Path:
    DATASET_ROOT.mkdir(parents=True, exist_ok=True)
    EVENTS_ROOT.mkdir(parents=True, exist_ok=True)

    meta_src = d_platform.get("D_meta") or {}
    platform = meta_src.get("platform") or "bilibili"
    keyword = meta_src.get("keyword") or "unknown"
    tr = meta_src.get("time_range") or {}
    since = _date_from_iso(tr.get("start"))
    until_end = _date_from_iso(tr.get("end"))
    # D_meta.end 多为开区间次日，索引展示用 until-1 日更贴近用户输入；这里仍记录规范 end
    until_display = since
    try:
        from datetime import timedelta

        until_display = (
            datetime.fromisoformat(str(tr.get("end"))).astimezone(TZ) - timedelta(days=1)
        ).strftime("%Y-%m-%d")
    except Exception:
        until_display = until_end

    eid = event_id or make_event_id(platform, keyword, since, until_display)
    event_dir = EVENTS_ROOT / eid
    event_dir.mkdir(parents=True, exist_ok=True)

    versions = meta_src.get("source_skill_versions") or {}
    meta = {
        "event_id": eid,
        "title": event_title or keyword,
        "keyword": keyword,
        "platform": platform,
        "platform_name_zh": "哔哩哔哩" if platform == "bilibili" else platform,
        "time_range": {
            "since": since,
            "until": until_display,
            "end_exclusive": until_end,
            "timezone": meta_src.get("timezone") or "Asia/Shanghai",
        },
        "granularity": meta_src.get("granularity") or "day",
        "description": description
        or f"单事件舆情数据集：关键词「{keyword}」，平台 {platform}。",
        "source": {
            "type": "bilibili_video_comments",
            "method": "keyword_search + comment_crawl + clean_c1c8 + stance_profiler",
            "tools": ["PlatformCrawler", "StanceProfiler"],
            "notes": source_notes
            or "公开视频评论；经清洗与立场画像后入库。仅供研究使用。",
        },
        "files": {
            "D_platform": "D_platform.json",
            "stance_profile": "stance_profile.json",
        },
        "stats": {
            "n_text": meta_src.get("n_text"),
            "n_buckets": meta_src.get("n_buckets"),
            "empty_ratio": meta_src.get("empty_ratio"),
            "stance_global": meta_src.get("stance_global"),
            "bias_score": meta_src.get("bias_score"),
            "is_empty": meta_src.get("is_empty"),
        },
        "schema_version": d_platform.get("schema_version") or "dataset_schema_v1",
        "created_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "pipeline_versions": {
            "platform_crawler": versions.get("platform_crawler"),
            "stance_profiler": versions.get("stance_profiler"),
        },
    }

    with (event_dir / "D_platform.json").open("w", encoding="utf-8") as f:
        json.dump(d_platform, f, ensure_ascii=False, indent=2)
    with (event_dir / "stance_profile.json").open("w", encoding="utf-8") as f:
        json.dump(stance_profile, f, ensure_ascii=False, indent=2)
    with (event_dir / "meta.json").open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    _upsert_index(meta)
    return event_dir


def _upsert_index(meta: dict[str, Any]) -> None:
    DATASET_ROOT.mkdir(parents=True, exist_ok=True)
    header = (
        "# 单事件数据集索引\n\n"
        "| event_id | 标题 | 平台 | 关键词 | since | until | n_text | stance_global | 路径 |\n"
        "|----------|------|------|--------|-------|-------|--------|---------------|------|\n"
    )
    row = (
        f"| {meta['event_id']} | {meta.get('title','')} | {meta.get('platform_name_zh') or meta.get('platform')} "
        f"| {meta.get('keyword')} | {meta['time_range'].get('since')} | {meta['time_range'].get('until')} "
        f"| {meta['stats'].get('n_text')} | {meta['stats'].get('stance_global')} "
        f"| `events/{meta['event_id']}/` |"
    )

    if not INDEX_PATH.exists():
        INDEX_PATH.write_text(header + row + "\n", encoding="utf-8")
        return

    lines = INDEX_PATH.read_text(encoding="utf-8").splitlines()
    # 去掉占位提示行与同 event_id 旧行
    kept = []
    for ln in lines:
        if "尚无入库" in ln:
            continue
        if ln.startswith("| ") and meta["event_id"] in ln.split("|")[1]:
            continue
        kept.append(ln)
    # 确保表头存在
    text = "\n".join(kept).strip() + "\n"
    if "| event_id |" not in text:
        text = header
    if not text.endswith("\n"):
        text += "\n"
    # 追加新行到表末
    if "|----------|" in text and row not in text:
        text = text.rstrip() + "\n" + row + "\n"
    INDEX_PATH.write_text(text, encoding="utf-8")
