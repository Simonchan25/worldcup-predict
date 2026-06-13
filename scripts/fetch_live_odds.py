#!/usr/bin/env python3
"""Fetch LIVE (and in-play) World Cup odds from the-odds-api.com and write the
tournament odds files. Reads the API key from .secrets.local.json (gitignored).

Emits:
  data/wc2026/odds_live.json      full: per-match 1X2 (consensus + best) + O/U 2.5, outright
  data/wc2026/odds_matches.json   1X2 consensus in the pipeline's existing format
  data/wc2026/odds_outright.json  live outright in the pipeline's existing format

Consensus = median across books (robust to outliers); best = max price (the most
favourable available to a bettor — the right number for value/edge detection).
Cost: ~2 of 500 monthly credits per run (markets=h2h,totals x 1 region).
"""
from __future__ import annotations

import json
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wc.names import canon  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WC = ROOT / "data" / "wc2026"
BASE = "https://api.the-odds-api.com/v4/sports"
REGION = "eu"


def _get(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode()), dict(r.headers)


def _median(xs):
    xs = [x for x in xs if x and x > 1.0]
    return round(statistics.median(xs), 3) if xs else None


def _best(xs):
    xs = [x for x in xs if x and x > 1.0]
    return round(max(xs), 3) if xs else None


def fetch(key: str):
    asof = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ---- match odds: 1X2 (h2h) + totals (O/U) ----
    murl = f"{BASE}/soccer_fifa_world_cup/odds/?apiKey={key}&regions={REGION}&markets=h2h,totals&oddsFormat=decimal&dateFormat=iso"
    raw, hdr = _get(murl)
    matches = []
    for ev in raw:
        home, away = canon(ev["home_team"]), canon(ev["away_team"])
        h, d, a, ov, un = [], [], [], [], []
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk["key"] == "h2h":
                    px = {o["name"]: o["price"] for o in mk["outcomes"]}
                    if ev["home_team"] in px:
                        h.append(px[ev["home_team"]])
                    if ev["away_team"] in px:
                        a.append(px[ev["away_team"]])
                    if "Draw" in px:
                        d.append(px["Draw"])
                elif mk["key"] == "totals":
                    for o in mk["outcomes"]:
                        if abs(o.get("point", 0) - 2.5) < 1e-6:
                            (ov if o["name"] == "Over" else un).append(o["price"])
        rec = {
            "home": home, "away": away, "commence": ev["commence_time"],
            "n_books": len(ev.get("bookmakers", [])),
            "h2h": {"home": _median(h), "draw": _median(d), "away": _median(a)},
            "h2h_best": {"home": _best(h), "draw": _best(d), "away": _best(a)},
        }
        if ov and un:
            rec["totals"] = {"line": 2.5, "over": _median(ov), "under": _median(un)}
        matches.append(rec)

    # ---- outright winner ----
    ourl = f"{BASE}/soccer_fifa_world_cup_winner/odds/?apiKey={key}&regions={REGION}&markets=outrights&oddsFormat=decimal"
    oraw, _ = _get(ourl)
    by_team = {}
    for ev in oraw:
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                for o in mk["outcomes"]:
                    by_team.setdefault(canon(o["name"]), []).append(o["price"])
    outright = {t: _median(v) for t, v in by_team.items() if _median(v)}

    live = {"asof": asof, "source": f"the-odds-api ({REGION}, {len(raw)} 场×~25 家书, 中位数)",
            "requests_remaining": hdr.get("x-requests-remaining"),
            "outright": outright, "matches": matches}
    (WC / "odds_live.json").write_text(json.dumps(live, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- refresh the files the pipeline already consumes ----
    om = [{"date": m["commence"][:10], "home": m["home"], "away": m["away"],
           "home_odds": m["h2h"]["home"], "draw_odds": m["h2h"]["draw"],
           "away_odds": m["h2h"]["away"], "source": "the-odds-api (live consensus)"}
          for m in matches if all(m["h2h"].values())]
    (WC / "odds_matches.json").write_text(json.dumps(om, ensure_ascii=False, indent=1), encoding="utf-8")
    (WC / "odds_outright.json").write_text(json.dumps(
        {"source": "the-odds-api (Betfair Exchange + William Hill, live)", "asof": asof,
         "odds": outright, "note": f"{len(outright)} teams, median across books"},
        ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"live odds: {len(matches)} matches ({sum('totals' in m for m in matches)} with O/U), "
          f"{len(outright)} outright; quota left {hdr.get('x-requests-remaining')}")
    print(f"  1X2 fixtures usable: {len(om)}")


if __name__ == "__main__":
    sec = json.loads((ROOT / ".secrets.local.json").read_text())
    fetch(sec["the_odds_api_key"])
