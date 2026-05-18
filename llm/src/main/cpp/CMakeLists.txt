cmake_minimum_required(VERSION 3.22.1)
project("chartlite-llm" VERSION 2.0.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED true)

include(FetchContent)

# MNN source tree (git submodule at external/MNN)
set(MNN_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../../external/MNN")

# MNN build flags for LLM on mobile
set(MNN_BUILD_LLM ON CACHE BOOL "" FORCE)
set(MNN_LOW_MEMORY ON CACHE BOOL "" FORCE)
set(MNN_CPU_WEIGHT_DEQUANT_GEMM ON CACHE BOOL "" FORCE)
set(MNN_SUPPORT_TRANSFORMER_FUSE ON CACHE BOOL "" FORCE)
set(MNN_SEP_BUILD ON CACHE BOOL "" FORCE)
set(MNN_BUILD_SHARED_LIBS ON CACHE BOOL "" FORCE)
set(MNN_BUILD_DEMO OFF CACHE BOOL "" FORCE)
set(MNN_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
set(MNN_BUILD_TEST OFF CACHE BOOL "" FORCE)
set(MNN_BUILD_BENCHMARK OFF CACHE BOOL "" FORCE)
set(MNN_BUILD_QUANTOOLS OFF CACHE BOOL "" FORCE)
set(MNN_BUILD_CONVERTER OFF CACHE BOOL "" FORCE)
set(MNN_USE_LOGCAT ON CACHE BOOL "" FORCE)

# Vision support — enables MNN::CV::imread + vision encoder in omni.cpp
set(MNN_BUILD_OPENCV ON CACHE BOOL "" FORCE)
set(MNN_IMGCODECS ON CACHE BOOL "" FORCE)

# ABI-specific optimizations
if(ANDROID_ABI STREQUAL "arm64-v8a")
    set(MNN_ARM82 ON CACHE BOOL "" FORCE)
    set(MNN_OPENCL ON CACHE BOOL "" FORCE)
    set(MNN_KLEIDIAI ON CACHE BOOL "" FORCE)
    set(MNN_VULKAN ON CACHE BOOL "" FORCE)
endif()

set(CHARTLITE_LLAMA_AVAILABLE OFF)
if(NOT ANDROID_ABI STREQUAL "armeabi-v7a")
    set(LLAMA_CPP_TAG "b8559")
    set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(LLAMA_BUILD_SERVER OFF CACHE BOOL "" FORCE)
    set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
    if(ANDROID_ABI STREQUAL "arm64-v8a")
        set(GGML_CPU_KLEIDIAI ON CACHE BOOL "" FORCE)
    else()
        set(GGML_CPU_KLEIDIAI OFF CACHE BOOL "" FORCE)
    endif()

    file(GLOB LLAMA_CPP_SOURCE_HINTS
        "${CMAKE_CURRENT_LIST_DIR}/../../../../benchmark/.cxx/*/*/*/_deps/llama_cpp-src/CMakeLists.txt"
    )
    list(LENGTH LLAMA_CPP_SOURCE_HINTS LLAMA_CPP_SOURCE_HINT_COUNT)
    if(LLAMA_CPP_SOURCE_HINT_COUNT GREATER 0)
        list(GET LLAMA_CPP_SOURCE_HINTS 0 LLAMA_CPP_SOURCE_HINT_CMAKE)
        get_filename_component(FETCHCONTENT_SOURCE_DIR_LLAMA_CPP "${LLAMA_CPP_SOURCE_HINT_CMAKE}" DIRECTORY)
        message(STATUS "Using cached llama.cpp source from ${FETCHCONTENT_SOURCE_DIR_LLAMA_CPP}")
    endif()

    FetchContent_Declare(
        llama_cpp
        GIT_REPOSITORY https://github.com/ggml-org/llama.cpp.git
        GIT_TAG        ${LLAMA_CPP_TAG}
        GIT_SHALLOW    TRUE
        GIT_PROGRESS   TRUE
    )
    FetchContent_MakeAvailable(llama_cpp)
    set(CHARTLITE_LLAMA_AVAILABLE ON)
endif()

# Android 15+ 16KB page size support
set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} -Wl,-z,max-page-size=16384")

# Build MNN from source
add_subdirectory(${MNN_ROOT} ${CMAKE_BINARY_DIR}/mnn EXCLUDE_FROM_ALL)

# Our JNI bridge
add_library(${CMAKE_PROJECT_NAME} SHARED
    chartlite_mnn.cpp
    chartlite_llama_backend.cpp
)

target_include_directories(${CMAKE_PROJECT_NAME} PRIVATE
    ${MNN_ROOT}/include
    ${MNN_ROOT}/transformers/llm/engine/include
)

if(CHARTLITE_LLAMA_AVAILABLE)
    target_include_directories(${CMAKE_PROJECT_NAME} PRIVATE
        ${llama_cpp_SOURCE_DIR}/include
        ${llama_cpp_SOURCE_DIR}/ggml/include
    )
    target_compile_definitions(${CMAKE_PROJECT_NAME} PRIVATE CHARTLITE_LLAMA_AVAILABLE=1)
endif()

target_link_libraries(${CMAKE_PROJECT_NAME}
    MNN
    MNNOpenCV
    llm
    android
    log
)

if(CHARTLITE_LLAMA_AVAILABLE)
    target_link_libraries(${CMAKE_PROJECT_NAME}
        llama
        ggml
        ggml-cpu
    )
endif()
