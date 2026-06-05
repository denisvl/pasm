#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

OUT_DIR="${OUT_DIR:-generated/keymapper_tool_host_hal_scaffold}"
PROCESSOR="${PROCESSOR:-examples/processors/mos6502.yaml}"
SYSTEM="${SYSTEM:-examples/systems/keymapper_tool/keymapper_tool_interactive.yaml}"
HOST="${HOST:-examples/hosts/keymapper_tool/keymapper_host_hal_interactive.yaml}"

UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}" uv run python -m src.main generate \
  --processor "${PROCESSOR}" \
  --system "${SYSTEM}" \
  --host "${HOST}" \
  --host-backend "${HOST_BACKEND:-glfw}" \
  --output "${OUT_DIR}"

cmake -S "${OUT_DIR}" -B "${OUT_DIR}/build"
cmake --build "${OUT_DIR}/build" -j

echo "Generated host-HAL scaffold at: ${OUT_DIR}"
echo "Build dir: ${OUT_DIR}/build"
