cmake_minimum_required(VERSION 3.16)
project(mos6510_emulator C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

include_directories(include src)


# Source files
set(SOURCES
    src/main.c
    src/MOS6510.c
    src/MOS6510_decoder.c
)

# Create executable
add_executable(mos6510_test ${SOURCES})

# Enable testing
enable_testing()
add_test(NAME basic_test COMMAND mos6510_test --test basic)
