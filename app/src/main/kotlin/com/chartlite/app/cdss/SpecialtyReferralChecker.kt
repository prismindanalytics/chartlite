package com.chartlite.app.cdss

import com.chartlite.app.model.*

/**
 * Suggests specialist referrals based on BODHI-S condition→specialty mappings.
 */
class SpecialtyReferralChecker(private val bodhiGraph: BodhiKnowledgeGraph) {

    companion object {
        // Don't suggest referral to these — the user is likely already a GP/internist
        private val EXCLUDED_SPECIALTIES = setOf(
            "general practice",
            "general practitioner",
            "internal medicine",
            "family medicine",
            "primary care"
        )
    }

    fun suggest(diagnoses: List<Diagnosis>): List<CDSSAlert> {
        if (diagnoses.isEmpty()) return emptyList()

        val alerts = mutableListOf<CDSSAlert>()
        val suggestedSpecialties = mutableSetOf<String>()

        for (dx in diagnoses) {
            val condition = bodhiGraph.findConditionForDiagnosis(dx) ?: continue
            val specialties = bodhiGraph.getSpecialtiesForCondition(condition.snomedId)
            if (specialties.isEmpty()) continue

            // Take the top specialty (highest weight) that isn't GP/internal medicine
            val topSpecialty = specialties.firstOrNull { spec ->
                spec.name.lowercase() !in EXCLUDED_SPECIALTIES &&
                    spec.name.lowercase() !in suggestedSpecialties
            } ?: continue

            suggestedSpecialties.add(topSpecialty.name.lowercase())
            alerts.add(
                CDSSAlert(
                    severity = AlertSeverity.INFO,
                    category = "Referral Suggestion",
                    message = "For ${condition.name}: consider referral to ${topSpecialty.name}.",
                    relatedField = "referral"
                )
            )
        }
        return alerts
    }
}
