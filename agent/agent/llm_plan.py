"""
用 DeepSeek 根据话题自动规划分析时间窗与采集参数。
人工只提供话题；时间窗等由 LLM 判断。

分工（硬规则）：
- 长轴 since/until = 爆发→今天 → 只服务 D_ts.topic_heat（搜索视频发布时序）
- 评论：固定最多 2 页；用近期 comment_since/comment_until，不深翻历史评论
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
COMMENT_PAGES_FIXED = 2
COMMENT_LOOKBACK_DAYS = 14

KNOWN_EVENT_STARTS: dict[str, str] = {
    "科比去世": "2020-01-26",
    "科比坠机": "2020-01-26",
    "kobe去世": "2020-01-26",
}


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"):
        if os.getenv(k):
            out[k] = os.getenv(k, "")
    return out


def _extract_json(text: str) -> dict[str, Any]:
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


def _guess_event_start(topic: str) -> str | None:
    t = topic.strip().lower()
    for k, v in KNOWN_EVENT_STARTS.items():
        if k.lower() in t or t in k.lower():
            return v
    return None


def _clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _normalize_plan(plan: dict[str, Any], topic: str, today: date) -> dict[str, Any]:
    for key in ("since", "until"):
        datetime.strptime(str(plan[key]), "%Y-%m-%d")
    if plan["since"] > plan["until"]:
        plan["since"], plan["until"] = plan["until"], plan["since"]

    plan.setdefault("event_start", plan["since"])
    plan.setdefault("search_since", plan["since"])
    plan.setdefault("search_until", plan["until"])
    plan.setdefault("analysis_mode", "event_window")
    plan.setdefault("order", "click")
    plan.setdefault("rank_by", "play")
    plan.setdefault("comment_mode", "latest")
    plan.setdefault("rationale", "")

    mode = str(plan.get("analysis_mode") or "event_window")
    guessed = _guess_event_start(topic)
    if guessed and mode == "recent_discussion":
        mode = "event_window"
        plan["rationale"] = (
            (plan.get("rationale") or "")
            + f" [系统校正：已知事件爆发日 {guessed}，长轴改用 event_window]"
        ).strip()

    # 长轴：爆发→今天（只服务 topic_heat / D_ts 轴）
    if mode != "recent_discussion":
        event_start = str(plan.get("event_start") or guessed or plan["since"])
        try:
            datetime.strptime(event_start, "%Y-%m-%d")
        except ValueError:
            event_start = guessed or plan["since"]
        plan["event_start"] = event_start
        plan["since"] = event_start
        plan["until"] = today.isoformat()
        plan["search_since"] = event_start
        plan["search_until"] = today.isoformat()
        plan["analysis_mode"] = "event_window"
    else:
        plan["search_since"] = plan.get("search_since") or plan["since"]
        plan["search_until"] = plan.get("search_until") or plan["until"]

    # 评论窗：近期；与长轴解耦
    comment_until = today
    comment_since = today - timedelta(days=COMMENT_LOOKBACK_DAYS - 1)
    # 若 LLM 给了合理近期窗且落在长轴内，可采纳（仍截断到 lookback）
    for key in ("comment_since", "comment_until"):
        if plan.get(key):
            try:
                datetime.strptime(str(plan[key]), "%Y-%m-%d")
            except (TypeError, ValueError):
                plan.pop(key, None)
    if plan.get("comment_since") and plan.get("comment_until"):
        cs, cu = str(plan["comment_since"]), str(plan["comment_until"])
        if cs > cu:
            cs, cu = cu, cs
        # 不允许评论窗拉到爆发长轴；最多 COMMENT_LOOKBACK_DAYS
        earliest = (today - timedelta(days=COMMENT_LOOKBACK_DAYS - 1)).isoformat()
        if cs < earliest:
            cs = earliest
        if cu > today.isoformat():
            cu = today.isoformat()
        comment_since = datetime.strptime(cs, "%Y-%m-%d").date()
        comment_until = datetime.strptime(cu, "%Y-%m-%d").date()

    plan["comment_since"] = comment_since.isoformat()
    plan["comment_until"] = comment_until.isoformat()

    plan["max_videos"] = _clamp_int(plan.get("max_videos"), 1, 8, 3)
    # 评论页数硬限制：固定 2，不做深翻
    plan["comment_pages"] = COMMENT_PAGES_FIXED
    plan["heat_search_pages"] = _clamp_int(plan.get("heat_search_pages"), 1, 8, 3)
    plan["heat_max_videos"] = _clamp_int(plan.get("heat_max_videos"), 20, 200, 100)
    plan["search_pages"] = _clamp_int(
        plan.get("search_pages"), 1, 8, int(plan["heat_search_pages"])
    )

    plan["topic"] = topic
    plan["planned_at"] = datetime.now().isoformat(timespec="seconds")
    return plan


def plan_analysis_window(topic: str, *, today: date | None = None) -> dict[str, Any]:
    """
    返回:
      since/until          — D_ts 长轴（爆发→今天），主要承载 topic_heat
      comment_since/until  — 评论抓取窗（近期）
      comment_pages        — 固定为 2
      search_* / heat_*    — 热度搜索池
    """
    today = today or date.today()
    env = _load_env()
    api_key = env.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未找到 DEEPSEEK_API_KEY，请在项目根目录 .env 中配置")

    model = env.get("DEEPSEEK_MODEL") or DEFAULT_MODEL
    hint = _guess_event_start(topic)
    hint_line = f"本地已知爆发日提示：{hint}。" if hint else "无本地已知爆发日提示。"

    system = f"""你是舆情分析任务规划助手，服务于 B 站「单平台舆情感知」Agent。
