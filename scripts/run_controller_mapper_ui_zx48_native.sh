#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/zx_spectrum48k/zx48_controller_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/zx_spectrum48k/host_controller_zx48_kempston.yaml}" \
  "${SCRIPT_DIR}/run_controller_mapper_ui_native.sh" "$@"
