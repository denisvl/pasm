#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Atari 2600.
#
# Usage:
#   scripts/run_atari2600_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xF000            (optional; leave unset to use reset vector)
#   MEMORY_SIZE=8192
#   OUTPUT_DIR=generated/atari2600_interactive
#   EXTRA_CARGO_ARGS="--release"
#   CMAKE_BUILD_TYPE=Release
#   RUN_SPEED=realtime|max
#   PASM_SDL_AUDIO=1
#   USE_CARTRIDGE=1|0
#   CARTRIDGE_MAP=examples/cartridges/atari2600/atari2600_mapper_none.yaml
#   CARTRIDGE_ROM_GEN=../../roms/atari2600/Pac-Man\ \(USA\).a26
#   CARTRIDGE_ROM_RUNTIME=/abs/path/to/cart.a26

PROFILE="${1:-interactive}"
START_PC="${START_PC:-}"
MEMORY_SIZE="${MEMORY_SIZE:-8192}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
PASM_SDL_AUDIO="${PASM_SDL_AUDIO:-1}"
USE_CARTRIDGE="${USE_CARTRIDGE:-1}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/atari2600/atari2600_mapper_none.yaml}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../../roms/atari2600/Pitfall! (1982) (Activision) [!].a26}"
CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

PROCESSOR="examples/processors/mos6502.yaml"
IC_MAIN="examples/ics/atari2600/atari2600_tia_riot.yaml"
DEVICE_VIDEO="examples/devices/atari2600/atari2600_video.yaml"
DEVICE_SPK="examples/devices/atari2600/atari2600_speaker.yaml"
SYSTEM_DIR="examples/systems"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/atari2600/mos6502_atari2600_default.yaml"
    HOST="examples/hosts/atari2600/atari2600_host_stub.yaml"
    DEFAULT_OUTPUT="generated/atari2600_default"
    ;;
  interactive)
    SYSTEM="examples/systems/atari2600/mos6502_atari2600_interactive.yaml"
    HOST="examples/hosts/atari2600/atari2600_host_sdl2_interactive.yaml"
    DEFAULT_OUTPUT="generated/atari2600_interactive"
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
ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"

GEN_CARTRIDGE_ARGS=()
RUN_CARTRIDGE_ARGS=()
if [[ "${USE_CARTRIDGE}" != "0" ]]; then
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
  RUN_CARTRIDGE_ARGS+=(--cart-rom "${ROM_RUNTIME}")
fi

if [[ "${USE_CARTRIDGE}" != "0" && ! -f "${ROM_RUNTIME}" ]]; then
  echo "Warning: cartridge ROM not found (${ROM_RUNTIME})." >&2
fi

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC_MAIN}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPK}" \
  --host "${HOST}" \
  "${GEN_CARTRIDGE_ARGS[@]}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}" --config "${CMAKE_BUILD_TYPE}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC:-<reset-vector>} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE} use_cartridge=${USE_CARTRIDGE}"
if [[ "${USE_CARTRIDGE}" != "0" ]]; then
  echo "    cartridge_map=${CARTRIDGE_MAP}"
  echo "    cartridge_rom_gen=${CARTRIDGE_ROM_GEN}"
  echo "    cartridge_rom_runtime=${ROM_RUNTIME}"
fi

if [[ -n "${START_PC}" ]]; then
  set -- --start-pc "${START_PC}"
else
  set --
fi

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_EMU_BUILD_DIR="${BUILD_DIR}" \
PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json" \
PASM_SDL_AUDIO="${PASM_SDL_AUDIO}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR}" \
  "${RUN_CARTRIDGE_ARGS[@]}" \
  "$@" \
  --run-speed "${RUN_SPEED}"
