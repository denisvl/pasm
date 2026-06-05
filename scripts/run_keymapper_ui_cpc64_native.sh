#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYBOARD_MAP="${KEYBOARD_MAP:-examples/hosts/cpc464/host_keyboard_cpc.yaml}" \
MAPPER="${MAPPER:-examples/hosts/cpc464/cpc_keyboard_mapper.yaml}" \
"${SCRIPT_DIR}/run_keymapper_ui_native.sh" "$@"

