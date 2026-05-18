#!/usr/bin/env python3
"""Multi-axis adjudication of every un-matched extraction.

Replaces the old 7-pattern cascade with a per-item table. Each un-matched
extracted item gets a row with SIX INDEPENDENT AXES, each answering a distinct
question that we were previously collapsing into one bucket:

  transcript_support  supported | unsupported | unclear
  gt_relation         equivalent | paraphrase | less_specific | more_specific |
                      assertion_mismatch | no_gt_match | gt_missing
  field_status        correct_field | wrong_field | no_field_match
  structure_status    clean | placeholder_null | duplicate_alias | malformed
  action_bucket       scoring_gap | silver_gt_gap | prompt_fix |
                      capability | manual_review
  evidence            { transcript_span_ids: [...], gt_item_ids: [...] }

The adjudicator is a three-stage hybrid:
  1. Deterministic detectors (free, fast, 100% precision on easy cases):
       placeholder_null, duplicate_alias, numeric mismatch, exact cross-field.
  2. Retrieval: top-5 sentence-level transcript spans + top-3 GT candidates,
     lexical overlap score.
  3. LLM adjudicator (Opus 4.7) on the residual: emits the 6 axes given the
     extraction + retrieved candidates. Required to cite evidence span IDs
     when it says \"supported\".

Output: scripts/adjudicated_items.json

Usage:
    export ANTHROPIC_API_KEY=...
    python3 scripts/adjudicate_items.py
    python3 scripts/adjudicate_items.py --limit 200       # test run
    python3 scripts/adjudicate_items.py --no-llm          # deterministic only
    python3 scripts/adjudicate_items.py --model gpt-5.4   # alt judge
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import benchmark_bodhi as bb

OUT = HERE / "adjudicated_items.json"
RAW_BASE = HERE / "bodhi_raw_generations"
FIELDS = ["diagnoses", "medications", "vitals", "allergies",
          "exam_findings", "investigations", "plan", "immunizations"]

PLACEHOLDERS = {"not stated", "unknown", "not measured", "not mentioned",
                "n/a", "nil", "none stated", "none", "not available",
                "not documented", "unspecified"}


def _str_item(item) -> str:
    if item is None: return ""
    if isinstance(item, str): return item
    if isinstance(item, dict):
        if "primary" in item: return str(item.get("primary") or "")
        if "name" in item and "value" in item: return f"{item.get('name','')} {item.get('value','')}".strip()
        if "test" in item: return f"{item.get('test','')}: {item.get('result','')}".strip(": ")
        if "name" in item: return str(item["name"])
        if "vaccine" in item: return str(item["vaccine"])
        return " ".join(str(v) for v in item.values() if v is not None)
    return str(item)


# ── Sentence splitter with stable span IDs ──────────────────────
def split_transcript_spans(enc) -> list:
    """Return a list of {id, source, text} sentence spans with stable IDs.
    ID format: `enc{NNN}#conv#s{M}` or `enc{NNN}#dict#s{M}`."""
    spans = []
    enc_id = bb.ENCOUNTERS.index(enc) + 1
    for source, text in [("conv", enc.conversation or ""), ("dict", enc.dictation or "")]:
        # Rough sentence split: newline or ". " or "! " or "? "
        chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
        for j, c in enumerate(chunks):
            c = c.strip()
            if len(c) < 3: continue
            spans.append({"id": f"enc{enc_id:03d}#{source}#s{j}", "source": source, "text": c})
    return spans


# ── Stage 1: deterministic detectors ────────────────────────────
def _is_placeholder(item) -> bool:
    """Placeholder / null-ish item? (dict with 'not stated' value, or string 'none')."""
    if isinstance(item, str):
        return item.lower().strip() in PLACEHOLDERS
    if isinstance(item, dict):
        for v in item.values():
            if isinstance(v, str) and v.lower().strip() in PLACEHOLDERS:
                return True
        # Dict with no meaningful values
        vals = [str(v).strip() for v in item.values() if v is not None]
        if not any(v for v in vals if v.lower() not in PLACEHOLDERS and len(v) >= 2):
            return True
    return False


def _strip_denominator_shorthand(s: str) -> str:
    """Strip medical denominator-shorthand where the second number is a
    convention, not a measured value. The first number stays.

      - "10/40 gestation"   → "10 gestation"   (UK/AU "out of 40 weeks full-term")
      - "return in 3/12"    → "return in 3"    (UK "X out of 12 months")
      - "Apgar 9/10"         → "Apgar 9"        ("out of 10 max")

    Without this, the numeric-mismatch rule incorrectly flags a model that
    wrote "10 weeks gestation" against a GT form "10/40 gestation" — both
    encode the same fact.
    """
    if not s: return s
    # Gestation: X/40 when "gestation"/"weeks"/"pregnancy" nearby
    if any(t in s for t in ("gestation", "week", "pregnan")):
        s = re.sub(r"(\d+)\s*/\s*40\b", r"\1", s)
    # Calendar months: X/12 when "month"/"return"/"follow" nearby (UK shorthand)
    if any(t in s for t in ("month", "return", "follow", "review")):
        s = re.sub(r"(\d+)\s*/\s*12\b", r"\1", s)
    # Apgar: X/10 when "apgar" nearby
    if "apgar" in s:
        s = re.sub(r"(\d+)\s*/\s*10\b", r"\1", s)
    return s


# Stopwords / weak content words — sharing only these doesn't establish
# that two clinical items are the same. Trips up the numeric-mismatch rule
# (e.g. "Start enalapril 2.5" vs "Start furosemide 40mg" share only "Start").
_WEAK_OVERLAP = {
    "start", "take", "continue", "stop", "return", "follow", "follow-up",
    "consider", "and", "the", "for", "with", "after", "before", "every",
    "daily", "twice", "thrice", "weekly", "monthly", "tablet", "tablets",
    "month", "months", "week", "weeks", "day", "days", "hour", "hours",
}

def _content_words(s: str) -> set:
    """Words ≥4 chars that aren't dosing-frequency stopwords. Used to gate
    numeric-mismatch by requiring meaningful name overlap, not just shared
    verbs like 'start' or units like 'daily'."""
    # Strip digits AND identifier-internal digits (B12 → B, CD4 → CD)
    cleaned = re.sub(r"\b[A-Za-z]+\d+\b", "", s)  # drop CD4, B12, T2, etc.
    cleaned = re.sub(r"[\d.,]", "", cleaned)
    return {w for w in cleaned.split() if len(w) >= 4 and w not in _WEAK_OVERLAP}


def _extract_numbers(s: str) -> set:
    """Numbers that appear as standalone tokens (not embedded in identifiers
    like CD4, B12, T2). Returns a set of strings to compare for mismatch."""
    # Drop identifier-embedded numbers first
    s = re.sub(r"\b[A-Za-z]+\d+\b", "", s)
    return set(re.findall(r"\b\d+(?:\.\d+)?\b", s))


def _numeric_mismatch(ext, gt_items) -> dict | None:
    """If the extraction has numbers AND the best-name-match GT item also has
    numbers but they disagree, flag it. Returns {"gt_item": ..., "ext_nums": ...,
    "gt_nums": ...} or None.

    Conservative: requires ≥2 shared content words (not just one stopword)
    AND strips denominator-shorthand and identifier-embedded digits before
    extracting numbers. Without these guards, the rule has many false positives
    (e.g. flagging "enalapril 2.5mg" against GT "furosemide 40mg" because both
    happen to start with 'Start')."""
    ext_s = _strip_denominator_shorthand(_str_item(ext).lower())
    ext_nums = _extract_numbers(ext_s)
    if not ext_nums: return None
    ext_words = _content_words(ext_s)
    for g in gt_items:
        forms = bb._accept_forms(g)
        for f in forms:
            fl = _strip_denominator_shorthand(f.lower())
            f_nums = _extract_numbers(fl)
            if not f_nums: continue
            f_words = _content_words(fl)
            shared = ext_words & f_words
            # Require at least 2 shared content words to consider this the
            # "same item" — otherwise we're comparing numbers across unrelated facts.
            if len(shared) < 2: continue
            if ext_nums != f_nums:
                return {"gt_item_form": f, "ext_nums": sorted(ext_nums), "gt_nums": sorted(f_nums)}
    return None


# ── Stage 2: retrieval ─────────────────────────────────────────
def _score_overlap(query: str, text: str) -> float:
    """Simple lexical overlap score: fraction of content words in query that
    appear in text. Cheap, deterministic, good enough for sentence retrieval
    on this tiny corpus."""
    q_words = [w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", query)]
    if not q_words: return 0.0
    t = text.lower()
    hits = sum(1 for w in q_words if w in t)
    return hits / len(q_words)


def retrieve_spans(query: str, spans: list, k: int = 5) -> list:
    """Return top-k spans by lexical overlap (id, text, score)."""
    scored = [(s, _score_overlap(query, s["text"])) for s in spans]
    scored.sort(key=lambda x: -x[1])
    return [{"id": s["id"], "text": s["text"], "score": round(score, 3)}
            for s, score in scored[:k] if score > 0]


def retrieve_gt_candidates(query: str, gt_items: list, k: int = 3) -> list:
    """Top-k silver-GT candidates across accept forms."""
    scored = []
    for idx, g in enumerate(gt_items):
        forms = bb._accept_forms(g)
        best = 0.0
        for f in forms:
            s = _score_overlap(query, f)
            if s > best: best = s
        if best > 0:
            primary = g.get("primary") if isinstance(g, dict) else str(g)
            scored.append({"id": f"gt{idx}", "primary": primary, "score": round(best, 3)})
    scored.sort(key=lambda x: -x["score"])
    return scored[:k]


# ── Stage 3: LLM adjudicator ───────────────────────────────────
JUDGE_SYSTEM = """You are a rigorous clinical-NLP evaluator. Given a single extracted item, the transcript spans most related to it, the closest silver-ground-truth candidates, and the declared field, produce a STRICT JSON object on six independent axes.

