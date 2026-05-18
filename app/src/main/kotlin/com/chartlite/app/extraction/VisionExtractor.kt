package com.chartlite.app.extraction

import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.JsonSyntaxException

/**
 * Null-safe wrappers around Gson's `as*` accessors. Gson's defaults throw
 * on `JsonNull` (the value the model emits for `"manufacturer": null`,
 * `"referral": null`, etc.) and on type mismatches, which previously crashed
 * the whole vision parser through the catch-all `Vision JSON parse error`
 * path. That sent the result back to the weak text-fallback heuristics and
 * mis-labelled prescriptions as vaccine cards. Returning null on JsonNull
 * lets every "field is optional" downstream path keep working.
 */
private fun JsonElement.asStringSafe(): String? =
    if (isJsonPrimitive) asString else null

private fun JsonElement.asDoubleSafe(): Double? =
    if (isJsonPrimitive) runCatching { asDouble }.getOrNull() else null

private fun JsonElement.asIntSafe(): Int? =
    if (isJsonPrimitive) runCatching { asInt }.getOrNull() else null

private fun JsonObject.getObjectOrNull(name: String): JsonObject? =
    this.get(name)?.takeIf { it.isJsonObject }?.asJsonObject

private fun JsonObject.getArrayOrNull(name: String): JsonArray? =
    this.get(name)?.takeIf { it.isJsonArray }?.asJsonArray

/**
 * Orchestrates on-device vision extraction: image → VLM inference → structured clinical data.
 * Auto-detects content type (lab report, RDT, vitals, medication, referral).
 */
