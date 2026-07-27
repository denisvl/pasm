#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for MSX1 Expanded.
#
# Usage:
#   scripts/run_msx1_expanded_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0x0000
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/z80_msx1_expanded_interactive
#   EXTRA_CARGO_ARGS="--release"
#   USE_CARTRIDGE=1|0
#   CARTRIDGE_MAP=examples/cartridges/msx1/msx_mapper_konami.yaml
#   CARTRIDGE_ROM_GEN=../roms/msx1/Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom
#   CARTRIDGE_ROM_RUNTIME=/abs/path/to/rom.rom
#   EXTRA_CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=/opt/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-linux"
#   VCPKG_ROOT=/opt/vcpkg
#   VCPKG_TARGET_TRIPLET=x64-linux
#   PASM_SDL_DEBUG=1
#   PASM_SDL_LOGFILE=/tmp/msx1_expanded_sdl.log
#   PASM_SDL_AUDIO=1|0
#   PASM_HOST_AUDIO=1|0
#   PASM_MSX_JOY_BUTTONS=1|2   (1=KP0/KP_ENTER, 2=KP1/KP2)
#   HOST_BACKEND=glfw|sdl2|stub
#   KEYBOARD_MAP=examples/hosts/msx1/host_keyboard_msx.yaml
#   CONTROLLER_MAP=examples/hosts/msx1/host_controller_msx1.yaml
#   CMAKE_BUILD_TYPE=Release
#   RUN_SPEED=realtime|max

PROFILE="${1:-interactive}"

START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
EXTRA_CMAKE_ARGS="${EXTRA_CMAKE_ARGS:-}"
VCPKG_TARGET_TRIPLET="${VCPKG_TARGET_TRIPLET:-x64-linux}"
PASM_SDL_DEBUG="${PASM_SDL_DEBUG:-0}"
PASM_SDL_LOGFILE="${PASM_SDL_LOGFILE:-/tmp/msx1_expanded_sdl.log}"
PASM_SDL_AUDIO="${PASM_SDL_AUDIO:-1}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-$PASM_SDL_AUDIO}"
HOST_BACKEND="${HOST_BACKEND:-glfw}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/msx1/host_keyboard_msx.yaml}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/msx1/host_controller_msx1.yaml}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
USE_CARTRIDGE="${USE_CARTRIDGE:-1}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/msx1/msx_mapper_konami.yaml}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../../roms/msx1/Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom}"
CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"
CARTRIDGE_DIR="${CARTRIDGE_DIR:-}"
BOOT_CARTRIDGE="${BOOT_CARTRIDGE:-0}"
PASM_EMU_CART_PICKER_RAW_KEYS="${PASM_EMU_CART_PICKER_RAW_KEYS:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

PROCESSOR="examples/processors/z80.yaml"
IC_VDP="examples/ics/msx1/msx1_vdp_tms9918a.yaml"
IC_PPI="examples/ics/msx1/msx1_ppi_8255_expanded.yaml"
IC_PSG="examples/ics/msx1/msx1_psg_ay8910.yaml"
IC_MAIN_RAM="examples/ics/msx1/msx1_main_ram.yaml"
IC_EXPANDED_SLOT="examples/ics/msx1/msx1_expanded_slot_controller.yaml"
DEVICE_KB="examples/devices/msx1/msx_keyboard.yaml"
DEVICE_CTRL="examples/devices/msx1/msx_controller.yaml"
DEVICE_VIDEO="examples/devices/msx1/msx_video.yaml"
DEVICE_SPK="examples/devices/msx1/msx_speaker.yaml"
DEVICE_CASSETTE="examples/devices/common/cassette_transport.yaml"
DEVICE_TV="examples/devices/common/tv_crt_mono.yaml"
SYSTEM_DIR="examples/systems/msx1"

case "${PROFILE}" in
  default)
    if [[ "${USE_CARTRIDGE}" != "0" ]]; then
      SYSTEM="examples/systems/msx1/msx1_expanded_cartridge_default.yaml"
    else
      SYSTEM="examples/systems/msx1/msx1_expanded_default.yaml"
    fi
    HOST="examples/hosts/msx1/msx_host_stub.yaml"
    DEFAULT_OUTPUT="generated/z80_msx1_expanded_default"
    ;;
  interactive)
    if [[ "${USE_CARTRIDGE}" != "0" ]]; then
      SYSTEM="examples/systems/msx1/msx1_expanded_cartridge_interactive.yaml"
    else
      SYSTEM="examples/systems/msx1/msx1_expanded_interactive.yaml"
    fi
    HOST="examples/hosts/msx1/msx_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/z80_msx1_expanded_interactive"
    ;;
  *)
    echo "Unsupported profile: ${PROFILE}" >&2
    echo "Use: default | interactive" >&2
    exit 2
    ;;
