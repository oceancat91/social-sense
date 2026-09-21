"""Shared schema, parsing and argument helpers for dataset commands."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATASET_COLUMN_SPEC = {
    "bili.csv": ("platform", "publish_time", "text_structured_clean"),
    "weibo.csv": ("platform", "publish_time", "text_structured_clean"),
    "xhs.csv": ("platform", "publish_time", "text_structured_clean"),
    "douyin.csv": ("platform", "publish_time", "text_structured_clean"),
    "kuaishou.csv": ("platform", "comment_time_iso", "comment_text"),
}
DATASET_FILES = tuple(DATASET_COLUMN_SPEC)

_DOMAIN_JSON = Path(__file__).resolve().parents[2] / "agent" / "dataset" / "domains.json"
DOMAIN_NAMES: dict[str, str] = json.loads(_DOMAIN_JSON.read_text(encoding="utf-8"))
DOMAIN_ZH_TO_CODE: dict[str, str] = {zh: code for code, zh in DOMAIN_NAMES.items()}

TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
)


def parse_time(value: Any, *, allow_unix: bool = False) -> datetime | None:
    """Parse the timestamp formats shared by dataset preparation and diagnostics."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"0", "-"}:
        return None

    if allow_unix and re.fullmatch(r"\d{10,13}", text):
        try:
            seconds = float(text) / (1000.0 if len(text) >= 13 else 1.0)
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

    candidate = text.replace("Z", "+0000")
    if len(candidate) > 6 and candidate[-3] == ":" and candidate[-6] in "+-":
        candidate = candidate[:-3] + candidate[-2:]
    for time_format in TIME_FORMATS:
        try:
            return datetime.strptime(candidate, time_format)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def directory_arg(value: str) -> Path:
    """Return an existing directory as an absolute path for argparse."""
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"目录不存在：{path}")
    return path


def file_arg(value: str) -> Path:
    """Return an existing file as an absolute path for argparse."""
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"文件不存在：{path}")
    return path


def output_directory_arg(value: str) -> Path:
    """Return a resolved output directory path; it may not exist yet."""
    return Path(value).expanduser().resolve()
