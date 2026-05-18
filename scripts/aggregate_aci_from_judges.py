#!/usr/bin/env python3
"""Re-aggregate ACI results directly from judge__*.json files.

The retry sequence in retry_aci_failures.sh ran benchmark_aci.py with only
on-device models per split, which caused the script's end-of-run aggregator
to overwrite scripts/aci_results_<split>.json with only those models. The
cloud-model judge files are intact on disk; this script reads ALL judge files
per split and produces a complete aci_results_<split>.json with every model
that has any judges.
"""
from __future__ import annotations
import json, glob, os
from collections import defaultdict
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
RAW = HERE / "aci_bench_raw"

# Map of filename-safe model id back to canonical name
def unsafe_to_canonical(safe: str) -> str:
    # benchmark_aci uses .replace(':', '_').replace('/', '_'), so reverse:
    # We don't know which underscore was originally a colon.
    # But our model list is fixed:
    canonical = {
        "claude-opus-4-7": "claude-opus-4-7",
        "claude-sonnet-4-6": "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
        "gpt-5.5": "gpt-5.5",
        "gpt-5.4": "gpt-5.4",
        "gpt-4.1": "gpt-4.1",
        "qwen3.5_9b": "qwen3.5:9b",
        "qwen3.5_2b": "qwen3.5:2b",
        "qwen3.5_0.8b": "qwen3.5:0.8b",
        "gemma4_e4b": "gemma4:e4b",
        "gemma4_e2b": "gemma4:e2b",
        "medgemma1.5": "medgemma1.5",
    }
    return canonical.get(safe, safe)


def aggregate_split(split: str) -> dict:
    pattern = str(RAW / f"judge__*__{split}.json")
    files = glob.glob(pattern)
    by_model = defaultdict(lambda: {
        "scores": defaultdict(list),
        "n_judged": 0,
    })
    for f in files:
        try:
            d = json.loads(open(f).read())
        except Exception:
            continue
        scores = d.get("scores")
        if not scores:
            continue
        # Filename: judge__<model_safe>__<encounter>__<split>.json
        base = os.path.basename(f).replace("judge__", "").replace(".json", "")
        # Encounter and split are last two segments
        parts = base.rsplit("__", 2)
        if len(parts) != 3:
            continue
        model_safe = parts[0]
        model = unsafe_to_canonical(model_safe)
        m = by_model[model]
        m["n_judged"] += 1
        for axis in ["overall", "soap_completeness", "factual_consistency",
                     "clinical_reasoning", "plan_appropriateness"]:
            v = scores.get(axis)
            if v is not None:
                m["scores"][axis].append(v)

    models_out = {}
    for model, info in by_model.items():
        if info["n_judged"] == 0:
            continue
        out = {"n_judged": info["n_judged"]}
        for axis in ["overall", "soap_completeness", "factual_consistency",
                     "clinical_reasoning", "plan_appropriateness"]:
            vals = info["scores"][axis]
            out[axis] = round(statistics.mean(vals), 1) if vals else None
        models_out[model] = out

    # Detect n_cases for the split from the dataset
    # (we'll just use max n_judged across models as a proxy if dataset isn't loaded)
    n_cases = max((m["n_judged"] for m in models_out.values()), default=0)

    return {
        "split": split,
        "n_cases": n_cases,
        "judge": "claude-opus-4-7",
        "models": models_out,
    }


def main():
    for split in ["train", "test1", "test2", "test3", "valid"]:
        out = aggregate_split(split)
        path = HERE / f"aci_results_{split}.json"
        path.write_text(json.dumps(out, indent=2))
        print(f"\n[{split}] n_cases={out['n_cases']}, {len(out['models'])} models")
        for m in sorted(out["models"].keys()):
            s = out["models"][m]
            print(f"  {m:32s} n={s['n_judged']:>3}  overall={s['overall']:5.1f}")
        print(f"  → {path}")


if __name__ == "__main__":
    main()
