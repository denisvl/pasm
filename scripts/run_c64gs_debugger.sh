#!/usr/bin/env bash
# One-shot helper: generate + build + run PASM C64GS emulator (mos6510_test).
#
# Usage:
#   scripts/run_c64gs_debugger.sh [interactive|default]
#
# Optional env overrides:
#   OUTPUT_DIR=generated/mos6510_c64gs_sdl
#   USE_CARTRIDGE=1|0
#   CARTRIDGE_MAP=examples/cartridges/c64/c64_cart_auto.yaml
#   CARTRIDGE_ROM_GEN=../../roms/c64c/64c.251913-01.bin
#   CARTRIDGE_ROM_RUNTIME=/full/path/to/rom.bin
#   EXTRA_CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=/opt/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-linux"
#   VCPKG_ROOT=/opt/vcpkg
#   VCPKG_TARGET_TRIPLET=x64-linux
#   PASM_SDL_DEBUG=1
#   PASM_SDL_LOGFILE=/tmp/c64gs_sdl.log
#   PASM_SDL_AUDIO=1|0
#   PASM_HOST_AUDIO=1|0
#   PASM_C64_JOY_BUTTONS=1|2   (1=KP0/KP_ENTER, 2=KP1/KP2)
#   HOST_BACKEND=glfw|sdl2|stub
#   KEYBOARD_MAP=examples/hosts/c64/host_keyboard_c64.yaml
#   CONTROLLER_MAP=examples/hosts/c64/host_controller_c64.yaml
#   CMAKE_BUILD_TYPE=Release
#   START_PC=0x0000
#   MEMORY_SIZE=65536
#   EXTRA_CARGO_ARGS=--release
#   RUN_SPEED=realtime|max

set -euo pipefail

PROFILE="${1:-interactive}"

EXTRA_CMAKE_ARGS="${EXTRA_CMAKE_ARGS:-}"
VCPKG_TARGET_TRIPLET="${VCPKG_TARGET_TRIPLET:-x64-linux}"
PASM_SDL_DEBUG="${PASM_SDL_DEBUG:-0}"
PASM_SDL_LOGFILE="${PASM_SDL_LOGFILE:-/tmp/c64gs_sdl.log}"
PASM_SDL_AUDIO="${PASM_SDL_AUDIO:-1}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-$PASM_SDL_AUDIO}"
HOST_BACKEND="${HOST_BACKEND:-glfw}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/c64/host_keyboard_c64.yaml}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/c64/host_controller_c64.yaml}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
USE_CARTRIDGE="${USE_CARTRIDGE:-1}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/c64/c64_cart_auto.yaml}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../../roms/c64c/64c.251913-01.bin}"
CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"
BOOT_CARTRIDGE="${BOOT_CARTRIDGE:-0}"
START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
RUN_SPEED="${RUN_SPEED:-realtime}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
if [[ $? -ne 0 ]]; then exit $?; fi

if [[ -z "${CARTRIDGE_DIR:-}" ]]; then
    CARTRIDGE_DIR="${REPO_ROOT}/examples/roms/c64c"
fi
if [[ -z "${CARTRIDGE_ROM_RUNTIME:-}" ]]; then
    CARTRIDGE_ROM_RUNTIME="${REPO_ROOT}/examples/roms/c64c/64c.251913-01.bin"
fi

PROCESSOR="examples/processors/mos6510.yaml"
IC_VDP="examples/ics/c64/c64_vic_ii_8565.yaml"
IC_SID="examples/ics/c64/c64_sid_8580.yaml"
IC_CIA1="examples/ics/c64/c64_cia1_6526.yaml"
IC_CIA2="examples/ics/c64/c64_cia2_6526.yaml"
IC_MAIN_RAM="examples/ics/c64/c64_main_ram.yaml"
IC_COLOR_RAM="examples/ics/c64/c64_color_ram_2114.yaml"
IC_PLA="examples/ics/c64/c64_pla_8580.yaml"
DEVICE_KB="examples/devices/c64/c64_keyboard.yaml"
DEVICE_CTRL="examples/devices/c64/c64_joystick.yaml"
DEVICE_VIDEO="examples/devices/c64/c64_video.yaml"
DEVICE_TV="examples/devices/common/tv_crt_mono.yaml"
DEVICE_SPK="examples/devices/c64/c64_speaker.yaml"

