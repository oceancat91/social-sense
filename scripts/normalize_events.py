# -*- coding: utf-8 -*-
"""把「政策舆情」7 个事件归一化成统一 schema，并导出每个事件的日度时序。

7 个事件的原始字段互不相同（英文列 / 中文列 / Excel 序列号 / 只有情绪分没有时间），
这里逐个适配，统一成：
    event_id, time, text, likes, comments, reposts, sentiment

输出：
    tmp/events_unified.parquet        全量归一行
    tmp/event_series/<event_id>.csv   每个事件的日度时序（供预测与 3D 使用）
    tmp/event_index.json              事件索引（标题/时间范围/条数/互动量）
"""
from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

import pandas as pd

BASE = Path(r"D:\HuaweiMoveData\Users\32002\Desktop\social-sense\tmp\datasetB\政策舆情研究数据集")
OUT = Path(r"D:\HuaweiMoveData\Users\32002\Desktop\social-sense\tmp")
SERIES_DIR = OUT / "event_series"
SERIES_DIR.mkdir(parents=True, exist_ok=True)

NUM = re.compile(r"[^\d.\-]")


def to_num(s):
    if pd.isna(s):
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    t = NUM.sub("", str(s))
    try:
        return float(t) if t else 0.0
    except ValueError:
        return 0.0


def parse_time(s):
    """尽力解析各种时间写法：2018/1/3 22:05、2023-02-28 12:49:00、2021年10月16日 12:00、Excel 序列号。"""
    if pd.isna(s):
        return pd.NaT
    if isinstance(s, (int, float)):
        # Excel 序列号（1900 基准）
        try:
            return pd.Timestamp("1899-12-30") + pd.to_timedelta(float(s), unit="D")
        except Exception:
            return pd.NaT
    txt = str(s).strip()
    txt = txt.replace("年", "-").replace("月", "-").replace("日", " ").replace("/", "-")
    txt = re.sub(r"\s+", " ", txt).strip()
    return pd.to_datetime(txt, errors="coerce")


def frame(rows, event_id):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["event_id"] = event_id
    for col in ("likes", "comments", "reposts", "sentiment"):
        if col not in df:
            df[col] = 0.0
    return df[["event_id", "time", "text", "likes", "comments", "reposts", "sentiment"]]


def load_tiaoxiu():
    """调休：只有 comment + sentiment，没有时间 → 只能做情绪分析，无法做时序。"""
    f = BASE / "“调休”政策舆情数据" / "数据" / "weibo&sentiment.xlsx"
    df = pd.read_excel(f, engine="openpyxl")
    rows = [
        {"time": pd.NaT, "text": r.get("comment"), "sentiment": to_num(r.get("sentiment"))}
        for _, r in df.iterrows()
    ]
    return frame(rows, "tiaoxiu")


def load_suanfa():
    """算法推荐规定：中文列 + Excel 序列号时间。"""
    f = BASE / "《互联网信息服务算法推荐管理规定》政策舆情数据" / "数据" / "原始数据.xlsx"
    df = pd.read_excel(f, engine="openpyxl")
    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "time": parse_time(r.get("时间1")),
                "text": r.get("内容") or r.get("标题"),
                "reposts": to_num(r.get("转")),
                "comments": to_num(r.get("评")),
                "likes": to_num(r.get("赞")),
            }
        )
    return frame(rows, "suanfa_tuijian")


def load_sanhai():
    """三孩：content + 评论时间 + 情感打分。"""
    f = BASE / "三孩政策舆情数据" / "数据" / "data.xlsx"
    df = pd.read_excel(f, engine="openpyxl")
    rows = [
        {"time": parse_time(r.get("评论时间")), "text": r.get("content"), "sentiment": to_num(r.get("情感打分"))}
        for _, r in df.iterrows()
    ]
    return frame(rows, "sanhai")


def load_luohu():
    """上海落户：英文列，博文 + 评论两个文件。"""
    d = BASE / "上海非沪籍高校毕业生落户相关政策的舆情数据" / "数据"
    out = []
    f1 = d / "博文数据.csv"
    if f1.exists():
        df = pd.read_csv(f1, low_memory=False, on_bad_lines="skip")
        out += [
            {
                "time": parse_time(r.get("time")),
                "text": r.get("content"),
                "likes": to_num(r.get("attitudes_count")),
                "comments": to_num(r.get("comments_count")),
                "reposts": to_num(r.get("reposts_count")),
            }
            for _, r in df.iterrows()
        ]
    f2 = d / "评论数据.csv"
    if f2.exists():
        df = pd.read_csv(f2, low_memory=False, on_bad_lines="skip")
        out += [
            {"time": parse_time(r.get("time")), "text": r.get("content"), "likes": to_num(r.get("attitudes_count"))}
            for _, r in df.iterrows()
        ]
    return frame(out, "shanghai_luohu")


