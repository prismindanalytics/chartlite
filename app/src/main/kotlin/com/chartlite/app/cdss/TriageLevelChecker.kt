package com.chartlite.app.cdss

import com.chartlite.app.model.*

/**
 * Surfaces BODHI triage levels as advisory notices during review.
 *
 * BODHI's `emergency` level reflects *acute presentation severity* — appropriate
 * for triage at first contact, but noisy when applied to every routine PHC visit
 * of a known condition. We therefore:
 *   - Suppress `worrisome` entirely (223 conditions, mostly chronic-managed).
 *   - Route context-dependent emergencies (depression, headache, back pain) to
 *     INFO-level advisories — surface the knowledge without false-alarming.
 *   - Fire WARNING-level (not CRITICAL) for the remaining ~170 true emergencies
 *     with advisory wording — the clinician assesses acuity.
 */
class TriageLevelChecker(private val bodhiGraph: BodhiKnowledgeGraph) {

    fun check(diagnoses: List<Diagnosis>): List<CDSSAlert> {
        val alerts = mutableListOf<CDSSAlert>()
        val seen = mutableSetOf<String>()

        for (dx in diagnoses) {
            val condition = bodhiGraph.findConditionForDiagnosis(dx) ?: continue
            if (!seen.add(condition.snomedId)) continue
            if (condition.triageLevel?.lowercase() != "emergency") continue

            val isContextDependent = CONTEXT_DEPENDENT_EMERGENCIES.any { term ->
                condition.name.lowercase().contains(term)
            }

            alerts.add(
                CDSSAlert(
                    severity = if (isContextDependent) AlertSeverity.INFO else AlertSeverity.WARNING,
                    category = "Triage Advisory",
                    message = if (isContextDependent) {
                        "BODHI notes ${condition.name} can be emergent in acute presentation. Assess severity."
                    } else {
                        "BODHI flags ${condition.name} as potentially emergency. Assess acuity."
                    },
                    relatedField = "diagnoses"
                )
            )
        }
        return alerts
    }

    companion object {
        // Conditions BODHI flags as "emergency" that are routinely managed in PHC
        // or where severity is highly context-dependent. We route these to INFO
        // rather than WARNING to avoid demo-breaking false alarms.
        private val CONTEXT_DEPENDENT_EMERGENCIES = setOf(
            "depression", "anxiety", "panic",
            "back pain", "headache", "migraine", "tension",
            "chest pain", "abdominal pain",
            "dyspnea", "palpitation",
            "insomnia", "dysmenorrhea",
            "dehydration", "hypoglycemia"
        )
    }
}
