# Workflow: maintaining the public clinical-edge-bench repo

The benchmark code lives here in `emr/` (alongside the ChartLite app). A curated subset is mirrored to the public repo at:

**Public repo:** https://github.com/prismindanalytics/clinical-edge-bench
**Local clone:** `~/Documents/GitHub/clinical-edge-bench`
**Live dashboard:** https://chartlite-bodhi-bench.pages.dev

## How to keep the public repo in sync

Develop normally in `emr/`. When you want to publish updates:

```bash
# 1. Sync — copies benchmark code, dashboard, docs (excludes Eka data)
cd ~/Documents/GitHub/emr
bash scripts/sync_to_public.sh

# 2. Review what changed
cd ~/Documents/GitHub/clinical-edge-bench
git status
git diff

# 3. Commit + push
git add .
git commit -m "sync: <what you changed>"
git push
```

That's it. The sync script is idempotent — running it without changes produces no diffs.

## What the sync script does and doesn't do

**It copies:**
- All 6 benchmark scripts (`benchmark_*.py`)
- All 4 aggregators (`aggregate_*.py`)
- BODHI triage audit, CRESCENDDI eligibility funnel
- Shell scripts (fetch_aci_bench, fetch_crescenddi, retry_*, run_*, deploy_watch)
- Dashboard frontend (`index.html`, `app.js`, `style.css`)
- Dashboard data JSON (excluding `eka_real_cases.json` — contains Eka transcripts)
- Dashboard export scripts
- Methodology + model-versions + code-review docs

**It does NOT touch:**
- `data/bodhi/` in the public repo (BODHI assets, fetched separately by users)
- `data/eka_real/` in the public repo (Eka transcripts, fetched separately)
- `eka_real_cases.json` (excluded by name — contains transcripts)
- The public repo's `BODHI_USAGE.md` (Eka-facing doc, lives only in public repo)
- The public repo's `README.md` (different framing from emr/'s README)
- `fetch_bodhi.sh` / `fetch_eka_real.sh` (public-repo-only helpers)
- Git operations (you review and commit yourself)

## Why path adaptations are dual-layout

Both repos use the same Python files. Path resolution falls back through:

1. `$BODHI_DIR` env var
2. `<repo_root>/data/bodhi/` — public repo layout (after `fetch_bodhi.sh`)
3. `<repo_root>/app/src/main/assets/bodhi/` — ChartLite app layout (already there)

Same pattern for `EKA_REAL_DATA_DIR`. **You can edit the same .py file in either repo without breaking the other.** The sync script just rsyncs them; no sed needed.

## Adding a new benchmark

1. Develop in `emr/scripts/benchmark_<new>.py` mirroring the pattern of `benchmark_pharmacology_mcqa.py` (simplest) or `benchmark_medical_calculators.py` (numerical scoring).
2. Add the export script to `emr/benchmark_dashboard/scripts/export_<new>.py`.
3. Add the dashboard tab in `emr/benchmark_dashboard/public/app.js` + `index.html`.
4. Update `emr/benchmark_dashboard/METHODOLOGY_ASSESSMENT.md` with caveats.
5. Update `emr/scripts/PUBLIC_RELEASE_WORKFLOW.md` (this file) — extend the sync script if your new benchmark touches files outside the standard set.
6. Smoke-test in `emr/`.
7. `bash scripts/sync_to_public.sh` to mirror.
8. cd into `clinical-edge-bench/`, review, commit, push.

## When to bump `MODEL_VERSIONS.md`

Every time you re-run a benchmark with new model handles or against a new data version. The "run window" field at the top should reflect the actual date range of the runs that produced the dashboard's current numbers.

## When the public repo and `emr/` diverge intentionally

The public repo has 4 things that should never sync from `emr/`:
- `README.md` (different framing — public is "Clinical-AI Edge Benchmark"; emr/ is "ChartLite app")
- `LICENSE` (already Apache 2.0 in both, identical)
- `docs/BODHI_USAGE.md` (Eka-facing, public-only)
- `scripts/fetch_bodhi.sh`, `scripts/fetch_eka_real.sh` (public-only helpers)

If you want to update any of these, edit them directly in `clinical-edge-bench/`.

## How to test the public repo in isolation

The public repo should run end-to-end without any reference to `emr/`. To verify:

```bash
cd /tmp
rm -rf clinical-edge-bench-test
git clone https://github.com/prismindanalytics/clinical-edge-bench clinical-edge-bench-test
cd clinical-edge-bench-test
python3 -m pip install -r scripts/requirements.txt
export ANTHROPIC_API_KEY=...
python3 scripts/benchmark_pharmacology_mcqa.py --models claude-haiku --limit 5
```

Should produce 5 question outputs without touching `emr/` at all.

## Cloudflare Pages dashboard

Currently deployed via the existing `deploy_watch.sh` from `emr/`. The Pages project name is `chartlite-bodhi-bench` (sticky for URL preservation). To deploy from the public repo specifically:

```bash
cd ~/Documents/GitHub/clinical-edge-bench
wrangler pages deploy benchmark_dashboard/public \
  --project-name chartlite-bodhi-bench \
  --commit-dirty=true --branch main
```

(Wrangler authentication is shared with the `emr/` deploys — same Cloudflare account.)
