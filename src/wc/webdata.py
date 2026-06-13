"""Build the rich JSON bundle the frontend renders.

Turns the pipeline's in-memory objects (ratings, fitted params, per-fixture
predictions, simulation advancement, market comparison, backtest) into one
self-contained bundle, and — crucially — generates a data-grounded reasoning
breakdown for every match: the factors that drive the model's call (Elo gap,
squad value, expected goals, recent form, home edge, model-vs-market) plus a
short prose narrative. Nothing here is hand-waved; every sentence is computed.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from scipy.stats import poisson

from . import backtest, market, model

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


def elo_trend(df: pd.DataFrame, teams: list[str], months: int = 16) -> dict:
    """Each team's pre-match Elo at every match in the last `months` — a real
    strength trajectory for the dashboard trend chart."""
    cutoff = df["date"].max() - pd.Timedelta(days=30 * months)
    sub = df[df["date"] >= cutoff]
    out = {}
    for t in teams:
        tm = sub[(sub["home_team"] == t) | (sub["away_team"] == t)].sort_values("date")
        rows = [{"date": str(pd.Timestamp(r.date).date()),
                 "elo": round(float(r.elo_h if r.home_team == t else r.elo_a))}
                for r in tm.itertuples(index=False)]
        if rows:
            out[t] = rows
    return out


def _devig2(o_over, o_under):
    inv = [1.0 / o_over, 1.0 / o_under]
    s = sum(inv)
    return inv[0] / s, inv[1] / s


def odds_compare(fx: dict, book: dict | None) -> list[dict]:
    """Model fair odds vs the live bookmaker across 1X2 and totals 2.5.
    edge = model_p × book_decimal − 1 (positive = model sees value)."""
    if not book:
        return []
    rows = []
    h2h = book.get("h2h") or {}
    if all(h2h.get(k) for k in ("home", "draw", "away")):
        imp = market.implied_1x2(h2h["home"], h2h["draw"], h2h["away"])
        for key, lbl, mp, bi in (("home", "主胜", fx["p_home"], imp[0]),
                                 ("draw", "平局", fx["p_draw"], imp[1]),
                                 ("away", "客胜", fx["p_away"], imp[2])):
            rows.append({"market": "胜平负", "sel": lbl, "model_p": round(mp, 4),
                         "fair": round(1.0 / max(mp, 1e-6), 2), "book": h2h[key],
                         "book_imp": round(float(bi), 4), "edge": round(mp * h2h[key] - 1, 3)})
    tot = book.get("totals")
    mk = fx.get("markets")
    if tot and mk and tot.get("over") and tot.get("under"):
        ou = mk["over_under"]["2.5"]
        bi_o, bi_u = _devig2(tot["over"], tot["under"])
        for sel, mp, bo, bi in (("大 2.5", ou["over"], tot["over"], bi_o),
                                ("小 2.5", ou["under"], tot["under"], bi_u)):
            rows.append({"market": "进球大小", "sel": sel, "model_p": round(mp, 4),
                         "fair": round(1.0 / max(mp, 1e-6), 2), "book": bo,
                         "book_imp": round(bi, 4), "edge": round(mp * bo - 1, 3)})
    return rows


def _score_breakdown(mk: dict) -> dict:
    """Most likely scoreline overall + the top score for each result type."""
    cs = mk.get("correct_score", []) if mk else []
    def _parse(s):
        a, _, b = s.partition("-"); return int(a), int(b)
    best = {"home": None, "draw": None, "away": None}
    for c in cs:
        h, a = _parse(c["score"])
        k = "home" if h > a else ("draw" if h == a else "away")
        if best[k] is None or c["p"] > best[k]["p"]:
            best[k] = c
    return {"top": cs[:8], "by_result": best}


def build_schedule(schedule: list, all_fixtures) -> list[dict]:
    """Full fixture list: every match with actual result (if played) and the
    model's prediction (concrete most-likely scoreline + 1X2)."""
    pred = {r.get("n"): r for r in all_fixtures.to_dict("records")} if all_fixtures is not None else {}
    out = []
    for m in schedule:
        n = m.get("n")
        home, away = str(m.get("home")), str(m.get("away"))
        ko_slot = m.get("stage") != "group" and home not in FLAGS
        e = {"n": n, "date": m.get("date"), "stage": m.get("stage"), "group": m.get("group"),
             "venue": m.get("venue_country", ""), "status": m.get("status", "scheduled"),
             "home": home, "away": away, "flagH": flag(home) if home in FLAGS else "",
             "flagA": flag(away) if away in FLAGS else "", "ko_slot": ko_slot}
        if m.get("status") == "played" and m.get("home_score") is not None:
            e["actual"] = f"{int(m['home_score'])}-{int(m['away_score'])}"
            e["actual_outcome"] = ("home" if m["home_score"] > m["away_score"]
                                   else "draw" if m["home_score"] == m["away_score"] else "away")
        p = pred.get(n)
        if p and p.get("home") in FLAGS and p.get("away") in FLAGS:
            sb = _score_breakdown(p.get("markets"))
            top = (sb.get("top") or [{}])[0]
            probs = {"home": p["p_home"], "draw": p["p_draw"], "away": p["p_away"]}
            pick = max(probs, key=probs.get)
            e.update(home=p["home"], away=p["away"], flagH=flag(p["home"]), flagA=flag(p["away"]))
            e["pred"] = {"p_home": p["p_home"], "p_draw": p["p_draw"], "p_away": p["p_away"],
                         "pick": pick, "pick_p": probs[pick], "score": top.get("score", ""),
                         "lambda_h": p["lambda_h"], "lambda_a": p["lambda_a"]}
            if "actual_outcome" in e:
                e["pred_hit"] = int(pick == e["actual_outcome"])
        out.append(e)
    return out


