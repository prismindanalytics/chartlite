#include <jni.h>
#include <android/log.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <mutex>
#include <unistd.h>

#include "llama.h"
#include "ggml.h"
#include "ggml-cpu.h"

#define TAG "LlamaCppBench"
#define LOGi(...) __android_log_print(ANDROID_LOG_INFO,  TAG, __VA_ARGS__)
#define LOGe(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

static llama_model  *g_model  = nullptr;
static llama_context *g_ctx   = nullptr;
static const llama_vocab *g_vocab = nullptr;
static ggml_threadpool *g_threadpool = nullptr;
static ggml_threadpool *g_threadpool_batch = nullptr;
static llama_batch g_batch = {};
static bool g_batch_initialized = false;
static bool g_backend_initialized = false;
static std::mutex g_mutex;

// ── Metrics from last generation ──
static double g_last_load_ms     = 0;
static double g_last_prefill_ms  = 0;
static double g_last_decode_ms   = 0;
static int    g_last_prompt_tokens  = 0;
static int    g_last_decode_tokens  = 0;

namespace {

struct CpuProfile {
    int total_cores = 1;
    int perf_cores = 1;
    long max_freq_khz = 0;
    long little_max_freq_khz = 0;
    bool symmetric_soc = true;
    std::vector<int> perf_core_ids;
};

struct RuntimeTuning {
    double total_ram_gb = 0.0;
    bool low_ram_device = false;
    bool ultra_low_ram = false;
    int n_ctx = 2048;
    int n_batch = 512;
    int n_ubatch = 256;
    int decode_threads = 2;
    int batch_threads = 4;
    bool pin_to_perf_cores = false;
    CpuProfile cpu_profile;
    std::vector<int> core_ids;
};

static RuntimeTuning g_runtime;

static CpuProfile detect_cpu_profile() {
    CpuProfile profile;
    profile.total_cores = std::max(1, (int)sysconf(_SC_NPROCESSORS_ONLN));

    std::vector<long> freqs(profile.total_cores, 0);
    for (int i = 0; i < profile.total_cores; ++i) {
        char path[128];
        std::snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_max_freq", i);
        FILE *f = std::fopen(path, "r");
        if (!f) {
            continue;
        }
        long freq = 0;
        if (std::fscanf(f, "%ld", &freq) == 1 && freq > 0) {
            freqs[i] = freq;
            profile.max_freq_khz = std::max(profile.max_freq_khz, freq);
        }
        std::fclose(f);
    }

    if (profile.max_freq_khz <= 0) {
        profile.perf_cores = profile.total_cores;
        for (int i = 0; i < profile.total_cores; ++i) {
            profile.perf_core_ids.push_back(i);
        }
        return profile;
    }

    const long perf_threshold = std::max(1L, (long)std::lround(profile.max_freq_khz * 0.8));
    for (int i = 0; i < profile.total_cores; ++i) {
        if (freqs[i] >= perf_threshold) {
            profile.perf_core_ids.push_back(i);
        } else if (freqs[i] > profile.little_max_freq_khz) {
            profile.little_max_freq_khz = freqs[i];
        }
    }

    if (profile.perf_core_ids.empty()) {
        for (int i = 0; i < profile.total_cores; ++i) {
            if (freqs[i] == profile.max_freq_khz || freqs[i] == 0) {
                profile.perf_core_ids.push_back(i);
            }
        }
    }

    if (profile.perf_core_ids.empty()) {
        for (int i = 0; i < profile.total_cores; ++i) {
            profile.perf_core_ids.push_back(i);
        }
    }

    profile.perf_cores = std::max(1, (int)profile.perf_core_ids.size());
    profile.symmetric_soc = profile.perf_cores == profile.total_cores || profile.little_max_freq_khz == 0;
    return profile;
}

static double detect_total_ram_gb() {
    const long page_count = sysconf(_SC_PHYS_PAGES);
    const long page_size = sysconf(_SC_PAGE_SIZE);
    if (page_count <= 0 || page_size <= 0) {
        return 0.0;
    }
    return (double)page_count * (double)page_size / (1024.0 * 1024.0 * 1024.0);
}

static RuntimeTuning choose_runtime_tuning(int requested_threads) {
    RuntimeTuning tuning;
    tuning.total_ram_gb = detect_total_ram_gb();
    tuning.ultra_low_ram = tuning.total_ram_gb > 0.0 && tuning.total_ram_gb <= 3.0;
    tuning.low_ram_device = tuning.total_ram_gb > 0.0 && tuning.total_ram_gb <= 3.5;
    tuning.cpu_profile = detect_cpu_profile();

    if (tuning.ultra_low_ram) {
        tuning.n_ctx = 1280;
        tuning.n_batch = 256;
        tuning.n_ubatch = 128;
    } else if (tuning.low_ram_device) {
        tuning.n_ctx = 1536;
        tuning.n_batch = 384;
        tuning.n_ubatch = 192;
    } else {
        tuning.n_ctx = 2048;
        tuning.n_batch = 512;
        tuning.n_ubatch = 256;
    }

    const bool asymmetric = !tuning.cpu_profile.symmetric_soc && !tuning.cpu_profile.perf_core_ids.empty();
    if (asymmetric) {
        tuning.batch_threads = std::max(1, std::min(
            tuning.cpu_profile.perf_cores,
            tuning.ultra_low_ram ? 2 : (tuning.low_ram_device ? 3 : 4)
        ));
        tuning.decode_threads = std::max(1, std::min(
            tuning.batch_threads,
            tuning.ultra_low_ram ? 2 : 3
        ));
        const int pinned_cores = std::max(tuning.batch_threads, tuning.decode_threads);
        tuning.core_ids.assign(
            tuning.cpu_profile.perf_core_ids.begin(),
            tuning.cpu_profile.perf_core_ids.begin() + std::min((int)tuning.cpu_profile.perf_core_ids.size(), pinned_cores)
        );
        tuning.pin_to_perf_cores = !tuning.core_ids.empty();
    } else {
        const int total = std::max(1, tuning.cpu_profile.total_cores);
        tuning.batch_threads = std::max(1, std::min(total, tuning.ultra_low_ram ? 3 : 4));
        tuning.decode_threads = std::max(1, std::min(total, tuning.ultra_low_ram ? 2 : (tuning.low_ram_device ? 2 : 3)));
    }

    if (requested_threads > 0) {
        tuning.batch_threads = std::max(1, std::min(tuning.batch_threads, requested_threads));
        tuning.decode_threads = std::max(1, std::min(tuning.decode_threads, requested_threads));
    }

    tuning.decode_threads = std::min(tuning.decode_threads, tuning.batch_threads);
    tuning.n_batch = std::min(tuning.n_batch, tuning.n_ctx);
    tuning.n_ubatch = std::min(tuning.n_ubatch, tuning.n_batch);

    if (!tuning.core_ids.empty() && (int)tuning.core_ids.size() > tuning.batch_threads) {
        tuning.core_ids.resize(tuning.batch_threads);
    }

    return tuning;
}

static void ensure_backend_initialized() {
    if (g_backend_initialized) {
        return;
    }
    llama_backend_init();
    g_backend_initialized = true;
    LOGi("llama backend initialized: %s", llama_print_system_info());
}

static void release_batch() {
    if (!g_batch_initialized) {
        return;
    }
    llama_batch_free(g_batch);
    g_batch = {};
    g_batch_initialized = false;
}

static void release_threadpools() {
    if (g_ctx) {
        llama_detach_threadpool(g_ctx);
    }
    if (g_threadpool_batch) {
        ggml_threadpool_free(g_threadpool_batch);
        g_threadpool_batch = nullptr;
    }
    if (g_threadpool) {
        ggml_threadpool_free(g_threadpool);
        g_threadpool = nullptr;
    }
}

static void release_model_state() {
    release_threadpools();
    release_batch();
    if (g_ctx) {
        llama_free(g_ctx);
        g_ctx = nullptr;
    }
    if (g_model) {
        llama_model_free(g_model);
        g_model = nullptr;
    }
    g_vocab = nullptr;
}

static void batch_clear(llama_batch &batch) {
    batch.n_tokens = 0;
}

static void batch_add(llama_batch &batch, llama_token token, llama_pos pos, bool request_logits) {
    const int i = batch.n_tokens++;
    batch.token[i] = token;
    batch.pos[i] = pos;
    batch.n_seq_id[i] = 1;
    batch.seq_id[i][0] = 0;
    batch.logits[i] = request_logits ? 1 : 0;
}

static void apply_core_mask(ggml_threadpool_params &params, const std::vector<int> &core_ids) {
    std::memset(params.cpumask, 0, sizeof(params.cpumask));
    for (int id : core_ids) {
        if (id >= 0 && id < GGML_MAX_N_THREADS) {
            params.cpumask[id] = true;
        }
    }
}

static bool attach_threadpools(const RuntimeTuning &tuning) {
    auto tpp = ggml_threadpool_params_default(tuning.decode_threads);
    auto tpp_batch = ggml_threadpool_params_default(tuning.batch_threads);

    tpp.poll = tuning.low_ram_device ? 40 : 50;
    tpp_batch.poll = tuning.low_ram_device ? 30 : 50;

    if (tuning.pin_to_perf_cores && !tuning.core_ids.empty()) {
        apply_core_mask(tpp, tuning.core_ids);
        apply_core_mask(tpp_batch, tuning.core_ids);
        tpp.strict_cpu = true;
        tpp_batch.strict_cpu = true;
    }

    const bool same_params = ggml_threadpool_params_match(&tpp, &tpp_batch);
    if (!same_params) {
        g_threadpool_batch = ggml_threadpool_new(&tpp_batch);
        if (!g_threadpool_batch) {
            LOGw("Batch threadpool creation failed, falling back to default ggml pool");
            return false;
        }
        tpp.paused = true;
    }

    g_threadpool = ggml_threadpool_new(&tpp);
    if (!g_threadpool) {
        LOGw("Decode threadpool creation failed, falling back to default ggml pool");
        if (g_threadpool_batch) {
            ggml_threadpool_free(g_threadpool_batch);
            g_threadpool_batch = nullptr;
        }
        return false;
    }

    llama_attach_threadpool(g_ctx, g_threadpool, same_params ? nullptr : g_threadpool_batch);
    llama_set_n_threads(g_ctx, tuning.decode_threads, tuning.batch_threads);
    return true;
}

static bool init_batch(int n_tokens_alloc) {
    release_batch();
    g_batch = llama_batch_init(std::max(1, n_tokens_alloc), 0, 1);
    g_batch_initialized = g_batch.token != nullptr;
    if (!g_batch_initialized) {
        LOGe("Failed to allocate llama batch");
    }
    return g_batch_initialized;
}

static int decode_prompt(const std::vector<llama_token> &tokens) {
    int processed = 0;
    while (processed < (int)tokens.size()) {
        batch_clear(g_batch);
        const int chunk = std::min(g_runtime.n_batch, (int)tokens.size() - processed);
        for (int i = 0; i < chunk; ++i) {
            const bool request_logits = (processed + i) == (int)tokens.size() - 1;
            batch_add(g_batch, tokens[processed + i], processed + i, request_logits);
        }
        const int decode_status = llama_decode(g_ctx, g_batch);
        if (decode_status != 0) {
            return decode_status;
        }
        processed += chunk;
    }
    return 0;
}

} // namespace

