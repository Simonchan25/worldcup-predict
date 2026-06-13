#!/usr/bin/env python3
"""Backtest the model on the 2014/2018/2022 World Cups."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wc import backtest, data, elo  # noqa: E402


def main():
    print("loading results ...")
    df = data.load_results("1950-01-01")
    print(f"  {len(df)} matches {df['date'].min().date()} .. {df['date'].max().date()}")
    print("running Elo ...")
    _, df = elo.run_elo(df)
    print("backtesting 2014/2018/2022 ...")
    per_match, summary = backtest.run_backtest(df)
    out = data.OUT
    out.mkdir(exist_ok=True)
    per_match.to_csv(out / "backtest_matches.csv", index=False)
    summary.to_csv(out / "backtest_summary.csv")
    print(summary.round(4).to_string())


if __name__ == "__main__":
    main()
