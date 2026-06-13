"""Bookmaker odds -> implied probabilities (margin removal)."""
from __future__ import annotations

import numpy as np


def implied_proportional(odds: dict[str, float]) -> dict[str, float]:
    inv = {t: 1.0 / v for t, v in odds.items() if v and v > 1.0}
    s = sum(inv.values())
    return {t: p / s for t, p in inv.items()}


def implied_power(odds: dict[str, float]) -> dict[str, float]:
    """Power method: find k with sum((1/odds)^k) = 1.

    Less biased than proportional for longshot-heavy markets (outrights),
    because the overround is mostly priced into longshots.
    """
    p = np.array([1.0 / v for v in odds.values() if v and v > 1.0])
    teams = [t for t, v in odds.items() if v and v > 1.0]
    if len(p) == 0:
        return {}

    def total(k):
        return float(np.sum(p ** k))

    lo, hi = 1e-3, 1.0
    if total(1.0) > 1.0:  # overround -> need k > 1
        lo, hi = 1.0, 10.0
        while total(hi) > 1.0:
            hi *= 2
            if hi > 1e3:
                return dict(zip(teams, p / p.sum()))
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if total(mid) > 1.0:
            lo = mid
        else:
            hi = mid
    k = 0.5 * (lo + hi)
    q = p ** k
    return dict(zip(teams, q / q.sum()))


def implied_1x2(home_odds: float, draw_odds: float, away_odds: float):
    inv = np.array([1.0 / home_odds, 1.0 / draw_odds, 1.0 / away_odds])
    return inv / inv.sum()
