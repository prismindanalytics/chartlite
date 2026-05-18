#include "chartlite_llama_backend.h"

#include <android/log.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <unistd.h>
#include <vector>

#if defined(CHARTLITE_LLAMA_AVAILABLE)
#include "llama.h"
#include "ggml.h"
#include "ggml-cpu.h"
#endif

#define TAG "ChartLiteLLama"
#define LOGi(...) __android_log_print(ANDROID_LOG_INFO,  TAG, __VA_ARGS__)
#define LOGw(...) __android_log_print(ANDROID_LOG_WARN,  TAG, __VA_ARGS__)
#define LOGe(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

namespace chartlite::llama_backend {

#if defined(CHARTLITE_LLAMA_AVAILABLE)

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

static llama_model* g_model = nullptr;
static llama_context* g_ctx = nullptr;
static const llama_vocab* g_vocab = nullptr;
static ggml_threadpool* g_threadpool = nullptr;
static ggml_threadpool* g_threadpool_batch = nullptr;
static llama_batch g_batch = {};
static bool g_batch_initialized = false;
static bool g_backend_initialized = false;
static std::mutex g_mutex;
static std::atomic<bool> g_cancel_generation(false);

static RuntimeTuning g_runtime;
static float g_temperature = 0.1f;
static int g_max_tokens = 256;
static float g_top_p = 0.95f;
static int g_top_k = 40;
static float g_repeat_penalty = 1.0f;

static CpuProfile detect_cpu_profile() {
    CpuProfile profile;
    profile.total_cores = std::max(1, (int)sysconf(_SC_NPROCESSORS_ONLN));

    std::vector<long> freqs(profile.total_cores, 0);
    for (int i = 0; i < profile.total_cores; ++i) {
        char path[128];
        std::snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_max_freq", i);
        FILE* f = std::fopen(path, "r");
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

static RuntimeTuning choose_runtime_tuning() {
    RuntimeTuning tuning;
    tuning.total_ram_gb = detect_total_ram_gb();
    tuning.ultra_low_ram = tuning.total_ram_gb > 0.0 && tuning.total_ram_gb <= 3.0;
    tuning.low_ram_device = tuning.total_ram_gb > 0.0 && tuning.total_ram_gb < 4.0;
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
            tuning.ultra_low_ram ? 2 : 4
        ));
        tuning.decode_threads = std::max(1, std::min(
            tuning.batch_threads,
            tuning.ultra_low_ram ? 2 : 3
        ));
        const int pinned = std::max(tuning.batch_threads, tuning.decode_threads);
        tuning.core_ids.assign(
            tuning.cpu_profile.perf_core_ids.begin(),
            tuning.cpu_profile.perf_core_ids.begin() + std::min((int)tuning.cpu_profile.perf_core_ids.size(), pinned)
        );
        tuning.pin_to_perf_cores = !tuning.core_ids.empty();
    } else {
        const int total = std::max(1, tuning.cpu_profile.total_cores);
        tuning.batch_threads = std::max(1, std::min(total, tuning.ultra_low_ram ? 3 : 4));
        tuning.decode_threads = std::max(1, std::min(total, tuning.ultra_low_ram ? 2 : 3));
    }

    tuning.decode_threads = std::min(tuning.decode_threads, tuning.batch_threads);
    tuning.n_batch = std::min(tuning.n_batch, tuning.n_ctx);
    tuning.n_ubatch = std::min(tuning.n_ubatch, tuning.n_batch);
    if (!tuning.core_ids.empty() && (int)tuning.core_ids.size() > tuning.batch_threads) {
        tuning.core_ids.resize(tuning.batch_threads);
    }
    return tuning;
}

static bool abort_callback(void*) {
    return g_cancel_generation.load();
}

