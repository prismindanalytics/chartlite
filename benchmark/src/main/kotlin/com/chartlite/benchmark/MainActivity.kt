package com.chartlite.benchmark

import android.app.ActivityManager
import android.content.Context
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.chartlite.benchmark.engine.*
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                BenchmarkScreen(this@MainActivity)
            }
        }
    }
}

private const val TAG = "LlmBenchmark"

/** Standard prompt used across all engines. */
private const val BENCHMARK_PROMPT = """45 year old male presenting with cough for 3 days, productive with yellow sputum. Temperature 38.5 degrees celsius. BP 135 over 88. Pulse 96 bpm. SpO2 94% on room air. Weight 82 kg. Known hypertensive on amlodipine 5mg daily. Allergic to penicillin. Assessment: community acquired pneumonia. Plan: prescribe levofloxacin 750mg OD for 7 days. Paracetamol 1g QDS PRN for fever. Continue amlodipine. Follow up in 5 days. Refer to chest clinic if no improvement."""

@Composable
fun BenchmarkScreen(context: Context) {
    val scope = rememberCoroutineScope()
    val engines = remember {
        listOf(
            MnnEngine(context),
            LlamaCppEngine(context),
            LiteRtLmEngine(context),
            MediaPipeEngine(context),
            ExecuTorchEngine(context),
        )
    }

    var status by remember { mutableStateOf("Ready") }
    var running by remember { mutableStateOf(false) }
    var results by remember { mutableStateOf<List<BenchmarkResult>>(emptyList()) }
    var downloadProgress by remember { mutableStateOf<Map<String, Int>>(emptyMap()) }

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Header
            item {
                Text(
                    "LLM Engine Benchmark",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    deviceLabel(context),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Engine status cards
            item {
                Text("Engines", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            }
            items(engines) { engine ->
                EngineCard(
                    engine = engine,
                    downloadProgress = downloadProgress[engine.name],
                    onDownload = {
                        scope.launch {
                            status = "Downloading ${engine.name} model..."
                            downloadProgress = downloadProgress + (engine.name to 0)
                            val success = downloadModel(engine, context) { pct ->
                                downloadProgress = downloadProgress + (engine.name to pct)
                            }
                            downloadProgress = downloadProgress - engine.name
                            status = if (success) "${engine.name} model ready" else "Download failed"
                        }
                    }
                )
            }

            // Run button
            item {
                Spacer(Modifier.height(8.dp))
                Button(
                    onClick = {
                        scope.launch {
                            running = true
                            results = emptyList()
                            status = "Running benchmarks..."
                            results = runBenchmarks(engines, context) { s -> status = s }
                            status = "Done! ${results.size} results"
                            running = false

                            // Save results
                            saveResults(context, results)
                        }
                    },
                    enabled = !running && engines.any { it.isModelReady() },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(if (running) "Running..." else "Run Benchmark")
                }
                Text(
                    status,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }

            // Results table
            if (results.isNotEmpty()) {
                item {
                    Spacer(Modifier.height(8.dp))
                    Text("Results", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                }
                item {
                    ResultsTable(results)
                }
                items(results) { result ->
                    ResultDetailCard(result)
                }
            }
        }
    }
}

@Composable
fun EngineCard(engine: BenchmarkEngine, downloadProgress: Int?, onDownload: () -> Unit) {
    val ready = engine.isModelReady()
    val hasModelUrl = when (engine) {
        is MediaPipeEngine -> MediaPipeEngine.MODEL_URL.isNotBlank()
        is ExecuTorchEngine -> ExecuTorchEngine.MODEL_URL.isNotBlank()
        else -> true
    }
    val statusText = when {
        ready -> "Ready"
        !hasModelUrl -> "Manual setup required"
        else -> "Not downloaded"
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = when {
                ready -> MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f)
                !hasModelUrl -> MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                else -> MaterialTheme.colorScheme.surfaceVariant
            }
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(engine.name, fontWeight = FontWeight.Bold)
                Text(
                    "${engine.modelFormat} | $statusText",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                if (downloadProgress != null) {
                    LinearProgressIndicator(
                        progress = { downloadProgress / 100f },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 4.dp)
                    )
                    Text(
                        "$downloadProgress%",
                        style = MaterialTheme.typography.labelSmall
                    )
                }
            }
            if (!ready && downloadProgress == null && hasModelUrl) {
                Button(onClick = onDownload, contentPadding = PaddingValues(horizontal = 12.dp)) {
                    Text("Download")
                }
            }
        }
    }
}

