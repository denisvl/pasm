#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for ZX Spectrum 48K.
#
# Usage:
#   scripts/run_zx48_debugger.sh [interactive|default]
#
# Optional env overrides:
#   START_PC=0x0000
#   MEMORY_SIZE=65536
#   OUTPUT_DIR=generated/z80_48k_sdl
#   EXTRA_CARGO_ARGS="--release"
#   USE_FLOPPY=1|0
#   FLOPPY=/abs/path/to/disk.trd
#   DISK_ROM=/abs/path/to/trdos.rom
#   RUN_SPEED=realtime|max

PROFILE="${1:-interactive}"
START_PC="${START_PC:-0x0000}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:-}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/zx_spectrum48k/host_keyboard_zx48.yaml}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/zx_spectrum48k/host_controller_zx48_kempston.yaml}"
USE_FLOPPY="${USE_FLOPPY:-0}"
FLOPPY="${FLOPPY:-}"
DISK_ROM="${DISK_ROM:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

PROCESSOR="examples/processors/z80.yaml"
IC="examples/ics/zx_spectrum48k/zx_spectrum_48k_ula.yaml"
IC_LORAM="examples/ics/zx_spectrum48k/zx_spectrum_48k_loram.yaml"
IC_HIRAM="examples/ics/zx_spectrum48k/zx_spectrum_48k_hiram.yaml"
DEVICE_KB="examples/devices/zx_spectrum48k/zx48_keyboard.yaml"
DEVICE_CTRL="examples/devices/zx_spectrum48k/zx48_controller.yaml"
DEVICE_VIDEO="examples/devices/zx_spectrum48k/zx48_video.yaml"
DEVICE_BEEPER="examples/devices/zx_spectrum48k/zx48_beeper.yaml"
DEVICE_MIC="examples/devices/zx_spectrum48k/zx48_mic.yaml"
DEVICE_CASS="examples/devices/common/cassette_transport_nomotor.yaml"
IC_FDC="examples/ics/common/wd1793.yaml"
IC_BETADISK="examples/ics/zx_spectrum48k/zx_betadisk_interface_wd1793.yaml"
DEVICE_FLOPPY_BACKEND="examples/devices/common/floppy_raw_sector_image_backend.yaml"

if [[ "${USE_FLOPPY}" == "0" && ( -n "${FLOPPY}" || -n "${DISK_ROM}" ) ]]; then
  USE_FLOPPY=1
fi

case "${PROFILE}" in
  default)
    if [[ "${USE_FLOPPY}" != "0" ]]; then
      SYSTEM="examples/systems/zx_spectrum48k/spectrum48k_betadisk_default.yaml"
    else
      SYSTEM="examples/systems/zx_spectrum48k/spectrum48k_default.yaml"
    fi
    HOST="examples/hosts/zx_spectrum48k/zx48_host_hal.yaml"
    DEFAULT_OUTPUT="generated/z80_48k_sdl"
    ;;
  interactive)
    if [[ "${USE_FLOPPY}" != "0" ]]; then
      SYSTEM="examples/systems/zx_spectrum48k/spectrum48k_betadisk_interactive.yaml"
    else
      SYSTEM="examples/systems/zx_spectrum48k/spectrum48k_interactive.yaml"
    fi
    HOST="examples/hosts/zx_spectrum48k/zx48_host_hal_interactive.yaml"
    DEFAULT_OUTPUT="generated/z80_48k_sdl_interactive"
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

if [[ "${USE_FLOPPY}" != "0" && -n "${DISK_ROM}" && ! -f "${DISK_ROM}" ]]; then
  echo "Disk ROM not found: ${DISK_ROM}" >&2
  exit 4
fi
if [[ "${USE_FLOPPY}" != "0" && -n "${FLOPPY}" && ! -f "${FLOPPY}" ]]; then
  echo "Floppy image not found: ${FLOPPY}" >&2
  exit 4
fi

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
GEN_ARGS=(
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC}" \
  --ic "${IC_LORAM}" \
  --ic "${IC_HIRAM}" \
  --device "${DEVICE_KB}" \
  --device "${DEVICE_CTRL}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_BEEPER}" \
  --device "${DEVICE_MIC}" \
  --device "${DEVICE_CASS}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-glfw}" \
  --output "${OUTPUT_DIR}"
)
RUN_ARGS=(
  --backend linked
  --memory-size "${MEMORY_SIZE}"
  --system-dir "${SYSTEM_DIR_ABS}"
  --start-pc "${START_PC}"
  --run-speed "${RUN_SPEED}"
  --keyboard-map "${KEYBOARD_MAP}"
)
if [[ "${USE_FLOPPY}" != "0" ]]; then
  GEN_ARGS+=(--ic "${IC_FDC}" --ic "${IC_BETADISK}" --device "${DEVICE_FLOPPY_BACKEND}")
  if [[ -n "${FLOPPY}" ]]; then
    RUN_ARGS+=(--floppy "${FLOPPY}")
  fi
fi
uv run python -m src.main generate "${GEN_ARGS[@]}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}"

echo "[3/3] Running Rust debugger (linked backend)"
if [[ "${PROFILE}" == "interactive" ]]; then
  RUN_ARGS+=(--controller-map "${CONTROLLER_MAP}")
fi
PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_ZX_BETADISK_ROM="${DISK_ROM}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  "${RUN_ARGS[@]}"
