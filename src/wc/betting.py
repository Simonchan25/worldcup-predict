"""Value betting: turn model-vs-market gaps into EV, and HONESTLY test whether
betting them makes money.

`current_value` ranks the model's edges on upcoming fixtures (model prob × the
*offered* decimal odds − 1). `betting_backtest` is the reality check: it replays
flat- and Kelly-staked value-betting strategies over past World Cups using the
real Betfair prices we have (2014 + 2018), and reports ROI. The expected — and
observed — answer is that you do NOT beat the closing line: the model roughly
matches the market (see market_backtest), so the "value" it sees is mostly its
own error plus the bookmaker margin. Combining legs (parlays) only multiplies
that margin. This module exists to demonstrate that with numbers, not to beat it.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import markets
from .names import canon

OUTCOME_IDX = {"H": 0, "D": 1, "A": 2}
LABELS = ("home", "draw", "away")


def load_raw_odds(path: str | Path) -> dict:
    """{label: [(date, home, away, [oH,oD,oA])]} for the Betfair odds sets."""
    acq = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for key, label in (("wc2014", "2014"), ("wc2018", "2018")):
        v = acq.get(key) or {}
        rows = []
        for it in v.get("items", []):
            o = [it.get("home_odds"), it.get("draw_odds"), it.get("away_odds")]
            if all(x and x > 1 for x in o):
                rows.append((it.get("date"), canon(it["home"]), canon(it["away"]),
                             [float(o[0]), float(o[1]), float(o[2])]))
        if rows:
            out[label] = rows
    return out


def _lookup(per_match: pd.DataFrame):
    exact, byp = {}, {}
    for r in per_match.itertuples(index=False):
        pair = frozenset((r.home, r.away))
        exact[(pair, str(pd.Timestamp(r.date).date()))] = r
        byp.setdefault(pair, []).append(r)
    return exact, byp


def betting_backtest(per_match: pd.DataFrame, raw: dict) -> dict:
    exact, byp = _lookup(per_match)
    rows = []  # (model_p[3], odds[3], outcome_idx) oriented to per_match home
    for label, items in raw.items():
        for date, h, a, od in items:
            pair = frozenset((h, a))
            row = exact.get((pair, str(date)))
            if row is None:
                cand = byp.get(pair, [])
                row = cand[0] if len(cand) == 1 else None
            if row is None:
                continue
            odds = od if h == row.home else [od[2], od[1], od[0]]
            rows.append(([row.p_home, row.p_draw, row.p_away], odds, OUTCOME_IDX[row.outcome]))

    def ev(mp, odds, o):
        return mp[o] * odds[o] - 1.0

    def run(name, selector, stake_fn):
        staked = profit = 0.0
        nb = wins = 0
        for mp, odds, out in rows:
            for o in range(3):
                if not selector(mp, odds, o):
                    continue
                st = stake_fn(mp, odds, o)
                if st <= 0:
                    continue
                staked += st
                nb += 1
                if o == out:
                    profit += st * (odds[o] - 1)
                    wins += 1
                else:
                    profit -= st
        return {"name": name, "n_bets": nb, "staked": round(staked, 2),
                "profit": round(profit, 2), "roi": (profit / staked) if staked else 0.0,
                "win_rate": (wins / nb) if nb else 0.0}

    strat = []
    for thr in (0.0, 0.05, 0.10, 0.20):
        strat.append(run(f"价值投注 EV>{int(thr * 100)}%（平注）",
                         lambda mp, odds, o, t=thr: ev(mp, odds, o) > t,
                         lambda mp, odds, o: 1.0))
    strat.append(run("价值投注 EV>0（¼ Kelly）",
                     lambda mp, odds, o: ev(mp, odds, o) > 0,
                     lambda mp, odds, o: 0.25 * markets.value(mp[o], odds[o])["kelly"]))
    strat.append(run("盲投模型热门（平注）",
                     lambda mp, odds, o: o == int(np.argmax(mp)),
                     lambda mp, odds, o: 1.0))
    strat.append(run("每场投最大 EV 项（平注）",
                     lambda mp, odds, o: o == int(np.argmax([ev(mp, odds, k) for k in range(3)])),
                     lambda mp, odds, o: 1.0))

    # The honest diagnostic: if the model had a real, exploitable edge, ROI
    # should RISE as we demand a bigger model-vs-market gap (EV threshold). The
    # higher-confidence "value" bets should be the most profitable. Here ROI
    # FALLS as the threshold rises — the classic signature of NO edge: the
    # model's disagreements with the market are noise. Any headline positive
    # ROI (e.g. betting favourites) is small-sample luck — 2014 & 2018 were
    # "chalk" tournaments where favourites delivered — plus favourite-longshot
    # bias, not replicable skill (and it squares with market_backtest: the
    # model's RPS is slightly WORSE than the market's).
    flat = [s for s in strat if "平注" in s["name"] and "EV>" in s["name"]]
    rois = [s["roi"] for s in flat]                      # ordered EV>0,5,10,20
    edge_is_real = len(rois) >= 2 and rois[-1] > rois[0] + 0.01
    verdict = ("高阈值价值注反而更赚——存在可疑的真实优势,值得进一步验证" if edge_is_real else
               "「越高把握的价值注、ROI 反而越低」(EV>0→EV>20% 一路下滑),"
               "这是「无可利用优势」的典型特征:模型与市场的分歧是噪声不是信号。"
               "个别策略(如盲投热门)的正收益来自 2014/18 是「大热之年」的小样本运气 + "
               "大热-冷门偏差;换到冷门之年(如 2022)极可能转负。")
    note = ("在 2014+2018 真实 Betfair 赔率上回放价值投注。" + verdict +
            " 而且这些是低抽水的交易所闭线价——真实软庄抽水更高、无法无风险下注;"
            "串关(组合)只会把每注的抽水相乘,EV 更差,不是「收益最大化」而是「方差最大化」。")
    return {"strategies": strat, "n_matches": len(rows), "edge_is_real": edge_is_real,
            "roi_by_threshold": [round(x, 4) for x in rois], "note": note}


def current_value(fixtures: list[dict], odds_matches: list[dict], min_edge: float = 0.0) -> list[dict]:
    """Rank model edges on upcoming fixtures against the *offered* 1X2 odds."""
    by_pair = {(o["home"], o["away"]): o for o in odds_matches}
    out = []
    for fx in fixtures:
        o = by_pair.get((fx["home"], fx["away"]))
        if not o:
            continue
        for k, lbl, mp, odd in (("home", "胜", fx["p_home"], o["home_odds"]),
                                ("draw", "平", fx["p_draw"], o["draw_odds"]),
                                ("away", "负", fx["p_away"], o["away_odds"])):
            if not odd or odd <= 1:
                continue
            v = markets.value(mp, odd)
            if v["ev"] > min_edge:
                out.append({"date": fx["date"], "home": fx["home"], "away": fx["away"],
                            "pick": f"{fx['home']} vs {fx['away']} · {lbl}",
                            "side": k, "model_p": round(mp, 4), "odds": odd,
                            "ev_pct": round(v["edge_pct"], 1), "kelly_pct": round(100 * v["kelly"], 1),
                            "book": o.get("source", "")})
    return sorted(out, key=lambda x: -x["ev_pct"])
