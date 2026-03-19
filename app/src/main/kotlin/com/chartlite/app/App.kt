package com.chartlite.app

import android.app.Application
import android.util.Log
import com.chartlite.app.asr.ASREngine
import com.chartlite.app.auth.AuditLogger
import com.chartlite.app.auth.JoinCodeManager
import com.chartlite.app.auth.SessionManager
import com.chartlite.app.cdss.StaticCDSS
import com.chartlite.app.config.AppConfig
import com.chartlite.app.config.CountryConfigLoader
import com.chartlite.app.database.AppDatabase
import com.chartlite.app.database.EncounterRepository
import com.chartlite.app.database.PatientRepository
import com.chartlite.app.database.VisitRepository
import com.chartlite.app.agent.ClinicalDataService
import com.chartlite.app.database.repository.AppointmentRepository
import com.chartlite.app.database.repository.FPRepository
import com.chartlite.app.database.repository.GrowthRepository
import com.chartlite.app.database.repository.ImmunizationRepository
import com.chartlite.app.database.repository.LabOrderRepository
import com.chartlite.app.database.repository.ReferralRepository
import com.chartlite.app.database.repository.SmsLogRepository
import com.chartlite.app.database.repository.StockRepository
import com.chartlite.app.export.DataExporter
import com.chartlite.app.extraction.*
import com.chartlite.app.facilities.FacilityDirectory
import com.chartlite.app.model.Formulary
import com.chartlite.app.model.ICD10Index
import com.chartlite.app.protocols.ClinicalProtocolEngine
import com.chartlite.app.sms.AppointmentReminder
import com.chartlite.app.sms.DecodedEncounterV4
import com.chartlite.app.sms.SMSSender
import com.chartlite.app.sync.SyncEngine
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class App : Application() {

    /** Application-scoped coroutine scope — use for fire-and-forget work that must survive navigation. */
    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    /**
     * Transient holder for decoded SMS data during "Register from SMS" flow.
     * Set in SMSDecryptScreen → consumed in PatientRegistrationScreen after patient is saved.
     * Allows the full decoded health record (encounter, immunizations, growth, chronic conditions)
     * to be imported into the new patient's local DB as a synthetic baseline encounter.
     */
    @Volatile
    var pendingSmsImport: DecodedEncounterV4? = null

    lateinit var appConfig: AppConfig private set
    lateinit var database: AppDatabase private set
    lateinit var patientRepository: PatientRepository private set
    lateinit var encounterRepository: EncounterRepository private set
    lateinit var visitRepository: VisitRepository private set
    lateinit var asr: ASREngine private set
    lateinit var cdss: StaticCDSS private set
    lateinit var smsSender: SMSSender private set
    lateinit var dataExporter: DataExporter private set
    lateinit var syncEngine: SyncEngine private set
    lateinit var sessionManager: SessionManager private set
    lateinit var auditLogger: AuditLogger private set
    lateinit var joinCodeManager: JoinCodeManager private set
    lateinit var labOrderRepository: LabOrderRepository private set
    lateinit var appointmentRepository: AppointmentRepository private set
    lateinit var referralRepository: ReferralRepository private set
    lateinit var clinicalDataService: ClinicalDataService private set
    lateinit var stockRepository: StockRepository private set
    lateinit var immunizationRepository: ImmunizationRepository private set
    lateinit var fpRepository: FPRepository private set
    lateinit var growthRepository: GrowthRepository private set
    lateinit var protocolEngine: ClinicalProtocolEngine private set
    lateinit var facilityDirectory: FacilityDirectory private set
    lateinit var smsLogRepository: SmsLogRepository private set
    lateinit var appointmentReminder: AppointmentReminder private set
    lateinit var playIntegrityManager: com.chartlite.app.auth.PlayIntegrityManager private set

    private lateinit var configLoader: CountryConfigLoader
    private val llmInitLock = Any()
    @Volatile private var llmModelManagerBacking: LlmModelManager? = null
    private val extractionInitLock = Any()
    @Volatile private var extractionServicesBacking: ExtractionServices? = null

    val llmModelManager: LlmModelManager
        get() = llmModelManagerBacking ?: synchronized(llmInitLock) {
            llmModelManagerBacking ?: createLlmModelManager().also { llmModelManagerBacking = it }
        }

    val vectorStore: ClinicalVectorStore
        get() = getOrCreateExtractionServices().vectorStore

    val clinicalExtractor: ClinicalExtractor
        get() = getOrCreateExtractionServices().clinicalExtractor

    val extractionOrchestrator: ExtractionOrchestrator
        get() = getOrCreateExtractionServices().extractionOrchestrator

    val extractionQueue: ExtractionQueue
        get() = getOrCreateExtractionServices().extractionQueue

    val extractionQueueRepository: ExtractionQueueRepository
        get() = getOrCreateExtractionServices().extractionQueueRepository

    val promptBuilder: ExtractionPromptBuilder
        get() = getOrCreateExtractionServices().promptBuilder

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "App.onCreate() starting")

        // Load SQLCipher native library before any database operations
        try {
            System.loadLibrary("sqlcipher")
            Log.d(TAG, "SQLCipher native library loaded")
        } catch (e: UnsatisfiedLinkError) {
            Log.e(TAG, "Failed to load sqlcipher native lib", e)
        }

        appConfig = AppConfig(this)
        configLoader = CountryConfigLoader(this)
        Log.d(TAG, "Config loaded, initializing database...")

        // Initialize database with a device-derived passphrase
        val passphrase = getOrCreatePassphrase()
        Log.d(TAG, "Passphrase ready, building Room database...")
        database = AppDatabase.getInstance(this, passphrase)
        Log.d(TAG, "Database initialized")

        patientRepository = PatientRepository(database.patientDao())
        encounterRepository = EncounterRepository(database.encounterDao())
        visitRepository = VisitRepository(database.visitDao())

        // Initialize auth system (SessionManager gets auditLogDao for auth event logging)
        sessionManager = SessionManager(appConfig, database.userDao(), database.auditLogDao())
        auditLogger = AuditLogger(database.auditLogDao(), sessionManager)
        joinCodeManager = JoinCodeManager(appConfig)

        // Wire audit logger into repositories that need it
        encounterRepository.auditLogger = auditLogger

        // Initialize Phase 2 repositories
        labOrderRepository = LabOrderRepository(database.labOrderDao())
        appointmentRepository = AppointmentRepository(database.appointmentDao(), database.patientDao())
        referralRepository = ReferralRepository(database.referralDao())

        // Initialize Phase 3+4 repositories
        smsLogRepository = SmsLogRepository(database.smsLogDao())
        stockRepository = StockRepository(database.stockDao())
        immunizationRepository = ImmunizationRepository(database.immunizationDao())
        fpRepository = FPRepository(database.fpVisitDao())
        growthRepository = GrowthRepository(database.growthDao())

        // Initialize AI agent data service (permission-gated, audit-logged)
        clinicalDataService = ClinicalDataService(
            patientRepository = patientRepository,
            encounterRepository = encounterRepository,
            labOrderRepository = labOrderRepository,
            appointmentRepository = appointmentRepository,
            referralRepository = referralRepository,
            auditLogger = auditLogger
        )

        // Initialize proxy auth manager (Play Integrity + non-GMS device enrollment)
        playIntegrityManager = com.chartlite.app.auth.PlayIntegrityManager(
            context = this,
            deviceId = appConfig.deviceId,
            deviceEnrollmentCodeProvider = { appConfig.chartliteEnrollmentCode },
            onDeviceEnrollmentSuccess = {
                // Keep enrollment code in AppConfig — needed if the device Keystore key is ever
                // regenerated (app reinstall, OS wipe) so the device can re-enroll automatically.
                // One-time enforcement is handled server-side per device_id.
            }
        )

        asr = ASREngine(this)
        // Restore ASR mode from saved preference
        asr.mode = when (appConfig.asrMode) {
            "onnx" -> ASREngine.Mode.ONNX_OFFLINE
            "cloud" -> ASREngine.Mode.CLOUD_ASR
            else -> ASREngine.Mode.GOOGLE_ONLINE
        }
        // Wire cloud ASR manager (lightweight — no resources allocated until recording starts)
        asr.cloudASRManager = com.chartlite.app.asr.cloud.CloudASRManager(this, appConfig, playIntegrityManager)
        smsSender = SMSSender(this, appConfig)
        dataExporter = DataExporter(this, encounterRepository)
        syncEngine = SyncEngine(this, patientRepository, encounterRepository, visitRepository, appConfig, auditLogger)

        // Initialize CDSS
        cdss = StaticCDSS(this)
        cdss.loadRules()

        // Initialize Clinical Protocol Engine
        protocolEngine = ClinicalProtocolEngine(this)
        protocolEngine.loadProtocols()

        // Initialize Facility Directory
        facilityDirectory = FacilityDirectory(this)

        // Initialize Appointment Reminder system
        appointmentReminder = AppointmentReminder(
            smsSender = smsSender,
            appointmentRepository = appointmentRepository,
            patientRepository = patientRepository,
            appConfig = appConfig,
            auditLogger = auditLogger,
            smsLogRepository = smsLogRepository
        )

        // Apply lightweight country presentation settings eagerly; the extraction
        // pipeline is deferred so first draw is not blocked by vector indexing.
        applyCountryPresentationConfig()
        facilityDirectory.loadFacilities(appConfig.countryCode)
        scheduleDeferredExtractionWarmup()

        // ASR model loading is deferred to first use (ASREngine.startListening)
        // to avoid consuming ~200MB of memory at startup on low-RAM devices.
        // Only refresh download state so Settings shows correct status.
        asr.modelDownloader.refreshState()

        // Start continuous sync service if multi-station mode is active
        if (com.chartlite.app.sync.ContinuousSyncService.shouldRun(this)) {
            com.chartlite.app.sync.ContinuousSyncService.start(this)
            Log.d(TAG, "Started continuous sync service")
        }
    }

    fun loadCountryData(deferExtraction: Boolean = false) {
        applyCountryPresentationConfig()
        facilityDirectory.loadFacilities(appConfig.countryCode)
        if (deferExtraction) {
            // Defer heavy extraction pipeline build to avoid OOM on low-RAM devices
            // during setup completion when memory is already constrained.
            scheduleDeferredExtractionWarmup()
        } else {
            getOrCreateExtractionServices(forceReload = true)
        }
    }

    /** Rebuild the extraction pipeline (e.g., after changing AI mode or cloud key mode). */
    fun rebuildExtractionPipeline() {
        getOrCreateExtractionServices(forceReload = true)
    }

    private fun applyCountryPresentationConfig() {
        try {
            val configJson = assets.open("config/country_${appConfig.countryCode}.json")
                .bufferedReader().use { it.readText() }
            val countryConfig = com.google.gson.JsonParser.parseString(configJson).asJsonObject
            appConfig.countryDateFormat = countryConfig.get("dateFormat")?.asString ?: "dd/MM/yyyy"
            appConfig.countryNationalIdLabel = countryConfig.get("nationalIdLabel")?.asString ?: "National ID"
        } catch (_: Exception) {
            // Keep defaults
        }
    }

    private fun createLlmModelManager(): LlmModelManager {
        val manager = LlmModelManager(this)
        val savedTier = appConfig.llmTierOverride
        if (savedTier.isNotBlank()) {
            try {
                manager.overrideTier = LlmModelManager.ModelTier.valueOf(savedTier)
            } catch (_: IllegalArgumentException) {
                appConfig.llmTierOverride = ""
            }
        }
        manager.refreshState()
        return manager
    }

    private fun getOrCreateExtractionServices(forceReload: Boolean = false): ExtractionServices {
        if (!forceReload) {
            extractionServicesBacking?.let { return it }
        }

        return synchronized(extractionInitLock) {
            if (!forceReload) {
                extractionServicesBacking?.let { return@synchronized it }
            }
            val previous = extractionServicesBacking
            buildExtractionServices().also { fresh ->
                extractionServicesBacking = fresh
                previous?.close()
            }
        }
    }

    private fun buildExtractionServices(): ExtractionServices {
        val formulary = try {
            configLoader.loadFormulary("formulary/${appConfig.countryCode}_formulary.json")
        } catch (_: Exception) {
            Formulary("1.0", appConfig.countryCode, emptyList())
        }

        val icd10 = try {
            configLoader.loadICD10("icd10/phc_top300.json")
        } catch (_: Exception) {
            ICD10Index("1.0", emptyList())
        }

        val vectorStore = ClinicalVectorStore(icd10, formulary)
        vectorStore.buildIndex()

        val clinicalExtractor = ClinicalExtractor(formulary, icd10, vectorStore)
        val extractionQueueRepository = ExtractionQueueRepository(database.extractionQueueDao())

        val promptBuilder = ExtractionPromptBuilder(icd10, formulary, vectorStore)
        val responseParser = LlmResponseParser(icd10, formulary)
        val strategies = mutableListOf<ExtractionStrategy>()

        // Build cloud extraction strategy based on selected model
        fun addCloudStrategy() {
            val model = appConfig.cloudNotesModel
            when {
                model.startsWith("claude") -> {
                    val authConfig = if (appConfig.cloudKeyMode == "chartlite") {
                        ClaudeExtractionStrategy.AuthConfig.Proxied { playIntegrityManager.getAuthHeaders() }
                    } else {
                        ClaudeExtractionStrategy.AuthConfig.Direct { appConfig.claudeApiKey }
                    }
                    strategies.add(ClaudeExtractionStrategy(this, promptBuilder, responseParser, authConfig))
                }
                model.startsWith("gemini") -> {
                    val authConfig = if (appConfig.cloudKeyMode == "chartlite") {
                        GeminiExtractionStrategy.AuthConfig.Proxied { playIntegrityManager.getAuthHeaders() }
                    } else {
                        GeminiExtractionStrategy.AuthConfig.Direct { appConfig.geminiApiKey }
                    }
                    strategies.add(GeminiExtractionStrategy(this, promptBuilder, responseParser, authConfig))
                }
                model.startsWith("gpt") -> {
                    val authConfig = if (appConfig.cloudKeyMode == "chartlite") {
                        OpenAIExtractionStrategy.AuthConfig.Proxied { playIntegrityManager.getAuthHeaders() }
                    } else {
                        OpenAIExtractionStrategy.AuthConfig.Direct { appConfig.openaiApiKey }
                    }
                    strategies.add(OpenAIExtractionStrategy(this, promptBuilder, responseParser, authConfig, model))
                }
                else -> {
                    val authConfig = if (appConfig.cloudKeyMode == "chartlite") {
                        ClaudeExtractionStrategy.AuthConfig.Proxied { playIntegrityManager.getAuthHeaders() }
                    } else {
                        ClaudeExtractionStrategy.AuthConfig.Direct { appConfig.claudeApiKey }
                    }
                    strategies.add(ClaudeExtractionStrategy(this, promptBuilder, responseParser, authConfig))
                }
            }
        }

        when (appConfig.aiMode) {
            "cloud" -> addCloudStrategy()
            "on_device" -> {
                strategies.add(QwenExtractionStrategy(llmModelManager, promptBuilder, responseParser))
            }
            else -> {
                addCloudStrategy()
                strategies.add(QwenExtractionStrategy(llmModelManager, promptBuilder, responseParser))
            }
        }

        strategies.add(RegexExtractionStrategy(clinicalExtractor))
        val transcriptValidator = TranscriptValidator()
        val vitalsExtractor = VitalsExtractor()

        val extractionOrchestrator = ExtractionOrchestrator(
            strategies,
            transcriptValidator = transcriptValidator,
            vitalsExtractor = vitalsExtractor
        )
        Log.d(
            "App",
            "Extraction pipeline rebuilt for aiMode=${appConfig.aiMode}: " +
                strategies.joinToString(" -> ") { it.name }
        )

        val extractionQueue = ExtractionQueue(
            extractionOrchestrator,
            extractionQueueRepository,
            appScope,
            { llmModelManagerBacking?.cancelInference() }
        )

        return ExtractionServices(
            vectorStore = vectorStore,
            clinicalExtractor = clinicalExtractor,
            extractionOrchestrator = extractionOrchestrator,
            extractionQueue = extractionQueue,
            extractionQueueRepository = extractionQueueRepository,
            promptBuilder = promptBuilder
        )
    }

    private fun scheduleDeferredExtractionWarmup() {
        appScope.launch(Dispatchers.Default) {
            delay(DEFERRED_EXTRACTION_WARMUP_MS)
            runCatching { getOrCreateExtractionServices() }
                .onFailure { Log.w(TAG, "Deferred extraction warm-up failed", it) }
        }
    }

    private fun getOrCreatePassphrase(): ByteArray {
        // Use EncryptedSharedPreferences to store the random DB passphrase securely
        val masterKey = androidx.security.crypto.MasterKey.Builder(this)
            .setKeyScheme(androidx.security.crypto.MasterKey.KeyScheme.AES256_GCM)
            .build()
        val prefs = androidx.security.crypto.EncryptedSharedPreferences.create(
            this,
            "db_key_secure",
            masterKey,
            androidx.security.crypto.EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            androidx.security.crypto.EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )

        // Migrate from plain SharedPreferences if needed (one-time upgrade)
        val plainPrefs = getSharedPreferences("db_key", MODE_PRIVATE)
        val plainPassphrase = plainPrefs.getString("passphrase", null)
        if (plainPassphrase != null) {
            prefs.edit().putString("passphrase", plainPassphrase).apply()
            plainPrefs.edit().clear().apply()
        }

        val existing = prefs.getString("passphrase", null)
        if (existing != null) {
            return existing.toByteArray(Charsets.UTF_8)
        }
        val newPassphrase = java.util.UUID.randomUUID().toString()
        prefs.edit().putString("passphrase", newPassphrase).apply()
        return newPassphrase.toByteArray(Charsets.UTF_8)
    }

    private data class ExtractionServices(
        val vectorStore: ClinicalVectorStore,
        val clinicalExtractor: ClinicalExtractor,
        val extractionOrchestrator: ExtractionOrchestrator,
        val extractionQueue: ExtractionQueue,
        val extractionQueueRepository: ExtractionQueueRepository,
        val promptBuilder: ExtractionPromptBuilder
    ) {
        fun close() {
            extractionQueue.close()
        }
    }

    companion object {
        private const val TAG = "App"
        private const val DEFERRED_EXTRACTION_WARMUP_MS = 1_500L
    }
}
