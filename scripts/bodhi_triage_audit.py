#!/usr/bin/env python3
"""BODHI triage classification audit on CRESCENDDI's clinician-curated events.

Question: of the CRESCENDDI adverse-event vocabulary that BODHI recognizes,
how often does BODHI's `triageLevel` for that event agree with what a
clinician judge says it *should* be when the event manifests as an ADR?

This is a *graph-internal* test of BODHI — no LLM extraction, no DDI logic.
It uses CRESCENDDI as a clinician-curated vocabulary source.

Two tiers:
  * Tier-1 (strict): EVENT exactly matches a BODHI condition name (after
    normalization). BODHI's `triageLevel` field on that condition is the
    classification under audit.
  * Tier-2 (extended): EVENT matches a BODHI symptom-leaf name. We then
    take the MAX severity of the conditions the symptom predicts (with
    likelihood >= 0.5) as the inferred triage level.

Adjudicator: Claude Opus 4.7. Given the event name and a brief CRESCENDDI
description (drug count, pair-frequency), Opus picks one of:
  EMERGENCY (ED/ICU same-hour) | WORRISOME (urgent same-day) | OPD_MANAGED (routine)

Output: scripts/bodhi_triage_audit.json
        with per-event rows + aggregate confusion matrix.
"""
from __future__ import annotations
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

def _resolve_bodhi_dir() -> Path:
    """Resolve BODHI directory. Tries $BODHI_DIR, then data/bodhi/ (public repo),
    then app/src/main/assets/bodhi/ (ChartLite app layout)."""
    import os as _os
    if _os.environ.get("BODHI_DIR"):
        return Path(_os.environ["BODHI_DIR"])
    candidates = [ROOT / "data" / "bodhi", ROOT / "app/src/main/assets/bodhi"]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]

BODHI = _resolve_bodhi_dir()
CDATA = HERE / "crescenddi"

sys.path.insert(0, str(HERE))
from crescenddi_funnel import norm  # reuse the normalization

# ── Load BODHI ─────────────────────────────────────────────────────────────
conds = json.loads((BODHI / "bodhi_conditions.json").read_text())
sym_raw = json.loads((BODHI / "bodhi_symptoms.json").read_text())

# normalized name -> condition record
cond_by_norm: dict[str, dict] = {}
for c in conds:
    if c.get("name"):
        cond_by_norm[norm(c["name"])] = c

# Symptom layer: each symptom node points to a list of {name, likelihood, ...}
# of CONDITIONS it predicts. Symptom NAMES (the leaves of those predictions)
# are themselves drawn from BODHI's condition namespace, so we can look up
# their own triageLevel via cond_by_norm.
sym_name_to_predicted = {}
for sid, preds in sym_raw.items():
    for p in preds:
        if not isinstance(p, dict): continue
        if "name" not in p: continue
        sym_name_to_predicted.setdefault(norm(p["name"]), []).append(p)

# ── Load CRESCENDDI positives ─────────────────────────────────────────────
POS = pd.read_excel(CDATA / "Data_Record_1_Positive_Controls.xlsx")
POS["_event_norm"] = POS["EVENT_CONCEPT_NAME"].apply(norm)
event_freq = POS["EVENT_CONCEPT_NAME"].value_counts().to_dict()

# Build the audit table
TRIAGE_ORDER = {"emergency": 3, "worrisome": 2, "opd_managed": 1, None: 0, "": 0}

def lookup_bodhi_triage(event_name: str) -> dict:
    """Return the BODHI triage record for this event under both tiers."""
    n = norm(event_name)
    out = {"event": event_name, "norm": n,
           "tier1_match": None, "tier1_triage": None,
           "tier2_match": None, "tier2_triage": None,
           "tier2_predicted_conditions": []}

    # Tier 1: direct condition match
    if n in cond_by_norm:
        c = cond_by_norm[n]
        out["tier1_match"] = c.get("name")
        out["tier1_triage"] = (c.get("triageLevel") or "").lower() or None

    # Tier 2: symptom-leaf match → look up predicted conditions
    if n in sym_name_to_predicted:
        out["tier2_match"] = event_name  # name from symptom leaf
        predicted = sym_name_to_predicted[n]
        # For each predicted-condition NAME, look up its triageLevel
        max_sev_score = 0
        max_sev_label = None
        cond_rows = []
        for p in predicted:
            cn = norm(p["name"])
            if cn in cond_by_norm:
                lvl = (cond_by_norm[cn].get("triageLevel") or "").lower() or None
                cond_rows.append({"name": p["name"], "triage": lvl,
                                  "likelihood": p.get("likelihood")})
                s = TRIAGE_ORDER.get(lvl, 0)
                if s > max_sev_score:
                    max_sev_score = s
                    max_sev_label = lvl
        out["tier2_triage"] = max_sev_label
        out["tier2_predicted_conditions"] = cond_rows[:8]
    return out

