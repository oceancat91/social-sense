"""清洗 5 平台 CSV -> 统一「分析字段集」（18 列）。

目标 schema（跨平台统一，源为 18/31/29 列三套异构结构）：
    platform, content_type, content_id, parent_id, author_id, author_name,
    publish_time, text, like_count, comment_count, share_count, collect_count,
    view_count, source_url, topic_name, domain, keywords, ip_label

保留依据（舆情分析 + 时序分析真正消费的字段）：
  - 互动量 like/comment/share/collect/view  -> 时序热度 heat / topic_heat
  - content_type                            -> 区分主帖与评论（topic_volume vs volume）
  - topic_name / domain / keywords          -> 话题圈层分组
  - content_id / parent_id / author_* / source_url / ip_label -> 主键、溯源、茧房指数
删除依据（项目会用自己的 Skill2 词典/LLM 重新标注，属冗余标签）：
  - 上游模型预测标签：relevance_score_pred、sentiment_joy/anger/sadness/
    questioning/surprise/fear/primary_score
  - 采集侧派生标记：data_quality_flags、crawl_time、schema_version、category、
    basket、has_emoji、emoji_count、has_url、has_mention、has_hashtag、text_length

清洗动作（每步计数并报告）：
  C1 列裁剪      三套异构 schema -> 统一 18 列，缺失列置空
  C2 平台归一    快手 -> kuaishou
  C3 时间统一    各种写法 -> ISO8601（东八区）
  C4 文本规整    HTML 实体还原 / 零宽字符剔除 / 去 HTML 标签 / 换行空格规整
  C5 丢弃无效行  空文本、时间不可解析
  C6 主键去重    (platform, content_id)；无原生 ID 的源用 sha1(text|ts|author) 派生，
                 冲突保留互动量更高者（对齐清洗规则 C5）
  C7 数值补零    like/comment/share/collect/view 空值 -> 0

源文件不改动，结果写入 数据集/cleaned/ 下的 5 个同名文件 + all_cleaned.csv。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from functools import partial
from typing import Any

from ..common import (
    DOMAIN_ZH_TO_CODE,
    directory_arg,
    output_directory_arg,
    parse_time as parse_common_time,
)

csv.field_size_limit(20 * 1024 * 1024)

CST = timezone(timedelta(hours=8))
OUTPUT_COLUMNS = [
    "platform", "content_type", "content_id", "parent_id", "author_id",
    "author_name", "publish_time", "text",
    "like_count", "comment_count", "share_count", "collect_count", "view_count",
    "source_url", "topic_name", "domain", "keywords", "ip_label",
]

ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff\u00a0]")
HTML_TAG = re.compile(r"<[^>]+>")
MULTI_SPACE = re.compile(r"[ \t\f\v]+")
MULTI_NL = re.compile(r"\n{3,}")

# DOMAIN_ZH_TO_CODE 来自 agent/dataset/domains.json，快手 category/basket 用中文名反查。

# ---------------------------------------------------------------- 工具函数

def norm_text(value: Any) -> str:
    """C4：HTML 实体还原、零宽剔除、去标签、换行与空格规整。"""
    t = "" if value is None else str(value)
    t = html.unescape(t)
    t = HTML_TAG.sub(" ", t)
    t = ZERO_WIDTH.sub("", t)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = MULTI_SPACE.sub(" ", t)
    t = MULTI_NL.sub("\n\n", t)
    return t.strip()


def parse_time(value: Any) -> datetime | None:
    """C3：把各种时间写法解析为带时区的 datetime；无法解析返回 None。"""
    parsed = parse_common_time(value, allow_unix=True)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CST)
    return parsed.astimezone(CST)


def iso_cst(dt: datetime) -> str:
    return dt.astimezone(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def as_number(value: Any) -> float:
    """C7：数值列解析，空值/异常一律 0。"""
    if value is None:
        return 0.0
    s = str(value).strip().replace(",", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def as_int_str(value: float) -> str:
    """整数则输出整数串，否则保留原样，避免 395 变成 395.0。"""
    return str(int(value)) if float(value).is_integer() else repr(value)


def clean_id(value: Any) -> str:
    s = "" if value is None else str(value).strip()
    return "" if s in ("", "0", "null", "None", "nan") else s


def derive_content_id(text: str, ts_iso: str, author: str) -> str:
    """无原生 ID 的源：按 DATASET_SPEC 4.2 用 sha1(text|ts|author) 派生。"""
    raw = f"{text}|{ts_iso}|{author or ''}"
    return "hash:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def build_row(
    *,
    platform: str,
    content_type: str,
    content_id: str,
    parent_id: str,
    author_id: str,
    author_name: str,
    publish_time: str,
    text: str,
    like: float,
    comment: float,
    share: float,
    collect: float,
    view: float,
    source_url: str,
    topic_name: str,
    domain: str,
    keywords: str,
    ip_label: str,
) -> dict[str, str]:
    return {
        "platform": platform,
        "content_type": content_type,
        "content_id": content_id,
        "parent_id": parent_id,
        "author_id": author_id,
        "author_name": author_name,
        "publish_time": publish_time,
        "text": text,
        "like_count": as_int_str(like),
        "comment_count": as_int_str(comment),
        "share_count": as_int_str(share),
        "collect_count": as_int_str(collect),
        "view_count": as_int_str(view),
        "source_url": source_url,
        "topic_name": topic_name,
        "domain": domain,
        "keywords": keywords,
        "ip_label": ip_label,
    }


# ------------------------------------------------- 各平台行映射（C1 列裁剪）

def map_standard(row: dict[str, Any], platform: str) -> tuple[dict[str, str] | None, str]:
    """bili / weibo / xhs 共用的 18 列结构。无原生 ID/话题列，需派生。"""
    text = norm_text(row.get("text_structured_clean"))
    dt = parse_time(row.get("publish_time"))
    if not text:
        return None, "empty_text"
    if dt is None:
        return None, "bad_time"
    author = str(row.get("author_name") or "").strip()
    ts_iso = iso_cst(dt)
    content_id = derive_content_id(text, ts_iso, author)
    return build_row(
        platform=platform,
        content_type=str(row.get("content_type") or "").strip(),
        content_id=content_id,
        parent_id="",
        author_id="",
        author_name=author,
        publish_time=ts_iso,
        text=text,
        like=as_number(row.get("like_count")),
        comment=as_number(row.get("comment_count")),
        share=as_number(row.get("share_count")),
        collect=as_number(row.get("collect_count")),
        view=as_number(row.get("view_count")),
        source_url="",
        topic_name="",
        domain="",
        keywords="",
        ip_label="",
    ), ""


def map_douyin(row: dict[str, Any]) -> tuple[dict[str, str] | None, str]:
    """douyin 的 31 列结构：ID / 话题 / 属地齐备。"""
    text = norm_text(row.get("text_structured_clean"))
    dt = parse_time(row.get("publish_time"))
    if not text:
        return None, "empty_text"
    if dt is None:
        return None, "bad_time"
    author = str(row.get("author_name") or "").strip()
    ts_iso = iso_cst(dt)
    content_id = clean_id(row.get("comment_id")) or derive_content_id(text, ts_iso, author)
    return build_row(
        platform="douyin",
        content_type=str(row.get("content_type") or "").strip(),
        content_id=content_id,
        parent_id=clean_id(row.get("parent_comment_id")),
        author_id=clean_id(row.get("author_id_hash")),
        author_name=author,
        publish_time=ts_iso,
        text=text,
        like=as_number(row.get("like_count")),
        comment=as_number(row.get("comment_count")),
        share=as_number(row.get("share_count")),
        collect=as_number(row.get("collect_count")),
        view=as_number(row.get("view_count")),
        source_url=str(row.get("source_content_url") or "").strip(),
        topic_name=str(row.get("topic_name") or "").strip(),
        domain=str(row.get("domain") or "").strip().lower(),
        keywords=str(row.get("keywords") or "").strip(),
        ip_label=clean_id(row.get("ip_label")),
    ), ""


def map_kuaishou(row: dict[str, Any]) -> tuple[dict[str, str] | None, str]:
    """kuaishou 的 29 列结构（异构字段名）。

    注意：该源 comment_id / comment_user_id / parent_comment_id 全为 '0'，
    不可用，故 content_id 走派生、author_id 置空、parent_id 置空。
    category 与 basket 取值相同（中文领域名），反查为英文 domain 以便跨平台对齐。
    """
    text = norm_text(row.get("comment_text"))
    dt = parse_time(row.get("comment_time_iso")) or parse_time(row.get("comment_time"))
    if not text:
        return None, "empty_text"
    if dt is None:
        return None, "bad_time"
    author = str(row.get("comment_user") or "").strip()
    ts_iso = iso_cst(dt)
    content_id = clean_id(row.get("comment_id")) or derive_content_id(text, ts_iso, author)
    topic_zh = str(row.get("category") or row.get("basket") or "").strip()
    return build_row(
        platform="kuaishou",
        content_type=str(row.get("content_type") or "").strip(),
        content_id=content_id,
        parent_id=clean_id(row.get("parent_comment_id")),
        author_id=clean_id(row.get("comment_user_id")),
        author_name=author,
        publish_time=ts_iso,
        text=text,
        # 评论级互动：点赞=comment_like_count，回复=reply_count；share/collect/view 无对应口径
        like=as_number(row.get("comment_like_count")),
        comment=as_number(row.get("reply_count")),
        share=0.0,
        collect=0.0,
        view=0.0,
        source_url=str(row.get("post_url") or "").strip(),
        topic_name=topic_zh,
        domain=DOMAIN_ZH_TO_CODE.get(topic_zh, ""),
        keywords=str(row.get("keyword") or "").strip(),
        ip_label=clean_id(row.get("ip_location")),
    ), ""


SPECS = {
    "bili.csv": ("bilibili", partial(map_standard, platform="bilibili")),
    "weibo.csv": ("weibo", partial(map_standard, platform="weibo")),
    "xhs.csv": ("xhs", partial(map_standard, platform="xhs")),
    "douyin.csv": ("douyin", map_douyin),
    "kuaishou.csv": ("kuaishou", map_kuaishou),
}


def process_file(src_path: str, dst_path: str, platform: str, mapper) -> dict[str, Any]:
    """单文件清洗：C1-C7 + 主键去重，写出统一 18 列。"""
    stats = {
        "platform": platform,
        "rows_in": 0,
        "empty_text": 0,
        "bad_time": 0,
        "dup": 0,
        "rows_out": 0,
    }
    dedup: dict[tuple[str, str], dict[str, Any]] = {}

    with open(src_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats["rows_in"] += 1
            mapped, reason = mapper(row)
            if mapped is None:
                stats[reason] += 1
                continue
            key = (mapped["platform"], mapped["content_id"])
            interaction = (
                as_number(mapped["like_count"]) + as_number(mapped["comment_count"])
                + as_number(mapped["share_count"]) + as_number(mapped["collect_count"])
            )
            prev = dedup.get(key)
            if prev is None:
                dedup[key] = {"row": mapped, "interaction": interaction}
            else:
                stats["dup"] += 1
                if interaction > prev["interaction"]:
                    dedup[key] = {"row": mapped, "interaction": interaction}

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(
            out, fieldnames=OUTPUT_COLUMNS, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n"
        )
        writer.writeheader()
        for entry in dedup.values():
            writer.writerow(entry["row"])
    stats["rows_out"] = len(dedup)
    return stats


def merge_all(dst_dir: str, names: list[str]) -> int:
    """把 5 个清洗结果按统一表头合并为 all_cleaned.csv。"""
    merged_path = os.path.join(dst_dir, "all_cleaned.csv")
    total = 0
    with open(merged_path, "w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(
            out, fieldnames=OUTPUT_COLUMNS, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n"
        )
        writer.writeheader()
        for name in names:
            with open(os.path.join(dst_dir, name), "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    writer.writerow(row)
                    total += 1
    return total


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="清洗 5 平台 CSV 为统一分析字段集")
    parser.add_argument("--src", required=True, type=directory_arg, help="源目录（5 个平台 CSV）")
    parser.add_argument("--dst", required=True, type=output_directory_arg, help="输出目录")
    args = parser.parse_args(argv)

    # 兼容源文件直接放在 src 或 src 的嵌套同名子目录
    src = args.src
    if not os.path.exists(os.path.join(src, "bili.csv")):
        nested = os.path.join(src, os.path.basename(src))
        if os.path.exists(os.path.join(nested, "bili.csv")):
            src = nested

    print(f"源目录: {src}")
    print(f"输出目录: {args.dst}\n")
    header = (
        f"{'文件':<14}{'原行数':>10}{'空文本':>9}{'时间异常':>9}"
        f"{'主键重复':>9}{'输出':>10}"
    )
    print(header)
    print("-" * len(header))

    all_stats = []
    output_names = []
    for name, (platform, mapper) in SPECS.items():
        src_path = os.path.join(src, name)
        if not os.path.exists(src_path):
            print(f"!! 缺失 {src_path}")
            continue
        dst_path = os.path.join(args.dst, name)
        st = process_file(src_path, dst_path, platform, mapper)
        all_stats.append(st)
        output_names.append(name)
        print(
            f"{name:<14}{st['rows_in']:>10,}{st['empty_text']:>9,}"
            f"{st['bad_time']:>9,}{st['dup']:>9,}{st['rows_out']:>10,}"
        )

    print("-" * len(header))
    print(
        f"{'合计':<14}{sum(s['rows_in'] for s in all_stats):>10,}"
        f"{sum(s['empty_text'] for s in all_stats):>9,}"
        f"{sum(s['bad_time'] for s in all_stats):>9,}"
        f"{sum(s['dup'] for s in all_stats):>9,}"
        f"{sum(s['rows_out'] for s in all_stats):>10,}"
    )

    merged = merge_all(args.dst, output_names) if output_names else 0
    print(f"\n合并全量: all_cleaned.csv  {merged:,} 行")
    print(f"列({len(OUTPUT_COLUMNS)}): {','.join(OUTPUT_COLUMNS)}")
    print("\n输出目录: " + str(args.dst))


if __name__ == "__main__":
    sys.exit(main())
