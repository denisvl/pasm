## ISA Definition Format

This document describes the YAML format that PASM expects for Instruction Set Architecture (ISA) descriptions. It is the human‑readable companion to the machine‑readable schema in `schemas/isa_schema.json` and the examples in `examples/`.

The top‑level YAML object must contain at least:

- `metadata`
- `registers`
- `flags`
- `memory`
- `instructions`

Optional sections are `ports`, `interrupts`, and `hooks`.

### 1. Metadata

The `metadata` section identifies the processor and basic sizing:

```yaml
metadata:
  name: "Simple8"        # Processor name (required)
  version: "1.0"         # ISA version (optional but recommended)
  bits: 8                # Primary register width (required)
  address_bits: 16       # Address bus width (required)
  endian: little         # Endianness: little | big (required)
  undefined_opcode_policy: trap   # Optional: trap | nop (default: trap)
```

See `metadata` in `schemas/isa_schema.json` for exact validation rules.

### 2. Registers

The `registers` array declares all architecturally visible registers. Each entry has:

```yaml
registers:
  - name: "R0"               # Register name (required)
    type: general            # general | program_counter | stack_pointer | index | special
    bits: 8                  # Width in bits (required)
  - name: "PC"
    type: program_counter
    bits: 16
  - name: "SP"
    type: stack_pointer
    bits: 16

  # Optional explicit subdivisions / overlap view (YAML is authoritative)
  - name: "AX"
    type: general
    bits: 16
    parts:
      - name: "AL"
        lsb: 0
        bits: 8
      - name: "AH"
        lsb: 8
        bits: 8
```

You can declare ranges that the loader expands automatically (see `expand_register_ranges` in `src/parser/yaml_loader.py`):

```yaml
registers:
  - name: "R0..R7"
    type: general
    bits: 8
```

After loading, this becomes `R0`, `R1`, …, `R7` with the same type and width.

### 3. Flags

The `flags` array defines condition flags. Both `name` and `bit` are required:

```yaml
flags:
  - name: "Z"      # Zero flag
    bit: 0         # Required bit position in the raw flag byte
    description: "Set when result is zero"
  - name: "N"      # Negative/Subtract flag
    bit: 1
  - name: "C"      # Carry flag
    bit: 2
```

Flag names must match `^[A-Z0-9_]+$` and each flag must declare a unique `bit` in range `0..7` (see `flags` in the schema).

### 4. Memory Model

The `memory` section configures the main address space:

```yaml
memory:
  address_bits: 16       # Required
  default_size: 65536    # Optional, bytes; derived from address_bits if omitted
  regions:
    - name: "RAM"
      start: 0x0000
      size: 32768
      read_write: true
    - name: "ROM"
      start: 0x8000
      size: 32768
      read_only: true
```

Generated emulators expose a flat `memory` array (`CPUState::memory`) with `memory_size` bytes. Region permissions are enforced in generated memory helpers: writes to `read_only: true` (or `read_write: false`) regions are rejected at runtime.

### 5. Port I/O (Optional)

If the ISA exposes a separate I/O port space, describe it with the `ports` object:

```yaml
ports:
  address_bits: 8        # Width of port addresses
  size: 256              # Number of addressable ports
```

The generator allocates a flat `port_memory` array of length `size`, accessed via generated helpers such as `{cpu_prefix}_read_port` and `{cpu_prefix}_write_port`.

### 6. Interrupts (Optional)

The `interrupts` object describes interrupt modes and vectoring:

```yaml
interrupts:
  model: z80                 # none | fixed_vector | z80
  modes:
    - name: "IM0"
      description: "Interrupt mode 0"
    - name: "IM1"
    - name: "IM2"
  fixed_vector: 0x0038       # Used by fixed_vector model
  vector_table: true
  vector_size: 2
```

`interrupts.model` selects the runtime interrupt strategy:

- `none`: generate no interrupt servicing block in `step()`.
- `fixed_vector`: pushes current `PC` and jumps to `fixed_vector` (default `0x0038`).
- `z80`: enables Z80-style IM0/IM1/IM2 handling.

