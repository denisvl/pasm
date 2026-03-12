cmake_minimum_required(VERSION 3.16)
project(simple8_emulator C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

include_directories(include src)


# Source files
set(SOURCES
    src/main.c
    src/Simple8.c
    src/Simple8_decoder.c
)

# Create executable
add_executable(simple8_test ${SOURCES})

# Enable testing
enable_testing()
add_test(NAME basic_test COMMAND simple8_test --test basic)
