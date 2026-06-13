"""Market-beat backtest: does the model beat the betting market on past
World Cups?

We have, from directly-readable raw mirrors:
  - 2014 Betfair pre-match 1X2 decimal odds (64 matches)
  - 2018 Betfair pre-match 1X2 decimal odds (48 group matches)
  - FiveThirtyEight SPI per-match win/draw/loss probabilities (2018 + 2022)

For every historical match where we have a market view, we line up the
model's *out-of-sample* probabilities (Dixon-Coles fit strictly before that
tournament's cutoff, pre-match Elo — exactly what backtest.run_backtest
already computes) against the market's, on the identical match and outcome,
and score both with RPS. Lower RPS wins. Bookmaker odds are de-margined
proportionally; 538 probabilities are used as published.

This is the honest "is there alpha?" test: beating the de-margined closing
line is the football analogue of beating the market in QStockLAB.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import market
from .backtest import rps
from .names import canon

OUTCOME_IDX = {"H": 0, "D": 1, "A": 2}


def load_hist(path: str | Path) -> dict:
    """Parse the raw acquisition JSON into {label: {'kind','rows'}} where each
    row is (date, home, away, probs[3]) with canonical names and home-oriented
    market probabilities."""
    acq = json.loads(Path(path).read_text(encoding="utf-8"))
    sets = {}

    def add_odds(key, label):
        v = acq.get(key) or {}
        rows = []
        for it in v.get("items", []):
            try:
                p = market.implied_1x2(it["home_odds"], it["draw_odds"], it["away_odds"])
            except (KeyError, TypeError, ZeroDivisionError):
                continue
            rows.append((it.get("date"), canon(it["home"]), canon(it["away"]),
                         [float(p[0]), float(p[1]), float(p[2])]))
        if rows:
            sets[label] = {"kind": "Betfair 赔率", "rows": rows,
                           "source": v.get("source", ""), "url": v.get("raw_url")}

    add_odds("wc2014", "2014 (Betfair)")
    add_odds("wc2018", "2018 (Betfair)")

    # FiveThirtyEight probabilities, split by tournament year via the date
    fte = acq.get("fte") or {}
    by_year = {}
    for it in fte.get("items", []):
        if it.get("p_home") is None:
            continue
        yr = str(it.get("date", ""))[:4]
        by_year.setdefault(yr, []).append(
            (it.get("date"), canon(it["home"]), canon(it["away"]),
             [float(it["p_home"]), float(it["p_draw"]), float(it["p_away"])]))
    for yr, rows in by_year.items():
        if yr in ("2018", "2022") and rows:
            sets[f"{yr} (538)"] = {"kind": "FiveThirtyEight 模型", "rows": rows,
                                   "source": fte.get("source", "")}
    return sets


def _build_lookup(per_match: pd.DataFrame):
    """(frozenset(pair), date) -> row, plus (frozenset(pair)) -> [rows] fallback."""
    exact, byp = {}, {}
    for r in per_match.itertuples(index=False):
        pair = frozenset((r.home, r.away))
        d = str(pd.Timestamp(r.date).date())
        exact[(pair, d)] = r
        byp.setdefault(pair, []).append(r)
    return exact, byp


def market_beat(per_match: pd.DataFrame, hist: dict) -> dict:
    exact, byp = _build_lookup(per_match)
    tournaments, bm_model, bm_market = [], [], []
    for label, blk in hist.items():
        rows_m, rows_k, n_unmatched = [], [], 0
        for date, h, a, mp in blk["rows"]:
            pair = frozenset((h, a))
            row = exact.get((pair, str(date)))
            if row is None:
                cand = byp.get(pair, [])
                row = cand[0] if len(cand) == 1 else None
            if row is None:
                n_unmatched += 1
                continue
            # orient market probs to the model row's home side
            mkt = mp if h == row.home else [mp[2], mp[1], mp[0]]
            out = OUTCOME_IDX[row.outcome]
            rows_m.append(rps([row.p_home, row.p_draw, row.p_away], out))
            rows_k.append(rps(mkt, out))
        if not rows_m:
            continue
        is_book = "Betfair" in blk["kind"]
        tournaments.append({
            "wc": label, "kind": blk["kind"], "n": len(rows_m),
            "rps_model": float(np.mean(rows_m)), "rps_market": float(np.mean(rows_k)),
            "is_bookmaker": is_book, "unmatched": n_unmatched,
            "source": blk.get("source", ""),
        })
        if is_book:
            bm_model.extend(rows_m)
            bm_market.extend(rows_k)

    overall = None
    if bm_model:
        rm, rk = float(np.mean(bm_model)), float(np.mean(bm_market))
        overall = {"n": len(bm_model), "rps_model": rm, "rps_market": rk,
                   "model_better": rm <= rk, "margin": rk - rm}
    note = ("对标真实博彩闭线（2014+2018 Betfair）。市场赔率经 proportional 去 margin。"
            "538 行为职业模型对照。RPS 越低越好；模型要「跑赢市场」须 RPS ≤ 市场。"
            "样本为可联网取得的历史赔率，不含全部淘汰赛场次。")
    return {"tournaments": tournaments, "overall": overall, "note": note}
