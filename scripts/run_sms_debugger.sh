#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Sega Master System.
#
# Usage:
#   scripts/run_sms_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0x0000
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/z80_sms_sdl
#   EXTRA_CARGO_ARGS="--release"
#   PASM_HOST_AUDIO=1
#   PASM_SMS_JOY2_CONNECTED=0|1  (default 0 for disconnected controller 2)
#   RUN_SPEED=realtime|max
#   CARTRIDGE_MAP=examples/cartridges/sms/sms_mapper_sega.yaml
#   CARTRIDGE_ROM_GEN=../../roms/sms/sega.rom
#   CARTRIDGE_ROM_RUN=/abs/path/to/cart.sms  (optional override)

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
PASM_SMS_JOY2_CONNECTED="${PASM_SMS_JOY2_CONNECTED:-0}"
PASM_SMS_CROP_LEFT8="${PASM_SMS_CROP_LEFT8:-1}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/sms/sms_mapper_sega.yaml}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../../roms/sms/sega.rom}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROCESSOR="examples/processors/z80.yaml"
IC_VDP="examples/ics/sms/sms_vdp_sega315_5124.yaml"
IC_JOY="examples/ics/sms/sms_joypad_io.yaml"
IC_PSG="examples/ics/common/psg_sn76489.yaml"
DEVICE_VIDEO="examples/devices/sms/sms_video.yaml"
DEVICE_SPK="examples/devices/sms/sms_speaker.yaml"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/sms/sms_default.yaml"
    HOST="examples/hosts/sms/sms_host_stub.yaml"
    DEFAULT_OUTPUT="generated/z80_sms"
    ;;
  interactive)
    SYSTEM="examples/systems/sms/sms_interactive.yaml"
    HOST="examples/hosts/sms/sms_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/z80_sms_sdl"
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

if [[ -n "${CARTRIDGE_ROM_RUN:-}" ]]; then
  CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUN}"
elif command -v realpath >/dev/null 2>&1; then
  CARTRIDGE_ROM_RUNTIME="$(realpath "${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}")"
elif command -v readlink >/dev/null 2>&1; then
  CARTRIDGE_ROM_RUNTIME="$(readlink -f "${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}")"
else
  CARTRIDGE_ROM_RUNTIME="${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}"
fi

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC_VDP}" \
  --ic "${IC_JOY}" \
  --ic "${IC_PSG}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPK}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-sdl2}" \
  --cartridge-map "${CARTRIDGE_MAP}" \
  --cartridge-rom "${CARTRIDGE_ROM_GEN}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} host_audio=${PASM_HOST_AUDIO} joy2_connected=${PASM_SMS_JOY2_CONNECTED} crop_left8=${PASM_SMS_CROP_LEFT8} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
echo "    cartridge_map=${CARTRIDGE_MAP}"
echo "    cartridge_rom_gen=${CARTRIDGE_ROM_GEN}"
echo "    cartridge_rom_runtime=${CARTRIDGE_ROM_RUNTIME}"
PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
PASM_SMS_JOY2_CONNECTED="${PASM_SMS_JOY2_CONNECTED}" \
PASM_SMS_CROP_LEFT8="${PASM_SMS_CROP_LEFT8}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR_ABS}" \
  --cart-rom "${CARTRIDGE_ROM_RUNTIME}" \
  --start-pc "${START_PC}" \
  --run-speed "${RUN_SPEED}"
