#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/coco1/trs80_coco1_keyboard_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/coco1/host_keyboard_coco.yaml}" \
DEVICE="${DEVICE:-examples/devices/coco1/coco_keyboard.yaml}" \
  "${SCRIPT_DIR}/run_keymapper_ui.sh" "$@"
