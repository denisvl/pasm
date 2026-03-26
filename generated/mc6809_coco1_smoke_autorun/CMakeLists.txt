cmake_minimum_required(VERSION 3.16)
project(mc6809_emulator C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Default to optimized builds for better emulator runtime performance.
if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()


# Emulator library sources
set(EMU_SOURCES
    src/MC6809.c
    src/MC6809_decoder.c
    src/MC6809_debug_abi.c
)

# Linkable emulator library for external tools (debugger/TUI, harnesses).
add_library(mc6809_emu STATIC ${EMU_SOURCES})
target_include_directories(mc6809_emu PUBLIC include src)

# CLI test executable
add_executable(mc6809_test src/main.c)
target_link_libraries(mc6809_test PRIVATE mc6809_emu)
target_include_directories(mc6809_test PRIVATE include src)

target_include_directories(mc6809_test PRIVATE
    "D:/Projects/pasm/examples/hosts/include"
)
target_include_directories(mc6809_emu PRIVATE
    "D:/Projects/pasm/examples/hosts/include"
)




# Enable testing
enable_testing()
add_test(NAME basic_test COMMAND mc6809_test --test basic)