@Composable
fun ResultsTable(results: List<BenchmarkResult>) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier
            .horizontalScroll(rememberScrollState())
            .padding(12.dp)
        ) {
            // Header row
            Row {
                TableCell("Engine", 100.dp, fontWeight = FontWeight.Bold)
                TableCell("Load", 70.dp, fontWeight = FontWeight.Bold)
                TableCell("Prefill", 80.dp, fontWeight = FontWeight.Bold)
                TableCell("Decode", 80.dp, fontWeight = FontWeight.Bold)
                TableCell("tok/s", 70.dp, fontWeight = FontWeight.Bold)
                TableCell("Tokens", 60.dp, fontWeight = FontWeight.Bold)
            }
            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
            // Data rows
            for (r in results) {
                Row {
                    TableCell(r.engine, 100.dp)
                    TableCell("${r.metrics.loadMs.toLong()}ms", 70.dp)
                    TableCell("${r.metrics.prefillMs.toLong()}ms", 80.dp)
                    TableCell("${r.metrics.decodeMs.toLong()}ms", 80.dp)
                    TableCell("%.1f".format(r.metrics.decodeTokPerSec), 70.dp)
                    TableCell("${r.metrics.decodedTokens}", 60.dp)
                }
            }
        }
    }
}

@Composable
fun TableCell(text: String, width: androidx.compose.ui.unit.Dp, fontWeight: FontWeight? = null) {
    Text(
        text,
        modifier = Modifier.width(width),
        style = MaterialTheme.typography.bodySmall.copy(
            fontFamily = FontFamily.Monospace,
            fontWeight = fontWeight
        ),
        maxLines = 1,
        overflow = TextOverflow.Ellipsis
    )
}

