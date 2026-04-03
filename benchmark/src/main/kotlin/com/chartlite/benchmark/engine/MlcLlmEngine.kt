package com.chartlite.benchmark.engine

import ai.mlc.mlcllm.MLCEngine
import ai.mlc.mlcllm.OpenAIProtocol
import ai.mlc.mlcllm.OpenAIProtocol.ChatCompletionMessage
import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File

/**
 * MLC LLM engine — Apache TVM-based runtime with Vulkan GPU acceleration (SPIR-V shaders).
 * Runs Qwen 3.5 0.8B from q4f16_1 weight shards.
 * Model auto-downloads from prismindanalytics/Qwen3.5-0.8B-q4f16_1-MLC (~427MB).
 */
class MlcLlmEngine(private val context: Context) : BenchmarkEngine {

    override val name = "MLC LLM"
    override val modelFormat = "MLC q4f16_1"

    private val modelDir = File(context.noBackupFilesDir, "benchmark_models/mlc/Qwen3.5-0.8B-q4f16_1-MLC")
    private var lastMetrics = EngineMetrics()
    private var engine: MLCEngine? = null
    // Vulkan crashes with VK_ERROR_DEVICE_LOST on longer prompts (Adreno 830).
    // Default to CPU which is reliable across all devices.
    private var useCpu = true

    override fun isModelReady(): Boolean {
        val config = File(modelDir, "mlc-chat-config.json")
        return config.exists()
    }

    override suspend fun loadModel(): Double = withContext(Dispatchers.Default) {
        val t0 = System.nanoTime()
        val modelLib = if (useCpu) "qwen3_5_cpu_q4f16_1" else "qwen3_5_q4f16_1"
        android.util.Log.i("MlcLlmEngine", "Creating MLCEngine (forceCpu=$useCpu, modelLib=$modelLib)...")
        val eng = MLCEngine(forceCpu = useCpu)
        eng.initError?.let { error("MLC init failed: $it") }
        Thread.sleep(500)
        android.util.Log.i("MlcLlmEngine", "MLCEngine created, reloading model from ${modelDir.absolutePath}")
        eng.reload(modelDir.absolutePath, modelLib)
        android.util.Log.i("MlcLlmEngine", "Model reloaded successfully")
        engine = eng
        val loadMs = (System.nanoTime() - t0) / 1_000_000.0
        lastMetrics = EngineMetrics(loadMs = loadMs)
        loadMs
    }

    override suspend fun generate(prompt: String, maxTokens: Int): String? =
        withContext(Dispatchers.Default) {
            val output = tryGenerate(prompt, maxTokens)

            // If Vulkan failed (0 chars + timeout), retry on CPU
            if (output == null && !useCpu) {
                android.util.Log.w("MlcLlmEngine", "Vulkan generation failed, retrying on CPU...")
                unload()
                useCpu = true
                loadModel()
                return@withContext tryGenerate(prompt, maxTokens)
            }
            output
        }

    private suspend fun tryGenerate(prompt: String, maxTokens: Int): String? {
        val eng = engine ?: error("Model not loaded")
        val chat = eng.chat ?: error("MLC chat not initialized")
        val t0 = System.nanoTime()
        android.util.Log.i("MlcLlmEngine", "generate: sending prompt (${prompt.length} chars, maxTokens=$maxTokens)")

        val messages = listOf(
            ChatCompletionMessage(
                role = OpenAIProtocol.ChatCompletionRole.user,
                content = prompt
            )
        )

        val result = StringBuilder()
        val channel = chat.completions.create(
            messages = messages,
            max_tokens = maxTokens,
            temperature = 0.1f,
            stream = true,
        )

        android.util.Log.i("MlcLlmEngine", "generate: waiting for stream responses...")

        val completed = withTimeoutOrNull(60_000L) {
            for (response in channel) {
                // Check if background worker crashed (e.g. VK_ERROR_DEVICE_LOST)
                eng.backgroundError()?.let { err ->
                    android.util.Log.e("MlcLlmEngine", "Background worker died: $err")
                    return@withTimeoutOrNull false
                }
                response.choices.forEach { choice ->
                    choice.delta.content?.let { result.append(it.asText()) }
                }
            }
            true
        }

        when (completed) {
            null -> android.util.Log.w("MlcLlmEngine", "generate: timed out after 60s, got ${result.length} chars")
            false -> android.util.Log.w("MlcLlmEngine", "generate: aborted due to background error")
            true -> android.util.Log.i("MlcLlmEngine", "generate: completed, ${result.length} chars")
        }

        val totalMs = (System.nanoTime() - t0) / 1_000_000.0
        val estimatedTokens = result.length / 4
        lastMetrics = EngineMetrics(
            loadMs = lastMetrics.loadMs,
            prefillMs = 0.0,
            decodeMs = totalMs,
            promptTokens = prompt.length / 4,
            decodedTokens = estimatedTokens
        )
        return result.toString().ifBlank { null }
    }

    override fun lastMetrics(): EngineMetrics = lastMetrics

    override fun unload() {
        engine?.unload()
        engine = null
        lastMetrics = EngineMetrics()
    }

    companion object {
        const val MODEL_URL =
            "https://huggingface.co/prismindanalytics/Qwen3.5-0.8B-q4f16_1-MLC/resolve/main/Qwen3.5-0.8B-q4f16_1-MLC.zip"
        const val MODEL_SIZE_MB = 360
    }
}