# Get the union of all events in either tier
covered_events = set()
for ev in POS["EVENT_CONCEPT_NAME"].dropna().unique():
    n = norm(ev)
    if n in cond_by_norm or n in sym_name_to_predicted:
        covered_events.add(ev)

audit_rows = [lookup_bodhi_triage(ev) for ev in sorted(covered_events)]
for row in audit_rows:
    row["crescenddi_freq"] = int(event_freq.get(row["event"], 0))

print(f"BODHI-recognized CRESCENDDI events: {len(audit_rows)}")
print(f"  tier-1 (condition match): {sum(1 for r in audit_rows if r['tier1_match'])}")
print(f"  tier-2 (symptom match):   {sum(1 for r in audit_rows if r['tier2_match'])}")
print(f"  both:                     {sum(1 for r in audit_rows if r['tier1_match'] and r['tier2_match'])}")

# ── Adjudicate with Claude Opus 4.7 ─────────────────────────────────────────
ADJUDICATOR_PROMPT = """You are a senior emergency-medicine and internal-medicine clinician reviewing adverse drug events from the CRESCENDDI reference set.

Given the adverse-event term below, classify the appropriate clinical-triage level **assuming the event has already manifested in an outpatient who is on the implicated drug regimen**:

  EMERGENCY    — needs immediate emergency department or ICU evaluation (life-threatening, time-critical)
  WORRISOME    — needs same-day urgent workup (could escalate; not immediately life-threatening)
  OPD_MANAGED  — can be managed at routine outpatient follow-up (mild/expected/self-limiting)

Event: {event}
CRESCENDDI frequency: {freq} positive drug-pairs implicated
Notes: this term is from BNF / Micromedex / ANSM clinician-curated DDI lists.

Respond with EXACTLY one of: EMERGENCY, WORRISOME, OPD_MANAGED. One word, no explanation.
"""

def call_anthropic_adjudicator(event: str, freq: int) -> str:
    import anthropic
    client = anthropic.Anthropic()
    prompt = ADJUDICATOR_PROMPT.format(event=event, freq=freq)
    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=20,
        messages=[{"role": "user", "content": prompt}],
    )
    txt = "".join(b.text for b in msg.content if hasattr(b, "text")).strip().upper()
    # Tolerate stray punctuation
    txt = re.sub(r"[^A-Z_]", "", txt)
    return txt

print()
print("Adjudicating with Opus 4.7…")
t0 = time.time()
RAW = HERE / "crescenddi" / "bodhi_triage_audit_raw"
RAW.mkdir(exist_ok=True)

def task(row):
    cache = RAW / f"{row['norm'].replace(' ', '_')[:60]}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    try:
        a = call_anthropic_adjudicator(row["event"], row["crescenddi_freq"])
    except Exception as e:
        a = f"ERROR: {type(e).__name__}: {e}"
    out = {**row, "judge_label": a}
    cache.write_text(json.dumps(out, indent=2, default=str))
    return out

results = []
with ThreadPoolExecutor(max_workers=4) as ex:
    futs = [ex.submit(task, r) for r in audit_rows]
    for fut in as_completed(futs):
        results.append(fut.result())
print(f"  done in {time.time()-t0:.1f}s")

# ── Score ───────────────────────────────────────────────────────────────────
LABELS = ["EMERGENCY", "WORRISOME", "OPD_MANAGED"]
BODHI_LBL = {"emergency": "EMERGENCY", "worrisome": "WORRISOME", "opd_managed": "OPD_MANAGED"}

def score(row, tier_key):
    bodhi = BODHI_LBL.get(row.get(f"{tier_key}_triage")) if row.get(f"{tier_key}_triage") else None
    judge = row.get("judge_label")
    if judge not in LABELS:
        return {"bodhi": bodhi, "judge": judge, "agree": None,
                "bodhi_severity": TRIAGE_ORDER.get(row.get(f"{tier_key}_triage"), 0),
                "judge_severity": TRIAGE_ORDER.get(judge.lower() if judge else None, 0)}
    return {
        "bodhi": bodhi, "judge": judge,
        "agree": bodhi == judge,
        "bodhi_severity": TRIAGE_ORDER.get(row.get(f"{tier_key}_triage"), 0),
        "judge_severity": TRIAGE_ORDER.get(judge.lower(), 0),
    }

for r in results:
    r["tier1_score"] = score(r, "tier1")
    r["tier2_score"] = score(r, "tier2")