if [[ "${PROFILE}" == "default" ]]; then
    if [[ "${USE_CARTRIDGE}" == "0" ]]; then
        SYSTEM="examples/systems/c64gs/c64gs_default.yaml"
    else
        SYSTEM="examples/systems/c64gs/c64gs_cartridge_default.yaml"
    fi
    HOST="examples/hosts/c64/c64_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/mos6510_c64gs_default"
elif [[ "${PROFILE}" == "interactive" ]]; then
    if [[ "${USE_CARTRIDGE}" == "0" ]]; then
        SYSTEM="examples/systems/c64gs/c64gs_interactive.yaml"
    else
        SYSTEM="examples/systems/c64gs/c64gs_cartridge_interactive.yaml"
    fi
    HOST="examples/hosts/c64/c64_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/mos6510_c64gs_sdl"
else
    echo "Unsupported profile: ${PROFILE}" >&2
    echo "Use: default | interactive" >&2
    exit 2
fi

gen_default() {
    OUTPUT_DIR="${OUTPUT_DIR:-${DEFAULT_OUTPUT}}"
    BUILD_DIR="${OUTPUT_DIR}/build"

    mkdir -p "$(dirname "${OUTPUT_DIR}")"
    if [[ $? -ne 0 ]]; then exit $?; fi

    if [[ -z "${EXTRA_CMAKE_ARGS:-}" ]]; then
        if [[ -n "${VCPKG_ROOT:-}" ]]; then
            VCPKG_CMAKE_FILE="${VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake"
            if [[ -f "${VCPKG_CMAKE_FILE}" ]]; then
                EXTRA_CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=${VCPKG_CMAKE_FILE} -DVCPKG_TARGET_TRIPLET=${VCPKG_TARGET_TRIPLET}"
            fi
        elif [[ -f "/opt/vcpkg/scripts/buildsystems/vcpkg.cmake" ]]; then
            EXTRA_CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=/opt/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=${VCPKG_TARGET_TRIPLET}"
        fi
    fi

    VCPKG_INSTALLED_TRIPLET_DIR=""
    if [[ -n "${VCPKG_ROOT:-}" ]]; then
        if [[ -d "${VCPKG_ROOT}/installed/${VCPKG_TARGET_TRIPLET}" ]]; then
            VCPKG_INSTALLED_TRIPLET_DIR="${VCPKG_ROOT}/installed/${VCPKG_TARGET_TRIPLET}"
        fi
    elif [[ -d "/opt/vcpkg/installed/${VCPKG_TARGET_TRIPLET}" ]]; then
        VCPKG_INSTALLED_TRIPLET_DIR="/opt/vcpkg/installed/${VCPKG_TARGET_TRIPLET}"
    fi

    if [[ -n "${VCPKG_INSTALLED_TRIPLET_DIR}" ]]; then
        if [[ -f "${VCPKG_INSTALLED_TRIPLET_DIR}/include/SDL2/SDL.h" ]]; then
            export INCLUDE="${VCPKG_INSTALLED_TRIPLET_DIR}/include:${INCLUDE:-}"
        fi
        if [[ -f "${VCPKG_INSTALLED_TRIPLET_DIR}/lib/libSDL2.a" ]]; then
            export LIB="${VCPKG_INSTALLED_TRIPLET_DIR}/lib:${LIB:-}"
        fi
        if [[ -f "${VCPKG_INSTALLED_TRIPLET_DIR}/lib/libSDL2.so" ]]; then
            export LIB="${VCPKG_INSTALLED_TRIPLET_DIR}/lib:${LIB:-}"
        fi
        if [[ -f "${VCPKG_INSTALLED_TRIPLET_DIR}/bin/SDL2" ]]; then
            export PATH="${VCPKG_INSTALLED_TRIPLET_DIR}/bin:${PATH}"
        fi
    fi

    if [[ -z "${PASM_EMU_EXTRA_LIB_DIRS:-}" ]]; then
        if [[ -n "${VCPKG_INSTALLED_TRIPLET_DIR}" ]]; then
            if [[ -d "${VCPKG_INSTALLED_TRIPLET_DIR}/lib" ]]; then
                export PASM_EMU_EXTRA_LIB_DIRS="${VCPKG_INSTALLED_TRIPLET_DIR}/lib"
                if [[ -d "${VCPKG_INSTALLED_TRIPLET_DIR}/debug/lib" ]]; then
                    export PASM_EMU_EXTRA_LIB_DIRS="${PASM_EMU_EXTRA_LIB_DIRS},${VCPKG_INSTALLED_TRIPLET_DIR}/debug/lib"
                fi
            fi
        fi
    fi

    echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
    uv run python -m src.main generate \
        --processor "${PROCESSOR}" \
        --system "${SYSTEM}" \
        --ic "${IC_VDP}" \
        --ic "${IC_SID}" \
        --ic "${IC_CIA1}" \
        --ic "${IC_CIA2}" \
        --ic "${IC_MAIN_RAM}" \
        --ic "${IC_COLOR_RAM}" \
        --ic "${IC_PLA}" \
        --device "${DEVICE_KB}" \
        --device "${DEVICE_CTRL}" \
        --device "${DEVICE_VIDEO}" \
        --device "${DEVICE_TV}" \
        --device "${DEVICE_SPK}" \
        --host "${HOST}" \
        --host-backend "${HOST_BACKEND}" \
        --output "${OUTPUT_DIR}"
    if [[ $? -ne 0 ]]; then
        echo "Generation failed."
        exit 1
    fi

    build_and_run
}

