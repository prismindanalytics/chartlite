#!/usr/bin/env bash
# Sequentially run pharmacology MCQA + medical calculator benchmarks across
# all 6 on-device models. concurrency=1 per model to avoid ollama contention
# (one ollama model loaded at a time). Logs per-model to /tmp/eka_ondevice/.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Source API keys from .env if present; otherwise rely on env.
if [ -f .env ]; then
  set -a; source .env; set +a
fi

LOGDIR=/tmp/eka_ondevice
mkdir -p "$LOGDIR"

ON_DEVICE="qwen3.5:9b qwen3.5:2b qwen3.5:0.8b gemma4:e4b gemma4:e2b medgemma1.5"

echo "[$(date)] Pharmacology MCQA on-device (sequential per model)..."
for model in $ON_DEVICE; do
  safe=$(echo "$model" | tr ':' '_')
  echo "[$(date)] -> pharm $model"
  python3 scripts/benchmark_pharmacology_mcqa.py \
    --models "$model" \
    --concurrency 1 \
    > "$LOGDIR/pharm_$safe.log" 2>&1
  tail -3 "$LOGDIR/pharm_$safe.log"
done

echo "[$(date)] Medical Calculator Eval on-device (sequential per model)..."
for model in $ON_DEVICE; do
  safe=$(echo "$model" | tr ':' '_')
  echo "[$(date)] -> calc $model"
  python3 scripts/benchmark_medical_calculators.py \
    --models "$model" \
    --concurrency 1 \
    > "$LOGDIR/calc_$safe.log" 2>&1
  tail -3 "$LOGDIR/calc_$safe.log"
done

echo "[$(date)] All Eka on-device runs complete."