class VisionExtractor(
    private val modelManager: LlmModelManager,
    private val promptBuilder: ExtractionPromptBuilder
) {
    data class VitalReading(val name: String, val value: String, val unit: String)
    data class LabResult(
        val test: String,
        val result: String,
        val referenceRange: String? = null,
        val unit: String? = null,
        val flag: String? = null,  // H/L/N/null
    )
    data class RdtResult(val testType: String, val result: String, val details: String? = null)
    data class MedicationInfo(
        val name: String,
        val dose: String? = null,
        val form: String? = null,
        val expiry: String? = null,
        val route: String? = null,
        val freq: String? = null,
        val duration: String? = null,
        val manufacturer: String? = null,
        val batch: String? = null,
    )
    data class ReferralInfo(
        val fromFacility: String? = null,
        val diagnosis: String? = null,
        val reason: String? = null,
        val urgency: String? = null,
    )
    /** Vaccine card / Yellow Card row. */
    data class Immunization(
        val vaccine: String,
        val date: String? = null,
        val doseNumber: Int? = null,
        val batch: String? = null,
        val route: String? = null,
    )
    /** Hospital discharge summary fields. */
    data class DischargeInfo(
        val dx: List<String> = emptyList(),
        val meds: List<String> = emptyList(),  // free-text "drug @ dose freq" lines
        val followUp: String? = null,
        val alerts: List<String> = emptyList(),
    )

    data class VisionResult(
        val contentType: String,
        val confidence: Double? = null,
        val itemName: String? = null,
        val vitals: List<VitalReading> = emptyList(),
        val investigations: List<LabResult> = emptyList(),
        val rdt: RdtResult? = null,
        val medications: List<MedicationInfo> = emptyList(),
        val referral: ReferralInfo? = null,
        val immunizations: List<Immunization> = emptyList(),
        val discharge: DischargeInfo? = null,
        val warnings: List<String> = emptyList(),
        val rawText: String? = null,
        val rawJson: String? = null,  // For audit trail storage
    )

    suspend fun extract(imagePath: String, additionalContext: String = ""): VisionResult? {
        if (!LlmModelManager.ON_DEVICE_VISION_ENABLED) {
            Log.w(TAG, "On-device vision is disabled; skipping vision extraction")
            return null
        }
        if (!modelManager.supportsOnDeviceVision()) {
            Log.w(TAG, "Vision extraction requested for a text-only model tier")
            return null
        }

        // Check memory headroom before loading vision model + bitmap
        if (!modelManager.hasRuntimeHeadroom()) {
            Log.w(TAG, "Insufficient RAM for vision extraction, skipping")
            return null
        }

        val isLargeModel = modelManager.activeTier() == LlmModelManager.ModelTier.LARGE
        val system = promptBuilder.visionSystemPrompt(isLargeModel)
        val user = promptBuilder.visionUserPrompt(isLargeModel = isLargeModel, additionalContext = additionalContext)
        val maxOutputTokens = modelManager.recommendedSnippetOutputTokens()

        Log.d(TAG, "Running vision extraction on: $imagePath (maxTokens=$maxOutputTokens)")

        val raw = modelManager.runVisionInference(
            systemPrompt = system,
            userMessage = user,
            imagePath = imagePath,
            maxTokens = maxOutputTokens,
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
        // Strip thinking blocks — handle both closed and unclosed (token cutoff)
        var cleaned = raw.replace(THINK_BLOCK_REGEX, "")
        // Handle unclosed <think> block (model ran out of tokens mid-thinking)
        val unclosedIdx = cleaned.indexOf("<think>")
        if (unclosedIdx >= 0) cleaned = cleaned.substring(0, unclosedIdx)
        cleaned = cleaned.trim()

        // Find JSON object
        val jsonStart = cleaned.indexOf('{')
        val jsonEnd = cleaned.lastIndexOf('}')
        if (jsonStart < 0 || jsonEnd <= jsonStart) {
            Log.w(TAG, "No JSON found in vision response, using text fallback")
            return textFallback(cleaned)
        }
        val jsonStr = cleaned.substring(jsonStart, jsonEnd + 1)

        return try {
            val obj = gson.fromJson(jsonStr, JsonObject::class.java)

            // Fuzzy field lookup — small models produce typos like "categoriess", "mediications"
            fun JsonObject.fuzzy(vararg candidates: String) =
                candidates.firstNotNullOfOrNull { key ->
                    // Exact match first, then prefix match (handles typos like extra letters)
                    this.get(key) ?: this.keySet().firstOrNull { k ->
                        k.startsWith(key.take(4)) || key.startsWith(k.take(4))
                    }?.let { this.get(it) }
                }

            val rawContentType = obj.fuzzy("content_type", "category", "categories", "type")?.asStringSafe() ?: ""
            val rawText = obj.get("text")?.asStringSafe() ?: ""
            val rawData = obj.get("data")?.asStringSafe() ?: ""
            val combined = "$rawContentType $rawText $rawData".lowercase()

            // Infer content type from type/text/data fields. Eight artifact
            // types are first-class; "unknown" is the catch-all bucket.
            val contentType = when {
                rawContentType.contains("vaccine") || rawContentType.contains("immuniz") ||
                    rawContentType.contains("yellow_card") -> "vaccine_card"
                rawContentType.contains("prescription") || rawContentType.contains("handwritten") -> "handwritten_prescription"
                rawContentType.contains("discharge") -> "discharge_summary"
                rawContentType.contains("rdt") -> "rdt_cassette"
                rawContentType.contains("lab_report") -> "lab_report"
                rawContentType.contains("vital") -> "vital_device"
                rawContentType.contains("medication") -> "medication_package"
                rawContentType.contains("referral") -> "referral_letter"
                combined.contains("cassette") || combined.contains("rapid test") || combined.contains("rdt") -> "rdt_cassette"
                combined.contains("yellow card") || combined.contains("vaccin") || combined.contains("immuniz") ||
                    combined.contains("dose 1") || combined.contains("dose 2") || combined.contains("dose 3") -> "vaccine_card"
                combined.contains("rx ") || combined.contains("prescription") || combined.contains("sig:") ||
                    combined.contains("bid") || combined.contains("tid") || combined.contains("qid") ||
                    combined.contains("po q") -> "handwritten_prescription"
                combined.contains("discharge") || combined.contains("admit") && combined.contains("follow up") -> "discharge_summary"
                combined.contains("lab") || combined.contains("cbc") || combined.contains("hemoglobin") -> "lab_report"
                combined.contains("thermometer") || combined.contains("blood pressure") ||
                    combined.contains("pulse ox") || combined.contains("glucometer") -> "vital_device"
                combined.contains("tablet") || combined.contains("capsule") || combined.contains("medication") -> "medication_package"
                combined.contains("referral") || combined.contains("refer to") -> "referral_letter"
                else -> "unknown"
            }
            val confidence = obj.get("confidence")?.let {
                runCatching { it.asDouble }.getOrNull()
            }
            val itemName = obj.get("item_name")?.asStringSafe()?.takeIf { it.isNotBlank() }

            val vitals = (obj.getArrayOrNull("vitals") ?: obj.getArrayOrNull("vital"))?.mapNotNull { elem ->
                if (!elem.isJsonObject) return@mapNotNull null
                val o = elem.asJsonObject
                val name = o.get("name")?.asStringSafe() ?: return@mapNotNull null
                val value = o.get("value")?.asStringSafe() ?: return@mapNotNull null
                val unit = o.get("unit")?.asStringSafe() ?: ""
                VitalReading(name, value, unit)
            } ?: emptyList()

            val investigations = (obj.getArrayOrNull("investigations") ?: obj.getArrayOrNull("investigation") ?: obj.getArrayOrNull("lab_results"))?.mapNotNull { elem ->
                if (!elem.isJsonObject) return@mapNotNull null
                val o = elem.asJsonObject
                val test = o.get("test")?.asStringSafe() ?: return@mapNotNull null
                val result = o.get("result")?.asStringSafe()
                    ?: o.get("value")?.asStringSafe()
                    ?: return@mapNotNull null
                LabResult(
                    test = test,
                    result = result,
                    referenceRange = o.get("reference_range")?.asStringSafe() ?: o.get("ref_range")?.asStringSafe(),
                    unit = o.get("unit")?.asStringSafe(),
                    flag = o.get("flag")?.asStringSafe()?.takeIf { it.isNotBlank() && it != "null" },
                )
            } ?: emptyList()

            val rdt = obj.getObjectOrNull("rdt")?.let { r ->
                val testType = r.get("test_type")?.asStringSafe() ?: return@let null
                val result = r.get("result")?.asStringSafe() ?: return@let null
                val rawDetails = r.get("details")?.asStringSafe()
                // Discard if model dumped schema junk into details
                val details = rawDetails?.takeIf { it.length < 200 && !it.contains("content_type") }
                RdtResult(testType, result, details)
            } ?: run {
                // Simple format: top-level "test"+"result" keys, or generic "data" field
                val testName = obj.get("test")?.asStringSafe()
                val testResult = obj.get("result")?.asStringSafe()
                val lines = obj.get("lines")?.asStringSafe()
                if (testName != null && testResult != null) {
                    RdtResult(testName, testResult, lines)
                } else if (contentType == "rdt_cassette") {
                    // Parse RDT from generic data/text fields via textFallback logic
                    val fallback = textFallback("$rawText $rawData")
                    fallback.rdt
                } else null
            }

            val medications = (obj.getArrayOrNull("medications") ?: obj.getArrayOrNull("mediications") ?: obj.getArrayOrNull("medication"))?.mapNotNull { elem ->
                if (!elem.isJsonObject) return@mapNotNull null
                val o = elem.asJsonObject
                val name = o.get("name")?.asStringSafe() ?: return@mapNotNull null
                MedicationInfo(
                    name = name,
                    dose = o.get("dose")?.asStringSafe(),
                    form = o.get("form")?.asStringSafe(),
                    expiry = o.get("expiry")?.asStringSafe(),
                    route = o.get("route")?.asStringSafe(),
                    freq = o.get("freq")?.asStringSafe() ?: o.get("frequency")?.asStringSafe(),
                    duration = o.get("duration")?.asStringSafe(),
                    manufacturer = o.get("manufacturer")?.asStringSafe(),
                    batch = o.get("batch")?.asStringSafe(),
                )
            } ?: emptyList()

            val referral = obj.getObjectOrNull("referral")?.let { r ->
                ReferralInfo(
                    r.get("from_facility")?.asStringSafe(),
                    r.get("diagnosis")?.asStringSafe(),
                    r.get("reason")?.asStringSafe(),
                    r.get("urgency")?.asStringSafe()
                )
            }

            val immunizations = (obj.getArrayOrNull("immunizations") ?: obj.getArrayOrNull("immunization") ?: obj.getArrayOrNull("vaccines"))?.mapNotNull { elem ->
                if (!elem.isJsonObject) return@mapNotNull null
                val o = elem.asJsonObject
                val vaccine = o.get("vaccine")?.asStringSafe() ?: o.get("name")?.asStringSafe() ?: return@mapNotNull null
                Immunization(
                    vaccine = vaccine,
                    date = o.get("date")?.asStringSafe(),
                    doseNumber = o.get("dose_number")?.let { n ->
                        runCatching { n.asInt }.getOrNull()
                    },
                    batch = o.get("batch")?.asStringSafe(),
                    route = o.get("route")?.asStringSafe(),
                )
            } ?: emptyList()

            val discharge = obj.getObjectOrNull("discharge")?.let { d ->
                fun JsonObject.stringList(field: String): List<String> =
                    this.getArrayOrNull(field)?.mapNotNull { it.asStringSafe()?.takeIf { s -> s.isNotBlank() } }
                        ?: emptyList()
                DischargeInfo(
                    dx = d.stringList("dx"),
                    meds = d.stringList("meds"),
                    followUp = d.get("follow_up")?.asStringSafe()?.takeIf { it.isNotBlank() },
                    alerts = d.stringList("alerts"),
                )
            }

            val warnings = obj.getArrayOrNull("warnings")?.mapNotNull {
                it.asStringSafe()?.takeIf { s -> s.isNotBlank() }
            } ?: emptyList()

            // Use raw_text if present, otherwise fall back to generic text/data fields
            val rawTextVal = obj.get("raw_text")?.asStringSafe()
                ?: rawData.takeIf { it.isNotBlank() }
                ?: rawText.takeIf { it.isNotBlank() }
            val parsedRawText = rawTextVal?.takeIf { it.length < 300 && !it.contains("content_type") }

            VisionResult(
                contentType = contentType,
                confidence = confidence,
                itemName = itemName,
                vitals = vitals,
                investigations = investigations,
                rdt = rdt,
                medications = medications,
                referral = referral,
                immunizations = immunizations,
                discharge = discharge,
                warnings = warnings,
                rawText = parsedRawText,
                rawJson = jsonStr,
            )
        } catch (e: JsonSyntaxException) {
            Log.w(TAG, "Failed to parse vision JSON: ${e.message}")
            null
        } catch (e: Exception) {
            Log.w(TAG, "Vision JSON parse error, falling back to text: ${e.message}")
            textFallback(raw)
        }
    }

    /** Fallback: wrap raw text description as a VisionResult so the UI can still show it. */
    private fun textFallback(text: String): VisionResult {
        // Try to detect content type from keywords. Cover all 8 first-class
        // artifact types; fall through to "unknown" so the UI can prompt the
        // clinician to retake the photo.
        val lower = text.lowercase()
        val contentType = when {
            lower.contains("rdt") || lower.contains("rapid test") || lower.contains("cassette") ||
                lower.contains("test line") || lower.contains("control line") -> "rdt_cassette"
            lower.contains("yellow card") || lower.contains("vaccin") || lower.contains("immuniz") ||
                lower.contains("penta") || lower.contains("bcg") || lower.contains("opv") -> "vaccine_card"
            lower.contains("rx ") || lower.contains("sig:") ||
                lower.contains(" bid") || lower.contains(" tid") || lower.contains(" qid") ||
                (lower.contains("po") && lower.contains("q")) -> "handwritten_prescription"
            lower.contains("discharge summary") || lower.contains("discharge dx") ||
                lower.contains("discharged on") -> "discharge_summary"
            lower.contains("blood pressure") || lower.contains("temperature") ||
                lower.contains("pulse ox") || lower.contains("glucometer") -> "vital_device"
            lower.contains("lab") || lower.contains("cbc") || lower.contains("hemoglobin") ||
                lower.contains("wbc") || lower.contains("rbc") -> "lab_report"
            lower.contains("tablet") || lower.contains("capsule") || lower.contains("mg") ||
                lower.contains("medication") || lower.contains("drug") -> "medication_package"
            lower.contains("referral") || lower.contains("refer to") -> "referral_letter"
            else -> "unknown"
        }

        // Try to extract RDT result from text
        val rdt = if (contentType == "rdt_cassette") {
            val testType = when {
                lower.contains("malaria") || lower.contains("pf") || lower.contains("plasmodium") -> "malaria"
                lower.contains("hiv") -> "hiv"
                lower.contains("pregnan") || lower.contains("hcg") -> "pregnancy"
                else -> "other"
            }
            // Determine result from model's description of bands/lines
            val result = when {
                lower.contains("no c line") || lower.contains("no control") -> "invalid"
                // Explicit positive/negative statements (but not from surrounding paper text)
                NEGATIVE_RESULT_REGEX.containsMatchIn(lower) ||
                    lower.contains("only c line") || lower.contains("only the c") || lower.contains("c line only") ||
                    lower.contains("only one line") || lower.contains("one colored line") ||
                    NO_LINE_AT_T_REGEX.containsMatchIn(lower) ||
                    lower.contains("no line next to t") || lower.contains("no colored line next to t") -> "negative"
                POSITIVE_RESULT_REGEX.containsMatchIn(lower) ||
                    lower.contains("c and t") || lower.contains("both lines") ||
                    lower.contains("two colored line") || lower.contains("2 colored line") ||
                    LINE_AT_T_REGEX.containsMatchIn(lower) ||
                    lower.contains("line next to t") || lower.contains("colored line next to t") -> "positive"
                else -> "unknown"
            }
            // Extract device/brand if mentioned
            val deviceMatch = DEVICE_NAME_REGEX.find(text)
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
        private val gson = Gson()
        // Pre-compiled regexes — avoids ~1-2ms of recompilation per parse call
        private val THINK_BLOCK_REGEX = Regex("<think>[\\s\\S]*?</think>")
        private val TRAILING_S_REGEX = Regex("s+$")
        private val NEGATIVE_RESULT_REGEX = Regex("result[:\\s]+(is )?negative|test is negative|non-reactive|nonreactive")
        private val POSITIVE_RESULT_REGEX = Regex("result[:\\s]+(is )?positive|test is positive|\\breactive\\b")
        private val NO_LINE_AT_T_REGEX = Regex("no.{0,20}(colored |visible )?(line|band).{0,10}(next to|at|near|beside) t", RegexOption.IGNORE_CASE)
        private val LINE_AT_T_REGEX = Regex("(colored |visible )?(line|band).{0,10}(next to|at|near|beside) t", RegexOption.IGNORE_CASE)
        private val DEVICE_NAME_REGEX = Regex("(binaxnow|sd bioline|first response|determine|uni-gold|oraquick|sure check|accutest)", RegexOption.IGNORE_CASE)
    }
}
