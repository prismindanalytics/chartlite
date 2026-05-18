package com.chartlite.app.extraction

import android.app.ActivityManager
import android.content.ComponentCallbacks2
import android.content.Context
import android.content.res.Configuration
import android.os.PowerManager
import android.util.Log
import com.chartlite.llm.LlamaBridge
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.Call
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.zip.ZipFile

/**
 * Manages downloading and loading of on-device Qwen models for text inference.
 *
 * Production backend selection is hardware-aware:
 * - <4GB RAM: llama.cpp + Qwen 3.5 0.8B Q4_K_M GGUF
 * - >=4GB RAM: MNN + Qwen 3.5 0.8B INT4
 *
 * MNN payloads are extracted directories. llama.cpp payloads are single GGUF files.
 * Models are stored in context.noBackupFilesDir/llm_models/ (excluded from auto-backup).
 */
class LlmModelManager(private val context: Context) : ComponentCallbacks2 {
    enum class InferenceBackend {
        MNN,
        LLAMA_CPP,
        /** Google's MediaPipe LLM Inference runtime — used for Gemma 4 .task
         *  bundles published by `litert-community` on HuggingFace. The
         *  `gemma-4-E{2,4}B-it-web.task` files inside the
         *  `gemma-4-E{2,4}B-it-litert-lm` repos are the MediaPipe-compatible
         *  variant; the `.litertlm` files in the same repo target the native
         *  LiteRT-LM runtime which we don't use. */
        MEDIAPIPE
    }

    data class GenerationConfig(
        val temperature: Float = 0.1f,
        val topP: Float = 0.95f,
        val topK: Int = 40,
        val repeatPenalty: Float = 1.0f
    )

    data class RuntimeStats(
        val lastLoadMs: Long = 0L,
        val lastInferenceMs: Long = 0L,
        val coldLoads: Int = 0,
        val warmStarts: Int = 0,
        val lastStartWasWarm: Boolean = false
    )

    private data class DownloadResult(
        val usedResume: Boolean
    )

    sealed class ModelState {
        data object NotDownloaded : ModelState()
        data class Downloading(val bytesDownloaded: Long, val totalBytes: Long) : ModelState()
        data object Verifying : ModelState()
        data class Installing(val bytesProcessed: Long, val totalBytes: Long) : ModelState()
        data object Ready : ModelState()
        data class Error(val message: String) : ModelState()
        data object Paused : ModelState()
    }

    private val _state = MutableStateFlow<ModelState>(ModelState.NotDownloaded)
    val state: StateFlow<ModelState> = _state
    private val _isPreparingModel = MutableStateFlow(false)
    val isPreparingModel: StateFlow<Boolean> = _isPreparingModel
    private val _runtimeStats = MutableStateFlow(RuntimeStats())
    val runtimeStats: StateFlow<RuntimeStats> = _runtimeStats

    private val modelsDir = File(context.noBackupFilesDir, "llm_models").apply { mkdirs() }

    // Lazy OkHttpClient — only created when a download starts, avoids ~1-3 MB of idle
    // connection pool + thread pool memory when no download is in progress.
    private var clientBacking: OkHttpClient? = null
    private val client: OkHttpClient
        get() = clientBacking ?: OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(120, TimeUnit.SECONDS)
            .build()
            .also { clientBacking = it }

    /** Release OkHttpClient resources after download completes (frees idle threads + connections). */
    private fun releaseHttpClient() {
        clientBacking?.let { c ->
            c.dispatcher.executorService.shutdown()
            c.connectionPool.evictAll()
        }
        clientBacking = null
    }

    private var downloadJob: Job? = null
    @Volatile private var activeCall: Call? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    // LlamaBridge inference state — LlamaBridge is a singleton object,
    // so we only track loaded/inferring state, no instance references needed.
    // All three flags are @Volatile for cross-thread visibility; actual
    // synchronization is provided by loadMutex.
    @Volatile private var modelLoaded = false
    @Volatile private var inferring = false
    @Volatile private var nativeAvailable: Boolean? = null
    @Volatile private var verifiedModelFingerprint: String? = null
    private val loadMutex = Mutex()
    private val inferenceMutex = Mutex()
    private var autoUnloadJob: Job? = null
    @Volatile private var loadCleanupPending = false
    @Volatile private var warmLeaseUntilMs = 0L
    private var timedOutLoadCleanupJob: Job? = null
    private val preparingModelCount = AtomicInteger(0)

    init {
        context.registerComponentCallbacks(this)
        // Guard: only load native library on supported ABIs (arm64-v8a, x86_64).
        // 32-bit devices (armeabi-v7a) would crash on System.loadLibrary since
        // we don't ship a 32-bit .so.
        if (isSupportedAbi()) {
            try {
                LlamaBridge.initialize(context)
            } catch (e: UnsatisfiedLinkError) {
                Log.e(TAG, "Native library load failed (ABI=${android.os.Build.SUPPORTED_ABIS.toList()})", e)
                nativeAvailable = false
            }
        } else {
            nativeAvailable = false
            Log.w(TAG, "Device ABI not supported for local Qwen: ${android.os.Build.SUPPORTED_ABIS.toList()}. " +
                "On-device note extraction disabled; Regex fallback will be used.")
        }
    }

    /** Check if device ABI matches our native library builds (arm64-v8a, x86_64). */
    fun isSupportedAbi(): Boolean {
        val supported = setOf("arm64-v8a", "x86_64")
        return android.os.Build.SUPPORTED_ABIS.any { it in supported }
    }

    /** User-overridden tier, or null to use hardware recommendation. */
    var overrideTier: ModelTier? = null

    /** Active tier: user override if set, otherwise hardware-recommended. */
    fun activeTier(): ModelTier = normalizeSupportedTier(overrideTier) ?: recommendedTier()

    /**
     * Inference backend for the active tier.
     *
     * The artifact's declared backend is the canonical source of truth — for
     * Gemma 4 tiers this is MEDIAPIPE regardless of device RAM. Previously this
     * resolved purely from RAM via [backendForRam], which incorrectly returned
     * MNN on high-RAM devices even when the active tier was Gemma. That caused
     * the MNN-shaped validator to reject Gemma's single-file `.task` install
     * and the on-device path silently fell back to regex.
     */
    fun activeBackend(): InferenceBackend = artifactFor(activeTier(), deviceRamGb()).backend

    fun supportsOnDeviceVision(): Boolean = ON_DEVICE_VISION_ENABLED && activeTier().supportsVision

    /** Directory containing the active backend's on-device model payload. */
    val modelDir: File get() = installRootFor(modelsDir, activeTier(), deviceRamGb())

    /** Active backend model entry point: MNN directory or llama.cpp GGUF file. */
    val modelFile: File get() = modelFileFor(modelsDir, activeTier(), deviceRamGb())

    fun activeModelSizeMb(): Int = modelSizeMbFor(activeTier(), deviceRamGb())

    fun activeExpectedSha256(): String = expectedSha256For(activeTier(), deviceRamGb())

    fun isModelDownloaded(): Boolean {
        if (isInstallInProgressState()) return false
        return isModelInstalled(modelsDir, activeTier(), deviceRamGb())
    }

    fun isNativeAvailable(): Boolean {
        nativeAvailable?.let { return it }

        if (!isSupportedAbi()) {
            nativeAvailable = false
            return false
        }

        return try {
            Class.forName("com.chartlite.llm.LlamaBridge")
            nativeAvailable = true
            true
        } catch (_: Exception) {
            nativeAvailable = false
            false
        }
    }

    fun isReady(): Boolean {
        val downloaded = isModelDownloaded()
        val native = isNativeAvailable()
        // Pinned SHA is preferred but not required: trust-on-first-download is
        // applied in `startDownload` / `importModelFile` for tiers that ship
        // without a published digest. Don't gate readiness on it here.
        if (!downloaded || !native) {
            Log.d(
                TAG,
                "isReady=false: downloaded=$downloaded, native=$native, file=${modelFile.absolutePath}"
            )
        }
        return downloaded && native
    }

    fun modelSizeBytes(): Long {
        val path = modelFile
        if (!path.exists()) return 0
        return if (path.isFile) path.length() else path.walkTopDown().filter { it.isFile }.sumOf { it.length() }
    }

    private fun isInstallInProgressState(state: ModelState = _state.value): Boolean =
        state is ModelState.Downloading || state is ModelState.Verifying || state is ModelState.Installing

    private data class MemoryBudget(
        val availableRamBytes: Long,
        val requiredRamBytes: Long,
        val headroomBytes: Long,
        val burstBytes: Long
    )

