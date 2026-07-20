package com.chartlite.app.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import android.widget.Toast
import java.util.concurrent.CancellationException
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.filled.MedicalServices
import androidx.compose.material.icons.automirrored.filled.EventNote
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.chartlite.app.App
import com.chartlite.app.R
import com.chartlite.app.extraction.EncounterSaveCoordinator
import com.chartlite.app.extraction.EncounterMerger
import com.chartlite.app.model.ClinicStation
import com.chartlite.app.model.AlertSeverity
import com.chartlite.app.model.CDSSAlert
import com.chartlite.app.model.Diagnosis
import com.chartlite.app.model.FollowUp
import com.chartlite.app.model.Investigation
import com.chartlite.app.model.Medication
import com.chartlite.app.model.Referral
import com.chartlite.app.model.StructuredEncounter
import com.chartlite.app.model.VitalSigns
import com.chartlite.app.model.normalizedOrNull
import com.chartlite.app.cdss.CdssToolRegistry
import com.chartlite.app.extraction.VisionExtractor
import com.chartlite.app.extraction.VisionToolFlow
import com.chartlite.app.database.entity.ClinicalPhotoEntity
import com.chartlite.app.ui.components.ClinicalCameraCapture
import com.chartlite.app.ui.components.MarkdownText
import com.chartlite.app.ui.components.MultimodalResultCard
import com.chartlite.app.ui.components.RecordButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EncounterRecordScreen(
    patientId: String,
    visitId: String? = null,
    stationName: String? = null,
    onEncounterSaved: (String) -> Unit,
    onBack: () -> Unit,
    onOpenSettings: (() -> Unit)? = null,
) {
    val context = LocalContext.current
    val app = context.applicationContext as App
    val scope = rememberCoroutineScope()
    val scanAnalyzingMessage = stringResource(R.string.scan_analyzing)
    val scanChoosingToolsMessage = stringResource(R.string.scan_stage_choosing_tools)
    val scanRunningToolsMessage = stringResource(R.string.scan_stage_running_tools)
    val asr = app.asr
    val providerId = app.sessionManager.currentSession?.userId ?: app.appConfig.providerId

    val station = stationName?.let {
        try { ClinicStation.valueOf(it) } catch (_: Exception) { null }
    }
    val strictLowRamSerialization = remember {
        app.shouldUseStrictLowRamSerialization()
    }
    var isBatchProcessing by remember {
        mutableStateOf(app.appConfig.noteProcessingMode == "batch")
    }

    // ── Camera scan state ──
    var showCamera by remember { mutableStateOf(false) }
    var isScanProcessing by remember { mutableStateOf(false) }
    /** UI label flipped per-stage by VisionToolFlow.captureAndCheck. */
    var scanStageMessage by remember { mutableStateOf<String?>(null) }
    var lastScanType by remember { mutableStateOf<String?>(null) }
    var lastScanResult by remember { mutableStateOf<VisionExtractor.VisionResult?>(null) }
    var lastSafetyOutcome by remember { mutableStateOf<VisionToolFlow.SafetyOutcome?>(null) }
    var lastPhotoEntityId by remember { mutableStateOf<String?>(null) }
    var lastPhotoFilePath by remember { mutableStateOf<String?>(null) }
    var showScanResult by remember { mutableStateOf(false) }
    var showScanError by remember { mutableStateOf(false) }
    val photoDir = remember {
        java.io.File(context.filesDir, "encounter_photos/$patientId").also { it.mkdirs() }
    }

    // ── Hold-to-dictate state ──
    var isHolding by remember { mutableStateOf(false) }

    // Observe ASR state — real-time transcript and amplitude
    val isRecording by asr.isListening.collectAsState()
    val isPreparing by asr.isPreparing.collectAsState()
    val liveTranscript by asr.transcript.collectAsState()
    val amplitude by asr.amplitude.collectAsState()
    val asrModelLoaded by asr.sherpaPipeline.isLoaded.collectAsState()
    val llmPreparing by app.llmModelManager.isPreparingModel.collectAsState()

    // Recording duration timer
    var recordingStartTime by remember { mutableStateOf(0L) }
    var durationMs by remember { mutableStateOf(0L) }

    var hasPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED
        )
    }
    /** True once we've asked at least once this composition; lets us
     *  show the "Grant microphone access" fallback only after a denial,
     *  not on first entry — auto-prompt is the natural first-run experience. */
    var hasRequestedMicPermission by rememberSaveable { mutableStateOf(false) }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        hasPermission = granted
        hasRequestedMicPermission = true
    }
    // Auto-request mic permission on first entry to the encounter screen.
    // Saves an explicit "Grant Microphone Access" tap that everyone has to
    // make exactly once. The system dialog is the same — we just trigger it
    // automatically instead of behind a button.
    LaunchedEffect(Unit) {
        if (!hasPermission && !hasRequestedMicPermission) {
            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    // ── SMS permission ──
    // Held in state so the SMS send path can request it inline at the moment
    // the user actually picks "send via SMS." We deliberately do NOT
    // auto-prompt on screen entry — the original flow stacked the SMS dialog
    // ON TOP of the mic-permission dialog the moment the user opened a new
    // encounter, which felt to a first-time user like the app was demanding
    // permissions for a feature they hadn't asked about.
    var hasSmsPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.SEND_SMS)
                == PackageManager.PERMISSION_GRANTED
        )
    }
    val smsPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> hasSmsPermission = granted }

    // ── Patient history context (allergies, meds, chronic conditions from prior visits) ──
    var patientContext by remember { mutableStateOf<com.chartlite.app.model.PatientContext?>(null) }
    LaunchedEffect(patientId) {
        withContext(Dispatchers.IO) {
            val patient = app.patientRepository.getById(patientId)
            val priorEncounters = app.encounterRepository.getByPatientId(patientId)
                .map { app.encounterRepository.toStructuredEncounter(it) }
            if (priorEncounters.isNotEmpty() || patient != null) {
                patientContext = com.chartlite.app.model.PatientContextBuilder.build(patient, priorEncounters)
            }
        }
    }

    // ── Shared state ──
    var transcript by remember { mutableStateOf("") }
    var isProcessing by remember { mutableStateOf(false) }
    var isSaving by remember { mutableStateOf(false) }
    var extractedEncounter by remember { mutableStateOf<StructuredEncounter?>(null) }
    var showManualInput by rememberSaveable { mutableStateOf(false) }
    var showDiscardDialog by remember { mutableStateOf(false) }
    var extractionError by remember { mutableStateOf<String?>(null) }
    var extractionStrategyUsed by remember { mutableStateOf<String?>(null) }
    var extractionFallbacks by remember { mutableStateOf<List<String>>(emptyList()) }
    val screenScrollState = rememberScrollState()

    // ── Draft note state (note-first architecture) ──
    var draftNote by remember { mutableStateOf<String?>(null) }
    var noteStrategyUsed by rememberSaveable { mutableStateOf<String?>(null) }
    var isGeneratingNote by remember { mutableStateOf(false) }

    // Keep the screen on for any active, scope-bound work: ASR listening,
    // ASR preparing (model load), note generation, structured extraction,
    // or vision scanning. On CPU the 4B Gemma takes 30-90s per pass; any
    // screen-off / lock event tears down the Compose scope, cancelling the
    // work and (worse) cancelling the active mic recording mid-dictation.
    // Releasing the lock the moment everything is idle lets normal screen-
    // timeout behaviour resume.
    val view = LocalView.current
    val keepScreenOn = isRecording || isPreparing || isGeneratingNote || isProcessing || isScanProcessing
    DisposableEffect(keepScreenOn) {
        view.keepScreenOn = keepScreenOn
        onDispose { view.keepScreenOn = false }
    }

    // ── Snippet mode state ──
    var snippetTranscripts by remember { mutableStateOf<List<String>>(emptyList()) }
    var accumulatedEncounter by remember { mutableStateOf<StructuredEncounter?>(null) }
    var snippetCount by rememberSaveable { mutableIntStateOf(0) }
    val maxRecordingMs = if (isHolding) 2 * 60_000L
        else app.appConfig.maxRecordingMinutes * 60_000L
    val noteReviewWarmRefreshMs = 20_000L

    suspend fun processTranscriptNow(
        text: String,
        fallbackEncounter: StructuredEncounter? = null,
        fallbackStrategy: String? = null,
        emptyResultMessage: String = "Extraction returned no result. Try again."
    ) {
        val trimmed = text.trim()
        if (trimmed.isBlank()) {
            extractionError = "Nothing to process yet. Record or type the consultation first."
            return
        }

        transcript = trimmed
        isProcessing = true
        extractionError = null
        val readyForLlm = app.prepareOnDeviceNoteProcessingForLowRam { extractionError = it }
        if (!readyForLlm) {
            isProcessing = false
            return
        }

        try {
            val queueId = app.extractionQueue.enqueue(
                transcript = trimmed,
                patientId = patientId,
                providerId = providerId,
                facilityId = app.appConfig.facilityId,
                urgent = true,
                visitId = visitId,
                stationType = station?.name
            )
            val queuedResult = app.extractionQueue.getResult(queueId)
            if (queuedResult != null) {
                extractedEncounter = mergePatientHistory(queuedResult.result.encounter, patientContext)
                extractionStrategyUsed = queuedResult.result.strategyUsed
                extractionFallbacks = queuedResult.result.fallbacksAttempted
                app.extractionQueue.consumeResult(queueId)
            } else if (fallbackEncounter != null) {
                extractedEncounter = mergePatientHistory(fallbackEncounter, patientContext)
                extractionStrategyUsed = fallbackStrategy ?: "Regex (fallback)"
                extractionFallbacks = emptyList()
            } else {
                extractionError = emptyResultMessage
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (fallbackEncounter != null) {
                extractedEncounter = fallbackEncounter
                extractionStrategyUsed = fallbackStrategy ?: "Regex (fallback)"
                extractionFallbacks = emptyList()
            } else {
                extractionError = "Extraction failed: ${e.message}"
            }
        } finally {
            isProcessing = false
        }
    }

    /**
     * Generate a draft clinical note from transcript (Call 1 of note-first flow).
     * If LLM is available, shows draft note for review. If not, falls through to
     * direct extraction (old behavior).
     */
    suspend fun generateDraftNote(text: String) {
        val trimmed = text.trim()
        if (trimmed.isBlank()) {
            extractionError = "Nothing to process yet. Record or type the consultation first."
            return
        }
        transcript = trimmed
        isGeneratingNote = true
        extractionError = null
        val readyForLlm = app.prepareOnDeviceNoteProcessingForLowRam { extractionError = it }
        if (!readyForLlm) {
            isGeneratingNote = false
            return
        }

        try {
            val noteResult = app.generateDraftNoteDirect(
                transcript = trimmed,
                patientId = patientId,
                providerId = providerId,
                facilityId = app.appConfig.facilityId
            )
            if (noteResult != null) {
                draftNote = noteResult.note
                noteStrategyUsed = noteResult.strategyUsed
                val usedOnDeviceNote = noteResult.strategyUsed.contains("(on-device)")
                if (usedOnDeviceNote) {
                    app.llmModelManager.keepModelWarmFor(app.llmModelManager.recommendedReviewWarmLeaseMs())
                }
                app.prewarmExtractionPipelineForImmediateReview()
                isGeneratingNote = false
            } else {
                // No LLM available — fall back to direct extraction (old flow)
                isGeneratingNote = false
                processTranscriptNow(trimmed)
            }
        } catch (e: kotlinx.coroutines.CancellationException) {
            // Propagate cancellation (user left screen, scope cancelled) — don't swallow
            isGeneratingNote = false
            throw e
        } catch (e: Exception) {
            // Note generation failed — fall back to direct extraction
            isGeneratingNote = false
            processTranscriptNow(trimmed)
        }
    }

    /**
     * Extract structured data from the approved draft note (Call 2 of note-first flow).
     * Uses the approved note text as input to the extraction pipeline.
     */
    suspend fun extractFromApprovedNote(approvedNote: String) {
        isProcessing = true
        extractionError = null
        val readyForLlm = app.prepareOnDeviceNoteProcessingForLowRam { extractionError = it }
        if (!readyForLlm) {
            isProcessing = false
            return
        }

        try {
            val queueId = app.extractionQueue.enqueue(
                transcript = transcript,  // Original transcript for audit/reference
                patientId = patientId,
                providerId = providerId,
                facilityId = app.appConfig.facilityId,
                urgent = true,
                visitId = visitId,
                stationType = station?.name,
                approvedNote = approvedNote  // Skip re-generating note — already reviewed
            )
            val queuedResult = app.extractionQueue.getResult(queueId)
            if (queuedResult != null) {
                // Set freeTextNote to the approved draft note (the document of record)
                extractedEncounter = mergePatientHistory(
                    queuedResult.result.encounter.copy(
                        freeTextNote = approvedNote,
                        transcript = transcript  // Keep original transcript for reference
                    ),
                    patientContext
                )
                extractionStrategyUsed = queuedResult.result.strategyUsed
                extractionFallbacks = queuedResult.result.fallbacksAttempted
                app.extractionQueue.consumeResult(queueId)
            } else {
                extractionError = "Extraction returned no result. Try again."
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            extractionError = "Extraction failed: ${e.message}"
        } finally {
            isProcessing = false
        }
    }

    suspend fun finalizeSnippetRecording() {
        val result = asr.stopListeningAndAwait(releaseOnnxAfterStop = false)
        val snippetText = result.text
        durationMs = 0L

        if (snippetText.isBlank()) {
            extractionError = result.error ?: "No speech detected. Try again."
            return
        }

        try {
            val regexEncounter = app.clinicalExtractor.extract(
                transcript = snippetText,
                patientId = patientId,
                providerId = providerId,
                facilityId = app.appConfig.facilityId
            )

            accumulatedEncounter = accumulatedEncounter?.let {
                EncounterMerger.merge(it, regexEncounter)
            } ?: regexEncounter

            snippetTranscripts = snippetTranscripts + snippetText
            snippetCount++
        } catch (e: Exception) {
            extractionError = "Processing failed: ${e.message}"
        }
    }

    val queuedBatchToastMsg = stringResource(R.string.queued_batch_toast)
    val smsSendingFormat = stringResource(R.string.sms_sending_format)
    suspend fun queueTranscriptForBatch(text: String) {
        val trimmed = text.trim()
        if (trimmed.isBlank()) {
            extractionError = "Nothing to queue yet. Record or type the consultation first."
            return
        }
        asr.unloadOfflineModelIfIdle()
        app.extractionQueue.enqueue(
            transcript = trimmed,
            patientId = patientId,
            providerId = providerId,
            facilityId = app.appConfig.facilityId,
            urgent = false,
            visitId = visitId,
            stationType = station?.name,
            deferredReview = true
        )
        Toast.makeText(
            context,
            queuedBatchToastMsg,
            Toast.LENGTH_LONG
        ).show()
        onBack()
    }

    fun startEncounterCapture(
        maxRecordingMinutes: Int,
        disableSilenceAutoStop: Boolean,
        onStartError: (String) -> Unit
    ) {
        scope.launch {
            app.startAsrCaptureWithLowMemoryHandoff(
                language = app.appConfig.language,
                onError = onStartError,
                maxRecordingMinutes = maxRecordingMinutes,
                disableSilenceAutoStop = disableSilenceAutoStop
            )
        }
    }

    suspend fun finalizeAmbientRecording() {
        extractionError = null
        // Show loading spinner immediately — cloud ASR finalization can take several seconds.
        // yield() gives Compose a frame to recompose and display the spinner BEFORE
        // the heavy stopListeningAndAwait() call blocks (especially cloud ASR).
        isGeneratingNote = true
        kotlinx.coroutines.yield()
        // Don't release ONNX here — generateDraftNote() calls unloadOfflineModelAndWait()
        // which does a synchronous release. Double-releasing wastes time and can race.
        val result = asr.stopListeningAndAwait(releaseOnnxAfterStop = false)
        transcript = result.text
        durationMs = 0L

        if (transcript.isBlank()) {
            isGeneratingNote = false
            extractionError = result.error ?: "No speech detected. Try again or type manually."
            showManualInput = true
            return
        }

        try {
            if (isBatchProcessing) {
                isGeneratingNote = false
                queueTranscriptForBatch(transcript)
                return
            }
            // Note-first flow: generate draft note first, then extract from approved note
            generateDraftNote(transcript)
        } catch (e: Exception) {
            extractionError = "Processing failed: ${e.message}. You can edit the transcript and try again."
            showManualInput = true
            isGeneratingNote = false
        }
    }

    LaunchedEffect(
        asr.mode,
        app.appConfig.language,
        asrModelLoaded,
        showManualInput,
        transcript.isNotBlank(),
        draftNote != null,
        extractedEncounter != null,
        isGeneratingNote,
        isProcessing,
        llmPreparing
    ) {
        val preferTypedNotePath = strictLowRamSerialization && (showManualInput || transcript.isNotBlank())
        if (
            asr.mode == com.chartlite.app.asr.ASREngine.Mode.ONNX_OFFLINE &&
            asr.isOnnxModelDownloadedFast() &&
            !asrModelLoaded &&
            !asr.isPreparing.value &&
            !preferTypedNotePath &&
            draftNote == null &&
            extractedEncounter == null &&
            !isGeneratingNote &&
            !isProcessing &&
            !llmPreparing
        ) {
            app.prepareOfflineAsrForCapture(app.appConfig.language)
        }
    }

    LaunchedEffect(
        showManualInput,
        transcript.isNotBlank(),
        isRecording,
        isPreparing,
        isGeneratingNote,
        isProcessing,
        asrModelLoaded
    ) {
        val preferTypedNotePath = strictLowRamSerialization && (showManualInput || transcript.isNotBlank())
        if (
            preferTypedNotePath &&
            asrModelLoaded &&
            !isRecording &&
            !isPreparing &&
            !isGeneratingNote &&
            !isProcessing
        ) {
            asr.unloadOfflineModelIfIdle()
        }
    }

    LaunchedEffect(
        showManualInput,
        transcript,
        isBatchProcessing,
        isRecording,
        isPreparing,
        isGeneratingNote,
        isProcessing
    ) {
        if (
            !showManualInput ||
            isBatchProcessing ||
            transcript.trim().length < 48 ||
            isRecording ||
            isPreparing ||
            isGeneratingNote ||
            isProcessing
        ) return@LaunchedEffect

        delay(900)

        if (
            showManualInput &&
            !isBatchProcessing &&
            transcript.trim().length >= 48 &&
            !isRecording &&
            !isPreparing &&
            !isGeneratingNote &&
            !isProcessing
        ) {
            app.prewarmOnDeviceNotesForLikelyImmediateUse()
        }
    }

    val keepOnDeviceNoteWarm =
        noteStrategyUsed?.contains("(on-device)") == true &&
            draftNote != null &&
            extractedEncounter == null

    LaunchedEffect(keepOnDeviceNoteWarm) {
        if (!keepOnDeviceNoteWarm) return@LaunchedEffect
        while (true) {
            app.llmModelManager.keepModelWarmFor(app.llmModelManager.recommendedReviewWarmLeaseMs())
            delay(noteReviewWarmRefreshMs)
        }
    }

    LaunchedEffect(isRecording, isHolding) {
        if (isRecording) {
            recordingStartTime = System.currentTimeMillis()
            while (true) {
                durationMs = System.currentTimeMillis() - recordingStartTime
                if (durationMs >= maxRecordingMs) {
                    if (isHolding) {
                        finalizeSnippetRecording()
                        isHolding = false
                    } else {
                        finalizeAmbientRecording()
                    }
                    break
                }
                delay(500)
            }
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            if (asr.isListening.value) asr.cancelListening(releaseOnnxAfterCancel = true)
        }
    }

    // Discard confirmation dialog
    if (showDiscardDialog) {
        AlertDialog(
            onDismissRequest = { showDiscardDialog = false },
            title = { Text(stringResource(R.string.discard_recording_title)) },
            text = { Text(
                if (snippetCount > 0)
                    stringResource(R.string.discard_snippets_format, snippetCount)
                else
                    stringResource(R.string.discard_active_recording)
            ) },
            confirmButton = {
                TextButton(onClick = {
                    showDiscardDialog = false
                    if (isRecording) asr.cancelListening(releaseOnnxAfterCancel = true)
                    onBack()
                }) {
                    Text(stringResource(R.string.discard))
                }
            },
            dismissButton = {
                TextButton(onClick = { showDiscardDialog = false }) {
                    Text(stringResource(R.string.keep_recording))
                }
            }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(when (station) {
                            ClinicStation.TRIAGE -> stringResource(R.string.triage)
                            ClinicStation.CONSULTATION -> stringResource(R.string.consultation)
                            else -> stringResource(R.string.record_encounter)
                        })
                        Text(
                            patientId,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = {
                        if (isRecording || transcript.isNotBlank() || snippetCount > 0) {
                            showDiscardDialog = true
                        } else {
                            onBack()
                        }
                    }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back))
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .imePadding()
                .padding(horizontal = 24.dp, vertical = 8.dp)
                .verticalScroll(screenScrollState),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // ── Patient Context Banner — show known history before recording ──
            patientContext?.let { ctx ->
                if (ctx.hasHistory) {
                    PatientContextBanner(ctx)
                    Spacer(Modifier.height(8.dp))
                }
            }

            // Processing-mode toggle moved to Settings → AI & Speech.
            // Surfacing it on every encounter screen taught users the wrong
            // mental model ("am I in batch right now?") and was visual noise
            // for clinicians who never need to flip it. The actual mode is
            // applied from `app.appConfig.noteProcessingMode` via the
            // `isBatchProcessing` state initialised at line 89.
            //
            // The strict-low-RAM hint is preserved as an inline note so the
            // user understands why ASR + LLM serialise on small phones.
            if (extractedEncounter == null && draftNote == null && !isGeneratingNote && !isProcessing && !isRecording) {
                if (strictLowRamSerialization) {
                    Text(
                        stringResource(R.string.settings_low_ram_processing_hint),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.outline,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Spacer(Modifier.height(4.dp))
                }
            }

            if (!hasPermission && hasRequestedMicPermission) {
                // Fallback: only shown after the user actively denied the
                // permission. The auto-request `LaunchedEffect` above
                // handles the first-time grant — most users never see this
                // card. Useful for the "denied, change my mind" path.
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(stringResource(R.string.microphone_access_required),
                            style = MaterialTheme.typography.bodyLarge,
                            textAlign = TextAlign.Center)
                        Spacer(Modifier.height(16.dp))
                        Button(onClick = {
                            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                        }) {
                            Text(stringResource(R.string.grant_microphone_access))
                        }
                    }
                }
            } else if (!hasPermission) {
                // First-run: auto-request is in flight. Render nothing — let
                // the system dialog be the only UI. Without this branch we
                // would briefly show the error card before LaunchedEffect runs.
                Spacer(Modifier.height(0.dp))
            } else if (isGeneratingNote) {
                // ── Generating draft note spinner ──
                CircularProgressIndicator(modifier = Modifier.size(64.dp))
                Spacer(Modifier.height(16.dp))
                Text(
                    if (llmPreparing) stringResource(R.string.preparing_notes_ai)
                    else stringResource(R.string.generating_clinical_note),
                    style = MaterialTheme.typography.titleMedium)
                Text(
                    if (llmPreparing) stringResource(R.string.preparing_notes_ai_hint)
                    else stringResource(R.string.ai_writing_draft),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else if (isProcessing) {
                // ── Extracting structured data spinner ──
                CircularProgressIndicator(modifier = Modifier.size(64.dp))
                Spacer(Modifier.height(16.dp))
                Text(
                    if (llmPreparing) stringResource(R.string.preparing_notes_ai)
                    else if (isHolding) stringResource(R.string.processing_snippet)
                    else stringResource(R.string.extracting_structured_data),
                    style = MaterialTheme.typography.titleMedium
                )
                Text(
                    if (llmPreparing) stringResource(R.string.preparing_notes_ai_hint)
                    else stringResource(R.string.coding_from_note),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else if (draftNote != null && extractedEncounter == null) {
                // ══════════════════════════════════════════════════════════════════
                // ── DRAFT NOTE REVIEW — clinician reviews/edits before extraction ──
                // ══════════════════════════════════════════════════════════════════

                Text(stringResource(R.string.draft_clinical_note),
                    style = MaterialTheme.typography.titleLarge)
                Text(stringResource(R.string.review_before_extracting),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)

                // Strategy badge
                noteStrategyUsed?.let { strategy ->
                    Spacer(Modifier.height(6.dp))
                    Surface(
                        color = MaterialTheme.colorScheme.primaryContainer,
                        shape = MaterialTheme.shapes.small
                    ) {
                        Text(
                            text = stringResource(R.string.generated_by_format, strategy),
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onPrimaryContainer
                        )
                    }
                }

                Spacer(Modifier.height(12.dp))

                // Editable draft note with formatted preview
                var editableDraftNote by remember(draftNote) { mutableStateOf(draftNote ?: "") }
                var isEditingNote by remember { mutableStateOf(false) }

                if (isEditingNote) {
                    OutlinedTextField(
                        value = editableDraftNote,
                        onValueChange = { editableDraftNote = it },
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = 250.dp, max = 500.dp),
                        textStyle = MaterialTheme.typography.bodyMedium,
                        shape = RoundedCornerShape(12.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = MaterialTheme.colorScheme.primary,
                            unfocusedBorderColor = MaterialTheme.colorScheme.outlineVariant
                        )
                    )
                    TextButton(onClick = { isEditingNote = false }) {
                        Text(stringResource(R.string.done_editing))
                    }
                } else {
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { isEditingNote = true },
                        shape = RoundedCornerShape(12.dp),
                        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            MarkdownText(
                                text = editableDraftNote,
                                style = MaterialTheme.typography.bodyMedium
                            )
                        }
                    }
                    Text(
                        text = stringResource(R.string.tap_to_edit),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }

                // Error display with retry
                ExtractionErrorCard(
                    error = extractionError,
                    onRetry = {
                        extractionError = null
                        scope.launch { extractFromApprovedNote(editableDraftNote) }
                    }
                )

                Spacer(Modifier.height(16.dp))

                // Approve & Extract button
                Button(
                    onClick = {
                        scope.launch {
                            extractFromApprovedNote(editableDraftNote)
                        }
                    },
                    enabled = editableDraftNote.isNotBlank(),
                    modifier = Modifier.fillMaxWidth().height(52.dp)
                ) {
                    Text(stringResource(R.string.approve_and_extract), style = MaterialTheme.typography.titleMedium)
                }

                Spacer(Modifier.height(8.dp))

                // Regenerate note from same transcript
                OutlinedButton(
                    onClick = {
                        draftNote = null
                        noteStrategyUsed = null
                        extractionError = null
                        scope.launch { generateDraftNote(transcript) }
                    },
                    enabled = !isGeneratingNote && transcript.isNotBlank(),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(
                        Icons.Default.Refresh,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(stringResource(R.string.regenerate_note))
                }

                Spacer(Modifier.height(8.dp))

                // Re-record / back to recording
                OutlinedButton(
                    onClick = {
                        draftNote = null
                        noteStrategyUsed = null
                        extractedEncounter = null
                        transcript = ""
                        showManualInput = false
                        extractionError = null
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(stringResource(R.string.re_record))
                }

                // Show original transcript for reference (collapsed by default)
                if (transcript.isNotBlank()) {
                    Spacer(Modifier.height(12.dp))
                    var showTranscript by rememberSaveable { mutableStateOf(false) }
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { showTranscript = !showTranscript },
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f)
                        )
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    if (showTranscript) stringResource(R.string.hide_original_transcript)
                                    else stringResource(R.string.show_original_transcript),
                                    style = MaterialTheme.typography.titleSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Icon(
                                    if (showTranscript) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                                    contentDescription = null,
                                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.size(20.dp)
                                )
                            }
                            if (showTranscript) {
                                Spacer(Modifier.height(4.dp))
                                Text(transcript,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            } else if (extractedEncounter == null) {
                // ══════════════════════════════════════════════════════════
                // ── UNIFIED RECORDING: Tap to scribe · Hold to dictate ──
                // ══════════════════════════════════════════════════════════

                // Accumulated snippet summary (from hold-to-dictate)
                accumulatedEncounter?.let { acc ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.secondaryContainer
                        )
                    ) {
                        Column(
                            modifier = Modifier.padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            Text(
                                stringResource(R.string.captured_snippets_format, snippetCount, if (snippetCount != 1) "s" else ""),
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.SemiBold,
                                color = MaterialTheme.colorScheme.onSecondaryContainer
                            )
                            val parts = mutableListOf<String>()
                            if (acc.suggestedDiagnoses.isNotEmpty())
                                parts += "Dx: ${acc.suggestedDiagnoses.joinToString(", ") { it.icd10Code }}"
                            if (acc.medications.isNotEmpty())
                                parts += "Rx: ${acc.medications.joinToString(", ") { it.name }}"
                            acc.vitals?.let { v ->
                                val vp = listOfNotNull(
                                    v.systolicBP?.let { "BP $it/${v.diastolicBP ?: "?"}" },
                                    v.pulse?.let { "P $it" },
                                    v.temperature?.let { "T ${"%.1f".format(it)}" }
                                )
                                if (vp.isNotEmpty()) parts += vp.joinToString(" | ")
                            }
                            if (acc.examFindings.isNotEmpty())
                                parts += "Exam: ${acc.examFindings.take(3).joinToString(", ")}"
                            if (parts.isNotEmpty()) {
                                Text(
                                    parts.joinToString("  ·  "),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSecondaryContainer,
                                    maxLines = 3
                                )
                            }
                        }
                    }
                    Spacer(Modifier.height(12.dp))
                }

                if (!showManualInput) {
                    // ── Voice recording UI ──

                    // Timer (while recording)
                    if (isRecording) {
                        val minutes = (durationMs / 60000).toInt()
                        val seconds = ((durationMs % 60000) / 1000).toInt()
                        Text(
                            String.format("%02d:%02d", minutes, seconds),
                            style = MaterialTheme.typography.headlineLarge,
                            fontWeight = FontWeight.Light,
                            fontSize = 48.sp
                        )
                        Spacer(Modifier.height(8.dp))

                        LinearProgressIndicator(
                            progress = { amplitude },
                            modifier = Modifier
                                .fillMaxWidth(0.6f)
                                .height(6.dp)
                                .clip(MaterialTheme.shapes.small),
                            color = if (isHolding) MaterialTheme.colorScheme.tertiary
                                    else MaterialTheme.colorScheme.primary,
                            trackColor = MaterialTheme.colorScheme.surfaceVariant
                        )

                        Spacer(Modifier.height(16.dp))
                    }

                    // ── Unified mic button: tap = scribe, hold = dictate ──
                    RecordButton(
                        isRecording = isRecording,
                        amplitude = amplitude,
                        enabled = !isPreparing,
                        isPreparing = isPreparing,
                        isHolding = isHolding,
                        onClick = {
                            // Tap: toggle ambient scribe
                            if (isRecording && !isHolding) {
                                scope.launch { finalizeAmbientRecording() }
                            } else if (!isRecording) {
                                extractionError = null
                                startEncounterCapture(
                                    maxRecordingMinutes = app.appConfig.maxRecordingMinutes,
                                    disableSilenceAutoStop = true,
                                    onStartError = { msg ->
                                        extractionError = msg
                                        showManualInput = true
                                    }
                                )
                            }
                        },
                        onHoldStart = {
                            // Hold: start dictation recording
                            if (!isRecording) {
                                isHolding = true
                                extractionError = null
                                startEncounterCapture(
                                    maxRecordingMinutes = 2,
                                    disableSilenceAutoStop = false,
                                    onStartError = { msg ->
                                        extractionError = msg
                                        isHolding = false
                                    }
                                )
                            }
                        },
                        onHoldEnd = {
                            // Release: finalize snippet or cancel if still preparing
                            if (isHolding) {
                                if (isRecording) {
                                    scope.launch {
                                        finalizeSnippetRecording()
                                        isHolding = false
                                    }
                                } else {
                                    // User released before ASR finished starting —
                                    // cancel the pending recording so it doesn't
                                    // keep running after finger lifts.
                                    asr.cancelListening(releaseOnnxAfterCancel = false)
                                    isHolding = false
                                }
                            }
                        }
                    )

                    Spacer(Modifier.height(8.dp))

                    // Contextual hint text
                    Text(
                        when {
                            isPreparing -> stringResource(R.string.preparing_voice_model_hint)
                            isRecording && isHolding -> stringResource(R.string.listening_release_to_capture)
                            isRecording -> stringResource(R.string.recording_consultation)
                            snippetCount > 0 -> stringResource(R.string.hold_to_add_more)
                            else -> stringResource(R.string.tap_to_scribe)
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center
                    )

                    // Explicit "Done Recording" button during ambient recording
                    if (isRecording && !isHolding) {
                        Spacer(Modifier.height(12.dp))
                        Button(
                            onClick = { scope.launch { finalizeAmbientRecording() } },
                            modifier = Modifier.fillMaxWidth().height(48.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.primary
                            )
                        ) {
                            Icon(
                                Icons.Default.Check,
                                contentDescription = stringResource(R.string.content_desc_done),
                                modifier = Modifier.size(20.dp)
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(stringResource(R.string.done_recording))
                        }
                    }

                    // ── Camera scan button ──
                    if (!isRecording) {
                        val visionTier = remember { app.fastActiveLlmTier() }
                        val visionReady = app.isLlmVisionModelDownloadedFast()
                        if (visionReady) {
                            Spacer(Modifier.height(12.dp))
                            OutlinedButton(
                                onClick = { showCamera = true },
                                modifier = Modifier.fillMaxWidth().height(44.dp),
                                enabled = !isScanProcessing
                            ) {
                                if (isScanProcessing) {
                                    CircularProgressIndicator(
                                        modifier = Modifier.size(18.dp),
                                        strokeWidth = 2.dp
                                    )
                                    Spacer(Modifier.width(8.dp))
                                    Text(scanStageMessage ?: stringResource(R.string.scan_analyzing))
                                } else {
                                    Icon(
                                        Icons.Default.CameraAlt,
                                        contentDescription = stringResource(R.string.content_desc_scan),
                                        modifier = Modifier.size(18.dp)
                                    )
                                    Spacer(Modifier.width(8.dp))
                                    Text(stringResource(R.string.scan_button_label))
                                }
                            }
                        } else {
                            // Either vision-capable tier without the model
                            // downloaded yet, OR a tier with no vision support
                            // at all (Qwen on a low-RAM device). Both paths
                            // need the user to visit Settings, so render a
                            // single clickable hint that deeplinks there —
                            // otherwise the user reads "in Settings" and has
                            // to manually navigate Home → Settings → AI tab.
                            val hint = if (visionTier.supportsVision)
                                stringResource(R.string.scan_setup_hint)
                            else
                                stringResource(R.string.scan_upgrade_hint)
                            Spacer(Modifier.height(12.dp))
                            Text(
                                text = hint,
                                style = MaterialTheme.typography.labelMedium,
                                color = if (onOpenSettings != null)
                                    MaterialTheme.colorScheme.primary
                                else
                                    MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .let { m ->
                                        if (onOpenSettings != null)
                                            m.clickable { onOpenSettings() }
                                        else m
                                    }
                                    .padding(vertical = 8.dp),
                                textAlign = TextAlign.Center,
                            )
                        }
                        lastScanType?.let { type ->
                            Spacer(Modifier.height(4.dp))
                            Text(
                                "Scanned: ${type.replace('_', ' ')}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.primary
                            )
                        }
                    }

                    // Live transcript while recording
                    LiveTranscriptCard(isRecording, liveTranscript)

                    // Error message
                    ExtractionErrorCard(
                        error = extractionError,
                        onRetry = {
                            extractionError = null
                            startEncounterCapture(
                                maxRecordingMinutes = app.appConfig.maxRecordingMinutes,
                                disableSilenceAutoStop = true,
                                onStartError = { msg ->
                                    extractionError = msg
                                    showManualInput = true
                                }
                            )
                        }
                    )

                    Spacer(Modifier.height(16.dp))

                    // Process button (when snippets captured and not recording)
                    if (snippetCount > 0 && !isRecording) {
                        Button(
                            onClick = {
                                scope.launch {
                                    val combined = snippetTranscripts.joinToString(". ")
                                    if (isBatchProcessing) {
                                        queueTranscriptForBatch(combined)
                                    } else {
                                        // Note-first flow for snippets too
                                        generateDraftNote(combined)
                                    }
                                }
                            },
                            modifier = Modifier.fillMaxWidth().height(48.dp)
                        ) {
                            Text(
                                if (isBatchProcessing)
                                    stringResource(R.string.queue_snippets_format, snippetCount, if (snippetCount != 1) "s" else "")
                                else
                                    stringResource(R.string.process_review_snippets_format, snippetCount, if (snippetCount != 1) "s" else ""))
                        }

                        Spacer(Modifier.height(6.dp))

                        OutlinedButton(
                            onClick = {
                                accumulatedEncounter = null
                                snippetTranscripts = emptyList()
                                snippetCount = 0
                                extractionError = null
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(stringResource(R.string.clear_all))
                        }
                    }

                    // Manual input option
                    if (!isRecording && snippetCount == 0) {
                        OutlinedButton(onClick = {
                            showManualInput = true

                        }) {
                            Text(stringResource(R.string.type_manually_instead))
                        }
                    }
                }

                // Manual text input
                if (showManualInput && !isRecording) {
                    OutlinedTextField(
                        value = transcript,
                        onValueChange = { transcript = it },
                        label = { Text(stringResource(R.string.clinical_encounter_label)) },
                        modifier = Modifier.fillMaxWidth().heightIn(min = 150.dp),
                        maxLines = 10,
                        placeholder = { Text(
                            stringResource(R.string.clinical_encounter_placeholder)
                        ) }
                    )
                    Spacer(Modifier.height(12.dp))
                    // Manual text input always processes immediately, regardless of
                    // the batch-mode setting. Reasoning: a clinician typing manually
                    // has the text ready *now* and wants the structured note *now*;
                    // the batch toggle is for long voice sessions on low-RAM phones,
                    // not for short typed snippets. The previous behaviour silently
                    // queued + dumped the user back to the timeline with no preview.
                    Button(
                        onClick = {
                            scope.launch {
                                generateDraftNote(transcript)
                            }
                        },
                        enabled = transcript.isNotBlank(),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(stringResource(R.string.process_notes))
                    }

                    if (!isBatchProcessing && llmPreparing) {
                        Spacer(Modifier.height(6.dp))
                        Text(
                            stringResource(R.string.preparing_notes_ai_hint),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }

                    Spacer(Modifier.height(4.dp))

                    // Back to voice recording
                    TextButton(onClick = {
                        showManualInput = false
                        transcript = ""
                    }) {
                        Text(stringResource(R.string.back_to_voice_recording))
                    }
                }
            } else if (extractedEncounter != null) {
                // ══════════════════════════════════════════════════════════════
                // ── REVIEW & EDIT — tap any section to edit ──
                // ══════════════════════════════════════════════════════════════
                val enc = extractedEncounter ?: return@Column

                // ── Editable state — initialized from extracted encounter ──
                var editSummary by remember(enc) { mutableStateOf(enc.freeTextNote) }
                val diagnosisCandidates = remember(enc) {
                    (enc.diagnoses + enc.suggestedDiagnoses)
                        .distinctBy { "${it.icd10Code.uppercase()}|${it.description.lowercase()}" }
                }
                var selectedDiagnosisKeys by remember(enc) {
                    mutableStateOf(
                        diagnosisCandidates
                            .filter { it.source.equals("clinician", ignoreCase = true) }
                            .map { "${it.icd10Code.uppercase()}|${it.description.lowercase()}" }
                            .toSet()
                    )
                }
                val needsDiagnosisReview = diagnosisCandidates.any {
                    !it.source.equals("clinician", ignoreCase = true)
                }
                var diagnosisReviewComplete by remember(enc) {
                    mutableStateOf(!needsDiagnosisReview)
                }
                var editExamFindings by remember(enc) { mutableStateOf(enc.examFindings.joinToString("\n")) }
                var editInvestigations by remember(enc) {
                    mutableStateOf(enc.investigations.joinToString("\n") { inv ->
                        "${inv.test}${inv.result?.let { ": $it" } ?: ""}"
                    })
                }
                var editMedications by remember(enc) {
                    mutableStateOf(enc.medications.joinToString("\n") { med ->
                        "${med.name} ${med.dose ?: ""}${med.unit ?: ""} ${med.frequency ?: ""}".trim()
                    })
                }
                var editImmunizations by remember(enc) {
                    mutableStateOf(enc.immunizations.joinToString("\n") { imm ->
                        "${imm.vaccineName.ifBlank { imm.vaccineCode }} dose ${imm.doseNumber}"
                    })
                }
                var editVitals by remember(enc) {
                    val v = enc.vitals
                    mutableStateOf(
                        listOfNotNull(
                            v?.systolicBP?.let { "BP: $it/${v.diastolicBP ?: "?"}" },
                            v?.temperature?.let { "Temp: ${"%.1f".format(it)}°C" },
                            v?.pulse?.let { "Pulse: $it bpm" },
                            v?.weight?.let { "Wt: ${"%.1f".format(it)} kg" },
                            v?.oxygenSaturation?.let { "SpO2: $it%" }
                        ).joinToString("\n")
                    )
                }
                var editAllergies by remember(enc) { mutableStateOf(enc.allergies.joinToString("\n")) }
                var editPlan by remember(enc) { mutableStateOf(enc.plan.joinToString("\n")) }
                var editSocialHistory by remember(enc) { mutableStateOf(enc.socialHistory.joinToString("\n")) }
                var editFollowUp by remember(enc) {
                    mutableStateOf(enc.followUp?.let {
                        "Return in ${it.days} days${it.reason?.let { r -> " — $r" } ?: ""}"
                    } ?: "")
                }
                var editReferral by remember(enc) {
                    val ref = enc.referral.normalizedOrNull()
                    mutableStateOf(ref?.let {
                        "${it.specialty ?: it.type} (${it.urgency})${it.reason?.let { r -> " — $r" } ?: ""}"
                    } ?: "")
                }
                // Referral patient instructions — auto-filled from urgency, editable by doctor
                var editReferralInstructions by remember(enc) {
                    val ref = enc.referral.normalizedOrNull()
                    mutableStateOf(when (ref?.urgency?.uppercase()) {
                        "EMERGENCY" -> "Go immediately. Bring ID and clinic card."
                        "URGENT" -> "Bring ID, clinic card, and current medications."
                        else -> if (ref != null) "Bring ID, clinic card, test results, and medications list." else ""
                    })
                }

                // Track which section is being edited
                var editingSection by remember { mutableStateOf<String?>(null) }
                var pendingSmsEncounter by remember { mutableStateOf<StructuredEncounter?>(null) }
                var pendingSmsPhone by remember { mutableStateOf<String?>(null) }
                var pendingSafetyEncounter by remember { mutableStateOf<StructuredEncounter?>(null) }
                var pendingSafetyPhone by remember { mutableStateOf<String?>(null) }
                var pendingSafetyAlerts by remember { mutableStateOf<List<CDSSAlert>>(emptyList()) }

                // Build edited encounter for saving
                fun buildEditedEncounter(): StructuredEncounter {
                    // Parse medications: preserve structured fields from original when name matches
                    val parsedMeds = editMedications.lines().map { it.trim() }.filter { it.isNotBlank() }.map { line ->
                        val originalMatch = enc.medications.firstOrNull { med ->
                            line.startsWith(med.name, ignoreCase = true)
                        }
                        if (originalMatch != null) {
                            originalMatch // preserve dose/unit/frequency/route
                        } else {
                            val parts = line.split(Regex("\\s+")).filter { it.isNotBlank() }
                            val doseIndex = parts.indexOfFirst { it.toFloatOrNull() != null }
                            val name = when {
                                doseIndex > 0 -> parts.take(doseIndex).joinToString(" ")
                                else -> line
                            }
                            Medication(
                                formularyCode = "",
                                name = name,
                                dose = doseIndex.takeIf { it >= 0 }?.let { parts.getOrNull(it)?.toFloatOrNull() },
                                unit = doseIndex.takeIf { it >= 0 }?.let { parts.getOrNull(it + 1) },
                                frequency = doseIndex.takeIf { it >= 0 }?.let { parts.drop(it + 2).joinToString(" ").ifBlank { null } }
                            )
                        }
                    }

                    // Parse vitals from display format (e.g., "BP: 130/85", "Temp: 37.5°C")
                    val parsedVitals = run {
                        val lines = editVitals.lines().map { it.trim() }.filter { it.isNotBlank() }
                        if (lines.isEmpty()) null
                        else {
                            var v = enc.vitals ?: VitalSigns()
                            lines.forEach { line ->
                                val upper = line.uppercase()
                                val afterColon = line.substringAfter(":", line).trim()
                                when {
                                    upper.startsWith("BP") -> {
                                        Regex("(\\d+)\\s*/\\s*(\\d+)").find(afterColon)?.let { m ->
                                            v = v.copy(systolicBP = m.groupValues[1].toIntOrNull(), diastolicBP = m.groupValues[2].toIntOrNull())
                                        }
                                    }
                                    upper.startsWith("TEMP") -> { Regex("([\\d.]+)").find(afterColon)?.let { v = v.copy(temperature = it.groupValues[1].toFloatOrNull()) } }
                                    upper.startsWith("PULSE") || upper.startsWith("HR") -> { Regex("(\\d+)").find(afterColon)?.let { v = v.copy(pulse = it.groupValues[1].toIntOrNull()) } }
                                    upper.startsWith("WT") || upper.startsWith("WEIGHT") -> { Regex("([\\d.]+)").find(afterColon)?.let { v = v.copy(weight = it.groupValues[1].toFloatOrNull()) } }
                                    upper.startsWith("SPO2") || upper.startsWith("SAT") -> { Regex("(\\d+)").find(afterColon)?.let { v = v.copy(oxygenSaturation = it.groupValues[1].toIntOrNull()) } }
                                    upper.startsWith("RR") || upper.startsWith("RESP") -> { Regex("(\\d+)").find(afterColon)?.let { v = v.copy(respiratoryRate = it.groupValues[1].toIntOrNull()) } }
                                    upper.startsWith("HT") || upper.startsWith("HEIGHT") -> { Regex("([\\d.]+)").find(afterColon)?.let { v = v.copy(height = it.groupValues[1].toFloatOrNull()) } }
                                }
                            }
                            v
                        }
                    }

                    // Parse follow-up: "Return in N days — reason"
                    val parsedFollowUp = editFollowUp.trim().let { text ->
                        if (text.isBlank()) null
                        else {
                            val daysMatch = Regex("(\\d+)\\s*days?", RegexOption.IGNORE_CASE).find(text)
                            val reason = text.replace(Regex("Return in\\s*\\d+\\s*days?\\s*—?\\s*", RegexOption.IGNORE_CASE), "").trim().ifBlank { null }
                            FollowUp(days = daysMatch?.groupValues?.get(1)?.toIntOrNull() ?: 7, reason = reason ?: text.takeIf { daysMatch == null })
                        }
                    }

                    // Parse referral: "Specialty (urgency) — reason"
                    val parsedReferral = editReferral.trim().let { text ->
                        if (text.isBlank()) null
                        else {
                            val match = Regex("^(.+?)\\s*\\((.+?)\\)\\s*(?:—\\s*(.+))?$").find(text)
                            if (match != null) Referral(type = "specialist", specialty = match.groupValues[1].trim(), urgency = match.groupValues[2].trim().lowercase(), reason = match.groupValues[3].trim().ifBlank { null })
                            else Referral(type = "specialist", specialty = text, urgency = "routine")
                        }
                    }

                    val confirmedDiagnoses = diagnosisCandidates
                        .filter { candidate ->
                            "${candidate.icd10Code.uppercase()}|${candidate.description.lowercase()}" in selectedDiagnosisKeys
                        }
                        .mapIndexed { index, diagnosis ->
                            diagnosis.copy(
                                isPrimary = index == 0,
                                source = "clinician"
                            )
                        }

                    return enc.copy(
                        freeTextNote = editSummary,
                        examFindings = editExamFindings.lines().map { it.trim() }.filter { it.isNotBlank() },
                        investigations = editInvestigations.lines().map { it.trim() }.filter { it.isNotBlank() }.map { line ->
                            val parts = line.split(":", limit = 2)
                            Investigation(test = parts[0].trim(), result = parts.getOrNull(1)?.trim()?.ifBlank { null })
                        },
                        medications = parsedMeds,
                        diagnoses = confirmedDiagnoses,
                        suggestedDiagnoses = emptyList(),
                        vitals = parsedVitals,
                        followUp = parsedFollowUp,
                        referral = parsedReferral,
                        allergies = editAllergies.lines().map { it.trim() }.filter { it.isNotBlank() },
                        plan = editPlan.lines().map { it.trim() }.filter { it.isNotBlank() },
                        socialHistory = editSocialHistory.lines().map { it.trim() }.filter { it.isNotBlank() }
                    )
                }

                fun saveEditedEncounter(editedEnc: StructuredEncounter, sendPatientSms: Boolean) {
                    if (isSaving) return
                    isSaving = true
                    extractionError = null
                    scope.launch {
                        try {
                            val patient = app.patientRepository.getById(patientId)
                            val savedId = EncounterSaveCoordinator.saveEncounter(
                                app = app,
                                encounter = editedEnc,
                                patientId = patientId,
                                visitId = visitId,
                                station = station,
                                referralInstructions = editReferralInstructions.ifBlank { null },
                                referralSmsOverride = null,
                                sendPatientSms = sendPatientSms
                            )
                            val phone = patient?.phoneNumber
                            if (sendPatientSms && !phone.isNullOrBlank()) {
                                val maskedPhone = "***" + phone.takeLast(4)
                                val dxCount = editedEnc.suggestedDiagnoses.size + editedEnc.diagnoses.size
                                val medCount = editedEnc.medications.size
                                Toast.makeText(
                                    context,
                                    String.format(smsSendingFormat, maskedPhone, dxCount, medCount),
                                    Toast.LENGTH_LONG
                                ).show()
                            }
                            onEncounterSaved(savedId)
                        } catch (e: CancellationException) {
                            isSaving = false
                            throw e
                        } catch (e: Exception) {
                            extractionError = "Save failed: ${e.message}"
                            isSaving = false
                        }
                    }
                }

                fun continueAfterSafetyCheck(editedEnc: StructuredEncounter, phone: String?) {
                    if (!phone.isNullOrBlank()) {
                        pendingSmsEncounter = editedEnc
                        pendingSmsPhone = phone
                    } else {
                        saveEditedEncounter(editedEnc, sendPatientSms = false)
                    }
                }

                pendingSafetyEncounter?.let { pendingEncounter ->
                    val criticalCount = pendingSafetyAlerts.count { it.severity == AlertSeverity.CRITICAL }
                    val warningCount = pendingSafetyAlerts.count { it.severity == AlertSeverity.WARNING }
                    AlertDialog(
                        onDismissRequest = { /* An explicit choice is required for clinical safety. */ },
                        icon = {
                            Icon(
                                Icons.Default.Warning,
                                contentDescription = null,
                                tint = if (criticalCount > 0) MaterialTheme.colorScheme.error
                                    else MaterialTheme.colorScheme.tertiary
                            )
                        },
                        title = {
                            Text(
                                if (criticalCount > 0) "Safety check — $criticalCount critical"
                                else "Safety check — $warningCount warning${if (warningCount == 1) "" else "s"}"
                            )
                        },
                        text = {
                            Column(
                                modifier = Modifier
                                    .heightIn(max = 360.dp)
                                    .verticalScroll(rememberScrollState()),
                                verticalArrangement = Arrangement.spacedBy(10.dp)
                            ) {
                                pendingSafetyAlerts.forEach { alert ->
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        verticalAlignment = Alignment.Top
                                    ) {
                                        Icon(
                                            Icons.Default.Warning,
                                            contentDescription = null,
                                            tint = when (alert.severity) {
                                                AlertSeverity.CRITICAL -> MaterialTheme.colorScheme.error
                                                AlertSeverity.WARNING -> MaterialTheme.colorScheme.tertiary
                                                AlertSeverity.INFO -> MaterialTheme.colorScheme.primary
                                            },
                                            modifier = Modifier.size(18.dp)
                                        )
                                        Spacer(Modifier.width(8.dp))
                                        Column {
                                            Text(
                                                alert.message,
                                                style = MaterialTheme.typography.bodyMedium,
                                                fontWeight = FontWeight.SemiBold
                                            )
                                            Text(
                                                alert.category,
                                                style = MaterialTheme.typography.labelSmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                        }
                                    }
                                }
                                Text(
                                    "Nothing has been saved yet. Review the encounter, or explicitly acknowledge these alerts to continue.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        },
                        confirmButton = {
                            Button(onClick = {
                                pendingSafetyEncounter = null
                                pendingSafetyPhone = null
                                pendingSafetyAlerts = emptyList()
                                editingSection = if (criticalCount > 0) "medications" else null
                                scope.launch { screenScrollState.animateScrollTo(0) }
                            }) {
                                Text("Review encounter")
                            }
                        },
                        dismissButton = {
                            TextButton(onClick = {
                                val phone = pendingSafetyPhone
                                pendingSafetyEncounter = null
                                pendingSafetyPhone = null
                                pendingSafetyAlerts = emptyList()
                                continueAfterSafetyCheck(pendingEncounter, phone)
                            }) {
                                Text("Acknowledge and continue")
                            }
                        }
                    )
                }

                pendingSmsEncounter?.let { pendingEncounter ->
                    AlertDialog(
                        onDismissRequest = {
                            pendingSmsEncounter = null
                            pendingSmsPhone = null
                        },
                        title = { Text("Send SMS health record?") },
                        text = {
                            Text(
                                "This will send an encrypted clinical SMS to ***${pendingSmsPhone.orEmpty().takeLast(4)}. Use Save only if the phone is shared, consent is unclear, or SMS costs should be avoided."
                            )
                        },
                        confirmButton = {
                            TextButton(onClick = {
                                pendingSmsEncounter = null
                                pendingSmsPhone = null
                                saveEditedEncounter(pendingEncounter, sendPatientSms = true)
                            }) {
                                Text("Save and send")
                            }
                        },
                        dismissButton = {
                            Row {
                                TextButton(onClick = {
                                    pendingSmsEncounter = null
                                    pendingSmsPhone = null
                                    saveEditedEncounter(pendingEncounter, sendPatientSms = false)
                                }) {
                                    Text("Save only")
                                }
                                TextButton(onClick = {
                                    pendingSmsEncounter = null
                                    pendingSmsPhone = null
                                }) {
                                    Text(stringResource(R.string.cancel))
                                }
                            }
                        }
                    )
                }

                // ── Header ──
                Text(
                    stringResource(R.string.review_and_edit),
                    style = MaterialTheme.typography.titleLarge
                )
                Text(
                    stringResource(R.string.tap_section_to_edit),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(6.dp))

                // Strategy badge row
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    extractionStrategyUsed?.let { strategy ->
                        val isAi = !strategy.contains("Regex", ignoreCase = true)
                        Surface(
                            color = if (isAi) MaterialTheme.colorScheme.primaryContainer
                                    else MaterialTheme.colorScheme.tertiaryContainer,
                            shape = MaterialTheme.shapes.small
                        ) {
                            Text(
                                text = strategy.replace("(on-device)", "").trim() +
                                    if (snippetCount > 0) " · $snippetCount snippets" else "",
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                                style = MaterialTheme.typography.labelSmall,
                                color = if (isAi) MaterialTheme.colorScheme.onPrimaryContainer
                                        else MaterialTheme.colorScheme.onTertiaryContainer
                            )
                        }
                    }
                }

                // ── Confidence bar ──
                Spacer(Modifier.height(8.dp))
                val confidencePct = enc.extractionConfidence
                val confidenceColor = when {
                    confidencePct >= 0.7f -> MaterialTheme.colorScheme.primary
                    confidencePct >= 0.5f -> MaterialTheme.colorScheme.tertiary
                    else -> MaterialTheme.colorScheme.error
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    LinearProgressIndicator(
                        progress = { confidencePct },
                        modifier = Modifier
                            .weight(1f)
                            .height(6.dp)
                            .clip(MaterialTheme.shapes.small),
                        color = confidenceColor,
                        trackColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                    Text(
                        "${"%.0f".format(confidencePct * 100)}%",
                        style = MaterialTheme.typography.labelSmall,
                        color = confidenceColor
                    )
                }
                if (confidencePct < 0.5f) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        stringResource(R.string.low_confidence_warning),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }

                Spacer(Modifier.height(12.dp))

                // ── Editable sections card ──
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surface
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(2.dp)
                    ) {
                        // Clinical Summary — collapsed by default (already approved on previous screen)
                        EditableSection(
                            title = stringResource(R.string.clinical_summary),
                            value = editSummary,
                            isEditing = editingSection == "summary",
                            onEditToggle = { editingSection = if (editingSection == "summary") null else "summary" },
                            onValueChange = { editSummary = it },
                            singleLine = false,
                            useMarkdown = true,
                            collapsible = true,
                            initiallyCollapsed = true
                        )

                        if (diagnosisCandidates.isNotEmpty()) {
                            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                            Text(
                                "Diagnoses — clinician review",
                                style = MaterialTheme.typography.titleSmall,
                                color = if (diagnosisReviewComplete) MaterialTheme.colorScheme.primary
                                    else MaterialTheme.colorScheme.tertiary
                            )
                            Text(
                                "Select only diagnoses you confirm. Unselected suggestions will not enter the patient record.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            diagnosisCandidates.forEach { diagnosis ->
                                val key = "${diagnosis.icd10Code.uppercase()}|${diagnosis.description.lowercase()}"
                                val selected = key in selectedDiagnosisKeys
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable {
                                            selectedDiagnosisKeys = if (selected) {
                                                selectedDiagnosisKeys - key
                                            } else {
                                                selectedDiagnosisKeys + key
                                            }
                                            if (needsDiagnosisReview) diagnosisReviewComplete = false
                                        },
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Checkbox(
                                        checked = selected,
                                        onCheckedChange = { checked ->
                                            selectedDiagnosisKeys = if (checked) {
                                                selectedDiagnosisKeys + key
                                            } else {
                                                selectedDiagnosisKeys - key
                                            }
                                            if (needsDiagnosisReview) diagnosisReviewComplete = false
                                        }
                                    )
                                    Text(
                                        "${diagnosis.icd10Code} — ${diagnosis.description}",
                                        style = MaterialTheme.typography.bodyMedium,
                                        modifier = Modifier.weight(1f)
                                    )
                                }
                            }
                            if (needsDiagnosisReview) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable { diagnosisReviewComplete = !diagnosisReviewComplete },
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Checkbox(
                                        checked = diagnosisReviewComplete,
                                        onCheckedChange = { diagnosisReviewComplete = it }
                                    )
                                    Text(
                                        "I reviewed these diagnosis suggestions",
                                        style = MaterialTheme.typography.labelLarge,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                }
                            }
                        }

                        // Exam Findings
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                        EditableSection(
                            title = stringResource(R.string.exam_findings),
                            value = editExamFindings,
                            isEditing = editingSection == "exam",
                            onEditToggle = { editingSection = if (editingSection == "exam") null else "exam" },
                            onValueChange = { editExamFindings = it },
                            displayPrefix = "· "
                        )

                        // Investigations
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                        EditableSection(
                            title = stringResource(R.string.investigations),
                            value = editInvestigations,
                            isEditing = editingSection == "investigations",
                            onEditToggle = { editingSection = if (editingSection == "investigations") null else "investigations" },
                            onValueChange = { editInvestigations = it },
                            displayPrefix = "· "
                        )

                        // Medications
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                        EditableSection(
                            title = stringResource(R.string.medications),
                            value = editMedications,
                            isEditing = editingSection == "medications",
                            onEditToggle = { editingSection = if (editingSection == "medications") null else "medications" },
                            onValueChange = { editMedications = it },
                            displayPrefix = "· "
                        )

                        // Immunizations (only show if any were extracted)
                        if (editImmunizations.isNotBlank()) {
                            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                            EditableSection(
                                title = stringResource(R.string.immunizations),
                                value = editImmunizations,
                                isEditing = editingSection == "immunizations",
                                onEditToggle = { editingSection = if (editingSection == "immunizations") null else "immunizations" },
                                onValueChange = { editImmunizations = it },
                                displayPrefix = "· "
                            )
                        }

                        // Vitals
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                        EditableSection(
                            title = stringResource(R.string.vitals),
                            value = editVitals,
                            isEditing = editingSection == "vitals",
                            onEditToggle = { editingSection = if (editingSection == "vitals") null else "vitals" },
                            onValueChange = { editVitals = it },
                            displayPrefix = ""
                        )

                        // Allergies
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                        EditableSection(
                            title = stringResource(R.string.allergies),
                            value = editAllergies,
                            isEditing = editingSection == "allergies",
                            onEditToggle = { editingSection = if (editingSection == "allergies") null else "allergies" },
                            onValueChange = { editAllergies = it },
                            titleColor = MaterialTheme.colorScheme.error,
                            displayPrefix = "· "
                        )

                        // Plan
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                        EditableSection(
                            title = stringResource(R.string.plan),
                            value = editPlan,
                            isEditing = editingSection == "plan",
                            onEditToggle = { editingSection = if (editingSection == "plan") null else "plan" },
                            onValueChange = { editPlan = it },
                            displayPrefix = "· "
                        )

                        // Social History
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                        EditableSection(
                            title = stringResource(R.string.social_history),
                            value = editSocialHistory,
                            isEditing = editingSection == "social",
                            onEditToggle = { editingSection = if (editingSection == "social") null else "social" },
                            onValueChange = { editSocialHistory = it },
                            displayPrefix = "· "
                        )

                        // Follow-up
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                        EditableSection(
                            title = stringResource(R.string.follow_up),
                            value = editFollowUp,
                            isEditing = editingSection == "followup",
                            onEditToggle = { editingSection = if (editingSection == "followup") null else "followup" },
                            onValueChange = { editFollowUp = it },
                            singleLine = true
                        )

                        // Referral
                        HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                        EditableSection(
                            title = stringResource(R.string.referral),
                            value = editReferral,
                            isEditing = editingSection == "referral",
                            onEditToggle = { editingSection = if (editingSection == "referral") null else "referral" },
                            onValueChange = { editReferral = it },
                            titleColor = MaterialTheme.colorScheme.error,
                            singleLine = true
                        )

                        // Patient instructions for referral (only shown when referral exists)
                        if (editReferral.isNotBlank() || editReferralInstructions.isNotBlank()) {
                            HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                            EditableSection(
                                title = stringResource(R.string.patient_instructions_sms),
                                value = editReferralInstructions,
                                isEditing = editingSection == "referral_instructions",
                                onEditToggle = { editingSection = if (editingSection == "referral_instructions") null else "referral_instructions" },
                                onValueChange = { editReferralInstructions = it },
                                singleLine = false
                            )
                        }

                    }
                }

                // ── Transcript preview (collapsed by default) ──
                if (transcript.isNotBlank()) {
                    Spacer(Modifier.height(12.dp))
                    var showPreviewTranscript by rememberSaveable { mutableStateOf(false) }
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { showPreviewTranscript = !showPreviewTranscript },
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f)
                        )
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    if (snippetCount > 0) stringResource(R.string.dictation_snippets) else stringResource(R.string.transcript),
                                    style = MaterialTheme.typography.titleSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                                Icon(
                                    if (showPreviewTranscript) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                                    contentDescription = null,
                                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.size(20.dp)
                                )
                            }
                            if (showPreviewTranscript) {
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    transcript,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }

                Spacer(Modifier.height(24.dp))

                // ── Save button (primary action) — uses edited values ──
                Button(
                    onClick = {
                        if (isSaving) return@Button
                        val editedEnc = buildEditedEncounter()
                        scope.launch {
                            try {
                                val patient = app.patientRepository.getById(patientId)
                                val phone = patient?.phoneNumber
                                val alerts = EncounterSaveCoordinator.evaluateSafety(
                                    app = app,
                                    encounter = editedEnc,
                                    patientId = patientId
                                )
                                if (alerts.isNotEmpty()) {
                                    pendingSafetyEncounter = editedEnc
                                    pendingSafetyPhone = phone
                                    pendingSafetyAlerts = alerts
                                } else {
                                    continueAfterSafetyCheck(editedEnc, phone)
                                }
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: Exception) {
                                extractionError = "Unable to check SMS details: ${e.message}"
                            }
                        }
                    },
                    enabled = !isSaving && diagnosisReviewComplete,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.primary
                    )
                ) {
                    if (isSaving) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = MaterialTheme.colorScheme.onPrimary
                        )
                    } else {
                        Text(when (station) {
                            ClinicStation.TRIAGE -> stringResource(R.string.save_send_consultation)
                            ClinicStation.CONSULTATION -> if (enc.medications.isNotEmpty()) stringResource(R.string.save_send_pharmacy) else stringResource(R.string.save_complete_visit)
                            else -> stringResource(R.string.save_and_review)
                        }, style = MaterialTheme.typography.titleMedium)
                    }
                }

                if (!diagnosisReviewComplete) {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "Review the diagnosis suggestions above before saving.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }

                Spacer(Modifier.height(8.dp))

                // ── Re-record (secondary action) ──
                OutlinedButton(
                    onClick = {
                        extractedEncounter = null
                        draftNote = null
                        noteStrategyUsed = null
                        transcript = ""
                        showManualInput = false
                        extractionError = null
                        if (snippetCount > 0) {
                            // Go back to snippet accumulation (keep snippets)
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(if (snippetCount > 0) stringResource(R.string.add_more_snippets) else stringResource(R.string.re_record))
                }
            }
        }
    }

    // ── Multimodal capture result dialog ──
    if (showScanResult && lastScanResult != null) {
        val result = lastScanResult!!
        val outcome = lastSafetyOutcome
        AlertDialog(
            onDismissRequest = { showScanResult = false },
            confirmButton = {},  // Actions live inside the card (Add / Discard)
            title = { Text("Captured artifact") },
            text = {
                MultimodalResultCard(
                    result = result,
                    toolCalls = outcome?.toolCalls.orEmpty(),
                    alerts = outcome?.alerts.orEmpty(),
                    onAdd = {
                        // Merge into the active encounter. If the user captured
                        // before recording (a perfectly natural first move with
                        // the new universal button), seed an empty encounter so
                        // the artifact data isn't silently dropped.
                        val baseEncounter = extractedEncounter ?: StructuredEncounter(
                            id = visitId ?: java.util.UUID.randomUUID().toString(),
                            patientId = patientId,
                            providerId = providerId,
                            facilityId = app.appConfig.facilityId,
                            timestamp = java.time.Instant.now(),
                            transcript = "",
                            medications = emptyList(),
                            diagnoses = emptyList(),
                            vitals = null,
                            allergies = emptyList(),
                            followUp = null,
                            referral = null,
                            freeTextNote = "",
                            extractionConfidence = 0f,
                        )
                        extractedEncounter = EncounterMerger.mergeVisionResult(baseEncounter, result)
                        showScanResult = false
                    },
                    onDiscard = {
                        // User rejected this capture — drop the photo + DB row
                        // so it doesn't pollute the patient's record or storage.
                        val photoId = lastPhotoEntityId
                        val photoPath = lastPhotoFilePath
                        scope.launch {
                            withContext(Dispatchers.IO) {
                                if (photoId != null) {
                                    app.database.clinicalPhotoDao().deleteById(photoId)
                                }
                                if (photoPath != null) {
                                    runCatching { java.io.File(photoPath).delete() }
                                }
                            }
                        }
                        lastPhotoEntityId = null
                        lastPhotoFilePath = null
                        lastScanType = null
                        showScanResult = false
                    },
                )
            },
        )
    }

    // ── Vision-failure error dialog ──
    if (showScanError) {
        AlertDialog(
            onDismissRequest = { showScanError = false },
            title = { Text(stringResource(R.string.scan_failed_title)) },
            text = { Text(stringResource(R.string.scan_failed_body)) },
            confirmButton = {
                TextButton(onClick = {
                    // Drop the failed photo and reopen the camera so the user
                    // can retake without an extra round-trip through the UI.
                    val path = lastPhotoFilePath
                    if (path != null) runCatching { java.io.File(path).delete() }
                    lastPhotoFilePath = null
                    showScanError = false
                    showCamera = true
                }) {
                    Text(stringResource(R.string.scan_retake))
                }
            },
            dismissButton = {
                TextButton(onClick = {
                    val path = lastPhotoFilePath
                    if (path != null) runCatching { java.io.File(path).delete() }
                    lastPhotoFilePath = null
                    showScanError = false
                }) {
                    Text(stringResource(R.string.scan_dismiss))
                }
            },
        )
    }

    // ── Camera scan overlay ──
    if (showCamera) {
        ClinicalCameraCapture(
            outputDir = photoDir,
            onImageCaptured = { filePath ->
                showCamera = false
                if (isBatchProcessing) {
                    // Batch mode: save photo only, skip vision LLM to avoid model load
                    scope.launch {
                        val photoEntity = ClinicalPhotoEntity(
                            id = java.util.UUID.randomUUID().toString(),
                            encounterId = visitId ?: patientId,
                            patientId = patientId,
                            contentType = "pending",
                            filePath = filePath,
                            extractedJson = null
                        )
                        app.database.clinicalPhotoDao().insert(photoEntity)
                        Toast.makeText(context, "Photo saved — will analyze during batch processing", Toast.LENGTH_SHORT).show()
                    }
                } else {
                    // Immediate mode: run vision extraction + Gemma-driven safety
                    // tool calls. On a 3GB device ASR is released first so the
                    // vision model has RAM headroom.
                    isScanProcessing = true
                    scanStageMessage = scanAnalyzingMessage
                    val readingMsg = scanAnalyzingMessage
                    val choosingMsg = scanChoosingToolsMessage
                    val runningMsg = scanRunningToolsMessage
                    scope.launch {
                        asr.unloadOfflineModelAndWait()
                        val outcome = withContext(Dispatchers.Default) {
                            val visionExtractor = VisionExtractor(app.llmModelManager, app.promptBuilder)
                            val toolRegistry = CdssToolRegistry(app.cdss)
                            val flow = VisionToolFlow(visionExtractor, app.llmModelManager, toolRegistry)
                            // Patient context: prior allergies + current+prior diagnoses
                            // give Gemma 4 the safety surface it needs to reason
                            // about whether to call check_drug_allergy / _condition.
                            val allergies = (patientContext?.knownAllergies ?: emptyList()) +
                                (extractedEncounter?.allergies ?: emptyList())
                            val priorDxs = (patientContext?.chronicConditions?.map { it.description } ?: emptyList()) +
                                (extractedEncounter?.diagnoses?.map { it.description } ?: emptyList())
                            flow.captureAndCheck(
                                imagePath = filePath,
                                patientAllergies = allergies.distinct(),
                                patientPriorDiagnoses = priorDxs.distinct(),
                                onStage = { stage ->
                                    // Marshal back to Main: the Compose state
                                    // setter is fine off-Main, but we want
                                    // immediate recomposition.
                                    val msg = when (stage) {
                                        VisionToolFlow.Stage.READING_IMAGE -> readingMsg
                                        VisionToolFlow.Stage.CHOOSING_TOOLS -> choosingMsg
                                        VisionToolFlow.Stage.RUNNING_TOOLS -> runningMsg
                                        VisionToolFlow.Stage.DONE -> null
                                    }
                                    scope.launch(Dispatchers.Main) { scanStageMessage = msg }
                                },
                            )
                        }
                        isScanProcessing = false
                        scanStageMessage = null
                        val result = outcome.visionResult
                        if (result != null) {
                            val photoId = java.util.UUID.randomUUID().toString()
                            val photoEntity = ClinicalPhotoEntity(
                                id = photoId,
                                encounterId = visitId ?: patientId,
                                patientId = patientId,
                                contentType = result.contentType,
                                filePath = filePath,
                                extractedJson = result.rawJson
                            )
                            app.database.clinicalPhotoDao().insert(photoEntity)
                            lastScanType = result.contentType
                            lastScanResult = result
                            lastSafetyOutcome = outcome
                            lastPhotoEntityId = photoId
                            lastPhotoFilePath = filePath
                            // Defer the merge into the encounter until the user
                            // taps "Add to encounter" in the result card.
                            showScanResult = true
                        } else {
                            // Keep the photo on disk so the user can retake
                            // from a known starting point — the error dialog
                            // gives them an explicit Retake action.
                            lastPhotoFilePath = filePath
                            showScanError = true
                        }
                    }
                }
            },
            onDismiss = { showCamera = false }
        )
    }
}

/** Shared live transcript card shown while recording in both snippet and ambient modes. */
@Composable
private fun LiveTranscriptCard(
    isRecording: Boolean,
    liveTranscript: String,
    topSpacing: androidx.compose.ui.unit.Dp = 16.dp
) {
    if (isRecording && liveTranscript.isNotBlank()) {
        Spacer(Modifier.height(topSpacing))
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
            )
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    stringResource(R.string.live_transcript_label),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    liveTranscript,
                    style = MaterialTheme.typography.bodyMedium,
                    fontStyle = FontStyle.Italic
                )
            }
        }
    }
}

