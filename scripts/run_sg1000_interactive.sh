#!/usr/bin/env bash
set -euo pipefail

"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_sg1000_debugger.sh" interactive "$@"
