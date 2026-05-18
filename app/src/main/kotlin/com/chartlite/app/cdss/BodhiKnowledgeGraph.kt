package com.chartlite.app.cdss

import android.content.Context
import android.util.Log
import com.chartlite.app.model.*
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

/**
 * In-memory knowledge graph loaded from pre-processed BODHI JSON assets.
 * Provides condition, drug, lab, and symptom lookups for CDSS and extraction grounding.
 *
 * Source: https://github.com/eka-care/BODHI (CC BY-NC 4.0)
 */
class BodhiKnowledgeGraph(private val context: Context) {

    // Primary data
    private var conditionsById: Map<String, BodhiCondition> = emptyMap()
    private var drugsByHash: Map<String, BodhiDrug> = emptyMap()
    private var labs: List<BodhiLab> = emptyList()
    private var symptomsByCondition: Map<String, List<BodhiSymptomLink>> = emptyMap()

    // Derived indices
    private var conditionsByName: Map<String, BodhiCondition> = emptyMap()
    private var drugsByName: Map<String, BodhiDrug> = emptyMap()
    private var drugNameIndex: List<Pair<String, BodhiDrug>> = emptyList() // sorted by name length desc
    private var labsByCondition: Map<String, List<BodhiLab>> = emptyMap()

    // Precomputed ICD-10 → BODHI SNOMED mapping (hand-verified + high-confidence auto)
    private var icd10ToSnomed: Map<String, String> = emptyMap()

    @Volatile private var loaded = false
    private val gson = Gson()

    @Synchronized
    fun load(forceReload: Boolean = false) {
        if (loaded && !forceReload) return

        loadConditions()
        loadDrugs()
        loadLabs()
        loadSymptoms()
        loadIcd10Map()

        loaded = true
        Log.i(TAG, "BODHI loaded: ${conditionsById.size} conditions, " +
            "${drugsByHash.size} drugs, ${labs.size} labs, " +
            "${symptomsByCondition.size} condition-symptom mappings, " +
            "${icd10ToSnomed.size} ICD-10 mappings")
    }

    fun preload() {
        if (!loaded) load()
    }

    // ── Public Query Methods ──

    fun findConditionBySnomed(snomedId: String): BodhiCondition? =
        conditionsById[snomedId]

    fun findConditionByName(name: String): BodhiCondition? =
        conditionsByName[name.lowercase().trim()]

    /**
     * Resolve a Diagnosis (ICD-10 based) to a BODHI condition.
     * Uses the precomputed ICD-10 → SNOMED mapping (hand-verified + high-confidence auto),
     * falling back to exact name match on Disorder-type concepts only.
     * Returns null if no high-confidence match — callers should degrade gracefully.
     *
     * Deliberately strict: better to return null than a wrong match that produces
     * false clinical alerts.
     */
    fun findConditionForDiagnosis(diagnosis: Diagnosis): BodhiCondition? {
        // Primary: ICD-10 code lookup (known-good mapping)
        icd10ToSnomed[diagnosis.icd10Code]?.let { snomedId ->
            conditionsById[snomedId]?.let { return it }
        }
        // Secondary: exact name match, restricted to Disorder conceptType
        val descLower = diagnosis.description.lowercase().trim()
        val exact = conditionsByName[descLower]
        if (exact?.conceptType == "Disorder") return exact
        return null
    }

    /**
     * Fuzzy drug name lookup. Strips common formulation noise
     * (500mg, caps, tabs, oral, suspension) before matching against BODHI drug names.
     * Returns null if no unambiguous match.
     */
    fun findDrugByName(name: String): BodhiDrug? {
        val normalized = normalizeDrugName(name)
        // Exact match first
        drugsByName[normalized]?.let { return it }
        // Substring match: pick the longest BODHI drug name contained in the input.
        // Longest-first ensures "amoxicillin clavulanate" beats "amoxicillin" for
        // "amoxicillin-clavulanate 625mg tabs".
        for ((bodhiName, drug) in drugNameIndex) {
            if (bodhiName.length >= 5 && normalized.contains(bodhiName)) return drug
        }
        return null
    }