def build_recommendations(value_bets, bankroll: int = 1000) -> list[dict]:
    """Turn positive-EV edges into concrete buy suggestions: ¼-Kelly stake and
    the model's expected return. (Honesty lives in the UI banner — the
    historical betting backtest shows these don't beat the closing line.)"""
    recs = []
    for v in (value_bets or [])[:12]:
        stake = round(bankroll * (v["kelly_pct"] / 100.0) * 0.25, 1)
        recs.append({**v, "stake": stake, "exp_return": round(stake * v["ev_pct"] / 100.0, 1),
                     "payout": round(stake * v["odds"], 1)})
    return recs


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


_RE_RANK = re.compile(r"^([12])([A-L])$")
_RE_THIRD = re.compile(r"^3:([A-L]+|\*)$")
_RE_WL = re.compile(r"^([WL]):?(\d+)$")


def ko_matchup(home, away, venue, ratings, params, max_goals: int = 10) -> dict:
    """Model probabilities for a knockout tie between two concrete teams,
    resolved exactly the way the simulator does: regulation from the
    Dixon-Coles grid, a draw goes to extra time (independent Poisson at a third
    of the 90' rate) and then a 50/50 shootout. Returns home/away advance
    probabilities plus the most-likely regulation scoreline."""
    swapped = away in HOSTS and away == venue and home != venue
    if swapped:
        a, b, flag = away, home, 1
    else:
        a, b = home, away
        flag = 1 if (home in HOSTS and home == venue) else 0
    m, lh, la = model.score_matrix(ratings[a], ratings[b], params, home=float(flag))
    p_a = float(np.tril(m, -1).sum())          # a wins in regulation
    p_d = float(np.trace(m))
    g = np.arange(max_goals + 1)
    et = np.outer(poisson.pmf(g, lh / 3.0), poisson.pmf(g, la / 3.0))
    et_a, et_d = float(np.tril(et, -1).sum()), float(np.trace(et))
    adv_a = p_a + p_d * (et_a + 0.5 * et_d)    # advance = reg win + draw→ET/pens
    idx = int(np.argmax(m))
    si, sj = idx // m.shape[1], idx % m.shape[1]
    if swapped:                                 # a is the displayed away side
        return {"p_home_adv": round(1 - adv_a, 4), "p_away_adv": round(adv_a, 4),
                "score": f"{sj}-{si}"}
    return {"p_home_adv": round(adv_a, 4), "p_away_adv": round(1 - adv_a, 4),
            "score": f"{si}-{sj}"}


