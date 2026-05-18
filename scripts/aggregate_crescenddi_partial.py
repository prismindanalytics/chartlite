#!/usr/bin/env python3
"""Re-aggregate CRESCENDDI results from raw arms__*.json files mid-run.

benchmark_crescenddi.py only writes scripts/crescenddi_results.json at the end
of its main(), so when the run is in flight the dashboard sees stale data even
though most models have finished. This script reads the raw per-(model,case)
files in scripts/crescenddi_raw/ and produces the same crescenddi_results.json
schema, including only models that have a meaningful number of completed cases
(>= MIN_CASES, default 100 of 200).

Usage:
  python3 scripts/aggregate_crescenddi_partial.py [--min-cases 100]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
RAW = HERE / "crescenddi_raw"
OUT = HERE / "crescenddi_results.json"

sys.path.insert(0, str(HERE))
from benchmark_crescenddi import did_arm_flag_interaction


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--min-cases", type=int, default=100,
                   help="Drop models with fewer than this many completed cases.")
    args = p.parse_args()

    by_model: dict[str, dict] = {}
    n_pos_seen, n_neg_seen = set(), set()

    for path in sorted(RAW.glob("arms__*.json")):
        try:
            d = json.loads(path.read_text())
        except Exception:
            continue
        model = d.get("model")
        case = d.get("case") or {}
        arms = d.get("arms") or {}
        if not model or "error" in arms:
            continue

        label = case.get("label")
        cid = case.get("id")
        if label == "positive":
            n_pos_seen.add(cid)
        elif label == "negative":
            n_neg_seen.add(cid)

        m = by_model.setdefault(model, {
            "n_evaluated": 0,
            "confusion": {arm: {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
                          for arm in ["arm1", "arm2", "arm3"]},
        })
        m["n_evaluated"] += 1
        expect_flag = (label == "positive")
        for arm in ["arm1", "arm2", "arm3"]:
            flagged = did_arm_flag_interaction(arms.get(arm) or [])
            if expect_flag and flagged:      m["confusion"][arm]["tp"] += 1
            elif expect_flag and not flagged: m["confusion"][arm]["fn"] += 1
            elif not expect_flag and flagged: m["confusion"][arm]["fp"] += 1
            else:                             m["confusion"][arm]["tn"] += 1

    # Filter + finalize
    final = {}
    for model, m in by_model.items():
        if m["n_evaluated"] < args.min_cases:
            print(f"  skip {model}: only {m['n_evaluated']} cases")
            continue
        per_arm = {}
        for arm, conf in m["confusion"].items():
            tp, fp, tn, fn = conf["tp"], conf["fp"], conf["tn"], conf["fn"]
            sens = tp / max(tp + fn, 1)
            spec = tn / max(tn + fp, 1)
            ppv = tp / max(tp + fp, 1)
            per_arm[arm] = {
                "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                "sensitivity": round(100 * sens, 1),
                "specificity": round(100 * spec, 1),
                "ppv": round(100 * ppv, 1),
            }
        final[model] = {"n_evaluated": m["n_evaluated"], "arms": per_arm}

    out = {
        "n_positive": len(n_pos_seen),
        "n_negative": len(n_neg_seen),
        "models": final,
        "_partial_aggregation": True,
        "_min_cases_threshold": args.min_cases,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"Wrote {OUT} ({len(final)} models, {len(n_pos_seen)} pos / {len(n_neg_seen)} neg seen)")
    for model, info in final.items():
        a3 = info["arms"]["arm3"]
        a1 = info["arms"]["arm1"]
        print(f"  {model:32s}  n={info['n_evaluated']:>3}  "
              f"arm1 sens={a1['sensitivity']:>5.1f}% spec={a1['specificity']:>5.1f}%  "
              f"arm3 sens={a3['sensitivity']:>5.1f}% spec={a3['specificity']:>5.1f}%")


if __name__ == "__main__":
    main()
