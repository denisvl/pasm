#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/apple2/host_keyboard_apple2.yaml}" \
MAPPER="${MAPPER:-examples/hosts/apple2/apple2_keyboard_mapper.yaml}" \
"${SCRIPT_DIR}/run_keymapper_ui_native.sh" "$@"

