"""
B站关键词 / 话题全站搜索

流程：关键词搜索视频（或话题）→ 导出结果列表 → 可选对前 N 个视频抓评论

用法示例：
  python B站关键词搜索.py 科比 --pages 1 --order pubdate
  python B站关键词搜索.py "某品牌 舆情" --pages 2 --max-videos 10 --crawl --comment-pages 2
  python B站关键词搜索.py 热搜话题 --search-type topic --pages 1
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from typing import Any

import requests

from bili_common import SCRIPT_DIR, enc_wbi, get_header

SEARCH_TYPE_URL = "https://api.bilibili.com/x/web-interface/wbi/search/type"
SEARCH_TYPE_URL_FALLBACK = "https://api.bilibili.com/x/web-interface/search/type"


def strip_em(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"</?em[^>]*>", "", text)


def parse_date(s: str | None) -> int | None:
    """YYYY-MM-DD → unix 秒（按 Asia/Shanghai 日界，避免本机时区漂移）。"""
    if not s:
        return None
    from zoneinfo import ZoneInfo
    dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return int(dt.timestamp())


def _to_number(v) -> float:
    """兼容 B 站搜索接口里 play 等字段为 int / '1234' / '31.5万'。"""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    try:
        if s.endswith("万"):
            return float(s[:-1] or 0) * 10000
        if s.endswith("亿"):
            return float(s[:-1] or 0) * 1e8
        return float(s)
    except ValueError:
        return 0.0


def normalize_video_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "bvid": item.get("bvid") or "",
        "aid": item.get("aid") or item.get("id") or "",
        "title": strip_em(item.get("title") or ""),
        "author": item.get("author") or "",
        "mid": item.get("mid") or "",
        "play": _to_number(item.get("play")),
        "danmaku": _to_number(item.get("video_review") or item.get("danmaku")),
        "favorites": _to_number(item.get("favorites")),
        "review": _to_number(item.get("review")),  # 评论数
        "pubdate": item.get("pubdate") or 0,
        "pubdate_str": (
            datetime.fromtimestamp(item["pubdate"]).strftime("%Y-%m-%d %H:%M:%S")
            if item.get("pubdate")
            else ""
        ),
        "duration": item.get("duration") or "",
        "tag": item.get("tag") or "",
        "description": strip_em(item.get("description") or ""),
        "arcurl": item.get("arcurl") or (
            f"https://www.bilibili.com/video/{item.get('bvid')}" if item.get("bvid") else ""
        ),
    }


def search_page(
    keyword: str,
    search_type: str,
    page: int,
    order: str,
    duration: int,
    tids: int,
    begin_ts: int | None,
    end_ts: int | None,
) -> dict[str, Any]:
    headers = get_header()
    params: dict[str, Any] = {
        "search_type": search_type,
        "keyword": keyword,
        "page": page,
        "order": order,
        "duration": duration,
        "tids": tids,
        "page_size": 42,
    }
    if begin_ts is not None:
        params["pubtime_begin_s"] = begin_ts
    if end_ts is not None:
        params["pubtime_end_s"] = end_ts

    # 优先 WBI 签名接口
    signed = enc_wbi(params, headers)
    resp = requests.get(SEARCH_TYPE_URL, params=signed, headers=headers, timeout=25)
    data = resp.json()
    if data.get("code") == 0:
        return data

    # 回退旧接口
    resp2 = requests.get(SEARCH_TYPE_URL_FALLBACK, params=params, headers=headers, timeout=25)
    data2 = resp2.json()
    if data2.get("code") != 0:
        raise RuntimeError(
            f"搜索失败：wbi code={data.get('code')} msg={data.get('message')}; "
            f"fallback code={data2.get('code')} msg={data2.get('message')}"
        )
    return data2


def normalize_topic_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic_id": item.get("topic_id") or item.get("id") or "",
        "title": strip_em(item.get("title") or item.get("name") or ""),
        "description": strip_em(item.get("description") or ""),
        "view": item.get("view") or item.get("mention") or 0,
        "discuss": item.get("discuss") or 0,
        "arcurl": item.get("arcurl") or item.get("url") or "",
    }


def search_all(
    keyword: str,
    search_type: str,
    pages: int,
    order: str,
    duration: int,
    tids: int,
    begin_ts: int | None,
    end_ts: int | None,
    max_items: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for page in range(1, pages + 1):
        print(f"搜索第 {page}/{pages} 页：keyword={keyword!r} type={search_type} order={order}")
        payload = search_page(
            keyword, search_type, page, order, duration, tids, begin_ts, end_ts
        )
        page_result = (payload.get("data") or {}).get("result") or []
        if not page_result:
            print("  本页无结果，停止翻页。")
            break

        for raw in page_result:
            if search_type == "video":
                row = normalize_video_item(raw)
                key = row["bvid"] or str(row["aid"])
            else:
                row = normalize_topic_item(raw)
                key = str(row.get("topic_id") or row.get("title"))

            if not key or key in seen:
                continue
            seen.add(key)
            results.append(row)
            if max_items and len(results) >= max_items:
                print(f"已达 max-videos/max-items={max_items}，停止搜索。")
                return results

        time.sleep(1.2)

    return results


def save_csv(rows: list[dict[str, Any]], path: str) -> None:
    if not rows:
        print("无数据可保存。")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"搜索结果已保存：{path}（{len(rows)} 条）")


def crawl_comments_for_videos(
    videos: list[dict[str, Any]],
    comment_pages: int,
    no_second: bool,
    mode: str,
    since: str | None = None,
    until: str | None = None,
) -> None:
    crawler = os.path.join(SCRIPT_DIR, "B站评论爬虫.py")
    if not os.path.isfile(crawler):
        raise FileNotFoundError(f"找不到评论爬虫：{crawler}")

    for i, v in enumerate(videos, 1):
        bvid = v.get("bvid")
        if not bvid:
            continue
        print("\n" + "=" * 60)
        print(f"[{i}/{len(videos)}] 抓评论：{bvid} | {v.get('title', '')[:40]}")
        cmd = [
            sys.executable,
            crawler,
            bvid,
            "--pages",
            str(comment_pages),
            "--mode",
            mode,
        ]
        if no_second:
            cmd.append("--no-second")
        if since:
            cmd.extend(["--since", since])
        if until:
            cmd.extend(["--until", until])
        subprocess.run(cmd, cwd=SCRIPT_DIR, check=False)
        time.sleep(2.0)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="B站关键词/话题全站搜索（可联动评论爬虫）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python B站关键词搜索.py 科比 --pages 1
  python B站关键词搜索.py "某事件" --order pubdate --since 2026-08-01 --until 2026-08-15
  python B站关键词搜索.py 某品牌 --pages 2 --max-videos 5 --crawl --comment-pages 2
  python B站关键词搜索.py 春节 --search-type topic --pages 1
""",
    )
    p.add_argument("keyword", help="搜索关键词 / 话题词")
    p.add_argument(
        "--search-type",
        choices=["video", "topic", "media_bangumi", "article"],
        default="video",
        help="搜索类型，默认 video",
    )
    p.add_argument("--pages", type=int, default=1, help="搜索结果翻页数，默认 1")
    p.add_argument(
        "--order",
        choices=["totalrank", "click", "pubdate", "dm", "stow", "scores"],
        default="totalrank",
        help="排序：综合/播放/最新/弹幕/收藏/评论",
    )
    p.add_argument(
        "--duration",
        type=int,
        default=0,
        choices=[0, 1, 2, 3, 4],
        help="时长筛选：0全部 1<10分 2=10-30 3=30-60 4>60",
    )
    p.add_argument("--tids", type=int, default=0, help="分区 tid，0=全部")
    p.add_argument("--since", default=None, help="发布时间起 YYYY-MM-DD")
    p.add_argument("--until", default=None, help="发布时间止 YYYY-MM-DD")
    p.add_argument(
        "--max-videos",
        type=int,
        default=20,
        help="最多保留结果条数（默认 20；0=不限制）",
    )
    p.add_argument(
        "--out",
        default=None,
        help="输出 CSV 路径（默认自动生成）",
    )
    p.add_argument(
        "--crawl",
        action="store_true",
        help="搜索后自动对视频抓取评论（仅 search-type=video）",
    )
    p.add_argument(
        "--comment-pages",
        type=int,
        default=2,
        help="每个视频评论页数上限（默认 2；0=不限制）",
    )
    p.add_argument("--no-second", action="store_true", help="评论不抓二级回复")
    p.add_argument(
        "--comment-mode",
        choices=["latest", "hot"],
        default="latest",
        help="评论排序",
    )
    return p


