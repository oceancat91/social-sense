"""清洗 5 个平台 CSV：仅保留「平台 / 时间序列 / 评论文字」三列。

清洗动作（每一步都计数并报告，便于核对）：
  1. 列裁剪        18/31/29 列 -> 3 列
  2. 平台值对齐    kuaishou 的「快手」-> kuaishou，与其余英文码一致
  3. 时间统一      各种格式 -> YYYY-MM-DD HH:MM:SS（均为东八区，去 offset 语义无损）
  4. 丢弃空文字    评论文字为空的行无分析价值
  5. 三列去重      输出只含 3 列，三列相同的行在输出中完全等价，保留无意义
                   （kuaishou 的重复源于采集笛卡尔积，同一条评论挂到多个 post_id）
  6. 文本规整      去首尾空白、CRLF/CR -> LF、HTML 实体还原

源文件不改动，结果写入 数据集/cleaned/。
"""
import argparse
import csv
import html
import os

from ..common import (
    DATASET_COLUMN_SPEC,
    directory_arg,
    output_directory_arg,
    parse_time,
)

PLATFORM_VALUE_MAP = {
    "kuaishou.csv": {"快手": "kuaishou"},
}


def norm_time(value: str) -> tuple[str, bool]:
    """把各种时间写法统一成 YYYY-MM-DD HH:MM:SS。返回 (结果, 是否成功)。"""
    text = (value or "").strip()
    if not text:
        return "", False
    parsed = parse_time(text)
    if parsed is None:
        return text, False
    return parsed.strftime("%Y-%m-%d %H:%M:%S"), True


def norm_text(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = html.unescape(s)
    return s.strip()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="清洗 5 平台 CSV 为轻量三列数据集")
    parser.add_argument("--src", required=True, type=directory_arg, help="源目录（5 个平台 CSV）")
    parser.add_argument("--dst", required=True, type=output_directory_arg, help="输出目录")
    args = parser.parse_args(argv)

    os.makedirs(args.dst, exist_ok=True)
    print(f"{'文件':<14}{'原行数':>9}{'空文字':>8}{'重复':>9}{'时间失败':>9}{'输出':>9}")
    print("-" * 62)

    grand_in = grand_out = 0
    for name, (pc, tc, xc) in DATASET_COLUMN_SPEC.items():
        pmap = PLATFORM_VALUE_MAP.get(name)
        src = os.path.join(args.src, name)
        dst = os.path.join(args.dst, name)

        seen = set()
        n_in = n_empty = n_dup = n_badtime = 0

        with open(src, "r", encoding="utf-8-sig", newline="") as f, \
             open(dst, "w", encoding="utf-8-sig", newline="") as out:
            w = csv.writer(out, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
            w.writerow(["platform", "time", "text"])

            for row in csv.DictReader(f):
                n_in += 1
                plat = (row.get(pc) or "").strip()
                if pmap:
                    plat = pmap.get(plat, plat)

                t, ok = norm_time(row.get(tc))
                if not ok:
                    n_badtime += 1

                x = norm_text(row.get(xc))
                if not x:
                    n_empty += 1
                    continue

                key = (plat, t, x)
                if key in seen:
                    n_dup += 1
                    continue
                seen.add(key)

                w.writerow([plat, t, x])

        n_out = len(seen)
        grand_in += n_in
        grand_out += n_out
        print(f"{name:<14}{n_in:>9,}{n_empty:>8,}{n_dup:>9,}{n_badtime:>9,}{n_out:>9,}")

    print("-" * 62)
    print(f"{'合计':<14}{grand_in:>9,}{'':>8}{'':>9}{'':>9}{grand_out:>9,}")
    print(f"\n输出目录: {args.dst}")


if __name__ == "__main__":
    main()
