"""Inspect source CSV schemas and basic quality metrics without writing output."""
from __future__ import annotations

import argparse
import csv
from collections import Counter

from ..common import DATASET_FILES, directory_arg, parse_time

TEXT_HINTS = ("text_structured_clean", "comment_text", "post_caption")
TIME_HINTS = ("publish_time", "comment_time_iso", "comment_time", "collected_at")

csv.field_size_limit(20 * 1024 * 1024)


def pick(header: list[str], candidates: tuple[str, ...]) -> str | None:
    return next((candidate for candidate in candidates if candidate in header), None)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="检查 CSV 字段、数据量、时间范围与质量指标")
    parser.add_argument("--src", required=True, type=directory_arg, help="包含五个平台 CSV 的目录")
    args = parser.parse_args(argv)
    print(f"数据集目录: {args.src}\n")

    for name in DATASET_FILES:
        file_path = args.src / name
        if not file_path.is_file():
            print(f"!! 缺失 {name}")
            continue
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            text_col, time_col = pick(header, TEXT_HINTS), pick(header, TIME_HINTS)
            total = empty_text = duplicate_projection = duplicate_full = bad_time = 0
            minimum = maximum = None
            projected_rows: set[tuple[str, str, str]] = set()
            full_rows: set[tuple[str, ...]] = set()
            for row in reader:
                total += 1
                text = (row.get(text_col) or "").strip() if text_col else ""
                timestamp = (row.get(time_col) or "").strip() if time_col else ""
                platform = (row.get("platform") or "").strip()
                empty_text += not bool(text)
                if timestamp:
                    parsed = parse_time(timestamp)
                    if parsed is None:
                        bad_time += 1
                    else:
                        minimum = parsed if minimum is None or parsed < minimum else minimum
                        maximum = parsed if maximum is None or parsed > maximum else maximum
                projected = (platform, timestamp[:19], text)
                duplicate_projection += projected in projected_rows
                projected_rows.add(projected)
                full = tuple((row.get(column) or "") for column in header)
                duplicate_full += full in full_rows
                full_rows.add(full)

        print("=" * 100)
        print(f"{name}  总行 {total:,}  列数 {len(header)}")
        print(f"  列: {header}")
        print(f"  空文字 {empty_text:,}   时间不可解析 {bad_time:,}   三列重复 {duplicate_projection:,}   整行完全重复 {duplicate_full:,}")
        print(f"  时间范围: {minimum} -> {maximum}")

    print("\n" + "=" * 100)
    print("platform 列取值分布:")
    for name in DATASET_FILES:
        file_path = args.src / name
        if not file_path.is_file():
            continue
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "platform" not in reader.fieldnames:
                print(f"  {name}: 无 platform 列")
                continue
            values = Counter((row.get("platform") or "").strip() for row in reader)
        print(f"  {name}: {dict(values.most_common(5))}")


if __name__ == "__main__":
    main()
