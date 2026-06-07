#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OUTPUT_DIR="${OUTPUT_DIR:-generated/z80_trs80_model4_sdl}"
SYSTEM_DIR="${SYSTEM_DIR:-examples/systems/trs80_model4}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/trs80_model4/host_keyboard_trs80.yaml}"
BIN="${BIN:-${OUTPUT_DIR}/build/mos6502_test}"
ROM_FILE="${ROM_FILE:-}"
LOAD_ADDR="${LOAD_ADDR:-0x0000}"
CYCLES="${CYCLES:-}"
TEST_NAME="${TEST_NAME:-}"

exec env \
  OUTPUT_DIR="${OUTPUT_DIR}" \
  SYSTEM_DIR="${SYSTEM_DIR}" \
  KEYBOARD_MAP="${KEYBOARD_MAP}" \
  BIN="${BIN}" \
  ROM_FILE="${ROM_FILE}" \
  LOAD_ADDR="${LOAD_ADDR}" \
  CYCLES="${CYCLES}" \
  TEST_NAME="${TEST_NAME}" \
  "${SCRIPT_DIR}/run_generated_no_tui.sh" "$@"
