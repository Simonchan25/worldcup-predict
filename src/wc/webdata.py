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


def head_to_head(df: pd.DataFrame, A: str, B: str, asof, n: int = 6) -> dict | None:
    """Real historical head-to-head between A and B before asof: all-time
    W-D-L from A's perspective, goals, and the last `n` meetings with scores."""
    asof = pd.Timestamp(asof)
    sub = df[(((df["home_team"] == A) & (df["away_team"] == B)) |
              ((df["home_team"] == B) & (df["away_team"] == A))) & (df["date"] < asof)]
    if not len(sub):
        return None
    aw = dw = bw = gfa = gfb = 0
    meetings = []
    for r in sub.itertuples(index=False):
        a_home = r.home_team == A
        ga, gb = (r.home_score, r.away_score) if a_home else (r.away_score, r.home_score)
        gfa += ga; gfb += gb
        aw += ga > gb; dw += ga == gb; bw += ga < gb
        meetings.append({"date": str(pd.Timestamp(r.date).date()),
                         "score": f"{int(ga)}-{int(gb)}", "comp": str(r.tournament),
                         "res": "A" if ga > gb else ("D" if ga == gb else "B")})
    last = meetings[-1]
    recent = meetings[-n:]
    ra = sum(m["res"] == "A" for m in recent)
    rb = sum(m["res"] == "B" for m in recent)
    return {"n": int(len(sub)), "a_wins": int(aw), "draws": int(dw), "b_wins": int(bw),
            "gf_a": int(gfa), "gf_b": int(gfb), "last": last,
            "recent_a": ra, "recent_b": rb, "recent_n": len(recent),
            "recent": list(reversed(recent))}


