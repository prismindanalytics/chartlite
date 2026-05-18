#!/usr/bin/env python3
"""Re-aggregate Eka benchmarks (Pharmacology + Calculators) from raw files.

Each benchmark script's end-of-run aggregator only includes the --models the
script was called with, so per-model retry runs overwrite the combined
results.json with only that one model. This script reads ALL raw files in
scripts/pharmacology_raw and scripts/calculators_raw and produces complete
results.json files for both benchmarks, including every model that has any
gradable rows.

Usage:
  python3 scripts/aggregate_eka_partial.py
"""
from __future__ import annotations
import json, glob, re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

# canonical-name lookup
_safe_to_name = {
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


def parse_answer(raw: str) -> str | None:
    if not raw:
        return None
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<unused\d+>.*?<unused\d+>", "", raw, flags=re.DOTALL)
    raw = raw.strip()
    m = re.match(r"^\s*([A-E])\b", raw) or re.search(r"\b([A-E])\b", raw)
    if m:
        return m.group(1)
    m = re.search(r"([A-Ea-e])", raw)
    return m.group(1).upper() if m else None


def parse_json_obj(raw: str):
    if not raw:
        return None
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<unused\d+>.*?<unused\d+>", "", raw, flags=re.DOTALL)
    raw = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    best = None
    depth = 0
    start = -1
    for i, c in enumerate(raw):
        if c == "{":
            if depth == 0: start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                cand = raw[start:i+1]
                try:
                    obj = json.loads(cand)
                    if best is None or len(cand) > len(json.dumps(best)):
                        best = obj
                except Exception:
                    pass
    return best


def numerical_match(predicted, expected, tolerance):
    try:
        p = float(predicted); e = float(expected)
    except (TypeError, ValueError):
        return str(predicted).strip().lower() == str(expected).strip().lower()
    if abs(e) < 1e-6:
        return abs(p - e) <= max(tolerance, 0.01)
    return abs(p - e) / abs(e) <= tolerance


def extract_safe_model(filename: str) -> str:
    """Extract safe model name from filename like 'q__gpt-5.5__0123.json'."""
    name = filename.replace("q__", "")
    # Strip .json and the trailing __<id>
    name = re.sub(r"\.json$", "", name)
    name = re.sub(r"__[a-zA-Z_0-9]*$", "", name)
    return name


def aggregate_pharmacology() -> dict:
    raw_dir = HERE / "pharmacology_raw"
    files = list(raw_dir.glob("q__*.json"))
    by_model: dict[str, dict] = defaultdict(lambda: {
        "n_evaluated": 0, "n_correct": 0, "n_parse_fail": 0, "latencies": [],
        "by_category": defaultdict(lambda: [0, 0]),
        "by_difficulty": defaultdict(lambda: [0, 0]),
        "by_question_type": defaultdict(lambda: [0, 0]),
    })
    n_seen_qids = set()
    for f in files:
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        raw = d.get("raw", "") or ""
        if raw.startswith("[ERROR]"):
            continue
        # Identify model from data, fall back to filename parsing
        model = d.get("model") or _safe_to_name.get(extract_safe_model(f.name), "unknown")
        m = by_model[model]
        m["n_evaluated"] += 1
        m["latencies"].append(d.get("latency_s") or 0)
        n_seen_qids.add(d.get("qid"))

        picked = parse_answer(raw)
        if picked is None:
            m["n_parse_fail"] += 1
            ok = False
        else:
            ok = picked == (d.get("expected") or "")
        if ok:
            m["n_correct"] += 1
        cat = d.get("category") or "unknown"
        diff = d.get("difficulty") or "unknown"
        qt = d.get("question_type") or "unknown"
        m["by_category"][cat][1] += 1
        m["by_difficulty"][diff][1] += 1
        m["by_question_type"][qt][1] += 1
        if ok:
            m["by_category"][cat][0] += 1
            m["by_difficulty"][diff][0] += 1
            m["by_question_type"][qt][0] += 1

    final = {}
    for model, info in by_model.items():
        n = info["n_evaluated"]
        if n == 0:
            continue
        acc = round(100 * info["n_correct"] / n, 1)
        lats = sorted(info["latencies"])
        median_lat = round(lats[len(lats)//2], 2) if lats else None
        final[model] = {
            "n_evaluated": n,
            "n_correct": info["n_correct"],
            "accuracy": acc,
            "n_parse_fail": info["n_parse_fail"],
            "median_latency_s": median_lat,
            "by_category": {k: {"correct": v[0], "total": v[1],
                                "accuracy": round(100 * v[0] / max(v[1], 1), 1)}
                            for k, v in info["by_category"].items()},
            "by_difficulty": {k: {"correct": v[0], "total": v[1],
                                  "accuracy": round(100 * v[0] / max(v[1], 1), 1)}
                              for k, v in info["by_difficulty"].items()},
            "by_question_type": {k: {"correct": v[0], "total": v[1],
                                     "accuracy": round(100 * v[0] / max(v[1], 1), 1)}
                                 for k, v in info["by_question_type"].items()},
        }
    return {
        "n_questions": max(len(n_seen_qids), 925),
        "dataset": "ekacare/Eka_NFI_MCQA (test split)",
        "license": "Open release, May 2026 — see ekacare HF org",
        "models": final,
    }


def aggregate_calculators() -> dict:
    raw_dir = HERE / "calculators_raw"
    files = list(raw_dir.glob("q__*.json"))
    by_model: dict[str, dict] = defaultdict(lambda: {
        "n_evaluated": 0, "n_correct": 0, "n_parse_fail": 0, "latencies": [],
        "by_category": defaultdict(lambda: [0, 0]),
        "by_difficulty": defaultdict(lambda: [0, 0]),
        "by_language": defaultdict(lambda: [0, 0]),
        "by_calculator": defaultdict(lambda: [0, 0]),
    })
    n_seen_ids = set()

    for f in files:
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        raw = d.get("raw", "") or ""
        if raw.startswith("[ERROR]"):
            continue
        model = d.get("model") or _safe_to_name.get(extract_safe_model(f.name), "unknown")
        m = by_model[model]
        m["n_evaluated"] += 1
        m["latencies"].append(d.get("latency_s") or 0)
        n_seen_ids.add(d.get("id"))

        try:
            expected_obj = json.loads(d.get("expected_output") or "{}")
        except Exception:
            expected_obj = {}
        try:
            tolerance = float(d.get("tolerance") or "0.01")
        except (TypeError, ValueError):
            tolerance = 0.01
        primary_field = d.get("primary_field") or ""

        predicted_obj = parse_json_obj(raw)
        if predicted_obj is None:
            m["n_parse_fail"] += 1
            ok = False
        else:
            p = predicted_obj.get(primary_field)
            if p is None:
                for k_alt in [primary_field.lower(), primary_field.replace("_", "")]:
                    if k_alt in predicted_obj:
                        p = predicted_obj[k_alt]
                        break
            e = expected_obj.get(primary_field) if isinstance(expected_obj, dict) else expected_obj
            ok = numerical_match(p, e, tolerance) if p is not None else False
        if ok:
            m["n_correct"] += 1

        cat = d.get("category") or "unknown"
        diff = d.get("difficulty_tier") or "unknown"
        lang = d.get("language_style") or "unknown"
        calc = d.get("expected_calculator") or "unknown"
        for bucket, key in [(m["by_category"], cat), (m["by_difficulty"], diff),
                            (m["by_language"], lang), (m["by_calculator"], calc)]:
            bucket[key][1] += 1
            if ok:
                bucket[key][0] += 1

    final = {}
    for model, info in by_model.items():
        n = info["n_evaluated"]
        if n == 0:
            continue
        acc = round(100 * info["n_correct"] / n, 1)
        lats = sorted(info["latencies"])
        median_lat = round(lats[len(lats)//2], 2) if lats else None

        def to_dict(d):
            return {k: {"correct": v[0], "total": v[1],
                        "accuracy": round(100 * v[0] / max(v[1], 1), 1)}
                    for k, v in d.items()}

        # Top-N calculators
        calcs_full = to_dict(info["by_calculator"])
        calcs_top = dict(sorted(calcs_full.items(), key=lambda x: -x[1]["total"])[:20])

        final[model] = {
            "n_evaluated": n,
            "n_correct": info["n_correct"],
            "accuracy": acc,
            "n_parse_fail": info["n_parse_fail"],
            "median_latency_s": median_lat,
            "by_category": to_dict(info["by_category"]),
            "by_difficulty": to_dict(info["by_difficulty"]),
            "by_language": to_dict(info["by_language"]),
            "by_calculator_top": calcs_top,
        }
    return {
        "n_vignettes": max(len(n_seen_ids), 1066),
        "dataset": "ekacare/medical_calculator_eval (test split)",
        "license": "Open release, May 2026 — see ekacare HF org",
        "models": final,
    }


def main():
    pharm = aggregate_pharmacology()
    (HERE / "pharmacology_results.json").write_text(json.dumps(pharm, indent=2, default=str))
    print(f"Wrote pharmacology_results.json — {len(pharm['models'])} models")
    for m, info in sorted(pharm["models"].items(), key=lambda x: -x[1]["accuracy"]):
        print(f"  {m:<32} n={info['n_evaluated']:>4}  acc={info['accuracy']:>5.1f}%  fail={info['n_parse_fail']}")

    calc = aggregate_calculators()
    (HERE / "calculators_results.json").write_text(json.dumps(calc, indent=2, default=str))
    print(f"\nWrote calculators_results.json — {len(calc['models'])} models")
    for m, info in sorted(calc["models"].items(), key=lambda x: -x[1]["accuracy"]):
        print(f"  {m:<32} n={info['n_evaluated']:>4}  acc={info['accuracy']:>5.1f}%  fail={info['n_parse_fail']}")


if __name__ == "__main__":
    main()
