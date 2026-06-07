#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Commodore 64.
#
# Usage:
#   scripts/run_c64_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xFCE2
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/c64_interactive
#   EXTRA_CARGO_ARGS="--release"
#   RUN_SPEED=realtime|max
#   CARTRIDGE_MAP=examples/cartridges/c64/c64_cart_auto.yaml
#   CARTRIDGE_ROM_GEN=../../roms/c64/basic.901226-01.bin
#   CARTRIDGE_ROM_RUNTIME=/abs/path/to/cart.bin
#   CARTRIDGE_DIR=/abs/path/to/c64/roms
#   BOOT_CARTRIDGE=0|1
#   PASM_EMU_CART_PICKER_RAW_KEYS=0|1

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0xFCE2}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/c64/host_keyboard_c64.yaml}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/c64/host_controller_c64.yaml}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/c64/c64_cart_auto.yaml}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../../roms/c64/basic.901226-01.bin}"
CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"
CARTRIDGE_DIR="${CARTRIDGE_DIR:-}"
BOOT_CARTRIDGE="${BOOT_CARTRIDGE:-0}"
PASM_EMU_CART_PICKER_RAW_KEYS="${PASM_EMU_CART_PICKER_RAW_KEYS:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"
if [[ -z "${CARTRIDGE_DIR}" ]]; then
  CARTRIDGE_DIR="${REPO_ROOT}/examples/roms/c64"
fi

PROCESSOR="examples/processors/mos6510.yaml"
IC_PLA="examples/ics/c64/c64_pla_906114.yaml"
IC_VIC="examples/ics/c64/c64_vic_ii_6569.yaml"
IC_SID="examples/ics/c64/c64_sid_6581.yaml"
IC_CIA1="examples/ics/c64/c64_cia1_6526.yaml"
IC_CIA2="examples/ics/c64/c64_cia2_6526.yaml"
IC_COLOR_RAM="examples/ics/c64/c64_color_ram_2114.yaml"
IC_MAIN_RAM="examples/ics/c64/c64_main_ram.yaml"
DEVICE_KB="examples/devices/c64/c64_keyboard.yaml"
DEVICE_JOY="examples/devices/c64/c64_joystick.yaml"
DEVICE_VIDEO="examples/devices/c64/c64_video.yaml"
DEVICE_TV="examples/devices/common/tv_crt_mono.yaml"
HOST_INTERACTIVE="examples/hosts/c64/c64_host_hal_interactive.yaml"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/c64/c64_cartridge_default.yaml"
    DEFAULT_OUTPUT="generated/c64"
    ;;
  interactive)
    SYSTEM="examples/systems/c64/c64_cartridge_interactive.yaml"
    DEFAULT_OUTPUT="generated/c64_interactive"
    ;;
  *)
    echo "Unsupported profile: ${PROFILE}" >&2
    echo "Use: default | interactive" >&2
    exit 2
    ;;
esac

SYSTEM_DIR="$(dirname "${SYSTEM}")"
SYSTEM_DIR_ABS="$(cd "$(dirname "${SYSTEM}")" && pwd)"
ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"
GEN_CARTRIDGE_ARGS=()
RUN_CARTRIDGE_ARGS=()
if [[ -n "${CARTRIDGE_ROM_RUNTIME}" ]]; then
  ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME}"
elif command -v realpath >/dev/null 2>&1; then
  ROM_RUNTIME="$(realpath "${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}")"
elif command -v readlink >/dev/null 2>&1; then
  ROM_RUNTIME="$(readlink -f "${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}")"
else
  ROM_RUNTIME="${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}"
fi
GEN_CARTRIDGE_ARGS+=(--cartridge-map "${CARTRIDGE_MAP}" --cartridge-rom "${CARTRIDGE_ROM_GEN}")
if [[ ! -d "${CARTRIDGE_DIR}" ]]; then
  echo "warning: CARTRIDGE_DIR does not exist: ${CARTRIDGE_DIR}" >&2
  echo "         picker hotkey will appear to do nothing until this is fixed." >&2
fi
RUN_CARTRIDGE_ARGS+=(--cartridge-dir "${CARTRIDGE_DIR}")
if [[ "${BOOT_CARTRIDGE}" != "0" ]]; then
  RUN_CARTRIDGE_ARGS+=(--cart-rom "${ROM_RUNTIME}")
fi

OUTPUT_DIR="${OUTPUT_DIR:-${DEFAULT_OUTPUT}}"
BUILD_DIR="${OUTPUT_DIR}/build"
mkdir -p "$(dirname "${OUTPUT_DIR}")"
OUTPUT_DIR_ABS="$(cd "$(dirname "${OUTPUT_DIR}")" && pwd)/$(basename "${OUTPUT_DIR}")"
BUILD_DIR_ABS="$(cd "$(dirname "${BUILD_DIR}")" && pwd)/$(basename "${BUILD_DIR}")"

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
if [[ "${PROFILE}" == "interactive" ]]; then
  uv run python -m src.main generate \
    --processor "${PROCESSOR}" \
    --system "${SYSTEM}" \
    --ic "${IC_PLA}" \
    --ic "${IC_VIC}" \
    --ic "${IC_SID}" \
    --ic "${IC_CIA1}" \
    --ic "${IC_CIA2}" \
    --ic "${IC_COLOR_RAM}" \
    --ic "${IC_MAIN_RAM}" \
    --device "${DEVICE_KB}" \
    --device "${DEVICE_JOY}" \
    --device "${DEVICE_VIDEO}" \
    --device "${DEVICE_TV}" \
    --host "${HOST_INTERACTIVE}" \
    --host-backend "${HOST_BACKEND:-glfw}" \
    "${GEN_CARTRIDGE_ARGS[@]}" \
    --output "${OUTPUT_DIR}"
else
  uv run python -m src.main generate \
    --processor "${PROCESSOR}" \
    --system "${SYSTEM}" \
    "${GEN_CARTRIDGE_ARGS[@]}" \
    --output "${OUTPUT_DIR}"
fi

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"
PASM_EMU_BUILD_DIR="${BUILD_DIR_ABS}"
if [[ -d "${BUILD_DIR_ABS}/${CMAKE_BUILD_TYPE}" ]]; then
  PASM_EMU_BUILD_DIR="${BUILD_DIR_ABS}/${CMAKE_BUILD_TYPE}"
fi

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED}"
echo "    cartridge_map=${CARTRIDGE_MAP}"
echo "    cartridge_rom_gen=${CARTRIDGE_ROM_GEN}"
echo "    cartridge_rom_runtime=${ROM_RUNTIME}"
echo "    cartridge_dir=${CARTRIDGE_DIR}"
echo "    boot_cartridge=${BOOT_CARTRIDGE}"
echo "    cart_picker_raw_keys=${PASM_EMU_CART_PICKER_RAW_KEYS}"

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
RUN_ARGS+=("${RUN_CARTRIDGE_ARGS[@]}")

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_EMU_BUILD_DIR="${PASM_EMU_BUILD_DIR}" \
PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json" \
PASM_EMU_CART_PICKER_RAW_KEYS="${PASM_EMU_CART_PICKER_RAW_KEYS}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  "${RUN_ARGS[@]}"
