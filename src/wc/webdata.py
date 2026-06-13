"""Build the rich JSON bundle the frontend renders.

Turns the pipeline's in-memory objects (ratings, fitted params, per-fixture
predictions, simulation advancement, market comparison, backtest) into one
self-contained bundle, and — crucially — generates a data-grounded reasoning
breakdown for every match: the factors that drive the model's call (Elo gap,
squad value, expected goals, recent form, home edge, model-vs-market) plus a
short prose narrative. Nothing here is hand-waved; every sentence is computed.
"""
from __future__ import annotations

import pandas as pd

FLAGS = {
    "Mexico": "🇲🇽", "South Africa": "🇿🇦", "South Korea": "🇰🇷", "Czech Republic": "🇨🇿",
    "Canada": "🇨🇦", "Bosnia and Herzegovina": "🇧🇦", "Qatar": "🇶🇦", "Switzerland": "🇨🇭",
    "Brazil": "🇧🇷", "Morocco": "🇲🇦", "Haiti": "🇭🇹", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "United States": "🇺🇸", "Paraguay": "🇵🇾", "Australia": "🇦🇺", "Turkey": "🇹🇷",
    "Germany": "🇩🇪", "Curaçao": "🇨🇼", "Ivory Coast": "🇨🇮", "Ecuador": "🇪🇨",
    "Netherlands": "🇳🇱", "Japan": "🇯🇵", "Sweden": "🇸🇪", "Tunisia": "🇹🇳",
    "Belgium": "🇧🇪", "Egypt": "🇪🇬", "Iran": "🇮🇷", "New Zealand": "🇳🇿",
    "Spain": "🇪🇸", "Cape Verde": "🇨🇻", "Saudi Arabia": "🇸🇦", "Uruguay": "🇺🇾",
    "France": "🇫🇷", "Senegal": "🇸🇳", "Iraq": "🇮🇶", "Norway": "🇳🇴",
    "Argentina": "🇦🇷", "Algeria": "🇩🇿", "Austria": "🇦🇹", "Jordan": "🇯🇴",
    "Portugal": "🇵🇹", "DR Congo": "🇨🇩", "Uzbekistan": "🇺🇿", "Colombia": "🇨🇴",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Croatia": "🇭🇷", "Ghana": "🇬🇭", "Panama": "🇵🇦",
}
HOSTS = ("United States", "Mexico", "Canada")


def flag(team: str) -> str:
    return FLAGS.get(team, "🏳️")


def recent_form(df: pd.DataFrame, team: str, asof, n: int = 6) -> list[dict]:
    """Last n completed matches for a team (any competition) before asof,
    from the team's own perspective."""
    asof = pd.Timestamp(asof)
    sub = df[((df["home_team"] == team) | (df["away_team"] == team)) & (df["date"] < asof)].tail(n)
    out = []
    for r in sub.itertuples(index=False):
        home = r.home_team == team
        gf, ga = (r.home_score, r.away_score) if home else (r.away_score, r.home_score)
        opp = r.away_team if home else r.home_team
        out.append({"res": "W" if gf > ga else ("D" if gf == ga else "L"),
                    "gf": int(gf), "ga": int(ga), "opp": opp,
                    "date": str(pd.Timestamp(r.date).date())})
    return out


def _lean(diff: float, tol: float) -> str:
    return "home" if diff > tol else ("away" if diff < -tol else "even")


