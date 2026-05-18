#!/usr/bin/env python3
"""Medical Calculator Eval benchmark.

Source: ekacare/medical_calculator_eval on Hugging Face — 1,066 clinical
vignettes spanning 26 specialties, each requiring the model to compute a
specific calculator value (BAC, AUDIT-C, MELD, CHA2DS2-VASc, GFR, BSA, etc.)
from a clinical scenario. Released May 2026 by Eka Care alongside MedAI MCP.

What this evaluates:
  Numerical clinical reasoning. The model has to (1) identify the right
  calculator, (2) extract the right inputs, (3) compute the value. Eka's
  published numbers show this is where the largest tool-use lift sits
  (Sonnet 4.6: 43.6% no-tools → 81.9% with MedAI MCP, +38.3pp).

Many vignettes use Hindi-English ("hinglish_clinical") code-switching prose,
so this also acts as an inadvertent multilingual test.

For each vignette we send {question_text + confinement_instruction} and
expect a JSON response. We extract the `primary_field` value from the
response and compare to the expected value within `tolerance` (relative).

Output: scripts/calculators_results.json
       per-model: accuracy + per-category + per-difficulty + per-language slice.

Usage:
    python3 scripts/benchmark_medical_calculators.py --limit 20 --models claude-haiku
    python3 scripts/benchmark_medical_calculators.py  # full 1,066 across all 12 models
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "calculators_raw"
RAW.mkdir(exist_ok=True)

sys.path.insert(0, str(HERE))
import benchmark_bodhi as bb

OLLAMA_URL = getattr(bb, "OLLAMA_URL", "http://localhost:11434")

MODELS = [
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

SYSTEM = """You are a clinical decision support system. You will receive a clinical \
vignette and must compute a specific medical-calculator value. Follow the \
formatting instruction in the question EXACTLY: if it says reply with ONLY a \
JSON object, do that — no explanation, no markdown, no text outside the JSON."""


_JSON_OBJ_RE = re.compile(r"\{[\s\S]*?\}", re.DOTALL)


def parse_json_from_response(raw: str) -> dict | None:
    """Try several strategies to extract a JSON object from raw model output."""
    if not raw:
        return None
    # Strip qwen / gemma think wrappers
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<unused\d+>.*?<unused\d+>", "", raw, flags=re.DOTALL)
    raw = raw.strip()
    # Strip markdown fences
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    # Try whole string
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Try the largest balanced {...}
    best = None
    depth = 0
    start = -1
    for i, c in enumerate(raw):
        if c == "{":
            if depth == 0:
                start = i
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


def call_model(model: str, backend: str, question: str, confinement: str) -> tuple[str, float]:
    """Send vignette + confinement instruction, return raw response + latency."""
    user = f"{question}\n\n{confinement}"
    t0 = time.time()
    try:
        if backend == "ollama":
            import requests
            payload = {
                "model": model, "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 8192},
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
            }
            if model.startswith("qwen3"):
                payload["think"] = False
            r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=600)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", ""), time.time() - t0
        elif backend == "anthropic":
            import anthropic
            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                return "[ERROR] no ANTHROPIC_API_KEY", time.time() - t0
            r = anthropic.Anthropic(api_key=key).messages.create(
                **bb._anthropic_kwargs(model, temperature=0.1, max_tokens=1024),
                system=SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            return r.content[0].text, time.time() - t0
        elif backend == "openai":
            import openai
            key = os.environ.get("OPENAI_API_KEY")
            if not key:
                return "[ERROR] no OPENAI_API_KEY", time.time() - t0
            is_reasoning = model.startswith(("gpt-5", "o1", "o3", "o4"))
            # Reasoning models need headroom for internal reasoning + JSON output.
            kw = {"max_completion_tokens": 4096} if is_reasoning else {"max_tokens": 1024, "temperature": 0.1}
            r = openai.OpenAI(api_key=key).chat.completions.create(
                model=model, **kw,
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": user}],
            )
            return r.choices[0].message.content or "", time.time() - t0
        else:
            return f"[ERROR] unknown backend {backend}", time.time() - t0
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}", time.time() - t0


def numerical_match(predicted, expected, tolerance: float) -> bool:
    """Check if predicted matches expected within tolerance.

    Tolerance is interpreted as RELATIVE (so 0.01 = 1%). For very small
    expected values we fall back to absolute comparison to avoid div-by-near-0.
    """
    try:
        p = float(predicted)
        e = float(expected)
    except (TypeError, ValueError):
        # Categorical/string match (e.g., risk_category)
        return str(predicted).strip().lower() == str(expected).strip().lower()
    if abs(e) < 1e-6:
        return abs(p - e) <= max(tolerance, 0.01)
    rel = abs(p - e) / abs(e)
    return rel <= tolerance


def score_one(predicted_obj, expected_obj, primary_field: str, tolerance_str: str) -> dict:
    """Return scoring breakdown for one vignette."""
    try:
        tolerance = float(tolerance_str)
    except (TypeError, ValueError):
        tolerance = 0.01

    if predicted_obj is None:
        return {"correct": False, "reason": "no_json_parsed",
                "predicted": None, "expected": expected_obj.get(primary_field) if expected_obj else None}

    p = predicted_obj.get(primary_field)
    if p is None:
        # Try common variants
        for k_alt in [primary_field.lower(), primary_field.replace("_", "")]:
            if k_alt in predicted_obj:
                p = predicted_obj[k_alt]
                break

    e = expected_obj.get(primary_field) if isinstance(expected_obj, dict) else expected_obj
    correct = numerical_match(p, e, tolerance) if p is not None else False
    return {
        "correct": correct,
        "predicted": p,
        "expected": e,
        "tolerance": tolerance,
        "reason": "ok" if correct else ("missing_field" if p is None else "value_mismatch"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--models", nargs="+")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--force", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    from datasets import load_dataset
    ds = load_dataset("ekacare/medical_calculator_eval", split="test")
    rows = list(ds)
    if args.limit > 0:
        import random
        random.Random(args.seed).shuffle(rows)
        rows = rows[:args.limit]
    print(f"Medical Calculator Eval: {len(rows)} vignettes")

    selected = MODELS
    if args.models:
        selected = [(m, b) for m, b in MODELS if any(k in m for k in args.models)]
    print(f"Models: {[m for m, _ in selected]}")

    def safe_path(model: str, qid: str) -> Path:
        safe_m = model.replace(":", "_").replace("/", "_")
        safe_q = qid.replace("/", "_").replace(":", "_")[:80]
        return RAW / f"q__{safe_m}__{safe_q}.json"

    print("\n=== Stage 1: answering ===")
    tasks = [(m, b, r) for m, b in selected for r in rows]
    t0 = time.time()
    done = 0

    def task(m, b, row):
        qid = row.get("id") or f"row{rows.index(row)}"
        path = safe_path(m, qid)
        if not args.force and path.exists():
            return
        raw, lat = call_model(m, b, row.get("question_text") or "",
                              row.get("confinement_instruction") or "")
        path.write_text(json.dumps({
            "model": m, "id": qid, "raw": raw, "latency_s": lat,
            "category": row.get("category"),
            "expected_calculator": row.get("expected_calculator"),
            "primary_field": row.get("primary_field"),
            "primary_field_unit": row.get("primary_field_unit"),
            "difficulty_tier": row.get("difficulty_tier"),
            "language_style": row.get("language_style"),
            "clinical_domain": row.get("clinical_domain"),
            "input_type": row.get("input_type"),
            "expected_output": row.get("expected_output"),
            "tolerance": row.get("tolerance"),
        }, default=str))

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(task, m, b, r) for m, b, r in tasks]
        for fut in as_completed(futs):
            done += 1
            if done % 50 == 0:
                print(f"  [{done}/{len(tasks)} {time.time()-t0:.0f}s]")
    print(f"  done: {done}/{len(tasks)} in {time.time()-t0:.0f}s")

    print("\n=== Stage 2: scoring ===")
    by_model = {}
    for m, _ in selected:
        n_evaluated = 0
        n_correct = 0
        n_parse_fail = 0
        latencies = []
        by_category = defaultdict(lambda: [0, 0])
        by_difficulty = defaultdict(lambda: [0, 0])
        by_language = defaultdict(lambda: [0, 0])
        by_calculator = defaultdict(lambda: [0, 0])

        for row in rows:
            qid = row.get("id") or ""
            path = safe_path(m, qid)
            if not path.exists():
                continue
            d = json.loads(path.read_text())
            raw = d.get("raw", "") or ""
            if raw.startswith("[ERROR]"):
                continue
            n_evaluated += 1
            latencies.append(d.get("latency_s", 0) or 0)

            # Parse expected_output (it's a string in the dataset)
            try:
                expected_obj = json.loads(d.get("expected_output") or "{}")
            except Exception:
                expected_obj = {}
            primary_field = d.get("primary_field") or ""
            tolerance_str = d.get("tolerance") or "0.01"

            predicted_obj = parse_json_from_response(raw)
            if predicted_obj is None:
                n_parse_fail += 1
            score = score_one(predicted_obj, expected_obj, primary_field, tolerance_str)
            ok = score["correct"]
            if ok:
                n_correct += 1

            cat = d.get("category") or "unknown"
            diff = d.get("difficulty_tier") or "unknown"
            lang = d.get("language_style") or "unknown"
            calc = d.get("expected_calculator") or "unknown"
            for bucket, key in [(by_category, cat), (by_difficulty, diff),
                                (by_language, lang), (by_calculator, calc)]:
                bucket[key][1] += 1
                if ok:
                    bucket[key][0] += 1

        acc = round(100 * n_correct / max(n_evaluated, 1), 1)
        median_lat = round(sorted(latencies)[len(latencies)//2], 2) if latencies else None
        by_model[m] = {
            "n_evaluated": n_evaluated,
            "n_correct": n_correct,
            "accuracy": acc,
            "n_parse_fail": n_parse_fail,
            "median_latency_s": median_lat,
            "by_category": {k: {"correct": v[0], "total": v[1],
                                "accuracy": round(100 * v[0] / max(v[1], 1), 1)}
                            for k, v in by_category.items()},
            "by_difficulty": {k: {"correct": v[0], "total": v[1],
                                  "accuracy": round(100 * v[0] / max(v[1], 1), 1)}
                              for k, v in by_difficulty.items()},
            "by_language": {k: {"correct": v[0], "total": v[1],
                                "accuracy": round(100 * v[0] / max(v[1], 1), 1)}
                            for k, v in by_language.items()},
            # Top-N calculators only — there are many
            "by_calculator_top": dict(sorted(
                ({k: {"correct": v[0], "total": v[1],
                      "accuracy": round(100 * v[0] / max(v[1], 1), 1)}
                  for k, v in by_calculator.items()}).items(),
                key=lambda x: -x[1]["total"])[:20]),
        }

    out_path = HERE / "calculators_results.json"
    out_path.write_text(json.dumps({
        "n_vignettes": len(rows),
        "dataset": "ekacare/medical_calculator_eval (test split)",
        "license": "Released by Eka Care, May 2026 — see ekacare HF org",
        "models": by_model,
    }, indent=2, default=str))
    print(f"\nWrote {out_path}")

    print(f"\n  {'Model':<32} {'n':>4}  {'Acc':>6}  {'Lat':>6}  parse-fail")
    for m, info in by_model.items():
        lat = info.get("median_latency_s")
        lat_s = f"{lat:.1f}s" if lat is not None else "—"
        print(f"  {m:<32} {info['n_evaluated']:>4}  {info['accuracy']:>5.1f}%  {lat_s:>6}  {info['n_parse_fail']}")


if __name__ == "__main__":
    main()
