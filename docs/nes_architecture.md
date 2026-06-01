# NES Architecture (Current)

This documents the active NES configuration used by:

- `examples/systems/nes/nes_interactive.yaml`
- `scripts/run_nes_interactive.sh`
- `scripts/run_nes_debugger.sh`

## Active ICs

1. `nes_io` (file: `examples/ics/nes/nes_ppu_apu_io.yaml`)
- Bridge/orchestrator for CPU-visible bus ranges.
- Owns CPU dispatch entry points (`mem_read_pre`, `mem_write_pre`) and frame-ready signaling.
- Delegates PPU/APU/controller/cart work to specialized ICs.

2. `nes_cpu_ram` (file: `examples/ics/nes/nes_cpu_ram.yaml`)
- Internal 2KB RAM mirror read/write (`$0000-$1FFF` mirrored).

3. `nes_io_ports` (file: `examples/ics/nes/nes_io_ports.yaml`)
- CPU I/O register dispatch in `$4000-$4017`.
- Routes:
  - controller ports (`$4016/$4017`) to `nes_controller_ports`
  - APU regs to `nes_apu`
  - OAM DMA (`$4014`) to `nes_ppu_regs`

4. `nes_controller_ports` (file: `examples/ics/nes/nes_controller_ports.yaml`)
- 4016 strobe + shift-register behavior for pad reads.
- Reads host controller state via device callbacks.

5. `nes_apu` (file: `examples/ics/nes/nes_apu.yaml`)
- APU register semantics and audio level signal generation.

6. `nes_ppu_regs` (file: `examples/ics/nes/nes_ppu_regs.yaml`)
- PPU register read/write behavior (`$2000-$3FFF` mirrored register space).
- Owns PPU memory buffers (`ppu_vram`, `palette_ram`, `oam`).
- Owns main PPU dot/render loop and frame finalize callbacks.

7. `nes_cart_bridge` (file: `examples/ics/nes/nes_cart_bridge.yaml`)
- Adapter between NES callbacks and cartridge callbacks (CHR, mirroring, IRQ).

## Ownership Summary

- CPU RAM data owner: `nes_cpu_ram`
- PPU VRAM/palette/OAM owner: `nes_ppu_regs`
- Controller latch/shift owner: `nes_controller_ports`
- APU channel/register/audio owner: `nes_apu`
- Cartridge callback adaptation owner: `nes_cart_bridge`
- Bus/orchestration owner: `nes_io`

## Current Notes

- The split is canonical now: no `_split` file names and no split-specific runner scripts remain.
- Component IDs were normalized to non-suffixed names across the NES system and IC callbacks.
