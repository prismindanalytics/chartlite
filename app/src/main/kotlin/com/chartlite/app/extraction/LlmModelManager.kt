package com.chartlite.app.extraction

import android.app.ActivityManager
import android.content.ComponentCallbacks2
import android.content.Context
import android.content.res.Configuration
import android.net.wifi.WifiManager
import android.os.PowerManager
import android.util.Log
import com.chartlite.llm.LlamaBridge
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
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
import java.util.zip.ZipInputStream

/**
 * Manages downloading and loading of MNN-LLM models for on-device inference.
 * MNN-LLM provides 2-8x faster inference than llama.cpp on ARM Android devices.
 *
 * Hardware-aware tier selection:
 * - <4GB RAM: Qwen 3.5 0.8B INT4 (~390MB) — fits Galaxy A03/A04
 * - >=4GB RAM: Qwen 3.5 2B INT4 (~1.0GB) — better accuracy
 *
 * MNN models are stored as directories (llm.mnn, llm.mnn.weight, llm_config.json,
 * tokenizer.txt, config.json) downloaded as zip archives and extracted on device.
 *
 * Models stored in context.noBackupFilesDir/llm_models/ (excluded from auto-backup).
 */
class LlmModelManager(private val context: Context) : ComponentCallbacks2 {
    data class GenerationConfig(
        val temperature: Float = 0.1f,
        val topP: Float = 0.95f,
        val topK: Int = 40,
        val repeatPenalty: Float = 1.0f
    )

    private data class DownloadResult(
        val usedResume: Boolean
    )

    sealed class ModelState {
        data object NotDownloaded : ModelState()
        data class Downloading(val bytesDownloaded: Long, val totalBytes: Long) : ModelState()
        data object Verifying : ModelState()
        data object Ready : ModelState()
        data class Error(val message: String) : ModelState()
        data object Paused : ModelState()
    }

    private val _state = MutableStateFlow<ModelState>(ModelState.NotDownloaded)
    val state: StateFlow<ModelState> = _state

    private val modelsDir = File(context.noBackupFilesDir, "llm_models").apply { mkdirs() }
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    private var downloadJob: Job? = null
    private var activeCall: Call? = null
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
    /** Keep model loaded for 30s after last inference to avoid repeated load/unload cycles
     *  during multi-snippet encounter sessions. onTrimMemory still overrides if system needs RAM. */
    private val autoUnloadDelayMs = 30_000L

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
    fun activeTier(): ModelTier = overrideTier ?: recommendedTier()

    /** Directory containing MNN model files for the active tier. */
    val modelDir: File get() = File(modelsDir, activeTier().dirName)

    /** Legacy accessor for callers that expect a single file path (returns model directory). */
    val modelFile: File get() = modelDir

    fun isModelDownloaded(): Boolean {
        val dir = modelDir
        return dir.exists() && File(dir, "llm_config.json").exists()
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
        val trusted = hasPinnedChecksum()
        if (!downloaded || !native || !trusted) {
            Log.d(
                TAG,
                "isReady=false: downloaded=$downloaded, native=$native, trusted=$trusted, file=${modelFile.absolutePath}"
            )
        }
        return downloaded && native && trusted
    }

