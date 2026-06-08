#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/c64/c64_keyboard_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/c64/host_keyboard_c64.yaml}" \
DEVICE="${DEVICE:-examples/devices/c64/c64_keyboard.yaml}" \
  "${SCRIPT_DIR}/run_keymapper_ui.sh" "$@"

