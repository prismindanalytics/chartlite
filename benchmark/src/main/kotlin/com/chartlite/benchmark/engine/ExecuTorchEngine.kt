package com.chartlite.benchmark.engine

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * ExecuTorch engine — Meta's on-device inference runtime.
 * Runs Qwen via .pte (ExecuTorch) format with XNNPACK delegate.
 *
 * Requires: org.pytorch:executorch-android dependency + model in .pte format.
 * Model conversion: python -m executorch.examples.models.llama.export --model qwen --checkpoint <path>
 */
class ExecuTorchEngine(private val context: Context) : BenchmarkEngine {

    override val name = "ExecuTorch"
    override val modelFormat = "PTE XNNPACK"

    private val modelDir = File(context.noBackupFilesDir, "benchmark_models/executorch")
    val modelFile = File(modelDir, "qwen3-0.6b-xnnpack.pte")
    private var lastMetrics = EngineMetrics()
    private var module: Any? = null

    override fun isModelReady(): Boolean = modelFile.exists() && modelFile.length() > 50_000_000

    override suspend fun loadModel(): Double = withContext(Dispatchers.Default) {
        val t0 = System.nanoTime()
        try {
            val moduleClass = Class.forName("org.pytorch.executorch.LlamaModule")
            module = moduleClass.getConstructor(String::class.java, String::class.java, Float::class.javaPrimitiveType)
                .newInstance(modelFile.absolutePath, "", 0.1f)

            val loadMs = (System.nanoTime() - t0) / 1_000_000.0
            lastMetrics = EngineMetrics(loadMs = loadMs)
            loadMs
        } catch (e: ClassNotFoundException) {
            error("ExecuTorch library not available. Add org.pytorch:executorch-android to dependencies.")
        }
    }

    override suspend fun generate(prompt: String, maxTokens: Int): String? =
        withContext(Dispatchers.Default) {
            val mod = module ?: error("Model not loaded")
            val t0 = System.nanoTime()

            val result = mod.javaClass.getMethod("generate", String::class.java, Int::class.javaPrimitiveType)
                .invoke(mod, prompt, maxTokens) as? String

            val totalMs = (System.nanoTime() - t0) / 1_000_000.0
            val estimatedTokens = (result?.length ?: 0) / 4
            lastMetrics = EngineMetrics(
                loadMs = lastMetrics.loadMs,
                prefillMs = 0.0,
                decodeMs = totalMs,
                promptTokens = prompt.length / 4,
                decodedTokens = estimatedTokens
            )
            result
        }

    override fun lastMetrics(): EngineMetrics = lastMetrics

    override fun unload() {
        module?.let {
            try {
                it.javaClass.getMethod("stop").invoke(it)
            } catch (_: Exception) {}
        }
        module = null
        lastMetrics = EngineMetrics()
    }

    companion object {
        // No official Qwen PTE model — placeholder
        const val MODEL_URL = ""
        const val MODEL_SIZE_MB = 500
    }
}
