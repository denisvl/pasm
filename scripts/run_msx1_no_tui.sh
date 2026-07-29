#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OUTPUT_DIR="${OUTPUT_DIR:-generated/z80_msx1_sdl}"
SYSTEM_DIR="${SYSTEM_DIR:-examples/systems/msx1}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/msx1/host_keyboard_msx.yaml}"
BIN="${BIN:-${OUTPUT_DIR}/build/z80_test}"
ROM_FILE="${ROM_FILE:-}"
LOAD_ADDR="${LOAD_ADDR:-0x0000}"
CYCLES="${CYCLES:-}"
TEST_NAME="${TEST_NAME:-}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/msx1/host_controller_msx1.yaml}"
FLOPPY="${FLOPPY:-}"
DISK_ROM="${DISK_ROM:-}"

exec env \
  OUTPUT_DIR="${OUTPUT_DIR}" \
  SYSTEM_DIR="${SYSTEM_DIR}" \
  KEYBOARD_MAP="${KEYBOARD_MAP}" \
  BIN="${BIN}" \
  ROM_FILE="${ROM_FILE}" \
  LOAD_ADDR="${LOAD_ADDR}" \
  CYCLES="${CYCLES}" \
  TEST_NAME="${TEST_NAME}" \
  CONTROLLER_MAP="${CONTROLLER_MAP:-}" \
  FLOPPY="${FLOPPY:-}" \
  PASM_EMU_FLOPPY_AUTO_PATH="${FLOPPY:-}" \
  PASM_MSX_DISK_ROM="${DISK_ROM:-}" \
  "${SCRIPT_DIR}/run_generated_no_tui.sh" "$@"
