#!/usr/bin/env bash
# Re-run note-gen for qwen3 models on ACI splits, now with the think:false fix
# in benchmark_aci.py. Sequential, concurrency=1.
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Source API keys from .env if present; otherwise rely on env.
if [ -f .env ]; then
  set -a; source .env; set +a
fi

LOGDIR=/tmp/retry_qwen
mkdir -p "$LOGDIR"

QWEN_MODELS="qwen3.5:9b qwen3.5:2b qwen3.5:0.8b"

for split in train test1 test2 test3 valid; do
  echo "[$(date)] qwen3 retry on $split..."
  python3 scripts/benchmark_aci.py \
    --split "$split" \
    --models $QWEN_MODELS \
    --skip-extract \
    --concurrency 1 \
    > "$LOGDIR/$split.log" 2>&1
  echo "  $split done. Log: $LOGDIR/$split.log"
done

echo "[$(date)] All qwen3 retries complete."
