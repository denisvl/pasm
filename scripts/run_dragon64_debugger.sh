#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Dragon 64.
#
# Usage:
#   scripts/run_dragon64_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xB3B4
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/mc6809_dragon64_sdl
#   EXTRA_CARGO_ARGS="--release"
#   CMAKE_BUILD_TYPE=Release
#   RUN_SPEED=realtime|max
#   PASM_HOST_AUDIO=1
#   HOST_BACKEND=glfw|sdl2|stub
#   USE_CARTRIDGE=0|1
#   CARTRIDGE_MAP=examples/cartridges/coco1/coco_mapper_none.yaml
#   CARTRIDGE_ROM_GEN=../../roms/dragon64/ddos10.rom
#   CARTRIDGE_ROM_RUN=/abs/path/to/cart.rom  (optional override)
#   CARTRIDGE_DIR=/abs/path/to/dragon64/roms (enable runtime cartridge picker list)
#   BOOT_CARTRIDGE=0|1                        (default 0: boot base Dragon 64, then pick cart)
#   PASM_EMU_CART_PICKER_RAW_KEYS=0|1         (default 1; raw picker hotkey F12)

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0xB3B4}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
HOST_BACKEND="${HOST_BACKEND:-glfw}"
USE_CARTRIDGE="${USE_CARTRIDGE:-0}"
CARTRIDGE_MAP="${CARTRIDGE_MAP:-}"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-}"
CARTRIDGE_ROM_RUN="${CARTRIDGE_ROM_RUN:-}"
CARTRIDGE_DIR="${CARTRIDGE_DIR:-}"
BOOT_CARTRIDGE="${BOOT_CARTRIDGE:-0}"
PASM_EMU_CART_PICKER_RAW_KEYS="${PASM_EMU_CART_PICKER_RAW_KEYS:-1}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/coco1/host_keyboard_coco.yaml}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/coco1/host_controller_coco.yaml}"

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
DEVICE_KB="examples/devices/coco1/coco_keyboard.yaml"
DEVICE_GP="examples/devices/coco1/coco_gameport.yaml"
DEVICE_VIDEO="examples/devices/coco1/coco_video.yaml"
DEVICE_SPK="examples/devices/coco1/coco_speaker.yaml"
DEVICE_CASS="examples/devices/common/cassette_transport.yaml"
SYSTEM_DIR="examples/systems/dragon64"

if [[ "$PROFILE" == "default" ]]; then
  SYSTEM="examples/systems/dragon64/dragon64_default.yaml"
  HOST="examples/hosts/coco1/coco_host_stub.yaml"
  DEFAULT_OUTPUT="generated/mc6809_dragon64"
else
  SYSTEM="examples/systems/dragon64/dragon64_interactive.yaml"
  HOST="examples/hosts/coco1/coco_host_hal_interactive.yaml"
  DEFAULT_OUTPUT="generated/mc6809_dragon64_sdl"
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
CARTRIDGE_DIR="${CARTRIDGE_DIR:-$REPO_ROOT/examples/roms/dragon64}"

if [[ "$USE_CARTRIDGE" == "0" ]]; then
  [[ -n "$CARTRIDGE_MAP" ]] && USE_CARTRIDGE=1
  [[ -n "$CARTRIDGE_ROM_GEN" ]] && USE_CARTRIDGE=1
  [[ -n "$CARTRIDGE_ROM_RUN" ]] && USE_CARTRIDGE=1
  [[ -n "$CARTRIDGE_DIR" ]] && USE_CARTRIDGE=1
fi

if [[ "$USE_CARTRIDGE" == "1" ]]; then
  [[ -z "$CARTRIDGE_MAP" ]] && CARTRIDGE_MAP="examples/cartridges/coco1/coco_mapper_none.yaml"
  if [[ -z "$CARTRIDGE_ROM_GEN" && -z "$CARTRIDGE_ROM_RUN" ]]; then
    CARTRIDGE_ROM_GEN="../../roms/dragon64/ddos10.rom"
  fi
