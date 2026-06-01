#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 /tmp/nes_backup_YYYYmmdd_HHMMSS_tag" >&2
  exit 2
fi

src="$1"

if [[ ! -d "${src}" ]]; then
  echo "backup not found: ${src}" >&2
  exit 3
fi

cp "${src}/nes_interactive.yaml" examples/systems/nes/nes_interactive.yaml
cp "${src}/nes_cpu_bus.yaml" examples/ics/nes/nes_cpu_bus.yaml
cp "${src}/nes_apu.yaml" examples/ics/nes/nes_apu.yaml
cp "${src}/nes_controller_ports.yaml" examples/ics/nes/nes_controller_ports.yaml
cp "${src}/nes_ppu_regs.yaml" examples/ics/nes/nes_ppu_regs.yaml
cp "${src}/nes_cpu_ram.yaml" examples/ics/nes/nes_cpu_ram.yaml
cp "${src}/nes_io_ports.yaml" examples/ics/nes/nes_io_ports.yaml
cp "${src}/nes_cart_bridge.yaml" examples/ics/nes/nes_cart_bridge.yaml
cp "${src}/run_nes_interactive.sh" scripts/run_nes_interactive.sh
cp "${src}/run_nes_debugger.sh" scripts/run_nes_debugger.sh

echo "restored from ${src}"
