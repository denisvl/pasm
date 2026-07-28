#!/usr/bin/env bash
# One-shot helper: generate + build + run PASM Rust debugger for Apple II Plus.
#
# Usage:
#   scripts/run_apple2plus_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xFA62
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/apple2plus_interactive
#   EXTRA_CARGO_ARGS=--release
#   EXTRA_CMAKE_ARGS=-DCMAKE_TOOLCHAIN_FILE=...
#   RUN_SPEED=realtime|max
#   PASM_HOST_AUDIO=1
#   PASM_HOST_AUDIO_DEVICE=default

set -euo pipefail

PROFILE="${1:-interactive}"

: "${MEMORY_SIZE:=65536}"
: "${EXTRA_CARGO_ARGS:=}"
: "${EXTRA_CMAKE_ARGS:=}"
: "${CMAKE_BUILD_TYPE:=Release}"
: "${RUN_SPEED:=realtime}"
: "${KEYBOARD_MAP:=examples/hosts/apple2/host_keyboard_apple2.yaml}"
: "${JOYSTICK_KEYBOARD_MAP:=examples/hosts/apple2/host_keyboard_apple2_joystick.yaml}"
: "${CONTROLLER_MAP:=examples/hosts/apple2/host_controller_apple2.yaml}"
: "${HOST_BACKEND:=glfw}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$REPO_ROOT/.uv-cache}"
mkdir -p "$UV_CACHE_DIR"

PROCESSOR="examples/processors/mos6502.yaml"
SYSTEM_DIR="examples/systems/apple2plus"
IC_KBD="examples/ics/apple2/apple2_keyboard_encoder_ay_5_3600.yaml"
IC_GAMEIO="examples/ics/apple2/apple2_gameio_ne558.yaml"
IC_VIDEO_SW="examples/ics/apple2/apple2_video_softswitches.yaml"
IC_SPK_SW="examples/ics/apple2/apple2_speaker_toggle.yaml"
IC_CHAR_ROM="examples/ics/apple2/apple2_char_generator_rom.yaml"
IC_SLOT_DEC="examples/ics/apple2/apple2_slot_decoder_ttl.yaml"
IC_CASSETTE="examples/ics/apple2/apple2_cassette_io.yaml"
IC_MAIN_RAM="examples/ics/apple2/apple2_main_ram.yaml"
DEVICE_KB="examples/devices/apple2/apple2_keyboard.yaml"
DEVICE_GP="examples/devices/apple2/apple2_gameport.yaml"
DEVICE_VIDEO="examples/devices/apple2/apple2_video.yaml"
DEVICE_SPK="examples/devices/apple2/apple2_speaker.yaml"
DEVICE_CASSETTE="examples/devices/apple2/apple2_cassette_adapter.yaml"
DEVICE_CASSETTE_TRANSPORT="examples/devices/common/cassette_transport.yaml"
DEVICE_MONITOR="examples/devices/common/monitor_crt_color.yaml"
HOST_INTERACTIVE="examples/hosts/apple2/apple2_host_hal_interactive.yaml"

case "$PROFILE" in
  default)
    SYSTEM="examples/systems/apple2plus/apple2plus_default.yaml"
    DEFAULT_OUTPUT="generated/apple2plus"
    ;;
  interactive)
    SYSTEM="examples/systems/apple2plus/apple2plus_interactive.yaml"
    DEFAULT_OUTPUT="generated/apple2plus_interactive"
    ;;
  *)
    echo "Unsupported profile: $PROFILE" >&2
    echo "Use: default | interactive" >&2
    exit 2
    ;;
esac

OUTPUT_DIR="${OUTPUT_DIR:-$DEFAULT_OUTPUT}"
BUILD_DIR="$OUTPUT_DIR/build"
mkdir -p "$OUTPUT_DIR"

