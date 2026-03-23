#include <jni.h>
#include <android/log.h>
#include <string>
#include <sstream>
#include <atomic>
#include <mutex>
#include <unistd.h>

#include <llm/llm.hpp>
#include <MNN/expr/Expr.hpp>
#include <MNN/expr/NeuralNetWorkOp.hpp>

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

static std::string escape_json_string(const std::string& value) {
    std::string escaped;
    escaped.reserve(value.size() + 8);
    for (char ch : value) {
        switch (ch) {
            case '\\':
                escaped += "\\\\";
                break;
            case '"':
                escaped += "\\\"";
                break;
            default:
                escaped += ch;
                break;
        }
    }
    return escaped;
}

// Build JSON config string for MNN sampling parameters
static std::string build_config_json() {
    std::ostringstream ss;
    ss << "{"
       << "\"max_new_tokens\":" << g_max_tokens << ","
       << "\"sampler_type\":\"mixed\","
       << "\"mixed_samplers\":[\"penalty\",\"topK\",\"topP\",\"temperature\"],"
       << "\"temperature\":" << g_temperature << ","
       << "\"topK\":" << g_top_k << ","
       << "\"topP\":" << g_top_p << ","
       << "\"penalty\":" << g_repeat_penalty << ","
       << "\"penalty_sampler\":\"temperature\""
       << "}";
    return ss.str();
}

// Apply current sampling params to the loaded model
static void apply_params() {
    if (!g_llm) return;
    std::string config = build_config_json();
    g_llm->set_config(config);
}

// Custom output stream buffer that checks cancellation.
// Pre-reserves 16 KB to avoid O(n^2) reallocation from char-by-char overflow() calls.
class CancelCheckBuf : public std::streambuf {
public:
    std::string result;
    CancelCheckBuf() { result.reserve(16384); }
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
Java_com_chartlite_llm_LlamaBridge_nativeInitGenerateModel(JNIEnv *env, jobject, jstring jModelPath, jstring jTmpPath) {
    std::lock_guard<std::mutex> lock(g_mutex);

    // Shutdown previous model if any
    if (g_llm) {
        Llm::destroy(g_llm);
        g_llm = nullptr;
    }

    const char *modelPath = env->GetStringUTFChars(jModelPath, nullptr);
    const char *tmpPathChars = env->GetStringUTFChars(jTmpPath, nullptr);
    LOGi("initGenerateModel (MNN): %s", modelPath);

    // MNN expects path to the directory containing llm_config.json, with trailing /
    std::string configDir(modelPath);
    std::string tmpPath = tmpPathChars ? tmpPathChars : "";
    if (!configDir.empty() && configDir.back() != '/') {
        configDir += '/';
    }
    g_llm = Llm::createLLM(configDir);
    env->ReleaseStringUTFChars(jModelPath, modelPath);
    if (tmpPathChars) {
        env->ReleaseStringUTFChars(jTmpPath, tmpPathChars);
    }

    if (!g_llm) {
        LOGe("Llm::createLLM failed");
        return JNI_FALSE;
    }

    // Configure threading with big.LITTLE awareness — count performance cores
    // by reading max frequency from sysfs and only counting cores within 80% of peak.
    int n_cpu = (int)sysconf(_SC_NPROCESSORS_ONLN);
    int n_big_cores = 0;
    {
        long max_freq = 0;
        long freqs[16] = {};
        int core_count = 0;
        for (int i = 0; i < 16 && i < n_cpu; i++) {
            char path[128];
            snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_max_freq", i);
            FILE* f = fopen(path, "r");
            if (!f) break;
            long freq = 0;
            if (fscanf(f, "%ld", &freq) == 1) {
                freqs[i] = freq;
                if (freq > max_freq) max_freq = freq;
                core_count++;
            }
            fclose(f);
        }
        for (int i = 0; i < core_count; i++) {
            if (freqs[i] >= (long)(max_freq * 0.8)) n_big_cores++;
        }
        if (n_big_cores == 0) n_big_cores = n_cpu; // Fallback: symmetric SoC
        LOGi("CPU topology: %d total cores, %d big cores (max freq=%ldkHz)", n_cpu, n_big_cores, max_freq);
    }

    // Get total RAM for logging
    long page_count = sysconf(_SC_PHYS_PAGES);
    long page_size = sysconf(_SC_PAGE_SIZE);
    double total_ram_gb = 0.0;
    if (page_count > 0 && page_size > 0) {
        total_ram_gb = (double)page_count * (double)page_size / (1024.0 * 1024.0 * 1024.0);
    }
    const bool low_ram_device = total_ram_gb <= 3.5;
    const bool can_push_three_threads = low_ram_device && total_ram_gb >= 2.5 && n_cpu >= 6;
    // Use big core count for thread allocation — ensures MNN runs on performance cores only.
    const int n_threads = low_ram_device
        ? (can_push_three_threads ? 3 : 2)
        : std::max(2, std::min(n_big_cores, 4));
    const int attention_mode = low_ram_device ? 10 : 8;

    // Use the MNN-documented runtime keys so low-RAM tuning is actually applied.
    std::ostringstream config;
    config << "{"
           << "\"async\":false,"
           << "\"thread_num\":" << n_threads << ","
           << "\"backend_type\":\"cpu\","
           << "\"precision\":\"low\","
           << "\"memory\":\"low\","
           << "\"power\":\"high\","
           << "\"use_mmap\":true,"
           << "\"use_cached_mmap\":true,";
    if (!tmpPath.empty()) {
        config << "\"tmp_path\":\"" << escape_json_string(tmpPath) << "\",";
    }
    config << "\"attention_mode\":" << attention_mode << ","
           << "\"jinja\":{\"context\":{\"enable_thinking\":false}}"
           << "}";
    if (!g_llm->set_config(config.str())) {
        LOGw("Initial MNN config rejected, continuing with model defaults");
    }

    // Load model weights
    if (!g_llm->load()) {
        LOGe("Llm::load() failed");
        Llm::destroy(g_llm);
        g_llm = nullptr;
        return JNI_FALSE;
    }

    // Apply current sampling parameters
    apply_params();

    // Low-RAM devices reload the model more often because ASR and LLM are serialized.
    // Skip encoder tuning there to cut reload latency and reduce peak memory pressure.
    if (!low_ram_device) {
        g_llm->tuning(OP_ENCODER_NUMBER, {1, 32, 64, 128});
    } else {
        LOGi("Skipping MNN tuning on low-RAM device to reduce reload latency");
    }

    LOGi(
        "MNN model loaded: ram=%.1fGB, threads=%d, attention=%d, low_ram=%d",
        total_ram_gb,
        n_threads,
        attention_mode,
        low_ram_device ? 1 : 0
    );
    return JNI_TRUE;
}

extern "C" JNIEXPORT void JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeUpdateGenerateParams(
    JNIEnv *, jobject,
    jfloat temperature, jint maxTokens, jfloat topP, jint topK, jfloat repeatPenalty
) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_temperature    = temperature;
    g_max_tokens     = maxTokens;
    g_top_p          = topP;
    g_top_k          = topK;
    g_repeat_penalty = repeatPenalty;
    apply_params();
    LOGi("Params updated: temp=%.2f, max=%d, topP=%.2f, topK=%d, repeat=%.2f",
         g_temperature, g_max_tokens, g_top_p, g_top_k, g_repeat_penalty);
}