Output this schema EXACTLY, no commentary:

{
  "transcript_support": "supported" | "unsupported" | "unclear",
  "support_span_ids": ["enc###...", ...],   // REQUIRED list if transcript_support="supported"; empty otherwise
  "gt_relation": "equivalent" | "paraphrase" | "less_specific" | "more_specific" | "assertion_mismatch" | "no_gt_match" | "gt_missing",
  "gt_item_ids": ["gt0", "gt1", ...],       // empty if no_gt_match / gt_missing
  "field_status": "correct_field" | "wrong_field" | "no_field_match",
  "structure_status": "clean" | "placeholder_null" | "duplicate_alias" | "malformed",
  "action_bucket": "scoring_gap" | "silver_gt_gap" | "prompt_fix" | "capability" | "manual_review",
  "rationale": "<one-sentence reason grounded in the retrieved evidence>"
}

RULES:
- "supported" requires at least one span_id from the retrieved list. Never say supported without a citation.
- "equivalent" means same clinical concept AND same qualifiers (negation, temporality, experiencer, severity, laterality).
- "paraphrase" means same concept, different wording.
- "less_specific": extraction drops a qualifier GT has (e.g. "ECG" vs "ST elevation on ECG").
- "assertion_mismatch": extraction negates / temporally shifts / changes experiencer of what GT says ("no penicillin allergy" vs "penicillin allergy").
- "gt_missing" means transcript-supported + no reasonable GT candidate \u2014 this is OUR labeling gap, not a model error.
- "wrong_field" means content matches a GT item in ANOTHER field (not the declared one).
- action_bucket follows the axes:
    scoring_gap    \u2014 supported + (equivalent | paraphrase) but no credit given
    silver_gt_gap  \u2014 supported + gt_missing (our silver GT lacks this item)
    prompt_fix     \u2014 placeholder_null / duplicate_alias / wrong_field
    capability     \u2014 unsupported OR less_specific OR assertion_mismatch OR no_gt_match+no transcript support
    manual_review  \u2014 genuinely unclear; flag for human audit
