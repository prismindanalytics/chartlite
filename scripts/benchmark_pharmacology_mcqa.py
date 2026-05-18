#!/usr/bin/env python3
"""NFI Pharmacology MCQA benchmark.

Source: ekacare/Eka_NFI_MCQA on Hugging Face — 925 multiple-choice questions
covering mechanisms, indications, contraindications, dosing, and adverse
effects, drawn from India's National Formulary (NFI) 2011 by Eka Care.
Released May 2026 alongside the MedAI MCP tools announcement.

What this evaluates:
  Pure clinical-knowledge axis. Tests whether each model can pick the right
  pharmacology answer from 5 options without any tools. Complements the
  CRESCENDDI safety arm (drug-drug) and the synthetic 100 (extraction +
  triage).

For each question we send {question, options A/B/C/D/E} and ask for one
letter. Score is exact match. We also break down by:
  * category (contraindications, dosing, mechanism, etc.)
  * difficulty (easy/medium/hard)
  * question_type

Output: scripts/pharmacology_results.json
       per-model: accuracy + sliced metrics + per-question outcome counts.

Usage:
    python3 scripts/benchmark_pharmacology_mcqa.py --limit 20 --models claude-haiku
    python3 scripts/benchmark_pharmacology_mcqa.py  # full 925 across all 12 models
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "pharmacology_raw"
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

SYSTEM = """You are a clinical pharmacist answering multiple-choice questions \
on the National Formulary of India 2011. Each question has options A, B, C, D, E. \
Choose the single best answer. Reply with EXACTLY one capital letter \
(A, B, C, D, or E) — no explanation, no punctuation, nothing else."""

USER_TEMPLATE = """Question: {question}

Options:
{options_text}

