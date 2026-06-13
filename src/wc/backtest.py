"""Backtest the model on past World Cups (2014/2018/2022).

For each tournament the goal model is fitted only on matches strictly
before the cutoff; pre-match Elo ratings come from the single global
chronological pass (so they update match-by-match through the tournament,
as they would in live use).

Metrics: RPS (ranked probability score), log loss, Brier, exact-score
hit rate — against uniform and historical-frequency baselines.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import model

WC_CUTOFFS = {
    2014: "2014-06-12",
    2018: "2018-06-14",
    2022: "2022-11-20",
}
WINDOW_DAYS = 45


def rps(p, outcome_idx):
    """p = [pW, pD, pL] (home perspective), outcome_idx in {0,1,2}."""
    o = np.zeros(3)
    o[outcome_idx] = 1.0
    c = np.cumsum(p) - np.cumsum(o)
    return float(np.sum(c[:2] ** 2) / 2.0)


def _outcome(hs, as_):
    return 0 if hs > as_ else (1 if hs == as_ else 2)


def run_backtest(df: pd.DataFrame, xi: float = 0.25):
    """df: full results frame with elo_h/elo_a columns. Returns
    (per-match frame, per-tournament summary frame)."""
    match_rows = []
    for year, cutoff in WC_CUTOFFS.items():
        c = pd.Timestamp(cutoff)
        train = df[df["date"] < c]
        fitres = model.fit(train, ref_date=c, since=f"{year - 16}-01-01", xi=xi)
        params = fitres["params"]

        neutral_train = train[(train["date"] >= c - pd.Timedelta(days=365 * 12))
                              & train["neutral"]]
        freq = np.array([
            (neutral_train["home_score"] > neutral_train["away_score"]).mean(),
            (neutral_train["home_score"] == neutral_train["away_score"]).mean(),
            (neutral_train["home_score"] < neutral_train["away_score"]).mean(),
        ])

        test = df[(df["tournament"] == "FIFA World Cup")
                  & (df["date"] >= c)
                  & (df["date"] < c + pd.Timedelta(days=WINDOW_DAYS))]
        for row in test.itertuples(index=False):
            home_flag = 0.0 if row.neutral else 1.0
            grid, lh, la = model.score_matrix(row.elo_h, row.elo_a, params,
                                              home=home_flag)
            p = np.array(model.wdl(grid))
            out = _outcome(row.home_score, row.away_score)
            top5 = model.top_scores(grid, 5)
            hs = min(int(row.home_score), model.MAX_GOALS)
            as_ = min(int(row.away_score), model.MAX_GOALS)
            match_rows.append({
                "wc": year, "date": row.date, "home": row.home_team,
                "away": row.away_team, "score": f"{row.home_score}-{row.away_score}",
                "p_home": p[0], "p_draw": p[1], "p_away": p[2],
                "outcome": ["H", "D", "A"][out],
                "rps_model": rps(p, out),
                "rps_uniform": rps(np.ones(3) / 3, out),
                "rps_freq": rps(freq, out),
                "logloss_model": -float(np.log(max(p[out], 1e-12))),
                "brier_model": float(np.sum((p - np.eye(3)[out]) ** 2)),
                "exact_hit_top1": int((top5[0][0], top5[0][1]) == (hs, as_)),
                "exact_hit_top5": int(any((i, j) == (hs, as_) for i, j, _ in top5)),
                "p_exact": float(grid[hs, as_]),
            })
    per_match = pd.DataFrame(match_rows)
    agg_cols = ["rps_model", "rps_uniform", "rps_freq", "logloss_model",
                "brier_model", "exact_hit_top1", "exact_hit_top5"]
    summary = per_match.groupby("wc")[agg_cols].mean()
    summary["n"] = per_match.groupby("wc").size()
    overall = per_match[agg_cols].mean().to_frame().T
    overall.index = ["all"]
    overall["n"] = len(per_match)
    summary = pd.concat([summary, overall])
    return per_match, summary
