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
#   FLOPPY=/abs/path/to/disk.jv1|.jv3|.dmk|.dsk
#   DISK_ROM=/abs/path/to/disk_basic.rom
#   ECB_ROM=/abs/path/to/extbasic.rom              (map Extended BASIC at $8000-$9FFF)
#   USE_CARTRIDGE=0|1
#   CARTRIDGE_MAP=examples/cartridges/coco1/coco_mapper_none.yaml
#   CARTRIDGE_ROM_GEN=../../roms/coco1/Downland V1.1 (1983) (26-3046) (Tandy) [a1].ccc
#   CARTRIDGE_ROM_RUN=/abs/path/to/cart.rom  (optional override)
#   CARTRIDGE_DIR=/abs/path/to/coco1/roms     (enable runtime cartridge picker list)
#   BOOT_CARTRIDGE=0|1                          (default 0: boot base CoCo, then pick cart)
#   PASM_EMU_CART_PICKER_RAW_KEYS=0|1           (default 1; raw picker hotkey F12)

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0xA027}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
USE_CARTRIDGE="${USE_CARTRIDGE:-0}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-}"
CARTRIDGE_DIR="${CARTRIDGE_DIR:-}"
BOOT_CARTRIDGE="${BOOT_CARTRIDGE:-0}"
PASM_EMU_CART_PICKER_RAW_KEYS="${PASM_EMU_CART_PICKER_RAW_KEYS:-1}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/coco1/host_keyboard_coco.yaml}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/coco1/host_controller_coco.yaml}"
DISK_ROM="${DISK_ROM:-}"
ECB_ROM="${ECB_ROM:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

PROCESSOR="examples/processors/mc6809.yaml"
IC_SAM="examples/ics/coco1/coco1_sam_6883.yaml"
IC_PIA0="examples/ics/coco1/coco1_pia0_6821.yaml"
IC_PIA1="examples/ics/coco1/coco1_pia1_6821.yaml"
IC_VDG="examples/ics/coco1/coco1_vdg_6847.yaml"
IC_CART_EXP="examples/ics/coco1/coco1_cart_expansion.yaml"
IC_MAIN_RAM="examples/ics/coco1/coco1_main_ram.yaml"
IC_FDC="examples/ics/common/wd1793.yaml"
DEVICE_KB="examples/devices/coco1/coco_keyboard.yaml"
DEVICE_GP="examples/devices/coco1/coco_gameport.yaml"
DEVICE_VIDEO="examples/devices/coco1/coco_video.yaml"
DEVICE_SPK="examples/devices/coco1/coco_speaker.yaml"
DEVICE_CASS="examples/devices/common/cassette_transport.yaml"
DEVICE_FLOPPY_BACKEND="examples/devices/common/trs80_floppy_image_backend.yaml"
RUN_FLOPPY_ARGS=()

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
BUILD_DIR_ABS="$(cd "$(dirname "${BUILD_DIR}")" && pwd)/$(basename "${BUILD_DIR}")"
SYSTEM_DIR="$(dirname "${SYSTEM}")"
SYSTEM_DIR_ABS="$(cd "$(dirname "${SYSTEM}")" && pwd)"
TEMP_SYSTEM_FILE=""
if [[ -z "${CARTRIDGE_DIR}" ]]; then
  CARTRIDGE_DIR="${REPO_ROOT}/examples/roms/coco1"
fi

if [[ -n "${FLOPPY:-}" ]]; then
  RUN_FLOPPY_ARGS+=(--floppy "${FLOPPY}")
fi

if [[ -n "${DISK_ROM}" ]]; then
  USE_CARTRIDGE=1
  CARTRIDGE_MAP="${CARTRIDGE_MAP:-examples/cartridges/coco1/coco_mapper_none.yaml}"
  CARTRIDGE_ROM_RUN="${CARTRIDGE_ROM_RUN:-${DISK_ROM}}"
  if [[ "${BOOT_CARTRIDGE}" == "0" ]]; then
    BOOT_CARTRIDGE=1
  fi
fi

