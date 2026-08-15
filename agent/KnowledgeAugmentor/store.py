"""
Skill4 核心：本地知识库写入 + BM25 检索（备用补充，非主路径）。

写入：取高 evidence_weight 文本入库（is_empty 跳过），主键 (platform, content_id) 去重。
检索：BM25 召回 + 时间/立场/平台过滤 + 同类事件历史对照。
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

SKILL_VERSION = "knowledge_augmentor_v1"
STORE_DIR = Path(__file__).resolve().parent / "store"
INDEX_PATH = STORE_DIR / "index.jsonl"


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


def _ts_iso(ts: str | None) -> str:
    return str(ts or "")


class KnowledgeStore:
    """append-only JSONL 本地库；同一进程内多轮写入/检索复用。"""

    def __init__(self, index_path: str | Path | None = None) -> None:
        self.index_path = Path(index_path) if index_path else INDEX_PATH
        self.docs: list[dict[str, Any]] = []
        self._tokens: list[list[str]] = []
        self._load()

    def _load(self) -> None:
        if not self.index_path.exists():
            return
        with self.index_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    doc = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self.docs.append(doc)
                self._tokens.append(_tokenize(str(doc.get("text") or "")))

    def _append(self, doc: dict[str, Any]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        self.docs.append(doc)
        self._tokens.append(_tokenize(str(doc.get("text") or "")))

    # ---------- 写入 ---------- #
    def write_d_platform(
        self, d_platform: dict[str, Any], *, min_evidence_weight: float = 0.5, top_k: int = 200
    ) -> dict[str, Any]:
        meta = d_platform.get("D_meta") or {}
        if meta.get("is_empty"):
            return {"written": 0, "skipped": 0, "reason": "is_empty", "index_uri": str(self.index_path)}

        texts = [
            t
            for t in d_platform.get("D_text") or []
            if not t.get("is_empty_placeholder") and str(t.get("text") or "").strip()
        ]
        texts.sort(key=lambda t: -float(t.get("evidence_weight") or 0))
        candidates = [t for t in texts if float(t.get("evidence_weight") or 0) >= min_evidence_weight]
        if len(candidates) < top_k:
            candidates = texts[:top_k]

        existing = {(d.get("platform"), d.get("content_id")) for d in self.docs}
        written = 0
        for t in candidates:
            key = (str(meta.get("platform")), str(t.get("content_id")))
            if key in existing:
                continue
            self._append(
                {
                    "platform": meta.get("platform"),
                    "keyword": meta.get("keyword"),
                    "content_id": str(t.get("content_id")),
                    "parent_id": t.get("parent_id"),
                    "author_id": t.get("author_id"),
                    "ts": t.get("ts"),
                    "ts_unix": t.get("ts_unix"),
                    "text": t.get("text"),
                    "stance_label": t.get("stance_label"),
                    "sentiment_score": t.get("sentiment_score"),
                    "evidence_weight": t.get("evidence_weight"),
                    "bucket_ts": t.get("bucket_ts"),
                    "time_range": meta.get("time_range"),
                    "source_url": t.get("source_url"),
                    "ext": t.get("ext") or {},
                }
            )
            existing.add(key)
            written += 1
        return {
            "written": written,
            "skipped": len(candidates) - written,
            "reason": None,
            "index_uri": str(self.index_path),
        }

    # ---------- 检索 ---------- #
    def _bm25(self, query: str) -> list[float]:
        q = _tokenize(query)
        n = len(self.docs)
        if n == 0 or not q:
            return [0.0] * n
        doc_lens = [len(tk) for tk in self._tokens]
        avgdl = sum(doc_lens) / n or 1.0
        df: Counter[str] = Counter()
        for tk in self._tokens:
            for w in set(tk):
                df[w] += 1
        k1, b = 1.5, 0.75
        scores = [0.0] * n
        for i, tk in enumerate(self._tokens):
            tf = Counter(tk)
            dl = doc_lens[i]
            s = 0.0
            for w in q:
                if w not in df:
                    continue
                idf = math.log((n - df[w] + 0.5) / (df[w] + 0.5) + 1.0)
                f = tf.get(w, 0)
                s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / avgdl))
            scores[i] = s
        return scores

    def _history_cases(self, keyword: str) -> list[dict[str, Any]]:
        """按关键词召回历史入库的不同时间窗摘要。"""
        groups: dict[tuple[str, str, str], dict[str, Any]] = {}
        for d in self.docs:
            if not keyword or keyword not in str(d.get("keyword") or ""):
                continue
            tr = d.get("time_range") or {}
            key = (
                str(d.get("platform")),
                str(tr.get("start") or ""),
                str(tr.get("end") or ""),
            )
            if key not in groups:
                groups[key] = {
                    "platform": d.get("platform"),
                    "keyword": d.get("keyword"),
                    "time_range": tr,
                    "n": 0,
                    "sample_content_ids": [],
                }
            g = groups[key]
            g["n"] += 1
            if len(g["sample_content_ids"]) < 3:
                g["sample_content_ids"].append(str(d.get("content_id")))
        return sorted(groups.values(), key=lambda g: -g["n"])

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 8,
        time_range: tuple[str | None, str | None] | None = None,
        stance_label: str | None = None,
        platform: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        scores = self._bm25(query)
        start, end = time_range or (None, None)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for s, d in zip(scores, self.docs):
            if s <= 0:
                continue
            if platform and d.get("platform") != platform:
                continue
            if stance_label and d.get("stance_label") != stance_label:
                continue
            ts = _ts_iso(d.get("ts"))
            if start and ts < str(start):
                continue
            if end and ts >= str(end):
                continue
            ranked.append((s, d))
        ranked.sort(key=lambda x: -x[0])
        chunks = [
            {
                "text": d.get("text"),
                "content_id": d.get("content_id"),
                "ts": d.get("ts"),
                "score": round(s, 4),
                "source": d.get("platform"),
                "stance_label": d.get("stance_label"),
                "source_url": d.get("source_url"),
            }
            for s, d in ranked[:top_k]
        ]
        return {
            "augment_used": bool(chunks),
            "rag_chunks": chunks,
            "history_cases": self._history_cases(keyword or query),
            "skill_version": SKILL_VERSION,
            "index_uri": str(self.index_path),
        }