When `model: z80`, generated `step()` includes interrupt servicing semantics gated by the declared modes:

- `IM0` (mode `0`): minimum viable behavior; treats `interrupt_vector` as an externally supplied opcode and resolves `RST` vectors (`0xC7` pattern), otherwise falls back to `0x0038`.
- `IM1` (mode `1`): fixed vector to `0x0038`.
- `IM2` (mode `2`): vector-table lookup using `I:vector` (`(REG_I << 8) | interrupt_vector`) when register `I` exists; otherwise falls back to `interrupt_vector << 8`.

If `model` is omitted, PASM keeps compatibility by inferring:
- `z80` when IM* modes are declared.
- `fixed_vector` otherwise.

Generated CPU state fields are model-aware:
- `none`: no interrupt state fields.
- `fixed_vector`: `interrupt_vector`, `interrupts_enabled`, `interrupt_pending`.
- `z80`: `interrupt_mode`, `interrupt_vector`, `interrupts_enabled`, `interrupt_pending`.

Calling `{cpu_prefix}_interrupt(cpu, vector)` queues a pending interrupt (or acts as a no-op for `none`); servicing occurs during `step()` when interrupts are enabled.

Generated interrupt APIs are also model-aware:
- `{cpu_prefix}_interrupt(cpu, vector)` and `{cpu_prefix}_set_irq(cpu, enabled)` are always emitted.
- `{cpu_prefix}_set_interrupt_mode(cpu, mode)` is emitted only for `model: z80`.

### 7. Hooks (Optional)

Execution hooks let you tap into specific points of execution and port I/O. The `hooks` object can contain:

```yaml
hooks:
  pre_fetch:
    enabled: true
    description: "Called before each instruction fetch"
  post_decode:
    enabled: false
  post_execute:
    enabled: true
    description: "Called after each instruction executes"
  port_read_pre:
    enabled: false
    description: "Called before read_port() returns"
  port_read_post:
    enabled: false
    description: "Called after read_port() resolves value"
  port_write_pre:
    enabled: false
    description: "Called before write_port() mutates port memory"
  port_write_post:
    enabled: false
    description: "Called after write_port() mutates port memory"
```

When any hook’s `enabled` flag is `true`, PASM will:

- Add hook state to `CPUState`.
- Generate a `{cpu_name}_hooks.h` / `{cpu_name}_hooks.c` pair with a small hook API.
- Invoke enabled execution hooks in `step()`.
- Invoke enabled port hooks in generated `{cpu_prefix}_read_port` / `{cpu_prefix}_write_port`.

Generated hook callbacks are event-based:

```c
typedef void (*CPUHookFunc)(CPUState *cpu, const CPUHookEvent *event, void *context);
```

`CPUHookEvent` includes event type plus payload (`pc`, `prefix`, `opcode`, `port`, `value`, `raw`).

### 8. Instructions

The `instructions` array is the heart of the ISA: each entry defines *what* an instruction does and *how* it is encoded.

#### 8.1 Required fields

Each instruction object must contain at least:

```yaml
instructions:
  - name: "ADD_A_r"                # Uppercase identifier (^[A-Z_][A-Z0-9_]*$)
    display: "ADD A, r"            # Optional printable mnemonic for trace/disassembly
    category: arithmetic           # arithmetic | logic | data_transfer | control | bit | rotate | misc
    encoding: { ... }              # See below
    length: 1                      # Total length in bytes
    cycles: 1                      # Nominal cycle count (integer)
    behavior: |                    # C code implementing the instruction
      /* Your C snippet here */
```

#### 8.2 Encoding object

The `encoding` block describes how to match opcodes and extract fields:

