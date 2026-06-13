"""Derive every common betting market from a Dixon-Coles scoreline grid.

The model already produces the full joint distribution P(home=i, away=j) for a
fixture (model.score_matrix). Every standard market is just a sum over cells of
that grid, so we can price over/under, both-teams-to-score, double chance,
draw-no-bet, Asian handicaps, correct score and team totals *for free* and put
them next to the bookmaker's prices. The grid is oriented to the home side.
"""
from __future__ import annotations

import numpy as np

EPS = 1e-12


def _totals(m: np.ndarray) -> np.ndarray:
    """P(total goals = k), k = 0 .. 2*(n-1)."""
    ii, jj = np.indices(m.shape)
    out = np.zeros(m.shape[0] + m.shape[1] - 1)
    np.add.at(out, (ii + jj).ravel(), m.ravel())
    return out


def over_under(m: np.ndarray, line: float) -> tuple[float, float]:
    """(P over, P under) for a .5 line — no push."""
    tot = _totals(m)
    k = np.arange(len(tot))
    return float(tot[k > line].sum()), float(tot[k < line].sum())


def btts(m: np.ndarray) -> tuple[float, float]:
    """(P both teams score, P not)."""
    yes = float(m[1:, 1:].sum())
    return yes, 1.0 - yes


def wdl(m: np.ndarray) -> tuple[float, float, float]:
    return float(np.tril(m, -1).sum()), float(np.trace(m)), float(np.triu(m, 1).sum())


def double_chance(m: np.ndarray) -> dict:
    h, d, a = wdl(m)
    return {"1X": h + d, "12": h + a, "X2": d + a}


def draw_no_bet(m: np.ndarray) -> tuple[float, float]:
    """(P home, P away) conditional on no draw (draw = stake back)."""
    h, _, a = wdl(m)
    s = max(h + a, EPS)
    return h / s, a / s


def asian_handicap(m: np.ndarray, line: float) -> dict:
    """Home-side handicap `line` (e.g. -1.5 means home must win by 2+).
    Returns {p_home, p_away, p_push} on the home margin = i - j."""
    ii, jj = np.indices(m.shape)
    margin = (ii - jj).ravel() + line
    p = m.ravel()
    return {
        "p_home": float(p[margin > 0].sum()),
        "p_away": float(p[margin < 0].sum()),
        "p_push": float(p[np.isclose(margin, 0)].sum()),
    }


def correct_score(m: np.ndarray, k: int = 6) -> list[dict]:
    flat = m.ravel()
    n = m.shape[1]
    idx = np.argsort(flat)[::-1][:k]
    return [{"score": f"{int(i // n)}-{int(i % n)}", "p": float(flat[i])} for i in idx]


def team_totals(m: np.ndarray) -> dict:
    """P(home over 1.5), P(away over 1.5), clean sheets."""
    home_goals = m.sum(axis=1)            # P(home scores i)
    away_goals = m.sum(axis=0)
    g = np.arange(m.shape[0])
    return {
        "home_over_1_5": float(home_goals[g > 1.5].sum()),
        "away_over_1_5": float(away_goals[g > 1.5].sum()),
        "home_clean_sheet": float(m[:, 0].sum()),
        "away_clean_sheet": float(m[0, :].sum()),
    }


def all_markets(m: np.ndarray) -> dict:
    """One compact dict of model probabilities for the common markets."""
    h, d, a = wdl(m)
    dnb_h, dnb_a = draw_no_bet(m)
    ou = {f"{ln}": over_under(m, ln) for ln in (1.5, 2.5, 3.5)}
    by = btts(m)
    return {
        "1x2": {"home": h, "draw": d, "away": a},
        "double_chance": double_chance(m),
        "draw_no_bet": {"home": dnb_h, "away": dnb_a},
        "over_under": {ln: {"over": o, "under": u} for ln, (o, u) in ou.items()},
        "btts": {"yes": by[0], "no": by[1]},
        "ah": {"-1.5": asian_handicap(m, -1.5), "-0.5": asian_handicap(m, -0.5),
               "+0.5": asian_handicap(m, 0.5), "+1.5": asian_handicap(m, 1.5)},
        "team_totals": team_totals(m),
        "correct_score": correct_score(m, 6),
    }


def fair_odds(p: float) -> float:
    """Fair decimal odds for a model probability (no margin)."""
    return round(1.0 / max(p, EPS), 2)


def value(model_p: float, dec_odds: float) -> dict:
    """Expected value and Kelly fraction of backing an outcome at `dec_odds`
    when the model thinks its probability is `model_p`.

      EV per unit staked = model_p * dec_odds - 1
      Kelly fraction f*  = (b*p - q)/b,  b = dec_odds-1, q = 1-p
    """
    b = dec_odds - 1.0
    ev = model_p * dec_odds - 1.0
    kelly = (b * model_p - (1.0 - model_p)) / b if b > 0 else 0.0
    return {"ev": float(ev), "kelly": float(max(0.0, kelly)),
            "edge_pct": float(100 * ev), "model_p": float(model_p), "odds": float(dec_odds)}
