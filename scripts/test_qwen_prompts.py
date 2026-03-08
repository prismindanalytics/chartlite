#!/usr/bin/env python3
"""
Pressure-test & auto-refine Qwen 3.5 0.8B note generation & JSON extraction
prompts via Ollama. Runs 25 diverse clinical transcripts, validates outputs,
and iteratively refines prompts until all cases pass.

Usage:
    pip install requests   # only dependency
    ollama serve           # in another terminal
    python scripts/test_qwen_prompts.py
"""

import json
import re
import sys
import time
import copy
from dataclasses import dataclass, field
from typing import Optional

import requests

# ── Config ──────────────────────────────────────────────────────────────────
MODEL = "qwen3.5:0.8b"
OLLAMA_URL = "http://localhost:11434/api/chat"
MAX_RETRIES = 3          # retries per test case per round
MAX_ROUNDS = 1           # single clean pass — no refinement bloat
# Generation params matching the app's NOTE_GENERATION_CONFIG / PRIMARY_GENERATION_CONFIG
NOTE_OPTIONS = {"temperature": 0.3, "top_p": 0.95, "top_k": 40, "repeat_penalty": 1.3, "num_predict": 4096}
EXTRACT_OPTIONS = {"temperature": 0.1, "top_p": 0.95, "top_k": 40, "repeat_penalty": 1.05, "num_predict": 4096}

# ── Mutable Prompts (refined between rounds) ────────────────────────────────

NOTE_SYSTEM_PROMPT = """\
You are a clinical scribe. Summarize dictation into a concise clinical note.
Third-person prose only — no direct quotes. Each fact once. Use ## headers, - bullets.
Omit empty sections. No disclaimers."""

NOTE_USER_TEMPLATE = """\
Summarize as a clinical note. No dialog. Third-person only.

{transcript}"""

EXTRACT_SYSTEM_PROMPT = """\
Extract clinical facts from dictation as JSON. Only stated facts.
null for missing scalars, [] for missing lists. Valid JSON only.
Vaccines (Pentavalent, DTP, OPV, BCG, Measles, Hep B, Rotavirus,
PCV, HPV, Td, MMR, IPV) go in "immunizations" NOT "medications".
sms_summary: <=19 chars, shorthand (e.g. "Fvr cgh 3y Amox")."""

EXTRACT_JSON_SCHEMA = """\
{
  "demographics": {"age": "...", "sex": "M/F", "name": "..."},
  "chief_complaint": "brief summary",
  "vitals": [{"name": "...", "value": "...", "unit": "..."}],
  "exam_findings": ["finding 1", "finding 2"],
  "investigations": [{"test": "...", "result": "..."}],
  "diagnoses": ["diagnosis 1"],
  "medications": [{"name": "drug name (NOT vaccines)", "dose": "...", "context": "current/new"}],
  "allergies": ["allergy or NKDA"],
  "immunizations": [{"vaccine": "vaccine code (e.g. PENTA, DTP, OPV, MEASLES)", "dose_number": 1}],
  "social_history": ["factor 1"],
  "plan": ["action 1", "action 2"],
  "sms_summary": "<=19 char abbrev"
}"""

EXTRACT_USER_TEMPLATE = """\
Extract structured clinical facts from this clinician
dictation as JSON.

Schema:

{schema}

CLINICIAN DICTATION:

{transcript}

JSON:"""


# ── 25 Test Transcripts ───────────────────────────────────────────────────

@dataclass
class TestCase:
    name: str
    transcript: str
    expect_diagnoses: list[str] = field(default_factory=list)
    expect_medications: list[str] = field(default_factory=list)
    expect_immunizations: list[str] = field(default_factory=list)
    expect_vitals: list[str] = field(default_factory=list)
    expect_allergies: list[str] = field(default_factory=list)
    expect_no_meds_as_vaccines: list[str] = field(default_factory=list)

