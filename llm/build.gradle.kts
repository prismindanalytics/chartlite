plugins {
    alias(libs.plugins.android.library)
}

android {
    namespace = "com.chartlite.llm"
    compileSdk = 36

    defaultConfig {
        minSdk = 26
        ndk {
            // Include 32-bit for install compatibility on older devices.
            // Runtime gating in LlmModelManager keeps on-device LLM disabled on unsupported ABIs.
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
        externalNativeBuild {
            cmake {
                arguments += listOf(
                    "-DCMAKE_BUILD_TYPE=Release",
                    "-DBUILD_SHARED_LIBS=ON",
                )
            }
        }
    }

    externalNativeBuild {
        cmake {
            path("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    // Kotlin 2.x removed the `kotlinOptions { jvmTarget = "17" }` DSL when the
    // Kotlin plugin isn't applied directly to a module. The Java 17
    // compileOptions above are enough — Kotlin's toolchain follows the AGP setting.
}

dependencies {
    // MediaPipe LLM Inference — on-device runtime for Gemma 3n .task bundles.
    // LiteRT-LM is Google's on-device LLM runtime that loads the modern `.task`
    // bundles published by `litert-community` on Hugging Face (gemma-4 series).
    // We migrated off the older `com.google.mediapipe:tasks-genai:0.10.35` on
    // 2026-05-18 because that SDK's litert_lm/zip_utils could not open the
    // current Gemma 4 .task format (error: "Unable to open zip archive"). The
    // `litertlm-android` AAR ships its own native libs, so no JNI work here.
    //
    // Used by `GemmaBridge.kt` (text + vision generation).
    implementation("com.google.ai.edge.litertlm:litertlm-android:0.11.0")
}
