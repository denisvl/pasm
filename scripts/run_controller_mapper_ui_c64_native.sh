#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/c64/c64_controller_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/c64/host_controller_c64.yaml}" \
  "${SCRIPT_DIR}/run_controller_mapper_ui_native.sh" "$@"

