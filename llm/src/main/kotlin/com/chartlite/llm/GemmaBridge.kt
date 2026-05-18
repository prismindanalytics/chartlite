package com.chartlite.llm

import android.content.Context
import android.util.Log
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Content
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.InputData
import com.google.ai.edge.litertlm.SamplerConfig
import com.google.ai.edge.litertlm.SessionConfig
import java.io.File

/**
 * Bridge to Google's LiteRT-LM runtime for the Gemma 4 family.
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
 *   - Gemma 4 ships as `.task` bundles built for LiteRT/LiteRT-LM — best perf for Gemma.
 * Each engine is the vendor-native option; we let each family use its own.
 *
 * Migration note (2026-05-18): switched from `com.google.mediapipe:tasks-genai:0.10.35`
 * to `com.google.ai.edge.litertlm:litertlm-android:0.11.0`. The older tasks-genai
 * library could not open the modern `litert-community` `.task` bundles (the inner
 * zip container moved formats). litertlm-android is the canonical runtime for the
 * current Gemma 4 publishes.
 */
object GemmaBridge {

    private const val TAG = "GemmaBridge"

    @Volatile
    private var engine: Engine? = null
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
        if (engine?.isInitialized() == true && modelPath == modelFile.absolutePath) {
            Log.d(TAG, "Gemma already initialized for ${modelFile.name}")
            return true
        }
        close()
        val cacheDir = File(context.cacheDir, "litertlm").apply { mkdirs() }

        // Try GPU first for text + vision — on a Fold 7 / Pixel 8 /
        // Snapdragon 8 Gen 3+ this gives a 3-5× speedup over CPU for the 4B
        // Gemma. The audio submodule of Gemma 4 has a hard CPU-only
        // constraint, so we always pin audioBackend=CPU. Fall back to
        // CPU-everywhere if GPU init throws (e.g. unsupported Adreno/Mali
        // generation).
        fun tryInit(textBackend: Backend, label: String): Boolean = try {
            val config = EngineConfig(
                modelPath = modelFile.absolutePath,
                backend = textBackend,
                visionBackend = textBackend,
                audioBackend = Backend.CPU(null),
                maxNumTokens = maxTokensCap,
                maxNumImages = 1,
                cacheDir = cacheDir.absolutePath,
            )
            val e = Engine(config)
            e.initialize()
            engine = e
            modelPath = modelFile.absolutePath
            maxTokens = maxTokensCap
            Log.i(
                TAG,
                "Gemma initialized via LiteRT-LM (text+vision=$label, audio=CPU; " +
                    "model=${modelFile.name}, maxTokens=$maxTokensCap)"
            )
            true
        } catch (t: Throwable) {
            Log.w(TAG, "Gemma init with text=$label failed", t)
            engine = null
            false
        }

        return tryInit(Backend.GPU(), "GPU") || tryInit(Backend.CPU(null), "CPU")
    }

    /**
     * Synchronous text generation. The Gemma chat template is applied by the
     * runtime when the model card declares it (Gemma 4 bundles do).
     *
     * For multi-turn chat with system + user framing, prefer [generateChat].
     */
    fun generate(prompt: String): String? {
        val e = engine ?: run {
            Log.w(TAG, "generate() called before initModel()")
            return null
        }
        return try {
            e.createSession(defaultSessionConfig()).use { session ->
                session.generateContent(listOf(InputData.Text(prompt)))
            }
        } catch (t: Throwable) {
            Log.e(TAG, "Gemma generate() failed", t)
            null
        }
    }

    /**
     * Apply Gemma's native chat framing. Gemma 4 folds the system message into
     * the first user turn (it doesn't have a dedicated system role, unlike
     * OpenAI/Claude). We let the runtime apply Gemma's chat template by
     * passing the merged prompt as a single user turn.
     */
    fun generateChat(
        systemPrompt: String,
        userMessage: String,
        topK: Int = 40,
        temperature: Float = 0.1f,
    ): String? {
        val e = engine ?: run {
            Log.w(TAG, "generateChat() called before initModel()")
            return null
        }
        return try {
            val sampler = SamplerConfig(
                topK = topK,
                topP = 1.0,
                temperature = temperature.toDouble(),
                seed = 42,
            )
            e.createSession(SessionConfig(sampler)).use { session ->
                val merged = if (systemPrompt.isBlank()) userMessage
                             else "$systemPrompt\n\n$userMessage"
                session.generateContent(listOf(InputData.Text(merged)))
            }
        } catch (t: Throwable) {
            Log.e(TAG, "Gemma generateChat() failed", t)
            null
        }
    }

    /**
     * Vision inference for Gemma 4: send an image + text prompt, get a structured
     * response. The image is read as raw bytes from disk and passed to the
     * session as an [InputData.Image]; the LiteRT-LM runtime handles the
     * decoding and tokenization.
     *
     * Per-call session (not pooled) because:
     *   - vision sessions allocate non-trivial graph memory and we want it freed
     *     deterministically after each call;
     *   - prompts are short-lived single-turn (caller has no need for KV reuse).
     *
     * @param imagePath absolute path to a JPEG / PNG file on device storage.
     * @return raw model output, or null if init / read / inference fails. The
     *         caller (VisionExtractor) is responsible for parsing JSON out of it.
     */
    fun generateVision(
        systemPrompt: String,
        userMessage: String,
        imagePath: String,
        topK: Int = 40,
        temperature: Float = 0.1f,
    ): String? {
        val e = engine ?: run {
            Log.w(TAG, "generateVision() called before initModel()")
            return null
        }
        val file = File(imagePath)
        if (!file.exists() || file.length() == 0L) {
            Log.w(TAG, "generateVision() image not found at $imagePath")
            return null
        }
        return try {
            // Vision goes through the Conversation API (not Session) because
            // LiteRT-LM's low-level Session.generateContent expects images to
            // be preprocessed first (the runtime throws
            // "Image must be preprocessed before being used in SessionAdvanced"
            // if you pass InputData.Image to it directly). Conversation +
            // Content.ImageFile handles the image-encoder preprocessing for
            // us. Per-call conversation so vision graph memory is freed
            // deterministically after each request.
            val sampler = SamplerConfig(
                topK = topK,
                topP = 1.0,
                temperature = temperature.toDouble(),
                seed = 42,
            )
            val systemInstruction = if (systemPrompt.isNotBlank()) {
                Contents.of(systemPrompt)
            } else {
                Contents.of("")
            }
            val config = ConversationConfig(
                systemInstruction,
                emptyList(),                // initial messages
                emptyList(),                // tools
                sampler,
                false,                      // automaticToolCalling
            )
            val conversation = e.createConversation(config)
            try {
                val message = conversation.sendMessage(
                    Contents.of(
                        Content.Text(userMessage),
                        Content.ImageFile(file.absolutePath)
                    ),
                    emptyMap()
                )
                val text = message.contents.contents
                    .filterIsInstance<Content.Text>()
                    .joinToString("") { it.text }
                text.takeIf { it.isNotBlank() }
            } finally {
                conversation.close()
            }
        } catch (t: Throwable) {
            Log.e(TAG, "Gemma generateVision() failed", t)
            null
        }
    }

    fun isReady(): Boolean = engine?.isInitialized() == true

    @Synchronized
    fun close() {
        try {
            engine?.close()
        } catch (t: Throwable) {
            Log.w(TAG, "Gemma close() threw", t)
        } finally {
            engine = null
            modelPath = ""
        }
    }

    private fun defaultSessionConfig(): SessionConfig =
        SessionConfig(SamplerConfig(topK = 40, topP = 1.0, temperature = 0.1, seed = 42))
}
