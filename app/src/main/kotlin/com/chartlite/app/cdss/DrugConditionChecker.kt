package com.chartlite.app.cdss

import com.chartlite.app.model.*

/**
 * Validates that prescribed medications have a known indication
 * for the diagnosed conditions using BODHI-M drug→condition mappings.
 */
class DrugConditionChecker(private val bodhiGraph: BodhiKnowledgeGraph) {

    fun check(medications: List<Medication>, diagnoses: List<Diagnosis>): List<CDSSAlert> {
        if (medications.isEmpty() || diagnoses.isEmpty()) return emptyList()

        // Resolve all diagnoses to BODHI condition SNOMED IDs
        val diagnosedConditionIds = diagnoses.mapNotNull { dx ->
            bodhiGraph.findConditionForDiagnosis(dx)?.snomedId
        }.toSet()

        // If we couldn't resolve any diagnosis, skip check entirely
        if (diagnosedConditionIds.isEmpty()) return emptyList()

        val alerts = mutableListOf<CDSSAlert>()
        for (med in medications) {
            val bodhiDrug = bodhiGraph.findDrugByName(med.name) ?: continue
            val treatedConditions = bodhiDrug.treatedConditions ?: continue

            // Check if any diagnosed condition overlaps with the drug's indications
            val hasIndication = treatedConditions.any { it in diagnosedConditionIds }
            if (!hasIndication) {
                alerts.add(
                    CDSSAlert(
                        severity = AlertSeverity.WARNING,
                        category = "Drug-Condition",
                        message = "${med.name}: no known indication for current diagnoses. Verify prescription.",
                        relatedField = "medications"
                    )
                )
            }
        }
        return alerts
    }
}
