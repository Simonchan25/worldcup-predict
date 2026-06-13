#!/usr/bin/env python3
"""Fetch 2026 World Cup results + kickoff times from ESPN's public scoreboard
API and merge them into data/wc2026/{schedule,kickoffs}.json.

This replaces the error-prone manual "type the score in by hand" step (which is
how USA–Paraguay got recorded 3-0 instead of 4-1). It is:
  - safe: only ingests a result when ESPN marks the match completed (state=post);
  - idempotent: re-running changes nothing once data matches;
  - reviewable: prints every change, and --dry-run writes nothing;
  - leak-free by design: it only records what already happened.

Kickoff times (UTC) are backfilled for *every* matched fixture; the frontend
localises them to each viewer's timezone. Wired into refresh.sh so the daily
refresh keeps scores + kickoff times current automatically.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wc import data as wcdata  # noqa: E402
from wc.names import canon, load_name_map  # noqa: E402

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={}"
WINDOW = (date(2026, 6, 11), date(2026, 7, 19))

# ESPN display names -> our canonical names (only the ones that differ)
ESPN_ALIAS = {
    "Czechia": "Czech Republic", "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Türkiye": "Turkey", "Turkiye": "Turkey", "Curacao": "Curaçao",
    "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde", "Korea Republic": "South Korea", "IR Iran": "Iran",
    "USA": "United States", "DR Congo": "DR Congo", "Congo DR": "DR Congo",
}


def _fetch(d: date) -> dict:
    url = ESPN.format(d.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def _cname(name: str, nm: dict) -> str:
    return ESPN_ALIAS.get(name, canon(name, nm))


def _iso(ko: str | None) -> str | None:
    """Normalise ESPN's '2026-06-13T19:00Z' to '...:00Z' (with seconds)."""
    if not ko:
        return None
    return ko[:-1] + ":00Z" if ko.endswith("Z") and ko.count(":") == 1 else ko


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="preview changes, write nothing")
    args = ap.parse_args()

    nm = load_name_map(wcdata.WC / "name_map.json")
    groups = json.loads((wcdata.WC / "groups.json").read_text(encoding="utf-8"))
    teams = {t for v in groups.values() for t in v}
    sched = json.loads((wcdata.WC / "schedule.json").read_text(encoding="utf-8"))
    # match only fixtures whose sides are concrete WC teams (skips KO slot codes)
    by_pair = {frozenset((m["home"], m["away"])): m for m in sched
               if m.get("home") in teams and m.get("away") in teams}
    kp = wcdata.WC / "kickoffs.json"
    kicks = json.loads(kp.read_text(encoding="utf-8")) if kp.exists() else {}

    ko_upd, res_upd, unmatched = 0, [], []
    d = WINDOW[0]
    while d <= WINDOW[1]:
        try:
            payload = _fetch(d)
        except Exception as ex:
            print(f"  fetch failed {d}: {type(ex).__name__} {ex}")
            d += timedelta(days=1)
            continue
        for e in payload.get("events", []):
            comp = e["competitions"][0]
            cs = comp["competitors"]
            h = next(c for c in cs if c["homeAway"] == "home")
            a = next(c for c in cs if c["homeAway"] == "away")
            hn, an = _cname(h["team"]["displayName"], nm), _cname(a["team"]["displayName"], nm)
            m = by_pair.get(frozenset((hn, an)))
            if not m:
                if hn in teams and an in teams:
                    unmatched.append(f"{hn} vs {an} @ {e.get('date')}")
                continue
            iso = _iso(e.get("date"))
            if iso and kicks.get(str(m["n"])) != iso:
                kicks[str(m["n"])] = iso
                ko_upd += 1
            st = comp["status"]["type"]
            if st.get("state") == "post" and st.get("completed"):
                try:
                    hs, as_ = int(h["score"]), int(a["score"])
                except (TypeError, ValueError):
                    continue
                if (hn, an) != (m["home"], m["away"]):   # ESPN orientation differs
                    hs, as_ = as_, hs
                winner = None
                if hs == as_:                            # decided in ET/pens
                    w = next((c for c in cs if c.get("winner")), None)
                    if w:
                        winner = _cname(w["team"]["displayName"], nm)
                changed = (m.get("status") != "played" or m.get("home_score") != hs
                           or m.get("away_score") != as_ or m.get("winner") != winner)
                if changed:
                    res_upd.append((m["n"], f"{m['home']} {hs}-{as_} {m['away']}"
                                    + (f" (pens: {winner})" if winner else ""),
                                    m.get("home_score"), m.get("away_score")))
                    m["status"] = "played"
                    m["home_score"], m["away_score"] = hs, as_
                    if winner:
                        m["winner"] = winner
        d += timedelta(days=1)

    print(f"== kickoff updates: {ko_upd} · result updates: {len(res_upd)} · unmatched: {len(unmatched)} ==")
    for n, desc, oh, oa in res_upd:
        print(f"   result n{n}: {desc}" + (f"  (was {oh}-{oa})" if oh is not None else "  (new)"))
    for u in unmatched[:12]:
        print("   UNMATCHED (check ESPN_ALIAS):", u)

    if args.dry_run:
        print("== dry-run: no files written ==")
        return
    kicks = {k: kicks[k] for k in sorted(kicks, key=int)}
    kp.write_text(json.dumps(kicks, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (wcdata.WC / "schedule.json").write_text(
        json.dumps(sched, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("== wrote schedule.json + kickoffs.json ==")


if __name__ == "__main__":
    main()