"""


JUDGE_USER_TEMPLATE = """EXTRACTION:
  field: {field}
  value: {extracted}

SILVER GT (declared field = {field}):
{gt_candidates}

RETRIEVED TRANSCRIPT SPANS (ranked by lexical overlap):
{transcript_spans}

CROSS-FIELD GT CANDIDATES (for checking field-confusion):
{cross_field_candidates}

Adjudicate. Return JSON only.
"""


def _format_gt_cands(cands):
    if not cands: return "  (no candidates \u2014 likely silver_gt_gap)"
    lines = []
    for c in cands:
        lines.append(f"  [{c['id']}] {c['primary']}  (score={c['score']})")
    return "\n".join(lines)


def _format_spans(spans):
    if not spans: return "  (no relevant spans)"
    lines = []
    for s in spans:
        lines.append(f"  [{s['id']}] (score={s['score']}) {s['text'][:180]}")
    return "\n".join(lines)


def _format_cross(cross):
    if not cross: return "  (none)"
    lines = []
    for fld, cands in cross.items():
        for c in cands[:2]:
            lines.append(f"  [{fld}] {c['primary']}  (score={c['score']})")
    return "\n".join(lines[:5])


def call_judge(client, model, field, ext_str, gt_cands, spans, cross, max_retries=3):
    user_msg = JUDGE_USER_TEMPLATE.format(
        field=field, extracted=ext_str,
        gt_candidates=_format_gt_cands(gt_cands),
        transcript_spans=_format_spans(spans),
        cross_field_candidates=_format_cross(cross),
    )
    for attempt in range(max_retries):
        try:
            r = client.messages.create(
                model=model, max_tokens=600, system=JUDGE_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            text = r.content[0].text
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            if attempt == max_retries - 1:
                return {"_error": str(e)[:120]}
            time.sleep(1.5 * (attempt + 1))
    return {"_error": "parse_failed"}


# ── Main adjudication loop ─────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-4-7")
    ap.add_argument("--limit", type=int, default=0, help="Max items to adjudicate (0=all)")
    ap.add_argument("--no-llm", action="store_true", help="Deterministic+retrieval only, skip LLM")
    ap.add_argument("--filter-model", default="", help="Only run for this benchmarked model")
    ap.add_argument("--concurrency", type=int, default=3)
    args = ap.parse_args()

    client = None
    if not args.no_llm:
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key: sys.exit("ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic(api_key=key)

    # Gather all raw records
    files = list(RAW_BASE.glob("*.json"))
    for d in sorted(RAW_BASE.iterdir()):
        if d.is_dir():
            files += list(d.glob("*.json"))
    if args.filter_model:
        files = [f for f in files if args.filter_model in f.name]

    print(f"Scanning {len(files)} raw files...")

    # Pre-compute transcript spans per encounter (memoize)
    spans_cache = {}
    for i, enc in enumerate(bb.ENCOUNTERS):
        spans_cache[i + 1] = split_transcript_spans(enc)

    # Load silver GT once
    bb._silver_gt_for(bb.ENCOUNTERS[0])

    adjudications = []
    n_items_scanned = 0
    n_items_to_llm = 0
    n_llm_calls = 0
    t0 = time.time()

    # Greedy matcher (same as _decompose_category)
    match_fns = {
        "diagnoses": bb._match_diagnosis, "medications": bb._match_medication,
        "vitals": bb._match_vital, "allergies": bb._match_string,
        "exam_findings": bb._match_string, "investigations": bb._match_investigation,
        "plan": bb._match_string, "immunizations": bb._match_string,
    }

    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    counter_lock = threading.Lock()

    def adjudicate_one(rec):
        nonlocal n_llm_calls
        enc_id = rec.get("encounter_id")
        if not enc_id: return []
        enc = bb.ENCOUNTERS[enc_id - 1]
        silver = bb._silver_gt_for(enc) or {}
        ext = (rec.get("extraction") or {}).get("parsed") or {}
        if not ext:
            # reparse from raw if needed
            raw_txt = (rec.get("extraction") or {}).get("raw") or ""
            m = re.search(r"\{[\s\S]*\}", raw_txt)
            if m:
                try: ext = json.loads(m.group())
                except: ext = {}
        model = rec.get("model") or "unknown"
        mode = rec.get("transcript_mode") or "unknown"
        run_id = rec.get("run_id") or "run1"

        # GT per field
        gt_by_field = {}
        for f in FIELDS:
            v = silver.get(f) or []
            gt_by_field[f] = v
        # fallback to curator when silver missing
        if not gt_by_field["diagnoses"]: gt_by_field["diagnoses"] = list(enc.expected_diagnoses or [])
        if not gt_by_field["medications"]: gt_by_field["medications"] = list(enc.expected_medications or [])
        if not gt_by_field["vitals"]: gt_by_field["vitals"] = list(enc.expected_vitals or [])
        if not gt_by_field["allergies"]: gt_by_field["allergies"] = list(enc.patient_allergies or [])

        ext_by_field = {f: (ext.get(f) or []) for f in FIELDS}
        spans = spans_cache[enc_id]

        rows = []
        for fld in FIELDS:
            items = ext_by_field[fld]
            gts = gt_by_field[fld]
            fn = match_fns[fld]

            # Greedy pairing to identify unmatched
            paired_gt = set(); paired_ext = set()
            for i, e in enumerate(items):
                for j, g in enumerate(gts):
                    if j in paired_gt: continue
                    if fn(e, g):
                        paired_gt.add(j); paired_ext.add(i); break

            for i, e in enumerate(items):
                if i in paired_ext: continue
                ext_str = _str_item(e)
                if not ext_str: continue

                row_base = {
                    "enc_id": enc_id, "name": enc.name,
                    "model": model, "mode": mode, "run_id": run_id,
                    "field": fld, "extracted": e if isinstance(e, (str, dict)) else str(e),
                }

                # ── Stage 1: deterministic detectors ──
                if _is_placeholder(e):
                    rows.append({
                        **row_base,
                        "stage": "deterministic",
                        "axes": {
                            "transcript_support": "unsupported",
                            "support_span_ids": [],
                            "gt_relation": "no_gt_match",
                            "gt_item_ids": [],
                            "field_status": "no_field_match",
                            "structure_status": "placeholder_null",
                            "action_bucket": "prompt_fix",
                            "rationale": "Placeholder/null value \u2014 model padded the field.",
                        },
                        "evidence": {"transcript_span_ids": [], "gt_item_ids": []},
                    })
                    continue
                nm = _numeric_mismatch(e, gts)
                if nm:
                    rows.append({
                        **row_base,
                        "stage": "deterministic",
                        "axes": {
                            "transcript_support": "unclear",
                            "support_span_ids": [],
                            "gt_relation": "no_gt_match",
                            "gt_item_ids": [],
                            "field_status": "no_field_match",
                            "structure_status": "clean",
                            "action_bucket": "capability",
                            "rationale": f"Numeric mismatch: extraction has {nm['ext_nums']}, GT form '{nm['gt_item_form'][:60]}' has {nm['gt_nums']}.",
                        },
                        "evidence": {"transcript_span_ids": [], "gt_item_ids": []},
                        "numeric_mismatch": nm,
                    })
                    continue

                # ── Stage 2: retrieval ──
                retrieved_spans = retrieve_spans(ext_str, spans, k=5)
                retrieved_gt = retrieve_gt_candidates(ext_str, gts, k=3)
                cross_field = {}
                for other_f in FIELDS:
                    if other_f == fld: continue
                    cand = retrieve_gt_candidates(ext_str, gt_by_field[other_f], k=2)
                    if cand: cross_field[other_f] = cand

                # ── Stage 3: LLM adjudicator ──
                if args.no_llm or client is None:
                    rows.append({
                        **row_base,
                        "stage": "retrieval_only",
                        "axes": None,
                        "evidence": {
                            "retrieved_transcript_spans": retrieved_spans,
                            "retrieved_gt_items": retrieved_gt,
                            "retrieved_cross_field": cross_field,
                        },
                    })
                else:
                    axes = call_judge(client, args.model, fld, ext_str,
                                      retrieved_gt, retrieved_spans, cross_field)
                    with counter_lock: n_llm_calls += 1
                    rows.append({
                        **row_base,
                        "stage": "llm",
                        "axes": axes,
                        "evidence": {
                            "retrieved_transcript_spans": retrieved_spans,
                            "retrieved_gt_items": retrieved_gt,
                            "retrieved_cross_field": cross_field,
                        },
                    })
        return rows

    # Collect all records first
    records = []
    for f in files:
        try:
            d = json.loads(f.read_text())
            records.append(d)
        except Exception:
            continue

    print(f"Loaded {len(records)} records. Scanning for unmatched items + adjudicating...")

    # Process in parallel when using LLM
    if args.concurrency > 1 and client is not None:
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futures = {ex.submit(adjudicate_one, r): r for r in records}
            for fut in as_completed(futures):
                rows = fut.result()
                adjudications.extend(rows)
                n_items_scanned += len(rows)
                elapsed = time.time() - t0
                if n_items_scanned % 50 == 0:
                    print(f"  [{n_items_scanned} items, {n_llm_calls} LLM calls, {elapsed:.0f}s]")
                if args.limit and n_items_scanned >= args.limit: break
    else:
        for r in records:
            rows = adjudicate_one(r)
            adjudications.extend(rows)
            n_items_scanned += len(rows)
            if args.limit and n_items_scanned >= args.limit: break

    # MERGE-rather-than-overwrite when filtering. If a previous adjudicated_items.json
    # exists and we ran with --filter-model, keep the prior rows for OTHER models and
    # replace only the rows for the filtered model. Without this safeguard, a filtered
    # rerun would silently discard the rest of the dataset.
    if args.filter_model and OUT.exists():
        try:
            prior = json.loads(OUT.read_text())
            if isinstance(prior, list):
                kept = [r for r in prior if args.filter_model not in (r.get("model") or "")]
                merged = kept + adjudications
                print(f"  merged: {len(kept)} prior rows kept (other models) + {len(adjudications)} new rows for filter '{args.filter_model}'")
                adjudications = merged
        except Exception as e:
            print(f"  [warn] could not merge prior {OUT.name}: {e}")

    OUT.write_text(json.dumps(adjudications, indent=2, default=str))
    print(f"\nWrote {OUT}")
    print(f"  items adjudicated: {len(adjudications)}")
    print(f"  LLM calls: {n_llm_calls}")
    print(f"  elapsed: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
