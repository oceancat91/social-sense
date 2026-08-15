"""
DeepSeek 客户端（结论生成与校准共用）。与 Agent.llm_plan 保持同一 .env 读取口径。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
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


def chat(
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
    model: str | None = None,
    timeout: int = 90,
) -> str:
    env = load_env()
    api_key = env.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未找到 DEEPSEEK_API_KEY，请在 agent/.env 中配置")
    model = model or env.get("DEEPSEEK_MODEL") or DEFAULT_MODEL
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
