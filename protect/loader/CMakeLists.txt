cmake_minimum_required(VERSION 3.18)
project(lexora_loader LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(NOT DEFINED KEY_HEADER_DIR)
    message(FATAL_ERROR "KEY_HEADER_DIR must point to the generated key_data.h directory")
endif()

find_package(Python3 3.12 EXACT REQUIRED COMPONENTS Development.Embed)
find_package(OpenSSL REQUIRED COMPONENTS Crypto)

add_executable(loader
    src/main.cpp
    src/crypto.cpp
    src/importer.cpp
)

target_include_directories(loader PRIVATE src "${KEY_HEADER_DIR}")
target_link_libraries(loader PRIVATE Python3::Python OpenSSL::Crypto)
target_compile_options(loader PRIVATE -O3 -flto -fvisibility=hidden -fno-ident)
target_link_options(loader PRIVATE -flto -Wl,--strip-all)
