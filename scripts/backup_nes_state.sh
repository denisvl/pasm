#!/usr/bin/env bash
set -euo pipefail

ts="$(date +%Y%m%d_%H%M%S)"
tag="${1:-manual}"
dst="/tmp/nes_backup_${ts}_${tag}"

mkdir -p "${dst}"

cp examples/systems/nes/nes_interactive.yaml "${dst}/"
cp examples/ics/nes/nes_cpu_bus.yaml "${dst}/"
cp examples/ics/nes/nes_apu.yaml "${dst}/"
cp examples/ics/nes/nes_controller_ports.yaml "${dst}/"
cp examples/ics/nes/nes_ppu_regs.yaml "${dst}/"
cp examples/ics/nes/nes_cpu_ram.yaml "${dst}/"
cp examples/ics/nes/nes_io_ports.yaml "${dst}/"
cp examples/ics/nes/nes_cart_bridge.yaml "${dst}/"
cp scripts/run_nes_interactive.sh "${dst}/"
cp scripts/run_nes_debugger.sh "${dst}/"

echo "${dst}"