gen_interactive() {
    OUTPUT_DIR="${OUTPUT_DIR:-${DEFAULT_OUTPUT}}"
    BUILD_DIR="${OUTPUT_DIR}/build"

    mkdir -p "$(dirname "${OUTPUT_DIR}")"
    if [[ $? -ne 0 ]]; then exit $?; fi

    if [[ -z "${EXTRA_CMAKE_ARGS:-}" ]]; then
        if [[ -n "${VCPKG_ROOT:-}" ]]; then
            VCPKG_CMAKE_FILE="${VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake"
            if [[ -f "${VCPKG_CMAKE_FILE}" ]]; then
                EXTRA_CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=${VCPKG_CMAKE_FILE} -DVCPKG_TARGET_TRIPLET=${VCPKG_TARGET_TRIPLET}"
            fi
        elif [[ -f "/opt/vcpkg/scripts/buildsystems/vcpkg.cmake" ]]; then
            EXTRA_CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=/opt/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=${VCPKG_TARGET_TRIPLET}"
        fi
    fi

    VCPKG_INSTALLED_TRIPLET_DIR=""
    if [[ -n "${VCPKG_ROOT:-}" ]]; then
        if [[ -d "${VCPKG_ROOT}/installed/${VCPKG_TARGET_TRIPLET}" ]]; then
            VCPKG_INSTALLED_TRIPLET_DIR="${VCPKG_ROOT}/installed/${VCPKG_TARGET_TRIPLET}"
        fi
    elif [[ -d "/opt/vcpkg/installed/${VCPKG_TARGET_TRIPLET}" ]]; then
        VCPKG_INSTALLED_TRIPLET_DIR="/opt/vcpkg/installed/${VCPKG_TARGET_TRIPLET}"
    fi

    if [[ -n "${VCPKG_INSTALLED_TRIPLET_DIR}" ]]; then
        if [[ -f "${VCPKG_INSTALLED_TRIPLET_DIR}/include/SDL2/SDL.h" ]]; then
            export INCLUDE="${VCPKG_INSTALLED_TRIPLET_DIR}/include:${INCLUDE:-}"
        fi
        if [[ -f "${VCPKG_INSTALLED_TRIPLET_DIR}/lib/libSDL2.a" ]]; then
            export LIB="${VCPKG_INSTALLED_TRIPLET_DIR}/lib:${LIB:-}"
        fi
        if [[ -f "${VCPKG_INSTALLED_TRIPLET_DIR}/lib/libSDL2.so" ]]; then
            export LIB="${VCPKG_INSTALLED_TRIPLET_DIR}/lib:${LIB:-}"
        fi
        if [[ -f "${VCPKG_INSTALLED_TRIPLET_DIR}/bin/SDL2" ]]; then
            export PATH="${VCPKG_INSTALLED_TRIPLET_DIR}/bin:${PATH}"
        fi
    fi

    if [[ -z "${PASM_EMU_EXTRA_LIB_DIRS:-}" ]]; then
        if [[ -n "${VCPKG_INSTALLED_TRIPLET_DIR}" ]]; then
            if [[ -d "${VCPKG_INSTALLED_TRIPLET_DIR}/lib" ]]; then
                export PASM_EMU_EXTRA_LIB_DIRS="${VCPKG_INSTALLED_TRIPLET_DIR}/lib"
                if [[ -d "${VCPKG_INSTALLED_TRIPLET_DIR}/debug/lib" ]]; then
                    export PASM_EMU_EXTRA_LIB_DIRS="${PASM_EMU_EXTRA_LIB_DIRS},${VCPKG_INSTALLED_TRIPLET_DIR}/debug/lib"
                fi
            fi
        fi
    fi

    echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
    if [[ "${USE_CARTRIDGE}" == "0" ]]; then
        uv run python -m src.main generate \
            --processor "${PROCESSOR}" \
            --system "${SYSTEM}" \
            --ic "${IC_VDP}" \
            --ic "${IC_SID}" \
            --ic "${IC_CIA1}" \
            --ic "${IC_CIA2}" \
            --ic "${IC_MAIN_RAM}" \
            --ic "${IC_COLOR_RAM}" \
            --ic "${IC_PLA}" \
            --device "${DEVICE_KB}" \
            --device "${DEVICE_CTRL}" \
            --device "${DEVICE_VIDEO}" \
            --device "${DEVICE_TV}" \
            --device "${DEVICE_SPK}" \
            --host "${HOST}" \
            --host-backend "${HOST_BACKEND}" \
            --output "${OUTPUT_DIR}"
    else
        uv run python -m src.main generate \
            --processor "${PROCESSOR}" \
            --system "${SYSTEM}" \
            --ic "${IC_VDP}" \
            --ic "${IC_SID}" \
            --ic "${IC_CIA1}" \
            --ic "${IC_CIA2}" \
            --ic "${IC_MAIN_RAM}" \
            --ic "${IC_COLOR_RAM}" \
            --ic "${IC_PLA}" \
            --device "${DEVICE_KB}" \
            --device "${DEVICE_CTRL}" \
            --device "${DEVICE_VIDEO}" \
            --device "${DEVICE_TV}" \
            --device "${DEVICE_SPK}" \
            --host "${HOST}" \
            --host-backend "${HOST_BACKEND}" \
            --cartridge-map "${CARTRIDGE_MAP}" \
            --cartridge-rom "${CARTRIDGE_ROM_GEN}" \
            --output "${OUTPUT_DIR}"
    fi
    if [[ $? -ne 0 ]]; then
        echo "Generation failed."
        exit 1
    fi

    build_and_run
}