def build_bracket(sim, adv, ratings, params) -> dict:
    """Projected knockout bracket: fill each slot with the model's most-likely
    occupant (group winners/runners-up by P(finish 1st/2nd), best thirds by
    P(qualify as third)), then let the favourite advance round by round. Each
    node carries that matchup's advance probabilities. Honest framing: this is
    the *modal-per-match* path, not the single most-likely whole bracket — the
    headline champion probabilities come from the full simulation."""
    advm = {r["team"]: r for r in adv.to_dict("records")}
    pf = lambda t, k: advm.get(t, {}).get(k, 0.0)
    g1, g2, third_of = {}, {}, {}
    for g, teams in sim.groups.items():
        ranked = sorted(teams, key=lambda t: -pf(t, "p_first"))
        g1[g] = ranked[0]
        rest = sorted(ranked[1:], key=lambda t: -pf(t, "p_second"))
        g2[g] = rest[0]
        third_of[g] = max(rest[1:], key=lambda t: pf(t, "p_qual3")) if len(rest) > 1 else rest[0]
    top_groups = sorted(sim.groups, key=lambda g: -pf(third_of[g], "p_qual3"))[:8]
    third_assign = sim.allocate_thirds({g: third_of[g] for g in top_groups})

    win, lose = {}, {}

    def resolve(code, n):
        code = str(code)
        rk = _RE_RANK.match(code)
        if rk:
            return (g1 if rk.group(1) == "1" else g2).get(rk.group(2))
        if _RE_THIRD.match(code):
            return third_assign.get(n)
        wl = _RE_WL.match(code)
        if wl:
            src = int(wl.group(2))
            return win.get(src) if wl.group(1) == "W" else lose.get(src)
        return code if code in ratings else None

    by_stage = {}
    for m in sim.ko_template:                   # already sorted by round then n
        n, stage, venue = m["n"], m["stage"], m.get("venue_country", "")
        played = (m.get("status") == "played" and str(m["home"]) in ratings
                  and m.get("home_score") is not None)
        if played:
            h, a = str(m["home"]), str(m["away"])
        else:
            h, a = resolve(m["home"], n), resolve(m["away"], n)
        node = {"n": n, "stage": stage, "home": h, "away": a,
                "flagH": flag(h) if h else "", "flagA": flag(a) if a else "",
                "home_code": str(m["home"]), "away_code": str(m["away"]),
                "venue": venue, "date": m.get("date"), "played": played}
        if h and a and h in ratings and a in ratings:
            if played:
                hs, as_ = int(m["home_score"]), int(m["away_score"])
                wn = m.get("winner")
                w = h if hs > as_ else a if as_ > hs else (wn if wn in (h, a) else h)
                node["actual"] = f"{hs}-{as_}"
                node["p_home_adv"] = 1.0 if w == h else 0.0
                node["p_away_adv"] = 1.0 if w == a else 0.0
            else:
                mm = ko_matchup(h, a, venue, ratings, params)
                node.update(mm)
                w = h if mm["p_home_adv"] >= mm["p_away_adv"] else a
            win[n], lose[n] = w, (a if w == h else h)
        by_stage.setdefault(stage, []).append(node)
    order = ["r32", "r16", "qf", "sf", "final", "third"]
    champion = win.get(sim.ko_template[-1]["n"]) if sim.ko_template else None
    # the final is the highest-round non-third match
    final_n = next((m["n"] for m in reversed(sim.ko_template) if m["stage"] == "final"), None)
    return {"rounds": [{"stage": s, "matches": by_stage[s]} for s in order if s in by_stage],
            "projected_champion": win.get(final_n), "g1": g1, "g2": g2}


def live_scoreboard(live) -> dict | None:
    """Honest running skill check on matches already played this tournament:
    model RPS vs the uniform baseline, plus how often the model's most-likely
    call landed. Tiny sample — surfaced with that caveat in the UI."""
    if live is None or not len(live):
        return None
    idx = {"H": 0, "D": 1, "A": 2}
    rps_model, rps_unif = [], []
    for r in live.itertuples(index=False):
        o = idx[r.outcome]
        rps_model.append(backtest.rps([r.p_home, r.p_draw, r.p_away], o))
        rps_unif.append(backtest.rps([1 / 3, 1 / 3, 1 / 3], o))
    n = len(rps_model)
    return {
        "n": n,
        "rps_model": round(float(np.mean(rps_model)), 4),
        "rps_uniform": round(float(np.mean(rps_unif)), 4),
        "calls_hit": int(live["fav_hit"].sum()),
        "beats_uniform": float(np.mean(rps_model)) < float(np.mean(rps_unif)),
    }


