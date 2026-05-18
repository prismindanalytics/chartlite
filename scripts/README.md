# Benchmark scripts — reproduction guide

Reproducibility entry point for the benchmark suite at https://benchmark.chartlite.health.

License: Apache 2.0. Methodology: [`../docs/METHODOLOGY.md`](../docs/METHODOLOGY.md). Model versions: [`../docs/MODEL_VERSIONS.md`](../docs/MODEL_VERSIONS.md).

## Layout

```
scripts/
├── README.md
├── requirements.txt                  # pinned Python deps
│
├── benchmark_bodhi.py                # synthetic 100 — extraction + 3-arm safety
├── benchmark_eka_real.py             # Eka 156 real transcripts — extraction
├── benchmark_aci.py                  # ACI-Bench — dialogue → SOAP
├── benchmark_crescenddi.py           # CRESCENDDI — DDI safety arms
├── benchmark_pharmacology_mcqa.py    # NFI Pharmacology MCQA
├── benchmark_medical_calculators.py  # Medical Calculator Eval
│
├── bodhi_triage_audit.py             # BODHI triage classification audit
├── crescenddi_funnel.py              # pre-registered CRESCENDDI eligibility filter
│
├── aggregate_aci_from_judges.py
├── aggregate_crescenddi_partial.py
├── aggregate_eka_partial.py
├── aggregate_runs.py
│
├── fetch_bodhi.sh                    # BODHI knowledge graph (CC BY-NC, Eka Care)
├── fetch_eka_real.sh                 # Eka real-data parquet shards
├── fetch_aci_bench.sh                # ACI-Bench dataset
├── fetch_crescenddi.sh               # CRESCENDDI .xlsx files
│
├── retry_aci_failures.sh             # retry ACI cases that hit ollama errors
├── retry_qwen3_thinking_fix.sh       # re-run Qwen 3.5 with think:false fix
├── run_eka_ondevice.sh               # sequential per-model on-device runs
├── deploy_watch.sh                   # periodic re-export + Cloudflare deploy
└── run_clean_5x.sh                   # multi-seed run orchestration
```

## Quick start

```bash
pip install -r scripts/requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...

python3 scripts/benchmark_pharmacology_mcqa.py \
    --models claude-haiku --limit 5 --concurrency 2
```

Expected: `claude-haiku-4-5-20251001  n=5  acc=80.0%  parse-fail=0`.

## Full reproduction

### 1. Install Ollama and pull on-device models

```bash
# https://ollama.com/download
ollama pull qwen3.5:9b qwen3.5:2b qwen3.5:0.8b
ollama pull gemma4:e4b gemma4:e2b medgemma1.5
```

Disk: ~30 GB.

### 2. Fetch source datasets

```bash
bash scripts/fetch_bodhi.sh         # BODHI graph (required by benchmark_bodhi + bodhi_triage_audit)
bash scripts/fetch_eka_real.sh      # Eka real transcripts
bash scripts/fetch_crescenddi.sh    # CRESCENDDI
bash scripts/fetch_aci_bench.sh     # ACI-Bench
# Eka NFI MCQA + Calculator Eval are loaded at runtime via huggingface datasets.
```

### 3. Run benchmarks

Cloud benchmarks (parallel, ~30–60 min):

```bash
python3 scripts/benchmark_bodhi.py
python3 scripts/benchmark_eka_real.py
for split in valid train test1 test2 test3; do
    python3 scripts/benchmark_aci.py --split "$split" --concurrency 4
done
python3 scripts/benchmark_crescenddi.py --limit 100 --concurrency 4
python3 scripts/benchmark_pharmacology_mcqa.py --concurrency 4
python3 scripts/benchmark_medical_calculators.py --concurrency 4
```

On-device benchmarks (sequential, 14–20 hours):

```bash
bash scripts/run_eka_ondevice.sh
```

### 4. Aggregate and export

```bash
python3 scripts/aggregate_eka_partial.py
python3 scripts/aggregate_aci_from_judges.py
python3 scripts/aggregate_crescenddi_partial.py

python3 benchmark_dashboard/scripts/export_data.py
python3 benchmark_dashboard/scripts/export_eka_real.py
python3 benchmark_dashboard/scripts/export_aci.py
python3 benchmark_dashboard/scripts/export_crescenddi.py
python3 benchmark_dashboard/scripts/export_pharmacology.py
python3 benchmark_dashboard/scripts/export_calculators.py
python3 benchmark_dashboard/scripts/export_triage_audit.py
```

