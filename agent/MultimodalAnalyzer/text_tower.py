"""
文本塔：对桶内高权重样本做分词 + TF-IDF 质心，产出语义漂移与桶级情绪代理。

默认用 jieba（后端依赖已含）；不可用则退化为字符二元组，保证可跑。
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any


def _tokenize(text: str) -> list[str]:
    try:
        import jieba  # type: ignore

        return [w.strip() for w in jieba.cut(text) if w.strip()]
    except ImportError:
        s = text.replace(" ", "")
        if not s:
            return []
        if len(s) == 1:
            return [s]
        return [s[i : i + 2] for i in range(len(s) - 1)]


def _group_texts_by_bucket(
    d_platform: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """把非占位有效文本按 bucket_ts 分组；bucket_order 与 D_ts 对齐。"""
    order = [str(b["ts"]) for b in d_platform["D_ts"]]
    grouped: dict[str, list[dict[str, Any]]] = {ts: [] for ts in order}
    for t in d_platform["D_text"]:
        if t.get("is_empty_placeholder"):
            continue
        if not str(t.get("text") or "").strip():
            continue
        bts = str(t.get("bucket_ts"))
        if bts in grouped:
            grouped[bts].append(t)
    return grouped, order


def _df_tfidf(docs: list[list[str]]) -> tuple[dict[str, float], list[Counter[str]]]:
    """计算全局 idf 与每个文档的 tf 词频。"""
    n = len(docs)
    df: Counter[str] = Counter()
    for doc in docs:
        for w in set(doc):
            df[w] += 1
    idf = {w: math.log((1 + n) / (1 + c)) + 1.0 for w, c in df.items()}
    tfs = [Counter(d) for d in docs]
    return idf, tfs


def _centroid(tf: Counter[str], idf: dict[str, float]) -> dict[str, float]:
    vec = {w: float(c) * idf.get(w, 1.0) for w, c in tf.items()}
    norm = math.sqrt(sum(x * x for x in vec.values())) or 1.0
    return {w: x / norm for w, x in vec.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    num = sum(a[w] * b[w] for w in common)
    na = math.sqrt(sum(x * x for x in a.values())) or 1.0
    nb = math.sqrt(sum(x * x for x in b.values())) or 1.0
    return num / (na * nb)


def analyze_text_tower(d_platform: dict[str, Any]) -> dict[str, Any]:
    """
    返回:
      bucket_order[]              — 与 D_ts 对齐的桶序列
      bucket_sentiment[]          — 桶级证据加权情绪（D_text 侧）
      bucket_volume[]             — 桶内有效文本条数
      drift_sim[]                 — 相邻桶 TF-IDF 质心余弦相似度（长度 = len-1，与后桶对齐）
      top_terms[]                 — 全局高频词（供结论引用）
    """
    grouped, order = _group_texts_by_bucket(d_platform)
    docs: list[list[str]] = []
    bucket_sentiment: list[float | None] = []
    bucket_volume: list[int] = []
    for ts in order:
        items = grouped[ts]
        texts = [t for t in items]
        tokens = [tk for t in texts for tk in _tokenize(str(t.get("text") or ""))]
        docs.append(tokens)
        bucket_volume.append(len(texts))
        if texts:
            num = sum(
                float(t.get("evidence_weight") or 0) * float(t.get("sentiment_score") or 0)
                for t in texts
            )
            den = sum(float(t.get("evidence_weight") or 0) for t in texts)
            bucket_sentiment.append(num / den if den > 0 else 0.0)
        else:
            bucket_sentiment.append(None)

    idf, tfs = _df_tfidf(docs)
    centroids = [_centroid(tf, idf) for tf in tfs]
    drift_sim: list[float | None] = []
    for i in range(1, len(centroids)):
        if bucket_volume[i - 1] and bucket_volume[i]:
            drift_sim.append(_cosine(centroids[i - 1], centroids[i]))
        else:
            drift_sim.append(None)

    top_terms = sorted(idf.items(), key=lambda kv: -kv[1])[:20]
    return {
        "bucket_order": order,
        "bucket_sentiment": bucket_sentiment,
        "bucket_volume": bucket_volume,
        "drift_sim": drift_sim,
        "top_terms": [w for w, _ in top_terms],
        "tokenizer": "jieba" if _has_jieba() else "char_bigram",
    }


def _has_jieba() -> bool:
    try:
        import jieba  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False
