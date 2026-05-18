package com.chartlite.app.model

/**
 * Data classes for the BODHI Clinical Knowledge Graph.
 * Source: https://github.com/eka-care/BODHI (CC BY-NC 4.0)
 *
 * BODHI-S: Condition-Symptom network (779 conditions, 4037 symptoms)
 * BODHI-M: Concept-Drug-Lab network (2471 concepts, 1186 drugs, 812 labs)
 */

// ── BODHI-S: Conditions ──

data class BodhiCondition(
    val snomedId: String,
    val name: String,
    val triageLevel: String? = null,
    val conceptType: String? = null,
    val specialties: List<BodhiSpecialtyLink>? = null
)

data class BodhiSpecialtyLink(
    val id: String,
    val name: String,
    val weight: Float = 1f
)

// ── BODHI-M: Drugs ──

data class BodhiDrug(
    val hash: String,
    val name: String,
    val therapeuticClass: String? = null,
    val treatedConditions: List<String>? = null  // SNOMED IDs
)

// ── BODHI-M: Lab Investigations ──

data class BodhiLab(
    val loincId: String,
    val name: String,
    val displayName: String? = null,
    val systemMap: String? = null,
    val monitoredConditions: List<BodhiLabConditionLink>? = null
)

data class BodhiLabConditionLink(
    val snomedId: String,
    val polarity: String? = null,
    val categoryThreshold: String? = null
)

// ── BODHI-S: Symptoms (per-condition) ──

data class BodhiSymptomLink(
    val name: String,
    val likelihood: Float? = null,
    val strongPredictor: Boolean = false
)

// ── ICD-10 → BODHI SNOMED precomputed mapping ──

data class Icd10SnomedMap(
    val version: Int,
    val mappings: Map<String, Icd10SnomedEntry>
)

data class Icd10SnomedEntry(
    val snomedId: String,
    val bodhiName: String,
    val confidence: Float,
    val triage: String? = null,
    val source: String? = null
)
