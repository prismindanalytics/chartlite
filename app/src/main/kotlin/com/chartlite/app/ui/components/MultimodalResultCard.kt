package com.chartlite.app.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.chartlite.app.cdss.CdssToolRegistry
import com.chartlite.app.extraction.VisionExtractor
import com.chartlite.app.model.AlertSeverity
import com.chartlite.app.model.CDSSAlert

/**
 * Polished result card for the multimodal capture flow.
 *
 * Layout (top → bottom):
 *   1. Header: artifact-type label, item name, confidence, warnings.
 *   2. Structured fields per category (only sections present in the result).
 *   3. Tool-call trace ("Gemma 4 chose to run check_drug_drug_interactions(...)").
 *   4. Safety alerts (severity-colored).
 *   5. Actions: [Add to encounter] [Discard].
 *
 * Used inside an [AlertDialog] in the encounter screen.
 */
@Composable
fun MultimodalResultCard(
    result: VisionExtractor.VisionResult,
    toolCalls: List<CdssToolRegistry.ToolCallResult>,
    alerts: List<CDSSAlert>,
    onAdd: () -> Unit,
    onDiscard: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // 1. Header
        ArtifactHeader(result)

        // 2. Per-section structured data
        ArtifactBody(result)

        // 3. Tool-call trace
        ToolCallTrace(toolCalls)

        // 4. Safety alerts
        SafetyAlertsList(alerts)

        // 5. Actions
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedButton(
                onClick = onDiscard,
                modifier = Modifier.weight(1f),
            ) {
                Text("Discard")
            }
            Button(
                onClick = onAdd,
                modifier = Modifier.weight(1f),
            ) {
                Text("Add to encounter")
            }
        }
    }
}

@Composable
private fun ArtifactHeader(result: VisionExtractor.VisionResult) {
    val typeLabel = friendlyContentType(result.contentType)
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer,
        ),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = typeLabel,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            result.itemName?.takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.bodyMedium)
            }
            // Suppress confidence when the model didn't fill it (null) or
            // emitted the schema's literal placeholder (0.0) — showing
            // "Confidence: 0%" reads as a broken model, not a real signal.
            result.confidence?.takeIf { it > 0.0 }?.let { c ->
                Text(
                    text = "Confidence: ${(c * 100).toInt()}%",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f),
                )
            }
            if (result.warnings.isNotEmpty()) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.Top,
                ) {
                    Icon(
                        Icons.Default.Warning,
                        contentDescription = null,
                        modifier = Modifier.size(14.dp),
                        tint = MaterialTheme.colorScheme.error,
                    )
                    Text(
                        text = result.warnings.joinToString("; "),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        }
    }
}

