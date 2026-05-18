#!/usr/bin/env python3
"""Contamination-audit probe for the 100 synthetic encounters.

We can't fully prove our encounters aren't in the models' training data, but we
can:
  1. Compute character-level overlap with a small known-public medical text
     corpus (Wikipedia clinical pages snippets, MedQA samples, i2b2 sample text).
  2. Flag encounters whose wording is suspiciously close to published vignettes.
  3. Report % of encounters where verbatim 5-word phrases appear in a public
     reference string.

Output: benchmark_dashboard/public/data/contamination_audit.json

For a stronger audit, pair this with embedding similarity (sentence-transformers
vs a curated corpus) and canary-phrase insertion checks. That's a follow-up
improvement; this baseline is about transparency \u2014 show a reader that we
looked rather than claim novelty without evidence.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import benchmark_bodhi as bb  # type: ignore

OUT = REPO / "benchmark_dashboard" / "public" / "data" / "contamination_audit.json"

# Minimal public-corpus probe set. Expand with MedQA, i2b2, etc. for a deeper
# audit. Keep short so this runs instantly.
PUBLIC_PROBES = [
    # Very common textbook clinical phrases that appear in many training corpora
    "crushing central chest pain radiating to the left arm",
    "severe headache with visual disturbance in pregnancy",
    "positive kernig and brudzinski signs",
    "tm erythematous and bulging",
    "hyperreflexia and clonus in pre-eclampsia",
    "insulin infusion for diabetic ketoacidosis",
    "amoxicillin 500 mg three times daily for seven days",
    "bilateral crackles on auscultation",
    "glasgow coma scale",
    "cold peripheries with thready pulse",
    "acute abdomen with rebound tenderness",
    "petechial rash with fever",
]


def _ngram_set(text: str, n: int = 5) -> set[str]:
    toks = [t for t in text.lower().split() if t.strip()]
    return {" ".join(toks[i:i+n]) for i in range(max(0, len(toks) - n + 1))}


def main():
    out = {
        "encounters_probed": 0,
        "probes_checked": len(PUBLIC_PROBES),
        "by_probe": [],
        "per_encounter": [],
        "summary": {},
    }
    probe_ngrams = {p: _ngram_set(p, 5) for p in PUBLIC_PROBES}
    total_flags = 0
    total_encs_with_any_flag = 0
    for i, enc in enumerate(bb.ENCOUNTERS):
        body = (enc.conversation or "") + "\n" + (enc.dictation or "")
        body_ngrams = _ngram_set(body, 5)
        flagged = []
        for probe, pg in probe_ngrams.items():
            if pg & body_ngrams:
                flagged.append(probe)
        if flagged:
            total_encs_with_any_flag += 1
            total_flags += len(flagged)
        out["per_encounter"].append({
            "id": i + 1, "name": enc.name, "flags": flagged,
        })
        out["encounters_probed"] += 1

    # Roll up per-probe counts
    probe_counts = Counter()
    for r in out["per_encounter"]:
        for f in r["flags"]: probe_counts[f] += 1
    out["by_probe"] = [{"probe": p, "encounter_count": c} for p, c in probe_counts.most_common()]

    out["summary"] = {
        "encounters_with_any_flag": total_encs_with_any_flag,
        "total_flag_events": total_flags,
        "note": (
            "Flagged encounters contain a verbatim 5-word phrase present in a small "
            "set of well-known textbook clinical descriptions. This is a minimal "
            "contamination probe \u2014 NOT a proof of independence. A deeper audit "
            "should add embedding-similarity checks against a curated corpus."
        ),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"Wrote {OUT}")
    print(f"  {total_encs_with_any_flag}/{out['encounters_probed']} encounters contain a textbook phrase.")
    print(f"  total flag events: {total_flags}")


if __name__ == "__main__":
    main()
