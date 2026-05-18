#!/usr/bin/env bash
# Re-export dashboard data + redeploy to Cloudflare Pages every ~20 min while
# the benchmark runs. Kill with Ctrl-C or `pkill -f deploy_watch` when done.

set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

INTERVAL=${INTERVAL:-1200}    # seconds between deploys (default 20 min)
PROJECT=${PROJECT:-chartlite-bodhi-bench}

while true; do
  echo "[$(date)] re-export + deploy"
  python3 benchmark_dashboard/scripts/export_data.py 2>&1 | tail -5
  # Optional derived files — best-effort
  python3 benchmark_dashboard/scripts/export_miss_analysis.py 2>&1 | tail -2 || true
  python3 benchmark_dashboard/scripts/export_normalization.py 2>&1 | tail -2 || true
  wrangler pages deploy benchmark_dashboard/public \
    --project-name=$PROJECT --commit-dirty=true 2>&1 | grep -E "(Success|Deployment|pages.dev)" | tail -3
  echo "[$(date)] sleep ${INTERVAL}s"
  sleep $INTERVAL
done
