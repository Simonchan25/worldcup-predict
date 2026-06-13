"""Dixon-Coles goal model on Elo features.

National teams play too few matches for per-team attack/defence parameters,
so goal rates are driven by the pre-match Elo difference:

    lambda_home = exp(b0 + b1 * (elo_h - elo_a)/400 + b_home * is_home)
    lambda_away = exp(b0 - b1 * (elo_h - elo_a)/400)

with the Dixon-Coles tau adjustment for low-score dependence and an
exponential time-decay weight on the training matches.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 10


def _tau_log(gh, ga, lh, la, rho):
    tau = np.ones_like(lh)
    tau = np.where((gh == 0) & (ga == 0), 1.0 - lh * la * rho, tau)
    tau = np.where((gh == 0) & (ga == 1), 1.0 + lh * rho, tau)
    tau = np.where((gh == 1) & (ga == 0), 1.0 + la * rho, tau)
    tau = np.where((gh == 1) & (ga == 1), 1.0 - rho, tau)
    return np.log(np.clip(tau, 1e-10, None))


def fit(df: pd.DataFrame, ref_date, since: str = "2010-01-01", xi: float = 0.25) -> dict:
    """Weighted MLE of (b0, b1, b_home, rho) on matches in [since, ref_date).

    df needs columns date, home_score, away_score, neutral, elo_h, elo_a
    (pre-match Elo from elo.run_elo). xi is the decay rate per year.
    """
    ref = pd.Timestamp(ref_date)
    sub = df[(df["date"] >= pd.Timestamp(since)) & (df["date"] < ref)]
    years = (ref - sub["date"]).dt.days.to_numpy() / 365.25
    w = np.exp(-xi * years)
    gh = sub["home_score"].to_numpy(float)
    ga = sub["away_score"].to_numpy(float)
    ed = (sub["elo_h"].to_numpy(float) - sub["elo_a"].to_numpy(float)) / 400.0
    home = (~sub["neutral"].to_numpy(bool)).astype(float)

    def nll(p):
        b0, b1, bh, rho = p
        lh = np.clip(np.exp(b0 + b1 * ed + bh * home), 1e-8, 12.0)
        la = np.clip(np.exp(b0 - b1 * ed), 1e-8, 12.0)
        ll = _tau_log(gh, ga, lh, la, rho) + gh * np.log(lh) - lh + ga * np.log(la) - la
        return -float(np.sum(w * ll))

    x0 = np.array([np.log(1.3), 0.9, 0.2, 0.0])
    bounds = [(-2.0, 2.0), (0.0, 4.0), (-0.5, 1.0), (-0.12, 0.12)]
    res = minimize(nll, x0, method="L-BFGS-B", bounds=bounds)
    if not res.success:
        res = minimize(nll, res.x, method="Nelder-Mead",
                       options={"maxiter": 8000, "xatol": 1e-7, "fatol": 1e-7})
    return {
        "params": [float(v) for v in res.x],
        "n_matches": int(len(sub)),
        "eff_n": float(w.sum()),
        "nll": float(res.fun),
        "converged": bool(res.success),
        "since": str(since),
        "xi": xi,
    }


def lambdas(elo_h: float, elo_a: float, params, home: float = 0.0):
    b0, b1, bh, _ = params
    ed = (elo_h - elo_a) / 400.0
    return float(np.exp(b0 + b1 * ed + bh * home)), float(np.exp(b0 - b1 * ed))


def score_matrix(elo_h: float, elo_a: float, params, home: float = 0.0,
                 max_goals: int = MAX_GOALS):
    """P(home goals = i, away goals = j) grid, DC-adjusted, renormalized."""
    rho = params[3]
    lh, la = lambdas(elo_h, elo_a, params, home)
    g = np.arange(max_goals + 1)
    m = np.outer(poisson.pmf(g, lh), poisson.pmf(g, la))
    m[0, 0] *= max(1.0 - lh * la * rho, 1e-10)
    m[0, 1] *= max(1.0 + lh * rho, 1e-10)
    m[1, 0] *= max(1.0 + la * rho, 1e-10)
    m[1, 1] *= max(1.0 - rho, 1e-10)
    m /= m.sum()
    return m, lh, la


def wdl(m: np.ndarray):
    """(P home win, P draw, P away win) from a score grid."""
    return (float(np.tril(m, -1).sum()), float(np.trace(m)), float(np.triu(m, 1).sum()))


def top_scores(m: np.ndarray, k: int = 5):
    flat = m.ravel()
    idx = np.argsort(flat)[::-1][:k]
    n = m.shape[0]
    return [(int(i // n), int(i % n), float(flat[i])) for i in idx]


def value_blend(elo_ratings: dict, values_eur_m: dict, weight: float = 0.25):
    """Blend Elo with a squad-market-value-implied rating.

    Cross-sectional fit elo ~ a + b*log(value) over teams with both, then
    rating = (1-weight)*elo + weight*value_implied. Returns (ratings, info).
    """
    teams = [t for t, v in values_eur_m.items() if t in elo_ratings and v and v > 0]
    out = dict(elo_ratings)
    if len(teams) < 8 or weight <= 0:
        return out, {"n": len(teams), "weight": 0.0, "skipped": True}
    x = np.log([values_eur_m[t] for t in teams])
    y = np.array([elo_ratings[t] for t in teams])
    b, a = np.polyfit(x, y, 1)
    for t in teams:
        ve = a + b * np.log(values_eur_m[t])
        out[t] = (1.0 - weight) * elo_ratings[t] + weight * ve
    return out, {"a": float(a), "b": float(b), "n": len(teams), "weight": weight,
                 "skipped": False}
