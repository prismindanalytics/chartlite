#!/usr/bin/env python3
"""
Pre-process BODHI CSV files into compact JSON for ChartLite Android assets.

Usage:
    python3 scripts/bodhi_to_json.py

Reads from:  scripts/bodhi_raw/{bodhi-s,bodhi-m}/*.csv
Writes to:   app/src/main/assets/bodhi/*.json

BODHI source: https://github.com/eka-care/BODHI (CC BY-NC 4.0)
"""

import csv
import json
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
RAW_DIR = SCRIPT_DIR / "bodhi_raw"
OUTPUT_DIR = SCRIPT_DIR.parent / "app" / "src" / "main" / "assets" / "bodhi"

# Likelihood text -> numeric score for compact storage
LIKELIHOOD_MAP = {
    "very_high": 0.9,
    "high": 0.7,
    "medium": 0.5,
    "low": 0.3,
    "very_low": 0.1,
    "rare": 0.05,
}


def read_csv(subdir: str, filename: str) -> list[dict]:
    path = RAW_DIR / subdir / filename
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def process_conditions():
    """Merge nodes_condition + edges_treated_by (S) + nodes_speciality -> bodhi_conditions.json"""
    conditions = read_csv("bodhi-s", "nodes_condition.csv")
    specialties_raw = read_csv("bodhi-s", "nodes_speciality.csv")
    treated_by = read_csv("bodhi-s", "edges_treated_by.csv")

    # Build specialty lookup
    specialty_map = {row["id"]: row["name"] for row in specialties_raw}

    # Build condition -> specialties map
    condition_specialties: dict[str, list] = {}
    for edge in treated_by:
        cond_id = edge.get("condition_snomed_id", "")
        spec_id = edge.get("speciality_id", "")
        weight = edge.get("weight", "1.0")
        if cond_id and spec_id and spec_id in specialty_map:
            condition_specialties.setdefault(cond_id, []).append({
                "id": spec_id,
                "name": specialty_map[spec_id],
                "weight": safe_float(weight, 1.0),
            })

    result = []
    for row in conditions:
        snomed_id = row.get("snomed_id", "").strip()
        if not snomed_id:
            continue
        entry = {
            "snomedId": snomed_id,
            "name": row.get("name", "").strip(),
            "triageLevel": row.get("triage_level", "").strip() or None,
            "conceptType": row.get("concept_type", "").strip() or None,
        }
        specs = condition_specialties.get(snomed_id, [])
        if specs:
            # Sort by weight descending
            specs.sort(key=lambda s: s["weight"], reverse=True)
            entry["specialties"] = specs
        result.append(entry)

    return result


def process_drugs():
    """Merge nodes_drug + edges_treated_by (M) -> bodhi_drugs.json"""
    drugs = read_csv("bodhi-m", "nodes_drug.csv")
    treated_by = read_csv("bodhi-m", "edges_treated_by.csv")

    # Build drug_hash -> list of treated condition SNOMED IDs
    drug_conditions: dict[str, list[str]] = {}
    for edge in treated_by:
        drug_hash = edge.get("drug_hash", "").strip()
        cond_id = edge.get("concept_snomed_id", "").strip()
        if drug_hash and cond_id:
            drug_conditions.setdefault(drug_hash, []).append(cond_id)

    result = []
    for row in drugs:
        h = row.get("hash", "").strip()
        name = row.get("name", "").strip()
        if not h or not name:
            continue
        entry = {
            "hash": h,
            "name": name,
        }
        tc = row.get("therapeutic_class", "").strip()
        if tc:
            entry["therapeuticClass"] = tc
        conditions = drug_conditions.get(h, [])
        if conditions:
            entry["treatedConditions"] = conditions
        result.append(entry)

    return result


