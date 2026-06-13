"""2026-venue climate / altitude adaptation layer.

The core Dixon-Coles model is venue-blind: it drives goal rates off a single
global Elo per team. But the 2026 World Cup is played across a continent with
genuinely different conditions — Mexico City sits at 2240 m, Guadalajara at
1566 m; Houston, Dallas, Monterrey and Miami are brutally hot (and humid) in
June–July. A sea-level Northern-European side parachuted into altitude, or a
cold-climate team into 34 °C humidity, is measurably disadvantaged versus a
side that lives in those conditions.

This module turns that into a small, **transparent, per-match Elo nudge** that
is applied ONLY to 2026 fixtures (never to the historical training data or the
backtest), so the model's validated calibration is untouched. It is a
literature-informed *prior*, not a parameter fitted on this tournament — the
magnitudes are deliberately conservative and fully documented below.

Grounding
---------
* Altitude: McSharry, "Effect of altitude on physiological performance: a
  statistical analysis using results of international football games" (BMJ
  2007) finds a large home-altitude advantage in South-American qualifiers
  (~0.5 GD per 2500 m of altitude *difference* for fly-in visitors). World Cup
  squads acclimatise (arrive ~10+ days early) and play one-offs, so we use a
  fraction of that: ALT_K Elo per 1000 m of *unfamiliar* altitude above a
  500 m grace band, capped at 2500 m.
* Heat/humidity: FIFA's own heat-mitigation protocols (cooling breaks above a
  WBGT threshold) acknowledge a real effect. It is harder to quantify cleanly
  than altitude, so the heat term is smaller and a roof/climate-controlled
  stadium discounts it sharply.

Both terms only ever *subtract* Elo (you are never helped by going somewhere
hard); a team at or below its home conditions gets 0.
"""
from __future__ import annotations

import json
from pathlib import Path

# --- documented magnitudes (Elo points) -------------------------------------
ALT_TOL_M = 500.0       # altitude grace band — below this, no effect
ALT_K = 14.0            # Elo penalty per 1000 m of unfamiliar altitude
ALT_CAP_M = 2500.0      # cap the stress (beyond ~Quito it saturates)
HEAT_K = 22.0           # max heat Elo penalty (severity=1, vulnerability=1)

# heat vulnerability by home-climate class (1 = most vulnerable)
HEAT_VULN = {"cold": 1.0, "temperate": 0.55, "hot_dry": 0.25, "hot_humid": 0.0}


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class Climate:
    def __init__(self, venues: dict, teams: dict):
        self.venues = (venues or {}).get("by_city", {})
        self.teams = (teams or {}).get("by_team", {})

    # ---- physical terms -------------------------------------------------
    def _alt_penalty(self, team: str, venue_alt: float) -> float:
        home = self.teams.get(team, {}).get("home_altitude_m", 0.0)
        stress = _clamp(venue_alt - home - ALT_TOL_M, 0.0, ALT_CAP_M)
        return -ALT_K * stress / 1000.0

    def _heat_severity(self, v: dict) -> float:
        sev = _clamp((v.get("temp_c", 20) - 26.0) / 12.0, 0.0, 1.0)
        sev *= 1.2 if v.get("humid") else 0.85
        if v.get("roof"):
            sev *= 0.4
        return _clamp(sev, 0.0, 1.0)

    def _heat_penalty(self, team: str, severity: float) -> float:
        vuln = HEAT_VULN.get(self.teams.get(team, {}).get("climate", "temperate"), 0.55)
        return -HEAT_K * severity * vuln

    # ---- public ---------------------------------------------------------
    def match_delta(self, home: str, away: str, venue_city: str) -> tuple[float, float]:
        """(Elo delta for home, Elo delta for away) — both <= 0."""
        v = self.venues.get(venue_city)
        if not v:
            return 0.0, 0.0
        alt = v.get("altitude_m", 0.0)
        sev = self._heat_severity(v)
        dh = self._alt_penalty(home, alt) + self._heat_penalty(home, sev)
        da = self._alt_penalty(away, alt) + self._heat_penalty(away, sev)
        return dh, da

    def context(self, home: str, away: str, venue_city: str) -> dict | None:
        """Structured per-match context for the UI (None if no venue data)."""
        v = self.venues.get(venue_city)
        if not v:
            return None
        alt = v.get("altitude_m", 0.0)
        sev = self._heat_severity(v)
        ah, aa = self._alt_penalty(home, alt), self._alt_penalty(away, alt)
        hh, ha = self._heat_penalty(home, sev), self._heat_penalty(away, sev)
        dh, da = ah + hh, aa + ha
        return {
            "venue": venue_city, "stadium": v.get("stadium", ""),
            "altitude_m": alt, "temp_c": v.get("temp_c"),
            "humid": bool(v.get("humid")), "roof": bool(v.get("roof")),
            "alt_home": round(ah, 1), "alt_away": round(aa, 1),
            "heat_home": round(hh, 1), "heat_away": round(ha, 1),
            "heat_severity": round(sev, 2),
            "d_home": round(dh, 1), "d_away": round(da, 1),
            "lean": "home" if dh - da > 4 else ("away" if dh - da < -4 else "even"),
        }


def load(wc_dir: Path) -> Climate | None:
    """Build a Climate from data/wc2026/{venues,team_climate}.json (or None)."""
    vp, tp = Path(wc_dir) / "venues.json", Path(wc_dir) / "team_climate.json"
    if not (vp.exists() and tp.exists()):
        return None
    return Climate(json.loads(vp.read_text(encoding="utf-8")),
                   json.loads(tp.read_text(encoding="utf-8")))