@Composable
private fun ArtifactBody(result: VisionExtractor.VisionResult) {
    // Render only the sections that have content. Each artifact type only
    // populates the fields relevant to it, so this works as a unified
    // renderer across all 8 types.

    result.rdt?.let { rdt ->
        Section("RDT") {
            Text("Test: ${rdt.testType}")
            Text(
                "Result: ${rdt.result.uppercase()}",
                style = MaterialTheme.typography.titleMedium,
                color = when (rdt.result.lowercase()) {
                    "positive" -> MaterialTheme.colorScheme.error
                    "negative" -> MaterialTheme.colorScheme.primary
                    else -> MaterialTheme.colorScheme.onSurface
                },
            )
            rdt.details?.takeIf { it.isNotBlank() && it.length < 200 }?.let {
                Text(it, style = MaterialTheme.typography.bodySmall)
            }
        }
    }

    if (result.vitals.isNotEmpty()) {
        Section("Vitals") {
            result.vitals.forEach { v ->
                Text("${v.name}: ${v.value} ${v.unit}".trim())
            }
        }
    }

    if (result.investigations.isNotEmpty()) {
        Section("Lab results") {
            result.investigations.forEach { lab ->
                val flag = lab.flag?.takeIf { it.isNotBlank() && it.lowercase() != "n" }
                val flagColor = when (flag?.uppercase()) {
                    "H" -> MaterialTheme.colorScheme.error
                    "L" -> MaterialTheme.colorScheme.tertiary
                    else -> MaterialTheme.colorScheme.onSurface
                }
                val unit = lab.unit?.let { " $it" } ?: ""
                val ref = lab.referenceRange?.let { " (ref: $it)" } ?: ""
                val flagSuffix = flag?.let { " [$it]" } ?: ""
                Text(
                    text = "${lab.test}: ${lab.result}$unit$ref$flagSuffix",
                    color = flagColor,
                )
            }
        }
    }

    if (result.medications.isNotEmpty()) {
        Section("Medications") {
            result.medications.forEach { med ->
                val parts = listOfNotNull(
                    med.name,
                    med.dose,
                    med.route,
                    med.freq,
                    med.duration?.let { "× $it" },
                ).joinToString(" ")
                Text(parts)
                listOfNotNull(
                    med.expiry?.let { "exp $it" },
                    med.batch?.let { "batch $it" },
                    med.manufacturer,
                ).takeIf { it.isNotEmpty() }?.let { line ->
                    Text(
                        line.joinToString(" · "),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }

    result.referral?.let { ref ->
        if (listOf(ref.fromFacility, ref.diagnosis, ref.reason, ref.urgency).any { !it.isNullOrBlank() }) {
            Section("Referral") {
                ref.fromFacility?.takeIf { it.isNotBlank() }?.let { Text("From: $it") }
                ref.diagnosis?.takeIf { it.isNotBlank() }?.let { Text("Diagnosis: $it") }
                ref.reason?.takeIf { it.isNotBlank() }?.let { Text("Reason: $it") }
                ref.urgency?.takeIf { it.isNotBlank() }?.let {
                    Text(
                        "Urgency: $it",
                        color = if (it.lowercase().contains("urgent")) MaterialTheme.colorScheme.error
                                else MaterialTheme.colorScheme.onSurface,
                    )
                }
            }
        }
    }

    if (result.immunizations.isNotEmpty()) {
        Section("Immunisations") {
            result.immunizations.forEach { imm ->
                val parts = listOfNotNull(
                    imm.vaccine,
                    imm.doseNumber?.let { "dose $it" },
                    imm.date,
                    imm.route,
                ).joinToString(" · ")
                Text(parts)
                imm.batch?.takeIf { it.isNotBlank() }?.let {
                    Text(
                        "batch $it",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }

    result.discharge?.let { d ->
        if (d.dx.isNotEmpty() || d.meds.isNotEmpty() || !d.followUp.isNullOrBlank() || d.alerts.isNotEmpty()) {
            Section("Discharge") {
                if (d.dx.isNotEmpty()) Text("Dx: " + d.dx.joinToString(", "))
                if (d.meds.isNotEmpty()) {
                    Text("Meds:")
                    d.meds.forEach { Text("  • $it", style = MaterialTheme.typography.bodySmall) }
                }
                d.followUp?.takeIf { it.isNotBlank() }?.let { Text("Follow-up: $it") }
                d.alerts.forEach { alertText ->
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.Top,
                    ) {
                        Icon(
                            Icons.Default.Warning,
                            contentDescription = null,
                            modifier = Modifier.size(14.dp),
                            tint = MaterialTheme.colorScheme.error,
                        )
                        Text(alertText, color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        }
    }

    // Final fallback: only show raw text if no structured section rendered.
    val anyStructured = result.rdt != null ||
        result.vitals.isNotEmpty() ||
        result.investigations.isNotEmpty() ||
        result.medications.isNotEmpty() ||
        result.referral != null ||
        result.immunizations.isNotEmpty() ||
        result.discharge != null
    if (!anyStructured) {
        result.rawText?.takeIf { it.isNotBlank() }?.let {
            Section("Raw text") {
                Text(it.take(400), style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun ToolCallTrace(toolCalls: List<CdssToolRegistry.ToolCallResult>) {
    if (toolCalls.isEmpty()) {
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant,
            ),
        ) {
            Text(
                // Reads as "the model decided no checks were warranted" rather
                // than "the model gave up" — important for artifacts like
                // vaccine cards where zero safety calls is the correct answer.
                "No interaction checks needed for this artifact.",
                modifier = Modifier.padding(12.dp),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        return
    }
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant,
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                "Safety checks Gemma 4 chose to run",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.SemiBold,
            )
            toolCalls.forEach { call ->
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(
                        text = "→ ${friendlyToolName(call.name)}",
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.Medium,
                    )
                    Text(
                        text = "   ${humaniseArgs(call.argsPretty)}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    val summary = call.notes
                        ?: "${call.alerts.size} alert${if (call.alerts.size == 1) "" else "s"}"
                    Text(
                        text = "   → $summary",
                        style = MaterialTheme.typography.labelSmall,
                        color = if (call.alerts.isNotEmpty()) MaterialTheme.colorScheme.error
                                else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

/** snake_case tool id → judge-friendly title. */
private fun friendlyToolName(raw: String): String = when (raw) {
    "check_drug_drug_interactions" -> "Drug-drug interactions"
    "check_drug_allergy" -> "Drug-allergy"
    "check_drug_condition" -> "Drug-condition match"
    "check_triage_urgency" -> "Triage urgency"
    else -> raw.replace("_", " ").replaceFirstChar { it.uppercase() }
}

/**
 * Convert a tool's JSON args (`{"medications":["amoxicillin"],"allergies":["penicillin"]}`)
 * into a single readable line: `medications=[amoxicillin], allergies=[penicillin]`.
 * Falls back to the raw JSON when parsing fails.
 */
private fun humaniseArgs(argsJson: String): String {
    return try {
        val obj = com.google.gson.JsonParser.parseString(argsJson)
        if (!obj.isJsonObject) return argsJson
        val parts = obj.asJsonObject.entrySet().mapNotNull { (key, value) ->
            if (value.isJsonArray) {
                val items = value.asJsonArray.mapNotNull { it.asString }
                if (items.isEmpty()) null else "$key=[${items.joinToString(", ")}]"
            } else if (value.isJsonPrimitive) {
                "$key=${value.asString}"
            } else null
        }
        if (parts.isEmpty()) "(no args)" else parts.joinToString(", ")
    } catch (e: Exception) {
        argsJson
    }
}

@Composable
private fun SafetyAlertsList(alerts: List<CDSSAlert>) {
    if (alerts.isEmpty()) return
    val sorted = alerts.sortedBy {
        when (it.severity) {
            AlertSeverity.CRITICAL -> 0
            AlertSeverity.WARNING -> 1
            AlertSeverity.INFO -> 2
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            "Safety alerts",
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
        )
        sorted.forEach { alert ->
            val (bg, fg, icon) = when (alert.severity) {
                AlertSeverity.CRITICAL -> Triple(
                    MaterialTheme.colorScheme.errorContainer,
                    MaterialTheme.colorScheme.onErrorContainer,
                    Icons.Default.Warning,
                )
                AlertSeverity.WARNING -> Triple(
                    MaterialTheme.colorScheme.tertiaryContainer,
                    MaterialTheme.colorScheme.onTertiaryContainer,
                    Icons.Default.Info,
                )
                AlertSeverity.INFO -> Triple(
                    MaterialTheme.colorScheme.surfaceVariant,
                    MaterialTheme.colorScheme.onSurfaceVariant,
                    Icons.Default.CheckCircle,
                )
            }
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = bg),
            ) {
                Row(
                    modifier = Modifier.padding(10.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.Top,
                ) {
                    Icon(icon, contentDescription = null, tint = fg, modifier = Modifier.size(18.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            alert.category,
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = fg,
                        )
                        Text(
                            alert.message,
                            style = MaterialTheme.typography.bodySmall,
                            color = fg,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun Section(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(
            title,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
        )
        content()
    }
}

private fun friendlyContentType(raw: String): String = when (raw) {
    "lab_report" -> "Lab Report"
    "rdt_cassette" -> "RDT Result"
    "vital_device" -> "Vital Signs"
    "medication_package" -> "Medication"
    "referral_letter" -> "Referral Letter"
    "vaccine_card" -> "Vaccine Card"
    "handwritten_prescription" -> "Handwritten Prescription"
    "discharge_summary" -> "Discharge Summary"
    "unknown" -> "Unknown artifact"
    else -> raw.replace("_", " ").replaceFirstChar { it.uppercase() }
}
