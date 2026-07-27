#!/usr/bin/env bash
set -euo pipefail

HOST_FILE="${HOST_FILE:-examples/hosts/bbcmicro/bbc_micro_model_a_host_hal_interactive.yaml}" \
"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_bbc_micro_model_a_debugger.sh" interactive "$@"
