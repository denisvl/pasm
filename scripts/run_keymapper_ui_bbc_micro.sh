#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/bbcmicro/bbc_micro_keyboard_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/bbcmicro/host_keyboard_bbc_micro.yaml}" \
DEVICE="${DEVICE:-examples/devices/bbcmicro/bbc_micro_keyboard.yaml}" \
  "${SCRIPT_DIR}/run_keymapper_ui.sh" "$@"
