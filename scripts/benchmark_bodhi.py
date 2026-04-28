#!/usr/bin/env python3
"""
BODHI vs Vanilla CDSS Benchmark (v2)
=====================================
Measures how the BODHI clinical knowledge graph improves safety alert detection
across extraction models of varying capability.

Each encounter has TWO transcript types:
  - conversation: raw patient-provider dialog (hardest — model must infer dx)
  - dictation: clinician summary in natural speech (no explicit labels)

Neither says "Diagnosis: X" or "Prescribing: Y" — the model must extract
clinical facts from realistic, ambiguous clinical language.

Scoring: out of all expected dangers in the encounter, how many does
vanilla-only vs vanilla+BODHI catch? Better models extract better →
feed better data to CDSS → catch more dangers.

Usage:
    python3 scripts/benchmark_bodhi.py --dry-run
    python3 scripts/benchmark_bodhi.py --models qwen3.5:0.8b qwen3.5:9b claude-opus-4-7
    python3 scripts/benchmark_bodhi.py  # auto-detect all
"""

import argparse
import json
import os
import re
import sys
import time
import functools
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import requests

print = functools.partial(print, flush=True)

# ── Paths ──
SCRIPT_DIR = Path(__file__).parent
ASSETS_DIR = SCRIPT_DIR.parent / "app" / "src" / "main" / "assets"
REPORT_PATH = SCRIPT_DIR / "bodhi_benchmark_report.json"

# ── LLM Config ──
OLLAMA_URL = "http://localhost:11434"
EXTRACT_OPTIONS = {"temperature": 0.1, "top_p": 0.95, "top_k": 40,
                   "repeat_penalty": 1.05, "num_predict": 4096}

EXTRACT_SYSTEM = """\
Extract clinical facts from the transcript as JSON.

Rules:
- Output ONLY facts the transcript states. Do not invent findings or vitals.
- If a value isn't given, OMIT the field. Use [] for empty lists, null for empty scalars.
- Place facts in the correct field: symptoms in chief_complaint, physical exam in exam_findings, measurements in vitals.
- Output valid JSON only — no commentary, no code fences."""

EXTRACT_SCHEMA = """\
{
  "chief_complaint": "<one short phrase>",
  "vitals": [{"name": "<vital name>", "value": "<value>", "unit": "<unit>"}],
  "exam_findings": ["<one finding per item>"],
  "diagnoses": ["<diagnosis>"],
  "medications": [{"name": "<drug>", "dose": "<dose>", "frequency": "<frequency>", "context": "new|current|stopped"}],
  "allergies": ["<allergen>"],
  "investigations": [{"test": "<test>", "result": "<result>"}],
  "immunizations": [{"vaccine": "<vaccine>", "status": "given|due|declined"}],
  "plan": ["<action>"],
  "sms_summary": "<=19 chars>"
}"""

EXTRACT_USER = """\
Extract structured clinical facts as JSON.

Schema:
{schema}

CLINICAL TRANSCRIPT:
{transcript}

JSON:"""

# ── Note Generation Prompt (clinical scribe) ──
NOTE_SYSTEM = """\
You are a clinical scribe. Write a clinical note organized into the four SOAP sections using markdown ## headers.

You MAY use either of these header sets:
- Strict SOAP: ## Subjective, ## Objective, ## Assessment, ## Plan
- Clinical format: ## Chief Complaint + ## History of Present Illness, ## Physical Exam + ## Vitals, ## Assessment, ## Plan

In either case, the content MUST flow Subjective → Objective → Assessment → Plan.

Rules:
- Third-person clinical prose. NEVER use "Patient:" or "Doctor:" as headers or prefixes.
- Summarize each fact once. No repetition.
- Use bullet points (- ) for lists of meds, findings, or plan items.
- Always include Assessment and Plan sections.
- No placeholders ("not mentioned"), no disclaimers."""

NOTE_USER = """\
Write a SOAP-organized clinical note for this encounter.

{transcript}"""


# ═══════════════════════════════════════════════════════════════════════════
# ENCOUNTERS — realistic, ambiguous, dual-transcript
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Encounter:
    name: str
    category: str
    conversation: str          # patient-provider dialog
    dictation: str             # clinician dictation (no labels)
    expected_diagnoses: list[str]
    expected_medications: list[str]
    expected_vitals: list[str] = field(default_factory=list)
    patient_allergies: list[str] = field(default_factory=list)
    # All expected dangers — vanilla + BODHI combined
    expected_dangers: list[dict] = field(default_factory=list)


def _d(severity: str, category: str, substring: str = "") -> dict:
    return {"severity": severity, "category": category, "substring": substring}


