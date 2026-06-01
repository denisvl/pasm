# PASM Architecture Overview

PASM (Processor Architecture Specification for Emulation) is a tool that generates high-performance C11 emulators from declarative YAML definitions. 

This document provides a high-level overview of the internal architecture of the Python generator found in `src/`.

## High-Level Pipeline

The code generation process follows a three-stage pipeline:

1. **Ingestion & Parsing (`src/parser/`)**
   Reads and validates the YAML definition files into a normalized, in-memory Python dictionary structure.
2. **Analysis (`src/analyzer/`)**
   Processes the abstract model to extract information required for code generation (e.g., resolving memory maps, calculating instruction widths, flattening connection graphs).
3. **Code Generation (`src/codegen/` & `src/generator.py`)**
   Uses Python formatting and logic to emit optimized C11 code, avoiding external templating engines like Jinja2 in favor of native logic templates for finer control.

## Component Breakdown

### 1. The Parser (`src/parser/yaml_loader.py`)
This module handles loading the various `.yaml` files passed via the CLI (e.g., `--processor`, `--system`, `--ic`, `--device`, `--host`).
- **Validation**: Ensures that all required keys are present and data types match expectations.
- **Normalization**: Flattens nested data structures and provides default values for optional fields, resulting in a single coherent `isa_data` dictionary that describes the entire emulated machine.

### 2. The Generator (`src/generator.py`)
The orchestrator of the code emission process. It creates the output directory structure (`generated/<cpu_name>/`) and directs the creation of the various C header and source files.
- Generates CMake build files.
- Emits the main entry points and structural files.
- Defers to specific `codegen/` modules for complex implementations.
- Prunes stale artifacts from older naming/layouts during regeneration (legacy monolithic CPU TU, stale system-scoped split files/headers).

### 3. Code Generation Modules (`src/codegen/`)
This is where the bulk of the logic resides. Key files include:

- **`cpu_impl.py`**: The heart of the CPU generator. It iterates over the processor's instructions to build the primary execution loop (the dispatch mechanism, either a massive `switch` statement or a computed goto/threaded dispatch). It emits:
  - Register read/write macros.
  - Flag calculation logic.
  - The core `step()` function.
  - The disassembler.
- **`split_units.py`**: Emits system-side split translation units (`*_runtime.c`, `*_system_bus.c`, `*_system_glue.c`, `*_host_glue.c`, `*_device_glue.c`) from codegen-owned sections.
- **`cpu_debug_abi.py`**: Generates the Debug ABI, providing an interface for debuggers (like the Rust TUI debugger) to inspect registers, memory, and CPU state without knowing the internal layout of the C structures.
- **`interrupts.py`**: Handles generating the logic for interrupt requests (IRQ, NMI) based on the CPU's interrupt model.
- **`templates.py`**: Contains the raw string templates for the C files, with placeholder tags that the Python logic fills in.
- **`split_layout.py`**: Canonical naming/layout registry for split unit suffixes and system prefix normalization.

## Execution Flow Example: `pasm generate`

1. User invokes `pasm generate --processor z80.yaml --system zx48k.yaml ...`
2. `main.py` parses the arguments and initializes `ProcessorSystemLoader`.
3. `yaml_loader.py` reads `z80.yaml`, `zx48k.yaml`, and other component files, returning a unified `isa_data` dict.
4. `generator.py` is instantiated with `isa_data`.
5. `generator.generate()` begins creating files:
   - `CMakeLists.txt`
   - `Z80.h` (using `isa_data` to define the CPU struct)
   - CPU-owned units:
     - `Z80_core.c` (delegating to `cpu_impl.py` for instruction dispatch and core CPU execution)
     - `Z80_decoder.c`
     - `Z80_debug_abi.c`
   - System-owned split units:
     - `<system_slug>_runtime.c`
     - `<system_slug>_system_bus.c`
     - `<system_slug>_system_glue.c`
     - `<system_slug>_host_glue.c`
     - `<system_slug>_device_glue.c`
   - `debugger_link.json` (split linkage contract consumed by debugger tooling)
6. The process exits, leaving behind a complete, compilable C11 emulator project in the output directory.

### Build Graph (Current)
- Generated CMake/Makefile use explicit split static libraries:
  - `<cpu>_cpu_core`
  - `<system>_system`
- Test executable links split archives explicitly (including ordering for static symbol resolution).
- The Rust TUI linked backend resolves split artifacts via `debugger_link.json` (no legacy single-library fallback).

## Design Philosophy

- **Zero-Dependency Templates**: Instead of using Jinja2, the generator constructs code via Python f-strings and list comprehensions. This makes it easier to trace where specific C lines come from and allows for complex string manipulation.
- **Static Resolution**: As much work as possible is done at generation time (e.g., expanding macros, resolving instruction overlaps) so that the generated C code is as "flat" and fast as possible.
- **Pluggable Architecture**: Systems, ICs, and Devices are defined independently of the CPU, allowing the same processor core to be reused across drastically different host environments (e.g., the MOS 6502 in the Apple II vs the NES vs the C64).
