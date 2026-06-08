#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Default to the native UI.
# The native version provides the controller mapping interface.
"${SCRIPT_DIR}/run_sg1000_controller_mapper_ui_native.sh" "$@"