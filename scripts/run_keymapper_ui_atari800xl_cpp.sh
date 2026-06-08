#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAPPER="${MAPPER:-examples/hosts/atari800xl/atari800xl_keyboard_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/atari800xl/host_keyboard_atari800xl.yaml}" \
"${SCRIPT_DIR}/run_keymapper_ui_cpp.sh" "$@"