def main() -> None:
    os.chdir(SCRIPT_DIR)
    args = build_parser().parse_args()

    begin_ts = parse_date(args.since)
    end_ts = parse_date(args.until)
    if end_ts is not None:
        # 包含当天
        end_ts += 24 * 3600 - 1

    max_items = None if args.max_videos == 0 else args.max_videos
    rows = search_all(
        keyword=args.keyword,
        search_type=args.search_type,
        pages=max(1, args.pages),
        order=args.order,
        duration=args.duration,
        tids=args.tids,
        begin_ts=begin_ts,
        end_ts=end_ts,
        max_items=0 if max_items is None else max_items,
    )

    safe_kw = re.sub(r'[\\/:*?"<>|\s]+', "_", args.keyword)[:30]
    out = args.out or os.path.join(
        SCRIPT_DIR, f"search_{args.search_type}_{safe_kw}.csv"
    )
    save_csv(rows, out)

    if args.crawl:
        if args.search_type != "video":
            print("--crawl 仅支持 --search-type video，已跳过评论抓取。")
            return
        videos = [r for r in rows if r.get("bvid")]
        if not videos:
            print("没有可抓评论的视频。")
            return
        crawl_comments_for_videos(
            videos,
            comment_pages=args.comment_pages,
            no_second=args.no_second,
            mode=args.comment_mode,
            since=args.since,
            until=args.until,
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已中断。")
        sys.exit(130)
    except Exception as e:
        print(f"失败：{e}")
        sys.exit(1)
