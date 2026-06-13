"""Data loading for the World Cup prediction pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .names import canon, load_name_map

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
WC = ROOT / "data" / "wc2026"
OUT = ROOT / "outputs"

RESULT_COLS = [
    "date", "home_team", "away_team", "home_score", "away_score",
    "tournament", "city", "country", "neutral",
]


def load_results(start: str = "1950-01-01") -> pd.DataFrame:
    """results.csv (+ supplement with recent matches), canonical names,
    sorted by date, scores as int, neutral as bool."""
    df = pd.read_csv(RAW / "results.csv")
    sup_path = RAW / "results_supplement.csv"
    if sup_path.exists():
        sup = pd.read_csv(sup_path)
        if len(sup):
            df = pd.concat([df[RESULT_COLS], sup[RESULT_COLS]], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["home_score", "away_score"])
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    if df["neutral"].dtype != bool:
        df["neutral"] = df["neutral"].astype(str).str.upper().eq("TRUE")
    nm = load_name_map(WC / "name_map.json")
    for c in ("home_team", "away_team"):
        df[c] = df[c].map(lambda x: canon(x, nm))
    df = df[df["date"] >= pd.Timestamp(start)]
    df = df.drop_duplicates(subset=["date", "home_team", "away_team"], keep="first")
    return df.sort_values("date").reset_index(drop=True)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_wc2026() -> dict:
    """All tournament-side inputs. Missing optional files come back as None."""
    out = {
        "groups": _load_json(WC / "groups.json"),
        "schedule": _load_json(WC / "schedule.json"),
        "format": _load_json(WC / "format.json"),
    }
    for key, fname in [
        ("elo_external", "elo_external.json"),
        ("squad_values", "squad_values.json"),
        ("odds_outright", "odds_outright.json"),
        ("odds_matches", "odds_matches.json"),
    ]:
        p = WC / fname
        out[key] = _load_json(p) if p.exists() else None
    # kickoff times (UTC ISO, keyed by match n) — attached onto the schedule so
    # they flow downstream; the frontend localises them to each viewer's zone.
    kp = WC / "kickoffs.json"
    if kp.exists():
        kicks = _load_json(kp)
        for m in out["schedule"]:
            ko = kicks.get(str(m.get("n")))
            if ko:
                m["kickoff"] = ko
    return out


def wc_team_list(groups: dict) -> list[str]:
    teams = [t for g in sorted(groups) for t in groups[g]]
    assert len(teams) == len(set(teams)), "duplicate team across groups"
    return teams


def wc_played_results(schedule: list) -> pd.DataFrame:
    """Played 2026 World Cup matches in results.csv format, so Elo can update
    in real time as the tournament unfolds — the upstream martj42 feed often
    records WC scores days late (rows sit at NA), which would otherwise leave
    the model blind to results that have already happened."""
    nm = load_name_map(WC / "name_map.json")
    rows = []
    for m in schedule:
        if (m.get("status") != "played" or m.get("home_score") is None
                or m.get("away_score") is None):
            continue
        vc = m.get("venue_country", "")
        rows.append({
            "date": pd.Timestamp(m["date"]),
            "home_team": canon(str(m["home"]), nm), "away_team": canon(str(m["away"]), nm),
            "home_score": int(m["home_score"]), "away_score": int(m["away_score"]),
            "tournament": "FIFA World Cup", "city": m.get("venue_city", ""),
            "country": vc, "neutral": vc not in (str(m["home"]), str(m["away"])),
        })
    return pd.DataFrame(rows, columns=RESULT_COLS)
