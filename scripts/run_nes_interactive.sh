#!/usr/bin/env bash
set -euo pipefail

PROFILE="interactive"
START_PC="${START_PC:-}"
MEMORY_SIZE="${MEMORY_SIZE:-65536}"
EXTRA_CARGO_ARGS="${EXTRA_CARGO_ARGS:---release}"
CMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-Release}"
RUN_SPEED="${RUN_SPEED:-realtime}"
PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"
PASM_HOST_DEBUG="${PASM_HOST_DEBUG:-0}"
PASM_NES_JOY2_CONNECTED="${PASM_NES_JOY2_CONNECTED:-0}"

# Hard-disable trace envs for performance.
export PASM_NES_MMC3_TRACE=0
export PASM_NES_IRQ_TRACE=0
export PASM_NES_PAD_TRACE=0
export PASM_NES_PPUSTATUS_TRACE=0
export PASM_NES_PAD_ZP_TRACE=0
export PASM_NES_ZP_TRACE=0
export PASM_NES_4016_TRACE=0
export PASM_TRACE=0
export PASM_CYC_DEBUG=0
export PASM_IRQ_TRACE=0

CARTRIDGE_MAP="examples/cartridges/nes/nes_mapper_auto.yaml"
CARTRIDGE_ROM_GEN="${CARTRIDGE_ROM_GEN:-../../roms/nes/Super Mario Bros. + Duck Hunt (USA).nes}"
CARTRIDGE_ROM_RUNTIME="${CARTRIDGE_ROM_RUNTIME:-}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/nes/host_console_nes.yaml}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/nes/host_controller_nes.yaml}"
CARTRIDGE_DIR="${CARTRIDGE_DIR:-examples/roms/nes}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${REPO_ROOT}/.uv-cache}"
mkdir -p "${UV_CACHE_DIR}"

PROCESSOR="examples/processors/ricoh2a03.yaml"
SYSTEM="examples/systems/nes/nes_interactive.yaml"
HOST="examples/hosts/nes/nes_host_hal_interactive.yaml"
IC_BUS="examples/ics/nes/nes_cpu_bus.yaml"
IC_CTRL="examples/ics/nes/nes_controller_ports.yaml"
IC_APU="examples/ics/nes/nes_apu.yaml"
IC_PPU_REGS="examples/ics/nes/nes_ppu_regs.yaml"
IC_CPU_RAM="examples/ics/nes/nes_cpu_ram.yaml"
IC_IO_PORTS="examples/ics/nes/nes_io_ports.yaml"
IC_CART_BRIDGE="examples/ics/nes/nes_cart_bridge.yaml"
DEVICE_CTRL="examples/devices/nes/nes_controller.yaml"
DEVICE_VIDEO="examples/devices/nes/nes_video.yaml"
DEVICE_SPK="examples/devices/nes/nes_speaker.yaml"
OUTPUT_DIR="${OUTPUT_DIR:-generated/mos6502_nes_interactive}"
BUILD_DIR="${OUTPUT_DIR}/build"
mkdir -p "$(dirname "${OUTPUT_DIR}")"
OUTPUT_DIR_ABS="$(cd "$(dirname "${OUTPUT_DIR}")" && pwd)/$(basename "${OUTPUT_DIR}")"
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

if [[ -n "${START_PC}" ]]; then
  set -- --start-pc "${START_PC}"
else
  set --
fi

echo "[3/3] Running Rust debugger (linked backend)"
PASM_EMU_DIR="${OUTPUT_DIR_ABS}" \
PASM_EMU_BUILD_DIR="${BUILD_DIR}" \
PASM_EMU_MANIFEST="${OUTPUT_DIR_ABS}/debugger_link.json" \
PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \
PASM_HOST_DEBUG="${PASM_HOST_DEBUG}" \
PASM_NES_JOY2_CONNECTED="${PASM_NES_JOY2_CONNECTED}" \
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
