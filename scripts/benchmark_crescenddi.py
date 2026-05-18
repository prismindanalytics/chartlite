#!/usr/bin/env python3
"""CRESCENDDI benchmark — drug-drug interaction detection.

Source: Lavertu et al., "A reference set of clinically relevant adverse
drug-drug interactions", Nature Scientific Data 2022. Licence: CC0.

What this evaluates:
  * Positive controls: 10,286 known DDI pairs with severity + evidence levels
    from BNF (UK), ANSM (France), Micromedex.
  * Negative controls: 4,544 drug pairs known NOT to interact.

For each (drug_1, drug_2) pair, we:
  1. Construct a synthetic encounter where the patient is on BOTH drugs.
  2. Pass it through our 3-arm safety pipeline (LLM-alone / rules /
     rules+BODHI) — exactly as in benchmark_bodhi.py.
  3. Score: did the arm flag a drug-drug interaction or drug-condition
     concern? (true positive on the positive set; false positive on the
     negative set).

This complements the synthetic-100 + Eka real-data benchmarks because:
  * The ground truth is **clinician-curated** (not model-generated like our
    synthetic 89-danger list), addressing the dashboard's "GT is itself
    LLM-output" caveat for the safety arms.
  * Negative controls let us measure the false-positive rate, which the
    synthetic suite doesn't isolate.

Output: scripts/crescenddi_results.json
       per-arm: TP, FP, TN, FN + severity-stratified breakdown.

Usage:
    bash scripts/fetch_crescenddi.sh
    python3 scripts/benchmark_crescenddi.py --limit 200 --models claude-opus-4-7 qwen3.5:9b
"""
from __future__ import annotations
import argparse, json, os, random, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "crescenddi"
RAW = HERE / "crescenddi_raw"
RAW.mkdir(exist_ok=True)

sys.path.insert(0, str(HERE))
import benchmark_bodhi as bb

POS_FILE = DATA / "Data_Record_1_Positive_Controls.xlsx"
NEG_FILE = DATA / "Data_Record_2_Negative_Controls.xlsx"


def load_positive() -> pd.DataFrame:
    df = pd.read_excel(POS_FILE)
    df["label"] = "positive"
    return df


def load_negative() -> pd.DataFrame:
    df = pd.read_excel(NEG_FILE)
    df["label"] = "negative"
    # Negative controls don't have severity columns; pad to align schema.
    for col in ["EVENT_CONCEPT_NAME", "BNF_SEV_LEVEL", "MICROMEDEX_SEV_LEVEL"]:
        if col not in df.columns:
            df[col] = None
    return df


def make_encounter(drug_1: str, drug_2: str) -> str:
    """Construct a minimal encounter transcript that puts the patient on both
    drugs. Same shape as the synthetic-100 dictation transcripts so the same
    extraction prompt can read it."""
    return (
        f"45 year old patient currently taking {drug_1} for an existing condition. "
        f"Today starting {drug_2} as well. Continue both medications. "
        f"Review in two weeks."
    )


def did_arm_flag_interaction(arm_alerts: list[dict]) -> bool:
    """Did this arm flag ANY drug-related concern (drug-drug, drug-condition,
    drug-allergy)? Conservative: any of those three categories counts as a
    flag, since CRESCENDDI labels are at the drug-drug-event level but our
    arms may decompose that into related categories."""
    flag_categories = {"drug-drug", "drug-condition", "drug-allergy"}
    for a in arm_alerts or []:
        cat = (a.get("category", "") or "").lower()
        if any(fc in cat for fc in flag_categories):
            return True
    return False


def score_pair(case: dict, arm_outputs: dict) -> dict:
    """Given an encounter (with label = positive/negative) and the alerts each
    arm produced, compute whether each arm correctly fired or correctly stayed
    silent. Returns per-arm {tp, fp, tn, fn} ∈ {0, 1}."""
    expect_flag = case["label"] == "positive"
    out = {}
    for arm, alerts in arm_outputs.items():
        flagged = did_arm_flag_interaction(alerts)
        if expect_flag and flagged:
            out[arm] = "tp"
        elif expect_flag and not flagged:
            out[arm] = "fn"
        elif not expect_flag and flagged:
            out[arm] = "fp"
        else:
            out[arm] = "tn"
    return out