static void ensure_backend_initialized() {
    if (g_backend_initialized) {
        return;
    }
    llama_backend_init();
    g_backend_initialized = true;
    LOGi("llama.cpp backend ready: %s", llama_print_system_info());
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

static void batch_clear(llama_batch& batch) {
    batch.n_tokens = 0;
}

static void batch_add(llama_batch& batch, llama_token token, llama_pos pos, bool request_logits) {
    const int i = batch.n_tokens++;
    batch.token[i] = token;
    batch.pos[i] = pos;
    batch.n_seq_id[i] = 1;
    batch.seq_id[i][0] = 0;
    batch.logits[i] = request_logits ? 1 : 0;
}

static void apply_core_mask(ggml_threadpool_params& params, const std::vector<int>& core_ids) {
    std::memset(params.cpumask, 0, sizeof(params.cpumask));
    for (int id : core_ids) {
        if (id >= 0 && id < GGML_MAX_N_THREADS) {
            params.cpumask[id] = true;
        }
    }
}

static void attach_threadpools() {
    auto tpp = ggml_threadpool_params_default(g_runtime.decode_threads);
    auto tpp_batch = ggml_threadpool_params_default(g_runtime.batch_threads);

    tpp.poll = g_runtime.low_ram_device ? 40 : 50;
    tpp_batch.poll = g_runtime.low_ram_device ? 30 : 50;

    if (g_runtime.pin_to_perf_cores && !g_runtime.core_ids.empty()) {
        apply_core_mask(tpp, g_runtime.core_ids);
        apply_core_mask(tpp_batch, g_runtime.core_ids);
        tpp.strict_cpu = true;
        tpp_batch.strict_cpu = true;
    }

    const bool same_params = ggml_threadpool_params_match(&tpp, &tpp_batch);
    if (!same_params) {
        g_threadpool_batch = ggml_threadpool_new(&tpp_batch);
        if (!g_threadpool_batch) {
            LOGw("Batch threadpool creation failed; using default ggml scheduling");
            return;
        }
        tpp.paused = true;
    }

    g_threadpool = ggml_threadpool_new(&tpp);
    if (!g_threadpool) {
        LOGw("Decode threadpool creation failed; using default ggml scheduling");
        if (g_threadpool_batch) {
            ggml_threadpool_free(g_threadpool_batch);
            g_threadpool_batch = nullptr;
        }
        return;
    }

    llama_attach_threadpool(g_ctx, g_threadpool, same_params ? nullptr : g_threadpool_batch);
    llama_set_n_threads(g_ctx, g_runtime.decode_threads, g_runtime.batch_threads);
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

static int decode_prompt(const std::vector<llama_token>& tokens) {
    int processed = 0;
    while (processed < (int)tokens.size()) {
        batch_clear(g_batch);
        const int chunk = std::min(g_runtime.n_batch, (int)tokens.size() - processed);
        for (int i = 0; i < chunk; ++i) {
            const bool request_logits = (processed + i) == (int)tokens.size() - 1;
            batch_add(g_batch, tokens[processed + i], processed + i, request_logits);
        }
        const int status = llama_decode(g_ctx, g_batch);
        if (status != 0) {
            return status;
        }
        processed += chunk;
    }
    return 0;
}

static std::string fallback_chatml_prompt(
    const std::string& system_prompt,
    const std::string& user_message
) {
    return "<|im_start|>system\n" + system_prompt +
        "<|im_end|>\n<|im_start|>user\n" + user_message +
        "<|im_end|>\n<|im_start|>assistant\n";
}

static std::string apply_chat_template_locked(
    const std::string& system_prompt,
    const std::string& user_message,
    bool /* enable_thinking */
) {
    if (!g_model) {
        return "";
    }

    const char* tmpl = llama_model_chat_template(g_model, nullptr);
    if (!tmpl || std::strlen(tmpl) == 0) {
        return fallback_chatml_prompt(system_prompt, user_message);
    }

    const llama_chat_message chat[] = {
        { "system", system_prompt.c_str() },
        { "user", user_message.c_str() },
    };

    const int32_t required = llama_chat_apply_template(tmpl, chat, 2, true, nullptr, 0);
    if (required <= 0) {
        LOGw("llama_chat_apply_template sizing failed; falling back to ChatML prompt");
        return fallback_chatml_prompt(system_prompt, user_message);
    }

    std::string rendered((size_t)required + 1, '\0');
    const int32_t written = llama_chat_apply_template(
        tmpl,
        chat,
        2,
        true,
        rendered.data(),
        (int32_t)rendered.size()
    );
    if (written <= 0) {
        LOGw("llama_chat_apply_template failed; falling back to ChatML prompt");
        return fallback_chatml_prompt(system_prompt, user_message);
    }

    rendered.resize((size_t)written);
    if (!rendered.empty() && rendered.back() == '\0') {
        rendered.pop_back();
    }
    return rendered;
}

static std::vector<llama_token> tokenize_prompt(const std::string& prompt) {
    std::vector<llama_token> tokens(prompt.size() + 32);
    int n_tokens = llama_tokenize(
        g_vocab,
        prompt.c_str(),
        prompt.size(),
        tokens.data(),
        tokens.size(),
        true,
        true
    );
    if (n_tokens < 0) {
        tokens.resize(-n_tokens);
        n_tokens = llama_tokenize(
            g_vocab,
            prompt.c_str(),
            prompt.size(),
            tokens.data(),
            tokens.size(),
            true,
            true
        );
    }
    if (n_tokens < 0) {
        return {};
    }
    tokens.resize(n_tokens);
    return tokens;
}

static std::string generate_locked(const std::string& prompt) {
    if (!g_ctx || !g_model || !g_vocab) {
        LOGe("generate called before llama backend was loaded");
        return "";
    }

    const std::vector<llama_token> tokens = tokenize_prompt(prompt);
    if (tokens.empty()) {
        LOGe("Prompt tokenization failed");
        return "";
    }

    g_cancel_generation.store(false);
    llama_memory_clear(llama_get_memory(g_ctx), false);

    const int ctx_limit = (int)llama_n_ctx(g_ctx);
    const int max_decode_tokens = std::max(0, std::min(g_max_tokens, ctx_limit - (int)tokens.size()));
    if (max_decode_tokens <= 0) {
        LOGe("Prompt consumes context budget: prompt=%d n_ctx=%d", (int)tokens.size(), ctx_limit);
        return "";
    }

    if (decode_prompt(tokens) != 0) {
        LOGe("Prompt prefill failed");
        return "";
    }

    auto* sampler = llama_sampler_chain_init(llama_sampler_chain_default_params());
    if (g_repeat_penalty > 1.001f) {
        llama_sampler_chain_add(sampler, llama_sampler_init_penalties(128, g_repeat_penalty, 0.0f, 0.0f));
    }
    if (g_top_k > 0) {
        llama_sampler_chain_add(sampler, llama_sampler_init_top_k(g_top_k));
    }
    if (g_top_p > 0.0f && g_top_p < 1.0f) {
        llama_sampler_chain_add(sampler, llama_sampler_init_top_p(g_top_p, 1));
    }
    if (g_temperature <= 0.0f) {
        llama_sampler_chain_add(sampler, llama_sampler_init_greedy());
    } else {
        llama_sampler_chain_add(sampler, llama_sampler_init_temp(g_temperature));
        llama_sampler_chain_add(sampler, llama_sampler_init_dist(42));
    }

    std::string result;
    result.reserve(4096);
    int cur_pos = (int)tokens.size();

    for (int i = 0; i < max_decode_tokens; ++i) {
        if (g_cancel_generation.load()) {
            break;
        }

        const llama_token new_token = llama_sampler_sample(sampler, g_ctx, -1);
        if (llama_vocab_is_eog(g_vocab, new_token)) {
            break;
        }

        char piece[256];
        const int piece_len = llama_token_to_piece(g_vocab, new_token, piece, sizeof(piece), 0, true);
        if (piece_len > 0) {
            result.append(piece, piece_len);
        }

        batch_clear(g_batch);
        batch_add(g_batch, new_token, cur_pos, true);
        const int status = llama_decode(g_ctx, g_batch);
        if (status == 2 && g_cancel_generation.load()) {
            break;
        }
        if (status != 0) {
            LOGe("Decode failed at token %d with status %d", i, status);
            break;
        }
        ++cur_pos;
    }

    llama_sampler_free(sampler);
    return result;
}

} // namespace

bool init_model(const std::string& model_path) {
    std::lock_guard<std::mutex> lock(g_mutex);
    ensure_backend_initialized();
    release_model_state();
    g_cancel_generation.store(false);

    auto mparams = llama_model_default_params();
    mparams.n_gpu_layers = 0;
    mparams.use_mmap = true;
    mparams.use_direct_io = false;
    mparams.use_mlock = false;
    mparams.check_tensors = false;
    mparams.use_extra_bufts = true;

    g_model = llama_model_load_from_file(model_path.c_str(), mparams);
    if (!g_model) {
        LOGe("Failed to load GGUF model: %s", model_path.c_str());
        return false;
    }

    g_vocab = llama_model_get_vocab(g_model);
    g_runtime = choose_runtime_tuning();

    auto cparams = llama_context_default_params();
    cparams.n_ctx = g_runtime.n_ctx;
    cparams.n_batch = g_runtime.n_batch;
    cparams.n_ubatch = g_runtime.n_ubatch;
    cparams.n_threads = g_runtime.decode_threads;
    cparams.n_threads_batch = g_runtime.batch_threads;
    cparams.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_AUTO;
    cparams.type_k = GGML_TYPE_F16;
    cparams.type_v = GGML_TYPE_F16;
    cparams.abort_callback = abort_callback;
    cparams.abort_callback_data = nullptr;

    g_ctx = llama_init_from_model(g_model, cparams);
    if (!g_ctx) {
        LOGe("Failed to create llama.cpp context");
        release_model_state();
        return false;
    }

    attach_threadpools();
    if (!g_threadpool) {
        llama_set_n_threads(g_ctx, g_runtime.decode_threads, g_runtime.batch_threads);
    }

    if (!init_batch(g_runtime.n_batch)) {
        release_model_state();
        return false;
    }

    LOGi(
        "llama.cpp model loaded: ram=%.1fGB, n_ctx=%d, n_batch=%d/%d, threads=%d/%d, perf_cores=%d, pinned=%d",
        g_runtime.total_ram_gb,
        g_runtime.n_ctx,
        g_runtime.n_batch,
        g_runtime.n_ubatch,
        g_runtime.decode_threads,
        g_runtime.batch_threads,
        g_runtime.cpu_profile.perf_cores,
        g_runtime.pin_to_perf_cores ? 1 : 0
    );
    return true;
}

void update_generate_params(
    float temperature,
    int max_tokens,
    float top_p,
    int top_k,
    float repeat_penalty
) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_temperature = temperature;
    g_max_tokens = max_tokens;
    g_top_p = top_p;
    g_top_k = top_k;
    g_repeat_penalty = repeat_penalty;
}

