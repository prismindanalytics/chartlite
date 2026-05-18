package com.chartlite.app.eval

import android.content.Context
import android.util.Log
import com.chartlite.app.cdss.StaticCDSS
import com.chartlite.app.extraction.ExtractionStrategy
import com.chartlite.app.model.AlertSeverity
import com.chartlite.app.model.CDSSAlert
import com.chartlite.app.model.StructuredEncounter
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName

/**
 * Runs the bundled `assets/benchmark/eval_mini.json` suite against the supplied
 * [ExtractionStrategy] + [StaticCDSS] and reports per-arm danger detection +
 * extraction accuracy on-device. Used by the Settings → Diagnostics screen
 * (`Run benchmark on this model`) so a clinician can see the loaded LLM's
 * actual numbers on their hardware before relying on it.
 *
 * Same shape as the dashboard's synthetic-100 suite, scoped to 5 representative
 * cases — fast enough to run while the screen is open (~30-60s on a Pixel 8 with
 * Gemma E4B).
 */
class InAppEvaluator(
    private val context: Context,
    private val cdss: StaticCDSS,
) {
    private val gson = Gson()

    data class CaseResult(
        val caseId: Int,
        val caseName: String,
        val category: String,
        val extracted: StructuredEncounter?,
        val alerts: List<CDSSAlert>,
        val expectedDangers: List<ExpectedDanger>,
        val matchedDangers: Int,
        val totalExpectedDangers: Int,
        val extractionLatencyMs: Long,
        val cdssLatencyMs: Long,
    ) {
        val dangerRecall: Double = if (totalExpectedDangers > 0) {
            100.0 * matchedDangers / totalExpectedDangers
        } else 0.0
    }

    data class Summary(
        val modelName: String,
        val nCases: Int,
        val nMatched: Int,
        val nExpected: Int,
        val avgExtractionLatencyMs: Long,
        val avgCdssLatencyMs: Long,
        val perCase: List<CaseResult>,
    ) {
        val overallDangerRecall: Double = if (nExpected > 0) 100.0 * nMatched / nExpected else 0.0
    }

    suspend fun runMiniSuite(strategy: ExtractionStrategy): Summary {
        val suite = loadSuite()
        val results = mutableListOf<CaseResult>()

        for (case in suite.cases) {
            val tExtractStart = System.currentTimeMillis()
            val extracted = try {
                strategy.extract(
                    transcript = case.transcript,
                    patientId = "eval-patient",
                    providerId = "eval-provider",
                    facilityId = "eval-facility",
                )
            } catch (e: Throwable) {
                Log.e(TAG, "Extraction failed for case ${case.id}", e)
                null
            }
            val extractMs = System.currentTimeMillis() - tExtractStart

            val tCdssStart = System.currentTimeMillis()
            val alerts = if (extracted != null) {
                cdss.evaluate(extracted, extracted.allergies)
            } else emptyList()
            val cdssMs = System.currentTimeMillis() - tCdssStart

            val matched = countMatchingDangers(alerts, case.expectedDangers)
            results.add(
                CaseResult(
                    caseId = case.id,
                    caseName = case.name,
                    category = case.category,
                    extracted = extracted,
                    alerts = alerts,
                    expectedDangers = case.expectedDangers,
                    matchedDangers = matched,
                    totalExpectedDangers = case.expectedDangers.size,
                    extractionLatencyMs = extractMs,
                    cdssLatencyMs = cdssMs,
                )
            )
        }

        return Summary(
            modelName = strategy.name,
            nCases = results.size,
            nMatched = results.sumOf { it.matchedDangers },
            nExpected = results.sumOf { it.totalExpectedDangers },
            avgExtractionLatencyMs = if (results.isNotEmpty())
                results.sumOf { it.extractionLatencyMs } / results.size else 0L,
            avgCdssLatencyMs = if (results.isNotEmpty())
                results.sumOf { it.cdssLatencyMs } / results.size else 0L,
            perCase = results,
        )
    }

    /** Severity + category + (optional substring) match — same scheme as benchmark_bodhi.py. */
    private fun countMatchingDangers(
        alerts: List<CDSSAlert>,
        expected: List<ExpectedDanger>,
    ): Int {
        var matched = 0
        for (exp in expected) {
            val sev = AlertSeverity.values().firstOrNull { it.name == exp.severity }
            val hit = alerts.any { a ->
                (sev == null || a.severity == sev) &&
                a.category.equals(exp.category, ignoreCase = true) &&
                (exp.substring.isBlank() ||
                    a.message.contains(exp.substring, ignoreCase = true))
            }
            if (hit) matched++
        }
        return matched
    }

    private fun loadSuite(): EvalSuite {
        val json = context.assets.open(ASSET_PATH).bufferedReader().use { it.readText() }
        return gson.fromJson(json, EvalSuite::class.java)
    }

    // ── JSON DTOs ──

    private data class EvalSuite(
        val version: String,
        @SerializedName("n_cases") val nCases: Int,
        val cases: List<EvalCase>,
    )

    private data class EvalCase(
        val id: Int,
        val name: String,
        val category: String,
        val transcript: String,
        @SerializedName("expected_dangers") val expectedDangers: List<ExpectedDanger>,
    )

    data class ExpectedDanger(
        val severity: String,
        val category: String,
        val substring: String = "",
    )

    companion object {
        private const val TAG = "InAppEvaluator"
        private const val ASSET_PATH = "benchmark/eval_mini.json"
    }
}
