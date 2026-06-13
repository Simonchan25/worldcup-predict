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


DRAW_ODDS_FLOOR = 2.6   # a real 1X2 draw is essentially never priced shorter


def valid_1x2(home_odds: float, draw_odds: float, away_odds: float) -> bool:
    """Reject a 1X2 line that is almost certainly a parse error.

    The discriminating signal is the *draw price*, not the bookmaker margin:
    a real match-odds draw is never priced below ~2.6 (the shortest draws in
    football, two ultra-defensive evenly-matched sides, sit around 2.9-3.1).
    A short draw is the fingerprint of a swapped/mis-read row or a
    double-chance / draw-no-bet number grabbed by mistake (e.g. Brazil-Morocco
    quoted 1.67/2.2/5.5: a 1.67 favourite cannot truly co-exist with a 2.2
    draw — that de-margins Brazil to an impossible 48%).

    We deliberately do NOT use a tight overround cap as the discriminator,
    since a high bookmaker margin is not itself a parse error. The book sum is
    only sanity-checked against a sub-100% book (parse error / impossible at a
    single book) and an egregiously broken one. Checks (reject if any fail):
    finite decimal odds > 1; book sum in [1.0, 1.40]; draw odds >= 2.6;
    de-margined draw share <= 0.40.
    """
    o = [home_odds, draw_odds, away_odds]
    if any(v is None or not np.isfinite(v) or v <= 1.0 for v in o):
        return False
    if draw_odds < DRAW_ODDS_FLOOR:
        return False
    inv = np.array([1.0 / v for v in o])
    book = float(inv.sum())
    if not (1.0 <= book <= 1.40):
        return False
    return float(inv[1] / book) <= 0.40
