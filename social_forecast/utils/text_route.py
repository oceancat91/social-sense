"""Route fact documents into trend vs event vs noise for T/C semantic split.

Heuristic (no extra LLM call): keyword + length cues.
Used to mask exo docs so event text cannot enter T, trend text cannot enter C.
"""
from __future__ import annotations

from typing import Literal, Optional, Tuple

RouteLabel = Literal["trend", "event", "noise"]

# weak labels for SRSA: T=0, S=1, C=2, R=3, ignore=-1
ROUTE2IDX = {"trend": 0, "seasonal": 1, "event": 2, "residual": 3, "noise": -1}

_EVENT_KW = (
    "flood", "drought", "storm", "earthquake", "war", "conflict", "attack",
    "outbreak", "epidemic", "emergency", "disaster", "hurricane", "typhoon",
    "explosion", "crash", "sanction", "coup", "riot", "wildfire", "tsunami",
    "outbreak", "lockdown", "evacuation", "declared", "catastrophe",
    "突发", "灾害", "洪水", "干旱", "地震", "战争", "冲突", "疫情", "紧急",
)
_TREND_KW = (
    "policy", "long-term", "long term", "trend", "growth", "gdp", "inflation",
    "climate type", "seasonal", "average", "outlook", "structural", "industry",
    "macro", "interest rate", "fiscal", "over the years", "historically",
    "政策", "趋势", "长期", "宏观", "产业", "平均",
)
_NOISE_KW = (
    "no relevant", "n/a", "none", ": na", "not available", "irrelevant",
    # LLM "could not retrieve / irrelevant" placeholders (very common in the
    # Agriculture / Climate facts — they previously leaked as weak events):
    "not relevant", "not directly mentioned", "not mentioned",
    "no relevant search", "no specific", "no information", "no data",
    "cannot be made", "could not be", "unable to", "insufficient",
    "no long-term predictions", "no short-term predictions",
    "not directly related", "search result", "provide \"na\"",
)


def route_document(body: str, date: Optional[str] = None) -> Tuple[RouteLabel, float]:
    """Return (label, confidence in [0,1])."""
    if body is None:
        return "noise", 1.0
    text = str(body).strip()
    if not text:
        return "noise", 1.0
    low = text.lower()
    # bare "NA(...)"/"NA:" placeholder heads are pure noise
    if low == "na" or low.startswith("na ") or low.startswith("na(") or low.startswith("na:"):
        return "noise", 1.0
    for k in _NOISE_KW:
        if k in low:
            return "noise", 1.0
    ev = sum(1 for k in _EVENT_KW if k in low)
    tr = sum(1 for k in _TREND_KW if k in low)
    # short dated shock mentions skew event
    if ev > tr and ev > 0:
        conf = min(1.0, 0.45 + 0.15 * ev)
        return "event", conf
    if tr > ev and tr > 0:
        conf = min(1.0, 0.45 + 0.15 * tr)
        return "trend", conf
    # undated encyclopedic climate blurbs → trend/noise; dated short → event-leaning
    if date and len(text.split()) < 40 and ev == 0 and tr == 0:
        return "event", 0.35  # weak: dated news-like
    if len(text.split()) > 60 and tr == 0 and ev == 0:
        return "trend", 0.3
    return "noise", 0.4
