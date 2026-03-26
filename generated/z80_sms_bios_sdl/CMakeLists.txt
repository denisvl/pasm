cmake_minimum_required(VERSION 3.16)
project(z80_emulator C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Default to optimized builds for better emulator runtime performance.
if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()


# Emulator library sources
set(EMU_SOURCES
    src/Z80.c
    src/Z80_decoder.c
    src/Z80_debug_abi.c
)

# Linkable emulator library for external tools (debugger/TUI, harnesses).
add_library(z80_emu STATIC ${EMU_SOURCES})
target_include_directories(z80_emu PUBLIC include src)

# CLI test executable
add_executable(z80_test src/main.c)
target_link_libraries(z80_test PRIVATE z80_emu)
target_include_directories(z80_test PRIVATE include src)


target_link_libraries(z80_test PRIVATE
    SDL2
)
target_link_libraries(z80_emu PRIVATE
    SDL2
)


# Enable testing
enable_testing()
add_test(NAME basic_test COMMAND z80_test --test basic)
