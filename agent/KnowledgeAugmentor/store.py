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

SKILL_VERSION = "knowledge_augmentor_v2_case_icl"
STORE_DIR = Path(__file__).resolve().parent / "store"
INDEX_PATH = STORE_DIR / "index.jsonl"
CASE_METRICS = ("volume", "heat", "topic_heat", "sent_mean")
SEVERITY_RANK = {"none": 0, "warning": 1, "important": 2, "critical": 3}


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


def _case_id(d_platform: dict[str, Any]) -> str:
    meta = d_platform.get("D_meta") or {}
    time_range = meta.get("time_range") or {}
    return "|".join(
        [
            str(meta.get("platform") or ""),
            str(meta.get("keyword") or ""),
            str(time_range.get("start") or ""),
            str(time_range.get("end") or ""),
            str(meta.get("granularity") or ""),
        ]
    )


def _downsample(values: list[float | None], max_points: int) -> list[float | None]:
    if len(values) <= max_points:
        return values
    compact: list[float | None] = []
    for i in range(max_points):
        lo = i * len(values) // max_points
        hi = max(lo + 1, (i + 1) * len(values) // max_points)
        valid = [v for v in values[lo:hi] if v is not None]
        compact.append(sum(valid) / len(valid) if valid else None)
    return compact


def _z_normalize(values: list[float | None]) -> list[float | None]:
    valid = [float(v) for v in values if v is not None]
    if not valid:
        return [None] * len(values)
    mean = sum(valid) / len(valid)
    variance = sum((value - mean) ** 2 for value in valid) / len(valid)
    std = math.sqrt(variance)
    if std <= 1e-9:
        return [0.0 if value is not None else None for value in values]
    return [
        (float(value) - mean) / std if value is not None else None
        for value in values
    ]


def _series_signature(
    d_platform: dict[str, Any], max_points: int = 48
) -> dict[str, list[float | None]]:
    d_ts = d_platform.get("D_ts") or []
    signature: dict[str, list[float | None]] = {}
    for metric in CASE_METRICS:
        values: list[float | None] = []
        for bucket in d_ts:
            value = bucket.get(metric)
            try:
                values.append(float(value) if value is not None else None)
            except (TypeError, ValueError):
                values.append(None)
        signature[metric] = _z_normalize(_downsample(values, max_points))
    return signature


def _dtw_distance(
    left: list[float | None], right: list[float | None]
) -> float:
    """依赖为零的 DTW；序列已压缩到至多 48 点，适合小型案例库。"""
    if not left or not right:
        return float("inf")
    previous = [float("inf")] * (len(right) + 1)
    previous[0] = 0.0
    for left_value in left:
        current = [float("inf")] * (len(right) + 1)
        for j, right_value in enumerate(right, start=1):
            if left_value is None and right_value is None:
                cost = 0.0
            elif left_value is None or right_value is None:
                cost = 1.5
            else:
                cost = abs(float(left_value) - float(right_value))
            current[j] = cost + min(previous[j], current[j - 1], previous[j - 1])
        previous = current
    return previous[-1] / max(1, len(left) + len(right))


def _signature_distance(
    left: dict[str, list[float | None]],
    right: dict[str, list[float | None]],
) -> float:
    weights = {"volume": 0.35, "heat": 0.25, "topic_heat": 0.25, "sent_mean": 0.15}
    weighted = 0.0
    total_weight = 0.0
    for metric, weight in weights.items():
        distance = _dtw_distance(left.get(metric) or [], right.get(metric) or [])
        if math.isinf(distance):
            continue
        weighted += weight * distance
        total_weight += weight
    return weighted / total_weight if total_weight else float("inf")


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

        existing = {
            (d.get("platform"), d.get("content_id"))
            for d in self.docs
            if d.get("doc_type", "content") == "content"
        }
        written = 0
        for t in candidates:
            key = (str(meta.get("platform")), str(t.get("content_id")))
            if key in existing:
                continue
            self._append(
                {
                    "doc_type": "content",
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

    def write_analysis_case(
        self,
        d_platform: dict[str, Any],
        skill3: dict[str, Any],
    ) -> dict[str, Any]:
        """写入一次已分析事件，供 LLMAD 风格的正常/异常正反例检索。"""
        meta = d_platform.get("D_meta") or {}
        case_id = _case_id(d_platform)
        existing = {
            str(doc.get("case_id"))
            for doc in self.docs
            if doc.get("doc_type") == "analysis_case"
        }
        if case_id in existing:
            return {
                "written": 0,
                "reason": "duplicate",
                "case_id": case_id,
                "index_uri": str(self.index_path),
            }

        anomalies = skill3.get("anomalies") or []
        label = "anomaly" if anomalies else "normal"
        anomaly_types = sorted({str(a.get("type")) for a in anomalies if a.get("type")})
        severity = str((skill3.get("risk_summary") or {}).get("max_severity") or "none")
        evidence_ids: list[str] = []
        for anomaly in anomalies:
            for evidence_id in anomaly.get("evidence_ids") or []:
                value = str(evidence_id)
                if value not in evidence_ids and len(evidence_ids) < 8:
                    evidence_ids.append(value)
        text = " ".join(
            part
            for part in (
                str(meta.get("keyword") or ""),
                str(meta.get("platform") or ""),
                label,
                severity,
                " ".join(anomaly_types),
            )
            if part
        )
        self._append(
            {
                "doc_type": "analysis_case",
                "case_id": case_id,
                "platform": meta.get("platform"),
                "keyword": meta.get("keyword"),
                "time_range": meta.get("time_range") or {},
                "granularity": meta.get("granularity"),
                "case_label": label,
                "label_source": "skill3_weak_label",
                "review_status": "unreviewed",
                "anomaly_types": anomaly_types,
                "severity": severity,
                "signature": _series_signature(d_platform),
                "evidence_ids": evidence_ids,
                "n_text": meta.get("n_text"),
                "empty_ratio": meta.get("empty_ratio"),
                "text": text,
            }
        )
        return {
            "written": 1,
            "reason": None,
            "case_id": case_id,
            "case_label": label,
            "index_uri": str(self.index_path),
        }

    # ---------- 检索 ---------- #
    def _bm25(self, query: str) -> list[float]:
        q = _tokenize(query)
        content_indices = [
            i
            for i, doc in enumerate(self.docs)
            if doc.get("doc_type", "content") == "content"
        ]
        n = len(content_indices)
        scores = [0.0] * len(self.docs)
        if n == 0 or not q:
            return scores
        doc_lens = {i: len(self._tokens[i]) for i in content_indices}
        avgdl = sum(doc_lens.values()) / n or 1.0
        df: Counter[str] = Counter()
        for i in content_indices:
            tk = self._tokens[i]
            for w in set(tk):
                df[w] += 1
        k1, b = 1.5, 0.75
        for i in content_indices:
            tk = self._tokens[i]
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
            if d.get("doc_type", "content") != "content":
                continue
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
            if d.get("doc_type", "content") != "content":
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

    def retrieve_analysis_examples(
        self,
        d_platform: dict[str, Any],
        *,
        top_anomaly: int = 2,
        top_normal: int = 1,
    ) -> dict[str, Any]:
        """按多变量 z-normalized DTW 召回相似异常例和正常例。"""
        current_id = _case_id(d_platform)
        current_signature = _series_signature(d_platform)
        current_platform = str((d_platform.get("D_meta") or {}).get("platform") or "")
        ranked: list[tuple[float, dict[str, Any]]] = []
        for doc in self.docs:
            if doc.get("doc_type") != "analysis_case":
                continue
            if str(doc.get("case_id")) == current_id:
                continue
            distance = _signature_distance(
                current_signature,
                doc.get("signature") or {},
            )
            if math.isinf(distance):
                continue
            if current_platform and str(doc.get("platform") or "") != current_platform:
                distance += 0.15
            ranked.append((distance, doc))
        ranked.sort(key=lambda item: item[0])

        def render(label: str, limit: int) -> list[dict[str, Any]]:
            examples: list[dict[str, Any]] = []
            for distance, doc in ranked:
                if doc.get("case_label") != label:
                    continue
                examples.append(
                    {
                        "case_id": doc.get("case_id"),
                        "platform": doc.get("platform"),
                        "keyword": doc.get("keyword"),
                        "time_range": doc.get("time_range"),
                        "case_label": label,
                        "label_source": doc.get("label_source") or "unknown",
                        "review_status": doc.get("review_status") or "unreviewed",
                        "anomaly_types": doc.get("anomaly_types") or [],
                        "severity": doc.get("severity") or "none",
                        "similarity": round(1.0 / (1.0 + distance), 4),
                        "evidence_ids": doc.get("evidence_ids") or [],
                    }
                )
                if len(examples) >= limit:
                    break
            return examples

        anomaly_examples = render("anomaly", top_anomaly)
        normal_examples = render("normal", top_normal)
        return {
            "example_retrieval_used": bool(anomaly_examples or normal_examples),
            "anomaly_examples": anomaly_examples,
            "normal_examples": normal_examples,
            "retrieval_method": "multivariate_znorm_dtw",
            "case_index_size": sum(
                1 for doc in self.docs if doc.get("doc_type") == "analysis_case"
            ),
        }