std::string generate(const std::string& prompt) {
    std::lock_guard<std::mutex> lock(g_mutex);
    return generate_locked(prompt);
}

std::string generate_chat(
    const std::string& system_prompt,
    const std::string& user_message,
    bool enable_thinking
) {
    std::lock_guard<std::mutex> lock(g_mutex);
    const std::string prompt = apply_chat_template_locked(system_prompt, user_message, enable_thinking);
    if (prompt.empty()) {
        return "";
    }
    return generate_locked(prompt);
}

std::string apply_chat_template(
    const std::string& system_prompt,
    const std::string& user_message,
    bool enable_thinking
) {
    std::lock_guard<std::mutex> lock(g_mutex);
    return apply_chat_template_locked(system_prompt, user_message, enable_thinking);
}

void cancel_generation() {
    g_cancel_generation.store(true);
}

void shutdown() {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_cancel_generation.store(true);
    release_model_state();
}

#else

bool init_model(const std::string&) {
    LOGw("llama.cpp backend is not built for this ABI");
    return false;
}

void update_generate_params(float, int, float, int, float) {}

std::string generate(const std::string&) {
    return "";
}

std::string generate_chat(const std::string&, const std::string&, bool) {
    return "";
}

std::string apply_chat_template(const std::string&, const std::string&, bool) {
    return "";
}

void cancel_generation() {}

void shutdown() {}

#endif

} // namespace chartlite::llama_backend
