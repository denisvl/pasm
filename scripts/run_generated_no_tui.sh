#!/usr/bin/env bash
set -euo pipefail

# Run a generated PASM system binary directly, without the debugger TUI.
# This script is generic: point OUTPUT_DIR/SYSTEM_DIR/KEYBOARD_MAP at any
# generated system you want to execute.

OUTPUT_DIR="${OUTPUT_DIR:-generated/apple2_interactive}"
SYSTEM_DIR="${SYSTEM_DIR:-examples/systems/apple2}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/apple2/host_keyboard_apple2.yaml}"
CONTROLLER_MAP="${CONTROLLER_MAP:-}"
BIN="${BIN:-${OUTPUT_DIR}/build/mos6502_test}"
ROM_FILE="${ROM_FILE:-}"
LOAD_ADDR="${LOAD_ADDR:-0x0000}"
CYCLES="${CYCLES:-}"
TEST_NAME="${TEST_NAME:-}"

if [[ ! -x "${BIN}" ]]; then
  echo "Generated binary not found or not executable: ${BIN}" >&2
  echo "Build the target first (for example with the system's debugger script)." >&2
  exit 1
fi

ARGS=(--system-dir "${SYSTEM_DIR}" --keyboard-map "${KEYBOARD_MAP}")
if [[ -n "${CONTROLLER_MAP}" ]]; then
  if "${BIN}" --help 2>/dev/null | grep -Fq -- "--controller-map"; then
    ARGS+=(--controller-map "${CONTROLLER_MAP}")
  else
    echo "warning: ${BIN} does not accept --controller-map; ignoring CONTROLLER_MAP=${CONTROLLER_MAP}" >&2
  fi
fi
if [[ -n "${ROM_FILE}" ]]; then
  ARGS+=(--rom "${ROM_FILE}" --addr "${LOAD_ADDR}")
fi
if [[ -n "${TEST_NAME}" ]]; then
  ARGS+=(--test "${TEST_NAME}")
elif [[ -n "${CYCLES}" ]]; then
  ARGS+=(--cycles "${CYCLES}")
else
  ARGS+=(--run)
fi

exec "${BIN}" "${ARGS[@]}" "$@"