# Aggregate
def aggregate(rows, tier):
    n = len(rows)
    valid = [r for r in rows if r[f"{tier}_score"].get("agree") is not None]
    n_valid = len(valid)
    n_agree = sum(1 for r in valid if r[f"{tier}_score"]["agree"])
    # Confusion matrix: judge label rows × BODHI label cols
    conf = {jl: {bl: 0 for bl in LABELS + ["MISSING"]} for jl in LABELS + ["MISSING"]}
    for r in valid:
        s = r[f"{tier}_score"]
        j = s["judge"] or "MISSING"
        b = s["bodhi"] or "MISSING"
        if j not in conf:
            conf[j] = {bl: 0 for bl in LABELS + ["MISSING"]}
        conf[j][b] = conf[j].get(b, 0) + 1
    # Severity agreement: ±0 (exact), ±1 step, ±2 steps
    diffs = [s["judge_severity"] - s["bodhi_severity"]
             for r in valid for s in [r[f"{tier}_score"]] if s["bodhi"]]
    return {
        "n": n, "n_valid": n_valid, "n_agree_exact": n_agree,
        "agree_pct": round(100 * n_agree / max(n_valid, 1), 1),
        "confusion": conf,
        "severity_diffs": diffs,
    }

agg_t1 = aggregate([r for r in results if r["tier1_match"]], "tier1")
agg_t2 = aggregate([r for r in results if r["tier2_match"]], "tier2")

# Frequency-weighted exact-agreement %
def freq_weighted_agree(rows, tier):
    valid = [r for r in rows if r[f"{tier}_score"].get("agree") is not None]
    total = sum(r["crescenddi_freq"] for r in valid)
    agree = sum(r["crescenddi_freq"] for r in valid if r[f"{tier}_score"]["agree"])
    return round(100 * agree / max(total, 1), 1), total, agree

t1_fw_pct, t1_tot, t1_agree = freq_weighted_agree([r for r in results if r["tier1_match"]], "tier1")
t2_fw_pct, t2_tot, t2_agree = freq_weighted_agree([r for r in results if r["tier2_match"]], "tier2")

out = {
    "method": (
        "For each CRESCENDDI EVENT that BODHI recognizes (by exact-name "
        "normalized match against bodhi_conditions.name [tier-1] or any "
        "symptom-leaf name in bodhi_symptoms predictions [tier-2]), compare "
        "BODHI's triageLevel against Opus 4.7's clinical-triage adjudication "
        "of the same event treated as a manifested ADR. Tier-2 takes the max "
        "severity of conditions the symptom-leaf predicts."
    ),
    "judge_model": "claude-opus-4-7",
    "n_unique_events_in_crescenddi": int(POS["EVENT_CONCEPT_NAME"].nunique()),
    "n_recognized": len(results),
    "tier1": {**agg_t1, "freq_weighted_agree_pct": t1_fw_pct,
              "freq_weighted_total_pairs": t1_tot,
              "freq_weighted_agree_pairs": t1_agree},
    "tier2": {**agg_t2, "freq_weighted_agree_pct": t2_fw_pct,
              "freq_weighted_total_pairs": t2_tot,
              "freq_weighted_agree_pairs": t2_agree},
    "rows": sorted(results, key=lambda r: -r["crescenddi_freq"]),
}
out_path = HERE / "bodhi_triage_audit.json"
out_path.write_text(json.dumps(out, indent=2, default=str))
print()
print(f"Tier-1 (BODHI condition match):")
print(f"  events: {agg_t1['n']}, valid: {agg_t1['n_valid']}, exact-agree: {agg_t1['n_agree_exact']} ({agg_t1['agree_pct']}%)")
print(f"  frequency-weighted agreement: {t1_fw_pct}% ({t1_agree}/{t1_tot} CRESCENDDI positive pairs)")
print()
print(f"Tier-2 (BODHI symptom match, max-severity inference):")
print(f"  events: {agg_t2['n']}, valid: {agg_t2['n_valid']}, exact-agree: {agg_t2['n_agree_exact']} ({agg_t2['agree_pct']}%)")
print(f"  frequency-weighted agreement: {t2_fw_pct}% ({t2_agree}/{t2_tot} CRESCENDDI positive pairs)")
print()
print("Per-event detail:")
print(f"  {'Event':<40} {'freq':>5}  {'BODHI':<14} {'Judge':<14} {'agree?':<6}")
for r in sorted(results, key=lambda r: -r["crescenddi_freq"])[:30]:
    s = r["tier1_score"] if r["tier1_match"] else r["tier2_score"]
    bodhi = s.get("bodhi") or "—"
    judge = s.get("judge") or "—"
    agree = "✓" if s.get("agree") else ("✗" if s.get("agree") is False else "?")
    print(f"  {r['event'][:38]:<40} {r['crescenddi_freq']:>5}  {bodhi:<14} {judge:<14} {agree:<6}")

print(f"\nSaved {out_path}")