fi

CARTRIDGE_ROM_RUNTIME="$CARTRIDGE_ROM_RUN"
if [[ "$USE_CARTRIDGE" == "1" ]]; then
  if [[ -z "$CARTRIDGE_ROM_RUNTIME" ]]; then
    if [[ "$CARTRIDGE_ROM_GEN" = /* ]]; then
      CARTRIDGE_ROM_RUNTIME="$CARTRIDGE_ROM_GEN"
    elif [[ -f "$SYSTEM_DIR_ABS/$CARTRIDGE_ROM_GEN" ]]; then
      CARTRIDGE_ROM_RUNTIME="$SYSTEM_DIR_ABS/$CARTRIDGE_ROM_GEN"
    else
      CARTRIDGE_ROM_RUNTIME="$REPO_ROOT/$CARTRIDGE_ROM_GEN"
    fi
  fi
  if [[ ! -f "$CARTRIDGE_ROM_RUNTIME" ]]; then
    echo "Cartridge ROM not found: $CARTRIDGE_ROM_RUNTIME" >&2
    echo "Set CARTRIDGE_ROM_RUN to an absolute cartridge path or CARTRIDGE_ROM_GEN to a path relative to ${SYSTEM_DIR_ABS} or ${REPO_ROOT}." >&2
    exit 4
  fi
  if [[ ! -d "$CARTRIDGE_DIR" ]]; then
    echo "Cartridge directory not found: $CARTRIDGE_DIR" >&2
    exit 4
  fi
fi

echo "[1/3] Generating Dragon 64 emulator -> $OUTPUT_DIR"
if [[ "$USE_CARTRIDGE" == "1" ]]; then
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
    --cartridge-map "$CARTRIDGE_MAP" \
    --cartridge-rom "$CARTRIDGE_ROM_GEN" \
    --output "$OUTPUT_DIR"
else
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
    --output "$OUTPUT_DIR"
fi

echo "[2/3] Building Dragon 64 emulator with CMake -> $BUILD_DIR"
cmake -S "$OUTPUT_DIR_ABS" -B "$BUILD_DIR_ABS" -DCMAKE_BUILD_TYPE="$CMAKE_BUILD_TYPE"
cmake --build "$BUILD_DIR_ABS" --config "$CMAKE_BUILD_TYPE"

echo "[3/3] Running Rust debugger (linked backend)"
CARGO_CMD="cargo run $EXTRA_CARGO_ARGS -- --manifest \"$OUTPUT_DIR_ABS/debugger_link.json\" --speed $RUN_SPEED --audio $PASM_HOST_AUDIO"
[[ -n "$KEYBOARD_MAP" ]] && CARGO_CMD="$CARGO_CMD --keyboard-map \"$KEYBOARD_MAP\""
[[ -n "$CONTROLLER_MAP" ]] && CARGO_CMD="$CARGO_CMD --controller-map \"$CONTROLLER_MAP\""
if [[ "$USE_CARTRIDGE" == "1" ]]; then
  [[ "$BOOT_CARTRIDGE" == "1" ]] && CARGO_CMD="$CARGO_CMD --boot-cartridge"
  [[ -n "$CARTRIDGE_ROM_RUNTIME" ]] && CARGO_CMD="$CARGO_CMD --cartridge-rom \"$CARTRIDGE_ROM_RUNTIME\""
  [[ -n "$CARTRIDGE_DIR" ]] && CARGO_CMD="$CARGO_CMD --cartridge-dir \"$CARTRIDGE_DIR\""
  [[ "$PASM_EMU_CART_PICKER_RAW_KEYS" == "1" ]] && CARGO_CMD="$CARGO_CMD --cart-picker-raw-keys"
fi
CARGO_CMD="$CARGO_CMD --auto-run"
cd tools/debugger_tui
echo "$CARGO_CMD"
eval "$CARGO_CMD"