if [[ -n "${ECB_ROM}" ]]; then
  if command -v realpath >/dev/null 2>&1; then
    ECB_ROM_RUNTIME="$(realpath "${ECB_ROM}")"
  elif command -v readlink >/dev/null 2>&1; then
    ECB_ROM_RUNTIME="$(readlink -f "${ECB_ROM}")"
  else
    ECB_ROM_RUNTIME="${ECB_ROM}"
  fi
  if [[ ! -f "${ECB_ROM_RUNTIME}" ]]; then
    echo "Extended BASIC ROM not found: ${ECB_ROM_RUNTIME}" >&2
    exit 4
  fi
  TEMP_SYSTEM_FILE="${SYSTEM_DIR}/.tmp_$(basename "${SYSTEM}" .yaml)_$$.yaml"
  ECB_ROM_RUNTIME="${ECB_ROM_RUNTIME}" TEMP_SYSTEM_FILE="${TEMP_SYSTEM_FILE}" SYSTEM="${SYSTEM}" \
    python3 - <<'PY'
import os
from pathlib import Path

system_path = Path(os.environ["SYSTEM"])
temp_path = Path(os.environ["TEMP_SYSTEM_FILE"])
ecb_rom = os.environ["ECB_ROM_RUNTIME"]
text = system_path.read_text(encoding="utf-8")
old_regions = """  - name: RAM_LOWER
    start: 0
    size: 40960
    read_write: true
  - name: ROM_COCOROM_A000
"""
new_regions = """  - name: RAM_LOWER
    start: 0
    size: 32768
    read_write: true
  - name: ROM_EXTBASIC_8000
    start: 32768
    size: 8192
    read_only: true
  - name: ROM_COCOROM_A000
"""
if old_regions not in text:
    raise SystemExit("unexpected CoCo memory layout; cannot inject ECB ROM")
text = text.replace(old_regions, new_regions, 1)
old_roms = """  rom_images:
  - name: coco_rom_primary
"""
new_roms = f"""  rom_images:
  - name: coco_rom_extbasic
    file: {ecb_rom}
    target_region: ROM_EXTBASIC_8000
    offset: 0
  - name: coco_rom_primary
"""
if old_roms not in text:
    raise SystemExit("unexpected CoCo rom_images layout; cannot inject ECB ROM")
text = text.replace(old_roms, new_roms, 1)
temp_path.write_text(text, encoding="utf-8")
PY
  SYSTEM="${TEMP_SYSTEM_FILE}"
  SYSTEM_DIR="$(dirname "${SYSTEM}")"
  SYSTEM_DIR_ABS="$(cd "$(dirname "${SYSTEM}")" && pwd)"
fi

if [[ -n "${FLOPPY:-}" && -z "${DISK_ROM}" && -z "${CARTRIDGE_ROM_RUN:-}" && -z "${CARTRIDGE_ROM_GEN}" ]]; then
  echo "warning: FLOPPY is set but no DISK_ROM/cartridge ROM is configured; CoCo Disk BASIC will not be available." >&2
fi

# Cartridge mode can be enabled explicitly (USE_CARTRIDGE=1) or implicitly by setting any
# cartridge-related env vars (legacy behavior), including CARTRIDGE_DIR for picker-only usage.
if [[ "${USE_CARTRIDGE}" == "0" ]]; then
  if [[ -n "${CARTRIDGE_MAP}" || -n "${CARTRIDGE_ROM_GEN}" || -n "${CARTRIDGE_ROM_RUN:-}" || -n "${CARTRIDGE_DIR}" ]]; then
    USE_CARTRIDGE=1
  fi
fi

if [[ "${USE_CARTRIDGE}" == "1" ]]; then
  # Defaults when using cartridges: Downland + no-mapper cart layout, unless overridden.
  if [[ -z "${CARTRIDGE_MAP}" ]]; then
    CARTRIDGE_MAP="examples/cartridges/coco1/coco_mapper_none.yaml"
  fi
  if [[ -z "${CARTRIDGE_ROM_GEN}" && -z "${CARTRIDGE_ROM_RUN:-}" ]]; then
    CARTRIDGE_ROM_GEN="../../roms/coco1/Downland V1.1 (1983) (26-3046) (Tandy) [a1].ccc"
  fi

  if [[ -z "${CARTRIDGE_MAP}" ]]; then
    echo "Set CARTRIDGE_MAP when enabling cartridge mode." >&2
    exit 4
  fi
  if [[ -z "${CARTRIDGE_ROM_GEN}" && -z "${CARTRIDGE_ROM_RUN:-}" ]]; then
    echo "Set either CARTRIDGE_ROM_GEN or CARTRIDGE_ROM_RUN when enabling cartridge mode." >&2
    exit 4
  fi
fi

