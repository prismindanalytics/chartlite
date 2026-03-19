package com.chartlite.app.extraction

import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonSyntaxException

/**
 * Orchestrates on-device vision extraction: image → VLM inference → structured clinical data.
 * Auto-detects content type (lab report, RDT, vitals, medication, referral).
 */
class VisionExtractor(
    private val modelManager: LlmModelManager,
    private val promptBuilder: ExtractionPromptBuilder
) {
    data class VitalReading(val name: String, val value: String, val unit: String)
    data class LabResult(val test: String, val result: String, val referenceRange: String? = null)
    data class RdtResult(val testType: String, val result: String, val details: String? = null)
    data class MedicationInfo(val name: String, val dose: String? = null, val form: String? = null, val expiry: String? = null)
    data class ReferralInfo(val fromFacility: String? = null, val diagnosis: String? = null, val reason: String? = null, val urgency: String? = null)

    data class VisionResult(
        val contentType: String,
        val vitals: List<VitalReading> = emptyList(),
        val investigations: List<LabResult> = emptyList(),
        val rdt: RdtResult? = null,
        val medications: List<MedicationInfo> = emptyList(),
        val referral: ReferralInfo? = null,
        val rawText: String? = null,
        val rawJson: String? = null  // For audit trail storage
    )

    suspend fun extract(imagePath: String, additionalContext: String = ""): VisionResult? {
        val system = promptBuilder.visionSystemPrompt()
        val user = promptBuilder.visionUserPrompt(additionalContext)

        Log.d(TAG, "Running vision extraction on: $imagePath")

        val raw = modelManager.runVisionInference(
            systemPrompt = system,
            userMessage = user,
            imagePath = imagePath,
            maxTokens = modelManager.recommendedOutputTokens(),
            config = LlmModelManager.GenerationConfig(
                temperature = 0.1f,
                topP = 0.95f,
                topK = 40,
                repeatPenalty = 1.0f
            )
        )

        if (raw.isNullOrBlank()) {
            Log.w(TAG, "Vision inference returned empty response")
            return null
        }

        Log.d(TAG, "Vision response: ${raw.length} chars")
        // Log first 500 chars for debugging model output format
        Log.d(TAG, "Vision raw (first 500): ${raw.take(500)}")
        return parseVisionJson(raw)
    }

    private fun parseVisionJson(raw: String): VisionResult? {
        // Strip thinking blocks if present
        val cleaned = raw.replace(Regex("<think>[\\s\\S]*?</think>"), "").trim()

        // Find JSON object
        val jsonStart = cleaned.indexOf('{')
        val jsonEnd = cleaned.lastIndexOf('}')
        if (jsonStart < 0 || jsonEnd <= jsonStart) {
            Log.w(TAG, "No JSON found in vision response, using text fallback")
            return textFallback(cleaned)
        }
        val jsonStr = cleaned.substring(jsonStart, jsonEnd + 1)

        return try {
            val gson = Gson()
            val obj = gson.fromJson(jsonStr, JsonObject::class.java)

            // Fuzzy field lookup — small models produce typos like "categoriess", "mediications"
            fun JsonObject.fuzzy(vararg candidates: String) =
                candidates.firstNotNullOfOrNull { key ->
                    // Exact match first, then prefix match (handles typos like extra letters)
                    this.get(key) ?: this.keySet().firstOrNull { k ->
                        k.startsWith(key.take(4)) || key.startsWith(k.take(4))
                    }?.let { this.get(it) }
                }

            val contentType = (obj.fuzzy("content_type", "category", "categories", "type")?.asString ?: "other")
                .replace(Regex("s+$"), "") // strip trailing 's' from typos

            val vitals = (obj.getAsJsonArray("vitals") ?: obj.getAsJsonArray("vital"))?.mapNotNull { elem ->
                val o = elem.asJsonObject
                val name = o.get("name")?.asString ?: return@mapNotNull null
                val value = o.get("value")?.asString ?: return@mapNotNull null
                val unit = o.get("unit")?.asString ?: ""
                VitalReading(name, value, unit)
            } ?: emptyList()

            val investigations = (obj.getAsJsonArray("investigations") ?: obj.getAsJsonArray("investigation"))?.mapNotNull { elem ->
                val o = elem.asJsonObject
                val test = o.get("test")?.asString ?: return@mapNotNull null
                val result = o.get("result")?.asString ?: return@mapNotNull null
                LabResult(test, result, o.get("reference_range")?.asString)
            } ?: emptyList()

            val rdt = obj.getAsJsonObject("rdt")?.let { r ->
                val testType = r.get("test_type")?.asString ?: return@let null
                val result = r.get("result")?.asString ?: return@let null
                val rawDetails = r.get("details")?.asString
                // Discard if model dumped schema junk into details
                val details = rawDetails?.takeIf { it.length < 200 && !it.contains("content_type") }
                RdtResult(testType, result, details)
            }

            val medications = (obj.getAsJsonArray("medications") ?: obj.getAsJsonArray("mediications") ?: obj.getAsJsonArray("medication"))?.mapNotNull { elem ->
                val o = elem.asJsonObject
                val name = o.get("name")?.asString ?: return@mapNotNull null
                MedicationInfo(name, o.get("dose")?.asString, o.get("form")?.asString, o.get("expiry")?.asString)
            } ?: emptyList()

            val referral = obj.getAsJsonObject("referral")?.let { r ->
                ReferralInfo(
                    r.get("from_facility")?.asString,
                    r.get("diagnosis")?.asString,
                    r.get("reason")?.asString,
                    r.get("urgency")?.asString
                )
            }

            val rawTextVal = obj.get("raw_text")?.asString
            val rawText = rawTextVal?.takeIf { it.length < 300 && !it.contains("content_type") }

            VisionResult(
                contentType = contentType,
                vitals = vitals,
                investigations = investigations,
                rdt = rdt,
                medications = medications,
                referral = referral,
                rawText = rawText,
                rawJson = jsonStr
            )
        } catch (e: JsonSyntaxException) {
            Log.w(TAG, "Failed to parse vision JSON: ${e.message}")
            null
        } catch (e: Exception) {
            Log.w(TAG, "Vision parse error: ${e.message}")
            null
        }
    }

    /** Fallback: wrap raw text description as a VisionResult so the UI can still show it. */
    private fun textFallback(text: String): VisionResult {
        // Try to detect content type from keywords
        val lower = text.lowercase()
        val contentType = when {
            lower.contains("rdt") || lower.contains("rapid test") || lower.contains("cassette") ||
                lower.contains("test line") || lower.contains("control line") -> "rdt_result"
            lower.contains("blood pressure") || lower.contains("temperature") ||
                lower.contains("pulse ox") || lower.contains("glucometer") -> "vital_device"
            lower.contains("lab") || lower.contains("cbc") || lower.contains("hemoglobin") ||
                lower.contains("wbc") || lower.contains("rbc") -> "lab_report"
            lower.contains("tablet") || lower.contains("capsule") || lower.contains("mg") ||
                lower.contains("medication") || lower.contains("drug") -> "medication_package"
            lower.contains("referral") || lower.contains("refer to") -> "referral_letter"
            else -> "other"
        }

        // Try to extract RDT result from text
        val rdt = if (contentType == "rdt_result") {
            val testType = when {
                lower.contains("malaria") || lower.contains("pf") || lower.contains("plasmodium") -> "malaria"
                lower.contains("hiv") -> "hiv"
                lower.contains("pregnan") || lower.contains("hcg") -> "pregnancy"
                else -> "other"
            }
            // Use regex to match "result is X" or "X result" patterns, avoiding echoed question text
            val result = when {
                lower.contains("no c line") || lower.contains("no control line") -> "invalid"
                Regex("result[:\\s]+negative|is negative|negative result|non-reactive|nonreactive").containsMatchIn(lower) ||
                    lower.contains("only c line") || lower.contains("only the c") || lower.contains("c line only") ||
                    lower.contains("one line visible") || lower.contains("only one line") -> "negative"
                Regex("result[:\\s]+positive|is positive|positive result|\\breactive\\b").containsMatchIn(lower) ||
                    lower.contains("c and t") || lower.contains("both lines") ||
                    lower.contains("two lines visible") || lower.contains("t line visible") -> "positive"
                else -> "unknown"
            }
            // Extract device/brand if mentioned
            val deviceMatch = Regex("(?i)(binaxnow|sd bioline|first response|determine|uni-gold|oraquick|sure check|accutest)", RegexOption.IGNORE_CASE).find(text)
            val details = deviceMatch?.value?.let { "Device: $it" }
            RdtResult(testType, result, details)
        } else null

        return VisionResult(
            contentType = contentType,
            rdt = rdt,
            rawText = text,
            rawJson = null
        )
    }

    companion object {
        private const val TAG = "VisionExtractor"
    }
}