/** Shared extraction error card. Optionally includes a retry button. */
@Composable
private fun ExtractionErrorCard(
    error: String?,
    onRetry: (() -> Unit)? = null
) {
    if (error == null) return
    Spacer(Modifier.height(12.dp))
    Card(
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer
        )
    ) {
        Column(modifier = Modifier.padding(if (onRetry != null) 16.dp else 12.dp)) {
            Text(
                error,
                color = MaterialTheme.colorScheme.onErrorContainer,
                style = if (onRetry != null) MaterialTheme.typography.bodyMedium
                        else MaterialTheme.typography.bodySmall
            )
            onRetry?.let {
                Spacer(Modifier.height(8.dp))
                TextButton(onClick = it) {
                    Text(stringResource(R.string.try_again))
                }
            }
        }
    }
}

/** Editable section: shows read-only text by default, becomes a TextField when tapped. */
@Composable
private fun EditableSection(
    title: String,
    value: String,
    isEditing: Boolean,
    onEditToggle: () -> Unit,
    onValueChange: (String) -> Unit,
    titleColor: Color = MaterialTheme.colorScheme.primary,
    displayPrefix: String = "",
    singleLine: Boolean = false,
    useMarkdown: Boolean = false,
    collapsible: Boolean = false,
    initiallyCollapsed: Boolean = false
) {
    var isCollapsed by rememberSaveable { mutableStateOf(initiallyCollapsed && collapsible) }

    // Section header with edit/expand icon
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = {
                if (collapsible && !isEditing) {
                    isCollapsed = !isCollapsed
                } else {
                    onEditToggle()
                }
            })
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            title,
            style = MaterialTheme.typography.titleSmall,
            color = titleColor
        )
        if (collapsible && !isEditing) {
            Icon(
                imageVector = if (isCollapsed) Icons.Default.ExpandMore else Icons.Default.ExpandLess,
                contentDescription = if (isCollapsed) "Expand" else "Collapse",
                modifier = Modifier.size(18.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
            )
        } else {
            Icon(
                imageVector = if (isEditing) Icons.Default.Check else Icons.Default.Edit,
                contentDescription = if (isEditing) stringResource(R.string.done_editing) else stringResource(R.string.edit_section_format, title),
                modifier = Modifier.size(18.dp),
                tint = if (isEditing) MaterialTheme.colorScheme.primary
                       else MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
            )
        }
    }

    if (isCollapsed) {
        // Show nothing when collapsed
    } else if (isEditing) {
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            modifier = Modifier.fillMaxWidth(),
            textStyle = MaterialTheme.typography.bodyLarge,
            singleLine = singleLine,
            shape = RoundedCornerShape(8.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = MaterialTheme.colorScheme.primary,
                unfocusedBorderColor = MaterialTheme.colorScheme.outlineVariant
            ),
            placeholder = { Text(stringResource(R.string.add_section_format, title), style = MaterialTheme.typography.bodyLarge) }
        )
    } else {
        Spacer(Modifier.height(2.dp))
        if (displayPrefix.isNotEmpty()) {
            value.lines().filter { it.isNotBlank() }.forEach { line ->
                Text(
                    "$displayPrefix${line.trim()}",
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier
                        .clickable(onClick = onEditToggle)
                        .padding(vertical = 1.dp)
                )
            }
        } else if (useMarkdown) {
            MarkdownText(
                text = value,
                modifier = Modifier.clickable(onClick = onEditToggle),
                style = MaterialTheme.typography.bodyMedium
            )
        } else {
            Text(
                value,
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.clickable(onClick = onEditToggle)
            )
        }
    }

    Spacer(Modifier.height(4.dp))
}

