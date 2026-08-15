"""
增强词表标注器（正式替换 PlatformCrawler.stance_lite）。

立场与情绪分开打分：立场看站队词，情绪看褒贬词；二者可不一致。
支持按平台合并「通用词表 + 平台专属词表」（见 platform_lexicons.py），
以适配各平台圈层用语，提升标注精准度。
"""

from __future__ import annotations

import re
from typing import Any

from .base import BaseLabeler
from .platform_lexicons import get_platform_lexicon, get_platform_markers, merge_lexicon

# 立场（站队）
SUPPORT_CUES = [
    "支持", "站", "挺", "力挺", "认同", "同意", "拥护", "给力", "加油",
    "值得", "推荐", "爱了", "yyds", "永远的神", "封神", "太强了", "牛逼", "牛",
]
OPPOSE_CUES = [
    "反对", "抵制", "不支持", "看不惯", "恶心", "滚", "离谱", "翻车", "避雷",
    "取关", "拉黑", "打假", "曝光", "有病", "无语透了", "别洗", "洗地",
]

# 情绪（褒贬），可与立场解耦
POS_SENT = [
    "喜欢", "好看", "厉害", "棒", "赞", "好评", "感谢", "泪目", "感动",
    "期待", "优秀", "真棒", "致敬", "佩服", "开心", "快乐", "幸福", "温暖",
    "哈哈哈", "笑死", "太好笑", "可爱",
]
NEG_SENT = [
    "失望", "难过", "破防", "崩溃", "讨厌", "恶心", "垃圾", "难看", "差评",
    "坑", "骗", "黑", "喷", "烂", "哭了", "难受", "压力", "焦虑", "累死",
]

EMOJI_POS = ["[喜欢]", "[支持]", "[点赞]", "[打call]", "[星星眼]", "[给心心]"]
EMOJI_NEG = ["[生气]", "[抠鼻]", "[白眼]", "[呕]", "[大哭]", "[笑哭]"]

TOPIC_RULES: list[tuple[str, list[str]]] = [
    ("怀旧考古", ["考古", "年前", "当年", "回忆", "重制", "挖坟"]),
    ("学业考试", ["大学", "高考", "考研", "期末", "考试", "复习", "作业", "论文"]),
    ("演技作品", ["演技", "舞剧", "红楼梦", "舞台", "演出", "翻拍"]),
    ("体育赛事", ["退役", "球员", "比赛", "总决赛", "NBA", "威少"]),
    ("情绪表达", []),  # 动态：有明显情绪词时追加
]


def _hits(text: str, words: list[str]) -> int:
    return sum(1 for w in words if w and w in text)


# 通用基础词表（跨平台）；平台专属增量见 platform_lexicons.py
_BASE_CUES = {
    "support_cues": SUPPORT_CUES,
    "oppose_cues": OPPOSE_CUES,
    "pos_sent": POS_SENT,
    "neg_sent": NEG_SENT,
}


class LexiconLabeler(BaseLabeler):
    name = "lexicon"
    version = "v2"

    def __init__(self, platform: str | None = None) -> None:
        # 合并通用词表 + 平台专属词表（缓存合并结果）
        self.platform = (platform or "").lower() or None
        self._cues = merge_lexicon(_BASE_CUES, get_platform_lexicon(self.platform))
        self._markers = get_platform_markers(self.platform)

    def label(self, text: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        t = text or ""
        support = _hits(t, self._cues["support_cues"])
        oppose = _hits(t, self._cues["oppose_cues"])
        pos_s = _hits(t, self._cues["pos_sent"]) + _hits(t, EMOJI_POS)
        neg_s = _hits(t, self._cues["neg_sent"]) + _hits(t, EMOJI_NEG)

        # —— 立场 —— #
        if support > 0 and oppose > 0:
            stance = "mixed"
            stance_conf = min(0.6, 0.35 + 0.05 * (support + oppose))
        elif support > oppose:
            stance = "support"
            stance_conf = min(0.85, 0.4 + 0.08 * support)
        elif oppose > support:
            stance = "oppose"
            stance_conf = min(0.85, 0.4 + 0.08 * oppose)
        else:
            stripped = t.strip()
            if len(stripped) < 2 or re.fullmatch(r"[\W\d_\s\[\]【】#@]+", stripped or ""):
                stance = "unclear"
                stance_conf = 0.25
            else:
                stance = "neutral"
                stance_conf = 0.45

        # —— 情绪（独立） —— #
        if pos_s == 0 and neg_s == 0:
            sentiment = 0.0
            sent_conf = 0.35
        else:
            raw = (pos_s - neg_s) / max(1, pos_s + neg_s)
            sentiment = max(-1.0, min(1.0, raw * (0.5 + 0.1 * min(5, pos_s + neg_s))))
            sent_conf = min(0.85, 0.4 + 0.06 * (pos_s + neg_s))

        # 综合置信：立场与情绪置信的温和平均
        conf = 0.6 * stance_conf + 0.4 * sent_conf

        tags: list[str] = []
        for name, keys in TOPIC_RULES:
            if name == "情绪表达":
                if pos_s or neg_s:
                    tags.append(name)
                continue
            if any(k in t for k in keys):
                tags.append(name)

        # 平台圈层标记词：命中则追加「圈层」标签，用于识别语境（不参与立场/情绪打分）
        for marker in self._markers:
            if marker and marker in t:
                tags.append(f"圈层:{marker}")
                break

        return {
            "stance_label": stance,
            "sentiment_score": float(sentiment),
            "stance_conf": float(conf),
            "topic_tags": tags,
        }
