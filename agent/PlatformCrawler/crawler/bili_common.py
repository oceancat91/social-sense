"""
B站公共工具：Cookie/UA 读取、WBI 签名
"""

from __future__ import annotations

import hashlib
import os
import time
import urllib.parse
from functools import reduce
from typing import Any

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_PATH = os.path.join(SCRIPT_DIR, "bili_cookie.txt")
UA_PATH = os.path.join(SCRIPT_DIR, "bili_ua.txt")

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
)

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

_wbi_cache: dict[str, Any] = {"ts": 0.0, "img_key": "", "sub_key": ""}


def get_header() -> dict[str, str]:
    if not os.path.isfile(COOKIE_PATH):
        raise FileNotFoundError(
            f"未找到 Cookie 文件，请先运行: python auto_get_cookie.py\n路径: {COOKIE_PATH}"
        )
    with open(COOKIE_PATH, "r", encoding="utf-8") as f:
        cookie = f.read().strip()
    if not cookie:
        raise FileNotFoundError("Cookie 为空，请先运行: python auto_get_cookie.py")

    ua = DEFAULT_UA
    if os.path.isfile(UA_PATH):
        with open(UA_PATH, "r", encoding="utf-8") as f:
            ua = f.read().strip() or DEFAULT_UA

    return {
        "Cookie": cookie,
        "User-Agent": ua,
        "Referer": "https://www.bilibili.com",
        "Origin": "https://www.bilibili.com",
    }


def _get_mixin_key(origin: str) -> str:
    return reduce(lambda s, i: s + origin[i], MIXIN_KEY_ENC_TAB, "")[:32]


def _refresh_wbi_keys(headers: dict[str, str]) -> tuple[str, str]:
    now = time.time()
    if _wbi_cache["img_key"] and now - float(_wbi_cache["ts"]) < 600:
        return str(_wbi_cache["img_key"]), str(_wbi_cache["sub_key"])

    resp = requests.get(
        "https://api.bilibili.com/x/web-interface/nav",
        headers=headers,
        timeout=20,
    )
    data = resp.json().get("data") or {}
    wbi = data.get("wbi_img") or {}
    img_url = wbi.get("img_url") or ""
    sub_url = wbi.get("sub_url") or ""
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    if not img_key or not sub_key:
        raise RuntimeError("无法获取 WBI 密钥，请检查 Cookie 是否有效")

    _wbi_cache.update({"ts": now, "img_key": img_key, "sub_key": sub_key})
    return img_key, sub_key


def enc_wbi(params: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    headers = headers or get_header()
    img_key, sub_key = _refresh_wbi_keys(headers)
    mixin_key = _get_mixin_key(img_key + sub_key)

    signed = dict(params)
    signed["wts"] = int(time.time())
    # 过滤特殊字符
    cleaned = {
        k: "".join(ch for ch in str(v) if ch not in "!'()*")
        for k, v in signed.items()
    }
    cleaned = dict(sorted(cleaned.items()))
    query = urllib.parse.urlencode(cleaned)
    cleaned["w_rid"] = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    return cleaned
