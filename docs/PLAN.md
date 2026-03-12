# PASM Plan and Status

## Current Focus

PASM prioritizes **Z80 closure first**, then expands to additional processors.

Current closure priorities:
1. Z80 decode/runtime determinism across opcode spaces.
2. YAML-driven contracts only (no legacy behavior access compatibility).
3. Port I/O hook observability.
4. Cross-platform C11 generation (MSVC/Clang/GCC).
5. Documentation alignment to implementation reality.

## Current Architecture

Input:
- YAML ISA definition.
- JSON Schema validation (`schemas/isa_schema.json`).

Generator pipeline:
- Parse + validate ISA.
- Generate C CPU state/header.
- Generate decoder and dispatch.
- Generate optional hook API files when hooks are enabled.
- Generate build system (`CMakeLists.txt`, `Makefile`) and test scaffold.

Output:
- `src/[CPU].h`, `src/[CPU].c`, `src/[CPU]_decoder.h`, `src/[CPU]_decoder.c`.
- `src/[CPU]_hooks.h/.c` only when at least one hook is enabled.
- `main.c`, build files, and generated C test scaffold.

## Implemented Contract (Authoritative)

### ISA behavior snippets
- Must use `inst->field` access.
- Must use CPU-prefixed helpers (`<cpu_prefix>_read_*`, `<cpu_prefix>_write_*`).
- Must use YAML-defined flags (`cpu->flags.<NAME>` or `cpu->flags.raw`).
- Legacy forms are rejected:
  - `inst.field`
  - generic `cpu_read_*` / `cpu_write_*`
  - helper-macro style legacy access

### Undefined opcode policy
- YAML metadata field: `metadata.undefined_opcode_policy`.
- Supported values:
  - `trap` (default)
  - `nop`

### Hook model
- YAML hooks can enable:
  - `pre_fetch`, `post_decode`, `post_execute`
  - `port_read_pre`, `port_read_post`, `port_write_pre`, `port_write_post`
- Hook callbacks are event-based with payload (`CPUHookEvent`), including pc/prefix/opcode/port/value/raw fields.

### Generation profile
- Single generation profile.
- No release/debug feature-tier split.
- Debug API surface is kept as placeholder/stable interface for later debugger implementation.

## Z80 Status

Implemented:
- Full Z80 opcode-space coverage in generated decode paths (documented + undocumented forms, including DD/FD/DDCB/FDCB handling).
- DD/FD prefixed decode fallback alias handling.
- DDCB/FDCB masked decode support.
- Interrupt model support (`none`, `fixed_vector`, `z80` with IM0/IM1/IM2 semantics).
- Hook points for execution and port I/O.
- Port I/O hook runtime-path tests covering IN/OUT and block I/O forms (INI/OUTI).
- Decode-cycle reference gate for all Z80 decode spaces (`base`, `cb`, `ed`, `dd`, `fd`, `ddcb`, `fdcb`).
- Canonical SectorZ demo assets committed in `examples/`:
  - `sectorz_hello.c`
  - `z80_sectorz_hooks.yaml`
  - `sectorz_out_harness.c`

Validation/testing state:
- `uv run --extra dev pytest -q` is the primary quality gate.
- Compile smoke is covered for generated examples including Z80.
- Opcode-space auditing utilities/tests exist for base/CB/ED/DD/FD/DDCB/FDCB visibility.
- Cycle-reference regression gate is enforced by `tests/test_z80_cycle_reference.py` against `tests/data/z80_cycle_reference.json`.
- SectorZ integration flow is validated by `tests/test_z80_sectorz_integration.py` (opt-in download/build mode).

## Roadmap Order

After Z80 closure and doc alignment, processor roadmap order is:
1. **MOS 6502/6510** (next target)
2. Motorola 68000
3. Ricoh 2A03

## Near-Term Work Breakdown

### Phase A: Keep Z80 green
- Maintain deterministic decode behavior and policy-driven undefined handling.
- Continue expanding targeted runtime semantics where remaining edge cases are discovered.
- Keep Z80 cycle reference table in sync only via explicit regeneration gate (`PASM_REGENERATE_Z80_CYCLE_REFERENCE=1`).

### Phase B: Hook and observability hardening
- Extend hook payload coverage as needed by emulator integrations.
- Keep hook generation fully conditional on YAML enablement.
- Maintain canonical OUT-port demo workflow via `scripts/run_sectorz_demo.py`.

### Phase C: 6502/6510 baseline
- Maintain schema-valid example ISAs (`examples/mos6502.yaml`, `examples/mos6510.yaml`) and compile-smoke generation paths.
- Grow instruction/runtime coverage incrementally with tests.

## Acceptance Criteria

A change is accepted only if:
1. `uv run --extra dev pytest -q` passes.
2. Generated examples compile under C11 toolchains in CI matrix.
3. Behavior contract remains strict (no legacy auto-rewrite compatibility).
4. Docs remain consistent with generated API and CLI.

## Notes

- `docs/ISA_FORMAT.md` is the detailed contract reference.
- This file tracks plan/state, priorities, and roadmap order.