    private fun currentMemoryBudget(forInference: Boolean): MemoryBudget {
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memInfo = ActivityManager.MemoryInfo()
        am.getMemoryInfo(memInfo)

        val modelBytes = modelSizeBytes().takeIf { it > 0L }
            ?: (activeModelSizeMb().toLong() * 1024L * 1024L)
        val ramGb = deviceRamGb()
        val backend = activeBackend()
        val useMmap = backend == InferenceBackend.LLAMA_CPP
        val isUltraLowRam = ramGb <= ULTRA_LOW_RAM_DEVICE_GB
        val isLowRamDevice = ramGb <= LOW_RAM_DEVICE_GB

        // llama.cpp uses mmap — the OS pages model weights from disk on demand,
        // so the file size does NOT count against available RAM like a malloc.
        // Only context buffers + KV cache consume real RSS (~100-150MB for 0.8B Q4).
        // MNN malloc's the full model, so file size directly maps to RSS.
        val modelRssEstimate = if (useMmap) {
            128L * 1024 * 1024  // KV cache + context + batch scratch for 0.8B Q4
        } else {
            modelBytes / 2
        }
        val baseHeadroom = if (useMmap) {
            128L * 1024 * 1024  // mmap pages are clean — kernel reclaims freely under pressure
        } else {
            (modelBytes / 4).coerceIn(128L * 1024 * 1024, 384L * 1024 * 1024)
        }
        // Ultra-low-RAM (≤3GB): aggressive but safe — onTrimMemory auto-unloads if pressured.
        // Context is 2048 (not 4096) so KV cache is ~50-80MB, batch=64 is tiny.
        val tierHeadroom = when (activeTier()) {
            ModelTier.SMALL -> when {
                useMmap && isUltraLowRam -> 128L * 1024 * 1024  // llama.cpp mmap: minimal headroom needed
                useMmap && isLowRamDevice -> 192L * 1024 * 1024
                isUltraLowRam -> 384L * 1024 * 1024   // MNN: tight but workable
                isLowRamDevice -> 512L * 1024 * 1024   // MNN: moderate
                else -> 512L * 1024 * 1024
            }
            ModelTier.LARGE -> 1024L * 1024 * 1024
            // MediaPipe handles its own delegate memory (NNAPI/GPU); we still
            // reserve broadly to avoid OOM during model load + KV cache.
            ModelTier.GEMMA_E2B -> 1024L * 1024 * 1024
            ModelTier.GEMMA_E4B -> 1536L * 1024 * 1024
        }
        val burst = if (!forInference) {
            0L
        } else when (activeTier()) {
            ModelTier.SMALL -> when {
                useMmap && isUltraLowRam -> 64L * 1024 * 1024   // llama.cpp: small decode burst
                useMmap && isLowRamDevice -> 96L * 1024 * 1024
                isUltraLowRam -> 192L * 1024 * 1024    // MNN: leaves room for KV/cache growth on 3GB devices
                isLowRamDevice -> 256L * 1024 * 1024
                else -> 256L * 1024 * 1024
            }
            ModelTier.LARGE -> 512L * 1024 * 1024
            ModelTier.GEMMA_E2B -> 384L * 1024 * 1024
            ModelTier.GEMMA_E4B -> 512L * 1024 * 1024
        }
        val headroom = maxOf(baseHeadroom, tierHeadroom)
        val required = modelRssEstimate + headroom + burst
        return MemoryBudget(
            availableRamBytes = memInfo.availMem,
            requiredRamBytes = required,
            headroomBytes = headroom,
            burstBytes = burst
        )
    }

    // Reuse MemoryInfo object to avoid allocation on every availableRamBytes() call.
    // Called 3-5 times per inference cycle from headroom checks.
    private val reusableMemInfo = ActivityManager.MemoryInfo()
    private fun availableRamBytes(): Long {
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        am.getMemoryInfo(reusableMemInfo)
        return reusableMemInfo.availMem
    }

    private fun availableRamMb(): Long = availableRamBytes() / 1024 / 1024

    private fun autoUnloadDelayMs(): Long = when {
        deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> ULTRA_LOW_RAM_AUTO_UNLOAD_DELAY_MS
        deviceRamGb() <= LOW_RAM_DEVICE_GB -> LOW_RAM_AUTO_UNLOAD_DELAY_MS
        deviceRamGb() < 4.0 -> MID_RAM_AUTO_UNLOAD_DELAY_MS
        else -> DEFAULT_AUTO_UNLOAD_DELAY_MS
    }

    private fun modelLoadTimeoutMs(): Long = when {
        deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> ULTRA_LOW_RAM_MODEL_LOAD_TIMEOUT_MS
        deviceRamGb() <= LOW_RAM_DEVICE_GB -> LOW_RAM_MODEL_LOAD_TIMEOUT_MS
        else -> DEFAULT_MODEL_LOAD_TIMEOUT_MS
    }

    private fun inferenceTimeoutMs(): Long = when {
        deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> ULTRA_LOW_RAM_INFERENCE_TIMEOUT_MS
        deviceRamGb() <= LOW_RAM_DEVICE_GB -> LOW_RAM_INFERENCE_TIMEOUT_MS
        else -> DEFAULT_INFERENCE_TIMEOUT_MS
    }

    private fun validateInstalledModelDirectoryOrThrow(dir: File, tier: ModelTier) {
        if (hasRequiredModelFiles(dir, tier)) return

        val missing = requiredModelFiles(tier).filter { name ->
            val file = File(dir, name)
            !file.exists() || file.length() <= 0L
        }
        val staleVision = !tier.supportsVision && File(dir, "visual.mnn").exists()
        val detail = buildString {
            if (missing.isNotEmpty()) {
                append("missing ")
                append(missing.joinToString(", "))
            }
            if (staleVision) {
                if (isNotEmpty()) append("; ")
                append("stale visual.mnn from an older vision install")
            }
        }.ifBlank { "unexpected extracted file layout" }

        throw IllegalStateException(
            "Installed ${tier.label} files are incomplete: $detail. Re-download or re-import the model."
        )
    }

    private fun validateInstalledModelOrThrow(path: File, tier: ModelTier, backend: InferenceBackend) {
        when (backend) {
            InferenceBackend.MNN -> validateInstalledModelDirectoryOrThrow(path, tier)
            InferenceBackend.LLAMA_CPP, InferenceBackend.MEDIAPIPE -> {
                if (!path.exists() || path.length() <= 0L) {
                    val artifactKind = when (backend) {
                        InferenceBackend.MEDIAPIPE -> "MediaPipe .task bundle"
                        InferenceBackend.LLAMA_CPP -> "GGUF file"
                        else -> "model file"
                    }
                    throw IllegalStateException(
                        "Installed ${tier.label} $artifactKind is missing or empty at " +
                            "${path.absolutePath}. Re-download or re-import the model."
                    )
                }
            }
        }
    }

    fun hasRuntimeHeadroom(forInference: Boolean = true): Boolean {
        if (!isModelDownloaded() || !isSupportedAbi()) return false

        // If the model is already loaded in memory, we only need burst headroom
        // for the next inference — the expensive model loading is already done.
        // This prevents the second extraction step from falling back to Regex
        // on 3GB devices where the loaded model itself consumes the "available" RAM.
        if (modelLoaded && forInference) {
            val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            val memInfo = ActivityManager.MemoryInfo()
            am.getMemoryInfo(memInfo)
            val backend = activeBackend()
            val burst = when (activeTier()) {
                ModelTier.SMALL -> when {
                    backend == InferenceBackend.LLAMA_CPP && deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> 64L * 1024 * 1024
                    backend == InferenceBackend.LLAMA_CPP -> 96L * 1024 * 1024
                    deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> 192L * 1024 * 1024
                    else -> 256L * 1024 * 1024
                }
                ModelTier.LARGE -> 512L * 1024 * 1024
                ModelTier.GEMMA_E2B -> 384L * 1024 * 1024
                ModelTier.GEMMA_E4B -> 512L * 1024 * 1024
            }
            val hasHeadroom = memInfo.availMem >= burst
            if (!hasHeadroom) {
                Log.w(TAG, "Model loaded but insufficient burst headroom: " +
                    "available=${memInfo.availMem / 1024 / 1024}MB, need=${burst / 1024 / 1024}MB burst")
            }
            return hasHeadroom
        }

        val budget = currentMemoryBudget(forInference)
        val hasHeadroom = budget.availableRamBytes >= budget.requiredRamBytes
        if (!hasHeadroom) {
            Log.w(
                TAG,
                "Skipping on-device LLM: available=${budget.availableRamBytes / 1024 / 1024}MB " +
                    "required=${budget.requiredRamBytes / 1024 / 1024}MB " +
                    "(headroom=${budget.headroomBytes / 1024 / 1024}MB, burst=${budget.burstBytes / 1024 / 1024}MB)"
            )
        }
        return hasHeadroom
    }

    fun isConstrainedDevice(): Boolean = deviceRamGb() <= CONSTRAINED_DEVICE_GB

    fun isUltraLowRamDevice(): Boolean = deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB

    /**
     * Low-RAM handoff helper: true while native generation is active or a timed-out
     * load is still cleaning itself up. Starting ASR during either state risks overlap.
     */
    fun isBusyForLowRamHandoff(): Boolean = inferring || loadCleanupPending

    fun maxTranscriptChars(): Int = when {
        activeTier() == ModelTier.LARGE -> LARGE_MODEL_MAX_TRANSCRIPT_CHARS
        deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> ULTRA_LOW_RAM_MAX_TRANSCRIPT_CHARS
        deviceRamGb() <= LOW_RAM_DEVICE_GB -> LOW_RAM_MAX_TRANSCRIPT_CHARS
        else -> DEFAULT_MAX_TRANSCRIPT_CHARS
    }

    fun shouldSkipLongTranscript(transcriptChars: Int): Boolean {
        val maxChars = maxTranscriptChars()
        val shouldSkip = transcriptChars > maxChars
        if (shouldSkip) {
            Log.w(
                TAG,
                "Skipping on-device LLM for long transcript: chars=$transcriptChars, max=$maxChars, " +
                    "tier=${activeTier().name}, ram=${"%.1f".format(deviceRamGb())}GB"
            )
        }
        return shouldSkip
    }

