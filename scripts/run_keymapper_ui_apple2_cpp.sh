#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAPPER="${MAPPER:-examples/hosts/apple2/apple2_keyboard_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/apple2/host_keyboard_apple2.yaml}" \
"${SCRIPT_DIR}/run_keymapper_ui_cpp.sh" "$@"