def load_yinsi():
    """个人信息保护：中文列，含话题字段。"""
    f = BASE / "个人信息与隐私保护政策舆情数据" / "output.csv"
    df = pd.read_csv(f, low_memory=False, on_bad_lines="skip")
    rows = [
        {
            "time": parse_time(r.get("发布时间")),
            "text": r.get("微博正文"),
            "reposts": to_num(r.get("转发数")),
            "comments": to_num(r.get("评论数")),
            "likes": to_num(r.get("点赞数")),
        }
        for _, r in df.iterrows()
    ]
    return frame(rows, "geren_yinsi")


def load_fangdichan():
    """房地产税：3 个 sheet 各覆盖一个时间段，合并读取。"""
    f = BASE / "房地产税试点政策舆情数据" / "数据" / "数据 总.xlsx"
    xl = pd.ExcelFile(f, engine="openpyxl")
    rows = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(f, sheet_name=sheet, engine="openpyxl")
        for _, r in df.iterrows():
            rows.append(
                {
                    "time": parse_time(r.get("博文详情链接")),  # 该表列整体错位一格，时间实际在「博文详情链接」列
                    "text": r.get("微博内容"),
                    "reposts": to_num(r.get("转发数")),
                    "comments": to_num(r.get("评论数")),
                    "likes": to_num(r.get("点赞数")),
                }
            )
    return frame(rows, "fangdichanshui")


def load_xinguan():
    """新冠疫情：博文 + 评论两个 csv，中文列。"""
    d = BASE / "新冠疫情政策数据"
    out = []
    f1 = d / "blog_csv.csv"
    if f1.exists():
        df = pd.read_csv(f1, low_memory=False, on_bad_lines="skip")
        out += [
            {
                "time": parse_time(r.get("发布时间")),
                "text": r.get("微博正文"),
                "likes": to_num(r.get("点赞数")),
                "reposts": to_num(r.get("转发数")),
                "comments": to_num(r.get("评论数")),
            }
            for _, r in df.iterrows()
        ]
    f2 = d / "comments_csv.csv"
    if f2.exists():
        df = pd.read_csv(f2, low_memory=False, on_bad_lines="skip")
        out += [
            {"time": parse_time(r.get("评论发布时间")), "text": r.get("评论内容"), "likes": to_num(r.get("评论获赞数"))}
            for _, r in df.iterrows()
        ]
    return frame(out, "xinguan")


LOADERS = [
    load_tiaoxiu,
    load_suanfa,
    load_sanhai,
    load_luohu,
    load_yinsi,
    load_fangdichan,
    load_xinguan,
]

parts = []
index = []
for fn in LOADERS:
    try:
        df = fn()
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {fn.__name__}: {type(e).__name__}: {str(e)[:90]}")
        continue
    if df.empty:
        print(f"  · {fn.__name__}: 空")
        continue
    eid = df["event_id"].iloc[0]
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    ok = df["time"].notna()
    print(f"  {eid:20} 共 {len(df):7,} 条   有时间 {int(ok.sum()):7,} 条   "
          f"{df.loc[ok,'time'].min()} ~ {df.loc[ok,'time'].max()}")
    parts.append(df)

    # 日度时序（只统计有时间戳的行）
    if ok.any():
        s = df.loc[ok].copy()
        s["date"] = s["time"].dt.date
        daily = s.groupby("date").agg(
            volume=("text", "count"),
            likes=("likes", "sum"),
            comments=("comments", "sum"),
            reposts=("reposts", "sum"),
        ).reset_index()
        daily["OT"] = daily["volume"]  # 与预测模块的 OT 字段对齐
        daily.to_csv(SERIES_DIR / f"{eid}.csv", index=False, encoding="utf-8-sig")
        index.append(
            {
                "event_id": eid,
                "n_rows": int(len(df)),
                "n_timed": int(ok.sum()),
                "start": str(s["time"].min().date()),
                "end": str(s["time"].max().date()),
                "days": int(daily.shape[0]),
                "total_volume": int(daily["volume"].sum()),
                "total_interactions": int(daily[["likes", "comments", "reposts"]].sum().sum()),
            }
        )

if parts:
    allx = pd.concat(parts, ignore_index=True)
    allx.to_csv(OUT / "events_unified.csv", index=False, encoding="utf-8-sig")
    print(f"\n  统一表: {len(allx):,} 行 → tmp/events_unified.csv")

idx = pd.DataFrame(index).sort_values("n_rows", ascending=False)
idx.to_csv(OUT / "event_index.csv", index=False, encoding="utf-8-sig")
print("\n=== 事件索引 ===")
print(idx.to_string(index=False))
