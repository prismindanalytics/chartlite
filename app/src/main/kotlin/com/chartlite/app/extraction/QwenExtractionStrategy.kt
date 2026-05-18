package com.chartlite.app.extraction

import android.util.Log
import com.chartlite.app.model.StructuredEncounter
import com.google.gson.JsonParser
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Extraction strategy using Qwen 3.5 (0.8B or 2B) via MNN-LLM on-device.
 *
 * Uses the shared benchmark JSON prompt used by the cloud extractor.
 *
 * Output format: shared JSON schema used across cloud and local extraction.
 */
class QwenExtractionStrategy(
    private val modelManagerProvider: () -> LlmModelManager,
    private val promptBuilder: ExtractionPromptBuilder,
    private val responseParser: LlmResponseParser,
    private val prepareForLowRamInference: (suspend () -> Boolean)? = null
) : ExtractionStrategy {

    private val modelManager: LlmModelManager
        get() = modelManagerProvider()

    private class QwenParseRejectedException(message: String) : IllegalStateException(message)

    internal data class PreparedTranscript(
        val text: String,
        val preparedChars: Int,
        val fillerSegmentsRemoved: Int,
        val duplicateSegmentsRemoved: Int,
        val clippedToBudget: Boolean,
        val compacted: Boolean
    )

    override val name: String
        get() = when (val tier = modelManager.activeTier()) {
            // Class is named QwenExtractionStrategy for historical reasons,
            // but it dispatches through LlmModelManager.runChatInference, which
            // routes Qwen tiers through MNN/llama.cpp and Gemma tiers through
            // MediaPipe LiteRT. Report the *actual* active model so the
            // orchestrator's strategyUsed metadata is accurate.
            LlmModelManager.ModelTier.GEMMA_E4B -> "Gemma 4 E4B (on-device)"
            LlmModelManager.ModelTier.GEMMA_E2B -> "Gemma 4 E2B (on-device)"
            LlmModelManager.ModelTier.LARGE -> "Qwen 3.5 2B (on-device)"
            LlmModelManager.ModelTier.SMALL -> "Qwen 3.5 0.8B (on-device)"
        }

    override suspend fun isAvailable(): Boolean {
        val ready = modelManager.isReady()
        val headroom = ready && modelManager.hasRuntimeHeadroom()
        val active = if (ready) name else "(no on-device model installed)"
        if (ready && headroom) {
            Log.i(TAG, "On-device extraction available: $active")
        } else {
            Log.i(
                TAG,
                "On-device extraction unavailable (ready=$ready, headroom=$headroom, " +
                    "tier=$active) — orchestrator will skip to next strategy"
            )
        }
        return ready && headroom
    }

    override suspend fun extract(
        transcript: String,
        patientId: String,
        providerId: String,
        facilityId: String
    ): StructuredEncounter? = withContext(Dispatchers.Default) {
        try {
            val response = runCombinedInferenceCached(transcript) ?: return@withContext null

            val normalized = normalizeModelResponse(response)
            val parseReport = responseParser.parseDetailed(
                responseText = normalized,
                transcript = transcript,
                patientId = patientId,
                providerId = providerId,
                facilityId = facilityId
            )

            if (parseReport.encounter == null) {
                val failureReason = parseReport.failureReason ?: "parser rejected output"
                Log.w(TAG, "Qwen parser rejected output: $failureReason")
                logRawOutputPreview(normalized)
                throw QwenParseRejectedException(failureReason)
            }

            Log.d(TAG, "Qwen extraction parsed successfully via ${parseReport.format}")
            parseReport.encounter
        } catch (e: QwenParseRejectedException) {
            throw e
        } catch (e: Exception) {
            Log.e(TAG, "Qwen extraction failed", e)
            null
        }
    }

    /**
     * Run the combined-output inference for this transcript, or return the
     * cached raw response if we've already run it. Returns null if guardrails
     * (RAM, ASR preflight, transcript too long, model emits empty) decline
     * the run. Caller is responsible for parsing the response (note vs JSON).
     */
    private suspend fun runCombinedInferenceCached(transcript: String): String? {
        val cacheKey = combinedCacheKey(transcript)
        combinedResponseCache.get(cacheKey)?.let { cached ->
            Log.i(TAG, "Reusing cached combined-inference response (${cached.length} chars) for transcript fingerprint")
            return cached
        }

        if (prepareForLowRamInference?.invoke() == false) {
            Log.w(TAG, "Skipping combined inference: ASR is active or still preparing")
            return null
        }
        if (!modelManager.hasRuntimeHeadroom()) {
            Log.w(TAG, "Skipping combined inference: not enough free memory")
            return null
        }
        val prepared = prepareTranscriptForInference(
            transcript = transcript,
            charBudget = modelManager.maxTranscriptChars()
        )
        if (prepared.text.isBlank()) {
            Log.w(TAG, "Skipping combined inference: transcript empty after preparation")
            return null
        }
        if (modelManager.shouldSkipLongTranscript(prepared.preparedChars)) {
            Log.w(TAG, "Skipping combined inference: transcript too long for stable on-device run")
            return null
        }

        val (systemPrompt, userMessage) = promptBuilder.combinedSystemAndUser(prepared.text)
        // Combined output carries both the note and the structured JSON, so
        // it needs the bigger extraction budget rather than the note-only one.
        val maxOutputTokens = modelManager.recommendedExtractionOutputTokens()

        Log.d(
            TAG,
            "Running combined inference (system: ${systemPrompt.length} chars, " +
                "user: ${userMessage.length} chars, transcript=${transcript.length}->${prepared.preparedChars}, " +
                "max_output_tokens=$maxOutputTokens)"
        )

        val response = runWithEmptyResponseRetry(
            systemPrompt = systemPrompt,
            userMessage = userMessage,
            maxOutputTokens = maxOutputTokens
        )

        if (response.isNullOrBlank()) {
            Log.w(TAG, "Combined inference returned empty response")
            return null
        }

        combinedResponseCache.put(cacheKey, response)
        Log.i(TAG, "Combined inference produced ${response.length}-char response (cached for reuse)")
        return response
    }

    companion object {
        private const val TAG = "QwenExtraction"
        internal const val JSON_RESPONSE_PREFIX = "{"
        private const val CHAT_ASSISTANT_PREFIX = "<|im_start|>assistant"
        private const val CHAT_END_TOKEN = "<|im_end|>"

        // ── Combined-inference cache ──
        //
        // The note-generation path and the structured-extraction path both
        // hit this LRU. Same transcript → one LLM inference; the second
        // call (whichever it is) returns instantly from cache. Bounded at
        // 4 entries (≈4 encounters in flight) so memory stays predictable.
        // Static so the two QwenExtractionStrategy instances built by App
        // (noteGenerationOrchestrator + extractionServices) share state.
        private const val COMBINED_CACHE_MAX_ENTRIES = 4

        private val combinedResponseCache: MutableMap<String, String> = java.util.Collections.synchronizedMap(
            object : LinkedHashMap<String, String>(8, 0.75f, true) {
                override fun removeEldestEntry(eldest: Map.Entry<String, String>): Boolean =
                    size > COMBINED_CACHE_MAX_ENTRIES
            }
        )

        /** Stable cache key for a transcript. Whitespace-normalised so trivial edits hit. */
        internal fun combinedCacheKey(transcript: String): String {
            val normalized = transcript.trim().replace(WHITESPACE_REGEX, " ")
            return Integer.toHexString(normalized.hashCode()) + ":" + normalized.length
        }

        /**
         * Build a markdown clinical note by rendering the structured JSON
         * fields that the combined response *did* include. Used as the
         * second-best fallback when the model forgot to write the `note`
         * field. Returns null if the JSON itself can't be parsed or the
         * resulting note would be too thin.
         */
        internal fun synthesizeNoteFromStructuredJson(rawResponse: String): String? {
            val firstBrace = rawResponse.indexOf('{')
            if (firstBrace < 0) return null
            val lastBrace = rawResponse.lastIndexOf('}')
            if (lastBrace <= firstBrace) return null
            val jsonSlice = rawResponse.substring(firstBrace, lastBrace + 1)
            return try {
                val root = JsonParser.parseString(jsonSlice).asJsonObject

                fun strList(name: String): List<String> = root.get(name)?.takeIf { it.isJsonArray }
                    ?.asJsonArray
                    ?.mapNotNull { el ->
                        when {
                            el.isJsonPrimitive -> el.asString.trim().takeIf { it.isNotEmpty() }
                            el.isJsonObject -> {
                                val obj = el.asJsonObject
                                val parts = obj.entrySet()
                                    .filter { it.value.isJsonPrimitive && !it.value.asString.isNullOrBlank() }
                                    .joinToString(", ") { "${it.key}: ${it.value.asString}" }
                                parts.takeIf { it.isNotEmpty() }
                            }
                            else -> null
                        }
                    } ?: emptyList()

                fun scalar(name: String): String? =
                    root.get(name)?.takeIf { it.isJsonPrimitive }?.asString?.trim()?.takeIf { it.isNotEmpty() }

                val builder = StringBuilder()
                fun appendSection(header: String, bullets: List<String>) {
                    if (bullets.isEmpty()) return
                    if (builder.isNotEmpty()) builder.append('\n')
                    builder.append("## ").append(header).append('\n')
                    for (b in bullets) builder.append("- ").append(b).append('\n')
                }

                scalar("chief_complaint")?.let { appendSection("Chief Complaint", listOf(it)) }
                appendSection("Vitals", strList("vitals"))
                appendSection("Examination Findings", strList("exam_findings"))
                appendSection("Investigations", strList("investigations"))
                appendSection("Assessment", strList("diagnoses"))
                appendSection("Plan", strList("plan") + strList("medications") + strList("immunizations"))
                appendSection("Allergies", strList("allergies"))

                val result = builder.toString().trimEnd()
                result.takeIf { looksLikeUsableNote(it) }
            } catch (_: Throwable) {
                null
            }
        }

        /**
         * Extract the `note` field (markdown string) from the combined JSON
         * response. Returns null if the response isn't valid JSON, lacks the
         * field, or the field is empty. Falls through to the regular note
         * normaliser (which strips chat tokens, thinking blocks, etc).
         */
        internal fun extractNoteField(rawResponse: String): String? {
            val firstBrace = rawResponse.indexOf('{')
            if (firstBrace < 0) return null
            val lastBrace = rawResponse.lastIndexOf('}')
            if (lastBrace <= firstBrace) return null
            val jsonSlice = rawResponse.substring(firstBrace, lastBrace + 1)
            return try {
                val root = JsonParser.parseString(jsonSlice).asJsonObject
                val noteElement = root.get("note") ?: return null
                if (noteElement.isJsonNull) return null
                val noteText = if (noteElement.isJsonPrimitive) {
                    noteElement.asString
                } else {
                    noteElement.toString()
                }
                val stripped = stripNotePreamble(noteText.trim())
                stripped.takeIf { looksLikeUsableNote(it) }
            } catch (_: Throwable) {
                null
            }
        }
        private val PRIMARY_GENERATION_CONFIG = LlmModelManager.GenerationConfig(
            temperature = 0.1f,
            topP = 0.95f,
            topK = 40,
            repeatPenalty = 1.05f
        )
        private val NOTE_GENERATION_CONFIG = LlmModelManager.GenerationConfig(
            temperature = 0.3f,
            topP = 0.95f,
            topK = 40,
            repeatPenalty = 1.3f
        )
        private val COMPACT_NOTE_GENERATION_CONFIG = LlmModelManager.GenerationConfig(
            temperature = 0.2f,
            topP = 0.92f,
            topK = 40,
            repeatPenalty = 1.2f
        )
        private val NOTE_RECOVERY_GENERATION_CONFIG = LlmModelManager.GenerationConfig(
            temperature = 0.2f,
            topP = 0.95f,
            topK = 40,
            repeatPenalty = 1.1f
        )
        private val EMPTY_RESPONSE_RETRY_CONFIG = LlmModelManager.GenerationConfig(
            temperature = 0.2f,
            topP = 0.98f,
            topK = 50,
            repeatPenalty = 1.02f
        )

        internal fun buildPrimedRetryPrompt(prompt: String): String = buildString {
            val trimmed = prompt.trimEnd()
            when {
                trimmed.endsWith(JSON_RESPONSE_PREFIX) -> append(trimmed)
                CHAT_ASSISTANT_PREFIX in trimmed -> {
                    append(trimmed)
                    if (!trimmed.endsWith(JSON_RESPONSE_PREFIX)) {
                        append(JSON_RESPONSE_PREFIX)
                    }
                }
                else -> {
                    append(trimmed)
                    appendLine()
                    appendLine()
                    appendLine("Continue by writing the JSON object immediately after the next line.")
                    append(JSON_RESPONSE_PREFIX)
                }
            }
        }

        internal fun mergePrimedResponse(responseText: String, prefix: String = JSON_RESPONSE_PREFIX): String {
            val trimmed = responseText.trimStart()
            return if (trimmed.trimStart().startsWith(prefix)) {
                trimmed.trimStart()
            } else {
                prefix + trimmed
            }
        }

        /** Regex to match <think>...</think> blocks (including multi-line). */
        private val THINK_TAG_REGEX = Regex("""<think>[\s\S]*?</think>""")
        private val WHITESPACE_REGEX = Regex("""\s+""")

        /**
         * Strip a "lead-in" before the first `## ` markdown section header.
         *
         * Gemma 4 e4b sometimes writes a brief inline summary (e.g.
         * `Chief Complaint: Fever.` lines) before the proper structured note
         * that begins with `## Chief Complaint`. The system prompt already
         * forbids this, but small open-weights models occasionally slip;
         * this is a deterministic backstop.
         *
         * Only strips when (a) a `## ` header exists, and (b) there is
         * non-whitespace content before it. If no `## ` header is present
         * at all, the response is left untouched so we never accidentally
         * blank out a model that wrote without headers.
         */
        internal fun stripNotePreamble(text: String): String {
            val firstHeaderIdx = Regex("(^|\\n)## ").find(text)?.range?.first ?: return text
            val cutAt = if (text[firstHeaderIdx] == '\n') firstHeaderIdx + 1 else firstHeaderIdx
            if (text.substring(0, cutAt).isBlank()) return text
            Log.w(TAG, "Stripping ${cutAt} chars of pre-amble before first `## ` header")
            return text.substring(cutAt)
        }

        /**
         * Strip all thinking blocks from model output. Handles both:
         * - Closed blocks: <think>...</think>
         * - Unclosed blocks: <think>... (model ran out of tokens mid-thinking)
         */
        internal fun stripThinkingBlocks(text: String): String {
            // First strip all closed <think>...</think> blocks
            var result = THINK_TAG_REGEX.replace(text, "")
            // Then strip any remaining unclosed <think> block (thinking filled entire output)
            val unclosedIdx = result.indexOf("<think>")
            if (unclosedIdx >= 0) {
                Log.w(TAG, "Stripping unclosed <think> block (model likely ran out of tokens mid-thinking)")
                result = result.substring(0, unclosedIdx)
            }
            return result.trim()
        }

        internal fun normalizeModelResponse(responseText: String): String {
            val trimmed = responseText.trimEnd()
            if (trimmed.isBlank()) return trimmed.trim()

            val unwrapped = trimmed
                .removePrefix(CHAT_ASSISTANT_PREFIX)
                .trimStart('\n', '\r')
                .removeSuffix(CHAT_END_TOKEN)
                .trimEnd()

            // Strip any thinking blocks the model may have emitted
            val withoutThinking = stripThinkingBlocks(unwrapped)

            val normalized = withoutThinking.trimStart()
            val result = when {
                normalized.startsWith("{") || normalized.startsWith("[") -> normalized
                normalized.startsWith("\"") -> mergePrimedResponse(normalized)
                else -> withoutThinking
            }

            // Detect and truncate degenerate repetition loops
            return truncateRepetition(result)
        }

        /**
         * Detect if the model output has degenerate repetition (same 40+ char
         * substring appearing 3+ times). If so, truncate at the 2nd occurrence
         * and attempt to close the JSON cleanly.
         */
        internal fun truncateRepetition(text: String, minPatternLen: Int = 40, maxOccurrences: Int = 3): String {
            if (text.length < minPatternLen * maxOccurrences) return text

            // Check the last portion of the output for repeating patterns
            val checkRegion = text.takeLast((minPatternLen * maxOccurrences * 2).coerceAtMost(text.length))
            for (patternLen in minPatternLen..80) {
                if (patternLen > checkRegion.length / 2) break
                val pattern = checkRegion.takeLast(patternLen)
                var count = 0
                var searchFrom = 0
                while (true) {
                    val idx = text.indexOf(pattern, searchFrom)
                    if (idx < 0) break
                    count++
                    searchFrom = idx + 1
                }
                if (count >= maxOccurrences) {
                    // Find the 2nd occurrence and truncate there
                    val firstIdx = text.indexOf(pattern)
                    val secondIdx = text.indexOf(pattern, firstIdx + 1)
                    if (secondIdx > 0) {
                        Log.w(TAG, "Repetition detected: ${patternLen}-char pattern repeated ${count}x, truncating at position $secondIdx")
                        val truncated = text.substring(0, secondIdx).trimEnd()
                        // Try to close JSON cleanly
                        return closeJsonBrackets(truncated)
                    }
                }
            }
            return text
        }

        /** Best-effort close unclosed JSON braces/brackets after truncation. */
        private fun closeJsonBrackets(text: String): String {
            var openBraces = 0
            var openBrackets = 0
            var inString = false
            var escaped = false
            for (ch in text) {
                if (escaped) { escaped = false; continue }
                if (ch == '\\' && inString) { escaped = true; continue }
                if (ch == '"') { inString = !inString; continue }
                if (inString) continue
                when (ch) {
                    '{' -> openBraces++
                    '}' -> openBraces--
                    '[' -> openBrackets++
                    ']' -> openBrackets--
                }
            }
            val sb = StringBuilder(text)
            // Close any open strings
            if (inString) sb.append('"')
            // Close brackets then braces
            repeat(openBrackets.coerceAtLeast(0)) { sb.append(']') }
            repeat(openBraces.coerceAtLeast(0)) { sb.append('}') }
            return sb.toString()
        }

        internal fun prepareTranscriptForInference(transcript: String, charBudget: Int): PreparedTranscript {
            val trimmedTranscript = transcript.trim()
            if (trimmedTranscript.isBlank()) {
                return PreparedTranscript(
                    text = "",
                    preparedChars = 0,
                    fillerSegmentsRemoved = 0,
                    duplicateSegmentsRemoved = 0,
                    clippedToBudget = false,
                    compacted = false
                )
            }

            if (charBudget <= 0 || trimmedTranscript.length <= charBudget) {
                return PreparedTranscript(
                    text = trimmedTranscript,
                    preparedChars = trimmedTranscript.length,
                    fillerSegmentsRemoved = 0,
                    duplicateSegmentsRemoved = 0,
                    clippedToBudget = false,
                    compacted = false
                )
            }

            val optimizedTranscript = AmbientTranscriptOptimizer.optimize(
                transcript = transcript,
                charBudget = charBudget
            )
            return PreparedTranscript(
                text = optimizedTranscript.optimizedTranscript,
                preparedChars = optimizedTranscript.optimizedChars,
                fillerSegmentsRemoved = optimizedTranscript.fillerSegmentsRemoved,
                duplicateSegmentsRemoved = optimizedTranscript.duplicateSegmentsRemoved,
                clippedToBudget = optimizedTranscript.clippedToBudget,
                compacted = true
            )
        }

        internal fun responsePreview(
            text: String,
            maxChars: Int = 1800
        ): String = text
            .replace(WHITESPACE_REGEX, " ")
            .trim()
            .take(maxChars)

        internal fun responseTailPreview(
            text: String,
            maxChars: Int = 500
        ): String = text
            .takeLast(maxChars)
            .replace(WHITESPACE_REGEX, " ")
            .trim()

        /**
         * Note-specific repetition truncation. Handles two patterns:
         * 1. Identical consecutive lines (bullet points or sentences repeated back-to-back)
         * 2. Longer substring repetition (30+ chars appearing 3+ times)
         *
         * Unlike [truncateRepetition], this does NOT attempt JSON bracket closing —
         * notes are plain text / Markdown.
         */
        internal fun truncateNoteRepetition(text: String): String {
            // Pass 1: Deduplicate identical consecutive lines
            val lines = text.lines()
            val deduped = mutableListOf<String>()
            var prevLine: String? = null
            var dupCount = 0
            for (line in lines) {
                val trimmedLine = line.trim()
                if (trimmedLine == prevLine && trimmedLine.isNotBlank()) {
                    dupCount++
                    if (dupCount >= 2) continue // keep at most 1 duplicate
                } else {
                    dupCount = 0
                }
                deduped.add(line)
                prevLine = trimmedLine
            }
            val afterLineDup = deduped.joinToString("\n")

            // Pass 2: Detect longer repeating substrings (30+ chars, 3+ occurrences)
            val minLen = 30
            val maxOccurrences = 3
            if (afterLineDup.length < minLen * maxOccurrences) return afterLineDup

            val checkRegion = afterLineDup.takeLast((minLen * maxOccurrences * 2).coerceAtMost(afterLineDup.length))
            for (patternLen in minLen..100) {
                if (patternLen > checkRegion.length / 2) break
                val pattern = checkRegion.takeLast(patternLen)
                var count = 0
                var searchFrom = 0
                while (true) {
                    val idx = afterLineDup.indexOf(pattern, searchFrom)
                    if (idx < 0) break
                    count++
                    searchFrom = idx + 1
                }
                if (count >= maxOccurrences) {
                    val firstIdx = afterLineDup.indexOf(pattern)
                    val secondIdx = afterLineDup.indexOf(pattern, firstIdx + 1)
                    if (secondIdx > 0) {
                        Log.w(TAG, "Note repetition: ${patternLen}-char pattern repeated ${count}x, truncating")
                        return afterLineDup.substring(0, secondIdx).trimEnd()
                    }
                }
            }
            return afterLineDup
        }

        internal fun looksLikeUsableNote(text: String): Boolean {
            val lines = text.lines()
                .map { it.trim() }
                .filter { it.isNotBlank() }
            val letterCount = text.count { it.isLetter() }
            val hasBodyContent = lines.any { it.startsWith("-") || it.length >= 32 }
            return letterCount >= 24 && hasBodyContent
        }
    }

    /**
     * Generate a draft clinical note from transcript via the combined
     * single-pass inference. Returns the markdown `note` field extracted
     * from the JSON envelope.
     *
     * The same inference output is cached by transcript, so the subsequent
     * call to [extract] for the same transcript is an instant cache hit —
     * a single LLM run produces both the note (for clinician review) and
     * the structured fields (for the database, BODHI safety checks, etc).
     */
    override suspend fun generateNote(transcript: String): String? = withContext(Dispatchers.Default) {
        try {
            val response = runCombinedInferenceCached(transcript) ?: return@withContext null
            logRawOutputPreview(response)
            val note = extractNoteField(response)
                ?: synthesizeNoteFromStructuredJson(response)
                ?: run {
                    Log.w(TAG, "Combined response had neither `note` field nor parseable structured fields; using normalized text")
                    normalizeGeneratedNote(response)
                }
            if (note.isNullOrBlank()) {
                Log.w(TAG, "Combined inference produced no usable note")
                return@withContext null
            }
            // Dual-key the cache: when the user reviews / approves this note
            // and the queue later calls extract(approvedNote), key(approvedNote)
            // also resolves to the same combined response — no second inference.
            combinedResponseCache.put(combinedCacheKey(note), response)
            Log.d(TAG, "Note extracted from combined response (${note.length} chars)")
            note
        } catch (e: Exception) {
            Log.e(TAG, "Qwen note generation failed", e)
            null
        }
    }

    private fun buildNoteRecoveryUserMessage(transcript: String): String = buildString {
        appendLine("Write a clinically useful note from this dictation.")
        appendLine("Return the note only.")
        appendLine("Include any stated diagnosis, medication, immunization, treatment, counseling, and follow-up.")
        appendLine("Use markdown headers (##) and bullet points (-).")
        appendLine("Start directly with a section header such as ## Chief Complaint or ## Assessment.")
        appendLine()
        appendLine("DICTATION:")
        appendLine()
        appendLine(transcript)
    }

    private fun normalizeGeneratedNote(responseText: String?): String? {
        if (responseText.isNullOrBlank()) {
            Log.w(TAG, "Qwen note generation returned empty response")
            return null
        }

        val cleaned = responseText.trimEnd()
            .removePrefix(CHAT_ASSISTANT_PREFIX)
            .trimStart('\n', '\r')
            .removeSuffix(CHAT_END_TOKEN)
            .let { stripThinkingBlocks(it) }
            .let { stripNotePreamble(it) }

        if (cleaned.isBlank()) {
            Log.w(TAG, "Qwen note was entirely a thinking block — no usable content")
            return null
        }

        val deduped = truncateNoteRepetition(cleaned)
        return deduped.takeIf {
            looksLikeUsableNote(it)
        } ?: run {
            Log.w(TAG, "Qwen note output was too thin to use (${deduped.length} chars)")
            null
        }
    }

    private suspend fun runWithEmptyResponseRetry(
        systemPrompt: String,
        userMessage: String,
        maxOutputTokens: Int
    ): String? {
        val primary = modelManager.runChatInference(
            systemPrompt = systemPrompt,
            userMessage = userMessage,
            maxTokens = maxOutputTokens,
            config = PRIMARY_GENERATION_CONFIG
        )
        if (!primary.isNullOrBlank()) return primary

        Log.w(TAG, "Primary Qwen attempt returned empty; retrying with JSON prefix priming")

        // For retry, append JSON prefix hint to user message
        val primedUserMessage = "$userMessage\n\nRespond with JSON starting with: {"
        val retry = modelManager.runChatInference(
            systemPrompt = systemPrompt,
            userMessage = primedUserMessage,
            maxTokens = maxOutputTokens,
            config = EMPTY_RESPONSE_RETRY_CONFIG
        )
        if (retry.isNullOrBlank()) return null
        return mergePrimedResponse(retry)
    }

    private fun logRawOutputPreview(responseText: String) {
        Log.d(TAG, "Qwen output received (${responseText.length} chars)")
    }

}