    fun recommendedOutputTokens(): Int = when {
        activeTier() == ModelTier.LARGE -> LARGE_MODEL_MAX_OUTPUT_TOKENS
        // Ultra-low-RAM: n_ctx=2048, must leave room for ~700 prompt tokens + 64 headroom
        deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> ULTRA_LOW_RAM_MAX_OUTPUT_TOKENS
        else -> SMALL_MODEL_MAX_OUTPUT_TOKENS
    }

    fun recommendedExtractionOutputTokens(): Int = when {
        activeTier() == ModelTier.LARGE -> LARGE_MODEL_EXTRACTION_OUTPUT_TOKENS
        deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> ULTRA_LOW_RAM_EXTRACTION_OUTPUT_TOKENS
        deviceRamGb() <= LOW_RAM_DEVICE_GB -> LOW_RAM_EXTRACTION_OUTPUT_TOKENS
        else -> SMALL_MODEL_EXTRACTION_OUTPUT_TOKENS
    }

    fun recommendedNoteOutputTokens(): Int = when {
        activeTier() == ModelTier.LARGE -> LARGE_MODEL_NOTE_OUTPUT_TOKENS
        else -> SMALL_MODEL_NOTE_OUTPUT_TOKENS
    }

    fun recommendedSnippetOutputTokens(): Int = when {
        activeTier() == ModelTier.LARGE -> LARGE_MODEL_MAX_SNIPPET_OUTPUT_TOKENS
        deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> ULTRA_LOW_RAM_MAX_SNIPPET_OUTPUT_TOKENS
        else -> SMALL_MODEL_MAX_SNIPPET_OUTPUT_TOKENS
    }

    private suspend fun prepareInstallDirectory(destDir: File) {
        if (loadCleanupPending) {
            throw IllegalStateException("Previous model load is still cleaning up. Try again in a few seconds.")
        }
        if (inferring) {
            throw IllegalStateException("Wait for note processing to finish before replacing the on-device model.")
        }
        unloadModelIfIdleAndWait()
        if (destDir.exists()) {
            Log.w(TAG, "Clearing existing model directory before install: ${destDir.absolutePath}")
            destDir.deleteRecursively()
        }
        if (!destDir.mkdirs() && !destDir.exists()) {
            throw IllegalStateException("Unable to create model directory: ${destDir.absolutePath}")
        }
    }

    private suspend fun installModelArchive(
        zipFile: File,
        destDir: File,
        tier: ModelTier,
        onProgress: ((Long, Long) -> Unit)? = null
    ) {
        prepareInstallDirectory(destDir)
        try {
            extractZip(zipFile, destDir, onProgress)
            validateInstalledModelDirectoryOrThrow(destDir, tier)
            clearVerifiedModelCache()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to install ${tier.label}; clearing partial files", e)
            destDir.deleteRecursively()
            destDir.mkdirs()
            clearVerifiedModelCache()
            throw e
        }
    }

    private suspend fun installModelFile(sourceFile: File, destDir: File, destFileName: String) {
        prepareInstallDirectory(destDir)
        try {
            val destFile = File(destDir, destFileName)
            sourceFile.copyTo(destFile, overwrite = true)
            if (!destFile.exists() || destFile.length() == 0L) {
                throw IllegalStateException("Copied GGUF file is empty")
            }
            clearVerifiedModelCache()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to install GGUF model file; clearing partial files", e)
            destDir.deleteRecursively()
            destDir.mkdirs()
            clearVerifiedModelCache()
            throw e
        }
    }

    private suspend fun runNativeLoadWithTimeout(modelPath: File, backend: InferenceBackend, timeoutMs: Long): Boolean {
        if (loadCleanupPending) {
            throw IllegalStateException("Previous model load is still cleaning up. Try again in a few seconds.")
        }

        val loadTask = scope.async(Dispatchers.IO) {
            // For Gemma 4 we load via MediaPipe (Google's native runtime).
            // The .task bundle is a single file, so modelPath is the file itself.
            if (activeTier().family == ModelFamily.GEMMA) {
                com.chartlite.llm.GemmaBridge.initModel(
                    context = context,
                    modelFile = modelPath,
                    maxTokensCap = 4096,
                    topK = 40,
                    temperature = 0.1f,
                )
            } else {
                LlamaBridge.initGenerateModel(
                    modelPath.absolutePath,
                    when (backend) {
                        InferenceBackend.MNN -> LlamaBridge.Backend.MNN
                        InferenceBackend.LLAMA_CPP -> LlamaBridge.Backend.LLAMA_CPP
                        // Should never reach here — Gemma path is taken in the if-branch above.
                        // Defensive: fall through to llama.cpp if somehow misrouted.
                        InferenceBackend.MEDIAPIPE -> LlamaBridge.Backend.LLAMA_CPP
                    }
                )
            }
        }

        val success = withTimeoutOrNull(timeoutMs) { loadTask.await() }
        if (success != null) return success

        Log.e(TAG, "On-device ${backend.name} model load timed out after ${timeoutMs / 1000}s for ${modelPath.name}")
        loadCleanupPending = true
        timedOutLoadCleanupJob?.cancel()
        timedOutLoadCleanupJob = scope.launch(Dispatchers.IO) {
            try {
                // CRITICAL: timeout the await — if native load hangs in OOM/page reclaim,
                // an untimed await() holds loadMutex forever via the finally block,
                // blocking all future loadModel() calls permanently.
                withTimeoutOrNull(timeoutMs + 10_000L) { loadTask.await() }
            } finally {
                try {
                    LlamaBridge.shutdown()
                    com.chartlite.llm.GemmaBridge.close()
                } catch (e: Exception) {
                    Log.w(TAG, "Error cleaning up timed-out model load", e)
                }
                modelLoaded = false
                loadCleanupPending = false
                timedOutLoadCleanupJob = null
            }
        }
        throw IllegalStateException("On-device ${backend.name} model load timed out after ${timeoutMs / 1000}s")
    }

    private fun scheduleAutoUnload() {
        autoUnloadJob?.cancel()
        val baseDelayMs = autoUnloadDelayMs()
        val leaseDelayMs = (warmLeaseUntilMs - System.currentTimeMillis()).coerceAtLeast(0L)
        val delayMs = maxOf(baseDelayMs, leaseDelayMs)
        autoUnloadJob = scope.launch {
            delay(delayMs)
            if (!inferring) {
                Log.d(
                    TAG,
                    "Auto-unloading model after ${delayMs / 1000}s idle (avail=${availableRamMb()}MB)"
                )
                unloadModel()
            }
        }
    }

    private fun markModelPreparing(active: Boolean) {
        if (active) {
            if (preparingModelCount.incrementAndGet() == 1) {
                _isPreparingModel.value = true
            }
            return
        }

        val remaining = preparingModelCount.decrementAndGet()
        if (remaining <= 0) {
            preparingModelCount.set(0)
            _isPreparingModel.value = false
        }
    }

    // ── Model loading ──

    /**
     * Load the model into memory for inference.
     * Uses [loadMutex] to prevent concurrent double-loading and to
     * coordinate with [unloadModel] / [onTrimMemory].
     *
     * On-device JNI bridge loading:
     * - Takes a file path string (no ContentResolver/FileProvider/FD dance)
     * - Returns Boolean on failure
     * - Dispatches to the selected backend for this device
     * - Supports updateGenerateParams for temperature/maxTokens control
     */
    suspend fun loadModel() {
        if (modelLoaded) return
        if (!isModelDownloaded()) throw IllegalStateException("Model not downloaded")
        if (loadCleanupPending) {
            throw IllegalStateException("Previous model load is still cleaning up. Try again in a few seconds.")
        }

        markModelPreparing(true)
        try {
            // Timeout on mutex acquisition — prevents hanging forever if a previous
            // load is stuck in native code (OOM/page reclaim on 3GB devices).
            val acquired = withTimeoutOrNull(modelLoadTimeoutMs() + 15_000L) {
                loadMutex.lock()
                true
            }
            if (acquired == null) {
                throw IllegalStateException("Timed out waiting for model load lock — previous load may be stuck")
            }

            try {
                // Re-check after acquiring lock
                if (modelLoaded) return
                if (loadCleanupPending) {
                    throw IllegalStateException("Previous model load is still cleaning up. Try again in a few seconds.")
                }

                val startedAt = System.currentTimeMillis()
                val timeoutMs = modelLoadTimeoutMs()
                withContext(Dispatchers.IO) {
                    val backend = activeBackend()
                    val path = modelFile
                    val tier = activeTier()
                    validateInstalledModelOrThrow(path, tier, backend)
                    val budget = currentMemoryBudget(forInference = true)
                    if (budget.availableRamBytes < budget.requiredRamBytes) {
                        Log.w(TAG, "Insufficient system memory to load LLM: " +
                            "${budget.availableRamBytes / 1024 / 1024}MB available, need " +
                            "${budget.requiredRamBytes / 1024 / 1024}MB " +
                            "(model mmap working set + ${budget.headroomBytes / 1024 / 1024}MB headroom + " +
                            "${budget.burstBytes / 1024 / 1024}MB inference burst)")
                        throw IllegalStateException("Not enough free memory for on-device note processing")
                    }

                    Log.d(
                        TAG,
                        "Loading model via ${backendDisplayName(backend)}: ${path.name} " +
                            "(avail=${availableRamMb()}MB, timeout=${timeoutMs / 1000}s)"
                    )

                    val success = runNativeLoadWithTimeout(path, backend, timeoutMs)
                    if (!success) {
                        throw IllegalStateException("${backendDisplayName(backend)} model load failed for ${path.name}")
                    }

                    // Keep the on-device generation budget conservative so structured
                    // extraction completes promptly instead of drifting into multi-minute runs.
                    applyGenerationParams(recommendedOutputTokens())

                    modelLoaded = true
                    val loadElapsedMs = System.currentTimeMillis() - startedAt
                    _runtimeStats.update {
                        it.copy(
                            lastLoadMs = loadElapsedMs,
                            coldLoads = it.coldLoads + 1,
                            lastStartWasWarm = false
                        )
                    }
                    Log.d(
                        TAG,
                        "Model loaded: ${path.name} via ${backendDisplayName(backend)} in ${loadElapsedMs}ms " +
                            "(avail=${availableRamMb()}MB)"
                    )
                }
            } finally {
                loadMutex.unlock()
            }
        } finally {
            markModelPreparing(false)
        }
    }

