# CPC464 Hardware Mapping

This project currently models CPC464 hardware with a pragmatic integration:

- `examples/ics/cpc464/cpc_gate_array_40010.yaml` currently contains the effective behavior for:
  - MC6845-compatible CRTC timing/address counters
  - Gate Array functions (palette, mode, ROM/RAM switching, timing/IRQ)
  - AY-3-8912 PSG generation and register model
  - 8255 PPI-style keyboard/joystick/cassette/printer I/O handling
- RAM and ROM are represented in system memory configuration:
  - `RAM_64K` region
  - `OS_464.ROM` and `BASIC_1.0.ROM` images

## Canonical CPC464 elements

- Video timing / CRTC: Motorola MC6845 (or compatible)
- Video glue / palette / memory timing: Amstrad Gate Array (40010/40007 families)
- Sound: GI AY-3-8912
- Parallel I/O: Intel 8255 PPI (or compatible)
- RAM: 64 KB DRAM total
- ROM: Firmware + BASIC ROM

## Current status

All canonical elements are present in the model inventory. Current executable behavior is still concentrated in `cpc_gate_array` while IC stubs exist for:
- `cpc_crtc_6845.yaml`
- `cpc_ppi_8255.yaml`
- `cpc_ay_3_8912.yaml`

## Planned decomposition (non-functional refactor)

When refactoring for stricter chip-level separation, split `cpc_io` into:

- `cpc_crtc_6845`
- `cpc_gate_array_40010`
- `cpc_ppi_8255`
- `cpc_psg_ay_3_8912`

while preserving existing external behavior and timing compatibility.
