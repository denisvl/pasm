#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for BBC Micro.
#
# Usage:
#   scripts/run_bbc_micro_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xFFFC
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/bbc_micro_interactive
#   EXTRA_CARGO_ARGS="--release"
#   RUN_SPEED=realtime|max

PROFILE="${1:-interactive}"
START_PC="${START_PC:-}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/bbcmicro/host_keyboard_bbc_micro.yaml}"
UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"
RUST_BACKTRACE="${RUST_BACKTRACE:-1}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
PASM_TRACE="0"
PASM_TRACE_FILE=""
PASM_BBC_IO_TRACE="0"
PASM_BBC_IO_TRACE_FILE=""
PASM_BBC_KB_TRACE="0"
PASM_BBC_KB_TRACE_FILE=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
mkdir -p "${UV_CACHE_DIR}"
mkdir -p log

PROCESSOR="examples/processors/mos6502.yaml"
SYSTEM_DIR="examples/systems/bbcmicro"
IC_CRTC="examples/ics/bbcmicro/bbc_micro_crtc_6845.yaml"
IC_VIDEO_ULA="examples/ics/bbcmicro/bbc_micro_video_ula.yaml"
IC_SYSTEM_VIA="examples/ics/bbcmicro/bbc_micro_system_via_6522.yaml"
IC_USER_VIA="examples/ics/bbcmicro/bbc_micro_user_via_6522.yaml"
IC_TELETEXT="examples/ics/bbcmicro/bbc_micro_teletext_saa5050.yaml"
IC_ADC="examples/ics/bbcmicro/bbc_micro_adc_upd7002.yaml"
IC_ACIA="examples/ics/bbcmicro/bbc_micro_acia_6850.yaml"
IC_MMU="examples/ics/bbcmicro/bbc_micro_mmu_paged_rom.yaml"
IC_PSG="examples/ics/bbcmicro/sn76489_psg0.yaml"
IC_MAIN_RAM="examples/ics/bbcmicro/bbc_micro_main_ram.yaml"
DEVICE_KB="examples/devices/bbcmicro/bbc_micro_keyboard.yaml"
DEVICE_VIDEO="examples/devices/bbcmicro/bbc_micro_video.yaml"
DEVICE_SPK="examples/devices/bbcmicro/bbc_micro_speaker.yaml"
HOST_INTERACTIVE="examples/hosts/bbcmicro/bbc_micro_host_hal_interactive.yaml"
HOST_STUB="examples/hosts/bbcmicro/bbc_micro_host_stub.yaml"
HOST_FILE="${HOST_FILE:-}"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/bbcmicro/bbc_micro_default.yaml"
    DEFAULT_OUTPUT="generated/bbcmicro"
    if [[ -z "${HOST_FILE}" ]]; then
      HOST_FILE="${HOST_STUB}"
    fi
    ;;
  interactive)
    SYSTEM="examples/systems/bbcmicro/bbc_micro_interactive.yaml"
    DEFAULT_OUTPUT="generated/bbc_micro_interactive"
    if [[ -z "${HOST_FILE}" ]]; then
      HOST_FILE="${HOST_INTERACTIVE}"
    fi
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
UV_CACHE_DIR="${UV_CACHE_DIR}" uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC_CRTC}" \
  --ic "${IC_VIDEO_ULA}" \
  --ic "${IC_SYSTEM_VIA}" \
  --ic "${IC_USER_VIA}" \
  --ic "${IC_TELETEXT}" \
  --ic "${IC_ADC}" \
  --ic "${IC_ACIA}" \
  --ic "${IC_MMU}" \
  --ic "${IC_PSG}" \
  --ic "${IC_MAIN_RAM}" \
  --device "${DEVICE_KB}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPK}" \
  --host "${HOST_FILE}" \
  --host-backend "${HOST_BACKEND:-glfw}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED}"
echo "    keyboard_map=${KEYBOARD_MAP}"
echo "    host_file=${HOST_FILE}"

RUN_ARGS=(
  --backend linked
  --memory-size "${MEMORY_SIZE}"
  --system-dir "${SYSTEM_DIR}"
  --run-speed "${RUN_SPEED}"
  --keyboard-map "${KEYBOARD_MAP}"
)
if [[ -n "${START_PC}" ]]; then
  RUN_ARGS+=(--start-pc "${START_PC}")
fi

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
PASM_TRACE="${PASM_TRACE}" \
PASM_TRACE_FILE="${PASM_TRACE_FILE}" \
PASM_BBC_IO_TRACE="${PASM_BBC_IO_TRACE}" \
PASM_BBC_IO_TRACE_FILE="${PASM_BBC_IO_TRACE_FILE}" \
PASM_BBC_KB_TRACE="${PASM_BBC_KB_TRACE}" \
PASM_BBC_KB_TRACE_FILE="${PASM_BBC_KB_TRACE_FILE}" \
RUST_BACKTRACE="${RUST_BACKTRACE}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  "${RUN_ARGS[@]}"