    /**
     * Unload the model from memory.
     * Uses [loadMutex] (same lock as [loadModel]) to prevent races where
     * onTrimMemory could shutdown the native context mid-load.
     * Skipped if inference is currently in progress.
     */
    fun unloadModel() {
        // tryLock: non-blocking so onTrimMemory / onLowMemory don't deadlock.
        // If the lock is held, loadModel is in progress — skip the unload.
        if (!loadMutex.tryLock()) {
            Log.d(TAG, "Skipping unload — loadMutex held (load in progress)")
            return
        }
        try {
            if (inferring) {
                Log.w(TAG, "Skipping unload — inference in progress")
                return
            }
            if (modelLoaded) {
                try {
                    LlamaBridge.shutdown()
                    com.chartlite.llm.GemmaBridge.close()
                } catch (e: Exception) {
                    Log.w(TAG, "Error during LlamaBridge.shutdown()", e)
                }
                modelLoaded = false
                warmLeaseUntilMs = 0L
                System.gc() // Help the OS observe reclaimed native model memory sooner
                Log.d(TAG, "Model unloaded (avail=${availableRamMb()}MB)")
            }
        } finally {
            loadMutex.unlock()
        }
    }

    /**
     * Synchronously unload the model when the manager is idle.
     * Use this before reloading offline ASR on low-memory devices so the two
     * native runtimes never overlap during a handoff.
     */
    suspend fun unloadModelIfIdleAndWait(): Boolean = withContext(Dispatchers.IO) {
        autoUnloadJob?.cancel()
        val startedAt = System.currentTimeMillis()
        loadMutex.withLock {
            if (inferring) {
                Log.w(TAG, "Skipping blocking unload — inference in progress")
                return@withLock false
            }
            if (!modelLoaded) {
                return@withLock false
            }
            try {
                LlamaBridge.shutdown()
                com.chartlite.llm.GemmaBridge.close()
            } catch (e: Exception) {
                Log.w(TAG, "Error during blocking LlamaBridge.shutdown()", e)
            }
            modelLoaded = false
            warmLeaseUntilMs = 0L
            Log.d(
                TAG,
                "Blocking model unload finished in ${System.currentTimeMillis() - startedAt}ms " +
                    "(avail=${availableRamMb()}MB)"
            )
            true
        }
    }

    fun cancelInference() {
        if (!inferring) return
        Log.w(TAG, "Cancelling in-flight on-device inference")
        LlamaBridge.cancelGeneration()
    }

    /**
     * Keep the current model load warm for a short period after inference so
     * note review / immediate follow-up extraction doesn't pay another cold load.
     * ASR handoff still forces an unload when recording starts.
     */
    fun keepModelWarmFor(durationMs: Long) {
        if (durationMs <= 0L) return
        val keepUntil = System.currentTimeMillis() + durationMs
        if (keepUntil > warmLeaseUntilMs) {
            warmLeaseUntilMs = keepUntil
        }
        if (modelLoaded && !inferring) {
            scheduleAutoUnload()
        }
    }

    fun recommendedReviewWarmLeaseMs(): Long {
        val lastLoadMs = runtimeStats.value.lastLoadMs
        return when {
            deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB && lastLoadMs >= 10_000L -> 180_000L
            deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> 150_000L
            deviceRamGb() <= LOW_RAM_DEVICE_GB && lastLoadMs >= 6_000L -> 150_000L
            deviceRamGb() <= LOW_RAM_DEVICE_GB -> 120_000L
            else -> 90_000L
        }
    }

    suspend fun prewarmModel(): Boolean {
        if (!isReady()) return false
        if (modelLoaded) {
            keepModelWarmFor(recommendedReviewWarmLeaseMs())
            return true
        }
        if (loadCleanupPending || inferring || _isPreparingModel.value) return true
        if (!hasRuntimeHeadroom(forInference = false)) return false

        return try {
            loadModel()
            keepModelWarmFor(recommendedReviewWarmLeaseMs())
            true
        } catch (e: Exception) {
            Log.w(TAG, "Background model prewarm skipped", e)
            false
        }
    }

    fun isModelLoaded(): Boolean = modelLoaded

    // ── Inference ──

    /**
     * Ensure the model is loaded and ready for API calls like [LlamaBridge.applyChatTemplate].
     * Safe to call multiple times — no-op if already loaded.
     */
    suspend fun ensureModelLoaded() {
        if (!modelLoaded) loadModel()
    }

    /**
     * Run inference on the loaded model.
     * Returns the generated text or null on failure.
     * Automatically unloads the model after completion to free RAM.
     */
    suspend fun runInference(
        prompt: String,
        maxTokens: Int = recommendedOutputTokens(),
        config: GenerationConfig = GenerationConfig()
    ): String? = executeInference("generate", maxTokens, config) {
        LlamaBridge.generate(prompt)
    }

    /**
     * Run chat-based inference with structured system/user messages.
     * The active backend applies the model's native chat template when available,
     * avoiding manual prompt tags that can tokenize incorrectly.
     */
    suspend fun runChatInference(
        systemPrompt: String,
        userMessage: String,
        maxTokens: Int = recommendedOutputTokens(),
        config: GenerationConfig = GenerationConfig()
    ): String? = executeInference("generateChat", maxTokens, config) {
        // Vendor-native dispatch: Qwen → MNN/llama.cpp via LlamaBridge,
        // Gemma → MediaPipe LLM Inference via GemmaBridge.
        when (activeTier().family) {
            ModelFamily.QWEN ->
                LlamaBridge.generateChat(systemPrompt, userMessage)
            ModelFamily.GEMMA ->
                com.chartlite.llm.GemmaBridge.generateChat(
                    systemPrompt = systemPrompt,
                    userMessage = userMessage,
                    topK = config.topK,
                    temperature = config.temperature
                )
        }
    }

    /**
     * Run vision inference on a clinical image.
     * The vision-language model auto-detects content type and extracts structured data.
     *
     * @param imagePath absolute path to JPEG/PNG on device storage
     */
    suspend fun runVisionInference(
        systemPrompt: String,
        userMessage: String,
        imagePath: String,
        maxTokens: Int = recommendedOutputTokens(),
        config: GenerationConfig = GenerationConfig()
    ): String? {
        if (!supportsOnDeviceVision()) {
            Log.w(TAG, "On-device vision is disabled; skipping vision inference request")
            return null
        }
        return executeInference("generateVision", maxTokens, config) {
            // Vendor-native dispatch: Qwen → MNN/llama.cpp via LlamaBridge
            // (currently a stub returning null — to be implemented), Gemma 4
            // → MediaPipe LLM Inference via GemmaBridge.
            when (activeTier().family) {
                ModelFamily.QWEN ->
                    LlamaBridge.generateVision(systemPrompt, userMessage, imagePath)
                ModelFamily.GEMMA ->
                    com.chartlite.llm.GemmaBridge.generateVision(
                        systemPrompt = systemPrompt,
                        userMessage = userMessage,
                        imagePath = imagePath,
                        topK = config.topK,
                        temperature = config.temperature,
                    )
            }
        }
    }

    /**
     * Run JSON schema-constrained inference.
     * The model is forced to output valid JSON matching the provided schema,
     * eliminating parse failures from free-text generation.
     *
     * @param prompt The extraction prompt
     * @param jsonSchema JSON schema string constraining the output structure
     * @return Valid JSON string or null on failure
     */
    suspend fun runInferenceJson(
        prompt: String,
        jsonSchema: String,
        maxTokens: Int = recommendedOutputTokens(),
        config: GenerationConfig = GenerationConfig()
    ): String? = executeInference("generateJson", maxTokens, config) {
        LlamaBridge.generateJson(prompt, jsonSchema)
    }

