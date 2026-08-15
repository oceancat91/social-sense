"""
轻量立场/情绪标注（在 StanceProfiler 接入前的占位实现）。

产出字段符合 DATASET_SPEC，并在 D_meta.ext 中标记 provisional=true。
后续 Skill2 可整表覆写 stance_label / sentiment_score / topic_tags / confidence。
"""

from __future__ import annotations

import re
from typing import Any


POS_WORDS = [
    "支持", "喜欢", "爱了", "好看", "厉害", "牛", "棒", "赞", "好评", "感谢",
    "泪目", "感动", "期待", "优秀", "真棒", "致敬", "佩服", "开心", "快乐",
]
NEG_WORDS = [
    "反对", "恶心", "垃圾", "难看", "失望", "坑", "骂", "滚", "差评", "无语",
    "烂", "恶心", "骗", "黑", "喷", "离谱", "崩溃", "讨厌", "恶心人",
]
EMOJI_POS = ["[喜欢]", "[支持]", "[点赞]", "[打call]", "[笑哭]"]
EMOJI_NEG = ["[生气]", "[抠鼻]", "[白眼]", "[呕]"]


def _count_hits(text: str, words: list[str]) -> int:
    return sum(1 for w in words if w in text)


def annotate_stance_sentiment(text: str) -> dict[str, Any]:
    t = text or ""
    pos = _count_hits(t, POS_WORDS) + _count_hits(t, EMOJI_POS)
    neg = _count_hits(t, NEG_WORDS) + _count_hits(t, EMOJI_NEG)

    if pos > 0 and neg > 0:
        label = "mixed"
        score = (pos - neg) / (pos + neg)
        conf = min(0.55, 0.3 + 0.05 * (pos + neg))
    elif pos > neg:
        label = "support"
        score = min(1.0, 0.25 + 0.2 * pos)
        conf = min(0.7, 0.35 + 0.08 * pos)
    elif neg > pos:
        label = "oppose"
        score = -min(1.0, 0.25 + 0.2 * neg)
        conf = min(0.7, 0.35 + 0.08 * neg)
    else:
        # 纯表情/过短 → unclear，否则中性
        if len(t.strip()) < 2 or re.fullmatch(r"[\W\d_\s\[\]【】]+", t.strip() or ""):
            label = "unclear"
            score = 0.0
            conf = 0.25
        else:
            label = "neutral"
            score = 0.0
            conf = 0.4

    tags: list[str] = []
    if "考古" in t or "年前" in t:
        tags.append("怀旧考古")
    if "大学" in t or "高考" in t or "考研" in t:
        tags.append("学业成长")
    if pos or neg:
        tags.append("情绪表达")

    return {
        "stance_label": label,
        "sentiment_score": max(-1.0, min(1.0, float(score))),
        "stance_conf": float(conf),
        "topic_tags": tags,
    }
