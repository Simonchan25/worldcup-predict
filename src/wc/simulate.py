"""Monte Carlo simulation of the 2026 World Cup (48 teams, 12 groups,
top 2 + 8 best thirds -> round of 32).

Already-played matches are taken as fixed; everything else is sampled from
the Dixon-Coles score grids. Knockout draws go to extra time (Poisson at a
third of the 90-minute rate) and then a 50/50 penalty shootout.
"""
from __future__ import annotations

import re
from collections import defaultdict

import numpy as np
import pandas as pd

from . import markets, model

HOSTS = ("United States", "Mexico", "Canada")
KO_ORDER = {"r32": 0, "r16": 1, "qf": 2, "sf": 3, "third": 4, "final": 5}

_RE_RANK = re.compile(r"^([12])([A-L])$")
_RE_THIRD = re.compile(r"^3:([A-L]+|\*)$")
_RE_WL = re.compile(r"^([WL]):?(\d+)$")


class Simulator:
    def __init__(self, schedule, groups, fmt, ratings, params, seed=42):
        self.groups = groups
        self.fmt = fmt or {}
        self.ratings = ratings
        self.params = params
        self.rng = np.random.default_rng(seed)
        self._cache = {}

        self.group_matches = []  # (group, home, away, venue_country, played, hs, as_)
        self.ko_template = []    # dicts sorted by round then match number
        for m in schedule:
            if m["stage"] == "group":
                played = m.get("status") == "played" and m.get("home_score") is not None
                self.group_matches.append((
                    m["group"], m["home"], m["away"], m.get("venue_country", ""),
                    played,
                    int(m["home_score"]) if played else -1,
                    int(m["away_score"]) if played else -1,
                ))
            else:
                self.ko_template.append(m)
        self.ko_template.sort(key=lambda m: (KO_ORDER[m["stage"]], m["n"]))

        # third-place slots in the R32 template: match n -> allowed group letters
        self.third_slots = {}
        self.ko_fixed_side = {}  # match n -> group letter of the non-third side
        all_letters = set(self.groups)
        for m in self.ko_template:
            if m["stage"] != "r32":
                continue
            for side in ("home", "away"):
                code = str(m[side])
                t3 = _RE_THIRD.match(code)
                if t3:
                    letters = t3.group(1)
                    self.third_slots[m["n"]] = (
                        all_letters if letters == "*" else set(letters)
                    )
                else:
                    rk = _RE_RANK.match(code)
                    if rk:
                        self.ko_fixed_side[m["n"]] = rk.group(2)
        combos = (self.fmt.get("third_allocation") or {}).get("combinations") or {}
        self.third_combos = {key: {int(n): g for n, g in v.items()}
                             for key, v in combos.items()}

    # ---- match sampling -------------------------------------------------
    def _grid(self, a, b, home_flag):
        key = (a, b, home_flag)
        if key not in self._cache:
            m, lh, la = model.score_matrix(
                self.ratings[a], self.ratings[b], self.params, home=float(home_flag))
            self._cache[key] = (m.ravel().cumsum(), m.shape[0], lh, la)
        return self._cache[key]

    def _oriented(self, home, away, venue_country):
        """Return (first, second, home_flag, swapped) with any host side first."""
        if away in HOSTS and away == venue_country and home != venue_country:
            return away, home, 1, True
        flag = 1 if (home in HOSTS and home == venue_country) else 0
        return home, away, flag, False

    def sample_match(self, home, away, venue_country):
        a, b, flag, swapped = self._oriented(home, away, venue_country)
        cum, n, _, _ = self._grid(a, b, flag)
        idx = int(np.searchsorted(cum, self.rng.random(), side="right"))
        idx = min(idx, n * n - 1)
        ga_, gb_ = idx // n, idx % n
        return (gb_, ga_) if swapped else (ga_, gb_)

    def play_knockout(self, home, away, venue_country):
        """Returns (winner, loser)."""
        a, b, flag, swapped = self._oriented(home, away, venue_country)
        cum, n, lh, la = self._grid(a, b, flag)
        idx = int(np.searchsorted(cum, self.rng.random(), side="right"))
        idx = min(idx, n * n - 1)
        ga_, gb_ = idx // n, idx % n
        if ga_ == gb_:  # extra time at a third of the 90' rate
            ga_ = self.rng.poisson(lh / 3.0)
            gb_ = self.rng.poisson(la / 3.0)
            if ga_ == gb_:  # penalties: coin flip
                return (a, b) if self.rng.random() < 0.5 else (b, a)
        return (a, b) if ga_ > gb_ else (b, a)

    # ---- group stage ----------------------------------------------------
    @staticmethod
    def _table(teams, results):
        stat = {t: [0, 0, 0] for t in teams}  # pts, gf, ga
        for t1, t2, g1, g2 in results:
            if t1 not in stat or t2 not in stat:
                continue
            stat[t1][1] += g1
            stat[t1][2] += g2
            stat[t2][1] += g2
            stat[t2][2] += g1
            if g1 > g2:
                stat[t1][0] += 3
            elif g2 > g1:
                stat[t2][0] += 3
            else:
                stat[t1][0] += 1
                stat[t2][0] += 1
        return stat

    def rank_group(self, teams, results, _depth=0):
        """FIFA order: points, GD, GF, then head-to-head among the tied set,
        then (proxy for fair play / lots) random."""
        stat = self._table(teams, results)
        key = {t: (-stat[t][0], -(stat[t][1] - stat[t][2]), -stat[t][1]) for t in teams}
        order = sorted(teams, key=lambda t: key[t])
        ranked = []
        i = 0
        while i < len(order):
            j = i
            while j < len(order) and key[order[j]] == key[order[i]]:
                j += 1
            tied = list(order[i:j])
            if len(tied) > 1:
                if _depth >= 2:
                    self.rng.shuffle(tied)
                else:
                    sub = [r for r in results if r[0] in tied and r[1] in tied]
                    tied = self.rank_group(tied, sub, _depth + 1)[0]
            ranked.extend(tied)
            i = j
        return ranked, stat

    # ---- third-place allocation -----------------------------------------
    def allocate_thirds(self, third_by_group):
        """third_by_group: {group letter: team} for the 8 qualified thirds.
        Returns {r32 match n: team}."""
        letters = frozenset(third_by_group)
        combo = self.third_combos.get("".join(sorted(letters)))
        if combo:
            return {n: third_by_group[g] for n, g in combo.items()}

        slots = sorted(self.third_slots.items(),
                       key=lambda kv: len(kv[1] & letters))
        assign = {}
        used = set()

        def bt(k, respect_opp):
            if k == len(slots):
                return True
            n, allowed = slots[k]
            for L in sorted(allowed & letters - used):
                if respect_opp and self.ko_fixed_side.get(n) == L:
                    continue
                assign[n] = L
                used.add(L)
                if bt(k + 1, respect_opp):
                    return True
                used.discard(L)
                del assign[n]
            return False

        if not bt(0, True):
            assign.clear()
            used.clear()
            if not bt(0, False):  # constraints unsatisfiable -> free assignment
                assign.clear()
                free = sorted(letters)
                for (n, _), L in zip(slots, free):
                    assign[n] = L
        return {n: third_by_group[L] for n, L in assign.items()}

    # ---- one tournament -------------------------------------------------
    def simulate_once(self):
        group_results = defaultdict(list)
        venue_of = {}
        for g, h, a, vc, played, hs, as_ in self.group_matches:
            if played:
                group_results[g].append((h, a, hs, as_))
            else:
                gh, ga_ = self.sample_match(h, a, vc)
                group_results[g].append((h, a, gh, ga_))

        pos = {}      # (rank, letter) -> team
        thirds = []   # (team, letter, pts, gd, gf)
        for g in sorted(self.groups):
            ranked, stat = self.rank_group(self.groups[g], group_results[g])
            pos[("1", g)] = ranked[0]
            pos[("2", g)] = ranked[1]
            s = stat[ranked[2]]
            thirds.append((ranked[2], g, s[0], s[1] - s[2], s[1]))

        thirds.sort(key=lambda t: (-t[2], -t[3], -t[4], self.rng.random()))
        third_by_group = {t[1]: t[0] for t in thirds[:8]}
        third_assign = self.allocate_thirds(third_by_group)

        # group-finish bookkeeping (purely observational — no RNG draws here,
        # so champion/advancement counts are unaffected): who topped / placed
        # second / qualified as a best third.
        finishes = {}
        for (rank, g), team in pos.items():
            finishes[team] = "first" if rank == "1" else "second"
        for team in third_by_group.values():
            finishes[team] = "qual3"

        ko_result = {}  # match n -> (winner, loser)

        def resolve(code, n):
            code = str(code)
            rk = _RE_RANK.match(code)
            if rk:
                return pos[(rk.group(1), rk.group(2))]
            if _RE_THIRD.match(code):
                return third_assign[n]
            wl = _RE_WL.match(code)
            if wl:
                w, l = ko_result[int(wl.group(2))]
                return w if wl.group(1) == "W" else l
            if code in self.ratings:  # already a concrete team name
                return code
            raise ValueError(f"unresolvable slot code {code!r} in match {n}")

        reached = {"r32": set(), "r16": set(), "qf": set(), "sf": set(),
                   "final": set()}
        champion = runner_up = None
        for m in self.ko_template:
            n = m["n"]
            if m.get("status") == "played" and str(m["home"]) in self.ratings \
                    and m.get("home_score") is not None:
                h, a = str(m["home"]), str(m["away"])
                hs, as_ = int(m["home_score"]), int(m["away_score"])
                win = m.get("winner")
                if hs != as_:
                    w, l = (h, a) if hs > as_ else (a, h)
                elif win in (h, a):  # decided in ET/pens, recorded by validator
                    w, l = (win, a if win == h else h)
                else:
                    w, l = self.play_knockout(h, a, m.get("venue_country", ""))
            else:
                h = resolve(m["home"], n)
                a = resolve(m["away"], n)
                w, l = self.play_knockout(h, a, m.get("venue_country", ""))
            ko_result[n] = (w, l)
            stage = m["stage"]
            if stage in reached:
                reached[stage].update((h, a))
            if stage == "final":
                champion, runner_up = w, l
        return reached, champion, runner_up, finishes

    # ---- many tournaments -----------------------------------------------
    def run(self, n_sims=10000, progress_every=0):
        teams = [t for g in sorted(self.groups) for t in self.groups[g]]
        counters = {t: defaultdict(int) for t in teams}
        for s in range(n_sims):
            reached, champion, runner_up, finishes = self.simulate_once()
            for stage, members in reached.items():
                for t in members:
                    counters[t][stage] += 1
            counters[champion]["champion"] += 1
            counters[runner_up]["runner_up"] += 1
            for t, code in finishes.items():
                counters[t][code] += 1
            if progress_every and (s + 1) % progress_every == 0:
                print(f"  sim {s + 1}/{n_sims}")
        rows = []
        for t in teams:
            c = counters[t]
            rows.append({
                "team": t,
                "p_r32": c["r32"] / n_sims,
                "p_r16": c["r16"] / n_sims,
                "p_qf": c["qf"] / n_sims,
                "p_sf": c["sf"] / n_sims,
                "p_final": c["final"] / n_sims,
                "p_runner_up": c["runner_up"] / n_sims,
                "p_champion": c["champion"] / n_sims,
                "p_first": c["first"] / n_sims,
                "p_second": c["second"] / n_sims,
                "p_qual3": c["qual3"] / n_sims,
            })
        df = pd.DataFrame(rows).sort_values("p_champion", ascending=False)
        return df.reset_index(drop=True)


