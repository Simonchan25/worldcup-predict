"""World Football Elo ratings computed from the full match history.

Follows the eloratings.net formula: K scaled by tournament importance and
goal difference, +100 home advantage for non-neutral matches.
"""
from __future__ import annotations

import pandas as pd

BASE = 1500.0
HOME_ADV = 100.0

_MAJOR_TOURNAMENTS = (
    "uefa euro", "copa américa", "copa america", "african cup of nations",
    "africa cup of nations", "afc asian cup", "gold cup",
    "concacaf championship", "oceania nations cup", "confederations cup",
)


def k_factor(tournament: str) -> float:
    t = str(tournament).lower()
    if "qualification" in t:
        return 40.0
    if "fifa world cup" in t or t == "world cup":
        return 60.0
    if any(m in t for m in _MAJOR_TOURNAMENTS):
        return 50.0
    if "nations league" in t:
        return 40.0
    if "friendly" in t:
        return 20.0
    return 30.0


def goal_mult(diff: int) -> float:
    if diff <= 1:
        return 1.0
    if diff == 2:
        return 1.5
    return (11.0 + diff) / 8.0


def run_elo(df: pd.DataFrame, base: float = BASE, home_adv: float = HOME_ADV):
    """One chronological pass. Returns (final_ratings, df_with_prematch_elo).

    The returned frame carries elo_h / elo_a = each side's rating *before*
    the match, which is what the goal model trains on.
    """
    ratings: dict[str, float] = {}
    eh, ea = [], []
    for row in df.itertuples(index=False):
        rh = ratings.get(row.home_team, base)
        ra = ratings.get(row.away_team, base)
        eh.append(rh)
        ea.append(ra)
        dr = rh - ra + (0.0 if row.neutral else home_adv)
        we = 1.0 / (1.0 + 10.0 ** (-dr / 400.0))
        if row.home_score > row.away_score:
            w = 1.0
        elif row.home_score == row.away_score:
            w = 0.5
        else:
            w = 0.0
        k = k_factor(row.tournament) * goal_mult(abs(row.home_score - row.away_score))
        delta = k * (w - we)
        ratings[row.home_team] = rh + delta
        ratings[row.away_team] = ra - delta
    out = df.copy()
    out["elo_h"] = eh
    out["elo_a"] = ea
    return ratings, out
