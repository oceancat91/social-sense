"""Report missing values, duplicate rows and timestamp parseability before cleaning."""
from __future__ import annotations

import argparse
import csv
from collections import Counter

from ..common import DATASET_COLUMN_SPEC, directory_arg, parse_time


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="清洗前质量体检：空值、重复与时间可解析性")
    parser.add_argument("--src", required=True, type=directory_arg, help="包含五个平台 CSV 的目录")
    args = parser.parse_args(argv)

    print(f"{'文件':<14}{'总行':>9}{'空文字':>9}{'空时间':>9}{'时间异常':>9}{'重复三元组':>11}{'平台值':>12}")
    print("-" * 78)
    for name, (platform_col, time_col, text_col) in DATASET_COLUMN_SPEC.items():
        file_path = args.src / name
        if not file_path.is_file():
            print(f"{name:<14}缺失：{file_path}")
            continue

        total = empty_text = empty_time = bad_time = duplicates = 0
        seen: set[tuple[str, str, str]] = set()
        platforms: Counter[str] = Counter()
        minimum = maximum = None
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                total += 1
                platform = (row.get(platform_col) or "").strip()
                timestamp = (row.get(time_col) or "").strip()
                text = (row.get(text_col) or "").strip()
                platforms[platform] += 1
                empty_text += not bool(text)
                if not timestamp:
                    empty_time += 1
                else:
                    parsed = parse_time(timestamp)
                    if parsed is None:
                        bad_time += 1
                    else:
                        minimum = parsed if minimum is None or parsed < minimum else minimum
                        maximum = parsed if maximum is None or parsed > maximum else maximum
                key = (platform, timestamp, text)
                duplicates += key in seen
                seen.add(key)

        platform_summary = ",".join(f"{key}:{count}" for key, count in platforms.most_common(3))
        print(f"{name:<14}{total:>9,}{empty_text:>9,}{empty_time:>9,}{bad_time:>9,}{duplicates:>11,}  {platform_summary}")
        print(f"{'':14}时间范围: {minimum}  ->  {maximum}")


if __name__ == "__main__":
    main()
