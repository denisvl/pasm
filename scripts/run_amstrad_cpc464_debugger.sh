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
#   PASM_HOST_AUDIO=1|0

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/cpc464/host_keyboard_cpc.yaml}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/cpc464/host_controller_cpc464.yaml}"
PASM_CPC_KB_TRACE="${PASM_CPC_KB_TRACE:-0}"
PASM_CPC_HOST_KB_TRACE="${PASM_CPC_HOST_KB_TRACE:-0}"
PASM_CPC_IRQ_TRACE="${PASM_CPC_IRQ_TRACE:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

PROCESSOR="examples/processors/z80.yaml"
IC_GATE_ARRAY="examples/ics/cpc464/cpc_gate_array_40010.yaml"
IC_CRTC="examples/ics/cpc464/cpc_crtc_6845.yaml"
IC_PPI="examples/ics/cpc464/cpc_ppi_8255.yaml"
IC_PSG="examples/ics/cpc464/cpc_ay_3_8912.yaml"
IC_RAM="examples/ics/cpc464/cpc464_ram_64k.yaml"
DEVICE_KB="examples/devices/cpc464/cpc_keyboard.yaml"
DEVICE_GP="examples/devices/cpc464/cpc_gameport.yaml"
DEVICE_VIDEO="examples/devices/cpc464/cpc_video.yaml"
DEVICE_SPK="examples/devices/cpc464/cpc_speaker.yaml"
DEVICE_CASS="examples/devices/common/cassette_transport.yaml"
SYSTEM_DIR="examples/systems/cpc464"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/cpc464/cpc464_default.yaml"
    HOST="examples/hosts/cpc464/cpc_host_stub.yaml"
    DEFAULT_OUTPUT="generated/z80_amstrad_cpc464"
    ;;
  interactive)
    SYSTEM="examples/systems/cpc464/cpc464_interactive.yaml"
    HOST="examples/hosts/cpc464/cpc_host_hal_interactive.yaml"
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
CLEAN_GENERATED="${CLEAN_GENERATED:-1}"

if [[ "${CLEAN_GENERATED}" == "1" ]]; then
  rm -rf "${OUTPUT_DIR}"
fi

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC_GATE_ARRAY}" \
  --ic "${IC_CRTC}" \
  --ic "${IC_PPI}" \
  --ic "${IC_PSG}" \
  --ic "${IC_RAM}" \
  --device "${DEVICE_KB}" \
  --device "${DEVICE_GP}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPK}" \
  --device "${DEVICE_CASS}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-glfw}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
echo "    expected_roms: examples/roms/cpc464/OS_464.ROM and examples/roms/cpc464/BASIC_1.0.ROM"
mkdir -p log
rm -f log/cpc_host_kb_trace.log log/cpc_kb_trace.log log/cpc_ppi_trace.log log/cpc_ay_trace.log
rm -f log/cpc_irq_trace.log

RUN_ARGS=(
  --backend linked
  --memory-size "${MEMORY_SIZE}"
  --system-dir "${SYSTEM_DIR}"
  --start-pc "${START_PC}"
  --run-speed "${RUN_SPEED}"
)
if [[ "${PROFILE}" == "interactive" ]]; then
  RUN_ARGS+=(--keyboard-map "${KEYBOARD_MAP}")
  RUN_ARGS+=(--controller-map "${CONTROLLER_MAP}")
fi

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
PASM_CPC_KB_TRACE="${PASM_CPC_KB_TRACE}" \
PASM_CPC_HOST_KB_TRACE="${PASM_CPC_HOST_KB_TRACE}" \
PASM_CPC_IRQ_TRACE="${PASM_CPC_IRQ_TRACE}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  "${RUN_ARGS[@]}"