Answer with only the letter of the correct option."""


def fmt_options(options_json_str: str) -> str:
    try:
        opts = json.loads(options_json_str)
    except Exception:
        return options_json_str
    return "\n".join(f"{k}. {v}" for k, v in sorted(opts.items()))


def parse_answer(raw: str) -> str | None:
    """Extract first standalone capital letter A-E from response."""
    if not raw:
        return None
    # Strip qwen-style think tags
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<unused\d+>.*?<unused\d+>", "", raw, flags=re.DOTALL)
    raw = raw.strip()
    # Most-restrictive: first character is a single letter
    m = re.match(r"^\s*([A-E])\b", raw)
    if m:
        return m.group(1)
    # Fallback: any standalone A-E in the response
    m = re.search(r"\b([A-E])\b", raw)
    if m:
        return m.group(1)
    # Final fallback: any A-E anywhere (handles lowercase too)
    m = re.search(r"([A-Ea-e])", raw)
    return m.group(1).upper() if m else None


def call_model(model: str, backend: str, question: str, options_text: str) -> tuple[str, float]:
    """Send question, return raw response + latency."""
    user = USER_TEMPLATE.format(question=question, options_text=options_text)
    t0 = time.time()
    try:
        if backend == "ollama":
            import requests
            payload = {
                "model": model, "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 4096},
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
            }
            # qwen3 routes content into `thinking` field on long prompts
            if model.startswith("qwen3"):
                payload["think"] = False
            r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", ""), time.time() - t0
        elif backend == "anthropic":
            import anthropic
            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                return "[ERROR] no ANTHROPIC_API_KEY", time.time() - t0
            r = anthropic.Anthropic(api_key=key).messages.create(
                **bb._anthropic_kwargs(model, temperature=0.1, max_tokens=10),
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
            # Reasoning models burn budget on internal reasoning; give them
            # plenty of room before the single-letter answer.
            kw = {"max_completion_tokens": 1024} if is_reasoning else {"max_tokens": 10, "temperature": 0.1}
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0,
                   help="Cap to N questions for smoke (0 = all 925).")
    p.add_argument("--models", nargs="+",
                   help="Substring match against model names.")
    p.add_argument("--concurrency", type=int, default=4,
                   help="Cloud models 4 OK; on-device set --concurrency 1.")
    p.add_argument("--force", action="store_true",
                   help="Re-run even if cached file exists.")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    # Load dataset
    from datasets import load_dataset
    ds = load_dataset("ekacare/Eka_NFI_MCQA", split="test")
    rows = list(ds)
    if args.limit > 0:
        import random
        random.Random(args.seed).shuffle(rows)
        rows = rows[:args.limit]
    print(f"Pharmacology MCQA: {len(rows)} questions")

    # Filter models
    selected = MODELS
    if args.models:
        selected = [(m, b) for m, b in MODELS if any(k in m for k in args.models)]
    print(f"Models: {[m for m, _ in selected]}")

    # Output paths
    def safe_path(model: str, qid: int) -> Path:
        safe = model.replace(":", "_").replace("/", "_")
        return RAW / f"q__{safe}__{qid:04d}.json"

    # Stage 1 — answer each question
    print("\n=== Stage 1: answering ===")
    tasks = [(m, b, i, r) for m, b in selected for i, r in enumerate(rows)]
    t0 = time.time()
    done = 0

    def task(m, b, i, row):
        path = safe_path(m, i)
        if not args.force and path.exists():
            return
        question = row.get("question") or ""
        options_text = fmt_options(row.get("options") or "{}")
        raw, lat = call_model(m, b, question, options_text)
        path.write_text(json.dumps({
            "model": m, "qid": i, "raw": raw, "latency_s": lat,
            "expected": row.get("answer"),
            "category": row.get("category"),
            "difficulty": row.get("difficulty"),
            "question_type": row.get("question_type"),
        }, default=str))

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(task, m, b, i, r) for m, b, i, r in tasks]
        for fut in as_completed(futs):
            done += 1
            if done % 50 == 0:
                print(f"  [{done}/{len(tasks)} {time.time()-t0:.0f}s]")
    print(f"  done: {done}/{len(tasks)} in {time.time()-t0:.0f}s")

    # Stage 2 — score
    print("\n=== Stage 2: scoring ===")
    by_model = {}
    for m, _ in selected:
        n_evaluated = 0
        n_correct = 0
        by_category = defaultdict(lambda: [0, 0])  # [correct, total]
        by_difficulty = defaultdict(lambda: [0, 0])
        by_question_type = defaultdict(lambda: [0, 0])
        latencies = []
        n_parse_fail = 0

        for i, row in enumerate(rows):
            path = safe_path(m, i)
            if not path.exists():
                continue
            d = json.loads(path.read_text())
            raw = d.get("raw", "") or ""
            expected = d.get("expected", "")
            if raw.startswith("[ERROR]"):
                continue
            n_evaluated += 1
            latencies.append(d.get("latency_s", 0) or 0)
            picked = parse_answer(raw)
            if picked is None:
                n_parse_fail += 1
                ok = False
            else:
                ok = (picked == expected)
            if ok:
                n_correct += 1
            cat = d.get("category") or "unknown"
            diff = d.get("difficulty") or "unknown"
            qt = d.get("question_type") or "unknown"
            by_category[cat][1] += 1
            by_difficulty[diff][1] += 1
            by_question_type[qt][1] += 1
            if ok:
                by_category[cat][0] += 1
                by_difficulty[diff][0] += 1
                by_question_type[qt][0] += 1

        acc = round(100 * n_correct / max(n_evaluated, 1), 1)
        by_model[m] = {
            "n_evaluated": n_evaluated,
            "n_correct": n_correct,
            "accuracy": acc,
            "n_parse_fail": n_parse_fail,
            "median_latency_s": round(sorted(latencies)[len(latencies)//2], 2) if latencies else None,
            "by_category": {k: {"correct": v[0], "total": v[1],
                                "accuracy": round(100 * v[0] / max(v[1], 1), 1)}
                            for k, v in by_category.items()},
            "by_difficulty": {k: {"correct": v[0], "total": v[1],
                                  "accuracy": round(100 * v[0] / max(v[1], 1), 1)}
                              for k, v in by_difficulty.items()},
            "by_question_type": {k: {"correct": v[0], "total": v[1],
                                     "accuracy": round(100 * v[0] / max(v[1], 1), 1)}
                                 for k, v in by_question_type.items()},
        }

    out_path = HERE / "pharmacology_results.json"
    out_path.write_text(json.dumps({
        "n_questions": len(rows),
        "dataset": "ekacare/Eka_NFI_MCQA (test split)",
        "license": "Released by Eka Care, May 2026 — see ekacare HF org",
        "models": by_model,
    }, indent=2, default=str))
    print(f"\nWrote {out_path}")

    # Console summary
    print(f"\n  {'Model':<32} {'n':>4}  {'Acc':>6}  {'Lat':>6}  parse-fail")
    for m, info in by_model.items():
        lat = info.get("median_latency_s")
        lat_s = f"{lat:.1f}s" if lat is not None else "—"
        print(f"  {m:<32} {info['n_evaluated']:>4}  {info['accuracy']:>5.1f}%  {lat_s:>6}  {info['n_parse_fail']}")


if __name__ == "__main__":
    main()
