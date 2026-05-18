package com.chartlite.app.cdss

import android.content.Context
import android.util.Log
import com.chartlite.app.model.*
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

/**
 * Static Clinical Decision Support System.
 * Evaluates clinical rules on-device without connectivity.
 */
class StaticCDSS(
    private val context: Context,
    private val bodhiGraph: BodhiKnowledgeGraph? = null
) {

    private var allergyInteractions: Map<String, AllergyInteraction> = emptyMap()
    private var drugInteractions: List<DrugInteraction> = emptyList()
    private var vitalAlerts = VitalAlerts()
    private var dosageChecker = DosageChecker()
    @Volatile private var rulesLoaded = false

    // BODHI-powered checkers (active only when bodhiGraph is loaded)
    private val drugConditionChecker by lazy { bodhiGraph?.let { DrugConditionChecker(it) } }
    private val triageLevelChecker by lazy { bodhiGraph?.let { TriageLevelChecker(it) } }
    private val labRecommendationChecker by lazy { bodhiGraph?.let { LabRecommendationChecker(it) } }
    private val specialtyReferralChecker by lazy { bodhiGraph?.let { SpecialtyReferralChecker(it) } }

    private val gson = Gson()

    @Synchronized
    fun loadRules(forceReload: Boolean = false) {
        if (rulesLoaded && !forceReload) return
        loadAllergyRules()
        loadDrugInteractions()
        rulesLoaded = true
    }

    private fun ensureRulesLoaded() {
        if (!rulesLoaded) loadRules()
    }

    fun preload() {
        ensureRulesLoaded()
    }

    private fun loadAllergyRules() {
        try {
            val json = context.assets.open("cdss/allergy_interactions.json")
                .bufferedReader().use { it.readText() }
            val type = object : TypeToken<Map<String, AllergyInteraction>>() {}.type
            allergyInteractions = gson.fromJson(json, type) ?: emptyMap()
        } catch (e: Exception) {
            Log.w(TAG, "Failed to load allergy rules from assets, using hardcoded defaults", e)
            allergyInteractions = defaultAllergyInteractions()
        }
    }

    private fun loadDrugInteractions() {
        try {
            val json = context.assets.open("cdss/drug_interactions.json")
                .bufferedReader().use { it.readText() }
            val wrapper = gson.fromJson(json, DrugInteractionWrapper::class.java)
            drugInteractions = wrapper?.interactions ?: emptyList()
        } catch (e: Exception) {
            Log.w(TAG, "Failed to load drug interactions from assets, using hardcoded defaults", e)
            drugInteractions = defaultDrugInteractions()
        }
    }

    /**
     * Evaluate all CDSS rules for an encounter.
     * Returns list of alerts sorted by severity (critical first).
     */
    fun evaluate(encounter: StructuredEncounter, patientAllergies: List<String>): List<CDSSAlert> {
        ensureRulesLoaded()
        val alerts = mutableListOf<CDSSAlert>()

        // 1. Drug-allergy interactions (CRITICAL)
        alerts.addAll(checkAllergyInteractions(encounter.medications, patientAllergies))

        // 2. Drug-drug interactions
        alerts.addAll(checkDrugInteractions(encounter.medications))

        // 3. Dosage range checks
        alerts.addAll(dosageChecker.check(encounter.medications))

        // 4. Vital sign alerts
        encounter.vitals?.let { alerts.addAll(vitalAlerts.check(it)) }

        // 5-8. BODHI knowledge graph checks (optional — graceful if BODHI not loaded)
        val allDiagnoses = encounter.diagnoses + encounter.suggestedDiagnoses
        if (allDiagnoses.isNotEmpty()) {
            drugConditionChecker?.let { alerts.addAll(it.check(encounter.medications, allDiagnoses)) }
            triageLevelChecker?.let { alerts.addAll(it.check(allDiagnoses)) }
            labRecommendationChecker?.let { alerts.addAll(it.check(allDiagnoses, encounter.investigations)) }
            specialtyReferralChecker?.let { alerts.addAll(it.suggest(allDiagnoses)) }
        }

        return alerts.sortedBy { alert ->
            when (alert.severity) {
                AlertSeverity.CRITICAL -> 0
                AlertSeverity.WARNING -> 1
                AlertSeverity.INFO -> 2
            }
        }
    }

    private fun checkAllergyInteractions(
        medications: List<Medication>,
        patientAllergies: List<String>
    ): List<CDSSAlert> {
        val alerts = mutableListOf<CDSSAlert>()

        for (allergy in patientAllergies) {
            val allergyLower = allergy.lowercase()
            val interaction = allergyInteractions[allergyLower] ?: continue

            for (med in medications) {
                val medNameLower = med.name.lowercase()
                // Match by formulary code OR drug name
                val isContraindicated = med.formularyCode in interaction.contraindicated ||
                    interaction.contraindicatedNames.any { medNameLower.contains(it.lowercase()) }

                if (isContraindicated) {
                    alerts.add(
                        CDSSAlert(
                            severity = AlertSeverity.CRITICAL,
                            category = "Drug-Allergy",
                            message = interaction.message.replace("{drug}", med.name),
                            relatedField = "medications"
                        )
                    )
                }
                // Check cross-reactivity: e.g. penicillin allergy → cephalosporin warning
                val isCrossReactive = (interaction.crossReactivity.isNotEmpty() &&
                    med.formularyCode in interaction.crossReactivity) ||
                    interaction.crossReactivityNames.any { medNameLower.contains(it.lowercase()) }

                if (isCrossReactive) {
                    alerts.add(
                        CDSSAlert(
                            severity = AlertSeverity.WARNING,
                            category = "Drug-Allergy Cross-Reactivity",
                            message = "Patient has ${interaction.allergen} allergy. ${med.name} may cross-react (~5-10% risk). Consider alternative.",
                            relatedField = "medications"
                        )
                    )
                }
            }
        }
        return alerts
    }

    private fun checkDrugInteractions(medications: List<Medication>): List<CDSSAlert> {
        val alerts = mutableListOf<CDSSAlert>()
        // Exclude empty codes — EncounterMerger can produce "" for ungrounded meds,
        // and many interaction rules also have empty drug codes. "" in codes would
        // match EVERY such rule, producing dozens of false positive alerts.
        val codes = medications.mapNotNull { it.formularyCode.ifBlank { null } }.toSet()
        val names = medications.map { it.name.lowercase() }.toSet()

        for (interaction in drugInteractions) {
            // Match by formulary code (if non-empty) OR drug name
            val match1 = (interaction.drug1.isNotBlank() && interaction.drug1 in codes) ||
                interaction.drugName1?.let { dn -> dn.isNotBlank() && names.any { it.contains(dn.lowercase()) } } == true
            val match2 = (interaction.drug2.isNotBlank() && interaction.drug2 in codes) ||
                interaction.drugName2?.let { dn -> dn.isNotBlank() && names.any { it.contains(dn.lowercase()) } } == true

            if (match1 && match2) {
                val severity = when (interaction.severity) {
                    "high" -> AlertSeverity.CRITICAL
                    "medium" -> AlertSeverity.WARNING
                    else -> AlertSeverity.INFO
                }
                alerts.add(
                    CDSSAlert(
                        severity = severity,
                        category = "Drug-Drug",
                        message = interaction.message,
                        relatedField = "medications"
                    )
                )
            }
        }
        return alerts
    }

    // Hardcoded defaults in case asset files aren't loaded
    private fun defaultAllergyInteractions(): Map<String, AllergyInteraction> = mapOf(
        "penicillin" to AllergyInteraction(
            allergen = "penicillin",
            contraindicated = listOf("0001", "0003", "0004", "0005"),
            contraindicatedNames = listOf(
                "amoxicillin", "ampicillin", "flucloxacillin", "penicillin",
                "cloxacillin", "piperacillin", "amoxicillin-clavulanate", "co-amoxiclav"
            ),
            crossReactivity = listOf("cephalosporins_1st_gen"),
            crossReactivityNames = listOf("cephalexin", "cefazolin", "cefadroxil"),
            severity = "high",
            message = "Patient has penicillin allergy. {drug} is a penicillin-type antibiotic."
        ),
        "sulfa" to AllergyInteraction(
            allergen = "sulfa",
            contraindicated = listOf("0050", "0051"),
            contraindicatedNames = listOf(
                "cotrimoxazole", "sulfamethoxazole", "trimethoprim-sulfamethoxazole",
                "tmp-smx", "bactrim", "septrin", "sulfadiazine", "sulfasalazine", "dapsone"
            ),
            crossReactivity = emptyList(),
            crossReactivityNames = listOf("furosemide", "hydrochlorothiazide", "thiazide"),
            severity = "high",
            message = "Patient has sulfa allergy. {drug} contains sulfonamide."
        )
    )

    private fun defaultDrugInteractions(): List<DrugInteraction> = listOf(
        DrugInteraction(drug1 = "0100", drug2 = "0101", drugName1 = "warfarin", drugName2 = "aspirin", severity = "high", message = "Warfarin + Aspirin: increased bleeding risk."),
        DrugInteraction(drug1 = "0002", drug2 = "0200", drugName1 = "metformin", drugName2 = "contrast", severity = "high", message = "Hold Metformin 48hrs before/after contrast.")
    )

    private data class DrugInteractionWrapper(val interactions: List<DrugInteraction>)

    // ── Function-calling tool surface ──
    //
    // The multimodal capture flow asks Gemma 4 to emit tool calls as JSON; the
    // LLM hands us simple string lists (no formulary codes, no ICD-10). These
    // wrappers wrap raw strings into the model objects expected by the
    // underlying checkers, so CdssToolRegistry can dispatch by name.
    //
    // Each existing checker's name-based fallback path means an empty
    // formularyCode / icd10Code is fine — the BODHI graph still resolves by
    // drug name + diagnosis description.

    fun toolCheckDrugDrugInteractions(medicationNames: List<String>): List<CDSSAlert> {
        ensureRulesLoaded()
        val meds = medicationNames.map { Medication(formularyCode = "", name = it) }
        return checkDrugInteractions(meds)
    }

    fun toolCheckDrugAllergy(
        medicationNames: List<String>,
        allergies: List<String>,
    ): List<CDSSAlert> {
        ensureRulesLoaded()
        val meds = medicationNames.map { Medication(formularyCode = "", name = it) }
        return checkAllergyInteractions(meds, allergies)
    }

    fun toolCheckDrugCondition(
        medicationNames: List<String>,
        diagnosisDescriptions: List<String>,
    ): List<CDSSAlert> {
        val checker = drugConditionChecker ?: return emptyList()
        val meds = medicationNames.map { Medication(formularyCode = "", name = it) }
        val dxs = diagnosisDescriptions.map { Diagnosis(icd10Code = "", description = it) }
        return checker.check(meds, dxs)
    }

    fun toolCheckTriageUrgency(diagnosisDescriptions: List<String>): List<CDSSAlert> {
        val checker = triageLevelChecker ?: return emptyList()
        val dxs = diagnosisDescriptions.map { Diagnosis(icd10Code = "", description = it) }
        return checker.check(dxs)
    }

    companion object {
        private const val TAG = "StaticCDSS"
    }
}
