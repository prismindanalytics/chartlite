#!/usr/bin/env python3
"""Generate inclusive silver-standard ground truth via a 3-model consensus panel.

For each encounter, three frontier models (Opus 4.7, GPT-5.4, Gemini 3.1 Pro) each
independently emit a silver GT across 7 clinical fields. Each field item has the
shape {primary, accepts: [...]} so matching can be permissive to clinical phrasing
variation without relying on a global synonym table.

The three models' outputs are then merged by `_merge_panel`:
  - Items whose primary forms share a synonym group OR fuzzy-match >= 0.6 are
    considered the same item; their `accepts` lists are unioned.
  - Each model's novel items (no match in the pool) are added to the merged list.
  - The merged `accepts` for a kept item include the primaries + accepts from all
    models that proposed it.

Output: scripts/silver_gt.json   \u2014  a list of {encounter_id, name, silver_gt: {\u2026},
                                   per_model: {opus: {\u2026}, gpt: {\u2026}, gemini: {\u2026}}}

Usage:
    export ANTHROPIC_API_KEY=\u2026 OPENAI_API_KEY=\u2026 GEMINI_API_KEY=\u2026
    python3 scripts/generate_silver_gt.py
    python3 scripts/generate_silver_gt.py --models opus,gpt,gemini
    python3 scripts/generate_silver_gt.py --encounters 1-10
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import benchmark_bodhi as bb  # type: ignore

OUT = HERE / "silver_gt.json"
FIELDS = ["diagnoses", "medications", "vitals", "allergies",
          "exam_findings", "investigations", "plan", "immunizations"]

MODELS = {
    "opus":   {"model": "claude-opus-4-7",   "provider": "anthropic"},
    "gpt":    {"model": "gpt-5.4",           "provider": "openai"},
    "gemini": {"model": "gemini-3.1-pro-preview",    "provider": "google"},
}

SYSTEM = """You are a senior primary-care clinician producing a canonical clinical summary AND a deliberately inclusive list of acceptable alternative phrasings that another clinician might reasonably write for the SAME item.

Be exhaustive but grounded: include every clinically relevant fact that's explicitly stated OR a direct clinical consequence of what's stated (e.g. "BP 160/95" \u2192 hypertension). Do NOT speculate beyond what the transcript supports.

For EACH fact item, emit both a canonical `primary` and an `accepts` list of alternate forms. Cover, for each item:
  - The full clinical name (hypertension, myocardial infarction).
  - Common abbreviations (HTN, MI, STEMI, CHF, COPD, UTI, DKA, HIV, TB, \u2026).
  - Lay/clinician shorthand (heart attack, ear infection, sugar check, high pressure, chest infection, blocked nose, etc.).
  - Brand \u2194 generic for medications (paracetamol/acetaminophen/panadol/tylenol; lasix/furosemide; coartem/artemether-lumefantrine; etc.).
  - Verbose academic form (e.g. "severe exacerbation of chronic obstructive pulmonary disease").
  - Syndromic or category forms that an AI extraction might emit ("inflammatory skin disease" for psoriasis; "fluid overload" for decompensated heart failure; "infection around the brain" for meningitis).
  - Minor spelling/morphology (preeclampsia / pre-eclampsia; anaemia / anemia; haemoglobin / hemoglobin; cough with sputum / productive cough).

Err on the side of INCLUSION. Only exclude forms that are clinically WRONG (different disease). Never include antonyms (hypertension vs hypotension are NOT interchangeable).

Output ONE valid JSON object, no prose, matching this schema exactly:

{
  "diagnoses": [
    {"primary": "Hypertension", "accepts": ["HTN", "high blood pressure", "elevated BP", "essential hypertension", "arterial hypertension"]},
    ...
  ],
  "medications": [
    {"primary": "metformin 500mg BD", "accepts": ["metformin 500 mg twice daily", "metformin", "glucophage", "metformin 500 bd"], "context": "current|new|stopped"},
    ...
  ],
  "vitals": [
    {"primary": "BP 162/98 mmHg", "accepts": ["blood pressure 162/98", "BP 162 over 98", "162/98", "systolic 162 diastolic 98"]},
    ...
  ],
  "allergies": [
    {"primary": "NKDA", "accepts": ["no known drug allergies", "no allergies", "none"]}
  ],
  "exam_findings": [
    {"primary": "Right tympanic membrane erythematous and bulging", "accepts": ["right TM red and bulging", "erythematous right ear drum", "right ear drum inflamed"]},
    ...
  ],
  "investigations": [
    {"primary": "RDT positive for P. falciparum", "accepts": ["malaria RDT positive", "rapid test positive for falciparum", "positive falciparum RDT"]},
    ...
  ],
  "plan": [
    {"primary": "Start amoxicillin 500mg TDS for 7 days", "accepts": ["amoxicillin 500mg three times daily x 7 days", "commence amoxicillin 500 TDS", "prescribe amox 500 tds for one week"]},
    ...
  ],
  "immunizations": [
    {"primary": "Pentavalent vaccine given", "accepts": ["pentavalent given", "5-in-1 vaccine", "DTP-HepB-Hib", "penta", "pentavalent"], "status": "given|due|declined"}
  ]
}

