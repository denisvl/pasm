#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for TRS-80 Color Computer 1.
#
# Usage:
#   scripts/run_coco_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xA027
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/mc6809_coco1_sdl
#   EXTRA_CARGO_ARGS="--release"
#   CMAKE_BUILD_TYPE=Release
#   RUN_SPEED=realtime|max
#   PASM_HOST_AUDIO=1
#   CARTRIDGE_MAP=examples/cartridges/coco1/coco_mapper_none.yaml
#   CARTRIDGE_ROM_GEN=../../roms/coco1/Dungeons of Daggorath (1982) (26-3093) (DynaMicro) [!].ccc
#   CARTRIDGE_ROM_RUN=/abs/path/to/cart.rom  (optional override)

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0xA027}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/coco1/host_keyboard_coco.yaml}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

PROCESSOR="examples/processors/mc6809.yaml"
IC_MAIN="examples/ics/coco1/coco1_peripherals.yaml"
DEVICE_KB="examples/devices/coco1/coco_keyboard.yaml"
DEVICE_VIDEO="examples/devices/coco1/coco_video.yaml"
DEVICE_SPK="examples/devices/coco1/coco_speaker.yaml"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/coco1/coco1_default.yaml"
    HOST="examples/hosts/coco1/coco_host_stub.yaml"
    DEFAULT_OUTPUT="generated/mc6809_coco1"
    ;;
  interactive)
    SYSTEM="examples/systems/coco1/coco1_interactive.yaml"
    HOST="examples/hosts/coco1/coco_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/mc6809_coco1_sdl"
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
SYSTEM_DIR="$(dirname "${SYSTEM}")"
SYSTEM_DIR_ABS="$(cd "$(dirname "${SYSTEM}")" && pwd)"

USE_CARTRIDGE=0
if [[ -n "${CARTRIDGE_MAP}" || -n "${CARTRIDGE_ROM_GEN}" || -n "${CARTRIDGE_ROM_RUN:-}" ]]; then
  if [[ -z "${CARTRIDGE_MAP}" ]]; then
    echo "Set CARTRIDGE_MAP when enabling cartridge mode." >&2
    exit 4
  fi
  if [[ -z "${CARTRIDGE_ROM_GEN}" && -z "${CARTRIDGE_ROM_RUN:-}" ]]; then
    echo "Set either CARTRIDGE_ROM_GEN or CARTRIDGE_ROM_RUN when enabling cartridge mode." >&2
    exit 4
  fi
  USE_CARTRIDGE=1
fi

GEN_CARTRIDGE_ARGS=()
RUN_CARTRIDGE_ARGS=()
if [[ "${USE_CARTRIDGE}" == "1" ]]; then
  if [[ -n "${CARTRIDGE_ROM_RUN:-}" ]]; then
    CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUN}"
  elif command -v realpath >/dev/null 2>&1; then
    CARTRIDGE_ROM_RUNTIME="$(realpath "${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}")"
  elif command -v readlink >/dev/null 2>&1; then
    CARTRIDGE_ROM_RUNTIME="$(readlink -f "${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}")"
  else
    CARTRIDGE_ROM_RUNTIME="${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}"
  fi
  if [[ ! -f "${CARTRIDGE_ROM_RUNTIME}" ]]; then
    echo "Cartridge ROM not found: ${CARTRIDGE_ROM_RUNTIME}" >&2
    exit 4
  fi
  if [[ -n "${CARTRIDGE_ROM_GEN}" ]]; then
    GEN_CARTRIDGE_ARGS+=(--cartridge-map "${CARTRIDGE_MAP}" --cartridge-rom "${CARTRIDGE_ROM_GEN}")
  else
    # Ensure cartridge component is present in generated emulator even when
    # caller provides only a runtime ROM path override.
    GEN_CARTRIDGE_ARGS+=(--cartridge-map "${CARTRIDGE_MAP}" --cartridge-rom "${CARTRIDGE_ROM_RUNTIME}")
  fi
  RUN_CARTRIDGE_ARGS+=(--cart-rom "${CARTRIDGE_ROM_RUNTIME}")
fi

KEYBOARD_ARGS=()
if [[ "${PROFILE}" == "interactive" ]]; then
  KEYBOARD_ARGS=(--keyboard-map "${KEYBOARD_MAP}")
fi

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC_MAIN}" \
  --device "${DEVICE_KB}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPK}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-sdl2}" \
  "${GEN_CARTRIDGE_ARGS[@]}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}" --config "${CMAKE_BUILD_TYPE}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
if [[ "${USE_CARTRIDGE}" == "1" ]]; then
  echo "    cartridge_map=${CARTRIDGE_MAP}"
  echo "    cartridge_rom_gen=${CARTRIDGE_ROM_GEN}"
  echo "    cartridge_rom_runtime=${CARTRIDGE_ROM_RUNTIME}"
fi
PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_EMU_BUILD_DIR="${BUILD_DIR}" \
PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json" \
PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR}" \
  "${KEYBOARD_ARGS[@]}" \
  "${RUN_CARTRIDGE_ARGS[@]}" \
  --start-pc "${START_PC}" \
  --run-speed "${RUN_SPEED}"
