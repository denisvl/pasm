#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/zx_spectrum48k/zx_spectrum_48k_keyboard_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/zx_spectrum48k/host_keyboard_zx48.yaml}" \
DEVICE="${DEVICE:-examples/devices/zx_spectrum48k/zx_spectrum_48k_keyboard.yaml}" \
  "${SCRIPT_DIR}/run_keymapper_ui.sh" "$@"
