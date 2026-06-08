#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OUTPUT_DIR="${OUTPUT_DIR:-generated/z80_sms_sdl}"
SYSTEM_DIR="${SYSTEM_DIR:-examples/systems/sms}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/sms/host_console_sms.yaml}"
BIN="${BIN:-${OUTPUT_DIR}/build/z80_test}"
ROM_FILE="${ROM_FILE:-}"
LOAD_ADDR="${LOAD_ADDR:-0x0000}"
CYCLES="${CYCLES:-}"
TEST_NAME="${TEST_NAME:-}"
CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/sms/host_controller_sms.yaml}"
PASM_SMS_DIRECT_PCM="${PASM_SMS_DIRECT_PCM:-1}"

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
  PASM_SMS_DIRECT_PCM="${PASM_SMS_DIRECT_PCM}" \
  "${SCRIPT_DIR}/run_generated_no_tui.sh" "$@"
