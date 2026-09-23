"""立场/情绪词表标注器（LexiconLabeler）的回归测试。

用 ``agent/tools/golden_stance.json`` 锁定四项曾让准确率停在
立场 0.90 / 情绪 0.80 的结构性根因，防止回退：

1. **极性去重**：同一个词可能同时挂在立场词表与情绪词表（如 weibo 的「支持」
   既在 ``support_cues`` 又在 ``pos_sent``），每词只能计一票。旧实现按列表
   各自计数，导致「支持他的勇气，但反对他的做法」正面得 2 票、负面得 1 票。
2. **mixed 判据**：正负极性冲突即为 mixed，不要求两套立场词表各自命中
   （支持性表达常落在情绪词表，如「佩服」）。
3. **否定处理**：极性词前出现否定词时须取反（「不喜欢」不是正面）。
4. **词表归属**：纯情绪词不得挂进立场词表（「心态崩了」不是站队反对）。

残留的 3 条错误均为转折句与无语境歧义，需要从句级结构入手，
不属于本测试的守护范围（见 ``_RESIDUAL``）。
"""

from __future__ import annotations

import json
from pathlib import Path

from StanceProfiler.labelers.lexicon import EMOJI_NEG, EMOJI_POS, LexiconLabeler

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT / "agent" / "tools" / "golden_stance.json").read_text(encoding="utf-8"))

# 已知残留：转折句（「既…又…」「虽然…但…」）与无语境单梗。
# 与 golden 的差异集合必须始终是它的子集——新增差异即视为回退。
_RESIDUAL = {
    "我既佩服他的勇气，又觉得这做法离谱",  # 转折句，前分句为次
    "虽然不喜欢他，但这次做得对",  # 转折句 + 隐性肯定
    "绝了",  # 无语境歧义（赞叹 / 反讽）
}


def _sentiment_class(score: float) -> str:
    """与 tools/evaluate_skills.py 保持同一判定阈值。"""
    if score > 0.15:
        return "pos"
    if score < -0.15:
        return "neg"
    return "neu"


def _label(text: str, platform: str) -> dict:
    return LexiconLabeler(platform=platform).label(text)


def _golden_errors() -> set[str]:
    errors: set[str] = set()
    labelers: dict[str, LexiconLabeler] = {}
    for item in GOLDEN:
        platform = item["platform"]
        labelers.setdefault(platform, LexiconLabeler(platform=platform))
        ann = labelers[platform].label(item["text"])
        if (
            ann["stance_label"] != item["stance"]
            or _sentiment_class(float(ann["sentiment_score"])) != item["sentiment"]
        ):
            errors.add(item["text"])
    return errors


def test_no_new_errors_on_golden_set():
    """golden 集上不允许出现新的错误条目。"""
    new_errors = _golden_errors() - _RESIDUAL
    assert not new_errors, f"出现新的标注错误：{sorted(new_errors)}"


def test_golden_accuracy_floor():
    """整体准确率不得低于修复后的水位。"""
    n = len(GOLDEN)
    stance_ok = sentiment_ok = 0
    labelers: dict[str, LexiconLabeler] = {}
    for item in GOLDEN:
        platform = item["platform"]
        labelers.setdefault(platform, LexiconLabeler(platform=platform))
        ann = labelers[platform].label(item["text"])
        stance_ok += ann["stance_label"] == item["stance"]
        sentiment_ok += _sentiment_class(float(ann["sentiment_score"])) == item["sentiment"]
    assert stance_ok / n >= 0.95, f"立场准确率回退到 {stance_ok / n:.4f}"
    assert sentiment_ok / n >= 0.95, f"情绪准确率回退到 {sentiment_ok / n:.4f}"


def test_symmetric_stance_and_sentiment_balance_to_mixed():
    """根因 1：两边表态对称时应判 mixed，且情绪相互抵消为中性。"""
    ann = _label("支持他的勇气，但反对他的做法", "weibo")
    assert ann["stance_label"] == "mixed"
    assert abs(float(ann["sentiment_score"])) <= 0.15


def test_stance_words_also_carry_valence():
    """根因 1：只靠立场词表达极性的短文本，情绪不能退化成中性。"""
    assert _label("支持正能量", "douyin")["sentiment_score"] > 0.15
    assert _label("反对这种行为", "douyin")["sentiment_score"] < -0.15
    assert _label("前排支持，白嫖失败", "bilibili")["sentiment_score"] > 0.15


def test_mixed_detected_from_polarity_conflict():
    """根因 2：支持性表达落在情绪词表（「佩服」）时也要能识别 mixed。"""
    assert _label("我既佩服他的勇气，又觉得这做法离谱", "bilibili")["stance_label"] == "mixed"


def test_negation_flips_polarity():
    """根因 3：「不喜欢」里的「喜欢」必须被否定，不能贡献正面极性。"""
    assert _label("虽然不喜欢他，但这次做得对", "weibo")["sentiment_score"] < 0.15
    assert _label("我一点也不喜欢这个", "weibo")["sentiment_score"] < 0


def test_negated_phrase_wins_over_inner_positive_word():
    """根因 3：长负向短语优先匹配，「不推荐」内部的「推荐」不得算正面。"""
    assert _label("不推荐这家店", "xiaohongshu")["sentiment_score"] < 0
    assert _label("实在看不惯这种行为", "weibo")["sentiment_score"] < 0


def test_pure_emotion_words_are_not_stance():
    """根因 4：纯情绪宣泄不构成站队。"""
    ann = _label("裂开了，心态崩了", "bilibili")
    assert ann["stance_label"] == "neutral"
    assert float(ann["sentiment_score"]) < -0.15


def test_ambiguous_slang_is_not_scored_as_stance():
    """根因 4：无语境的歧义单梗不应被判成支持。"""
    ann = _label("绝了", "douyin")
    assert ann["stance_label"] not in ("support", "oppose")
    assert _sentiment_class(float(ann["sentiment_score"])) != "pos"


def test_emoji_lists_are_wired_into_polarity():
    """表情符号词表仍参与极性打分（重构后不得被遗漏）。"""
    assert _label(EMOJI_POS[0], "bilibili")["sentiment_score"] > 0
    assert _label(EMOJI_NEG[0], "bilibili")["sentiment_score"] < 0


def test_output_contract_preserved():
    """label() 的输出契约被 PlatformCrawler / profiler / evaluate_skills 依赖。"""
    ann = _label("三连了，这期真的封神", "bilibili")
    assert set(ann) == {"stance_label", "sentiment_score", "stance_conf", "topic_tags"}
    assert isinstance(ann["topic_tags"], list)
    assert 0.0 <= float(ann["stance_conf"]) <= 1.0
    assert -1.0 <= float(ann["sentiment_score"]) <= 1.0


def test_empty_and_punctuation_only_inputs():
    """空文本与纯符号不得抛错，立场应为 unclear。"""
    for text in ("", "？", "...", "   "):
        assert _label(text, "douyin")["stance_label"] == "unclear"
