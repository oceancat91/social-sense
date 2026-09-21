"""Validate the three-column output written by ``clean_minimal``."""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from datetime import datetime

from ..common import DATASET_FILES, directory_arg

TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="校验轻量三列清洗结果")
    parser.add_argument("--src", required=True, type=directory_arg, help="clean_minimal 的输出目录")
    args = parser.parse_args(argv)

    print(f"{'文件':<14}{'行数':>9}{'列数':>6}{'平台值':>12}{'空文字':>8}{'重复':>7}{'时间格式':>10}")
    print("-" * 70)
    all_platforms: Counter[str] = Counter()
    total_rows = 0
    last_header: list[str] = []
    for name in DATASET_FILES:
        file_path = args.src / name
        if not file_path.is_file():
            raise FileNotFoundError(f"缺失清洗结果：{file_path}")
        rows = empty = duplicates = bad_time = malformed = 0
        platforms: Counter[str] = Counter()
        seen: set[tuple[str, str, str]] = set()
        minimum = maximum = None
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            last_header = next(reader, [])
            for row in reader:
                rows += 1
                if len(row) != 3:
                    malformed += 1
                    continue
                platform, timestamp, text = row
                platforms[platform] += 1
                all_platforms[platform] += 1
                empty += not bool(text)
                if not TIME_RE.match(timestamp):
                    bad_time += 1
                else:
                    parsed = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                    minimum = parsed if minimum is None or parsed < minimum else minimum
                    maximum = parsed if maximum is None or parsed > maximum else maximum
                key = (platform, timestamp, text)
                duplicates += key in seen
                seen.add(key)

        total_rows += rows
        valid = not any((duplicates, empty, bad_time, malformed)) and len(last_header) == 3
        status = "OK" if valid else "!! 异常"
        print(f"{name:<14}{rows:>9,}{len(last_header):>6}{str(dict(platforms)):>12}{empty:>8}{duplicates:>7}{bad_time:>10}  {status}")
        print(f"{'':14}时间范围 {minimum} -> {maximum}")
    print("-" * 70)
    print(f"合计 {total_rows:,} 行")
    print(f"平台分布: {dict(all_platforms)}")
    print(f"表头: {last_header}")


if __name__ == "__main__":
    main()
