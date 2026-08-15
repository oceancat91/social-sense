"""
受限改写：据 deviation_report 纠偏（删幻觉、改矛盾句、补引用），不覆盖量化结论。
"""

from __future__ import annotations

import json
from typing import Any

from ..llm import chat, extract_json
from ..schema import normalize_ot0

REWRITE_SYSTEM = """你是结论校准助手。根据「偏差清单」修正结论 JSON，目标是让结论与硬数据一致。
规则：
1. 只能修改与偏差清单相关的字段（claim_*、summary_analysis、evidence_ids、uncertainty 等）。
2. 不得改动/伪造证据包中没有的数字；引用 ID 必须来自证据包。
3. summary_analysis 保持中文概括分析，删除与数据矛盾或臆造的句子，补齐引用。
4. 只输出一个 JSON 对象，schema 与原始结论一致，不要 Markdown。"""


def rewrite_ot0(
    ot0: dict[str, Any],
    deviations: list[dict[str, Any]],
    evidence_package: dict[str, Any],
) -> dict[str, Any]:
    clean = {k: v for k, v in ot0.items() if not k.startswith("_")}
    user = (
        "原结论：\n"
        + json.dumps(clean, ensure_ascii=False, indent=2)
        + "\n\n偏差清单：\n"
        + json.dumps(deviations, ensure_ascii=False, indent=2)
        + "\n\n证据包（唯一事实来源）：\n"
        + json.dumps(evidence_package, ensure_ascii=False, indent=2)
    )
    raw = chat(REWRITE_SYSTEM, user, temperature=0.2)
    return normalize_ot0(extract_json(raw))
