#!/usr/bin/env python3
"""
Three-judge LLM-as-judge evaluator for the **quality** dimensions of
benchmark_bodhi raw outputs.

Design principle: extraction accuracy is measured deterministically via the
silver-standard ground truth (benchmark_bodhi.extraction_quality). This script
handles the *subjective quality* dimensions where deterministic rubrics are
insufficient:

  - Clinical-note quality  (soap_quality, clinical_reasoning, plan_appropriateness,
                            hallucination_severity, overall)
  - Safety-review quality  (coverage, relevance, overall)

To mitigate self-bias, each record is graded by a PANEL of three cross-vendor
frontier judges:
  - claude-opus-4-7       (Anthropic)
  - gpt-5.4               (OpenAI)
  - gemini-3.1-pro        (Google)

Each judge writes its score under a namespaced key, and the script also writes
mean / stdev / agreement across the panel. Discrepancies between judges are
surfaced on the dashboard so genuinely contested cases are visible.

Usage:
    export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... GEMINI_API_KEY=...
    python3 scripts/judge_llm.py                          # all three judges
    python3 scripts/judge_llm.py --judges opus,gpt        # subset
    python3 scripts/judge_llm.py --filter claude-opus-4-7 # only this target model
    python3 scripts/judge_llm.py --concurrency 4
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW_DIR_BASE = REPO / "scripts" / "bodhi_raw_generations"


JUDGE_SYSTEM = """\
You are a senior clinical educator evaluating AI clinical-assistant output. Be precise, strict, terse. Output JSON ONLY \u2014 no commentary, no markdown fences.

You score TWO artefacts per encounter:
  1. The clinical NOTE the AI generated.
  2. The clinical safety REVIEW (Arm 1) the AI generated.

(Extraction accuracy is scored separately against a silver-standard ground truth; do NOT grade the extraction here.)

Scoring scale 0 (unusable) to 100 (excellent). Use the full range \u2014 a typical good-but-imperfect output is 70\u201385, strong is 85\u201395, reserve 95+ for near-perfect. Do not grade-inflate.

Your JSON output must match this schema EXACTLY:
{
  "note_judge": {
    "soap_quality": 0-100,              // substantive SOAP organization, not just headers
    "clinical_reasoning": 0-100,        // Assessment ties findings to diagnosis with reasoning
    "plan_appropriateness": 0-100,      // Plan is actionable, right drug/dose/follow-up
    "hallucination_severity": 0-100,    // 100 = zero hallucinated facts; 0 = pervasive
    "overall": 0-100,
    "notes": "one-sentence critique focused on what's missing or wrong"
  },
  "review_judge": {
    "coverage": 0-100,                  // of the real dangers, how many flagged
    "relevance": 0-100,                 // of flagged concerns, how many legitimate
    "overall": 0-100,
    "notes": "one-sentence critique"
  }
}
"""


JUDGE_USER_TEMPLATE = """\
You are judging an AI clinical assistant's work on one primary-care encounter in a low-resource setting.

=== TRANSCRIPT ===
{transcript}

=== GROUND TRUTH (what a senior clinician expected) ===
Expected diagnoses: {dx}
Expected medications: {meds}
Expected vitals: {vitals}
Patient allergies: {allergies}
Expected safety dangers:
{dangers}

=== MODEL'S CLINICAL NOTE ===
{note}

=== MODEL'S SAFETY REVIEW (Arm 1 \u2014 parsed concerns) ===
{review}