// Internal generate without mutex — called by locked entry points
static jstring generate_internal_jni(JNIEnv *env, jstring jPrompt) {
    if (!g_llm) {
        LOGe("generate_internal_jni: model not loaded");
        return nullptr;
    }
    const char *prompt = env->GetStringUTFChars(jPrompt, nullptr);
    if (!prompt) return nullptr;
    std::string promptStr(prompt);
    env->ReleaseStringUTFChars(jPrompt, prompt);

    g_cancel_generation.store(false);
    CancelCheckBuf buf;
    std::ostream os(&buf);
    LOGi("Generating response for prompt (%zu chars)...", promptStr.size());
    g_llm->response(promptStr, &os, nullptr, g_max_tokens);

    const auto *ctx = g_llm->getContext();
    if (ctx) {
        LOGi("Generate metrics: prompt=%d tokens, decode=%d tokens, first_token_ms=%.1f, total_decode_ms=%.1f",
             ctx->prompt_len, ctx->gen_seq_len,
             ctx->prefill_us / 1000.0, ctx->decode_us / 1000.0);
    }
    if (g_cancel_generation.load()) LOGw("Generation was cancelled");
    if (buf.result.empty()) return nullptr;
    return env->NewStringUTF(buf.result.c_str());
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeGenerate(JNIEnv *env, jobject, jstring jPrompt) {
    std::lock_guard<std::mutex> lock(g_mutex);
    return generate_internal_jni(env, jPrompt);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeGenerateChat(
    JNIEnv *env, jobject,
    jstring jSystemPrompt, jstring jUserMessage
) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (!g_llm) {
        LOGe("nativeGenerateChat: model not loaded");
        return nullptr;
    }

    const char *sys = env->GetStringUTFChars(jSystemPrompt, nullptr);
    if (!sys) { LOGe("nativeGenerateChat: GetStringUTFChars failed for system"); return nullptr; }
    const char *usr = env->GetStringUTFChars(jUserMessage, nullptr);
    if (!usr) { env->ReleaseStringUTFChars(jSystemPrompt, sys); LOGe("nativeGenerateChat: GetStringUTFChars failed for user"); return nullptr; }

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
        LOGi("GenerateChat metrics: prompt=%d tokens, decode=%d tokens, first_token_ms=%.1f, total_decode_ms=%.1f",
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
    JNIEnv *env, jobject, jstring jPrompt, jstring /* jJsonSchema */
) {
    std::lock_guard<std::mutex> lock(g_mutex);
    LOGw("nativeGenerateJson: grammar not supported in MNN, using standard generation");
    return generate_internal_jni(env, jPrompt);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_chartlite_llm_LlamaBridge_nativeGenerateVision(
    JNIEnv *env, jobject,
    jstring jSystemPrompt, jstring jUserMessage, jbyteArray jRgbData, jint width, jint height
) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (!g_llm) {
        LOGe("nativeGenerateVision: model not loaded");
        return nullptr;
    }

    // Extract JNI strings early to avoid leaks if later calls fail
    const char *sysRaw = env->GetStringUTFChars(jSystemPrompt, nullptr);
    if (!sysRaw) return nullptr;
    std::string sysStr(sysRaw);
    env->ReleaseStringUTFChars(jSystemPrompt, sysRaw);

    const char *usrRaw = env->GetStringUTFChars(jUserMessage, nullptr);
    if (!usrRaw) return nullptr;
    std::string usrStr(usrRaw);
    env->ReleaseStringUTFChars(jUserMessage, usrRaw);

    // Convert RGB byte array to MNN VARP tensor [1, height, width, 3] UINT8
    // Use GetPrimitiveArrayCritical for zero-copy access — avoids ~2.6 MB duplicate
    // native buffer that GetByteArrayElements would create for a 960x960 image.
    jsize dataLen = env->GetArrayLength(jRgbData);

    LOGi("GenerateVision: system=%zu chars, user=%zu chars, image=%dx%d (%d bytes)",
         sysStr.size(), usrStr.size(), (int)width, (int)height, (int)dataLen);

    // Create MNN VARP from raw RGB data
    auto imageVar = MNN::Express::_Input({1, (int)height, (int)width, 3}, MNN::Express::NHWC, halide_type_of<uint8_t>());
    auto imagePtr = imageVar->writeMap<uint8_t>();

    jbyte *rgbBytes = (jbyte*)env->GetPrimitiveArrayCritical(jRgbData, nullptr);
    if (!rgbBytes) { imageVar->unMap(); return nullptr; }
    memcpy(imagePtr, rgbBytes, dataLen);
    env->ReleasePrimitiveArrayCritical(jRgbData, rgbBytes, JNI_ABORT);

    imageVar->unMap();

    // Build MultimodalPrompt with image data in the images map
    MultimodalPrompt mp;
    std::ostringstream prompt;
    prompt << "<|im_start|>system\n" << sysStr << "<|im_end|>\n"
           << "<|im_start|>user\n"
           << "<img>clinical_photo</img>\n"
           << usrStr << "<|im_end|>\n"
           << "<|im_start|>assistant\n";
    mp.prompt_template = prompt.str();

    // Put the image VARP into the images map with the placeholder key
    PromptImagePart imgPart;
    imgPart.image_data = imageVar;
    imgPart.width = (int)width;
    imgPart.height = (int)height;
    mp.images["clinical_photo"] = imgPart;

    g_cancel_generation.store(false);

    CancelCheckBuf buf;
    std::ostream os(&buf);

    g_llm->response(mp, &os, nullptr, g_max_tokens);

    const auto *ctx = g_llm->getContext();
    if (ctx) {
        LOGi("GenerateVision metrics: prompt=%d tokens, decode=%d tokens, first_token_ms=%.1f, total_decode_ms=%.1f, vision_ms=%.1f",
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
    std::lock_guard<std::mutex> lock(g_mutex);
    if (!g_llm) {
        LOGe("applyChatTemplate: model not loaded");
        return nullptr;
    }

    const char *systemPrompt = env->GetStringUTFChars(jSystemPrompt, nullptr);
    if (!systemPrompt) { LOGe("applyChatTemplate: GetStringUTFChars failed for system"); return nullptr; }
    const char *userMessage  = env->GetStringUTFChars(jUserMessage, nullptr);
    if (!userMessage) { env->ReleaseStringUTFChars(jSystemPrompt, systemPrompt); LOGe("applyChatTemplate: GetStringUTFChars failed for user"); return nullptr; }

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
