#!/usr/bin/env bash
# Retry failed ACI note-gen + judge for combos where the original run hit
# ollama connection / timeout errors. Runs sequentially (concurrency=1) so
# ollama only handles one model at a time.
#
# Usage: bash scripts/retry_aci_failures.sh
# Logs: /tmp/retry_aci_*.log

set -u
# Resolve repo root from this script's location (scripts/<this-file> → ..)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Source API keys if a .env file exists; otherwise rely on already-exported env vars.
# Expected: ANTHROPIC_API_KEY (for Opus judge), OPENAI_API_KEY (for gpt-5.5).
if [ -f .env ]; then
  set -a; source .env; set +a
fi

LOGDIR=/tmp/retry_aci
mkdir -p "$LOGDIR"

# Step 1: delete all [ERROR] note files so they get regenerated
echo "[$(date)] Step 1: deleting [ERROR] note files..."
DELETED=$(python3 -c "
import json, glob, os, sys
n = 0
for f in glob.glob('scripts/aci_bench_raw/note__*.json'):
    try:
        raw = json.loads(open(f).read()).get('raw', '') or ''
    except Exception:
        continue
    if not raw or raw.startswith('[ERROR]'):
        os.remove(f)
        n += 1
print(n)
")
echo "  deleted $DELETED error note files"

# Step 2: re-run by split, concurrency=1, only the on-device models (cloud
# already complete except gpt-5.5 on valid). The benchmark script's path-exists
# guard skips already-completed (model, case) combos automatically.
ON_DEVICE="qwen3.5:9b qwen3.5:2b qwen3.5:0.8b gemma4:e4b gemma4:e2b medgemma1.5"

# train + test1 + test2 + test3: re-run on-device models
for split in train test1 test2 test3; do
  echo "[$(date)] Step 2.$split: on-device models, concurrency=1..."
  python3 scripts/benchmark_aci.py \
    --split "$split" \
    --models $ON_DEVICE \
    --skip-extract \
    --concurrency 1 \
    > "$LOGDIR/$split.log" 2>&1
  echo "  $split done. Log: $LOGDIR/$split.log"
done

# valid split: gpt-5.5 had OPENAI_API_KEY error, plus on-device tier sparse
echo "[$(date)] Step 2.valid: gpt-5.5 + on-device, concurrency=1..."
python3 scripts/benchmark_aci.py \
  --split valid \
  --models gpt-5.5 $ON_DEVICE \
  --skip-extract \
  --concurrency 1 \
  > "$LOGDIR/valid.log" 2>&1
echo "  valid done. Log: $LOGDIR/valid.log"

echo "[$(date)] All retries complete."
