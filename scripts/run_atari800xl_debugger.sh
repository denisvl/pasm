#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Atari 800XL.
#
# Usage:
#   scripts/run_atari800xl_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xE477            (optional; leave unset to use reset vector)
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/atari800xl_interactive
#   EXTRA_CARGO_ARGS="--release"
#   CMAKE_BUILD_TYPE=Release
#   RUN_SPEED=realtime|max
#   PASM_HOST_AUDIO=1
#   CARTRIDGE_MAP=examples/cartridges/atari800xl/atari800xl_cart_8k_none.yaml
#   CARTRIDGE_ROM_GEN=../../roms/atari800xl/Star_Raiders_1979_Atari_US.rom
#   CARTRIDGE_ROM_RUNTIME=/abs/path/to/cart.rom
#   USE_CARTRIDGE=0|1                           (default 1: picker-enabled system)
#   BOOT_CARTRIDGE=0|1                          (default 0: boot BASIC/no cart)
#   CARTRIDGE_DIR=/abs/path/to/atari800xl/roms   (enable runtime cartridge picker list)
#   PASM_EMU_CART_PICKER_RAW_KEYS=0|1            (default 1; raw picker hotkey F12)
#   OS_ROM=../../roms/atari800xl/ATARIXL.ROM
#   BASIC_ROM=../../roms/atari800xl/BASIC_C.ROM
#   SELFTEST_ROM=../../roms/atari800xl/ATARIXL_SELFTEST.ROM

PROFILE="${1:-interactive}"
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
CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/atari800xl/atari800xl_cart_8k_none.yaml}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../../roms/atari800xl/Star_Raiders_1979_Atari_US.rom}"
CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"
USE_CARTRIDGE="${USE_CARTRIDGE:-1}"
BOOT_CARTRIDGE="${BOOT_CARTRIDGE:-0}"
CARTRIDGE_DIR="${CARTRIDGE_DIR:-}"
OS_ROM="${OS_ROM:-../../roms/atari800xl/ATARIXL.ROM}"
BASIC_ROM="${BASIC_ROM:-../../roms/atari800xl/BASIC_C.ROM}"
SELFTEST_ROM="${SELFTEST_ROM:-../../roms/atari800xl/ATARIXL_SELFTEST.ROM}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/atari800xl/host_keyboard_atari800xl.yaml}"
PASM_EMU_CART_PICKER_RAW_KEYS="${PASM_EMU_CART_PICKER_RAW_KEYS:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"
if [[ -z "${CARTRIDGE_DIR}" ]]; then
  CARTRIDGE_DIR="${REPO_ROOT}/examples/roms/atari800xl"
fi

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
DEVICE_TV="examples/devices/common/tv_crt_mono.yaml"
case "${PROFILE}" in
  default)
    if [[ "${USE_CARTRIDGE}" != "0" ]]; then
      SYSTEM="examples/systems/atari800xl/atari800xl_cartridge_default.yaml"
    else
      SYSTEM="examples/systems/atari800xl/atari800xl_default.yaml"
    fi
    HOST="examples/hosts/atari800xl/atari800xl_host_stub.yaml"
    DEFAULT_OUTPUT="generated/atari800xl_default"
    ;;
  interactive)
    if [[ "${USE_CARTRIDGE}" != "0" ]]; then
      SYSTEM="examples/systems/atari800xl/atari800xl_cartridge_interactive.yaml"
    else
      SYSTEM="examples/systems/atari800xl/atari800xl_interactive.yaml"
    fi
    HOST="examples/hosts/atari800xl/atari800xl_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/atari800xl_interactive"
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
ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"
SYSTEM_FOR_GEN="${SYSTEM}"

GEN_CARTRIDGE_ARGS=()
RUN_CARTRIDGE_ARGS=()
GEN_CARTRIDGE_ROM="${CARTRIDGE_ROM_GEN}"
if [[ -n "${CARTRIDGE_ROM_RUNTIME}" ]]; then
  ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME}"
elif command -v realpath >/dev/null 2>&1; then
  ROM_RUNTIME="$(realpath "${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}")"
elif command -v readlink >/dev/null 2>&1; then
  ROM_RUNTIME="$(readlink -f "${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}")"
else
  ROM_RUNTIME="${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}"
fi
if [[ "${USE_CARTRIDGE}" != "0" ]]; then
  if [[ ! -d "${CARTRIDGE_DIR}" ]]; then
    echo "warning: CARTRIDGE_DIR does not exist: ${CARTRIDGE_DIR}" >&2
    echo "         picker hotkey will appear to do nothing until this is fixed." >&2
  fi
  RUN_CARTRIDGE_ARGS+=(--cartridge-dir "${CARTRIDGE_DIR}")
  if [[ "${BOOT_CARTRIDGE}" != "0" ]]; then
    RUN_CARTRIDGE_ARGS+=(--cart-rom "${ROM_RUNTIME}")
  fi

  # Keep picker-enabled cartridge systems booting to BASIC by default:
  # when BOOT_CARTRIDGE=0, seed codegen with BASIC ROM instead of a game cart.
  if [[ "${BOOT_CARTRIDGE}" == "0" ]]; then
    GEN_CARTRIDGE_ROM="${BASIC_ROM}"
  fi
  GEN_CARTRIDGE_ARGS=(--cartridge-map "${CARTRIDGE_MAP}" --cartridge-rom "${GEN_CARTRIDGE_ROM}")
