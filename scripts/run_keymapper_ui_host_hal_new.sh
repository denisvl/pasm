#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

OUT_DIR="${OUT_DIR:-generated/keymapper_tool_host_hal_scaffold}"
BUILD_DIR="${BUILD_DIR:-${OUT_DIR}/build}"
BIN="${BIN:-${BUILD_DIR}/mos6502_test}"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/cpc464/host_keyboard_cpc.yaml}"
MAPPER="${MAPPER:-examples/hosts/cpc464/cpc_keyboard_mapper.yaml}"

"${SCRIPT_DIR}/run_keymapper_ui_host_hal_scaffold.sh"

if [[ ! -x "${BIN}" ]]; then
  echo "error: generated mapper host-HAL binary not found: ${BIN}" >&2
  exit 1
fi

PASM_KEYMAPPER_FILE="${PASM_KEYMAPPER_FILE:-${MAPPER}}" \
  exec "${BIN}" --run --keyboard-map "${KEYBOARD_MAP}" "$@"
