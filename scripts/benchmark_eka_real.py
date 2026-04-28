#!/usr/bin/env python3
"""Real-data benchmark using Eka Care's clinical_note_generation_dataset.

156 real doctor-patient transcripts (EN/Hindi/Marathi), each annotated by
clinicians with a ground-truth structured JSON and ~16 binary rubrics for
LLM-judge evaluation. License: MIT.

Two-stage pipeline:
  1. EXTRACT: each model receives the transcript + the dataset's own
     `sample_prompt` (its bespoke schema) and returns JSON.
  2. JUDGE:   a fixed LLM judge (Opus 4.7 by default) scores the model's
     JSON against the dataset's `rubrics`. Each rubric is binary 0/1.

Per-model score = mean rubric pass rate × 100 (0–100). Per-category breakdown
is also computed from rubric category IDs.

Output: scripts/eka_real_results.json

Usage:
    export ANTHROPIC_API_KEY=... OPENAI_API_KEY=...
    python3 scripts/benchmark_eka_real.py                          # all models, all 156 cases
    python3 scripts/benchmark_eka_real.py --limit 5                # smoke test, 5 cases
    python3 scripts/benchmark_eka_real.py --models opus sonnet     # subset
    python3 scripts/benchmark_eka_real.py --judge gpt-5.4          # cheaper judge
    python3 scripts/benchmark_eka_real.py --concurrency 4

Resumable: per-(model, case) outputs are written to scripts/eka_real_raw/
and reused on subsequent runs unless --force.
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DATA_DIR = HERE / "eka_clinical_note_generation_dataset"
RAW_DIR = HERE / "eka_real_raw"
OUT = HERE / "eka_real_results.json"

# Reuse the extraction backends from the synthetic benchmark.
sys.path.insert(0, str(HERE))
import benchmark_bodhi as bb  # type: ignore

# ── Model registry (matches MODEL_INFO in app.js) ───────────────
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

JUDGE_SYSTEM = """You are a strict but fair clinical-NLP evaluator. You will be given a transcript, a candidate JSON extraction, and a list of binary rubrics. For each rubric, output 1 if the criterion is met (semantic / medical similarity is allowed) and 0 otherwise. Return JSON only."""


# ── "Tight" prompt-mode preamble ─────────────────────────────────
# Prepended before Eka's own sample_prompt. Same schema, but explicit rules
# against schema-artifact failure modes we observed on Qwen 0.8B:
#   - severity / laterality / since defaults filled when not stated
#   - newly-prescribed meds put in `currentMedications` (existing-chronic slot)
#   - dose values placed in `duration` field
#   - duplicate symptom entries
TIGHT_PREAMBLE = """\
CRITICAL EXTRACTION RULES — read before processing:

1. OMIT FIELDS NOT EXPLICITLY STATED. Do NOT fill `severity`, `laterality`, `since`,
   `status`, `details`, or any other field if the transcript does not state it.
   Use empty string "", null, or omit the field entirely. Do NOT guess defaults
   like "Moderate" or "Right".

2. CURRENT vs NEWLY PRESCRIBED MEDICATIONS:
   - `medications` (top level) = drugs prescribed/changed during THIS visit.
   - `medicalHistory.currentMedications` = drugs the patient was ALREADY taking
     before this visit (chronic medications, ongoing therapy).
   - Never put a newly-prescribed drug into currentMedications.

3. CURRENT vs PAST diagnoses:
   - `diagnosis` = the condition addressed in THIS visit.
   - `medicalHistory.patientHistory.patientMedicalConditions` = past/historical
     conditions the patient has had previously.
   - Never put the current visit's diagnosis into patientHistory.

4. FIELD MEANING:
   - `dose` = strength per unit (e.g. "500 mg", "1 tablet")
   - `duration` = how long the patient takes the med (e.g. "1 month", "7 days")
   - Do NOT put a dose value in the duration field, or vice versa.

5. DO NOT DUPLICATE entries. One entry per distinct symptom / medication / diagnosis.

6. SYMPTOM vs DIAGNOSIS: a symptom is what the patient feels (pain, fever,
   tingling, fatigue). A diagnosis is a clinical label (Diabetes, Hypertension,
   Migraine). Do not list a diagnosis in the `symptoms` array.

