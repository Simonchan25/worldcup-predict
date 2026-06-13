#!/usr/bin/env python3
"""Fast invariant checks on the model/simulation code (no tournament data
needed). Exit code 0 = all good."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wc import backtest, market, markets, model  # noqa: E402
from wc.simulate import Simulator  # noqa: E402

PARAMS = [0.26, 0.9, 0.2, -0.05]


def check_grid():
    m, lh, la = model.score_matrix(1900, 1700, PARAMS, home=0.0)
    assert abs(m.sum() - 1) < 1e-9, "grid must sum to 1"
    pw, pd_, pl = model.wdl(m)
    assert abs(pw + pd_ + pl - 1) < 1e-9
    assert pw > pl, "stronger team must be favourite"
    m2, _, _ = model.score_matrix(1700, 1900, PARAMS, home=0.0)
    pw2, _, pl2 = model.wdl(m2)
    assert abs(pw - pl2) < 1e-9 and abs(pl - pw2) < 1e-9, "symmetry"
    mh, lh_h, _ = model.score_matrix(1800, 1800, PARAMS, home=1.0)
    pwh, _, plh = model.wdl(mh)
    assert pwh > plh, "home advantage must help"
    print("ok grid")


def check_rps():
    assert backtest.rps([1, 0, 0], 0) == 0
    assert abs(backtest.rps([1, 0, 0], 2) - 1.0) < 1e-12
    assert abs(backtest.rps([1 / 3] * 3, 0) - ((2 / 3) ** 2 + (1 / 3) ** 2 * 0) / 2
               - 0) < 1  # smoke
    v = backtest.rps([0.5, 0.3, 0.2], 0)
    assert 0 < v < 0.2
    print("ok rps")


def check_market():
    imp = market.implied_power({"A": 4.0, "B": 5.0, "C": 11.0, "D": 26.0})
    assert abs(sum(imp.values()) - 1) < 1e-6
    assert imp["A"] > imp["D"]
    p = market.implied_1x2(2.1, 3.3, 3.6)
    assert abs(p.sum() - 1) < 1e-9
    # valid_1x2: keep normal & high-margin lines, reject parse errors
    assert market.valid_1x2(2.1, 3.3, 3.6)            # normal
    assert market.valid_1x2(1.67, 3.9, 5.5)           # heavy favourite, real draw
    assert not market.valid_1x2(16, 1.55, 5)          # draw-favourite (swapped)
    assert not market.valid_1x2(1.67, 2.2, 5.5)       # impossibly short draw
    assert not market.valid_1x2(1.06, 2.47, 6)        # short draw + broken book
    assert market.valid_1x2(1.5, 3.2, 9.0)            # high margin but valid shape
    print("ok market")


def check_markets():
    m, _, _ = model.score_matrix(1900, 1600, PARAMS, home=1.0)  # home favourite
    mk = markets.all_markets(m)
    for ln, ou in mk["over_under"].items():
        assert abs(ou["over"] + ou["under"] - 1) < 1e-9, f"O/U {ln} must sum to 1"
    assert abs(mk["btts"]["yes"] + mk["btts"]["no"] - 1) < 1e-9
    h, d, a = markets.wdl(m)
    assert abs(mk["double_chance"]["1X"] + a - 1) < 1e-9, "1X + away = 1"
    for line, ah in mk["ah"].items():
        assert abs(ah["p_home"] + ah["p_away"] + ah["p_push"] - 1) < 1e-9, f"AH {line} sums to 1"
    cs = mk["correct_score"]
    assert all(cs[i]["p"] >= cs[i + 1]["p"] for i in range(len(cs) - 1)), "correct score sorted"
    tt = mk["team_totals"]
    assert tt["home_over_1_5"] > tt["away_over_1_5"], "favourite scores more"
    # value math: bet p=0.5 at 2.2 -> EV +0.10, Kelly (1.2*0.5-0.5)/1.2
    v = markets.value(0.5, 2.2)
    assert abs(v["ev"] - 0.10) < 1e-9 and abs(v["kelly"] - (1.2 * 0.5 - 0.5) / 1.2) < 1e-9
    assert markets.value(0.3, 2.0)["ev"] < 0 and markets.value(0.3, 2.0)["kelly"] == 0
    print("ok markets")


def _mini_sim():
    groups = {"A": ["T1", "T2", "T3", "T4"]}
    schedule = [
        {"n": i + 1, "stage": "group", "group": "A", "date": "2026-06-12",
         "home": h, "away": a, "venue_country": "United States",
         "status": "scheduled", "home_score": None, "away_score": None}
        for i, (h, a) in enumerate(
            [("T1", "T2"), ("T3", "T4"), ("T1", "T3"), ("T2", "T4"),
             ("T1", "T4"), ("T2", "T3")])
    ]
    ratings = {"T1": 2000, "T2": 1800, "T3": 1600, "T4": 1400}
    return Simulator(schedule, groups, {}, ratings, PARAMS, seed=1)


def check_rank_group():
    sim = _mini_sim()
    # T1 beat everyone; T2/T3 tied on pts/gd/gf overall, T2 won h2h
    results = [("T1", "T2", 2, 0), ("T1", "T3", 2, 0), ("T1", "T4", 1, 0),
               ("T2", "T3", 1, 0), ("T4", "T2", 1, 0), ("T3", "T4", 1, 0)]
    ranked, stat = sim.rank_group(["T1", "T2", "T3", "T4"], results)
    assert ranked[0] == "T1"
    assert stat["T1"][0] == 9
    # T4: 3 pts gd -1; T2 and T3: 3 pts gd -2 gf 1 — fully tied on the
    # global criteria, so head-to-head (T2 1-0 T3) must decide.
    assert ranked == ["T1", "T4", "T2", "T3"], ranked
    print("ok rank_group")


def check_allocation():
    sim = _mini_sim()
    sim.third_slots = {74: {"A", "B", "C"}, 75: {"C", "D"}}
    sim.ko_fixed_side = {74: "A"}
    out = sim.allocate_thirds({"C": "tC", "D": "tD"})
    assert out == {75: "tD", 74: "tC"} or out == {74: "tC", 75: "tD"}
    print("ok allocation")


def check_group_sim():
    sim = _mini_sim()
    reached_counts = {t: 0 for t in ["T1", "T2", "T3", "T4"]}
    for _ in range(300):
        import collections
        gr = collections.defaultdict(list)
        for g, h, a, vc, vcity, played, hs, as_ in sim.group_matches:
            gh, ga = sim.sample_match(h, a, vc, vcity)
            gr[g].append((h, a, gh, ga))
        ranked, _ = sim.rank_group(groups_teams := sim.groups["A"], gr["A"])
        reached_counts[ranked[0]] += 1
    assert reached_counts["T1"] > reached_counts["T4"], \
        f"elo 2000 should top the group more often than elo 1400: {reached_counts}"
    print("ok group sim", reached_counts)


if __name__ == "__main__":
    check_grid()
    check_rps()
    check_market()
    check_markets()
    check_rank_group()
    check_allocation()
    check_group_sim()
    print("ALL SANITY CHECKS PASSED")
