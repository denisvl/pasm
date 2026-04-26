#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

MAPPER="${MAPPER:-examples/hosts/cpc464/cpc_keyboard_mapper.yaml}"
HOST_MAP="${HOST_MAP:-examples/hosts/cpc464/host_keyboard_cpc.yaml}"

cmake -S tools/keymapper_native -B tools/keymapper_native/build
cmake --build tools/keymapper_native/build -j

exec tools/keymapper_native/build/keymapper_native --mapper "${MAPPER}" --host-map "${HOST_MAP}" "$@"
