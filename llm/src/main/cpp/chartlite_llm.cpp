#include <jni.h>
#include <android/log.h>
#include <string>
#include <vector>
#include <algorithm>
#include <atomic>
#include <unistd.h>

#include "llama.h"
#include "ggml.h"
#include "common.h"
#include "sampling.h"
#include "chat.h"
#include "json-schema-to-grammar.h"
#include <nlohmann/json.hpp>

#define TAG "ChartLiteLLM"
#define LOGi(...) __android_log_print(ANDROID_LOG_INFO,  TAG, __VA_ARGS__)
#define LOGw(...) __android_log_print(ANDROID_LOG_WARN,  TAG, __VA_ARGS__)
#define LOGe(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

// Global state — single model at a time (singleton pattern)
static llama_model   *g_model   = nullptr;
static llama_context *g_context = nullptr;
static int            g_n_ctx   = 4096;
static int            g_n_batch = 128;

// Sampling parameters (set by updateGenerateParams)
static float g_temperature    = 0.3f;
static int   g_max_tokens     = 2048;
static float g_top_p          = 0.95f;
static int   g_top_k          = 40;
static float g_repeat_penalty = 1.0f;
static std::atomic<bool> g_cancel_generation(false);

// Forward declaration
static void shutdown_internal();
static bool should_abort_generation(void *) {
    return g_cancel_generation.load();
}

// ── Shared generation logic ──

static std::string generate_internal(const std::string &prompt, const std::string &grammar_str) {
    if (!g_model || !g_context) {
        LOGe("generate_internal: model or context not loaded");
        return "";
    }

    // Tokenize prompt
    auto tokens = common_tokenize(g_context, prompt, true, true);
    if (tokens.empty()) {
        LOGe("generate_internal: tokenization produced no tokens");
        return "";
    }
    LOGi("Prompt tokenized: %zu tokens (ctx=%d batch=%d)", tokens.size(), g_n_ctx, g_n_batch);

    const int context_headroom = 64;
    const int max_prompt_tokens = std::max(1, g_n_ctx - g_max_tokens - context_headroom);
    if ((int) tokens.size() > max_prompt_tokens) {
        LOGw("generate_internal: prompt too long (%zu tokens, max %d after reserving %d output tokens)",
             tokens.size(), max_prompt_tokens, g_max_tokens);
        return "";
    }

    g_cancel_generation.store(false);

    // Clear KV cache
    llama_memory_clear(llama_get_memory(g_context), false);

    // Decode prompt tokens in batches
    const int batch_size = std::max(32, g_n_batch);
    llama_batch batch = llama_batch_init(batch_size, 0, 1);

    for (int i = 0; i < (int)tokens.size(); i += batch_size) {
        int n = std::min((int)tokens.size() - i, batch_size);
        common_batch_clear(batch);
        for (int j = 0; j < n; j++) {
            bool is_last = (i + j == (int)tokens.size() - 1);
            common_batch_add(batch, tokens[i + j], i + j, {0}, is_last);
        }
        if (llama_decode(g_context, batch) != 0) {
            if (g_cancel_generation.load()) {
                LOGw("generate_internal: prompt processing cancelled");
            } else {
                LOGe("generate_internal: llama_decode failed during prompt processing");
            }
            llama_batch_free(batch);
            return "";
        }
        if (g_cancel_generation.load()) {
            LOGw("generate_internal: cancelled after prompt batch %d", i / batch_size);
            llama_batch_free(batch);
            return "";
        }
    }

    // Create sampler with current params
    common_params_sampling sparams;
    sparams.temp           = g_temperature;
    sparams.top_p          = g_top_p;
    sparams.top_k          = g_top_k;
    sparams.penalty_repeat = g_repeat_penalty;
    if (!grammar_str.empty()) {
        sparams.grammar = grammar_str;
    }

    common_sampler *smpl = common_sampler_init(g_model, sparams);
    if (!smpl) {
        LOGe("generate_internal: failed to init sampler");
        llama_batch_free(batch);
        return "";
    }

    // Generate tokens
    std::string result;
    int n_cur = (int)tokens.size();
    const auto *vocab = llama_model_get_vocab(g_model);

    for (int i = 0; i < g_max_tokens; i++) {
        if (g_cancel_generation.load()) {
            LOGw("generate_internal: generation cancelled at token %d", i);
            break;
        }

        llama_token new_token = common_sampler_sample(smpl, g_context, -1);

        if (llama_vocab_is_eog(vocab, new_token)) {
            if (i == 0) {
                LOGw("generate_internal: sampled EOG immediately");
            } else {
                LOGi("generate_internal: reached EOG at token %d", i);
            }
            break;
        }

        common_sampler_accept(smpl, new_token, true);
        result += common_token_to_piece(g_context, new_token);

        common_batch_clear(batch);
        common_batch_add(batch, new_token, n_cur, {0}, true);
        n_cur++;

        if (llama_decode(g_context, batch) != 0) {
            if (g_cancel_generation.load()) {
                LOGw("generate_internal: generation cancelled during decode at token %d", i);
            } else {
                LOGe("generate_internal: llama_decode failed at token %d", i);
            }
            break;
        }
    }

    common_sampler_free(smpl);
    llama_batch_free(batch);

    LOGi("Generated %zu chars", result.size());
    return result;
}

