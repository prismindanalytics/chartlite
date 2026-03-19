package com.chartlite.llm

import android.content.Context
import android.util.Log

/**
 * JNI bridge to MNN-LLM for on-device Qwen inference.
 * Loads libchartlite-llm.so which wraps MNN's Llm C++ API.
 */
object LlamaBridge {

    private const val TAG = "LlamaBridge"

    @Volatile
    private var initialized = false

    /**
     * Initialize the llama.cpp backend. Must be called once before any other method.
     */
    fun initialize(context: Context) {
        if (initialized) return
        synchronized(this) {
            if (initialized) return
            System.loadLibrary("chartlite-llm")
            nativeInit()
            initialized = true
            Log.i(TAG, "MNN-LLM backend initialized")
        }
    }

    fun initGenerateModel(modelPath: String): Boolean {
        check(initialized) { "LlamaBridge.initialize() not called" }
        return nativeInitGenerateModel(modelPath)
    }

    fun updateGenerateParams(
        temperature: Float,
        maxTokens: Int,
        topP: Float,
        topK: Int,
        repeatPenalty: Float
    ) {
        nativeUpdateGenerateParams(temperature, maxTokens, topP, topK, repeatPenalty)
    }

    fun generate(prompt: String): String? {
        check(initialized) { "LlamaBridge.initialize() not called" }
        return nativeGenerate(prompt)
    }

    fun generateJson(prompt: String, jsonSchema: String): String? {
        check(initialized) { "LlamaBridge.initialize() not called" }
        return nativeGenerateJson(prompt, jsonSchema)
    }

    /**
     * Generate a response using structured system/user messages.
     * MNN applies the model's native chat template with proper special token handling.
     */
    fun generateChat(systemPrompt: String, userMessage: String): String? {
        check(initialized) { "LlamaBridge.initialize() not called" }
        return nativeGenerateChat(systemPrompt, userMessage)
    }

    /**
     * Apply the model's native chat template with thinking control.
     * Returns a fully formatted prompt string, or null if the model isn't loaded.
     *
     * @param enableThinking false to disable Qwen's thinking mode (equivalent to --reasoning-budget 0)
     */
    fun applyChatTemplate(
        systemPrompt: String,
        userMessage: String,
        enableThinking: Boolean = false
    ): String? {
        check(initialized) { "LlamaBridge.initialize() not called" }
        return nativeApplyChatTemplate(systemPrompt, userMessage, enableThinking)
    }

    /**
     * Generate a response from a clinical image using the vision-language model.
     * The model auto-detects content type (lab report, RDT, vitals, medication, referral).
     *
     * @param imagePath absolute path to a JPEG/PNG file on device storage
     */
    fun generateVision(systemPrompt: String, userMessage: String, imagePath: String): String? {
        check(initialized) { "LlamaBridge.initialize() not called" }
        return nativeGenerateVision(systemPrompt, userMessage, imagePath)
    }

    fun cancelGeneration() {
        if (!initialized) return
        nativeCancelGeneration()
    }

    fun shutdown() {
        if (!initialized) return
        nativeShutdown()
    }

    // JNI native methods
    private external fun nativeInit()
    private external fun nativeInitGenerateModel(modelPath: String): Boolean
    private external fun nativeUpdateGenerateParams(
        temperature: Float, maxTokens: Int, topP: Float, topK: Int, repeatPenalty: Float
    )
    private external fun nativeGenerate(prompt: String): String?
    private external fun nativeGenerateJson(prompt: String, jsonSchema: String): String?
    private external fun nativeGenerateChat(systemPrompt: String, userMessage: String): String?
    private external fun nativeApplyChatTemplate(
        systemPrompt: String, userMessage: String, enableThinking: Boolean
    ): String?
    private external fun nativeGenerateVision(
        systemPrompt: String, userMessage: String, imagePath: String
    ): String?
    private external fun nativeCancelGeneration()
    private external fun nativeShutdown()
}
