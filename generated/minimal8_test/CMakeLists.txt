cmake_minimum_required(VERSION 3.16)
project(minimal8_emulator C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

include_directories(include src)


# Source files
set(SOURCES
    src/main.c
    src/Minimal8.c
    src/Minimal8_decoder.c
)

# Create executable
add_executable(minimal8_test ${SOURCES})

# Enable testing
enable_testing()
add_test(NAME basic_test COMMAND minimal8_test --test basic)
