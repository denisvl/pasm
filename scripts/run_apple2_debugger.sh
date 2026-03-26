#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Apple II.
#
# Usage:
#   scripts/run_apple2_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xFA62
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/apple2_interactive
#   EXTRA_CARGO_ARGS="--release"
#   RUN_SPEED=realtime|max

PROFILE="${1:-interactive}"
START_PC="${START_PC:-}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROCESSOR="examples/processors/mos6502.yaml"
SYSTEM_DIR="examples/systems"
IC_IO="examples/ics/apple2/apple2_io.yaml"
DEVICE_KB="examples/devices/apple2/apple2_keyboard.yaml"
DEVICE_VIDEO="examples/devices/apple2/apple2_video.yaml"
DEVICE_SPK="examples/devices/apple2/apple2_speaker.yaml"
HOST_INTERACTIVE="examples/hosts/apple2/apple2_host_sdl2_interactive.yaml"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/apple2/apple2_default.yaml"
    DEFAULT_OUTPUT="generated/apple2"
    ;;
  interactive)
    SYSTEM="examples/systems/apple2/apple2_interactive.yaml"
    DEFAULT_OUTPUT="generated/apple2_interactive"
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
if [[ "${PROFILE}" == "interactive" ]]; then
  uv run python -m src.main generate \
    --processor "${PROCESSOR}" \
    --system "${SYSTEM}" \
    --ic "${IC_IO}" \
    --device "${DEVICE_KB}" \
    --device "${DEVICE_VIDEO}" \
    --device "${DEVICE_SPK}" \
    --host "${HOST_INTERACTIVE}" \
    --output "${OUTPUT_DIR}"
else
  uv run python -m src.main generate \
    --processor "${PROCESSOR}" \
    --system "${SYSTEM}" \
    --output "${OUTPUT_DIR}"
fi

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED}"

if [[ -n "${START_PC}" ]]; then
  PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
  cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
    --backend linked \
    --memory-size "${MEMORY_SIZE}" \
    --system-dir "${SYSTEM_DIR}" \
    --start-pc "${START_PC}" \
    --run-speed "${RUN_SPEED}"
else
  PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
  cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
    --backend linked \
    --memory-size "${MEMORY_SIZE}" \
    --system-dir "${SYSTEM_DIR}" \
    --run-speed "${RUN_SPEED}"
fi
