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
        return parseVisionJson(raw)
    }

    private fun parseVisionJson(raw: String): VisionResult? {
        // Strip thinking blocks if present
        val cleaned = raw.replace(Regex("<think>[\\s\\S]*?</think>"), "").trim()

        // Find JSON object
        val jsonStart = cleaned.indexOf('{')
        val jsonEnd = cleaned.lastIndexOf('}')
        if (jsonStart < 0 || jsonEnd <= jsonStart) {
            Log.w(TAG, "No JSON found in vision response")
            return null
        }
        val jsonStr = cleaned.substring(jsonStart, jsonEnd + 1)

        return try {
            val gson = Gson()
            val obj = gson.fromJson(jsonStr, JsonObject::class.java)

            val contentType = obj.get("content_type")?.asString ?: "other"

            val vitals = obj.getAsJsonArray("vitals")?.mapNotNull { elem ->
                val o = elem.asJsonObject
                val name = o.get("name")?.asString ?: return@mapNotNull null
                val value = o.get("value")?.asString ?: return@mapNotNull null
                val unit = o.get("unit")?.asString ?: ""
                VitalReading(name, value, unit)
            } ?: emptyList()

            val investigations = obj.getAsJsonArray("investigations")?.mapNotNull { elem ->
                val o = elem.asJsonObject
                val test = o.get("test")?.asString ?: return@mapNotNull null
                val result = o.get("result")?.asString ?: return@mapNotNull null
                LabResult(test, result, o.get("reference_range")?.asString)
            } ?: emptyList()

            val rdt = obj.getAsJsonObject("rdt")?.let { r ->
                val testType = r.get("test_type")?.asString ?: return@let null
                val result = r.get("result")?.asString ?: return@let null
                RdtResult(testType, result, r.get("details")?.asString)
            }

            val medications = obj.getAsJsonArray("medications")?.mapNotNull { elem ->
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

            val rawText = obj.get("raw_text")?.asString

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

    companion object {
        private const val TAG = "VisionExtractor"
    }
}