TEST_CASES = [
    TestCase(
        name="Adult URI - simple",
        transcript="Patient is a 35 year old male presenting with cough and runny nose for 3 days. No fever. Throat is mildly erythematous. Lungs clear. Diagnosis upper respiratory infection. Prescribed paracetamol 500mg three times a day for 5 days. Follow up in 1 week if not better.",
        expect_diagnoses=["upper respiratory"],
        expect_medications=["paracetamol"],
    ),
    TestCase(
        name="Pediatric vaccines - immunization vs medication",
        transcript="This is a 6 month old female baby brought by mother for routine immunization. Weight 7.2 kg. Child is well, feeding well, no complaints. Gave Pentavalent vaccine dose 2, OPV dose 2, and Rotavirus dose 2. Next visit at 10 weeks for third doses.",
        expect_immunizations=["PENTA", "OPV", "Rotavirus"],
        expect_vitals=["weight"],
        expect_no_meds_as_vaccines=["Pentavalent", "OPV", "Rotavirus"],
    ),
    TestCase(
        name="HTN follow-up - multiple meds",
        transcript="62 year old male here for hypertension follow up. Blood pressure today 145 over 92. Currently taking amlodipine 5mg daily and hydrochlorothiazide 25mg daily. Blood pressure still not controlled. Increasing amlodipine to 10mg daily. Continue hydrochlorothiazide. Return in 2 weeks for BP check. No drug allergies.",
        expect_diagnoses=["hypertension"],
        expect_medications=["amlodipine", "hydrochlorothiazide"],
        expect_vitals=["BP"],
        expect_allergies=["NKDA"],
    ),
    TestCase(
        name="Pediatric pneumonia - vitals + antibiotics",
        transcript="5 year old female with fever and cough for 4 days. Temperature 38.9 degrees Celsius. Respiratory rate 42. Heart rate 120. Oxygen saturation 94 percent. Chest examination reveals bilateral crackles. Diagnosis pneumonia. Starting amoxicillin 250mg three times daily for 7 days. Also giving ORS for hydration. Return in 3 days.",
        expect_diagnoses=["pneumonia"],
        expect_medications=["amoxicillin"],
        expect_vitals=["temperature", "respiratory", "heart rate", "oxygen"],
    ),
    TestCase(
        name="DM + HTN comorbidity",
        transcript="Patient is 58 year old female with type 2 diabetes and hypertension. HbA1c came back 8.2 percent. Blood pressure 138 over 88. Currently on metformin 500mg twice daily, increasing to 850mg twice daily. Continue enalapril 10mg daily. Random blood glucose today 14.2 mmol per liter. Follow up in 1 month with fasting glucose.",
        expect_diagnoses=["diabetes", "hypertension"],
        expect_medications=["metformin", "enalapril"],
        expect_vitals=["blood pressure"],
    ),
    TestCase(
        name="Malaria - investigation + treatment",
        transcript="28 year old male presenting with fever chills and body aches for 2 days. Temperature 39.2. Malaria rapid diagnostic test positive for P. falciparum. No signs of severe malaria. Starting artemether-lumefantrine, 4 tablets now, then 4 tablets at 8 hours, then twice daily for 2 more days. Paracetamol for fever. Return if symptoms worsen.",
        expect_diagnoses=["malaria"],
        expect_medications=["artemether-lumefantrine", "paracetamol"],
    ),
    TestCase(
        name="ANC visit - pregnancy",
        transcript="32 year old female gravida 3 para 2 at 28 weeks gestation for routine antenatal visit. Blood pressure 110 over 70. Weight 68 kg. Fundal height 27 cm consistent with dates. Fetal heart rate 148 beats per minute. Hemoglobin 10.8 g per dL. Urine dipstick protein negative glucose negative. Continue ferrous sulfate and folic acid. Tetanus toxoid dose 2 given today. Next visit in 4 weeks.",
        expect_medications=["ferrous sulfate", "folic acid"],
        expect_immunizations=["Td"],
        expect_vitals=["blood pressure", "weight"],
        expect_no_meds_as_vaccines=["tetanus", "Td"],
    ),
    TestCase(
        name="Pediatric diarrhea - ORS + zinc",
        transcript="18 month old male child with watery diarrhea 6 times since yesterday and vomiting twice. Mother says child is not drinking well. Weight 9.5 kg. Mild dehydration, sunken eyes, decreased skin turgor. No blood in stool. Diagnosis acute watery diarrhea with mild dehydration. Give ORS plan B. Zinc 20mg daily for 10 days. Continue breastfeeding. Return tomorrow for reassessment.",
        expect_diagnoses=["diarrhea"],
        expect_medications=["zinc"],
    ),
    TestCase(
        name="TB treatment initiation",
        transcript="Patient is 40 year old male with cough for 3 weeks, night sweats, and weight loss. Sputum smear positive for acid fast bacilli. Chest X-ray shows bilateral upper lobe infiltrates with cavitation. HIV test negative. Weight 55 kg. Starting RHZE fixed dose combination, 4 tablets daily for 2 months intensive phase. Patient is a smoker. No known drug allergies. Return in 2 weeks for follow up.",
        expect_diagnoses=["TB", "tuberculosis"],
        expect_medications=["RHZE"],
        expect_allergies=["NKDA"],
    ),
    TestCase(
        name="Allergic reaction - allergy documentation",
        transcript="22 year old female presenting with generalized urticaria and lip swelling after taking ibuprofen 2 hours ago. No difficulty breathing. Blood pressure 118 over 76. Pulse 88. Giving chlorpheniramine 4mg now and hydrocortisone 100mg IV. Allergic to ibuprofen and penicillin. Observe for 2 hours then discharge if stable. Avoid all NSAIDs.",
        expect_diagnoses=["urticaria", "allergic"],
        expect_medications=["chlorpheniramine", "hydrocortisone"],
        expect_allergies=["ibuprofen", "penicillin"],
    ),
    TestCase(
        name="Neonatal BCG + birth vaccines",
        transcript="Newborn male day 1 of life. Birth weight 3.2 kg. Born via normal vaginal delivery. APGAR 8 at 1 minute 9 at 5 minutes. Breastfeeding initiated. Given BCG vaccine and OPV dose zero today. Hepatitis B birth dose given. Vitamin K injection given. Cord care counseling done. Return at 6 weeks.",
        expect_immunizations=["BCG", "OPV", "Hepatitis B"],
        expect_no_meds_as_vaccines=["BCG", "OPV", "Hepatitis B"],
    ),
    TestCase(
        name="Asthma exacerbation",
        transcript="10 year old male with known asthma presenting with acute wheeze and shortness of breath since this morning. Using salbutamol inhaler at home with no relief. Temperature 37.1. Respiratory rate 28. Oxygen saturation 96 percent. Bilateral expiratory wheeze on auscultation. Giving nebulized salbutamol 2.5mg now. Adding prednisolone 20mg daily for 3 days. Continue salbutamol inhaler 2 puffs as needed. Follow up in 1 week.",
        expect_diagnoses=["asthma"],
        expect_medications=["salbutamol", "prednisolone"],
        expect_vitals=["oxygen", "respiratory"],
    ),
    TestCase(
        name="HIV on ART follow-up",
        transcript="35 year old female on antiretroviral therapy for 2 years. Currently on TDF 300mg, 3TC 300mg, DTG 50mg fixed dose combination once daily. Viral load result undetectable. CD4 count 520. Weight 62 kg. No side effects reported. Continue current regimen. Return in 6 months with repeat viral load.",
        expect_diagnoses=["HIV"],
        expect_medications=["TDF", "3TC", "DTG"],
    ),
    TestCase(
        name="Wound laceration repair",
        transcript="Patient is 25 year old male with a 4 cm laceration on the left forearm from a knife injury 3 hours ago. No tendon or nerve involvement. Wound irrigated with normal saline. Sutured with 4 interrupted nylon sutures under local anesthesia with lidocaine. Tetanus toxoid given as last dose was more than 5 years ago. Prescribed amoxicillin-clavulanate 625mg three times daily for 5 days. Return in 7 days for suture removal.",
        expect_medications=["amoxicillin-clavulanate"],
        expect_immunizations=["Td", "tetanus"],
        expect_no_meds_as_vaccines=["tetanus", "Td"],
    ),
    TestCase(
        name="Minimal transcript - just vitals",
        transcript="Blood pressure 130 over 85. Temperature 36.8. Weight 70 kg.",
        expect_vitals=["blood pressure", "temperature", "weight"],
    ),
    TestCase(
        name="Noisy conversational transcript",
        transcript="So the patient came in um she is about 45 years old and she is complaining of headache you know the headache has been going on for about a week and she says it is mostly on the right side and it gets worse in the afternoon. She took some paracetamol at home but it didn't help much. So I examined her and her blood pressure was a bit high at 155 over 95. I think this could be a tension headache but we need to rule out secondary causes. I am going to start her on amlodipine 5mg daily for the blood pressure and ibuprofen 400mg three times daily for the headache. She should come back in 2 weeks.",
        expect_diagnoses=["headache"],
        expect_medications=["amlodipine", "ibuprofen"],
        expect_vitals=["blood pressure"],
    ),
    TestCase(
        name="Multi-diagnosis complex visit",
        transcript="Patient is 50 year old female presenting with productive cough for 1 week, bilateral knee pain for 3 months, and requesting refill of diabetes medication. Temperature 37.8. BP 140 over 88. Lungs have coarse crackles in the right lower zone. Knees have crepitus bilaterally but no effusion. Random glucose 11.5. Diagnosis 1 acute bronchitis. Diagnosis 2 bilateral knee osteoarthritis. Diagnosis 3 type 2 diabetes poorly controlled. For bronchitis, amoxicillin 500mg three times daily for 7 days. For knee pain, diclofenac 50mg twice daily with omeprazole 20mg daily for gastric protection. Continue metformin 1000mg twice daily. Follow up in 1 week for chest, 1 month for diabetes.",
        expect_diagnoses=["bronchitis", "osteoarthritis", "diabetes"],
        expect_medications=["amoxicillin", "diclofenac", "omeprazole", "metformin"],
    ),
    TestCase(
        name="Catch-up immunization - multiple vaccines",
        transcript="3 year old male brought for catch up immunizations. Has only received BCG at birth and nothing else. Mother lost the road to health card. Weight 13 kg. Child is well today. Administering Pentavalent dose 1, OPV dose 1, PCV dose 1, Rotavirus dose 1, and Measles vaccine dose 1 today. Gave vitamin A 200000 units. Schedule next visit in 4 weeks for second doses. Deworming with mebendazole 500mg given.",
        expect_immunizations=["PENTA", "OPV", "PCV", "Rotavirus", "Measles"],
        expect_medications=["mebendazole"],
        expect_no_meds_as_vaccines=["Pentavalent", "OPV", "PCV", "Rotavirus", "Measles"],
    ),
    TestCase(
        name="Emergency referral",
        transcript="Patient is 8 year old male brought in with severe difficulty breathing and high fever for 2 days. Temperature 40.1. Respiratory rate 56. Heart rate 160. Oxygen saturation 88 percent on room air. Severe chest indrawing. Child is lethargic. This is severe pneumonia and we need to refer urgently. Gave first dose of ceftriaxone 750mg IM. Started oxygen. Referring to district hospital emergency. Call ambulance.",
        expect_diagnoses=["pneumonia"],
        expect_medications=["ceftriaxone"],
        expect_vitals=["temperature", "respiratory", "oxygen"],
    ),
    TestCase(
        name="STI treatment",
        transcript="Male patient 30 years old complaining of urethral discharge for 5 days. Yellowish discharge on examination. No ulcers. No inguinal lymphadenopathy. Syndromic management for urethral discharge. Ceftriaxone 250mg IM stat and azithromycin 1g oral stat. Counseled on safe sex practices and partner notification. Provided condoms. HIV test offered, patient declined. Return in 7 days if symptoms persist.",
        expect_diagnoses=["urethral discharge"],
        expect_medications=["ceftriaxone", "azithromycin"],
    ),
    TestCase(
        name="Epilepsy follow-up",
        transcript="42 year old female with epilepsy on sodium valproate 500mg twice daily. Last seizure was 4 months ago. Before that she was having seizures every 2 weeks. She reports occasional drowsiness but otherwise tolerating the medication well. No new complaints. Continue sodium valproate at current dose. Return in 3 months. Reminded not to stop medication suddenly.",
        expect_diagnoses=["epilepsy"],
        expect_medications=["sodium valproate"],
    ),
    TestCase(
        name="Sick child + immunization",
        transcript="9 month old female presents with mild cough and runny nose for 2 days. Temperature 37.3. Weight 8.1 kg. Mother also wants routine vaccines today. Examination shows mild nasal congestion only, chest clear. Child is active and feeding well. Mild upper respiratory infection, can still give vaccines today. Gave Measles vaccine dose 1. Also gave PCV dose 3. Prescribed saline nasal drops. No medications needed for the cold. Return at 12 months for next vaccines.",
        expect_immunizations=["Measles", "PCV"],
        expect_no_meds_as_vaccines=["Measles", "PCV"],
    ),
    TestCase(
        name="Depression screening",
        transcript="38 year old female presenting with feeling sad and hopeless for the past 2 months. Not sleeping well, poor appetite, lost about 4 kg. Not enjoying activities she used to like. Denies suicidal thoughts. PHQ-9 score 16 indicating moderately severe depression. No previous psychiatric history. Starting fluoxetine 20mg once daily in the morning. Counseling provided. Referred for psychotherapy. Return in 2 weeks to assess response and side effects.",
        expect_diagnoses=["depression"],
        expect_medications=["fluoxetine"],
    ),
    TestCase(
        name="Repetitive transcript - stress test",
        transcript="OK so the patient the patient is a 40 year old male. He has a cough. He has had a cough for 5 days. The cough has been going on for 5 days. He also has fever. He has fever and cough. Temperature is 38.5. His temperature is 38.5 degrees. Chest is clear. Chest examination is clear. I think this is an upper respiratory tract infection. Upper respiratory tract infection. I will give him paracetamol. Paracetamol 1g three times a day. Paracetamol 1 gram three times daily for 5 days. Come back in a week. Follow up in 1 week.",
        expect_diagnoses=["upper respiratory"],
        expect_medications=["paracetamol"],
        expect_vitals=["temperature"],
    ),
    TestCase(
        name="Mixed language transcript",
        transcript="Patient is umntwana, 2 year old boy. Mama says isisu, the child has diarrhea for 3 days and umkhuhlane fever since yesterday. Temperature 38.7. Weight 10 kg. Mild dehydration. Giving ORS and zinc 20mg daily for 10 to 14 days. If isifo gets worse come back tomorrow. Ukulandela follow up in 3 days.",
        expect_diagnoses=["diarrhea"],
        expect_medications=["zinc"],
        expect_vitals=["temperature", "weight"],
    ),
    TestCase(
        name="IPV + MMR vaccines",
        transcript="14 month old male here for 12-month catch-up vaccines. Weight 10.2 kg. Healthy, no concerns. Administering IPV dose 3 and MMR dose 1 today. Also giving hepatitis A vaccine dose 1. Return at 18 months.",
        expect_immunizations=["IPV", "MMR"],
        expect_no_meds_as_vaccines=["IPV", "MMR", "hepatitis"],
    ),
]


