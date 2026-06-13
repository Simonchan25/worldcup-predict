#!/usr/bin/env python3
"""End-to-end pipeline: data -> Elo -> Dixon-Coles fit -> tournament
simulation -> market comparison -> report."""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wc import backtest, data, elo, market, model, report, simulate  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sims", type=int, default=20000)
    ap.add_argument("--value-weight", type=float, default=0.25)
    ap.add_argument("--xi", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--skip-backtest", action="store_true")
    args = ap.parse_args()

    today = pd.Timestamp(date.today())
    out = data.OUT
    out.mkdir(exist_ok=True)

    # 1. history + Elo
    print("== loading results ==")
    df = data.load_results("1950-01-01")
    data_info = (f"{len(df)} 场国际比赛({df['date'].min().date()} 至 "
                 f"{df['date'].max().date()}),来源 martj42/international_results")
    print("  ", data_info)
    ratings_elo, df = elo.run_elo(df)

    # 2. goal model fit
    print("== fitting Dixon-Coles ==")
    fit = model.fit(df, ref_date=today, since="2010-01-01", xi=args.xi)
    print("   params:", [round(v, 4) for v in fit["params"]],
          "converged:", fit["converged"], "n:", fit["n_matches"])
    params = fit["params"]

    # 3. tournament inputs
    wc = data.load_wc2026()
    teams = data.wc_team_list(wc["groups"])
    missing = [t for t in teams if t not in ratings_elo]
    if missing:
        print("   WARNING: no Elo history for", missing, "-> default 1400")
        for t in missing:
            ratings_elo[t] = 1400.0

    values = (wc["squad_values"] or {}).get("values_eur_m", {})
    ratings, blend_info = model.value_blend(
        ratings_elo, {t: values.get(t) for t in teams}, weight=args.value_weight)
    pd.DataFrame({
        "team": teams,
        "elo": [round(ratings_elo[t], 1) for t in teams],
        "value_eur_m": [values.get(t) for t in teams],
        "rating_blended": [round(ratings[t], 1) for t in teams],
    }).sort_values("rating_blended", ascending=False).to_csv(
        out / "ratings.csv", index=False)

    # 4. upcoming fixture predictions (model level)
    fixtures = simulate.predict_fixtures(
        wc["schedule"], ratings, params, today, today + timedelta(days=7))
    fixtures = fixtures[fixtures["status"] != "played"]
    fixtures.to_csv(out / "match_predictions.csv", index=False)
    print(f"== {len(fixtures)} upcoming fixtures predicted ==")

    # 4b. live out-of-sample check: model vs realized on already-played matches
    live = simulate.predict_fixtures(
        wc["schedule"], ratings, params, "2026-06-01", "2026-08-01")
    live = live[live["status"] == "played"].copy()
    if len(live):
        live["actual"] = (live["home_score"].astype(int).astype(str) + "-"
                          + live["away_score"].astype(int).astype(str))
        live["outcome"] = np.where(live["home_score"] > live["away_score"], "H",
                          np.where(live["home_score"] == live["away_score"], "D", "A"))
        live["fav_hit"] = live.apply(lambda r: int(
            (r["outcome"] == "H" and r["p_home"] >= max(r["p_draw"], r["p_away"])) or
            (r["outcome"] == "A" and r["p_away"] >= max(r["p_draw"], r["p_home"])) or
            (r["outcome"] == "D" and r["p_draw"] >= max(r["p_home"], r["p_away"]))), axis=1)
        live["rps"] = live.apply(lambda r: backtest.rps(
            [r["p_home"], r["p_draw"], r["p_away"]],
            {"H": 0, "D": 1, "A": 2}[r["outcome"]]), axis=1)
        live.to_csv(out / "live_eval.csv", index=False)
        print(f"== live check: {len(live)} played, mean model RPS "
              f"{live['rps'].mean():.3f}, favourite called {int(live['fav_hit'].sum())}/{len(live)} ==")

    # 5. tournament simulation
    print(f"== simulating tournament x{args.sims} ==")
    sim = simulate.Simulator(wc["schedule"], wc["groups"], wc["format"],
                             ratings, params, seed=args.seed)
    adv = sim.run(args.sims, progress_every=max(args.sims // 4, 1))
    adv.to_csv(out / "advancement.csv", index=False)

    # 6. market comparison
    market_outright = None
    sources = {}
    oo = wc.get("odds_outright")
    if oo and oo.get("odds"):
        sources["夺冠赔率"] = f"{oo.get('source', '?')}(截至 {oo.get('asof', '?')})"
        imp = market.implied_power({k: v for k, v in oo["odds"].items()})
        rows = []
        for r in adv.itertuples(index=False):
            if r.team in imp:
                rows.append({"team": r.team, "p_model": r.p_champion,
                             "p_market": imp[r.team]})
        market_outright = pd.DataFrame(rows)
        market_outright.to_csv(out / "market_compare_outright.csv", index=False)

    fixtures_market = None
    dropped_odds = []
    om = wc.get("odds_matches")
    if om:
        rows = []
        for o in om:
            try:
                if not market.valid_1x2(o["home_odds"], o["draw_odds"], o["away_odds"]):
                    dropped_odds.append(f"{o.get('home')} vs {o.get('away')}")
                    continue
                p = market.implied_1x2(o["home_odds"], o["draw_odds"], o["away_odds"])
            except (KeyError, TypeError, ZeroDivisionError):
                continue
            rows.append({"date": o["date"], "home": o["home"], "away": o["away"],
                         "mkt_home": p[0], "mkt_draw": p[1], "mkt_away": p[2],
                         "source": o.get("source", "")})
        fixtures_market = pd.DataFrame(rows)
        if len(fixtures_market):
            fixtures_market.to_csv(out / "market_compare_matches.csv", index=False)
            sources["单场赔率"] = f"{len(fixtures_market)} 场, " + \
                str(fixtures_market["source"].mode().iat[0] if len(fixtures_market) else "")
            if dropped_odds:
                sources["单场赔率"] += (f";剔除 {len(dropped_odds)} 场疑似解析错误的赔率"
                                       f"({', '.join(dropped_odds)})")
                print("   dropped implausible odds rows:", dropped_odds)

    if wc.get("elo_external"):
        sources["外部 Elo 对照"] = f"{wc['elo_external'].get('source', '?')}(截至 {wc['elo_external'].get('asof', '?')})"
    if wc.get("squad_values"):
        sources["阵容市值"] = f"{wc['squad_values'].get('source', '?')}(截至 {wc['squad_values'].get('asof', '?')})"

    # 7. backtest + market-beat
    bt_summary = None
    calibration = None
    market_beat = None
    if not args.skip_backtest:
        print("== backtesting 2014/2018/2022 ==")
        per_match, bt_summary, calibration = backtest.run_backtest(df, xi=args.xi)
        per_match.to_csv(out / "backtest_matches.csv", index=False)
        bt_summary.to_csv(out / "backtest_summary.csv")
        if calibration is not None and len(calibration):
            calibration.to_csv(out / "calibration.csv", index=False)
            print(f"   calibration ECE = {backtest.ece(calibration):.4f}")
        print(bt_summary.round(4).to_string())

        hist_path = data.RAW / "historical_odds_acq.json"
        if hist_path.exists():
            from wc import market_backtest  # noqa: E402
            market_beat = market_backtest.market_beat(
                per_match, market_backtest.load_hist(hist_path))
            (out / "market_beat.json").write_text(
                json.dumps(market_beat, ensure_ascii=False, indent=1), encoding="utf-8")
            o = market_beat.get("overall")
            if o:
                print(f"   MARKET-BEAT ({o['n']} bookmaker matches): model RPS "
                      f"{o['rps_model']:.4f} vs market {o['rps_market']:.4f} -> "
                      f"{'MODEL beats market' if o['model_better'] else 'market wins'}")
            for t in market_beat["tournaments"]:
                print(f"     {t['wc']:16} n={t['n']:<3} model {t['rps_model']:.4f} / market {t['rps_market']:.4f}")

    # 8. report + JSON bundle
    ctx = {
        "asof": str(today.date()),
        "n_sims": args.sims,
        "data_info": data_info,
        "fit": fit,
        "blend_info": blend_info,
        "adv": adv,
        "market_outright": (market_outright.sort_values("p_model", ascending=False)
                            if market_outright is not None else None),
        "fixtures": fixtures,
        "fixtures_market": fixtures_market,
        "backtest_summary": bt_summary,
        "calibration": calibration,
        "calibration_ece": backtest.ece(calibration) if calibration is not None else None,
        "market_beat": market_beat,
        "live": live if len(live) else None,
        "sources": sources,
    }
    (out / "report.md").write_text(report.render(ctx), encoding="utf-8")
    bundle = {
        "asof": str(today.date()),
        "fit": fit,
        "blend": blend_info,
        "advancement": adv.to_dict("records"),
        "market_outright": (market_outright.to_dict("records")
                            if market_outright is not None else None),
        "fixtures": fixtures.to_dict("records"),
    }
    (out / "predictions.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")

    # 9. frontend data bundle (with per-match reasoning)
    from wc import webdata  # noqa: E402
    mb_path = out / "market_beat.json"
    market_beat = json.loads(mb_path.read_text(encoding="utf-8")) if mb_path.exists() else None
    web_bundle = webdata.build_bundle(
        asof=str(today.date()), n_sims=args.sims, df=df, groups=wc["groups"],
        schedule=wc["schedule"], ratings_elo=ratings_elo, ratings=ratings, values=values,
        fixtures=fixtures, live=live, adv=adv, market_outright=market_outright,
        fixtures_market=fixtures_market, fit=fit, blend_info=blend_info,
        bt_summary=bt_summary, calibration=calibration,
        calibration_ece=(backtest.ece(calibration) if calibration is not None else None),
        market_beat=market_beat, sources=sources)
    web_dir = data.ROOT / "web"
    web_dir.mkdir(exist_ok=True)
    (web_dir / "data.js").write_text(
        "window.WC_DATA = " + json.dumps(web_bundle, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    print(f"== web bundle: {len(web_bundle['fixtures'])} fixtures, "
          f"{len(web_bundle['leaderboard'])} teams -> web/data.js ==")
    print("== done ==")
    print("report:", out / "report.md")


if __name__ == "__main__":
    main()