    private fun normalizeDrugName(name: String): String {
        var n = name.lowercase().trim()
        // Strip dosage patterns: "500mg", "2.5 ml", "10%"
        n = n.replace(Regex("\\d+(\\.\\d+)?\\s*(mg|mcg|g|ml|iu|%)"), " ")
        // Strip formulation words
        val noise = listOf(
            "tablet", "tablets", "tab", "tabs", "capsule", "capsules", "cap", "caps",
            "suspension", "syrup", "oral", "injection", "inj", "solution", "drops",
            "ointment", "cream", "gel", "patch", "spray"
        )
        for (w in noise) n = n.replace(Regex("\\b$w\\b"), " ")
        return n.replace(Regex("\\s+"), " ").trim()
    }

    fun getLabsForCondition(snomedId: String): List<BodhiLab> =
        labsByCondition[snomedId] ?: emptyList()

    fun getSpecialtiesForCondition(snomedId: String): List<BodhiSpecialtyLink> =
        conditionsById[snomedId]?.specialties ?: emptyList()

    fun getSymptomsForCondition(snomedId: String): List<BodhiSymptomLink> =
        symptomsByCondition[snomedId] ?: emptyList()

    val isLoaded: Boolean get() = loaded

    // ── Loading ──

    private fun loadConditions() {
        try {
            val json = readAsset("bodhi/bodhi_conditions.json")
            val type = object : TypeToken<List<BodhiCondition>>() {}.type
            val list: List<BodhiCondition> = gson.fromJson(json, type) ?: emptyList()
            conditionsById = list.associateBy { it.snomedId }
            conditionsByName = buildMap {
                for (c in list) {
                    put(c.name.lowercase().trim(), c)
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to load BODHI conditions", e)
        }
    }

    private fun loadDrugs() {
        try {
            val json = readAsset("bodhi/bodhi_drugs.json")
            val type = object : TypeToken<List<BodhiDrug>>() {}.type
            val list: List<BodhiDrug> = gson.fromJson(json, type) ?: emptyList()
            drugsByHash = list.associateBy { it.hash }
            drugsByName = buildMap {
                for (d in list) {
                    put(d.name.lowercase().trim(), d)
                }
            }
            // Sort by name length desc so longest match wins during substring lookup
            drugNameIndex = list
                .map { it.name.lowercase().trim() to it }
                .sortedByDescending { it.first.length }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to load BODHI drugs", e)
        }
    }

    private fun loadIcd10Map() {
        try {
            val json = readAsset("bodhi/icd10_snomed_map.json")
            val map = gson.fromJson(json, Icd10SnomedMap::class.java)
            icd10ToSnomed = map?.mappings?.mapValues { it.value.snomedId } ?: emptyMap()
        } catch (e: Exception) {
            Log.w(TAG, "Failed to load ICD-10 → SNOMED map", e)
        }
    }

    private fun loadLabs() {
        try {
            val json = readAsset("bodhi/bodhi_labs.json")
            val type = object : TypeToken<List<BodhiLab>>() {}.type
            labs = gson.fromJson(json, type) ?: emptyList()

            // Build reverse index: condition SNOMED ID -> list of labs
            val index = mutableMapOf<String, MutableList<BodhiLab>>()
            for (lab in labs) {
                lab.monitoredConditions?.forEach { link ->
                    index.getOrPut(link.snomedId) { mutableListOf() }.add(lab)
                }
            }
            labsByCondition = index
        } catch (e: Exception) {
            Log.w(TAG, "Failed to load BODHI labs", e)
        }
    }

    private fun loadSymptoms() {
        try {
            val json = readAsset("bodhi/bodhi_symptoms.json")
            val type = object : TypeToken<Map<String, List<BodhiSymptomLink>>>() {}.type
            symptomsByCondition = gson.fromJson(json, type) ?: emptyMap()
        } catch (e: Exception) {
            Log.w(TAG, "Failed to load BODHI symptoms", e)
        }
    }

    private fun readAsset(path: String): String =
        context.assets.open(path).bufferedReader().use { it.readText() }

    companion object {
        private const val TAG = "BodhiKnowledgeGraph"
    }
}
