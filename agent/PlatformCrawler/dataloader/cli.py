"""
仅跑清洗+建库：

  python -m PlatformCrawler.dataloader.cli --csv a.csv b.csv --keyword 话题 --since 2026-07-01 --until 2026-08-01
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .builder import build_from_comment_csvs


def main() -> None:
    p = argparse.ArgumentParser(description="评论 CSV → 清洗 → D_platform")
    p.add_argument("--csv", nargs="+", required=True, help="B站评论 CSV 路径")
    p.add_argument("--keyword", required=True)
    p.add_argument("--since", required=True, help="YYYY-MM-DD 含")
    p.add_argument("--until", required=True, help="YYYY-MM-DD 含当日")
    p.add_argument("--granularity", choices=["hour", "day"], default="day")
    p.add_argument("--out", required=True, help="输出 D_platform JSON")
    args = p.parse_args()

    from datetime import datetime, timedelta

    end_exclusive = (
        datetime.strptime(args.until, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    d = build_from_comment_csvs(
        args.csv,
        keyword=args.keyword,
        time_range=(args.since, end_exclusive),
        granularity=args.granularity,
        out_path=args.out,
    )
    meta = d["D_meta"]
    print(
        f"OK n_text={meta['n_text']} n_buckets={meta['n_buckets']} "
        f"empty_ratio={meta['empty_ratio']:.3f} is_empty={meta['is_empty']} -> {args.out}"
    )


if __name__ == "__main__":
    main()