### 5. View dashboard locally

```bash
cd benchmark_dashboard/public && python3 -m http.server 8000
# http://localhost:8000
```

## Output paths

| Benchmark | Per-(model, case) raw | Aggregate |
|---|---|---|
| Synthetic 100 | `scripts/bodhi_raw/` | `scripts/bodhi_benchmark_report.json` |
| Eka real 156 | `scripts/eka_real_raw/` | (in-script export) |
| ACI-Bench | `scripts/aci_bench_raw/` | `scripts/aci_results_<split>.json` |
| CRESCENDDI | `scripts/crescenddi_raw/` | `scripts/crescenddi_results.json` |
| NFI Pharmacology | `scripts/pharmacology_raw/` | `scripts/pharmacology_results.json` |
| Medical Calculators | `scripts/calculators_raw/` | `scripts/calculators_results.json` |
| BODHI triage audit | `scripts/crescenddi/bodhi_triage_audit_raw/` | `scripts/bodhi_triage_audit.json` |

Raw files are the canonical record. Aggregates can be regenerated from raw via the `aggregate_*.py` scripts.

## Common gotchas

### Qwen 3.5 silent-failure mode

Qwen 3 routes long-form output into `message.thinking`, leaving `content` empty without `"think": false`. All ollama callers in this suite already pass it for `qwen3*` handles. If forking, preserve this.

### gpt-5.x reasoning-token budgets

Reasoning models use `max_completion_tokens` and consume tokens internally before producing output. Pharmacology MCQA: 1,024 tokens. Calculators: 4,096 tokens.

### macOS rename duplicates

Concurrent retries can produce `q__model__id 2.json` files (empty/stale). Clean periodically:

```bash
find scripts/*_raw -name "* 2.json" -delete
```

### Anthropic temperature deprecation

Extended-thinking models (Opus 4.7, Sonnet 4.6/4.7) deprecated `temperature`. The `_anthropic_kwargs()` helper in `benchmark_bodhi.py` handles this; direct API calls without that helper return HTTP 400.

## Cost estimate

One full 12-model run across all 6 benchmarks:

| Component | Estimate |
|---|---|
| Anthropic API | ~$80–150 |
| OpenAI API | ~$50–100 |
| On-device compute (single Apple Silicon, sequential) | 14–20 hours wall-clock |
| Storage for raw outputs | ~1.5 GB |

Smoke runs (single model, small `--limit`): <$1.

## Datasets

| Dataset | n | License | Source |
|---|---|---|---|
| Synthetic 100 | 100 enc / 89 dangers | Apache 2.0 (this repo) | inlined in `benchmark_bodhi.py` |
| Eka real 156 | 156 transcripts | Eka Care eval license | `ekacare/clinical_note_generation_dataset` |
| ACI-Bench | 207 × 5 splits | CC BY 4.0 | Yim et al., Nature Sci Data 2023 |
| CRESCENDDI | 14,830 pairs | CC0 | Lavertu et al., Nature Sci Data 2022 |
| NFI Pharmacology MCQA | 925 Q | Eka Care, May 2026 | `ekacare/Eka_NFI_MCQA` |
| Medical Calculator Eval | 1,066 vignettes | Eka Care, May 2026 | `ekacare/medical_calculator_eval` |

BODHI knowledge graph (CC BY-NC 4.0, Eka Care) is required by `benchmark_bodhi.py` and `bodhi_triage_audit.py`. Not bundled. Fetch via `scripts/fetch_bodhi.sh`. Non-commercial use unrestricted; commercial deployment requires Eka Care license.

## Adding a new model

Edit the `MODELS` list at the top of each benchmark script. Tuple format: `(model_handle, backend)` where backend is `anthropic`, `openai`, or `ollama`. Routing is automatic.

## Adding a new benchmark

Pattern (~300 lines, mirror `benchmark_pharmacology_mcqa.py` for MCQA-style or `benchmark_medical_calculators.py` for numerical scoring):

1. Stage 1: per-(model, case) inference, cached as JSON in `scripts/<bench>_raw/<safe_id>.json`. Idempotent.
2. Stage 2: scoring with category/difficulty slices.
3. End-of-run: write `scripts/<bench>_results.json`.
