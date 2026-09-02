"""
清洗流水线 C1–C8（README Skill1）

输入：爬虫原始 dict 列表或 B 站评论 CSV
输出：raw_clean_bundle（规范化记录 + clean_log + quarantine）
"""

from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .metrics import interact
from .stance_lite import annotate_stance_sentiment

TZ = ZoneInfo("Asia/Shanghai")
CLEAN_RULE_VERSION = "clean_c1c8_v1"
ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff\u00a0]")
HTML_TAG = re.compile(r"<[^>]+>")
MULTI_SPACE = re.compile(r"[ \t\f\v]+")
MULTI_NL = re.compile(r"\n{3,}")


def _parse_ts(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=TZ)
        except (OSError, OverflowError, ValueError):
            return None
    s = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s.replace("+08:00", ""), fmt.replace("%z", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            return dt.astimezone(TZ)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    except ValueError:
        return None


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _hash_content_id(text: str, ts_iso: str, author_id: str | None) -> str:
    raw = f"{text}|{ts_iso}|{author_id or ''}"
    return "hash:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _normalize_text(text: str) -> str:
    # C3 + C4
    t = HTML_TAG.sub("", text)
    t = ZERO_WIDTH.sub("", t)
    t = unicodedata.normalize("NFKC", t)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = MULTI_SPACE.sub(" ", t)
    t = MULTI_NL.sub("\n\n", t)
    return t.strip()


def _is_pure_noise(text: str) -> bool:
    if not text:
        return True
    # 纯数字 / 纯表情括号刷屏
    if re.fullmatch(r"[\d\s\.\,\!\?？！。，、~～]+", text):
        return True
    if re.fullmatch(r"(\[[^\]]+\]\s*)+", text) and len(text) < 40:
        return True
    return False


def map_bilibili_csv_row(row: dict[str, Any], *, bvid: str | None = None) -> dict[str, Any]:
    """C1：B站评论 CSV → 跨平台原始字段。"""
    parent = _safe_str(row.get("上级评论ID") or row.get("parent_id"))
    if parent in ("", "0"):
        parent_id = None
    else:
        parent_id = parent

    content_id = _safe_str(row.get("评论ID") or row.get("content_id") or row.get("rpid"))
    author_id = _safe_str(row.get("用户ID") or row.get("author_id") or row.get("mid")) or None
    text = _safe_str(row.get("评论内容") or row.get("text") or row.get("content"))
    source_url = None
    if bvid:
        source_url = f"https://www.bilibili.com/video/{bvid}"

    # 注意：不能用 `a or b`，否则点赞=0 会被误判为空
    like_raw = row.get("点赞数", row.get("like", 0))
    reply_raw = row.get("回复数", row.get("reply_count", row.get("rereply", 0)))

    return {
        "platform": "bilibili",
        "content_id": content_id or None,
        "parent_id": parent_id,
        "author_id": author_id,
        "text": text,
        "ts_raw": row.get("评论时间") or row.get("ts") or row.get("ctime"),
        "like": _safe_float(like_raw),
        "reply_count": _safe_float(reply_raw),
        "share_or_coin": _safe_float(row.get("share_or_coin") or 0),
        "source_url": source_url,
        "ext": {
            "uname": _safe_str(row.get("用户名")),
            "level": row.get("用户等级"),
            "sex": row.get("性别"),
            "ip": row.get("IP属地"),
            "vip": row.get("是否为大会员") or row.get("是否是大会员"),
            "bvid": bvid,
        },
    }


def load_bilibili_comment_csv(path: str | Path, *, bvid: str | None = None) -> list[dict[str, Any]]:
    path = Path(path)
    # 从文件名尝试解析 BV
    if bvid is None:
        m = re.search(r"(BV[\w]+)", path.name, re.I)
        if m:
            bvid = m.group(1)

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(map_bilibili_csv_row(row, bvid=bvid))
    return rows


def load_many_comment_csvs(paths: list[str | Path]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in paths:
        out.extend(load_bilibili_comment_csv(p))
    return out


def clean_records(
    raw_rows: list[dict[str, Any]],
    *,
    time_range: tuple[datetime, datetime] | None = None,
    platform: str = "bilibili",
    spam_window_seconds: int = 300,
    spam_sim_prefix: int = 24,
) -> dict[str, Any]:
    """
    执行 C1–C7（C8 空窗在 builder 中按时间轴生成）。

    返回:
      {
        records: [...],          # 主集（进 D_text / 时序）
        quarantine: [...],
        out_of_range: [...],
        clean_log: [...],
        n_raw_in: int,
        clean_rule_version: str,
      }
    """
    clean_log: list[str] = []
    quarantine: list[dict[str, Any]] = []
    out_of_range: list[dict[str, Any]] = []
    mapped: list[dict[str, Any]] = []

    n_raw = len(raw_rows)
    clean_log.append(f"C0: input_rows={n_raw}")

    # —— C1/C2/C3/C4 —— #
    for i, row in enumerate(raw_rows):
        item = dict(row)
        item["platform"] = item.get("platform") or platform
        text = _normalize_text(_safe_str(item.get("text")))
        item["text"] = text

        dt = _parse_ts(item.get("ts_raw") or item.get("ts"))
        if dt is None:
            quarantine.append({**item, "reason": "bad_ts"})
            continue

        like = _safe_float(item.get("like"))
        reply_count = _safe_float(item.get("reply_count"))
        share_or_coin = _safe_float(item.get("share_or_coin"))

        # C2：规范化后空文本必须丢弃，否则会违反 D_platform 的有效文本计数契约。
        # 纯噪声仍沿用原策略：无互动时丢弃，有互动时保留用于反映热度。
        if not text:
            clean_log.append(f"C2 drop empty idx={i}")
            continue
        if _is_pure_noise(text) and like <= 0 and reply_count <= 0:
            clean_log.append(f"C2 drop empty/noise idx={i}")
            continue

        ts_iso = _to_iso(dt)
        author_id = item.get("author_id")
        content_id = _safe_str(item.get("content_id")) or None
        if not content_id:
            content_id = _hash_content_id(text, ts_iso, author_id)

        mapped.append(
            {
                "platform": item["platform"],
                "content_id": str(content_id),
                "parent_id": item.get("parent_id"),
                "author_id": str(author_id) if author_id is not None else None,
                "ts": ts_iso,
                "ts_unix": int(dt.timestamp()),
                "text": text,
                "like": like,
                "reply_count": reply_count,
                "share_or_coin": share_or_coin,
                "interact": interact(like, reply_count, share_or_coin),
                "source_url": item.get("source_url"),
                "lang": "zh",
                "ext": item.get("ext") or {},
                "_dt": dt,
            }
        )

    clean_log.append(f"C1-C4: kept={len(mapped)} quarantine={len(quarantine)}")

    # —— C6 时间窗 —— #
    in_range: list[dict[str, Any]] = []
    if time_range is not None:
        start, end = time_range
        if start.tzinfo is None:
            start = start.replace(tzinfo=TZ)
        if end.tzinfo is None:
            end = end.replace(tzinfo=TZ)
        start, end = start.astimezone(TZ), end.astimezone(TZ)
        for item in mapped:
            dt = item["_dt"]
            if start <= dt < end:
                in_range.append(item)
            else:
                out_of_range.append({k: v for k, v in item.items() if k != "_dt"})
        clean_log.append(f"C6: in_range={len(in_range)} out_of_range={len(out_of_range)}")
    else:
        in_range = mapped
        clean_log.append("C6: skipped (no time_range)")

    # —— C5 去重 —— #
    dedup: dict[tuple[str, str], dict[str, Any]] = {}
    for item in in_range:
        key = (item["platform"], item["content_id"])
        prev = dedup.get(key)
        if prev is None or item["interact"] >= prev["interact"]:
            dedup[key] = item
    records = list(dedup.values())
    clean_log.append(f"C5: after_dedup={len(records)}")

    # —— C7 刷屏弱化：同作者短窗相似前缀降权标记 —— #
    records.sort(key=lambda x: (x.get("author_id") or "", x["ts_unix"]))
    last_seen: dict[str, list[tuple[int, str]]] = {}
    for item in records:
        aid = item.get("author_id") or ""
        prefix = item["text"][:spam_sim_prefix]
        spam_factor = 1.0
        hist = last_seen.setdefault(aid, [])
        for ts_u, prev_prefix in hist:
            if item["ts_unix"] - ts_u <= spam_window_seconds and prev_prefix == prefix and prefix:
                spam_factor = min(spam_factor, 0.35)
        hist.append((item["ts_unix"], prefix))
        # 保留最近若干条即可
        if len(hist) > 30:
            del hist[:-30]
        item["_anti_spam"] = spam_factor

    # 轻量立场（可被 StanceProfiler 覆写）
    for item in records:
        ann = annotate_stance_sentiment(item["text"])
        item["stance_label"] = ann["stance_label"]
        item["sentiment_score"] = ann["sentiment_score"]
        item["topic_tags"] = ann["topic_tags"]
        item["_stance_conf"] = ann["stance_conf"]

    clean_log.append(f"C7: spam_marked; stance_lite applied; final={len(records)}")

    # 去掉内部 datetime
    for item in records:
        item.pop("_dt", None)

    return {
        "records": records,
        "quarantine": quarantine,
        "out_of_range": out_of_range,
        "clean_log": clean_log,
        "n_raw_in": n_raw,
        "clean_rule_version": CLEAN_RULE_VERSION,
        "is_empty": len(records) == 0,
    }
