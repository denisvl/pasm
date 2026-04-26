#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Default to the full C++/ImGui UI (canvas + inspector panels).
# The host-HAL scaffold (canvas-only) remains available via:
#   scripts/run_keymapper_ui_native.sh
"${SCRIPT_DIR}/run_keymapper_ui_cpp.sh" "$@"
