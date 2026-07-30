#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for ColecoVision.
#
# Usage:
#   scripts/run_colecovision_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0x0000
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/z80_colecovision_sdl
#   EXTRA_CARGO_ARGS="--release"
#   PASM_HOST_AUDIO=1
#   PASM_COLECOVISION_JOY2_CONNECTED=0|1   (host player 2 connection flag)
#   RUN_SPEED=realtime|max
#   CARTRIDGE_MAP=examples/cartridges/colecovision/colecovision_mapper_none.yaml
#   CARTRIDGE_ROM_GEN="../../roms/colecovision/ColecoVision BIOS (1982).col"
#   CARTRIDGE_ROM_RUN=/abs/path/to/cart.col
#   CARTRIDGE_DIR=/abs/path/to/colecovision/roms   (enable runtime cartridge picker)

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
PASM_COLECOVISION_JOY2_CONNECTED="${PASM_COLECOVISION_JOY2_CONNECTED:-0}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/colecovision/colecovision_mapper_none.yaml}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../../roms/colecovision/ColecoVision BIOS (1982).col}"
CARTRIDGE_DIR="${CARTRIDGE_DIR:-}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/colecovision/host_controller_colecovision.yaml}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/colecovision/host_console_colecovision.yaml}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

if [[ -z "${CARTRIDGE_DIR}" ]]; then
  CARTRIDGE_DIR="${REPO_ROOT}/examples/roms/colecovision"
fi

PROCESSOR="examples/processors/z80.yaml"
IC_VDP="examples/ics/colecovision/colecovision_vdp_tms9928a.yaml"
IC_JOY="examples/ics/colecovision/colecovision_joypad_io.yaml"
IC_BUS="examples/ics/colecovision/colecovision_cpu_bus.yaml"
IC_RAM="examples/ics/colecovision/colecovision_main_ram.yaml"
IC_PSG="examples/ics/colecovision/colecovision_psg_sn76489.yaml"
DEVICE_VIDEO="examples/devices/sms/sms_video.yaml"
DEVICE_TV="examples/devices/common/tv_crt_mono.yaml"
SYSTEM_DIR="examples/systems"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/colecovision/colecovision_default.yaml"
    HOST="examples/hosts/colecovision/colecovision_host_stub.yaml"
    DEFAULT_OUTPUT="generated/z80_colecovision"
    ;;
  interactive)
    SYSTEM="examples/systems/colecovision/colecovision_interactive.yaml"
    HOST="examples/hosts/colecovision/colecovision_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/z80_colecovision_sdl"
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
  --ic "${IC_BUS}" \
  --ic "${IC_RAM}" \
  --ic "${IC_PSG}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_TV}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-glfw}" \
  --cartridge-map "${CARTRIDGE_MAP}" \
  --cartridge-rom "${CARTRIDGE_ROM_GEN}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
echo "    cartridge_map=${CARTRIDGE_MAP}"
echo "    cartridge_rom_gen=${CARTRIDGE_ROM_GEN}"
echo "    cartridge_rom_runtime=${CARTRIDGE_ROM_RUNTIME}"
if [[ -n "${CARTRIDGE_DIR}" ]]; then
  echo "    cartridge_dir=${CARTRIDGE_DIR}"
fi
if [[ "${PROFILE}" == "interactive" ]]; then
  echo "    controller_map=${CONTROLLER_MAP}"
  echo "    keyboard_map=${KEYBOARD_MAP}"
fi

EXTRA_MAP_ARGS=()
if [[ "${PROFILE}" == "interactive" ]]; then
  EXTRA_MAP_ARGS+=(--controller-map "${CONTROLLER_MAP}")
  EXTRA_MAP_ARGS+=(--keyboard-map "${KEYBOARD_MAP}")
fi
if [[ -n "${CARTRIDGE_DIR}" ]]; then
  if [[ ! -d "${CARTRIDGE_DIR}" ]]; then
    echo "warning: CARTRIDGE_DIR does not exist: ${CARTRIDGE_DIR}" >&2
    echo "         picker hotkey will appear to do nothing until this is fixed." >&2
  fi
  EXTRA_MAP_ARGS+=(--cartridge-dir "${CARTRIDGE_DIR}")
fi

PASM_EMU_BUILD_DIR="${BUILD_DIR}"
if [[ -d "${BUILD_DIR}/${CMAKE_BUILD_TYPE}" ]]; then
  PASM_EMU_BUILD_DIR="${BUILD_DIR}/${CMAKE_BUILD_TYPE}"
fi

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_EMU_BUILD_DIR="${PASM_EMU_BUILD_DIR}" \
PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
PASM_COLECOVISION_JOY2_CONNECTED="${PASM_COLECOVISION_JOY2_CONNECTED}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR}" \
  --cart-rom "${CARTRIDGE_ROM_RUNTIME}" \
  --start-pc "${START_PC}" \
  "${EXTRA_MAP_ARGS[@]}" \
  --run-speed "${RUN_SPEED}"
