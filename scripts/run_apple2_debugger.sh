#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Apple II.
#
# Usage:
#   scripts/run_apple2_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0xFA62
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/apple2_interactive
#   EXTRA_CARGO_ARGS="--release"
#   RUN_SPEED=realtime|max
#   PASM_SDL_AUDIO_DRIVER=pipewire|pulseaudio|alsa
#   PASM_HOST_AUDIO_DEVICE=pipewire|default|plughw:0,0

PROFILE="${1:-interactive}"
if [[ $# -gt 0 ]]; then
  shift
fi
START_PC="${START_PC:-}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
PASM_HOST_AUDIO_DEVICE="${PASM_HOST_AUDIO_DEVICE:-pipewire}"
PASM_SDL_AUDIO_DRIVER="${PASM_SDL_AUDIO_DRIVER:-}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/apple2/host_keyboard_apple2.yaml}"
JOYSTICK_KEYBOARD_MAP="${JOYSTICK_KEYBOARD_MAP:-examples/hosts/apple2/host_keyboard_apple2_joystick.yaml}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/apple2/host_controller_apple2.yaml}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

PROCESSOR="examples/processors/mos6502.yaml"
SYSTEM_DIR="examples/systems/apple2"
IC_KBD="examples/ics/apple2/apple2_keyboard_encoder_ay_5_3600.yaml"
IC_GAMEIO="examples/ics/apple2/apple2_gameio_ne558.yaml"
IC_VIDEO_SW="examples/ics/apple2/apple2_video_softswitches.yaml"
IC_SPK_SW="examples/ics/apple2/apple2_speaker_toggle.yaml"
IC_CASS_IO="examples/ics/apple2/apple2_cassette_io.yaml"
IC_CHAR_ROM="examples/ics/apple2/apple2_char_generator_rom.yaml"
IC_SLOT_DEC="examples/ics/apple2/apple2_slot_decoder_ttl.yaml"
IC_MAIN_RAM="examples/ics/apple2/apple2_main_ram.yaml"
DEVICE_KB="examples/devices/apple2/apple2_keyboard.yaml"
DEVICE_GP="examples/devices/apple2/apple2_gameport.yaml"
DEVICE_VIDEO="examples/devices/apple2/apple2_video.yaml"
DEVICE_SPK="examples/devices/apple2/apple2_speaker.yaml"
DEVICE_CASS_ADAPTER="examples/devices/apple2/apple2_cassette_adapter.yaml"
DEVICE_CASS="examples/devices/common/cassette_transport_nomotor.yaml"
HOST_INTERACTIVE="examples/hosts/apple2/apple2_host_hal_interactive.yaml"

case "${PROFILE}" in
  default)
    SYSTEM="examples/systems/apple2/apple2_default.yaml"
    DEFAULT_OUTPUT="generated/apple2"
    ;;
  interactive)
    SYSTEM="examples/systems/apple2/apple2_interactive.yaml"
    DEFAULT_OUTPUT="generated/apple2_interactive"
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

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
if [[ "${PROFILE}" == "interactive" ]]; then
  uv run python -m src.main generate \
    --processor "${PROCESSOR}" \
    --system "${SYSTEM}" \
    --ic "${IC_KBD}" \
    --ic "${IC_GAMEIO}" \
    --ic "${IC_VIDEO_SW}" \
    --ic "${IC_SPK_SW}" \
    --ic "${IC_CASS_IO}" \
    --ic "${IC_CHAR_ROM}" \
    --ic "${IC_SLOT_DEC}" \
    --ic "${IC_MAIN_RAM}" \
    --device "${DEVICE_KB}" \
    --device "${DEVICE_GP}" \
    --device "${DEVICE_VIDEO}" \
    --device "${DEVICE_SPK}" \
    --device "${DEVICE_CASS_ADAPTER}" \
    --device "${DEVICE_CASS}" \
    --host "${HOST_INTERACTIVE}" \
  --host-backend "${HOST_BACKEND:-glfw}" \
    --output "${OUTPUT_DIR}"
else
  uv run python -m src.main generate \
    --processor "${PROCESSOR}" \
    --system "${SYSTEM}" \
    --output "${OUTPUT_DIR}"
fi

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend)"
echo "    profile=${PROFILE} memory_size=${MEMORY_SIZE} start_pc=${START_PC} run_speed=${RUN_SPEED}"

RUN_ARGS=(
  --backend linked
  --memory-size "${MEMORY_SIZE}"
  --system-dir "${SYSTEM_DIR}"
  --run-speed "${RUN_SPEED}"
)
if [[ "${PROFILE}" == "interactive" ]]; then
  KB_PATH="${KEYBOARD_MAP}"
  if [[ -n "${JOYSTICK_KEYBOARD_MAP}" && -f "${JOYSTICK_KEYBOARD_MAP}" ]]; then
    MERGED_KB="/tmp/pasm_apple2_keyboard_merged.yaml"
    python3 scripts/merge_keyboard_maps.py "${KEYBOARD_MAP}" "${JOYSTICK_KEYBOARD_MAP}" > "${MERGED_KB}"
    KB_PATH="${MERGED_KB}"
  fi
  RUN_ARGS+=(--keyboard-map "${KB_PATH}")
  if [[ -n "${CONTROLLER_MAP}" && -f "${CONTROLLER_MAP}" ]]; then
    RUN_ARGS+=(--controller-map "${CONTROLLER_MAP}")
  fi
fi
if [[ -n "${START_PC}" ]]; then
  RUN_ARGS+=(--start-pc "${START_PC}")
fi
if [[ $# -gt 0 ]]; then
  RUN_ARGS+=("$@")
fi

if [[ -n "${PASM_SDL_AUDIO_DRIVER}" ]]; then
  SDL_AUDIODRIVER="${PASM_SDL_AUDIO_DRIVER}" \
  PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
  PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
  PASM_HOST_AUDIO_DEVICE="${PASM_HOST_AUDIO_DEVICE}" \
  cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
    "${RUN_ARGS[@]}"
else
  PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
  PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
  PASM_HOST_AUDIO_DEVICE="${PASM_HOST_AUDIO_DEVICE}" \
  cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
    "${RUN_ARGS[@]}"
fi
