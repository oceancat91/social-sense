"""Pelt jump detection (L2) + C_t construction — pure numpy."""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np


def _cumsums(x: np.ndarray):
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    s1 = np.concatenate([[0.0], np.cumsum(x)])
    s2 = np.concatenate([[0.0], np.cumsum(x * x)])
    return s1, s2


def segment_cost(s1, s2, a: int, b: int) -> float:
    n = b - a
    if n <= 0:
        return 0.0
    sx = s1[b] - s1[a]
    sxx = s2[b] - s2[a]
    return float(sxx - (sx * sx) / n)


def pelt_l2(x: np.ndarray, beta: float = 1.0, min_size: int = 2) -> List[int]:
    """Return changepoint starts in (0, N)."""
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    n = x.size
    if n < 2 * min_size:
        return []
    s1, s2 = _cumsums(x)
    F = np.full(n + 1, np.inf)
    F[0] = -beta
    last = np.full(n + 1, -1, dtype=np.int64)
    R = {0}

    for t_end in range(min_size, n + 1):
        best_c, best_s = np.inf, 0
        for s in list(R):
            if t_end - s < min_size:
                continue
            c = F[s] + segment_cost(s1, s2, s, t_end) + beta
            if c < best_c:
                best_c, best_s = c, s
        F[t_end] = best_c
        last[t_end] = best_s
        R_new = set()
        for s in R:
            if t_end - s < min_size or F[s] + segment_cost(s1, s2, s, t_end) <= F[t_end] + 1e-12:
                R_new.add(s)
        R_new.add(t_end)
        R = {s for s in R_new if s <= t_end}

    # backtrack
    bps = []
    cur = n
    while cur > 0 and last[cur] >= 0:
        s = int(last[cur])
        if s > 0:
            bps.append(s)
        cur = s
        if s == 0:
            break
    return sorted(bps)


def filter_breakpoints(
    x: np.ndarray,
    bps: Sequence[int],
    tau: Optional[float] = None,
    w_side: int = 3,
    w_min: int = 3,
) -> List[int]:
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    n = x.size
    if tau is None:
        tau = 3.0 * float(np.std(x) + 1e-8)
    kept: List[int] = []
    for b in sorted(bps):
        if not (0 < b < n):
            continue
        left, right = x[max(0, b - w_side):b], x[b:min(n, b + w_side)]
        if left.size == 0 or right.size == 0:
            continue
        dmu = abs(float(right.mean() - left.mean()))
        if dmu < tau:
            continue
        if kept and b - kept[-1] < w_min:
            prev = kept[-1]
            pl, pr = x[max(0, prev - w_side):prev], x[prev:min(n, prev + w_side)]
            d_prev = abs(float(pr.mean() - pl.mean())) if pl.size and pr.size else 0.0
            if dmu > d_prev:
                kept[-1] = b
            continue
        kept.append(int(b))
    return kept


def _noise_sigma(x: np.ndarray) -> float:
    """Robust noise scale from consecutive differences (excludes large jumps)."""
    d = np.diff(np.asarray(x, dtype=np.float64).reshape(-1))
    if d.size == 0:
        return 1e-8
    return float(np.median(np.abs(d)) / 0.6745 / np.sqrt(2.0) + 1e-8)


def build_jump_series(
    x: np.ndarray,
    bps: Sequence[int],
    w_min: int = 3,
    tau: Optional[float] = None,
) -> Tuple[np.ndarray, List[dict]]:
    """C_t = segment mean on centered series when |μ|>=tau (else 0)."""
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    n = x.size
    C = np.zeros(n, dtype=np.float64)
    if tau is None:
        tau = 3.0 * _noise_sigma(x)
    cuts = [0] + sorted(int(b) for b in bps if 0 < b < n) + [n]
    events = []
    for i in range(len(cuts) - 1):
        a, b = cuts[i], cuts[i + 1]
        if b <= a:
            continue
        mu = float(x[a:b].mean())
        length = b - a
        if abs(mu) < tau:
            continue
        if length >= w_min:
            C[a:b] = mu
            events.append({'type': 'step', 'start': a, 'end': b, 'amp': mu})
        else:
            seg = x[a:b]
            k = int(np.argmax(np.abs(seg)))
            amp = float(seg[k])
            C[a + k] = amp
            events.append({'type': 'pulse', 'start': a + k, 'end': a + k + 1, 'amp': amp})
    return C, events


def detect_jumps(
    r2: np.ndarray,
    beta: Optional[float] = None,
    w_min: int = 3,
    w_side: int = 3,
    period: int = 12,
) -> Tuple[np.ndarray, List[int], List[dict]]:
    r2 = np.asarray(r2, dtype=np.float64).reshape(-1)
    n = r2.size
    xc = r2 - float(r2.mean())  # C = offset from global mean level
    sig = _noise_sigma(xc)
    if beta is None:
        beta = 2.0 * (sig ** 2) * np.log(max(n, 2))
    bps = pelt_l2(xc, beta=float(beta), min_size=max(2, w_min))
    tau = 2.0 * sig  # amplitude gate (paper uses ~3σ; noise σ is tighter)
    gap = max(w_min, 2)  # mild; period used only as soft hint
    _ = period
    bps = filter_breakpoints(xc, bps, tau=tau, w_side=w_side, w_min=gap)
    C, events = build_jump_series(xc, bps, w_min=w_min, tau=tau)
    return C, bps, events
