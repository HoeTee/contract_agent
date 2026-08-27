cmake_minimum_required(VERSION 3.18)
project(lexora_loader LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_C_STANDARD 11)

if(NOT DEFINED KEY_HEADER_DIR)
    message(FATAL_ERROR "KEY_HEADER_DIR must point to the generated key_data.h directory")
endif()
if(NOT DEFINED VMP_SDK_INCLUDE)
    message(FATAL_ERROR "VMP_SDK_INCLUDE must point to the VMProtect SDK include directory")
endif()
if(NOT DEFINED VMP_SDK_LIB)
    message(FATAL_ERROR "VMP_SDK_LIB must point to libVMProtectSDK64.so")
endif()

find_package(Python3 3.12 EXACT REQUIRED COMPONENTS Development.Embed)
find_package(OpenSSL REQUIRED COMPONENTS Crypto)

add_executable(loader
    src/main.cpp
    src/loader_entry.cpp
    src/crypto.cpp
    src/importer.cpp
)

target_include_directories(loader PRIVATE src "${KEY_HEADER_DIR}")
target_link_libraries(loader PRIVATE Python3::Python OpenSSL::Crypto)
target_compile_options(loader PRIVATE -O3 -flto -fvisibility=hidden -fno-ident)
target_link_options(loader PRIVATE -flto -Wl,--strip-all)

# Shared library that carries the sensitive loader logic and is VMProtect-packed
# before deployment; host loads it via dlopen.
add_library(loader_so SHARED
    src/loader_entry.cpp
    src/crypto.cpp
    src/importer.cpp
)
set_target_properties(loader_so PROPERTIES OUTPUT_NAME loader)
target_include_directories(loader_so PRIVATE src "${KEY_HEADER_DIR}" "${VMP_SDK_INCLUDE}")
target_link_libraries(loader_so PRIVATE Python3::Python OpenSSL::Crypto "${VMP_SDK_LIB}")
target_compile_options(loader_so PRIVATE -O3 -fvisibility=hidden -fno-ident)

add_executable(host src/host.c)
target_link_libraries(host PRIVATE ${CMAKE_DL_LIBS})
target_compile_options(host PRIVATE -O2 -fno-ident)
