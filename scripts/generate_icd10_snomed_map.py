#!/usr/bin/env python3
"""
Generate app/src/main/assets/bodhi/icd10_snomed_map.json

Maps ICD-10 PHC top 300 codes to BODHI SNOMED IDs using a hybrid strategy:
  1. Manual overrides for common PHC conditions (hand-verified, confidence 1.0)
  2. Token-based fuzzy matching for the rest, filtered to conceptType=Disorder
     with a 0.65 confidence threshold (better to leave unmapped than wrong).

Run from repo root:
  python3 scripts/generate_icd10_snomed_map.py

Re-run whenever:
  - bodhi/bodhi_conditions.json changes
  - icd10/phc_top300.json changes
  - You add a new manual override
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ICD_PATH = REPO / 'app/src/main/assets/icd10/phc_top300.json'
BODHI_PATH = REPO / 'app/src/main/assets/bodhi/bodhi_conditions.json'
OUT_PATH = REPO / 'app/src/main/assets/bodhi/icd10_snomed_map.json'

STOPWORDS = {
    'acute', 'chronic', 'unspecified', 'nos', 'other', 'common', 'simple',
    'of', 'the', 'and', 'or', 'in', 'at', 'on', 'to', 'due', 'from',
    'with', 'without', 'history',
    'mild', 'moderate', 'severe', 'disease', 'disorder', 'syndrome',
    'primary', 'secondary', 'type', 'stage', 'grade',
}

SYNONYMS = {
    'mellitus': 'diabetes', 'htn': 'hypertension',
    'copd': 'obstructive pulmonary', 'uti': 'urinary tract infection',
    'uri': 'upper respiratory', 'gerd': 'reflux',
    'mi': 'myocardial infarction', 'cva': 'stroke cerebrovascular',
    'dka': 'diabetic ketoacidosis', 'pid': 'pelvic inflammatory',
    'tb': 'tuberculosis',
}

# Hand-verified mappings for common PHC diagnoses.
# If a target name isn't found in BODHI it's printed as a conflict.
# Note: HIV (B20) has no BODHI concept — intentionally unmapped.
MANUAL_OVERRIDES = {
    'A09': 'Acute gastroenteritis',
    'B54': 'Malaria',
    'B50.9': 'Malaria',
    'A16.2': 'Pulmonary tuberculosis',
    'I10': 'Hypertension',
    'I21.9': 'Acute myocardial infarction',
    'J06.9': 'Upper respiratory infection',
    'J18.9': 'Pneumonia',
    'J45.9': 'Asthma',
    'J44.9': 'Chronic obstructive lung disease',
    'E10.9': 'Diabetes mellitus type 1',
    'E11.9': 'Diabetes Type 2',
    'K29.7': 'Gastritis',
    'K21.9': 'Gastroesophageal Reflux Disease',
    'N39.0': 'UTI (Urinary tract infectious disease)',
    'N30.0': 'Cystitis',
    'L08.9': 'Cellulitis',
    'F32.9': 'Depression',
    'F41.1': 'Generalised Anxiety disorder (GAD)',
    'M54.5': 'Mechanical back pain',
    'G43.9': 'Migraine',
    'G44.2': 'Tension Headache',
    'O24.4': 'Gestational Diabetes Mellitus',
}

AUTO_THRESHOLD = 0.65


def tokenize(s):
    s = s.lower()
    for k, v in SYNONYMS.items():
        s = re.sub(r'\b' + re.escape(k) + r'\b', v, s)
    return {t for t in re.findall(r'[a-z]+', s) if len(t) > 2 and t not in STOPWORDS}


def acuity(name):
    n = name.lower()
    if 'acute' in n or 'sudden' in n:
        return 'acute'
    if 'chronic' in n or 'long-term' in n:
        return 'chronic'
    return None


def score_match(icd_tokens, bodhi_tokens, icd_name, bodhi_name):
    if not icd_tokens or not bodhi_tokens:
        return 0.0
    inter = icd_tokens & bodhi_tokens
    if not inter:
        return 0.0
    jaccard = len(inter) / len(icd_tokens | bodhi_tokens)
    coverage = len(inter) / min(len(icd_tokens), len(bodhi_tokens))
    score = 0.5 * jaccard + 0.5 * coverage
    a1, a2 = acuity(icd_name), acuity(bodhi_name)
    if a1 and a2 and a1 != a2:
        score *= 0.5
    return score


def main():
    icd = json.loads(ICD_PATH.read_text())['codes']
    all_conditions = json.loads(BODHI_PATH.read_text())

    disorders = [
        c for c in all_conditions
        if c.get('conceptType') == 'Disorder'
        and not c['name'].startswith(('FH ', 'H/O '))
    ]
    bodhi_tokens_cache = [(d, tokenize(d['name'])) for d in disorders]
    bodhi_by_name = {d['name'].lower(): d for d in disorders}

    mappings = {}
    stats = Counter()
    conflicts = []

    for code_entry in icd:
        code = code_entry['code']
        desc = code_entry['description']
        keywords = code_entry.get('keywords', [])

        if code in MANUAL_OVERRIDES:
            target = bodhi_by_name.get(MANUAL_OVERRIDES[code].lower())
            if target:
                mappings[code] = {
                    'snomedId': target['snomedId'],
                    'bodhiName': target['name'],
                    'confidence': 1.0,
                    'triage': target.get('triageLevel'),
                    'icdDesc': desc,
                    'source': 'manual',
                }
                stats['manual'] += 1
                continue
            else:
                conflicts.append(f'{code} target "{MANUAL_OVERRIDES[code]}" not found')

        icd_tokens = tokenize(desc)
        for kw in keywords:
            icd_tokens |= tokenize(kw)
        best_score, best_match = 0.0, None
        for disorder, bodhi_tokens in bodhi_tokens_cache:
            s = score_match(icd_tokens, bodhi_tokens, desc, disorder['name'])
            if s > best_score:
                best_score, best_match = s, disorder

        if best_score >= AUTO_THRESHOLD and best_match is not None:
            mappings[code] = {
                'snomedId': best_match['snomedId'],
                'bodhiName': best_match['name'],
                'confidence': round(best_score, 2),
                'triage': best_match.get('triageLevel'),
                'icdDesc': desc,
                'source': 'auto',
            }
            stats['auto'] += 1
        else:
            stats['unmapped'] += 1

    result = {
        'version': 1,
        'source': 'Derived from PHC top 300 ICD-10 + BODHI (Eka.Care) Disorder conditions',
        'attribution': 'BODHI knowledge graph: https://github.com/eka-care/BODHI (CC BY-NC 4.0)',
        'generatedFrom': {
            'icdVersion': '2026.1',
            'bodhiDisorders': len(disorders),
            'thresholdAuto': AUTO_THRESHOLD,
            'manualOverrides': len(MANUAL_OVERRIDES),
        },
        'mappings': mappings,
    }
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    total = len(icd)
    mapped = stats['manual'] + stats['auto']
    print(f'Wrote {OUT_PATH.relative_to(REPO)}')
    print(f'ICD codes: {total}')
    print(f'Mapped: {mapped} ({100 * mapped / total:.0f}%)  '
          f'[manual: {stats["manual"]}, auto: {stats["auto"]}]')
    print(f'Unmapped: {stats["unmapped"]}')
    if conflicts:
        print(f'\nCONFLICTS:', file=sys.stderr)
        for c in conflicts:
            print(f'  {c}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