ENCOUNTERS = [
    # ═══ 1. DRUG-CONDITION MISMATCH — model must infer diagnosis + match wrong drug ═══

    Encounter(
        name="HTN visit, diabetes drug prescribed",
        category="drug-condition",
        conversation="""\
Doctor: Good morning, what brings you in today?
Patient: My head's been pounding for a few days, especially in the mornings. I feel a bit dizzy when I stand up.
Doctor: Let me check your pressure... okay it's running quite high, 162 over 98. Have you been taking any medications?
Patient: No, nothing at all.
Doctor: Right, we need to get this under control. I'm going to start you on metformin 500 milligrams, take it twice a day with meals. Come back in two weeks and we'll see how you're doing.
Patient: Okay doctor, thank you.""",
        dictation="""\
55 year old male, complaining of headaches and dizziness for several days. Checked his pressure today, running 162 over 98, no current medications, no prior treatment. Going to start him on metformin 500 twice daily and bring him back in a fortnight to recheck.""",
        expected_diagnoses=["hypertension"],
        expected_medications=["metformin"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("WARNING", "Drug-Condition", "metformin"),
        ],
    ),

    Encounter(
        name="Child with ear infection, statin prescribed",
        category="drug-condition",
        conversation="""\
Mother: Doctor, my son has been pulling at his right ear since yesterday and he's been very fussy and crying a lot.
Doctor: Let me take a look... he's running a temperature, 38.6. And yes, the right eardrum is quite red and bulging.
Mother: Is it serious?
Doctor: It's an ear infection, quite common in children. I'll give him something for it. Let me write up amoxicillin 250 three times a day for a week, atorvastatin 10 milligrams daily, and some paracetamol for the fever and pain.
Mother: Thank you doctor.""",
        dictation="""\
7 year old boy brought by mother, pulling at right ear since yesterday, irritable, crying. Temp 38.6. Right TM erythematous and bulging. Ears otherwise clear. Starting amoxicillin 250 TDS for 7 days, atorvastatin 10mg daily, and paracetamol for symptomatic relief.""",
        expected_diagnoses=["otitis media", "ear infection"],
        expected_medications=["amoxicillin", "atorvastatin", "paracetamol"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("WARNING", "Drug-Condition", "atorvastatin"),
        ],
    ),

    Encounter(
        name="Pneumonia with antihypertensive added",
        category="drug-condition",
        conversation="""\
Patient: I've had this terrible cough for almost a week now, and I started getting fevers two days ago. Last night I could barely sleep.
Doctor: Let me listen to your chest... I can hear crackles on both sides, especially the right lower zone. Your temperature is 39.1. This is looking like a chest infection that's gone into your lungs.
Patient: That sounds bad.
Doctor: We need to treat it aggressively. I'm putting you on amoxicillin 500 three times a day. I'm also going to add amlodipine 5 milligrams for you. Come back in three days, and if you're getting worse, go straight to the hospital.
Patient: What's the amlodipine for?
Doctor: Just something to help. Take it once a day.""",
        dictation="""\
28 year old female, productive cough for a week, fevers for 2 days, poor sleep. Bilateral crackles on auscultation, worse right lower zone. Temp 39.1. Consistent with community acquired lower respiratory tract infection. Starting amoxicillin 500 TDS for 7 days and amlodipine 5mg daily. Review in 3 days.""",
        expected_diagnoses=["pneumonia"],
        expected_medications=["amoxicillin", "amlodipine"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("WARNING", "Drug-Condition", "amlodipine"),
        ],
    ),

    Encounter(
        name="Malaria with enalapril added",
        category="drug-condition",
        conversation="""\
Patient: Doctor I've been feeling terrible, shaking and sweating for three days. My body aches all over and I can't keep food down.
Doctor: Have you travelled recently?
Patient: I was in the rural area last week visiting family.
Doctor: Let me do a rapid test... it's positive for falciparum malaria. Your temperature is 39.2. I'm going to give you the artemether-lumefantrine combination, four tablets now, another four in eight hours, then continue twice a day for two more days. I'll also give you paracetamol for the fever and enalapril 10 milligrams to take daily.
Patient: What's the enalapril?
Doctor: It'll help. Take them all as I said.""",
        dictation="""\
30 year old male, 3 day history of rigors, sweats, myalgia, vomiting. Recent rural travel. Temp 39.2. RDT positive P. falciparum. No features of severe disease. Treating with AL combo standard course, paracetamol for symptomatic relief, and adding enalapril 10mg daily. Return if worsening.""",
        expected_diagnoses=["malaria"],
        expected_medications=["artemether-lumefantrine", "enalapril", "paracetamol"],
        expected_dangers=[
            _d("WARNING", "Drug-Condition", "enalapril"),
        ],
    ),

    # ═══ 2. EMERGENCY TRIAGE — model must recognize urgency from clinical picture ═══

    Encounter(
        name="Acute MI presentation",
        category="triage",
        conversation="""\
Wife: Please help, my husband suddenly grabbed his chest about an hour ago and he's been in terrible pain since. He's sweating a lot.
Doctor: Sir, can you tell me about the pain?
Patient: [grimacing] It's crushing... right here in the center... going down my left arm...
Doctor: Let me check him quickly. Pressure is dropping, 90 over 60. Heart rate 110. The ECG is showing ST elevation across the anterior leads. We need to act fast. Give him aspirin 300 stat, chew and swallow. Get the oxygen on. I'm calling for an ambulance to get him to the cardiac unit immediately.
Wife: Is he having a heart attack?
Doctor: Yes, we need to move quickly.""",
        dictation="""\
60 year old male, sudden onset crushing central chest pain radiating to left arm, 1 hour duration. Diaphoretic, distressed. Wife brought him in. Pressure dropping at 90 over 60, tachycardic at 110. ECG showing ST elevation V1 through V4, consistent with anterior STEMI. Gave aspirin 300mg stat. Oxygen applied. Arranging emergency transfer to cardiac catheterization lab.""",
        expected_diagnoses=["myocardial infarction"],
        expected_medications=["aspirin"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
        ],
    ),

    Encounter(
        name="Status epilepticus in child",
        category="triage",
        conversation="""\
Mother: [screaming] My child is shaking! He won't stop! Please help!
Doctor: How long has he been fitting?
Mother: At least fifteen minutes, I don't know, it started at home!
Doctor: Nurse, get the diazepam ready, 5mg IV. His temperature is 38.8, he's still actively seizing. If this doesn't break it in five minutes we go to phenytoin loading dose. This is status. We need to get him transferred.
Mother: What's happening to him?
Doctor: He's having prolonged seizures and we need to stop them. We're giving him medication now and arranging transfer to the hospital.""",
        dictation="""\
8 year old boy brought in actively convulsing, mother says ongoing for at least 15 minutes. Temp 38.8. Generalized tonic-clonic activity, no focal features. Giving diazepam 5mg IV. If seizure persists after 5 minutes will proceed to phenytoin loading. This is a prolonged seizure requiring urgent management. Arranging emergency transfer.""",
        expected_diagnoses=["status epilepticus", "seizure"],
        expected_medications=["diazepam"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
        ],
    ),

    Encounter(
        name="Severe pre-eclampsia",
        category="triage",
        conversation="""\
Patient: Doctor, I can't see properly, everything is blurry. My head is splitting. I'm 34 weeks pregnant.
Doctor: Let me check your pressure urgently... 180 over 115. That's dangerously high. Nurse, dip her urine. How long have you had the headache?
Patient: Since this morning, and I've been seeing spots.
Nurse: Urine shows protein 3 plus.
Doctor: Right, I'm checking her reflexes... they're brisk, hyperreflexia. This is very concerning. We need magnesium sulfate loaded now and start labetalol for the pressure. We're sending you to the hospital for an emergency delivery.
Patient: Is my baby okay?
Doctor: We need to act now to keep both of you safe.""",
        dictation="""\
26 year old female, 34 weeks gestation, presenting with severe headache, visual disturbance including scotomata. Pressure 180 over 115. Urine protein 3 plus. Hyperreflexia present. Clinical picture consistent with severe toxemia of pregnancy. Loading magnesium sulfate and starting labetalol. Emergency obstetric referral for delivery.""",
        expected_diagnoses=["pre-eclampsia", "eclampsia"],
        expected_medications=["magnesium sulfate", "labetalol"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
        ],
    ),

    Encounter(
        name="DKA in young diabetic",
        category="triage",
        conversation="""\
Friend: She's been vomiting all day and she's breathing really fast and deep. She's a type 1 diabetic.
Doctor: Ma'am, can you hear me? She's drowsy. Let me check her sugar... 28 millimoles. Urine ketones 3 plus. Her breathing pattern — that's Kussmaul respiration. What's the pH? 7.1. She's in severe metabolic acidosis.
Friend: Is she going to be okay?
Doctor: She's very sick. We need IV fluids immediately and an insulin drip. This needs intensive monitoring. Nurse, get a line in, start normal saline running, and prepare the insulin infusion. She's going to need admission.""",
        dictation="""\
19 year old female, known type 1 diabetic, brought by friend. Vomiting all day, Kussmaul breathing pattern, drowsy. Glucose 28, urinary ketones strongly positive, pH 7.1. Severe metabolic acidosis with ketosis in a known diabetic — this is a metabolic emergency. Starting IV fluids and insulin infusion. Needs immediate admission for monitoring.""",
        expected_diagnoses=["diabetic ketoacidosis", "DKA"],
        expected_medications=["insulin"],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
        ],
    ),

    Encounter(
        name="Bacterial meningitis in toddler",
        category="triage",
        conversation="""\
Mother: She's been burning up since last night and she won't stop crying. She vomited three times this morning and she seems really out of it.
Doctor: Let me examine her. Temperature is 40.2. She's very lethargic. Her neck... there's definite stiffness, positive Kernig sign. The fontanelle is tense and bulging. This is extremely concerning.
Mother: What's wrong with her?
Doctor: I think she has an infection around the brain. We need to give antibiotics right now — ceftriaxone — and get her to the children's intensive care unit immediately. Every minute counts.
Mother: Oh my God.
Doctor: Nurse, ceftriaxone 100mg per kg IV now. Call the ambulance.""",
        dictation="""\
3 year old girl, high fever since last night, vomiting, lethargy. Temp 40.2. Neck rigidity present, positive Kernig sign, bulging fontanelle. Clinical picture strongly suggestive of bacterial CNS infection. Giving ceftriaxone 100mg per kg IV stat. This child needs immediate transfer to pediatric intensive care. Called ambulance.""",
        expected_diagnoses=["meningitis"],
        expected_medications=["ceftriaxone"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
        ],
    ),

    # ═══ 3. LAB RECOMMENDATIONS — model must extract diagnosis for BODHI to suggest labs ═══

    Encounter(
        name="New diabetes — needs HbA1c",
        category="lab-recommendation",
        conversation="""\
Patient: Doctor, I've been running to the bathroom constantly for the past few weeks, and I'm always thirsty no matter how much I drink. I've lost some weight too.
Doctor: Those symptoms are concerning. Let me check your sugar... random glucose is 16.5. That's very high. Your weight is 88kg. I think we're looking at sugar diabetes here.
Patient: My mother had it too.
Doctor: Family history makes sense. I'm going to start you on metformin 500 twice a day, and I need you to watch your diet — reduce sugar and starches. We'll bring you back in a month to see how you're doing.
Patient: Is it serious?
Doctor: It's manageable if we control it properly.""",
        dictation="""\
52 year old female, 3 week history of polyuria, polydipsia, unintentional weight loss. Random glucose 16.5. Weight 88kg. Family history positive — mother affected. Clinical picture and glucose level consistent with new onset type 2 sugar disease. Starting metformin 500 BD. Dietary counseling provided. Follow up one month.""",
        expected_diagnoses=["diabetes"],
        expected_medications=["metformin"],
        expected_dangers=[
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="Hypothyroidism — needs thyroid function",
        category="lab-recommendation",
        conversation="""\
Patient: I just feel so tired all the time, doctor. I'm gaining weight even though I'm not eating more. And I'm always cold, even when everyone else is fine.
Doctor: How long has this been going on?
Patient: Maybe six months, gradually getting worse.
Doctor: Let me examine your neck... I can feel your thyroid, it's a bit enlarged. With the fatigue, weight gain, and cold intolerance, I think your thyroid gland is underactive.
Patient: What does that mean?
Doctor: Your thyroid isn't making enough hormone. I'm going to start you on levothyroxine 50 micrograms, take it first thing in the morning on an empty stomach. We'll check your levels in six weeks and adjust if needed.""",
        dictation="""\
38 year old female, 6 month history of progressive fatigue, unexplained weight gain despite stable diet, cold intolerance. Thyroid palpably enlarged. Clinical presentation classic for underactive thyroid. Starting levothyroxine 50 micrograms daily. Will need levels checked in 6 weeks for dose titration.""",
        expected_diagnoses=["hypothyroidism"],
        expected_medications=["levothyroxine"],
        expected_dangers=[
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="Declining kidney function — needs renal panel",
        category="lab-recommendation",
        conversation="""\
Doctor: I'm looking at your results from last time and your kidney function has gotten worse. The creatinine is up to 180.
Patient: What does that mean?
Doctor: Your kidneys aren't filtering as well as they should. You're in stage 3 now. We need to keep a close eye on this.
Patient: I've been taking the enalapril like you said.
Doctor: Good, that actually helps protect the kidneys. Your pressure today is 135 over 82 which is reasonable. Let's keep everything the same for now and check again in three months.
Patient: Is there anything else I can do?
Doctor: Watch your salt intake and stay hydrated.""",
        dictation="""\
65 year old male, known to have declining renal function, now stage 3. Creatinine risen to 180 from last visit. On enalapril 10mg which we'll continue for renal protection. Pressure today acceptable at 135 over 82. Conservative management, repeat bloods in 3 months to monitor trend.""",
        expected_diagnoses=["chronic kidney disease", "kidney"],
        expected_medications=["enalapril"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="Iron deficiency anemia — needs iron studies",
        category="lab-recommendation",
        conversation="""\
Patient: I've been so exhausted lately, doctor. I can barely get through the day. And people keep telling me I look pale.
Doctor: Let me look at your results... your hemoglobin is only 8.2, and your MCV is 68 which is low. You're quite anemic and the small red cells tell me it's likely from iron deficiency.
Patient: How did that happen?
Doctor: Could be your diet, or heavy periods. Are your periods heavy?
Patient: Yes, very heavy actually.
Doctor: That's probably the cause. I'm going to give you ferrous sulfate 200 milligrams three times a day. Take it with orange juice, it helps absorption. And try to eat more iron-rich foods — red meat, spinach, lentils. We'll recheck in a month.""",
        dictation="""\
29 year old female, presenting with fatigue and pallor. Hemoglobin 8.2, MCV 68 — microcytic picture. Reports menorrhagia. Likely iron deficiency as the cause. Starting ferrous sulfate 200mg TDS with advice on absorption and dietary iron. Recheck bloods in 1 month.""",
        expected_diagnoses=["anemia", "iron deficiency"],
        expected_medications=["ferrous sulfate"],
        expected_dangers=[
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    # ═══ 4. SPECIALTY REFERRAL — model must extract diagnosis for BODHI to suggest specialist ═══

    Encounter(
        name="Heart failure needs cardiology",
        category="specialty-referral",
        conversation="""\
Patient: Doctor, I can't breathe when I lie down at night. I have to prop myself up with three pillows. And look at my ankles, they're huge.
Doctor: How long has the swelling been getting worse?
Patient: A few weeks. And I'm more short of breath walking than I used to be.
Doctor: Let me examine you. Your pressure is on the low side, 100 over 65. Pulse is 92 and irregular. Your neck veins are distended. And I can hear crackles at both lung bases. With the ankle swelling, the orthopnea, and the congestion in your lungs, your heart isn't pumping effectively anymore.
Patient: What can we do?
Doctor: I'm starting you on furosemide to get rid of the fluid, 40mg daily, and enalapril 2.5mg to help the heart. But you're going to need specialist input for this.""",
        dictation="""\
70 year old female, progressive dyspnea on exertion, orthopnea requiring 3 pillows, bilateral ankle edema worsening over weeks. Exam shows low pressure at 100 over 65, irregular pulse 92, raised JVP, bilateral basal crackles. Clinical picture of decompensated cardiac failure. Starting furosemide 40mg OD and enalapril 2.5mg. Needs specialist cardiology assessment.""",
        expected_diagnoses=["heart failure"],
        expected_medications=["furosemide", "enalapril"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="Severe psoriasis needs dermatology",
        category="specialty-referral",
        conversation="""\
Patient: These patches on my skin keep spreading. They're red and flaky and they itch terribly. I've been using the steroid cream you gave me but it's not helping anymore.
Doctor: Let me have a look... this has really spread. You've got thick silvery plaques on your elbows, knees, trunk, scalp — I'd estimate it's covering more than 30 percent of your body now. The topical steroids aren't going to be enough at this stage.
Patient: So what now?
Doctor: With this extent of involvement, you need to be seen by a skin specialist who can consider systemic treatment — tablets or injections that work from the inside. The creams alone won't control this.
Patient: How long will it take to get an appointment?
Doctor: I'll write the referral today as urgent.""",
        dictation="""\
35 year old female, extensive plaque-type skin disease, thick silvery plaques affecting elbows, knees, trunk, scalp, covering estimated greater than 30 percent BSA. Failed topical steroids. At this severity, needs systemic therapy — methotrexate or biologic agents. Referring urgently to dermatology for assessment and initiation of systemic treatment.""",
        expected_diagnoses=["psoriasis"],
        expected_medications=[],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="Glaucoma needs ophthalmology",
        category="specialty-referral",
        conversation="""\
Patient: I've noticed my side vision isn't as good as it used to be. Things seem to be narrowing in, and sometimes I see halos around lights at night.
Doctor: How long has this been happening?
Patient: Gradually, maybe a few months. I thought I just needed new glasses.
Doctor: Let me check your eye pressures... the right eye is 28, which is significantly elevated. And looking at the back of your eye, the optic disc has a deep cup which suggests pressure damage over time. This is glaucoma.
Patient: Can it be treated?
Doctor: I'm starting you on timolol eye drops, half percent, use them twice a day. But you absolutely need to see an eye specialist for proper monitoring and to discuss whether you need laser treatment.""",
        dictation="""\
55 year old male, gradual visual field narrowing, halos around lights. Intraocular pressures elevated — right eye 28 mmHg. Fundoscopy shows significant optic disc cupping. Consistent with chronic open angle glaucoma. Starting timolol 0.5 percent drops BD. Referring to ophthalmology for visual field testing, monitoring, and consideration of laser.""",
        expected_diagnoses=["glaucoma"],
        expected_medications=["timolol"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    # ═══ 5. DRUG SAFETY — vanilla should catch these (allergies, interactions, vitals) ═══

    Encounter(
        name="Warfarin patient given aspirin",
        category="drug-safety",
        conversation="""\
Patient: My knee has been really sore the past few days, hard to walk on.
Doctor: Are you still taking your warfarin for the heart rhythm problem?
Patient: Yes, every day, 5 milligrams.
Doctor: Let me have a look at the knee... it's a bit swollen. I think it's just wear and tear arthritis flaring up. I'll give you aspirin 300 milligrams daily for the pain and inflammation. Keep taking your warfarin as normal. Your pressure is fine today, 128 over 78.
Patient: Won't those two clash?
Doctor: Just take them as prescribed.""",
        dictation="""\
68 year old male, on warfarin 5mg daily for AF, presenting with acute knee pain. Knee mildly swollen, no effusion. Likely degenerative joint flare. BP 128 over 78. Adding aspirin 300mg daily for analgesia. Continue warfarin. Review as needed.""",
        expected_diagnoses=["atrial fibrillation", "arthritis"],
        expected_medications=["warfarin", "aspirin"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("CRITICAL", "Drug-Drug", "warfarin"),
        ],
    ),

    Encounter(
        name="Penicillin allergy given amoxicillin",
        category="drug-safety",
        conversation="""\
Patient: My throat has been killing me for three days. It hurts to swallow and I've had a fever.
Doctor: Let me take a look... your tonsils are very red and swollen, and you've got pus on them. Temperature is 38.5. This is a bacterial throat infection.
Patient: I should mention, I'm allergic to penicillin. I got a rash all over my body last time.
Doctor: Noted. I'm going to give you amoxicillin 500 three times daily for seven days. That should clear it up.
Patient: Is that safe with my allergy?
Doctor: It should be fine, don't worry.""",
        dictation="""\
40 year old female, 3 day sore throat, odynophagia, febrile. Tonsils erythematous with exudate. Temp 38.5. Bacterial tonsillitis. Known penicillin allergy — previous generalized rash. Starting amoxicillin 500 TDS for 7 days.""",
        expected_diagnoses=["tonsillitis", "pharyngitis"],
        expected_medications=["amoxicillin"],
        expected_vitals=["temperature"],
        patient_allergies=["penicillin"],
        expected_dangers=[
            _d("CRITICAL", "Drug-Allergy", "penicillin"),
        ],
    ),

    Encounter(
        name="Dangerously high blood pressure",
        category="drug-safety",
        conversation="""\
Patient: I came in because I've had the worst headache of my life since this morning. It won't go away.
Doctor: Let me check your blood pressure... [pause] Okay, this is very concerning. Your blood pressure is 210 over 130. That's dangerously high.
Patient: Is that bad?
Doctor: Very. At these levels you're at risk of a stroke or damage to your heart and kidneys. I'm going to start you on amlodipine 10 milligrams right now and you need to go to the hospital today for monitoring. This is urgent.
Patient: I've never had blood pressure problems before.
Doctor: Well you have one now and it needs immediate attention.""",
        dictation="""\
50 year old male, thunderclap headache since this morning. Found to have severely elevated pressure at 210 over 130. No prior history of hypertensive disease. At this level there's risk of end-organ damage. Starting amlodipine 10mg stat. Urgent referral to hospital for monitoring and workup of secondary causes.""",
        expected_diagnoses=["hypertension"],
        expected_medications=["amlodipine"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("CRITICAL", "Vitals", ""),
        ],
    ),

    Encounter(
        name="Sulfa allergy given cotrimoxazole",
        category="drug-safety",
        conversation="""\
Patient: It burns when I pass urine and I'm going every half hour. It started two days ago.
Doctor: Sounds like a urinary tract infection. Any allergies to medications?
Patient: Yes, I'm allergic to sulfa drugs. I got a severe reaction years ago.
Doctor: Right. Let me prescribe cotrimoxazole double strength, take one tablet twice a day for five days. That should sort it out.
Patient: Wait, isn't cotrimoxazole a sulfa drug?
Doctor: Just take it as prescribed and come back if you have any problems.""",
        dictation="""\
33 year old male, 2 day dysuria and frequency. Clinical UTI. Known sulfa drug allergy — severe reaction historically. Prescribing cotrimoxazole DS BD for 5 days.""",
        expected_diagnoses=["UTI", "urinary tract"],
        expected_medications=["cotrimoxazole"],
        patient_allergies=["sulfa"],
        expected_dangers=[
            _d("CRITICAL", "Drug-Allergy", "sulfa"),
        ],
    ),

    Encounter(
        name="ACE inhibitor plus NSAID",
        category="drug-safety",
        conversation="""\
Patient: My back has been terrible this week, I can barely move.
Doctor: Is this new or an old problem?
Patient: It started after I helped my son move house over the weekend.
Doctor: I see. You're on enalapril 10 for your blood pressure, correct?
Patient: Yes, have been for years.
Doctor: Your pressure today is 140 over 88, a bit higher than ideal. I'm going to add diclofenac 50 three times a day for the back pain. Take it with food. Keep taking the enalapril as normal.
Patient: For how long?
Doctor: A week should do it. Come back if it's not better.""",
        dictation="""\
55 year old male, acute lower back pain since lifting over the weekend, mechanical in nature. On enalapril 10mg for longstanding hypertension. BP today 140 over 88. Adding diclofenac 50 TDS for pain relief. Continue enalapril. Review in one week.""",
        expected_diagnoses=["back pain", "hypertension"],
        expected_medications=["enalapril", "diclofenac"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("WARNING", "Drug-Drug", ""),
        ],
    ),

    Encounter(
        name="NSAID allergy given ibuprofen",
        category="drug-safety",
        conversation="""\
Patient: I twisted my knee playing football on the weekend and it's really swollen and sore.
Doctor: Let me examine it. There's some swelling but the ligaments feel stable. I think it's a soft tissue injury, it should heal with rest.
Patient: Can I get something for the pain? I should mention I'm allergic to anti-inflammatories. Last time I took one I had an asthma attack and my face swelled up.
Doctor: I understand. I'm going to prescribe ibuprofen 400 milligrams three times a day for the pain and swelling. Use ice as well.
Patient: But I just told you I react to those?
Doctor: This is a different one, you'll be fine.""",
        dictation="""\
35 year old female, twisted knee during sport. Swollen, stable ligaments, soft tissue injury. Known NSAID allergy — previous bronchospasm and angioedema. Prescribing ibuprofen 400 TDS for 5 days.""",
        expected_diagnoses=["knee injury"],
        expected_medications=["ibuprofen"],
        patient_allergies=["nsaid"],
        expected_dangers=[
            _d("CRITICAL", "Drug-Allergy", ""),
        ],
    ),

    Encounter(
        name="Critically low oxygen saturation",
        category="drug-safety",
        conversation="""\
Patient: [gasping] I can't... catch my breath... it's been getting worse... all day.
Doctor: You have severe COPD, is that right?
Patient: Yes... for years...
Doctor: His oxygen is only 82 percent. Respiratory rate 32. Pulse 115. This is a severe exacerbation. Nurse, get the nebulizer going with salbutamol and ipratropium. Put him on oxygen via nasal cannula. And give prednisolone 40 milligrams orally.
Nurse: Nebulizer going now.
Doctor: If his saturations don't come up we may need to transfer him. Keep monitoring closely.""",
        dictation="""\
70 year old male, known COPD, severe exacerbation with worsening dyspnea throughout the day. Saturations only 82 percent on room air. RR 32. Pulse 115. Started nebulized salbutamol and ipratropium. Oxygen via nasal cannula. Prednisolone 40mg stat. Monitoring closely, may need transfer if no improvement.""",
        expected_diagnoses=["COPD"],
        expected_medications=["salbutamol", "prednisolone"],
        expected_vitals=["oxygen"],
        expected_dangers=[
            _d("CRITICAL", "Vitals", ""),
        ],
    ),

    Encounter(
        name="Warfarin + metronidazole interaction",
        category="drug-safety",
        conversation="""\
Patient: My tooth has been killing me for days and now my gum is swollen with pus.
Doctor: Let me look... yes, you've got a dental abscess there. We need to treat that with antibiotics. You're on warfarin, correct?
Patient: Yes, for my artificial heart valve. Five milligrams daily.
Doctor: I'm going to prescribe metronidazole 400 milligrams three times a day for five days. Continue your warfarin as normal. See the dentist as soon as possible.
Patient: Will they affect each other?
Doctor: Just take them as directed.""",
        dictation="""\
60 year old female, dental abscess, purulent gingival swelling. On warfarin 5mg for mechanical valve. Prescribing metronidazole 400 TDS for 5 days. Continue warfarin. Advise dental review.""",
        expected_diagnoses=["dental abscess"],
        expected_medications=["warfarin", "metronidazole"],
        expected_dangers=[
            _d("WARNING", "Drug-Drug", ""),
        ],
    ),

    # ═══ 6. COMPLEX — multiple dangers, both vanilla and BODHI needed ═══

    Encounter(
        name="Diabetic with pneumonia + warfarin + aspirin",
        category="complex",
        conversation="""\
Patient: Doctor, I've had this cough and fever for about three days. My chest hurts when I breathe deeply.
Doctor: I see from your file you're diabetic on metformin and also on warfarin for that DVT you had last year. Let me examine you. Temperature is 39.2. BP 145 over 90. Oxygen level is 92 percent, that's low. I can hear crackling in both lungs. This is a serious chest infection.
Patient: Do I need to go to hospital?
Doctor: Let me treat you here for now. I'll start amoxicillin 500 three times a day. And I want to add aspirin 100 milligrams daily for the chest pain. Continue your metformin and warfarin. Also, are you allergic to anything?
Patient: Sulfa drugs, I had a bad reaction once.
Doctor: Noted. Come back in three days or sooner if you're worse.""",
        dictation="""\
58 year old male, known diabetic on metformin 1g BD, also on warfarin post-DVT. Presenting with 3 day cough, fever, pleuritic chest pain. Temp 39.2. BP 145 over 90. Sats 92 percent. Bilateral crackles. Consistent with community acquired chest infection. Starting amoxicillin 500 TDS. Adding aspirin 100mg daily. Continue metformin and warfarin. Known sulfa allergy. Review 3 days.""",
        expected_diagnoses=["pneumonia", "diabetes"],
        expected_medications=["amoxicillin", "aspirin", "warfarin", "metformin"],
        expected_vitals=["temperature", "blood pressure", "oxygen"],
        patient_allergies=["sulfa"],
        expected_dangers=[
            _d("CRITICAL", "Drug-Drug", "warfarin"),     # warfarin + aspirin
            _d("CRITICAL", "Triage", "EMERGENCY"),       # pneumonia triage
            _d("INFO", "Lab Recommendation", ""),          # diabetes labs
        ],
    ),

    Encounter(
        name="Eclampsia + penicillin allergy + amoxicillin",
        category="complex",
        conversation="""\
Nurse: Doctor, the pregnant woman in room 3 just had a seizure! She's 36 weeks.
Doctor: Get me in there now. What's her pressure? 190 over 120. Urine?
Nurse: Protein 3 plus.
Doctor: This is eclampsia. Load magnesium sulfate immediately. Does she have any allergies?
Nurse: Chart says penicillin.
Doctor: Right. She also had some discharge that looked infected, so let's add amoxicillin 500 for that. Get the OB team on the phone, she needs an emergency section.
Nurse: Amoxicillin with a penicillin allergy?
Doctor: Just give it, we need to cover infection. Priority is the seizure and the baby.""",
        dictation="""\
24 year old female, 36 weeks gestation, witnessed generalized seizure. Pressure 190 over 120. Proteinuria 3 plus. Eclamptic seizure. Loading magnesium sulfate. Known penicillin allergy per chart. Adding amoxicillin 500 for possible infection. Emergency cesarean referral to obstetrics.""",
        expected_diagnoses=["eclampsia"],
        expected_medications=["magnesium sulfate", "amoxicillin"],
        expected_vitals=["blood pressure"],
        patient_allergies=["penicillin"],
        expected_dangers=[
            _d("CRITICAL", "Drug-Allergy", "penicillin"),  # amoxicillin + penicillin allergy
            _d("CRITICAL", "Triage", "EMERGENCY"),          # eclampsia triage
        ],
    ),

    Encounter(
        name="HIV + TB + sulfa allergy + cotrimoxazole",
        category="complex",
        conversation="""\
Doctor: Your test has come back positive for HIV. I know this is a lot to take in.
Patient: [long pause] I was afraid of that.
Doctor: Your CD4 count is 180, which means your immune system is significantly weakened. And the sputum results show tuberculosis as well.
Patient: Both at the same time?
Doctor: Unfortunately yes, but both are treatable. We're going to start you on TB treatment first — the RHZE combination — and then begin antiretroviral therapy. I also want to put you on cotrimoxazole to prevent opportunistic infections.
Patient: I should tell you I'm allergic to sulfa drugs. I had a terrible reaction years ago.
Doctor: We'll manage that. Let me write everything up. You weigh 52 kilos. Come back in two weeks so we can check your liver function and see how you're tolerating everything.""",
        dictation="""\
35 year old male, newly confirmed HIV positive. CD4 180. Sputum smear positive TB. Starting RHZE intensive phase for TB. Initiating ART with TDF/3TC/DTG. Adding cotrimoxazole prophylaxis. Known sulfa allergy — previous severe reaction. Weight 52kg. Follow up 2 weeks with liver function tests.""",
        expected_diagnoses=["HIV", "tuberculosis"],
        expected_medications=["RHZE", "cotrimoxazole"],
        patient_allergies=["sulfa"],
        expected_dangers=[
            _d("CRITICAL", "Drug-Allergy", "sulfa"),       # cotrimoxazole + sulfa allergy
            _d("INFO", "Lab Recommendation", ""),            # TB labs
        ],
    ),

    Encounter(
        name="Elderly multi-morbid: HTN + DM + CKD + gout",
        category="complex",
        conversation="""\
Doctor: How are things going? Let me go through your conditions. Your blood pressure is still a bit high at 155 over 95.
Patient: The pills don't seem to be working well enough.
Doctor: You're on enalapril 20 and metformin 500 twice a day. Your sugar was 12 today. The kidney function... creatinine is still climbing. And your uric acid — have you had any gout flares lately?
Patient: Yes, my big toe last month. Terrible.
Doctor: I'm going to add hydrochlorothiazide 25 milligrams for the blood pressure. Continue everything else. We need to keep a close eye on those kidneys especially.
Patient: You've got me on so many tablets, doctor.
Doctor: I know, but each one is important.""",
        dictation="""\
72 year old male, multiple comorbidities. Hypertensive on enalapril 20, pressure today 155 over 95 — adding hydrochlorothiazide 25mg. Diabetic on metformin 500 BD, glucose 12 today. Known progressive kidney disease, creatinine trending up. Also has gouty arthritis, recent flare. Continues allopurinol 300mg. Complex multi-morbid patient needing close monitoring.""",
        expected_diagnoses=["hypertension", "diabetes", "kidney", "gout"],
        expected_medications=["enalapril", "metformin", "hydrochlorothiazide", "allopurinol"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("INFO", "Lab Recommendation", ""),            # CKD/diabetes labs
            _d("INFO", "Referral Suggestion", ""),           # nephrology/cardiology
        ],
    ),

    Encounter(
        name="Child severe malaria + wrong drug + emergency",
        category="complex",
        conversation="""\
Mother: Doctor please, my child has been shaking and talking nonsense. He's burning up.
Doctor: How old is he? When did this start?
Mother: He's four. The fever started two days ago but the confusion started this morning. He had a fit on the way here.
Doctor: His temperature is 40.5. Let me do the rapid test... positive for malaria. With the altered consciousness and convulsions, this is severe. Nurse, get IV artesunate ready. I'm also going to give him enalapril 5 milligrams. We need to transfer him to the hospital immediately.
Mother: Is he going to be okay?
Doctor: He's very sick and needs intensive care. We're doing everything we can.""",
        dictation="""\
4 year old male, 2 day fever with altered consciousness and convulsions since this morning. Temp 40.5. RDT positive. Cerebral involvement — this is severe complicated malaria. Starting IV artesunate. Also giving enalapril 5mg. This child needs immediate hospital transfer for intensive management.""",
        expected_diagnoses=["malaria"],
        expected_medications=["artesunate", "enalapril"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),          # severe malaria triage
            _d("WARNING", "Drug-Condition", "enalapril"),   # enalapril wrong for malaria
        ],
    ),

    Encounter(
        name="Post-MI + penicillin allergy + new pneumonia",
        category="complex",
        conversation="""\
Nurse: Doctor, the patient in bed 4 who had the heart attack three days ago is now developing a fever and cough.
Doctor: Let me see him. Temperature is 38.8. Sats are 94 percent. I can hear crackles in the right base. He's picking up a hospital-acquired chest infection on top of the cardiac event. He's on aspirin, clopidogrel, atorvastatin, metoprolol, and enalapril from the cardiac team.
Nurse: His chart says penicillin allergy.
Doctor: Right. Let me add amoxicillin-clavulanate for the chest infection.
Nurse: But he's allergic to penicillin.
Doctor: He needs antibiotic cover. Start it and we'll watch for reactions.""",
        dictation="""\
62 year old male, 3 days post MI, on full cardiac regimen — aspirin, clopidogrel, statin, beta blocker, ACE inhibitor. Now febrile at 38.8, sats 94, right basal crackles. Developing hospital acquired pneumonia. Known penicillin allergy per chart. Adding co-amoxiclav 1g TDS. Will monitor.""",
        expected_diagnoses=["pneumonia", "myocardial infarction"],
        expected_medications=["aspirin", "amoxicillin-clavulanate"],
        expected_vitals=["temperature", "oxygen"],
        patient_allergies=["penicillin"],
        expected_dangers=[
            _d("CRITICAL", "Drug-Allergy", "penicillin"),  # amox-clav + pen allergy
            _d("CRITICAL", "Triage", "EMERGENCY"),          # MI triage
        ],
    ),

    # ═══ 7. CHRONIC DISEASE MANAGEMENT — ROUTINE ═══

    Encounter(
        name="HTN refill visit — stable on enalapril",
        category="chronic-routine",
        conversation="""\
Doctor: Good morning, how have you been since last time?
Patient: I'm doing well, doctor. No headaches, no dizziness. I've been taking my enalapril every morning like you said.
Doctor: That's good to hear. Let me check your pressure. Okay, 134 over 82 today.
Patient: Is that alright?
Doctor: Yes, that's well controlled. Much better than when we started. You were sitting at 165 over 100 when you first came in.
Patient: I remember, I was feeling terrible then. The headaches were awful.
Doctor: How are you doing with the tablets? Any side effects? Any dry cough?
Patient: No, nothing at all. I feel fine on them.
Doctor: Good. Let me check your file... you've been on enalapril 10 milligrams for about eight months now. Your pressure has been stable the last three visits. I'm happy to continue the same dose. I'll give you a three month supply. Come back in three months or sooner if you have any problems.
Patient: Thank you, doctor. I'm also trying to cut down on the salt like you told me.
Doctor: Excellent, keep that up. It makes a real difference.""",
        dictation="""\
62 year old male, routine follow-up for high blood pressure diagnosed eight months ago. Currently on enalapril 10mg once daily. Reports feeling well with no headaches, dizziness, or other symptoms. No medication side effects, specifically no dry cough. Blood pressure today 134 over 82, which represents good control and is consistent with the past three visits showing a stable trend. No evidence of end-organ damage. Plan is to continue enalapril 10mg daily at the current dose. Three month supply of medication dispensed. Patient actively working on reducing dietary salt intake, which was reinforced during this visit. Return in three months for routine pressure check or sooner if any new symptoms develop.""",
        expected_diagnoses=["hypertension"],
        expected_medications=["enalapril"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="Diabetes review — on metformin, needs HbA1c",
        category="chronic-routine",
        conversation="""\
Doctor: Welcome back. How's the sugar been at home?
Patient: I've been checking with the machine you gave me. It's usually around 7 or 8 in the mornings. Today when I checked before coming it was 8.2.
Doctor: That's not bad but we'd like it a bit lower. Have you been taking the metformin?
Patient: Yes, 500 milligrams morning and evening, with meals like you said.
Doctor: Good. Any stomach problems? Some people get nausea or loose stools.
Patient: I had some loose stools in the beginning but that's settled now.
Doctor: How about your diet? Are you managing to reduce the starches?
Patient: I'm trying, doctor, but it's difficult. My wife cooks a lot of pap and rice.
Doctor: I understand. Try to have smaller portions and add more vegetables. Even small changes help over time. Your weight is 84 kilograms today, same as last visit.
Patient: At least I'm not gaining.
Doctor: That's right. I want to continue the metformin 500 twice daily. You're doing okay but I want to check a long-term sugar test next time to see how you've been doing over the past three months. Come back in six weeks.""",
        dictation="""\
58 year old female, known type 2 diabetes, attending routine review. Currently on metformin 500mg twice daily taken with meals. Self-monitoring blood glucose at home showing fasting readings consistently between 7 and 8 millimoles per litre. Fasting glucose today 8.2. Initial gastrointestinal side effects have resolved. Weight stable at 84 kilograms compared to previous visit. Dietary counseling reinforced regarding starch and sugar reduction but patient reports ongoing difficulties with dietary changes. Plan to continue metformin 500mg BD at current dose. HbA1c to be ordered at next visit in six weeks to assess three-month glycemic control and guide any dose adjustment.""",
        expected_diagnoses=["diabetes"],
        expected_medications=["metformin"],
        expected_dangers=[
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="Asthma maintenance — well controlled",
        category="chronic-routine",
        conversation="""\
Doctor: How's the breathing been?
Patient: Much better, doctor. I haven't had any attacks since you started me on the preventer inhaler.
Doctor: When was your last flare-up?
Patient: Maybe four months ago. Before that I was using the blue inhaler almost every day.
Doctor: And now?
Patient: I use the salbutamol maybe once a week, sometimes less. Only when I'm around a lot of dust.
Doctor: That's excellent. So the beclomethasone is working well. Are you using it every morning and evening?
Patient: Yes, two puffs twice a day.
Doctor: Any hoarseness or mouth problems?
Patient: No, I rinse my mouth after like you told me.
Doctor: Good technique. Let me listen to your chest. Both sides are clear, no wheeze. Your peak flow is 380, that's in your green zone. I'm very happy with how you're doing. Let's continue the beclomethasone inhaler and keep the salbutamol for when you need it. I'll see you in three months.
Patient: Thank you, doctor. Should I avoid anything?
Doctor: Keep avoiding the dust triggers as much as you can.""",
        dictation="""\
30 year old male, asthma follow-up visit. Currently maintained on beclomethasone inhaler two puffs twice daily as preventer and salbutamol inhaler as needed for rescue. Well controlled with no acute flares or exacerbations in the past four months. Rescue inhaler use reduced to approximately once per week, mainly with dust exposure. Patient practising good inhaler technique including mouth rinsing after steroid use with no oral thrush or hoarseness. Chest examination clear bilaterally with no wheeze on auscultation. Peak flow reading 380 litres per minute which is within the green zone. Plan to continue current regimen unchanged. Review in three months. Trigger avoidance strategies reinforced.""",
        expected_diagnoses=["asthma"],
        expected_medications=["salbutamol", "beclomethasone"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
        ],
    ),

    Encounter(
        name="Epilepsy follow-up — seizure free on phenytoin",
        category="chronic-routine",
        conversation="""\
Doctor: How are you doing? Any fits since I last saw you?
Patient: No, doctor, none at all. It's been six months now since the last one.
Doctor: That's wonderful news. You're taking the phenytoin regularly?
Patient: Yes, 200 milligrams every night before bed. I never miss it.
Doctor: Any problems? Dizziness, blurred vision, gum swelling?
Patient: My gums do look a bit thick but it doesn't bother me.
Doctor: That's a known side effect of phenytoin. Make sure you brush well and see the dentist if it gets worse. Are you still driving?
Patient: No, you told me to wait at least a year seizure-free. I'm using the minibus.
Doctor: That's the right thing. Let me examine you... no nystagmus, coordination is fine, you seem well. I'm happy to continue the phenytoin 200 at night. Let's see you again in three months. If you have any seizures before then, come straight back.
Patient: Thank you, doctor. I'm just so relieved they've stopped.""",
        dictation="""\
44 year old female, epilepsy follow-up. Currently on phenytoin 200mg nocte, reports excellent adherence with no missed doses. Seizure-free for six months which is a significant milestone. Mild gingival hyperplasia noted on examination, a recognized side effect of phenytoin, but no functional impairment and patient is not troubled by it. Dental hygiene advice reinforced. Full neurological examination performed showing no nystagmus, coordination normal, no cerebellar signs. Patient not driving as per medical recommendation to wait at least one year seizure-free. Plan to continue phenytoin 200mg daily at current dose. Review in three months. Advised to return immediately if any seizure activity occurs.""",
        expected_diagnoses=["epilepsy"],
        expected_medications=["phenytoin"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="HTN + DM combination — needs adjustment",
        category="chronic-routine",
        conversation="""\
Doctor: Let me go through everything today. How are you feeling?
Patient: Not great, doctor. I've been getting headaches again and I feel tired.
Doctor: Let me check your pressure... 142 over 88. That's crept up. And your sugar today?
Patient: The nurse checked, she said 10.1.
Doctor: Both are a bit higher than we want. You're on enalapril 10 and metformin 500 twice a day, yes?
Patient: Yes, I take them every day.
Doctor: We might need to add something for the blood pressure. I'm going to add hydrochlorothiazide 12.5 milligrams in the morning along with the enalapril. That should bring the pressure down further. The metformin we'll keep the same for now but I want to recheck your sugar and your kidney function in four weeks.
Patient: More tablets, doctor?
Doctor: I know it's frustrating, but both conditions need good control to prevent complications. Are you watching the diet?
Patient: I'm trying. My wife helps me with the cooking.
Doctor: Good. Let's also check your urine for protein next time. Come back in four weeks.""",
        dictation="""\
55 year old male with concurrent hypertension and type 2 diabetes mellitus. Currently on enalapril 10mg daily and metformin 500mg twice daily, reports good adherence. Blood pressure today 142 over 88, which is above target despite current therapy. Patient complaining of recurrent headaches and fatigue. Random glucose 10.1 millimoles, also above target. Adding hydrochlorothiazide 12.5mg daily in the mornings alongside enalapril for improved blood pressure control. Continue metformin at current dose. Dietary counseling reinforced with emphasis on both salt and carbohydrate reduction. Ordering renal function panel and urine protein at next visit in four weeks to monitor kidney health given the dual risk factors of hypertension and diabetes.""",
        expected_diagnoses=["hypertension", "diabetes"],
        expected_medications=["enalapril", "metformin", "hydrochlorothiazide"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="New HTN diagnosis — starting enalapril",
        category="chronic-routine",
        conversation="""\
Doctor: What brings you in today?
Patient: I've been having these headaches, doctor, mostly in the back of my head. They come almost every day now, especially in the afternoons.
Doctor: How long has this been going on?
Patient: Maybe three weeks. I thought it was just stress from work.
Doctor: Let me check your pressure... 158 over 96. That's high. Let me do it again on the other arm... 155 over 94. Both sides elevated.
Patient: What does that mean?
Doctor: Your blood pressure is raised. The headaches could be related. Have you ever been told you have high pressure before?
Patient: No, never. But my father had it.
Doctor: Family history is a risk factor. I need to start you on medication. I'm going to give you enalapril 10 milligrams, one tablet every morning. It's important you take it every day. I also want you to cut down on salt and try to exercise — even walking for thirty minutes a day helps.
Patient: Is this something I'll take forever?
Doctor: Most likely, yes, but it will protect your heart and kidneys. Come back in two weeks so I can check the pressure again.""",
        dictation="""\
48 year old male, presenting with occipital headaches for three weeks, initially attributed to stress. Blood pressure measured at 158 over 96 in the right arm, confirmed at 155 over 94 in the left arm, elevated bilaterally. No prior history of raised blood pressure. Positive family history with father having hypertensive disease. No evidence of end-organ damage on examination. New diagnosis of essential hypertension. Initiating enalapril 10mg once daily as first-line therapy. Comprehensive lifestyle advice provided including salt restriction, regular aerobic exercise of at least 30 minutes of brisk walking daily, and stress management. Return in two weeks for repeat blood pressure assessment and to evaluate medication tolerance. Advised to present urgently if severe headache or visual disturbance occurs.""",
        expected_diagnoses=["hypertension"],
        expected_medications=["enalapril"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="HTN medication adjustment — increasing enalapril",
        category="chronic-routine",
        conversation="""\
Doctor: How are you doing on the enalapril?
Patient: I'm taking it every day but the headaches are still coming and going.
Doctor: Let me check your pressure... 155 over 95. That's still too high. You've been on 10 milligrams for six weeks now.
Patient: The headaches have improved a bit but they haven't gone away completely.
Doctor: Six weeks is enough time to see the full effect. The 10 milligrams isn't doing enough on its own. I'm going to increase it to 20 milligrams daily. Same tablet, just double the dose.
Patient: Any side effects from the higher dose?
Doctor: Watch for dizziness when you stand up, and let me know if you develop a dry cough. Also monitor how you feel in the first few days. Your kidneys were fine on the last blood test.
Patient: Should I come back sooner?
Doctor: Yes, let's see you in three weeks. If the headaches get worse or you get any chest pain, come immediately.""",
        dictation="""\
50 year old male, hypertension follow-up after six weeks on enalapril 10mg daily. Blood pressure today remains elevated at 155 over 95, with persistent intermittent occipital headaches that have only partially improved. Headaches improved compared to baseline but not resolved. Adequate time has passed to assess response and current dose is providing insufficient control. Previous renal function tests were within normal limits. Increasing enalapril from 10mg to 20mg once daily. Counseled on potential side effects at the higher dose including postural dizziness and dry cough. Continue monitoring at home where possible. Return in three weeks for repeat assessment. Safety netting advice given regarding chest pain and sudden worsening headache.""",
        expected_diagnoses=["hypertension"],
        expected_medications=["enalapril"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="Diabetic non-adherence — education and restart",
        category="chronic-routine",
        conversation="""\
Doctor: Your sugar today is 15.8. When did you last take your metformin?
Patient: [pause] I stopped taking it about two months ago, doctor.
Doctor: Why did you stop?
Patient: It was giving me diarrhea and I ran out. And I couldn't afford to come to the clinic.
Doctor: I understand the difficulties, but stopping your medication is very dangerous. At 15.8 your sugar is very high and you could develop serious complications — problems with your eyes, your kidneys, your feet.
Patient: I know, I feel terrible about it. I'm always thirsty and going to the bathroom all the time.
Doctor: Those are symptoms of uncontrolled sugar. We need to restart the metformin. I'm going to start you back on 500 milligrams once a day for a week, then increase to twice a day. Take it with food, it helps with the stomach side effects.
Patient: And if I get the diarrhea again?
Doctor: Take it in the middle of meals, not before. If it's still bad, come back and we can try a different formulation. But please don't stop without talking to me first. Your tablets are free at the clinic.
Patient: I didn't know they were free. I'll take them, doctor.""",
        dictation="""\
45 year old male, known diabetic, has been non-adherent to metformin for approximately two months. Stopped medication due to troublesome diarrhea and was unaware that clinic medications are dispensed free of charge. Now presenting with symptomatic hyperglycemia including polyuria and polydipsia. Random glucose today markedly elevated at 15.8 millimoles per litre. No features of metabolic crisis. Restarting metformin at a reduced dose of 500mg once daily with the main meal to minimize gastrointestinal side effects, with plan to increase to 500mg twice daily after one week if tolerated. Extensive adherence counseling provided covering the importance of uninterrupted therapy and the risks of long-term poor glycemic control including eye, kidney, and nerve complications. Fasting glucose and HbA1c to be checked in four weeks to guide further management.""",
        expected_diagnoses=["diabetes"],
        expected_medications=["metformin"],
        expected_dangers=[
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="Lifestyle modification — new HTN, no meds",
        category="chronic-routine",
        conversation="""\
Doctor: Your pressure today is 145 over 92. That's raised.
Patient: My mother always had high pressure. Is mine that bad?
Doctor: It's stage one. Not dangerously high, but it needs attention. I see you're overweight — 96 kilograms at your height. Do you exercise?
Patient: Honestly, no. I sit at a desk all day and by the time I get home I'm too tired.
Doctor: And your diet?
Patient: Lots of takeaways, salty foods, I know it's not good.
Doctor: Here's what I'd like to try. You're young and motivated, so let's give lifestyle changes a real chance before starting tablets. I want you to walk briskly for thirty minutes at least five days a week. Cut your salt intake in half. Eat more vegetables, less fried food. Try to lose five kilograms over the next three months.
Patient: I can try that.
Doctor: If your pressure is still above 140 over 90 in three months, we'll need to start medication. But many people can bring it down with these changes alone. I'll see you in three months. Check your pressure at the pharmacy once a month and write it down for me.
Patient: Alright, doctor, I'll do my best.""",
        dictation="""\
38 year old male, incidental finding of elevated blood pressure at 145 over 92 during routine visit. Currently overweight at 96 kilograms with a body mass index in the overweight range. Predominantly sedentary lifestyle working at a desk with a diet high in processed and salty foods. Positive family history with mother having hypertensive disease. This is a stage one elevation without evidence of end-organ damage. Patient is young and motivated, so electing for a three-month trial of lifestyle modification before considering pharmacotherapy. Comprehensive advice provided including brisk walking for at least thirty minutes five days per week, halving current salt intake, increasing vegetable consumption, reducing fried and processed foods, and targeting a five kilogram weight loss. Instructed to check blood pressure monthly at the pharmacy and document readings. Review in three months with initiation of medication if pressure remains above 140 over 90.""",
        expected_diagnoses=["hypertension"],
        expected_medications=[],
        expected_vitals=["blood pressure"],
        expected_dangers=[],
    ),

    Encounter(
        name="Early CKD in diabetic — creatinine rising",
        category="chronic-routine",
        conversation="""\
Doctor: I have your blood results and I'm concerned. Your creatinine has gone up to 150. Last time it was 120.
Patient: What does that mean?
Doctor: It means your kidneys aren't working as well as they should. This is likely related to your diabetes. The sugar, when it's not well controlled, can damage the small blood vessels in the kidneys over time.
Patient: Is it serious?
Doctor: It's something we need to watch very carefully. You're in the early stages of kidney damage. The good news is that the enalapril you're already taking for your blood pressure also helps protect the kidneys.
Patient: I've been on the enalapril 10 for two years now.
Doctor: Good. Your pressure today is 132 over 78 which is reasonable. How's the sugar?
Patient: It was 9.5 this morning.
Doctor: We need to keep that as low as possible. Continue the enalapril and the metformin. I'm going to order some more blood tests — your kidney function panel, urine for protein, and the long-term sugar test. We may need to involve the kidney specialist if things don't stabilize.
Patient: I'm worried, doctor.
Doctor: I understand. But early detection means we can slow this down significantly.""",
        dictation="""\
60 year old male, known type 2 diabetic on metformin 500mg twice daily and enalapril 10mg daily for hypertension over the past two years. Blood results show creatinine has risen to 150 micromol per litre from 120 at the previous visit, indicating a progressive decline in renal function. This represents early chronic kidney disease likely secondary to diabetic nephropathy. Blood pressure today is 132 over 78 which is acceptably controlled. Fasting glucose 9.5 which remains above target. Continuing both current medications with enalapril serving a dual role for blood pressure and renal protection. Ordering full renal function panel including electrolytes, urine albumin to creatinine ratio, and HbA1c. May need referral to nephrology if creatinine continues to rise or if estimated glomerular filtration rate drops further. Patient counseled on the importance of strict glycemic and blood pressure control.""",
        expected_diagnoses=["chronic kidney disease", "diabetes"],
        expected_medications=["enalapril", "metformin"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
            _d("INFO", "Lab Recommendation", ""),
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    # ═══ 8. STI / REPRODUCTIVE HEALTH ═══

    Encounter(
        name="Vaginal discharge syndrome — syndromic management",
        category="sti-reproductive",
        conversation="""\
Patient: Doctor, I have a problem down below. There's a smell and the discharge is different from normal.
Doctor: How long has this been going on?
Patient: About a week. It's yellowish-green and the smell is really bad, especially after my period.
Doctor: Any pain?
Patient: Yes, my lower belly has been sore. And it hurts during relations with my husband.
Doctor: Any burning when you pass urine?
Patient: A little bit, yes.
Doctor: I need to examine you. [After exam] There is quite a bit of discharge and the cervix looks inflamed. With the foul-smelling discharge, the lower abdominal pain, and the cervical inflammation, I'm going to treat you for multiple possible infections using our syndromic approach. I'm giving you metronidazole 2 grams as a single dose today, doxycycline 100 milligrams twice daily for seven days, and ceftriaxone 250 milligrams by injection now. Your partner needs to be treated too — please send him in.
Patient: Is it serious?
Doctor: If left untreated it can spread and cause problems with fertility. But with treatment you should recover fully.""",
        dictation="""\
28 year old female, presenting with one week history of foul-smelling yellowish-green vaginal discharge, associated lower abdominal pain, and dyspareunia. Also reports mild dysuria. Speculum examination reveals purulent cervical discharge with cervical inflammation consistent with cervicitis. No adnexal tenderness or masses on bimanual examination. Using syndromic management approach for vaginal discharge syndrome with lower abdominal pain to cover likely causes including gonorrhea, chlamydia, and bacterial vaginosis. Treatment regimen: metronidazole 2 grams as a single oral dose today, doxycycline 100mg twice daily for seven days, and ceftriaxone 250mg intramuscular stat. Partner notification and concurrent treatment strongly advised. Counseled on abstinence until both partners complete treatment. Return if symptoms not improving within one week.""",
        expected_diagnoses=["vaginal discharge"],
        expected_medications=["metronidazole", "doxycycline", "ceftriaxone"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="Urethral discharge male — syndromic management",
        category="sti-reproductive",
        conversation="""\
Patient: Doctor, I have a problem. It burns badly when I urinate and there's some fluid coming out.
Doctor: When did this start?
Patient: About four days ago. I noticed a yellowish discharge on my underwear.
Doctor: Have you had any sexual contact recently?
Patient: Yes, about ten days ago. With someone I met at a social gathering. We didn't use protection.
Doctor: Let me take a look. [After exam] Yes, there's a definite purulent discharge from the urethra. Given the history and the appearance, this is most likely a sexually transmitted infection. We treat this with a combination to cover the most common causes.
Patient: I'm very embarrassed, doctor.
Doctor: No need to be. This is very common and treatable. I'm going to give you a ceftriaxone 250 milligram injection now, and doxycycline 100 milligrams tablets twice a day for seven days. You need to abstain from sexual contact until you finish the full course and your symptoms have completely resolved. Any partners from the last two weeks should be treated too.
Patient: Thank you, doctor.""",
        dictation="""\
25 year old male, presenting with four day history of dysuria and yellowish purulent urethral discharge. Reports unprotected sexual contact approximately ten days ago with a casual partner. No prior history of sexually transmitted infections. On examination, active purulent discharge from the urethral meatus confirmed, no inguinal lymphadenopathy, no genital ulceration. Syndromic management for male urethral discharge syndrome initiated to cover gonococcal and chlamydial infection. Ceftriaxone 250mg administered intramuscularly stat in clinic and doxycycline 100mg twice daily prescribed for seven days. Abstinence counseling provided until treatment completed and symptoms fully resolved. Partner notification and treatment within the last two weeks strongly advised. Condom use education reinforced. Return if symptoms persist after completing the course.""",
        expected_diagnoses=["urethral discharge"],
        expected_medications=["ceftriaxone", "doxycycline"],
        expected_dangers=[],
    ),

    Encounter(
        name="Genital ulcer syndrome — benzathine penicillin + acyclovir",
        category="sti-reproductive",
        conversation="""\
Patient: Doctor, I have a sore down below that won't heal. It appeared about five days ago.
Doctor: Can you describe it?
Patient: It started as a small lump, then it opened up into a painful sore. The glands in my groin are swollen too.
Doctor: Any other sores elsewhere? Mouth, hands?
Patient: No, just the one.
Doctor: Let me examine you. [After exam] There's a single ulcer about one centimeter, with irregular edges. The inguinal lymph nodes are enlarged and tender. Given the ulcer with lymphadenopathy, I need to treat you for the most common causes using our syndromic guidelines. I'm giving you benzathine penicillin 2.4 million units as an injection in the buttock today, and acyclovir 400 milligrams three times a day for seven days.
Patient: Both at the same time?
Doctor: Yes, we treat for the two most likely causes together. It's important you finish the acyclovir course. We also need to test your blood for other infections. Please abstain from sexual contact until the ulcer has healed completely.
Patient: Alright, doctor.""",
        dictation="""\
32 year old male, presenting with single genital ulcer of five days duration. The ulcer is painful with irregular edges, approximately one centimeter in diameter, located on the penile shaft. Bilateral inguinal lymph nodes are enlarged and tender. No other mucocutaneous lesions identified on examination of the oral cavity, palms, or soles. Using syndromic management approach for genital ulcer syndrome to cover the two most likely causes. Administered benzathine penicillin G 2.4 million units intramuscularly stat for presumptive primary syphilis, and prescribed acyclovir 400mg three times daily for seven days for presumptive genital herpes. Serological testing for syphilis and HIV requested. Counseled on abstinence from sexual contact until the ulcer has completely healed. Partner notification and concurrent treatment strongly advised.""",
        expected_diagnoses=["genital ulcer"],
        expected_medications=["benzathine penicillin", "acyclovir"],
        expected_dangers=[],
    ),

    Encounter(
        name="UTI in woman — nitrofurantoin",
        category="sti-reproductive",
        conversation="""\
Patient: Doctor, it's burning every time I go to the toilet and I feel like I need to go every ten minutes.
Doctor: When did this start?
Patient: Two days ago. There's no discharge, just the burning and the urgency. I've been drinking lots of water.
Doctor: Any blood in the urine?
Patient: I noticed it was a bit pink yesterday.
Doctor: Any fever or pain in your back or sides?
Patient: No fever, just the burning down below.
Doctor: Any chance you could be pregnant?
Patient: No, I had my period last week.
Doctor: Let me dip your urine... positive for leukocytes and nitrites. This is a bladder infection, very common in women. It's straightforward to treat. I'm going to give you nitrofurantoin 100 milligrams twice a day for five days. Make sure you finish the full course even if you feel better after a day or two. Keep drinking plenty of fluids.
Patient: How quickly will it get better?
Doctor: You should notice improvement within a day or two. If it doesn't improve, or you develop fever or back pain, come back immediately.""",
        dictation="""\
34 year old female, presenting with two day history of dysuria, urinary frequency, and urgency. Reports microscopic hematuria with urine appearing slightly pink on one occasion. No fever, no flank or loin pain, no vaginal discharge. Last menstrual period one week ago, not pregnant. Urine dipstick testing positive for leukocytes and nitrites, supporting the clinical diagnosis. This is an uncomplicated lower urinary tract infection. No features of upper tract involvement. Prescribing nitrofurantoin 100mg twice daily for five days as first-line therapy per local guidelines. Patient instructed to complete the full course even if symptoms improve early. Advised to increase oral fluid intake. Clear safety netting advice given to return immediately if symptoms fail to improve within two days, or if fever, loin pain, or systemic unwellness develops suggesting ascending infection.""",
        expected_diagnoses=["UTI", "urinary tract"],
        expected_medications=["nitrofurantoin"],
        expected_dangers=[],
    ),

    # ═══ 9. SKIN / WOUND / INFECTION ═══

    Encounter(
        name="Cellulitis of leg — flucloxacillin",
        category="skin-wound",
        conversation="""\
Patient: Doctor, my leg has been getting worse over the past two days. It's red and hot and the swelling is spreading.
Doctor: Which leg?
Patient: The left one, from the ankle up to about mid-calf.
Doctor: Let me have a look. How did this start?
Patient: I scratched it on some wire in the garden about four days ago. At first it was just a small cut, but then the whole area went red.
Doctor: I can see a clear area of erythema spreading up the lower leg. It's warm to touch, tender, and there's some pitting edema. Let me check your temperature... 38.4. You've got a fever as well.
Patient: Is it infected?
Doctor: Yes, the infection has spread into the skin and soft tissue. We call it cellulitis. This needs antibiotics right away. I'm starting you on flucloxacillin 500 milligrams four times a day for seven days. Keep the leg elevated as much as possible. Mark the edge of the redness with a pen so we can see if it's spreading.
Patient: Should I come back?
Doctor: Come back in two days. If the redness spreads past the mark, or your fever goes up, come sooner.""",
        dictation="""\
52 year old male, presenting with left lower leg cellulitis following a traumatic skin break from wire injury in the garden four days ago. Examination reveals well-demarcated spreading erythema extending from the ankle to mid-calf, the skin is warm and tender to palpation with pitting edema present. Temperature elevated at 38.4. No evidence of abscess formation or fluctuance. No crepitus suggestive of necrotizing infection. Peripheral pulses palpable. Starting flucloxacillin 500mg four times daily for seven days to cover staphylococcal and streptococcal pathogens. Advised strict leg elevation whenever sitting or lying. Borders of erythema marked with skin marker pen for objective monitoring of progression or regression. Review in two days. Instructed to return sooner if redness spreads beyond the marked border or fever worsens.""",
        expected_diagnoses=["cellulitis"],
        expected_medications=["flucloxacillin"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
        ],
    ),

    Encounter(
        name="Abscess drainage — axillary abscess",
        category="skin-wound",
        conversation="""\
Patient: Doctor, I have this very painful lump under my arm. I can't put my arm down properly.
Doctor: How long has it been there?
Patient: It started as a small bump maybe a week ago. Now it's much bigger and it's throbbing.
Doctor: Let me look... there's a large, about four centimeter, fluctuant swelling in the right axilla. It's extremely tender. You can see the skin is thinned and almost ready to burst.
Patient: Can you do something about it? I can't sleep with the pain.
Doctor: Yes, this needs to be drained. It's an abscess — a collection of pus under the skin. I'm going to numb the area with local anesthetic and then open it up to let the pus out. We'll pack it with gauze so it heals from the inside.
Patient: Will it hurt?
Doctor: The injection will sting briefly but then you won't feel the procedure. After that I'll put you on flucloxacillin 500 milligrams four times daily for five days. Come back in two days so the nurse can change the packing.
Patient: Okay, let's do it.
Doctor: [Proceeds with I&D] There's a good 30 milliliters of pus. The cavity is clean. I've packed it. The relief should be almost immediate.""",
        dictation="""\
40 year old female, presenting with a large right axillary abscess of approximately one week duration. On examination, the swelling measures approximately four centimeters, is fluctuant, extremely tender, with overlying skin thinning and erythema. Patient unable to fully adduct the right arm due to pain and swelling. Incision and drainage performed under local anesthesia with lignocaine infiltration. Approximately 30 milliliters of purulent material expressed from the cavity. Cavity thoroughly irrigated and packed with ribbon gauze to allow healing by secondary intention. Prescribing flucloxacillin 500mg four times daily for five days as adjunctive oral antibiotic therapy. Wound repacking scheduled with the nurse in two days. Patient advised to apply warm compresses between visits and take paracetamol for residual pain. Return earlier if fever develops or swelling recurs.""",
        expected_diagnoses=["abscess"],
        expected_medications=["flucloxacillin"],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
        ],
    ),

    Encounter(
        name="Scabies — family treatment",
        category="skin-wound",
        conversation="""\
Mother: Doctor, my whole family is itching. It started with my youngest about three weeks ago and now all four of us have it.
Doctor: Where is the itching worst?
Mother: Between the fingers, the wrists, and around the waistline. It's terrible at night, none of us can sleep.
Doctor: Let me look at the children's hands... I can see the typical burrows between the fingers. And these small papules on the wrists and belly. This is scabies, a mite that burrows into the skin. It's very contagious which is why it spread through the family.
Mother: Is it dangerous?
Doctor: Not dangerous but very uncomfortable. The important thing is that everyone in the household must be treated at the same time, even if they're not itching yet. I'm prescribing permethrin 5 percent cream for everyone. Apply it from the neck down to the entire body. Leave it on overnight and wash it off in the morning. Repeat in one week. Wash all bed linens and clothes in hot water on the same day you apply the cream.
Mother: Even the baby?
Doctor: For the baby we include the scalp and face, avoiding the eyes and mouth. Come back in two weeks if the itching hasn't improved.""",
        dictation="""\
Family of four presenting with scabies infestation. Three week history beginning with the youngest child and now affecting all household members. Pruritus is the predominant symptom, characteristically worse at night and disrupting sleep. Examination of the children reveals typical serpiginous burrow tracks in the interdigital web spaces of both hands, with papular rash at the wrists, waistline, and anterior axillary folds. Diagnosis is clinical based on the distribution, morphology, and household spread pattern. Prescribing permethrin 5 percent cream for all household members including those who are currently asymptomatic. Application from the neck down to the entire body surface overnight, washed off after eight to twelve hours, to be repeated in seven days. For the infant, cream to include the scalp and face avoiding eyes and mouth. All bed linens, clothing, and towels to be washed in hot water on the day of treatment. Review in two weeks if itching persists.""",
        expected_diagnoses=["scabies"],
        expected_medications=["permethrin"],
        expected_dangers=[],
    ),

    Encounter(
        name="Ringworm — child with tinea corporis",
        category="skin-wound",
        conversation="""\
Mother: Doctor, my son has this funny ring on his tummy that won't go away.
Doctor: How long has it been there?
Mother: About two weeks. It started small but it's getting bigger. It's a circle with the skin clearing in the middle.
Doctor: Let me have a look. How old is he?
Mother: He's six.
Doctor: I can see a well-defined circular patch, about three centimeters, with raised scaly edges and central clearing on the anterior trunk. Any pets at home?
Mother: We have a cat.
Doctor: That's likely where he picked it up. This is a fungal skin infection. We see it often in children. I'm going to prescribe clotrimazole cream, apply it twice a day to the patch and about one centimeter around it. Continue for two weeks even after it looks like it's cleared.
Mother: Is it contagious?
Doctor: Mildly, yes. Try not to share towels. If you notice similar patches on other children, bring them in. It should respond well to the cream. If it's not improving in two weeks, come back and we may need to add oral medication.
Mother: Thank you, doctor.""",
        dictation="""\
6 year old male, brought by mother with an annular scaly patch on the anterior trunk present for approximately two weeks and gradually enlarging. On examination, there is a well-defined circular lesion approximately three centimeters in diameter with raised erythematous scaly edges and central clearing, which is the classic presentation of tinea corporis. No satellite lesions and no scalp involvement. Household has a pet cat which is the most likely source of the dermatophyte infection given the zoonotic transmission pattern. Prescribing clotrimazole cream to be applied twice daily to the lesion and one centimeter of surrounding skin, continuing for at least one week beyond apparent clinical clearance to prevent recurrence. Hygiene advice given regarding avoiding shared towels. Return if the lesion fails to respond or if new patches appear, as oral antifungal therapy may then be required.""",
        expected_diagnoses=["ringworm", "tinea"],
        expected_medications=["clotrimazole"],
        expected_dangers=[],
    ),

    Encounter(
        name="Minor burn wound — hot water scald",
        category="skin-wound",
        conversation="""\
Mother: Doctor, my daughter burnt her hand on boiling water about an hour ago. She was trying to pour tea and it spilled.
Doctor: How old is she?
Mother: She's nine.
Doctor: Let me see the hand. Where exactly?
Mother: The back of the right hand and two fingers.
Doctor: I can see a well-demarcated area of redness and blistering on the dorsum of the right hand, about five by three centimeters, extending to the index and middle fingers. The blisters are intact. Can you feel me touching here?
Child: [crying] Yes, it hurts!
Doctor: Good, the sensation is intact. This is a partial thickness burn, what we call a superficial second degree burn. The skin is red with blisters but the deeper layers are undamaged. I'm going to clean this gently, apply silver sulfadiazine cream, and put a sterile dressing on it.
Mother: Will it scar?
Doctor: At this depth, probably not if we keep it clean and it doesn't get infected. Change the dressing daily. Apply the cream each time. Keep the hand elevated. Bring her back in three days so I can check it. Give her paracetamol for the pain.
Mother: Thank you, doctor.""",
        dictation="""\
9 year old female, brought by mother with a hot water scald injury to the right hand sustained approximately one hour prior while pouring tea. On examination, there is a partial thickness superficial second degree burn to the dorsum of the right hand measuring five by three centimeters, extending onto the index and middle fingers. Blisters are intact with surrounding erythema. Sensation is preserved throughout the affected area and capillary refill is normal, indicating the deeper structures are undamaged. Wound gently cleaned with normal saline. Silver sulfadiazine cream applied as a topical antimicrobial barrier and sterile non-adherent dressing applied. Instructions given for daily dressing changes at home with fresh cream application each time. Paracetamol syrup prescribed for analgesia at weight-appropriate dosing. Hand to be kept elevated. Review in three days to assess healing progress and exclude secondary infection. Burn prevention and kitchen safety education provided to the family.""",
        expected_diagnoses=["burn"],
        expected_medications=["silver sulfadiazine", "paracetamol"],
        expected_dangers=[],
    ),

    # ═══ 10. MENTAL HEALTH ═══

    Encounter(
        name="Depression — starting fluoxetine",
        category="mental-health",
        conversation="""\
Doctor: Tell me what's been going on.
Patient: [long pause] I just... nothing feels right anymore. I don't enjoy anything. I used to love cooking for my family but now I just can't be bothered. Even getting out of bed is hard.
Doctor: How long have you been feeling this way?
Patient: Months. Maybe since my mother passed away. I cry for no reason. I feel like a burden to everyone.
Doctor: How's your sleep?
Patient: Terrible. I wake up at three in the morning and can't get back to sleep. I just lie there thinking.
Doctor: And your appetite?
Patient: I've lost weight. My clothes are loose.
Doctor: I'd like to ask you some specific questions from a screening tool we use. Over the last two weeks, how often have you felt down or hopeless?
Patient: Nearly every day.
Doctor: [Completes PHQ-9] Your score is 14, which indicates moderate depression. This is a real medical condition, not a weakness. I'd like to start you on fluoxetine 20 milligrams, one tablet every morning. It takes about two to three weeks to start working, so don't give up if you don't feel better immediately.
Patient: Will I need it forever?
Doctor: Usually at least six months to a year. Let's see how you respond. I want to see you in two weeks. And please, if you ever feel like harming yourself, come to the clinic immediately or call this number.""",
        dictation="""\
42 year old female, presenting with several months of persistent low mood following the death of her mother. Reports prominent anhedonia with loss of interest in previously enjoyed activities including cooking. Early morning wakening at three AM with inability to return to sleep. Significant unintentional weight loss with clothes becoming loose. Frequent tearfulness and feelings of being a burden to her family. Patient Health Questionnaire PHQ-9 screening completed with a score of 14 indicating moderate depression. No active suicidal ideation elicited but safety netting performed with emergency contact information provided. Initiating fluoxetine 20mg once daily in the morning. Counseled that therapeutic response typically takes two to three weeks and the medication should not be stopped early. Review in two weeks for early assessment of tolerability and any emergence of side effects. Bereavement context acknowledged as a precipitating factor.""",
        expected_diagnoses=["depression"],
        expected_medications=["fluoxetine"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="Generalized anxiety — amitriptyline low-dose",
        category="mental-health",
        conversation="""\
Patient: Doctor, I can't stop worrying. It's about everything — my children, money, my health. My heart races and I feel like something terrible is going to happen.
Doctor: How long has this been going on?
Patient: At least a year, but it's gotten much worse the last three months. I can't concentrate at work. My boss noticed.
Doctor: Any physical symptoms?
Patient: My heart pounds, I get trembling in my hands, my stomach is always in knots. Sometimes I feel dizzy.
Doctor: Do you have specific attacks that come on suddenly, or is it more of a constant feeling?
Patient: It's constant. Always there, just sometimes worse than others.
Doctor: Are you sleeping alright?
Patient: No, it takes me hours to fall asleep because my mind won't switch off.
Doctor: What I'm hearing sounds like generalized anxiety. It's very real and very treatable. I want to try two things. First, I'm going to start you on a low dose of amitriptyline, 25 milligrams at night. It will help with the sleep and also take the edge off the anxiety over time. Second, I'd like you to learn some breathing techniques — slow, deep breaths when you feel the anxiety building.
Patient: I don't want to become addicted to tablets.
Doctor: Amitriptyline is not addictive. Let's try it for a few weeks and see how you go. Come back in three weeks.""",
        dictation="""\
36 year old male, presenting with generalized anxiety symptoms ongoing for over a year with significant worsening in the past three months. Reports persistent and pervasive worry about multiple domains including family, finances, and health. Prominent somatic symptoms include palpitations, hand tremor, gastrointestinal distress, and dizziness. Significant insomnia with prolonged sleep latency due to racing thoughts. No history of discrete panic attacks with sudden onset and offset, distinguishing this from a panic disorder presentation. Functional impairment noted at work with employer expressing concern about concentration. Starting amitriptyline 25mg at night to address both anxiety symptoms and insomnia, taking advantage of its sedative properties. Reassured patient that amitriptyline is not habit-forming. Non-pharmacological strategies discussed including diaphragmatic breathing exercises and progressive muscle relaxation techniques. Review in three weeks to assess response and tolerability.""",
        expected_diagnoses=["anxiety"],
        expected_medications=["amitriptyline"],
        expected_dangers=[],
    ),

    Encounter(
        name="Alcohol use disorder — thiamine and counseling",
        category="mental-health",
        conversation="""\
Patient: Doctor, I need help. I've been drinking too much for too long and it's destroying my life.
Doctor: I appreciate you coming in. Can you tell me about your drinking?
Patient: I drink every day. Usually a bottle of wine, sometimes more. On weekends I drink much more. My wife is threatening to leave.
Doctor: When did you last have a drink?
Patient: Last night. This morning my hands were shaking so badly I couldn't hold a cup of tea.
Doctor: Those morning tremors are a sign your body has become dependent on the alcohol. How long have you been drinking at this level?
Patient: Maybe three years.
Doctor: Any stomach problems? Vomiting blood?
Patient: No, just heartburn sometimes.
Doctor: I'm going to check a few things. [Examines] Your liver feels a bit enlarged. Heavy alcohol use depletes certain vitamins that your brain and nerves need. I'm starting you on thiamine 100 milligrams three times daily — that's vitamin B1, very important. I also want to arrange counseling with our social worker who specializes in substance use.
Patient: Do I need to stop cold turkey?
Doctor: Stopping suddenly can be dangerous when you're at this level. I'm going to refer you to the district hospital for a medically supervised detox program. In the meantime, try to reduce gradually.
Patient: Thank you for not judging me, doctor.""",
        dictation="""\
48 year old male, presenting with alcohol use disorder of at least three years duration. Reports daily consumption of approximately one bottle of wine with significantly higher intake on weekends. Morning tremors present indicating established physical dependence on alcohol. Social consequences including marital strain with wife threatening to leave. On examination, mild hepatomegaly palpated approximately two centimeters below the costal margin. No jaundice, no spider naevi, no ascites. Starting thiamine 100mg three times daily as nutritional supplementation to prevent Wernicke encephalopathy which is common in chronic alcohol use. Counseling referral arranged with clinic social worker specializing in substance use disorders. Referral letter written to the district hospital for medically supervised detoxification given the risk of withdrawal seizures at this level of dependence. Patient appears motivated for change. Liver function tests and full blood count to be ordered. Advised against abrupt cessation while awaiting supervised program.""",
        expected_diagnoses=["alcohol"],
        expected_medications=["thiamine"],
        expected_dangers=[],
    ),

    # ═══ 11. MUSCULOSKELETAL / PAIN ═══

    Encounter(
        name="Low back pain — mechanical, paracetamol + ibuprofen",
        category="musculoskeletal",
        conversation="""\
Patient: Doctor, my back went out yesterday. I was lifting a heavy bag of maize and I felt something pull.
Doctor: Where exactly is the pain?
Patient: Right in the lower back, across both sides. It's worse when I bend forward or try to twist.
Doctor: Any pain going down your legs? Numbness or tingling? Weakness in either leg?
Patient: No, just in the back.
Doctor: Any problems with your bladder or bowels since this happened?
Patient: No, everything is normal there.
Doctor: Good. Let me examine you. [Examines] There's muscle spasm across the lower back. Straight leg raise is negative on both sides. Your reflexes and strength are normal in both legs. There are no red flag features here. This is a mechanical strain from the lifting.
Patient: Do I need an X-ray?
Doctor: No, X-rays don't show muscle injuries and your examination doesn't suggest anything more serious. I'm going to give you paracetamol 1 gram four times a day and ibuprofen 400 milligrams three times a day with food. Try to keep gently active — bed rest actually makes it worse. Use a hot water bottle on the area.
Patient: How long until it gets better?
Doctor: Most cases like this improve significantly within one to two weeks. If it's not improving, or if you develop any leg symptoms, come back.""",
        dictation="""\
40 year old male, acute onset lower back pain since yesterday precipitated by heavy lifting of a bag of maize. Pain localized across the lower lumbar region bilaterally, exacerbated by forward flexion and rotation. No radicular symptoms, no pain or tingling radiating into either lower limb. No bladder or bowel disturbance. On examination, paravertebral muscle spasm palpable across the lower lumbar spine. Straight leg raise negative bilaterally. Lower limb reflexes intact and symmetrical. Motor power full. No red flag features identified. Clinical assessment consistent with acute mechanical low back strain. Prescribing paracetamol 1 gram four times daily and ibuprofen 400mg three times daily with food. Advised to remain gently active rather than bed rest. Avoid heavy lifting for two weeks. Hot compresses for comfort. Review if not improving within two weeks or if leg symptoms develop.""",
        expected_diagnoses=["back pain"],
        expected_medications=["paracetamol", "ibuprofen"],
        expected_dangers=[],
    ),

    Encounter(
        name="Knee osteoarthritis — elderly, paracetamol + advice",
        category="musculoskeletal",
        conversation="""\
Patient: Doctor, my knees have been getting worse and worse. Some mornings I can hardly get out of bed.
Doctor: How long has this been a problem?
Patient: Many years, but the last six months especially. The right knee is worse than the left.
Doctor: What makes it worse?
Patient: Walking far, climbing stairs, and when I've been sitting for a long time. When I first stand up it's very stiff.
Doctor: How long does the stiffness last?
Patient: About fifteen to twenty minutes, then it loosens up.
Doctor: Any swelling?
Patient: The right knee looks bigger than the left.
Doctor: Let me examine them. [Examines] The right knee has a small effusion and bony enlargement. There's crepitus on movement. Limited flexion compared to the left. The left knee has some crepitus but no effusion. Given your age and the pattern of symptoms — the stiffness with activity, the crepitus, the gradual onset — this is joint wear and tear, what we call osteoarthritis.
Patient: Can anything be done?
Doctor: Yes. First, regular paracetamol 1 gram three times a day for the pain. Lose some weight if you can — every kilogram you lose takes four kilograms of pressure off the knees. Swimming or gentle exercise in warm water is excellent. I'll also refer you to the physiotherapist for strengthening exercises.
Patient: I was hoping you'd say that, not surgery.
Doctor: Surgery is a last resort. Let's try these measures first.""",
        dictation="""\
68 year old female, bilateral knee pain progressive over many years with significant worsening in the past six months. Right knee more severely affected. Morning stiffness lasting fifteen to twenty minutes that improves with movement, typical of mechanical pattern. Pain worsened by prolonged ambulation, climbing stairs, and rising from seated position. Right knee examination shows small effusion, bony enlargement from osteophyte formation, crepitus on passive movement, and limited terminal flexion. Left knee crepitus only, no effusion. Findings consistent with primary osteoarthritis of both knees. Prescribing paracetamol 1 gram three times daily as first-line analgesic. Weight loss counseling provided as each kilogram lost significantly reduces joint load. Hydrotherapy recommended for low-impact exercise. Physiotherapy referral for quadriceps strengthening and range of motion exercises. Review as needed.""",
        expected_diagnoses=["osteoarthritis"],
        expected_medications=["paracetamol"],
        expected_dangers=[],
    ),

    # ═══ 11. HIV/TB MANAGEMENT ═══

    Encounter(
        name="New HIV diagnosis + ART initiation",
        category="hiv-tb",
        conversation="""\
Doctor: Good morning. I have your results back. Please sit down.
Patient: I've been worrying all week, doctor.
Doctor: I understand. Your HIV test has come back positive. I know this is very difficult news.
Patient: [long pause] I... I was afraid of that.
Doctor: We caught it at a reasonable stage. Your CD4 count is 350, which means your immune system is still fairly strong but we need to start treatment now to keep it that way. Your weight today is 58 kilograms.
Patient: What kind of treatment?
Doctor: We're going to start you on a combination of three medicines in one tablet. It contains tenofovir, lamivudine, and dolutegravir. You take one tablet every day at the same time. It's very well tolerated.
Patient: Will I have to take it forever?
Doctor: Yes, but it works very well. Most people on this treatment have an undetectable viral load within a few months. We'll need to check your blood regularly to make sure everything is working. I want you back in two weeks, and we'll do viral load testing at three months.
Patient: Can I still work?
Doctor: Absolutely. You can live a completely normal life on this treatment.""",
        dictation="""\
38 year old female, newly confirmed HIV positive. CD4 count 350. Weight 58 kilograms. Clinically well, no opportunistic infections currently. Counseled on diagnosis and lifelong treatment. Initiating fixed-dose combination tenofovir, lamivudine, and dolutegravir, one tablet daily. Will need baseline bloods including renal function given tenofovir. Viral load at three months to confirm suppression. Follow up two weeks.""",
        expected_diagnoses=["HIV"],
        expected_medications=["tenofovir", "lamivudine", "dolutegravir"],
        expected_dangers=[
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="TB treatment initiation — sputum positive",
        category="hiv-tb",
        conversation="""\
Doctor: I have your sputum results. You tested positive for tuberculosis.
Patient: TB? But I thought it was just a bad cough.
Doctor: You've had this cough for more than two weeks now, and you told me you've been sweating at night and losing weight. Those are all typical signs. Your sputum came back positive for TB bacilli.
Patient: Is it serious?
Doctor: It's very treatable if you take the medication properly. We're going to start you on four medicines combined in one tablet. It's called RHZE — that's rifampicin, isoniazid, pyrazinamide, and ethambutol. You take it every morning on an empty stomach for two months.
Patient: Four medicines?
Doctor: Yes, all four are needed to kill the TB properly. After two months, if your follow-up sputum is negative, we reduce to two medicines for another four months. The total treatment is six months. You must not skip doses or stop early, even when you feel better.
Patient: I've been coughing around my family. Are they in danger?
Doctor: We'll need to screen your household contacts. Bring them in next week. And please wear a mask at home for the first two weeks of treatment.""",
        dictation="""\
42 year old male, persistent productive cough for three weeks, night sweats, weight loss of 5 kilograms. Sputum smear positive for acid-fast bacilli. Confirmed pulmonary TB. Starting intensive phase with RHZE — rifampicin, isoniazid, pyrazinamide, ethambutol — as fixed-dose combination daily for two months. Sputum conversion check at two months. Household contact screening needed. Weight 62 kilograms. Counseled on adherence and infection control.""",
        expected_diagnoses=["tuberculosis"],
        expected_medications=["rifampicin", "isoniazid", "pyrazinamide", "ethambutol"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="TB follow-up at 2 months — sputum conversion",
        category="hiv-tb",
        conversation="""\
Doctor: Welcome back. You've been on your TB treatment for two months now. How are you feeling?
Patient: Much better, doctor. The cough is almost gone and I've put on some weight.
Doctor: That's excellent. Your weight is up to 65 kilograms from 62 when we started. Any problems with the tablets? Any stomach upset, joint pains, tingling in your hands or feet?
Patient: My urine is orange but the nurse told me that's normal from the rifampicin.
Doctor: That's correct, nothing to worry about. Now, we sent off another sputum sample last week. The result is back and it's negative — no TB bacilli seen. That's a very good sign.
Patient: Does that mean I'm cured?
Doctor: Not yet. We still need to continue treatment. But because your sputum has converted to negative, we can move you to the continuation phase. That's just rifampicin and isoniazid for another four months. Same routine — take it daily on an empty stomach.
Patient: So four more months?
Doctor: Yes. And I need to check your liver function since these medicines can affect the liver. We'll do bloods today.""",
        dictation="""\
42 year old male, two months into TB intensive phase on RHZE. Reports significant improvement, cough nearly resolved, weight gained from 62 to 65 kilograms. No adverse effects apart from expected orange urine. Sputum conversion confirmed — smear negative at two months. Transitioning to continuation phase with rifampicin and isoniazid for four months. Checking liver function tests today. Tolerating treatment well. Good adherence reported.""",
        expected_diagnoses=["tuberculosis"],
        expected_medications=["rifampicin", "isoniazid"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="HIV + cotrimoxazole prophylaxis + sulfa allergy",
        category="hiv-tb",
        conversation="""\
Doctor: Your CD4 is quite low at 150, so we need to add a preventive antibiotic to protect you from certain infections while your immune system recovers.
Patient: What kind of infections?
Doctor: Things like a type of pneumonia called PCP, and certain parasites. The medicine is called cotrimoxazole. You'll take one double-strength tablet every day.
Patient: Wait, doctor. I need to tell you something. I'm allergic to sulfa drugs. A few years ago I took something with sulfa in it and I broke out in a terrible rash, my lips swelled up, and I had to go to hospital.
Doctor: I see. Well, cotrimoxazole is really important for your protection at this CD4 level. Let me write it up — cotrimoxazole double strength once daily. We'll also continue your ARVs as before.
Patient: But I told you about my allergy. Isn't cotrimoxazole a sulfa drug?
Doctor: We need the prophylaxis. Take it and come back if you have any problems.""",
        dictation="""\
36 year old male, known HIV positive on ART, CD4 count 150. Needs opportunistic infection prophylaxis. Known sulfa drug allergy — previous severe reaction with rash and angioedema requiring hospitalization. Starting cotrimoxazole double strength once daily for PCP prophylaxis despite allergy history. Continue current ART regimen.""",
        expected_diagnoses=["HIV"],
        expected_medications=["cotrimoxazole"],
        patient_allergies=["sulfa"],
        expected_dangers=[
            _d("CRITICAL", "Drug-Allergy", "sulfa"),
        ],
    ),

    Encounter(
        name="ART side effects — TDF/3TC/EFV dizziness and dreams",
        category="hiv-tb",
        conversation="""\
Patient: Doctor, these ARV pills are giving me problems. I'm dizzy all the time, especially in the mornings, and I'm having the most terrible dreams at night. I wake up confused.
Doctor: How long have you been on this regimen?
Patient: About six weeks now. The dizziness started in the first week and the dreams maybe two weeks in.
Doctor: Which combination are you taking?
Patient: The one with three medicines — tenofovir, lamivudine, and efavirenz. The nurse at the clinic wrote it down for me.
Doctor: The dizziness and vivid dreams are well-known side effects of efavirenz. For many people they settle down after the first few weeks, but you're at six weeks and still having them. Are they affecting your daily life?
Patient: I can't drive to work properly because of the dizziness. And the dreams — I feel like I'm not sleeping at all.
Doctor: I think we should consider switching your regimen. We can change the efavirenz to dolutegravir, which doesn't have these central nervous system effects. The tenofovir and lamivudine would stay the same. Let me arrange that for you.
Patient: Will the new one work as well?
Doctor: Yes, actually dolutegravir is considered even better. Your last viral load was suppressed at less than 50 copies, so you're doing well on treatment.""",
        dictation="""\
34 year old male, HIV positive on TDF/3TC/EFV for six weeks. Complaining of persistent dizziness and vivid nightmares since starting treatment, affecting work and sleep quality. Viral load suppressed at less than 50 copies. Side effects attributable to efavirenz, not settling at six weeks. Plan to switch from efavirenz to dolutegravir, maintaining tenofovir and lamivudine backbone. Counseled on new regimen. Follow up four weeks.""",
        expected_diagnoses=["HIV"],
        expected_medications=["tenofovir", "lamivudine", "efavirenz"],
        expected_dangers=[],
    ),

    Encounter(
        name="PMTCT — HIV positive pregnant woman 28 weeks",
        category="hiv-tb",
        conversation="""\
Midwife: Doctor, I've just done the routine antenatal HIV test on this patient and it's come back positive. She's 28 weeks.
Doctor: Thank you. Ma'am, I need to talk to you about your test result. Your HIV test today is positive.
Patient: [crying] No... what about my baby?
Doctor: I know this is very hard to hear, but the good news is that with the right treatment, there is a very high chance your baby will be born HIV negative. We need to start you on antiretroviral treatment today.
Patient: Today? Right now?
Doctor: Yes, the sooner we start, the better the protection for your baby. We're going to give you the same combination we use for everyone — tenofovir, lamivudine, and dolutegravir. One tablet daily. You'll continue this through pregnancy, delivery, and while breastfeeding.
Patient: Will it hurt the baby?
Doctor: No, these medicines are safe in pregnancy. Your baby will also receive a short course of medicine after birth as extra protection. We need to check your CD4 count and viral load today. Your blood pressure is normal at 116 over 72 and the baby is moving well. Fundal height is appropriate for 28 weeks.
Patient: Will I have to deliver by caesarean?
Doctor: Not necessarily. If your viral load is suppressed by the time of delivery, you can deliver normally.""",
        dictation="""\
28 year old female, 28 weeks gestation, first pregnancy. Routine antenatal HIV screening positive today. Counseled on diagnosis and PMTCT. Initiating ART with tenofovir, lamivudine, and dolutegravir fixed-dose combination daily. Baseline CD4 and viral load being sent. Blood pressure 116 over 72, fundal height appropriate, fetal movements present. Plan to continue ART through pregnancy, delivery, and breastfeeding. Infant nevirapine prophylaxis at delivery. Obstetric referral for high-risk pregnancy monitoring.""",
        expected_diagnoses=["HIV", "pregnancy"],
        expected_medications=["tenofovir", "lamivudine", "dolutegravir"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    # ═══ 12. MATERNAL HEALTH ═══

    Encounter(
        name="First ANC visit — 16 weeks booking",
        category="maternal",
        conversation="""\
Midwife: Welcome to antenatal clinic. This is your first visit?
Patient: Yes, sister. I think I'm about four months pregnant. This is my first baby.
Midwife: Congratulations. Let me do a full booking assessment. When was your last period?
Patient: I think it was around the end of December. I've been missing periods since January.
Midwife: That puts you at about 16 weeks. Let me check a few things. Your blood pressure is 118 over 72, which is perfect. Weight is 64 kilograms. Let me measure your tummy... fundal height is just at the umbilicus, which fits with 16 weeks. Have you felt the baby move yet?
Patient: I think so, little flutters.
Midwife: That's normal for this stage. I'm going to start you on folic acid and ferrous sulfate tablets — the folic acid helps the baby's spine develop, and the iron keeps your blood levels up. Take them every day. We'll also do your routine bloods today — HIV test, syphilis, blood group, and hemoglobin.
Patient: When do I come back?
Midwife: Every four weeks until 28 weeks, then every two weeks, then weekly near the end. Keep your Road to Health card with you always.""",
        dictation="""\
22 year old female, primigravida, first antenatal visit at approximately 16 weeks by dates. Blood pressure 118 over 72. Weight 64 kilograms. Fundal height consistent with dates at umbilicus. Early fetal movements reported. Starting folic acid and ferrous sulfate supplementation. Routine booking bloods sent — HIV, RPR, blood group, hemoglobin. Road to Health booklet issued. Return visit four weeks. Low-risk pregnancy at present.""",
        expected_diagnoses=["pregnancy"],
        expected_medications=["folic acid", "ferrous sulfate"],
        expected_dangers=[],
    ),

    Encounter(
        name="Routine ANC follow-up — 28 weeks",
        category="maternal",
        conversation="""\
Midwife: Welcome back. You're 28 weeks now. How have you been feeling?
Patient: Fine, sister. The baby is kicking a lot, especially at night.
Midwife: That's a good sign, means baby is active. Let me check your blood pressure... 125 over 80, that's fine. Weight is 70 kilograms, you've gained nicely. Let me feel your tummy. Fundal height is measuring right on track for 28 weeks. Baby is lying head down which is good, but it can still turn at this stage.
Patient: My feet have been swelling a bit in the afternoons.
Midwife: Some swelling is normal in pregnancy, especially in the legs and feet. But if your face swells, or you get a bad headache, or your vision goes blurry, you must come straight to the clinic because those can be danger signs. Are you still taking your iron tablets?
Patient: Yes, every day with breakfast.
Midwife: Good. Your hemoglobin at the last visit was 11.2 which is fine, but we'll recheck today since you're in the third trimester now. Continue the ferrous sulfate. I'll see you in two weeks.
Patient: Everything is okay with the baby?
Midwife: Baby is growing well. Heart rate is strong at 142 beats per minute.""",
        dictation="""\
22 year old primigravida, 28 weeks gestation, routine antenatal visit. Blood pressure 125 over 80. Weight 70 kilograms, appropriate gain. Fundal height appropriate for dates, cephalic presentation. Fetal heart rate 142. Good fetal movements reported. Mild pedal edema, physiological. Previous hemoglobin 11.2, rechecking today. Continuing ferrous sulfate. Danger signs counseling done. Return two weeks. Low-risk pregnancy continues.""",
        expected_diagnoses=["pregnancy"],
        expected_medications=["ferrous sulfate"],
        expected_dangers=[],
    ),

    Encounter(
        name="Hyperemesis in early pregnancy — 10 weeks",
        category="maternal",
        conversation="""\
Patient: Doctor, I can't stop vomiting. I've been throwing up all day and night for the past week. I can't keep anything down, not even water.
Doctor: How far along are you?
Patient: Ten weeks. The vomiting started at six weeks but it's gotten so much worse this past week.
Doctor: Let me examine you. Your mouth is very dry, your skin is tenting when I pinch it — you're quite dehydrated. Your pulse is 105 and your blood pressure is a bit low at 95 over 60. How many times are you vomiting per day?
Patient: Maybe fifteen or twenty times. I've lost about four kilograms.
Doctor: This is more than normal morning sickness. You have severe vomiting in pregnancy and you need fluids. I'm going to put up a drip — normal saline with some potassium. And I'll give you metoclopramide to help stop the nausea, 10 milligrams three times a day.
Patient: Is the medicine safe for the baby?
Doctor: Yes, metoclopramide is safe in pregnancy. We need to get you rehydrated and keep testing your urine for ketones. If this doesn't settle, we may need to admit you.
Patient: I'm so miserable, doctor.
Doctor: I know. Let's get these fluids running and hopefully you'll feel much better in a few hours.""",
        dictation="""\
25 year old female, 10 weeks gestation, severe vomiting for one week, unable to tolerate oral intake including fluids. Vomiting 15 to 20 times daily. Weight loss 4 kilograms. Clinically dehydrated — dry mucous membranes, reduced skin turgor. Pulse 105, blood pressure 95 over 60. Clinical picture of hyperemesis gravidarum. Starting IV normal saline with potassium replacement. Metoclopramide 10 milligrams three times daily for antiemesis. Urine ketone monitoring. May need admission if not improving.""",
        expected_diagnoses=["pregnancy"],
        expected_medications=["metoclopramide"],
        expected_vitals=["blood pressure"],
        expected_dangers=[],
    ),

    Encounter(
        name="Mild pre-eclampsia detected — 32 weeks",
        category="maternal",
        conversation="""\
Midwife: Your blood pressure is a bit high today. Let me check it again... 148 over 95. That's definitely elevated.
Patient: Is that bad? I'm 32 weeks now.
Midwife: It's concerning. Have you had any headaches or swelling?
Patient: My ankles have been quite swollen the last few days, and I had a mild headache yesterday.
Midwife: Let me check your urine... there's a trace of protein. Doctor, can you see this patient please?
Doctor: I see the blood pressure is 148 over 95 with trace proteinuria at 32 weeks. Any visual changes? Seeing spots or flashing lights?
Patient: No, nothing like that.
Doctor: Good. Your reflexes are normal. The baby's heart rate is 138, good and strong. This looks like mild pre-eclampsia. We need to bring your pressure down. I'm starting you on methyldopa 250 milligrams three times a day. And I want you back in three days to recheck the pressure and protein.
Patient: Should I be worried?
Doctor: We're catching it early, which is good. But you need close monitoring from now on. If you develop a bad headache, visual changes, or upper abdominal pain, come to the hospital immediately — day or night.""",
        dictation="""\
30 year old female, 32 weeks gestation, second pregnancy. Blood pressure found elevated at 148 over 95 on repeated measurement. Trace proteinuria on dipstick. Ankle edema present. Mild headache yesterday, no visual symptoms. Reflexes normal. Fetal heart rate 138, reassuring. Clinical picture consistent with mild pre-eclampsia. Starting methyldopa 250 milligrams three times daily. Close monitoring — return in three days for blood pressure and protein recheck. Danger signs counseling reinforced. May need early delivery if progresses.""",
        expected_diagnoses=["pre-eclampsia"],
        expected_medications=["methyldopa"],
        expected_vitals=["blood pressure"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
        ],
    ),

    Encounter(
        name="Postpartum check — 6 weeks post delivery",
        category="maternal",
        conversation="""\
Midwife: Welcome to your six-week postnatal check. How are you and baby doing?
Patient: We're doing well, sister. The baby is feeding well and growing.
Midwife: Wonderful. Let me check a few things. How was the delivery? Normal vaginal delivery, is that right?
Patient: Yes, but I had a small cut — the episiotomy.
Midwife: Let me have a look at the episiotomy site... it's healing nicely, no signs of infection. Are you having any pain there?
Patient: Just a little discomfort when I sit for too long.
Midwife: That's normal at this stage. It should be completely healed within another week or two. How is breastfeeding going?
Patient: Very well. He feeds every two to three hours and seems satisfied.
Midwife: That's perfect. Let me check your blood pressure — 115 over 70, perfect. Your lochia — any bleeding still?
Patient: Just a little brown spotting.
Midwife: That's normal at six weeks, it should stop soon. I'm going to continue your iron tablets for another month since your hemoglobin was a bit low after delivery. Are you thinking about family planning?
Patient: Maybe next visit. I want to breastfeed for at least six months first.
Midwife: We can discuss options that are safe with breastfeeding when you're ready.""",
        dictation="""\
24 year old female, six weeks postpartum after normal vaginal delivery. Episiotomy site healing well, no infection. Mild residual discomfort. Breastfeeding exclusively, good milk supply, baby feeding well. Blood pressure 115 over 70. Lochia minimal brown spotting, appropriate for six weeks. Continuing ferrous sulfate for post-delivery anemia. Family planning deferred to next visit — will discuss breastfeeding-compatible options. Routine postnatal check, mother and baby well.""",
        expected_diagnoses=["postpartum"],
        expected_medications=["ferrous sulfate"],
        expected_vitals=["blood pressure"],
        expected_dangers=[],
    ),

    Encounter(
        name="Breastfeeding difficulty — 2 week old",
        category="maternal",
        conversation="""\
Mother: Sister, my baby won't latch properly. Every time I try to feed her, she just cries and turns away. My nipples are so sore and cracked.
Midwife: How old is she?
Mother: Two weeks. She was born at the clinic and feeding was okay at first, but the last few days have been terrible.
Midwife: Is she having any wet nappies? And how many times have you tried to feed today?
Mother: She had maybe three wet nappies today. I've been trying every hour but she just screams.
Midwife: Let me weigh her. She's 3.1 kilograms. What was her birth weight?
Mother: 3.3 kilograms.
Midwife: She's lost a little weight, which at two weeks we don't want to see — she should be back to birth weight by now. Let me watch you try to feed... I can see the problem. She's not taking enough of the areola into her mouth. Let me show you a better positioning technique. Support her neck like this, and bring her to the breast, not the breast to her. Wait until she opens her mouth wide... there, see how much more she's taking in?
Mother: Oh, that feels different. It doesn't hurt as much.
Midwife: Good. For your sore nipples, express a little milk after feeding and let it dry on them. Come back in three days so I can reweigh her and make sure she's gaining.""",
        dictation="""\
Two week old female, birth weight 3.3 kilograms, current weight 3.1 kilograms — has not regained birth weight. Mother reporting difficulty with breastfeeding, poor latch, cracked and sore nipples. Reduced wet nappies, approximately three per day. Observed feed — poor attachment technique identified. Repositioning and latch correction demonstrated with improvement. Nipple care advice given — expressed breast milk application. Follow up in three days for weight check. If no weight gain, will consider supplementation.""",
        expected_diagnoses=["breastfeeding difficulty"],
        expected_medications=[],
        expected_dangers=[],
    ),

    Encounter(
        name="Family planning counseling — combined oral contraceptive",
        category="maternal",
        conversation="""\
Patient: Doctor, I want to start using contraception. My youngest is now two years old and I don't want another baby right now.
Doctor: Of course. Let me ask you a few questions first. How old are you?
Patient: Twenty-eight.
Doctor: Do you smoke?
Patient: No, never.
Doctor: Any history of blood clots, migraines with aura, or high blood pressure?
Patient: No, nothing like that. I'm healthy.
Doctor: Good. Your blood pressure today is 120 over 75. There are several options we can discuss. There are pills, injections, implants, and intrauterine devices. What appeals to you?
Patient: I think the pill would be easiest. My sister uses it and she's happy with it.
Doctor: For you, the combined oral contraceptive would be fine. It has estrogen and progesterone. You take one tablet every day for 21 days, then seven days off, then start again. The most important thing is to take it at the same time every day.
Patient: Are there side effects?
Doctor: Some women get mild nausea or breast tenderness in the first few months, but it usually settles. If you miss a pill, use a condom as backup. Come back in three months to check how you're doing.
Patient: Thank you, doctor.""",
        dictation="""\
28 year old female, requesting contraception. Para 2, youngest child two years old. Non-smoker. No contraindications — no history of VTE, migraine with aura, or hypertension. Blood pressure 120 over 75. Counseled on all methods. Patient chose combined oral contraceptive pill. Started on low-dose combined pill, 21-day pack with 7-day break. Advised on daily timing, missed pill protocol, and backup contraception. Follow up three months.""",
        expected_diagnoses=["contraception"],
        expected_medications=[],
        expected_dangers=[],
    ),

    Encounter(
        name="STI in pregnancy — doxycycline contraindicated",
        category="maternal",
        conversation="""\
Patient: Sister, I have a discharge that's been getting worse for a week. It's yellowish and it smells bad.
Midwife: How far along are you?
Patient: Twenty-four weeks.
Midwife: Any itching or pain when you pass urine?
Patient: Yes, both. And my husband told me last week that he was treated for something at the men's clinic.
Midwife: That's important information. Let me examine you. Doctor, I need you to see this patient — she's 24 weeks pregnant with a vaginal discharge and her partner was recently treated at the STI clinic.
Doctor: Let me take a look. There's a purulent discharge and some cervical tenderness. Given the history, we need to treat for possible sexually transmitted infection. I'm going to give her metronidazole 400 milligrams three times daily for seven days and doxycycline 100 milligrams twice daily for seven days.
Midwife: Doctor, she's 24 weeks pregnant. Is doxycycline safe?
Doctor: She needs coverage. Start both and we'll see how she responds.""",
        dictation="""\
26 year old female, 24 weeks gestation, presenting with purulent vaginal discharge for one week, dysuria, and pruritus. Partner recently treated at STI clinic. Cervical tenderness on examination. Syndromic management for mixed STI — prescribing metronidazole 400 milligrams three times daily for seven days plus doxycycline 100 milligrams twice daily for seven days. Pregnancy 24 weeks.""",
        expected_diagnoses=["sexually transmitted infection", "pregnancy"],
        expected_medications=["metronidazole", "doxycycline"],
        expected_dangers=[
            _d("WARNING", "Drug-Condition", "doxycycline"),
        ],
    ),

    # ═══ 13. CHILD HEALTH ═══

    Encounter(
        name="Well-child immunization visit — 6 weeks",
        category="child-health",
        conversation="""\
Mother: We're here for the six-week injections, sister.
Nurse: Welcome. Let me first weigh the baby and check a few things. Baby's name?
Mother: Sipho.
Nurse: Sipho weighs 4.2 kilograms today. What was the birth weight?
Mother: 3.4 kilograms.
Nurse: That's good, he's gaining well. Let me plot this on his Road to Health booklet... he's tracking nicely between the 25th and 50th centile. Is he feeding well?
Mother: Yes, only breast milk. He feeds every two to three hours.
Nurse: Perfect, exclusive breastfeeding is best. Now, today he's due for his six-week vaccines. He'll get the pentavalent injection — that covers five diseases including diphtheria, tetanus, and whooping cough. He'll also get the oral polio drops and the pneumococcal vaccine injection. That's two injections and one oral dose.
Mother: Will he get a fever afterwards?
Nurse: He might get a mild fever or be fussy for a day or two. You can give paracetamol drops if he's uncomfortable. If he gets a high fever or is very irritable for more than two days, bring him back. His next vaccines are at ten weeks.
Mother: Thank you, sister.""",
        dictation="""\
Six week old male, Sipho. Birth weight 3.4 kilograms, current weight 4.2 kilograms, tracking 25th to 50th centile on Road to Health chart. Exclusively breastfed, feeding well. Due immunizations administered today — pentavalent vaccine, oral polio vaccine, and pneumococcal conjugate vaccine. Routine six-week immunization visit. Advised paracetamol drops for post-vaccine fever or irritability. Next visit at ten weeks for next round. Growing and developing normally.""",
        expected_diagnoses=["immunization"],
        expected_medications=["paracetamol"],
        expected_dangers=[],
    ),

    Encounter(
        name="Underweight child — 18 months nutritional counseling",
        category="child-health",
        conversation="""\
Nurse: Let me weigh Amahle... she's 8.2 kilograms. At 18 months she should be closer to 10. Let me check the Road to Health booklet. She's dropped below the minus 2 line.
Mother: She's always been small, sister.
Nurse: She's underweight for her age. Doctor, can you see this child please?
Doctor: I see she's below minus 2 z-score. What is she eating?
Mother: Mostly soft porridge. Sometimes I add a little milk. She doesn't like meat.
Doctor: At 18 months she needs more than just porridge. She needs protein — eggs, beans, peanut butter, small pieces of chicken or fish. And she needs to eat at least five times a day, not just three. Has she been sick recently?
Mother: She had diarrhea two weeks ago.
Doctor: That may have contributed to the weight loss. Let me examine her. No signs of severe malnutrition — no edema, no skin changes. Her hair is a bit thin. I'm going to start her on a multivitamin supplement and I want you to come to our nutritional counseling group on Tuesdays. We'll reweigh her monthly.
Mother: Is she going to be okay?
Doctor: With better nutrition she should catch up. But we need to monitor her closely.""",
        dictation="""\
18 month old female, Amahle. Weight 8.2 kilograms, below minus 2 z-score on Road to Health chart — moderate underweight. Diet history poor — predominantly soft porridge with occasional milk. Recent diarrheal illness two weeks ago. No signs of severe acute malnutrition — no edema, no skin changes, thin hair noted. Starting multivitamin supplementation. Nutritional counseling provided — advised on protein-rich foods, frequency of meals, dietary diversity. Referred to nutritional support group. Monthly weight monitoring planned.""",
        expected_diagnoses=["underweight", "malnutrition"],
        expected_medications=["multivitamin"],
        expected_dangers=[],
    ),

    Encounter(
        name="Oral thrush in 3-month-old infant",
        category="child-health",
        conversation="""\
Mother: Doctor, my baby has white patches all over the inside of her mouth and she's not feeding properly. She keeps pulling off the breast and crying.
Doctor: How old is she?
Mother: Three months. It started about four days ago and keeps getting worse.
Doctor: Let me have a look. Open her mouth gently... yes, I can see thick white plaques on the tongue, inner cheeks, and palate. When I try to wipe them off, the tissue underneath is red and raw. This is oral thrush — a fungal infection in the mouth.
Mother: How did she get it?
Doctor: It's very common in young babies. The yeast is naturally present but sometimes overgrows. Her weight today is 5.6 kilograms — what was her last weight?
Mother: 5.4 at her last visit two weeks ago.
Doctor: She's still gaining, which is good, but the thrush is making feeding painful. I'm going to prescribe nystatin oral drops. You put one milliliter in each side of her mouth four times a day, after feeds. Use it for seven days, even if the patches clear before then.
Mother: Should I put anything on my nipples?
Doctor: Yes, apply some nystatin cream to your nipples after each feed to prevent reinfection.""",
        dictation="""\
Three month old female, four day history of white oral plaques and reduced feeding. White plaques on tongue, buccal mucosa, and palate — non-removable without bleeding. Consistent with oral candidiasis. Weight 5.6 kilograms, gaining from 5.4 two weeks ago. Prescribing nystatin oral suspension 1 milliliter to each cheek four times daily for seven days. Nystatin cream to mother's nipples to prevent reinfection cycle. Continue breastfeeding. Review if not improving in one week.""",
        expected_diagnoses=["oral thrush", "candidiasis"],
        expected_medications=["nystatin"],
        expected_dangers=[],
    ),

    Encounter(
        name="Measles — 9-month-old with rash and fever",
        category="child-health",
        conversation="""\
Mother: Doctor, my baby has had a high fever for three days and now this rash has appeared all over his body. His eyes are very red and he has a cough.
Doctor: How old is he?
Mother: Nine months. He hasn't had his measles vaccine yet — it was scheduled for next week.
Doctor: Let me examine him. Temperature is 39.4. He has a maculopapular rash starting on the face and spreading down to the trunk and arms. Bilateral conjunctivitis — both eyes red and watery. And yes, a dry cough. Let me look in his mouth... I can see small white spots on the inner cheeks. These are Koplik spots.
Mother: What's wrong with him?
Doctor: This is measles. It's a notifiable disease, so I need to report it. The good news is that most children recover well with supportive care. I'm going to give him vitamin A — 100,000 units today and another dose tomorrow. This reduces complications significantly. Also paracetamol for the fever.
Mother: Is it dangerous?
Doctor: It can cause complications, especially in malnourished children. Watch for difficulty breathing, ear discharge, or if he becomes more drowsy. Bring him back immediately if any of those happen. Keep him away from other children who haven't been vaccinated.
Mother: His older sister had her vaccines. Is she safe?
Doctor: Yes, she should be protected.""",
        dictation="""\
Nine month old male, three day history of high fever with maculopapular rash starting on face spreading to trunk and limbs. Bilateral conjunctivitis, dry cough. Koplik spots visible on buccal mucosa. Temperature 39.4. Classic measles presentation. Unimmunized — measles vaccine was due next week. Giving vitamin A 100,000 units today, repeat dose tomorrow per WHO protocol. Paracetamol for fever. This is a notifiable disease — public health notification required. Counseled on complications — watch for pneumonia, otitis, encephalitis. Isolate from unvaccinated contacts.""",
        expected_diagnoses=["measles"],
        expected_medications=["vitamin A", "paracetamol"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
        ],
    ),

    Encounter(
        name="Impetigo — 5-year-old honey-crusted lesions",
        category="child-health",
        conversation="""\
Mother: Doctor, my son has these sores on his face that started as small blisters and now they've got this thick yellowish crust on them. They keep spreading.
Doctor: How long has this been going on?
Mother: About five days. First it was just one next to his nose, now there are three or four patches on his face and one on his arm.
Doctor: Let me look. Yes, these are typical honey-colored crusted lesions around the nose and mouth, with a new one starting on the right forearm. Is he scratching them?
Mother: Yes, he says they itch.
Doctor: That's how they spread — through scratching and touching. This is impetigo, a bacterial skin infection. It's very common in children and quite contagious. I'm going to prescribe flucloxacillin 125 milligrams four times a day for seven days — that's the antibiotic syrup. Also wash the affected areas twice daily with chlorhexidine wash before applying the medicine.
Mother: Can he go to creche?
Doctor: Not until the sores have crusted and dried up, usually about 48 hours after starting antibiotics. Keep his nails short so he can't scratch, and make sure he uses his own towel. Wash his hands frequently.""",
        dictation="""\
Five year old male, five day history of spreading skin lesions. Multiple honey-colored crusted plaques perioral and on right forearm, started as vesicles. Pruritic, spreading by autoinoculation. Classic non-bullous impetigo. Prescribing flucloxacillin 125 milligrams four times daily for seven days. Chlorhexidine wash twice daily to affected areas. Hygiene advice — short nails, separate towel, handwashing. Exclude from creche for 48 hours after starting antibiotics. Review if not improving.""",
        expected_diagnoses=["impetigo"],
        expected_medications=["flucloxacillin"],
        expected_dangers=[],
    ),

    Encounter(
        name="Febrile convulsion — 2-year-old post-ictal",
        category="child-health",
        conversation="""\
Mother: [panicked] My child was shaking all over! His eyes rolled back and his whole body went stiff and then started jerking. I thought he was dying!
Doctor: When did this happen?
Mother: About twenty minutes ago. He's been hot since last night with a cold. Then suddenly he just went stiff and started shaking.
Doctor: How long did the shaking last?
Mother: Maybe two or three minutes. Then he went limp and fell asleep. He's just waking up now.
Doctor: Okay, let me examine him. Temperature is 39.5. He's drowsy but he's responding to me — opening his eyes, moving all four limbs. His neck is supple, no stiffness. Fontanelle is flat. Let me check his ears and throat... his throat is red, probably a viral infection causing the fever.
Mother: Is he going to have more fits?
Doctor: This looks like a febrile seizure — a fit brought on by the rapid rise in temperature. They're frightening but usually not dangerous. I'm going to give him paracetamol now to bring the fever down, and sponge him with lukewarm water. We need to observe him for at least an hour.
Mother: Should I take him to the hospital?
Doctor: If this was his first seizure and it lasted less than five minutes and he's recovering well, which he is, we can manage him here. But if it happens again, or lasts longer than five minutes, go straight to the hospital.""",
        dictation="""\
Two year old male, brought in after witnessed generalized tonic-clonic seizure at home lasting approximately two to three minutes. Currently post-ictal, drowsy but rousable. Temperature 39.5. Upper respiratory tract infection — pharyngitis likely viral. Neck supple, fontanelle flat, no meningism. Moving all limbs. First febrile seizure, simple type — generalized, brief, single episode. Paracetamol given stat, tepid sponging. Observing in clinic. Fever management counseling to mother. If recurrent or prolonged seizure, emergency referral required.""",
        expected_diagnoses=["febrile seizure", "seizure"],
        expected_medications=["paracetamol"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
        ],
    ),

    Encounter(
        name="Neonatal jaundice — 4-day-old yellow baby",
        category="child-health",
        conversation="""\
Mother: Sister, my baby looks very yellow. Even the whites of his eyes are yellow. He was born on Monday and it started yesterday.
Nurse: Let me have a look. Yes, he's definitely jaundiced — the yellow colour extends to his chest and abdomen. Let me check a few things. How is he feeding?
Mother: He's breastfeeding but he seems sleepy and doesn't feed for very long.
Nurse: That can happen with jaundice. Birth weight was 3.2 kilograms, today he's 2.9. That's a bit more weight loss than we'd like. Doctor, can you assess this baby please?
Doctor: Day four jaundice, extending below the umbilicus, which concerns me. He's sleepy and feeding poorly. We need to check the bilirubin level urgently. If it's above the treatment threshold for his age, he'll need phototherapy — that's the blue light treatment.
Mother: Is it serious?
Doctor: Jaundice is common in newborns, but when the bilirubin gets too high it can affect the brain. That's why we check the level. I also want to check his blood group and his mother's blood group to rule out blood group incompatibility. We'll also check his hemoglobin. For now, feed him as often as possible — every two hours if you can. The feeding helps clear the bilirubin.
Mother: Will he need to stay in hospital?
Doctor: If the level is high, yes, for the light treatment. We'll know once the blood results come back.""",
        dictation="""\
Four day old male, born at term, birth weight 3.2 kilograms, current weight 2.9 kilograms. Onset of jaundice day three, now extending below umbilicus. Sleepy, poor breastfeeding. Clinically significant neonatal jaundice requiring investigation. Urgent serum bilirubin level needed. Also checking blood group and Coombs test to exclude hemolytic disease, and hemoglobin. If bilirubin above phototherapy threshold for age, will initiate phototherapy. Encouraging frequent breastfeeding. May need admission depending on results.""",
        expected_diagnoses=["neonatal jaundice", "jaundice"],
        expected_medications=[],
        expected_dangers=[
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="IMCI assessment — sick infant with cough, diarrhea, fever",
        category="child-health",
        conversation="""\
Mother: My baby has been sick for three days. He has a bad cough, loose stools, and he's very hot.
Doctor: How old is he?
Mother: Fourteen months.
Doctor: Let me assess him systematically. First, is he able to drink?
Mother: He took some breast milk this morning but not much.
Doctor: Is he vomiting everything?
Mother: No, he kept the milk down.
Doctor: His temperature is 39.2. Let me count his breathing... respiratory rate is 58 per minute, that's fast for his age. Let me look at his chest — I can see the lower ribs pulling in when he breathes. That's chest indrawing. Let me listen... I hear crackles on the right side.
Mother: He's breathing very fast.
Doctor: Yes. Now let me check the diarrhea. How many loose stools per day?
Mother: About six watery ones.
Doctor: Is there blood in the stool?
Mother: No.
Doctor: Let me check for dehydration. His eyes are a bit sunken, skin pinch goes back slowly. He has some dehydration. His weight is 8.5 kilograms. Using the IMCI approach, this child has pneumonia with chest indrawing — that's severe classification — plus diarrhea with some dehydration. He needs amoxicillin 250 milligrams three times a day for the pneumonia, oral rehydration solution for the diarrhea, paracetamol for the fever, and he needs to be referred to the hospital for the severe pneumonia.
Mother: Hospital? Is it that serious?
Doctor: The chest indrawing means his lungs are working very hard. He needs closer monitoring than we can give here.""",
        dictation="""\
Fourteen month old male, three day illness with cough, watery diarrhea six times per day, and fever. Temperature 39.2. Respiratory rate 58 per minute — tachypneic for age. Lower chest wall indrawing present. Right-sided crackles on auscultation. Diarrhea without blood. Some dehydration — sunken eyes, slow skin pinch. Weight 8.5 kilograms. IMCI classification: severe pneumonia with chest indrawing, plus diarrhea with some dehydration. Starting amoxicillin 250 milligrams three times daily. Oral rehydration solution plan B. Paracetamol for fever. Urgent referral to hospital for severe pneumonia classification and inpatient management.""",
        expected_diagnoses=["pneumonia"],
        expected_medications=["amoxicillin", "paracetamol"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    # ═══ 10. ACUTE RESPIRATORY ═══

    Encounter(
        name="Adult URTI — common cold",
        category="respiratory",
        conversation="""\
Patient: Morning doctor. I walked two hours from Nqamakwe to get here. My nose has been running for four days now and my throat is sore. I also have a small cough but nothing serious.
Doctor: Let me have a look. Open your mouth... throat is a bit red but no pus on the tonsils. Let me listen to your chest — clear on both sides. Your temperature is 37.1, that's normal. This is just a common cold, it should pass on its own in a few days.
Patient: Can you give me something? I took umhlonyane tea at home but it didn't help much.
Doctor: I'll give you paracetamol for the sore throat and any aches. Take two tablets three times a day. Drink plenty of warm fluids — your umhlonyane tea is fine to continue. You don't need antibiotics for this.
Patient: Thank you doctor. I was worried it might be something worse.
Doctor: No, just a viral infection. If you get worse — high fever or trouble breathing — come back.""",
        dictation="""\
Adult female, walked in from rural area. Four day history of rhinorrhea, sore throat, mild dry cough. Afebrile at 37.1. Pharynx mildly erythematous, no tonsillar exudate. Chest clear bilaterally. Simple upper respiratory tract infection, viral etiology. Prescribing paracetamol for symptomatic relief. No antibiotics indicated. Reassurance and safety-net advice given.""",
        expected_diagnoses=["upper respiratory tract infection", "URTI", "common cold"],
        expected_medications=["paracetamol"],
        expected_vitals=["temperature"],
        expected_dangers=[],
    ),

    Encounter(
        name="Child sore throat — tonsillitis",
        category="respiratory",
        conversation="""\
Mother: My daughter has been refusing to eat since yesterday. She says her throat is very painful and she feels hot.
Doctor: How old is she?
Mother: She's nine years old.
Doctor: Let me check her temperature... 38.2. Open your mouth for me, sweetie. I can see the tonsils are big and very red with some white patches on them. Her lymph nodes in the neck are swollen too.
Mother: Is it serious?
Doctor: It's a throat infection — tonsillitis. The white patches and fever tell me she needs an antibiotic. I'm going to give her amoxicillin syrup, five mils three times a day for seven days. Also paracetamol for the pain and fever. Make sure she finishes all the antibiotic even when she feels better.
Mother: She doesn't like taking medicine.
Doctor: Mix it in some yogurt or soft porridge. Give her soft foods and warm drinks. If she can't swallow at all or has trouble breathing, bring her straight back.""",
        dictation="""\
Nine year old girl, one day history of odynophagia, refusing to eat, febrile. Temperature 38.2. Bilateral tonsillar enlargement with exudate. Cervical lymphadenopathy. Clinical acute exudative tonsillitis. Starting amoxicillin suspension 250mg per 5ml, five mils TDS for seven days. Paracetamol for symptomatic relief. Mother counseled on completing course and warning signs.""",
        expected_diagnoses=["tonsillitis"],
        expected_medications=["amoxicillin", "paracetamol"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="TB suspect — chronic cough screening",
        category="respiratory",
        conversation="""\
Patient: I've had this cough for about three weeks now, doctor. It won't go away. Sometimes I bring up thick phlegm and once there was a little blood in it.
Doctor: Three weeks is a long time. Do you sweat at night?
Patient: Yes, I wake up with my shirt wet almost every night. And I've lost weight — my trousers are loose now.
Doctor: Have you been in contact with anyone who has TB?
Patient: My uncle was on TB treatment last year. We share a house.
Doctor: That's important. Let me listen to your chest... I can hear some crackles in the upper right zone. Your temperature is 37.5, low grade. With the chronic productive cough, night sweats, weight loss, and a TB contact, I need to screen you for tuberculosis. I'm going to send you for sputum testing — we need two samples, one now and one early tomorrow morning.
Patient: Do I need treatment now?
Doctor: Let's wait for the sputum results first. We should have them in a few days. I won't start any medication until we know for sure.""",
        dictation="""\
35 year old male, three week productive cough with one episode of hemoptysis. Night sweats, unintentional weight loss. Close household TB contact — uncle treated last year. Temperature 37.5. Crackles right upper zone on auscultation. High index of suspicion for pulmonary tuberculosis. Sending two sputum samples for GeneXpert. No treatment started pending results. Follow up for results in three days.""",
        expected_diagnoses=["tuberculosis", "TB"],
        expected_medications=[],
        expected_dangers=[
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="Acute bronchitis in adult",
        category="respiratory",
        conversation="""\
Patient: Doctor, I had a cold last week that got better but now I've developed this terrible cough. It's dry and keeps me up at night. Sometimes I hear a wheezing sound when I breathe out.
Doctor: Any fever?
Patient: No, I haven't felt hot. Just this cough that won't stop.
Doctor: Let me listen... I can hear some wheeze on expiration but no crackles and no consolidation. Your temperature is 36.8, normal. Your oxygen is fine at 97 percent. This sounds like the cold has irritated your airways and you've developed bronchitis.
Patient: Do I need antibiotics?
Doctor: No, this is viral bronchitis. Antibiotics won't help. I'm going to give you a salbutamol inhaler — take two puffs when the cough is bad or you hear the wheeze. It should settle in another week or so.
Patient: What if it doesn't get better?
Doctor: If you're still coughing in three weeks or you develop a fever, come back and I'll reassess.""",
        dictation="""\
42 year old male, post-viral cough for five days following resolved URTI. Dry cough, nocturnal, with audible wheeze. Afebrile at 36.8. Oxygen saturation 97 percent. Auscultation reveals expiratory wheeze bilaterally, no crackles. No consolidation. Acute post-viral bronchitis. Prescribing salbutamol inhaler two puffs as needed for bronchospasm. No antibiotics indicated. Review if persistent beyond three weeks or new fever develops.""",
        expected_diagnoses=["bronchitis"],
        expected_medications=["salbutamol"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="Child first wheeze episode",
        category="respiratory",
        conversation="""\
Mother: My child has been breathing funny since this morning. She makes a whistling sound and her chest goes in and out fast.
Doctor: How old is she?
Mother: Three years old. She's never had this before. She had a runny nose for two days.
Doctor: Let me check her. Temperature is 37.8. Her respiratory rate is 46 which is elevated for her age. I can hear wheeze throughout both lungs. There's some subcostal recession. Her oxygen level is 93 percent which is a bit low.
Mother: What's happening to her?
Doctor: Her airways are tightened up, probably triggered by the cold she had. I'm going to give her a nebulizer with salbutamol right now to open up her airways. I'm also going to give a short course of prednisone syrup for three days to reduce the inflammation. We need to watch her closely.
Mother: Will she be okay?
Doctor: The nebulizer should help quickly. If she doesn't improve or gets worse, we'll need to send her to the hospital.""",
        dictation="""\
Three year old girl, first episode of wheeze. Two day coryzal prodrome followed by acute onset of respiratory distress this morning. Temperature 37.8. Respiratory rate 46, subcostal recession present. Bilateral diffuse wheeze on auscultation. Oxygen saturation 93 percent. No prior history of wheeze or atopy. Treating with salbutamol nebulizer stat, repeat as needed. Starting prednisone 1mg per kg for 3 days. Observe post-nebulizer response. If inadequate improvement, refer for admission.""",
        expected_diagnoses=["wheeze", "bronchospasm"],
        expected_medications=["salbutamol", "prednisone"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
        ],
    ),

    Encounter(
        name="Adult asthma exacerbation",
        category="respiratory",
        conversation="""\
Patient: Doctor, I can't breathe properly. My asthma has been getting worse all week. My inhaler isn't helping anymore.
Doctor: How often are you using the salbutamol?
Patient: Every two or three hours. Even at night.
Doctor: That's too frequent. Let me check you. You're using your accessory muscles to breathe. I can hear widespread wheeze. Your peak flow is 180 — what's your normal?
Patient: Usually about 400.
Doctor: So you're at 45 percent of your best, that's a moderate to severe attack. Your oxygen is 92 percent. Temperature is 37.0. I'm going to nebulize you with salbutamol now, and start you on a course of prednisone 40 milligrams daily for five days. We'll watch how you respond.
Patient: I ran out of my preventer inhaler a month ago. I couldn't afford to buy another one.
Doctor: That explains the worsening. After we stabilize you, we need to get you back on a preventer. For now, let's get this under control.""",
        dictation="""\
32 year old female, known asthmatic, one week progressive worsening of dyspnea and wheeze. Using salbutamol every two to three hours including nocturnal use. Ran out of preventer inhaler one month ago. Peak flow 180, best 400, so at 45 percent predicted. Oxygen saturation 92 percent. Accessory muscle use. Bilateral wheeze. Temperature 37.0. Moderate to severe exacerbation. Salbutamol nebulizer given. Starting prednisone 40mg daily for five days. Monitor response. Will need to restart preventer inhaler.""",
        expected_diagnoses=["asthma"],
        expected_medications=["salbutamol", "prednisone"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
        ],
    ),

    Encounter(
        name="Uncomplicated pneumonia adult",
        category="respiratory",
        conversation="""\
Patient: I've been coughing for five days and now I'm bringing up green sputum. I feel terrible. My wife says I was burning up last night.
Doctor: Let me check you properly. Your temperature is 38.8. Respiratory rate is 24. Let me listen... I can hear crackles over the right lower lobe, dull to percussion there as well. Your oxygen is 94 percent.
Patient: Is it serious?
Doctor: You've got a chest infection in your right lung — pneumonia. Your oxygen is acceptable and you don't look too unwell, so I can treat you here without sending you to hospital. I'm going to give you amoxicillin 500 milligrams three times a day for five days. Take paracetamol for the fever. Rest, drink plenty of fluids.
Patient: How long until I feel better?
Doctor: The fever should come down in two to three days. If it doesn't, or you get worse — more short of breath, can't keep food down — come straight back or go to the emergency unit.""",
        dictation="""\
48 year old male, five day productive cough with green sputum, febrile. Temperature 38.8. Respiratory rate 24. Crackles and dullness to percussion right lower zone. Oxygen saturation 94 percent. Community acquired pneumonia, right lower lobe. CURB-65 score low — can manage as outpatient. Amoxicillin 500mg TDS for five days. Paracetamol. Safety-net advice given regarding worsening symptoms and return visit.""",
        expected_diagnoses=["pneumonia"],
        expected_medications=["amoxicillin"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
        ],
    ),

    Encounter(
        name="Child pneumonia — fast breathing",
        category="respiratory",
        conversation="""\
Mother: My baby has been coughing and breathing very fast since yesterday. She didn't want to breastfeed this morning.
Doctor: How old is she?
Mother: Fifteen months. She was fine until three days ago when she got a runny nose.
Doctor: Let me assess her. Temperature is 39.1. Respiratory rate is 56 which is fast for her age. I can see her lower ribs pulling in with each breath — that's chest indrawing. Let me listen... crackles on the left side. Her oxygen is 91 percent.
Mother: She's been making grunting sounds too.
Doctor: That's concerning. This is pneumonia — a serious lung infection. The fast breathing and chest indrawing mean this is classified as severe. I'm starting amoxicillin right now but she may need to be referred to the district hospital for close monitoring.
Mother: We came from far. Can she be treated here?
Doctor: I'll give the first dose and watch her for a few hours. If she doesn't improve, she must go to hospital. Make sure you keep trying to breastfeed her — small frequent feeds.""",
        dictation="""\
Fifteen month old girl, three day coryzal prodrome progressing to cough with fast breathing and poor feeding. Temperature 39.1. Respiratory rate 56, lower chest wall indrawing present, grunting noted. Left-sided crackles on auscultation. Oxygen saturation 91 percent. Severe pneumonia by IMCI classification. First dose amoxicillin given. Observing response. Low threshold for referral to district hospital for inpatient management if inadequate improvement.""",
        expected_diagnoses=["pneumonia"],
        expected_medications=["amoxicillin"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
        ],
    ),

    Encounter(
        name="Sinusitis — facial pain",
        category="respiratory",
        conversation="""\
Patient: I've had this terrible pressure in my face for about ten days. It started as a cold but then I got this pain over my cheekbones and between my eyes. When I bend forward it gets much worse.
Doctor: Any nasal discharge?
Patient: Yes, thick yellow-green stuff, especially in the morning. And everything tastes and smells wrong.
Doctor: Let me have a look. There's tenderness over both maxillary sinuses. Your nasal mucosa is congested and I can see mucopurulent discharge. Temperature is 37.6. Given that this has been going on for ten days with colored discharge and facial pain, I'm going to treat this as a bacterial sinusitis.
Patient: What do I take?
Doctor: Amoxicillin 500 three times a day for seven days. Also do steam inhalation — lean over a bowl of hot water with a towel over your head, twice a day. It helps drain the sinuses. Take paracetamol for the pain.
Patient: Thank you doctor.""",
        dictation="""\
40 year old female, ten day history of facial pain and pressure over maxillary and frontal sinuses, worse on bending forward. Post-nasal drip with thick yellow-green nasal discharge. Anosmia. Follows a viral URTI. Temperature 37.6. Tenderness over both maxillary sinuses. Mucopurulent discharge visible. Acute bacterial sinusitis. Prescribing amoxicillin 500mg TDS for seven days. Steam inhalation twice daily. Paracetamol for pain. Review if not improving after five days.""",
        expected_diagnoses=["sinusitis"],
        expected_medications=["amoxicillin"],
        expected_vitals=["temperature"],
        expected_dangers=[],
    ),

    Encounter(
        name="Pharyngitis + wrong drug prescribed",
        category="respiratory",
        conversation="""\
Patient: My throat has been burning for three days. It hurts every time I swallow. I haven't been eating properly because of the pain.
Doctor: Open wide for me... your pharynx is very red and inflamed. I can see the uvula is swollen as well. Your temperature is 38.0 and your lymph nodes are tender. This is a bacterial throat infection.
Patient: What will you give me?
Doctor: I'm going to prescribe enalapril 10 milligrams daily for this. Take it every morning.
Patient: Enalapril? My neighbor takes that for her blood pressure.
Doctor: It works for different things. Just take it as I've said. Also gargle with warm salt water and drink warm fluids. Come back if it doesn't improve in a week.""",
        dictation="""\
38 year old male, three day sore throat with odynophagia and reduced oral intake. Pharynx erythematous, uvula edematous, cervical lymphadenopathy. Temperature 38.0. Acute bacterial pharyngitis. Prescribing enalapril 10mg daily. Advised warm salt water gargles. Follow up if no improvement.""",
        expected_diagnoses=["pharyngitis"],
        expected_medications=["enalapril"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("WARNING", "Drug-Condition", "enalapril"),
        ],
    ),

    # ═══ 11. DIARRHEAL / GI ═══

    Encounter(
        name="Child acute gastroenteritis",
        category="gi-diarrheal",
        conversation="""\
Mother: My son has had loose watery stools since yesterday morning. He's been going at least eight times a day. He vomited twice last night.
Doctor: How old is he?
Mother: He's four years old.
Doctor: Is he still drinking?
Mother: He's thirsty and drinks but then some of it comes back up.
Doctor: Let me examine him. His eyes look a bit sunken and when I pinch the skin it goes back slowly. His temperature is 37.9. He's still active and alert though, which is good. He has some dehydration but it's not severe.
Mother: What caused it?
Doctor: Probably a stomach bug — gastroenteritis. The most important thing is to replace the fluids he's losing. I'm giving you oral rehydration salt sachets — dissolve one in a liter of clean water and give him small sips frequently. Also zinc tablets, half a tablet daily for ten days. The zinc helps the gut recover faster.
Mother: Does he need antibiotics?
Doctor: No, this is most likely viral. The ORS and zinc are the treatment. If he can't keep anything down, or the stools have blood in them, or he becomes very drowsy, bring him back immediately.""",
        dictation="""\
Four year old boy, acute onset watery diarrhea eight times daily since yesterday, vomiting twice. Temperature 37.9. Some dehydration — sunken eyes, slow skin pinch — but alert and drinking. No blood in stool. Acute gastroenteritis, likely viral. ORS rehydration plan B — frequent small sips. Zinc supplementation 10mg daily for ten days. No antibiotics indicated. Mother counseled on danger signs requiring return.""",
        expected_diagnoses=["gastroenteritis", "diarrhea"],
        expected_medications=["oral rehydration salts", "zinc"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="Adult food poisoning",
        category="gi-diarrheal",
        conversation="""\
Patient: Doctor, I've been vomiting since last night, I can't keep anything down. I also have loose stools and my stomach is cramping badly.
Doctor: Did you eat anything unusual yesterday?
Patient: I had some chicken from a street vendor in the afternoon. My wife ate it too and she's also sick.
Doctor: That sounds like food poisoning. Let me check you. Your temperature is 37.3, so no real fever. Your abdomen is soft but tender generally. You're a bit dry — your mouth is dry and your pulse is 96. But your blood pressure is okay at 110 over 70.
Patient: I can't stop vomiting.
Doctor: I'm going to give you an injection of metoclopramide now to stop the vomiting. Then start sipping ORS slowly — a teaspoon every few minutes. Once you can keep fluids down, increase the amount. Eat bland food when you can tolerate it.
Patient: How long will this last?
Doctor: Usually 24 to 48 hours. If you're still vomiting tomorrow or you see blood, come back.""",
        dictation="""\
34 year old male, acute onset nausea, vomiting and diarrhea since last night. Ate takeaway chicken — wife also symptomatic. Temperature 37.3. Mild dehydration — dry mucosa, pulse 96, BP 110 over 70. Abdomen soft, diffusely tender. Acute gastroenteritis, food-borne etiology. Metoclopramide 10mg IM stat for vomiting. ORS for rehydration. Bland diet when tolerated. Expect resolution 24 to 48 hours. Return if persistent or bloody stools.""",
        expected_diagnoses=["food poisoning", "gastroenteritis"],
        expected_medications=["metoclopramide", "oral rehydration salts"],
        expected_dangers=[],
    ),

    Encounter(
        name="Worm infestation in child",
        category="gi-diarrheal",
        conversation="""\
Mother: Doctor, I found worms in my daughter's stool this morning. She's been scratching her bottom a lot at night and it wakes her up.
Doctor: How old is she?
Mother: She's six. She started at a new school two months ago.
Doctor: That's very common, especially in young children at school. Let me check her. She looks well, no fever, abdomen is soft. She's well nourished. The perianal area looks a bit irritated from the scratching.
Mother: Is it dangerous?
Doctor: No, it's very common and easy to treat. I'm giving her mebendazole — one tablet now and another one in two weeks. The whole family should be treated at the same time to stop reinfection. Make sure she washes her hands after using the toilet and before eating. Keep her nails short so she can't scratch.
Mother: Should I deworm her brothers too?
Doctor: Yes, everyone in the house. I'll give you tablets for the family.""",
        dictation="""\
Six year old girl, worms visible in stool, perianal itching especially nocturnal. Started new school recently. Well appearing, afebrile, abdomen soft. Perianal excoriation from scratching. Helminth infestation — likely enterobius. Mebendazole 100mg stat, repeat in two weeks. Treating entire household. Hygiene counseling — handwashing, short nails, separate towels.""",
        expected_diagnoses=["worm infestation", "helminth"],
        expected_medications=["mebendazole"],
        expected_dangers=[],
    ),

    Encounter(
        name="Bloody diarrhea — dysentery",
        category="gi-diarrheal",
        conversation="""\
Patient: I've had terrible stomach cramps and diarrhea for three days. Since yesterday there's blood mixed in the stool. I feel very weak.
Doctor: How many times a day?
Patient: Maybe ten or twelve. Small amounts each time with a lot of cramping.
Doctor: Any fever?
Patient: Yes, I've been feeling hot and cold.
Doctor: Let me check. Temperature is 38.5. You're looking dehydrated — dry lips, sunken eyes. Your pulse is 100. Your abdomen is tender in the lower part. The bloody diarrhea with fever and cramps points to dysentery. Where do you get your water from?
Patient: From the communal tap. Sometimes the river when the tap is dry.
Doctor: That may be the source. I'm starting you on ciprofloxacin 500 milligrams twice a day for three days. You also need ORS — drink it as much as you can. If the bleeding gets worse or you start vomiting and can't keep fluids down, go to the hospital.
Patient: Okay doctor.""",
        dictation="""\
45 year old male, three day diarrhea progressing to bloody stools since yesterday. Frequent small volume stools with tenesmus. Temperature 38.5, pulse 100. Dehydrated — dry mucosa, sunken eyes. Lower abdominal tenderness. Drinks water from communal tap and river. Clinical dysentery — likely bacterial. Ciprofloxacin 500mg BD for three days. ORS rehydration. Return if worsening or unable to tolerate oral fluids. May need IV hydration if deteriorates.""",
        expected_diagnoses=["dysentery", "diarrhea"],
        expected_medications=["ciprofloxacin", "oral rehydration salts"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="Gastritis — epigastric burning",
        category="gi-diarrheal",
        conversation="""\
Patient: I have this burning pain right here in my upper stomach. It's been going on for three weeks. It gets worse after I eat, especially spicy food.
Doctor: Any other symptoms?
Patient: Sometimes I feel bloated and nauseous. I belch a lot.
Doctor: Have you vomited blood or had any dark stools?
Patient: No, nothing like that.
Doctor: Do you drink alcohol or smoke?
Patient: I drink beer on weekends. I don't smoke.
Doctor: Let me examine your abdomen. There's tenderness in the epigastric area but no guarding, no masses. Your temperature is normal. I think this is gastritis — inflammation of the stomach lining. The spicy food and alcohol are aggravating it.
Patient: What should I take?
Doctor: I'm going to give you omeprazole 20 milligrams, take it once a day before breakfast for four weeks. Cut down on the spicy food and reduce the alcohol. Eat smaller meals more often. If the pain doesn't improve or you vomit blood, come back urgently.
Patient: Thank you doctor.""",
        dictation="""\
50 year old male, three week history of epigastric burning pain worse post-prandially, especially with spicy food. Associated bloating and belching. No hematemesis or melena. Social drinker, non-smoker. Epigastric tenderness, no peritonism, no organomegaly. Clinical gastritis. Omeprazole 20mg daily before breakfast for four weeks. Dietary advice — avoid spicy food, reduce alcohol, small frequent meals. Red flag counseling. Review in four weeks.""",
        expected_diagnoses=["gastritis"],
        expected_medications=["omeprazole"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="Chronic diarrhea + wrong drug",
        category="gi-diarrheal",
        conversation="""\
Patient: Doctor, I've had loose stools for about six weeks now. It's not getting better. I go four or five times a day.
Doctor: Any blood in the stool?
Patient: No blood, just watery loose stools. Sometimes they're very urgent and I barely make it to the toilet.
Doctor: Have you lost weight?
Patient: Yes, maybe five or six kilograms. My clothes are loose.
Doctor: Any fever or night sweats?
Patient: No, I don't think so.
Doctor: Let me examine you. You've lost some weight, abdomen is soft, mildly tender in the left lower area. No masses. I'm concerned about the duration and weight loss. I'd like to investigate this further. In the meantime, I'm going to start you on metformin 500 milligrams twice a day to help manage the symptoms.
Patient: My neighbor takes metformin for diabetes. Are you sure that's for my stomach?
Doctor: Yes, just take it as prescribed and come back in two weeks.""",
        dictation="""\
42 year old female, six week history of chronic watery diarrhea four to five times daily. Urgency present. Unintentional weight loss approximately five kilograms. No blood, no fever, no night sweats. Abdomen soft, mild left iliac fossa tenderness. Needs workup to exclude inflammatory or infective cause. Starting metformin 500mg BD. Review in two weeks with results.""",
        expected_diagnoses=["diarrhea", "chronic diarrhea"],
        expected_medications=["metformin"],
        expected_dangers=[
            _d("WARNING", "Drug-Condition", "metformin"),
        ],
    ),

    Encounter(
        name="Child severe vomiting — dehydration",
        category="gi-diarrheal",
        conversation="""\
Mother: My baby has been vomiting everything since yesterday. Even water comes back up. She's had loose stools too and she's very listless.
Doctor: How old is the baby?
Mother: Eighteen months.
Doctor: How many times has she vomited?
Mother: I stopped counting. Maybe eight or nine times. And the stools are watery, about five or six times.
Doctor: Let me look at her. Her eyes are definitely sunken. The fontanelle is depressed. When I pinch the skin it goes back very slowly. She's irritable when I touch her but then goes back to being listless. Her temperature is 38.4. She's significantly dehydrated.
Mother: She won't take anything from the cup.
Doctor: We need to give her ORS by spoon or syringe — five mls every few minutes. Even if she vomits, keep going because some will stay down. If she can't keep anything down in the next two hours, she'll need a drip and we'll have to send her to the hospital.
Mother: Please help her, doctor.""",
        dictation="""\
Eighteen month old girl, 24 hour history of persistent vomiting and watery diarrhea. Unable to tolerate oral fluids. Sunken eyes, depressed fontanelle, slow skin pinch, alternating between irritability and lethargy. Temperature 38.4. Moderate to severe dehydration by IMCI criteria. Starting ORS by syringe — 5ml aliquots every two to three minutes. Observe for two hours. If unable to rehydrate orally, will need IV fluids and hospital referral. Mother instructed on ORS technique.""",
        expected_diagnoses=["gastroenteritis", "dehydration"],
        expected_medications=["oral rehydration salts"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    Encounter(
        name="Elderly constipation",
        category="gi-diarrheal",
        conversation="""\
Patient: Doctor, I'm struggling with my stomach. I can only go to the toilet every four or five days and when I do it's very hard and painful. This has been going on for about two months.
Doctor: How's your diet?
Patient: I eat mostly pap and bread. I don't drink much water because I don't feel thirsty.
Doctor: Are you taking any medications?
Patient: Just the blood pressure tablets the other doctor gave me.
Doctor: Okay. Any blood when you pass stool? Any weight loss?
Patient: No blood. My weight is the same.
Doctor: Let me feel your abdomen. I can feel some stool in the left side. No masses, no tenderness. Everything else looks fine. You need more fiber and water in your diet. Eat more vegetables and fruit if you can, and try to drink six to eight cups of water a day. I'm also going to give you lactulose syrup — take 15 mils twice a day. It softens the stool and makes it easier to pass.
Patient: Thank you doctor. I was too embarrassed to come earlier.""",
        dictation="""\
72 year old female, two month history of constipation, passing hard stool every four to five days with straining. Diet low in fiber and fluid. On antihypertensive medication. No red flags — no rectal bleeding, no weight loss, no change in stool caliber. Abdomen soft, palpable stool left iliac fossa. Lactulose 15ml BD. Dietary counseling — increase fiber, increase fluid intake to six to eight glasses daily. Review in four weeks. Consider further workup if no improvement.""",
        expected_diagnoses=["constipation"],
        expected_medications=["lactulose"],
        expected_dangers=[],
    ),

    # ═══ 12. MALARIA / FEBRILE ═══

    Encounter(
        name="Uncomplicated malaria adult",
        category="malaria-febrile",
        conversation="""\
Patient: Doctor, I've been having terrible shaking chills for two days. I shake so much the bed rattles. Then I sweat heavily and feel a bit better before it starts again.
Doctor: Where do you live?
Patient: I'm from a village near Tzaneen. There are many mosquitoes there this time of year.
Doctor: Do you use a bed net?
Patient: No, mine has holes and I haven't replaced it.
Doctor: Let me check you. Your temperature is 39.8. I'm going to prick your finger for a malaria rapid test. You're looking a bit pale and your spleen feels slightly enlarged. While we wait — any confusion, convulsions, or dark urine?
Patient: No, just the shaking and sweating and tiredness.
Doctor: The rapid test is positive for falciparum malaria. The good news is you don't have any signs of severe malaria. I'm starting you on artemether-lumefantrine — that's four tablets now, four in eight hours, then four tablets twice a day for the next two days. Take them with some food or milk, it helps absorption. Also paracetamol for the fever.
Patient: How soon will I feel better?
Doctor: The fever should break within 48 hours. If you get worse — confusion, continuous vomiting, dark urine — go straight to the hospital.""",
        dictation="""\
36 year old male from malaria-endemic area near Tzaneen. Two day history of cyclical rigors and sweating. Not using bed net. Temperature 39.8, mild pallor, palpable spleen tip. RDT positive for P. falciparum. No features of severe disease — no altered consciousness, no persistent vomiting, no dark urine, no prostration. Uncomplicated falciparum malaria. Artemether-lumefantrine standard six-dose regimen commenced. Paracetamol for fever. Safety-net advice regarding severe malaria warning signs. Follow up day three.""",
        expected_diagnoses=["malaria"],
        expected_medications=["artemether-lumefantrine", "paracetamol"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="Uncomplicated malaria child",
        category="malaria-febrile",
        conversation="""\
Mother: My child has been burning with fever since yesterday. She won't eat and just lies there. I gave her umuthi from the traditional healer but it didn't help.
Doctor: How old is she?
Mother: Five years old.
Doctor: Let me check her temperature... 39.5. She looks uncomfortable but she's alert. No neck stiffness. Let me do a malaria test — we see a lot of malaria in this area. Are you using a mosquito net for her?
Mother: We have one but it fell down last week.
Doctor: The rapid test is positive. She has malaria. Let me check — no jaundice, she's not confused, she can drink. These are good signs. I'm going to give her artemether-lumefantrine tablets. Because she's young, I'll crush them and mix with water. Also paracetamol syrup for the fever.
Mother: The healer said it was abantu medicine. Is malaria different?
Doctor: Malaria is caused by a parasite from mosquito bites. The tablets I'm giving will kill the parasite. Please fix the mosquito net — it's the best protection. She must finish all six doses even when she feels better.
Mother: Thank you doctor. I was very worried.""",
        dictation="""\
Five year old girl, brought by mother. Fever since yesterday, lethargy, poor appetite. Traditional remedy tried without improvement. Temperature 39.5. Alert but unwell. No meningism, no jaundice, no signs of severity. RDT positive for malaria. Uncomplicated falciparum malaria. Weight-based dosing of artemether-lumefantrine, crushed and mixed. Paracetamol syrup for fever. Mother counseled on completing full course and mosquito net use. Review if deterioration.""",
        expected_diagnoses=["malaria"],
        expected_medications=["artemether-lumefantrine", "paracetamol"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="Fever workup negative",
        category="malaria-febrile",
        conversation="""\
Patient: I've had a fever for three days now. It comes and goes. My body aches everywhere and I've had a headache. I thought it might be malaria so I came in.
Doctor: Good that you came. Where do you live?
Patient: Here in town, but I travelled to Mpumalanga two weeks ago.
Doctor: Let me test you. Temperature today is 38.4. I'll do a malaria rapid test and also check your urine. While we wait — any cough, sore throat, rash, or urinary symptoms?
Patient: No, nothing like that. Just the fever and the body pains.
Doctor: The malaria test is negative. Your urine dipstick is also clear. On examination your chest is clear, throat looks normal, abdomen is soft. No obvious source of infection at this point.
Patient: So what do I have?
Doctor: It could be a viral infection that hasn't declared itself yet. I'm going to give you paracetamol for the fever and pain. Come back in 48 hours — if the fever is still there, we'll do blood tests. If you develop any new symptoms before then — cough, neck stiffness, rash — come back sooner.
Patient: Okay, I'll come back on Thursday.""",
        dictation="""\
28 year old male, three day fever with myalgia and headache. Recent travel to malaria area. Temperature 38.4. RDT malaria negative. Urine dipstick normal. Chest clear, throat clear, abdomen soft. No localizing signs of infection identified. Likely viral. Paracetamol 1g TDS for symptomatic relief. Review in 48 hours. If persistent fever, send bloods including FBC and CRP. Safety-net for new symptoms.""",
        expected_diagnoses=["fever"],
        expected_medications=["paracetamol"],
        expected_vitals=["temperature"],
        expected_dangers=[],
    ),

    Encounter(
        name="Typhoid suspect",
        category="malaria-febrile",
        conversation="""\
Patient: Doctor, I've been sick for over a week. The fever won't break. I feel terrible — my whole body aches, I have no appetite, and my stomach has been sore.
Doctor: A week of fever is a long time. Have you had any diarrhea?
Patient: Yes, loose stools for the last four days. And headaches every day.
Doctor: Do you have clean water at home?
Patient: We share a borehole with the neighbors. Sometimes the water looks cloudy.
Doctor: Let me check you. Temperature is 39.0, been high for a while then. Your pulse is relatively slow for the fever — 78, that's unusual. Let me feel your abdomen... your spleen is definitely enlarged and there's tenderness in the right lower area. With a prolonged fever, relative bradycardia, splenomegaly, and questionable water source, I'm thinking of enteric fever — typhoid.
Patient: That sounds serious.
Doctor: It can be if not treated. I'm starting you on ciprofloxacin 500 milligrams twice a day for seven days. You must finish the full course. Drink only boiled water. If you develop severe abdominal pain or bleeding from the rectum, go to hospital immediately.""",
        dictation="""\
30 year old male, eight day history of persistent high fever, headache, anorexia, and four days of diarrhea. Drinks from shared borehole, water quality uncertain. Temperature 39.0. Relative bradycardia — pulse 78. Splenomegaly palpable. Right iliac fossa tenderness. Clinical picture consistent with enteric fever. Ciprofloxacin 500mg BD for seven days. Water and food hygiene counseling. Red flag advice regarding intestinal complications. Ideally would confirm with blood cultures but not available at this facility.""",
        expected_diagnoses=["typhoid", "enteric fever"],
        expected_medications=["ciprofloxacin"],
        expected_vitals=["temperature"],
        expected_dangers=[],
    ),

    Encounter(
        name="Malaria + wrong drug added",
        category="malaria-febrile",
        conversation="""\
Patient: I've been shivering and sweating for three days. It goes in cycles. I work on a farm near Komatipoort where there are lots of mosquitoes.
Doctor: Let me test you right away. Temperature is 39.4. The rapid test is positive for malaria. Let me check for severity — are you confused or seeing things?
Patient: No, just very tired and achy.
Doctor: Good, no severe features. I can see you're a bit jaundiced though — eyes slightly yellow. Your liver and spleen are both palpable. I'm going to start the malaria treatment — artemether-lumefantrine, four tablets now. I'm also going to add atenolol 50 milligrams daily for you.
Patient: What's the atenolol for? I don't have heart problems.
Doctor: It'll help with the symptoms. Just take everything as I prescribe. Come back in three days and if you're getting worse — can't keep food down, more confused, very dark urine — go straight to casualty.
Patient: Okay doctor.""",
        dictation="""\
40 year old male, farm worker from malaria-endemic area near Komatipoort. Three day cyclical rigors and sweats. Temperature 39.4. RDT positive P. falciparum. Mild jaundice, hepatosplenomegaly. No altered consciousness, no prostration, no severe vomiting. Uncomplicated malaria with mild hepatic involvement. Starting artemether-lumefantrine standard course and adding atenolol 50mg daily. Review day three. Danger sign counseling provided.""",
        expected_diagnoses=["malaria"],
        expected_medications=["artemether-lumefantrine", "atenolol"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
            _d("WARNING", "Drug-Condition", "atenolol"),
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    Encounter(
        name="Recurrent malaria — 3rd episode",
        category="malaria-febrile",
        conversation="""\
Patient: It's the malaria again, doctor. This is the third time this year. I know the feeling — the shaking, the sweating, the terrible headache.
Doctor: Third episode? That's concerning. Are you using prevention?
Patient: I sleep under the net most nights but sometimes it's too hot and I don't use it.
Doctor: Let me test you. Temperature is 39.1. The rapid test is positive again. Any vomiting, confusion, or trouble breathing?
Patient: No, just the usual shaking and fever. I know the drill by now.
Doctor: No signs of severe disease which is good. I'm going to give you the artemether-lumefantrine again — same course as before, six doses over three days. Take it with food. We also need to discuss prevention more seriously. You must use the net every single night, even when it's hot. Three episodes in a year is not acceptable.
Patient: I try, doctor. But the mosquitoes are so bad this season.
Doctor: I understand, but malaria can be fatal. Use the net, wear long sleeves in the evening, and use repellent if you can get it. If this keeps happening we may need to look at prophylaxis.""",
        dictation="""\
28 year old female, third episode of malaria this calendar year. Recognizes symptoms — cyclical fever, rigors, headache. Temperature 39.1. RDT positive P. falciparum. No features of severe malaria. Intermittent bed net use — non-adherent on hot nights. Uncomplicated falciparum malaria, recurrent. Artemether-lumefantrine standard course. Extensive prevention counseling — consistent net use, protective clothing, repellent. If further recurrences, consider chemoprophylaxis discussion. Review day three for treatment response.""",
        expected_diagnoses=["malaria"],
        expected_medications=["artemether-lumefantrine"],
        expected_vitals=["temperature"],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# CDSS ENGINE (same as before)
# ═══════════════════════════════════════════════════════════════════════════

class ClinicalData:
    def __init__(self):
        self.allergy_interactions = {}
        self.drug_interactions = []
        self.bodhi_conditions = {}
        self.bodhi_conditions_by_name = {}
        self.bodhi_drugs_by_name = {}
        self.bodhi_labs_by_condition = {}
        self._load()

    def _load(self):
        self.allergy_interactions = self._json("cdss/allergy_interactions.json") or {}
        di = self._json("cdss/drug_interactions.json")
        self.drug_interactions = di.get("interactions", []) if di else []

        for c in (self._json("bodhi/bodhi_conditions.json") or []):
            self.bodhi_conditions[c.get("snomedId", "")] = c
            n = c.get("name", "").lower().strip()
            if n:
                self.bodhi_conditions_by_name[n] = c

        for d in (self._json("bodhi/bodhi_drugs.json") or []):
            n = d.get("name", "").lower().strip()
            if n:
                self.bodhi_drugs_by_name[n] = d

        for lab in (self._json("bodhi/bodhi_labs.json") or []):
            for mc in lab.get("monitoredConditions", []):
                self.bodhi_labs_by_condition.setdefault(mc["snomedId"], []).append(lab)

    def _json(self, path):
        p = ASSETS_DIR / path
        if not p.exists():
            return None
        with open(p) as f:
            return json.load(f)

    def find_condition(self, name):
        if not name or not isinstance(name, str): return None
        low = name.lower().strip()
        if not low: return None
        if low in self.bodhi_conditions_by_name:
            return self.bodhi_conditions_by_name[low]
        return next((c for n, c in self.bodhi_conditions_by_name.items()
                      if low in n or n in low), None)

    def find_drug(self, name):
        if not name or not isinstance(name, str): return None
        return self.bodhi_drugs_by_name.get(name.lower().strip())


@dataclass
class Alert:
    severity: str
    category: str
    message: str


class CDSS:
    GP = {"general practice", "general practitioner", "internal medicine",
          "family medicine", "primary care"}

    def __init__(self, data: ClinicalData):
        self.data = data

    def evaluate(self, extraction: dict, allergies: list[str]) -> tuple[list[Alert], list[Alert]]:
        """Returns (vanilla_alerts, bodhi_alerts)."""
        meds = extraction.get("medications") or []
        vitals = extraction.get("vitals") or []
        diagnoses = extraction.get("diagnoses") or []
        investigations = extraction.get("investigations") or []

        vanilla = []
        vanilla.extend(self._allergy(meds, allergies))
        vanilla.extend(self._drug_drug(meds))
        vanilla.extend(self._vitals(vitals))
        vanilla.extend(self._dosage(meds))

        bodhi = []
        bodhi.extend(self._drug_condition(meds, diagnoses))
        bodhi.extend(self._triage(diagnoses))
        bodhi.extend(self._lab_recs(diagnoses, investigations))
        bodhi.extend(self._referrals(diagnoses))

        return vanilla, bodhi

    def _allergy(self, meds, allergies):
        alerts = []
        for allergy in allergies:
            inter = self.data.allergy_interactions.get(allergy.lower())
            if not inter:
                continue
            contra = [n.lower() for n in inter.get("contraindicatedNames", [])]
            for med in meds:
                mn = ((med.get("name") if isinstance(med, dict) else str(med)) or "").lower()
                if any(c in mn or mn in c for c in contra):
                    alerts.append(Alert("CRITICAL", "Drug-Allergy",
                        inter.get("message", "").replace("{drug}", mn)))
        return alerts

    def _drug_drug(self, meds):
        alerts = []
        names = {((m.get("name") if isinstance(m, dict) else str(m)) or "").lower() for m in meds}
        for i in self.data.drug_interactions:
            d1 = (i.get("drugName1") or "").lower()
            d2 = (i.get("drugName2") or "").lower()
            if d1 and d2:
                m1 = any(d1 in n or n in d1 for n in names)
                m2 = any(d2 in n or n in d2 for n in names)
                if m1 and m2:
                    sev = {"high": "CRITICAL", "medium": "WARNING"}.get(i.get("severity", ""), "INFO")
                    alerts.append(Alert(sev, "Drug-Drug", i.get("message", "")))
        return alerts

    def _vitals(self, vitals):
        """Mirrors production VitalAlerts.kt — CRITICAL and WARNING tiers."""
        alerts = []
        for v in (vitals or []):
            if not isinstance(v, dict): continue
            name = (v.get("name") or "").lower()
            val = str(v.get("value") or "")
            if "blood pressure" in name or name == "bp":
                m = re.search(r"(\d+)\s*/\s*(\d+)", val)
                if m:
                    s, d = int(m.group(1)), int(m.group(2))
                    if s < 70 or s > 200:
                        alerts.append(Alert("CRITICAL", "Vitals", f"Systolic BP {s} mmHg critically abnormal"))
                    elif s < 90 or s > 160:
                        alerts.append(Alert("WARNING", "Vitals", f"Systolic BP {s} mmHg outside normal range"))
                    if d < 40 or d > 120:
                        alerts.append(Alert("CRITICAL", "Vitals", f"Diastolic BP {d} mmHg critically abnormal"))
                    elif d < 50 or d > 100:
                        alerts.append(Alert("WARNING", "Vitals", f"Diastolic BP {d} mmHg outside normal range"))
            elif "oxygen" in name or "spo2" in name:
                try:
                    o = int(re.search(r"\d+", val).group())
                    if o < 90:
                        alerts.append(Alert("CRITICAL", "Vitals", f"SpO2 {o}% critically low"))
                    elif o < 94:
                        alerts.append(Alert("WARNING", "Vitals", f"SpO2 {o}% below normal"))
                except:
                    pass
            elif "temperature" in name or name == "temp":
                try:
                    t = float(re.search(r"[\d.]+", val).group())
                    if t < 35.0 or t > 40.0:
                        alerts.append(Alert("CRITICAL", "Vitals", f"Temperature {t}°C critically abnormal"))
                    elif t < 35.5 or t > 38.5:
                        alerts.append(Alert("WARNING", "Vitals", f"Temperature {t}°C outside normal range"))
                except:
                    pass
            elif "pulse" in name or "heart rate" in name or name == "hr":
                try:
                    p = int(re.search(r"\d+", val).group())
                    if p < 40 or p > 150:
                        alerts.append(Alert("CRITICAL", "Vitals", f"Pulse {p} bpm critically abnormal"))
                    elif p < 50 or p > 120:
                        alerts.append(Alert("WARNING", "Vitals", f"Pulse {p} bpm outside normal range"))
                except:
                    pass
            elif "respiratory" in name or "resp" in name or name == "rr":
                try:
                    r = int(re.search(r"\d+", val).group())
                    if r < 8 or r > 30:
                        alerts.append(Alert("CRITICAL", "Vitals", f"Respiratory rate {r} critically abnormal"))
                    elif r < 12 or r > 20:
                        alerts.append(Alert("WARNING", "Vitals", f"Respiratory rate {r} outside normal range"))
                except:
                    pass
        return alerts

    # Mirrors production DosageChecker.kt
    _MAX_DAILY_DOSES = {
        "amoxicillin": (3000, "mg"), "paracetamol": (4000, "mg"),
        "ibuprofen": (2400, "mg"), "metformin": (2550, "mg"),
        "amlodipine": (10, "mg"), "enalapril": (40, "mg"),
        "hydrochlorothiazide": (50, "mg"), "metoprolol": (400, "mg"),
        "omeprazole": (40, "mg"), "prednisolone": (60, "mg"),
        "prednisone": (60, "mg"), "ciprofloxacin": (1500, "mg"),
        "azithromycin": (500, "mg"), "doxycycline": (200, "mg"),
        "fluconazole": (400, "mg"), "morphine": (200, "mg"),
        "tramadol": (400, "mg"), "diclofenac": (150, "mg"),
    }
    _FREQ_MULT = {
        "OD": 1, "DAILY": 1, "NOCTE": 1, "MANE": 1,
        "BD": 2, "BID": 2, "TDS": 3, "TID": 3, "QDS": 4, "QID": 4,
    }

    def _dosage(self, meds):
        """Mirrors production DosageChecker.kt — max daily dose checks."""
        alerts = []
        for med in meds:
            if not isinstance(med, dict):
                continue
            name = (med.get("name") or "").lower()
            max_info = None
            for drug_key, info in self._MAX_DAILY_DOSES.items():
                if drug_key in name:
                    max_info = info
                    break
            if not max_info:
                continue
            max_val, max_unit = max_info

            # Parse dose (might be "500", "500mg", etc.)
            dose_raw = str(med.get("dose") or "")
            dose_match = re.search(r"(\d+\.?\d*)\s*(mg|g|mcg|ml|iu)?", dose_raw.lower())
            if not dose_match:
                continue
            try:
                dose = float(dose_match.group(1))
            except ValueError:
                continue
            unit = (dose_match.group(2) or "mg").lower()
            # Normalize g → mg
            if unit == "g":
                dose *= 1000
                unit = "mg"
            if unit != max_unit.lower():
                continue

            freq_raw = (med.get("frequency") or "").upper().strip()
            # Skip frequencies we can't convert
            if any(k in freq_raw for k in ("PRN", "STAT", "WEEKLY", "SOS")):
                continue
            # Find matching freq key
            mult = None
            for freq_key, m in self._FREQ_MULT.items():
                if freq_key in freq_raw:
                    mult = m
                    break
            if mult is None:
                mult = 1  # default assume OD

            daily = dose * mult
            name_display = med.get("name", "drug")
            if daily > max_val * 2:
                alerts.append(Alert("CRITICAL", "Dosage",
                    f"{name_display}: daily dose {daily:g}{unit} exceeds safe max ({max_val}{max_unit}/day) by >2x"))
            elif daily > max_val:
                alerts.append(Alert("WARNING", "Dosage",
                    f"{name_display}: daily dose {daily:g}{unit} exceeds recommended max ({max_val}{max_unit}/day)"))
        return alerts

    def _drug_condition(self, meds, diagnoses):
        if not meds or not diagnoses:
            return []
        cond_ids = set()
        for dx in diagnoses:
            dn = dx if isinstance(dx, str) else dx.get("description", dx.get("name", ""))
            c = self.data.find_condition(dn)
            if c:
                cond_ids.add(c["snomedId"])
        if not cond_ids:
            return []
        alerts = []
        for med in meds:
            mn = (med.get("name") if isinstance(med, dict) else str(med))
            drug = self.data.find_drug(mn)
            if not drug:
                continue
            treated = set(drug.get("treatedConditions", []))
            if treated and not treated.intersection(cond_ids):
                alerts.append(Alert("WARNING", "Drug-Condition",
                    f"{mn}: no known indication for current diagnoses"))
        return alerts

    def _triage(self, diagnoses):
        alerts, seen = [], set()
        for dx in diagnoses:
            dn = dx if isinstance(dx, str) else dx.get("description", dx.get("name", ""))
            c = self.data.find_condition(dn)
            if not c or c["snomedId"] in seen:
                continue
            seen.add(c["snomedId"])
            tl = (c.get("triageLevel") or "").lower()
            if tl == "emergency":
                alerts.append(Alert("CRITICAL", "Triage",
                    f"{c['name']} classified as EMERGENCY"))
            elif tl == "worrisome":
                alerts.append(Alert("WARNING", "Triage",
                    f"{c['name']} classified as WORRISOME"))
        return alerts

    def _lab_recs(self, diagnoses, investigations):
        if not diagnoses:
            return []
        existing = set()
        for inv in investigations:
            existing.add(((inv.get("test") if isinstance(inv, dict) else str(inv)) or "").lower())
        alerts, used = [], set()
        for dx in diagnoses:
            dn = dx if isinstance(dx, str) else dx.get("description", dx.get("name", ""))
            c = self.data.find_condition(dn)
            if not c:
                continue
            labs = self.data.bodhi_labs_by_condition.get(c["snomedId"], [])
            new = [l for l in labs if l["loincId"] not in used][:5]
            if new:
                for l in new:
                    used.add(l["loincId"])
                names = ", ".join(l.get("displayName") or l.get("name", "") for l in new)
                alerts.append(Alert("INFO", "Lab Recommendation",
                    f"For {c['name']}: consider {names}"))
        return alerts

    def _referrals(self, diagnoses):
        alerts, used = [], set()
        for dx in diagnoses:
            dn = dx if isinstance(dx, str) else dx.get("description", dx.get("name", ""))
            c = self.data.find_condition(dn)
            if not c:
                continue
            for spec in c.get("specialties", []):
                sn = spec["name"].lower()
                if sn not in self.GP and sn not in used:
                    used.add(sn)
                    alerts.append(Alert("INFO", "Referral Suggestion",
                        f"For {c['name']}: refer to {spec['name']}"))
                    break
        return alerts


# ═══════════════════════════════════════════════════════════════════════════
# EXTRACTION PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def _strip_think(text):
    text = re.sub(r"<think>[\s\S]*?</think>", "", text)
    text = re.sub(r"<unused\d+>(?:thought|reasoning)[\s\S]*?(?=\n\n|\*\*|```|\Z)", "", text, flags=re.IGNORECASE)
    i = text.find("<think>")
    return text[:i].strip() if i >= 0 else text.strip()


def _parse_json(text):
    """Robustly find and parse the largest valid JSON object in the text.
    Handles thinking-token preamble, markdown fences, and trailing code blocks.
    Scans all '{' positions and tries to parse — returns the largest valid object."""
    text = _strip_think(text)
    # Fast path: fenced ```json block
    fenced = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    for candidate in fenced:
        try:
            d = json.loads(candidate)
            if isinstance(d, dict): return d
        except json.JSONDecodeError: pass
    # Slow path: scan every '{' and try to parse at that position (JSONDecoder allows extra trailing data)
    decoder = json.JSONDecoder()
    best = None; best_len = 0
    for i, c in enumerate(text):
        if c != "{": continue
        try:
            obj, end = decoder.raw_decode(text, i)
            if isinstance(obj, dict):
                size = end - i
                if size > best_len:
                    best_len = size; best = obj
        except json.JSONDecodeError: continue
    return best

def call_ollama(model, transcript):
    """Returns (parsed_dict|None, raw_text, elapsed_s)."""
    t0 = time.time()
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": model, "stream": False, "options": EXTRACT_OPTIONS,
            "messages": [
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": EXTRACT_USER.format(schema=EXTRACT_SCHEMA, transcript=transcript)},
                {"role": "assistant", "content": "<think>\n</think>\n"},
            ],
        }, timeout=120)
        r.raise_for_status()
        raw = r.json().get("message", {}).get("content", "")
        return _parse_json(raw), raw, time.time() - t0
    except Exception as e:
        return None, f"[ERROR] {e}", time.time() - t0

def call_anthropic(model, transcript):
    """Returns (parsed_dict|None, raw_text, elapsed_s)."""
    try:
        import anthropic
    except ImportError:
        return None, "[ImportError] anthropic", 0
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None, "[no ANTHROPIC_API_KEY]", 0
    t0 = time.time()
    try:
        r = anthropic.Anthropic(api_key=key).messages.create(
            model=model, max_tokens=4096, system=EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": EXTRACT_USER.format(schema=EXTRACT_SCHEMA, transcript=transcript)}],
        )
        raw = r.content[0].text
        return _parse_json(raw), raw, time.time() - t0
    except Exception as e:
        print(f"    [Anthropic: {str(e)[:60]}]")
        return None, f"[ERROR] {e}", time.time() - t0

def call_openai(model, transcript):
    """Returns (parsed_dict|None, raw_text, elapsed_s)."""
    try:
        import openai
    except ImportError:
        return None, "[ImportError] openai", 0
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None, "[no OPENAI_API_KEY]", 0
    t0 = time.time()
    try:
        kw = {"max_completion_tokens": 4096} if model.startswith(("gpt-5", "o1", "o3", "o4")) else {"max_tokens": 4096}
        r = openai.OpenAI(api_key=key).chat.completions.create(
            model=model, **kw,
            messages=[{"role": "system", "content": EXTRACT_SYSTEM},
                      {"role": "user", "content": EXTRACT_USER.format(schema=EXTRACT_SCHEMA, transcript=transcript)}],
        )
        raw = r.choices[0].message.content
        return _parse_json(raw), raw, time.time() - t0
    except Exception as e:
        print(f"    [OpenAI: {str(e)[:60]}]")
        return None, f"[ERROR] {e}", time.time() - t0

def extract(model, backend, transcript):
    """Returns (parsed_dict|None, raw_text, elapsed_s)."""
    if backend == "ollama": return call_ollama(model, transcript)
    if backend == "anthropic": return call_anthropic(model, transcript)
    if backend == "openai": return call_openai(model, transcript)
    return None, "", 0


# ═══════════════════════════════════════════════════════════════════════════
# ARM 1: LLM-ALONE CLINICAL REVIEWER
# ═══════════════════════════════════════════════════════════════════════════

CLINICAL_REVIEW_SYSTEM = """\
You are a senior clinical safety reviewer. Before outputting JSON, silently check each category and list concerns only where YES:

1. Drug-Allergy: is a prescribed drug contraindicated by a stated allergy?
2. Drug-Drug: are any two prescribed drugs a known dangerous interaction?
3. Drug-Condition: is any prescribed drug NOT indicated for the diagnosis given?
4. Dosage: is any prescribed drug above max safe dose?
5. Vitals: are any vitals outside safe range (BP, temp, pulse, SpO2, RR)?
6. Triage: is this an emergency or time-critical presentation?
7. Lab Rec: is a standard lab missing for the given diagnosis?
8. Referral: does the diagnosis require specialist care beyond primary care?

Output JSON only. Include only real concerns. Empty array if none."""

CLINICAL_REVIEW_SCHEMA = """\
{
  "concerns": [
    {
      "severity": "CRITICAL|WARNING|INFO",
      "category": "Drug-Allergy|Drug-Drug|Drug-Condition|Dosage|Vitals|Triage|Lab Recommendation|Referral Suggestion",
      "concern": "short description; include drug name and/or condition name"
    }
  ]
}"""

CLINICAL_REVIEW_USER = """\
Identify every clinical safety concern in this encounter. Output JSON matching the schema.

Schema:
{schema}

CLINICAL ENCOUNTER:
{transcript}

JSON:"""


def _parse_review(text):
    """Parse clinical review JSON into list[Alert]."""
    if not text:
        return []
    data = _parse_json(text)
    if not data:
        return []
    # Accept either {"concerns": [...]} or bare [...]
    items = data.get("concerns") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    alerts = []
    valid_severities = {"CRITICAL", "WARNING", "INFO"}
    valid_categories = {"Drug-Allergy", "Drug-Drug", "Drug-Condition", "Dosage",
                        "Vitals", "Triage", "Lab Recommendation", "Referral Suggestion"}
    for item in items:
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity", "")).upper().strip()
        cat = str(item.get("category", "")).strip()
        msg = str(item.get("concern") or item.get("message") or "").strip()
        if sev not in valid_severities or cat not in valid_categories:
            continue
        alerts.append(Alert(sev, cat, msg))
    return alerts


def clinical_review(model, backend, transcript):
    """Arm 1: ask the LLM directly for clinical safety concerns.
    Returns (alerts_list, raw_text, elapsed_s)."""
    user_msg = CLINICAL_REVIEW_USER.format(schema=CLINICAL_REVIEW_SCHEMA, transcript=transcript)

    if backend == "ollama":
        t0 = time.time()
        try:
            r = requests.post(f"{OLLAMA_URL}/api/chat", json={
                "model": model, "stream": False, "options": EXTRACT_OPTIONS,
                "messages": [
                    {"role": "system", "content": CLINICAL_REVIEW_SYSTEM},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": "<think>\n</think>\n"},
                ],
            }, timeout=120)
            r.raise_for_status()
            raw = r.json().get("message", {}).get("content", "")
            return _parse_review(raw), raw, time.time() - t0
        except Exception as e:
            return [], f"[ERROR] {e}", time.time() - t0

    elif backend == "anthropic":
        try:
            import anthropic
        except ImportError:
            return [], "[ImportError] anthropic", 0
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return [], "[no ANTHROPIC_API_KEY]", 0
        t0 = time.time()
        try:
            r = anthropic.Anthropic(api_key=key).messages.create(
                model=model, max_tokens=4096, system=CLINICAL_REVIEW_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = r.content[0].text
            return _parse_review(raw), raw, time.time() - t0
        except Exception as e:
            print(f"    [Anthropic review: {str(e)[:60]}]")
            return [], f"[ERROR] {e}", time.time() - t0

    elif backend == "openai":
        try:
            import openai
        except ImportError:
            return [], "[ImportError] openai", 0
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            return [], "[no OPENAI_API_KEY]", 0
        t0 = time.time()
        try:
            kw = {"max_completion_tokens": 4096} if model.startswith(("gpt-5", "o1", "o3", "o4")) else {"max_tokens": 4096}
            r = openai.OpenAI(api_key=key).chat.completions.create(
                model=model, **kw,
                messages=[{"role": "system", "content": CLINICAL_REVIEW_SYSTEM},
                          {"role": "user", "content": user_msg}],
            )
            raw = r.choices[0].message.content
            return _parse_review(raw), raw, time.time() - t0
        except Exception as e:
            print(f"    [OpenAI review: {str(e)[:60]}]")
            return [], f"[ERROR] {e}", time.time() - t0

    return [], "", 0


# ═══════════════════════════════════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════════════════════════════════

def alert_matches(alert: Alert, expected: dict) -> bool:
    if alert.severity != expected["severity"] or alert.category != expected["category"]:
        return False
    sub = expected.get("substring", "")
    return not sub or sub.lower() in alert.message.lower()

def count_caught(alerts: list[Alert], expected: list[dict]) -> int:
    return sum(1 for exp in expected if any(alert_matches(a, exp) for a in alerts))

# Clinical abbreviations/synonym pairs — each line lists equivalent terms.
# Used for semantic-recall scoring so we don't over-penalize models that output
# the standard medical abbreviation instead of the full term (or vice versa).
_DX_SYNONYM_GROUPS = [
    {"hypertension", "htn", "high blood pressure", "elevated blood pressure", "high bp"},
    {"diabetes", "diabetes mellitus", "dm", "type 2 diabetes", "t2dm", "diabetic"},
    {"type 1 diabetes", "dm1", "t1dm", "type 1 dm"},
    {"diabetic ketoacidosis", "dka"},
    {"tuberculosis", "tb", "pulmonary tuberculosis", "ptb"},
    {"myocardial infarction", "mi", "heart attack", "stemi", "nstemi", "acute mi", "acute myocardial infarction"},
    {"urinary tract infection", "uti", "urinary tract", "urethritis"},
    {"chronic obstructive pulmonary disease", "copd"},
    {"chronic kidney disease", "ckd", "kidney failure", "renal failure", "kidney disease", "renal disease"},
    {"acute kidney injury", "aki", "acute renal failure"},
    {"upper respiratory infection", "uri", "upper respiratory tract infection", "urti", "common cold"},
    {"lower respiratory tract infection", "lrti"},
    {"pneumonia", "lobar pneumonia", "bronchopneumonia", "community acquired pneumonia", "cap"},
    {"bronchitis", "acute bronchitis", "chronic bronchitis"},
    {"asthma", "bronchial asthma", "reactive airway disease"},
    {"otitis media", "ear infection", "acute otitis media", "aom", "middle ear infection"},
    {"pharyngitis", "strep throat", "sore throat", "tonsillitis", "strep pharyngitis"},
    {"gastroenteritis", "ge", "stomach flu", "viral gastroenteritis", "acute gastroenteritis"},
    {"sexually transmitted infection", "sti", "std", "sexually transmitted disease"},
    {"human immunodeficiency virus", "hiv", "hiv infection", "hiv positive"},
    {"pre-eclampsia", "preeclampsia", "pre eclampsia", "eclampsia"},
    {"atrial fibrillation", "afib", "af", "a-fib"},
    {"congestive heart failure", "chf", "heart failure", "hf"},
    {"cerebrovascular accident", "cva", "stroke", "ischemic stroke", "hemorrhagic stroke"},
    {"chronic heart disease", "coronary artery disease", "cad", "ihd", "ischemic heart disease"},
    {"anemia", "iron deficiency anemia", "ida"},
    {"malaria", "p. falciparum malaria", "falciparum malaria", "plasmodium falciparum"},
    {"status epilepticus", "prolonged seizure", "generalized seizure"},
    {"meningitis", "bacterial meningitis", "viral meningitis"},
    {"hypothyroidism", "low thyroid", "underactive thyroid"},
    {"hyperthyroidism", "overactive thyroid", "thyrotoxicosis", "graves disease"},
    {"psoriasis", "plaque psoriasis"},
    {"eczema", "atopic dermatitis"},
    {"gout", "gout flare", "gouty arthritis"},
    {"osteoarthritis", "oa", "degenerative joint disease", "wear and tear arthritis"},
    {"rheumatoid arthritis", "ra"},
    {"peptic ulcer disease", "pud", "peptic ulcer"},
    {"gastritis", "acute gastritis", "chronic gastritis"},
    {"gastroesophageal reflux disease", "gerd", "acid reflux"},
    {"migraine", "migraine headache"},
    {"tension headache", "tension-type headache"},
    {"epilepsy", "seizure disorder"},
    {"depression", "major depressive disorder", "mdd"},
    {"anxiety", "generalized anxiety disorder", "gad"},
    {"pregnancy", "gravid", "antenatal", "prenatal"},
    {"wheeze", "wheezing", "bronchospasm", "acute bronchospasm"},
    {"knee injury", "soft tissue injury", "knee sprain", "acute knee injury"},
    {"glaucoma", "acute glaucoma", "angle closure glaucoma", "primary open angle glaucoma"},
    {"contraception", "family planning", "birth control"},
    {"measles", "rubeola"},
    # ── Lay-to-clinical paraphrases (pattern-2 fixes from miss analysis) ──
    {"ear infection", "otitis media", "middle ear infection", "aom", "acute otitis media"},
    {"heart attack", "myocardial infarction", "mi", "stemi", "nstemi", "acute mi", "acute myocardial infarction",
     "anterior stemi", "acute coronary syndrome", "acs"},
    {"pulmonary infection", "lower respiratory tract infection", "lrti", "pneumonia", "chest infection",
     "community acquired pneumonia", "cap", "bacterial pneumonia"},
    {"infection around the brain", "brain infection", "bacterial meningitis", "meningitis",
     "meningococcal meningitis"},
    {"fluid overload", "volume overload", "congestive heart failure", "chf", "heart failure", "hf",
     "decompensated heart failure", "decompensated congestive cardiac failure", "cardiac failure"},
    {"inflammatory skin disease", "plaque psoriasis", "severe plaque psoriasis", "psoriasis"},
    {"high blood sugar", "hyperglycemia", "elevated glucose", "elevated blood sugar"},
    {"low blood sugar", "hypoglycemia", "low glucose"},
    {"kidney injury", "acute kidney injury", "aki", "acute renal failure", "renal injury"},
    {"liver failure", "hepatic failure", "acute hepatic failure", "hepatic insufficiency"},
    {"stomach flu", "gastroenteritis", "viral gastroenteritis", "acute gastroenteritis",
     "acute diarrheal illness", "viral enteritis"},
    {"uri", "upper respiratory tract infection", "urti", "common cold", "viral pharyngitis", "viral uri"},
    {"sore throat", "pharyngitis", "streptococcal pharyngitis", "strep throat", "acute pharyngitis"},
    {"chest pain", "angina", "unstable angina", "stable angina", "anginal pain"},
    {"breathlessness", "shortness of breath", "dyspnea", "dyspnoea", "sob"},
    {"high pressure", "hypertension", "hypertensive emergency", "hypertensive urgency",
     "severe hypertension", "uncontrolled hypertension"},
    {"pregnancy", "gravid", "antenatal", "prenatal", "gestation"},
    {"irregular heartbeat", "atrial fibrillation", "afib", "af", "a-fib", "arrhythmia"},
    {"seizure", "status epilepticus", "convulsion", "fit", "epileptic seizure", "generalized seizure",
     "tonic-clonic seizure", "grand mal seizure", "prolonged seizure"},
    {"blood in stool", "rectal bleeding", "melena", "hematochezia", "lower gi bleed"},
    {"anaemia", "anemia", "iron deficiency anaemia", "iron deficiency anemia", "ida"},
    {"severe toxemia of pregnancy", "severe pre-eclampsia", "pre-eclampsia", "preeclampsia",
     "eclampsia", "hypertensive disorder of pregnancy"},
    {"tb", "tuberculosis", "pulmonary tuberculosis", "ptb", "pulmonary tb",
     "smear positive tb", "active tb"},
    {"aids", "advanced hiv", "advanced hiv disease", "hiv", "hiv infection", "hiv positive"},
    {"candidiasis", "thrush", "oral thrush", "oral candidiasis", "vaginal candidiasis"},
    {"utis", "urinary tract infection", "uti", "cystitis", "acute cystitis"},
    {"diabetes", "diabetes mellitus", "dm", "type 2 diabetes", "t2dm", "type 2 dm",
     "diabetic", "non-insulin dependent diabetes", "niddm"},
]

# ── Medication brand\u2194generic equivalence ─────────────────────────
_MED_SYNONYM_GROUPS = [
    {"paracetamol", "acetaminophen", "panadol", "tylenol", "calpol"},
    {"adrenaline", "epinephrine"},
    {"noradrenaline", "norepinephrine"},
    {"salbutamol", "albuterol", "ventolin"},
    {"frusemide", "furosemide", "lasix"},
    {"ibuprofen", "brufen", "advil", "nurofen", "motrin"},
    {"aspirin", "asa", "acetylsalicylic acid", "disprin"},
    {"diclofenac", "voltaren", "voltarol"},
    {"amoxicillin", "amoxycillin", "amoxil"},
    {"co-amoxiclav", "co amoxiclav", "amoxiclav", "augmentin"},
    {"co-trimoxazole", "cotrimoxazole", "trimethoprim-sulfamethoxazole", "bactrim", "septrin", "tmp-smx"},
    {"metformin", "glucophage", "glucophage xr"},
    {"enalapril", "vasotec", "renitec"},
    {"captopril", "capoten"},
    {"atenolol", "tenormin"},
    {"amlodipine", "norvasc"},
    {"hydrochlorothiazide", "hctz", "microzide"},
    {"warfarin", "coumadin"},
    {"simvastatin", "zocor"},
    {"atorvastatin", "lipitor"},
    {"omeprazole", "losec", "prilosec"},
    {"ceftriaxone", "rocephin"},
    {"diazepam", "valium"},
    {"lorazepam", "ativan"},
    {"phenytoin", "dilantin", "epanutin"},
    {"phenobarbital", "phenobarbitone", "luminal"},
    {"insulin", "humulin", "actrapid", "mixtard", "insulatard"},
    {"magnesium sulfate", "magnesium sulphate", "mgso4"},
    {"prednisone", "prednisolone"},
    {"isoniazid", "inh"},
    {"rifampicin", "rifampin", "rmp"},
    {"rhze", "rifampicin isoniazid pyrazinamide ethambutol"},
    {"artemether-lumefantrine", "al", "coartem"},
    {"artesunate", "artesunic acid"},
    {"benzathine penicillin", "benzathine", "pencillin g"},
    {"azithromycin", "zithromax"},
    {"doxycycline", "vibramycin"},
    {"ciprofloxacin", "cipro"},
    {"nitrofurantoin", "macrobid", "furadantin"},
    {"oral rehydration solution", "ors", "oral rehydration salts", "rehydration solution"},
    {"tdf/3tc/dtg", "tenofovir-lamivudine-dolutegravir", "tld", "tenofovir/lamivudine/dolutegravir"},
]

# Build a flat lookup: every term → a canonical set-id (integer)
_SYN_INDEX = {}
for _i, _grp in enumerate(_DX_SYNONYM_GROUPS):
    for _t in _grp:
        _SYN_INDEX[_t.lower().strip()] = _i


def _synonym_groups_in(text: str) -> set:
    """Return the set of synonym-group IDs for every synonym term that appears
    as a whole-token match inside `text`. Whole-token avoids false positives like
    matching 'mi' inside 'milk'. Short terms (<=3 chars) require word-boundary.
    """
    out = set()
    tl = text.lower().strip()
    if not tl: return out
    # pad with spaces + strip punctuation for word-boundary check
    padded = " " + re.sub(r"[^a-z0-9 ]+", " ", tl) + " "
    for term, grp in _SYN_INDEX.items():
        tl_term = term.lower().strip()
        # multi-word or long-word synonyms: simple substring suffices
        if " " in tl_term or len(tl_term) > 3:
            if tl_term in tl: out.add(grp)
        else:
            # short abbreviations (MI, TB, HIV, UTI, etc.) \u2014 require word boundary
            if f" {tl_term} " in padded: out.add(grp)
    return out


def _dx_equivalent(a: str, b: str, bodhi_data=None) -> bool:
    """Two diagnoses are equivalent if:
    (1) substring match,
    (2) both contain synonym terms from the same group (e.g. 'Severe COPD exacerbation'
        vs 'severe exacerbation of chronic obstructive pulmonary disease'),
    (3) both resolve to the same BODHI SNOMED condition (when bodhi_data provided).
    Antonym guard: hyper-/hypo- pairs are forced non-equivalent."""
    a_lower = (a or "").lower().strip()
    b_lower = (b or "").lower().strip()
    if not a_lower or not b_lower: return False
    if _are_antonyms(a_lower, b_lower): return False
    if a_lower in b_lower or b_lower in a_lower: return True
    # Any shared synonym group between the two strings
    ga = _synonym_groups_in(a_lower)
    gb = _synonym_groups_in(b_lower)
    if ga & gb: return True
    # BODHI equivalence
    if bodhi_data:
        ca = bodhi_data.find_condition(a_lower)
        cb = bodhi_data.find_condition(b_lower)
        if ca and cb and ca.get("snomedId") == cb.get("snomedId"): return True
    return False


def dx_is_explicit_in_transcript(enc: Encounter, transcript_text: str | None = None) -> bool:
    """True if any expected diagnosis appears verbatim (case-insensitive) in at least one transcript form.
    Used to split dx extraction performance by 'spoken' vs 'requires clinical inference'."""
    tconv = (enc.conversation or "").lower()
    tdict = (enc.dictation or "").lower()
    blob = (tconv + " " + tdict) if transcript_text is None else transcript_text.lower()
    return any(dx.lower() in blob for dx in (enc.expected_diagnoses or []))


# Known vaccine codes for the structural-error check (vaccines in medications is a hard fail)
_VACCINE_TERMS = {
    "bcg", "dtp", "opv", "ipv", "pentavalent", "penta", "pcv", "hpv",
    "measles", "rubeola", "mmr", "hepatitis b", "hep b", "rotavirus",
    "td", "tdap", "tetanus", "dtap", "yellow fever", "influenza flu shot",
    "covid", "varicella", "meningococcal",
}


def _fact_in_transcript(fact_str, transcript_text: str) -> bool:
    """Is the extracted fact actually in the transcript? Checks substring + synonym table.
    Tolerates non-string fact values by coercing to str."""
    if not fact_str or not transcript_text: return False
    if not isinstance(fact_str, str):
        try: fact_str = str(fact_str)
        except Exception: return False
    fl = fact_str.lower().strip()
    tl = transcript_text.lower()
    if fl in tl: return True
    grp_id = _SYN_INDEX.get(fl)
    if grp_id is not None:
        for term, gid in _SYN_INDEX.items():
            if gid == grp_id and term in tl: return True
    return False


def _is_vaccine(name) -> bool:
    if not name: return False
    if not isinstance(name, str):
        try: name = str(name)
        except Exception: return False
    nl = name.lower().strip()
    return any(v in nl for v in _VACCINE_TERMS)


# ═══════════════════════════════════════════════════════════════════════════
# SILVER GT LOADER
# ═══════════════════════════════════════════════════════════════════════════

_SILVER_GT_PATH = os.path.join(os.path.dirname(__file__), "silver_gt.json")
_silver_gt_by_name: dict | None = None


def _silver_gt_for(enc) -> dict | None:
    """Return silver GT dict for an encounter (matched by name), or None.
    Silver GT is generated once by scripts/generate_silver_gt.py."""
    global _silver_gt_by_name
    if _silver_gt_by_name is None:
        if not os.path.exists(_SILVER_GT_PATH):
            _silver_gt_by_name = {}
        else:
            try:
                recs = json.loads(open(_SILVER_GT_PATH).read())
                _silver_gt_by_name = {r["name"]: (r.get("silver_gt") or {}) for r in recs}
            except Exception:
                _silver_gt_by_name = {}
    return _silver_gt_by_name.get(enc.name)


# ═══════════════════════════════════════════════════════════════════════════
# SCORING (SequenceMatcher ≥ 0.5 — matches the 50-case × 5-run benchmark
# methodology described in Benchmark_0.8B_Narrative.pptx and implemented in
# /Users/haohu/Documents/GitHub/benchmark/evaluation/extraction_evaluator.py)
# ═══════════════════════════════════════════════════════════════════════════

_SM_THRESHOLD = 0.5
_NEAR_MISS_LO = 0.3  # near-miss band [0.3, 0.5)


def _sm_norm(text) -> str:
    return re.sub(r"\s+", " ", str(text).lower().strip())


def _sm_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _sm_fuzzy(a: str, b: str, threshold: float = _SM_THRESHOLD) -> bool:
    return _sm_ratio(_sm_norm(a), _sm_norm(b)) >= threshold


def _fact_blob(item) -> str:
    """Flatten any extracted/GT item (string, dict, or list fragment) to one normalized string."""
    if item is None: return ""
    if isinstance(item, str): return _sm_norm(item)
    if isinstance(item, dict):
        # Prefer the `primary` form for silver-GT shape; fall back to all values
        if "primary" in item:
            return _sm_norm(str(item.get("primary") or ""))
        return _sm_norm(" ".join(str(v) for v in item.values() if v is not None))
    return _sm_norm(str(item))


def _accept_forms(gt_item) -> list:
    """Return all acceptable strings for a GT item: primary + accepts list + key fields.
    Handles the inclusive silver-GT shape {primary, accepts: [\u2026], context, status, \u2026}."""
    if gt_item is None: return [""]
    if isinstance(gt_item, str): return [gt_item]
    if isinstance(gt_item, dict):
        forms = []
        # Inclusive silver-GT shape
        if "primary" in gt_item:
            forms.append(str(gt_item["primary"]))
            accepts = gt_item.get("accepts") or []
            if isinstance(accepts, list):
                forms.extend(str(a) for a in accepts if a)
            return [f for f in forms if f]
        # Legacy dict shape (name/value/dose etc.)
        if "name" in gt_item and "value" in gt_item:
            forms.append(f"{gt_item.get('name','')} {gt_item.get('value','')}".strip())
        if "test" in gt_item:
            r = gt_item.get("result", "")
            forms.append(f"{gt_item.get('test','')} {r}".strip())
        if "name" in gt_item: forms.append(str(gt_item["name"]))
        if "vaccine" in gt_item: forms.append(str(gt_item["vaccine"]))
        if not forms:
            forms = [" ".join(str(v) for v in gt_item.values() if v is not None)]
        return [f for f in forms if f]
    return [str(gt_item)]


_VITAL_ALIASES = {
    "blood pressure": ("bp", "systolic", "diastolic"),
    "temperature": ("temp",),
    "heart rate": ("hr", "pulse"),
    "respiratory rate": ("rr", "resp", "respiration"),
    "oxygen": ("spo2", "o2", "sat", "oxygen saturation"),
    "weight": ("wt",),
}


def _match_vital(extracted, gt, dx_synonym=False) -> bool:
    """Vital match: name alias + STRICT numeric compatibility. If GT has numbers,
    the extracted side must contain each of them (no fuzzy on numbers)."""
    e = _fact_blob(extracted)
    if not e: return False
    for g_form in _accept_forms(gt):
        g = _sm_norm(g_form)
        if not g: continue
        # Numeric check: if GT has numbers, extracted side must have every one of them (exact)
        if not _numbers_compatible(e, g, tol=0.0):
            continue
        # Exact number overlap
        e_nums = set(re.findall(r"[\d.]+", e))
        g_nums = set(re.findall(r"[\d.]+", g))
        if g_nums and e_nums and g_nums.issubset(e_nums):
            return True
        # Name-only aliases (when no numbers on GT side)
        for canon, aliases in _VITAL_ALIASES.items():
            if canon in g and (canon in e or any(a in e.split() or f" {a} " in f" {e} " for a in aliases)):
                return True
        # Fuzzy allowed only if numbers already passed the compatibility gate
        if _sm_fuzzy(e, g, _SM_THRESHOLD): return True
    return False


def _match_medication(extracted, gt) -> bool:
    """Medication match: name check + NUMERIC compatibility on dose.
    `amoxicillin 5 mg` and `amoxicillin 50 mg` share 50% of characters but are
    clinically very different, so dose numbers must match exactly when present."""
    gt_forms = _accept_forms(gt)
    if isinstance(extracted, dict):
        e_name = _sm_norm(extracted.get("name") or extracted.get("primary") or "")
        e_dose = _sm_norm(extracted.get("dose") or "")
        e_full = _sm_norm(" ".join(str(v) for v in extracted.values() if v is not None))
    else:
        e_name = _sm_norm(str(extracted))
        e_dose = ""
        e_full = e_name
    if not e_full or not gt_forms: return False
    for g in gt_forms:
        gn = _sm_norm(g)
        if not gn: continue
        # Dangerous distinction guard (brand combo vs mono, etc.)
        if _are_antonyms(e_name, gn): continue
        # Numeric compatibility on dose: if GT has numbers, e_full must contain them.
        if not _numbers_compatible(e_full, gn, tol=0.0):
            continue
        # Name-level equivalence
        g_head = gn.split()[0] if gn else ""
        e_head = e_name.split()[0] if e_name else e_full.split()[0]
        if g_head and e_head and (g_head in e_full or e_head in gn):
            return True
        if _med_equivalent(e_head or e_name, g_head or gn): return True
        # Fuzzy \u2014 ONLY on non-numeric portion of the name
        e_clean = re.sub(r"[\d.,]+\s*(?:mg|g|mcg|ml|iu|units?|tds|bd|bid|tid|qd|od)?", "", e_full).strip()
        g_clean = re.sub(r"[\d.,]+\s*(?:mg|g|mcg|ml|iu|units?|tds|bd|bid|tid|qd|od)?", "", gn).strip()
        if e_clean and g_clean and _sm_fuzzy(e_clean, g_clean, _SM_THRESHOLD):
            return True
    return False


# Pre-index medication synonym groups after dx ones are defined above.
_MED_SYN_INDEX = {}
for _i, _grp in enumerate(_MED_SYNONYM_GROUPS):
    for _t in _grp:
        _MED_SYN_INDEX[_t.lower().strip()] = _i


def _med_equivalent(a: str, b: str) -> bool:
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b: return False
    # Extract just the drug name root (first token)
    ra, rb = a.split()[0] if a else "", b.split()[0] if b else ""
    ga = _MED_SYN_INDEX.get(ra) or _MED_SYN_INDEX.get(a)
    gb = _MED_SYN_INDEX.get(rb) or _MED_SYN_INDEX.get(b)
    if ga is not None and gb is not None and ga == gb:
        return True
    # Substring of any synonym term within the extracted string
    for term, grp in _MED_SYN_INDEX.items():
        if term in a and _MED_SYN_INDEX.get(rb) == grp: return True
        if term in b and _MED_SYN_INDEX.get(ra) == grp: return True
    return False


def _match_investigation(extracted, gt) -> bool:
    # Extracted as (test, result) pair
    if isinstance(extracted, dict):
        e_test = _sm_norm(extracted.get("test", ""))
        e_result = _sm_norm(extracted.get("result", ""))
    else:
        e_test = _sm_norm(str(extracted)); e_result = e_test
    e_combined = f"{e_test} {e_result}"

    # New silver-GT shape: {primary, accepts[]} \u2014 iterate all accept forms
    for g_form in _accept_forms(gt):
        g = _sm_norm(g_form)
        if not g: continue
        # test-name overlap
        if _sm_fuzzy(e_test, g, _SM_THRESHOLD) or _sm_fuzzy(e_combined, g, _SM_THRESHOLD):
            g_nums = re.findall(r"[\d.]+", g)
            if g_nums:
                if any(n in e_combined for n in g_nums): return True
            else:
                return True
        # substring of whole form in extracted combined
        if g in e_combined or e_combined in g: return True
    # Legacy shape fallback
    if isinstance(gt, dict) and "test" in gt:
        g_test = _sm_norm(gt.get("test", "")); g_result = _sm_norm(gt.get("result", ""))
        if g_test and _sm_fuzzy(e_test, g_test, _SM_THRESHOLD):
            g_nums = re.findall(r"[\d.]+", g_result)
            if g_nums:
                return any(n in e_combined for n in g_nums)
            return _sm_fuzzy(e_result, g_result, _SM_THRESHOLD)
    return False


_ANTONYM_PREFIXES = [("hyper", "hypo")]

# ── Dangerous-distinction guards ──────────────────────────────
# These are strings that look fuzzy-similar to their counterparts but mean
# clinically-different things. Mis-crediting any of these is a safety concern.
#
# Each entry is a pair of regex fragments. If one string matches the "qualified"
# form and the other matches the "bare" form, we force non-match. The intent
# is to catch cases like:
#   "history of TB"       vs  "active TB"
#   "rule out MI"         vs  "confirmed MI"
#   "mother had stroke"   vs  "patient had stroke"
#   "no penicillin allergy" vs "penicillin allergy"
_QUALIFIER_PATTERNS = [
    # Negation: rejected by the scorer when one side has negation and the other doesn't.
    (re.compile(r"\b(no|not|denies|without|negative\s+for|nkda|no\s+known)\b"), "negated"),
    # Temporality: history/past vs active/current
    (re.compile(r"\b(history|hx|past|prior|previous|resolved|remote)\b"), "past"),
    (re.compile(r"\b(active|acute|current|ongoing|new)\b"), "active"),
    # Uncertainty: suspected / rule-out / possible
    (re.compile(r"\b(rule\s+out|r\/o|suspected|possible|query|consider|consistent\s+with|likely|probable|differential)\b"), "suspected"),
    # Experiencer: family/mother/father vs patient
    (re.compile(r"\b(mother|father|family|sister|brother|parent|relative|spouse|wife|husband|child|son|daughter)\b"), "family"),
]


def _qualifier_tags(text: str) -> set[str]:
    """Return the set of qualifier tags present in `text` (e.g. {negated, past})."""
    t = (text or "").lower()
    return {tag for pat, tag in _QUALIFIER_PATTERNS if pat.search(t)}


def _dangerous_distinction(a: str, b: str) -> bool:
    """If `a` and `b` have different qualifier tags (e.g. one is negated / past /
    suspected / family-history and the other isn't), force a non-match. This
    catches clinically critical distinctions that fuzzy matching blows past."""
    ta, tb = _qualifier_tags(a), _qualifier_tags(b)
    # negation mismatch is always dangerous
    if ("negated" in ta) != ("negated" in tb): return True
    # past vs active is dangerous
    if ("past" in ta) != ("past" in tb) and ("active" in ta or "active" in tb): return True
    # suspected vs confirmed (confirmed = no suspected tag) is dangerous when
    # one side has suspicion language and the other doesn't
    if ("suspected" in ta) != ("suspected" in tb): return True
    # experiencer: family vs patient
    if ("family" in ta) != ("family" in tb): return True
    return False


# ── Brand-combination guards ──────────────────────────────────
# Combination drugs are NOT equivalent to their mono-ingredient versions.
_COMBO_GUARD = {
    "augmentin": "amoxicillin-clavulanate",
    "amoxiclav": "amoxicillin-clavulanate",
    "co-amoxiclav": "amoxicillin-clavulanate",
    "tmp-smx": "co-trimoxazole",
    "bactrim": "co-trimoxazole",
    "septrin": "co-trimoxazole",
    "al": "artemether-lumefantrine",
    "coartem": "artemether-lumefantrine",
}
_MONO_INGREDIENTS = {"amoxicillin", "clavulanate", "trimethoprim", "sulfamethoxazole",
                      "artemether", "lumefantrine"}


def _is_combo_vs_mono(a: str, b: str) -> bool:
    """Flag brand-combination vs single-ingredient mismatches (e.g. Augmentin vs
    amoxicillin). Extracts the first clinical token from each side and checks if
    one is a combo product while the other is a bare ingredient of it."""
    al, bl = (a or "").lower().strip(), (b or "").lower().strip()
    if not al or not bl: return False
    # is `al` a combo brand?
    for brand, combo in _COMBO_GUARD.items():
        if brand in al.split() or brand == al.split()[0] if al else False:
            # `bl` is a mono ingredient of the same combo?
            bl_head = bl.split()[0] if bl else ""
            if bl_head in _MONO_INGREDIENTS and bl_head in combo:
                return True
    for brand, combo in _COMBO_GUARD.items():
        if brand in bl.split() or brand == bl.split()[0] if bl else False:
            al_head = al.split()[0] if al else ""
            if al_head in _MONO_INGREDIENTS and al_head in combo:
                return True
    return False


def _are_antonyms(a: str, b: str) -> bool:
    """Guard against fuzzy false positives like hyper-/hypotension \u2014 the strings
    share ~87% of characters but mean opposite conditions.
    Also folds in: dangerous qualifier mismatches (negation/temporality/etc.)
    and brand-combination vs mono-ingredient mismatches."""
    a, b = a.lower().strip(), b.lower().strip()
    for pa, pb in _ANTONYM_PREFIXES:
        if a.startswith(pa) and b.startswith(pb) and a[len(pa):] == b[len(pb):]:
            return True
        if a.startswith(pb) and b.startswith(pa) and a[len(pb):] == b[len(pa):]:
            return True
    if _dangerous_distinction(a, b): return True
    if _is_combo_vs_mono(a, b): return True
    return False


# ── Numeric equality helpers (dose, vitals) ────────────────────
# Fuzzy matching on numeric strings is dangerous (`5 mg` vs `50 mg` share 50%
# of characters). These helpers pull numbers out and compare them with tolerance.
_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _extract_numbers(s) -> list:
    if s is None: return []
    if isinstance(s, dict):
        s = " ".join(str(v) for v in s.values() if v is not None)
    return [float(m) for m in _NUM_RE.findall(str(s))]


def _numbers_compatible(a, b, tol: float = 0.0) -> bool:
    """True if both sides contain numbers AND those numbers differ by at most
    `tol` (relative). Default tol=0.0 means exact equality."""
    na, nb = _extract_numbers(a), _extract_numbers(b)
    if not na or not nb: return True     # at least one side has no numbers \u2192 skip numeric check
    # Every GT number must have a matching extracted number within tolerance.
    for g in nb:
        if not any(abs(e - g) <= max(tol * abs(g), 1e-9) for e in na):
            return False
    return True


def _match_diagnosis(extracted, gt, bodhi_data=None) -> bool:
    """Diagnosis match: check extracted against EVERY accept form of the GT item.
    Cascade: antonym-guard \u2192 substring \u2192 synonym/BODHI \u2192 fuzzy \u22650.5."""
    e = _fact_blob(extracted)
    if not e: return False
    for g_form in _accept_forms(gt):
        g = _sm_norm(g_form)
        if not g: continue
        if _are_antonyms(e, g): continue   # skip this form, try the next
        if g in e or e in g: return True
        if _dx_equivalent(e, g, bodhi_data=bodhi_data): return True
        if _sm_fuzzy(e, g, _SM_THRESHOLD): return True
    return False


def _match_string(extracted, gt) -> bool:
    """Generic match (exam_findings, allergies, plan, immunizations): check against
    every accept form, substring \u2192 fuzzy \u22650.5 cascade."""
    e = _fact_blob(extracted)
    if not e: return False
    for g_form in _accept_forms(gt):
        g = _sm_norm(g_form)
        if not g: continue
        if g in e or e in g: return True
        if _sm_fuzzy(e, g, _SM_THRESHOLD): return True
    return False


def _decompose_category(extracted, gt_items, match_fn,
                        all_gt_by_category=None, category_name=None,
                        match_fns_by_cat=None) -> dict:
    """Greedy one-to-one match; decompose unmatched extractions into
    {duplication, near_miss, miscategorization, fabrication}. Returns per-field
    P/R/F1 + counts + error breakdown. Matches the scheme in
    /Users/haohu/Documents/GitHub/benchmark/evaluation/extraction_evaluator.py.
    """
    extracted = extracted or []
    gt_items = gt_items or []
    # No GT curated for this field \u2192 don't score precision/recall; just count extractions.
    # This applies to exam_findings/investigations/plan/immunizations in our current dataset.
    if not gt_items:
        return {"precision": None, "recall": None, "f1": None,
                "matched": 0, "missed": 0, "hallucinated": len(extracted),
                "total_gt": 0, "total_extracted": len(extracted),
                "no_gt": True,
                "errors": {"fabrication": 0, "miscategorization": 0, "duplication": 0, "near_miss": 0}}

    # ── Pass 1: greedy one-to-one matching for RECALL ──
    # Each GT item is credited at most once. Extractions that claim a GT slot
    # are `paired_ext`. This is what `matched_gt` reflects.
    matched_gt = set(); paired_ext = set()
    for i, ext in enumerate(extracted):
        for j, gt in enumerate(gt_items):
            if j in matched_gt: continue
            if match_fn(ext, gt):
                matched_gt.add(j); paired_ext.add(i); break

    # ── Pass 2: extraction-level correctness for PRECISION ──
    # An extraction is correct if it matches ANY GT item (even one already taken)
    # or matches any GT item's accept-form. This is the right "did the model
    # say something clinically valid" signal \u2014 the inclusive silver-GT design
    # should not penalize a model for saying the same correct concept more
    # than once or saying two correct concepts that happen to overlap in accepts.
    correct_ext = set(paired_ext)
    for i, ext in enumerate(extracted):
        if i in correct_ext: continue
        for gt in gt_items:
            if match_fn(ext, gt):
                correct_ext.add(i); break

    n_matched = len(matched_gt)           # unique GT credited
    n_correct = len(correct_ext)          # extractions that are clinically valid
    n_missed = len(gt_items) - n_matched
    n_hallucinated = len(extracted) - n_correct

    # Redundant-but-correct: correct extractions that didn't pair with a unique
    # GT slot (they matched a GT item already taken). Reported for transparency
    # but NOT counted as an error \u2014 precision includes them.
    n_redundant = len(correct_ext) - len(paired_ext)

    # ── Pass 3: classify only the truly-unmatched extractions ──
    n_fab = n_misc = n_near = 0
    for i, ext in enumerate(extracted):
        if i in correct_ext: continue      # skip correct (and redundant-correct)
        classified = False
        # near-miss \u2014 fuzzy ratio 0.3..0.5 against any GT form in this category
        ext_str = _fact_blob(ext)
        for gt in gt_items:
            for g_form in _accept_forms(gt):
                if _NEAR_MISS_LO <= _sm_ratio(ext_str, _sm_norm(g_form)) < _SM_THRESHOLD:
                    n_near += 1; classified = True; break
            if classified: break
        if classified: continue
        # miscategorization \u2014 matches GT in a DIFFERENT field
        if all_gt_by_category and category_name and match_fns_by_cat:
            for other_cat, other_gt in all_gt_by_category.items():
                if other_cat == category_name: continue
                other_fn = match_fns_by_cat.get(other_cat, _match_string)
                if any(other_fn(ext, gt) for gt in other_gt):
                    n_misc += 1; classified = True; break
        if classified: continue
        # fabrication \u2014 no match anywhere in GT
        n_fab += 1

    # ── Precision: two definitions reported side-by-side ──
    # precision_strict: UNIQUE GT items credited / total extractions
    #   (penalizes shotgun aliasing \u2014 "paracetamol/APAP/Tylenol" counts as ONE)
    # precision_loose: ALL clinically-valid extractions / total extractions
    #   (charitable; what the previous version reported)
    # We report strict as the primary precision metric.
    prec_strict = n_matched / len(extracted) if extracted else 1.0
    prec_loose = n_correct / len(extracted) if extracted else 1.0
    rec = n_matched / len(gt_items) if gt_items else 1.0
    f1_strict = (2 * prec_strict * rec / (prec_strict + rec)) if (prec_strict + rec) else 0.0
    return {
        "precision": round(prec_strict, 3),          # strict, primary
        "precision_loose": round(prec_loose, 3),     # includes redundant-correct
        "recall": round(rec, 3),
        "f1": round(f1_strict, 3),
        "matched": n_matched,
        "missed": n_missed,
        "hallucinated": n_hallucinated,
        "total_gt": len(gt_items),
        "total_extracted": len(extracted),
        "n_redundant": n_redundant,
        "duplication_rate": round(n_redundant / len(extracted), 3) if extracted else 0.0,
        "errors": {
            "fabrication": n_fab,
            "miscategorization": n_misc,
            "duplication": n_redundant,    # back-compat key
            "near_miss": n_near,
        },
    }


def extraction_quality(ext: dict, enc: Encounter) -> dict:
    """Per-field P/R/F1 + 4-bucket error decomposition, matching the methodology
    of the earlier 50-case × 5-run benchmark (SequenceMatcher ≥ 0.5).

    Also carries a `dx_recall_semantic` pass that grants credit via the
    synonym table + BODHI equivalence (more lenient than the strict fuzzy match),
    so TB ↔ tuberculosis etc. aren't over-penalized.
    """
    if not ext:
        empty_field = {"precision": 0, "recall": 0, "f1": 0, "matched": 0, "missed": 0,
                       "hallucinated": 0, "total_gt": 0, "total_extracted": 0,
                       "errors": {"fabrication": 0, "miscategorization": 0, "duplication": 0, "near_miss": 0}}
        return {
            "dx_recall": 0, "dx_precision": 0, "dx_f1": 0,
            "dx_recall_semantic": 0, "dx_f1_semantic": 0,
            "meds_recall": 0, "meds_precision": 0, "meds_f1": 0,
            "vitals_recall": 0, "allergies_recall": 0,
            "dx_extracted": 0, "meds_extracted": 0, "investigations_extracted": 0,
            "chief_complaint_set": False, "plan_populated": False, "sms_summary_ok": False,
            "dx_explicit_in_transcript": False,
            "per_field": {k: empty_field for k in ("diagnoses", "medications", "vitals",
                                                   "allergies", "exam_findings", "investigations",
                                                   "plan", "immunizations")},
            "overall_precision": 0, "overall_recall": 0, "overall_f1": 0,
            "structural_errors": [], "has_vaccine_in_meds": False,
        }

    # ── Collect extracted lists (normalize defaults) ──
    dx_list = ext.get("diagnoses") or []
    meds_list = ext.get("medications") or []
    vitals_ext = ext.get("vitals") or []
    allerg_list = ext.get("allergies") or []
    invs_list = ext.get("investigations") or []
    plan_list = ext.get("plan") or []
    exam_list = ext.get("exam_findings") or []
    immz_list = ext.get("immunizations") or []

    # ── GT lookup: silver (Opus-generated, 7 fields) overrides curator (4 fields) ──
    silver = _silver_gt_for(enc)
    def _use(silver_key, curator_val):
        v = silver.get(silver_key) if silver else None
        return list(v) if v else (list(curator_val or []))
    gt_dx     = _use("diagnoses",     enc.expected_diagnoses)
    gt_meds   = _use("medications",   enc.expected_medications)
    gt_vitals = _use("vitals",        enc.expected_vitals)
    gt_allerg = _use("allergies",     enc.patient_allergies)
    gt_exam   = list(silver.get("exam_findings") or []) if silver else []
    gt_invs   = list(silver.get("investigations") or []) if silver else []
    gt_plan   = list(silver.get("plan") or []) if silver else []
    gt_immz   = list(silver.get("immunizations") or []) if silver else []

    # ── Strict P/R/F1 with 4-bucket decomposition ──
    match_fns_by_cat = {
        "diagnoses": _match_diagnosis,
        "medications": _match_medication,
        "vitals": _match_vital,
        "allergies": _match_string,
        "exam_findings": _match_string,
        "investigations": _match_investigation,
        "plan": _match_string,
        "immunizations": _match_string,
    }
    all_gt_by_category = {
        "diagnoses": gt_dx, "medications": gt_meds, "vitals": gt_vitals,
        "allergies": gt_allerg, "exam_findings": gt_exam,
        "investigations": gt_invs, "plan": gt_plan, "immunizations": gt_immz,
    }

    per_field = {}
    for cat, fn in match_fns_by_cat.items():
        ext_items = {
            "diagnoses": dx_list, "medications": meds_list, "vitals": vitals_ext,
            "allergies": allerg_list, "exam_findings": exam_list,
            "investigations": invs_list, "plan": plan_list, "immunizations": immz_list,
        }[cat]
        per_field[cat] = _decompose_category(
            ext_items, all_gt_by_category[cat], fn,
            all_gt_by_category=all_gt_by_category, category_name=cat,
            match_fns_by_cat=match_fns_by_cat,
        )

    # ── Semantic dx recall (synonym/BODHI) — strictly more lenient than fuzzy ──
    # Chief complaint is searched too, since small models often put the dx there.
    cc_val = ext.get("chief_complaint")
    chief = cc_val if isinstance(cc_val, str) else (json.dumps(cc_val) if cc_val else "")
    dx_candidates = []
    for x in dx_list:
        if isinstance(x, str):
            dx_candidates.append(x)
        elif isinstance(x, dict):
            dx_candidates.append(x.get("name") or x.get("description") or "")
    if chief: dx_candidates.append(chief)
    if gt_dx:
        # GT items may be silver-GT dicts {primary, accepts} \u2014 compare any accept
        # form to any extracted candidate via _dx_equivalent (string\u2192string).
        sem_tp = 0
        for exp_item in gt_dx:
            exp_forms = _accept_forms(exp_item)
            if any(_dx_equivalent(exp, c) for exp in exp_forms if exp for c in dx_candidates if c):
                sem_tp += 1
        # Sanity: semantic can only add matches, not remove them.
        sem_tp = max(sem_tp, per_field["diagnoses"]["matched"])
        dx_recall_semantic = sem_tp / len(gt_dx)
    else:
        dx_recall_semantic = 1.0

    # ── Structural errors (hard fails) ──
    structural = []
    for med in meds_list:
        _nm_raw = (med.get("name") if isinstance(med, dict) else med)
        nm = _nm_raw if isinstance(_nm_raw, str) else (str(_nm_raw) if _nm_raw else "")
        if _is_vaccine(nm):
            structural.append({"type": "vaccine_in_medications", "value": nm})
    dx_explicit = dx_is_explicit_in_transcript(enc)
    if not dx_list and dx_explicit:
        structural.append({"type": "empty_dx_despite_explicit_transcript"})

    # ── Per-field fabrication rate (support-in-transcript check) ──
    transcript_blob = ((enc.conversation or "") + " " + (enc.dictation or "")).lower()
    def _fabrication_rate(items, key="name"):
        supported = 0; total = 0
        for item in items or []:
            total += 1
            if isinstance(item, dict):
                value = item.get(key) or item.get("description") or item.get("test") or item.get("vaccine")
            else:
                value = item
            # Coerce list/dict/other weirdness to a string for the substring test.
            if not isinstance(value, str):
                value = str(value) if value is not None else ""
            if _fact_in_transcript(value, transcript_blob):
                supported += 1
        return {"total": total, "supported": supported,
                "fabrication_rate": round((total - supported) / total, 3) if total else 0,
                "support_rate": round(supported / total, 3) if total else 1.0}

    fab_dx = _fabrication_rate(dx_list)
    fab_meds = _fabrication_rate(meds_list)
    fab_invs = _fabrication_rate(invs_list)
    fab_plan = _fabrication_rate(plan_list)
    fab_exam = _fabrication_rate(exam_list)
    fab_allerg = _fabrication_rate(allerg_list)

    # ── Chief complaint / plan / SMS presence ──
    chief_complaint_set = bool((cc_val.strip() if isinstance(cc_val, str) else cc_val))
    plan_populated = bool(plan_list) and any(str(p).strip() for p in plan_list)
    _sms_raw = ext.get("sms_summary")
    sms = _sms_raw.strip() if isinstance(_sms_raw, str) else str(_sms_raw or "").strip()
    sms_is_placeholder = any(p in sms.lower() for p in ("<=19", "...", "\u226419", "short shorthand"))
    sms_summary_ok = 0 < len(sms) <= 25 and not sms_is_placeholder

    # ── Overall micro-averaged P/R/F1 across ALL fields that have GT ──
    # (silver GT enables exam/investigations/plan/immunizations to count)
    tp_total = sum(per_field[c]["matched"] for c in per_field
                   if per_field[c]["total_gt"] > 0 or per_field[c]["total_extracted"] > 0)
    ext_total = sum(per_field[c]["total_extracted"] for c in per_field
                    if per_field[c]["total_gt"] > 0 or per_field[c]["total_extracted"] > 0)
    gt_total = sum(per_field[c]["total_gt"] for c in per_field)
    overall_p = tp_total / ext_total if ext_total else 1.0
    overall_r = tp_total / gt_total if gt_total else 1.0
    overall_f1 = (2 * overall_p * overall_r / (overall_p + overall_r)) if (overall_p + overall_r) else 0.0

    # ── F1 scores (for backward-compat with legacy output keys) ──
    def _f1(p, r):
        return round(2*p*r/(p+r), 3) if (p+r) > 0 else 0
    dx_f1_sem = _f1(per_field["diagnoses"]["precision"], dx_recall_semantic)

    return {
        # ── Backward-compat flat keys (used by run() aggregation) ──
        "dx_precision": per_field["diagnoses"]["precision"],
        "dx_recall":    per_field["diagnoses"]["recall"],
        "dx_f1":        per_field["diagnoses"]["f1"],
        "dx_recall_semantic": round(dx_recall_semantic, 3),
        "dx_f1_semantic":     dx_f1_sem,
        "meds_precision": per_field["medications"]["precision"],
        "meds_recall":    per_field["medications"]["recall"],
        "meds_f1":        per_field["medications"]["f1"],
        "vitals_recall":    per_field["vitals"]["recall"],
        "allergies_recall": per_field["allergies"]["recall"],
        "dx_extracted": per_field["diagnoses"]["total_extracted"],
        "meds_extracted": per_field["medications"]["total_extracted"],
        "investigations_extracted": per_field["investigations"]["total_extracted"],
        "exam_findings_extracted":  per_field["exam_findings"]["total_extracted"],
        "immunizations_extracted":  per_field["immunizations"]["total_extracted"],
        "chief_complaint_set": chief_complaint_set,
        "plan_populated": plan_populated,
        "sms_summary_ok": sms_summary_ok,
        "dx_explicit_in_transcript": dx_explicit,
        # ── Per-field P/R/F1 + 4-bucket decomposition ──
        "per_field": per_field,
        # ── Per-field fabrication (transcript-support) ──
        "fab_dx": fab_dx, "fab_meds": fab_meds, "fab_investigations": fab_invs,
        "fab_plan": fab_plan, "fab_exam_findings": fab_exam, "fab_allergies": fab_allerg,
        # ── Structural errors ──
        "structural_errors": structural,
        "has_vaccine_in_meds": any(s["type"] == "vaccine_in_medications" for s in structural),
        # ── Overall micro-avg ──
        "overall_precision": round(overall_p, 3),
        "overall_recall":    round(overall_r, 3),
        "overall_f1":        round(overall_f1, 3),
    }


# ═══════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def generate_note(model, backend, transcript):
    """Call the LLM to generate a clinical note (separate from extraction).
    Returns (note_text|None, raw_text, elapsed_s)."""
    user_msg = NOTE_USER.format(transcript=transcript)
    if backend == "ollama":
        t0 = time.time()
        try:
            r = requests.post(f"{OLLAMA_URL}/api/chat", json={
                "model": model, "stream": False, "options": {"temperature": 0.3, "top_p": 0.95, "num_predict": 4096},
                "messages": [
                    {"role": "system", "content": NOTE_SYSTEM},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": "<think>\n</think>\n"},
                ],
            }, timeout=120)
            r.raise_for_status()
            raw = r.json().get("message", {}).get("content", "")
            return _strip_think(raw), raw, time.time() - t0
        except Exception as e:
            return None, f"[ERROR] {e}", time.time() - t0
    elif backend == "anthropic":
        try:
            import anthropic
        except ImportError:
            return None, "[ImportError] anthropic", 0
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key: return None, "[no ANTHROPIC_API_KEY]", 0
        t0 = time.time()
        try:
            r = anthropic.Anthropic(api_key=key).messages.create(
                model=model, max_tokens=4096, system=NOTE_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = r.content[0].text
            return _strip_think(raw), raw, time.time() - t0
        except Exception as e:
            return None, f"[ERROR] {e}", time.time() - t0
    elif backend == "openai":
        try:
            import openai
        except ImportError:
            return None, "[ImportError] openai", 0
        key = os.environ.get("OPENAI_API_KEY")
        if not key: return None, "[no OPENAI_API_KEY]", 0
        t0 = time.time()
        try:
            kw = {"max_completion_tokens": 4096} if model.startswith(("gpt-5", "o1", "o3", "o4")) else {"max_tokens": 4096}
            r = openai.OpenAI(api_key=key).chat.completions.create(
                model=model, **kw,
                messages=[{"role": "system", "content": NOTE_SYSTEM},
                          {"role": "user", "content": user_msg}],
            )
            raw = r.choices[0].message.content
            return _strip_think(raw), raw, time.time() - t0
        except Exception as e:
            return None, f"[ERROR] {e}", time.time() - t0
    return None, "", 0


_SOAP_PATTERNS = {
    "subjective": [r"##?\s*subjective\b", r"\*\*subjective\*\*", r"^subjective:?\s*$",
                   r"chief complaint\b", r"history of present", r"\bhpi\b", r"presenting complaint"],
    "objective":  [r"##?\s*objective\b", r"\*\*objective\*\*", r"^objective:?\s*$",
                   r"physical exam", r"vital signs?\b", r"on examination", r"\bo/e\b",
                   r"temperature.*\d+", r"blood pressure.*\d+", r"pulse.*\d+"],
    "assessment": [r"##?\s*assessment\b", r"\*\*assessment\*\*", r"^assessment:?\s*$",
                   r"^impression:?", r"^diagnosis:?", r"differential diagnosis"],
    "plan":       [r"##?\s*plan\b", r"\*\*plan\*\*", r"^plan:?\s*$",
                   r"^treatment:?", r"^management:?", r"^disposition:?",
                   r"^medications?:?", r"^follow[-\s]?up:?", r"^rx:?"],
}

_FOLLOWUP_PATTERNS = [r"follow[-\s]?up", r"review in \d+", r"return in \d+", r"come back",
                     r"recheck", r"re-?assess", r"next visit"]
_REFERRAL_PATTERNS = [r"refer(?:ral)?", r"specialist", r"transfer to", r"admit to",
                    r"send to", r"cardiolog", r"neurolog", r"ob[/\s-]?gyn", r"ent\b",
                    r"hospital", r"emergency"]
_INVESTIGATION_PATTERNS = [r"\border(?:ed)?", r"\bsend\b.*\b(labs?|blood|sample|test)",
                           r"cbc\b", r"fbs\b", r"rbs\b", r"hba1c", r"ecg", r"x[-\s]?ray",
                           r"ultrasound", r"urinalysis", r"culture", r"lipid panel",
                           r"rapid test", r"rdt\b", r"smear", r"biopsy", r"mri", r"ct scan"]


def score_note(note: str, enc) -> dict:
    """Score clinical note quality on multiple clinically meaningful criteria.

    Returns a rich dict with per-SOAP-section, per-fact-type, and aggregate scores.
    """
    if not note or len(note) < 30:
        return {"structure": 0, "completeness": 0, "hallucination": 0,
                "soap_s": 0, "soap_o": 0, "soap_a": 0, "soap_p": 0,
                "completeness_dx": 0, "completeness_meds": 0, "completeness_vitals": 0,
                "has_followup": False, "has_referral": False, "has_investigations": False,
                "prose_quality": 0, "hallucinated_meds": [],
                "issues": ["empty or too short"], "length": 0}

    note_lower = note.lower()
    issues = []
    note_len = len(note)

    # ── SOAP section presence (per-section 0-1) ─────────────────────────
    soap_scores = {}
    for section, patterns in _SOAP_PATTERNS.items():
        hits = sum(1 for p in patterns if re.search(p, note_lower, re.MULTILINE | re.IGNORECASE))
        # 0 hits = section missing; 1 hit = probably present; 2+ hits = definitely present
        soap_scores[section] = min(1.0, hits / 2.0) if hits else 0.0

    # ── Per-fact-type completeness (dx / meds / vitals) ─────────────────
    aliases = {"blood pressure": ["bp", "pressure", "mmhg"],
               "temperature": ["temp", "fever", "degrees", "celsius"],
               "oxygen": ["spo2", "o2", "saturation", "sat"]}

    dx_found = sum(1 for dx in enc.expected_diagnoses if dx.lower() in note_lower)
    completeness_dx = dx_found / len(enc.expected_diagnoses) if enc.expected_diagnoses else 1.0

    meds_found = sum(1 for m in enc.expected_medications if m.lower() in note_lower)
    completeness_meds = meds_found / len(enc.expected_medications) if enc.expected_medications else 1.0

    vit_found = sum(1 for v in enc.expected_vitals
                    if v.lower() in note_lower or any(a in note_lower for a in aliases.get(v.lower(), [])))
    completeness_vitals = vit_found / len(enc.expected_vitals) if enc.expected_vitals else 1.0

    total_facts = len(enc.expected_diagnoses) + len(enc.expected_medications) + len(enc.expected_vitals)
    completeness = (dx_found + meds_found + vit_found) / total_facts if total_facts else 1.0

    # ── Clinical completeness ──────────────────────────────────────────
    has_followup = any(re.search(p, note_lower) for p in _FOLLOWUP_PATTERNS)
    has_referral = any(re.search(p, note_lower) for p in _REFERRAL_PATTERNS)
    has_investigations = any(re.search(p, note_lower) for p in _INVESTIGATION_PATTERNS)

    # ── Prose quality (1.0 = pure third-person clinical prose) ─────────
    dialog_patterns = [
        r'(?:patient|doctor|nurse|mother|wife|friend)\s*:',
        r'"[^"]{15,}"',
        r'\b(I told|I said|I gave|I checked|let me)\b',
        r'\b(please help|oh my god|is he going|thank you doctor)\b',
    ]
    dialog_hits = sum(1 for p in dialog_patterns if re.search(p, note, re.I))
    filler_patterns = [
        r"(none provided|not mentioned|no data available|n/a(?!\w)|not applicable)",
        r"(disclaimer|important note:|warning:)",
    ]
    filler_hits = sum(1 for p in filler_patterns if re.search(p, note_lower))
    prose_quality = max(0.0, 1.0 - 0.3 * dialog_hits - 0.2 * filler_hits)
    if dialog_hits:
        issues.append(f"dialog leakage ({dialog_hits})")
    if filler_hits:
        issues.append(f"filler/padding ({filler_hits})")

    # ── Repetition penalty ─────────────────────────────────────────────
    from collections import Counter
    lines = [l.strip() for l in note.split("\n") if l.strip() and len(l.strip()) > 15]
    if any(c >= 3 for _, c in Counter(lines).items()):
        prose_quality = max(0, prose_quality - 0.3)
        issues.append("repetition loop")

    # ── Aggregate structure score (0-1) ────────────────────────────────
    # Blend SOAP-section presence + prose quality + length adequacy
    n_sections_present = sum(1 for s in soap_scores.values() if s >= 0.5)
    section_score = n_sections_present / 4.0  # 0 if no SOAP, 1 if all 4 present
    length_score = (1.0 if 200 <= note_len <= 1500 else
                    0.5 if 100 <= note_len <= 2000 else 0.0)
    if not (100 <= note_len <= 2000):
        issues.append(f"length {note_len}ch (ideal 200–1500)")
    structure = round(0.5 * section_score + 0.3 * prose_quality + 0.2 * length_score, 2)

    # ── Hallucination (fact precision on meds) ────────────────────────
    common_drugs = ["amoxicillin", "metformin", "paracetamol", "ibuprofen", "aspirin",
                    "warfarin", "enalapril", "amlodipine", "diclofenac", "prednisolone",
                    "salbutamol", "ceftriaxone", "metronidazole", "fluoxetine", "diazepam",
                    "cotrimoxazole", "insulin", "furosemide", "omeprazole", "erythromycin",
                    "levothyroxine", "labetalol", "atorvastatin", "hydrochlorothiazide",
                    "ferrous sulfate", "artesunate", "artemether", "glimepiride", "timolol",
                    "magnesium sulfate", "allopurinol", "sodium valproate", "methotrexate",
                    "folic acid", "carbimazole", "propranolol", "spironolactone",
                    "tramadol", "morphine", "ceftazidime", "ciprofloxacin", "doxycycline",
                    "fluconazole", "nystatin", "acyclovir", "azithromycin"]
    expected_meds_lower = {m.lower() for m in enc.expected_medications}
    hallucinated_meds = []
    for drug in common_drugs:
        if drug in note_lower and not any(em in drug or drug in em for em in expected_meds_lower):
            idx = note_lower.find(drug)
            allergy_context = "allerg" in note_lower[max(0, idx - 30):idx]
            if not allergy_context:
                hallucinated_meds.append(drug)
    hallucination_score = max(0, 1.0 - len(hallucinated_meds) * 0.25)
    if hallucinated_meds:
        issues.append(f"hallucinated meds: {', '.join(hallucinated_meds[:3])}")

    return {
        # Aggregate (backward-compat)
        "structure": structure,
        "completeness": round(completeness, 2),
        "hallucination": round(hallucination_score, 2),
        # Per-SOAP-section presence (0-1)
        "soap_s": round(soap_scores["subjective"], 2),
        "soap_o": round(soap_scores["objective"], 2),
        "soap_a": round(soap_scores["assessment"], 2),
        "soap_p": round(soap_scores["plan"], 2),
        # Per-fact-type completeness
        "completeness_dx": round(completeness_dx, 2),
        "completeness_meds": round(completeness_meds, 2),
        "completeness_vitals": round(completeness_vitals, 2),
        # Clinical completeness (boolean)
        "has_followup": has_followup,
        "has_referral": has_referral,
        "has_investigations": has_investigations,
        # Prose quality
        "prose_quality": round(prose_quality, 2),
        "hallucinated_meds": hallucinated_meds,
        "issues": issues,
        "length": note_len,
    }


def detect_models():
    models = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        for m in ["claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]:
            models.append((m, "anthropic"))
    if os.environ.get("OPENAI_API_KEY"):
        for m in ["gpt-5.5", "gpt-5.4", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"]:
            models.append((m, "openai"))
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.ok:
            for m in r.json().get("models", []):
                models.append((m["name"], "ollama"))
    except:
        pass
    return models


DANGER_CATEGORIES = [
    "Drug-Allergy", "Drug-Drug", "Dosage", "Vitals",
    "Drug-Condition", "Triage", "Lab Recommendation", "Referral Suggestion",
]


def _count_by_category(alerts, expected):
    """For each category, count caught and total expected."""
    by_cat = {cat: {"caught": 0, "expected": 0} for cat in DANGER_CATEGORIES}
    for exp in expected:
        cat = exp["category"]
        if cat in by_cat:
            by_cat[cat]["expected"] += 1
            if any(alert_matches(a, exp) for a in alerts):
                by_cat[cat]["caught"] += 1
    return by_cat


RAW_DIR_BASE = os.path.join(os.path.dirname(__file__), "bodhi_raw_generations")
# RAW_DIR is set per-run at main() time; default is the base folder (run 1).
RAW_DIR = RAW_DIR_BASE
SKIP_EXISTING = True  # skip encounters whose raw file already exists (resume-friendly)


def _safe_slug(s: str) -> str:
    return s.replace(":", "-").replace("/", "-")


def _save_raw(model_name, mode, enc, i, payload):
    """Persist full raw outputs for one encounter under RAW_DIR (per-run subfolder if set)."""
    try:
        os.makedirs(RAW_DIR, exist_ok=True)
        slug = f"{_safe_slug(model_name)}__{mode}__enc{i+1:03d}"
        # Include run_id in the payload so downstream tools can identify it
        if RAW_DIR != RAW_DIR_BASE:
            payload.setdefault("run_id", os.path.basename(RAW_DIR))
        with open(os.path.join(RAW_DIR, f"{slug}.json"), "w") as f:
            json.dump(payload, f, indent=2, default=str)
    except Exception as e:
        print(f"    [raw save error: {e}]")


def _alert_to_dict(a):
    return {"severity": a.severity, "category": a.category, "message": a.message}


def run(models, transcript_mode, dry_run=False):
    data = ClinicalData()
    cdss = CDSS(data)
    print(f"BODHI: {len(data.bodhi_conditions)} conditions, {len(data.bodhi_drugs_by_name)} drugs")
    print(f"Vanilla: {len(data.allergy_interactions)} allergy rules, {len(data.drug_interactions)} drug interactions")
    print()

    all_results = {}

    for model_name, backend in models:
        print(f"{'='*80}")
        print(f"MODEL: {model_name} ({backend})  |  transcript: {transcript_mode}")
        print(f"{'='*80}")

        total_dangers = 0
        arm1_caught = 0
        arm2_caught = 0
        arm3_caught = 0
        total_time = 0
        failures = 0
        per_encounter = []

        # Aggregate extraction + note scores
        sum_dx_prec = sum_dx_rec = sum_meds_prec = sum_meds_rec = sum_vit_rec = 0.0
        sum_allerg_rec = sum_chief = sum_plan = sum_sms = 0.0
        sum_note_struct = sum_note_complete = sum_note_halluc = 0.0
        sum_soap_s = sum_soap_o = sum_soap_a = sum_soap_p = 0.0
        sum_complete_dx = sum_complete_meds = sum_complete_vit = 0.0
        sum_prose = 0.0
        sum_followup = sum_referral = sum_invest = 0
        n_scored = 0
        n_notes = 0
        # NEW: split dx recall by whether the dx appears in the transcript
        sum_dx_rec_explicit = 0.0; n_dx_explicit = 0
        sum_dx_rec_inferred = 0.0; n_dx_inferred = 0

        cat_totals = {cat: {"caught_arm1": 0, "caught_arm2": 0, "caught_arm3": 0, "expected": 0}
                      for cat in DANGER_CATEGORIES}

        for i, enc in enumerate(ENCOUNTERS):
            transcript = enc.conversation if transcript_mode == "conversation" else enc.dictation
            print(f"\n  [{i+1}/{len(ENCOUNTERS)}] {enc.name}")

            n_dangers = len(enc.expected_dangers)
            total_dangers += n_dangers

            for exp in enc.expected_dangers:
                if exp["category"] in cat_totals:
                    cat_totals[exp["category"]]["expected"] += 1

            # Skip if raw output already exists for this run (resume-friendly)
            _slug = _safe_slug(model_name)
            _existing_path = os.path.join(RAW_DIR, f"{_slug}__{transcript_mode}__enc{i+1:03d}.json")
            if SKIP_EXISTING and os.path.exists(_existing_path):
                try:
                    _d = json.loads(open(_existing_path).read())
                    if _d.get("extraction", {}).get("parsed") is not None:
                        print(f"    (skip \u2014 already done)")
                        continue
                except Exception:
                    pass

            if dry_run:
                ext = {"diagnoses": enc.expected_diagnoses,
                       "medications": [{"name": m} for m in enc.expected_medications],
                       "vitals": [{"name": v, "value": "normal"} for v in enc.expected_vitals],
                       "investigations": [], "allergies": enc.patient_allergies,
                       "chief_complaint": "(dry-run)", "plan": ["(dry-run)"]}
                ext_raw = "(dry-run)"
                elapsed = 0
                review_alerts, review_raw, review_time = [], "(dry-run)", 0
                note, note_raw, note_time = None, "(dry-run)", 0
            else:
                ext, ext_raw, elapsed = extract(model_name, backend, transcript)
                total_time += elapsed
                if not ext:
                    print(f"    EXTRACTION FAILED ({elapsed:.1f}s)")
                    failures += 1
                    _save_raw(model_name, transcript_mode, enc, i, {
                        "encounter_id": i + 1, "encounter_name": enc.name, "category": enc.category,
                        "model": model_name, "backend": backend,
                        "transcript_mode": transcript_mode, "transcript": transcript,
                        "ground_truth": {
                            "expected_diagnoses": enc.expected_diagnoses,
                            "expected_medications": enc.expected_medications,
                            "expected_vitals": enc.expected_vitals,
                            "patient_allergies": enc.patient_allergies,
                            "expected_dangers": enc.expected_dangers,
                        },
                        "extraction": {"raw": ext_raw, "parsed": None, "latency_s": round(elapsed, 2)},
                        "failed": "extraction",
                    })
                    per_encounter.append({"name": enc.name, "failed": True})
                    continue

                review_alerts, review_raw, review_time = clinical_review(model_name, backend, transcript)
                total_time += review_time

                note, note_raw, note_time = generate_note(model_name, backend, transcript)
                total_time += note_time

            # Extraction scoring
            eq = extraction_quality(ext, enc)
            n_scored += 1
            # Per-field scores can be None when silver GT has no items for that field.
            # Treat missing as 0 contribution (doesn't affect micro-average; n_scored still grows).
            _z = lambda v: v if v is not None else 0
            sum_dx_prec += _z(eq["dx_precision"]);    sum_dx_rec += _z(eq["dx_recall"])
            sum_meds_prec += _z(eq["meds_precision"]); sum_meds_rec += _z(eq["meds_recall"])
            sum_vit_rec += _z(eq["vitals_recall"])
            sum_allerg_rec += _z(eq["allergies_recall"])
            sum_chief += 1 if eq["chief_complaint_set"] else 0
            sum_plan += 1 if eq["plan_populated"] else 0
            sum_sms += 1 if eq["sms_summary_ok"] else 0
            # NEW: split dx recall by explicit vs inferred
            if enc.expected_diagnoses:
                if eq["dx_explicit_in_transcript"]:
                    sum_dx_rec_explicit += _z(eq["dx_recall"]); n_dx_explicit += 1
                else:
                    sum_dx_rec_inferred += _z(eq["dx_recall"]); n_dx_inferred += 1

            _fmt = lambda v: "n/a" if v is None else f"{v:.0%}"
            print(f"    Extract: dx P={_fmt(eq['dx_precision'])}/R={_fmt(eq['dx_recall'])}  "
                  f"meds P={_fmt(eq['meds_precision'])}/R={_fmt(eq['meds_recall'])}  "
                  f"vitals R={_fmt(eq['vitals_recall'])}  "
                  f"allerg R={_fmt(eq['allergies_recall'])}  ({elapsed:.1f}s)")

            # Arm 2 + Arm 3
            vanilla_alerts, bodhi_alerts = cdss.evaluate(ext, enc.patient_allergies)
            arm3_alerts = vanilla_alerts + bodhi_alerts

            a1 = count_caught(review_alerts, enc.expected_dangers)
            a2 = count_caught(vanilla_alerts, enc.expected_dangers)
            a3 = count_caught(arm3_alerts, enc.expected_dangers)
            arm1_caught += a1; arm2_caught += a2; arm3_caught += a3

            a1_by_cat = _count_by_category(review_alerts, enc.expected_dangers)
            a2_by_cat = _count_by_category(vanilla_alerts, enc.expected_dangers)
            a3_by_cat = _count_by_category(arm3_alerts, enc.expected_dangers)
            for cat in DANGER_CATEGORIES:
                cat_totals[cat]["caught_arm1"] += a1_by_cat[cat]["caught"]
                cat_totals[cat]["caught_arm2"] += a2_by_cat[cat]["caught"]
                cat_totals[cat]["caught_arm3"] += a3_by_cat[cat]["caught"]

            print(f"    Dangers caught — Arm1(LLM)={a1}/{n_dangers}  Arm2(Rules)={a2}/{n_dangers}  Arm3(Rules+BODHI)={a3}/{n_dangers}")
            for a in vanilla_alerts[:3]:
                print(f"      [V] [{a.severity}] {a.category}: {a.message[:70]}")
            for a in bodhi_alerts[:3]:
                print(f"      [B] [{a.severity}] {a.category}: {a.message[:70]}")

            # Note scoring
            if dry_run:
                ns = {"structure": 1.0, "completeness": 1.0, "hallucination": 1.0,
                      "soap_s": 1.0, "soap_o": 1.0, "soap_a": 1.0, "soap_p": 1.0,
                      "completeness_dx": 1.0, "completeness_meds": 1.0, "completeness_vitals": 1.0,
                      "has_followup": True, "has_referral": False, "has_investigations": False,
                      "prose_quality": 1.0, "hallucinated_meds": [], "issues": [], "length": 500}
            elif note:
                ns = score_note(note, enc)
                sum_note_struct += ns["structure"]
                sum_note_complete += ns["completeness"]
                sum_note_halluc += ns["hallucination"]
                sum_soap_s += ns["soap_s"]; sum_soap_o += ns["soap_o"]
                sum_soap_a += ns["soap_a"]; sum_soap_p += ns["soap_p"]
                sum_complete_dx += ns["completeness_dx"]; sum_complete_meds += ns["completeness_meds"]
                sum_complete_vit += ns["completeness_vitals"]
                sum_prose += ns["prose_quality"]
                sum_followup += 1 if ns["has_followup"] else 0
                sum_referral += 1 if ns["has_referral"] else 0
                sum_invest += 1 if ns["has_investigations"] else 0
                n_notes += 1
                issue_str = f"  issues: {', '.join(ns['issues'][:2])}" if ns["issues"] else ""
                print(f"    Note: struct={ns['structure']:.0%} compl={ns['completeness']:.0%} "
                      f"halluc={ns['hallucination']:.0%} "
                      f"SOAP(S/O/A/P)={int(ns['soap_s']*100)}/{int(ns['soap_o']*100)}/{int(ns['soap_a']*100)}/{int(ns['soap_p']*100)} "
                      f"({ns['length']}ch){issue_str}")
            else:
                ns = {"structure": 0, "completeness": 0, "hallucination": 0,
                      "soap_s": 0, "soap_o": 0, "soap_a": 0, "soap_p": 0,
                      "completeness_dx": 0, "completeness_meds": 0, "completeness_vitals": 0,
                      "has_followup": False, "has_referral": False, "has_investigations": False,
                      "prose_quality": 0, "hallucinated_meds": [],
                      "issues": ["generation failed"], "length": 0}
                print(f"    Note: GENERATION FAILED")

            # Persist raw capture
            if not dry_run:
                _save_raw(model_name, transcript_mode, enc, i, {
                    "encounter_id": i + 1, "encounter_name": enc.name, "category": enc.category,
                    "model": model_name, "backend": backend, "transcript_mode": transcript_mode,
                    "transcript": transcript,
                    "ground_truth": {
                        "expected_diagnoses": enc.expected_diagnoses,
                        "expected_medications": enc.expected_medications,
                        "expected_vitals": enc.expected_vitals,
                        "patient_allergies": enc.patient_allergies,
                        "expected_dangers": enc.expected_dangers,
                    },
                    "extraction": {"raw": ext_raw, "parsed": ext, "latency_s": round(elapsed, 2),
                                   "score": eq},
                    "note": {"raw": note_raw, "text": note, "latency_s": round(note_time, 2),
                             "score": ns},
                    "clinical_review_arm1": {"raw": review_raw, "parsed_alerts": [_alert_to_dict(a) for a in review_alerts],
                                             "latency_s": round(review_time, 2),
                                             "dangers_caught": a1, "dangers_total": n_dangers},
                    "arm2_rules_alerts": [_alert_to_dict(a) for a in vanilla_alerts],
                    "arm3_bodhi_added_alerts": [_alert_to_dict(a) for a in bodhi_alerts],
                    "arm_caught": {"arm1": a1, "arm2": a2, "arm3": a3, "total": n_dangers},
                })

            per_encounter.append({
                "name": enc.name, "category": enc.category,
                "extraction": eq, "note": ns, "time": round(elapsed, 1),
                "dangers_total": n_dangers,
                "arm1_caught": a1, "arm2_caught": a2, "arm3_caught": a3,
            })

        avg_time = total_time / len(ENCOUNTERS) if not dry_run else 0
        a1_rate = arm1_caught / total_dangers if total_dangers else 0
        a2_rate = arm2_caught / total_dangers if total_dangers else 0
        a3_rate = arm3_caught / total_dangers if total_dangers else 0
        bodhi_over_llm = arm3_caught - arm1_caught
        bodhi_over_rules = arm3_caught - arm2_caught

        # Average extraction + note scores
        _avg = lambda s: (s / n_scored) if n_scored else 0
        _avgn = lambda s: (s / n_notes) if n_notes else 0
        avg_dx_prec = _avg(sum_dx_prec); avg_dx_rec = _avg(sum_dx_rec)
        avg_meds_prec = _avg(sum_meds_prec); avg_meds_rec = _avg(sum_meds_rec)
        avg_vit_rec = _avg(sum_vit_rec)
        avg_allerg_rec = _avg(sum_allerg_rec)
        avg_chief = _avg(sum_chief)
        avg_plan = _avg(sum_plan)
        avg_sms = _avg(sum_sms)
        # NEW: per-bucket dx recall (explicit-in-transcript vs must-be-inferred)
        avg_dx_rec_explicit = (sum_dx_rec_explicit / n_dx_explicit) if n_dx_explicit else None
        avg_dx_rec_inferred = (sum_dx_rec_inferred / n_dx_inferred) if n_dx_inferred else None

        avg_note_struct = _avgn(sum_note_struct)
        avg_note_complete = _avgn(sum_note_complete)
        avg_note_halluc = _avgn(sum_note_halluc)
        avg_soap_s = _avgn(sum_soap_s); avg_soap_o = _avgn(sum_soap_o)
        avg_soap_a = _avgn(sum_soap_a); avg_soap_p = _avgn(sum_soap_p)
        avg_complete_dx = _avgn(sum_complete_dx); avg_complete_meds = _avgn(sum_complete_meds)
        avg_complete_vit = _avgn(sum_complete_vit)
        avg_prose = _avgn(sum_prose)
        pct_followup = _avgn(sum_followup); pct_referral = _avgn(sum_referral); pct_invest = _avgn(sum_invest)

        summary = {
            "model": model_name, "backend": backend,
            "transcript_mode": transcript_mode,
            "total_dangers": total_dangers,
            "arm1_caught": arm1_caught, "arm1_rate": round(a1_rate, 3),
            "arm2_caught": arm2_caught, "arm2_rate": round(a2_rate, 3),
            "arm3_caught": arm3_caught, "arm3_rate": round(a3_rate, 3),
            "bodhi_over_llm": bodhi_over_llm,
            "bodhi_over_rules": bodhi_over_rules,
            "failures": failures,
            "avg_time": round(avg_time, 1),
            # Extraction
            "dx_precision": round(avg_dx_prec, 2), "dx_recall": round(avg_dx_rec, 2),
            "dx_recall_explicit": round(avg_dx_rec_explicit, 3) if avg_dx_rec_explicit is not None else None,
            "dx_recall_inferred": round(avg_dx_rec_inferred, 3) if avg_dx_rec_inferred is not None else None,
            "n_dx_explicit": n_dx_explicit, "n_dx_inferred": n_dx_inferred,
            "meds_precision": round(avg_meds_prec, 2), "meds_recall": round(avg_meds_rec, 2),
            "vitals_recall": round(avg_vit_rec, 2),
            "allergies_recall": round(avg_allerg_rec, 2),
            "chief_complaint_rate": round(avg_chief, 2),
            "plan_populated_rate": round(avg_plan, 2),
            "sms_summary_rate": round(avg_sms, 2),
            # Note aggregates
            "note_structure": round(avg_note_struct, 2),
            "note_completeness": round(avg_note_complete, 2),
            "note_hallucination": round(avg_note_halluc, 2),
            # Per-SOAP
            "note_soap_s": round(avg_soap_s, 2), "note_soap_o": round(avg_soap_o, 2),
            "note_soap_a": round(avg_soap_a, 2), "note_soap_p": round(avg_soap_p, 2),
            # Per-fact completeness in note
            "note_completeness_dx": round(avg_complete_dx, 2),
            "note_completeness_meds": round(avg_complete_meds, 2),
            "note_completeness_vitals": round(avg_complete_vit, 2),
            # Qualitative
            "note_prose_quality": round(avg_prose, 2),
            "note_followup_rate": round(pct_followup, 2),
            "note_referral_rate": round(pct_referral, 2),
            "note_investigations_rate": round(pct_invest, 2),
            "category_totals": cat_totals,
            "encounters": per_encounter,
        }
        all_results[f"{model_name}|{transcript_mode}"] = summary

        print(f"\n  {'─'*70}")
        print(f"  Extraction:")
        print(f"    Dx P={avg_dx_prec:.0%}/R={avg_dx_rec:.0%}  "
              f"Meds P={avg_meds_prec:.0%}/R={avg_meds_rec:.0%}  "
              f"Vitals R={avg_vit_rec:.0%}  Allergies R={avg_allerg_rec:.0%}")
        if avg_dx_rec_explicit is not None or avg_dx_rec_inferred is not None:
            e_txt = f"{avg_dx_rec_explicit:.0%}" if avg_dx_rec_explicit is not None else "n/a"
            i_txt = f"{avg_dx_rec_inferred:.0%}" if avg_dx_rec_inferred is not None else "n/a"
            print(f"    Dx recall split:  explicit-in-transcript={e_txt} (n={n_dx_explicit})   inferred={i_txt} (n={n_dx_inferred})")
        print(f"    Chief complaint set: {avg_chief:.0%}  Plan populated: {avg_plan:.0%}  SMS summary ok: {avg_sms:.0%}")
        print(f"  Note quality (aggregate):")
        print(f"    structure={avg_note_struct:.0%}  completeness={avg_note_complete:.0%}  "
              f"no-hallucination={avg_note_halluc:.0%}  prose-quality={avg_prose:.0%}")
        print(f"  Note — SOAP section presence:")
        print(f"    S={avg_soap_s:.0%}  O={avg_soap_o:.0%}  A={avg_soap_a:.0%}  P={avg_soap_p:.0%}")
        print(f"  Note — per-fact completeness (in note):")
        print(f"    Dx={avg_complete_dx:.0%}  Meds={avg_complete_meds:.0%}  Vitals={avg_complete_vit:.0%}")
        print(f"  Note — clinical completeness:")
        print(f"    follow-up={pct_followup:.0%}  referral={pct_referral:.0%}  investigations={pct_invest:.0%}")
        print(f"\n  Safety catch rate (N={total_dangers} dangers):")
        print(f"    Arm 1 — LLM alone (inherent clinical reasoning):  {arm1_caught}/{total_dangers} ({a1_rate:.0%})")
        print(f"    Arm 2 — ChartLite rules only (vanilla CDSS):      {arm2_caught}/{total_dangers} ({a2_rate:.0%})")
        print(f"    Arm 3 — Rules + BODHI (integrated):               {arm3_caught}/{total_dangers} ({a3_rate:.0%})")
        print(f"\n  BODHI incremental value:")
        print(f"    Over LLM alone:      +{bodhi_over_llm} dangers (Arm 3 − Arm 1)")
        print(f"    Over ChartLite rules: +{bodhi_over_rules} dangers (Arm 3 − Arm 2)")
        print(f"\n  Per-category Arm 3 catch rate:")
        for cat in DANGER_CATEGORIES:
            t = cat_totals[cat]
            if t["expected"] > 0:
                tag = " [BODHI-enabled]" if cat in ("Drug-Condition", "Triage", "Lab Recommendation", "Referral Suggestion") else ""
                print(f"    {cat:<22} {t['caught_arm3']}/{t['expected']} "
                      f"(Arm1={t['caught_arm1']}, Arm2={t['caught_arm2']}, Arm3={t['caught_arm3']}){tag}")
        print(f"\n  Failures: {failures}  Avg time: {avg_time:.1f}s/encounter")

    return all_results


def print_table(results):
    print()
    W = 155
    print("=" * W)
    print("FINAL RESULTS: 3-Arm Comparison (LLM-alone vs ChartLite rules vs Rules+BODHI)")
    print("=" * W)
    print(f"{'Model':<26} {'Mode':<10} {'Dx P/R':>10} {'Med P/R':>10} {'NStruc':>7} {'NCompl':>7} "
          f"{'Arm1':>10} {'Arm2':>10} {'Arm3':>10} {'Δ(3-1)':>7} {'Δ(3-2)':>7} {'Fail':>5}")
    print("-" * W)

    for key, s in results.items():
        name = s["model"][:26]
        mode = s["transcript_mode"][:10]
        dx_pr = f"{s['dx_precision']:.0%}/{s['dx_recall']:.0%}"
        med_pr = f"{s['meds_precision']:.0%}/{s['meds_recall']:.0%}"
        ns = f"{s.get('note_structure', 0):.0%}"
        nc = f"{s.get('note_completeness', 0):.0%}"
        a1 = f"{s['arm1_caught']}/{s['total_dangers']} ({s['arm1_rate']:.0%})"
        a2 = f"{s['arm2_caught']}/{s['total_dangers']} ({s['arm2_rate']:.0%})"
        a3 = f"{s['arm3_caught']}/{s['total_dangers']} ({s['arm3_rate']:.0%})"
        d1 = f"+{s['bodhi_over_llm']}"
        d2 = f"+{s['bodhi_over_rules']}"
        print(f"{name:<26} {mode:<10} {dx_pr:>10} {med_pr:>10} {ns:>7} {nc:>7} "
              f"{a1:>10} {a2:>10} {a3:>10} {d1:>7} {d2:>7} {s['failures']:>5}")

    print("-" * W)
    print()
    print("  Arm 1   = LLM-alone clinical reasoning (dedicated review prompt)")
    print("  Arm 2   = ChartLite rules only (drug-allergy + drug-drug + dosage + vitals)")
    print("  Arm 3   = ChartLite rules + BODHI knowledge graph")
    print("  Δ(3-1)  = Dangers BODHI catches that the LLM alone missed")
    print("  Δ(3-2)  = Dangers BODHI catches that current ChartLite rules miss")
    print()

    # ── Q2: On-device gap analysis (Opus 4.7 vs Qwen 0.8B) ──
    _q2_gap_analysis(results)


def _q2_gap_analysis(results):
    """Q2: Can we deploy Qwen 0.8B + BODHI on-device? What do we miss vs Opus?"""
    # Find conversation-mode results for Opus and Qwen 0.8B
    opus = results.get("claude-opus-4-7|conversation")
    qwen = results.get("qwen3.5:0.8b|conversation")
    if not opus or not qwen:
        return

    print("=" * 90)
    print("Q2: ON-DEVICE VIABILITY — Qwen 0.8B + BODHI vs Opus 4.7 + BODHI (conversation mode)")
    print("=" * 90)
    rows = [
        ("Diagnosis extraction P/R", f"{qwen['dx_precision']:.0%}/{qwen['dx_recall']:.0%}",
         f"{opus['dx_precision']:.0%}/{opus['dx_recall']:.0%}"),
        ("Medication extraction P/R", f"{qwen['meds_precision']:.0%}/{qwen['meds_recall']:.0%}",
         f"{opus['meds_precision']:.0%}/{opus['meds_recall']:.0%}"),
        ("Vitals extraction R", f"{qwen['vitals_recall']:.0%}", f"{opus['vitals_recall']:.0%}"),
        ("Note structure", f"{qwen['note_structure']:.0%}", f"{opus['note_structure']:.0%}"),
        ("Note completeness", f"{qwen['note_completeness']:.0%}", f"{opus['note_completeness']:.0%}"),
        ("Note no-hallucination", f"{qwen['note_hallucination']:.0%}", f"{opus['note_hallucination']:.0%}"),
        ("Arm 1 dangers caught", f"{qwen['arm1_caught']}/{qwen['total_dangers']} ({qwen['arm1_rate']:.0%})",
         f"{opus['arm1_caught']}/{opus['total_dangers']} ({opus['arm1_rate']:.0%})"),
        ("Arm 2 dangers caught", f"{qwen['arm2_caught']}/{qwen['total_dangers']} ({qwen['arm2_rate']:.0%})",
         f"{opus['arm2_caught']}/{opus['total_dangers']} ({opus['arm2_rate']:.0%})"),
        ("Arm 3 dangers caught (on-device)", f"{qwen['arm3_caught']}/{qwen['total_dangers']} ({qwen['arm3_rate']:.0%})",
         f"{opus['arm3_caught']}/{opus['total_dangers']} ({opus['arm3_rate']:.0%})"),
    ]
    print(f"{'Dimension':<36} {'Qwen 0.8B':>18} {'Opus 4.7':>18}")
    print("-" * 90)
    for label, q, o in rows:
        print(f"{label:<36} {q:>18} {o:>18}")

    # Per-category gap (Arm 3)
    print()
    print(f"Per-category Arm 3 catch rate:")
    print(f"{'Category':<24} {'Qwen 0.8B':>14} {'Opus 4.7':>14}")
    for cat in DANGER_CATEGORIES:
        qt = qwen["category_totals"].get(cat, {})
        ot = opus["category_totals"].get(cat, {})
        exp = ot.get("expected", 0)
        if exp == 0:
            continue
        q_val = f"{qt.get('caught_arm3', 0)}/{exp}"
        o_val = f"{ot.get('caught_arm3', 0)}/{exp}"
        tag = " [BODHI]" if cat in ("Drug-Condition", "Triage", "Lab Recommendation", "Referral Suggestion") else ""
        print(f"{cat + tag:<24} {q_val:>14} {o_val:>14}")
    print()

    # Headline: BODHI recovery
    arm1_gap = opus["arm1_caught"] - qwen["arm1_caught"]
    arm3_gap = opus["arm3_caught"] - qwen["arm3_caught"]
    if arm1_gap > 0:
        recovery_pct = (1 - arm3_gap / arm1_gap) * 100 if arm1_gap > arm3_gap else 0
        print(f"  ↑ Qwen 0.8B alone trails Opus by {arm1_gap} dangers")
        print(f"  ↑ With BODHI, Qwen 0.8B trails Opus by only {arm3_gap} dangers")
        print(f"  ↑ BODHI recovers {recovery_pct:.0f}% of the capability gap for on-device deployment")
    print()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-cloud", action="store_true")
    p.add_argument("--mode", choices=["both", "conversation", "dictation"], default="both")
    p.add_argument("--run-id", default=None,
                   help="Name for this run (e.g. 'run2'). Raw files go to bodhi_raw_generations/<run-id>/.")
    args = p.parse_args()

    # Per-run output folder
    global RAW_DIR
    if args.run_id:
        RAW_DIR = os.path.join(RAW_DIR_BASE, args.run_id)
        os.makedirs(RAW_DIR, exist_ok=True)
        print(f"Raw output folder: {RAW_DIR}")

    if args.dry_run:
        models = [("ground-truth", "dry-run")]
    elif args.models:
        models = []
        for m in args.models:
            if m.startswith("claude-"):
                models.append((m, "anthropic"))
            elif m.startswith(("gpt-", "o1", "o3", "o4")):
                models.append((m, "openai"))
            else:
                models.append((m, "ollama"))
    else:
        models = detect_models()
        if args.no_cloud:
            models = [(m, b) for m, b in models if b == "ollama"]

    if not models:
        print("No models found.")
        sys.exit(1)

    modes = ["conversation", "dictation"] if args.mode == "both" else [args.mode]

    print(f"Models: {', '.join(m for m, _ in models)}")
    print(f"Encounters: {len(ENCOUNTERS)}")
    print(f"Transcript modes: {', '.join(modes)}")
    print(f"Total runs: {len(models) * len(modes) * len(ENCOUNTERS)}")
    print()

    all_results = {}
    for mode in modes:
        results = run(models, mode, dry_run=args.dry_run)
        all_results.update(results)

    with open(REPORT_PATH, "w") as f:
        json.dump({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "encounters": len(ENCOUNTERS), "results": all_results}, f, indent=2, default=str)
    print(f"\nReport: {REPORT_PATH}")

    print_table(all_results)


if __name__ == "__main__":
    main()