def match_factors(fx: dict, values: dict, form_h: list, form_a: list, mkt: dict | None,
                  h2h: dict | None = None, inj_h: list | None = None,
                  inj_a: list | None = None) -> dict:
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

    clim = fx.get("climate")
    if clim and (abs(clim["d_home"]) >= 2 or abs(clim["d_away"]) >= 2):
        parts = []
        if clim["altitude_m"] >= 1200:
            parts.append(f"{int(clim['altitude_m'])}m 高原")
        if clim["heat_severity"] >= 0.4:
            parts.append(f"{int(clim['temp_c'])}°C{'湿热' if clim['humid'] else '高温'}"
                         f"{'·有顶棚' if clim['roof'] else ''}")
        if not parts:
            parts.append(f"{int(clim['altitude_m'])}m / {int(clim['temp_c'])}°C")
        worse = H if clim["d_home"] < clim["d_away"] else A
        factors.append({"label": "气候/海拔", "lean": clim["lean"],
                        "detail": f"{'·'.join(parts)} — {worse} 适应偏弱"})

    diverge = None
    if mkt:
        mh, md, ma = mkt["mkt_home"], mkt["mkt_draw"], mkt["mkt_away"]
        d_fav = (ph - mh) if fav == H else (pa - ma)
        diverge = round(100 * d_fav, 1)
        factors.append({"label": "模型 vs 市场", "lean": "home" if d_fav > 0.02 else ("away" if d_fav < -0.02 else "even"),
                        "detail": f"{fav} 模型 {favp:.0%} / 市场 {(mh if fav==H else ma):.0%}"})

    # ---- evidence: explicit, numeric, per-match facts (rendered as a list) ----
    evidence = []
    if h2h:
        if h2h["n"] >= 2:
            evidence.append({"k": "h2h", "t":
                f"历史交手 {h2h['n']} 次：{H} {h2h['a_wins']} 胜 {h2h['draws']} 平 "
                f"{h2h['b_wins']} 负（总比分 {h2h['gf_a']}:{h2h['gf_b']}）"})
        last = h2h["last"]
        won = H if last["res"] == "A" else (A if last["res"] == "B" else None)
        evidence.append({"k": "h2h_last", "t":
            f"最近交手 {last['date']}：{H} {last['score']} {A}"
            + (f"（{won} 胜 · {last['comp']}）" if won else f"（战平 · {last['comp']}）")})
    else:
        evidence.append({"k": "h2h", "t": f"{H} 与 {A} 此前无可考的交手记录，参照系更依赖实力评分"})
    evidence.append({"k": "form", "t":
        f"近况：{H} {form_str(form_h)}（{fpts(form_h)} 分）· {A} {form_str(form_a)}（{fpts(form_a)} 分）"})
    evidence.append({"k": "elo", "t": f"实力评分 Elo {eh:.0f} vs {ea:.0f}（差 {gap:+.0f}）"})
    if vh and va:
        evidence.append({"k": "value", "t": f"阵容总身价 €{vh:.0f}M vs €{va:.0f}M"})
    if inj_h:
        evidence.append({"k": "inj", "t": f"{H} 伤停/存疑：" + "、".join(x.get("player", "") for x in inj_h[:3])})
    if inj_a:
        evidence.append({"k": "inj", "t": f"{A} 伤停/存疑：" + "、".join(x.get("player", "") for x in inj_a[:3])})
    if clim and abs(clim["d_home"] - clim["d_away"]) >= 4:
        net = clim["d_home"] - clim["d_away"]
        adv = H if net > 0 else A
        loc = (f"{int(clim['altitude_m'])}m 高原" if clim["altitude_m"] >= 1200
               else f"{int(clim['temp_c'])}°C {'湿热' if clim['humid'] else '高温'}")
        evidence.append({"k": "climate", "t":
            f"{loc}（{clim['venue']}）：{adv} 更适应（净 {abs(net):.0f} Elo）"})
    mp_fav = None
    if diverge is not None:
        mp_fav = mkt["mkt_home"] if fav == H else mkt["mkt_away"]
        evidence.append({"k": "market", "t":
            f"市场对 {fav} 隐含 {mp_fav:.0%}，模型 {favp:.0%}（差 {diverge:+.1f}pp）"})

    def _gavg(f):
        return (sum(x["gf"] for x in f) / len(f), sum(x["ga"] for x in f) / len(f)) if f else None
    gh_, ga_ = _gavg(form_h), _gavg(form_a)
    if gh_ and ga_:
        evidence.append({"k": "goals", "t":
            f"近期攻防：{H} 场均进 {gh_[0]:.1f}/失 {gh_[1]:.1f} · {A} 场均进 {ga_[0]:.1f}/失 {ga_[1]:.1f}"})
    # Elo-implied (paper) win prob for the favourite — a cross-check on the DC model
    elo_adv = gap if fav == H else -gap
    elo_p = 1.0 / (1.0 + 10 ** (-elo_adv / 400.0))
    evidence.append({"k": "elo", "t":
        f"Elo 纸面胜率（不计平局）≈ {fav} {elo_p:.0%}；模型（含平局/主场/状态）给 {favp:.0%}"})
    pick_o = max(("home", "draw", "away"), key=lambda k: {"home": ph, "draw": pdr, "away": pa}[k])
    sb_local = _score_breakdown(fx.get("markets"))
    pred_score = (((sb_local.get("by_result") or {}).get(pick_o)
                   or (sb_local.get("top") or [{}])[0]) or {}).get("score", "")

    # ---- narrative: a structured, evidence-backed argument ----
    conf = "强烈看好" if favp >= 0.62 else ("看好" if favp >= 0.45 else "略偏向")
    bits = [f"模型{conf} **{fav}**（胜率 {favp:.0%}；预期进球 {lh:.1f}–{la:.1f}，单一最可能比分 {pred_score}）。"]
    why = []
    if abs(gap) >= 100:
        why.append(f"{(H if gap>0 else A)} 实力评分高 {abs(gap):.0f} 分（Elo 纸面胜率约 {elo_p:.0%}）")
    if vh and va and max(vh, va) / max(min(vh, va), 1) >= 2:
        rich = H if vh > va else A
        why.append(f"{rich} 阵容身价约为对手 {max(vh, va) / max(min(vh, va), 1):.1f} 倍（€{max(vh, va):.0f}M vs €{min(vh, va):.0f}M）")
    if clim and abs(clim["d_home"] - clim["d_away"]) >= 8:
        net = clim["d_home"] - clim["d_away"]
        why.append(f"{'高原' if clim['altitude_m'] >= 1200 else '湿热高温'}环境利好 {(H if net>0 else A)}（气候净 {abs(net):.0f} Elo）")
    if why:
        bits.append("核心支撑：" + "；".join(why[:2]) + "。")
    if h2h and h2h["n"] >= 3:
        dom = h2h["a_wins"] - h2h["b_wins"]
        tail = (f"，{(H if dom>0 else A)} 略占上风" if abs(dom) >= 2 else "，互有胜负")
        bits.append(f"历史交手 {H} {h2h['a_wins']}-{h2h['draws']}-{h2h['b_wins']}"
                    f"（最近 {h2h['last']['score']}，{h2h['last']['date']}）{tail}。")
    elif h2h is None:
        bits.append("两队几乎无交手史，故判断权重落在实力评分与近期状态、而非历史心理优势。")
    caveats = []
    if inj_h:
        caveats.append(f"{H} {inj_h[0].get('player', '')} 伤停存疑")
    if inj_a:
        caveats.append(f"{A} {inj_a[0].get('player', '')} 伤停存疑")
    if abs(gap) < 80:
        caveats.append("两队实力接近")
    if 0.33 <= favp <= 0.42:
        caveats.append("无明显热门、平局概率不低")
    if caveats:
        bits.append("不确定性：" + "、".join(caveats[:3]) + "。")
    if diverge is not None and abs(diverge) >= 3:
        bits.append(f"市场给 {fav} {mp_fav:.0%}、比模型{'高' if diverge < 0 else '低'} {abs(diverge):.0f}pp——"
                    + ("市场更看重其纸面实力，模型因上述不确定性更保守。" if diverge < 0
                       else "模型认为市场低估了它，是值得留意的分歧点。"))
    elif mkt:
        bits.append("模型与市场基本一致，无显著分歧。")
    return {"factors": factors, "narrative": " ".join(bits), "diverge": diverge,
            "evidence": evidence, "h2h": h2h}


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