    /**
     * Shared inference lifecycle: load → infer → delayed unload.
     * The [inferring] flag is held for the full duration so that
     * [onTrimMemory] cannot unload the model mid-inference.
     *
     * Model is kept loaded for [autoUnloadDelayMs] after inference to avoid
     * repeated load/unload cycles when processing multiple snippets in a session.
     * System memory pressure (onTrimMemory) overrides the delay if RAM is needed.
     */
    private suspend fun executeInference(
        label: String,
        maxTokens: Int,
        config: GenerationConfig,
        generate: () -> String?
    ): String? {
        autoUnloadJob?.cancel()
        val timeoutMs = inferenceTimeoutMs()
        val startedAt = System.currentTimeMillis()
        val warmStart = modelLoaded
        if (warmStart) {
            _runtimeStats.update {
                it.copy(
                    warmStarts = it.warmStarts + 1,
                    lastStartWasWarm = true
                )
            }
        }
        return try {
            // Set inferring BEFORE loadModel() to prevent onTrimMemory from
            // unloading mid-load on 3GB devices under memory pressure.
            inferring = true
            try {
                if (!modelLoaded) loadModel()
            } catch (e: Exception) {
                inferring = false
                throw e
            }

            val result = CompletableDeferred<String?>()
            val generationJob = scope.launch {
                try {
                    inferenceMutex.withLock {
                        applyGenerationParams(maxTokens, config)
                        Log.d(
                            TAG,
                            "Starting $label inference " +
                                "(start=${if (warmStart) "warm" else "cold"}, maxTokens=$maxTokens, " +
                                "timeout=${timeoutMs / 1000}s, avail=${availableRamMb()}MB)"
                        )

                        val text = generate()

                        if (text.isNullOrBlank()) {
                            Log.w(TAG, "LlamaBridge.$label returned empty")
                            result.complete(null)
                        } else {
                            val inferenceElapsedMs = System.currentTimeMillis() - startedAt
                            _runtimeStats.update {
                                it.copy(
                                    lastInferenceMs = inferenceElapsedMs,
                                    lastStartWasWarm = warmStart
                                )
                            }
                            Log.d(
                                TAG,
                                "$label inference complete: ${text.length} chars " +
                                    "in ${inferenceElapsedMs}ms (start=${if (warmStart) "warm" else "cold"}, avail=${availableRamMb()}MB)"
                            )
                            result.complete(text)
                        }
                    }
                } catch (e: CancellationException) {
                    if (!result.isCompleted) result.complete(null)
                    throw e
                } catch (e: Exception) {
                    Log.e(TAG, "$label inference failed", e)
                    if (!result.isCompleted) result.complete(null)
                } finally {
                    inferring = false
                    scheduleAutoUnload()
                }
            }

            try {
                val awaited = withTimeoutOrNull(timeoutMs) { result.await() }
                if (awaited != null || result.isCompleted) {
                    awaited
                } else {
                    Log.e(TAG, "$label inference timed out after ${timeoutMs / 1000}s; signalling native inference stop")
                    cancelInference()
                    val joined = withContext(NonCancellable) {
                        withTimeoutOrNull(CANCEL_WAIT_TIMEOUT_MS) {
                            generationJob.join()
                            true
                        }
                    } ?: false
                    if (!joined) {
                        Log.e(TAG, "Timed out waiting for cancelled $label inference to stop; scheduling deferred cleanup")
                        scope.launch {
                            val eventuallyJoined = withTimeoutOrNull(DEFERRED_CANCEL_CLEANUP_TIMEOUT_MS) {
                                generationJob.join()
                                true
                            } ?: false
                            if (!eventuallyJoined) {
                                Log.e(TAG, "$label native generation still running after deferred cleanup timeout")
                            }
                            unloadModelIfIdleAndWait()
                        }
                    }
                    null
                }
            } catch (e: CancellationException) {
                Log.w(TAG, "$label cancelled; signalling native inference stop")
                cancelInference()
                val joined = withContext(NonCancellable) {
                    withTimeoutOrNull(CANCEL_WAIT_TIMEOUT_MS) {
                        generationJob.join()
                        true
                    }
                } ?: false
                if (!joined) {
                    Log.e(TAG, "Timed out waiting for cancelled $label inference to stop; scheduling deferred cleanup")
                    scope.launch {
                        val eventuallyJoined = withTimeoutOrNull(DEFERRED_CANCEL_CLEANUP_TIMEOUT_MS) {
                            generationJob.join()
                            true
                        } ?: false
                        if (!eventuallyJoined) {
                            Log.e(TAG, "$label native generation still running after deferred cleanup timeout")
                        }
                        unloadModelIfIdleAndWait()
                    }
                }
                throw e
            }
        } catch (e: CancellationException) {
            throw e // don't swallow coroutine cancellation
        } catch (e: Exception) {
            Log.e(TAG, "$label inference failed", e)
            null
        }
    }

    private fun applyGenerationParams(maxTokens: Int, config: GenerationConfig = GenerationConfig()) {
        LlamaBridge.updateGenerateParams(
            temperature = config.temperature,
            maxTokens = maxTokens,
            topP = config.topP,
            topK = config.topK,
            repeatPenalty = config.repeatPenalty
        )
    }

    // ── ComponentCallbacks2 — respond to system memory pressure ──

    override fun onTrimMemory(level: Int) {
        @Suppress("DEPRECATION")
        val threshold = ComponentCallbacks2.TRIM_MEMORY_RUNNING_LOW
        // Check inferring flag atomically: only unload if no inference is running.
        // The inferring flag is set before inferenceMutex is acquired (line 474),
        // so checking it here prevents the race where onTrimMemory fires between
        // loadModel() and inferring=true.
        if (level >= threshold && modelLoaded && !inferring) {
            // Try to acquire inferenceMutex to ensure no inference is in-progress.
            // If locked, an inference is running — skip unload to avoid SIGSEGV.
            if (inferenceMutex.tryLock()) {
                try {
                    Log.w(TAG, "System low on memory (level=$level), unloading model")
                    unloadModel()
                } finally {
                    inferenceMutex.unlock()
                }
            } else {
                Log.w(TAG, "System low on memory but inference is active, deferring unload")
            }
        }
    }

    override fun onConfigurationChanged(newConfig: Configuration) {}
    @Deprecated("Deprecated in ComponentCallbacks", replaceWith = ReplaceWith("onTrimMemory"))
    override fun onLowMemory() {
        if (!inferring && modelLoaded) {
            if (inferenceMutex.tryLock()) {
                try { unloadModel() } finally { inferenceMutex.unlock() }
            }
        }
    }

    // ── Download ──

    fun startDownload() {
        if (downloadJob?.isActive == true) return

        val tier = activeTier()
        val ramGb = deviceRamGb()
        val backend = backendForRam(ramGb)
        val filename = modelFilenameFor(tier, ramGb)
        val modelUrl = modelUrlFor(tier, ramGb)
        downloadJob = scope.launch {
            // Note: wake locks removed — ModelDownloadService foreground service
            // keeps the process alive during screen-off / Doze mode.
            try {
                // Pinned SHA-256 is preferred. Tiers that ship without one
                // (Gemma `.task` from litert-community) fall through to
                // trust-on-first-download from the official source URL.
                val pinnedSha = pinnedSha256OrNull(tier)
                if (pinnedSha == null) {
                    Log.w(
                        TAG,
                        "${tier.label}: SHA-256 not pinned — using trust-on-first-download. " +
                            "Computed SHA will be logged after download for promotion."
                    )
                }
                val tmpFile = File(modelsDir, "${filename}.tmp")
                var resumeFromByte = if (tmpFile.exists()) tmpFile.length() else 0L
                var verified = false

                for (attempt in 1..2) {
                    _state.value = ModelState.Downloading(resumeFromByte, -1)
                    val downloadResult = downloadFile(modelUrl, tmpFile, resumeFromByte)

                    _state.value = ModelState.Verifying
                    val actualSha = sha256(tmpFile)
                    if (pinnedSha == null) {
                        Log.i(TAG, "$filename downloaded (sha256=$actualSha) — pin this digest in ModelTier when convenient")
                        verified = true
                        break
                    }
                    if (actualSha.equals(pinnedSha, ignoreCase = true)) {
                        Log.i(TAG, "SHA-256 verified for $filename via pinned digest")
                        verified = true
                        break
                    }

                    val mismatchMessage =
                        "SHA-256 mismatch (pinned). " +
                            "Expected: ${pinnedSha.take(12)}... " +
                            "Got: ${actualSha.take(12)}..."

                    // Resume can stitch bytes from an older partial; retry once from byte 0.
                    if (downloadResult.usedResume && attempt == 1) {
                        Log.w(TAG, "$mismatchMessage Retrying from scratch.")
                        tmpFile.delete()
                        resumeFromByte = 0L
                        continue
                    }

                    tmpFile.delete()
                    _state.value = ModelState.Error("SHA-256 verification failed")
                    return@launch
                }

                if (!verified) {
                    tmpFile.delete()
                    _state.value = ModelState.Error("SHA-256 verification failed")
                    return@launch
                }

                val destDir = modelDir
                if (isArchiveInstallFor(tier, ramGb)) {
                    _state.value = ModelState.Installing(0L, -1L)
                    installModelArchive(tmpFile, destDir, tier) { bytesProcessed, totalBytes ->
                        _state.value = ModelState.Installing(bytesProcessed, totalBytes)
                    }
                } else {
                    _state.value = ModelState.Installing(tmpFile.length(), tmpFile.length())
                    installModelFile(tmpFile, destDir, filename)
                }
                tmpFile.delete()
                Log.i(TAG, "Installed ${tier.label} for ${backendDisplayName(backend)} successfully")
                _state.value = ModelState.Ready

            } catch (e: CancellationException) {
                _state.value = ModelState.Paused
            } catch (e: IllegalStateException) {
                _state.value = ModelState.Error(e.message ?: "Download failed")
            } catch (e: Exception) {
                _state.value = ModelState.Error(toUserFacingDownloadError(e))
            } finally {
                releaseHttpClient() // Free connection pool + threads after download finishes
            }
        }
    }

    fun cancelDownload() {
        downloadJob?.cancel()
        activeCall?.cancel()
        _state.value = ModelState.Paused
    }