extern "C" {

JNIEXPORT jboolean JNICALL
Java_com_chartlite_benchmark_engine_LlamaCppBridge_nativeLoadModel(
    JNIEnv *env, jobject, jstring jModelPath, jint nThreads
) {
    std::lock_guard<std::mutex> lock(g_mutex);
    ensure_backend_initialized();

    release_model_state();

    const char *path = env->GetStringUTFChars(jModelPath, nullptr);
    LOGi("Loading GGUF model: %s (threads=%d)", path, nThreads);

    auto t0 = ggml_time_us();

    // Load model
    auto mparams = llama_model_default_params();
    mparams.n_gpu_layers = 0; // CPU only
    mparams.use_mmap = true;
    mparams.use_direct_io = false;
    mparams.use_mlock = false;
    mparams.check_tensors = false;
    mparams.use_extra_bufts = true;
    g_model = llama_model_load_from_file(path, mparams);
    env->ReleaseStringUTFChars(jModelPath, path);

    if (!g_model) {
        LOGe("Failed to load model");
        return JNI_FALSE;
    }

    g_vocab = llama_model_get_vocab(g_model);
    g_runtime = choose_runtime_tuning(nThreads);

    // Create context
    auto cparams = llama_context_default_params();
    cparams.n_ctx = g_runtime.n_ctx;
    cparams.n_batch = g_runtime.n_batch;
    cparams.n_ubatch = g_runtime.n_ubatch;
    cparams.n_threads = g_runtime.decode_threads;
    cparams.n_threads_batch = g_runtime.batch_threads;
    cparams.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_AUTO;
    cparams.type_k = GGML_TYPE_F16;
    cparams.type_v = GGML_TYPE_F16;

    g_ctx = llama_init_from_model(g_model, cparams);
    if (!g_ctx) {
        LOGe("Failed to create context");
        llama_model_free(g_model);
        g_model = nullptr;
        g_vocab = nullptr;
        return JNI_FALSE;
    }

    if (!attach_threadpools(g_runtime)) {
        llama_set_n_threads(g_ctx, g_runtime.decode_threads, g_runtime.batch_threads);
    }

    if (!init_batch(g_runtime.n_batch)) {
        release_model_state();
        return JNI_FALSE;
    }

    g_last_load_ms = (ggml_time_us() - t0) / 1000.0;
    LOGi(
        "Model loaded in %.0f ms (ram=%.1fGB, n_ctx=%d, n_batch=%d/%d, threads=%d/%d, perf_cores=%d, pinned=%d)",
        g_last_load_ms,
        g_runtime.total_ram_gb,
        g_runtime.n_ctx,
        g_runtime.n_batch,
        g_runtime.n_ubatch,
        g_runtime.decode_threads,
        g_runtime.batch_threads,
        g_runtime.cpu_profile.perf_cores,
        g_runtime.pin_to_perf_cores ? 1 : 0
    );
    return JNI_TRUE;
}

JNIEXPORT jstring JNICALL
Java_com_chartlite_benchmark_engine_LlamaCppBridge_nativeGenerate(
    JNIEnv *env, jobject,
    jstring jPrompt, jint maxTokens, jfloat temperature
) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (!g_ctx || !g_model || !g_vocab) {
        LOGe("Model not loaded");
        return nullptr;
    }

    const char *promptRaw = env->GetStringUTFChars(jPrompt, nullptr);
    std::string prompt(promptRaw);
    env->ReleaseStringUTFChars(jPrompt, promptRaw);

    // Tokenize
    std::vector<llama_token> tokens(prompt.size() + 32);
    int n_tokens = llama_tokenize(g_vocab, prompt.c_str(), prompt.size(),
                                  tokens.data(), tokens.size(), true, true);
    if (n_tokens < 0) {
        tokens.resize(-n_tokens);
        n_tokens = llama_tokenize(g_vocab, prompt.c_str(), prompt.size(),
                                  tokens.data(), tokens.size(), true, true);
    }
    tokens.resize(n_tokens);
    g_last_prompt_tokens = n_tokens;

    LOGi("Prompt: %d tokens, generating up to %d tokens", n_tokens, maxTokens);

    // Clear KV cache
    llama_memory_clear(llama_get_memory(g_ctx), false);

    const int ctx_limit = (int)llama_n_ctx(g_ctx);
    const int max_decode_tokens = std::max(0, std::min(maxTokens, ctx_limit - n_tokens));
    if (max_decode_tokens <= 0) {
        LOGe("No context budget left: prompt=%d, n_ctx=%d", n_tokens, ctx_limit);
        return nullptr;
    }

    // Prefill
    auto t_prefill = ggml_time_us();
    if (decode_prompt(tokens) != 0) {
        LOGe("Prefill decode failed");
        return nullptr;
    }
    g_last_prefill_ms = (ggml_time_us() - t_prefill) / 1000.0;

    // Decode
    auto t_decode = ggml_time_us();
    std::string result;
    result.reserve(4096);

    auto *smpl = llama_sampler_chain_init(llama_sampler_chain_default_params());
    llama_sampler_chain_add(smpl, llama_sampler_init_temp(temperature));
    llama_sampler_chain_add(smpl, llama_sampler_init_dist(42));

    int n_decoded = 0;
    int cur_pos = n_tokens;
    for (int i = 0; i < max_decode_tokens; i++) {
        llama_token new_token = llama_sampler_sample(smpl, g_ctx, -1);

        if (llama_vocab_is_eog(g_vocab, new_token)) break;

        // Convert token to text
        char buf[256];
        int len = llama_token_to_piece(g_vocab, new_token, buf, sizeof(buf), 0, true);
        if (len > 0) {
            result.append(buf, len);
        }

        batch_clear(g_batch);
        batch_add(g_batch, new_token, cur_pos, true);
        if (llama_decode(g_ctx, g_batch) != 0) {
            LOGe("Decode failed at token %d", i);
            break;
        }
        cur_pos++;
        n_decoded++;
    }

    llama_sampler_free(smpl);

    g_last_decode_ms = (ggml_time_us() - t_decode) / 1000.0;
    g_last_decode_tokens = n_decoded;

    double prefill_tps = g_last_prompt_tokens > 0 && g_last_prefill_ms > 0
        ? g_last_prompt_tokens / (g_last_prefill_ms / 1000.0) : 0;
    double decode_tps = n_decoded > 0 && g_last_decode_ms > 0
        ? n_decoded / (g_last_decode_ms / 1000.0) : 0;

    LOGi("Done: prefill=%d tok (%.1f tok/s, %.0fms), decode=%d tok (%.1f tok/s, %.0fms)",
         g_last_prompt_tokens, prefill_tps, g_last_prefill_ms,
         n_decoded, decode_tps, g_last_decode_ms);

    if (result.empty()) return nullptr;
    return env->NewStringUTF(result.c_str());
}

JNIEXPORT jdoubleArray JNICALL
Java_com_chartlite_benchmark_engine_LlamaCppBridge_nativeGetMetrics(JNIEnv *env, jobject) {
    // Returns: [load_ms, prefill_ms, decode_ms, prompt_tokens, decode_tokens]
    jdoubleArray arr = env->NewDoubleArray(5);
    double metrics[5] = {
        g_last_load_ms,
        g_last_prefill_ms,
        g_last_decode_ms,
        (double)g_last_prompt_tokens,
        (double)g_last_decode_tokens
    };
    env->SetDoubleArrayRegion(arr, 0, 5, metrics);
    return arr;
}

JNIEXPORT void JNICALL
Java_com_chartlite_benchmark_engine_LlamaCppBridge_nativeUnload(JNIEnv *, jobject) {
    std::lock_guard<std::mutex> lock(g_mutex);
    release_model_state();
    LOGi("Model unloaded");
}

} // extern "C"
