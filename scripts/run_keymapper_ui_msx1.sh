#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/msx1/msx1_keyboard_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/msx1/host_keyboard_msx.yaml}" \
DEVICE="${DEVICE:-examples/devices/msx1/msx_keyboard.yaml}" \
  "${SCRIPT_DIR}/run_keymapper_ui.sh" "$@"