def call_extract_and_arms(model: str, backend: str, transcript: str) -> dict:
    """Run extraction + 3-arm safety review for a single transcript. Reuses the
    same plumbing as benchmark_bodhi.py — we re-import the helpers and the
    CDSS class so any future improvement to the safety arms shows up here too.

    Arm 1 = `clinical_review` (LLM-alone safety review)
    Arm 2 = `cdss.evaluate(...)[0]` — vanilla rules-only alerts
    Arm 3 = vanilla + bodhi alerts together (rules + BODHI knowledge graph)
    """
    from benchmark_bodhi import (
        call_ollama, call_anthropic, call_openai,
        clinical_review, CDSS, ClinicalData,
    )
    # Cache CDSS across calls — graph load is the expensive bit.
    global _CDSS_INSTANCE
    if "_CDSS_INSTANCE" not in globals() or _CDSS_INSTANCE is None:
        _CDSS_INSTANCE = CDSS(ClinicalData())

    if backend == "ollama":
        parsed, raw, lat = call_ollama(model, transcript)
    elif backend == "anthropic":
        parsed, raw, lat = call_anthropic(model, transcript)
    elif backend == "openai":
        parsed, raw, lat = call_openai(model, transcript)
    else:
        return {"error": f"unknown backend {backend}"}
    if not parsed:
        return {"error": "extraction failed", "raw": (raw or "")[:400]}

    # Arm 1 — LLM-alone clinical safety review
    review_alerts, _review_raw, _review_lat = clinical_review(model, backend, transcript)

    # Arm 2 + Arm 3 — rules vs rules+BODHI
    vanilla_alerts, bodhi_alerts = _CDSS_INSTANCE.evaluate(parsed, parsed.get("allergies") or [])
    arm3_alerts = vanilla_alerts + bodhi_alerts

    def _to_dicts(alerts):
        # Alerts are dataclass-like objects with severity/category/message
        return [
            {"severity": getattr(a, "severity", ""),
             "category": getattr(a, "category", ""),
             "message":  getattr(a, "message", "")}
            for a in (alerts or [])
        ]

    return {
        "extracted": parsed,
        "arm1": _to_dicts(review_alerts),
        "arm2": _to_dicts(vanilla_alerts),
        "arm3": _to_dicts(arm3_alerts),
    }


