#!/usr/bin/env bash
set -euo pipefail

# One-shot helper: generate + build + run PASM Rust debugger for Famicom.
# Canonical Famicom interactive debugger runner.

PROFILE="${1:-interactive}"
START_PC="${START_PC:-}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
PASM_HOST_DEBUG="${PASM_HOST_DEBUG:-0}"
# Famicom: Player 2 controller is hardwired (always connected).
PASM_NES_JOY2_CONNECTED="${PASM_NES_JOY2_CONNECTED:-1}"

CARTRIDGE_MAP="examples/cartridges/famicom/famicom_mapper_auto.yaml"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../../roms/famicom/1942 (Japan, USA).nes}"
CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/famicom/host_console_famicom.yaml}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/famicom/host_controller_famicom.yaml}"
CARTRIDGE_DIR="${CARTRIDGE_DIR:-examples/roms/famicom}"

# Hard-disable traces for performance.
PASM_NES_MMC3_TRACE="0"
PASM_NES_IRQ_TRACE="0"
PASM_NES_PAD_TRACE="0"
PASM_NES_PPUSTATUS_TRACE="0"
PASM_NES_PAD_ZP_TRACE="0"
PASM_NES_ZP_TRACE="0"
PASM_CYC_DEBUG="0"
PASM_TRACE="0"
export PASM_NES_4016_TRACE=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

PROCESSOR="examples/processors/ricoh2a03.yaml"
SYSTEM="examples/systems/famicom/famicom_interactive.yaml"
HOST="examples/hosts/famicom/famicom_host_hal_interactive.yaml"
IC_BUS="examples/ics/famicom/famicom_cpu_bus.yaml"
IC_CTRL="examples/ics/famicom/famicom_controller_ports.yaml"
IC_APU="examples/ics/famicom/famicom_apu.yaml"
IC_PPU_REGS="examples/ics/famicom/famicom_ppu_regs.yaml"
IC_CPU_RAM="examples/ics/nes/nes_cpu_ram.yaml"
IC_IO_PORTS="examples/ics/famicom/famicom_io_ports.yaml"
IC_CART_BRIDGE="examples/ics/nes/nes_cart_bridge.yaml"
DEVICE_CTRL="examples/devices/famicom/famicom_controller.yaml"
DEVICE_VIDEO="examples/devices/nes/nes_video.yaml"
DEVICE_SPK="examples/devices/nes/nes_speaker.yaml"

case "${PROFILE}" in
  interactive)
    DEFAULT_OUTPUT="generated/mos6502_famicom_interactive"
    ;;
  *)
    echo "Unsupported profile: ${PROFILE}" >&2
    echo "Use: interactive" >&2
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

if [[ -n "${CARTRIDGE_ROM_RUNTIME}" ]]; then
  ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME}"
elif command -v realpath >/dev/null 2>&1; then
  ROM_RUNTIME="$(realpath "${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}")"
else
  ROM_RUNTIME="${SYSTEM_DIR_ABS}/${CARTRIDGE_ROM_GEN}"
fi

if [[ ! -f "${ROM_RUNTIME}" ]]; then
  echo "Cartridge ROM not found: ${ROM_RUNTIME}" >&2
  exit 4
fi

echo "[1/3] Generating emulator -> ${OUTPUT_DIR}"
uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --ic "${IC_BUS}" \
  --ic "${IC_CTRL}" \
  --ic "${IC_APU}" \
  --ic "${IC_PPU_REGS}" \
  --ic "${IC_CPU_RAM}" \
  --ic "${IC_IO_PORTS}" \
  --ic "${IC_CART_BRIDGE}" \
  --device "${DEVICE_CTRL}" \
  --device "${DEVICE_VIDEO}" \
  --device "${DEVICE_SPK}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-glfw}" \
  --cartridge-map "${CARTRIDGE_MAP}" \
  --cartridge-rom "${CARTRIDGE_ROM_GEN}" \
  --output "${OUTPUT_DIR}"

echo "[2/3] Building emulator with CMake -> ${BUILD_DIR}"
cmake -S "${OUTPUT_DIR}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
cmake --build "${BUILD_DIR}" --config "${CMAKE_BUILD_TYPE}"
PASM_EMU_BUILD_DIR="${BUILD_DIR_ABS}"
if [[ -d "${BUILD_DIR_ABS}/${CMAKE_BUILD_TYPE}" ]]; then
  PASM_EMU_BUILD_DIR="${BUILD_DIR_ABS}/${CMAKE_BUILD_TYPE}"
fi

if [[ -n "${START_PC}" ]]; then
  set -- --start-pc "${START_PC}"
else
  set --
fi

echo "[3/3] Running Rust debugger (linked backend)"
PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_EMU_BUILD_DIR="${PASM_EMU_BUILD_DIR}" \
PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json" \
PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
PASM_HOST_DEBUG="${PASM_HOST_DEBUG}" \
PASM_NES_JOY2_CONNECTED="${PASM_NES_JOY2_CONNECTED}" \
PASM_NES_MMC3_TRACE="${PASM_NES_MMC3_TRACE}" \
PASM_NES_PAD_TRACE="${PASM_NES_PAD_TRACE}" \
PASM_NES_PPUSTATUS_TRACE="${PASM_NES_PPUSTATUS_TRACE}" \
PASM_NES_PAD_ZP_TRACE="${PASM_NES_PAD_ZP_TRACE}" \
PASM_NES_ZP_TRACE="${PASM_NES_ZP_TRACE}" \
PASM_IRQ_TRACE="${PASM_NES_IRQ_TRACE}" \
PASM_IRQ_TRACE_FILE="log/famicom_irq_trace.log" \
PASM_CYC_DEBUG="${PASM_CYC_DEBUG}" \
PASM_TRACE="${PASM_TRACE}" \
cargo run ${EXTRA_CARGO_ARGS} --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked \
  --memory-size "${MEMORY_SIZE}" \
  --system-dir "${SYSTEM_DIR}" \
  --cart-rom "${ROM_RUNTIME}" \
  --keyboard-map "${KEYBOARD_MAP}" \
  --controller-map "${CONTROLLER_MAP}" \
  --cartridge-dir "${CARTRIDGE_DIR}" \
  "$@" \
  --run-speed "${RUN_SPEED}"