Rules:
- Omit any field that has no data (do NOT pad with empty lists or "not stated").
- `accepts` should have 3\u20138 alternative phrasings per item \u2014 cover common cases, don't be exhaustive to absurdity.
- Never include the antonym or a clinically-different condition in accepts.
- Keep each string concise and clinical.
"""

USER = """CONVERSATION TRANSCRIPT:
{conversation}

DICTATION TRANSCRIPT:
{dictation}

Produce the canonical clinical summary JSON."""


# ── Per-provider callers ────────────────────────────────────────
def _call_anthropic(model, user_msg):
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY"); assert key, "ANTHROPIC_API_KEY missing"
    r = anthropic.Anthropic(api_key=key).messages.create(
        model=model, max_tokens=4096, system=SYSTEM,
        messages=[{"role": "user", "content": user_msg}])
    return r.content[0].text


def _call_openai(model, user_msg):
    import openai
    key = os.environ.get("OPENAI_API_KEY"); assert key, "OPENAI_API_KEY missing"
    kw = {"max_completion_tokens": 4096} if model.startswith(("gpt-5", "o1", "o3", "o4")) else {"max_tokens": 4096}
    r = openai.OpenAI(api_key=key).chat.completions.create(
        model=model, **kw,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_msg}])
    return r.choices[0].message.content


def _call_google(model, user_msg):
    import google.generativeai as genai
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    assert key, "GEMINI_API_KEY missing"
    genai.configure(api_key=key)
    m = genai.GenerativeModel(model, system_instruction=SYSTEM,
                               generation_config={"temperature": 0.0, "max_output_tokens": 4096})
    r = m.generate_content(user_msg)
    return r.text


PROVIDER_CALL = {"anthropic": _call_anthropic, "openai": _call_openai, "google": _call_google}


def generate_one(enc, model_key: str) -> dict | None:
    cfg = MODELS[model_key]
    user_msg = USER.format(conversation=enc.conversation, dictation=enc.dictation)
    try:
        raw = PROVIDER_CALL[cfg["provider"]](cfg["model"], user_msg)
    except Exception as e:
        return {"_error": str(e)[:200]}
    return bb._parse_json(raw) or {"_error": "parse_failed", "_raw": (raw or "")[:500]}


# ── Panel merge ────────────────────────────────────────────────
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().strip())


def _same_item(a_forms: list[str], b_forms: list[str]) -> bool:
    """Two items match if any of their forms share a synonym group OR fuzzy-match \u2265 0.6."""
    a_norms = [_norm(x) for x in a_forms if x]
    b_norms = [_norm(x) for x in b_forms if x]
    if not a_norms or not b_norms: return False
    # Substring within first form
    if a_norms[0] in b_norms[0] or b_norms[0] in a_norms[0]: return True
    # Synonym group overlap
    for a in a_norms:
        for b in b_norms:
            if bb._synonym_groups_in(a) & bb._synonym_groups_in(b):
                return True
            if SequenceMatcher(None, a, b).ratio() >= 0.6:
                return True
    return False


def _forms_of(item) -> list[str]:
    """Extract [primary, *accepts] from an item dict; handle legacy shapes gracefully."""
    if item is None: return []
    if isinstance(item, str): return [item]
    if isinstance(item, dict):
        out = []
        if item.get("primary"):
            out.append(item["primary"])
            accepts = item.get("accepts") or []
            if isinstance(accepts, list):
                out.extend(a for a in accepts if isinstance(a, str))
        elif "name" in item and "value" in item:
            out.append(f"{item.get('name','')} {item.get('value','')}".strip())
        elif "test" in item:
            r = item.get("result", "")
            out.append(f"{item.get('test','')} {r}".strip())
        elif "name" in item:
            out.append(item["name"])
        elif "vaccine" in item:
            out.append(item["vaccine"])
        return [o for o in out if o]
    return [str(item)]


def _merge_field_items(lists_per_model: dict[str, list]) -> list[dict]:
    """Merge per-model lists of items for one field.
    Returns a list of {primary, accepts, contributors: [model_keys]}."""
    merged: list[dict] = []
    for model_key, items in lists_per_model.items():
        if not items: continue
        for item in items:
            forms = _forms_of(item)
            if not forms: continue
            matched = False
            for m in merged:
                if _same_item(forms, m["_forms"]):
                    # Union the accepts
                    existing = set(_norm(x) for x in m["_forms"])
                    for f in forms:
                        if _norm(f) not in existing:
                            m["_forms"].append(f); existing.add(_norm(f))
                    m["contributors"].add(model_key)
                    # carry extra fields (context, status) if present
                    for k in ("context", "status"):
                        if isinstance(item, dict) and item.get(k) and not m.get(k):
                            m[k] = item[k]
                    matched = True; break
            if not matched:
                entry = {
                    "_forms": list(forms),
                    "contributors": {model_key},
                }
                if isinstance(item, dict):
                    if item.get("context"): entry["context"] = item["context"]
                    if item.get("status"):  entry["status"] = item["status"]
                merged.append(entry)

    # Produce output records
    out = []
    for m in merged:
        primary = m["_forms"][0]
        accepts = m["_forms"][1:] if len(m["_forms"]) > 1 else []
        rec = {"primary": primary, "accepts": accepts, "contributors": sorted(m["contributors"])}
        if m.get("context"): rec["context"] = m["context"]
        if m.get("status"):  rec["status"] = m["status"]
        out.append(rec)
    return out


def merge_panel(per_model: dict[str, dict]) -> dict:
    """Merge the three models' silver-GT dicts into a consensus silver GT."""
    merged = {}
    for fld in FIELDS:
        per = {k: (per_model.get(k) or {}).get(fld) or [] for k in per_model}
        merged[fld] = _merge_field_items(per)
    return merged


