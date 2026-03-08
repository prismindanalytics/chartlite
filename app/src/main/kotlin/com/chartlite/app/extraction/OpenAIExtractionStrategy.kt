package com.chartlite.app.extraction

import android.content.Context
import android.util.Log
import com.chartlite.app.asr.cloud.NetworkUtils
import com.chartlite.app.asr.cloud.SharedHttpClient
import com.chartlite.app.model.StructuredEncounter
import com.google.gson.Gson
import com.google.gson.JsonObject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Clinical extraction via OpenAI GPT models (gpt-5.4 / gpt-4.1).
 * Supports proxied (ChartLite Cloud) and direct (BYOK) modes.
 */
class OpenAIExtractionStrategy(
    private val context: Context,
    private val promptBuilder: ExtractionPromptBuilder,
    private val responseParser: LlmResponseParser,
    private val authConfig: AuthConfig,
    private val model: String = GPT_5_4
) : ExtractionStrategy {

    sealed class AuthConfig {
        data class Direct(val apiKeyProvider: () -> String) : AuthConfig()
        data class Proxied(val authHeaderProvider: suspend () -> Map<String, String>) : AuthConfig()
    }

    override val name = when (authConfig) {
        is AuthConfig.Direct -> "OpenAI $model (cloud)"
        is AuthConfig.Proxied -> "OpenAI $model (ChartLite Cloud)"
    }

    private val gson = Gson()

    override suspend fun isAvailable(): Boolean {
        val hasCredential = when (authConfig) {
            is AuthConfig.Direct -> authConfig.apiKeyProvider().isNotBlank()
            is AuthConfig.Proxied -> true
        }
        if (!hasCredential) return false
        if (!NetworkUtils.hasNetwork(context)) return false
        return true
    }

    override suspend fun extract(
        transcript: String,
        patientId: String,
        providerId: String,
        facilityId: String
    ): StructuredEncounter? = withContext(Dispatchers.IO) {
        val systemPrompt = promptBuilder.buildSystemPrompt(condensed = false)
        val userPrompt = promptBuilder.buildUserPrompt(transcript)
        val responseText = callApi(systemPrompt, userPrompt, "extraction") ?: return@withContext null
        responseParser.parse(responseText, transcript, patientId, providerId, facilityId)
    }

    override suspend fun generateNote(transcript: String): String? = withContext(Dispatchers.IO) {
        val systemPrompt = promptBuilder.buildNoteSystemPrompt()
        val userPrompt = promptBuilder.buildNoteUserPrompt(transcript)
        callApi(systemPrompt, userPrompt, "note generation")?.trim()
    }

    private suspend fun callApi(systemPrompt: String, userPrompt: String, purpose: String): String? {
        Log.d(TAG, "Calling OpenAI $model for $purpose")

        // Send Claude-compatible format — worker transforms to OpenAI chat completions format
        val requestBody = gson.toJson(mapOf(
            "model" to model,
            "max_tokens" to 2048,
            "system" to systemPrompt,
            "messages" to listOf(mapOf("role" to "user", "content" to userPrompt))
        ))

        val requestBuilder = when (authConfig) {
            is AuthConfig.Direct -> {
                if (authConfig.apiKeyProvider().isBlank()) return null
                Request.Builder()
                    .url("$PROXY_BASE_URL/v1/extract")
                    .addHeader("X-ChartLite-AI-Provider", "openai")
                    .addHeader("X-OpenAI-Api-Key", authConfig.apiKeyProvider())
            }
            is AuthConfig.Proxied -> {
                val authHeaders = try { authConfig.authHeaderProvider() }
                catch (e: Exception) { Log.w(TAG, "OpenAI proxy auth unavailable: ${e.message}"); return null }
                val builder = Request.Builder()
                    .url("$PROXY_BASE_URL/v1/extract")
                    .addHeader("X-ChartLite-AI-Provider", "openai")
                authHeaders.forEach { (k, v) -> builder.addHeader(k, v) }
                builder
            }
        }

        val request = requestBuilder
            .addHeader("content-type", "application/json")
            .post(requestBody.toRequestBody("application/json".toMediaType()))
            .build()

        val call = SharedHttpClient.instance.newCall(request)
        val response = suspendCancellableCoroutine { cont ->
            cont.invokeOnCancellation { call.cancel() }
            try { cont.resumeWith(Result.success(call.execute())) }
            catch (e: Exception) { cont.resumeWith(Result.failure(e)) }
        }

        return response.use { resp ->
            if (!resp.isSuccessful) { Log.e(TAG, "OpenAI $model $purpose error ${resp.code}"); return@use null }
            val body = resp.body?.string() ?: return@use null
            try {
                val json = gson.fromJson(body, JsonObject::class.java)
                json.get("text")?.asString
            } catch (e: Exception) { Log.e(TAG, "Failed to parse OpenAI response", e); null }
        }
    }

    companion object {
        private const val TAG = "OpenAIExtraction"
        private const val PROXY_BASE_URL = "https://api.chartlite.health"
        const val GPT_5_4 = "gpt-5.4"
        const val GPT_4_1 = "gpt-4.1"
    }
}
