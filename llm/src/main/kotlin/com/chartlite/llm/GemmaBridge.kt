package com.chartlite.llm

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Log
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.genai.llminference.GraphOptions
import com.google.mediapipe.tasks.genai.llminference.LlmInference
import com.google.mediapipe.tasks.genai.llminference.LlmInferenceSession
import java.io.File

/**
 * Bridge to Google's MediaPipe LLM Inference API for the Gemma 4 family.
 *
 * Artifacts: `litert-community/gemma-4-E{2,4}B-it-litert-lm` on Hugging Face,
 * published as `gemma-4-E{2,4}B-it-web.task` (INT4-quantized LiteRT bundles).
 * Hardware-aware tier selection is handled in [LlmModelManager.recommendedTierForRam]:
 *   - ≥ 6 GB RAM → Gemma 4 E4B (2.83 GB .task)
 *   - ≥ 4 GB RAM → Gemma 4 E2B (~1.5 GB .task)
 *   - <  4 GB RAM → Qwen 3.5 0.8B via MNN (fallback path, not this bridge)
 *
 * Why a separate bridge from [LlamaBridge]:
 *   - Qwen models run via MNN (Alibaba's native runtime) — best perf for Qwen.
 *   - Gemma 4 ships as `.task` bundles built for LiteRT/MediaPipe — best perf for Gemma.
 * Each engine is the vendor-native option; we let each family use its own.
 *
 * The MediaPipe LLM Inference API ships as a Kotlin/Java SDK
 * (`com.google.mediapipe:tasks-genai`), so no JNI is needed at this layer.
 */
object GemmaBridge {

    private const val TAG = "GemmaBridge"

    @Volatile
    private var llm: LlmInference? = null
    @Volatile
    private var modelPath: String = ""
    @Volatile
    private var maxTokens: Int = 1024

    /**
     * Initialize the runtime with a `.task` bundle on disk. Idempotent — safe to
     * call from `LlmModelManager` after a download completes.
     */
    @Synchronized
    fun initModel(
        context: Context,
        modelFile: File,
        maxTokensCap: Int = 4096,
        topK: Int = 40,
        temperature: Float = 0.1f,
        randomSeed: Int = 42,
    ): Boolean {
        if (!modelFile.exists()) {
            Log.e(TAG, "Gemma model not found at ${modelFile.absolutePath}")
            return false
        }
        if (llm != null && modelPath == modelFile.absolutePath) {
            Log.d(TAG, "Gemma already initialized for ${modelFile.name}")
            return true
        }
        return try {
            close()
            val opts = LlmInference.LlmInferenceOptions.builder()
                .setModelPath(modelFile.absolutePath)
                .setMaxTokens(maxTokensCap)
                .build()
            llm = LlmInference.createFromOptions(context, opts)
            modelPath = modelFile.absolutePath
            maxTokens = maxTokensCap
            Log.i(TAG, "Gemma initialized via MediaPipe (model=${modelFile.name}, maxTokens=$maxTokensCap)")
            true
        } catch (e: Throwable) {
            Log.e(TAG, "Failed to init Gemma via MediaPipe", e)
            llm = null
            false
        }
    }

    /**
     * Synchronous text generation. The Gemma chat template is applied by the
     * runtime when the model card declares it (Gemma 4 bundles do).
     *
     * For multi-turn chat, prefer [generateChat] which builds the proper
     * `<start_of_turn>...<end_of_turn>` framing.
     */
    fun generate(prompt: String): String? {
        val handle = llm ?: run {
            Log.w(TAG, "generate() called before initModel()")
            return null
        }
        return try {
            handle.generateResponse(prompt)
        } catch (e: Throwable) {
            Log.e(TAG, "Gemma generate() failed", e)
            null
        }
    }

