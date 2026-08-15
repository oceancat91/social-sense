"""
多平台主控层 DeepSeek 客户端（与 agent/Conclusion/llm.py 同口径，独立可用）。

.env 查找顺序：仓库根目录 → agent/ 目录。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import requests

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def _env_paths() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    return [root / ".env", root / "agent" / ".env"]


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for p in _env_paths():
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"):
        if os.getenv(k):
            env[k] = os.getenv(k, "")
    return env


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise
        return json.loads(m.group(0))


def chat(system: str, user: str, *, temperature: float = 0.3, timeout: int = 90) -> str:
    env = load_env()
    api_key = env.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未找到 DEEPSEEK_API_KEY")
    model = env.get("DEEPSEEK_MODEL") or DEFAULT_MODEL
    resp = requests.post(
        DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "stream": False,
        },
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"DeepSeek API 失败 HTTP {resp.status_code}: {resp.text[:500]}")
    return resp.json()["choices"][0]["message"]["content"]
