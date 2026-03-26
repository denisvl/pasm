#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Sega SG-1000.
#
# Usage:
#   scripts/run_sg1000_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0x0000
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/z80_sg1000_sdl
#   EXTRA_CARGO_ARGS="--release"
#   PASM_SDL_AUDIO=1
#   PASM_SG1000_JOY2_CONNECTED=0|1   (host player 2 connection flag)
#   RUN_SPEED=realtime|max
#   CARTRIDGE_MAP=examples/cartridges/sg1000/sg1000_mapper_none.yaml
#   CARTRIDGE_ROM_GEN="../roms/Hang-On II (Japan).sg"
#   CARTRIDGE_ROM_RUN=/abs/path/to/cart.sg

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
PASM_SDL_AUDIO="${PASM_SDL_AUDIO:-1}"
PASM_SG1000_JOY2_CONNECTED="${PASM_SG1000_JOY2_CONNECTED:-0}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/sg1000/sg1000_mapper_none.yaml}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../roms/Hang-On II (Japan).sg}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROCESSOR="examples/processors/z80.yaml"
IC_VDP="examples/ics/sg1000/sg1000_vdp_tms9918a.yaml"
IC_JOY="examples/ics/sg1000/sg1000_joypad_io.yaml"
IC_PSG="examples/ics/common/psg_sn76489.yaml"
DEVICE_VIDEO="examples/devices/sms/sms_video.yaml"
DEVICE_SPK="examples/devices/sms/sms_speaker.yaml"
SYSTEM_DIR="examples/systems"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/sg1000/z80_sg1000_default.yaml"
    HOST="examples/hosts/sg1000/sg1000_host_stub.yaml"
    DEFAULT_OUTPUT="generated/z80_sg1000"
    ;;
  interactive)
    SYSTEM="examples/systems/sg1000/z80_sg1000_interactive.yaml"
    HOST="examples/hosts/sg1000/sg1000_host_sdl2_interactive.yaml"
    DEFAULT_OUTPUT="generated/z80_sg1000_sdl"
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
PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_SDL_AUDIO="${PASM_SDL_AUDIO}" \
PASM_SG1000_JOY2_CONNECTED="${PASM_SG1000_JOY2_CONNECTED}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR}" \
  --cart-rom "${CARTRIDGE_ROM_RUNTIME}" \
  --start-pc "${START_PC}" \
  --run-speed "${RUN_SPEED}"
