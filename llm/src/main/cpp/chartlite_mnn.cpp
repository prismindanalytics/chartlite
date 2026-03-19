#include <jni.h>
#include <android/log.h>
#include <string>
#include <sstream>
#include <atomic>
#include <mutex>
#include <unistd.h>

#include <llm/llm.hpp>

#define TAG "ChartLiteLLM"
#define LOGi(...) __android_log_print(ANDROID_LOG_INFO,  TAG, __VA_ARGS__)
#define LOGw(...) __android_log_print(ANDROID_LOG_WARN,  TAG, __VA_ARGS__)
#define LOGe(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

using namespace MNN::Transformer;

// Global state — single model at a time (singleton pattern)
static Llm *g_llm = nullptr;
static std::mutex g_mutex;

// Sampling parameters (applied via set_config JSON)
static float g_temperature    = 0.3f;
static int   g_max_tokens     = 2048;
static float g_top_p          = 0.95f;
static int   g_top_k          = 40;
static float g_repeat_penalty = 1.0f;
static std::atomic<bool> g_cancel_generation(false);

// Build JSON config string for MNN sampling parameters
static std::string build_config_json() {
    std::ostringstream ss;
    ss << "{"
       << "\"max_new_tokens\":" << g_max_tokens << ","
       << "\"temperature\":" << g_temperature << ","
       << "\"top_k\":" << g_top_k << ","
       << "\"top_p\":" << g_top_p << ","
       << "\"repeat_penalty\":" << g_repeat_penalty
       << "}";
    return ss.str();
}

// Apply current sampling params to the loaded model
static void apply_params() {
    if (!g_llm) return;
    std::string config = build_config_json();
    g_llm->set_config(config);
}

// Custom output stream buffer that checks cancellation
class CancelCheckBuf : public std::streambuf {
public:
    std::string result;
protected:
    int overflow(int c) override {
        if (g_cancel_generation.load()) return EOF;
        if (c != EOF) result += static_cast<char>(c);
        return c;
    }
    std::streamsize xsputn(const char* s, std::streamsize n) override {
        if (g_cancel_generation.load()) return 0;
        result.append(s, n);
        return n;
    }
};

// ── JNI Methods ──
// Note: JNI names use LlamaBridge for backward compatibility with Kotlin wrapper.
// The Kotlin class name remains LlamaBridge to avoid touching all callers,
// but the native implementation now uses MNN.

