#!/usr/bin/env python3
"""Pre-registered eligibility funnel for the CRESCENDDI-Enriched test.

A pair (drug_A, drug_B, event) is BODHI-testable iff:
  (a) event matches a BODHI condition by exact (case-folded, lemma-normalized) name; AND
  (b) both drug_A and drug_B match a BODHI drug (same normalization).

Why both drugs must match: BODHI's drug-condition checker only fires when it can
look up `treatedConditions` for the drug. If a drug isn't in the BODHI index,
BODHI literally has no signal — counting that as a BODHI "miss" would be unfair.

Why exact-with-normalization (not fuzzy substring): "hypertensive crisis" should
NOT match "hypertension" — they're different SNOMED concepts. We allow only:
  * lowercasing
  * stripping common modifiers ("acute ", "chronic ", "moderate ", "severe ",
    "mild ", "transient ", "drug-induced ")
  * collapsing whitespace
  * canonical spelling (US/UK -ae- vs -e-, -ise vs -ize)

Output: scripts/crescenddi/eligible_pairs.json
        with the funnel breakdown printed to stdout.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BODHI = ROOT / "app/src/main/assets/bodhi"
CDATA = HERE / "crescenddi"

POS = pd.read_excel(CDATA / "Data_Record_1_Positive_Controls.xlsx")
NEG = pd.read_excel(CDATA / "Data_Record_2_Negative_Controls.xlsx")

bodhi_conditions = json.loads((BODHI / "bodhi_conditions.json").read_text())
bodhi_drugs      = json.loads((BODHI / "bodhi_drugs.json").read_text())

_MODIFIERS = (
    "acute", "chronic", "moderate", "severe", "mild", "transient",
    "drug-induced", "drug induced", "early", "late", "primary",
    "secondary", "recurrent", "intermittent", "persistent",
    "subacute", "non-specific", "nonspecific",
)
_UK_US = {
    "haemo": "hemo", "haema": "hema", "haemat": "hemat",
    "anaemia": "anemia", "oedema": "edema", "oesophag": "esophag",
    "diarrhoea": "diarrhea", "ise ": "ize ", "yse ": "yze ",
    "centre": "center", "tumour": "tumor", "anaesth": "anesth",
    "aetiology": "etiology", "fibre": "fiber", "leukaemia": "leukemia",
    "paediatr": "pediatr", "gynaec": "gynec", "ischaemia": "ischemia",
    "ageing": "aging", "behaviour": "behavior", "colour": "color",
    # blood-chemistry "aemia/aemic" → "emia/emic"
    "kalaemia": "kalemia", "natraemia": "natremia", "calcaemia": "calcemia",
    "magnesaemia": "magnesemia", "phosphataemia": "phosphatemia",
    "glycaemia": "glycemia", "uricaemia": "uricemia", "ammonaemia": "ammonemia",
    "lipidaemia": "lipidemia", "cholesteraemia": "cholesteremia",
    "ureaemia": "uremia", "septicaemia": "septicemia", "viraemia": "viremia",
    "bacteraemia": "bacteremia", "fungaemia": "fungemia",
    "thalassaemia": "thalassemia",
    # other "ae" pairs in medical terms
    "haemorrh": "hemorrh",  # haemorrhagic, haemorrhage already, but be explicit
    "leukocyt": "leukocyt",  # already same; placeholder
}
_PUNCT_RE = re.compile(r"[,;:'\"()]+")
_PARENS_RE = re.compile(r"\([^)]*\)")
_WS_RE = re.compile(r"\s+")

def norm(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = _PARENS_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s)
    for uk, us in _UK_US.items():
        s = s.replace(uk, us)
    # strip leading/trailing modifiers iteratively
    changed = True
    while changed:
        changed = False
        for m in _MODIFIERS:
            if s.startswith(m + " "):
                s = s[len(m) + 1:]
                changed = True
            if s.endswith(" " + m):
                s = s[: -len(m) - 1]
                changed = True
    s = _WS_RE.sub(" ", s).strip()
    return s

# Build BODHI lookup tables
cond_norms = {norm(c["name"]): c["snomedId"] for c in bodhi_conditions if c.get("name")}
drug_norms = {norm(d["name"]): d for d in bodhi_drugs if d.get("name")}

print("=" * 72)
print("PRE-REGISTERED ELIGIBILITY FUNNEL — CRESCENDDI ∩ BODHI")
print("=" * 72)
print(f"BODHI conditions (unique normalized names): {len(cond_norms)}")
print(f"BODHI drugs      (unique normalized names): {len(drug_norms)}")
print()
print(f"CRESCENDDI raw positives: {len(POS):>6}")
print(f"CRESCENDDI raw negatives: {len(NEG):>6}")

# Step 1: positive pairs whose EVENT is in BODHI conditions
def event_in_bodhi(e):
    return norm(e) in cond_norms

POS["_event_norm"] = POS["EVENT_CONCEPT_NAME"].apply(norm)
POS["_event_in_bodhi"] = POS["_event_norm"].isin(set(cond_norms.keys()))
POS["_drug1_norm"] = POS["DRUG_1_CONCEPT_NAME"].apply(norm)
POS["_drug2_norm"] = POS["DRUG_2_CONCEPT_NAME"].apply(norm)
POS["_drug1_in_bodhi"] = POS["_drug1_norm"].isin(set(drug_norms.keys()))
POS["_drug2_in_bodhi"] = POS["_drug2_norm"].isin(set(drug_norms.keys()))

print()
print("POSITIVE controls:")
print(f"  + event matches BODHI condition (exact, normalized): {POS['_event_in_bodhi'].sum():>6} / {len(POS)} ({100*POS['_event_in_bodhi'].mean():.1f}%)")
print(f"  + drug_1 in BODHI:                                   {POS['_drug1_in_bodhi'].sum():>6} / {len(POS)} ({100*POS['_drug1_in_bodhi'].mean():.1f}%)")
print(f"  + drug_2 in BODHI:                                   {POS['_drug2_in_bodhi'].sum():>6} / {len(POS)} ({100*POS['_drug2_in_bodhi'].mean():.1f}%)")
both = POS["_drug1_in_bodhi"] & POS["_drug2_in_bodhi"]
print(f"  + both drugs in BODHI:                               {both.sum():>6} / {len(POS)} ({100*both.mean():.1f}%)")
eligible = POS["_event_in_bodhi"] & both
POS_ELIG = POS[eligible].copy()
print(f"  + ELIGIBLE (event + both drugs):                     {len(POS_ELIG):>6} / {len(POS)} ({100*len(POS_ELIG)/len(POS):.1f}%)")

# Step 2: matched negatives — for each eligible event, sample negatives where
# both drugs are also in BODHI. We will assign the same event distribution
# during transcript construction (so "patient with E" appears in both arms).
NEG["_drug1_norm"] = NEG["DRUG_1_CONCEPT_NAME"].apply(norm)
NEG["_drug2_norm"] = NEG["DRUG_2_CONCEPT_NAME"].apply(norm)
NEG["_drug1_in_bodhi"] = NEG["_drug1_norm"].isin(set(drug_norms.keys()))
NEG["_drug2_in_bodhi"] = NEG["_drug2_norm"].isin(set(drug_norms.keys()))
neg_both = NEG["_drug1_in_bodhi"] & NEG["_drug2_in_bodhi"]
NEG_ELIG = NEG[neg_both].copy()
print()
print("NEGATIVE controls:")
print(f"  + drug_1 in BODHI:                                   {NEG['_drug1_in_bodhi'].sum():>6} / {len(NEG)} ({100*NEG['_drug1_in_bodhi'].mean():.1f}%)")
print(f"  + drug_2 in BODHI:                                   {NEG['_drug2_in_bodhi'].sum():>6} / {len(NEG)} ({100*NEG['_drug2_in_bodhi'].mean():.1f}%)")
print(f"  + ELIGIBLE (both drugs in BODHI):                    {len(NEG_ELIG):>6} / {len(NEG)} ({100*len(NEG_ELIG)/len(NEG):.1f}%)")

# How many distinct events do we cover?
distinct_events = POS_ELIG["EVENT_CONCEPT_NAME"].nunique()
print()
print(f"Distinct BODHI-recognized events in eligible positives: {distinct_events}")
top_events = POS_ELIG["EVENT_CONCEPT_NAME"].value_counts().head(15)
print("Top 15 events by frequency in eligible set:")
for e, n in top_events.items():
    print(f"  {n:>4}  {e}")

# Save eligibility tables for the actual run
out_dir = CDATA
out = {
    "n_pos_total": int(len(POS)),
    "n_neg_total": int(len(NEG)),
    "n_pos_eligible": int(len(POS_ELIG)),
    "n_neg_eligible": int(len(NEG_ELIG)),
    "n_distinct_events": int(distinct_events),
    "modifiers_stripped": list(_MODIFIERS),
    "uk_us_canonicalizations": _UK_US,
    "bodhi_condition_count": len(cond_norms),
    "bodhi_drug_count": len(drug_norms),
}
(out_dir / "eligibility_funnel.json").write_text(json.dumps(out, indent=2))

# Save eligible pair lists with normalized names for the run script
POS_ELIG[["DRUG_1_CONCEPT_NAME", "DRUG_2_CONCEPT_NAME", "EVENT_CONCEPT_NAME",
          "BNF_SEV_LEVEL", "MICROMEDEX_SEV_LEVEL",
          "_drug1_norm", "_drug2_norm", "_event_norm"]].to_csv(
    out_dir / "eligible_positives.csv", index=False)

NEG_ELIG[["DRUG_1_CONCEPT_NAME", "DRUG_2_CONCEPT_NAME",
          "_drug1_norm", "_drug2_norm"]].to_csv(
    out_dir / "eligible_negatives.csv", index=False)

print()
print("=" * 72)
print(f"Saved eligibility tables to {out_dir}/")
print(f"  eligible_positives.csv  ({len(POS_ELIG)} rows)")
print(f"  eligible_negatives.csv  ({len(NEG_ELIG)} rows)")
print(f"  eligibility_funnel.json")
print("=" * 72)