    fun modelSizeBytes(): Long {
        val dir = modelDir
        if (!dir.exists()) return 0
        return dir.walkTopDown().filter { it.isFile }.sumOf { it.length() }
    }

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
            ?: (activeTier().sizeMb.toLong() * 1024L * 1024L)
        val ramGb = deviceRamGb()
        val isUltraLowRam = ramGb <= ULTRA_LOW_RAM_DEVICE_GB
        val isLowRamDevice = ramGb <= LOW_RAM_DEVICE_GB
        val baseHeadroom = (modelBytes / 4).coerceIn(128L * 1024 * 1024, 384L * 1024 * 1024)
        // Ultra-low-RAM (≤3GB): aggressive but safe — onTrimMemory auto-unloads if pressured.
        // Context is 2048 (not 4096) so KV cache is ~50-80MB, batch=64 is tiny.
        val tierHeadroom = when (activeTier()) {
            ModelTier.SMALL -> when {
                isUltraLowRam -> 384L * 1024 * 1024   // 384MB — tight but workable
                isLowRamDevice -> 512L * 1024 * 1024   // 512MB — moderate
                else -> 512L * 1024 * 1024
            }
            ModelTier.LARGE -> 1024L * 1024 * 1024
        }
        val burst = if (!forInference) {
            0L
        } else when (activeTier()) {
            ModelTier.SMALL -> when {
                isUltraLowRam -> 128L * 1024 * 1024    // 128MB — ctx=2048, batch=64
                isLowRamDevice -> 256L * 1024 * 1024
                else -> 256L * 1024 * 1024
            }
            ModelTier.LARGE -> 512L * 1024 * 1024
        }
        val headroom = maxOf(baseHeadroom, tierHeadroom)
        val required = modelBytes / 2 + headroom + burst
        return MemoryBudget(
            availableRamBytes = memInfo.availMem,
            requiredRamBytes = required,
            headroomBytes = headroom,
            burstBytes = burst
        )
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
            val burst = when (activeTier()) {
                ModelTier.SMALL -> when {
                    deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> 128L * 1024 * 1024
                    else -> 256L * 1024 * 1024
                }
                ModelTier.LARGE -> 512L * 1024 * 1024
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

    fun recommendedSnippetOutputTokens(): Int = when {
        activeTier() == ModelTier.LARGE -> LARGE_MODEL_MAX_SNIPPET_OUTPUT_TOKENS
        deviceRamGb() <= ULTRA_LOW_RAM_DEVICE_GB -> ULTRA_LOW_RAM_MAX_SNIPPET_OUTPUT_TOKENS
        else -> SMALL_MODEL_MAX_SNIPPET_OUTPUT_TOKENS
    }

    // ── Model loading ──

    /**
     * Load the model into memory for inference.
     * Uses [loadMutex] to prevent concurrent double-loading and to
     * coordinate with [unloadModel] / [onTrimMemory].
     *
     * MNN-LLM JNI bridge loading:
     * - Takes a file path string (no ContentResolver/FileProvider/FD dance)
     * - Returns Boolean on failure (no SIGSEGV)
     * - Handles mmap automatically
     * - Supports updateGenerateParams for temperature/maxTokens control
     */
    suspend fun loadModel() {
        if (modelLoaded) return
        if (!isModelDownloaded()) throw IllegalStateException("Model not downloaded")

        loadMutex.withLock {
            // Re-check after acquiring lock
            if (modelLoaded) return

            withContext(Dispatchers.IO) {
                val dir = modelDir
                val budget = currentMemoryBudget(forInference = true)
                if (budget.availableRamBytes < budget.requiredRamBytes) {
                    Log.w(TAG, "Insufficient system memory to load LLM: " +
                        "${budget.availableRamBytes / 1024 / 1024}MB available, need " +
                        "${budget.requiredRamBytes / 1024 / 1024}MB " +
                        "(model mmap working set + ${budget.headroomBytes / 1024 / 1024}MB headroom + " +
                        "${budget.burstBytes / 1024 / 1024}MB inference burst)")
                    throw IllegalStateException("Not enough free memory for on-device note processing")
                }

                // Validate MNN model directory has required files
                val configFile = File(dir, "llm_config.json")
                if (!configFile.exists()) {
                    Log.e(TAG, "Model directory missing llm_config.json: ${dir.absolutePath}")
                    throw IllegalStateException("Invalid MNN model — re-download may be needed")
                }

                Log.d(TAG, "Loading model via MNN-LLM: ${dir.name}")

                // MNN: pass directory path containing llm_config.json, llm.mnn, llm.mnn.weight, tokenizer.txt
                val success = LlamaBridge.initGenerateModel(dir.absolutePath)
                if (!success) {
                    throw IllegalStateException("MNN model load failed for ${dir.name}")
                }

                // Keep the on-device generation budget conservative so structured
                // extraction completes promptly instead of drifting into multi-minute runs.
                applyGenerationParams(recommendedOutputTokens())

                modelLoaded = true
                Log.d(TAG, "Model loaded: ${dir.name}")
            }
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
                } catch (e: Exception) {
                    Log.w(TAG, "Error during LlamaBridge.shutdown()", e)
                }
                modelLoaded = false
            }
        } finally {
            loadMutex.unlock()
        }
    }

    fun cancelInference() {
        if (!inferring) return
        Log.w(TAG, "Cancelling in-flight on-device inference")
        LlamaBridge.cancelGeneration()
    }

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
     * MNN applies the model's native chat template with proper special token IDs.
     * This avoids the tokenization issue where manually-written <|im_start|> tags
     * are treated as regular text instead of special tokens.
     */
    suspend fun runChatInference(
        systemPrompt: String,
        userMessage: String,
        maxTokens: Int = recommendedOutputTokens(),
        config: GenerationConfig = GenerationConfig()
    ): String? = executeInference("generateChat", maxTokens, config) {
        LlamaBridge.generateChat(systemPrompt, userMessage)
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
    ): String? = executeInference("generateVision", maxTokens, config) {
        LlamaBridge.generateVision(systemPrompt, userMessage, imagePath)
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
        return try {
            // Set inferring BEFORE loadModel() to prevent onTrimMemory from
            // unloading mid-load on 3GB devices under memory pressure.
            inferring = true
            if (!modelLoaded) loadModel()

            val result = CompletableDeferred<String?>()
            val generationJob = scope.launch {
                try {
                    inferenceMutex.withLock {
                        applyGenerationParams(maxTokens, config)
                        Log.d(TAG, "Starting $label inference")

                        val text = generate()

                        if (text.isNullOrBlank()) {
                            Log.w(TAG, "LlamaBridge.$label returned empty")
                            result.complete(null)
                        } else {
                            Log.d(TAG, "$label inference complete: ${text.length} chars")
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
                    autoUnloadJob = scope.launch {
                        delay(autoUnloadDelayMs)
                        if (!inferring) {
                            Log.d(TAG, "Auto-unloading model after ${autoUnloadDelayMs / 1000}s idle")
                            unloadModel()
                        }
                    }
                }
            }

            try {
                result.await()
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
                    Log.e(TAG, "Timed out waiting for cancelled $label inference to stop")
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
        if (!inferring) unloadModel()
    }

    // ── Download ──

    fun startDownload() {
        if (downloadJob?.isActive == true) return

        val tier = activeTier()
        downloadJob = scope.launch {
            // Note: wake locks removed — ModelDownloadService foreground service
            // keeps the process alive during screen-off / Doze mode.
            try {
                val pinnedSha = requirePinnedSha256(tier)
                val tmpFile = File(modelsDir, "${tier.filename}.tmp")
                var resumeFromByte = if (tmpFile.exists()) tmpFile.length() else 0L
                var verified = false

                for (attempt in 1..2) {
                    _state.value = ModelState.Downloading(resumeFromByte, -1)
                    val downloadResult = downloadFile(tier.modelUrl, tmpFile, resumeFromByte)

                    _state.value = ModelState.Verifying
                    val actualSha = sha256(tmpFile)
                    if (actualSha.equals(pinnedSha, ignoreCase = true)) {
                        Log.i(TAG, "SHA-256 verified for ${tier.filename} via pinned digest")
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

                // Extract zip to model directory
                val destDir = modelDir
                destDir.mkdirs()
                extractZip(tmpFile, destDir)
                tmpFile.delete()
                clearVerifiedModelCache()
                _state.value = ModelState.Ready

            } catch (e: CancellationException) {
                _state.value = ModelState.Paused
            } catch (e: IllegalStateException) {
                _state.value = ModelState.Error(e.message ?: "Download failed")
            } catch (e: Exception) {
                _state.value = ModelState.Error(toUserFacingDownloadError(e))
            }
        }
    }

    fun cancelDownload() {
        downloadJob?.cancel()
        activeCall?.cancel()
        _state.value = ModelState.Paused
    }

    /**
     * Import a local MNN model zip (USB/SD sideload).
     * Extracts into the active tier directory and marks the model ready.
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
            _state.value = ModelState.Verifying

            val configuredSha = normalizeSha256(expectedSha256)
            if (configuredSha == null) {
                _state.value = ModelState.Error(
                    "Trusted model SHA-256 is not configured for this tier."
                )
                return false
            }
            val actualSha = sha256(sourceFile)
            if (!actualSha.equals(configuredSha, ignoreCase = true)) {
                _state.value = ModelState.Error(
                    "SHA-256 mismatch. Expected: ${configuredSha.take(12)}... " +
                        "Got: ${actualSha.take(12)}..."
                )
                return false
            }

            downloadJob?.cancel()
            activeCall?.cancel()
            unloadModel()

            val destDir = modelDir
            destDir.mkdirs()
            extractZip(sourceFile, destDir)
            clearVerifiedModelCache()
            _state.value = ModelState.Ready
            true
        } catch (e: Exception) {
            _state.value = ModelState.Error("Model import failed: ${e.message}")
            false
        }
    }

    /** Extract a zip archive to the given directory. */
    private fun extractZip(zipFile: File, destDir: File) {
        ZipInputStream(zipFile.inputStream().buffered()).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                if (!entry.isDirectory) {
                    val outFile = File(destDir, entry.name)
                    outFile.parentFile?.mkdirs()
                    FileOutputStream(outFile).use { fos ->
                        zis.copyTo(fos)
                    }
                }
                zis.closeEntry()
                entry = zis.nextEntry
            }
        }
    }

    /** Cancel all coroutines and unload the model. Call on app shutdown. */
    fun close() {
        cancelDownload()
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
        _state.value = when {
            !hasPinnedChecksum() -> ModelState.Error("Trusted SHA-256 is not configured for ${activeTier().label}")
            isModelDownloaded() -> ModelState.Ready
            modelsDir.listFiles()?.any { it.name.endsWith(".tmp") } == true -> ModelState.Paused
            else -> {
                // Auto-detect sideloaded model on external storage / microSD
                val sideloaded = scanExternalStorageForModel()
                if (sideloaded != null) {
                    Log.i(TAG, "Found sideloaded LLM model: ${sideloaded.absolutePath}")
                    scope.launch(Dispatchers.IO) {
                        importModelFile(sideloaded, activeTier().sha256)
                    }
                    ModelState.Verifying
                } else {
                    ModelState.NotDownloaded
                }
            }
        }
    }

    /**
     * Scan external storage directories (microSD, USB OTG) for a sideloaded MNN model zip.
     *
     * For LMIC zero-connectivity deployments, models can be pre-loaded onto a microSD card.
     * Place the zip at: `<sdcard>/Android/data/com.chartlite.app/files/chartlite/<filename>.zip`
     *
     * Uses scoped storage ([Context.getExternalFilesDirs]) — no extra permissions needed.
     */
    fun scanExternalStorageForModel(): File? {
        val allDirs = context.getExternalFilesDirs(null) ?: return null
        // Skip index 0 (primary internal storage) — only check SD card / USB
        val externalDirs = allDirs.filterNotNull().drop(1)
        if (externalDirs.isEmpty()) return null

        val tier = activeTier()
        for (dir in externalDirs) {
            val modelFile = File(File(dir, "chartlite"), tier.filename)
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
        val description: String
    ) {
        SMALL(
            label = "Qwen 3.5 0.8B",
            dirName = "qwen35-0.8b-mnn",
            filename = "qwen35-0.8b-int4-mnn-vision.zip",
            modelUrl = "https://huggingface.co/prismindanalytics/qwen3.5-0.8b-int4-mnn/resolve/main/qwen35-0.8b-int4-mnn-vision.zip",
            sha256 = "2667046bc560c5fc3e38b28d2b91a14d6b659b9d5e02db76adb5ec02fe18fe8e",
            sizeMb = 452,
            description = "Fast inference + vision via MNN, fits devices with 2+ GB RAM"
        ),
        LARGE(
            label = "Qwen 3.5 2B",
            dirName = "qwen35-2b-mnn",
            filename = "qwen35-2b-int4-mnn-vision.zip",
            modelUrl = "https://huggingface.co/prismindanalytics/qwen3.5-0.8b-int4-mnn/resolve/main/qwen35-2b-int4-mnn-vision.zip",
            sha256 = "344f169dcb38b3fc6f2b67e8ed9ffdbb9906edf85d87fb1228aae195348de29a",
            sizeMb = 1205,
            description = "Higher accuracy + vision via MNN, needs 4+ GB RAM"
        );

        /** Non-technical display name for simplified UI (e.g., setup wizard). */
        val friendlyName: String get() = when (this) {
            SMALL -> "Standard"
            LARGE -> "Enhanced"
        }
    }

    fun recommendedTier(): ModelTier {
        val ramGb = deviceRamGb()
        // 4GB threshold: LARGE model (1.5GB mmap) needs ~2.5GB free for OS+apps.
        // 3GB devices can't sustain this — they'd OOM under memory pressure.
        return if (ramGb >= 4.0) ModelTier.LARGE else ModelTier.SMALL
    }

    fun deviceRamGb(): Double {
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memInfo = ActivityManager.MemoryInfo()
        am.getMemoryInfo(memInfo)
        return memInfo.totalMem / (1024.0 * 1024.0 * 1024.0)
    }

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
        normalizeSha256(tier.sha256) != null

    private fun requirePinnedSha256(tier: ModelTier): String =
        normalizeSha256(tier.sha256)
            ?: throw IllegalStateException("Trusted SHA-256 is not configured for ${tier.label}")

    private fun clearVerifiedModelCache() {
        verifiedModelFingerprint = null
    }

    private fun verifyInstalledModelFile(file: File, tier: ModelTier) {
        val fingerprint = "${tier.name}:${file.absolutePath}:${file.length()}:${file.lastModified()}"
        if (verifiedModelFingerprint == fingerprint) return

        val expectedSha = requirePinnedSha256(tier)
        val actualSha = sha256(file)
        if (!actualSha.equals(expectedSha, ignoreCase = true)) {
            clearVerifiedModelCache()
            throw IllegalStateException(
                "Installed model failed SHA-256 verification. Delete and re-import ${tier.label}."
            )
        }
        verifiedModelFingerprint = fingerprint
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

    private fun acquireWifiLock(tag: String): WifiManager.WifiLock? {
        return try {
            val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
                ?: return null
            val lock = runCatching {
                wifiManager.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, tag)
            }.getOrElse {
                wifiManager.createWifiLock(WifiManager.WIFI_MODE_FULL, tag)
            }
            lock.setReferenceCounted(false)
            lock.acquire()
            lock
        } catch (e: Exception) {
            Log.w(TAG, "Unable to acquire Wi-Fi lock for LLM download", e)
            null
        }
    }

    companion object {
        private const val TAG = "LlmModelManager"
        private const val LLM_DOWNLOAD_WAKELOCK_TIMEOUT_MS = 8L * 60L * 60L * 1000L
        private const val ULTRA_LOW_RAM_DEVICE_GB = 3.0
        private const val LOW_RAM_DEVICE_GB = 3.5
        private const val CONSTRAINED_DEVICE_GB = 6.0
        private const val ULTRA_LOW_RAM_MAX_TRANSCRIPT_CHARS = 2500
        private const val LOW_RAM_MAX_TRANSCRIPT_CHARS = 4000
        private const val DEFAULT_MAX_TRANSCRIPT_CHARS = 6400
        private const val LARGE_MODEL_MAX_TRANSCRIPT_CHARS = 8000
        private const val ULTRA_LOW_RAM_MAX_OUTPUT_TOKENS = 1024  // n_ctx=2048, leaves ~960 for prompt + 64 headroom
        private const val SMALL_MODEL_MAX_OUTPUT_TOKENS = 2048
        private const val LARGE_MODEL_MAX_OUTPUT_TOKENS = 3072
        private const val ULTRA_LOW_RAM_MAX_SNIPPET_OUTPUT_TOKENS = 256
        private const val SMALL_MODEL_MAX_SNIPPET_OUTPUT_TOKENS = 320
        private const val LARGE_MODEL_MAX_SNIPPET_OUTPUT_TOKENS = 448
        private const val CANCEL_WAIT_TIMEOUT_MS = 5_000L
    }
}
