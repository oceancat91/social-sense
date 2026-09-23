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
    "哈哈哈", "笑死", "太好笑", "可爱", "高级",
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


# 否定词：紧邻极性词前 0–2 字时，极性取反（"不喜欢" → 负面）。
NEGATORS = ("不", "别", "没", "无", "非", "未", "莫")

# 极性空间：立场词表与情绪词表共享同一组「正/负」极性。
# 旧实现把四个列表各自独立计数，同一极性会被重复计票：weibo 把「支持」同时
# 收进 support_cues 与 pos_sent，而「反对」只在 oppose_cues，于是
# 「支持他的勇气，但反对他的做法」正面得 2 票、负面得 1 票，被判成 support
# （人工标注为 mixed）。改为按「词」去重、按「极性」汇总。
_POLARITY_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pos", ("support_cues", "pos_sent")),
    ("neg", ("oppose_cues", "neg_sent")),
)


def _polarity_hits(
    text: str,
    cues: dict[str, list[str]],
) -> tuple[set[str], set[str], set[str], set[str]]:
    """按极性汇总命中词，返回去重后的四个集合。

    返回值 ``(pos_hits, neg_hits, stance_pos, stance_neg)``：

    - ``pos_hits`` / ``neg_hits``：全部极性证据（立场词 + 情绪词 + 表情，按词去重）；
    - ``stance_pos`` / ``stance_neg``：其中来自立场词表、即明确「站队」的部分。

    两个细节决定标注质量：

    1. 长词优先并占用字符区间，避免「不推荐」内部的「推荐」被单独算成正面；
    2. 词前 0–2 字内出现否定词则极性取反，补上历史缺失的否定处理。
    """
    consumed = [False] * len(text)
    stance_words = set(cues.get("support_cues") or []) | set(cues.get("oppose_cues") or [])

    candidates: list[tuple[str, str]] = []
    for polarity, keys in _POLARITY_BUCKETS:
        for key in keys:
            candidates.extend((w, polarity) for w in (cues.get(key) or []) if w)
    candidates.extend((w, "pos") for w in EMOJI_POS if w)
    candidates.extend((w, "neg") for w in EMOJI_NEG if w)
    candidates.sort(key=lambda item: -len(item[0]))

    pos_hits: set[str] = set()
    neg_hits: set[str] = set()
    stance_pos: set[str] = set()
    stance_neg: set[str] = set()

    for word, polarity in candidates:
        start = 0
        while True:
            i = text.find(word, start)
            if i < 0:
                break
            start = i + 1
            j = i + len(word)
            if any(consumed[i:j]):
                continue
            for k in range(i, j):
                consumed[k] = True
            # 否定窗口只看词前，避免把词自身的否定语素误当修饰
            ctx = text[max(0, i - 2):i]
            effective = ("neg" if polarity == "pos" else "pos") if any(
                neg in ctx for neg in NEGATORS
            ) else polarity
            if effective == "pos":
                pos_hits.add(word)
                if word in stance_words:
                    stance_pos.add(word)
            else:
                neg_hits.add(word)
                if word in stance_words:
                    stance_neg.add(word)

    return pos_hits, neg_hits, stance_pos, stance_neg


# 通用基础词表（跨平台）；平台专属增量见 platform_lexicons.py
_BASE_CUES = {
    "support_cues": SUPPORT_CUES,
    "oppose_cues": OPPOSE_CUES,
    "pos_sent": POS_SENT,
    "neg_sent": NEG_SENT,
}


class LexiconLabeler(BaseLabeler):
    name = "lexicon"
    version = "v3"

    def __init__(self, platform: str | None = None) -> None:
        # 合并通用词表 + 平台专属词表（缓存合并结果）
        self.platform = (platform or "").lower() or None
        self._cues = merge_lexicon(_BASE_CUES, get_platform_lexicon(self.platform))
        self._markers = get_platform_markers(self.platform)

    def label(self, text: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        t = text or ""
        pos_hits, neg_hits, stance_pos, stance_neg = _polarity_hits(t, self._cues)
        pos_n, neg_n = len(pos_hits), len(neg_hits)

        # —— 立场 —— #
        # mixed 判据改为「同一文本内正负极性冲突」：支持性表达常落在情绪词表
        # （如「佩服」），旧判据要求两套立场词表各自命中，会漏判 mixed。
        if pos_hits and neg_hits:
            stance = "mixed"
            stance_conf = min(0.6, 0.35 + 0.05 * (pos_n + neg_n))
        elif stance_pos:
            stance = "support"
            stance_conf = min(0.85, 0.4 + 0.08 * len(stance_pos))
        elif stance_neg:
            stance = "oppose"
            stance_conf = min(0.85, 0.4 + 0.08 * len(stance_neg))
        elif pos_hits or neg_hits:
            stance = "neutral"  # 有褒贬但未站队
            stance_conf = 0.45
        else:
            stripped = t.strip()
            if len(stripped) < 2 or re.fullmatch(r"[\W\d_\s\[\]【】#@]+", stripped or ""):
                stance = "unclear"
                stance_conf = 0.25
            else:
                stance = "neutral"
                stance_conf = 0.45

        # —— 情绪（独立） —— #
        if pos_n == 0 and neg_n == 0:
            sentiment = 0.0
            sent_conf = 0.35
        else:
            raw = (pos_n - neg_n) / max(1, pos_n + neg_n)
            sentiment = max(-1.0, min(1.0, raw * (0.5 + 0.1 * min(5, pos_n + neg_n))))
            sent_conf = min(0.85, 0.4 + 0.06 * (pos_n + neg_n))

        # 综合置信：立场与情绪置信的温和平均
        conf = 0.6 * stance_conf + 0.4 * sent_conf

        tags: list[str] = []
        for name, keys in TOPIC_RULES:
            if name == "情绪表达":
                if pos_hits or neg_hits:
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
