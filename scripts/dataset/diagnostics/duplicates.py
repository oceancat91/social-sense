"""Compare projection duplicates with whole-row duplicates for every platform CSV."""
from __future__ import annotations

import argparse
import csv
from collections import Counter

from ..common import DATASET_COLUMN_SPEC, directory_arg


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="剖析三列投影重复与整行完全重复")
    parser.add_argument("--src", required=True, type=directory_arg, help="包含五个平台 CSV 的目录")
    args = parser.parse_args(argv)

    for name, (platform_col, time_col, text_col) in DATASET_COLUMN_SPEC.items():
        file_path = args.src / name
        if not file_path.is_file():
            print(f"!! 缺失 {file_path}")
            continue
        print("=" * 76)
        print(f"### {name}")
        projection_rows: set[tuple[str, str, str]] = set()
        full_rows: set[tuple[str, ...]] = set()
        projection_counts: Counter[tuple[str, str, str]] = Counter()
        total = projection_duplicates = full_duplicates = 0
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            for row in reader:
                total += 1
                projection = (
                    (row.get(platform_col) or "").strip(),
                    (row.get(time_col) or "").strip(),
                    (row.get(text_col) or "").strip(),
                )
                projection_duplicates += projection in projection_rows
                projection_rows.add(projection)
                projection_counts[projection] += 1
                full = tuple((row.get(column) or "").strip() for column in columns)
                full_duplicates += full in full_rows
                full_rows.add(full)

        duplicate_rate = projection_duplicates / total * 100 if total else 0
        whole_rate = full_duplicates / total * 100 if total else 0
        print(f"  总行数        : {total:,}")
        print(f"  三列投影重复  : {projection_duplicates:,}  ({duplicate_rate:.1f}%)")
        print(f"  整行完全重复  : {full_duplicates:,}  ({whole_rate:.1f}%)")
        print(f"  去重后三列行数: {total - projection_duplicates:,}")
        print("  重复最多的组合:")
        for key, count in projection_counts.most_common(3):
            text = key[2][:36].replace("\n", "\\n").encode("unicode_escape").decode("ascii")
            print(f"    x{count:<6} time={key[1][:24]!r} text={text}")


if __name__ == "__main__":
    main()
