"""Team-name canonicalization.

Everything in this project joins on the team names used by the
martj42/international_results dataset (data/raw/results.csv). The data
acquisition workflow writes data/wc2026/name_map.json with any extra
variants it encountered; FALLBACK covers the common FIFA/Transfermarkt
spellings as a safety net.
"""
from __future__ import annotations

import json
from pathlib import Path

FALLBACK = {
    "USA": "United States",
    "United States of America": "United States",
    "Korea Republic": "South Korea",
    "Korea DPR": "North Korea",
    "IR Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "Congo DR": "DR Congo",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Turkiye": "Turkey",
    "UAE": "United Arab Emirates",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Curacao": "Curaçao",
    "Ireland": "Republic of Ireland",
}


def load_name_map(path: str | Path) -> dict:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def canon(name: str, name_map: dict | None = None) -> str:
    name = str(name).strip()
    if name_map and name in name_map:
        return name_map[name]
    return FALLBACK.get(name, name)