extern "C" JNIEXPORT void JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeInit(JNIEnv *, jobject) {
    // MNN doesn't need a global backend init — this is a no-op for API compatibility
    LOGi("MNN backend ready");
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeInitGenerateModel(JNIEnv *env, jobject, jstring jModelPath) {
    std::lock_guard<std::mutex> lock(g_mutex);

    // Shutdown previous model if any
    if (g_llm) {
        Llm::destroy(g_llm);
        g_llm = nullptr;
    }

    const char *modelPath = env->GetStringUTFChars(jModelPath, nullptr);
    LOGi("initGenerateModel (MNN): %s", modelPath);

    // MNN expects path to the directory containing llm_config.json, with trailing /
    std::string configDir(modelPath);
    if (!configDir.empty() && configDir.back() != '/') {
        configDir += '/';
    }
    g_llm = Llm::createLLM(configDir);
    env->ReleaseStringUTFChars(jModelPath, modelPath);

    if (!g_llm) {
        LOGe("Llm::createLLM failed");
        return JNI_FALSE;
    }

    // Configure threading based on available CPUs
    int n_cpu = (int)sysconf(_SC_NPROCESSORS_ONLN);
    int n_threads = std::max(2, std::min(4, n_cpu - 2));

    // Get total RAM for logging
    long page_count = sysconf(_SC_PHYS_PAGES);
    long page_size = sysconf(_SC_PAGE_SIZE);
    double total_ram_gb = 0.0;
    if (page_count > 0 && page_size > 0) {
        total_ram_gb = (double)page_count * (double)page_size / (1024.0 * 1024.0 * 1024.0);
    }

    // Set thread count, backend, and disable thinking (saves tokens for actual output)
    std::ostringstream config;
    config << "{"
           << "\"thread_num\":" << n_threads << ","
           << "\"backend\":\"cpu\","
           << "\"jinja\":{\"context\":{\"enable_thinking\":false}}"
           << "}";
    g_llm->set_config(config.str());

    // Load model weights
    if (!g_llm->load()) {
        LOGe("Llm::load() failed");
        Llm::destroy(g_llm);
        g_llm = nullptr;
        return JNI_FALSE;
    }

    // Apply current sampling parameters
    apply_params();

    // Run tuning for optimal performance on this device
    g_llm->tuning(OP_ENCODER_NUMBER, {1, 32, 64, 128});

    LOGi("MNN model loaded: ram=%.1fGB, threads=%d", total_ram_gb, n_threads);
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
    apply_params();
    LOGi("Params updated: temp=%.2f, max=%d, topP=%.2f, topK=%d, repeat=%.2f",
         g_temperature, g_max_tokens, g_top_p, g_top_k, g_repeat_penalty);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeGenerate(JNIEnv *env, jobject, jstring jPrompt) {
    if (!g_llm) {
        LOGe("nativeGenerate: model not loaded");
        return nullptr;
    }

    const char *prompt = env->GetStringUTFChars(jPrompt, nullptr);
    std::string promptStr(prompt);
    env->ReleaseStringUTFChars(jPrompt, prompt);

    g_cancel_generation.store(false);

    CancelCheckBuf buf;
    std::ostream os(&buf);

    LOGi("Generating response for prompt (%zu chars)...", promptStr.size());

    // Pass as plain user content — MNN applies the chat template internally
    g_llm->response(promptStr, &os, nullptr, g_max_tokens);

    const auto *ctx = g_llm->getContext();
    if (ctx) {
        LOGi("Generated: prompt=%d tokens, decode=%d tokens, prefill=%.1fms, decode=%.1fms",
             ctx->prompt_len, ctx->gen_seq_len,
             ctx->prefill_us / 1000.0, ctx->decode_us / 1000.0);
    }

    if (g_cancel_generation.load()) {
        LOGw("Generation was cancelled");
    }

    if (buf.result.empty()) return nullptr;
    return env->NewStringUTF(buf.result.c_str());
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeGenerateChat(
    JNIEnv *env, jobject,
    jstring jSystemPrompt, jstring jUserMessage
) {
    if (!g_llm) {
        LOGe("nativeGenerateChat: model not loaded");
        return nullptr;
    }

    const char *sys = env->GetStringUTFChars(jSystemPrompt, nullptr);
    const char *usr = env->GetStringUTFChars(jUserMessage, nullptr);

    ChatMessages messages = {
        {"system", std::string(sys)},
        {"user",   std::string(usr)},
    };

    env->ReleaseStringUTFChars(jSystemPrompt, sys);
    env->ReleaseStringUTFChars(jUserMessage, usr);

    g_cancel_generation.store(false);

    CancelCheckBuf buf;
    std::ostream os(&buf);

    LOGi("GenerateChat: system=%zu chars, user=%zu chars",
         messages[0].second.size(), messages[1].second.size());

    // response(ChatMessages) applies the model's native chat template
    // with proper special token handling, then generates
    g_llm->response(messages, &os, nullptr, g_max_tokens);

    const auto *ctx = g_llm->getContext();
    if (ctx) {
        LOGi("Generated: prompt=%d tokens, decode=%d tokens, prefill=%.1fms, decode=%.1fms",
             ctx->prompt_len, ctx->gen_seq_len,
             ctx->prefill_us / 1000.0, ctx->decode_us / 1000.0);
    }

    if (g_cancel_generation.load()) {
        LOGw("Generation was cancelled");
    }

    if (buf.result.empty()) return nullptr;
    return env->NewStringUTF(buf.result.c_str());
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeGenerateJson(
    JNIEnv *env, jobject thiz, jstring jPrompt, jstring /* jJsonSchema */
) {
    // MNN doesn't support grammar-constrained generation.
    // Fall through to standard generation — the prompt instructs JSON output.
    LOGw("nativeGenerateJson: grammar not supported in MNN, using standard generation");
    return Java_com_chartlite_llm_LlamaBridge_nativeGenerate(env, thiz, jPrompt);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeGenerateVision(
    JNIEnv *env, jobject,
    jstring jSystemPrompt, jstring jUserMessage, jstring jImagePath
) {
    if (!g_llm) {
        LOGe("nativeGenerateVision: model not loaded");
        return nullptr;
    }

    const char *sys = env->GetStringUTFChars(jSystemPrompt, nullptr);
    const char *usr = env->GetStringUTFChars(jUserMessage, nullptr);
    const char *img = env->GetStringUTFChars(jImagePath, nullptr);

    // Build MultimodalPrompt with image file path.
    // MNN's tokenizer_encode(MultimodalPrompt) detects <img>...</img> tags
    // and routes to visionProcess() which loads the image via imread().
    MultimodalPrompt mp;
    std::ostringstream prompt;
    prompt << "<|im_start|>system\n" << sys << "<|im_end|>\n"
           << "<|im_start|>user\n"
           << "<img>" << img << "</img>\n"
           << usr << "<|im_end|>\n"
           << "<|im_start|>assistant\n";
    mp.prompt_template = prompt.str();

    LOGi("GenerateVision: system=%zu chars, user=%zu chars, image=%s",
         strlen(sys), strlen(usr), img);

    env->ReleaseStringUTFChars(jSystemPrompt, sys);
    env->ReleaseStringUTFChars(jUserMessage, usr);
    env->ReleaseStringUTFChars(jImagePath, img);

    g_cancel_generation.store(false);

    CancelCheckBuf buf;
    std::ostream os(&buf);

    g_llm->response(mp, &os, nullptr, g_max_tokens);

    const auto *ctx = g_llm->getContext();
    if (ctx) {
        LOGi("Vision generated: prompt=%d tokens, decode=%d tokens, prefill=%.1fms, decode=%.1fms, vision=%.1fms",
             ctx->prompt_len, ctx->gen_seq_len,
             ctx->prefill_us / 1000.0, ctx->decode_us / 1000.0,
             ctx->vision_us / 1000.0);
    }

    if (g_cancel_generation.load()) {
        LOGw("Vision generation was cancelled");
    }

    if (buf.result.empty()) return nullptr;
    return env->NewStringUTF(buf.result.c_str());
}

extern "C" JNIEXPORT void JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeCancelGeneration(JNIEnv *, jobject) {
    g_cancel_generation.store(true);
    LOGw("Cancellation requested");
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeApplyChatTemplate(
    JNIEnv *env, jobject,
    jstring jSystemPrompt, jstring jUserMessage, jboolean /* enableThinking */
) {
    if (!g_llm) {
        LOGe("applyChatTemplate: model not loaded");
        return nullptr;
    }

    const char *systemPrompt = env->GetStringUTFChars(jSystemPrompt, nullptr);
    const char *userMessage  = env->GetStringUTFChars(jUserMessage, nullptr);

    // Use MNN's built-in chat template from model metadata
    ChatMessages messages = {
        {"system", std::string(systemPrompt)},
        {"user",   std::string(userMessage)},
    };

    env->ReleaseStringUTFChars(jSystemPrompt, systemPrompt);
    env->ReleaseStringUTFChars(jUserMessage, userMessage);

    try {
        std::string result = g_llm->apply_chat_template(messages);
        LOGi("applyChatTemplate: generated prompt (%zu chars)", result.size());
        return env->NewStringUTF(result.c_str());
    } catch (const std::exception &e) {
        LOGe("applyChatTemplate failed: %s", e.what());
        return nullptr;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeShutdown(JNIEnv *, jobject) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_llm) {
        Llm::destroy(g_llm);
        g_llm = nullptr;
    }
    LOGi("MNN model unloaded");
}
