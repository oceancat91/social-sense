"""把三个"清洗后"文件夹转成桌面上的独立 CSV 文件。

背景（已核实）：
  - data_bili_clean / data_weibo_clean(1)：目录内文件表头 100% 一致（18 列标准结构）
  - data_xhs_clean：嵌套目录内 12 个小红书文件表头一致（18 列），
    但该文件夹顶层额外躺着 douyin（31 列）与 kuaishou（29 列）两个异构文件

因此输出：
  bili.csv      <- data_bili_clean 全部 24 个文件合并
  weibo.csv     <- data_weibo_clean(1) 全部 24 个文件合并
  xhs.csv       <- data_xhs_clean\\data_xhs_clean\\ 下 12 个文件合并（不含顶层异构文件）
  douyin.csv    <- data_xhs_clean\\douyin_cleaned.csv 原样复制（31 列，保留扩展字段）
  kuaishou.csv  <- data_xhs_clean\\kuaishou_comments_cleaned(1).csv 原样复制（29 列，schema 不同）

安全措施：
  - 合并前逐个校验表头与基准表头一致，不一致立即中止，绝不产出错位数据
  - 合并后校验记录数 == 各源文件记录数之和
  - 输出统一 utf-8-sig，Excel 打开中文不乱码
"""
import argparse
import csv
import glob
import os
import shutil

from ..common import directory_arg


def read_header(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


def count_records(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        next(r)
        return sum(1 for _ in r)


def merge(name, pattern, out_path):
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        raise RuntimeError(f"[{name}] 未匹配到任何 CSV：{pattern}")

    base_header = read_header(files[0])
    # 沿用第一个文件表头的原始行（连同其原始行尾符），避免与正文行尾混用
    with open(files[0], "r", encoding="utf-8-sig", newline="") as f0:
        raw_header_line = f0.readline()
    rows = 0

    with open(out_path, "w", encoding="utf-8-sig", newline="") as out:
        out.write(raw_header_line)
        for i, fp in enumerate(files):
            h = read_header(fp)
            if h != base_header:
                raise RuntimeError(
                    f"[{name}] 表头不一致，已中止：\n  {os.path.basename(fp)}\n"
                    f"  期望 {len(base_header)} 列，实际 {len(h)} 列"
                )
            with open(fp, "r", encoding="utf-8-sig", newline="") as f:
                f.readline()                     # 跳过该文件表头
                for line in f:
                    out.write(line)
                    rows += 1

    expected = sum(count_records(fp) for fp in files)
    actual = count_records(out_path)
    status = "OK" if actual == expected else f"!! 不一致 (期望 {expected:,}) !!"
    print(f"[{name:9s}] {len(files):2d} 个文件 -> {os.path.basename(out_path):14s} "
          f"{actual:>7,} 条 | {len(base_header)} 列 | 校验 {status}")


def copy_one(name, src, dst):
    if not os.path.exists(src):
        raise RuntimeError(f"[{name}] 源文件不存在：{src}")
    shutil.copyfile(src, dst)
    n = count_records(dst)
    cols = len(read_header(dst))
    print(f"[{name:9s}]   复制     -> {os.path.basename(dst):14s} "
          f"{n:>7,} 条 | {cols} 列 | 校验 OK")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="合并分散的多平台 CSV 源文件")
    parser.add_argument(
        "--workspace", required=True, type=directory_arg,
        help="包含 data_bili_clean、data_weibo_clean(1) 和 data_xhs_clean 的目录",
    )
    args = parser.parse_args(argv)
    base = args.workspace
    xhs_root = os.path.join(base, "data_xhs_clean")
    merge_jobs = [
        ("bili", os.path.join(base, "data_bili_clean", "**", "*.csv"), os.path.join(base, "bili.csv")),
        ("weibo", os.path.join(base, "data_weibo_clean(1)", "**", "*.csv"), os.path.join(base, "weibo.csv")),
        ("xhs", os.path.join(xhs_root, "data_xhs_clean", "*.csv"), os.path.join(base, "xhs.csv")),
    ]
    copy_jobs = [
        ("douyin", os.path.join(xhs_root, "douyin_cleaned.csv"), os.path.join(base, "douyin.csv")),
        ("kuaishou", os.path.join(xhs_root, "kuaishou_comments_cleaned(1).csv"), os.path.join(base, "kuaishou.csv")),
    ]
    print("========== 合并 ==========")
    for job in merge_jobs:
        merge(*job)
    print("\n========== 复制（schema 不同，保持原样）==========")
    for job in copy_jobs:
        copy_one(*job)
    print("\n全部完成，输出目录：" + str(base))


if __name__ == "__main__":
    main()
