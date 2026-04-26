#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/atari2600/atari2600_controller_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/atari2600/host_controller_atari2600.yaml}" \
  "${SCRIPT_DIR}/run_controller_mapper_ui_native.sh" "$@"

