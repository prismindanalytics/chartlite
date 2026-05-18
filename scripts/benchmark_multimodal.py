#!/usr/bin/env python3
"""Multimodal clinical artifact benchmark — Gemma 4 vision vs SOTA.

Evaluates whether on-device Gemma 4 (e4b / e2b) can read 8 categories of
clinical artifacts and emit the unified JSON schema that drives the
ChartLite Universal Capture button.

The 8 artifact types:
    lab_report · rdt_cassette · vital_device · medication_package
    referral_letter · vaccine_card · handwritten_prescription
    discharge_summary

Test data lives in `scripts/multimodal_dataset/manifest.json`. Each case
ships its own image (public-domain or synthetic) and a hand-labelled
ground truth. See `scripts/multimodal_dataset/README.md` for how to add
cases.

Metrics:
    1. content_type classification accuracy (exact match)
    2. per-field extraction precision / recall, sliced by artifact type
    3. failure-mode analysis (low-resolution, glare, handwriting)

Output:
    scripts/multimodal_raw/<model>__<case_id>.json   — per-(model, case) cache
    scripts/multimodal_results.json                  — aggregate per-model scores

Usage:
    python3 scripts/benchmark_multimodal.py \\
        --models gemma4-e4b --limit 5 --concurrency 1
    python3 scripts/benchmark_multimodal.py  # full sweep across all models

The script is idempotent: existing cache files are reused unless --force.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "multimodal_raw"
RAW.mkdir(exist_ok=True)
DATASET = HERE / "multimodal_dataset"

sys.path.insert(0, str(HERE))
import benchmark_bodhi as bb

OLLAMA_URL = getattr(bb, "OLLAMA_URL", "http://localhost:11434")

# Vision-capable models only. The on-device leaderboard headlines Gemma 4 e4b
# and e2b; cloud SOTA is the comparator. Qwen 3.5 / MedGemma omitted because
# our deployment paths don't ship vision (Qwen visual.mnn unwired, MedGemma
# 1.5 text-only via ollama).
MODELS = [
    ("claude-opus-4-7",          "anthropic"),
    ("claude-sonnet-4-6",        "anthropic"),
    ("claude-haiku-4-5-20251001","anthropic"),
    ("gpt-5.5",                  "openai"),
    ("gpt-5.4",                  "openai"),
    ("gpt-4.1",                  "openai"),
    ("gemma4:e4b",               "ollama"),
    ("gemma4:e2b",               "ollama"),
]

# Mirrors `ExtractionPromptBuilder.VISION_SYSTEM_PROMPT` in the Android app.
SYSTEM = """\
You are a clinical data extractor for medical images. Auto-detect the content
type and extract structured data.

Content types:
- lab_report
- rdt_cassette
- vital_device
- medication_package
- referral_letter
- vaccine_card
- handwritten_prescription
- discharge_summary

Rules:
- Extract ONLY what is visible. Do NOT infer.
- For RDT cassettes, determine result from colored lines on the cassette only.
- For handwriting, leave fields empty if illegible and add a "warnings" entry.
- Set content_type to one of the eight types above (or "unknown").
- Output valid JSON only.
"""

USER = """\
Output JSON with these fields. Fill ONLY the fields relevant to the artifact
type you see; leave the rest empty/null.

{"content_type":"...","confidence":0.0,"raw_text":"...","item_name":"...",
 "investigations":[{"test":"","result":"","unit":"","reference_range":"","flag":""}],
 "rdt":{"test_type":"","result":"","bands":""},
 "vitals":[{"name":"","value":"","unit":""}],
 "medications":[{"name":"","dose":"","route":"","freq":"","duration":"","expiry":"","manufacturer":"","batch":""}],
 "referral":{"from_facility":"","diagnosis":"","reason":"","urgency":""},
 "immunizations":[{"vaccine":"","date":"","dose_number":1,"batch":"","route":""}],
 "discharge":{"dx":[],"meds":[],"follow_up":"","alerts":[]},
 "warnings":[]}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Vision API calls
# ─────────────────────────────────────────────────────────────────────────────

def _b64(image_path: Path) -> tuple[str, str]:
    """Base64-encode the image and return (data, media_type)."""
    data = image_path.read_bytes()
    suffix = image_path.suffix.lower().lstrip(".")
    media_type = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"
    return base64.b64encode(data).decode("ascii"), media_type


