package com.chartlite.app.cdss

import android.util.Log
import com.chartlite.app.model.CDSSAlert
import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonObject

/**
 * Exposes the BODHI / CDSS safety checkers as a Gemma 4 function-calling
 * toolset. Used by the multimodal capture flow:
 *
 *   1. Vision extracts an artifact JSON (medication package, prescription, etc.)
 *   2. Gemma 4 sees the artifact + tool definitions, emits a JSON array of tool calls.
 *   3. We parse and execute deterministically against the existing CDSS layer.
 *   4. The UI shows: structured artifact + tool-call trace + safety alerts.
 *
 * Why JSON-as-tool-calling and not the cloud-Gemma function-calling API?
 *
 * Gemma 4 on-device (via MediaPipe LLM Inference) doesn't expose the
 * API-level function-calling that the cloud Gemma family does. Asking the
 * model to emit a structured JSON array of `{name, args}` is reliable on
 * E4B and reasonably reliable on E2B — empirically more so than freeform
 * tool reasoning at the small-model end of the spectrum.
 */
class CdssToolRegistry(private val cdss: StaticCDSS) {

    data class ToolDefinition(
        val name: String,
        val description: String,
        /** JSON-Schema-style description shown to the LLM. */
        val parametersSchema: String,
    )

    data class ToolCall(
        val name: String,
        /** Parsed args as a JsonObject; empty object if the LLM omitted them. */
        val args: JsonObject,
    )

    data class ToolCallResult(
        val name: String,
        val argsPretty: String,  // for the "tool trace" UI panel
        val alerts: List<CDSSAlert>,
        val notes: String? = null,  // e.g. "no alerts" or "error: ..."
    )

    val toolDefinitions: List<ToolDefinition> = listOf(
        ToolDefinition(
            name = "check_drug_drug_interactions",
            description = "Check the medication list against the drug-drug interaction table. Call when there are 2+ medications.",
            parametersSchema = """{"type":"object","properties":{"medications":{"type":"array","items":{"type":"string"}}},"required":["medications"]}""",
        ),
        ToolDefinition(
            name = "check_drug_allergy",
            description = "Cross-reference the medication list against patient allergies. Call when both medications and allergies are known.",
            parametersSchema = """{"type":"object","properties":{"medications":{"type":"array","items":{"type":"string"}},"allergies":{"type":"array","items":{"type":"string"}}},"required":["medications","allergies"]}""",
        ),
        ToolDefinition(
            name = "check_drug_condition",
            description = "For each medication, check whether the patient's diagnoses include a known indication for that drug (BODHI). Call when medications and diagnoses are both present.",
            parametersSchema = """{"type":"object","properties":{"medications":{"type":"array","items":{"type":"string"}},"diagnoses":{"type":"array","items":{"type":"string"}}},"required":["medications","diagnoses"]}""",
        ),
        ToolDefinition(
            name = "check_triage_urgency",
            description = "Look up BODHI's triage level for each diagnosis and surface any flagged emergency conditions. Call when diagnoses are present.",
            parametersSchema = """{"type":"object","properties":{"diagnoses":{"type":"array","items":{"type":"string"}}},"required":["diagnoses"]}""",
        ),
    )

    /**
     * Build the (system, user) pair that asks Gemma 4 to choose which tools
     * to invoke given the extracted artifact + patient context.
     *
     * The user message is intentionally compact — small on-device models
     * lose accuracy past ~2k tokens of preamble.
     */
    fun buildToolDecisionPrompt(
        extractedArtifactJson: String,
        patientAllergies: List<String>,
        patientPriorDiagnoses: List<String>,
    ): Pair<String, String> {
        val system = SYSTEM_PROMPT
        val user = buildString {
            appendLine("Available tools:")
            toolDefinitions.forEachIndexed { idx, t ->
                appendLine("${idx + 1}. ${t.name} — ${t.description}")
                appendLine("   schema: ${t.parametersSchema}")
            }
            appendLine()
            appendLine("Extracted clinical artifact (from photo):")
            appendLine(extractedArtifactJson)
            appendLine()
            appendLine("Patient allergies: ${if (patientAllergies.isEmpty()) "[]" else patientAllergies.joinToString(", ")}")
            appendLine("Patient prior diagnoses: ${if (patientPriorDiagnoses.isEmpty()) "[]" else patientPriorDiagnoses.joinToString(", ")}")
            appendLine()
            appendLine(OUTPUT_INSTRUCTIONS)
        }
        return system to user
    }

