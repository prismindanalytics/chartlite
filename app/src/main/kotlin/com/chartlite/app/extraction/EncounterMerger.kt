package com.chartlite.app.extraction

import com.chartlite.app.model.Investigation
import com.chartlite.app.model.StructuredEncounter
import com.chartlite.app.model.VitalSigns

/**
 * Merges multiple snippet-based extractions into a single accumulated encounter.
 *
 * Used in snippet recording mode: clinician dictates short clinical phrases
 * ("BP 168/98, pulse 92"), each snippet is extracted independently, then
 * merged here into a running encounter that accumulates all clinical facts.
 *
 * Merge rules:
 * - Medications: union by formularyCode, keep highest confidence per drug
 * - Diagnoses: union by icd10Code, keep highest confidence per code
 * - Vitals: later values override earlier (null = not mentioned, doesn't override)
 * - Allergies: union (distinct)
 * - Follow-up / Referral: last non-null wins
 * - Transcript: concatenated with newline
 * - Confidence: weighted average (base weighted by its snippet count)
 */
object EncounterMerger {

    /**
     * Merge a new snippet extraction into the accumulated encounter.
     *
     * @param base The accumulated encounter so far (from previous snippets)
     * @param snippet The newly extracted snippet
     * @return A new StructuredEncounter combining both
     */
    fun merge(base: StructuredEncounter, snippet: StructuredEncounter): StructuredEncounter {
        return StructuredEncounter(
            id = base.id,
            patientId = base.patientId,
            providerId = base.providerId,
            facilityId = base.facilityId,
            timestamp = base.timestamp,
            transcript = listOf(base.transcript, snippet.transcript)
                .filter { it.isNotBlank() }
                .joinToString("\n"),
            medications = mergeMedications(base.medications, snippet.medications),
            diagnoses = mergeDiagnoses(base.diagnoses, snippet.diagnoses),
            vitals = mergeVitals(base.vitals, snippet.vitals),
            allergies = (base.allergies + snippet.allergies).distinct(),
            followUp = snippet.followUp ?: base.followUp,
            referral = snippet.referral ?: base.referral,
            freeTextNote = listOf(base.freeTextNote, snippet.freeTextNote)
                .filter { it.isNotBlank() }
                .joinToString("\n"),
            extractionConfidence = (base.extractionConfidence + snippet.extractionConfidence) / 2f,
            // Benchmark-driven categories: accumulate across snippets
            examFindings = (base.examFindings + snippet.examFindings).distinct(),
            investigations = mergeInvestigations(base.investigations, snippet.investigations),
            plan = (base.plan + snippet.plan).distinct(),
            socialHistory = (base.socialHistory + snippet.socialHistory).distinct(),
            suggestedDiagnoses = mergeDiagnoses(base.suggestedDiagnoses, snippet.suggestedDiagnoses)
        )
    }

    /**
     * Merge medications: union by formularyCode, keeping higher confidence when duplicate.
     */
    private fun mergeMedications(
        base: List<com.chartlite.app.model.Medication>,
        snippet: List<com.chartlite.app.model.Medication>
    ): List<com.chartlite.app.model.Medication> {
        val byCode = LinkedHashMap<String, com.chartlite.app.model.Medication>()

        // Base medications first
        for (med in base) {
            byCode[med.formularyCode] = med
        }

        // Snippet medications: override if higher confidence or new
        for (med in snippet) {
            val existing = byCode[med.formularyCode]
            if (existing == null || med.confidence > existing.confidence) {
                byCode[med.formularyCode] = med
            }
        }

        return byCode.values.toList()
    }

    /**
     * Merge diagnoses: union by ICD-10 code, keeping higher confidence when duplicate.
     * Preserves isPrimary from whichever entry has higher confidence.
     */
    private fun mergeDiagnoses(
        base: List<com.chartlite.app.model.Diagnosis>,
        snippet: List<com.chartlite.app.model.Diagnosis>
    ): List<com.chartlite.app.model.Diagnosis> {
        val byCode = LinkedHashMap<String, com.chartlite.app.model.Diagnosis>()

        for (dx in base) {
            byCode[dx.icd10Code] = dx
        }

        for (dx in snippet) {
            val existing = byCode[dx.icd10Code]
            if (existing == null || dx.confidence > existing.confidence) {
                byCode[dx.icd10Code] = dx
            }
        }

        return byCode.values.toList()
    }

    /**
     * Merge investigations: union by test name, snippet result overrides if both have same test.
     */
    private fun mergeInvestigations(
        base: List<Investigation>,
        snippet: List<Investigation>
    ): List<Investigation> {
        val byTest = LinkedHashMap<String, Investigation>()
        for (inv in base) { byTest[inv.test.lowercase()] = inv }
        for (inv in snippet) { byTest[inv.test.lowercase()] = inv }
        return byTest.values.toList()
    }

    /**
     * Merge vitals: newer snippet values override base values.
     * Null fields in snippet mean "not mentioned" and don't override.
     */
    fun mergeVitals(base: VitalSigns?, snippet: VitalSigns?): VitalSigns? {
        if (base == null) return snippet
        if (snippet == null) return base

        return VitalSigns(
            systolicBP = snippet.systolicBP ?: base.systolicBP,
            diastolicBP = snippet.diastolicBP ?: base.diastolicBP,
            temperature = snippet.temperature ?: base.temperature,
            pulse = snippet.pulse ?: base.pulse,
            weight = snippet.weight ?: base.weight,
            height = snippet.height ?: base.height,
            respiratoryRate = snippet.respiratoryRate ?: base.respiratoryRate,
            oxygenSaturation = snippet.oxygenSaturation ?: base.oxygenSaturation
        )
    }
}
