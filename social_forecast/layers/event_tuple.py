"""Structured event parse for exo facts.

GPT-2 is frozen as an encoder only.  Zero-shot JSON from GPT-2 is unreliable,
so the default parser is a deterministic, replaceable EventParser:

  parse(body, date) → EventTuple

A stronger LLM (offline Llama / API) can implement the same interface and
drop tensors into ExoEventBatch without changing SRSA / C heads.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from utils.text_route import route_document, ROUTE2IDX

COMP_NAMES = ("T", "S", "C", "R")
SHAPE_NAMES = ("step", "pulse", "decay")  # 阶跃 / 脉冲 / 衰减
SHAPE2IDX = {n: i for i, n in enumerate(SHAPE_NAMES)}

_POLICY = (
    "policy", "sanction", "fiscal", "interest rate", "regulation", "law",
    "政策", "制裁", "法规",
)
_ACCIDENT = (
    "crash", "explosion", "earthquake", "flood", "drought", "storm",
    "hurricane", "typhoon", "wildfire", "tsunami", "disaster", "accident",
    "事故", "灾害", "洪水", "干旱", "地震", "飓风",
)
_HOLIDAY = ("holiday", "festival", "christmas", "new year", "节假", "春节")
_OUTBREAK = (
    "outbreak", "epidemic", "pandemic", "lockdown", "war", "conflict",
    "attack", "coup", "riot", "疫情", "战争", "冲突",
)
_SEASON = (
    "seasonal", "calendar", "monthly", "quarterly", "harvest", "monsoon",
    "季节", "月度", "季度",
)
_INTENSE = (
    "emergency", "catastrophe", "severe", "major", "unprecedented",
    "declared", "crisis", "突发", "紧急", "重大",
)
_PULSE = ("one-off", "one off", "spike", "shock", "instant", "announced today")
_DECAY = ("aftermath", "recovery", "fade", "lingering", "weeks after")


@dataclass
class EventTuple:
    event_type: str          # policy / accident / holiday / industry / none
    target_component: str    # trend / seasonal / jump / residual / noise
    occur_time: Optional[str]
    intensity: float         # [0,1]
    duration: int            # expected steps, 1..H
    shape_hint: str          # step / pulse / decay
    confidence: float        # [0,1]
    body: str = ""

    @property
    def route_idx(self) -> int:
        m = {
            "trend": 0, "seasonal": 1, "jump": 2, "event": 2,
            "residual": 3, "noise": -1,
        }
        return int(m.get(self.target_component, -1))

    @property
    def shape_idx(self) -> int:
        return int(SHAPE2IDX.get(self.shape_hint, 2))

    @property
    def is_jump(self) -> bool:
        return self.target_component in ("jump", "event")


class EventParser:
    """Replaceable structured parser. Default = lexicon + route_document."""

    def parse(self, body: Optional[str], date: Optional[str] = None) -> EventTuple:
        if body is None or not str(body).strip():
            return EventTuple(
                event_type="none", target_component="noise", occur_time=date,
                intensity=0.0, duration=1, shape_hint="pulse",
                confidence=1.0, body="")
        text = str(body).strip()
        low = text.lower()
        label, conf = route_document(text, date)

        if label == "noise":
            return EventTuple(
                event_type="none", target_component="noise", occur_time=date,
                intensity=0.0, duration=1, shape_hint="pulse",
                confidence=conf, body=text)

        etype = "industry"
        if any(k in low for k in _ACCIDENT):
            etype = "accident"
        elif any(k in low for k in _OUTBREAK):
            etype = "accident"
        elif any(k in low for k in _HOLIDAY):
            etype = "holiday"
        elif any(k in low for k in _POLICY) or label == "trend":
            etype = "policy"

        if label == "event":
            target = "jump"
        elif any(k in low for k in _SEASON):
            target = "seasonal"
        elif label == "trend":
            target = "trend"
        else:
            target = "residual"

        hits_i = sum(1 for k in _INTENSE if k in low)
        ntok = max(len(text.split()), 1)
        intensity = min(1.0, 0.25 + 0.35 * conf + 0.12 * hits_i + min(0.2, ntok / 80.0))
        if etype == "accident":
            intensity = min(1.0, intensity + 0.15)

        if any(k in low for k in _PULSE) or etype == "holiday":
            shape = "pulse"
            duration = 1
        elif any(k in low for k in _DECAY) or etype == "accident":
            shape = "decay"
            duration = 3
        else:
            shape = "step"
            duration = 4 if target == "trend" else 2

        return EventTuple(
            event_type=etype,
            target_component=target,
            occur_time=date,
            intensity=float(intensity),
            duration=int(duration),
            shape_hint=shape,
            confidence=float(conf),
            body=text,
        )


_DEFAULT_PARSER = EventParser()


def parse_event(body: Optional[str], date: Optional[str] = None) -> EventTuple:
    return _DEFAULT_PARSER.parse(body, date)


def tuples_to_tensors(
    tuples: Sequence[Sequence[EventTuple]],
    max_events: int,
    pred_len: int,
    device,
):
    """Pack per-sample EventTuple lists into [B,E] tensors for ExoEventBatch."""
    import torch
    B = len(tuples)
    E = int(max_events)
    H = max(int(pred_len), 1)
    # Build on CPU, move once: per-element writes into CUDA tensors issue
    # thousands of tiny H2D copies and have hung the driver mid-cache.
    target = torch.full((B, E), -1, dtype=torch.long)
    intensity = torch.zeros(B, E)
    duration = torch.ones(B, E)
    shape = torch.full((B, E), -1, dtype=torch.long)
    conf = torch.zeros(B, E)
    for b, ts in enumerate(tuples):
        for e, t in enumerate(list(ts)[:E]):
            target[b, e] = t.route_idx
            intensity[b, e] = t.intensity
            duration[b, e] = float(min(max(t.duration, 1), H))
            shape[b, e] = t.shape_idx if t.route_idx >= 0 else -1
            conf[b, e] = t.confidence
    return {
        "target": target.to(device),
        "intensity": intensity.to(device),
        "duration": duration.to(device),
        "shape": shape.to(device),
        "confidence": conf.to(device),
    }
