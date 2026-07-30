#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Apple I.
#
# Usage:
#   scripts/run_apple1_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xFF00
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/apple1_interactive
#   EXTRA_CARGO_ARGS="--release"
#   RUN_SPEED=realtime|max
#   HOST_BACKEND=glfw|sdl2

PROFILE="${1:-interactive}"
if [[ $# -gt 0 ]]; then
  shift
fi
START_PC="${START_PC:-}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
HOST_BACKEND="${HOST_BACKEND:-glfw}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROCESSOR="examples/processors/mos6502.yaml"
SYSTEM_DIR="examples/systems/apple1"
export PASM_SYSTEM_DIR="${SYSTEM_DIR}"
IC_PIA="examples/ics/apple/apple1_pia_6820.yaml"
IC_CHAR_ROM="examples/ics/apple/apple1_char_rom.yaml"
IC_CASSETTE="examples/ics/apple/apple1_cassette_io.yaml"
DEVICE_KB="examples/devices/apple1/apple1_keyboard.yaml"
DEVICE_VIDEO="examples/devices/apple1/apple1_video.yaml"
DEVICE_CASSETTE="examples/devices/common/cassette_transport_nomotor.yaml"
HOST_INTERACTIVE="examples/hosts/apple1/apple1_host_hal_interactive.yaml"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/apple1/apple1_default.yaml"
    DEFAULT_OUTPUT="generated/apple1"
    ;;
  interactive)
    SYSTEM="examples/systems/apple1/apple1_interactive.yaml"
    DEFAULT_OUTPUT="generated/apple1_interactive"
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
GEN_ARGS=(
  --processor "${PROCESSOR}"
  --system "${SYSTEM}"
  --ic "${IC_PIA}"
  --ic "${IC_CHAR_ROM}"
  --ic "${IC_CASSETTE}"
  --device "${DEVICE_KB}"
  --device "${DEVICE_VIDEO}"
  --device "${DEVICE_CASSETTE}"
  --output "${OUTPUT_DIR}"
)
if [[ "${PROFILE}" == "interactive" ]]; then
  GEN_ARGS+=(
    --host "${HOST_INTERACTIVE}"
    --host-backend "${HOST_BACKEND}"
  )
fi
UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}" uv run python -m src.main generate "${GEN_ARGS[@]}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED}"

RUN_ARGS=(
  --backend linked
  --memory-size "${MEMORY_SIZE}"
  --system-dir "${SYSTEM_DIR}"
  --run-speed "${RUN_SPEED}"
)
if [[ "${PROFILE}" == "interactive" ]]; then
  RUN_ARGS+=(--keyboard-map "examples/hosts/apple1/host_keyboard_apple1.yaml")
  if [[ -f "examples/hosts/apple1/host_keyboard_apple1_joystick.yaml" ]]; then
    RUN_ARGS+=(--joystick-keyboard-map "examples/hosts/apple1/host_keyboard_apple1_joystick.yaml")
  fi
  if [[ -f "examples/hosts/apple1/host_controller_apple1.yaml" ]]; then
    RUN_ARGS+=(--controller-map "examples/hosts/apple1/host_controller_apple1.yaml")
  fi
fi
if [[ -n "${START_PC}" ]]; then
  RUN_ARGS+=(--start-pc "${START_PC}")
fi
if [[ $# -gt 0 ]]; then
  RUN_ARGS+=("$@")
fi

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  "${RUN_ARGS[@]}"