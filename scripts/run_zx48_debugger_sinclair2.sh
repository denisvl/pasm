#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/zx_spectrum48k/host_controller_zx48_sinclair2.yaml}" \
  "${SCRIPT_DIR}/run_zx48_debugger.sh" interactive "$@"