    /**
     * Import a local on-device model artifact (USB/SD sideload).
     * Installs the active backend payload and marks the model ready.
     */
    fun importModelFile(sourceFile: File, expectedSha256: String): Boolean {
        if (!isSupportedAbi()) {
            _state.value = ModelState.Error("On-device Qwen is not supported on this device")
            return false
        }
        if (!sourceFile.exists() || sourceFile.length() == 0L) {
            _state.value = ModelState.Error("Source model file not found or empty")
            return false
        }

        return try {
            val ramGb = deviceRamGb()
            val filename = modelFilenameFor(activeTier(), ramGb)
            _state.value = ModelState.Verifying

            val configuredSha = normalizeSha256(expectedSha256)
            val actualSha = sha256(sourceFile)
            if (configuredSha == null) {
                // Tier ships without a pinned SHA-256 (e.g. Gemma `.task` from
                // litert-community). Trust the sideloaded file; log the digest
                // so we can promote it into the tier definition later.
                Log.w(
                    TAG,
                    "${activeTier().label}: SHA-256 not pinned — accepting sideload (sha256=$actualSha)"
                )
            } else if (!actualSha.equals(configuredSha, ignoreCase = true)) {
                _state.value = ModelState.Error(
                    "SHA-256 mismatch. Expected: ${configuredSha.take(12)}... " +
                        "Got: ${actualSha.take(12)}..."
                )
                return false
            }

            downloadJob?.cancel()
            activeCall?.cancel()
            val destDir = modelDir
            runBlocking(Dispatchers.IO) {
                if (isArchiveInstallFor(activeTier(), ramGb)) {
                    _state.value = ModelState.Installing(0L, -1L)
                    installModelArchive(sourceFile, destDir, activeTier()) { bytesProcessed, totalBytes ->
                        _state.value = ModelState.Installing(bytesProcessed, totalBytes)
                    }
                } else {
                    _state.value = ModelState.Installing(sourceFile.length(), sourceFile.length())
                    installModelFile(sourceFile, destDir, filename)
                }
            }
            Log.i(TAG, "Imported ${activeTier().label} for ${backendDisplayName(activeBackend())} successfully")
            _state.value = ModelState.Ready
            true
        } catch (e: Exception) {
            _state.value = ModelState.Error("Model import failed: ${e.message}")
            false
        }
    }

    /** Extract a zip archive to the given directory with byte progress updates. */
    private suspend fun extractZip(
        zipFile: File,
        destDir: File,
        onProgress: ((Long, Long) -> Unit)? = null
    ) {
        ZipFile(zipFile).use { archive ->
            val entries = archive.entries().toList()
            val totalBytes = entries
                .filterNot { it.isDirectory }
                .mapNotNull { entry -> entry.size.takeIf { it > 0L } }
                .sum()
                .takeIf { it > 0L } ?: -1L

            var bytesProcessed = 0L
            var lastUpdateTime = 0L
            val destRoot = destDir.canonicalFile
            val buffer = ByteArray(8192)

            onProgress?.invoke(0L, totalBytes)

            for (entry in entries) {
                yield()
                val outFile = File(destDir, entry.name)
                val canonicalOutFile = outFile.canonicalFile
                if (!canonicalOutFile.path.startsWith(destRoot.path + File.separator) &&
                    canonicalOutFile != destRoot
                ) {
                    throw IllegalStateException("Invalid model archive entry: ${entry.name}")
                }

                if (entry.isDirectory) {
                    if (!canonicalOutFile.mkdirs() && !canonicalOutFile.exists()) {
                        throw IllegalStateException("Unable to create model directory: ${canonicalOutFile.absolutePath}")
                    }
                    continue
                }

                canonicalOutFile.parentFile?.mkdirs()
                archive.getInputStream(entry).use { input ->
                    FileOutputStream(canonicalOutFile).use { output ->
                        while (true) {
                            yield()
                            val read = input.read(buffer)
                            if (read == -1) break
                            output.write(buffer, 0, read)
                            bytesProcessed += read

                            val now = System.currentTimeMillis()
                            if (now - lastUpdateTime >= 200) {
                                onProgress?.invoke(bytesProcessed, totalBytes)
                                lastUpdateTime = now
                            }
                        }
                    }
                }
            }

            onProgress?.invoke(bytesProcessed, totalBytes)
        }
    }

    /** Cancel all coroutines and unload the model. Call on app shutdown. */
    fun close() {
        cancelDownload()
        timedOutLoadCleanupJob?.cancel()
        unloadModel()
        context.unregisterComponentCallbacks(this)
        scope.cancel()
    }

    fun deleteModel() {
        cancelDownload()
        unloadModel()
        modelsDir.deleteRecursively()
        modelsDir.mkdirs()
        clearVerifiedModelCache()
        _state.value = ModelState.NotDownloaded
    }

    fun refreshState() {
        // Note: a missing pinned SHA-256 no longer hard-errors the state.
        // Tiers that ship without one (Gemma `.task` from litert-community)
        // use trust-on-first-download in `startDownload` / `importModelFile`,
        // which logs the actual digest for later promotion.
        _state.value = when {
            isModelDownloaded() -> ModelState.Ready
            modelDir.exists() && modelDir.listFiles()?.isNotEmpty() == true ->
                ModelState.Error("Installed ${activeTier().label} files are incomplete. Re-download or re-import the model.")
            modelsDir.listFiles()?.any { it.name.endsWith(".tmp") } == true -> ModelState.Paused
            else -> {
                // Auto-detect sideloaded model on external storage / microSD
                val sideloaded = scanExternalStorageForModel()
                if (sideloaded != null) {
                    Log.i(TAG, "Found sideloaded LLM model: ${sideloaded.absolutePath}")
                    scope.launch(Dispatchers.IO) {
                        importModelFile(sideloaded, activeExpectedSha256())
                    }
                    ModelState.Verifying
                } else {
                    ModelState.NotDownloaded
                }
            }
        }
    }

    /**
     * Scan external storage directories (microSD, USB OTG) for a sideloaded model artifact.
     *
     * For zero-connectivity deployments, the active backend artifact can be pre-loaded
     * onto a microSD card at: `<sdcard>/Android/data/com.chartlite.app/files/chartlite/<filename>`
     *
     * Uses scoped storage ([Context.getExternalFilesDirs]) — no extra permissions needed.
     */
    fun scanExternalStorageForModel(): File? {
        val allDirs = context.getExternalFilesDirs(null) ?: return null
        // Skip index 0 (primary internal storage) — only check SD card / USB
        val externalDirs = allDirs.filterNotNull().drop(1)
        if (externalDirs.isEmpty()) return null

        val tier = activeTier()
        val filename = modelFilenameFor(tier, deviceRamGb())
        for (dir in externalDirs) {
            val modelFile = File(File(dir, "chartlite"), filename)
            if (modelFile.exists() && modelFile.length() > 0) {
                Log.d(TAG, "Sideloaded LLM model found: ${modelFile.absolutePath} (${modelFile.length() / 1024 / 1024} MB)")
                return modelFile
            }
        }
        return null
    }

    // ── Hardware detection ──

    enum class ModelTier(
        val label: String,
        /** Directory name under llm_models/ for extracted model files. */
        val dirName: String,
        /** Zip archive filename for download/sideload. */
        val filename: String,
        val modelUrl: String,
        val sha256: String,
        val sizeMb: Int,
        val description: String,
        val supportsVision: Boolean
    ) {
        SMALL(
            label = "Qwen 3.5 0.8B",
            dirName = "qwen35-0.8b-mnn",
            filename = "qwen35-0.8b-int4-mnn.zip",
            modelUrl = "https://huggingface.co/prismindanalytics/qwen3.5-0.8b-int4-mnn/resolve/main/qwen35-0.8b-int4-mnn.zip",
            sha256 = "5780c9f0912679ae8f271dae7cc15690bf803dfefd9e94d14bfd105100bc7b44",
            sizeMb = 390,
            description = "Fast text-only inference; uses llama.cpp below 4 GB RAM and MNN at 4 GB or higher",
            supportsVision = false
        ),
        LARGE(
            label = "Qwen 3.5 2B",
            dirName = "qwen35-2b-mnn",
            filename = "qwen35-2b-int4-mnn-vision.zip",
            modelUrl = "https://huggingface.co/prismindanalytics/qwen3.5-0.8b-int4-mnn/resolve/main/qwen35-2b-int4-mnn-vision.zip",
            sha256 = "344f169dcb38b3fc6f2b67e8ed9ffdbb9906edf85d87fb1228aae195348de29a",
            sizeMb = 1205,
            description = "Higher-accuracy on-device model via MNN, needs 4+ GB RAM",
            supportsVision = true
        ),
        GEMMA_E2B(
            label = "Gemma 4 E2B",
            dirName = "gemma4-e2b-mediapipe",
            // `-web.task` is the MediaPipe-compatible bundle inside the LiteRT-LM
            // repo. The repo also ships a native `.litertlm` (LiteRT-LM runtime)
            // and Qualcomm-specific NPU variants we don't use.
            filename = "gemma-4-E2B-it-web.task",
            // Source: https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm
            // Base model card: https://huggingface.co/google/gemma-4-E2B-it
            modelUrl = "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it-web.task",
            // SHA-256 verified against HuggingFace LFS metadata (X-Linked-ETag).
            sha256 = "2cbff161177a4d51c9d04360016185976f504517ba5758cd10c1564e5421c5a5",
            sizeMb = 1910,  // 2,003,697,664 bytes
            description = "Gemma 4 E2B via MediaPipe LLM Inference (Google's native runtime, GPU/NNAPI delegated). Vision-capable. Recommended for 4+ GB RAM phones.",
            supportsVision = true
        ),
        GEMMA_E4B(
            label = "Gemma 4 E4B",
            dirName = "gemma4-e4b-mediapipe",
            filename = "gemma-4-E4B-it-web.task",
            modelUrl = "https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/resolve/main/gemma-4-E4B-it-web.task",
            sha256 = "f3bd72fc27627be2a2cc6722199a333599590ed0962ee7047b516a506b7bf086",
            sizeMb = 2827,  // 2,964,324,352 bytes
            description = "Gemma 4 E4B via MediaPipe LLM Inference. Best-on-device accuracy in the Gemma 4 family. Vision-capable. Recommended for 6+ GB RAM phones.",
            supportsVision = true
        );

        /** Non-technical display name for simplified UI (e.g., setup wizard).
         *  Gemma 4 is now the primary recommendation on phones with ≥4 GB RAM
         *  (vision-capable + best on the public clinical-edge-bench). Qwen tiers
         *  remain selectable as alternatives. */
        val friendlyName: String get() = when (this) {
            SMALL -> "Compact (Qwen 0.8B, low-RAM)"
            LARGE -> "Qwen 2B (text-only)"
            GEMMA_E2B -> "Gemma 4 E2B (recommended, 4 GB+)"
            GEMMA_E4B -> "Gemma 4 E4B (recommended, 6 GB+)"
        }

        /** Model family — drives which ExtractionStrategy and which native engine to use. */
        val family: ModelFamily get() = when (this) {
            SMALL, LARGE -> ModelFamily.QWEN
            GEMMA_E2B, GEMMA_E4B -> ModelFamily.GEMMA
        }
    }

