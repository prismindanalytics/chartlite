#!/usr/bin/env bash
# Single-run benchmark with parallel cloud groups + sequential local.
# Resume-friendly: benchmark_bodhi.py skips encounters whose raw file already exists.
#
# Set RUNS=5 to re-enable the full 5-run sweep after validating single-run results.

set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Source API keys from .env if present; otherwise rely on env.
if [ -f .env ]; then
  set -a; source .env; set +a
fi

ANTHROPIC="claude-opus-4-7 claude-sonnet-4-6 claude-haiku-4-5-20251001"
OPENAI="gpt-5.4 gpt-4.1"
LOCAL="medgemma1.5 qwen3.5:9b qwen3.5:2b qwen3.5:0.8b gemma4:e2b gemma4:e4b"

RUNS=${RUNS:-1}
LOG=/tmp/bodhi_clean5x.log

echo "[$(date)] starting $RUNS-run benchmark (parallel cloud + sequential local)" | tee -a "$LOG"

for RUN in $(seq 1 $RUNS); do
  echo "[$(date)] ===== run$RUN =====" | tee -a "$LOG"

  python3 scripts/benchmark_bodhi.py --models $ANTHROPIC --run-id run$RUN >> "$LOG.anthropic.run$RUN" 2>&1 &
  A_PID=$!
  python3 scripts/benchmark_bodhi.py --models $OPENAI    --run-id run$RUN >> "$LOG.openai.run$RUN"    2>&1 &
  O_PID=$!
  python3 scripts/benchmark_bodhi.py --models $LOCAL     --run-id run$RUN >> "$LOG.local.run$RUN"     2>&1 &
  L_PID=$!

  echo "[$(date)] run$RUN launched: anthropic=$A_PID openai=$O_PID local=$L_PID" | tee -a "$LOG"
  wait $A_PID; echo "[$(date)] run$RUN anthropic done (exit=$?)" | tee -a "$LOG"
  wait $O_PID; echo "[$(date)] run$RUN openai done (exit=$?)" | tee -a "$LOG"
  wait $L_PID; echo "[$(date)] run$RUN local done (exit=$?)" | tee -a "$LOG"
done

echo "[$(date)] rescore + aggregate + judge + export + dashboard refresh" | tee -a "$LOG"
python3 scripts/rescore_raw.py >> "$LOG" 2>&1
python3 scripts/aggregate_runs.py >> "$LOG" 2>&1
python3 scripts/judge_llm.py --concurrency 3 >> "$LOG" 2>&1 || echo "judge skipped" | tee -a "$LOG"
python3 benchmark_dashboard/scripts/export_data.py >> "$LOG" 2>&1
python3 benchmark_dashboard/scripts/export_miss_analysis.py >> "$LOG" 2>&1
python3 benchmark_dashboard/scripts/export_prompts.py >> "$LOG" 2>&1
bash benchmark_dashboard/scripts/refresh.sh >> "$LOG" 2>&1 || true
echo "[$(date)] all done" | tee -a "$LOG"