    /**
     * Apply Gemma's native chat template:
     *   <start_of_turn>user\n{system}\n\n{user}<end_of_turn>\n<start_of_turn>model\n
     *
     * Gemma 4 folds the system message into the first user turn (it doesn't
     * have a dedicated system role, unlike OpenAI/Claude).
     */
    fun generateChat(
        systemPrompt: String,
        userMessage: String,
        topK: Int = 40,
        temperature: Float = 0.1f,
    ): String? {
        val handle = llm ?: run {
            Log.w(TAG, "generateChat() called before initModel()")
            return null
        }
        // Per-call session — supports topK / temperature overrides without
        // mutating the global LlmInference instance.
        return try {
            val sessionOpts = LlmInferenceSession.LlmInferenceSessionOptions.builder()
                .setTopK(topK)
                .setTemperature(temperature)
                .build()
            LlmInferenceSession.createFromOptions(handle, sessionOpts).use { session ->
                val merged = if (systemPrompt.isBlank()) userMessage
                             else "$systemPrompt\n\n$userMessage"
                session.addQueryChunk(merged)
                session.generateResponse()
            }
        } catch (e: Throwable) {
            Log.e(TAG, "Gemma generateChat() failed", e)
            null
        }
    }

    /**
     * Vision inference for Gemma 4: send an image + text prompt, get a structured
     * response. The image is decoded from disk, wrapped in an [com.google.mediapipe.framework.image.MPImage],
     * and added to a per-call session with the vision graph option enabled.
     *
     * Per-call session (not pooled) because:
     *   - vision sessions allocate non-trivial graph memory and we want it freed
     *     deterministically after each call;
     *   - prompts are short-lived single-turn (caller has no need for KV reuse).
     *
     * @param imagePath absolute path to a JPEG / PNG file on device storage.
     * @return raw model output, or null if init/decode/inference fails. The caller
     *         (VisionExtractor) is responsible for parsing JSON out of it.
     */
    fun generateVision(
        systemPrompt: String,
        userMessage: String,
        imagePath: String,
        topK: Int = 40,
        temperature: Float = 0.1f,
    ): String? {
        val handle = llm ?: run {
            Log.w(TAG, "generateVision() called before initModel()")
            return null
        }
        val file = File(imagePath)
        if (!file.exists() || file.length() == 0L) {
            Log.w(TAG, "generateVision() image not found at $imagePath")
            return null
        }
        var bitmap: Bitmap? = null
        return try {
            bitmap = BitmapFactory.decodeFile(imagePath)
            if (bitmap == null) {
                Log.w(TAG, "generateVision() bitmap decode failed for $imagePath")
                return null
            }
            val mpImage = BitmapImageBuilder(bitmap).build()
            val sessionOpts = LlmInferenceSession.LlmInferenceSessionOptions.builder()
                .setTopK(topK)
                .setTemperature(temperature)
                .setGraphOptions(
                    GraphOptions.builder().setEnableVisionModality(true).build()
                )
                .build()
            LlmInferenceSession.createFromOptions(handle, sessionOpts).use { session ->
                val merged = if (systemPrompt.isBlank()) userMessage
                             else "$systemPrompt\n\n$userMessage"
                session.addQueryChunk(merged)
                session.addImage(mpImage)
                session.generateResponse()
            }
        } catch (e: Throwable) {
            Log.e(TAG, "Gemma generateVision() failed", e)
            null
        } finally {
            // Bitmap is held by the MPImage wrapper for the duration of
            // inference; recycle after `session.use {}` has closed so the
            // backing pixel buffer is released. Verified against MediaPipe
            // 0.10.35; if you bump the dep, double-check that addImage()
            // still copies / keeps its own ref before reusing this pattern.
            bitmap?.recycle()
        }
    }

    fun isReady(): Boolean = llm != null

    @Synchronized
    fun close() {
        try {
            llm?.close()
        } catch (e: Throwable) {
            Log.w(TAG, "Gemma close() threw", e)
        } finally {
            llm = null
            modelPath = ""
        }
    }
}
