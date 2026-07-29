#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Atari XEGS.
#
# Usage:
#   scripts/run_atari_xegs_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xE477            (optional; leave unset to use reset vector)
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/atari_xegs_interactive
#   EXTRA_CARGO_ARGS="--release"
#   CMAKE_BUILD_TYPE=Release
#   RUN_SPEED=realtime|max
#   PASM_HOST_AUDIO=1
#   KEYBOARD_MAP=examples/hosts/atari800xl/host_keyboard_atari800xl.yaml
#   OS_ROM_LOW=../../roms/atari_xegs/c101687.rom
#   OS_ROM_HIGH=../../roms/atari_xegs/c101687.rom
#   BASIC_ROM=../../roms/atari_xegs/c101687.rom

PROFILE="${1:-interactive}"
if [[ $# -gt 0 ]]; then
  shift
fi
EXTRA_DEBUGGER_ARGS=("$@")
START_PC="${START_PC:-}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
PASM_TRACE="0"
PASM_TRACE_FILE=""
PASM_ATARI800XL_KEY_TRACE="0"
PASM_ATARI800XL_KB_EVENTS="0"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/atari800xl/host_keyboard_atari800xl.yaml}"
OS_ROM_LOW="${OS_ROM_LOW:-../../roms/atari_xegs/c101687.rom}"
OS_ROM_HIGH="${OS_ROM_HIGH:-../../roms/atari_xegs/c101687.rom}"
BASIC_ROM="${BASIC_ROM:-../../roms/atari_xegs/c101687.rom}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

resolve_path_for_gen() {
  local p="$1"
  if [[ -z "$p" ]]; then
    printf "%s" ""
    return 0
  fi
  if [[ "$p" = /* ]]; then
    printf "%s" "$p"
    return 0
  fi
  if [[ -f "${SYSTEM_DIR_ABS}/${p}" ]]; then
    if command -v realpath >/dev/null 2>&1; then
      realpath "${SYSTEM_DIR_ABS}/${p}"
    elif command -v readlink >/dev/null 2>&1; then
      readlink -f "${SYSTEM_DIR_ABS}/${p}"
    else
      printf "%s" "${SYSTEM_DIR_ABS}/${p}"
    fi
    return 0
  fi
  if [[ -f "$p" ]]; then
    if command -v realpath >/dev/null 2>&1; then
      realpath "$p"
    elif command -v readlink >/dev/null 2>&1; then
      readlink -f "$p"
    else
      printf "%s" "$p"
    fi
    return 0
  fi
  printf "%s" "$p"
}

PROCESSOR="examples/processors/mos6502.yaml"
IC_ANTIC="examples/ics/atari800xl/atari800xl_antic.yaml"
IC_GTIA="examples/ics/atari800xl/atari800xl_gtia.yaml"
IC_POKEY="examples/ics/atari800xl/atari800xl_pokey.yaml"
IC_PIA="examples/ics/atari800xl/atari800xl_pia_6520.yaml"
IC_MMU="examples/ics/atari800xl/atari800xl_mmu.yaml"
IC_MAIN_RAM="examples/ics/atari800xl/atari800xl_main_ram.yaml"
DEVICE_KB="examples/devices/atari800xl/atari800xl_keyboard.yaml"
DEVICE_CTRL="examples/devices/atari800xl/atari800xl_controller.yaml"
DEVICE_VIDEO="examples/devices/atari800xl/atari800xl_video.yaml"
DEVICE_SPEAKER="examples/devices/atari800xl/atari800xl_speaker.yaml"
DEVICE_TV="examples/devices/common/tv_crt_mono.yaml"
case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/atari_xegs/atari_xegs_default.yaml"
    HOST="examples/hosts/atari800xl/atari800xl_host_stub.yaml"
    DEFAULT_OUTPUT="generated/atari_xegs_default"
    DEVICE_ARGS="--device ${DEVICE_CTRL} --device ${DEVICE_VIDEO} --device ${DEVICE_SPEAKER} --device ${DEVICE_TV}"
    ;;
  interactive)
    SYSTEM="examples/systems/atari_xegs/atari_xegs_interactive.yaml"
    HOST="examples/hosts/atari800xl/atari800xl_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/atari_xegs_interactive"
    DEVICE_ARGS="--device ${DEVICE_KB} --device ${DEVICE_CTRL} --device ${DEVICE_VIDEO} --device ${DEVICE_SPEAKER} --device ${DEVICE_TV}"
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
SYSTEM_FOR_GEN="${SYSTEM}"

if [[ ! -f "${SYSTEM_DIR_ABS}/${OS_ROM_LOW}" && ! -f "${OS_ROM_LOW}" ]]; then
  echo "Warning: OS ROM (low) not found (${OS_ROM_LOW})." >&2
fi
if [[ ! -f "${SYSTEM_DIR_ABS}/${OS_ROM_HIGH}" && ! -f "${OS_ROM_HIGH}" ]]; then
  echo "Warning: OS ROM (high) not found (${OS_ROM_HIGH})." >&2
fi
if [[ ! -f "${SYSTEM_DIR_ABS}/${BASIC_ROM}" && ! -f "${BASIC_ROM}" ]]; then
  echo "Warning: BASIC ROM not found (${BASIC_ROM})." >&2
fi
TMP_SYSTEM="${SYSTEM_DIR_ABS}/.tmp_atari_xegs_system_${$}_$RANDOM.yaml"
touch "${TMP_SYSTEM}"
trap 'rm -f "${TMP_SYSTEM}"' EXIT
OS_ROM_LOW_GEN="$(resolve_path_for_gen "${OS_ROM_LOW}")"
OS_ROM_HIGH_GEN="$(resolve_path_for_gen "${OS_ROM_HIGH}")"
BASIC_ROM_GEN="$(resolve_path_for_gen "${BASIC_ROM}")"
python - "${SYSTEM}" "${TMP_SYSTEM}" "${OS_ROM_LOW_GEN}" "${OS_ROM_HIGH_GEN}" "${BASIC_ROM_GEN}" <<'PY'
import sys
import yaml

src_path, dst_path, os_low, os_high, basic_rom = sys.argv[1:6]

with open(src_path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)

rom_images = data.get("memory", {}).get("rom_images", [])
for rom in rom_images:
    name = str(rom.get("name", ""))
    if name == "atari_xegs_basic":
        rom["file"] = basic_rom
    elif name == "atari_xegs_os_low":
        rom["file"] = os_low
    elif name == "atari_xegs_os_high":
        rom["file"] = os_high

with open(dst_path, "w", encoding="utf-8") as f:
    yaml.safe_dump(data, f, sort_keys=False)
PY
SYSTEM_FOR_GEN="${TMP_SYSTEM}"

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM_FOR_GEN}" \
  --ic "${IC_ANTIC}" \
  --ic "${IC_GTIA}" \
  --ic "${IC_POKEY}" \
  --ic "${IC_PIA}" \
  --ic "${IC_MMU}" \
  --ic "${IC_MAIN_RAM}" \
  ${DEVICE_ARGS} \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-glfw}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}" --config "${CMAKE_BUILD_TYPE}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC:-<reset-vector>} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
echo "    os_rom_low=${OS_ROM_LOW} os_rom_high=${OS_ROM_HIGH}"
echo "    basic_rom=${BASIC_ROM}"

BUILD_DIR_ABS="$(cd "$(dirname "${BUILD_DIR}")" && pwd)/$(basename "${BUILD_DIR}")"
CMAKE_CONFIG_BUILD_DIR="${BUILD_DIR}/${CMAKE_BUILD_TYPE}"
if [[ -d "${CMAKE_CONFIG_BUILD_DIR}" ]]; then
  CMAKE_CONFIG_BUILD_DIR_ABS="$(cd "$(dirname "${CMAKE_CONFIG_BUILD_DIR}")" && pwd)/$(basename "${CMAKE_CONFIG_BUILD_DIR}")"
else
  CMAKE_CONFIG_BUILD_DIR_ABS="${BUILD_DIR_ABS}"
fi

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_EMU_BUILD_DIR="${CMAKE_CONFIG_BUILD_DIR_ABS}" \
PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json" \
PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
PASM_TRACE="${PASM_TRACE}" \
PASM_TRACE_FILE="${PASM_TRACE_FILE}" \
PASM_ATARI800XL_KEY_TRACE="${PASM_ATARI800XL_KEY_TRACE}" \
PASM_ATARI800XL_KB_EVENTS="${PASM_ATARI800XL_KB_EVENTS}" \
PASM_SYSTEM_DIR="${SYSTEM_DIR_ABS}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR_ABS}" \
  ${START_PC:+--start-pc "${START_PC}"} \
  --run-speed "${RUN_SPEED}" \
  ${KEYBOARD_MAP:+--keyboard-map "${KEYBOARD_MAP}"} \
  "${EXTRA_DEBUGGER_ARGS[@]}"