def match_factors(fx: dict, values: dict, form_h: list, form_a: list, mkt: dict | None) -> dict:
    """Structured driver list + prose narrative for one fixture."""
    H, A = fx["home"], fx["away"]
    eh, ea = float(fx["elo_h"]), float(fx["elo_a"])
    lh, la = float(fx["lambda_h"]), float(fx["lambda_a"])
    ph, pdr, pa = float(fx["p_home"]), float(fx["p_draw"]), float(fx["p_away"])
    vh, va = values.get(H), values.get(A)
    gap = eh - ea
    fav, favp = (H, ph) if ph >= pa else (A, pa)

    factors = [{
        "label": "实力评分 Elo", "lean": _lean(gap, 25),
        "detail": f"{eh:.0f} vs {ea:.0f}（{gap:+.0f}）",
    }, {
        "label": "预期进球 xG", "lean": _lean(lh - la, 0.2),
        "detail": f"{lh:.2f} – {la:.2f}",
    }]
    if vh and va:
        factors.append({"label": "阵容市值", "lean": _lean(vh - va, max(50, 0.15 * max(vh, va))),
                        "detail": f"€{vh:.0f}M vs €{va:.0f}M"})

    def form_str(f):
        return "".join(x["res"] for x in f) or "—"
    fpts = lambda f: sum(3 if x["res"] == "W" else (1 if x["res"] == "D" else 0) for x in f)
    factors.append({"label": "近期状态", "lean": _lean(fpts(form_h) - fpts(form_a), 2),
                    "detail": f"{form_str(form_h)} vs {form_str(form_a)}"})

    venue = fx.get("venue_country", "")
    if H in HOSTS and H == venue:
        factors.append({"label": "主场", "lean": "home", "detail": f"{H} 主办国主场"})
    elif A in HOSTS and A == venue:
        factors.append({"label": "主场", "lean": "away", "detail": f"{A} 主办国主场"})
    else:
        factors.append({"label": "场地", "lean": "even", "detail": "中立场"})

    diverge = None
    if mkt:
        mh, md, ma = mkt["mkt_home"], mkt["mkt_draw"], mkt["mkt_away"]
        d_fav = (ph - mh) if fav == H else (pa - ma)
        diverge = round(100 * d_fav, 1)
        factors.append({"label": "模型 vs 市场", "lean": "home" if d_fav > 0.02 else ("away" if d_fav < -0.02 else "even"),
                        "detail": f"{fav} 模型 {favp:.0%} / 市场 {(mh if fav==H else ma):.0%}"})

    # prose
    bits = [f"模型看好 **{fav}**（{favp:.0%}），预期比分约 {lh:.1f}–{la:.1f}。"]
    if abs(gap) >= 150:
        bits.append(f"{'实力差距明显' if abs(gap)>=300 else '实力略占优'}（Elo {gap:+.0f}）。")
    if vh and va and max(vh, va) / max(min(vh, va), 1) >= 3:
        rich = H if vh > va else A
        bits.append(f"{rich} 阵容身价高出数倍。")
    top = str(fx.get("top_scores", "")).split("; ")[:1]
    if top and top[0]:
        bits.append(f"最可能比分 {top[0]}。")
    if diverge is not None and abs(diverge) >= 3:
        bits.append(f"模型比市场更{'看好' if diverge>0 else '看淡'} {fav}（{diverge:+.1f}pp）——值得关注的分歧点。")
    elif mkt:
        bits.append("与市场基本一致。")
    return {"factors": factors, "narrative": " ".join(bits), "diverge": diverge}


def _top_scores_list(s: str) -> list[dict]:
    out = []
    for chunk in str(s).split("; "):
        chunk = chunk.strip()
        if not chunk:
            continue
        sc, _, pct = chunk.partition(" ")
        out.append({"score": sc, "p": pct})
    return out


def _group_standings(groups, schedule):
    """Live points table from played group matches only."""
    tables = {}
    for g, teams in groups.items():
        stat = {t: {"team": t, "flag": flag(t), "pld": 0, "w": 0, "d": 0, "l": 0,
                    "gf": 0, "ga": 0, "pts": 0} for t in teams}
        tables[g] = stat
    for m in schedule:
        if m.get("stage") != "group" or m.get("status") != "played":
            continue
        g = m["group"]
        h, a = m["home"], m["away"]
        hs, as_ = int(m["home_score"]), int(m["away_score"])
        for t, gf, ga in ((h, hs, as_), (a, as_, hs)):
            s = tables[g][t]
            s["pld"] += 1
            s["gf"] += gf
            s["ga"] += ga
            s["w"] += gf > ga
            s["d"] += gf == ga
            s["l"] += gf < ga
            s["pts"] += 3 if gf > ga else (1 if gf == ga else 0)
    return {g: sorted(s.values(), key=lambda x: (-x["pts"], -(x["gf"] - x["ga"]), -x["gf"]))
            for g, s in tables.items()}


