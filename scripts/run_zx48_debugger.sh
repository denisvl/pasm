#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for ZX Spectrum 48K.
#
# Usage:
#   scripts/run_zx48_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0x0000
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/z80_48k_sdl
#   EXTRA_CARGO_ARGS="--release"
#   RUN_SPEED=realtime|max

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROCESSOR="examples/processors/z80.yaml"
IC="examples/ics/zx_spectrum48k/zx_spectrum_48k_ula.yaml"
DEVICE_KB="examples/devices/zx_spectrum48k/zx48_keyboard.yaml"
DEVICE_VIDEO="examples/devices/zx_spectrum48k/zx48_video.yaml"
DEVICE_SPK="examples/devices/zx_spectrum48k/zx48_speaker.yaml"
DEVICE_MIC="examples/devices/zx_spectrum48k/zx48_mic.yaml"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/zx_spectrum48k/spectrum48k_default.yaml"
    HOST="examples/hosts/zx_spectrum48k/zx48_host_hal.yaml"
    DEFAULT_OUTPUT="generated/z80_48k_sdl"
    ;;
  interactive)
    SYSTEM="examples/systems/zx_spectrum48k/spectrum48k_interactive.yaml"
    HOST="examples/hosts/zx_spectrum48k/zx48_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/z80_48k_sdl_interactive"
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

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC}" \
  --device "${DEVICE_KB}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPK}" \
  --device "${DEVICE_MIC}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-sdl2}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend)"
PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR_ABS}" \
  --start-pc "${START_PC}" \
  --run-speed "${RUN_SPEED}"
