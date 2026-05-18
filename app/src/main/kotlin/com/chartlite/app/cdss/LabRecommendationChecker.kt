package com.chartlite.app.cdss

import com.chartlite.app.model.*

/**
 * Suggests relevant lab investigations for diagnosed conditions
 * based on BODHI-M condition→lab monitoring edges.
 */
class LabRecommendationChecker(private val bodhiGraph: BodhiKnowledgeGraph) {

    fun check(
        diagnoses: List<Diagnosis>,
        existingInvestigations: List<Investigation>
    ): List<CDSSAlert> {
        if (diagnoses.isEmpty()) return emptyList()

        val existingLabNames = existingInvestigations.map { it.test.lowercase().trim() }.toSet()
        val alerts = mutableListOf<CDSSAlert>()
        val suggestedLabIds = mutableSetOf<String>() // Dedup across conditions

        for (dx in diagnoses) {
            val condition = bodhiGraph.findConditionForDiagnosis(dx) ?: continue
            val recommendedLabs = bodhiGraph.getLabsForCondition(condition.snomedId)
            if (recommendedLabs.isEmpty()) continue

            val newLabs = recommendedLabs.filter { lab ->
                lab.loincId !in suggestedLabIds &&
                    !existingLabNames.any { existing ->
                        val labName = (lab.displayName ?: lab.name).lowercase()
                        existing.contains(labName) || labName.contains(existing)
                    }
            }

            if (newLabs.isEmpty()) continue

            // Cap at 3 per condition to avoid wall-of-text in alert banner
            val top = newLabs.take(3)
            top.forEach { suggestedLabIds.add(it.loincId) }

            val labNames = top.joinToString(", ") { it.displayName ?: it.name }
            alerts.add(
                CDSSAlert(
                    severity = AlertSeverity.INFO,
                    category = "Lab Recommendation",
                    message = "For ${condition.name}: consider ordering $labNames.",
                    relatedField = "investigations"
                )
            )
        }
        return alerts
    }
}
