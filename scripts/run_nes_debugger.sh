#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for NES (MOS6502 + NROM mapper).
#
# Usage:
#   scripts/run_nes_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0x8000   (optional; leave unset to use reset vector at FFFC/FFFD)
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/mos6502_nes_interactive
#   EXTRA_CARGO_ARGS="--release"
#   CMAKE_BUILD_TYPE=Release
#   RUN_SPEED=realtime|max
#   PASM_HOST_AUDIO=1
#   CARTRIDGE_MAP=examples/cartridges/nes/nes_mapper_gxrom.yaml
#   CARTRIDGE_ROM_GEN="../../roms/nes/Super Mario Bros. + Duck Hunt (USA).nes"
#   CARTRIDGE_ROM_RUNTIME=/abs/path/to/cart.nes
#   PASM_NES_JOY2_CONNECTED=0|1

PROFILE="${1:-interactive}"
START_PC="${START_PC:-}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
PASM_NES_JOY2_CONNECTED="${PASM_NES_JOY2_CONNECTED:-0}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/nes/nes_mapper_gxrom.yaml}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../../roms/nes/Super Mario Bros. + Duck Hunt (USA).nes}"
CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

PROCESSOR="examples/processors/mos6502.yaml"
IC_MAIN="examples/ics/nes/nes_ppu_apu_io.yaml"
DEVICE_VIDEO="examples/devices/nes/nes_video.yaml"
DEVICE_SPK="examples/devices/nes/nes_speaker.yaml"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/nes/nes_default.yaml"
    HOST="examples/hosts/nes/nes_host_stub.yaml"
    DEFAULT_OUTPUT="generated/mos6502_nes_default"
    ;;
  interactive)
    SYSTEM="examples/systems/nes/nes_interactive.yaml"
    HOST="examples/hosts/nes/nes_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/mos6502_nes_interactive"
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

if [[ -n "${CARTRIDGE_ROM_RUNTIME}" ]]; then
  ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME}"
elif command -v realpath >/dev/null 2>&1; then
  ROM_RUNTIME="$(realpath "${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}")"
elif command -v readlink >/dev/null 2>&1; then
  ROM_RUNTIME="$(readlink -f "${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}")"
else
  ROM_RUNTIME="${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}"
fi

if [[ ! -f "${ROM_RUNTIME}" ]]; then
  echo "Cartridge ROM not found: ${ROM_RUNTIME}" >&2
  exit 4
fi

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC_MAIN}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPK}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-sdl2}" \
  --cartridge-map "${CARTRIDGE_MAP}" \
  --cartridge-rom "${CARTRIDGE_ROM_GEN}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}" --config "${CMAKE_BUILD_TYPE}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC:-<reset-vector>} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
echo "    cartridge_map=${CARTRIDGE_MAP}"
echo "    cartridge_rom_gen=${CARTRIDGE_ROM_GEN}"
echo "    cartridge_rom_runtime=${ROM_RUNTIME}"
if [[ -n "${START_PC}" ]]; then
  set -- --start-pc "${START_PC}"
else
  set --
fi

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_EMU_BUILD_DIR="${BUILD_DIR}" \
PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json" \
PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
PASM_NES_JOY2_CONNECTED="${PASM_NES_JOY2_CONNECTED}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR}" \
  --cart-rom "${ROM_RUNTIME}" \
  "$@" \
  --run-speed "${RUN_SPEED}"
