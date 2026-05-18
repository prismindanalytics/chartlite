#!/usr/bin/env bash
# Sync benchmark code from this repo (emr/) to the public clinical-edge-bench
# repo. Run from emr/ root: bash scripts/sync_to_public.sh [--dry-run]
#
# What this does:
#   - Copies benchmark + aggregator + audit Python scripts
#   - Copies shell scripts (fetch / retry / run)
#   - Copies dashboard frontend (HTML/JS/CSS)
#   - Copies dashboard data JSON (EXCLUDING eka_real_cases.json — Eka transcripts)
#   - Copies dashboard export scripts
#   - Copies docs (METHODOLOGY, MODEL_VERSIONS, BODHI_USAGE, CODE_REVIEW)
#
# What this does NOT do:
#   - Touch BODHI assets (data/bodhi/ in public repo, fetched separately)
#   - Touch Eka real-data (data/eka_real/, fetched separately)
#   - Touch the inline 100 synthetic encounters (already public)
#   - Stage / commit / push (you review and commit yourself in the public repo)
#
# After sync, cd into the public repo and review with `git diff` before pushing.

set -eu
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DST="${PUBLIC_REPO:-$HOME/Documents/GitHub/clinical-edge-bench}"

if [ ! -d "$DST" ]; then
  echo "ERROR: public repo not found at $DST"
  echo "Set PUBLIC_REPO env var or clone first:"
  echo "  git clone https://github.com/prismindanalytics/clinical-edge-bench $DST"
  exit 1
fi

DRY_RUN=""
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN="--dry-run"
  echo "[DRY RUN] No files will be copied."
fi

echo "Source: $SRC"
echo "Dest:   $DST"
echo ""

# 1. Benchmark + aggregator + audit Python files
echo "[1/4] Python scripts..."
for f in benchmark_aci.py benchmark_bodhi.py benchmark_crescenddi.py \
         benchmark_eka_real.py benchmark_pharmacology_mcqa.py \
         benchmark_medical_calculators.py \
         bodhi_triage_audit.py crescenddi_funnel.py \
         aggregate_aci_from_judges.py aggregate_crescenddi_partial.py \
         aggregate_eka_partial.py aggregate_runs.py; do
  rsync -av $DRY_RUN "$SRC/scripts/$f" "$DST/scripts/$f"
done

# 2. Shell scripts (the public repo has its own fetch_bodhi.sh + fetch_eka_real.sh,
#    don't overwrite them)
echo ""
echo "[2/4] Shell scripts (preserving public-only fetch_bodhi.sh, fetch_eka_real.sh)..."
for f in fetch_aci_bench.sh fetch_crescenddi.sh \
         retry_aci_failures.sh retry_qwen3_thinking_fix.sh \
         run_eka_ondevice.sh run_clean_5x.sh deploy_watch.sh; do
  rsync -av $DRY_RUN "$SRC/scripts/$f" "$DST/scripts/$f"
done

# 3. Dashboard
echo ""
echo "[3/4] Dashboard..."
# Frontend (overwrite freely)
for f in index.html app.js style.css; do
  rsync -av $DRY_RUN "$SRC/benchmark_dashboard/public/$f" "$DST/benchmark_dashboard/public/$f"
done
# Data: copy ALL EXCEPT eka_real_cases.json (contains Eka transcripts)
rsync -av $DRY_RUN \
  --exclude="eka_real_cases.json" \
  "$SRC/benchmark_dashboard/public/data/" \
  "$DST/benchmark_dashboard/public/data/"
# Export scripts
rsync -av $DRY_RUN \
  --exclude="__pycache__" \
  "$SRC/benchmark_dashboard/scripts/" \
  "$DST/benchmark_dashboard/scripts/"

# 4. Docs (handle name remapping: METHODOLOGY_ASSESSMENT → METHODOLOGY)
echo ""
echo "[4/4] Docs..."
rsync -av $DRY_RUN "$SRC/benchmark_dashboard/METHODOLOGY_ASSESSMENT.md" "$DST/docs/METHODOLOGY.md"
rsync -av $DRY_RUN "$SRC/benchmark_dashboard/MODEL_VERSIONS.md"        "$DST/docs/MODEL_VERSIONS.md"
rsync -av $DRY_RUN "$SRC/benchmark_dashboard/CODE_REVIEW.md"           "$DST/docs/CODE_REVIEW.md"
# BODHI_USAGE.md lives only in the public repo (Eka-facing); not copied from emr/.

echo ""
echo "Done."
if [ -z "$DRY_RUN" ]; then
  echo ""
  echo "Next:"
  echo "  cd $DST"
  echo "  git status                    # review what changed"
  echo "  git diff                      # detailed review"
  echo "  git add . && git commit -m 'sync: update from emr/ <date>'"
  echo "  git push"
fi
