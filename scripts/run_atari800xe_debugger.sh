#!/usr/bin/env bash
# One-shot helper: generate + build + run PASM Rust debugger for Atari 800XE.
#
# Usage:
#   scripts/run_atari800xe_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xE477    (optional; if unset, uses reset vector)
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/atari800xe_interactive
#   EXTRA_CARGO_ARGS=--release
#   EXTRA_CMAKE_ARGS=-DCMAKE_TOOLCHAIN_FILE=/opt/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-linux
#   VCPKG_ROOT=/opt/vcpkg
#   VCPKG_TARGET_TRIPLET=x64-linux
#   CMAKE_BUILD_TYPE=Release
#   RUN_SPEED=realtime|max
#   PASM_SDL_AUDIO=1

set -euo pipefail

PROFILE="${1:-interactive}"

: "${MEMORY_SIZE:=65536}"
: "${EXTRA_CARGO_ARGS:=--release}"
: "${EXTRA_CMAKE_ARGS:=}"
: "${VCPKG_TARGET_TRIPLET:=x64-linux}"
: "${CMAKE_BUILD_TYPE:=Release}"
: "${RUN_SPEED:=realtime}"
: "${PASM_HOST_AUDIO:=1}"
PASM_TRACE=0
PASM_ATARI800XL_KEY_TRACE=0
PASM_ATARI800XL_KB_EVENTS=0
: "${KEYBOARD_MAP:=examples/hosts/atari800xl/host_keyboard_atari800xl.yaml}"
: "${HOST_BACKEND:=glfw}"

# ROM paths (800XE reuses 800XL OS ROMs; BASIC is copied to 800XE dir)
: "${OS_ROM_LOW:=../../roms/atari800xe/ATARIXL_C000.ROM}"
: "${OS_ROM_HIGH:=../../roms/atari800xe/ATARIXL_D800.ROM}"
: "${SELFTEST_ROM:=../../roms/atari800xe/ATARIXL_SELFTEST.ROM}"
: "${BASIC_ROM:=../../roms/atari800xe/AtariBasic.rom}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
: "${UV_CACHE_DIR:=${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

PROCESSOR="examples/processors/mos6502.yaml"
IC_ANTIC="examples/ics/atari800xl/atari800xl_antic.yaml"
IC_GTIA="examples/ics/atari800xl/atari800xl_gtia.yaml"
IC_POKEY="examples/ics/atari800xl/atari800xl_pokey.yaml"
IC_PIA="examples/ics/atari800xl/atari800xl_pia_6520.yaml"
IC_MMU="examples/ics/atari800xl/atari800xl_mmu.yaml"
IC_MAIN_RAM="examples/ics/atari800xl/atari800xl_main_ram.yaml"
DEVICE_KB="examples/devices/atari800xl/atari800xl_keyboard.yaml"
DEVICE_CTRL="examples/devices/atari800xl/atari800xl_controller.yaml"
DEVICE_VIDEO="examples/devices/atari800xl/atari800xl_video.yaml"
DEVICE_SPEAKER="examples/devices/atari800xl/atari800xl_speaker.yaml"
DEVICE_CASSETTE_ADAPTER="examples/devices/atari800xl/atari800xl_cassette_adapter.yaml"
DEVICE_CASSETTE_TRANSPORT="examples/devices/common/cassette_transport.yaml"
DEVICE_CASSETTE_LINE_IN="examples/devices/common/cassette_line_in_source.yaml"
DEVICE_CASSETTE_WAV="examples/devices/common/cassette_wav_source.yaml"
DEVICE_TV="examples/devices/common/tv_crt_mono.yaml"
SYSTEM_DIR="examples/systems/atari800xe"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/atari800xe/atari800xe_default.yaml"
    HOST="examples/hosts/atari800xl/atari800xl_host_stub.yaml"
    DEFAULT_OUTPUT="generated/atari800xe_default"
    ;;
  interactive)
    SYSTEM="examples/systems/atari800xe/atari800xe_interactive.yaml"
    HOST="examples/hosts/atari800xl/atari800xl_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/atari800xe_interactive"
    ;;
  *)
    echo "Unsupported profile: ${PROFILE}" >&2
    echo "Use: default | interactive" >&2
    exit 2
    ;;