def smart_bets(mk: dict, oc_rows: list | None) -> dict | None:
    """Per-match betting suggestions derived from the model's full market set
    + whatever live book odds we have. Returns:
      safest  — highest model hit-rate single pick (odds in a sane 1.25–4 band)
      value   — highest-EV pick *among book-priced* selections (honest: often ≤0)
      basket  — smallest set of correct scores covering ≥50% (not just one score)
      combo   — a same-game 2-leg ticket whose JOINT probability is summed from
                the score grid (correct correlation), priced at book odds×book odds
    """
    if not mk:
        return None
    ocm = {(r["market"], r["sel"]): r for r in (oc_rows or [])}
    plays = []

    def add(market, sel, p, bookrow=None):
        book = bookrow.get("book") if bookrow else None
        odds = float(book) if book else round(1.0 / max(p, 1e-6), 2)
        plays.append({"market": market, "sel": sel, "p": round(float(p), 4),
                      "odds": round(odds, 2), "ev": round(float(p) * odds - 1, 3),
                      "book": bool(book)})

    x = mk.get("1x2", {})
    add("胜平负", "主胜", x.get("home", 0), ocm.get(("胜平负", "主胜")))
    add("胜平负", "平局", x.get("draw", 0), ocm.get(("胜平负", "平局")))
    add("胜平负", "客胜", x.get("away", 0), ocm.get(("胜平负", "客胜")))
    dc = mk.get("double_chance", {})
    add("双重机会", "主胜或平", dc.get("1X", 0))
    add("双重机会", "平或客胜", dc.get("X2", 0))
    add("双重机会", "不平局", dc.get("12", 0))
    for ln in ("1.5", "2.5", "3.5"):
        ou = mk.get("over_under", {}).get(ln, {})
        add("进球", "大 " + ln, ou.get("over", 0), ocm.get(("进球大小", "大 " + ln)))
        add("进球", "小 " + ln, ou.get("under", 0), ocm.get(("进球大小", "小 " + ln)))
    by = mk.get("btts", {})
    add("双方进球", "是", by.get("yes", 0))
    add("双方进球", "否", by.get("no", 0))
    for ln, d in (mk.get("ah", {}) or {}).items():
        if d.get("p_home", 0) > 0.03:
            add("亚盘", f"主 {ln}", d["p_home"])
        if d.get("p_away", 0) > 0.03:
            add("亚盘", f"客 {ln}", d["p_away"])

    safe_cand = [p for p in plays if 1.25 <= p["odds"] <= 4.0]
    safest = max(safe_cand or plays, key=lambda p: p["p"])
    bookp = [p for p in plays if p["book"]]
    value = max(bookp, key=lambda p: p["ev"]) if bookp else None

    cs = sorted(mk.get("correct_score", []) or [], key=lambda c: -c["p"])
    scores, cum = [], 0.0
    for c in cs:
        scores.append(c["score"]); cum += c["p"]
        if cum >= 0.5 or len(scores) >= 4:
            break
    basket = {"scores": scores, "hit": round(cum, 4),
              "fair": round(1.0 / max(cum, 1e-6), 2)} if scores else None

    combo = None
    grid = mk.get("grid")
    if grid and x:
        fav = "主胜" if x.get("home", 0) >= x.get("away", 0) else "客胜"
        ou25 = mk.get("over_under", {}).get("2.5", {})
        gl = "大 2.5" if ou25.get("over", 0) >= ou25.get("under", 0) else "小 2.5"
        jp = 0.0
        for i, row in enumerate(grid):
            for j, pij in enumerate(row):
                res_ok = (i > j) if fav == "主胜" else (j > i)
                gl_ok = (i + j >= 3) if gl == "大 2.5" else (i + j <= 2)
                if res_ok and gl_ok:
                    jp += pij
        ra, rb = ocm.get(("胜平负", fav)), ocm.get(("进球大小", gl))
        pa = x.get("home", 0) if fav == "主胜" else x.get("away", 0)
        pb = ou25.get("over", 0) if gl == "大 2.5" else ou25.get("under", 0)
        oa = float(ra["book"]) if ra and ra.get("book") else round(1.0 / max(pa, 1e-6), 2)
        ob = float(rb["book"]) if rb and rb.get("book") else round(1.0 / max(pb, 1e-6), 2)
        codds = round(oa * ob, 2)
        combo = {"legs": [fav, gl], "p": round(jp, 4), "odds": codds,
                 "ev": round(jp * codds - 1, 3),
                 "book": bool(ra and ra.get("book") and rb and rb.get("book"))}
    return {"safest": safest, "value": value, "basket": basket, "combo": combo}


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
        e = {"n": n, "date": m.get("date"), "kickoff": m.get("kickoff"),
             "stage": m.get("stage"), "group": m.get("group"),
             "venue": m.get("venue_city") or m.get("venue_country", ""),
             "status": m.get("status", "scheduled"),
             "home": home, "away": away, "flagH": flag(home) if home in FLAGS else "",
             "flagA": flag(away) if away in FLAGS else "", "ko_slot": ko_slot}
        if m.get("status") == "played" and m.get("home_score") is not None:
            e["actual"] = f"{int(m['home_score'])}-{int(m['away_score'])}"
            e["actual_outcome"] = ("home" if m["home_score"] > m["away_score"]
                                   else "draw" if m["home_score"] == m["away_score"] else "away")
        p = pred.get(n)
        if p and p.get("home") in FLAGS and p.get("away") in FLAGS:
            sb = _score_breakdown(p.get("markets"))
            probs = {"home": p["p_home"], "draw": p["p_draw"], "away": p["p_away"]}
            pick = max(probs, key=probs.get)
            # show the most-likely scoreline *consistent with the pick* (a
            # favourite's single likeliest exact score, not the global modal
            # which is often a low draw) — fixes "everything shows 1-1".
            byr = (sb.get("by_result") or {}).get(pick) or (sb.get("top") or [{}])[0]
            e.update(home=p["home"], away=p["away"], flagH=flag(p["home"]), flagA=flag(p["away"]))
            e["pred"] = {"p_home": p["p_home"], "p_draw": p["p_draw"], "p_away": p["p_away"],
                         "pick": pick, "pick_p": probs[pick], "score": (byr or {}).get("score", ""),
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


def ko_matchup(home, away, venue, ratings, params, venue_city=None, climate=None,
               max_goals: int = 10) -> dict:
    """Model probabilities for a knockout tie between two concrete teams,
    resolved exactly the way the simulator does: regulation from the
    Dixon-Coles grid, a draw goes to extra time (independent Poisson at a third
    of the 90' rate) and then a 50/50 shootout, plus the same 2026 venue/
    altitude adaptation nudge the simulator uses. Returns home/away advance
    probabilities plus the most-likely regulation scoreline."""
    dh, da = (climate.match_delta(home, away, venue_city)
              if (climate and venue_city) else (0.0, 0.0))
    swapped = away in HOSTS and away == venue and home != venue
    if swapped:
        a, b, flag, d_a, d_b = away, home, 1, da, dh
    else:
        a, b, d_a, d_b = home, away, dh, da
        flag = 1 if (home in HOSTS and home == venue) else 0
    m, lh, la = model.score_matrix(ratings[a] + d_a, ratings[b] + d_b, params,
                                   home=float(flag))
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
                mm = ko_matchup(h, a, venue, ratings, params,
                                venue_city=m.get("venue_city"),
                                climate=getattr(sim, "climate", None))
                node.update(mm)
                w = h if mm["p_home_adv"] >= mm["p_away_adv"] else a
            win[n], lose[n] = w, (a if w == h else h)
        by_stage.setdefault(stage, []).append(node)
    order = ["r32", "r16", "qf", "sf", "final", "third"]
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
    rps_model, rps_unif, scores_hit = [], [], 0
    for r in live.itertuples(index=False):
        o = idx[r.outcome]
        rps_model.append(backtest.rps([r.p_home, r.p_draw, r.p_away], o))
        rps_unif.append(backtest.rps([1 / 3, 1 / 3, 1 / 3], o))
        if live_pred_score(r._asdict()) == getattr(r, "actual", None):
            scores_hit += 1
    n = len(rps_model)
    return {
        "n": n,
        "rps_model": round(float(np.mean(rps_model)), 4),
        "rps_uniform": round(float(np.mean(rps_unif)), 4),
        "calls_hit": int(live["fav_hit"].sum()),
        "scores_hit": scores_hit,
        "beats_uniform": float(np.mean(rps_model)) < float(np.mean(rps_unif)),
    }


def live_pred_score(r: dict) -> str:
    """Pick-consistent most-likely scoreline for a (played or upcoming) row."""
    sb = _score_breakdown(r.get("markets"))
    probs = {"home": r.get("p_home", 0), "draw": r.get("p_draw", 0), "away": r.get("p_away", 0)}
    pick = max(probs, key=probs.get)
    return (((sb.get("by_result") or {}).get(pick) or (sb.get("top") or [{}])[0]) or {}).get("score", "")


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

    inj_map = (injuries or {}).get("by_team", {}) if isinstance(injuries, dict) else {}

    def enrich(fx):
        """Full per-match record: probabilities, drivers + narrative, derived
        markets, live-odds comparison and best plays — everything the
        click-through detail view needs for one match."""
        H, A = fx["home"], fx["away"]
        mkt = fmkt.get((H, A))
        meta = match_factors(fx, values, form(H), form(A), mkt,
                             h2h=head_to_head(df, H, A, asof),
                             inj_h=inj_map.get(H), inj_a=inj_map.get(A))
        ocmp = odds_compare({**fx}, live_map.get((H, A)))
        return {
            "n": fx.get("n"), "date": fx["date"],
            "kickoff": fx.get("kickoff") if isinstance(fx.get("kickoff"), str) else None,
            "group": fx.get("group"), "stage": fx.get("stage"), "status": fx.get("status"),
            "home": H, "away": A, "flagH": flag(H), "flagA": flag(A),
            "p_home": fx["p_home"], "p_draw": fx["p_draw"], "p_away": fx["p_away"],
            "lambda_h": fx["lambda_h"], "lambda_a": fx["lambda_a"],
            "elo_h": round(float(fx["elo_h"])), "elo_a": round(float(fx["elo_a"])),
            "top_scores": _top_scores_list(fx.get("top_scores", "")),
            "market": ({"h": mkt["mkt_home"], "d": mkt["mkt_draw"], "a": mkt["mkt_away"],
                        "source": mkt.get("source", "")} if mkt else None),
            "form_h": form(H), "form_a": form(A),
            "factors": meta["factors"], "narrative": meta["narrative"], "diverge": meta["diverge"],
            "evidence": meta.get("evidence", []), "h2h": meta.get("h2h"),
            "markets": fx.get("markets"),
            "odds_compare": ocmp,
            "smart_bets": smart_bets(fx.get("markets"), ocmp),
            "score_breakdown": _score_breakdown(fx.get("markets")),
            "referee": (referees or {}).get("by_match", {}).get(f"{H}|{A}"),
            "climate": fx.get("climate"), "venue_city": fx.get("venue_city"),
        }

    fixtures_out = [enrich(fx) for fx in fixtures.to_dict("records")]
    # rich detail for EVERY OTHER known-team match (not just the next 7 days),
    # so the click-through detail view works for any group fixture; the upcoming
    # set already lives in fixtures_out, so we only add the rest here.
    upcoming_ns = {fo["n"] for fo in fixtures_out}
    match_details = {}
    if all_fixtures is not None:
        for fx in all_fixtures.to_dict("records"):
            n = fx.get("n")
            if (fx.get("home") in FLAGS and fx.get("away") in FLAGS
                    and n not in upcoming_ns and n not in match_details):
                match_details[n] = enrich(fx)

    # best picks — model's most confident calls, ranked by max outcome prob
    best_picks = []
    for fo in fixtures_out:
        probs = {"主胜": fo["p_home"], "平局": fo["p_draw"], "客胜": fo["p_away"]}
        sel = max(probs, key=probs.get)
        sb = fo.get("score_breakdown") or {}
        # scoreline consistent with the pick (not the global modal draw)
        key = {"主胜": "home", "平局": "draw", "客胜": "away"}[sel]
        topcs = (sb.get("by_result") or {}).get(key) or (sb.get("top") or [{}])[0]
        edges = [r["edge"] for r in fo.get("odds_compare", [])]
        best_picks.append({
            "n": fo.get("n"),
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
            pscore = live_pred_score(r)
            live_out.append({
                "n": r.get("n"), "stage": r.get("stage"), "group": r.get("group"),
                "date": r["date"],
                "kickoff": r.get("kickoff") if isinstance(r.get("kickoff"), str) else None,
                "home": r["home"], "away": r["away"],
                "flagH": flag(r["home"]), "flagA": flag(r["away"]),
                "actual": r["actual"], "p_home": r["p_home"], "p_draw": r["p_draw"],
                "p_away": r["p_away"], "outcome": r["outcome"], "rps": round(r["rps"], 4),
                "rps_uniform": round(backtest.rps([1 / 3, 1 / 3, 1 / 3], idx3[r["outcome"]]), 4),
                "fav_hit": int(r["fav_hit"]),
                "pred_score": pscore, "score_hit": int(pscore == r["actual"]),
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
        "match_details": match_details,
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
