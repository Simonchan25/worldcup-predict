#!/usr/bin/env bash
# Daily mechanical refresh during the tournament:
#   1. pull the latest international results (martj42 updates live),
#   2. re-run the full pipeline (Elo -> Dixon-Coles -> 50k Monte Carlo ->
#      backtest -> market-beat -> report + web bundle).
#
# This keeps ratings / simulation / the web dashboard current as new
# international matches land. World Cup *played results* and *kickoff times* are
# pulled automatically from ESPN's scoreboard API (scripts/fetch_results.py);
# only brand-new *odds* still come from the the-odds-api fetch below.
#
# Self-terminating: it no-ops once the tournament is over (after 2026-07-19),
# so the scheduler can be left in place and forgotten.
set -uo pipefail

ROOT="/Volumes/thunderbolt/ai/worldcup-predict"
PY="$ROOT/.venv/bin/python"
LOG="$ROOT/outputs/refresh.log"
RESULTS_URL="https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
END_DATE="2026-07-19"

cd "$ROOT" 2>/dev/null || { echo "$(date) repo not reachable (drive unmounted?)" >>"$LOG"; exit 0; }

# Stop running once the World Cup is over.
TODAY="$(date +%Y-%m-%d)"
if [[ "$TODAY" > "$END_DATE" ]]; then
  echo "$(date) tournament over ($TODAY > $END_DATE) — skipping" >>"$LOG"
  exit 0
fi

{
  echo "=== refresh $(date) ==="
  if curl -fsS --max-time 90 "$RESULTS_URL" -o data/raw/results.csv.tmp; then
    mv data/raw/results.csv.tmp data/raw/results.csv
    echo "results.csv refreshed ($(wc -l <data/raw/results.csv) rows)"
  else
    rm -f data/raw/results.csv.tmp
    echo "results.csv download failed — keeping existing"
  fi
  if [[ -f .secrets.local.json ]]; then
    "$PY" scripts/fetch_live_odds.py || echo "live-odds fetch failed — using last odds"
  fi
  # pull played results + kickoff times from ESPN (safe: only ingests completed
  # matches; idempotent). Keeps scores/times current without the manual step.
  "$PY" scripts/fetch_results.py || echo "results fetch failed — keeping existing"
  "$PY" scripts/run_pipeline.py --sims 50000
  echo "=== done $(date) ==="
} >>"$LOG" 2>&1