esac

: "${OUTPUT_DIR:=${DEFAULT_OUTPUT}}"
BUILD_DIR="${OUTPUT_DIR}/build"
SYSTEM_DIR_ABS="$(cd "$(dirname "${SYSTEM}")" && pwd)"
OUTPUT_PARENT="$(dirname "${OUTPUT_DIR}")"
mkdir -p "${OUTPUT_DIR}" "${BUILD_DIR}"
OUTPUT_DIR_ABS="$(cd "$(dirname "${OUTPUT_DIR}")" && pwd)/$(basename "${OUTPUT_DIR}")"

if [[ -z "${EXTRA_CMAKE_ARGS}" ]]; then
  if [[ -n "${VCPKG_ROOT:-}" ]]; then
    VCPKG_CMAKE_FILE="${VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake"
    if [[ -f "${VCPKG_CMAKE_FILE}" ]]; then
      EXTRA_CMAKE_ARGS="-DCMAKE_TOOLCHAIN_FILE=${VCPKG_CMAKE_FILE} -DVCPKG_TARGET_TRIPLET=${VCPKG_TARGET_TRIPLET}"
    fi
  fi
fi

VCPKG_INSTALLED_TRIPLET_DIR=""
if [[ -n "${VCPKG_ROOT:-}" ]]; then
  if [[ -d "${VCPKG_ROOT}/installed/${VCPKG_TARGET_TRIPLET}" ]]; then
    VCPKG_INSTALLED_TRIPLET_DIR="${VCPKG_ROOT}/installed/${VCPKG_TARGET_TRIPLET}"
  fi
fi

if [[ -n "${VCPKG_INSTALLED_TRIPLET_DIR}" ]]; then
  if [[ -f "${VCPKG_INSTALLED_TRIPLET_DIR}/include/SDL2/SDL.h" ]]; then
    export INCLUDE="${VCPKG_INSTALLED_TRIPLET_DIR}/include:${INCLUDE:-}"
  fi
  if [[ -f "${VCPKG_INSTALLED_TRIPLET_DIR}/lib/libSDL2.so" ]]; then
    export LIBRARY_PATH="${VCPKG_INSTALLED_TRIPLET_DIR}/lib:${LIBRARY_PATH:-}"
    export LD_LIBRARY_PATH="${VCPKG_INSTALLED_TRIPLET_DIR}/lib:${LD_LIBRARY_PATH:-}"
  fi
fi

if [[ -z "${PASM_EMU_EXTRA_LIB_DIRS:-}" ]]; then
  if [[ -n "${VCPKG_INSTALLED_TRIPLET_DIR}" ]]; then
    if [[ -d "${VCPKG_INSTALLED_TRIPLET_DIR}/lib" ]]; then
      PASM_EMU_EXTRA_LIB_DIRS="${VCPKG_INSTALLED_TRIPLET_DIR}/lib"
    fi
  fi
fi

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
TMP_SYSTEM="${SYSTEM_DIR_ABS}/.tmp_atari800xe_system_$$.yaml"
uv run python - <<PYEOF "${SYSTEM}" "${TMP_SYSTEM}" "${OS_ROM_LOW}" "${OS_ROM_HIGH}" "${SELFTEST_ROM}" "${BASIC_ROM}"
import yaml, sys
src, dst, osl, osh, st, bas = sys.argv[1:7]
data = yaml.safe_load(open(src, 'r', encoding='utf-8'))
imgs = ((data.get('memory') or {}).get('rom_images') or [])
for rom in imgs:
    name = str(rom.get('name', ''))
    if name == 'atari800xe_basic':
        rom['file'] = bas
    elif name == 'atari800xe_selftest':
        rom['file'] = st
    elif name == 'atari800xe_os_low':
        rom['file'] = osl
    elif name == 'atari800xe_os_high':
        rom['file'] = osh
