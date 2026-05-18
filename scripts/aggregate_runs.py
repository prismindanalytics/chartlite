#!/usr/bin/env python3
"""Combine N benchmark runs (from bodhi_raw_generations/run<N>/ subfolders) into
mean ± stddev per-metric scores. Writes a single aggregate JSON that downstream
export/dashboard tools consume.

Each run lives in its own subfolder:
  bodhi_raw_generations/
    run1/*.json
    run2/*.json
    run3/*.json
    ...
  (or top-level files — treated as run1 for backward compat)

The aggregator:
 1. Loads all runs for each (model, mode, encounter_id) triple.
 2. Computes per-triple mean of each metric across runs.
 3. Rolls up to per-(model, mode) aggregate: mean of per-encounter-means + stddev across runs.
 4. Outputs scripts/bodhi_multi_run_aggregate.json.
"""
from __future__ import annotations
import json, os, sys, glob, statistics
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW_BASE = REPO / "scripts" / "bodhi_raw_generations"
OUT_PATH = REPO / "scripts" / "bodhi_multi_run_aggregate.json"


def discover_runs():
    """Return dict: run_id -> list of file paths."""
    runs = {}
    # Subfolder runs
    for d in sorted(RAW_BASE.iterdir()):
        if d.is_dir():
            runs[d.name] = sorted(d.glob("*.json"))
    # Top-level files (run1 default)
    top = sorted(RAW_BASE.glob("*.json"))
    if top:
        runs.setdefault("run1", []).extend(top)
    return runs


def load_record(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def main():
    runs = discover_runs()
    if not runs:
        print("No run data found.")
        return

    print(f"Discovered {len(runs)} runs:")
    for rid, paths in runs.items():
        print(f"  {rid}: {len(paths)} files")

    # per-triple samples: (model, mode, encounter_id) -> list of score dicts
    triples = defaultdict(list)
    # Also track run-level aggregate scores per (model, mode) for stddev
    per_run_model_mode = defaultdict(lambda: defaultdict(list))  # run_id -> (model|mode) -> [per-encounter metrics]

    for run_id, paths in runs.items():
        for p in paths:
            d = load_record(p)
            if not d: continue
            model = d.get("model")
            mode = d.get("transcript_mode")
            eid = d.get("encounter_id")
            if not (model and mode and eid): continue
            triples[(model, mode, eid)].append({"run": run_id, "record": d})
            per_run_model_mode[run_id][f"{model}|{mode}"].append(d)

    # Compute per-(model,mode) summary across runs
    summary = {}
    keys = sorted(set(k for r in per_run_model_mode.values() for k in r))
    for k in keys:
        # Collect per-run summary numbers for this (model,mode)
        per_run_dx_rec = []
        per_run_dx_rec_sem = []
        per_run_meds_rec = []
        per_run_arm1 = []
        per_run_arm3 = []
        per_run_note_struct = []
        n_encs_list = []
        for run_id, mkv in per_run_model_mode.items():
            encs = mkv.get(k, [])
            if not encs: continue
            n_encs_list.append(len(encs))
            def field(path):
                vals = []
                for e in encs:
                    v = e
                    for p in path:
                        v = (v or {}).get(p) if isinstance(v, dict) else None
                    if v is not None and isinstance(v, (int, float)):
                        vals.append(v)
                return statistics.mean(vals) if vals else None
            per_run_dx_rec.append(field(("extraction", "score", "dx_recall")))
            per_run_dx_rec_sem.append(field(("extraction", "score", "dx_recall_semantic")))
            per_run_meds_rec.append(field(("extraction", "score", "meds_recall")))
            per_run_note_struct.append(field(("note", "score", "structure")))
            # Arm1/Arm3 = fraction of encounters where caught == total
            arm_caught = [e.get("arm_caught") for e in encs if e.get("arm_caught")]
            if arm_caught:
                tot = sum(a["total"] for a in arm_caught)
                if tot:
                    per_run_arm1.append(sum(a["arm1"] for a in arm_caught) / tot)
                    per_run_arm3.append(sum(a["arm3"] for a in arm_caught) / tot)

        def stats(vals):
            vals = [v for v in vals if v is not None]
            if not vals: return None
            return {
                "mean": round(statistics.mean(vals), 3),
                "stdev": round(statistics.stdev(vals), 3) if len(vals) > 1 else 0,
                "n_runs": len(vals),
                "values": [round(v, 3) for v in vals],
            }

        summary[k] = {
            "n_encounters_per_run": n_encs_list,
            "dx_recall": stats(per_run_dx_rec),
            "dx_recall_semantic": stats(per_run_dx_rec_sem),
            "meds_recall": stats(per_run_meds_rec),
            "note_structure": stats(per_run_note_struct),
            "arm1_rate": stats(per_run_arm1),
            "arm3_rate": stats(per_run_arm3),
        }

    out = {
        "runs_discovered": {rid: len(paths) for rid, paths in runs.items()},
        "model_modes": summary,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {OUT_PATH}")
    # Print a preview
    print("\nPreview (dx_recall_semantic mean ± stdev across runs):")
    for k, s in sorted(summary.items()):
        dxr = s.get("dx_recall_semantic")
        if dxr:
            print(f"  {k:40}  {dxr['mean']:.3f} ± {dxr['stdev']:.3f}  (n_runs={dxr['n_runs']})")


if __name__ == "__main__":
    main()
