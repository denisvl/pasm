#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OUTPUT_DIR="${OUTPUT_DIR:-generated/c64_interactive}"
SYSTEM_DIR="${SYSTEM_DIR:-examples/systems/c64}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/c64/host_keyboard_c64.yaml}"
BIN="${BIN:-${OUTPUT_DIR}/build/mos6510_test}"
ROM_FILE="${ROM_FILE:-}"
LOAD_ADDR="${LOAD_ADDR:-0x0000}"
CYCLES="${CYCLES:-}"
TEST_NAME="${TEST_NAME:-}"
CONTROLLER_MAP="${CONTROLLER_MAP:-}"
FLOPPY="${FLOPPY:-}"
C64_AUTOTYPE="${C64_AUTOTYPE:-}"
C64_AUTOTYPE_CYCLE="${C64_AUTOTYPE_CYCLE:-5000000}"

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
  FLOPPY="${FLOPPY}" \
  PASM_EMU_FLOPPY_AUTO_PATH="${FLOPPY}" \
  PASM_C64_AUTOTYPE="${C64_AUTOTYPE}" \
  PASM_C64_AUTOTYPE_CYCLE="${C64_AUTOTYPE_CYCLE}" \
  "${SCRIPT_DIR}/run_generated_no_tui.sh" "$@"
