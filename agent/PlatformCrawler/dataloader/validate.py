"""
D_platform 完整性校验（DATASET_SPEC §3.2 / §5.3 / §12）
"""

from __future__ import annotations

from typing import Any


class DatasetSpecError(ValueError):
    pass


def validate_d_platform(d: dict[str, Any], *, strict: bool = True) -> list[str]:
    errors: list[str] = []

    def err(msg: str) -> None:
        errors.append(msg)

    if d.get("schema_version") != "dataset_schema_v1":
        err(f"schema_version must be dataset_schema_v1, got {d.get('schema_version')}")

    meta = d.get("D_meta")
    texts = d.get("D_text")
    series = d.get("D_ts")
    if not isinstance(meta, dict):
        err("D_meta missing")
        _raise_or_return(errors, strict)
        return errors
    if not isinstance(texts, list):
        err("D_text must be list")
    if not isinstance(series, list):
        err("D_ts must be list")
        _raise_or_return(errors, strict)
        return errors

    n_buckets = meta.get("n_buckets")
    if n_buckets != len(series):
        err(f"n_buckets ({n_buckets}) != len(D_ts) ({len(series)})")

    # 有效文本计数
    n_eff = sum(
        1
        for t in texts
        if not t.get("is_empty_placeholder") and str(t.get("text") or "").strip()
    )
    if meta.get("n_text") != n_eff:
        err(f"n_text ({meta.get('n_text')}) != effective texts ({n_eff})")

    if meta.get("is_empty") is True:
        if n_eff != 0:
            err("is_empty=true but n_text>0")
        if meta.get("stance_global") != "neutral":
            err("is_empty=true requires stance_global=neutral")
        if float(meta.get("bias_score") or 0) != 0:
            err("is_empty=true requires bias_score=0")

    tr = meta.get("time_range") or {}
    if not tr.get("start") or not tr.get("end"):
        err("time_range.start/end required")
    elif str(tr["start"]) >= str(tr["end"]):
        err("time_range.start must be < end")

    # D_ts 升序、无重复
    prev = None
    for i, b in enumerate(series):
        ts = b.get("ts")
        if prev is not None and not (str(prev) < str(ts)):
            err(f"D_ts not strictly increasing at {i}: {prev} -> {ts}")
        prev = ts
        if b.get("is_empty"):
            if float(b.get("volume") or 0) != 0 or float(b.get("heat") or 0) != 0:
                err(f"empty bucket {ts} must have volume=heat=0")
        else:
            s = (
                float(b.get("stance_pos_ratio") or 0)
                + float(b.get("stance_neg_ratio") or 0)
                + float(b.get("stance_neu_ratio") or 0)
                + float(b.get("stance_mixed_ratio") or 0)
            )
            if abs(s - 1.0) > 1e-6:
                err(f"bucket {ts} stance ratios sum={s}, want 1")

    # content_id 唯一
    ids = [str(t.get("content_id")) for t in texts]
    if len(ids) != len(set(ids)):
        err("D_text content_id not unique")

    # bucket_ts 可对齐
    bucket_set = {str(b.get("ts")) for b in series}
    for t in texts:
        bt = str(t.get("bucket_ts"))
        if bt not in bucket_set:
            err(f"bucket_ts {bt} not in D_ts")

    required_meta = [
        "platform",
        "keyword",
        "time_range",
        "timezone",
        "granularity",
        "n_text",
        "n_buckets",
        "empty_ratio",
        "is_empty",
        "stance_global",
        "bias_score",
        "confidence",
        "clean_rule_version",
        "source_skill_versions",
    ]
    for k in required_meta:
        if k not in meta:
            err(f"D_meta missing {k}")

    _raise_or_return(errors, strict)
    return errors


def _raise_or_return(errors: list[str], strict: bool) -> None:
    if errors and strict:
        raise DatasetSpecError("D_platform validation failed:\n- " + "\n- ".join(errors))