# Merge joystick keyboard map into the main keyboard map so the debugger can
# accept joystick input via the keyboard when a physical controller is absent.
MERGED_KB_MAP="$OUTPUT_DIR/host_keyboard_apple2_merged.yaml"
if [[ "$MERGED_KB_MAP" = /* ]]; then
  MERGED_KB_MAP_ABS="$MERGED_KB_MAP"
else
  MERGED_KB_MAP_ABS="$REPO_ROOT/$MERGED_KB_MAP"
fi
if [[ "$PROFILE" == "interactive" && -f "$REPO_ROOT/scripts/merge_keyboard_maps.py" ]]; then
  python3 "$REPO_ROOT/scripts/merge_keyboard_maps.py" \
    "$REPO_ROOT/$KEYBOARD_MAP" \
    "$REPO_ROOT/$JOYSTICK_KEYBOARD_MAP" \
    > "$MERGED_KB_MAP_ABS"
  if [[ ! -s "$MERGED_KB_MAP_ABS" ]]; then
    echo "Keyboard map merge produced no output: $MERGED_KB_MAP" >&2
    exit 4
  fi
  KEYBOARD_MAP="$MERGED_KB_MAP"
fi

echo "[1/3] Generating emulator -> $OUTPUT_DIR"
if [[ "$PROFILE" == "interactive" ]]; then
  uv run python -m src.main generate \
    --processor "$PROCESSOR" \
    --system "$SYSTEM" \
    --ic "$IC_KBD" \
    --ic "$IC_GAMEIO" \
    --ic "$IC_VIDEO_SW" \
    --ic "$IC_SPK_SW" \
    --ic "$IC_CHAR_ROM" \
    --ic "$IC_SLOT_DEC" \
    --ic "$IC_CASSETTE" \
    --ic "$IC_MAIN_RAM" \
    --device "$DEVICE_KB" \
    --device "$DEVICE_GP" \
    --device "$DEVICE_VIDEO" \
    --device "$DEVICE_SPK" \
    --device "$DEVICE_CASSETTE" \
    --device "$DEVICE_CASSETTE_TRANSPORT" \
    --device "$DEVICE_MONITOR" \
    --host "$HOST_INTERACTIVE" \
    --host-backend "$HOST_BACKEND" \
    --output "$OUTPUT_DIR"
else
  uv run python -m src.main generate \
    --processor "$PROCESSOR" \
    --system "$SYSTEM" \
    --output "$OUTPUT_DIR"
fi

echo "[2/3] Building emulator with CMake -> $BUILD_DIR"
cmake -S "$OUTPUT_DIR" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE="$CMAKE_BUILD_TYPE" $EXTRA_CMAKE_ARGS \
  || { rm -rf "$BUILD_DIR"; cmake -S "$OUTPUT_DIR" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE="$CMAKE_BUILD_TYPE" $EXTRA_CMAKE_ARGS; }
cmake --build "$BUILD_DIR" --config "$CMAKE_BUILD_TYPE"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=$PROFILE memory_size=$MEMORY_SIZE start_pc=${START_PC:-} run_speed=$RUN_SPEED cmake_build_type=$CMAKE_BUILD_TYPE"

OUTPUT_DIR_ABS="$(cd "$OUTPUT_DIR" && pwd)"
BUILD_DIR_ABS="$(cd "$BUILD_DIR" && pwd)"
CMAKE_CONFIG_BUILD_DIR="$BUILD_DIR/$CMAKE_BUILD_TYPE"
if [[ -d "$CMAKE_CONFIG_BUILD_DIR" ]]; then
  PASM_EMU_BUILD_DIR="$(cd "$CMAKE_CONFIG_BUILD_DIR" && pwd)"
else
  PASM_EMU_BUILD_DIR="$BUILD_DIR_ABS"
fi
export PASM_EMU_DIR="$OUTPUT_DIR_ABS"
export PASM_EMU_BUILD_DIR
export PASM_EMU_MANIFEST="$OUTPUT_DIR_ABS/debugger_link.json"

if [[ -n "${START_PC:-}" ]]; then
  cargo run $EXTRA_CARGO_ARGS --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
    --backend linked \
    --memory-size "$MEMORY_SIZE" \
    --system-dir "$SYSTEM_DIR" \
    --keyboard-map "$KEYBOARD_MAP" \
    --controller-map "$CONTROLLER_MAP" \
    --start-pc "$START_PC" \
    --run-speed "$RUN_SPEED"
else
  cargo run $EXTRA_CARGO_ARGS --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
    --backend linked \
    --memory-size "$MEMORY_SIZE" \
    --system-dir "$SYSTEM_DIR" \
    --keyboard-map "$KEYBOARD_MAP" \
    --controller-map "$CONTROLLER_MAP" \
    --run-speed "$RUN_SPEED"
fi
