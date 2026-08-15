"""
核心：逐条标注 + 汇总 stance_profile + 刷新 D_platform。
"""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any

from PlatformCrawler.dataloader.validate import validate_d_platform

from .labelers import BaseLabeler, LexiconLabeler
from .recompute import STANCE_PROFILER_VERSION, recompute_after_labeling


def _extract_keywords(texts: list[dict[str, Any]], top_k: int = 8) -> list[dict[str, Any]]:
    """从 topic_tags 与短词共现做简单簇统计。"""
    tag_counter: Counter[str] = Counter()
    tag_examples: dict[str, list[str]] = {}
    for t in texts:
        cid = str(t.get("content_id"))
        for tag in t.get("topic_tags") or []:
            tag_counter[tag] += 1
            tag_examples.setdefault(tag, [])
            if len(tag_examples[tag]) < 3:
                tag_examples[tag].append(cid)

    clusters = []
    for tag, cnt in tag_counter.most_common(top_k):
        clusters.append(
            {
                "label": tag,
                "weight": float(cnt),
                "sample_content_ids": tag_examples.get(tag, []),
            }
        )
    return clusters


def build_stance_profile(
    d_platform: dict[str, Any],
    *,
    stance_conf_by_id: dict[str, float],
    labeler: BaseLabeler,
) -> dict[str, Any]:
    meta = d_platform["D_meta"]
    texts = [
        t
        for t in d_platform["D_text"]
        if not t.get("is_empty_placeholder") and str(t.get("text") or "").strip()
    ]
    n = len(texts)
    if n == 0:
        return {
            "stance_global": "neutral",
            "bias_score": 0.0,
            "confidence": 0.15,
            "sentiment_global_mean": None,
            "sentiment_dist": {"pos": 0.0, "neu": 1.0, "neg": 0.0},
            "stance_ratios": {
                "support": 0.0,
                "oppose": 0.0,
                "neutral": 1.0,
                "mixed": 0.0,
                "unclear": 0.0,
            },
            "keyword_clusters": [],
            "n_labeled": 0,
            "model_version": STANCE_PROFILER_VERSION,
            "labeler": f"{labeler.name}:{labeler.version}",
            "platform": meta.get("platform"),
            "keyword": meta.get("keyword"),
        }

    stance_cnt = Counter(str(t.get("stance_label")) for t in texts)
    pos = sum(1 for t in texts if float(t.get("sentiment_score") or 0) > 0.15)
    neg = sum(1 for t in texts if float(t.get("sentiment_score") or 0) < -0.15)
    neu = n - pos - neg

    ratios = {
        "support": stance_cnt.get("support", 0) / n,
        "oppose": stance_cnt.get("oppose", 0) / n,
        "neutral": stance_cnt.get("neutral", 0) / n,
        "mixed": stance_cnt.get("mixed", 0) / n,
        "unclear": stance_cnt.get("unclear", 0) / n,
    }

    return {
        "stance_global": meta.get("stance_global"),
        "bias_score": meta.get("bias_score"),
        "confidence": meta.get("confidence"),
        "sentiment_global_mean": meta.get("sentiment_global_mean"),
        "sentiment_dist": {
            "pos": pos / n,
            "neu": neu / n,
            "neg": neg / n,
        },
        "stance_ratios": ratios,
        "keyword_clusters": _extract_keywords(texts),
        "n_labeled": n,
        "model_version": STANCE_PROFILER_VERSION,
        "labeler": f"{labeler.name}:{labeler.version}",
        "platform": meta.get("platform"),
        "keyword": meta.get("keyword"),
        "time_range": meta.get("time_range"),
    }


def profile_d_platform(
    d_platform: dict[str, Any],
    *,
    labeler: BaseLabeler | None = None,
    inplace: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    返回 (刷新后的 D_platform, stance_profile)。
    """
    if not inplace:
        d_platform = copy.deepcopy(d_platform)

    if "D_meta" not in d_platform or "D_text" not in d_platform or "D_ts" not in d_platform:
        raise ValueError("输入不是合法 D_platform，请先运行 PlatformCrawler")

    if labeler is None:
        platform = str((d_platform.get("D_meta") or {}).get("platform") or "")
        labeler = LexiconLabeler(platform=platform or None)
    stance_conf_by_id: dict[str, float] = {}

    for t in d_platform["D_text"]:
        if t.get("is_empty_placeholder"):
            continue
        text = str(t.get("text") or "")
        if not text.strip():
            t["stance_label"] = "unclear"
            t["sentiment_score"] = 0.0
            t["topic_tags"] = []
            stance_conf_by_id[str(t.get("content_id"))] = 0.2
            continue

        ann = labeler.label(text, context={"content_id": t.get("content_id")})
        t["stance_label"] = ann["stance_label"]
        t["sentiment_score"] = float(ann["sentiment_score"])
        t["topic_tags"] = list(ann.get("topic_tags") or [])
        stance_conf_by_id[str(t.get("content_id"))] = float(ann.get("stance_conf") or 0.4)

    recompute_after_labeling(
        d_platform,
        stance_conf_by_id=stance_conf_by_id,
        labeler_name=labeler.name,
        labeler_version=labeler.version,
    )
    validate_d_platform(d_platform)
    profile = build_stance_profile(
        d_platform, stance_conf_by_id=stance_conf_by_id, labeler=labeler
    )
    return d_platform, profile