build_and_run() {
    echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
    cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}" ${EXTRA_CMAKE_ARGS}
    if [[ $? -ne 0 ]]; then
        echo "CMake configure failed; clearing ${BUILD_DIR} and retrying once..."
        rm -rf "${BUILD_DIR}"
        cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}" ${EXTRA_CMAKE_ARGS}
        if [[ $? -ne 0 ]]; then exit 1; fi
    fi
    cmake --build "${BUILD_DIR}" --config "${CMAKE_BUILD_TYPE}"
    if [[ $? -ne 0 ]]; then exit 1; fi

    if [[ "${PROFILE}" == "interactive" ]]; then
        # Interactive profile: run Rust TUI debugger
        echo "[3/3] Running Rust debugger (linked backend)"
        echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} sdl_audio=${PASM_SDL_AUDIO} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
        if [[ "${USE_CARTRIDGE}" != "0" ]]; then
          echo "    cartridge_map=${CARTRIDGE_MAP}"
          echo "    cartridge_rom_gen=${CARTRIDGE_ROM_GEN}"
          echo "    cartridge_rom_runtime=${CARTRIDGE_ROM_RUNTIME}"
        fi
        if [[ "${PASM_SDL_DEBUG}" != "0" ]]; then
          echo "    SDL debug log -> ${PASM_SDL_LOGFILE}"
        fi

        BUILD_DIR_ABS="$(cd "${BUILD_DIR}" && pwd)"
        CMAKE_CONFIG_BUILD_DIR="${BUILD_DIR}/${CMAKE_BUILD_TYPE}"
        CMAKE_CONFIG_BUILD_DIR_ABS="$(cd "${CMAKE_CONFIG_BUILD_DIR}" 2>/dev/null && pwd)"
        OUTPUT_DIR_ABS="$(cd "${OUTPUT_DIR}" && pwd)"
        export PASM_EMU_DIR="${OUTPUT_DIR_ABS}"
        export PASM_EMU_BUILD_DIR="${BUILD_DIR_ABS}"
        if [[ -d "${CMAKE_CONFIG_BUILD_DIR}" ]]; then
            export PASM_EMU_BUILD_DIR="${CMAKE_CONFIG_BUILD_DIR_ABS}"
        fi
        export PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json"
        export PASM_SDL_DEBUG="${PASM_SDL_DEBUG}"
        export PASM_SDL_LOGFILE="${PASM_SDL_LOGFILE}"
        export PASM_SDL_AUDIO="${PASM_SDL_AUDIO}"
        export PASM_HOST_DEBUG="${PASM_SDL_DEBUG}"
        export PASM_HOST_LOGFILE="${PASM_SDL_LOGFILE}"
        export PASM_HOST_AUDIO="${PASM_HOST_AUDIO}"

        CARGO_BIN="cargo"
        if ! command -v cargo >/dev/null 2>&1; then
            if [[ -f "${HOME}/.cargo/bin/cargo" ]]; then
                CARGO_BIN="${HOME}/.cargo/bin/cargo"
            else
                echo "cargo executable not found." >&2
                echo "Install Rust with rustup, or add \"${HOME}/.cargo/bin\" to PATH." >&2
                exit 3
            fi
        fi

        SYSTEM_DIR="examples/systems/c64gs"
        if [[ "${USE_CARTRIDGE}" == "0" ]]; then
            "${CARGO_BIN}" run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
                --backend linked \
                --memory-size "${MEMORY_SIZE}" \
                --system-dir "${SYSTEM_DIR}" \
                --keyboard-map "${KEYBOARD_MAP}" \
                --controller-map "${CONTROLLER_MAP}" \
                --start-pc "${START_PC}" \
                --run-speed "${RUN_SPEED}" \
                --auto-run
        else
            if [[ "${BOOT_CARTRIDGE}" == "0" ]]; then
                "${CARGO_BIN}" run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
                    --backend linked \
                    --memory-size "${MEMORY_SIZE}" \
                    --system-dir "${SYSTEM_DIR}" \
                    --cartridge-dir "${CARTRIDGE_DIR}" \
                    --keyboard-map "${KEYBOARD_MAP}" \
                    --controller-map "${CONTROLLER_MAP}" \
                    --start-pc "${START_PC}" \
                    --run-speed "${RUN_SPEED}" \
                    --auto-run
            else
                "${CARGO_BIN}" run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
                    --backend linked \
                    --memory-size "${MEMORY_SIZE}" \
                    --system-dir "${SYSTEM_DIR}" \
                    --cartridge-dir "${CARTRIDGE_DIR}" \
                    --cart-rom "${CARTRIDGE_ROM_RUNTIME}" \
                    --keyboard-map "${KEYBOARD_MAP}" \
                    --controller-map "${CONTROLLER_MAP}" \
                    --start-pc "${START_PC}" \
                    --run-speed "${RUN_SPEED}" \
                    --auto-run
            fi
        fi
        exit $?
    else
        # Default profile: run mos6510_test.exe directly
        echo "[3/3] Running emulator (mos6510_test)"
        echo "    profile=${PROFILE} sdl_audio=${PASM_SDL_AUDIO} cmake_build_type=${CMAKE_BUILD_TYPE}"
        if [[ "${USE_CARTRIDGE}" != "0" ]]; then
          echo "    cartridge_map=${CARTRIDGE_MAP}"
          echo "    cartridge_rom_gen=${CARTRIDGE_ROM_GEN}"
          echo "    cartridge_rom_runtime=${CARTRIDGE_ROM_RUNTIME}"
        fi

        BUILD_DIR_ABS="$(cd "${BUILD_DIR}" && pwd)"
        CMAKE_CONFIG_BUILD_DIR="${BUILD_DIR}/${CMAKE_BUILD_TYPE}"
        CMAKE_CONFIG_BUILD_DIR_ABS="$(cd "${CMAKE_CONFIG_BUILD_DIR}" 2>/dev/null && pwd)"
        OUTPUT_DIR_ABS="$(cd "${OUTPUT_DIR}" && pwd)"
        export PASM_EMU_DIR="${OUTPUT_DIR_ABS}"
        export PASM_EMU_BUILD_DIR="${BUILD_DIR_ABS}"
        if [[ -d "${CMAKE_CONFIG_BUILD_DIR}" ]]; then
            export PASM_EMU_BUILD_DIR="${CMAKE_CONFIG_BUILD_DIR_ABS}"
        fi
        export PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json"
        export PASM_SDL_DEBUG="${PASM_SDL_DEBUG}"
        export PASM_SDL_LOGFILE="${PASM_SDL_LOGFILE}"
        export PASM_SDL_AUDIO="${PASM_SDL_AUDIO}"
        export PASM_HOST_DEBUG="${PASM_SDL_DEBUG}"
        export PASM_HOST_LOGFILE="${PASM_SDL_LOGFILE}"
        export PASM_HOST_AUDIO="${PASM_HOST_AUDIO}"

        EXE_PATH="${CMAKE_CONFIG_BUILD_DIR}/mos6510_test"
        if [[ ! -f "${EXE_PATH}" ]]; then
          EXE_PATH="${BUILD_DIR}/mos6510_test"
        fi
        if [[ ! -f "${EXE_PATH}" ]]; then
          echo "Executable not found: ${EXE_PATH}" >&2
          exit 1
        fi

        SYSTEM_DIR="examples/systems/c64gs"
        "${EXE_PATH}" --run --system-dir "${SYSTEM_DIR}" --keyboard-map "${KEYBOARD_MAP}"
        exit $?
    fi
}

# Entry point - call the appropriate gen function
if [[ "${PROFILE}" == "default" ]]; then
    gen_default
else
    gen_interactive
fi
