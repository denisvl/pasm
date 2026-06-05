#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/msx1/msx1_controller_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/msx1/host_controller_msx1.yaml}" \
  "${SCRIPT_DIR}/run_controller_mapper_ui_native.sh" "$@"

