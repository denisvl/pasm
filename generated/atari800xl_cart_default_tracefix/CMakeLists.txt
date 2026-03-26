cmake_minimum_required(VERSION 3.16)
project(mos6502_emulator C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Default to optimized builds for better emulator runtime performance.
if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()


# Emulator library sources
set(EMU_SOURCES
    src/MOS6502.c
    src/MOS6502_decoder.c
    src/MOS6502_debug_abi.c
)

# Linkable emulator library for external tools (debugger/TUI, harnesses).
add_library(mos6502_emu STATIC ${EMU_SOURCES})
target_include_directories(mos6502_emu PUBLIC include src)

# CLI test executable
add_executable(mos6502_test src/main.c)
target_link_libraries(mos6502_test PRIVATE mos6502_emu)
target_include_directories(mos6502_test PRIVATE include src)





# Enable testing
enable_testing()
add_test(NAME basic_test COMMAND mos6502_test --test basic)
