#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAPPER="${MAPPER:-examples/hosts/apple2/apple2_controller_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/apple2/host_controller_apple2.yaml}" \
  "${SCRIPT_DIR}/run_controller_mapper_ui_native.sh" "$@"