_CDSS_INSTANCE = None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=200,
                   help="Cap to N pairs from each of pos/neg sets for quick smoke.")
    p.add_argument("--models", nargs="+",
                   help="Substring match against model names. Default: cloud + on-device picks.")
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--seed", type=int, default=42,
                   help="Random seed for sampling pairs from the full set.")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    random.seed(args.seed)
    pos = load_positive().sample(frac=1, random_state=args.seed).head(args.limit)
    neg = load_negative().sample(frac=1, random_state=args.seed).head(args.limit)
    print(f"Positive controls (sampled): {len(pos)}")
    print(f"Negative controls (sampled): {len(neg)}")

    cases = []
    for _, row in pd.concat([pos, neg]).iterrows():
        cases.append({
            "id": f"{row['DRUG_1_CONCEPT_NAME']}__{row['DRUG_2_CONCEPT_NAME']}__{row.get('label')}",
            "drug_1": row["DRUG_1_CONCEPT_NAME"],
            "drug_2": row["DRUG_2_CONCEPT_NAME"],
            "event": row.get("EVENT_CONCEPT_NAME"),
            "severity_bnf": row.get("BNF_SEV_LEVEL"),
            "severity_micromedex": row.get("MICROMEDEX_SEV_LEVEL"),
            "label": row["label"],
            "transcript": make_encounter(row["DRUG_1_CONCEPT_NAME"], row["DRUG_2_CONCEPT_NAME"]),
        })

    # Full 12-model menu (same shape as benchmark_eka_real.py / benchmark_aci.py).
    # Don't rely on benchmark_bodhi.detect_models() — it filters by what's
    # currently installed in Ollama + env-var availability and dropped gpt-5.5
    # in the first run of this script.
    ALL_MODELS = [
        ("claude-opus-4-7",          "anthropic"),
        ("claude-sonnet-4-6",        "anthropic"),
        ("claude-haiku-4-5-20251001","anthropic"),
        ("gpt-5.5",                  "openai"),
        ("gpt-5.4",                  "openai"),
        ("gpt-4.1",                  "openai"),
        ("qwen3.5:9b",               "ollama"),
        ("qwen3.5:2b",               "ollama"),
        ("qwen3.5:0.8b",             "ollama"),
        ("gemma4:e4b",               "ollama"),
        ("gemma4:e2b",               "ollama"),
        ("medgemma1.5",              "ollama"),
    ]
    selected = ALL_MODELS
    if args.models:
        selected = [(m, b) for m, b in ALL_MODELS if any(k in m for k in args.models)]
    print(f"Models: {[m for m, _ in selected]}")

    # Stage 1: extract + run 3 arms per (model, case)
    print("\n=== Stage 1: extraction + 3-arm safety ===")
    tasks = [(m, b, c) for m, b in selected for c in cases]

    def safe_path(model: str, case_id: str) -> Path:
        safe = case_id.replace("/", "_").replace(":", "_")[:120]
        return RAW / f"arms__{model.replace(':', '_').replace('/', '_')}__{safe}.json"

    import time
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        def task(m, b, c):
            path = safe_path(m, c["id"])
            if not args.force and path.exists():
                return
            result = call_extract_and_arms(m, b, c["transcript"])
            path.write_text(json.dumps({
                "model": m, "case": c, "arms": result,
            }, default=str))
        futs = {ex.submit(task, m, b, c): (m, c["id"]) for m, b, c in tasks}
        for fut in as_completed(futs):
            done += 1
            if done % 25 == 0:
                print(f"  [{done}/{len(tasks)}, {time.time()-t0:.0f}s]")
    print(f"  done: {done}/{len(tasks)} in {time.time()-t0:.0f}s")

    # Aggregate
    print("\n=== Aggregating ===")
    by_model = {}
    for m, _ in selected:
        confusion = {arm: {"tp": 0, "fp": 0, "tn": 0, "fn": 0} for arm in ["arm1", "arm2", "arm3"]}
        n_evaluated = 0
        for c in cases:
            path = safe_path(m, c["id"])
            if not path.exists(): continue
            d = json.loads(path.read_text())
            arms = d.get("arms") or {}
            if "error" in arms: continue
            n_evaluated += 1
            scored = score_pair(c, {
                "arm1": arms.get("arm1") or [],
                "arm2": arms.get("arm2") or [],
                "arm3": arms.get("arm3") or [],
            })
            for arm, label in scored.items():
                confusion[arm][label] += 1
        # Compute metrics
        per_arm = {}
        for arm, conf in confusion.items():
            tp, fp, tn, fn = conf["tp"], conf["fp"], conf["tn"], conf["fn"]
            sens = tp / (tp + fn) if (tp + fn) else 0.0
            spec = tn / (tn + fp) if (tn + fp) else 0.0
            ppv = tp / (tp + fp) if (tp + fp) else 0.0
            per_arm[arm] = {
                "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                "sensitivity": round(100 * sens, 1),
                "specificity": round(100 * spec, 1),
                "ppv": round(100 * ppv, 1),
            }
        by_model[m] = {"n_evaluated": n_evaluated, "arms": per_arm}

    out_path = HERE / "crescenddi_results.json"
    out_path.write_text(json.dumps({
        "n_positive": len(pos), "n_negative": len(neg),
        "models": by_model,
    }, indent=2, default=str))
    print(f"Wrote {out_path}")

    print(f"\n  Per-arm sensitivity (= % positive DDIs caught) and specificity (= % negatives correctly silent):")
    print(f"  {'Model':<32} {'Arm':<5} {'Sens':>6} {'Spec':>6} {'PPV':>6}  TP/FP/TN/FN")
    for m, d in by_model.items():
        for arm, s in d["arms"].items():
            print(f"  {m:<32} {arm:<5} {s['sensitivity']:>5.1f}% {s['specificity']:>5.1f}% {s['ppv']:>5.1f}%  "
                  f"{s['tp']}/{s['fp']}/{s['tn']}/{s['fn']}")


if __name__ == "__main__":
    main()
