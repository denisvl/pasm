#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OUTPUT_DIR="${OUTPUT_DIR:-generated/c64_interactive}"
SYSTEM_DIR="${SYSTEM_DIR:-examples/systems/c64}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/c64/host_keyboard_c64.yaml}"
BIN="${BIN:-${OUTPUT_DIR}/build/mos6502_test}"
ROM_FILE="${ROM_FILE:-}"
LOAD_ADDR="${LOAD_ADDR:-0x0000}"
CYCLES="${CYCLES:-}"
TEST_NAME="${TEST_NAME:-}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/c64/host_controller_c64.yaml}"

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
