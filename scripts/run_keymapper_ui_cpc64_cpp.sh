#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAPPER="${MAPPER:-examples/hosts/cpc464/cpc_keyboard_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/cpc464/host_keyboard_cpc.yaml}" \
"${SCRIPT_DIR}/run_keymapper_ui_cpp.sh" "$@"