def call_anthropic(model: str, image_path: Path) -> tuple[str, float]:
    try:
        import anthropic
    except ImportError:
        return "[ImportError] anthropic", 0
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return "[no ANTHROPIC_API_KEY]", 0
    t0 = time.time()
    try:
        b64, media_type = _b64(image_path)
        r = anthropic.Anthropic(api_key=key).messages.create(
            **bb._anthropic_kwargs(model, temperature=0.1),
            system=SYSTEM,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": USER},
            ]}],
        )
        return r.content[0].text, time.time() - t0
    except Exception as e:
        return f"[ERROR] {e}", time.time() - t0


def call_openai(model: str, image_path: Path) -> tuple[str, float]:
    try:
        import openai
    except ImportError:
        return "[ImportError] openai", 0
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return "[no OPENAI_API_KEY]", 0
    t0 = time.time()
    try:
        b64, media_type = _b64(image_path)
        is_reasoning = model.startswith(("gpt-5", "o1", "o3", "o4"))
        kw = {"max_completion_tokens": 4096} if is_reasoning else {"max_tokens": 4096, "temperature": 0.1}
        r = openai.OpenAI(api_key=key).chat.completions.create(
            model=model, **kw,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": USER},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                ]},
            ],
        )
        return r.choices[0].message.content or "", time.time() - t0
    except Exception as e:
        return f"[ERROR] {e}", time.time() - t0


def call_ollama(model: str, image_path: Path) -> tuple[str, float]:
    """Ollama vision API: pass image as base64 in the `images` field."""
    import requests
    t0 = time.time()
    try:
        b64, _ = _b64(image_path)
        payload = {
            "model": model, "stream": False,
            "options": {"temperature": 0.1, "num_ctx": 4096},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": USER, "images": [b64]},
            ],
        }
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=600)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", ""), time.time() - t0
    except Exception as e:
        return f"[ERROR] {e}", time.time() - t0


def call_model(model: str, backend: str, image_path: Path) -> tuple[str, float]:
    if backend == "anthropic": return call_anthropic(model, image_path)
    if backend == "openai":    return call_openai(model, image_path)
    if backend == "ollama":    return call_ollama(model, image_path)
    return f"[unknown backend {backend}]", 0


# ─────────────────────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────────────────────

def parse_json(raw: str) -> dict | None:
    """Lenient JSON extraction — strips markdown fences and trailing chatter."""
    if not raw:
        return None
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"```(?:json)?\s*|```", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def field_recall(predicted: list[str], expected: list[str]) -> float:
    """Fraction of expected items found anywhere in predicted (case-insensitive substring)."""
    if not expected:
        return 1.0
    found = 0
    pred_norm = [str(p).lower() for p in predicted]
    for e in expected:
        en = str(e).lower()
        if any(en in p or p in en for p in pred_norm):
            found += 1
    return found / len(expected)


