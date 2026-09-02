"""
Skill5：ConclusionGen —— 生成 OT₀。
"""

from __future__ import annotations

from typing import Any

from ..llm import chat, extract_json
from ..schema import normalize_ot0
from .prompts import SYSTEM_PROMPT, build_evidence_package, build_user_prompt

GENERATOR_VERSION = "conclusion_gen_v2_case_icl"


def generate_ot0(
    d_platform: dict[str, Any],
    stance_profile: dict[str, Any] | None,
    skill3: dict[str, Any] | None,
    rag: dict[str, Any] | None = None,
    *,
    topk_text: int = 15,
    temperature: float = 0.3,
) -> dict[str, Any]:
    pkg = build_evidence_package(d_platform, stance_profile, skill3, rag, topk_text=topk_text)
    raw = chat(SYSTEM_PROMPT, build_user_prompt(pkg), temperature=temperature)
    ot0 = normalize_ot0(extract_json(raw))
    ot0["_generator_version"] = GENERATOR_VERSION
    ot0["_evidence_package"] = pkg  # 供校准复用，不落盘到结论正文
    return ot0
