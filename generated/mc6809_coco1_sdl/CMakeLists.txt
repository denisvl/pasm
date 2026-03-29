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

if(NOT DEFINED PASM_VCPKG_TRIPLET OR PASM_VCPKG_TRIPLET STREQUAL "")
    if(DEFINED ENV{VCPKG_TARGET_TRIPLET} AND NOT "$ENV{VCPKG_TARGET_TRIPLET}" STREQUAL "")
        set(PASM_VCPKG_TRIPLET "$ENV{VCPKG_TARGET_TRIPLET}")
    elseif(WIN32)
        set(PASM_VCPKG_TRIPLET "x64-windows")
    elseif(APPLE)
        set(PASM_VCPKG_TRIPLET "x64-osx")
    else()
        set(PASM_VCPKG_TRIPLET "x64-linux")
    endif()
endif()

if(NOT TARGET SDL2::SDL2)
    find_package(SDL2 CONFIG QUIET)
endif()

set(PASM_SDL2_LINK_TARGET SDL2)
if(TARGET SDL2::SDL2)
    set(PASM_SDL2_LINK_TARGET SDL2::SDL2)
else()
    set(PASM_VCPKG_ROOT_HINT "")
    if(DEFINED ENV{VCPKG_ROOT} AND NOT "$ENV{VCPKG_ROOT}" STREQUAL "")
        set(PASM_VCPKG_ROOT_HINT "$ENV{VCPKG_ROOT}")
    elseif(EXISTS "D:/Development/vcpkg")
        set(PASM_VCPKG_ROOT_HINT "D:/Development/vcpkg")
    elseif(EXISTS "C:/vcpkg")
        set(PASM_VCPKG_ROOT_HINT "C:/vcpkg")
    endif()

    if(NOT PASM_VCPKG_ROOT_HINT STREQUAL "")
        set(PASM_VCPKG_BASE "${PASM_VCPKG_ROOT_HINT}/installed/${PASM_VCPKG_TRIPLET}")
        find_path(PASM_SDL2_INCLUDE_DIR SDL2/SDL.h
            HINTS "${PASM_VCPKG_BASE}/include"
        )
        if(PASM_SDL2_INCLUDE_DIR)
            target_include_directories(mc6809_test PRIVATE "${PASM_SDL2_INCLUDE_DIR}")
            target_include_directories(mc6809_emu PRIVATE "${PASM_SDL2_INCLUDE_DIR}")
        endif()

        find_library(PASM_SDL2_LIBRARY NAMES SDL2
            HINTS "${PASM_VCPKG_BASE}/lib" "${PASM_VCPKG_BASE}/debug/lib"
        )
        if(PASM_SDL2_LIBRARY)
            set(PASM_SDL2_LINK_TARGET "${PASM_SDL2_LIBRARY}")
        endif()
    endif()
endif()

target_include_directories(mc6809_test PRIVATE
    "/home/dvlop/projects/pasm/examples/ics/hosts/include"
    "/home/dvlop/projects/pasm/examples/devices/hosts/include"
    "/home/dvlop/projects/pasm/examples/hosts/include"
)
target_include_directories(mc6809_emu PRIVATE
    "/home/dvlop/projects/pasm/examples/ics/hosts/include"
    "/home/dvlop/projects/pasm/examples/devices/hosts/include"
    "/home/dvlop/projects/pasm/examples/hosts/include"
)


target_link_libraries(mc6809_test PRIVATE
    ${PASM_SDL2_LINK_TARGET}
)
target_link_libraries(mc6809_emu PRIVATE
    ${PASM_SDL2_LINK_TARGET}
)


# Enable testing
enable_testing()
add_test(NAME basic_test COMMAND mc6809_test --test basic)
