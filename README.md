## PASM – Processor Architecture Specification for Emulation

PASM is a Python‑based code generator that reads a YAML Instruction Set Architecture (ISA) description and produces a complete, compilable C emulator for that processor.

The goal is to go from a declarative ISA file (registers, flags, memory model, opcode encodings, and behavior snippets) to a working emulator with minimal boilerplate.

### Features

- **Declarative ISA definitions** in YAML, validated by a strict JSON Schema.
- **Automatic C code generation** for:
  - CPU state (`CPUState`) and register/flag enums.
  - Instruction decoder and decision‑tree dispatch loop.
  - Runtime helpers for memory, ports, and interrupts.
  - Debug interface placeholders and execution hooks.
- **Configurable dispatch output**:
  - `--dispatch` supports `switch`, `threaded`, and `both`.
- **Build integration**:
  - Auto‑generated `CMakeLists.txt` and `Makefile`.
  - Basic test harness wiring for generated CPUs.

See `docs/PLAN.md` for the high‑level architecture and roadmap.

### Installation

You need Python 3.10+.

From the project root (recommended with `uv`):

```bash
uv sync --extra dev
```

This installs the `pasm` console script defined in `pyproject.toml`.

### Quickstart

1. **Inspect an example ISA**

   ```bash
   # From the project root
   cat examples/simple8.yaml
   ```

2. **Validate the ISA**

   ```bash
   pasm validate --isa examples/simple8.yaml
   ```

3. **Generate an emulator**

   ```bash
   pasm generate \
     --isa examples/simple8.yaml \
     --output generated/simple8
   ```

   This creates:

   - `generated/simple8/src/` with `Simple8.c`, `Simple8.h`, decoder, hooks (if enabled), and `main.c`.
   - `generated/simple8/include/cpu_defs.h`.
   - `generated/simple8/CMakeLists.txt` and `generated/simple8/Makefile`.

4. **Build and run (optional)**

   With CMake and a C compiler installed:

   ```bash
   cd generated/simple8
   cmake -S . -B build
   cmake --build build
   ctest --test-dir build  # or run the built test binary manually
   ```

### CLI Reference

The main entrypoint lives in `src/main.py` and is exposed as the `pasm` command.

- **Generate an emulator from an ISA file**

   ```bash
  pasm generate \
    --isa examples/simple8.yaml \
    --output generated/simple8 \
    [--dispatch switch] \
    [--validate-only] \
    [--verbose]
  ```

- **Validate an ISA file only**

  ```bash
  pasm validate --isa examples/simple8.yaml [--verbose]
  ```

- **Show a summary of an ISA**

  ```bash
  pasm info --isa examples/simple8.yaml
  ```

Flags (as specified in `docs/PLAN.md`):

- `--isa PATH` (required): Input YAML ISA file.
- `--output PATH`: Output directory (default: `./generated/[cpu_name]`).
- `--dispatch [switch|threaded|both]`:
  - `switch`: portable switch‑case dispatch (current implementation).
  - `threaded`: uses threaded dispatch (computed goto) on GCC/Clang, with switch fallback elsewhere.
  - `both`: emits both paths; toggle threaded mode with `-DUSE_THREADED_DISPATCH=ON` in CMake or `DISPATCH=threaded` in Make.
  - Generated code targets C11 and supports MSVC, Clang, and GCC.
- `--validate-only`: Validate the ISA and exit without generating code.
- `--verbose`: Print additional progress and error details.

### ISA Format

The ISA YAML format is documented in detail in:

- `docs/ISA_FORMAT.md` – human‑oriented description with examples.
- `schemas/isa_schema.json` – machine‑readable JSON Schema used at runtime.

Example files:

- `examples/minimal8.yaml` – very small 8‑bit ISA for smoke testing.
- `examples/simple8.yaml` – richer 8‑bit ISA with arithmetic, control flow, and a few hooks.
- `examples/z80.yaml` – full Z80 opcode-space coverage (documented + undocumented, including prefixed spaces).
- `examples/mos6502.yaml` – starter MOS 6502 ISA.
- `examples/mos6510.yaml` – starter MOS 6510 ISA (6502-compatible core plus 6510-specific I/O registers).

### Behavior Contract

Behavior snippets in ISA files are generated against a canonical API:

- Use decoded fields as `inst->field_name`.
- Use generated CPU-prefixed helpers (`<cpu_prefix>_read_*`, `<cpu_prefix>_write_*`).
- Define flag bits in YAML (`flags[].bit`) and access flags as `cpu->flags.<NAME>`.
- Declare register overlaps/bitfields in YAML (`registers[].parts`) when needed.
- Configure undefined opcode behavior in metadata (`undefined_opcode_policy: trap|nop`).

Legacy access compatibility is hard-cut: legacy forms are rejected at generation time.

### SectorZ Demo (OUT Hook)

Canonical demo assets are committed:

- `examples/sectorz_hello.c` - `print(char*)` emits bytes (including NUL) via `OUT (0x10), A`.
- `examples/z80_sectorz_hooks.yaml` - Z80 ISA with `port_write_post` hook enabled.
- `examples/sectorz_out_harness.c` - hook callback prints OUT bytes with `putc`.

Run end-to-end in one command:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev python scripts/run_sectorz_demo.py --z88dk-root /tmp/z88dk-src
```

Direct integration test gate:

```bash
UV_CACHE_DIR=/tmp/uv-cache PASM_SECTORZ_ROOT=/tmp/z88dk-src \
uv run --extra dev pytest -q tests/test_z80_sectorz_integration.py
```

CI can run this path optionally by setting repository variable `PASM_ENABLE_SECTORZ_TEST=1`.

### Development

- **Source**: `src/`
- **Schema**: `schemas/isa_schema.json`
- **Docs**: `docs/PLAN.md`, `docs/ISA_FORMAT.md`

Run tests with:

```bash
uv run --extra dev pytest
```

Z80 decode-cycle regression gate:

```bash
uv run --extra dev pytest -q tests/test_z80_cycle_reference.py
```

### License

This project is licensed under the MIT License. See `pyproject.toml` for metadata.