    /**
     * Parse a model's response into a structured list of tool calls.
     * Tolerant of preamble, markdown fences, and trailing chatter.
     * Drops calls whose `name` isn't one of our four registered tools.
     */
    fun parseToolCalls(modelOutput: String): List<ToolCall> {
        if (modelOutput.isBlank()) return emptyList()
        val cleaned = modelOutput.replace(MD_FENCE_REGEX, "").trim()
        val arrStart = cleaned.indexOf('[')
        val arrEnd = cleaned.lastIndexOf(']')
        if (arrStart < 0 || arrEnd <= arrStart) return emptyList()
        val arrStr = cleaned.substring(arrStart, arrEnd + 1)
        return try {
            val arr = gson.fromJson(arrStr, JsonArray::class.java) ?: return emptyList()
            arr.mapNotNull { elem ->
                if (!elem.isJsonObject) return@mapNotNull null
                val o = elem.asJsonObject
                val name = o.get("name")?.asString?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
                if (name !in TOOL_NAMES) return@mapNotNull null
                val args = o.getAsJsonObject("args")
                    ?: o.getAsJsonObject("arguments")
                    ?: JsonObject()
                ToolCall(name, args)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to parse tool calls: ${e.message}")
            emptyList()
        }
    }

    /**
     * Execute a list of tool calls deterministically. One
     * [ToolCallResult] per call; the input order is preserved so the UI
     * can show the trace top-to-bottom.
     */
    fun execute(calls: List<ToolCall>): List<ToolCallResult> = calls.map { call ->
        try {
            val alerts = dispatch(call)
            ToolCallResult(
                name = call.name,
                argsPretty = gson.toJson(call.args),
                alerts = alerts,
                notes = if (alerts.isEmpty()) "no alerts" else null,
            )
        } catch (e: Exception) {
            Log.e(TAG, "Tool call ${call.name} threw", e)
            ToolCallResult(
                name = call.name,
                argsPretty = gson.toJson(call.args),
                alerts = emptyList(),
                notes = "error: ${e.message}",
            )
        }
    }

    private fun dispatch(call: ToolCall): List<CDSSAlert> {
        val medications = call.args.getAsJsonArray("medications")?.mapNotNull { it.asString } ?: emptyList()
        val diagnoses = call.args.getAsJsonArray("diagnoses")?.mapNotNull { it.asString } ?: emptyList()
        val allergies = call.args.getAsJsonArray("allergies")?.mapNotNull { it.asString } ?: emptyList()
        return when (call.name) {
            "check_drug_drug_interactions" -> cdss.toolCheckDrugDrugInteractions(medications)
            "check_drug_allergy" -> cdss.toolCheckDrugAllergy(medications, allergies)
            "check_drug_condition" -> cdss.toolCheckDrugCondition(medications, diagnoses)
            "check_triage_urgency" -> cdss.toolCheckTriageUrgency(diagnoses)
            else -> emptyList()
        }
    }

    companion object {
        private const val TAG = "CdssToolRegistry"
        private val gson = Gson()
        private val MD_FENCE_REGEX = Regex("```(?:json)?\\s*|```")
        private val TOOL_NAMES = setOf(
            "check_drug_drug_interactions",
            "check_drug_allergy",
            "check_drug_condition",
            "check_triage_urgency",
        )

        private val SYSTEM_PROMPT = """
You are a clinical safety reasoner. You decide which deterministic CDSS
checks to run on a clinical artifact (medication package, handwritten
prescription, vaccine card, lab report, etc.) extracted from a photo.
You do NOT make clinical decisions yourself — your job is to pick the
right tools so the deterministic engine can.

Rules:
- Only call tools when the required inputs are present.
- Never invent a medication, diagnosis, or allergy that isn't in the artifact or patient record.
- It's fine to return [] when no tool is appropriate (e.g. a vaccine card with no medications).
- Return ONLY a JSON array of tool calls. No prose, no markdown.
        """.trimIndent()

        private val OUTPUT_INSTRUCTIONS = """
Return ONLY a JSON array of tool calls in this exact shape, with no
preamble or commentary:

[
  {"name": "<tool_name>", "args": { ... }}
]

Empty array [] is acceptable.
        """.trimIndent()
    }
}