```yaml
encoding:
  opcode: 0x80         # Primary opcode value (8 or 16 bits)
  mask: 0xF8           # Optional mask for matching variable‑field opcodes
  prefix: 0xDD         # Optional prefix byte (for Z80‑style extended opcodes)
  subop: 0xB0          # Optional secondary opcode (usually in the second byte)
  subop_mask: 0xF8     # Optional mask applied to subop before comparison
  length: 2            # Total instruction length in bytes
  fields:              # Optional list of extracted fields
    - name: "r"
      position: [5, 3] # Bit range [msb, lsb] within the 16‑bit `raw` word
      width: 3         # Optional; can be derived from position
      type: register   # register | immediate | address
```

- `opcode` and `mask` control how the decoder matches an instruction.
- `prefix` and `subop` let you describe multi‑byte encodings such as Z80’s extended opcodes.
- `subop_mask` (default `0xFF`) enables masked sub-opcode matching for grouped forms (for example `DD/FD CB d op`, where `op` packs bit/register fields).
- `fields` become members on the generated `DecodedInstruction` struct and should be referenced in `behavior` as `inst-><field_name>`.
- `display` is optional and, when present, is used as the printable instruction text in generated trace/disassembly output.

The JSON Schema in `schemas/isa_schema.json` rigorously validates ranges and shapes of these fields.

#### 8.3 Behavior code

`behavior` is a multi‑line C snippet that implements the instruction’s semantics. It runs inside a generated function with the signature:

```c
static void inst_<NAME>(CPUState *cpu, DecodedInstruction *inst);
```

You should:

- Read and write registers via the generated `cpu->registers[...]` array and any special fields (`pc`, `sp`, etc.).
- Access decoded fields through `inst->field_name`.
- Use generated helper functions with the CPU prefix, for example `<cpu_prefix>_read_byte` / `<cpu_prefix>_write_byte`.
- Use YAML-defined named flags directly (`cpu->flags.<FLAG_NAME>`).

Canonical behavior contract (recommended for all new ISA files):
- `DecodedInstruction` fields are always pointer-style (`inst->field`).
- Runtime helper calls are always CPU-prefixed (`<cpu_prefix>_read_*`, `<cpu_prefix>_write_*`).
- Flag access is always through YAML-defined members (`cpu->flags.<FLAG_NAME>`).
- Register overlaps/bitfields are emitted only when declared in YAML (`registers[].parts`).

Hard cutover:
- `flags[].bit` is mandatory.
- Helper macros/inline helpers for flags/PC are not generated.
- Legacy behavior access is rejected at generation time (`inst.field`, generic `cpu_read_*`/`cpu_write_*`, helper-macro legacy forms).

The generator automatically increments `cpu->total_cycles` by the instruction’s `cycles` value at the end of each generated function.

### 9. Minimal Example (Minimal8)

`examples/minimal8.yaml` demonstrates a very small ISA:

- A handful of 8‑bit general‑purpose registers plus `PC` and `SP`.
- A single `Z` flag.
- Simple `NOP`, `INC`, and `HALT` instructions.

Use it as a reference when building your own “toy” architectures.

### 10. Richer Example (Simple8)

`examples/simple8.yaml` illustrates:

- Multiple flags (`Z`, `N`, `P`, `S`, `C`).
- Immediate, register‑to‑register, and memory‑based operations.
- Simple control‑flow instructions (`JP`, `JPZ`, `JPNZ`, `CALL`, `RET`).
- Optional hooks configuration.

It is a good starting point for designing non‑trivial ISAs that still fit in a single page of YAML.

### 11. Processor Examples

Additional bundled ISA examples:

- `examples/z80.yaml`: full Z80 opcode-space coverage including documented/undocumented forms, prefixed decode spaces, interrupts, ports, and block I/O instructions.
- `examples/mos6502.yaml`: starter MOS 6502 core.
- `examples/mos6510.yaml`: starter MOS 6510 core with 6510-specific `IO_DDR` and `IO_DATA` registers.

### 12. Authoring Guidelines

- Keep instruction names concise and consistent; use suffixes like `_IMM` or `_REL` for addressing modes.
- Prefer mask‑and‑field encodings over duplicating near‑identical entries for each register or condition code.
- Start with a small, bootstrapping subset of instructions, then grow the ISA once you have the generator and tests passing.

