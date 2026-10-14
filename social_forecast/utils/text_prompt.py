# -*- coding: utf-8 -*-
"""Prompt construction for the multimodal (text + numeric) forecaster.

WHY THIS FILE EXISTS
--------------------
The original prompt builder was an inline blob inside
``Exp_Long_Term_Forecast_Clip.get_text_emb``.  It accepted ``batch_text`` and then
never used it, so the prompt was a deterministic function of the numerical input
window and **the text could not reach the model at all**.  That made every
"text does not help" measurement structurally unfalsifiable.

This module makes the prompt a pure, unit-testable function so the wiring can be
asserted without a model:

    build_prompt(window, raw_text, source="template")   -> the historical prompt
    build_prompt(window, raw_text, source="raw_text")   -> the historical prompt + the text

PROMPT SOURCES (FLAG A)
-----------------------
``template``      EXACT byte-for-byte reproduction of the old behaviour: the numeric
                  window only, text ignored.  This is the text-blind baseline and
                  the regression anchor.
``raw_text``      the same numeric block, with the CSV ``fact`` cell appended.
                  Nothing else changes, so the template-vs-raw_text comparison
                  isolates "does adding text help?".
``rebuilt_text``  same as ``raw_text`` but reads the rebuilt corpus.  The rebuilt
                  corpus is owned by a different worker; if it is not present yet
                  the prompt falls back to the explicit NO-TEXT token (never to the
                  numeric template) and the run logs it.

IRON RULE-ADJACENT NOTE: everything in this file is a function of
(numeric window, text cell).  None of it is used to compute ground-truth primitive
labels ``v*_{t,k}``; labelling stays a function of ``Y_t`` only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

PROMPT_SOURCES = ("template", "raw_text", "rebuilt_text", "oracle", "oracle_strict")

PROMPT_PREFIX = ("<|start_prompt|Make predictions about the future based on the "
                 "following information:")
PROMPT_SUFFIX = "<|<end_prompt>|>"

# EXACT copy of the template in the original implementation. Do not "clean" the
# trailing formatting; `{ot_values}` is filled with a python list, so the prompt
# literally contains  ['1.00', '2.00', ...]  -- which is part of the old behaviour
# we must be able to reproduce byte-for-byte.
NUMERIC_TEMPLATE = """- Complete data: {ot_values}
- Start value: {start_value:.2f}
- End value: {end_value:.2f}
- Maximum fluctuation: {max_delta:.2f} (occurred at hour {max_pos})
- Trend slope: {trend:.2f}/h
- Standard deviation: {std:.2f}"""

#: inserted when a sample has no usable text.  NEVER fall back to the numeric
#: template here: that would silently turn a text-blind sample into a
#: text-wired one and corrupt the attribution the factorial is trying to make.
NO_TEXT_TOKEN = "<|no_text_available|>"

TEXT_SECTION_HEADER = "\n- Related event text: "

#: default character budget for the appended text.  The tokenizer truncates at
#: ``max_length`` tokens anyway; a char budget keeps the numeric head of the
#: prompt (which comes first) intact instead of letting a 6 kB RAG blob push it out.
TEXT_CHAR_BUDGET = 900

#: strings that mean "there is no text" in the shipped CSVs
_EMPTY_PATTERNS = (r"^\s*$", r"^\s*na\s*$", r"^\s*n/?a\.?\s*$", r"^\s*none\s*$",
                   r"^\s*null\s*$", r"^\s*nan\s*$")

#: RAG boilerplate that carries no prediction-relevant content
_BOILERPLATE_PATTERNS = (
    r"if you could provide more relevant search results",
    r"no useful information can be extracted",
    r"the provided search results do not",
    r"i would be happy to assist",
    r"not contain any relevant information",
    r"no relevant information",
)

_DOC_SPLIT = re.compile(r"\s*;\s*(?=\d{4}-\d{2}-\d{2}\s*:)")


# ---------------------------------------------------------------------------
# small helpers (all pure)
# ---------------------------------------------------------------------------

def numeric_stats(window: np.ndarray) -> Dict[str, float]:
    """The stats dict of the ORIGINAL implementation, unchanged."""
    v = np.asarray(window, dtype=float).ravel()
    seq_len = int(v.size)
    d = np.abs(np.diff(v)) if seq_len > 1 else np.zeros(1)
    return {
        "start_value": float(v[0]),
        "end_value": float(v[-1]),
        "max_delta": float(np.max(d)),
        "max_pos": int(np.argmax(d) + 1),
        "trend": float(np.polyfit(range(seq_len), v, 1)[0]) if seq_len > 1 else 0.0,
        "std": float(np.std(v)),
    }


def build_numeric_block(window: np.ndarray) -> str:
    """The historical numeric prompt body (no prefix/suffix)."""
    v = np.asarray(window, dtype=float).ravel()
    return NUMERIC_TEMPLATE.format(
        ot_values=[f"{x:.2f}" for x in v], **numeric_stats(v))


def build_template_prompt(window: np.ndarray) -> str:
    """Byte-for-byte the prompt the original code produced."""
    return PROMPT_PREFIX + build_numeric_block(window) + PROMPT_SUFFIX


# ---------------------------------------------------------------------------
# calendar / date prior (injected into the four-component endogenous prompts)
# ---------------------------------------------------------------------------

_MONTH_NAME = (
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_MET_SEASON = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
}


def parse_date_str(s: Optional[str]):
    """Parse ``YYYY-MM-DD`` / ``YYYYMM`` / ``YYYY-MM`` → ``datetime.date`` or None."""
    from datetime import date, datetime
    if s is None:
        return None
    t = str(s).strip()
    if not t or t.lower() in ("nan", "none", "nat"):
        return None
    if re.fullmatch(r"\d{6}", t):
        try:
            return datetime.strptime(t, "%Y%m").date()
        except ValueError:
            return None
    if re.fullmatch(r"\d{4}", t):
        try:
            return date(int(t), 1, 1)
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y%m%d", "%Y%m", "%Y"):
        try:
            return datetime.strptime(t[:10] if fmt.startswith("%Y-%m-%d") else t, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(t[:10]).date()
    except ValueError:
        return None


def calendar_features(dates: Optional[Sequence[Optional[str]]],
                      pred_len: int = 0) -> Dict[str, object]:
    """Structured calendar features for a history window (+ optional horizon).

    ``dates`` aligns with the history steps (length L).  The last entry is the
    forecast origin.  Features are deterministic functions of the calendar only
    (no future *values*) — safe for option-A endogenous prompts.
    """
    from datetime import date, timedelta
    parsed = [parse_date_str(d) for d in (dates or [])]
    valid = [d for d in parsed if d is not None]
    feat: Dict[str, object] = {
        "has_calendar": bool(valid),
        "origin": None,
        "start": None,
        "end": None,
        "months": [],
        "years": [],
        "quarters": [],
        "seasons": [],
        "month_names": [],
        "origin_month": None,
        "origin_quarter": None,
        "origin_season": None,
        "origin_year": None,
        "steps_to_year_end": None,
        "steps_to_quarter_end": None,
        "horizon_months": [],
        "span_desc": "calendar unavailable",
    }
    if not valid:
        return feat
    origin = parsed[-1] if parsed[-1] is not None else valid[-1]
    start = parsed[0] if parsed[0] is not None else valid[0]
    feat["origin"] = origin.isoformat()
    feat["start"] = start.isoformat()
    feat["end"] = origin.isoformat()
    feat["origin_month"] = origin.month
    feat["origin_year"] = origin.year
    feat["origin_quarter"] = (origin.month - 1) // 3 + 1
    feat["origin_season"] = _MET_SEASON[origin.month]
    months, years, quarters, seasons, names = [], [], [], [], []
    for d in parsed:
        if d is None:
            months.append(None); years.append(None); quarters.append(None)
            seasons.append(None); names.append(None)
            continue
        months.append(d.month)
        years.append(d.year)
        quarters.append((d.month - 1) // 3 + 1)
        seasons.append(_MET_SEASON[d.month])
        names.append(_MONTH_NAME[d.month])
    feat["months"] = months
    feat["years"] = years
    feat["quarters"] = quarters
    feat["seasons"] = seasons
    feat["month_names"] = names
    # month-steps to calendar boundaries (monthly series assumption)
    feat["steps_to_year_end"] = 12 - origin.month
    q_end_month = feat["origin_quarter"] * 3
    feat["steps_to_quarter_end"] = q_end_month - origin.month
    # foresight *calendar* only (not values): next pred_len months
    horiz = []
    y, m = origin.year, origin.month
    for _ in range(max(0, int(pred_len))):
        m += 1
        if m > 12:
            m = 1
            y += 1
        horiz.append(f"{_MONTH_NAME[m]} {y} (Q{(m - 1) // 3 + 1}, {_MET_SEASON[m]})")
    feat["horizon_months"] = horiz
    feat["span_desc"] = (
        f"{start.isoformat()} → {origin.isoformat()} "
        f"({len(valid)} dated steps; origin={_MONTH_NAME[origin.month]} {origin.year}, "
        f"Q{feat['origin_quarter']}, {_MET_SEASON[origin.month]})"
    )
    return feat


# Calendar text policy
#   off   : no calendar string
#   short : one-line origin tag (default; avoids diluting GPT avg-pool)
#   full  : verbose block (history + horizon) — often hurts non-seasonal domains
CALENDAR_MODES = ("off", "short", "full")


def build_calendar_block(dates: Optional[Sequence[Optional[str]]],
                         pred_len: int = 0,
                         focus: str = "all",
                         mode: str = "short") -> str:
    """Natural-language calendar prior for prompt injection.

    ``focus`` ∈ {all, T, S, C, R}.  Under the stable policy, only ``S`` (and
    ``all``) receive calendar text; T/C/R return empty so event/fact semantics
    are not washed out by month boilerplate.

    ``mode``: off | short | full.
    """
    mode = (mode or "short").lower()
    if mode not in CALENDAR_MODES:
        raise ValueError(f"calendar mode must be in {CALENDAR_MODES}, got {mode}")
    if mode == "off":
        return ""

    focus_u = (focus or "all").upper()
    # stable default: calendar is a *seasonal* cue, not a global prefix
    if focus_u in ("T", "C", "R"):
        return ""

    f = calendar_features(dates, pred_len=pred_len)
    if not f["has_calendar"]:
        return ""

    # short: single line — enough for phase grounding, cheap on token budget
    short = (
        f"- Calendar origin: {_MONTH_NAME[f['origin_month']]} {f['origin_year']} "
        f"(Q{f['origin_quarter']}, {f['origin_season']})"
    )
    if mode == "short":
        if focus_u == "S":
            return short + "; use month/quarter to align seasonal phase."
        return short

    # full (legacy verbose) — keep for ablations only
    lines = [
        f"- Calendar span: {f['span_desc']}",
        f"- Forecast origin: {f['origin']} "
        f"({_MONTH_NAME[f['origin_month']]} {f['origin_year']}, "
        f"Q{f['origin_quarter']}, {f['origin_season']})",
        f"- Steps to quarter-end: {f['steps_to_quarter_end']}; "
        f"steps to year-end: {f['steps_to_year_end']}",
    ]
    hist = []
    for name, y in zip(f["month_names"], f["years"]):
        if name is None:
            hist.append("?")
        else:
            hist.append(f"{name[:3]}{y}")
    if hist:
        lines.append(f"- History calendar: {', '.join(hist)}")
    if f["horizon_months"]:
        lines.append(
            f"- Upcoming calendar (horizon, no values): "
            + "; ".join(f["horizon_months"])
        )
    if focus_u == "S":
        lines.append(
            "- Seasonal prior: align phase with month/quarter/meteorological season."
        )
    else:
        lines.append("- Calendar prior: month/quarter/season context.")
    return "\n".join(lines)


def build_event_date_tag(event_date: Optional[str],
                         origin_date: Optional[str] = None) -> str:
    """Tiny date tag for exogenous documents (no long calendar essay)."""
    ed = parse_date_str(event_date)
    if ed is None:
        return ""
    tag = f"[event-date {ed.isoformat()} {_MONTH_NAME[ed.month]} Q{(ed.month - 1) // 3 + 1}]"
    od = parse_date_str(origin_date)
    if od is not None:
        # month delta from origin (negative = past)
        delta = (ed.year - od.year) * 12 + (ed.month - od.month)
        tag += f" [Δmonths={delta:+d}]"
    return tag


def build_numeric_block_with_calendar(
    window: np.ndarray,
    dates: Optional[Sequence[Optional[str]]] = None,
    pred_len: int = 0,
    mode: str = "short",
) -> str:
    """Numeric template (A) + optional short calendar — four-component path."""
    cal = build_calendar_block(dates, pred_len=pred_len, focus="S", mode=mode)
    if not cal:
        return build_numeric_block(window)
    return build_numeric_block(window) + "\n" + cal

def is_empty_text(s: Optional[str]) -> bool:
    """True for empty / 'NA' / 'none' cells.  Pure string logic, no text model."""
    if s is None:
        return True
    t = str(s).strip()
    if not t:
        return True
    low = t.lower()
    for pat in _EMPTY_PATTERNS:
        if re.match(pat, low):
            return True
    return False


def split_documents(cell: Optional[str]) -> List[str]:
    """Split one CSV cell into its ``YYYY-MM-DD: ...`` documents.

    The shipped ``fact`` cells concatenate several documents with ``;``; the
    document-level structure is needed because averaging 5 documents into one
    embedding divides any single relevant document's signal by ~5.
    """
    if is_empty_text(cell):
        return []
    docs = _DOC_SPLIT.split(str(cell))
    return [d.strip() for d in docs if d.strip()]


def count_relevant_documents(cell: Optional[str]) -> Tuple[int, int]:
    """(n_docs, n_docs_that_are_not_pure_boilerplate)."""
    docs = split_documents(cell)
    rel = 0
    for d in docs:
        low = d.lower()
        if any(re.search(p, low) for p in _BOILERPLATE_PATTERNS):
            continue
        # a doc whose content is only the date stamp + "NA"
        body = re.sub(r"^\d{4}-\d{2}-\d{2}\s*:", "", d).strip()
        if is_empty_text(body):
            continue
        rel += 1
    return len(docs), rel


def clean_text_block(cell: Optional[str], char_budget: int = TEXT_CHAR_BUDGET
                     ) -> Tuple[str, Dict[str, object]]:
    """Turn a raw CSV cell into the text block inserted into the prompt.

    Returns ``(block, info)``.  ``block`` is ``NO_TEXT_TOKEN`` when the cell is
    empty (explicitly, never the numeric template).
    """
    n_docs, n_rel = count_relevant_documents(cell)
    info: Dict[str, object] = {"n_docs": n_docs, "n_relevant_docs": n_rel,
                               "empty": is_empty_text(cell), "chars_used": 0}
    if n_docs == 0:
        info["chars_used"] = len(NO_TEXT_TOKEN)
        return NO_TEXT_TOKEN, info
    # keep the documents in order, drop the pure-boilerplate ones, then budget
    kept: List[str] = []
    for d in split_documents(cell):
        low = d.lower()
        if any(re.search(p, low) for p in _BOILERPLATE_PATTERNS):
            continue
        body = re.sub(r"^\d{4}-\d{2}-\d{2}\s*:", "", d).strip()
        if is_empty_text(body):
            continue
        kept.append(d)
    if not kept:
        kept = split_documents(cell)          # everything was boilerplate: keep raw
    block = " ".join(kept)
    info["n_docs_kept"] = len(kept)
    if char_budget and len(block) > char_budget:
        block = block[:char_budget] + " ..."
    info["chars_used"] = len(block)
    return block, info


# ---------------------------------------------------------------------------
# ORACLE TEXT (the ceiling test)
# ---------------------------------------------------------------------------
# WHY: every arm so far hands the model *real* text and finds no causal effect.
# That is consistent with two very different stories:
#   (a) the corpus is the bottleneck  -- better text would help;
#   (b) the model cannot DECODE temporally-relevant semantics even when handed to
#       it -- a modality gap, so no amount of corpus cleaning will ever help.
# This source separates them.  It renders statistics of the FUTURE window into
# natural language, i.e. it is LEAKY BY CONSTRUCTION.  Leakage is the point: it is
# the CEILING on what any text channel could contribute at this horizon and
# architecture.  If a leaky oracle cannot beat the text-blind arm, no honest
# corpus can, and the direction must change.
#
# WHAT GOES IN (and what deliberately does NOT):
#   IN : interval-level statistics of ``Y`` (the forecast window) -- standardised
#        mean shift, volatility ratio, normalised range, trend/curvature, shape
#        class, turning-point count, lag-1 persistence, and the centroid of the
#        interval's variation.
#   OUT: the raw future VALUES, in any form.  A list of the target would let the
#        head read off the answer instead of using semantics, which would measure
#        nothing.  `assert_no_future_leak()` checks this by brute force.
#   OUT: a restatement of the input window.  The oracle text section describes Y
#        only.
#
# The statistics are deterministic functions of Y; no LLM/API is involved.  This
# mirrors the TESS recipe (GPT rendered statistical features into prose) with the
# renderer replaced by a template, which is the only difference the information
# content cares about.

ORACLE_HEADER = ("\n- Forward-looking event briefing for the forecast interval "
                 "(rule-based statistical summary; contains no raw observations): ")

#: constant context.  Deliberately identical for every sample so it dilutes the
#: informative part without adding information -- this tests the realistic case
#: where most of a document is background, and it cannot confound the comparison.
ORACLE_CONTEXT = ("Analyst note: this briefing was produced by a deterministic "
                  "rule-based summariser from interval-level statistics. Comparable "
                  "episodes in this series have historically been driven by a mix of "
                  "seasonal and policy factors, and no single driver dominates.")

_EPS = 1e-8


def _turn_count(y: np.ndarray) -> int:
    """Number of sign changes in the first difference (a turning-point count)."""
    d = np.diff(np.asarray(y, dtype=float).ravel())
    s = np.sign(d)
    s = s[s != 0]
    if s.size < 2:
        return 0
    return int(np.sum(s[1:] != s[:-1]))


def _shape_class(y: np.ndarray) -> str:
    """Classify the trajectory of the forecast window into words."""
    y = np.asarray(y, dtype=float).ravel()
    n = y.size
    if n < 3:
        return "too short to classify"
    t = np.arange(n, dtype=float)
    slope = float(np.polyfit(t, y, 1)[0])
    scale = float(np.std(y)) + _EPS
    turns = _turn_count(y)
    imax, imin = int(np.argmax(y)), int(np.argmin(y))
    interior_max = 0 < imax < n - 1
    interior_min = 0 < imin < n - 1
    if turns >= max(2, n // 3):
        return "oscillating with repeated reversals"
    if interior_max and not interior_min:
        return "peaking in the interval then receding"
    if interior_min and not interior_max:
        return "dipping in the interval then recovering"
    if slope * n > 0.75 * scale:
        return "steadily ascending"
    if slope * n < -0.75 * scale:
        return "steadily descending"
    return "broadly flat"


def _bucket(v: float, edges: Sequence[float], labels: Sequence[str]) -> str:
    for e, lab in zip(edges, labels):
        if v < e:
            return lab
    return labels[-1]


def future_stats(future: np.ndarray, past: np.ndarray) -> Dict[str, float]:
    """Statistics of the FORECAST window ``Y``, scale-free where it matters.

    ``past`` is used only as the normalising scale (its own std/mean), so the
    numbers describe Y relative to the recent level rather than absolute units.
    """
    y = np.asarray(future, dtype=float).ravel()
    x = np.asarray(past, dtype=float).ravel()
    xs = float(np.std(x)) + _EPS
    xm = float(np.mean(x))
    n = max(1, y.size)
    t = np.arange(y.size, dtype=float)
    slope = float(np.polyfit(t, y, 1)[0]) if y.size > 1 else 0.0
    # centre of the interval's variation (0 = all variation early, 1 = late)
    dev = np.abs(y - np.mean(y))
    w = dev.sum()
    centroid = float((np.arange(y.size) * dev).sum() / w / max(1, y.size - 1)) \
        if w > _EPS else 0.5
    dy = np.diff(y)
    acf1 = float(np.corrcoef(y[:-1], y[1:])[0, 1]) if y.size > 2 and np.std(y) > _EPS \
        else 0.0
    return {
        "mean_shift_z": (float(np.mean(y)) - xm) / xs,
        "vol_ratio": (float(np.std(y)) + _EPS) / xs,
        "norm_range": (float(np.max(y)) - float(np.min(y))) / xs,
        "slope_total_z": slope * n / xs,
        "end_delta_z": (float(y[-1]) - float(y[0])) / xs,
        "n_turns": float(_turn_count(y)),
        "persistence": acf1,
        "centroid": centroid,
        "max_abs_step_z": float(np.max(np.abs(dy))) / xs if dy.size else 0.0,
        "frac_above_start": float(np.mean(y > y[0])) if y.size else 0.0,
    }


def oracle_text(future: np.ndarray, past: np.ndarray) -> str:
    """Render the statistics of ``Y`` into prose.  Deterministic; no raw values."""
    s = future_stats(future, past)
    shape = _shape_class(future)
    shift = _bucket(s["mean_shift_z"], (-1.0, -0.25, 0.25, 1.0),
                    ("a marked downward step", "a mild downward drift",
                     "no material level change", "a mild upward drift",
                     "a marked upward step"))
    vol = _bucket(s["vol_ratio"], (0.5, 0.85, 1.2, 2.0),
                  ("sharply reduced", "somewhat reduced", "broadly unchanged",
                   "somewhat elevated", "strongly elevated"))
    rng = _bucket(s["norm_range"], (0.5, 1.0, 2.0, 4.0),
                  ("very narrow", "narrow", "moderate", "wide", "extremely wide"))
    pers = _bucket(s["persistence"], (-0.4, 0.1, 0.5),
                   ("strongly mean-reverting", "weakly mean-reverting",
                    "weakly persistent", "strongly persistent"))
    ctr = _bucket(s["centroid"], (0.35, 0.65),
                  ("concentrated early in the interval",
                   "spread evenly across the interval",
                   "concentrated late in the interval"))
    balance = _bucket(s["frac_above_start"], (0.25, 0.5, 0.75),
                      ("mostly below the initial level", "predominantly below the initial level",
                       "predominantly above the initial level", "mostly above the initial level"))
    parts = [
        f"The interval is expected to show {shift} versus the recent level "
        f"(standardised shift {s['mean_shift_z']:+.2f}).",
        f"Volatility is assessed as {vol} (ratio {s['vol_ratio']:.2f}).",
        f"The trajectory is classified as {shape}, spanning a {rng} range "
        f"(normalised range {s['norm_range']:.2f}) and a net change of "
        f"{s['slope_total_z']:+.2f} standard deviations.",
        f"{int(s['n_turns'])} turning point(s) are detected and the series is {pers}, "
        f"with the largest single step measuring {s['max_abs_step_z']:.2f} standard "
        f"deviations.",
        f"Variation is {ctr}; the interval closes {balance}.",
    ]
    return " ".join(parts)


def build_oracle_prompt_body(future: np.ndarray, past: np.ndarray) -> str:
    return ORACLE_HEADER + oracle_text(future, past) + " " + ORACLE_CONTEXT


def numbers_leaked_in_text(text: str, future: np.ndarray, decimals: int = 2) -> List[str]:
    """Return any future value that appears verbatim in ``text``.

    The oracle channel must carry *semantics*, not the answer.  This is a brute
    force check: every future observation is rendered at a few precisions and
    searched for.  Used by the tests, so a future edit to the renderer cannot
    quietly turn the oracle into a lookup table.
    """
    y = np.asarray(future, dtype=float).ravel()
    found: List[str] = []
    for v in np.unique(y):
        for d in (0, 1, 2, 3):
            tok = f"{v:.{d}f}"
            # ignore trivially short tokens (e.g. "1") -- they match everywhere
            if len(tok) < 4:
                continue
            if tok in text:
                found.append(tok)
    return found


# ---------------------------------------------------------------------------
# rebuilt-corpus hook (owned by the other worker)
# ---------------------------------------------------------------------------

REBUILT_DIR_BUILTIN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "VoT", "data_rebuilt")


def rebuilt_dir_default() -> str:
    """Resolve the rebuilt-corpus directory AT CALL TIME.

    ``os.environ`` is read here rather than at import time on purpose: the env
    var is the documented override (the corpus worker reports a path, we point
    ``TESS_REBUILT_DIR`` at it), and reading it at import made that override
    silently ineffective whenever anything had already imported this module.
    """
    return os.environ.get("TESS_REBUILT_DIR", REBUILT_DIR_BUILTIN)


REBUILT_DIR_DEFAULT = REBUILT_DIR_BUILTIN   # kept for backwards compatibility
    

@dataclass
class RebuiltCorpus:
    """Very thin reader for the rebuilt-corpus hook.

    The rebuilt corpus is produced by a DIFFERENT worker; this class must not be
    treated as a contract.  It accepts either
      * a directory holding ``<domain>.json`` mapping the row index (or the
        ``date`` / ``start_date`` string) to a text block, or
      * a directory holding ``<domain>.csv`` with a column named in
        ``text_column`` (default: tries 'rebuilt_text', 'text', 'fact').
    Anything unreadable -> ``available=False`` and the caller logs a NO-TEXT run.
    """

    domain: str
    root: Optional[str] = None
    text_column: str = "rebuilt_text"

    def __post_init__(self) -> None:
        if self.root is None:
            self.root = rebuilt_dir_default()
        self.available = False
        self.resolved_column = None
        self.reason = ""
        self._by_index: Dict[int, str] = {}
        self._by_date: Dict[str, str] = {}
        d = self.root if os.path.isabs(self.root) else os.path.join(os.getcwd(), self.root)
        self.dir = os.path.abspath(d)
        # An explicit file may be named by the corpus worker, in which case we read
        # it directly instead of guessing; otherwise the <domain>.{json,csv}
        # convention is used.  The explicit file's TYPE decides the parser, so a
        # named CSV is never fed to the JSON reader.
        explicit = os.environ.get("TESS_REBUILT_FILE", "")
        if explicit and os.path.exists(explicit):
            jp = explicit if explicit.lower().endswith(".json") else ""
            cp = explicit if not explicit.lower().endswith(".json") \
                else os.path.join(d, f"{self.domain}.csv")
        else:
            jp = os.path.join(d, f"{self.domain}.json")
            cp = os.path.join(d, f"{self.domain}.csv")
        self.text_column = os.environ.get("TESS_REBUILT_COLUMN", self.text_column)
        if os.path.exists(jp):
            try:
                import json
                obj = json.load(open(jp, encoding="utf-8"))
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        ks = str(k)
                        if ks.isdigit():
                            self._by_index[int(ks)] = str(v)
                        else:
                            self._by_date[ks] = str(v)
                elif isinstance(obj, list):
                    for i, v in enumerate(obj):
                        self._by_index[i] = str(v)
                self.available = True
            except Exception as exc:
                self.reason = f"{jp}: {type(exc).__name__}: {exc}"
        elif os.path.exists(cp):
            try:
                import csv as _csv
                with open(cp, encoding="utf-8", errors="replace", newline="") as fh:
                    rd = _csv.DictReader(fh)
                    cols = rd.fieldnames or []
                    col = self.text_column if self.text_column in cols else (
                        "text" if "text" in cols else ("fact" if "fact" in cols else None))
                    if col is None:
                        self.reason = f"{cp}: no usable text column in {cols}"
                    else:
                        self.resolved_column = col
                        for i, r in enumerate(rd):
                            self._by_index[i] = str(r.get(col) or "")
                        self.available = True
            except Exception as exc:
                self.reason = f"{cp}: {type(exc).__name__}: {exc}"
        else:
            self.reason = (f"neither {jp} nor {cp} exists -- the rebuilt corpus is owned "
                           "by a different worker")
        self.n = len(self._by_index)

    def get(self, index: Optional[int] = None, date: Optional[str] = None
            ) -> Optional[str]:
        if not self.available:
            return None
        if index is not None and int(index) in self._by_index:
            return self._by_index[int(index)]
        if date is not None and str(date) in self._by_date:
            return self._by_date[str(date)]
        return None


# ---------------------------------------------------------------------------
# the public builder
# ---------------------------------------------------------------------------

def build_prompt(window: np.ndarray,
                 raw_text: Optional[str] = None,
                 source: str = "template",
                 rebuilt_text: Optional[str] = None,
                 text_char_budget: int = TEXT_CHAR_BUDGET,
                 ) -> Tuple[str, Dict[str, object]]:
    """Build one prompt.  Returns ``(prompt, info)``.

    ``info`` records ``used_text`` so the caller can log the real empty rate
    instead of guessing it.

    ORACLE NOTE: for ``oracle``/``oracle_strict`` the caller must pass the
    rendered oracle text as ``raw_text`` (the loader builds it from ``Y`` via
    ``oracle_text``).  ``oracle`` keeps the shared numeric scaffold so the ONLY
    difference from the ``template`` arm is the text section -- that is the causal
    comparison we want.  ``oracle_strict`` drops the scaffold entirely, which is
    the other reading of "the text channel should carry only what the numbers
    already give the encoder".
    """
    if source not in PROMPT_SOURCES:
        raise ValueError(f"unknown prompt source {source!r}; expected {PROMPT_SOURCES}")
    base = build_template_prompt(window)
    info: Dict[str, object] = {"source": source, "used_text": False,
                               "n_docs": 0, "n_relevant_docs": 0, "empty": True,
                               "chars_used": 0}
    if source == "template":
        return base, info

    if source == "oracle_strict":
        # no numeric scaffold: the text channel is the prompt
        block, tinfo = clean_text_block(raw_text, char_budget=text_char_budget)
        info.update(tinfo)
        prompt = PROMPT_PREFIX + block + PROMPT_SUFFIX
        info["used_text"] = block != NO_TEXT_TOKEN
        return prompt, info

    cell = rebuilt_text if source == "rebuilt_text" else raw_text
    block, tinfo = clean_text_block(cell, char_budget=text_char_budget)
    info.update(tinfo)
    # the numeric block stays first so that a tokenizer truncation never removes
    # the model's view of its own history; the text follows it.
    prompt = PROMPT_PREFIX + build_numeric_block(window) + \
        TEXT_SECTION_HEADER + block + PROMPT_SUFFIX
    info["used_text"] = block != NO_TEXT_TOKEN
    return prompt, info


def build_prompts(windows: Sequence[np.ndarray],
                  raw_texts: Optional[Sequence[Optional[str]]] = None,
                  source: str = "template",
                  rebuilt_texts: Optional[Sequence[Optional[str]]] = None,
                  text_char_budget: int = TEXT_CHAR_BUDGET,
                  ) -> Tuple[List[str], Dict[str, object]]:
    """Vectorised helper.  Returns ``(prompts, aggregate_info)``."""
    n = len(windows)
    rt = list(raw_texts) if raw_texts is not None else [None] * n
    bt = list(rebuilt_texts) if rebuilt_texts is not None else [None] * n
    prompts: List[str] = []
    used = 0
    empty = 0
    docs = 0
    rel = 0
    chars = 0
    for i in range(n):
        p, info = build_prompt(windows[i], rt[i] if i < len(rt) else None, source,
                              bt[i] if i < len(bt) else None, text_char_budget)
        prompts.append(p)
        used += int(bool(info["used_text"]))
        empty += int(bool(info["empty"]))
        docs += int(info.get("n_docs", 0))
        rel += int(info.get("n_relevant_docs", 0))
        chars += int(info.get("chars_used", 0))
    agg = {
        "source": source,
        "n": n,
        "n_used_text": used,
        "frac_used_text": used / max(1, n),
        "n_empty": empty,
        "frac_empty": empty / max(1, n),
        "mean_n_docs": docs / max(1, n),
        "mean_n_relevant_docs": rel / max(1, n),
        "mean_chars_used": chars / max(1, n),
    }
    return prompts, agg


def prompt_invariant_to_text(window: np.ndarray, text_a: Optional[str],
                             text_b: Optional[str], source: str = "raw_text") -> bool:
    """True if swapping the text leaves the prompt unchanged (i.e. text is ignored)."""
    pa, _ = build_prompt(window, text_a, source)
    pb, _ = build_prompt(window, text_b, source)
    return pa == pb


__all__ = [
    "PROMPT_SOURCES", "PROMPT_PREFIX", "PROMPT_SUFFIX", "NUMERIC_TEMPLATE",
    "NO_TEXT_TOKEN", "TEXT_CHAR_BUDGET", "REBUILT_DIR_DEFAULT",
    "numeric_stats", "build_numeric_block", "build_template_prompt",
    "parse_date_str", "calendar_features", "build_calendar_block",
    "build_event_date_tag", "build_numeric_block_with_calendar", "CALENDAR_MODES",
    "is_empty_text", "split_documents", "count_relevant_documents",
    "clean_text_block", "RebuiltCorpus", "build_prompt", "build_prompts",
    "prompt_invariant_to_text",
    "ORACLE_HEADER", "ORACLE_CONTEXT", "future_stats", "oracle_text",
    "build_oracle_prompt_body", "numbers_leaked_in_text",
]