今天日期：{today.isoformat()}。
{hint_line}

职责分工（必须遵守，不要混淆）：
A. **时序热度长轴** since/until：事件爆发日 → 今天。只用于搜索相关视频并按发布日汇总 topic_heat，**不是**为了深翻历史评论。
B. **评论文本**：每个视频最多爬 **2** 页一级评论；评论时间窗用近期（约最近 {COMMENT_LOOKBACK_DAYS} 天）comment_since/comment_until。
C. 禁止为了「覆盖爆发期评论」而把 comment_pages 调大，或把评论窗拉成数年。

硬约束：
1. 先判断 event_start。默认 analysis_mode=event_window：since=event_start，until=今天。
2. comment_pages 必须为 2；comment_since/comment_until 为近期窗。
3. heat_search_pages 建议 2～5，heat_max_videos 建议 60～120；max_videos 建议 3～5。
4. 无法对应单一事件时才用 recent_discussion（近 7～30 天），此时 since/until 可与评论窗接近。
5. 只输出一个 JSON 对象，不要 Markdown。

JSON schema:
{{
  "event_start": "YYYY-MM-DD",
  "since": "YYYY-MM-DD",
  "until": "YYYY-MM-DD",
  "comment_since": "YYYY-MM-DD",
  "comment_until": "YYYY-MM-DD",
  "search_since": "YYYY-MM-DD",
  "search_until": "YYYY-MM-DD",
  "analysis_mode": "event_window" | "recent_discussion",
  "max_videos": 1到8的整数,
  "comment_pages": 2,
  "heat_search_pages": 1到8的整数,
  "heat_max_videos": 20到200的整数,
  "order": "click" | "totalrank" | "pubdate",
  "rank_by": "play" | "review" | "favorites",
  "comment_mode": "latest" | "hot",
  "rationale": "中文：爆发日、长轴用于 topic_heat、评论仅 2 页近期抽样"
}}
"""
    user = (
        f"话题：{topic}\n"
        "请规划：长轴做话题热度时序；评论固定 2 页、只用近期窗。"
    )

    resp = requests.post(
        DEEPSEEK_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "stream": False,
        },
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"DeepSeek API 失败 HTTP {resp.status_code}: {resp.text[:500]}")

    content = resp.json()["choices"][0]["message"]["content"]
    plan = _normalize_plan(_extract_json(content), topic, today)
    plan["planned_by"] = f"deepseek:{model}"
    return plan


def fallback_plan(topic: str, *, today: date | None = None) -> dict[str, Any]:
    """API 不可用：长轴爆发→今天；评论近 14 天 × 2 页。"""
    today = today or date.today()
    event_start = _guess_event_start(topic)
    comment_since = (today - timedelta(days=COMMENT_LOOKBACK_DAYS - 1)).isoformat()
    comment_until = today.isoformat()
    if event_start:
        plan = {
            "topic": topic,
            "event_start": event_start,
            "since": event_start,
            "until": today.isoformat(),
            "comment_since": comment_since,
            "comment_until": comment_until,
            "search_since": event_start,
            "search_until": today.isoformat(),
            "analysis_mode": "event_window",
            "max_videos": 3,
            "comment_pages": COMMENT_PAGES_FIXED,
            "heat_search_pages": 3,
            "heat_max_videos": 100,
            "order": "click",
            "rank_by": "play",
            "comment_mode": "latest",
            "rationale": (
                f"LLM 不可用；长轴 {event_start}→今天做 topic_heat；"
                f"评论仅近{COMMENT_LOOKBACK_DAYS}天、{COMMENT_PAGES_FIXED}页。"
            ),
            "planned_by": "fallback_local",
            "planned_at": datetime.now().isoformat(timespec="seconds"),
        }
        return _normalize_plan(plan, topic, today)

    since = (today - timedelta(days=29)).isoformat()
    plan = {
        "topic": topic,
        "event_start": since,
        "since": since,
        "until": comment_until,
        "comment_since": comment_since,
        "comment_until": comment_until,
        "search_since": since,
        "search_until": comment_until,
        "analysis_mode": "recent_discussion",
        "max_videos": 3,
        "comment_pages": COMMENT_PAGES_FIXED,
        "heat_search_pages": 2,
        "heat_max_videos": 60,
        "order": "click",
        "rank_by": "play",
        "comment_mode": "latest",
        "rationale": f"LLM 不可用；近30天轴 + 评论{COMMENT_PAGES_FIXED}页。",
        "planned_by": "fallback_local",
        "planned_at": datetime.now().isoformat(timespec="seconds"),
    }
    return _normalize_plan(plan, topic, today)
