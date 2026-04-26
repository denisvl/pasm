#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/atari2600/atari2600_console_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/atari2600/host_console_atari2600.yaml}" \
DEVICE="${DEVICE:-examples/devices/atari2600/atari2600_console.yaml}" \
  "${SCRIPT_DIR}/run_keymapper_ui.sh" "$@"