When a field is genuinely not present in the transcript, it is BETTER to omit
it than to guess a plausible default. Sparse but accurate outputs are preferred
over verbose-and-wrong.

---

"""

PRECISION_JUDGE_SYSTEM = """You are a strict clinical-NLP evaluator scoring extraction PRECISION (the inverse problem from recall). You will be given a transcript and a candidate JSON extraction. Enumerate every distinct clinical claim in the candidate (each medication entry, each diagnosis, each prescribed test, each symptom, each vital sign, each examination finding, each piece of medical advice) and judge whether the transcript SUPPORTS that specific claim.

Rules:
- A claim is SUPPORTED (1) if the transcript clearly mentions or implies it. Allow medical synonyms (HTN = Hypertension, PCM = Paracetamol).
- A claim is UNSUPPORTED (0) if the transcript does not mention it OR contradicts it OR specifies a different value (e.g. transcript says "twice daily" but candidate says "once daily").
- Empty / null / placeholder values do NOT count as claims.
- Be strict on numeric values: dose, frequency, vitals.
- Treat the transcript as the only source of truth.

Return JSON only with this shape:
{
  "claims": [
    {"path": "medications[0].name", "value": "Paracetamol 500mg", "supported": 1, "note": "transcript mentions 'paracetamol 500'"},
    {"path": "medications[0].dose", "value": "1 tablet", "supported": 1},
    {"path": "diagnoses[0].name", "value": "Hypertension", "supported": 0, "note": "not mentioned in transcript"}
  ],
  "summary": {"total_claims": N, "supported": M}
}
"""


def load_dataset() -> list[dict]:
    """Load both Parquet shards and return a list of {session_id, text, sample_prompt, rubrics}."""
    try:
        import pandas as pd
    except ImportError:
        sys.exit("pandas required. pip install pandas pyarrow")
    files = sorted(DATA_DIR.glob("test-*.parquet"))
    if not files:
        sys.exit(f"No parquet files at {DATA_DIR}")
    df = None
    for f in files:
        d = pd.read_parquet(f)
        df = d if df is None else __import__("pandas").concat([df, d], ignore_index=True)
    return df.to_dict(orient="records")


def parse_rubrics(rubric_text: str) -> list[dict]:
    """Extract individual rubrics from the rubric prompt block.
    Returns a list of {id, category, criterion}."""
    out = []
    pat = re.compile(
        r"Rubric ID:\s*(\d+)\s*\n"
        r"Category ID:\s*(\S+)\s*\n"
        r"Criterion:\s*(.+?)(?=\n\n|$)",
        re.DOTALL,
    )
    for m in pat.finditer(rubric_text):
        out.append({"id": m.group(1), "category": m.group(2), "criterion": m.group(3).strip()})
    return out


def extract_one(model: str, backend: str, transcript: str, system: str, user_prompt: str,
                max_tokens: int = 4096) -> tuple[dict | None, str, float]:
    """Generic extraction: send (system, user) to the model. Returns (parsed_dict|None, raw, latency_s)."""
    t0 = time.time()
    try:
        if backend == "ollama":
            import requests
            r = requests.post(f"{bb.OLLAMA_URL}/api/chat", json={
                "model": model, "stream": False, "options": bb.EXTRACT_OPTIONS,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": "<think>\n</think>\n"},
                ],
            }, timeout=180)
            r.raise_for_status()
            raw = r.json().get("message", {}).get("content", "")
        elif backend == "anthropic":
            import anthropic
            r = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = r.content[0].text
        elif backend == "openai":
            import openai
            kw = {"max_completion_tokens": max_tokens} if model.startswith(("gpt-5", "o1", "o3", "o4")) else {"max_tokens": max_tokens}
            r = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(
                model=model, **kw,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user_prompt}],
            )
            raw = r.choices[0].message.content or ""
        else:
            return None, f"[unknown backend: {backend}]", 0
        return bb._parse_json(raw), raw, time.time() - t0
    except Exception as e:
        return None, f"[ERROR] {str(e)[:200]}", time.time() - t0


def call_judge(judge_model: str, transcript: str, candidate: str,
               rubrics_text: str, max_retries: int = 2) -> dict | None:
    """Score `candidate` against `rubrics_text` using `judge_model`. Returns
    {"rubric_scores": {"1": 0/1, ...}} or None on failure."""
    user = (
        "TRANSCRIPT:\n" + transcript[:6000] + "\n\n"
        + "CANDIDATE JSON:\n" + (candidate or "(empty)")[:6000] + "\n\n"
        + rubrics_text
    )
    for attempt in range(max_retries):
        try:
            import anthropic
            r = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(
                model=judge_model, max_tokens=2000, system=JUDGE_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            text = r.content[0].text
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try: return json.loads(m.group())
                except json.JSONDecodeError: pass
        except Exception as e:
            if attempt == max_retries - 1:
                return {"_error": str(e)[:200]}
            time.sleep(1.0 * (attempt + 1))
    return None


def call_precision_judge(judge_model: str, transcript: str, candidate: str,
                         max_retries: int = 2) -> dict | None:
    """Score the candidate JSON for precision: every claim → supported (1) or not (0)."""
    if not candidate or not candidate.strip():
        return {"claims": [], "summary": {"total_claims": 0, "supported": 0}}
    user = (
        "TRANSCRIPT:\n" + transcript[:6000] + "\n\n"
        + "CANDIDATE JSON:\n" + candidate[:8000] + "\n\n"
        + "Enumerate every distinct clinical claim in the candidate JSON and judge each against the transcript. Be strict on numeric values."
    )
    for attempt in range(max_retries):
        try:
            import anthropic
            r = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(
                model=judge_model, max_tokens=4000, system=PRECISION_JUDGE_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            text = r.content[0].text
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try: return json.loads(m.group())
                except json.JSONDecodeError: pass
        except Exception as e:
            if attempt == max_retries - 1:
                return {"_error": str(e)[:200]}
            time.sleep(1.0 * (attempt + 1))
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0, help="Cap to N cases (0 = all)")
    p.add_argument("--models", nargs="+", help="Substring match on model name")
    p.add_argument("--judge", default="claude-opus-4-7")
    p.add_argument("--prompt-mode", choices=["eka", "tight", "chartlite", "chartlite_clean"], default="eka",
                   help="eka = use the dataset's own sample_prompt as-is; "
                        "tight = prepend omission preamble (small-model attempt); "
                        "chartlite = ChartLite's tight 8-field schema (legacy: had verbatim example values that small models leaked); "
                        "chartlite_clean = ChartLite v2 — examples removed, fixes the verbatim-leak failure mode on Qwen 0.8B / 2B")
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--force", action="store_true", help="Re-extract / re-judge even if cached")
    p.add_argument("--skip-extract", action="store_true", help="Use cached extractions; only run judge")
    p.add_argument("--skip-judge", action="store_true", help="Run extractions only; no judge")
    args = p.parse_args()

    cases = load_dataset()
    if args.limit > 0:
        cases = cases[: args.limit]
    print(f"Cases: {len(cases)}")

    selected = MODELS
    if args.models:
        sel = []
        for m, b in MODELS:
            if any(k in m for k in args.models): sel.append((m, b))
        selected = sel
    print(f"Models: {[m for m, _ in selected]}")
    print(f"Judge:  {args.judge}")

    RAW_DIR.mkdir(exist_ok=True)

    # ── Stage 1: extract ───────────────────────────────────────
    pm_suffix = "" if args.prompt_mode == "eka" else f"_{args.prompt_mode}"
    def extract_task(model, backend, case):
        sid = case["session_id"]
        mclean = model.replace('/', '_').replace(':', '_')
        path = RAW_DIR / f"extract{pm_suffix}__{mclean}__{sid}.json"
        if not args.force and path.exists():
            return json.loads(path.read_text())
        # Build prompt according to selected mode
        if args.prompt_mode == "chartlite" or args.prompt_mode == "chartlite_clean":
            # ChartLite's tight 8-field schema, identical to the synthetic benchmark.
            system = bb.EXTRACT_SYSTEM
            user_prompt = bb.EXTRACT_USER.format(schema=bb.EXTRACT_SCHEMA, transcript=case["text"])
        elif args.prompt_mode == "tight":
            base_prompt = case["sample_prompt"]
            system = base_prompt.split("JSON schema:")[0].strip()
            user_prompt = TIGHT_PREAMBLE + case["text"] + "\n\n" + base_prompt
        else:  # eka
            base_prompt = case["sample_prompt"]
            system = base_prompt.split("JSON schema:")[0].strip()
            user_prompt = case["text"] + "\n\n" + base_prompt
        parsed, raw, lat = extract_one(model, backend, case["text"], system, user_prompt)
        out = {"model": model, "backend": backend, "session_id": sid,
               "prompt_mode": args.prompt_mode,
               "raw": raw, "parsed_present": parsed is not None, "latency_s": lat}
        path.write_text(json.dumps(out, indent=2, default=str))
        return out

    if not args.skip_extract:
        print("\n=== Stage 1: extraction ===")
        tasks = [(m, b, c) for m, b in selected for c in cases]
        t0 = time.time()
        done = 0
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = {ex.submit(extract_task, m, b, c): (m, c["session_id"]) for m, b, c in tasks}
            for fut in as_completed(futs):
                done += 1
                m, sid = futs[fut]
                try: r = fut.result()
                except Exception as e: print(f"  [extract fail] {m}/{sid}: {e}")
                if done % 25 == 0:
                    print(f"  [{done}/{len(tasks)} extracts, {time.time()-t0:.0f}s]")
        print(f"  extraction done: {done}/{len(tasks)} in {time.time()-t0:.0f}s")

    # ── Stage 2: judge ─────────────────────────────────────────
    def judge_task(model, case):
        sid = case["session_id"]
        mclean = model.replace('/', '_').replace(':', '_')
        path = RAW_DIR / f"judge{pm_suffix}__{mclean}__{sid}.json"
        if not args.force and path.exists():
            return json.loads(path.read_text())
        ext_path = RAW_DIR / f"extract{pm_suffix}__{mclean}__{sid}.json"
        if not ext_path.exists():
            return {"model": model, "session_id": sid, "_error": "no extraction"}
        ext = json.loads(ext_path.read_text())
        scores = call_judge(args.judge, case["text"], ext.get("raw", ""),
                            case["rubrics"])
        out = {"model": model, "session_id": sid, "judge": args.judge,
               "prompt_mode": args.prompt_mode,
               "scores": scores, "n_rubrics": len(parse_rubrics(case["rubrics"]))}
        path.write_text(json.dumps(out, indent=2, default=str))
        return out

    if not args.skip_judge:
        print("\n=== Stage 2: judge (recall — rubric pass rate) ===")
        tasks = [(m, c) for m, _ in selected for c in cases]
        t0 = time.time()
        done = 0
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = {ex.submit(judge_task, m, c): (m, c["session_id"]) for m, c in tasks}
            for fut in as_completed(futs):
                done += 1
                if done % 25 == 0:
                    print(f"  [{done}/{len(tasks)} judges, {time.time()-t0:.0f}s]")
        print(f"  judging done: {done}/{len(tasks)} in {time.time()-t0:.0f}s")

    # ── Stage 3: precision judge ──────────────────────────────
    def precision_task(model, case):
        sid = case["session_id"]
        mclean = model.replace('/', '_').replace(':', '_')
        path = RAW_DIR / f"precision{pm_suffix}__{mclean}__{sid}.json"
        if not args.force and path.exists():
            return json.loads(path.read_text())
        ext_path = RAW_DIR / f"extract{pm_suffix}__{mclean}__{sid}.json"
        if not ext_path.exists():
            return {"model": model, "session_id": sid, "_error": "no extraction"}
        ext = json.loads(ext_path.read_text())
        result = call_precision_judge(args.judge, case["text"], ext.get("raw", ""))
        out = {"model": model, "session_id": sid, "judge": args.judge,
               "prompt_mode": args.prompt_mode, "precision": result}
        path.write_text(json.dumps(out, indent=2, default=str))
        return out

    if not args.skip_judge:
        print("\n=== Stage 3: precision judge (claims supported by transcript) ===")
        tasks = [(m, c) for m, _ in selected for c in cases]
        t0 = time.time()
        done = 0
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = {ex.submit(precision_task, m, c): (m, c["session_id"]) for m, c in tasks}
            for fut in as_completed(futs):
                done += 1
                if done % 25 == 0:
                    print(f"  [{done}/{len(tasks)} precision judges, {time.time()-t0:.0f}s]")
        print(f"  precision done: {done}/{len(tasks)} in {time.time()-t0:.0f}s")

    # ── Aggregate ──────────────────────────────────────────────
    print("\n=== Aggregating ===")
    rubric_lookup = {}
    for c in cases:
        rubric_lookup[c["session_id"]] = parse_rubrics(c["rubrics"])

    by_model = {}
    for m, _ in selected:
        cat_pass, cat_total = {}, {}
        n_rubrics_seen = 0
        n_passed = 0
        n_cases_with_judge = 0
        # Precision aggregates
        n_prec_total, n_prec_supported, n_cases_with_prec = 0, 0, 0
        for c in cases:
            sid = c["session_id"]
            mclean = m.replace('/', '_').replace(':', '_')
            judge_path = RAW_DIR / f"judge{pm_suffix}__{mclean}__{sid}.json"
            if judge_path.exists():
                jd = json.loads(judge_path.read_text())
                scores = ((jd.get("scores") or {}).get("rubric_scores")) or {}
                if scores:
                    n_cases_with_judge += 1
                    for rb in rubric_lookup.get(sid, []):
                        rid, cat = rb["id"], rb["category"]
                        v = scores.get(rid)
                        if v is None: continue
                        n_rubrics_seen += 1
                        cat_total[cat] = cat_total.get(cat, 0) + 1
                        if int(v) >= 1:
                            n_passed += 1
                            cat_pass[cat] = cat_pass.get(cat, 0) + 1
            # Precision
            prec_path = RAW_DIR / f"precision{pm_suffix}__{mclean}__{sid}.json"
            if prec_path.exists():
                pd_ = json.loads(prec_path.read_text())
                prec = pd_.get("precision") or {}
                summ = (prec.get("summary") or {})
                if summ.get("total_claims") is not None:
                    n_cases_with_prec += 1
                    n_prec_total += summ.get("total_claims", 0)
                    n_prec_supported += summ.get("supported", 0)
        recall = round(100 * n_passed / max(1, n_rubrics_seen), 1) if n_rubrics_seen else None
        precision = round(100 * n_prec_supported / max(1, n_prec_total), 1) if n_prec_total else None
        f1 = None
        if recall is not None and precision is not None and (precision + recall) > 0:
            f1 = round(2 * precision * recall / (precision + recall), 1)
        by_model[m] = {
            "model": m,
            "n_cases_with_judge": n_cases_with_judge,
            "n_cases_with_precision": n_cases_with_prec,
            "n_rubrics_total": n_rubrics_seen,
            "n_passed": n_passed,
            "n_claims_total": n_prec_total,
            "n_claims_supported": n_prec_supported,
            "recall": recall,
            "precision": precision,
            "f1": f1,
            "by_category": {
                cat: {"passed": cat_pass.get(cat, 0), "total": cat_total[cat],
                      "rate": round(100 * cat_pass.get(cat, 0) / cat_total[cat], 1)}
                for cat in sorted(cat_total)
            },
        }

    out = {
        "dataset": "ekacare/clinical_note_generation_dataset",
        "n_cases": len(cases),
        "judge": args.judge,
        "models": list(by_model.values()),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {OUT}")
    print(f"  {'Model':32s}  Recall  Prec.   F1     (claims supp/total)")
    for m in by_model.values():
        rec = f"{m['recall']:5.1f}%" if m['recall'] is not None else "  —  "
        prc = f"{m['precision']:5.1f}%" if m['precision'] is not None else "  —  "
        f1  = f"{m['f1']:5.1f}"   if m['f1']  is not None else "  —  "
        print(f"  {m['model']:32s}  {rec}  {prc}  {f1}  ({m['n_claims_supported']}/{m['n_claims_total']})")


if __name__ == "__main__":
    main()
