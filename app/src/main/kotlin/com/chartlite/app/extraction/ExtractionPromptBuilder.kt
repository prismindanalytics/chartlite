package com.chartlite.app.extraction

import com.chartlite.app.model.Formulary
import com.chartlite.app.model.ICD10Index

/**
 * Builds the shared benchmark JSON prompt used by both local and cloud extraction.
 */
class ExtractionPromptBuilder(
    @Suppress("UNUSED_PARAMETER") icd10: ICD10Index,
    @Suppress("UNUSED_PARAMETER") formulary: Formulary,
    @Suppress("UNUSED_PARAMETER") vectorStore: ClinicalVectorStore? = null
) {

    /** Build the shared extraction prompt for on-device LLM extraction. */
    fun buildRagPrompt(transcript: String): String = buildOnDeviceChatPrompt(transcript)

    fun buildSystemPrompt(@Suppress("UNUSED_PARAMETER") condensed: Boolean = false): String =
        BENCHMARK_SYSTEM_PROMPT

    /**
     * Build the user message containing the transcript.
     */
    fun buildUserPrompt(transcript: String): String = buildBenchmarkUserPrompt(transcript)

    /**
     * Build a single combined prompt (for models that don't support system/user separation).
     */
    fun buildCombinedPrompt(transcript: String, @Suppress("UNUSED_PARAMETER") condensed: Boolean = false): String = buildString {
        append(buildSystemPrompt())
        appendLine()
        appendLine("---")
        appendLine()
        append(buildUserPrompt(transcript))
    }

    /**
     * Build the shared chat-formatted prompt for short dictation snippets.
     */
    fun buildSnippetPrompt(snippet: String): String {
        return buildOnDeviceChatPrompt(snippet)
    }

    // ── Separated system+user for native chat template ──

    /** Return (system, user) pair for extraction — used with LlamaBridge.applyChatTemplate(). */
    fun extractionSystemAndUser(transcript: String): Pair<String, String> =
        Pair(buildOnDeviceSystemPrompt(), buildOnDeviceUserPrompt(transcript))

    /** Return (system, user) pair for note generation — used with LlamaBridge.applyChatTemplate(). */
    fun noteSystemAndUser(transcript: String, compact: Boolean = false): Pair<String, String> =
        Pair(buildNoteSystemPrompt(), buildNoteUserPrompt(transcript, compact))

    // ── Note Generation Prompts (draft-note-first architecture) ──

    /** System prompt for generating a clinical note from transcript. */
    fun buildNoteSystemPrompt(): String = NOTE_SYSTEM_PROMPT

    /** User prompt for note generation (cloud LLM). */
    fun buildNoteUserPrompt(transcript: String, compact: Boolean = false): String = buildString {
        appendLine("Summarize this dictation into a concise clinical note.")
        appendLine("Include ONLY facts from the dictation. Omit empty sections.")
        appendLine()
        if (compact) {
            // Compact prompt for 0.8B model — fewer sections to reduce padding/repetition
            // Dropped HPI + Exam Findings (biggest padding offenders) and Investigations
            appendLine("Sections (skip any not mentioned in dictation):")
            appendLine("## Chief Complaint")
            appendLine("## Vitals")
            appendLine("## Assessment & Plan")
            appendLine("## Allergies")
            appendLine("## Follow-up")
        } else {
            appendLine("Sections (include only if relevant):")
            appendLine("## Chief Complaint")
            appendLine("## History of Present Illness")
            appendLine("## Examination Findings")
            appendLine("## Vitals")
            appendLine("## Investigations")
            appendLine("## Assessment")
            appendLine("## Plan (include all treatments, medications, immunizations given)")
            appendLine("## Follow-up")
            appendLine("## Allergies")
        }
        appendLine()
        appendLine("DICTATION:")
        appendLine()
        appendLine(transcript)
    }

    /** On-device chat-formatted prompt for note generation (Qwen). */
    fun buildOnDeviceNoteChatPrompt(transcript: String, compact: Boolean = false): String = buildString {
        appendLine("<|im_start|>system")
        appendLine(buildNoteSystemPrompt())
        appendLine("<|im_end|>")
        appendLine("<|im_start|>user")
        appendLine(buildNoteUserPrompt(transcript, compact))
        appendLine("<|im_end|>")
        appendLine("<|im_start|>assistant")
        // Pre-close thinking block so Qwen skips thinking and generates content directly
        appendLine("<think>")
        appendLine("</think>")
    }

    private fun buildOnDeviceChatPrompt(transcript: String): String {
        return buildString {
            appendLine("<|im_start|>system")
            appendLine(buildOnDeviceSystemPrompt())
            appendLine("<|im_end|>")
            appendLine("<|im_start|>user")
            appendLine(buildOnDeviceUserPrompt(transcript))
            appendLine("<|im_end|>")
            appendLine("<|im_start|>assistant")
            // Pre-close thinking block so Qwen skips thinking and generates content directly
            appendLine("<think>")
            appendLine("</think>")
            append(ON_DEVICE_ASSISTANT_PREFIX)
        }
    }

    private fun buildOnDeviceSystemPrompt(): String = buildSystemPrompt()

    private fun buildOnDeviceUserPrompt(transcript: String): String = buildBenchmarkUserPrompt(transcript)

    private fun buildBenchmarkUserPrompt(transcript: String): String {
        // Detect if input is a structured note (from note-first flow) vs raw dictation
        val isStructuredNote = transcript.contains("## ")
        return buildString {
            if (isStructuredNote) {
                appendLine("Extract structured clinical facts from this clinical note as JSON.")
                appendLine("\"Assessment & Plan\" contains diagnoses, medications, immunizations, and plan items — extract each into the correct JSON field.")
            } else {
                appendLine("Extract structured clinical facts from this clinician")
                appendLine("dictation as JSON.")
            }
            appendLine()
            appendLine("Schema:")
            appendLine()
            appendLine(BENCHMARK_JSON_SCHEMA)
            appendLine()
            if (isStructuredNote) {
                appendLine("CLINICAL NOTE:")
            } else {
                appendLine("CLINICIAN DICTATION:")
            }
            appendLine()
            appendLine(transcript)
            appendLine()
            append("JSON:")
        }
    }

    // ── Vision Prompts (camera scan → auto-extract) ──

    /** System prompt for vision-based clinical image extraction. */
    fun visionSystemPrompt(): String = VISION_SYSTEM_PROMPT

    /** User prompt for vision extraction — the image is passed separately via JNI. */
    fun visionUserPrompt(additionalContext: String = ""): String = buildString {
        appendLine("Read this clinical image.")
        if (additionalContext.isNotBlank()) {
            appendLine()
            appendLine(additionalContext)
        }
        appendLine()
        appendLine(VISION_JSON_SCHEMA)
    }

    companion object {
        private const val ON_DEVICE_ASSISTANT_PREFIX = "{"
        private val BENCHMARK_SYSTEM_PROMPT = """
You are a clinical data extractor. Extract structured
facts from clinical text.

Rules:

- Extract ONLY what is explicitly stated. Do NOT infer or
assume.

- Use exact numbers and values as dictated.

- Use null for unmentioned scalar fields.

- Use [] for unmentioned list fields.

- Do NOT output placeholder values like "unknown", "not stated",
or schema labels.

- Do NOT repeat duplicate entries.

- Include vitals only when they are explicitly stated.

- Vaccines and immunizations go in "immunizations", NOT in
"medications". If something is a vaccine (e.g. Pentavalent,
DTP, OPV, BCG, Measles, Hepatitis B, Rotavirus, PCV, HPV,
Td, MMR, IPV), put it in "immunizations" with its vaccine
code and dose number. Only therapeutic drugs go in
"medications".

- Output valid JSON only.

- sms_summary: a ≤19-character abbreviated REASON FOR VISIT only.
  Do NOT include age, sex, vitals, medications, vaccines, or
  immunizations (these are already stored in binary fields).
  Use medical shorthand for the chief complaint / diagnosis only.
  Examples: "Imm f/u prev pneum", "HTN DM f/u 2wk",
  "Fvr cgh 3d", "Pn f/u improving". ASCII-only.
        """.trimIndent()

        private val NOTE_SYSTEM_PROMPT = """
You are a clinical scribe. Summarize a clinician's dictation into
a concise, professional clinical note.

Rules:
- SUMMARIZE in third-person clinical prose. Never copy dialog.
- Include ONLY facts explicitly stated. Do NOT infer or add anything.
- Remove ALL repetition — each fact appears once.
- Omit sections with no content. Do NOT write "None" or "Not mentioned".
- Use exact numbers, values, and medical terms as dictated.
- Format: ## for headers, - for bullets, **bold** for key terms.
- No disclaimers or commentary.
        """.trimIndent()

        private val BENCHMARK_JSON_SCHEMA = """
{
  "demographics": {"age": "...", "sex": "M/F", "name": "..."},
  "chief_complaint": "brief summary",
  "vitals": [{"name": "...", "value": "...", "unit": "..."}],
  "exam_findings": ["finding 1", "finding 2"],
  "investigations": [{"test": "...", "result": "..."}],
  "diagnoses": ["diagnosis 1"],
  "medications": [{"name": "drug name (NOT vaccines)", "dose": "...", "context": "current/new"}],
  "allergies": ["allergy or NKDA"],
  "immunizations": [{"vaccine": "vaccine code (e.g. PENTA, DTP, OPV, MEASLES)", "dose_number": 1}],
  "social_history": ["factor 1"],
  "plan": ["action 1", "action 2"],
  "sms_summary": "≤19 char abbrev"
}
        """.trimIndent()

        private val VISION_SYSTEM_PROMPT = """
Read the image. Respond with ONLY a short JSON object. No other text.
        """.trimIndent()

        private val VISION_JSON_SCHEMA = """
Respond with JSON only: {"type":"what is this item","text":"all visible text","data":"clinical readings or results"}""".trimIndent()
    }
}
