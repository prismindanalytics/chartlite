#pragma once

#include <string>

namespace chartlite::llama_backend {

bool init_model(const std::string& model_path);

void update_generate_params(
    float temperature,
    int max_tokens,
    float top_p,
    int top_k,
    float repeat_penalty
);

std::string generate(const std::string& prompt);

std::string generate_chat(
    const std::string& system_prompt,
    const std::string& user_message,
    bool enable_thinking
);

std::string apply_chat_template(
    const std::string& system_prompt,
    const std::string& user_message,
    bool enable_thinking
);

void cancel_generation();

void shutdown();

} // namespace chartlite::llama_backend
