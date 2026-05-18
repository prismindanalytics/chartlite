#!/usr/bin/env python3
"""ACI-Bench benchmark — dialogue → clinical-note evaluation.

Source: Yim et al., "ACI-BENCH: a Novel Ambient Clinical Intelligence Dataset
for Benchmarking Automatic Visit Note Generation", Nature Scientific Data 2023.
Licence: CC BY 4.0.

Pipeline (mirrors benchmark_eka_real.py shape so the dashboard can adopt it):
  1. Extraction stage: feed the dialogue to each model with our chartlite or
     eka prompt; collect the raw extraction.
  2. Note-generation stage: feed the dialogue to each model and ask for a
     SOAP-style clinical note (using bb.NOTE_SYSTEM).
  3. Judge stage: Opus 4.7 LLM-judge scores both the generated extraction
     against the reference note (entity-level recall) AND the generated note
     against the reference note (4 axes: SOAP completeness, hallucination,
     clinical reasoning, plan appropriateness — same rubric as the synthetic
     3-judge panel).

Usage:
    bash scripts/fetch_aci_bench.sh    # one-time data download
    python3 scripts/benchmark_aci.py --split valid --models gpt-5.5 qwen3.5:9b
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "aci_bench" / "aci-bench-corpus" / "challenge_data"
RAW = HERE / "aci_bench_raw"
RAW.mkdir(exist_ok=True)

sys.path.insert(0, str(HERE))
import benchmark_bodhi as bb

SPLITS = {
    "train": DATA / "train.csv",
    "valid": DATA / "valid.csv",
    "test1": DATA / "clinicalnlp_taskB_test1.csv",
    "test2": DATA / "clinicalnlp_taskC_test2.csv",
    "test3": DATA / "clef_taskC_test3.csv",
}

# Same model menu we use elsewhere — registry shared with benchmark_eka_real.py.
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

NOTE_JUDGE_SYSTEM = """You score AI-generated clinical notes against a clinician-written reference.
Output ONLY JSON with this shape:
{
  "soap_completeness": 0-100,    // does it cover all SOAP sections present in the reference?
  "factual_consistency": 0-100,  // 100 = no hallucinated facts vs reference; 0 = pervasive
  "clinical_reasoning": 0-100,   // does Assessment tie findings to dx with reasoning?
  "plan_appropriateness": 0-100, // is Plan actionable, right meds/dose/follow-up?
  "overall": 0-100,
  "notes": "one-sentence critique"
}
Be strict. 70-85 = good-but-imperfect, 85-95 = strong, 95+ = near-perfect.
"""


def load_split(name: str, limit: int = 0) -> pd.DataFrame:
    df = pd.read_csv(SPLITS[name])
    if limit > 0:
        df = df.head(limit)
    return df


def call_extract(model: str, backend: str, dialogue: str) -> tuple[str, float]:
    """Run extraction. Reuses the chartlite prompt from benchmark_bodhi.py."""
    t0 = time.time()
    try:
        if backend == "ollama":
            import requests
            r = requests.post(f"{bb.OLLAMA_URL}/api/chat", json={
                "model": model, "stream": False, "options": bb.EXTRACT_OPTIONS,
                "messages": [
                    {"role": "system", "content": bb.EXTRACT_SYSTEM},
                    {"role": "user", "content": bb.EXTRACT_USER.format(
                        schema=bb.EXTRACT_SCHEMA, transcript=dialogue)},
                ],
            }, timeout=600)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", ""), time.time() - t0
        elif backend == "anthropic":
            import anthropic
            r = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(
                **bb._anthropic_kwargs(model, temperature=0.1),
                system=bb.EXTRACT_SYSTEM,
                messages=[{"role": "user", "content": bb.EXTRACT_USER.format(
                    schema=bb.EXTRACT_SCHEMA, transcript=dialogue)}],
            )
            return r.content[0].text, time.time() - t0
        elif backend == "openai":
            import openai
            is_reasoning = model.startswith(("gpt-5", "o1", "o3", "o4"))
            kw = {"max_completion_tokens": 4096} if is_reasoning else {"max_tokens": 4096, "temperature": 0.1}
            r = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(
                model=model, **kw,
                messages=[{"role": "system", "content": bb.EXTRACT_SYSTEM},
                          {"role": "user", "content": bb.EXTRACT_USER.format(
                              schema=bb.EXTRACT_SCHEMA, transcript=dialogue)}],
            )
            return r.choices[0].message.content, time.time() - t0
    except Exception as e:
        return f"[ERROR] {e}", time.time() - t0


def call_note(model: str, backend: str, dialogue: str) -> tuple[str, float]:
    """Run note generation."""
    t0 = time.time()
    try:
        if backend == "ollama":
            import requests
            # Disable thinking-mode for qwen3 — by default qwen3 models route all
            # output into `message.thinking` and leave `message.content` empty on
            # long open-ended prompts (ACI dialogues), which makes the response
            # ungradable. think:false routes everything to `content`.
            payload = {
                "model": model, "stream": False, "options": bb.EXTRACT_OPTIONS,
                "messages": [
                    {"role": "system", "content": bb.NOTE_SYSTEM},
                    {"role": "user", "content": bb.NOTE_USER.format(transcript=dialogue)},
                ],
            }
            if model.startswith("qwen3"):
                payload["think"] = False
            r = requests.post(f"{bb.OLLAMA_URL}/api/chat", json=payload, timeout=600)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", ""), time.time() - t0
        elif backend == "anthropic":
            import anthropic
            r = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(
                **bb._anthropic_kwargs(model, temperature=0.3),
                system=bb.NOTE_SYSTEM,
                messages=[{"role": "user", "content": bb.NOTE_USER.format(transcript=dialogue)}],
            )
            return r.content[0].text, time.time() - t0
        elif backend == "openai":
            import openai
            is_reasoning = model.startswith(("gpt-5", "o1", "o3", "o4"))
            kw = {"max_completion_tokens": 4096} if is_reasoning else {"max_tokens": 4096, "temperature": 0.3}
            r = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(
                model=model, **kw,
                messages=[{"role": "system", "content": bb.NOTE_SYSTEM},
                          {"role": "user", "content": bb.NOTE_USER.format(transcript=dialogue)}],
            )
            return r.choices[0].message.content, time.time() - t0
    except Exception as e:
        return f"[ERROR] {e}", time.time() - t0


def call_note_judge(judge_model: str, reference_note: str, candidate_note: str) -> dict | None:
    import anthropic
    user = (
        f"REFERENCE clinical note (clinician-written):\n{reference_note}\n\n"
        f"CANDIDATE clinical note (AI-generated):\n{candidate_note}\n\n"
        "Score the candidate vs the reference. Output JSON only."
    )
    try:
        r = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]).messages.create(
            model=judge_model, max_tokens=600, system=NOTE_JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        m = re.search(r"\{[\s\S]*\}", r.content[0].text)
        return json.loads(m.group()) if m else None
    except Exception as e:
        return {"_error": str(e)[:200]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="valid", choices=list(SPLITS.keys()))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--models", nargs="+")
    p.add_argument("--judge", default="claude-opus-4-7")
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--force", action="store_true")
    p.add_argument("--skip-extract", action="store_true")
    p.add_argument("--skip-note", action="store_true")
    p.add_argument("--skip-judge", action="store_true")
    args = p.parse_args()

    df = load_split(args.split, args.limit)
    cases = df.to_dict("records")
    print(f"Split {args.split}: {len(cases)} cases")

    selected = MODELS
    if args.models:
        selected = [(m, b) for m, b in MODELS if any(k in m for k in args.models)]
    print(f"Models: {[m for m, _ in selected]}")
    print(f"Judge:  {args.judge}")

    def safe_id(model: str, encounter: str) -> Path:
        return RAW / f"__{model.replace(':', '_').replace('/', '_')}__{encounter}__{args.split}.json"

    # Stage 1: extraction
    if not args.skip_extract:
        print("\n=== Stage 1: extraction ===")
        tasks = [(m, b, c) for m, b in selected for c in cases]
        t0 = time.time()
        done = 0
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            def task(m, b, c):
                eid = c["encounter_id"]
                path = safe_id(m, eid).with_name(f"extract{safe_id(m, eid).name}")
                if not args.force and path.exists():
                    return
                raw, lat = call_extract(m, b, c["dialogue"])
                path.write_text(json.dumps({
                    "model": m, "encounter_id": eid, "split": args.split,
                    "raw": raw, "latency_s": lat,
                }, default=str))
            futs = {ex.submit(task, m, b, c): (m, c["encounter_id"]) for m, b, c in tasks}
            for fut in as_completed(futs):
                done += 1
                if done % 25 == 0:
                    print(f"  [{done}/{len(tasks)} extracts, {time.time()-t0:.0f}s]")
        print(f"  extraction done: {done}/{len(tasks)} in {time.time()-t0:.0f}s")

    # Stage 2: note generation
    if not args.skip_note:
        print("\n=== Stage 2: note generation ===")
        tasks = [(m, b, c) for m, b in selected for c in cases]
        t0 = time.time()
        done = 0
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            def task(m, b, c):
                eid = c["encounter_id"]
                path = safe_id(m, eid).with_name(f"note{safe_id(m, eid).name}")
                if not args.force and path.exists():
                    return
                raw, lat = call_note(m, b, c["dialogue"])
                path.write_text(json.dumps({
                    "model": m, "encounter_id": eid, "split": args.split,
                    "raw": raw, "latency_s": lat,
                }, default=str))
            futs = {ex.submit(task, m, b, c): (m, c["encounter_id"]) for m, b, c in tasks}
            for fut in as_completed(futs):
                done += 1
                if done % 25 == 0:
                    print(f"  [{done}/{len(tasks)} notes, {time.time()-t0:.0f}s]")
        print(f"  note generation done: {done}/{len(tasks)} in {time.time()-t0:.0f}s")

    # Stage 3: judge notes against reference
    if not args.skip_judge:
        print("\n=== Stage 3: judge (note quality vs reference) ===")
        case_index = {c["encounter_id"]: c for c in cases}
        tasks = [(m, c) for m, _ in selected for c in cases]
        t0 = time.time()
        done = 0
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            def task(m, c):
                eid = c["encounter_id"]
                jpath = safe_id(m, eid).with_name(f"judge{safe_id(m, eid).name}")
                if not args.force and jpath.exists():
                    return
                npath = safe_id(m, eid).with_name(f"note{safe_id(m, eid).name}")
                if not npath.exists(): return
                cand = json.loads(npath.read_text()).get("raw", "")
                if not cand or cand.startswith("[ERROR]"): return
                scores = call_note_judge(args.judge, c["note"], cand)
                jpath.write_text(json.dumps({
                    "model": m, "encounter_id": eid, "split": args.split,
                    "judge": args.judge, "scores": scores,
                }, default=str))
            futs = {ex.submit(task, m, c): (m, c["encounter_id"]) for m, c in tasks}
            for fut in as_completed(futs):
                done += 1
                if done % 25 == 0:
                    print(f"  [{done}/{len(tasks)} judges, {time.time()-t0:.0f}s]")
        print(f"  judging done: {done}/{len(tasks)} in {time.time()-t0:.0f}s")

    # Aggregate
    print("\n=== Aggregating ===")
    by_model = {}
    for m, _ in selected:
        scores_overall = []
        scores_complete = []
        scores_factual = []
        scores_reasoning = []
        scores_plan = []
        for c in cases:
            eid = c["encounter_id"]
            jpath = safe_id(m, eid).with_name(f"judge{safe_id(m, eid).name}")
            if not jpath.exists(): continue
            sc = json.loads(jpath.read_text()).get("scores") or {}
            if "_error" in sc: continue
            for src, dst in [("overall", scores_overall), ("soap_completeness", scores_complete),
                             ("factual_consistency", scores_factual), ("clinical_reasoning", scores_reasoning),
                             ("plan_appropriateness", scores_plan)]:
                v = sc.get(src)
                if isinstance(v, (int, float)):
                    dst.append(v)
        n = len(scores_overall)
        if not n: continue
        by_model[m] = {
            "n_judged": n,
            "overall": round(sum(scores_overall) / n, 1),
            "soap_completeness": round(sum(scores_complete) / max(1, len(scores_complete)), 1),
            "factual_consistency": round(sum(scores_factual) / max(1, len(scores_factual)), 1),
            "clinical_reasoning": round(sum(scores_reasoning) / max(1, len(scores_reasoning)), 1),
            "plan_appropriateness": round(sum(scores_plan) / max(1, len(scores_plan)), 1),
        }

    out_path = HERE / f"aci_results_{args.split}.json"
    out_path.write_text(json.dumps({
        "split": args.split, "n_cases": len(cases),
        "judge": args.judge, "models": by_model,
    }, indent=2, default=str))
    print(f"Wrote {out_path}")
    print(f"\n  Model                          n   Overall  SOAP  Factual  Reason  Plan")
    for m, s in sorted(by_model.items(), key=lambda x: -x[1]["overall"]):
        print(f"  {m:30s}  {s['n_judged']:>3}  {s['overall']:>7.1f}  "
              f"{s['soap_completeness']:>4.0f}  {s['factual_consistency']:>7.0f}  "
              f"{s['clinical_reasoning']:>6.0f}  {s['plan_appropriateness']:>4.0f}")


if __name__ == "__main__":
    main()
