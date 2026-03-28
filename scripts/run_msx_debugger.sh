#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for MSX.
#
# Usage:
#   scripts/run_msx_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0x0000
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/z80_msx1_sdl
#   EXTRA_CARGO_ARGS="--release"
#   USE_CARTRIDGE=1|0
#   CARTRIDGE_MAP=examples/cartridges/msx1/msx_mapper_konami.yaml
#   CARTRIDGE_ROM_GEN="../../roms/msx1/Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom"
#   CARTRIDGE_ROM_RUNTIME=/abs/path/to/rom.rom
#   PASM_SDL_DEBUG=1
#   PASM_SDL_LOGFILE=/tmp/msx_sdl.log
#   PASM_SDL_AUDIO=1
#   PASM_MSX_JOY_BUTTONS=1|2  (1=KP0/KP_ENTER, 2=KP1/KP2)
#   RUN_SPEED=realtime|max

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
PASM_SDL_DEBUG="${PASM_SDL_DEBUG:-0}"
PASM_SDL_LOGFILE="${PASM_SDL_LOGFILE:-/tmp/msx_sdl.log}"
PASM_SDL_AUDIO="${PASM_SDL_AUDIO:-1}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
USE_CARTRIDGE="${USE_CARTRIDGE:-1}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/msx1/msx_mapper_konami.yaml}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-}"
CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROCESSOR="examples/processors/z80.yaml"
IC_VDP="examples/ics/msx1/msx1_vdp_tms9918a.yaml"
IC_PPI="examples/ics/msx1/msx1_ppi_8255.yaml"
IC_PSG="examples/ics/msx1/msx1_psg_ay8910.yaml"
DEVICE_KB="examples/devices/msx1/msx_keyboard.yaml"
DEVICE_VIDEO="examples/devices/msx1/msx_video.yaml"
DEVICE_SPK="examples/devices/msx1/msx_speaker.yaml"
SYSTEM_DIR="examples/systems"

case "${PROFILE}" in
  default)
    if [[ "${USE_CARTRIDGE}" != "0" ]]; then
      SYSTEM="examples/systems/msx1/z80_msx1_cartridge_default.yaml"
    else
      SYSTEM="examples/systems/msx1/z80_msx1_default.yaml"
    fi
    HOST="examples/hosts/msx1/msx_host_stub.yaml"
    DEFAULT_OUTPUT="generated/z80_msx1"
    ;;
  interactive)
    if [[ "${USE_CARTRIDGE}" != "0" ]]; then
      SYSTEM="examples/systems/msx1/z80_msx1_cartridge_interactive.yaml"
    else
      SYSTEM="examples/systems/msx1/z80_msx1_interactive.yaml"
    fi
    HOST="examples/hosts/msx1/msx_host_sdl2_interactive.yaml"
    DEFAULT_OUTPUT="generated/z80_msx1_sdl"
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
if [[ -z "${CARTRIDGE_ROM_RUNTIME}" ]]; then
  CARTRIDGE_ROM_RUNTIME="${REPO_ROOT}/examples/roms/msx1/Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom"
fi
if [[ -z "${CARTRIDGE_ROM_GEN}" ]]; then
  CARTRIDGE_ROM_GEN="../../roms/msx1/Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom"
fi

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
GEN_ARGS=(
  --processor "${PROCESSOR}"
  --system "${SYSTEM}"
  --ic "${IC_VDP}"
  --ic "${IC_PPI}"
  --ic "${IC_PSG}"
  --device "${DEVICE_KB}"
  --device "${DEVICE_VIDEO}"
  --device "${DEVICE_SPK}"
  --host "${HOST}"
  --output "${OUTPUT_DIR}"
)
RUN_ARGS=(
  --backend linked
  --memory-size "${MEMORY_SIZE}"
  --system-dir "${SYSTEM_DIR}"
  --start-pc "${START_PC}"
  --run-speed "${RUN_SPEED}"
)
if [[ "${USE_CARTRIDGE}" != "0" ]]; then
  GEN_ARGS+=(--cartridge-map "${CARTRIDGE_MAP}" --cartridge-rom "${CARTRIDGE_ROM_GEN}")
  RUN_ARGS+=(--cart-rom "${CARTRIDGE_ROM_RUNTIME}")
fi
uv run python -m src.main generate \
  "${GEN_ARGS[@]}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED}"
if [[ "${USE_CARTRIDGE}" != "0" ]]; then
  echo "    cartridge_map=${CARTRIDGE_MAP}"
  echo "    cartridge_rom_gen=${CARTRIDGE_ROM_GEN}"
  echo "    cartridge_rom_runtime=${CARTRIDGE_ROM_RUNTIME}"
fi
if [[ "${PROFILE}" == "interactive" && "${PASM_SDL_DEBUG}" != "0" ]]; then
  echo "    SDL debug log -> ${PASM_SDL_LOGFILE}"
fi

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_SDL_DEBUG="${PASM_SDL_DEBUG}" \
PASM_SDL_LOGFILE="${PASM_SDL_LOGFILE}" \
PASM_SDL_AUDIO="${PASM_SDL_AUDIO}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  "${RUN_ARGS[@]}"
