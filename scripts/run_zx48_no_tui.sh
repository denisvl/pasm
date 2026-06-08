#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OUTPUT_DIR="${OUTPUT_DIR:-generated/z80_48k_sdl_interactive}"
SYSTEM_DIR="${SYSTEM_DIR:-examples/systems/zx_spectrum48k}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/zx_spectrum48k/host_keyboard_zx48.yaml}"
BIN="${BIN:-${OUTPUT_DIR}/build/mos6502_test}"
ROM_FILE="${ROM_FILE:-}"
LOAD_ADDR="${LOAD_ADDR:-0x0000}"
CYCLES="${CYCLES:-}"
TEST_NAME="${TEST_NAME:-}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/zx_spectrum48k/host_controller_zx48_kempston.yaml}"

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
  "${SCRIPT_DIR}/run_generated_no_tui.sh" "$@"
