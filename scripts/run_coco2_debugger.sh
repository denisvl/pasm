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
CARTRIDGE_ROM_RUN="${CARTRIDGE_ROM_RUN:-}"
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
IC_VDG="examples/ics/coco2/coco2_vdg_6847t1.yaml"
IC_CART_EXP="examples/ics/coco1/coco1_cart_expansion.yaml"
IC_MAIN_RAM="examples/ics/coco1/coco1_main_ram.yaml"
DEVICE_KB="examples/devices/coco1/coco_keyboard.yaml"
DEVICE_GP="examples/devices/coco1/coco_gameport.yaml"
DEVICE_VIDEO="examples/devices/coco1/coco_video.yaml"
DEVICE_SPK="examples/devices/coco1/coco_speaker.yaml"
DEVICE_CASS="examples/devices/common/cassette_transport.yaml"
SYSTEM_DIR="examples/systems/coco2"

if [[ "$PROFILE" == "default" ]]; then
  SYSTEM="examples/systems/coco2/coco2_default.yaml"
  HOST="examples/hosts/coco1/coco_host_stub.yaml"
  DEFAULT_OUTPUT="generated/mc6809_coco2"
else
  SYSTEM="examples/systems/coco2/coco2_interactive.yaml"
  HOST="examples/hosts/coco1/coco_host_hal_interactive.yaml"
  DEFAULT_OUTPUT="generated/mc6809_coco2_sdl"
fi

OUTPUT_DIR="${OUTPUT_DIR:-$DEFAULT_OUTPUT}"
BUILD_DIR="$OUTPUT_DIR/build"
OUTPUT_DIR_ABS="$(cd "$REPO_ROOT" && mkdir -p "$OUTPUT_DIR" && cd "$OUTPUT_DIR" && pwd)"
BUILD_DIR_ABS="$(cd "$REPO_ROOT" && mkdir -p "$BUILD_DIR" && cd "$BUILD_DIR" && pwd)"
CMAKE_CONFIG_BUILD_DIR="$BUILD_DIR/$CMAKE_BUILD_TYPE"
if [[ -d "$CMAKE_CONFIG_BUILD_DIR" ]]; then
  CMAKE_CONFIG_BUILD_DIR_ABS="$(cd "$CMAKE_CONFIG_BUILD_DIR" && pwd)"
else
  CMAKE_CONFIG_BUILD_DIR_ABS="$BUILD_DIR_ABS"
fi
SYSTEM_DIR_ABS="$(cd "$REPO_ROOT" && cd "$(dirname "$SYSTEM")" && pwd)"
CARTRIDGE_DIR="${CARTRIDGE_DIR:-$REPO_ROOT/examples/roms/coco2}"

if [[ "$USE_CARTRIDGE" == "0" ]]; then
  [[ -n "$CARTRIDGE_MAP" ]] && USE_CARTRIDGE=1
  [[ -n "$CARTRIDGE_ROM_GEN" ]] && USE_CARTRIDGE=1
  [[ -n "$CARTRIDGE_ROM_RUN" ]] && USE_CARTRIDGE=1
  [[ -n "$CARTRIDGE_DIR" ]] && USE_CARTRIDGE=1
fi

if [[ "$USE_CARTRIDGE" == "1" ]]; then
  [[ -z "$CARTRIDGE_MAP" ]] && CARTRIDGE_MAP="examples/cartridges/coco1/coco_mapper_none.yaml"
  if [[ -z "$CARTRIDGE_ROM_GEN" && -z "$CARTRIDGE_ROM_RUN" ]]; then
    CARTRIDGE_ROM_GEN="../../roms/coco1/Download V1.1 (1983) (26-3046) (Tandy) [a1].ccc"
  fi
fi