    /**
     * On-device LLM family. Each family uses its vendor's native engine:
     *   - QWEN  → MNN (Alibaba's runtime, optimal for Qwen 3.5)
     *   - GEMMA → MediaPipe LLM Inference (Google's runtime, optimal for Gemma 4)
     */
    enum class ModelFamily { QWEN, GEMMA }

    fun recommendedTier(): ModelTier = recommendedTierForRam(deviceRamGb())

    // Cache total RAM — never changes at runtime. Avoids repeated MemoryInfo allocations
    // which are called ~10 times per inference cycle from autoUnloadDelay, timeout, headroom checks.
    private val cachedDeviceRamGb: Double by lazy {
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memInfo = ActivityManager.MemoryInfo()
        am.getMemoryInfo(memInfo)
        memInfo.totalMem / (1024.0 * 1024.0 * 1024.0)
    }

    fun deviceRamGb(): Double = cachedDeviceRamGb

    fun deviceName(): String = "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}"

    // ── Download helper ──

    private suspend fun downloadFile(
        url: String,
        targetFile: File,
        resumeFromByte: Long
    ): DownloadResult {
        val requestBuilder = Request.Builder().url(url)
        if (resumeFromByte > 0) {
            requestBuilder.addHeader("Range", "bytes=$resumeFromByte-")
        }

        val call = client.newCall(requestBuilder.build())
        activeCall = call

        val response = suspendCancellableCoroutine { cont ->
            cont.invokeOnCancellation { call.cancel() }
            try {
                cont.resumeWith(Result.success(call.execute()))
            } catch (e: Exception) {
                cont.resumeWith(Result.failure(e))
            }
        }

        response.use { resp ->
            if (!resp.isSuccessful && resp.code != 206) {
                throw Exception("HTTP ${resp.code}: ${resp.message}")
            }

            val body = resp.body ?: throw Exception("Empty response body")
            val contentLength = body.contentLength()

            val isResume = resumeFromByte > 0 && resp.code == 206
            val totalBytes = if (contentLength > 0) {
                if (isResume) contentLength + resumeFromByte else contentLength
            } else -1L

            val outputStream = if (isResume) {
                FileOutputStream(targetFile, true)
            } else {
                FileOutputStream(targetFile)
            }

            var bytesWritten = if (isResume) resumeFromByte else 0L
            val buffer = ByteArray(8192)
            var lastUpdateTime = 0L

            body.byteStream().use { input ->
                outputStream.use { output ->
                    while (true) {
                        yield()
                        val read = input.read(buffer)
                        if (read == -1) break
                        output.write(buffer, 0, read)
                        bytesWritten += read

                        // Throttle UI updates to max once per 500ms to prevent recomposition thrashing
                        val now = System.currentTimeMillis()
                        if (now - lastUpdateTime >= 500) {
                            _state.value = ModelState.Downloading(bytesWritten, totalBytes)
                            lastUpdateTime = now
                        }
                    }
                }
            }
            // Always emit final progress after loop completes
            _state.value = ModelState.Downloading(bytesWritten, totalBytes)
            activeCall = null
            return DownloadResult(usedResume = isResume)
        }
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(8192)
            var read: Int
            while (input.read(buffer).also { read = it } != -1) {
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    fun hasPinnedChecksum(tier: ModelTier = activeTier()): Boolean =
        normalizeSha256(expectedSha256For(tier, deviceRamGb())) != null

    private fun requirePinnedSha256(tier: ModelTier): String =
        normalizeSha256(expectedSha256For(tier, deviceRamGb()))
            ?: throw IllegalStateException("Trusted SHA-256 is not configured for ${tier.label}")

    /**
     * Pinned SHA-256 for the active tier, or null when the tier ships without a
     * pinned digest (e.g. the Gemma `.task` bundles from `litert-community` on
     * HuggingFace, where we don't have a published SHA yet). Callers treat null
     * as "trust on first download from the official source" and log the actual
     * SHA so it can be promoted into the tier definition later.
     */
    private fun pinnedSha256OrNull(tier: ModelTier): String? =
        normalizeSha256(expectedSha256For(tier, deviceRamGb()))

    private fun clearVerifiedModelCache() {
        verifiedModelFingerprint = null
    }

    private fun normalizeSha256(raw: String): String? {
        val cleaned = raw.trim().lowercase()
        return if (Regex("^[a-f0-9]{64}$").matches(cleaned)) cleaned else null
    }

    private fun toUserFacingDownloadError(e: Exception): String {
        val raw = e.message?.trim().orEmpty()
        val lowered = raw.lowercase()
        return when {
            lowered.contains("software caused connection abort") ||
                lowered.contains("connection reset") ||
                lowered.contains("stream was reset") ||
            lowered.contains("unexpected end of stream") ||
                lowered.contains("timeout") -> {
                    "Connection dropped during download (often when phone sleeps). Keep screen on and tap Retry to resume."
                }
            raw.isNotBlank() -> raw
            else -> "Download failed"
        }
    }

    companion object {
        private data class BackendArtifact(
            val backend: InferenceBackend,
            val installDirName: String,
            val filename: String,
            val downloadUrl: String,
            val sha256: String,
            val sizeMb: Int,
            val extractedArchive: Boolean
        )

        private const val TAG = "LlmModelManager"
        // Enabled for Gemma 4 via MediaPipe LLM Inference (LlmInferenceSession.addImage).
        // Qwen vision is still stubbed in LlamaBridge.generateVision; on Qwen tiers
        // VisionExtractor returns null and the UI falls back to text-only flows.
        const val ON_DEVICE_VISION_ENABLED = true
        private const val ULTRA_LOW_RAM_DEVICE_GB = 3.0
        private const val LOW_RAM_DEVICE_GB = 3.5
        private const val MNN_BACKEND_RAM_THRESHOLD_GB = 4.0
        private const val CONSTRAINED_DEVICE_GB = 6.0
        private const val ULTRA_LOW_RAM_MAX_TRANSCRIPT_CHARS = 2500
        private const val LOW_RAM_MAX_TRANSCRIPT_CHARS = 4000
        private const val DEFAULT_MAX_TRANSCRIPT_CHARS = 6400
        private const val LARGE_MODEL_MAX_TRANSCRIPT_CHARS = 8000
        private const val ULTRA_LOW_RAM_MAX_OUTPUT_TOKENS = 768  // smaller decode budget keeps 3GB devices responsive and leaves more prompt headroom
        private const val SMALL_MODEL_MAX_OUTPUT_TOKENS = 2048
        private const val LARGE_MODEL_MAX_OUTPUT_TOKENS = 3072
        private const val ULTRA_LOW_RAM_EXTRACTION_OUTPUT_TOKENS = 512
        private const val LOW_RAM_EXTRACTION_OUTPUT_TOKENS = 640
        // Budget calibrated for Gemma 4 E4B on CPU (~7-8 tok/s on a Fold 7
        // post-thermal-throttle). 384 note tokens × 8 = 48s of decode, plus
        // ~12s prefill on a 1100-char system + dictation prompt, comfortably
        // fits the 150s inference timeout. Real clinical notes from short
        // dictations land in the 200-300 token range, so 384 is generous
        // without burning the timeout budget.
        private const val SMALL_MODEL_EXTRACTION_OUTPUT_TOKENS = 640
        private const val LARGE_MODEL_EXTRACTION_OUTPUT_TOKENS = 1024
        private const val SMALL_MODEL_NOTE_OUTPUT_TOKENS = 384
        private const val LARGE_MODEL_NOTE_OUTPUT_TOKENS = 640
        private const val ULTRA_LOW_RAM_MAX_SNIPPET_OUTPUT_TOKENS = 256
        private const val SMALL_MODEL_MAX_SNIPPET_OUTPUT_TOKENS = 320
        private const val LARGE_MODEL_MAX_SNIPPET_OUTPUT_TOKENS = 448
        // Keep model warm longer — each reload costs 5-15s on eMMC. The memory pressure
        // handler (onTrimMemory) still unloads if the system truly needs RAM.
        private const val ULTRA_LOW_RAM_AUTO_UNLOAD_DELAY_MS = 15_000L
        private const val LOW_RAM_AUTO_UNLOAD_DELAY_MS = 15_000L
        private const val MID_RAM_AUTO_UNLOAD_DELAY_MS = 15_000L
        private const val DEFAULT_AUTO_UNLOAD_DELAY_MS = 30_000L
        // With mmap disabled on ≤3GB, full model load from eMMC takes longer.
        private const val ULTRA_LOW_RAM_MODEL_LOAD_TIMEOUT_MS = 45_000L
        private const val LOW_RAM_MODEL_LOAD_TIMEOUT_MS = 45_000L
        private const val DEFAULT_MODEL_LOAD_TIMEOUT_MS = 45_000L
        // At ~2-3 tok/s on Cortex-A53, 512 tokens takes ~170-256s. Allow enough time
        // to complete rather than timing out mid-generation on slow eMMC phones.
        // 90s was borderline for Gemma 4 E4B CPU inference at 640 tokens
        // and would time out under thermal throttling. With the tighter
        // note-token budget (384) the typical run completes in 50-70s, so
        // 150s gives ~2× margin without leaving the user staring at a
        // hung-looking screen for too long.
        private const val ULTRA_LOW_RAM_INFERENCE_TIMEOUT_MS = 180_000L
        private const val LOW_RAM_INFERENCE_TIMEOUT_MS = 150_000L
        private const val DEFAULT_INFERENCE_TIMEOUT_MS = 150_000L
        private const val CANCEL_WAIT_TIMEOUT_MS = 5_000L
        private const val DEFERRED_CANCEL_CLEANUP_TIMEOUT_MS = 15_000L

        fun backendForRam(ramGb: Double): InferenceBackend =
            if (ramGb >= MNN_BACKEND_RAM_THRESHOLD_GB) {
                InferenceBackend.MNN
            } else {
                InferenceBackend.LLAMA_CPP
            }

        fun backendDisplayName(backend: InferenceBackend): String = when (backend) {
            InferenceBackend.MNN -> "MNN-LLM"
            InferenceBackend.LLAMA_CPP -> "llama.cpp"
            InferenceBackend.MEDIAPIPE -> "MediaPipe LLM"
        }

        private fun artifactFor(tier: ModelTier, ramGb: Double): BackendArtifact = when (tier) {
            // backendForRam() only returns MNN or LLAMA_CPP for Qwen tiers — the
            // MEDIAPIPE branch is unreachable here (Gemma routes through its own
            // ModelTier branch below). Defensive `else` keeps the `when`
            // exhaustive for Kotlin 2.x without obscuring the SMALL-tier branches.
            ModelTier.SMALL -> when (backendForRam(ramGb)) {
                InferenceBackend.MNN -> BackendArtifact(
                    backend = InferenceBackend.MNN,
                    installDirName = "qwen35-0.8b-mnn",
                    filename = "qwen35-0.8b-int4-mnn.zip",
                    downloadUrl = "https://huggingface.co/prismindanalytics/qwen3.5-0.8b-int4-mnn/resolve/main/qwen35-0.8b-int4-mnn.zip",
                    sha256 = "5780c9f0912679ae8f271dae7cc15690bf803dfefd9e94d14bfd105100bc7b44",
                    sizeMb = 390,
                    extractedArchive = true
                )
                InferenceBackend.LLAMA_CPP -> BackendArtifact(
                    backend = InferenceBackend.LLAMA_CPP,
                    installDirName = "qwen35-0.8b-gguf",
                    filename = "Qwen3.5-0.8B-Q4_K_M.gguf",
                    downloadUrl = "https://huggingface.co/prismindanalytics/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_K_M.gguf",
                    sha256 = "eae8384b021563263ff2411abd10d5de250af63bbe1341925845cd482fefe17a",
                    sizeMb = 505,
                    extractedArchive = false
                )
                InferenceBackend.MEDIAPIPE -> error(
                    "Unreachable: backendForRam() never returns MEDIAPIPE for Qwen SMALL tier"
                )
            }
            ModelTier.LARGE -> BackendArtifact(
                backend = InferenceBackend.MNN,
                installDirName = "qwen35-2b-mnn",
                filename = "qwen35-2b-int4-mnn-vision.zip",
                downloadUrl = "https://huggingface.co/prismindanalytics/qwen3.5-0.8b-int4-mnn/resolve/main/qwen35-2b-int4-mnn-vision.zip",
                sha256 = "344f169dcb38b3fc6f2b67e8ed9ffdbb9906edf85d87fb1228aae195348de29a",
                sizeMb = 1205,
                extractedArchive = true
            )
            // .litertlm (Android-native) instead of -web.task (web/WASM). The
            // litert-community repo publishes both; only the .litertlm bundle is
            // loadable by litertlm-android. The .task suffix is the web variant
            // and the native runtime cannot open it ("Unable to open zip archive").
            // Empty SHA-256 → trust-on-first-download; computed digest is logged
            // after install and can be pinned later.
            ModelTier.GEMMA_E2B -> BackendArtifact(
                backend = InferenceBackend.MEDIAPIPE,
                installDirName = "gemma4-e2b-litertlm",
                filename = "gemma-4-E2B-it.litertlm",
                downloadUrl = "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it.litertlm",
                sha256 = "",
                sizeMb = 2468,  // 2,588,147,712 B per HF content-length
                extractedArchive = false
            )
            ModelTier.GEMMA_E4B -> BackendArtifact(
                backend = InferenceBackend.MEDIAPIPE,
                installDirName = "gemma4-e4b-litertlm",
                filename = "gemma-4-E4B-it.litertlm",
                downloadUrl = "https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/resolve/main/gemma-4-E4B-it.litertlm",
                sha256 = "",
                sizeMb = 3490,  // 3,659,530,240 B per HF content-length
                extractedArchive = false
            )
        }

        fun modelSizeMbFor(tier: ModelTier, ramGb: Double): Int = artifactFor(tier, ramGb).sizeMb

        fun expectedSha256For(tier: ModelTier, ramGb: Double): String = artifactFor(tier, ramGb).sha256

        fun modelUrlFor(tier: ModelTier, ramGb: Double): String = artifactFor(tier, ramGb).downloadUrl

        fun modelFilenameFor(tier: ModelTier, ramGb: Double): String = artifactFor(tier, ramGb).filename

        fun installRootFor(baseDir: File, tier: ModelTier, ramGb: Double): File =
            File(baseDir, artifactFor(tier, ramGb).installDirName)

        fun modelFileFor(baseDir: File, tier: ModelTier, ramGb: Double): File {
            val artifact = artifactFor(tier, ramGb)
            val root = installRootFor(baseDir, tier, ramGb)
            return if (artifact.extractedArchive) root else File(root, artifact.filename)
        }

        fun isArchiveInstallFor(tier: ModelTier, ramGb: Double): Boolean =
            artifactFor(tier, ramGb).extractedArchive

        fun isModelInstalled(baseDir: File, tier: ModelTier, ramGb: Double): Boolean {
            val artifact = artifactFor(tier, ramGb)
            return if (artifact.extractedArchive) {
                hasRequiredModelFiles(installRootFor(baseDir, tier, ramGb), tier)
            } else {
                modelFileFor(baseDir, tier, ramGb).let { it.exists() && it.length() > 0L }
            }
        }

        fun supportedModelTiers(): List<ModelTier> = ModelTier.entries
        // All four tiers are selectable. Gemma 4 (E2B / E4B) is the recommended
        // default on capable hardware (vision-capable, best on clinical-edge-bench).
        // Qwen 0.8B remains the only working option <4 GB RAM, and Qwen 2B stays
        // available as a text-only alternative for users who prefer MNN. Vision
        // calls fall back gracefully when the active tier doesn't support them
        // (LlamaBridge.generateVision returns null on Qwen).

        fun normalizeSupportedTier(tier: ModelTier?): ModelTier? =
            tier?.takeIf { it in supportedModelTiers() }

        fun recommendedTierForRam(ramGb: Double): ModelTier {
            // Gemma 4 (via MediaPipe) is the on-device default on phones with
            // enough RAM. It supports vision, and on the public clinical-edge-bench
            // it out-performs Qwen 3.5 across pharmacology MCQA, calculator
            // vignettes, and SOAP generation. See benchmark.chartlite.health.
            //
            // Below 4GB stays on Qwen 0.8B (Gemma E2B is too heavy at <4GB; our
            // llama.cpp + Qwen path is the only working ultra-low-RAM option
            // today). On these devices vision returns null and the UI falls
            // back to text-only flows gracefully.
            return when {
                ramGb >= 6.0 -> ModelTier.GEMMA_E4B
                ramGb >= 4.0 -> ModelTier.GEMMA_E2B
                else -> ModelTier.SMALL
            }
        }

        fun requiredModelFiles(tier: ModelTier): List<String> = buildList {
            add("llm_config.json")
            add("config.json")
            add("llm.mnn")
            add("llm.mnn.weight")
            add("tokenizer.txt")
            if (tier.supportsVision) {
                add("visual.mnn")
            }
        }

        fun hasRequiredModelFiles(dir: File, tier: ModelTier): Boolean {
            if (!dir.exists()) return false
            val requiredFilesPresent = requiredModelFiles(tier).all { name ->
                val file = File(dir, name)
                file.exists() && file.length() > 0L
            }
            if (!requiredFilesPresent) return false
            return tier.supportsVision || !File(dir, "visual.mnn").exists()
        }
    }
}
