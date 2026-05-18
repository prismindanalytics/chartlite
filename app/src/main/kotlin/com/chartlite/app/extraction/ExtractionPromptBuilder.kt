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
        Pair(buildNoteSystemPrompt(compact), buildNoteUserPrompt(transcript, compact))

    /**
     * Combined inference (single LLM call producing markdown note + structured
     * JSON in one JSON envelope). Replaces the legacy two-pass flow.
     *
     * Output schema (the model fills this in):
     *   {
     *     "note": "## Chief Complaint\n- Fever\n...",
     *     "demographics": {...},
     *     ... rest of BENCHMARK_JSON_SCHEMA ...
     *   }
     *
     * The `note` field carries the markdown clinical note for display; the
     * remaining fields are parsed by [LlmResponseParser] into the structured
     * encounter. One inference instead of two.
     */
    fun combinedSystemAndUser(transcript: String): Pair<String, String> =
        Pair(COMBINED_NOTE_AND_JSON_SYSTEM_PROMPT, buildCombinedUserPrompt(transcript))

    private fun buildCombinedUserPrompt(transcript: String): String = buildString {
        appendLine("Produce the JSON object for this clinician dictation.")
        appendLine()
        appendLine("CLINICIAN DICTATION:")
        appendLine()
        appendLine(transcript)
        appendLine()
        append("JSON:")
    }

    // ── Note Generation Prompts (draft-note-first architecture) ──

    /** System prompt for generating a clinical note from transcript. */
    fun buildNoteSystemPrompt(compact: Boolean = false): String =
        if (compact) COMPACT_NOTE_SYSTEM_PROMPT else NOTE_SYSTEM_PROMPT

    /** User prompt for note generation (cloud LLM). */
    fun buildNoteUserPrompt(transcript: String, compact: Boolean = false): String = buildString {
        // Note: section guidance moved into the system prompt (see
        // NOTE_SYSTEM_PROMPT). Listing section headers verbatim in the user
        // prompt caused small open-weights models (Gemma 4 e4b at temp=0.1)
        // to echo the list back as output instead of filling it in.
        if (compact) {
            appendLine("Write a concise clinical note from the dictation below.")
            appendLine("Keep bullets short. Do not omit important diagnoses,")
            appendLine("medications, immunizations, counseling, or follow-up.")
        } else {
            appendLine("Write a clinical note from the dictation below.")
        }
        appendLine()
        appendLine("Dictation:")
        appendLine(transcript)
    }

    /** On-device chat-formatted prompt for note generation (Qwen). */
    fun buildOnDeviceNoteChatPrompt(transcript: String, compact: Boolean = false): String = buildString {
        appendLine("<|im_start|>system")
        appendLine(buildNoteSystemPrompt(compact))
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
    fun visionSystemPrompt(isLargeModel: Boolean = false): String = VISION_SYSTEM_PROMPT

    /** User prompt for vision extraction — the image is passed separately via JNI.
     *  @param isLargeModel true for 2B+ models that can interpret results, false for 0.8B OCR-only
     */
    fun visionUserPrompt(isLargeModel: Boolean = false, additionalContext: String = ""): String = buildString {
        if (additionalContext.isNotBlank()) {
            appendLine(additionalContext)
            appendLine()
        }
        appendLine(if (isLargeModel) VISION_PROMPT_LARGE else VISION_PROMPT_SMALL)
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
You are a clinical scribe. Convert a clinician's dictation into a
professional clinical note.

OUTPUT FORMAT (strict):
- Every line is either a `## Section Header` line, a `- bullet item`
  line, or a blank line between sections. No other lines are allowed.
- Write the note exactly once. Do not produce a brief summary followed
  by a detailed version, or vice versa.
- Begin output with the first applicable section header. No preamble,
  no greeting, no commentary, no closing remarks.

CONTENT:
- Use only facts explicitly stated in the dictation. Do not infer.
- Use exact numbers, values, and medical terms as dictated.
- Each fact appears once across the whole note. No repetition.
- Use these section names when applicable, in this order: Chief
  Complaint, History of Present Illness, Examination Findings, Vitals,
  Investigations, Assessment, Plan, Follow-up, Allergies. The Plan
  section must include any stated treatments, medications,
  immunizations, counseling, or follow-up actions.
- Omit any section that has no content from the dictation. Never write
  "None" or "Not mentioned".
        """.trimIndent()

        private val COMPACT_NOTE_SYSTEM_PROMPT = """
You are a clinical scribe. Write one concise clinical note from the
dictation.

OUTPUT FORMAT (strict):
- Every line is either a `## Section Header`, a `- bullet item`, or a
  blank line. No other lines are allowed.
- Write the note exactly once. No introductory summary, no closing
  remarks, no preamble.

CONTENT:
- Use only facts stated in the dictation. No repetition. No inference.
- Use these section names when applicable, in order: Chief Complaint,
  History of Present Illness, Examination Findings, Vitals,
  Investigations, Assessment, Plan, Follow-up, Allergies. Omit any
  section that has no content.
- Do not drop stated treatments, medications, immunizations, diagnoses,
  counseling, or follow-up.
        """.trimIndent()

        /**
         * Single-pass system prompt: model outputs ONE JSON object containing
         * both the markdown clinical note (`note` field) and the structured
         * clinical facts. Replaces the legacy two-pass flow (note → JSON).
         * Cuts wall-clock inference time roughly in half because the model
         * loads weights once and runs a single prefill+decode cycle.
         */
        private val COMBINED_NOTE_AND_JSON_SYSTEM_PROMPT = """
You are a clinical scribe and data extractor.

For each clinician dictation, output ONE JSON object that contains both
a markdown clinical note and the structured clinical facts.

OUTPUT FORMAT (strict):
- Output exactly one valid JSON object. No markdown fences. No preamble,
  no commentary, no closing remarks. The whole response is the JSON.
- The JSON must include this top-level field "note" with a markdown
  clinical note as a JSON string (use \n for line breaks inside the
  string). All other top-level fields hold the structured facts.

note FIELD CONTENT:
- The note uses ## section headers and - bullets. Each line is either a
  `## Section Header`, a `- bullet item`, or a blank line.
- Section names in this order when applicable: Chief Complaint, History
  of Present Illness, Examination Findings, Vitals, Investigations,
  Assessment, Plan, Follow-up, Allergies. Plan must include any stated
  treatments, medications, immunizations, counseling, or follow-up.
- Omit any section that has no content from the dictation.
- Write the note exactly once. No brief-then-detailed duplication.

STRUCTURED FIELDS:
- Use only facts explicitly stated. Do not infer.
- Use exact numbers and values as dictated.
- Use null for unmentioned scalar fields. Use [] for unmentioned list
  fields.
- Do not output placeholder values like "unknown" or "not stated".
- No duplicate entries.
- Vaccines and immunizations (PENTA, DTP, OPV, BCG, Measles, Hep B,
  Rotavirus, PCV, HPV, Td, MMR, IPV, ...) belong in "immunizations",
  never in "medications". Only therapeutic drugs go in "medications".
- sms_summary: ≤19-character ASCII abbreviation of the reason for visit
  only. No age, sex, vitals, drugs, vaccines.

Schema (fill these top-level fields):
{
  "note": "## Chief Complaint\n- Fever\n...",
  "demographics": {"age": "...", "sex": "M/F", "name": "..."},
  "chief_complaint": "brief summary",
  "vitals": [{"name": "...", "value": "...", "unit": "..."}],
  "exam_findings": ["finding"],
  "investigations": [{"test": "...", "result": "..."}],
  "diagnoses": ["diagnosis"],
  "medications": [{"name": "drug", "dose": "...", "context": "current/new"}],
  "allergies": ["allergy or NKDA"],
  "immunizations": [{"vaccine": "code", "dose_number": 1}],
  "social_history": ["factor"],
  "plan": ["action"],
  "sms_summary": "≤19 char abbrev"
}
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
You are a clinical data extractor for medical images.
Auto-detect the content type and extract structured data.

Content types:
- lab_report: CBC, chemistry, urinalysis, microbiology results
- rdt_cassette: Malaria RDT, HIV RDT, pregnancy test (positive/negative/invalid)
- vital_device: BP monitor, pulse oximeter, thermometer, glucometer readings
- medication_package: Drug name, strength, manufacturer, expiry, batch
- referral_letter: Referring facility, diagnosis, reason, urgency
- vaccine_card: Yellow Card / immunisation record — vaccine, date, dose number, batch, route, given_by
- handwritten_prescription: Prescriber's handwritten Rx — drug, dose, route, frequency, duration, sig
- discharge_summary: Hospital discharge note — discharge diagnosis, meds at discharge, follow-up plan, red-flag alerts

Rules:
- Extract ONLY what is visible. Do NOT infer.
- Use exact numbers from device displays.
- For RDT cassettes: determine result from colored lines on the cassette ONLY. Ignore text on surrounding papers.
- For handwriting: if a token is unreadable, leave the field empty rather than guessing.
- Set content_type to one of the eight types above (or "unknown").
- Add caveats to "warnings" (e.g. "low resolution", "partial occlusion", "handwriting illegible") so a clinician can review.
- Output valid JSON only.
        """.trimIndent()

        // Small model (0.8B): schema with "..." placeholders — model fills in real values
        private val VISION_PROMPT_SMALL = """
<schema>
{
  "content_type": "lab_report|rdt_cassette|vital_device|medication_package|referral_letter|vaccine_card|handwritten_prescription|discharge_summary|unknown",
  "vitals": [{"name": "...", "value": "...", "unit": "..."}],
  "investigations": [{"test": "...", "result": "..."}],
  "medications": [{"name": "...", "dose": "...", "manufacturer": "...", "expiry": "..."}],
  "referral": {"from_facility": "...", "diagnosis": "...", "reason": "...", "urgency": "..."},
  "immunizations": [{"vaccine": "...", "date": "...", "dose_number": 0, "batch": "..."}],
  "discharge": {"dx": [], "meds": [], "follow_up": "", "alerts": []},
  "raw_text": "any visible text not captured above",
  "warnings": []
}
</schema>

JSON:""".trimIndent()

        // Large model (2B+): classify + OCR + interpret results as structured JSON.
        // Single unified schema covering all 8 artifact types — model fills only
        // the relevant fields based on what it sees, leaves the others empty.
        private val VISION_PROMPT_LARGE = """
Read and interpret the clinical image. Output JSON with these fields. Fill ONLY the fields relevant to the artifact type you see; leave the rest empty/null.

{"content_type":"lab_report|rdt_cassette|vital_device|medication_package|referral_letter|vaccine_card|handwritten_prescription|discharge_summary|unknown","confidence":0.0,"raw_text":"ALL TEXT VISIBLE ON THE ARTIFACT","item_name":"SPECIFIC ITEM NAME","investigations":[{"test":"TEST NAME","result":"RESULT","unit":"UNIT","reference_range":"REF","flag":"H|L|N|null"}],"rdt":{"test_type":"HIV|malaria|pregnancy|hepatitis|syphilis|other","result":"positive|negative|invalid","bands":"DESCRIBE WHICH COLORED LINES ARE VISIBLE ON THE CASSETTE — DETERMINE RESULT FROM BANDS ONLY, NOT SURROUNDING TEXT"},"vitals":[{"name":"READING NAME","value":"NUMBER","unit":"UNIT"}],"medications":[{"name":"DRUG NAME","dose":"DOSE","route":"PO|IV|IM|SC|TOP|INH","freq":"FREQUENCY","duration":"DURATION","expiry":"DATE","manufacturer":"MFG","batch":"BATCH"}],"referral":{"from_facility":"FACILITY","diagnosis":"DX","reason":"REASON","urgency":"URGENT|ROUTINE"},"immunizations":[{"vaccine":"VACCINE CODE OR NAME","date":"YYYY-MM-DD","dose_number":1,"batch":"BATCH","route":"IM|SC|ORAL"}],"discharge":{"dx":["DIAGNOSIS"],"meds":["DRUG @ DOSE FREQ"],"follow_up":"FOLLOW-UP PLAN","alerts":["RED FLAG"]},"warnings":["caveats like low resolution, partial occlusion, illegible handwriting"]}

Rules:
- For RDT: determine result from colored lines on the cassette only; ignore surrounding text.
- For handwriting: if a token is illegible, leave the field empty and add an entry to "warnings".
- For vaccine cards: every vaccine entry needs at least vaccine + date OR dose_number.
- For medication_package and handwritten_prescription: route/freq/duration are key — extract from explicit text only.""".trimIndent()
    }
}
