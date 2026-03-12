## PASM YAML Format (Hard Cutover)

PASM now requires two YAML files:

1. `processor.yaml` for CPU semantics.
2. `system.yaml` for runtime/deployment configuration.

Single-file ISA input is removed.

Schemas:
- `schemas/processor_schema.json`
- `schemas/system_schema.json`

## 1) `processor.yaml`

Owns CPU architecture and instruction semantics.

Required top-level keys:
- `metadata`
- `registers`
- `flags`
- `instructions`

Optional:
- `ports`
- `interrupts`

### `metadata`

```yaml
metadata:
  name: "Z80"
  version: "0.1"
  bits: 8
  address_bits: 16
  endian: little
  undefined_opcode_policy: trap   # trap|nop, default trap
```

### `registers`

```yaml
registers:
  - name: "A"
    type: general
    bits: 8
  - name: "PC"
    type: program_counter
    bits: 16
  - name: "SP"
    type: stack_pointer
    bits: 16
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

Range expansion is supported: `R0..R7`.

### `flags`

`flags[].bit` is required.

```yaml
flags:
  - name: "Z"
    bit: 0
  - name: "C"
    bit: 1
```

Rules:
- names are uppercase identifier style
- bit range is `0..7`
- duplicate flag names or duplicate bits are rejected

### `instructions`

```yaml
instructions:
  - name: "LD_A_N"
    display: "LD A, n"
    category: data_transfer
    encoding:
      opcode: 0x3E
      mask: 0xFF
      length: 2
      fields:
        - name: "n"
          position: [15, 8]
          type: immediate
    cycles: 7
    behavior: |
      cpu->registers[REG_A] = inst->n;
```

Behavior contract is strict:
- Use decoded operands as `inst->field`.
- Use CPU-prefixed runtime helpers (`<cpu_prefix>_read_*`, `<cpu_prefix>_write_*`).
- Use YAML-defined flags as `cpu->flags.<NAME>` or `cpu->flags.raw`.
- Legacy forms are rejected (`inst.field`, `cpu_read_*`, `cpu_write_*`, helper-style legacy APIs).

### `ports` and `interrupts`

These remain processor-owned. Runtime generation still derives port/interrupt semantics from processor YAML.

## 2) `system.yaml`

Owns deployment/runtime configuration.

Required top-level keys:
- `metadata`
- `clock_hz`
- `memory`

Optional:
- `hooks`
- `integrations`

### Example

```yaml
metadata:
  name: "Z80DefaultSystem"
  version: "0.1"
clock_hz: 1000000
memory:
  default_size: 65536
  regions:
    - name: "RAM"
      start: 0x0000
      size: 0x8000
      read_write: true
    - name: "ROM"
      start: 0x8000
      size: 0x8000
      read_only: true
hooks:
  post_execute:
    enabled: false
  port_write_post:
    enabled: true
integrations:
  sectorz_demo:
    channel: "stdout"
```

## 3) Cross-file Validation

Composition checks enforce:
- `system.memory.default_size > 0`
- `system.memory.default_size <= 2^processor.metadata.address_bits`
- region `start`/`size` are non-negative
- each region must fit inside `default_size`
- system hook names must be in supported hook set:
  - `pre_fetch`
  - `post_decode`
  - `post_execute`
  - `port_read_pre`
  - `port_read_post`
  - `port_write_pre`
  - `port_write_post`

## 4) CLI

Use dual arguments only:

```bash
pasm generate --processor <processor.yaml> --system <system.yaml> --output <dir>
pasm validate --processor <processor.yaml> --system <system.yaml>
pasm info --processor <processor.yaml> --system <system.yaml>
```

`--isa` is removed.

## 5) Generated Model Notes

- Memory behavior and ROM write guards are generated from `system.memory.regions`.
- Hook generation is driven only by `system.hooks`.
- Port and interrupt runtime behavior are driven only by processor declarations.
- System metadata (`name`, `version`, `clock_hz`, `integrations`) is exposed in generated metadata constants/comments.
