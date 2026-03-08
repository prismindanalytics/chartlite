package com.chartlite.app.extraction

import android.util.Log
import com.chartlite.app.model.Formulary
import com.chartlite.app.model.ICD10Index
import java.util.Locale
import kotlin.math.sqrt

/**
 * On-device vector store for clinical terminology retrieval (RAG).
 *
 * Instead of stuffing all 300 ICD-10 codes + 515 formulary drugs into every LLM prompt
 * (~6,000 tokens, 80% of the 8K context window), we embed them into lightweight vectors
 * and retrieve only the top-K most relevant entries per transcript.
 *
 * This implementation uses TF-IDF bag-of-words embeddings — no neural model required,
 * zero additional APK size, runs in <50ms on a Galaxy A03. A neural embedder (e.g.,
 * all-MiniLM-L6-v2 via ONNX) can replace the vectorization method later without
 * changing the retrieval interface.
 *
 * Token budget impact:
 * - Before: ~6,000 tokens (all 815 entries, condensed)
 * - After:  ~400-800 tokens (15-25 relevant entries, with full detail)
 * - Frees ~5,000 tokens for longer transcripts and better generation
 */
class ClinicalVectorStore(
    private val icd10: ICD10Index,
    private val formulary: Formulary
) {

    // ── Indexed entries ─────────────────────────────────────────────────

    data class IndexedEntry(
        val type: EntryType,
        val code: String,
        val name: String,
        val fullDetail: String,      // Rich text for prompt (includes keywords, aliases, routes)
        val searchableText: String,   // Lowercased, normalized for matching
        val vector: FloatArray        // TF-IDF vector
    ) {
        enum class EntryType { ICD10, DRUG }

        override fun equals(other: Any?) = other is IndexedEntry && code == other.code && type == other.type
        override fun hashCode() = 31 * type.hashCode() + code.hashCode()
    }

    private var entries: List<IndexedEntry> = emptyList()
    private var vocabulary: Map<String, Int> = emptyMap()
    private var idfWeights: FloatArray = floatArrayOf()
    private var indexed = false

    // ── Indexing ─────────────────────────────────────────────────────────

    /**
     * Build the vector index from ICD-10 and formulary data.
     * Call once at app startup after loading country data (~20-50ms).
     */
    fun buildIndex() {
        val allEntries = mutableListOf<IndexedEntry>()

        // Index ICD-10 codes
        for (entry in icd10.codes) {
            val keywords = entry.keywords.joinToString(" ")
            val localTerms = entry.localTerms.values.flatten().joinToString(" ")
            val searchable = "${entry.code} ${entry.description} $keywords $localTerms".lowercase(Locale.ROOT)

            val fullDetail = buildString {
                append("${entry.code} - ${entry.description}")
                if (entry.keywords.isNotEmpty()) {
                    append(" [${entry.keywords.joinToString(", ")}]")
                }
                if (entry.localTerms.isNotEmpty()) {
                    val local = entry.localTerms.entries.joinToString("; ") { (lang, terms) ->
                        "$lang: ${terms.joinToString(", ")}"
                    }
                    append(" ($local)")
                }
            }

            allEntries.add(IndexedEntry(
                type = IndexedEntry.EntryType.ICD10,
                code = entry.code,
                name = entry.description,
                fullDetail = fullDetail,
                searchableText = searchable,
                vector = floatArrayOf() // placeholder, computed below
            ))
        }

        // Index formulary drugs
        for (drug in formulary.drugs) {
            val aliases = drug.aliases.joinToString(" ")
            val searchable = "${drug.code} ${drug.name} $aliases ${drug.category} ${drug.defaultRoute}".lowercase(Locale.ROOT)

            val fullDetail = buildString {
                append("${drug.code} - ${drug.name}")
                if (drug.aliases.isNotEmpty()) {
                    append(" (${drug.aliases.joinToString(", ")})")
                }
                append(" [${drug.defaultRoute}]")
            }

            allEntries.add(IndexedEntry(
                type = IndexedEntry.EntryType.DRUG,
                code = drug.code,
                name = drug.name,
                fullDetail = fullDetail,
                searchableText = searchable,
                vector = floatArrayOf()
            ))
        }

        // Build vocabulary from all searchable text
        val docFreq = mutableMapOf<String, Int>()
        val tokenized = allEntries.map { entry ->
            val tokens = tokenize(entry.searchableText)
            tokens.toSet().forEach { token ->
                docFreq[token] = (docFreq[token] ?: 0) + 1
            }
            tokens
        }

        // Filter vocabulary: keep tokens appearing in 2+ docs but <80% of docs (IDF filtering)
        val totalDocs = allEntries.size
        vocabulary = docFreq.entries
            .filter { it.value >= 2 && it.value < (totalDocs * 0.8).toInt() }
            .mapIndexed { index, entry -> entry.key to index }
            .toMap()

        val vocabSize = vocabulary.size

        // Build reverse index for O(1) lookup (avoids O(V^2) in IDF computation)
        val indexToTerm = Array(vocabSize) { "" }
        for ((term, idx) in vocabulary) {
            indexToTerm[idx] = term
        }

        // Compute IDF weights
        idfWeights = FloatArray(vocabSize) { idx ->
            val df = docFreq[indexToTerm[idx]] ?: 1
            kotlin.math.ln((totalDocs + 1f) / (df + 1f)) + 1f
        }

        // Compute TF-IDF vectors for each entry
        entries = allEntries.mapIndexed { i, entry ->
            val vector = computeTfIdfVector(tokenized[i])
            entry.copy(vector = vector)
        }

        indexed = true
        Log.d(TAG, "Vector store indexed: ${entries.size} entries, vocabulary size: $vocabSize")
    }

    // ── Retrieval ───────────────────────────────────────────────────────

    /**
     * Retrieve the top-K most relevant ICD-10 codes and drugs for a transcript.
     *
     * @param transcript The clinical transcript text
     * @param topKDiagnoses Max ICD-10 codes to retrieve (default 10)
     * @param topKDrugs Max formulary drugs to retrieve (default 15)
     * @return Pair of (matched ICD-10 entries, matched drug entries), sorted by relevance
     */
    fun retrieve(
        transcript: String,
        topKDiagnoses: Int = 10,
        topKDrugs: Int = 15
    ): RetrievalResult {
        if (!indexed) {
            Log.w(TAG, "Vector store not indexed, returning empty results")
            return RetrievalResult(emptyList(), emptyList())
        }

        val queryVector = computeTfIdfVector(tokenize(transcript.lowercase(Locale.ROOT)))

        // Score all entries by cosine similarity
        val scored = entries.map { entry ->
            entry to cosineSimilarity(queryVector, entry.vector)
        }

        val icd10Matches = scored
            .filter { it.first.type == IndexedEntry.EntryType.ICD10 && it.second > SIMILARITY_THRESHOLD }
            .sortedByDescending { it.second }
            .take(topKDiagnoses)
            .map { it.first }

        val drugMatches = scored
            .filter { it.first.type == IndexedEntry.EntryType.DRUG && it.second > SIMILARITY_THRESHOLD }
            .sortedByDescending { it.second }
            .take(topKDrugs)
            .map { it.first }

        Log.d(TAG, "Retrieved ${icd10Matches.size} ICD-10 codes + ${drugMatches.size} drugs for transcript (${transcript.length} chars)")

        return RetrievalResult(icd10Matches, drugMatches)
    }

    data class RetrievalResult(
        val icd10Entries: List<IndexedEntry>,
        val drugEntries: List<IndexedEntry>
    ) {
        val totalEntries get() = icd10Entries.size + drugEntries.size
    }

    // ── TF-IDF computation ──────────────────────────────────────────────

    private fun computeTfIdfVector(tokens: List<String>): FloatArray {
        val vocabSize = vocabulary.size
        if (vocabSize == 0) return floatArrayOf()

        val tf = FloatArray(vocabSize)
        val totalTokens = tokens.size.toFloat().coerceAtLeast(1f)

        for (token in tokens) {
            val idx = vocabulary[token] ?: continue
            tf[idx] += 1f / totalTokens
        }

        // TF-IDF = TF * IDF
        val tfidf = FloatArray(vocabSize) { i -> tf[i] * idfWeights[i] }

        // L2 normalize
        val norm = sqrt(tfidf.sumOf { (it * it).toDouble() }).toFloat()
        if (norm > 0f) {
            for (i in tfidf.indices) tfidf[i] /= norm
        }

        return tfidf
    }

    private fun cosineSimilarity(a: FloatArray, b: FloatArray): Float {
        if (a.isEmpty() || b.isEmpty()) return 0f
        val len = minOf(a.size, b.size)
        var dot = 0f
        for (i in 0 until len) {
            dot += a[i] * b[i]
        }
        // Vectors are already L2-normalized, so dot product = cosine similarity
        return dot
    }

    /**
     * Simple clinical-aware tokenizer.
     * Splits on whitespace/punctuation, keeps alphanumeric tokens, handles ICD-10 codes.
     */
    private fun tokenize(text: String): List<String> {
        return text.split(Regex("[\\s,;()\\[\\]{}]+"))
            .map { it.trim('.', ':', '-', '"', '\'') }
            .filter { it.length >= 2 }
    }

    companion object {
        private const val TAG = "ClinicalVectorStore"
        /** Minimum cosine similarity to include in results. */
        private const val SIMILARITY_THRESHOLD = 0.05f
    }
}
