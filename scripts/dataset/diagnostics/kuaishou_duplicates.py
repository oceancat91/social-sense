"""Show which fields vary within duplicate Kuaishou comment groups."""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict

from ..common import file_arg


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="分析快手重复评论组内发生变化的字段")
    parser.add_argument("--input", required=True, type=file_arg, help="快手 CSV 文件")
    args = parser.parse_args(argv)

    groups: defaultdict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        for row in reader:
            key = ((row.get("comment_time_iso") or "").strip(), (row.get("comment_text") or "").strip())
            groups[key].append(row)

    duplicates = {key: rows for key, rows in groups.items() if len(rows) > 1}
    print(f"总组数: {len(groups):,}")
    print(f"含重复的组数: {len(duplicates):,}")
    print(f"重复组内总行数: {sum(len(rows) for rows in duplicates.values()):,}")
    print("\n--- 变化列分析（对最大的 200 个重复组）---")
    varying: Counter[str] = Counter()
    for _, rows in sorted(duplicates.items(), key=lambda item: -len(item[1]))[:200]:
        for column in columns:
            if len({(row.get(column) or "").strip() for row in rows}) > 1:
                varying[column] += 1
    for column, count in varying.most_common():
        print(f"  {column:22s} 在 {count}/200 组内发生变化")

    print("\n--- 逐列变化详情（最大 3 组）---")
    for key, rows in sorted(duplicates.items(), key=lambda item: -len(item[1]))[:3]:
        print(f"\n  组: {len(rows)} 行 | time={key[0]} | text={key[1][:30]!r}")
        for column in columns:
            values = Counter((row.get(column) or "").strip() for row in rows)
            if len(values) > 1:
                shown = ", ".join(f"{value[:28]}(x{count})" for value, count in values.most_common(4))
                print(f"    变化 {column:20s}: {shown}")
            else:
                value = next(iter(values), "")
                print(f"    固定 {column:20s}: {value[:40]}")


if __name__ == "__main__":
    main()