yaml.safe_dump(data, open(dst, 'w', encoding='utf-8'), sort_keys=False)
PYEOF

uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${TMP_SYSTEM}" \
  --ic "${IC_ANTIC}" \
  --ic "${IC_GTIA}" \
  --ic "${IC_POKEY}" \
  --ic "${IC_PIA}" \
  --ic "${IC_MMU}" \
  --ic "${IC_MAIN_RAM}" \
  --device "${DEVICE_KB}" \
  --device "${DEVICE_CTRL}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPEAKER}" \
  --device "${DEVICE_CASSETTE_ADAPTER}" \
  --device "${DEVICE_CASSETTE_TRANSPORT}" \
  --device "${DEVICE_CASSETTE_LINE_IN}" \
  --device "${DEVICE_CASSETTE_WAV}" \
  --device "${DEVICE_TV}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND}" \
  --output "${OUTPUT_DIR}"
rm -f "${TMP_SYSTEM}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
if ! cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}" ${EXTRA_CMAKE_ARGS}; then
  echo "CMake configure failed; clearing ${BUILD_DIR} and retrying once..."
  rm -rf "${BUILD_DIR}"
  cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}" ${EXTRA_CMAKE_ARGS}
fi
cmake --build "${BUILD_DIR}" --config "${CMAKE_BUILD_TYPE}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC:-} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"

BUILD_DIR_ABS="$(cd "${BUILD_DIR}" && pwd)"
CMAKE_CONFIG_BUILD_DIR="${BUILD_DIR}/${CMAKE_BUILD_TYPE}"
CMAKE_CONFIG_BUILD_DIR_ABS=""
if [[ -d "${CMAKE_CONFIG_BUILD_DIR}" ]]; then
  CMAKE_CONFIG_BUILD_DIR_ABS="$(cd "${CMAKE_CONFIG_BUILD_DIR}" && pwd)"
fi
export PASM_EMU_DIR="${OUTPUT_DIR_ABS}"
export PASM_EMU_BUILD_DIR="${BUILD_DIR_ABS}"
if [[ -n "${CMAKE_CONFIG_BUILD_DIR_ABS}" ]]; then
  export PASM_EMU_BUILD_DIR="${CMAKE_CONFIG_BUILD_DIR_ABS}"
fi
export PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json"
export PASM_HOST_AUDIO="${PASM_HOST_AUDIO}"
export PASM_TRACE="${PASM_TRACE}"
export PASM_ATARI800XL_KEY_TRACE="${PASM_ATARI800XL_KEY_TRACE}"
export PASM_ATARI800XL_KB_EVENTS="${PASM_ATARI800XL_KB_EVENTS}"
export PASM_SYSTEM_DIR="${SYSTEM_DIR_ABS}"

CARGO_BIN="cargo"
if ! command -v cargo >/dev/null 2>&1; then
  if [[ -x "${HOME}/.cargo/bin/cargo" ]]; then
    CARGO_BIN="${HOME}/.cargo/bin/cargo"
  else
    echo "cargo executable not found." >&2
    echo "Install Rust with rustup, or add \"${HOME}/.cargo/bin\" to PATH." >&2
    exit 3
  fi
fi

if [[ -n "${START_PC:-}" ]]; then
  "${CARGO_BIN}" run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
    --backend linked \
    --memory-size "${MEMORY_SIZE}" \
    --system-dir "${SYSTEM_DIR}" \
    --keyboard-map "${KEYBOARD_MAP}" \
    --start-pc "${START_PC}" \
    --run-speed "${RUN_SPEED}"
else
  "${CARGO_BIN}" run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
    --backend linked \
    --memory-size "${MEMORY_SIZE}" \
    --system-dir "${SYSTEM_DIR}" \
    --keyboard-map "${KEYBOARD_MAP}" \
    --run-speed "${RUN_SPEED}"
fi

exit 0