CARTRIDGE_ROM_RUNTIME="$CARTRIDGE_ROM_RUN"
if [[ "$USE_CARTRIDGE" == "1" ]]; then
  if [[ -z "$CARTRIDGE_ROM_RUNTIME" ]]; then
    CARTRIDGE_ROM_RUNTIME="$SYSTEM_DIR_ABS/$CARTRIDGE_ROM_GEN"
  fi
  if [[ -z "$CARTRIDGE_ROM_RUNTIME" ]]; then
    CARTRIDGE_ROM_RUNTIME="$REPO_ROOT/examples/roms/coco1/Download V1.1 (1983) (26-3046) (Tandy) [a1].ccc"
  fi
  if [[ ! -f "$CARTRIDGE_ROM_RUNTIME" ]]; then
    CARTRIDGE_ROM_RUNTIME="$(cd "$REPO_ROOT" && cd "$(dirname "$CARTRIDGE_ROM_GEN")" && pwd)/$(basename "$CARTRIDGE_ROM_GEN")"
  fi
  if [[ ! -f "$CARTRIDGE_ROM_RUNTIME" ]]; then
    echo "Cartridge ROM not found: $CARTRIDGE_ROM_RUNTIME" >&2
    exit 4
  fi
fi

GEN_CARTRIDGE_ARGS=()
RUN_CARTRIDGE_ARGS=()
if [[ "$USE_CARTRIDGE" == "1" ]]; then
  CART_GEN_ROM="$CARTRIDGE_ROM_GEN"
  [[ -z "$CART_GEN_ROM" ]] && CART_GEN_ROM="$CARTRIDGE_ROM_RUNTIME"
  GEN_CARTRIDGE_ARGS=(--cartridge-map "$CARTRIDGE_MAP" --cartridge-rom "$CART_GEN_ROM")
  RUN_CARTRIDGE_ARGS=(--cartridge-dir "$CARTRIDGE_DIR" --cart-rom "$CARTRIDGE_ROM_RUNTIME")
fi

KEYBOARD_ARGS=(--keyboard-map "$KEYBOARD_MAP")
if [[ "$PROFILE" == "interactive" ]]; then
  KEYBOARD_ARGS+=(--controller-map "$CONTROLLER_MAP")
fi

echo "[1/3] Generating emulator -> $OUTPUT_DIR"
uv run python -m src.main generate \
  --processor "$PROCESSOR" \
  --system "$SYSTEM" \
  --ic "$IC_SAM" \
  --ic "$IC_PIA0" \
  --ic "$IC_PIA1" \
  --ic "$IC_VDG" \
  --ic "$IC_CART_EXP" \
  --ic "$IC_MAIN_RAM" \
  --device "$DEVICE_KB" \
  --device "$DEVICE_GP" \
  --device "$DEVICE_VIDEO" \
  --device "$DEVICE_SPK" \
  --device "$DEVICE_CASS" \
  --host "$HOST" \
  --host-backend "$HOST_BACKEND" \
  "${GEN_CARTRIDGE_ARGS[@]}" \
  --output "$OUTPUT_DIR"

echo "[2/3] Building emulator with CMake -> $BUILD_DIR"
cmake -S "$OUTPUT_DIR" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE="$CMAKE_BUILD_TYPE"
cmake --build "$BUILD_DIR" --config "$CMAKE_BUILD_TYPE"

echo "[3/3] Running Rust debugger (linked backend)"
export PASM_EMU_DIR="$OUTPUT_DIR_ABS"
export PASM_EMU_BUILD_DIR="$CMAKE_CONFIG_BUILD_DIR_ABS"
export PASM_EMU_MANIFEST="$OUTPUT_DIR_ABS/debugger_link.json"
export PATH="$PASM_EMU_BUILD_DIR:$PATH"
export PASM_HOST_AUDIO="$PASM_HOST_AUDIO"
export PASM_EMU_CART_PICKER_RAW_KEYS="$PASM_EMU_CART_PICKER_RAW_KEYS"
export PASM_SYSTEM_DIR="$SYSTEM_DIR"

cargo run $EXTRA_CARGO_ARGS --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "$MEMORY_SIZE" \
  --system-dir "$SYSTEM_DIR" \
  "${KEYBOARD_ARGS[@]}" \
  "${RUN_CARTRIDGE_ARGS[@]}" \
  --start-pc "$START_PC" \
  --run-speed "$RUN_SPEED" \
  "$@"
