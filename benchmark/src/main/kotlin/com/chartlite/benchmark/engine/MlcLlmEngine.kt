package com.chartlite.benchmark.engine

import ai.mlc.mlcllm.MLCEngine
import ai.mlc.mlcllm.OpenAIProtocol
import ai.mlc.mlcllm.OpenAIProtocol.ChatCompletionMessage
import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * MLC LLM engine — Apache TVM-based runtime with OpenCL GPU acceleration.
 * Runs Qwen 3.5 0.8B from q4f16_1 weight shards.
 * Model auto-downloads from prismindanalytics/Qwen3.5-0.8B-q4f16_1-MLC (~427MB).
 */
class MlcLlmEngine(private val context: Context) : BenchmarkEngine {

    override val name = "MLC LLM"
    override val modelFormat = "MLC q4f16_1"

    private val modelDir = File(context.noBackupFilesDir, "benchmark_models/mlc/Qwen3.5-0.8B-q4f16_1-MLC")
    private var lastMetrics = EngineMetrics()
    private var engine: MLCEngine? = null

    override fun isModelReady(): Boolean {
        val config = File(modelDir, "mlc-chat-config.json")
        return config.exists()
    }

    override suspend fun loadModel(): Double = withContext(Dispatchers.Default) {
        val t0 = System.nanoTime()
        android.util.Log.i("MlcLlmEngine", "Creating MLCEngine...")
        val eng = MLCEngine()
        // Check if init failed (constructor catches exceptions internally)
        eng.initError?.let { error("MLC init failed: $it") }
        // Give background threads a moment to start
        Thread.sleep(500)
        android.util.Log.i("MlcLlmEngine", "MLCEngine created, reloading model from ${modelDir.absolutePath}")
        eng.reload(modelDir.absolutePath, "qwen3_5_q4f16_1")
        android.util.Log.i("MlcLlmEngine", "Model reloaded successfully")
        engine = eng
        val loadMs = (System.nanoTime() - t0) / 1_000_000.0
        lastMetrics = EngineMetrics(loadMs = loadMs)
        loadMs
    }

    override suspend fun generate(prompt: String, maxTokens: Int): String? =
        withContext(Dispatchers.Default) {
            val eng = engine ?: error("Model not loaded")
            val chat = eng.chat ?: error("MLC chat not initialized")
            val t0 = System.nanoTime()

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

            for (response in channel) {
                response.choices.forEach { choice ->
                    choice.delta.content?.let { result.append(it.asText()) }
                }
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
            result.toString().ifBlank { null }
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
