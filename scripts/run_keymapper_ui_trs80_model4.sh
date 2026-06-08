#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/trs80_model4/trs80_model4_keyboard_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/trs80_model4/host_keyboard_trs80.yaml}" \
DEVICE="${DEVICE:-examples/devices/trs80_model4/trs80_model4_keyboard.yaml}" \
  "${SCRIPT_DIR}/run_keymapper_ui.sh" "$@"