// ── JNI Methods ──

extern "C" JNIEXPORT void JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeInit(JNIEnv *, jobject) {
    llama_backend_init();
    LOGi("llama_backend_init() done");
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeInitGenerateModel(JNIEnv *env, jobject, jstring jModelPath) {
    if (g_model) {
        shutdown_internal();
    }

    const char *modelPath = env->GetStringUTFChars(jModelPath, nullptr);
    LOGi("initGenerateModel: %s", modelPath);

    llama_model_params model_params = llama_model_default_params();
    model_params.use_mmap = true;
    g_model = llama_model_load_from_file(modelPath, model_params);
    env->ReleaseStringUTFChars(jModelPath, modelPath);

    if (!g_model) {
        LOGe("gen model load failed");
        return JNI_FALSE;
    }

    // Auto-scale context and batch size based on model parameter count and
    // total system RAM. Low-end Android phones need tighter limits so note
    // processing degrades gracefully instead of crashing the process.
    uint64_t n_params = llama_model_n_params(g_model);
    bool is_small_model = (n_params < 1500000000ULL);
    long page_count = sysconf(_SC_PHYS_PAGES);
    long page_size = sysconf(_SC_PAGE_SIZE);
    double total_ram_gb = 0.0;
    if (page_count > 0 && page_size > 0) {
        total_ram_gb = (double) page_count * (double) page_size / (1024.0 * 1024.0 * 1024.0);
    }

    int n_ctx = 4096;
    int n_batch = 128;
    if (is_small_model) {
        if (total_ram_gb > 0.0 && total_ram_gb <= 3.0) {
            // Ultra-low-RAM: halve KV cache, minimize batch peak allocation
            n_ctx = 2048;
            n_batch = 64;
        } else if (total_ram_gb > 0.0 && total_ram_gb <= 3.5) {
            n_ctx = 4096;
            n_batch = 128;
        } else if (total_ram_gb > 0.0 && total_ram_gb <= 4.5) {
            n_ctx = 6144;
            n_batch = 192;
        } else {
            n_ctx = 8192;
            n_batch = 256;
        }
    } else {
        n_ctx = (total_ram_gb > 0.0 && total_ram_gb <= 6.0) ? 3072 : 4096;
        n_batch = (total_ram_gb > 0.0 && total_ram_gb <= 6.0) ? 192 : 256;
    }
    g_n_ctx = n_ctx;
    g_n_batch = n_batch;

    // Create context
    llama_context_params ctx_params = llama_context_default_params();
    ctx_params.n_ctx    = n_ctx;
    ctx_params.n_batch  = n_batch;
    ctx_params.n_ubatch = n_batch;

    // Performance: flash attention reduces memory bandwidth pressure on ARM NEON
    ctx_params.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_ENABLED;

    // Performance: Q8_0 KV cache halves memory vs F16 default, faster on memory-bound devices
    ctx_params.type_k = GGML_TYPE_Q8_0;
    ctx_params.type_v = GGML_TYPE_Q8_0;

    // Threading: leave 2 cores for Android system during generation,
    // but use more cores for batch (prompt processing is embarrassingly parallel)
    int n_cpu = (int)sysconf(_SC_NPROCESSORS_ONLN);
    int n_threads = std::max(2, std::min(4, n_cpu - 2));
    int n_threads_batch = std::max(2, std::min(6, n_cpu - 1));
    ctx_params.n_threads       = n_threads;
    ctx_params.n_threads_batch = n_threads_batch;

    g_context = llama_init_from_model(g_model, ctx_params);
    if (!g_context) {
        LOGe("llama_init_from_model failed");
        llama_model_free(g_model);
        g_model = nullptr;
        return JNI_FALSE;
    }

    llama_set_abort_callback(g_context, should_abort_generation, nullptr);

    LOGi("Model loaded: params=%lluM, ram=%.1fGB, n_ctx=%d, n_batch=%d, threads=%d/%d, flash_attn=on, kv=q8_0",
         (unsigned long long)(n_params / 1000000), total_ram_gb, n_ctx, n_batch, n_threads, n_threads_batch);
    return JNI_TRUE;
}

extern "C" JNIEXPORT void JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeUpdateGenerateParams(
    JNIEnv *, jobject,
    jfloat temperature, jint maxTokens, jfloat topP, jint topK, jfloat repeatPenalty
) {
    g_temperature    = temperature;
    g_max_tokens     = maxTokens;
    g_top_p          = topP;
    g_top_k          = topK;
    g_repeat_penalty = repeatPenalty;
    LOGi("Params updated: temp=%.2f, max=%d, topP=%.2f, topK=%d, repeat=%.2f",
         g_temperature, g_max_tokens, g_top_p, g_top_k, g_repeat_penalty);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeGenerate(JNIEnv *env, jobject, jstring jPrompt) {
    const char *prompt = env->GetStringUTFChars(jPrompt, nullptr);
    std::string result = generate_internal(std::string(prompt), "");
    env->ReleaseStringUTFChars(jPrompt, prompt);

    if (result.empty()) return nullptr;
    return env->NewStringUTF(result.c_str());
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeGenerateJson(
    JNIEnv *env, jobject, jstring jPrompt, jstring jJsonSchema
) {
    const char *prompt     = env->GetStringUTFChars(jPrompt, nullptr);
    const char *jsonSchema = env->GetStringUTFChars(jJsonSchema, nullptr);

    // Convert JSON schema to GBNF grammar
    std::string grammar_str;
    try {
        auto schema = nlohmann::ordered_json::parse(jsonSchema);
        grammar_str = json_schema_to_grammar(schema);
    } catch (const std::exception &e) {
        LOGe("Failed to parse JSON schema: %s", e.what());
        env->ReleaseStringUTFChars(jPrompt, prompt);
        env->ReleaseStringUTFChars(jJsonSchema, jsonSchema);
        return nullptr;
    }

    std::string result = generate_internal(std::string(prompt), grammar_str);
    env->ReleaseStringUTFChars(jPrompt, prompt);
    env->ReleaseStringUTFChars(jJsonSchema, jsonSchema);

    if (result.empty()) return nullptr;
    return env->NewStringUTF(result.c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeCancelGeneration(JNIEnv *, jobject) {
    g_cancel_generation.store(true);
    LOGw("Cancellation requested");
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeApplyChatTemplate(
    JNIEnv *env, jobject,
    jstring jSystemPrompt, jstring jUserMessage, jboolean enableThinking
) {
    if (!g_model) {
        LOGe("applyChatTemplate: model not loaded");
        return nullptr;
    }

    const char *systemPrompt = env->GetStringUTFChars(jSystemPrompt, nullptr);
    const char *userMessage  = env->GetStringUTFChars(jUserMessage, nullptr);

    // Initialize chat templates from model metadata (Jinja template)
    common_chat_templates_ptr tmpls = common_chat_templates_init(g_model, nullptr);
    if (!tmpls) {
        LOGe("applyChatTemplate: failed to init chat templates from model");
        env->ReleaseStringUTFChars(jSystemPrompt, systemPrompt);
        env->ReleaseStringUTFChars(jUserMessage, userMessage);
        return nullptr;
    }

    // Build messages array
    common_chat_templates_inputs inputs;
    inputs.messages = {
        { /* role */ "system", /* content */ std::string(systemPrompt), {}, {}, "" },
        { /* role */ "user",   /* content */ std::string(userMessage),  {}, {}, "" },
    };
    inputs.add_generation_prompt = true;
    inputs.use_jinja = true;
    inputs.enable_thinking = (bool) enableThinking;

    env->ReleaseStringUTFChars(jSystemPrompt, systemPrompt);
    env->ReleaseStringUTFChars(jUserMessage, userMessage);

    // Apply chat template — this produces the correctly formatted prompt
    // with thinking disabled when enableThinking=false
    try {
        common_chat_params result = common_chat_templates_apply(tmpls.get(), inputs);
        LOGi("applyChatTemplate: generated prompt (%zu chars), thinking=%s",
             result.prompt.size(), enableThinking ? "on" : "off");
        return env->NewStringUTF(result.prompt.c_str());
    } catch (const std::exception &e) {
        LOGe("applyChatTemplate: template apply failed: %s", e.what());
        return nullptr;
    }
}

static void shutdown_internal() {
    g_cancel_generation.store(false);
    if (g_context) {
        llama_free(g_context);
        g_context = nullptr;
    }
    if (g_model) {
        llama_model_free(g_model);
        g_model = nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeShutdown(JNIEnv *, jobject) {
    shutdown_internal();
    LOGi("Model unloaded");
}