@Composable
fun ResultDetailCard(result: BenchmarkResult) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                "${result.engine} (${result.format})",
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleSmall
            )
            Spacer(Modifier.height(4.dp))
            val m = result.metrics
            Text(
                buildString {
                    appendLine("Load: ${m.loadMs.toLong()}ms")
                    appendLine("Prefill: ${m.promptTokens} tok in ${m.prefillMs.toLong()}ms (${"%.1f".format(m.prefillTokPerSec)} tok/s)")
                    appendLine("Decode: ${m.decodedTokens} tok in ${m.decodeMs.toLong()}ms (${"%.1f".format(m.decodeTokPerSec)} tok/s)")
                    appendLine("Total: ${m.totalMs.toLong()}ms")
                },
                style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                lineHeight = 18.sp
            )
            if (result.outputPreview.isNotBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(
                    "Output: ${result.outputPreview}",
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            if (result.error != null) {
                Text(
                    "Error: ${result.error}",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
    }
}

data class BenchmarkResult(
    val engine: String,
    val format: String,
    val metrics: EngineMetrics,
    val outputPreview: String = "",
    val error: String? = null
)

private suspend fun downloadModel(
    engine: BenchmarkEngine,
    context: Context,
    onProgress: (Int) -> Unit
): Boolean {
    return when (engine) {
        is MnnEngine -> {
            val zipFile = File(context.noBackupFilesDir, "benchmark_models/mnn/model.zip")
            val success = ModelDownloader.download(MnnEngine.MODEL_URL, zipFile) {
                onProgress(it.percent)
            }
            if (success) {
                val destDir = File(context.noBackupFilesDir, "benchmark_models/mnn")
                ModelDownloader.extractZip(zipFile, destDir)
            } else false
        }
        is LlamaCppEngine -> {
            engine.modelFile.parentFile?.mkdirs()
            ModelDownloader.download(LlamaCppEngine.MODEL_URL, engine.modelFile) {
                onProgress(it.percent)
            }
        }
        is LiteRtLmEngine -> {
            engine.modelFile.parentFile?.mkdirs()
            ModelDownloader.download(LiteRtLmEngine.MODEL_URL, engine.modelFile) {
                onProgress(it.percent)
            }
        }
        is MediaPipeEngine -> {
            if (MediaPipeEngine.MODEL_URL.isBlank()) {
                false // No model URL available yet
            } else {
                engine.modelFile.parentFile?.mkdirs()
                ModelDownloader.download(MediaPipeEngine.MODEL_URL, engine.modelFile) {
                    onProgress(it.percent)
                }
            }
        }
        is ExecuTorchEngine -> {
            if (ExecuTorchEngine.MODEL_URL.isBlank()) {
                false // No model URL available yet
            } else {
                engine.modelFile.parentFile?.mkdirs()
                ModelDownloader.download(ExecuTorchEngine.MODEL_URL, engine.modelFile) {
                    onProgress(it.percent)
                }
            }
        }
        else -> false
    }
}

private suspend fun runBenchmarks(
    engines: List<BenchmarkEngine>,
    context: Context,
    onStatus: (String) -> Unit
): List<BenchmarkResult> {
    val results = mutableListOf<BenchmarkResult>()

    for (engine in engines) {
        if (!engine.isModelReady()) {
            results += BenchmarkResult(engine.name, engine.modelFormat, EngineMetrics(), error = "Model not downloaded")
            continue
        }

        onStatus("Loading ${engine.name}...")
        try {
            // Cold start load
            engine.unload()
            Thread.sleep(300)
            val loadMs = engine.loadModel()
            Log.i(TAG, "${engine.name} loaded in ${loadMs.toLong()}ms")

            // Warm-up
            onStatus("${engine.name}: warm-up...")
            engine.generate("Hello", maxTokens = 16)

            // Benchmark
            onStatus("${engine.name}: benchmarking...")
            val output = engine.generate(BENCHMARK_PROMPT, maxTokens = 256)
            val metrics = engine.lastMetrics()

            results += BenchmarkResult(
                engine = engine.name,
                format = engine.modelFormat,
                metrics = metrics,
                outputPreview = output?.take(200) ?: "(empty)"
            )

            Log.i(TAG, "${engine.name}: prefill=${metrics.prefillTokPerSec.toLong()} tok/s, decode=${metrics.decodeTokPerSec.toLong()} tok/s")

            // Unload to free memory for next engine
            engine.unload()
            Thread.sleep(500) // let GC settle
        } catch (e: Exception) {
            Log.e(TAG, "${engine.name} benchmark failed", e)
            results += BenchmarkResult(engine.name, engine.modelFormat, EngineMetrics(), error = e.message)
            try { engine.unload() } catch (_: Exception) {}
        }
    }

    return results
}

private fun saveResults(context: Context, results: List<BenchmarkResult>) {
    try {
        val deviceName = "${Build.MANUFACTURER}_${Build.MODEL}".replace(" ", "_")
        val report = JSONObject().apply {
            put("device", JSONObject().apply {
                put("manufacturer", Build.MANUFACTURER)
                put("model", Build.MODEL)
                put("sdk", Build.VERSION.SDK_INT)
                put("abi", Build.SUPPORTED_ABIS.toList().toString())
                put("total_ram_mb", totalRamMb(context))
                put("cores", Runtime.getRuntime().availableProcessors())
            })
            put("timestamp", System.currentTimeMillis())
            put("prompt_length", BENCHMARK_PROMPT.length)
            put("results", JSONArray().apply {
                results.forEach { r ->
                    put(JSONObject().apply {
                        put("engine", r.engine)
                        put("format", r.format)
                        put("load_ms", r.metrics.loadMs)
                        put("prefill_ms", r.metrics.prefillMs)
                        put("decode_ms", r.metrics.decodeMs)
                        put("prefill_tok_s", r.metrics.prefillTokPerSec)
                        put("decode_tok_s", r.metrics.decodeTokPerSec)
                        put("prompt_tokens", r.metrics.promptTokens)
                        put("decoded_tokens", r.metrics.decodedTokens)
                        put("error", r.error)
                    })
                }
            })
        }

        val outFile = File(context.getExternalFilesDir(null), "benchmark_$deviceName.json")
        outFile.writeText(report.toString(2))
        Log.i(TAG, "Results saved to: ${outFile.absolutePath}")
    } catch (e: Exception) {
        Log.w(TAG, "Could not save results", e)
    }
}

private fun deviceLabel(context: Context): String {
    val ram = totalRamMb(context)
    val cores = Runtime.getRuntime().availableProcessors()
    return "${Build.MANUFACTURER} ${Build.MODEL} | ${ram / 1024}GB RAM | $cores cores | API ${Build.VERSION.SDK_INT}"
}

private fun totalRamMb(context: Context): Long {
    val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
    val memInfo = ActivityManager.MemoryInfo()
    am.getMemoryInfo(memInfo)
    return memInfo.totalMem / 1024 / 1024
}
