"""
PlatformCrawler 完整流水线

流程：
  1) 关键词全站检索（crawler）
  2) 逐视频抓评论（crawler）
  3) 清洗 C1–C8 + 组装 D_platform（dataloader，严格 DATASET_SPEC）

用法：
  python -m PlatformCrawler.pipeline 科比 --since 2026-07-01 --until 2026-08-15 --max-videos 3 --order click --rank-by play
  python -m PlatformCrawler.pipeline --from-csv path1.csv path2.csv --keyword 科比 --since 2026-07-01 --until 2026-08-15
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CRAWLER_DIR = ROOT / "crawler"
OUTPUT_DIR = ROOT / "outputs"


def _load_search_module():
    path = CRAWLER_DIR / "B站关键词搜索.py"
    spec = importlib.util.spec_from_file_location("bili_keyword_search", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载搜索模块: {path}")
    mod = importlib.util.module_from_spec(spec)
    # 搜索脚本依赖同目录 bili_common
    sys.path.insert(0, str(CRAWLER_DIR))
    spec.loader.exec_module(mod)
    return mod


def _parse_day(s: str) -> str:
    datetime.strptime(s, "%Y-%m-%d")
    return s


def run_search(
    keyword: str,
    *,
    pages: int = 1,
    max_videos: int = 5,
    order: str = "click",
    rank_by: str = "play",
    since: str | None = None,
    until: str | None = None,
    pool_size: int | None = None,
) -> list[dict[str, Any]]:
    """
    检索视频列表。
    rank_by:
      - play / review / favorites: 在候选池内按该指标降序，取 Top max_videos（热度最高）
      - search: 保持接口返回顺序，直接截断 max_videos
    pool_size: 可选，扩大候选池后再截断；默认按 rank_by 自动估算。
    返回的列表长度为 min(命中数, max_videos)。
    """
    mod = _load_search_module()
    begin_ts = mod.parse_date(since)
    end_ts = mod.parse_date(until)
    if end_ts is not None:
        end_ts += 24 * 3600 - 1

    if pool_size is not None:
        pool = max(1, int(pool_size))
    elif rank_by == "search":
        pool = max_videos
    else:
        pool = max(max_videos * 5, pages * 42, max_videos)

    rows = mod.search_all(
        keyword=keyword,
        search_type="video",
        pages=max(1, pages),
        order=order,
        duration=0,
        tids=0,
        begin_ts=begin_ts,
        end_ts=end_ts,
        max_items=pool,
    )

    if rank_by != "search":
        key_map = {"play": "play", "review": "review", "favorites": "favorites"}
        key = key_map[rank_by]
        rows = sorted(rows, key=lambda r: float(r.get(key) or 0), reverse=True)
        rows = rows[:max_videos]
        print(f"已按 {rank_by} 降序选取 Top-{max_videos} 视频：")
        for i, v in enumerate(rows, 1):
            print(
                f"  {i}. {v.get('bvid')} | play={v.get('play')} review={v.get('review')} "
                f"| {(v.get('title') or '')[:36]}"
            )
    else:
        rows = rows[:max_videos]

    out = OUTPUT_DIR / "search"
    out.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", keyword)[:40]
    csv_path = out / f"search_video_{safe}.csv"
    mod.save_csv(rows, str(csv_path))
    return rows


def run_search_heat_pool(
    keyword: str,
    *,
    pages: int = 3,
    max_videos: int = 100,
    order: str = "pubdate",
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    """
    话题热度时序专用搜索池：尽量覆盖爆发→至今的发布分布。
    默认按 pubdate，保留更多条目，不做播放量截断到个位数。
    """
    print(
        f"==> heat catalog search: pages={pages}, max={max_videos}, "
        f"order={order}, window=[{since}, {until}]"
    )
    return run_search(
        keyword,
        pages=pages,
        max_videos=max_videos,
        order=order,
        rank_by="search",
        since=since,
        until=until,
        pool_size=max_videos,
    )


def run_crawl_comments(
    videos: list[dict[str, Any]],
    *,
    comment_pages: int = 2,
    no_second: bool = False,
    mode: str = "latest",
    since: str | None = None,
    until: str | None = None,
) -> list[Path]:
    """
    逐视频抓评论。
    since/until：评论时间窗（YYYY-MM-DD，含首尾日），传给评论爬虫做过滤；
    mode=latest 时越过 since 会早停，便于扫到历史评论窗。
    """
    crawler_py = CRAWLER_DIR / "B站评论爬虫.py"
    csv_paths: list[Path] = []
    failures: list[str] = []

    for i, v in enumerate(videos, 1):
        bvid = v.get("bvid")
        if not bvid:
            continue
        print(f"\n[{i}/{len(videos)}] crawl comments: {bvid} | {(v.get('title') or '')[:40]}")
        if since or until:
            print(f"  comment time window: [{since or '-∞'}, {until or '+∞'}]")

        # 记录该 BV 旧文件 mtime，用于判断是否写出新文件
        prev_matches = {
            p.resolve(): p.stat().st_mtime for p in CRAWLER_DIR.glob(f"*_{bvid}.csv")
        }
        started = time.time()

        cmd = [
            sys.executable,
            str(crawler_py),
            str(bvid),
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
        proc = subprocess.run(cmd, cwd=str(CRAWLER_DIR), check=False)
        if proc.returncode != 0:
            failures.append(f"{bvid} exit={proc.returncode}")
            print(f"⚠ 爬取失败：{bvid}（exit={proc.returncode}）")
            time.sleep(1.0)
            continue

        # 优先：mtime 在本次开始之后更新/新建的同 BV 文件
        candidates = list(CRAWLER_DIR.glob(f"*_{bvid}.csv"))
        fresh = [
            p
            for p in candidates
            if p.stat().st_mtime >= started - 1
            or p.resolve() not in prev_matches
            or p.stat().st_mtime > prev_matches.get(p.resolve(), 0)
        ]
        if not fresh and candidates:
            # 回退：取该 BV 最新一个，但给出警告（可能是旧文件）
            fresh = [max(candidates, key=lambda x: x.stat().st_mtime)]
            print(f"⚠ 未检测到新 CSV，回退使用已有文件（可能陈旧）：{fresh[0].name}")

        if not fresh:
            failures.append(f"{bvid} missing_csv")
            print(f"⚠ 未找到评论 CSV：*{bvid}.csv")
        else:
            chosen = max(fresh, key=lambda x: x.stat().st_mtime)
            csv_paths.append(chosen)
            print(f"✓ 使用评论文件：{chosen.name}")

        time.sleep(1.0)

    # 去重保序
    seen = set()
    uniq: list[Path] = []
    for p in csv_paths:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        uniq.append(p)

    if failures:
        print("爬取问题汇总：" + "; ".join(failures))
    if videos and not uniq:
        raise RuntimeError(
            "所有视频评论均未成功产出 CSV。请检查 Cookie、限流或 B站评论爬虫 报错。"
        )
    return uniq


def run_dataloader(
    csv_paths: list[Path | str],
    *,
    keyword: str,
    since: str,
    until: str,
    granularity: str = "day",
    out_json: Path | None = None,
    heat_videos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # 保证可 import PlatformCrawler
    proj = ROOT.parent
    if str(proj) not in sys.path:
        sys.path.insert(0, str(proj))

    from PlatformCrawler.dataloader.builder import build_from_comment_csvs

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", keyword)[:40]
    if out_json is None:
        out_json = OUTPUT_DIR / f"D_platform_{safe}_{since}_{until}_{granularity}.json"

    # until 日含义：规范为 [start, end)；若用户给日期，用次日 00:00 作为 end
    end_exclusive = (
        datetime.strptime(until, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    d_platform = build_from_comment_csvs(
        list(csv_paths),
        keyword=keyword,
        time_range=(since, end_exclusive),
        granularity=granularity,
        platform="bilibili",
        out_path=out_json,
        heat_videos=heat_videos,
    )

    meta = d_platform["D_meta"]
    n_raw = int(meta.get("n_text_raw_in") or 0)
    n_text = int(meta.get("n_text") or 0)
    n_oor = int((meta.get("ext") or {}).get("n_out_of_range") or 0)
    ext = meta.get("ext") or {}

    # 关键告警：抓到了大量评论却被时间窗裁光（典型：页数不够，未翻到窗内）
    if n_raw > 0 and n_text == 0:
        print(
            "\n⚠⚠⚠ 严重告警：原始评论 "
            f"{n_raw} 条，但时间窗内有效文本为 0（out_of_range={n_oor}）。\n"
            "  常见原因：评论爬取页数不够，尚未翻到 --since/--until 区间；\n"
            "  或 CSV 来自未带时间窗的旧爬取。\n"
            "  建议：加大 --comment-pages，并确认爬虫已传 since/until。\n"
        )
    elif n_raw > 0 and n_oor / max(n_raw, 1) >= 0.8:
        print(
            f"\n⚠ 告警：{n_oor}/{n_raw} 条评论落在时间窗外被丢弃，"
            f"仅保留 {n_text} 条。请核对 since/until 与评论时间是否一致。\n"
        )

    print(f"D_platform saved: {out_json}")
    print(
        json.dumps(
            {
                "n_text": meta["n_text"],
                "n_text_raw_in": n_raw,
                "n_out_of_range": n_oor,
                "n_buckets": meta["n_buckets"],
                "empty_ratio": meta["empty_ratio"],
                "is_empty": meta["is_empty"],
                "stance_global": meta["stance_global"],
                "bias_score": meta["bias_score"],
                "n_heat_videos": ext.get("n_heat_videos"),
                "topic_heat_peak_ts": ext.get("topic_heat_peak_ts"),
                "topic_heat_peak": ext.get("topic_heat_peak"),
                "topic_volume_sum": ext.get("topic_volume_sum"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return d_platform


def run_full_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    if args.from_csv:
        csv_paths = [Path(p) for p in args.from_csv]
        for p in csv_paths:
            if not p.exists():
                raise FileNotFoundError(p)
        return run_dataloader(
            csv_paths,
            keyword=args.keyword,
            since=args.since,
            until=args.until,
            granularity=args.granularity,
            out_json=Path(args.out) if args.out else None,
        )

    heat_pages = int(getattr(args, "heat_search_pages", None) or max(args.search_pages, 2))
    heat_max = int(getattr(args, "heat_max_videos", None) or max(80, args.max_videos * 20))

    print("==> Step1a topic heat catalog (search pool)")
    heat_videos = run_search_heat_pool(
        args.keyword,
        pages=heat_pages,
        max_videos=heat_max,
        order="pubdate",
        since=args.since,
        until=args.until,
    )

    print("==> Step1b comment targets (Top-N by rank)")
    videos = run_search(
        args.keyword,
        pages=args.search_pages,
        max_videos=args.max_videos,
        order=args.order,
        rank_by=args.rank_by,
        since=args.since,
        until=args.until,
    )
    # 热度池并入评论候选去重：优先保证 Top-N 在池中
    if not videos and heat_videos:
        videos = heat_videos[: args.max_videos]

    if not videos:
        print("搜索无结果，仍将生成空 D_platform 时间轴（可含 topic_heat）。")
        return run_dataloader(
            [],
            keyword=args.keyword,
            since=args.since,
            until=args.until,
            granularity=args.granularity,
            out_json=Path(args.out) if args.out else None,
            heat_videos=heat_videos,
        )

    print("==> Step2 crawl comments")
    comment_since = getattr(args, "comment_since", None) or args.since
    comment_until = getattr(args, "comment_until", None) or args.until
    csv_paths = run_crawl_comments(
        videos,
        comment_pages=min(2, int(args.comment_pages)),
        no_second=args.no_second,
        mode=args.comment_mode,
        since=comment_since,
        until=comment_until,
    )
    print(f"comment csv files: {len(csv_paths)}")

    print("==> Step3 clean + build D_platform (+ topic_heat)")
    return run_dataloader(
        csv_paths,
        keyword=args.keyword,
        since=args.since,
        until=args.until,
        granularity=args.granularity,
        out_json=Path(args.out) if args.out else None,
        heat_videos=heat_videos or videos,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="PlatformCrawler 全流水线：检索→评论→清洗→D_platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  # 时段内按播放量选最热 3 个视频（推荐）
  python -m PlatformCrawler.pipeline 舞剧红楼梦 --since 2026-07-01 --until 2026-08-14 --max-videos 3 --order click --rank-by play

  # 按评论数选最热
  python -m PlatformCrawler.pipeline 舞剧红楼梦 --since 2026-07-01 --until 2026-08-14 --max-videos 3 --rank-by review

  # 只要最新发布（不按热度）
  python -m PlatformCrawler.pipeline 舞剧红楼梦 --since 2026-07-01 --until 2026-08-14 --order pubdate --rank-by search
""",
    )
    p.add_argument("keyword", nargs="?", default=None, help="话题关键词（--from-csv 时可与 --keyword 二选一）")
    p.add_argument("--keyword", dest="keyword_opt", default=None, help="话题关键词（显式）")
    p.add_argument(
        "--since",
        required=True,
        help="D_ts/话题热度长轴开始日 YYYY-MM-DD（含）；亦用于视频搜索发布窗",
    )
    p.add_argument(
        "--until",
        required=True,
        help="D_ts/话题热度长轴结束日 YYYY-MM-DD（含当日）",
    )
    p.add_argument(
        "--comment-since",
        default=None,
        help="评论抓取时间下界；默认与 --since 相同。长轴任务建议设为近 14 天",
    )
    p.add_argument(
        "--comment-until",
        default=None,
        help="评论抓取时间上界；默认与 --until 相同",
    )
    p.add_argument("--granularity", choices=["hour", "day"], default="day")
    p.add_argument("--search-pages", type=int, default=1, help="搜索翻页数；越大候选池越大")
    p.add_argument("--max-videos", type=int, default=3, help="最终选取并抓评论的视频数")
    p.add_argument(
        "--order",
        default="click",
        choices=["totalrank", "click", "pubdate", "dm", "stow", "scores"],
        help="B站搜索排序：click=播放 totalrank=综合 scores=评论 pubdate=最新",
    )
    p.add_argument(
        "--rank-by",
        default="play",
        choices=["play", "review", "favorites", "search"],
        help="本地再排序取 Top-N：play播放/review评论/favorites收藏/search保持接口顺序",
    )
    p.add_argument(
        "--comment-pages",
        type=int,
        default=2,
        help="每个视频一级评论页数（建议 2；流水线会上限截断为 2）",
    )
    p.add_argument("--comment-mode", choices=["latest", "hot"], default="latest")
    p.add_argument(
        "--heat-search-pages",
        type=int,
        default=3,
        help="话题热度时序：搜索翻页数（按 pubdate 拉发布分布）",
    )
    p.add_argument(
        "--heat-max-videos",
        type=int,
        default=100,
        help="话题热度时序：搜索池最大视频数",
    )
    p.add_argument("--no-second", action="store_true")
    p.add_argument("--from-csv", nargs="+", default=None, help="跳过爬取，直接从评论 CSV 建库")
    p.add_argument("--out", default=None, help="D_platform JSON 输出路径")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    _parse_day(args.since)
    _parse_day(args.until)
    kw = args.keyword_opt or args.keyword
    if not kw:
        raise SystemExit("请提供关键词，或使用: --from-csv ... --keyword xxx")
    args.keyword = kw
    run_full_pipeline(args)


if __name__ == "__main__":
    main()