# ── Main ──────────────────────────────────────────────────────
def parse_encounter_range(spec: str, total: int) -> list[int]:
    if not spec: return list(range(1, total + 1))
    ids = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-"); ids.update(range(int(a), int(b) + 1))
        else:
            ids.add(int(part))
    return sorted(ids)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--models", default="opus,gpt,gemini",
                   help="Comma-separated model keys.")
    p.add_argument("--encounters", default="", help="Range like 1-10 or 5,7,12 (default: all)")
    p.add_argument("--force", action="store_true", help="Regenerate even if already present")
    args = p.parse_args()

    model_keys = [m.strip() for m in args.models.split(",") if m.strip() in MODELS]
    if not model_keys:
        sys.exit(f"No valid models. Must be subset of: {list(MODELS)}")

    encounters = bb.ENCOUNTERS
    enc_ids = parse_encounter_range(args.encounters, len(encounters))

    # Load existing
    existing = {}
    if OUT.exists():
        try:
            existing = {r["encounter_id"]: r for r in json.loads(OUT.read_text())}
        except Exception:
            existing = {}

    print(f"Generating consensus silver GT for {len(enc_ids)} encounters with models: {model_keys}")
    t0 = time.time()
    records = list(existing.values())
    for eid in enc_ids:
        if 0 < eid <= len(encounters):
            enc = encounters[eid - 1]
        else:
            continue

        existing_rec = existing.get(eid)
        per_model = (existing_rec or {}).get("per_model", {}) or {}

        # Call each model if missing or force
        for mk in model_keys:
            if not args.force and mk in per_model and "_error" not in (per_model[mk] or {}):
                continue
            parsed = generate_one(enc, mk)
            per_model[mk] = parsed or {"_error": "no_response"}
            time.sleep(0.3)  # small gap between providers

        # Merge into consensus
        merged = merge_panel(per_model)

        rec = {
            "encounter_id": eid,
            "name": enc.name,
            "category": enc.category,
            "silver_gt": merged,
            "per_model": per_model,
            "curator_diagnoses": enc.expected_diagnoses,
            "curator_medications": enc.expected_medications,
            "curator_vitals": enc.expected_vitals,
            "curator_allergies": enc.patient_allergies,
        }

        # Insert or replace
        upd = False
        for i, r in enumerate(records):
            if r.get("encounter_id") == eid:
                records[i] = rec; upd = True; break
        if not upd:
            records.append(rec)

        elapsed = time.time() - t0
        counts = {f: len(merged.get(f) or []) for f in FIELDS}
        print(f"  [{eid:3d}/100] {enc.name[:38]:<38}  "
              f"dx={counts['diagnoses']} med={counts['medications']} vit={counts['vitals']} "
              f"exam={counts['exam_findings']} inv={counts['investigations']} plan={counts['plan']} "
              f"({elapsed:.0f}s)")

        # Incremental save after each
        records_sorted = sorted(records, key=lambda r: r.get("encounter_id") or 0)
        OUT.write_text(json.dumps(records_sorted, indent=2, default=str))

    print(f"\nWrote {OUT} ({len(records)} records, {time.time()-t0:.0f}s total)")


if __name__ == "__main__":
    main()
