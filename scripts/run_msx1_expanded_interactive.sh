#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEBUGGER="${SCRIPT_DIR}/run_msx1_expanded_debugger.sh"
if [[ ! -x "${DEBUGGER}" ]]; then
  echo "MSX1 Expanded debugger launcher not found or not executable: ${DEBUGGER}" >&2
  exit 2
fi

# MSX interactive defaults:
# - keep cartridge subsystem enabled for runtime picker
# - boot to BASIC (no auto-loaded cartridge)
# - enable raw picker key fallback on F12; host map also binds F12
USE_CARTRIDGE=1 \
BOOT_CARTRIDGE=0 \
PASM_EMU_CART_PICKER_RAW_KEYS=1 \
"${DEBUGGER}" interactive "$@"
