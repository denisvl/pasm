#!/usr/bin/env bash
# Build and run the schema editor from the project root.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BUILD_DIR="${PROJECT_ROOT}/build/schema_editor_build_release"

mkdir -p "${BUILD_DIR}"
cmake -S "${PROJECT_ROOT}/tools/schema_editor" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release &>/dev/null
cmake --build "${BUILD_DIR}" -j"$(nproc)" &>/dev/null

cd "${PROJECT_ROOT}"
exec "${BUILD_DIR}/schema_editor" "$@"
