#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Amstrad CPC464.
#
# Usage:
#   scripts/run_amstrad_cpc464_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0x0000
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/z80_amstrad_cpc464_sdl
#   EXTRA_CARGO_ARGS="--release"
#   CMAKE_BUILD_TYPE=Release
#   RUN_SPEED=realtime|max
#   PASM_SDL_AUDIO=1|0

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
PASM_SDL_AUDIO="${PASM_SDL_AUDIO:-1}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROCESSOR="examples/processors/z80.yaml"
IC_MAIN="examples/ics/cpc464/amstrad_cpc_io.yaml"
DEVICE_KB="examples/devices/cpc464/cpc_keyboard.yaml"
DEVICE_VIDEO="examples/devices/cpc464/cpc_video.yaml"
DEVICE_SPK="examples/devices/cpc464/cpc_speaker.yaml"
SYSTEM_DIR="examples/systems"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/cpc464/z80_amstrad_cpc464_default.yaml"
    HOST="examples/hosts/cpc464/cpc_host_stub.yaml"
    DEFAULT_OUTPUT="generated/z80_amstrad_cpc464"
    ;;
  interactive)
    SYSTEM="examples/systems/cpc464/z80_amstrad_cpc464_interactive.yaml"
    HOST="examples/hosts/cpc464/cpc_host_sdl2_interactive.yaml"
    DEFAULT_OUTPUT="generated/z80_amstrad_cpc464_sdl"
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

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC_MAIN}" \
  --device "${DEVICE_KB}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPK}" \
  --host "${HOST}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
echo "    expected_roms: examples/roms/cpc464/OS_464.ROM and examples/roms/cpc464/BASIC_664.ROM"

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_SDL_AUDIO="${PASM_SDL_AUDIO}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR}" \
  --start-pc "${START_PC}" \
  --run-speed "${RUN_SPEED}"
