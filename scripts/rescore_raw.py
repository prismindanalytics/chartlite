#!/usr/bin/env python3
"""Post-hoc rescoring pass for scripts/bodhi_raw_generations/*.json.

Applies the latest benchmark scoring to every raw file:
- Re-parses extraction with the improved JSON parser (recovers medgemma1.5 failures)
- Recomputes dx recall — strict (substring) AND semantic (synonym + BODHI-aware)
- Recomputes note scoring, danger arm catches, and overall scores

Writes results back in-place to each raw file. After this, re-run
benchmark_dashboard/scripts/export_data.py to refresh dashboard data.

Usage:  python3 scripts/rescore_raw.py
"""
from __future__ import annotations
import json, os, sys, glob, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import benchmark_bodhi as bb


def main():
    base = os.path.join(os.path.dirname(__file__), "bodhi_raw_generations")
    files = sorted(glob.glob(os.path.join(base, "*.json")))
    for sub in sorted(glob.glob(os.path.join(base, "run*"))):
        if os.path.isdir(sub):
            files += sorted(glob.glob(os.path.join(sub, "*.json")))
    print(f"Rescoring {len(files)} raw files with SequenceMatcher\u20650.5 + decomposition...\n")

    # Encounter lookup by id
    enc_by_id = {i + 1: enc for i, enc in enumerate(bb.ENCOUNTERS)}

    recovered = 0
    changed = 0
    errors = 0
    t0 = time.time()

    for p in files:
        try:
            d = json.loads(open(p).read())
        except Exception as e:
            print(f"  skip {os.path.basename(p)}: {e}")
            errors += 1
            continue

        enc_id = d.get("encounter_id")
        enc = enc_by_id.get(enc_id)
        if not enc:
            continue

        ext = d.get("extraction", {}) or {}
        raw = ext.get("raw", "") or ""
        original_parsed = ext.get("parsed")

        # Try re-parse (might recover previously-failed extractions)
        new_parsed = bb._parse_json(raw) if raw else None

        # If previously failed, but now parseable, flip it
        was_failed = d.get("failed") == "extraction"
        if was_failed and new_parsed is not None and any(new_parsed.get(k) is not None for k in ("diagnoses", "medications", "chief_complaint")):
            d["extraction"]["parsed"] = new_parsed
            d.pop("failed", None)
            recovered += 1
            parsed_to_score = new_parsed
        elif new_parsed and new_parsed != original_parsed:
            d["extraction"]["parsed"] = new_parsed
            parsed_to_score = new_parsed
        else:
            parsed_to_score = original_parsed

        # Rescore extraction with improved (semantic) matcher
        if parsed_to_score:
            eq = bb.extraction_quality(parsed_to_score, enc)
            if d["extraction"].get("score") != eq:
                d["extraction"]["score"] = eq
                changed += 1

        # Save back
        try:
            open(p, "w").write(json.dumps(d, indent=2, default=str))
        except Exception as e:
            print(f"  write failed for {os.path.basename(p)}: {e}")
            errors += 1

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")
    print(f"  Files processed:     {len(files)}")
    print(f"  Extractions recovered (from 'failed'): {recovered}")
    print(f"  Score records updated: {changed}")
    print(f"  Errors: {errors}")


if __name__ == "__main__":
    main()
