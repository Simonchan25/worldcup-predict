#!/usr/bin/env python3
"""Turn a raw web-acquisition JSON into the tournament-side data files the
pipeline consumes, canonicalizing every team name so all joins line up:

    data/wc2026/odds_outright.json   outright (to-win) decimal odds
    data/wc2026/odds_matches.json    upcoming-fixture 1X2 decimal odds
    data/wc2026/squad_values.json    Transfermarkt squad market values (EUR m)
    data/wc2026/name_map.json        any spelling variants -> canonical

It also patches schedule.json with any match results found in the
acquisition (status -> played, scores filled), matching on team pair in
either orientation. Idempotent: re-running with the same input is a no-op.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wc.names import canon  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WC = ROOT / "data" / "wc2026"


def main(acq_path: str):
    acq = json.loads(Path(acq_path).read_text(encoding="utf-8"))
    groups = json.loads((WC / "groups.json").read_text(encoding="utf-8"))
    canon_teams = {t for g in groups.values() for t in g}

    name_map: dict[str, str] = {}
    unmapped: set[str] = set()

    def cz(name: str) -> str:
        c = canon(name)
        if c != name:
            name_map[name] = c
        if c not in canon_teams:
            unmapped.add(f"{name!r}->{c!r}")
        return c

    # ---- outright odds -------------------------------------------------
    oo = acq["outright"]
    odds = {cz(it["team"]): float(it["decimal_odds"]) for it in oo["items"]}
    (WC / "odds_outright.json").write_text(json.dumps({
        "source": f'{oo.get("bookmaker", "?")} (via web aggregators)',
        "asof": oo.get("asof"),
        "odds": odds,
        "sources": oo.get("sources", []),
        "note": oo.get("coverage", ""),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- match 1X2 odds ------------------------------------------------
    mo = acq["match_odds"]
    matches = [{
        "date": it.get("date"),
        "home": cz(it["home"]), "away": cz(it["away"]),
        "home_odds": float(it["home_odds"]),
        "draw_odds": float(it["draw_odds"]),
        "away_odds": float(it["away_odds"]),
        "source": it.get("bookmaker", ""),
    } for it in mo["items"]]
    (WC / "odds_matches.json").write_text(
        json.dumps(matches, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- squad market values ------------------------------------------
    vv = acq["values"]
    values = {cz(it["team"]): float(it["value_eur_m"])
              for it in vv["items"] if it.get("value_eur_m") is not None}
    (WC / "squad_values.json").write_text(json.dumps({
        "source": "Transfermarkt (via web aggregators)",
        "asof": vv.get("asof"),
        "values_eur_m": values,
        "sources": vv.get("sources", []),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- name map ------------------------------------------------------
    (WC / "name_map.json").write_text(
        json.dumps(name_map, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- patch schedule with finished results --------------------------
    sched = json.loads((WC / "schedule.json").read_text(encoding="utf-8"))
    applied, already = 0, 0
    for r in acq.get("results", {}).get("items", []):
        h, a = cz(r["home"]), cz(r["away"])
        hs, as_ = int(r["home_score"]), int(r["away_score"])
        for m in sched:
            if m.get("stage") != "group":
                continue
            mh, ma = str(m["home"]), str(m["away"])
            if (mh, ma) == (h, a):
                sh, sa = hs, as_
            elif (mh, ma) == (a, h):
                sh, sa = as_, hs        # result reported in opposite orientation
            else:
                continue
            if m.get("status") == "played":
                already += 1
            else:
                applied += 1
            m["status"], m["home_score"], m["away_score"] = "played", sh, sa
            break
    (WC / "schedule.json").write_text(
        json.dumps(sched, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- report --------------------------------------------------------
    print(f"odds_outright : {len(odds)} teams  (bookmaker {oo.get('bookmaker')})")
    print(f"odds_matches  : {len(matches)} fixtures")
    print(f"squad_values  : {len(values)} teams")
    print(f"name_map      : {name_map}")
    print(f"schedule      : {applied} new results applied, {already} already present")
    n_played = sum(m.get("status") == "played" for m in sched if m["stage"] == "group")
    print(f"              : {n_played} group matches now marked played")
    if unmapped:
        print("!! UNMAPPED team names (not in the 48-team draw):", unmapped)
        sys.exit(1)
    print("all team names canonical and within the 48-team draw ✓")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data/raw/acquisition_2026-06-13.json"))