def predict_fixtures(schedule, ratings, params, start, end):
    """Model-level (not simulation) predictions for named fixtures in a
    date window: 1X2 probabilities, expected goals, top scorelines."""
    rows = []
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    for m in schedule:
        d = pd.Timestamp(m["date"])
        if not (start <= d <= end):
            continue
        h, a = str(m["home"]), str(m["away"])
        if h not in ratings or a not in ratings:
            continue
        vc = m.get("venue_country", "")
        if a in HOSTS and a == vc:
            grid, la_, lh_ = model.score_matrix(
                ratings[a], ratings[h], params, home=1.0)
            grid = grid.T
            lh, la = lh_, la_
        else:
            flag = 1.0 if (h in HOSTS and h == vc) else 0.0
            grid, lh, la = model.score_matrix(ratings[h], ratings[a], params, home=flag)
        pw, pd_, pl = model.wdl(grid)
        top = model.top_scores(grid, 5)
        rows.append({
            "n": m.get("n"), "date": m["date"], "stage": m["stage"],
            "group": m.get("group"), "home": h, "away": a,
            "status": m.get("status"),
            "home_score": m.get("home_score"), "away_score": m.get("away_score"),
            "elo_h": round(ratings[h], 1), "elo_a": round(ratings[a], 1),
            "lambda_h": round(lh, 3), "lambda_a": round(la, 3),
            "p_home": round(pw, 4), "p_draw": round(pd_, 4), "p_away": round(pl, 4),
            "top_scores": "; ".join(f"{i}-{j} {p:.1%}" for i, j, p in top),
            "markets": markets.all_markets(grid),
        })
    return pd.DataFrame(rows)