GEN_CARTRIDGE_ARGS=()
RUN_CARTRIDGE_ARGS=()
if [[ "${USE_CARTRIDGE}" == "1" || -n "${CARTRIDGE_DIR}" ]]; then
  if [[ -n "${CARTRIDGE_DIR}" ]]; then
    if [[ ! -d "${CARTRIDGE_DIR}" ]]; then
      echo "warning: CARTRIDGE_DIR does not exist: ${CARTRIDGE_DIR}" >&2
      echo "         picker hotkey will appear to do nothing until this is fixed." >&2
    fi
    RUN_CARTRIDGE_ARGS+=(--cartridge-dir "${CARTRIDGE_DIR}")
  fi
fi

if [[ "${USE_CARTRIDGE}" == "1" ]]; then
  if [[ -n "${CARTRIDGE_ROM_RUN:-}" ]]; then
    if command -v realpath >/dev/null 2>&1; then
      CARTRIDGE_ROM_RUNTIME="$(realpath "${CARTRIDGE_ROM_RUN}")"
    elif command -v readlink >/dev/null 2>&1; then
      CARTRIDGE_ROM_RUNTIME="$(readlink -f "${CARTRIDGE_ROM_RUN}")"
    else
      CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUN}"
    fi
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
  if [[ "${BOOT_CARTRIDGE}" != "0" ]]; then
    RUN_CARTRIDGE_ARGS+=(--cart-rom "${CARTRIDGE_ROM_RUNTIME}")
  fi
fi

KEYBOARD_ARGS=()
if [[ "${PROFILE}" == "interactive" || "${PROFILE}" == "default" ]]; then
  KEYBOARD_ARGS=(--keyboard-map "${KEYBOARD_MAP}")
fi
if [[ "${PROFILE}" == "interactive" ]]; then
  KEYBOARD_ARGS+=(--controller-map "${CONTROLLER_MAP}")
fi

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC_SAM}" \
  --ic "${IC_PIA0}" \
  --ic "${IC_PIA1}" \
  --ic "${IC_VDG}" \
  --ic "${IC_CART_EXP}" \
  --ic "${IC_MAIN_RAM}" \
  --ic "${IC_FDC}" \
  --device "${DEVICE_KB}" \
  --device "${DEVICE_GP}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPK}" \
  --device "${DEVICE_CASS}" \
  --device "${DEVICE_FLOPPY_BACKEND}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-glfw}" \
  "${GEN_CARTRIDGE_ARGS[@]}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}" --config "${CMAKE_BUILD_TYPE}"
PASM_EMU_BUILD_DIR="${BUILD_DIR_ABS}"
if [[ -d "${BUILD_DIR_ABS}/${CMAKE_BUILD_TYPE}" ]]; then
  PASM_EMU_BUILD_DIR="${BUILD_DIR_ABS}/${CMAKE_BUILD_TYPE}"
fi

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED} cmake_build_type=${CMAKE_BUILD_TYPE}"
if [[ "${USE_CARTRIDGE}" == "1" ]]; then
  echo "    cartridge_map=${CARTRIDGE_MAP}"
  echo "    cartridge_rom_gen=${CARTRIDGE_ROM_GEN}"
  echo "    cartridge_rom_runtime=${CARTRIDGE_ROM_RUNTIME}"
fi
echo "    cartridge_dir=${CARTRIDGE_DIR}"
echo "    boot_cartridge=${BOOT_CARTRIDGE}"
echo "    cart_picker_raw_keys=${PASM_EMU_CART_PICKER_RAW_KEYS}"
if [[ -n "${FLOPPY:-}" ]]; then
  echo "    floppy=${FLOPPY}"
fi
if [[ -n "${DISK_ROM}" ]]; then
  echo "    disk_rom=${DISK_ROM}"
fi
if [[ -n "${ECB_ROM}" ]]; then
  echo "    ecb_rom=${ECB_ROM_RUNTIME}"
fi
PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_EMU_BUILD_DIR="${PASM_EMU_BUILD_DIR}" \
PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json" \
PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
PASM_EMU_CART_PICKER_RAW_KEYS="${PASM_EMU_CART_PICKER_RAW_KEYS}" \
PASM_SYSTEM_DIR="${SYSTEM_DIR}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR}" \
  "${KEYBOARD_ARGS[@]}" \
  "${RUN_FLOPPY_ARGS[@]}" \
  "${RUN_CARTRIDGE_ARGS[@]}" \
  --start-pc "${START_PC}" \
  --run-speed "${RUN_SPEED}"

if [[ -n "${TEMP_SYSTEM_FILE}" ]]; then
  rm -f "${TEMP_SYSTEM_FILE}"
fi
