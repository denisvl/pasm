#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

BUILD_DIR="tools/controller_mapper_native/build"
BIN="${BUILD_DIR}/controller_mapper_native"

if [[ ! -x "${BIN}" ]]; then
  cmake -S tools/controller_mapper_native -B "${BUILD_DIR}"
  cmake --build "${BUILD_DIR}" -j
fi

MAPPER="${MAPPER:-examples/hosts/apple2/apple2_controller_mapper.yaml}"
HOST_MAP="${HOST_MAP:-examples/hosts/apple2/host_controller_apple2.yaml}"

MAPPER="${MAPPER}" HOST_MAP="${HOST_MAP}" exec "${BIN}" --mapper "${MAPPER}" --host-map "${HOST_MAP}" "$@"

