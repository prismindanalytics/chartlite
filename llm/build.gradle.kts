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
    // Used by `GemmaBridge.kt`. Kotlin/Java SDK; no JNI needed at this layer
    // because MediaPipe ships native libs inside the AAR.
    //
    // 0.10.20+ exposes vision modality on LlmInferenceSession
    // (GraphOptions.setEnableVisionModality + addImage). Pinning to the latest
    // stable (0.10.35, released April 2026) for the most reliable Gemma 3n
    // vision path on mid-tier Android.
    implementation("com.google.mediapipe:tasks-genai:0.10.35")

    // tasks-vision ships the `com.google.mediapipe.framework.image` package
    // (BitmapImageBuilder, MPImage) that we use to wrap a Bitmap before passing
    // it to LlmInferenceSession.addImage(). Kept on the same minor as tasks-genai.
    implementation("com.google.mediapipe:tasks-vision:0.10.35")
}
