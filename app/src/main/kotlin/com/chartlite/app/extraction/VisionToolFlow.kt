package com.chartlite.app.extraction

import android.util.Log
import com.chartlite.app.cdss.CdssToolRegistry
import com.chartlite.app.model.CDSSAlert
import com.google.gson.Gson

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
        val (system, user) = toolRegistry.buildToolDecisionPrompt(
            extractedArtifactJson = artifactJson,
            patientAllergies = patientAllergies,
            patientPriorDiagnoses = patientPriorDiagnoses,
        )

        val response = modelManager.runChatInference(system, user) ?: ""
        val calls = toolRegistry.parseToolCalls(response)
        Log.d(
            TAG,
            "Gemma 4 chose ${calls.size} tool call(s) for ${visionResult.contentType}: " +
                calls.joinToString(", ") { it.name }
        )
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

    companion object {
        private const val TAG = "VisionToolFlow"
        private val gson = Gson()
    }
}
