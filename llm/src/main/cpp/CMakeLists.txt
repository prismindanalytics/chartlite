cmake_minimum_required(VERSION 3.22.1)
project("chartlite-llm" VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED true)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED true)

# ABI-specific flags
if(ANDROID_ABI STREQUAL "arm64-v8a")
    set(GGML_OPENMP ON CACHE BOOL "" FORCE)
    # Explicit NEON/FP16 — baseline ARMv8-A always has NEON but the compiler
    # may not emit optimal sequences without the flag. We intentionally omit
    # +dotprod since not all A55 cores support it (e.g. some Unisoc T603 SKUs).
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -march=armv8-a+fp16")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -march=armv8-a+fp16")
elseif(ANDROID_ABI STREQUAL "armeabi-v7a")
    set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
elseif(ANDROID_ABI STREQUAL "x86_64")
    set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
endif()

# llama.cpp source tree (git submodule at external/llama.cpp)
set(LLAMA_SRC "${CMAKE_CURRENT_LIST_DIR}/../../../../external/llama.cpp")

# Build llama.cpp as a subdirectory
set(LLAMA_BUILD_COMMON ON CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER OFF CACHE BOOL "" FORCE)
add_subdirectory(${LLAMA_SRC} build-llama EXCLUDE_FROM_ALL)

# Our JNI bridge
add_library(${CMAKE_PROJECT_NAME} SHARED
    chartlite_llm.cpp
)

target_include_directories(${CMAKE_PROJECT_NAME} PRIVATE
    ${LLAMA_SRC}/include
    ${LLAMA_SRC}/common
    ${LLAMA_SRC}/ggml/include
)

target_link_libraries(${CMAKE_PROJECT_NAME}
    llama
    common
    android
    log
)
