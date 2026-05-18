package com.chartlite.app.extraction

import android.util.Log
import com.chartlite.app.cdss.CdssToolRegistry
import com.chartlite.app.model.CDSSAlert
import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonObject

/**
 * Orchestrates the multimodal capture safety flow end-to-end:
 *
 *   1. [VisionExtractor] reads the photo and returns a structured artifact.
 *   2. Gemma 4 chooses which BODHI / CDSS tools to invoke given the artifact
 *      and patient context.
 *   3. Each chosen tool is executed deterministically against the existing
 *      [com.chartlite.app.cdss.StaticCDSS] layer.
 *   4. The artifact, the tool-call trace, and the merged safety alerts are
 *      returned in a single bundle for the UI to render.
 *
 * The "Gemma 4 chooses tools" step is what makes this hackathon feature land
 * the rubric's `function-calling` and `unique Gemma features` axes — see
 * `benchmark_dashboard/HACKATHON_MULTIMODAL_SPEC.md`.
 */
class VisionToolFlow(
    private val visionExtractor: VisionExtractor,
    private val modelManager: LlmModelManager,
    private val toolRegistry: CdssToolRegistry,
) {

    /** Coarse stages reported back to the UI so it can swap progress copy. */
    enum class Stage { READING_IMAGE, CHOOSING_TOOLS, RUNNING_TOOLS, DONE }

    data class SafetyOutcome(
        val visionResult: VisionExtractor.VisionResult?,
        val toolCalls: List<CdssToolRegistry.ToolCallResult> = emptyList(),
        val alerts: List<CDSSAlert> = emptyList(),
        /** Raw Gemma 4 response — useful for the "tool trace" debug panel. */
        val toolReasoningRaw: String? = null,
        /** True iff vision extraction itself failed (image unreadable, RAM, etc.). */
        val visionFailed: Boolean = false,
    )

    /**
     * Run the full capture flow on a photo.
     *
     * @param imagePath absolute path to the JPEG/PNG just captured.
     * @param patientAllergies known allergies from the patient record.
     * @param patientPriorDiagnoses prior diagnoses from the patient record.
     * @param onStage optional callback invoked on each stage transition so the
     *   UI can update its progress copy. Called from a worker thread; the
     *   caller is responsible for marshalling to Main.
     */
    suspend fun captureAndCheck(
        imagePath: String,
        patientAllergies: List<String>,
        patientPriorDiagnoses: List<String>,
        onStage: ((Stage) -> Unit)? = null,
    ): SafetyOutcome {
        onStage?.invoke(Stage.READING_IMAGE)
        val visionResult = visionExtractor.extract(imagePath)
        if (visionResult == null) {
            Log.w(TAG, "Vision extraction returned null for $imagePath")
            onStage?.invoke(Stage.DONE)
            return SafetyOutcome(visionResult = null, visionFailed = true)
        }

        onStage?.invoke(Stage.CHOOSING_TOOLS)
        val artifactJson = visionResult.rawJson ?: gson.toJson(visionResult)
        Log.i(
            TAG,
            "Tool-decision context: artifact=${visionResult.contentType}, " +
                "patient_allergies=${patientAllergies}, " +
                "patient_prior_dxs=${patientPriorDiagnoses}"
        )
        val (system, user) = toolRegistry.buildToolDecisionPrompt(
            extractedArtifactJson = artifactJson,
            patientAllergies = patientAllergies,
            patientPriorDiagnoses = patientPriorDiagnoses,
        )

        val response = modelManager.runChatInference(system, user) ?: ""
        val gemmaCalls = toolRegistry.parseToolCalls(response)
        Log.i(
            TAG,
            "Gemma 4 chose ${gemmaCalls.size} tool call(s) for ${visionResult.contentType}: " +
                gemmaCalls.joinToString(", ") { it.name } +
                " | model response: ${response.take(240).replace('\n', ' ')}"
        )

        // Deterministic safety floor. Gemma 4 e4b at temp=0.1 sometimes
        // declines to invoke any tool even when the patient context clearly
        // warrants one (we observed this on a handwritten prescription
        // with a known penicillin allergy). The "Gemma chooses tools" story
        // is real for the function-calling rubric line, but the patient-
        // safety bar cannot depend on the model picking the right call —
        // we always run the deterministic checks that obviously apply,
        // appended after whatever Gemma chose. Duplicates Gemma already
        // picked are skipped so the trace doesn't double-render.
        val calls = augmentWithDeterministicSafetyChecks(
            gemmaCalls = gemmaCalls,
            vision = visionResult,
            patientAllergies = patientAllergies,
            patientPriorDiagnoses = patientPriorDiagnoses,
        )
        if (calls.size > gemmaCalls.size) {
            val added = calls.drop(gemmaCalls.size).joinToString(", ") { it.name }
            Log.i(TAG, "Deterministic safety floor added tool call(s): $added")
        }

        onStage?.invoke(Stage.RUNNING_TOOLS)
        val results = toolRegistry.execute(calls)
        val alerts = results.flatMap { it.alerts }
        onStage?.invoke(Stage.DONE)

        return SafetyOutcome(
            visionResult = visionResult,
            toolCalls = results,
            alerts = alerts,
            toolReasoningRaw = response,
        )
    }

    /**
     * Insurance against the small-model tool-picker missing the obvious. We
     * compute the set of safety checks whose preconditions are met given
     * the vision result + patient context, then append any that Gemma did
     * not already include. The result still records what Gemma chose first
     * (so the demo's "Gemma 4 chose these checks" story holds for the calls
     * it did make), with the deterministic ones appended after.
     */
    private fun augmentWithDeterministicSafetyChecks(
        gemmaCalls: List<CdssToolRegistry.ToolCall>,
        vision: com.chartlite.app.extraction.VisionExtractor.VisionResult,
        patientAllergies: List<String>,
        patientPriorDiagnoses: List<String>,
    ): List<CdssToolRegistry.ToolCall> {
        val chosen = gemmaCalls.map { it.name }.toMutableSet()
        val out = gemmaCalls.toMutableList()

        val meds = vision.medications.map { it.name }.filter { it.isNotBlank() }
        val allergies = patientAllergies.filter { it.isNotBlank() }
        val priorDxs = patientPriorDiagnoses.filter { it.isNotBlank() }

        // drug-allergy: meds + any known allergy
        if ("check_drug_allergy" !in chosen && meds.isNotEmpty() && allergies.isNotEmpty()) {
            out.add(buildToolCall("check_drug_allergy", mapOf(
                "medications" to meds,
                "allergies" to allergies,
            )))
            chosen.add("check_drug_allergy")
        }

        // drug-drug: 2+ meds
        if ("check_drug_drug_interactions" !in chosen && meds.size >= 2) {
            out.add(buildToolCall("check_drug_drug_interactions", mapOf(
                "medications" to meds,
            )))
            chosen.add("check_drug_drug_interactions")
        }

        // drug-condition: meds + prior dx (e.g. renal, hepatic)
        if ("check_drug_condition" !in chosen && meds.isNotEmpty() && priorDxs.isNotEmpty()) {
            out.add(buildToolCall("check_drug_condition", mapOf(
                "medications" to meds,
                "diagnoses" to priorDxs,
            )))
            chosen.add("check_drug_condition")
        }

        return out
    }

    private fun buildToolCall(
        name: String,
        args: Map<String, List<String>>,
    ): CdssToolRegistry.ToolCall {
        val obj = JsonObject()
        for ((k, v) in args) {
            val arr = JsonArray()
            v.forEach { arr.add(it) }
            obj.add(k, arr)
        }
        return CdssToolRegistry.ToolCall(name = name, args = obj)
    }

    companion object {
        private const val TAG = "VisionToolFlow"
        private val gson = Gson()
    }
}