esac

OUTPUT_DIR="${OUTPUT_DIR:-${DEFAULT_OUTPUT}}"
BUILD_DIR="${OUTPUT_DIR}/build"
mkdir -p "$(dirname "${OUTPUT_DIR}")"
OUTPUT_DIR_ABS="$(cd "$(dirname "${OUTPUT_DIR}")" && pwd)/$(basename "${OUTPUT_DIR}")"
SYSTEM_DIR_ABS="$(cd "$(dirname "${SYSTEM}")" && pwd)"
if [[ -z "${CARTRIDGE_ROM_RUNTIME}" ]]; then
  CARTRIDGE_ROM_RUNTIME="${REPO_ROOT}/examples/roms/msx1/Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom"
fi
if [[ -z "${CARTRIDGE_ROM_GEN}" ]]; then
  CARTRIDGE_ROM_GEN="../../roms/msx1/Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom"
fi

# Determine output directory based on profile
if [[ "${PROFILE}" == "interactive" ]]; then
  OUTPUT_DIR="${OUTPUT_DIR:-generated/z80_msx1_expanded_interactive}"
else
  OUTPUT_DIR="${OUTPUT_DIR:-generated/z80_msx1_expanded_default}"
fi
BUILD_DIR="${OUTPUT_DIR}/build"
mkdir -p "$(dirname "${OUTPUT_DIR}")"
OUTPUT_DIR_ABS="$(cd "$(dirname "${OUTPUT_DIR}")" && pwd)/$(basename "${OUTPUT_DIR}")"

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
    --ic "${IC_PPI}" \
    --ic "${IC_PSG}" \
    --ic "${IC_MAIN_RAM}" \
    --ic "${IC_EXPANDED_SLOT}" \
    --device "${DEVICE_KB}" \
    --device "${DEVICE_CTRL}" \
    --device "${DEVICE_VIDEO}" \
    --device "${DEVICE_SPK}" \
    --device "${DEVICE_CASSETTE}" \
    --device "${DEVICE_TV}" \
    --host "${HOST}" \
    --host-backend "${HOST_BACKEND}" \
    --output "${OUTPUT_DIR}"
else
  uv run python -m src.main generate \
    --processor "${PROCESSOR}" \
    --system "${SYSTEM}" \
    --ic "${IC_VDP}" \
    --ic "${IC_PPI}" \
    --ic "${IC_PSG}" \
    --ic "${IC_MAIN_RAM}" \
    --ic "${IC_EXPANDED_SLOT}" \
    --device "${DEVICE_KB}" \
    --device "${DEVICE_CTRL}" \
    --device "${DEVICE_VIDEO}" \
    --device "${DEVICE_SPK}" \
    --device "${DEVICE_CASSETTE}" \
    --device "${DEVICE_TV}" \
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

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} sdl_audio=${PASM_SDL_AUDIO} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
if [[ "${USE_CARTRIDGE}" != "0" ]]; then
  echo "    cartridge_map=${CARTRIDGE_MAP}"
  echo "    cartridge_rom_gen=${CARTRIDGE_ROM_GEN}"
  echo "    cartridge_rom_runtime=${CARTRIDGE_ROM_RUNTIME}"
fi
if [[ "${PROFILE}" == "interactive" ]]; then
  if [[ "${PASM_SDL_DEBUG}" != "0" ]]; then
    echo "    SDL debug log -> ${PASM_SDL_LOGFILE}"
  fi
fi

BUILD_DIR_ABS="$(cd "${BUILD_DIR}" && pwd)"
CMAKE_CONFIG_BUILD_DIR="${BUILD_DIR}/${CMAKE_BUILD_TYPE}"
CMAKE_CONFIG_BUILD_DIR_ABS="$(cd "${CMAKE_CONFIG_BUILD_DIR}" && pwd)"
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

if [[ "${USE_CARTRIDGE}" == "0" ]]; then
  "${CARGO_BIN}" run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
    --backend linked \
    --memory-size "${MEMORY_SIZE}" \
    --system-dir "${SYSTEM_DIR}" \
    --keyboard-map "${KEYBOARD_MAP}" \
    --controller-map "${CONTROLLER_MAP}" \
    --start-pc "${START_PC}" \
    --run-speed "${RUN_SPEED}"
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
      --run-speed "${RUN_SPEED}"
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
      --run-speed "${RUN_SPEED}"
  fi
fi
exit $?