def process_labs():
    """Merge nodes_lab_investigation + edges_monitored_by -> bodhi_labs.json"""
    labs = read_csv("bodhi-m", "nodes_lab_investigation.csv")
    monitored_by = read_csv("bodhi-m", "edges_monitored_by.csv")

    # Build loinc_id -> monitored conditions
    lab_conditions: dict[str, list] = {}
    for edge in monitored_by:
        loinc = edge.get("loinc_id", "").strip()
        cond_id = edge.get("concept_snomed_id", "").strip()
        if loinc and cond_id:
            link = {"snomedId": cond_id}
            polarity = edge.get("polarity", "").strip()
            threshold = edge.get("category_threshold", "").strip()
            if polarity:
                link["polarity"] = polarity
            if threshold:
                link["categoryThreshold"] = threshold
            lab_conditions.setdefault(loinc, []).append(link)

    # Also add edges_impacts (lab -> concept)
    impacts = read_csv("bodhi-m", "edges_impacts.csv")
    lab_impacts: dict[str, list[str]] = {}
    for edge in impacts:
        loinc = edge.get("loinc_id", "").strip()
        cond_id = edge.get("concept_snomed_id", "").strip()
        if loinc and cond_id:
            lab_impacts.setdefault(loinc, []).append(cond_id)

    result = []
    for row in labs:
        loinc = row.get("loinc_id", "").strip()
        name = row.get("name", "").strip()
        display = row.get("display_name", "").strip()
        if not loinc:
            continue
        entry = {
            "loincId": loinc,
            "name": name or display,
            "displayName": display or name,
        }
        system_map = row.get("system_map", "").strip()
        if system_map:
            entry["systemMap"] = system_map

        monitored = lab_conditions.get(loinc, [])
        impacted = lab_impacts.get(loinc, [])
        # Combine: monitored conditions + impacted conditions (dedup)
        all_condition_ids = set()
        combined = []
        for m in monitored:
            if m["snomedId"] not in all_condition_ids:
                all_condition_ids.add(m["snomedId"])
                combined.append(m)
        for cid in impacted:
            if cid not in all_condition_ids:
                all_condition_ids.add(cid)
                combined.append({"snomedId": cid})
        if combined:
            entry["monitoredConditions"] = combined
        result.append(entry)

    return result


def process_symptoms():
    """Merge edges_present_in + nodes_symptom -> bodhi_symptoms.json

    Output: map of condition_snomed_id -> list of {name, likelihood, strongPredictor}
    """
    symptoms_raw = read_csv("bodhi-s", "nodes_symptom.csv")
    present_in = read_csv("bodhi-s", "edges_present_in.csv")

    # Build symptom UUID -> name lookup
    symptom_names: dict[str, str] = {}
    for row in symptoms_raw:
        uuid = row.get("uuid", "").strip()
        name = row.get("name", "").strip()
        if uuid and name:
            symptom_names[uuid] = name

    # Build condition -> symptoms
    result: dict[str, list] = {}
    for edge in present_in:
        sym_uuid = edge.get("symptom_uuid", "").strip()
        cond_id = edge.get("condition_snomed_id", "").strip()
        if not sym_uuid or not cond_id:
            continue
        sym_name = symptom_names.get(sym_uuid)
        if not sym_name:
            continue

        likelihood_text = edge.get("likelihood_symptom_given_condition", "").strip()
        likelihood = LIKELIHOOD_MAP.get(likelihood_text)
        strong = edge.get("strong_predictor", "").strip() == "1"

        entry = {"name": sym_name}
        if likelihood is not None:
            entry["likelihood"] = likelihood
        if strong:
            entry["strongPredictor"] = True

        result.setdefault(cond_id, []).append(entry)

    # Sort each condition's symptoms by likelihood descending
    for cond_id in result:
        result[cond_id].sort(
            key=lambda s: (s.get("likelihood", 0), s.get("strongPredictor", False)),
            reverse=True,
        )

    return result


def safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def write_json(data, filename: str):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
    size_kb = os.path.getsize(path) / 1024
    return size_kb


def main():
    print("Processing BODHI CSVs -> JSON...")
    print()

    conditions = process_conditions()
    size = write_json(conditions, "bodhi_conditions.json")
    print(f"  bodhi_conditions.json: {len(conditions)} conditions ({size:.1f} KB)")

    drugs = process_drugs()
    size = write_json(drugs, "bodhi_drugs.json")
    print(f"  bodhi_drugs.json: {len(drugs)} drugs ({size:.1f} KB)")

    labs = process_labs()
    size = write_json(labs, "bodhi_labs.json")
    print(f"  bodhi_labs.json: {len(labs)} labs ({size:.1f} KB)")

    symptoms = process_symptoms()
    total_links = sum(len(v) for v in symptoms.values())
    size = write_json(symptoms, "bodhi_symptoms.json")
    print(f"  bodhi_symptoms.json: {len(symptoms)} conditions, {total_links} symptom links ({size:.1f} KB)")

    print()
    print("Done! Files written to app/src/main/assets/bodhi/")


if __name__ == "__main__":
    main()