def build_bundle(*, asof, n_sims, df, groups, schedule, ratings_elo, ratings, values,
                 fixtures, live, adv, market_outright, fixtures_market, fit, blend_info,
                 bt_summary, calibration, calibration_ece, market_beat, sources,
                 betting_backtest=None, value_bets=None, injuries=None, methodology=None):
    advm = {r["team"]: r for r in adv.to_dict("records")}
    mkt_map = {}
    if market_outright is not None:
        mkt_map = {r["team"]: r["p_market"] for r in market_outright.to_dict("records")}

    leaderboard = []
    for r in adv.to_dict("records"):
        t = r["team"]
        leaderboard.append({
            "team": t, "flag": flag(t), "p_champion": r["p_champion"], "p_r32": r["p_r32"],
            "p_market": mkt_map.get(t), "elo": round(ratings_elo.get(t, 0), 0),
            "value": values.get(t),
            "diff": (r["p_champion"] - mkt_map[t]) if t in mkt_map else None,
        })

    team_group = {t: g for g, ts in groups.items() for t in ts}
    advancement = [{
        "team": r["team"], "flag": flag(r["team"]), "group": team_group.get(r["team"]),
        "p_r32": r["p_r32"], "p_r16": r["p_r16"], "p_qf": r["p_qf"], "p_sf": r["p_sf"],
        "p_final": r["p_final"], "p_champion": r["p_champion"],
    } for r in adv.to_dict("records")]

    standings = _group_standings(groups, schedule)
    groups_out = {}
    for g, teams in groups.items():
        groups_out[g] = [{
            "team": t, "flag": flag(t), "elo": round(ratings_elo.get(t, 0), 0),
            "value": values.get(t), "p_advance": advm.get(t, {}).get("p_r32"),
        } for t in teams]

    fmkt = {}
    if fixtures_market is not None:
        for r in fixtures_market.to_dict("records"):
            fmkt[(r["home"], r["away"])] = r

    forms = {}

    def form(t):
        if t not in forms:
            forms[t] = recent_form(df, t, asof)
        return forms[t]

    fixtures_out = []
    for fx in fixtures.to_dict("records"):
        H, A = fx["home"], fx["away"]
        mkt = fmkt.get((H, A))
        meta = match_factors(fx, values, form(H), form(A), mkt)
        fixtures_out.append({
            "n": fx.get("n"), "date": fx["date"], "group": fx.get("group"),
            "stage": fx.get("stage"), "home": H, "away": A,
            "flagH": flag(H), "flagA": flag(A),
            "p_home": fx["p_home"], "p_draw": fx["p_draw"], "p_away": fx["p_away"],
            "lambda_h": fx["lambda_h"], "lambda_a": fx["lambda_a"],
            "elo_h": round(float(fx["elo_h"])), "elo_a": round(float(fx["elo_a"])),
            "top_scores": _top_scores_list(fx.get("top_scores", "")),
            "market": ({"h": mkt["mkt_home"], "d": mkt["mkt_draw"], "a": mkt["mkt_away"],
                        "source": mkt.get("source", "")} if mkt else None),
            "form_h": form(H), "form_a": form(A),
            "factors": meta["factors"], "narrative": meta["narrative"], "diverge": meta["diverge"],
            "markets": fx.get("markets"),
        })

    live_out = []
    if live is not None and len(live):
        for r in live.to_dict("records"):
            live_out.append({
                "date": r["date"], "home": r["home"], "away": r["away"],
                "flagH": flag(r["home"]), "flagA": flag(r["away"]),
                "actual": r["actual"], "p_home": r["p_home"], "p_draw": r["p_draw"],
                "p_away": r["p_away"], "outcome": r["outcome"], "rps": r["rps"],
                "fav_hit": int(r["fav_hit"]),
            })

    credibility = {
        "backtest": (bt_summary.reset_index().rename(columns={"index": "wc"}).to_dict("records")
                     if bt_summary is not None else []),
        "calibration": (calibration.to_dict("records") if calibration is not None else []),
        "calibration_ece": calibration_ece,
        "market_beat": market_beat,
        "betting_backtest": betting_backtest,
    }
    # attach injuries to each group team for the UI
    inj = (injuries or {}).get("by_team", {}) if isinstance(injuries, dict) else {}
    for g in groups_out:
        for row in groups_out[g]:
            if row["team"] in inj:
                row["injuries"] = inj[row["team"]]

    return {
        "meta": {
            "asof": str(asof), "n_sims": n_sims,
            "tournament": {"name": "FIFA World Cup 2026", "dates": "2026-06-11 → 07-19",
                           "hosts": "USA · Canada · Mexico", "teams": 48},
            "data_info": sources,
            "fit": {"b0": round(fit["params"][0], 3), "b1": round(fit["params"][1], 3),
                    "home": round(fit["params"][2], 3), "rho": round(fit["params"][3], 4),
                    "n": fit["n_matches"]},
        },
        "leaderboard": leaderboard,
        "advancement": advancement,
        "groups": groups_out,
        "standings": standings,
        "fixtures": fixtures_out,
        "live": live_out,
        "credibility": credibility,
        "betting": {"value_bets": value_bets or [], "backtest": betting_backtest},
        "injuries": inj,
        "methodology": methodology,
    }
