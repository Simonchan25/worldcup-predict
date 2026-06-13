#!/usr/bin/env python3
"""Does sharpening the model's probabilities improve it? (Answer: no.)

The backtest calibration table shows the model is mildly UNDER-dispersed:
in the 0.4-0.7 predicted-probability bins, favourites win a bit more often
than predicted. The natural fix is to sharpen — scale the Elo coefficient
b1 by a multiplier m>1 so the favourite's goal rate stretches further from
the underdog's (this propagates consistently into the score grid and the
Monte Carlo, unlike a post-hoc 1X2 power transform).

This script sweeps m and, crucially, runs leave-one-tournament-out CV. The
verdict: the best m is tournament-specific noise (2014 was a chalk World
Cup and wants m>1.5; 2022 was an upset-heavy one and wants m=1.0), so
tuning it makes HELD-OUT RPS worse. We therefore keep the MLE-fit b1 (m=1)
and treat the residual under-dispersion as the irreducible humility the
model should have about modern World Cups. Rerun to re-verify the decision.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wc import backtest, data, elo, model  # noqa: E402

CUT = {2014: "2014-06-12", 2018: "2018-06-14", 2022: "2022-11-20"}
GRID_M = [1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.4, 1.5, 1.6]


def build():
    df = data.load_results("1950-01-01")
    _, df = elo.run_elo(df)
    per_wc = {}
    for yr, cut in CUT.items():
        c = pd.Timestamp(cut)
        fit = model.fit(df[df["date"] < c], ref_date=c, since=f"{yr - 16}-01-01", xi=0.25)
        p = fit["params"]
        test = df[(df["tournament"] == "FIFA World Cup") & (df["date"] >= c)
                  & (df["date"] < c + pd.Timedelta(days=45))]
        per_wc[yr] = [(r.elo_h, r.elo_a, 0.0 if r.neutral else 1.0,
                       0 if r.home_score > r.away_score else (1 if r.home_score == r.away_score else 2),
                       p) for r in test.itertuples(index=False)]
    return per_wc


def wdl_at(eh, ea, params, m, home):
    pp = [params[0], m * params[1], params[2], params[3]]
    grid, _, _ = model.score_matrix(eh, ea, pp, home=home)
    return np.array(model.wdl(grid))


def wc_rps(per_wc, yr, m):
    return float(np.mean([backtest.rps(wdl_at(eh, ea, p, m, hm), o)
                          for eh, ea, hm, o, p in per_wc[yr]]))


def main():
    per_wc = build()
    print("=== per-World-Cup RPS by sharpening multiplier m on b1 ===")
    print(f"{'m':>5} " + " ".join(f"{yr:>8}" for yr in CUT) + f" {'ALL':>8}")
    allm = [r for yr in CUT for r in per_wc[yr]]
    for m in GRID_M:
        allrps = np.mean([backtest.rps(wdl_at(eh, ea, p, m, hm), o) for eh, ea, hm, o, p in allm])
        print(f"{m:>5} " + " ".join(f"{wc_rps(per_wc, yr, m):8.4f}" for yr in CUT) + f" {allrps:8.4f}")

    print("\n=== leave-one-tournament-out CV (m* chosen on the other two) ===")
    cv_base, cv_tuned = [], []
    for test_yr in CUT:
        others = [y for y in CUT if y != test_yr]
        best_m = min(GRID_M, key=lambda m: sum(wc_rps(per_wc, y, m) * len(per_wc[y]) for y in others))
        base, tuned = wc_rps(per_wc, test_yr, 1.0), wc_rps(per_wc, test_yr, best_m)
        cv_base.append((base, len(per_wc[test_yr])))
        cv_tuned.append((tuned, len(per_wc[test_yr])))
        print(f"  held-out {test_yr}: m*={best_m}  m=1: {base:.4f} -> tuned: {tuned:.4f}"
              f"  ({'better' if tuned < base else 'WORSE'})")
    w = lambda xs: sum(v * n for v, n in xs) / sum(n for _, n in xs)
    print(f"\n  CV mean RPS  baseline(m=1): {w(cv_base):.4f}   tuned: {w(cv_tuned):.4f}")
    print("  => " + ("keep m=1 (tuning does not generalise)" if w(cv_tuned) >= w(cv_base)
                     else "tuning helps — reconsider"))


if __name__ == "__main__":
    main()