// ═══════════════════════════════════════════════════════════════
// Patient Context Banner — known history from prior visits / SMS
// ═══════════════════════════════════════════════════════════════

@Composable
private fun PatientContextBanner(ctx: com.chartlite.app.model.PatientContext) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        shape = MaterialTheme.shapes.medium,
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Icon(Icons.Default.History, null, Modifier.size(14.dp),
                    tint = MaterialTheme.colorScheme.primary)
                Text(
                    "Patient History (${ctx.visitCount} prior visit${if (ctx.visitCount != 1) "s" else ""})",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.primary
                )
            }

            // Allergies (most critical — red)
            if (ctx.knownAllergies.isNotEmpty()) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Icon(Icons.Default.Warning, null, Modifier.size(12.dp),
                        tint = MaterialTheme.colorScheme.error)
                    Text(
                        "Allergies: ${ctx.knownAllergies.joinToString(", ")}",
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.Medium,
                        color = MaterialTheme.colorScheme.error
                    )
                }
            }

            // Active medications
            if (ctx.activeMedications.isNotEmpty()) {
                val medText = ctx.activeMedications.joinToString(", ") { med ->
                    buildString {
                        append(med.name)
                        med.dose?.let { append(" $it${med.frequency?.let { f -> " $f" } ?: ""}") }
                    }
                }
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Icon(Icons.Default.MedicalServices, null, Modifier.size(12.dp),
                        tint = MaterialTheme.colorScheme.primary)
                    Text(
                        medText,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // Chronic conditions
            if (ctx.chronicConditions.isNotEmpty()) {
                val condText = ctx.chronicConditions.joinToString(", ") { "${it.description} (${it.occurrenceCount}×)" }
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    Icon(Icons.AutoMirrored.Filled.EventNote, null, Modifier.size(12.dp),
                        tint = MaterialTheme.colorScheme.tertiary)
                    Text(
                        condText,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

/**
 * Merge prior patient history (allergies) into a newly extracted encounter.
 * Ensures CDSS drug-allergy interaction checks work during review, not just at save time.
 */
private fun mergePatientHistory(
    encounter: StructuredEncounter,
    context: com.chartlite.app.model.PatientContext?
): StructuredEncounter {
    if (context == null || context.knownAllergies.isEmpty()) return encounter
    val mergedAllergies = (encounter.allergies + context.knownAllergies).distinct()
    return if (mergedAllergies.size == encounter.allergies.size) encounter
    else encounter.copy(allergies = mergedAllergies)
}
