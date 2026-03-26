# PASM Plan and Status

Last verified on: March 19, 2026

## Current State (Implemented)

- Hard cutover to multi-file composition:
  - required: `processor.yaml`, `system.yaml`
  - repeatable: `ic.yaml`, `device.yaml`, `host.yaml`
  - optional single active cartridge: `cartridge.yaml`
- CLI supports:
  - `--processor --system`
  - repeatable `--ic`, `--device`, `--host`
  - cartridge flow: `--cartridge-map`, `--cartridge-rom`
  - `generate` options: `--dispatch`, `--validate-only`
- System-owned wiring graph is implemented via:
  - `components.ics[]`, `components.devices[]`, `components.hosts[]`
  - optional `components.cartridge`
  - `connections[]`
- ROM loading is implemented:
  - system manifests: `memory.rom_images[]`
  - runtime API: `<cpu_prefix>_load_system_roms(...)`
  - cartridge runtime API: `<cpu_prefix>_load_cartridge_rom(...)`
  - generated `main.c` supports runtime override `--cart-rom`
- Generic component runtime generation is in place:
  - no hardware-model-specific branches in generator/runtime
  - behavior comes from YAML snippets (`ic`/`device`/`host`/`cartridge`)
  - generic endpoint routing (`callback` / `signal` / `handler`)
- `coding` merge support is implemented for behavior-capable YAMLs:
  - deterministic merged includes/link config in generated CMake/Makefile
  - merge order: processor -> ICs -> devices -> hosts -> cartridge
- Processor display features are implemented:
  - `registers[].display_name`
  - operand-resolved disassembly via `display_template` + `display_operands`
- Emulator stacks implemented and exercised in repo examples:
  - ZX Spectrum 48K (Z80 + ULA/devices/host)
  - MSX1 baseline and interactive profiles
  - Sega Master System baseline/interative + cartridge mapping flow
  - CoCo1 (MC6809)
  - Apple II (MOS6502)
  - C64 (MOS6510)

## Ownership Contract

- `processor.yaml` owns CPU semantics and instruction behavior.
- `system.yaml` owns memory/clock/hooks/reset/audio plus all component wiring and ROM manifests.
- `ic.yaml`, `device.yaml`, `host.yaml`, and `cartridge.yaml` own component-local state/interfaces/behavior/coding.

## Verification Commands

Use these to re-check documented behavior quickly:

```bash
uv run python -m src.main --help
uv run python -m src.main generate --help
uv run python -m src.main validate --help
uv run python -m src.main info --help
uv run --extra dev pytest -q
```

## Next Suggested Work

1. Expand typed signature compatibility checks beyond arity in `connections[]`.
2. Add CI matrix for generated C builds across MSVC/Clang/GCC with interactive/non-interactive targets.
3. Strengthen runtime reference tests for video/audio correctness in interactive systems.
4. Continue processor fidelity work (remaining undocumented/edge opcode semantics and timing corner cases).
