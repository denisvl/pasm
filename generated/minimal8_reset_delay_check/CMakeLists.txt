cmake_minimum_required(VERSION 3.16)
project(minimal8_emulator C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Default to optimized builds for better emulator runtime performance.
if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()


# Emulator library sources
set(EMU_SOURCES
    src/Minimal8.c
    src/Minimal8_decoder.c
    src/Minimal8_debug_abi.c
)

# Linkable emulator library for external tools (debugger/TUI, harnesses).
add_library(minimal8_emu STATIC ${EMU_SOURCES})
target_include_directories(minimal8_emu PUBLIC include src)

# CLI test executable
add_executable(minimal8_test src/main.c)
target_link_libraries(minimal8_test PRIVATE minimal8_emu)
target_include_directories(minimal8_test PRIVATE include src)





# Enable testing
enable_testing()
add_test(NAME basic_test COMMAND minimal8_test --test basic)
