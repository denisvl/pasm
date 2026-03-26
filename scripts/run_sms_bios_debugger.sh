#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Sega Master System BIOS only.
#
# Usage:
#   scripts/run_sms_bios_debugger.sh
#
# Optional env overrides:
#   START_PC=0x0000
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/z80_sms_bios_sdl
#   EXTRA_CARGO_ARGS="--release"
#   PASM_SDL_AUDIO=1
#   PASM_SMS_JOY2_CONNECTED=0|1  (default 0 for disconnected controller 2)
#   RUN_SPEED=realtime|max
#   CMAKE_BUILD_TYPE=Release|Debug

START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
PASM_SDL_AUDIO="${PASM_SDL_AUDIO:-1}"
PASM_SMS_JOY2_CONNECTED="${PASM_SMS_JOY2_CONNECTED:-0}"
PASM_SMS_CROP_LEFT8="${PASM_SMS_CROP_LEFT8:-1}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROCESSOR="examples/processors/z80.yaml"
SYSTEM="examples/systems/sms/z80_sms_bios_interactive.yaml"
IC_VDP="examples/ics/sms/sms_vdp_sega315_5124.yaml"
IC_JOY="examples/ics/sms/sms_joypad_io.yaml"
IC_PSG="examples/ics/common/psg_sn76489.yaml"
DEVICE_VIDEO="examples/devices/sms/sms_video.yaml"
DEVICE_SPK="examples/devices/sms/sms_speaker.yaml"
HOST="examples/hosts/sms/sms_host_sdl2_interactive.yaml"
SYSTEM_DIR="examples/systems"

DEFAULT_OUTPUT="generated/z80_sms_bios_sdl"
OUTPUT_DIR="${OUTPUT_DIR:-${DEFAULT_OUTPUT}}"
BUILD_DIR="${OUTPUT_DIR}/build"
mkdir -p "$(dirname "${OUTPUT_DIR}")"
OUTPUT_DIR_ABS="$(cd "$(dirname "${OUTPUT_DIR}")" && pwd)/$(basename "${OUTPUT_DIR}")"

echo "[1/3] Generating BIOS-only emulator -> ${OUTPUT_DIR}"
uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC_VDP}" \
  --ic "${IC_JOY}" \
  --ic "${IC_PSG}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPK}" \
  --host "${HOST}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend, BIOS only)"
echo "    memory_size=${MEMORY_SIZE} start_pc=${START_PC} sdl_audio=${PASM_SDL_AUDIO} joy2_connected=${PASM_SMS_JOY2_CONNECTED} crop_left8=${PASM_SMS_CROP_LEFT8} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_SDL_AUDIO="${PASM_SDL_AUDIO}" \
PASM_SMS_JOY2_CONNECTED="${PASM_SMS_JOY2_CONNECTED}" \
PASM_SMS_CROP_LEFT8="${PASM_SMS_CROP_LEFT8}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR}" \
  --start-pc "${START_PC}" \
  --run-speed "${RUN_SPEED}"
