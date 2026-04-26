#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MAPPER="${MAPPER:-examples/hosts/coco1/coco1_controller_mapper.yaml}" \
HOST_MAP="${HOST_MAP:-examples/hosts/coco1/host_controller_coco.yaml}" \
  "${SCRIPT_DIR}/run_controller_mapper_ui_native.sh" "$@"

