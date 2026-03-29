#!/usr/bin/env bash
set -euo pipefail

# Generate + build + run SMS cartridge mode with debugger, while logging all phases.
#
# Usage:
#   scripts/run_sms_cartridge_debugger_with_logs.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0x0000
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/z80_sms_sdl
#   EXTRA_CARGO_ARGS="--release"
#   PASM_HOST_AUDIO=1
#   PASM_SMS_JOY2_CONNECTED=0|1  (default 0 for disconnected controller 2)
#   PASM_SMS_BOOT_BIOS=1         (optional: force BIOS-visible boot even with cart loaded)
#   RUN_SPEED=realtime|max
#   CMAKE_BUILD_TYPE=Release|Debug
#   CARTRIDGE_MAP=examples/cartridges/sms/sms_mapper_sega.yaml
#   CARTRIDGE_ROM_GEN=../../roms/sms/Sonic The Hedgehog (USA, Europe).sms
#   CARTRIDGE_ROM_RUN=/abs/path/to/your/cart.sms
#   LOG_DIR=log

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
PASM_SMS_JOY2_CONNECTED="${PASM_SMS_JOY2_CONNECTED:-0}"
PASM_SMS_CROP_LEFT8="${PASM_SMS_CROP_LEFT8:-1}"
PASM_SMS_DEBUG="${PASM_SMS_DEBUG:-0}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
RUNTIME_LOG_TO_CONSOLE="${RUNTIME_LOG_TO_CONSOLE:-0}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/sms/sms_mapper_sega.yaml}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../../roms/sms/Sonic the Hedgehog 2 (UE) [!].sms}"
LOG_DIR="${LOG_DIR:-log}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROCESSOR="examples/processors/z80.yaml"
IC_VDP="examples/ics/sms/sms_vdp_sega315_5124.yaml"
IC_JOY="examples/ics/sms/sms_joypad_io.yaml"
IC_PSG="examples/ics/common/psg_sn76489.yaml"
DEVICE_VIDEO="examples/devices/sms/sms_video.yaml"
DEVICE_SPK="examples/devices/sms/sms_speaker.yaml"
SYSTEM_DIR="examples/systems"

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
mkdir -p "${LOG_DIR}" "$(dirname "${OUTPUT_DIR}")"
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

TS="$(date +%Y%m%d_%H%M%S)"
GEN_LOG="${LOG_DIR}/sms_cart_generate_${TS}.log"
BUILD_LOG="${LOG_DIR}/sms_cart_build_${TS}.log"
RUN_LOG="${LOG_DIR}/sms_cart_debugger_${TS}.log"

echo "[1/4] Generating emulator -> ${OUTPUT_DIR}"
echo "      log: ${GEN_LOG}"
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
  --output "${OUTPUT_DIR}" 2>&1 | tee "${GEN_LOG}"

echo "[2/4] Building emulator with CMake -> ${BUILD_DIR}"
echo "      log: ${BUILD_LOG}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}" 2>&1 | tee "${BUILD_LOG}"
cmake --build "${BUILD_DIR}" 2>&1 | tee -a "${BUILD_LOG}"

echo "[3/4] Building Rust debugger (linked backend)"
echo "      log: ${RUN_LOG}"
echo "      profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED} host_audio=${PASM_HOST_AUDIO} joy2_connected=${PASM_SMS_JOY2_CONNECTED} crop_left8=${PASM_SMS_CROP_LEFT8} sms_debug=${PASM_SMS_DEBUG}" | tee "${RUN_LOG}"
echo "      sms_boot_bios=${PASM_SMS_BOOT_BIOS:-0}" | tee -a "${RUN_LOG}"
echo "      cartridge_map=${CARTRIDGE_MAP}" | tee -a "${RUN_LOG}"
echo "      cartridge_rom_gen=${CARTRIDGE_ROM_GEN}" | tee -a "${RUN_LOG}"
echo "      cartridge_rom_runtime=${CARTRIDGE_ROM_RUNTIME}" | tee -a "${RUN_LOG}"
echo "      runtime_log_to_console=${RUNTIME_LOG_TO_CONSOLE}" | tee -a "${RUN_LOG}"

if [[ " ${EXTRA_CARGO_ARGS} " == *" --release "* ]]; then
  CARGO_PROFILE_DIR="release"
else
  CARGO_PROFILE_DIR="debug"
fi

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
cargo build ${EXTRA_CARGO_ARGS} \
  --manifest-path tools/debugger_tui/Cargo.toml \
  --features linked-emulator >> "${RUN_LOG}" 2>&1

DBG_BIN="tools/debugger_tui/target/${CARGO_PROFILE_DIR}/pasm-debugger-tui"

if [[ ! -x "${DBG_BIN}" ]]; then
  echo "Debugger binary not found: ${DBG_BIN}" | tee -a "${RUN_LOG}"
  exit 1
fi

echo "[4/4] Running Rust debugger"
echo "      binary: ${DBG_BIN}"

if [[ "${RUNTIME_LOG_TO_CONSOLE}" == "1" ]]; then
  PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
  PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
  PASM_SMS_JOY2_CONNECTED="${PASM_SMS_JOY2_CONNECTED}" \
  PASM_SMS_CROP_LEFT8="${PASM_SMS_CROP_LEFT8}" \
  PASM_SMS_DEBUG="${PASM_SMS_DEBUG}" \
  "${DBG_BIN}" \
    --backend linked \
    --memory-size "${MEMORY_SIZE}" \
    --system-dir "${SYSTEM_DIR}" \
    --cart-rom "${CARTRIDGE_ROM_RUNTIME}" \
    --start-pc "${START_PC}" \
    --run-speed "${RUN_SPEED}" 2>&1 | tee -a "${RUN_LOG}"
else
  # Keep TUI clean: send runtime stderr to log file and keep stdout attached to terminal.
  PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
  PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
  PASM_SMS_JOY2_CONNECTED="${PASM_SMS_JOY2_CONNECTED}" \
  PASM_SMS_CROP_LEFT8="${PASM_SMS_CROP_LEFT8}" \
  PASM_SMS_DEBUG="${PASM_SMS_DEBUG}" \
  "${DBG_BIN}" \
    --backend linked \
    --memory-size "${MEMORY_SIZE}" \
    --system-dir "${SYSTEM_DIR}" \
    --cart-rom "${CARTRIDGE_ROM_RUNTIME}" \
    --start-pc "${START_PC}" \
    --run-speed "${RUN_SPEED}" 2>> "${RUN_LOG}"
fi

echo ""
echo "Logs:"
echo "  generate: ${GEN_LOG}"
echo "  build:    ${BUILD_LOG}"
echo "  runtime:  ${RUN_LOG}"