Output JSON only, conforming to the schema in the system message. Be strict.
"""


# Short names used as keys in the stored panel (opus / gpt / gemini).
JUDGE_CONFIGS = {
    "opus":   {"model": "claude-opus-4-7",   "provider": "anthropic"},
    "gpt":    {"model": "gpt-5.4",           "provider": "openai"},
    "gemini": {"model": "gemini-3.1-pro-preview",    "provider": "google"},
}


def _format_dangers(dangers):
    if not dangers:
        return "(none \u2014 control case)"
    return "\n".join(f"- [{d.get('severity')}] {d.get('category')}: {d.get('substring', '')}" for d in dangers)


def _format_review(parsed_alerts):
    if not parsed_alerts:
        return "(model flagged none)"
    return "\n".join(f"- [{a.get('severity')}] {a.get('category')}: {a.get('message', '')}" for a in parsed_alerts)


def _parse_judge(text: str):
    """Best-effort JSON parse of a judge response."""
    if not text:
        return None
    # Strip code fences if any
    t = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.I)
    t = re.sub(r"\s*```\s*$", "", t)
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        # Try stripping trailing commas
        try:
            return json.loads(re.sub(r",\s*([\]}])", r"\1", m.group()))
        except json.JSONDecodeError:
            return None


# ── Per-provider callers ─────────────────────────────────────────
def _call_anthropic(model, sys_prompt, user_msg, _clients):
    c = _clients["anthropic"]
    r = c.messages.create(model=model, max_tokens=800, system=sys_prompt,
                           messages=[{"role": "user", "content": user_msg}])
    return r.content[0].text


def _call_openai(model, sys_prompt, user_msg, _clients):
    c = _clients["openai"]
    kw = {"max_completion_tokens": 1200} if model.startswith(("gpt-5", "o1", "o3", "o4")) else {"max_tokens": 1200}
    r = c.chat.completions.create(model=model, **kw,
                                   messages=[{"role": "system", "content": sys_prompt},
                                             {"role": "user", "content": user_msg}])
    return r.choices[0].message.content


def _call_google(model, sys_prompt, user_msg, _clients):
    genai = _clients["google_module"]
    m = genai.GenerativeModel(model, system_instruction=sys_prompt,
                               generation_config={"temperature": 0.0, "max_output_tokens": 1200})
    r = m.generate_content(user_msg)
    return r.text


_PROVIDER_CALL = {
    "anthropic": _call_anthropic,
    "openai":    _call_openai,
    "google":    _call_google,
}


def call_one_judge(clients, judge_key: str, payload: dict, max_retries: int = 3) -> dict | None:
    cfg = JUDGE_CONFIGS[judge_key]
    transcript = payload.get("transcript", "(no transcript)")
    gt = payload.get("ground_truth", {}) or {}
    note_text = (payload.get("note", {}) or {}).get("text") or (payload.get("note", {}) or {}).get("raw") or "(no note generated)"
    review_alerts = (payload.get("clinical_review_arm1", {}) or {}).get("parsed_alerts") or []

    user_msg = JUDGE_USER_TEMPLATE.format(
        transcript=transcript[:3500],
        dx=", ".join(gt.get("expected_diagnoses") or []) or "\u2014",
        meds=", ".join(gt.get("expected_medications") or []) or "\u2014",
        vitals=", ".join(gt.get("expected_vitals") or []) or "\u2014",
        allergies=", ".join(gt.get("patient_allergies") or []) or "\u2014",
        dangers=_format_dangers(gt.get("expected_dangers")),
        note=note_text[:3000],
        review=_format_review(review_alerts),
    )

    backoff = 2.0
    for attempt in range(max_retries):
        try:
            text = _PROVIDER_CALL[cfg["provider"]](cfg["model"], JUDGE_SYSTEM, user_msg, clients)
            parsed = _parse_judge(text)
            if parsed:
                return {"judge": judge_key, "model": cfg["model"], **parsed, "raw": text}
            if attempt == max_retries - 1:
                return {"judge": judge_key, "model": cfg["model"], "error": "parse_failed", "raw": text}
        except Exception as e:
            msg = str(e)
            if any(s in msg.lower() for s in ("rate", "overload", "quota", "529", "429", "503")):
                time.sleep(backoff); backoff *= 2
                continue
            if attempt == max_retries - 1:
                return {"judge": judge_key, "model": cfg["model"], "error": msg[:200]}
    return None


def _aggregate_panel(panel_results: list[dict]) -> dict:
    """Compute mean + stdev + agreement across the panel for note_judge and review_judge."""
    valid = [r for r in panel_results if r and "error" not in r]
    if not valid:
        return {"mean": {}, "stdev": {}, "n_judges": 0}

    def _stats(key, subkeys):
        out_mean, out_sd = {}, {}
        for sk in subkeys:
            vals = []
            for r in valid:
                v = (r.get(key) or {}).get(sk)
                if isinstance(v, (int, float)):
                    vals.append(float(v))
            if vals:
                out_mean[sk] = round(statistics.mean(vals), 1)
                out_sd[sk] = round(statistics.stdev(vals), 1) if len(vals) > 1 else 0.0
        return out_mean, out_sd

    note_keys = ("soap_quality", "clinical_reasoning", "plan_appropriateness", "hallucination_severity", "overall")
    review_keys = ("coverage", "relevance", "overall")
    nm, nsd = _stats("note_judge", note_keys)
    rm, rsd = _stats("review_judge", review_keys)
    return {
        "n_judges": len(valid),
        "note_mean": nm, "note_stdev": nsd,
        "review_mean": rm, "review_stdev": rsd,
    }


def judge_one(path: Path, judges: list[str], clients, force: bool = False) -> tuple[str, str]:
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        return path.name, f"read_error: {e}"

    existing = data.get("judge_panel", {}) if isinstance(data.get("judge_panel"), dict) else {}
    if not force and all(j in existing for j in judges) and "aggregate" in existing:
        return path.name, "skipped (already judged by all)"

    if data.get("failed"):
        return path.name, "skipped (extraction failed)"
    n = (data.get("note") or {})
    if not (n.get("text") or n.get("raw")):
        return path.name, "skipped (no note)"

    # Call each judge that's missing or forced
    panel = {k: existing[k] for k in existing if k in JUDGE_CONFIGS}
    for jk in judges:
        if not force and jk in panel and "error" not in (panel[jk] or {}):
            continue
        result = call_one_judge(clients, jk, data)
        if result:
            panel[jk] = result

    agg = _aggregate_panel([panel[jk] for jk in judges if jk in panel])
    data["judge_panel"] = {**panel, "aggregate": agg, "scored_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    try:
        path.write_text(json.dumps(data, indent=2, default=str))
    except Exception as e:
        return path.name, f"write_error: {e}"

    parts = []
    for jk in judges:
        r = panel.get(jk, {})
        if "error" in r:
            parts.append(f"{jk}=ERR")
        else:
            nj = r.get("note_judge", {}) or {}
            parts.append(f"{jk}={nj.get('overall','?')}")
    return path.name, "ok  note: " + "  ".join(parts)


def _load_clients(judges: list[str]) -> dict:
    clients = {}
    if "opus" in judges:
        try: import anthropic
        except ImportError: sys.exit("pip install anthropic")
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key: sys.exit("ANTHROPIC_API_KEY not set")
        clients["anthropic"] = anthropic.Anthropic(api_key=key)
    if "gpt" in judges:
        try: import openai
        except ImportError: sys.exit("pip install openai")
        key = os.environ.get("OPENAI_API_KEY")
        if not key: sys.exit("OPENAI_API_KEY not set")
        clients["openai"] = openai.OpenAI(api_key=key)
    if "gemini" in judges:
        try: import google.generativeai as genai
        except ImportError: sys.exit("pip install google-generativeai")
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key: sys.exit("GEMINI_API_KEY not set")
        genai.configure(api_key=key)
        clients["google_module"] = genai
    return clients


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--judges", default="opus,gpt,gemini",
                   help="Comma-separated judge keys (opus,gpt,gemini). Default: all three.")
    p.add_argument("--filter", default="", help="Only judge raw files whose filename contains this substring")
    p.add_argument("--force", action="store_true", help="Re-judge files already judged")
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--runs", default="",
                   help="Comma-separated run IDs to judge (e.g. 'run1'). Empty = all runs + top-level files.")
    args = p.parse_args()

    judges = [j.strip() for j in args.judges.split(",") if j.strip() in JUDGE_CONFIGS]
    if not judges:
        sys.exit(f"No valid judges. Must be subset of: {list(JUDGE_CONFIGS)}")

    if not RAW_DIR_BASE.exists():
        sys.exit(f"ERROR: {RAW_DIR_BASE} not found")

    # File discovery: top-level + per-run subdirs (optionally filtered)
    all_files = list(RAW_DIR_BASE.glob("*.json"))
    run_dirs = sorted(d for d in RAW_DIR_BASE.iterdir() if d.is_dir() and d.name.startswith("run"))
    if args.runs:
        allowed = set(args.runs.split(","))
        run_dirs = [d for d in run_dirs if d.name in allowed]
    for rd in run_dirs:
        all_files += list(rd.glob("*.json"))
    files = sorted(all_files)
    if args.filter:
        files = [f for f in files if args.filter in f.name]
    if args.limit > 0:
        files = files[:args.limit]

    print(f"Judges: {judges}")
    print(f"Target raw files: {len(files)}")
    print(f"Concurrency: {args.concurrency}")
    print()

    clients = _load_clients(judges)
    t0 = time.time()
    processed = errors = 0

    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = [ex.submit(judge_one, p, judges, clients, args.force) for p in files]
        for i, fut in enumerate(cf.as_completed(futures), 1):
            name, status = fut.result()
            processed += 1
            if "error" in status or "failed" in status:
                errors += 1
            elapsed = time.time() - t0
            rate = processed / elapsed * 60 if elapsed > 0 else 0
            eta = (len(files) - processed) / (rate / 60) if rate > 0 else 0
            print(f"[{i:4d}/{len(files)}]  {status:<70s}  {name}  ({rate:.0f}/min, ETA {eta/60:.0f}m)")

    print(f"\nDone: {processed} processed, {errors} errors, {time.time()-t0:.0f}s total")


if __name__ == "__main__":
    main()
