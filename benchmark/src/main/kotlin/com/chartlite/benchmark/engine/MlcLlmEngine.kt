package com.chartlite.benchmark.engine

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * MLC LLM engine — Apache TVM-based LLM runtime with OpenCL GPU acceleration.
 *
 * Uses MLC-compiled model format (.bin weight shards + mlc-chat-config.json).
 * Requires the mlc4j local subproject (not available on Maven Central).
 *
 * Setup:
 *   1. pip install mlc-llm
 *   2. mlc_llm convert_weight Qwen3.5-0.8B/ --quantization q4f16_1 -o dist/Qwen3.5-0.8B-q4f16_1-MLC
 *   3. mlc_llm gen_config Qwen3.5-0.8B/ --quantization q4f16_1 --conv-template qwen2 -o dist/Qwen3.5-0.8B-q4f16_1-MLC/
 *   4. mlc_llm compile dist/Qwen3.5-0.8B-q4f16_1-MLC/mlc-chat-config.json --device android -o dist/libs/Qwen3.5-0.8B-q4f16_1-android.tar
 *   5. mlc_llm package --device android  (generates dist/lib/mlc4j subproject)
 *   6. Add include(':mlc4j') to settings.gradle.kts
 *   7. Add implementation(project(":mlc4j")) to benchmark/build.gradle.kts
 *   8. Push weight files to device: adb push dist/Qwen3.5-0.8B-q4f16_1-MLC /data/local/tmp/
 */
class MlcLlmEngine(private val context: Context) : BenchmarkEngine {

    override val name = "MLC LLM"
    override val modelFormat = "MLC q4f16_1"

    private val modelDir = File(context.noBackupFilesDir, "benchmark_models/mlc/Qwen3.5-0.8B-q4f16_1-MLC")
    private var lastMetrics = EngineMetrics()
    private var engine: Any? = null

    override fun isModelReady(): Boolean {
        val config = File(modelDir, "mlc-chat-config.json")
        return config.exists()
    }

    override suspend fun loadModel(): Double = withContext(Dispatchers.Default) {
        val t0 = System.nanoTime()
        try {
            val engineClass = Class.forName("ai.mlc.mlcllm.MLCEngine")
            engine = engineClass.getConstructor().newInstance()

            // MLCEngine.reload(modelPath, modelLib)
            // modelLib name follows pattern: "Qwen3.5-0.8B-q4f16_1"
            engineClass.getMethod("reload", String::class.java, String::class.java)
                .invoke(engine, modelDir.absolutePath, "Qwen3.5-0.8B-q4f16_1")

            val loadMs = (System.nanoTime() - t0) / 1_000_000.0
            lastMetrics = EngineMetrics(loadMs = loadMs)
            loadMs
        } catch (e: ClassNotFoundException) {
            error("MLC LLM library not available. Add mlc4j subproject — see MlcLlmEngine.kt header for setup instructions.")
        }
    }

    override suspend fun generate(prompt: String, maxTokens: Int): String? =
        withContext(Dispatchers.Default) {
            val eng = engine ?: error("Model not loaded")
            val t0 = System.nanoTime()

            try {
                // Build chat completion request via MLC's OpenAI-compatible API
                // MLCEngine.chat.completions.create(messages, model, temperature, max_tokens)
                // Since the API is streaming-only, we collect all chunks
                val chatField = eng.javaClass.getField("chat")
                val chat = chatField.get(eng)
                val completionsField = chat!!.javaClass.getField("completions")
                val completions = completionsField.get(chat)

                // Create message list
                val msgClass = Class.forName("ai.mlc.mlcllm.ChatCompletionMessage")
                val msg = msgClass.getConstructor(String::class.java, String::class.java)
                    .newInstance("user", prompt)
                val messages = listOf(msg)

                // Call create() which returns Flow<ChatCompletionStreamResponse>
                val createMethod = completions!!.javaClass.methods.find { it.name == "create" }
                    ?: error("create method not found")

                // For benchmarking, use the simpler generateResponse if available
                val result = StringBuilder()
                // Fallback: use reflection-based simple generate
                val generateMethod = eng.javaClass.methods.find { it.name == "generate" }
                if (generateMethod != null) {
                    val response = generateMethod.invoke(eng, prompt, maxTokens) as? String
                    result.append(response ?: "")
                } else {
                    result.append("(MLC streaming API — use chat.completions.create)")
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
            } catch (e: Exception) {
                val totalMs = (System.nanoTime() - t0) / 1_000_000.0
                lastMetrics = EngineMetrics(loadMs = lastMetrics.loadMs, decodeMs = totalMs)
                throw e
            }
        }

    override fun lastMetrics(): EngineMetrics = lastMetrics

    override fun unload() {
        engine?.let {
            try { it.javaClass.getMethod("unload").invoke(it) } catch (_: Exception) {}
            try { it.javaClass.getMethod("reset").invoke(it) } catch (_: Exception) {}
        }
        engine = null
        lastMetrics = EngineMetrics()
    }

    companion object {
        // No pre-compiled Qwen3.5-0.8B MLC model. Must compile locally — see class header.
        // Weight files are pushed to device via adb, not downloaded via HTTP.
        const val MODEL_URL = ""
        const val MODEL_SIZE_MB = 500
    }
}