fi

if [[ ! -f "${SYSTEM_DIR_ABS}/${OS_ROM}" && ! -f "${OS_ROM}" ]]; then
  echo "Warning: OS ROM not found (${OS_ROM})." >&2
fi
if [[ ! -f "${SYSTEM_DIR_ABS}/${BASIC_ROM}" && ! -f "${BASIC_ROM}" ]]; then
  echo "Warning: BASIC ROM not found (${BASIC_ROM})." >&2
fi
if [[ ! -f "${SYSTEM_DIR_ABS}/${SELFTEST_ROM}" && ! -f "${SELFTEST_ROM}" ]]; then
  OS_SRC="${SYSTEM_DIR_ABS}/${OS_ROM}"
  SELFTEST_DST="${SYSTEM_DIR_ABS}/${SELFTEST_ROM}"
  if [[ -f "${OS_SRC}" ]]; then
    mkdir -p "$(dirname "${SELFTEST_DST}")"
    dd if="${OS_SRC}" of="${SELFTEST_DST}" bs=1 skip=$((0x1000)) count=$((0x0800)) status=none
    echo "Generated self-test ROM slice: ${SELFTEST_DST}"
  else
    echo "Warning: self-test ROM not found (${SELFTEST_ROM}) and source OS ROM missing (${OS_ROM})." >&2
  fi
fi
if [[ "${USE_CARTRIDGE}" != "0" && "${BOOT_CARTRIDGE}" != "0" && ! -f "${ROM_RUNTIME}" ]]; then
  echo "Warning: cartridge ROM not found (${ROM_RUNTIME})." >&2
fi

# Materialize ROM path overrides into a temp system YAML for codegen
# (do not mutate repository files in-place).
TMP_SYSTEM="${SYSTEM_DIR_ABS}/.tmp_atari800xl_system_${$}_$RANDOM.yaml"
touch "${TMP_SYSTEM}"
trap 'rm -f "${TMP_SYSTEM}"' EXIT
OS_ROM_GEN="$(resolve_path_for_gen "${OS_ROM}")"
BASIC_ROM_GEN="$(resolve_path_for_gen "${BASIC_ROM}")"
SELFTEST_ROM_GEN="$(resolve_path_for_gen "${SELFTEST_ROM}")"
python - "${SYSTEM}" "${TMP_SYSTEM}" "${OS_ROM_GEN}" "${BASIC_ROM_GEN}" "${SELFTEST_ROM_GEN}" <<'PY'
import sys
import yaml

src_path, dst_path, os_rom, basic_rom, selftest_rom = sys.argv[1:6]

with open(src_path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)

rom_images = data.get("memory", {}).get("rom_images", [])
for rom in rom_images:
    name = str(rom.get("name", ""))
    if name == "atari800xl_basic":
        rom["file"] = basic_rom
    elif name == "atari800xl_selftest":
        rom["file"] = selftest_rom
    elif name in ("atari800xl_os", "atari800xl_os_rom"):
        rom["file"] = os_rom

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
  --device "${DEVICE_KB}" \
  --device "${DEVICE_CTRL}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_TV}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-glfw}" \
  "${GEN_CARTRIDGE_ARGS[@]}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}" --config "${CMAKE_BUILD_TYPE}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC:-<reset-vector>} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
echo "    os_rom=${OS_ROM} basic_rom=${BASIC_ROM}"
echo "    use_cartridge=${USE_CARTRIDGE}"
if [[ "${USE_CARTRIDGE}" != "0" ]]; then
  echo "    cartridge_map=${CARTRIDGE_MAP}"
  echo "    cartridge_rom_gen=${GEN_CARTRIDGE_ROM}"
  echo "    cartridge_rom_runtime=${ROM_RUNTIME}"
  echo "    cartridge_dir=${CARTRIDGE_DIR}"
  echo "    boot_cartridge=${BOOT_CARTRIDGE}"
  echo "    cart_picker_raw_keys=${PASM_EMU_CART_PICKER_RAW_KEYS}"
fi

if [[ -n "${START_PC}" ]]; then
  set -- --start-pc "${START_PC}"
else
  set --
fi

KEYBOARD_ARGS=()
if [[ "${PROFILE}" == "interactive" ]]; then
  KEYBOARD_ARGS=(--keyboard-map "${KEYBOARD_MAP}")
fi

PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_EMU_BUILD_DIR="${BUILD_DIR}" \
PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json" \
PASM_SYSTEM_DIR="${SYSTEM_DIR_ABS}" \
PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
PASM_TRACE="${PASM_TRACE}" \
PASM_TRACE_FILE="${PASM_TRACE_FILE}" \
PASM_ATARI800XL_KEY_TRACE="${PASM_ATARI800XL_KEY_TRACE}" \
PASM_ATARI800XL_KB_EVENTS="${PASM_ATARI800XL_KB_EVENTS}" \
PASM_EMU_CART_PICKER_RAW_KEYS="${PASM_EMU_CART_PICKER_RAW_KEYS}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR}" \
  "${KEYBOARD_ARGS[@]}" \
  "${RUN_CARTRIDGE_ARGS[@]}" \
  "$@" \
  --run-speed "${RUN_SPEED}"