def score_case(predicted: dict | None, expected: dict) -> dict:
    if predicted is None:
        return {
            "content_type_correct": False,
            "field_recall": 0.0,
            "parsed": False,
        }
    pred_type = predicted.get("content_type", "")
    exp_type = expected.get("content_type") or expected.get("expected_content_type", "")
    type_correct = pred_type == exp_type

    # Per-type field recall — collapses each artifact's structured fields
    # into a flat list of strings the model should have produced.
    expected_fields = expected.get("expected_fields") or {}
    flatten = []
    pred_flat = []
    if exp_type == "medication_package" or exp_type == "handwritten_prescription":
        flatten = [m.get("name", "") for m in expected_fields.get("medications", [])]
        pred_flat = [m.get("name", "") for m in (predicted.get("medications") or [])]
    elif exp_type == "lab_report":
        flatten = [t.get("test", "") for t in expected_fields.get("investigations", [])]
        pred_flat = [t.get("test", "") for t in (predicted.get("investigations") or [])]
    elif exp_type == "rdt_cassette":
        flatten = [(expected_fields.get("rdt") or {}).get("result", "")]
        pred_flat = [(predicted.get("rdt") or {}).get("result", "")]
    elif exp_type == "vital_device":
        flatten = [v.get("name", "") for v in expected_fields.get("vitals", [])]
        pred_flat = [v.get("name", "") for v in (predicted.get("vitals") or [])]
    elif exp_type == "vaccine_card":
        flatten = [i.get("vaccine", "") for i in expected_fields.get("immunizations", [])]
        pred_flat = [i.get("vaccine", "") for i in (predicted.get("immunizations") or [])]
    elif exp_type == "discharge_summary":
        flatten = (expected_fields.get("discharge") or {}).get("dx", [])
        pred_flat = (predicted.get("discharge") or {}).get("dx", [])
    elif exp_type == "referral_letter":
        ref = expected_fields.get("referral") or {}
        flatten = [ref.get("diagnosis", ""), ref.get("reason", "")]
        pred_ref = predicted.get("referral") or {}
        pred_flat = [pred_ref.get("diagnosis", ""), pred_ref.get("reason", "")]

    flatten = [x for x in flatten if x]
    pred_flat = [x for x in pred_flat if x]
    return {
        "content_type_correct": type_correct,
        "field_recall": field_recall(pred_flat, flatten),
        "parsed": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────

def safe_id(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)


def run_case(model: str, backend: str, case: dict, repo_root: Path, force: bool) -> dict:
    case_id = case["id"]
    cache = RAW / f"{safe_id(model)}__{safe_id(case_id)}.json"
    if cache.exists() and not force:
        return json.loads(cache.read_text())

    image_path = repo_root / case["image_path"]
    if not image_path.exists():
        out = {
            "model": model, "case_id": case_id,
            "raw": f"[MISSING image] {case['image_path']}",
            "parsed": None,
            "score": {"content_type_correct": False, "field_recall": 0.0, "parsed": False},
            "elapsed_s": 0.0,
        }
        cache.write_text(json.dumps(out, indent=2))
        return out

    raw, elapsed = call_model(model, backend, image_path)
    parsed = parse_json(raw)
    score = score_case(parsed, case)
    out = {
        "model": model, "case_id": case_id,
        "raw": raw,
        "parsed": parsed,
        "score": score,
        "elapsed_s": round(elapsed, 2),
    }
    cache.write_text(json.dumps(out, indent=2))
    return out


def aggregate(model: str, results: list[dict], cases: list[dict]) -> dict:
    n = len(results)
    if n == 0:
        return {"model": model, "n": 0}
    type_correct = sum(1 for r in results if r["score"]["content_type_correct"])
    field_recall = sum(r["score"]["field_recall"] for r in results) / n
    parsed = sum(1 for r in results if r["score"]["parsed"])

    # Per-type slice
    by_type: dict[str, dict] = {}
    case_types = {c["id"]: c.get("expected_content_type", "unknown") for c in cases}
    for r in results:
        t = case_types.get(r["case_id"], "unknown")
        bt = by_type.setdefault(t, {"n": 0, "type_correct": 0, "field_recall_sum": 0.0})
        bt["n"] += 1
        if r["score"]["content_type_correct"]:
            bt["type_correct"] += 1
        bt["field_recall_sum"] += r["score"]["field_recall"]
    for t, bt in by_type.items():
        bt["type_acc"] = round(bt["type_correct"] / bt["n"], 3)
        bt["field_recall_avg"] = round(bt["field_recall_sum"] / bt["n"], 3)
        del bt["field_recall_sum"]

    return {
        "model": model,
        "n": n,
        "content_type_acc": round(type_correct / n, 3),
        "field_recall_avg": round(field_recall, 3),
        "parse_rate": round(parsed / n, 3),
        "by_type": by_type,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", default=str(DATASET / "manifest.json"))
    p.add_argument("--models", default="", help="comma-separated model substrings, empty = all")
    p.add_argument("--limit", type=int, default=0, help="cap number of cases (0 = all)")
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--force", action="store_true", help="ignore cache and re-run")
    args = p.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"[FATAL] manifest not found: {manifest_path}", file=sys.stderr)
        print("        See scripts/multimodal_dataset/README.md for the format.", file=sys.stderr)
        sys.exit(2)
    manifest = json.loads(manifest_path.read_text())
    cases = manifest.get("cases", [])
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("[FATAL] no cases in manifest", file=sys.stderr)
        sys.exit(2)

    selected = [(m, b) for m, b in MODELS if not args.models or any(s in m for s in args.models.split(","))]
    if not selected:
        print(f"[FATAL] no models matched '{args.models}'", file=sys.stderr)
        sys.exit(2)

    repo_root = HERE.parent
    aggregates = {}
    for model, backend in selected:
        print(f"\n[{model}] running on {len(cases)} cases (backend={backend}) ...")
        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futs = [ex.submit(run_case, model, backend, c, repo_root, args.force) for c in cases]
            for fut in as_completed(futs):
                results.append(fut.result())
        agg = aggregate(model, results, cases)
        aggregates[model] = agg
        print(
            f"  type_acc={agg.get('content_type_acc', 0):.1%} "
            f"field_recall={agg.get('field_recall_avg', 0):.1%} "
            f"parse={agg.get('parse_rate', 0):.1%}"
        )

    out_path = HERE / "multimodal_results.json"
    out_path.write_text(json.dumps({
        "schema_version": 1,
        "manifest_version": manifest.get("version", "?"),
        "n_cases": len(cases),
        "results": aggregates,
    }, indent=2))
    print(f"\n→ wrote {out_path.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
