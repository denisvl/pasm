## PASM

PASM generates C11 CPU emulators from YAML definitions.

Hard cutover is active:
- CPU semantics are defined in `processor.yaml`.
- Runtime/deployment configuration is defined in `system.yaml`.
- Single-file ISA input (`--isa`) is removed.

### Install

```bash
uv sync --extra dev
```

### Quickstart

Use a processor/system pair:

- Processor: `examples/processors/simple8.yaml`
- System: `examples/systems/simple8_default.yaml`

Validate:

```bash
pasm validate \
  --processor examples/processors/simple8.yaml \
  --system examples/systems/simple8_default.yaml
```

Generate:

```bash
pasm generate \
  --processor examples/processors/simple8.yaml \
  --system examples/systems/simple8_default.yaml \
  --output generated/simple8
```

Build (optional):

```bash
cmake -S generated/simple8 -B generated/simple8/build
cmake --build generated/simple8/build
ctest --test-dir generated/simple8/build --output-on-failure
```

### CLI

`pasm generate --processor <file> --system <file> --output <dir> [--dispatch switch|threaded|both]`

`pasm validate --processor <file> --system <file> [--verbose]`

`pasm info --processor <file> --system <file>`

Notes:
- `--dispatch switch` is the portable default.
- Generated code is C11 and gated for MSVC/Clang/GCC.

### File Ownership

`processor.yaml` owns:
- `metadata` (`name`, `version`, `bits`, `address_bits`, `endian`, `undefined_opcode_policy`)
- `registers`, `flags`, `instructions`
- `ports`, `interrupts`

`system.yaml` owns:
- `metadata` (`name`, optional `version`)
- `clock_hz`
- `memory` (`default_size`, `regions`)
- `hooks`
- `integrations` (pass-through metadata)

Cross-validation enforces:
- `memory.default_size <= 2^processor.metadata.address_bits`
- regions must be non-negative and fit within `default_size`
- only supported hook names are accepted

### Examples

Processors:
- `examples/processors/minimal8.yaml`
- `examples/processors/simple8.yaml`
- `examples/processors/z80.yaml`
- `examples/processors/mos6502.yaml`
- `examples/processors/mos6510.yaml`

Systems:
- `examples/systems/minimal8_default.yaml`
- `examples/systems/simple8_default.yaml`
- `examples/systems/z80_default.yaml`
- `examples/systems/z80_sectorz_hooks.yaml`
- `examples/systems/mos6502_default.yaml`
- `examples/systems/mos6510_default.yaml`

### SectorZ Demo

Demo assets:
- `examples/sectorz_hello.c`
- `examples/sectorz_out_harness.c`
- `examples/processors/z80.yaml`
- `examples/systems/z80_sectorz_hooks.yaml`

Run:

```bash
uv run --extra dev python scripts/run_sectorz_demo.py --z88dk-root /tmp/z88dk-src
```

### Development

Run tests:

```bash
uv run --extra dev pytest -q
```

Docs:
- `docs/ISA_FORMAT.md`
- `docs/PLAN.md`
