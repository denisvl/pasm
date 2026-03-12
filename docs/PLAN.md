# PASM Plan and Status

## Current State

Implemented:
- Hard cutover to dual-file model: `processor.yaml` + `system.yaml`.
- CLI uses `--processor` and `--system`; single-file `--isa` is rejected.
- Parser split into processor loader, system loader, and composition validation.
- Codegen input model is composed from processor+system with ownership boundaries.
- Hooks derive from system config.
- Memory regions (including ROM write protection) derive from system config.
- Ports and interrupts remain processor-owned.
- Generated output includes system metadata constants/comments (`clock_hz`, integrations metadata).

Quality gate:
- `uv run --extra dev pytest -q` is green.

## Ownership Contract

`processor.yaml` owns:
- `metadata` (`name`, `version`, `bits`, `address_bits`, `endian`, `undefined_opcode_policy`)
- `registers`, `flags`, `instructions`
- `ports`, `interrupts`

`system.yaml` owns:
- `metadata` (`name`, optional `version`)
- `clock_hz`
- `memory` (`default_size`, `regions`)
- `hooks`
- `integrations`

Cross-file checks:
- `memory.default_size <= 2^address_bits`
- regions are non-negative and fit in `default_size`
- unsupported hook names are rejected

## Z80 Status

Implemented:
- Full decode-space coverage across base/CB/ED/DD/FD/DDCB/FDCB.
- Documented and undocumented opcode handling in current generator/spec.
- Interrupt model support including Z80 IM0/IM1/IM2 behavior path.
- Port I/O hooks (`port_read_*`, `port_write_*`) with event payload.
- SectorZ hook demo path and integration test.
- Decode-cycle regression reference gate.

## Next Priorities

1. Keep Z80 coverage/cycle semantics locked with regression tests.
2. Expand platform CI matrix for generated C11 outputs (MSVC/Clang/GCC).
3. Continue next-processor roadmap:
   1. MOS 6502/6510
   2. Motorola 68000
   3. Ricoh 2A03
