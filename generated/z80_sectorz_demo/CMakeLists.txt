cmake_minimum_required(VERSION 3.16)
project(z80_emulator C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

include_directories(include src)


# Source files
set(SOURCES
    src/main.c
    src/Z80.c
    src/Z80_decoder.c
    src/Z80_hooks.c
)

# Create executable
add_executable(z80_test ${SOURCES})

# Enable testing
enable_testing()
add_test(NAME basic_test COMMAND z80_test --test basic)