def build_bundle(*, asof, n_sims, df, groups, schedule, ratings_elo, ratings, values,
                 fixtures, live, adv, market_outright, fixtures_market, fit, blend_info,
                 bt_summary, calibration, calibration_ece, market_beat, sources,
                 betting_backtest=None, value_bets=None, injuries=None, methodology=None,
                 live_odds=None, all_fixtures=None, referees=None, bracket=None):
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
        "p_first": r.get("p_first"), "p_second": r.get("p_second"), "p_qual3": r.get("p_qual3"),
    } for r in adv.to_dict("records")]

    standings = _group_standings(groups, schedule)
    groups_out = {}
    for g, teams in groups.items():
        groups_out[g] = [{
            "team": t, "flag": flag(t), "elo": round(ratings_elo.get(t, 0), 0),
            "value": values.get(t), "p_advance": advm.get(t, {}).get("p_r32"),
            "p_first": advm.get(t, {}).get("p_first"),
            "p_second": advm.get(t, {}).get("p_second"),
            "p_qual3": advm.get(t, {}).get("p_qual3"),
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

    live_map = {}
    if live_odds:
        for m in live_odds.get("matches", []):
            live_map[(m["home"], m["away"])] = m

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
            "odds_compare": odds_compare({**fx, "p_home": fx["p_home"], "p_draw": fx["p_draw"],
                                          "p_away": fx["p_away"]}, live_map.get((H, A))),
            "score_breakdown": _score_breakdown(fx.get("markets")),
            "referee": (referees or {}).get("by_match", {}).get(f"{H}|{A}"),
        })

    # best picks — model's most confident calls, ranked by max outcome prob
    best_picks = []
    for fo in fixtures_out:
        probs = {"主胜": fo["p_home"], "平局": fo["p_draw"], "客胜": fo["p_away"]}
        sel = max(probs, key=probs.get)
        sb = fo.get("score_breakdown") or {}
        topcs = (sb.get("top") or [{}])[0]
        edges = [r["edge"] for r in fo.get("odds_compare", [])]
        best_picks.append({
            "date": fo["date"], "home": fo["home"], "away": fo["away"], "stage": fo["stage"],
            "group": fo.get("group"), "flagH": fo["flagH"], "flagA": fo["flagA"],
            "pick": sel, "pick_p": probs[sel], "p_home": fo["p_home"], "p_draw": fo["p_draw"],
            "p_away": fo["p_away"], "score": topcs.get("score", ""), "score_p": topcs.get("p", 0),
            "lambda_h": fo["lambda_h"], "lambda_a": fo["lambda_a"],
            "narrative": fo["narrative"], "best_edge": max(edges) if edges else None,
        })
    best_picks.sort(key=lambda x: -x["pick_p"])

    live_out = []
    idx3 = {"H": 0, "D": 1, "A": 2}
    if live is not None and len(live):
        for r in live.to_dict("records"):
            live_out.append({
                "n": r.get("n"), "stage": r.get("stage"), "group": r.get("group"),
                "date": r["date"], "home": r["home"], "away": r["away"],
                "flagH": flag(r["home"]), "flagA": flag(r["away"]),
                "actual": r["actual"], "p_home": r["p_home"], "p_draw": r["p_draw"],
                "p_away": r["p_away"], "outcome": r["outcome"], "rps": round(r["rps"], 4),
                "rps_uniform": round(backtest.rps([1 / 3, 1 / 3, 1 / 3], idx3[r["outcome"]]), 4),
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
        "live_scoreboard": live_scoreboard(live),
        "bracket": bracket,
        "credibility": credibility,
        "betting": {"value_bets": value_bets or [], "backtest": betting_backtest,
                    "recommendations": build_recommendations(value_bets)},
        "schedule_full": build_schedule(schedule, all_fixtures),
        "referees": referees or {},
        "best_picks": best_picks,
        "elo_trend": {"teams": [t["team"] for t in leaderboard[:6]],
                      "flags": {t["team"]: t["flag"] for t in leaderboard[:6]},
                      "series": elo_trend(df, [t["team"] for t in leaderboard[:6]])},
        "injuries": inj,
        "methodology": methodology,
        "live_odds": ({"asof": live_odds.get("asof"), "source": live_odds.get("source"),
                       "remaining": live_odds.get("requests_remaining")} if live_odds else None),
    }