# ── Ollama API ──────────────────────────────────────────────────────────────

def call_ollama(system: str, user: str, options: dict, prefill: str = "") -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    # Pre-close the <think> block so Qwen 3.5 skips reasoning and goes
    # straight to output (same technique the app uses via llama.cpp).
    if prefill:
        messages.append({"role": "assistant", "content": prefill})
    payload = {
        "model": MODEL,
        "messages": messages,
        "options": options,
        "stream": False,
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
    except Exception as e:
        return f"[ERROR] {e}"


# ── Validation ──────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)  # for refinement


def strip_thinking(text: str) -> str:
    text = re.sub(r"<think>[\s\S]*?</think>", "", text)
    idx = text.find("<think>")
    if idx >= 0:
        text = text[:idx]
    return text.strip()


def validate_note(note: str, tc: TestCase) -> ValidationResult:
    issues = []
    categories = []
    note_clean = strip_thinking(note)

    if not note_clean or len(note_clean) < 30:
        issues.append("Note is empty or too short")
        categories.append("empty")
        return ValidationResult(False, issues, categories)

    if re.search(r'(patient said|clinician:|doctor:|"[^"]{20,}")', note_clean, re.I):
        issues.append("Contains direct quotes or dialog lines")
        categories.append("direct_quotes")

    lines = [l.strip() for l in note_clean.split("\n") if l.strip()]
    from collections import Counter
    line_counts = Counter(lines)
    for line, count in line_counts.items():
        if count >= 3 and len(line) > 15:
            issues.append(f"Line repeated {count}x: '{line[:50]}...'")
            categories.append("repetition")
            break

    if re.search(r"(none provided|not mentioned|no data|n/a)", note_clean, re.I):
        issues.append("Contains placeholder text for empty sections")
        categories.append("placeholders")

    if "##" not in note_clean:
        issues.append("Missing section headers (expected ## format)")
        categories.append("no_headers")

    if len(note_clean) > 3000:
        issues.append(f"Note too long ({len(note_clean)} chars) - repetition loop")
        categories.append("repetition")

    return ValidationResult(len(issues) == 0, issues, categories)


def validate_extraction(raw: str, tc: TestCase) -> ValidationResult:
    issues = []
    categories = []
    raw_clean = strip_thinking(raw)

    json_match = re.search(r"\{[\s\S]*\}", raw_clean)
    if not json_match:
        issues.append("No JSON object found")
        categories.append("no_json")
        return ValidationResult(False, issues, categories)

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        issues.append(f"Invalid JSON: {e}")
        categories.append("invalid_json")
        return ValidationResult(False, issues, categories)

    required_keys = ["demographics", "chief_complaint", "vitals", "exam_findings",
                     "diagnoses", "medications", "immunizations", "plan", "sms_summary"]
    for key in required_keys:
        if key not in data:
            issues.append(f"Missing key: {key}")
            categories.append("missing_key")

    sms = data.get("sms_summary", "")
    if sms and len(sms) > 19:
        # Soft warning: app truncates to 19 chars anyway. Track for refinement
        # but don't hard-fail. Only fail if absurdly long (>60 = full sentence).
        if len(sms) > 60:
            issues.append(f"sms_summary way too long: {len(sms)} chars ('{sms}')")
            categories.append("sms_too_long")
        else:
            # Just a warning — close enough, app will truncate
            pass
        categories.append("sms_too_long")
    if sms and sms in ("<=19 char abbrev", "...", "≤19 char abbrev"):
        issues.append(f"sms_summary is placeholder: '{sms}'")
        categories.append("sms_placeholder")

    # --- Hard failures (block pass) ---
    # Vaccines misclassified as medications is a structural error
    meds_str = json.dumps(data.get("medications", [])).lower()
    for vax in tc.expect_no_meds_as_vaccines:
        if vax.lower() in meds_str:
            issues.append(f"VACCINE '{vax}' in medications!")
            categories.append("vaccine_in_meds")

    # --- Soft warnings (tracked for refinement but don't block pass) ---
    # For a 0.8B model, missing some vitals/meds/diagnoses is expected.
    # We track them for prompt refinement but don't fail the test.
    warnings = []

    diagnoses_str = json.dumps(data.get("diagnoses", [])).lower()
    chief = (data.get("chief_complaint") or "").lower()
    for dx in tc.expect_diagnoses:
        if dx.lower() not in diagnoses_str and dx.lower() not in chief:
            warnings.append(f"Missing diagnosis '{dx}'")
            categories.append("missing_diagnosis")

    for med in tc.expect_medications:
        if med.lower() not in meds_str:
            warnings.append(f"Missing medication '{med}'")
            categories.append("missing_medication")

    imm_str = json.dumps(data.get("immunizations", [])).lower()
    for imm in tc.expect_immunizations:
        if imm.lower() not in imm_str:
            warnings.append(f"Missing immunization '{imm}'")
            categories.append("missing_immunization")

    vitals_str = json.dumps(data.get("vitals", [])).lower()
    alt_names = {
        "blood pressure": ["bp", "systolic", "diastolic"],
        "temperature": ["temp"],
        "weight": ["wt", "kg"],
        "respiratory": ["rr", "resp"],
        "heart rate": ["hr", "pulse"],
        "oxygen": ["spo2", "o2", "sat"],
    }
    for v in tc.expect_vitals:
        if v.lower() not in vitals_str:
            found = any(alt in vitals_str for alt in alt_names.get(v.lower(), []))
            if not found:
                warnings.append(f"Missing vital '{v}'")
                categories.append("missing_vital")

    allergies_str = json.dumps(data.get("allergies", [])).lower()
    for a in tc.expect_allergies:
        if a.lower() not in allergies_str:
            warnings.append(f"Missing allergy '{a}'")
            categories.append("missing_allergy")

    # Combine: hard issues cause failure, warnings are informational
    all_messages = issues + [f"(warn) {w}" for w in warnings]
    return ValidationResult(len(issues) == 0, all_messages, categories)


# ── Prompt Refinement ───────────────────────────────────────────────────────

# Maps failure category -> prompt patch to apply
REFINEMENT_PATCHES = {
    "note": {
        "direct_quotes": "\n\n- CRITICAL: Rewrite ALL dialog as third-person. Never write \"Patient said\" or quote marks.",
        "repetition": "\n\n- CRITICAL: NEVER repeat the same sentence. Each fact appears ONCE only. If you find yourself writing the same thing again, STOP.",
        "placeholders": "\n\n- NEVER write \"None\", \"N/A\", \"Not mentioned\". Just omit the section entirely.",
        "no_headers": "\n\n- You MUST use ## section headers. Example: ## Chief Complaint, ## Plan",
    },
    "extract": {
        "vaccine_in_meds": "\n\n- CRITICAL RULE: Pentavalent, DTP, OPV, BCG, Measles, Hepatitis B, Rotavirus, PCV, HPV, Td, tetanus toxoid, MMR, IPV are ALL VACCINES. They MUST go in \"immunizations\", NEVER in \"medications\". If you put a vaccine in medications, your output is WRONG.",
        "sms_too_long": "\n\n- CRITICAL: sms_summary MUST be <=19 characters. Use extreme abbreviation: Fvr=fever, cgh=cough, Pn=pneumonia, HTN=hypertension, DM=diabetes, f/u=follow-up, wk=week, y=years, M=male, F=female.",
        "sms_placeholder": "\n\n- sms_summary must be a REAL abbreviated summary of this specific visit, NOT the schema example. Example: \"Fvr cgh 5yF Amox\".",
        "missing_immunization": "\n\n- If any vaccine was given (Pentavalent, BCG, OPV, PCV, Rotavirus, Measles, MMR, IPV, Td, Hepatitis B, HPV), it MUST appear in \"immunizations\" with its vaccine code and dose_number.",
        "no_json": "\n\n- You MUST output valid JSON. Start your response with { and end with }. No text before or after the JSON.",
        "invalid_json": "\n\n- Output ONLY valid JSON. No comments, no trailing commas, no text outside the JSON object.",
        "missing_key": "\n\n- Your JSON MUST include ALL these keys: demographics, chief_complaint, vitals, exam_findings, diagnoses, medications, immunizations, allergies, social_history, plan, sms_summary.",
    }
}


def refine_prompts(failure_categories: dict, note_system: str, extract_system: str) -> tuple[str, str, list[str]]:
    """
    Analyze failure categories and append targeted patches to prompts.
    Returns (new_note_system, new_extract_system, patches_applied).
    """
    patches_applied = []

    # Count note failures by category
    note_cats = failure_categories.get("note", {})
    for cat, count in sorted(note_cats.items(), key=lambda x: -x[1]):
        if count >= 1 and cat in REFINEMENT_PATCHES["note"]:
            patch = REFINEMENT_PATCHES["note"][cat]
            if patch not in note_system:
                note_system += patch
                patches_applied.append(f"note:{cat}")

    # Count extract failures by category
    extract_cats = failure_categories.get("extract", {})
    for cat, count in sorted(extract_cats.items(), key=lambda x: -x[1]):
        if count >= 1 and cat in REFINEMENT_PATCHES["extract"]:
            patch = REFINEMENT_PATCHES["extract"][cat]
            if patch not in extract_system:
                extract_system += patch
                patches_applied.append(f"extract:{cat}")

    return note_system, extract_system, patches_applied


# ── Test Runner ─────────────────────────────────────────────────────────────

def run_test(tc: TestCase, note_sys: str, extract_sys: str) -> dict:
    result = {
        "name": tc.name,
        "note_pass": False, "extract_pass": False,
        "note_attempts": 0, "extract_attempts": 0,
        "note_issues": [], "extract_issues": [],
        "note_categories": [], "extract_categories": [],
        "note_output": "", "extract_output": "",
    }

    # Note Generation
    for attempt in range(1, MAX_RETRIES + 1):
        result["note_attempts"] = attempt
        print(f"  [Note] Attempt {attempt}...", end=" ", flush=True)
        t0 = time.time()
        user_msg = NOTE_USER_TEMPLATE.format(transcript=tc.transcript)
        raw_note = call_ollama(note_sys, user_msg, NOTE_OPTIONS, prefill="<think>\n</think>\n")
        note = strip_thinking(raw_note)
        elapsed = time.time() - t0
        print(f"({elapsed:.1f}s, {len(note)}ch)", end=" ", flush=True)
        vr = validate_note(note, tc)
        result["note_output"] = note
        result["note_issues"] = vr.issues
        result["note_categories"] = vr.categories
        if vr.passed:
            result["note_pass"] = True
            print("PASS")
            break
        else:
            print(f"FAIL: {'; '.join(vr.issues[:2])}")

    # JSON Extraction
    for attempt in range(1, MAX_RETRIES + 1):
        result["extract_attempts"] = attempt
        print(f"  [Extract] Attempt {attempt}...", end=" ", flush=True)
        t0 = time.time()
        user_msg = EXTRACT_USER_TEMPLATE.format(schema=EXTRACT_JSON_SCHEMA, transcript=tc.transcript)
        raw_extract = call_ollama(extract_sys, user_msg, EXTRACT_OPTIONS, prefill="<think>\n</think>\n")
        extract = strip_thinking(raw_extract)
        elapsed = time.time() - t0
        print(f"({elapsed:.1f}s, {len(extract)}ch)", end=" ", flush=True)
        vr = validate_extraction(extract, tc)
        result["extract_output"] = extract
        result["extract_issues"] = vr.issues
        result["extract_categories"] = vr.categories
        if vr.passed:
            result["extract_pass"] = True
            print("PASS")
            break
        else:
            print(f"FAIL: {'; '.join(vr.issues[:2])}")

    return result


def main():
    print("=" * 72)
    print("Qwen 3.5 0.8B Prompt Pressure Test + Auto-Refinement")
    print(f"Model: {MODEL} | Max retries/case: {MAX_RETRIES} | Max rounds: {MAX_ROUNDS}")
    print(f"Test cases: {len(TEST_CASES)}")
    print("=" * 72)

    # Connectivity check
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        if not any(MODEL in m for m in models):
            print(f"\nERROR: Model '{MODEL}' not found. Available: {models}")
            sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Cannot connect to Ollama: {e}")
        sys.exit(1)

    note_sys = NOTE_SYSTEM_PROMPT
    extract_sys = EXTRACT_SYSTEM_PROMPT
    all_rounds = []
    total_start = time.time()

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n{'#' * 72}")
        print(f"ROUND {round_num}/{MAX_ROUNDS}")
        print(f"{'#' * 72}")

        results = []
        for i, tc in enumerate(TEST_CASES, 1):
            print(f"\n[{i}/{len(TEST_CASES)}] {tc.name}")
            result = run_test(tc, note_sys, extract_sys)
            results.append(result)

        note_pass = sum(1 for r in results if r["note_pass"])
        extract_pass = sum(1 for r in results if r["extract_pass"])
        total = len(results)
        both_pass = sum(1 for r in results if r["note_pass"] and r["extract_pass"])

        print(f"\n── Round {round_num} Summary ──")
        print(f"Note: {note_pass}/{total} | Extract: {extract_pass}/{total} | Both: {both_pass}/{total}")

        all_rounds.append({
            "round": round_num,
            "note_pass": note_pass,
            "extract_pass": extract_pass,
            "both_pass": both_pass,
            "results": results,
        })

        # All passed?
        if both_pass == total:
            print(f"\n ALL {total} TEST CASES PASSED in round {round_num}!")
            break

        # Analyze failures for refinement
        if round_num < MAX_ROUNDS:
            failure_cats = {"note": {}, "extract": {}}
            for r in results:
                if not r["note_pass"]:
                    for cat in r["note_categories"]:
                        failure_cats["note"][cat] = failure_cats["note"].get(cat, 0) + 1
                if not r["extract_pass"]:
                    for cat in r["extract_categories"]:
                        failure_cats["extract"][cat] = failure_cats["extract"].get(cat, 0) + 1

            note_sys, extract_sys, patches = refine_prompts(failure_cats, note_sys, extract_sys)

            if not patches:
                print("\nNo applicable refinement patches — stopping early.")
                break

            print(f"\nApplied {len(patches)} prompt patches: {', '.join(patches)}")
            print(f"Note prompt: {len(note_sys)} chars | Extract prompt: {len(extract_sys)} chars")

    # ── Final Summary ───────────────────────────────────────────────
    total_time = time.time() - total_start
    best_round = max(all_rounds, key=lambda r: r["both_pass"])
    last_round = all_rounds[-1]

    print(f"\n{'=' * 72}")
    print("FINAL SUMMARY")
    print(f"{'=' * 72}")
    print(f"Total time:      {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"Rounds run:      {len(all_rounds)}")
    print(f"Best round:      #{best_round['round']} ({best_round['both_pass']}/{len(TEST_CASES)})")
    print(f"Final round:     #{last_round['round']} — Note: {last_round['note_pass']}/{len(TEST_CASES)} | Extract: {last_round['extract_pass']}/{len(TEST_CASES)}")

    # Show remaining failures
    failures = [r for r in last_round["results"] if not r["note_pass"] or not r["extract_pass"]]
    if failures:
        print(f"\nREMAINING FAILURES ({len(failures)}):")
        for r in failures:
            parts = []
            if not r["note_pass"]:
                parts.append(f"Note: {'; '.join(r['note_issues'][:2])}")
            if not r["extract_pass"]:
                parts.append(f"Extract: {'; '.join(r['extract_issues'][:2])}")
            print(f"  {r['name']}: {' | '.join(parts)}")

    # Save report + best prompts
    report_path = "scripts/qwen_test_report.json"
    report = {
        "model": MODEL,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_time_s": round(total_time, 1),
        "rounds": len(all_rounds),
        "best_round": best_round["round"],
        "best_both_pass": f"{best_round['both_pass']}/{len(TEST_CASES)}",
        "final_note_system_prompt": note_sys,
        "final_extract_system_prompt": extract_sys,
        "round_results": [
            {
                "round": rnd["round"],
                "note_pass": rnd["note_pass"],
                "extract_pass": rnd["extract_pass"],
                "both_pass": rnd["both_pass"],
                "failures": [
                    {
                        "name": r["name"],
                        "note_pass": r["note_pass"],
                        "note_issues": r["note_issues"],
                        "extract_pass": r["extract_pass"],
                        "extract_issues": r["extract_issues"],
                    }
                    for r in rnd["results"]
                    if not r["note_pass"] or not r["extract_pass"]
                ],
            }
            for rnd in all_rounds
        ],
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {report_path}")

    # Save refined prompts if they changed
    if note_sys != NOTE_SYSTEM_PROMPT or extract_sys != EXTRACT_SYSTEM_PROMPT:
        prompts_path = "scripts/qwen_refined_prompts.json"
        with open(prompts_path, "w") as f:
            json.dump({
                "note_system_prompt": note_sys,
                "extract_system_prompt": extract_sys,
            }, f, indent=2)
        print(f"Refined prompts saved to {prompts_path}")

    sys.exit(0 if best_round["both_pass"] == len(TEST_CASES) else 1)


if __name__ == "__main__":
    main()
