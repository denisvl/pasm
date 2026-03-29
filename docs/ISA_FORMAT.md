## PASM YAML Format (Current)

PASM composes a system from these YAML layers:
1. `processor.yaml` (required)
2. `system.yaml` (required)
3. `ic.yaml` (repeatable)
4. `device.yaml` (repeatable)
5. `host.yaml` (repeatable)
6. `cartridge.yaml` (optional, single active cartridge)

Single-file ISA input is removed.

Schemas:
- `schemas/processor_schema.json`
- `schemas/system_schema.json`
- `schemas/ic_schema.json`
- `schemas/device_schema.json`
- `schemas/host_schema.json`
- `schemas/cartridge_schema.json`

## 1) `processor.yaml`

Owns CPU semantics:
- `metadata`
- `registers`
- `flags`
- `instructions`
- optional `ports`, `interrupts`
- required `coding`

Implemented display fields:
- `registers[].display_name` (debug/UI label override)
- `instructions[].display_template` (`{field}` / `{field:formatter}`)
- `instructions[].display_operands` (operand render specs)

Supported `interrupts.model` values:
- `none`
- `fixed_vector`
- `z80`
- `mos6502`
- `mc6809`

Instruction behavior contract:
- operand access: `inst->field`
- runtime helpers: `<cpu_prefix>_read_*` / `<cpu_prefix>_write_*`
- flags via `cpu->flags.<NAME>` or `cpu->flags.raw`
- legacy access patterns are rejected

When components (`ic`/`device`/`host`/`cartridge`) are present, each instruction must include:
- `timing_profile.bus_events[]`
- `timing_profile.total_tstates == cycles`

## 2) `system.yaml`

Owns runtime deployment and wiring graph:
- `metadata`, `clock_hz`, `memory`
- optional `reset_delay_seconds` (default `0`)
- optional `hooks`, `integrations`
- required `components`:
  - `ics[]`
  - `devices[]`
  - `hosts[]`
  - optional `cartridge` (single ID)
- required `connections[]`
- optional `audio`:
  - `sample_rate`
  - `format` (`s16le` or `float32`)
  - `channels` (1 or 2)

`reset_delay_seconds` applies every time generated runtime calls `<cpu_prefix>_reset`.

`system.yaml` memory can declare ROM manifests:

```yaml
memory:
  default_size: 65536
  regions:
    - name: ROM
      start: 0xC000
      size: 0x4000
      read_only: true
  rom_images:
    - name: system_rom
      file: ../../roms/example_system/system.rom
      target_region: ROM
      offset: 0
```

Generated runtime APIs:
- `<cpu_prefix>_load_system_roms(cpu, system_base_dir)`
- `<cpu_prefix>_load_cartridge_rom(cpu, path)`

Generated `main.c` runtime flags:
- `--system-dir <dir>`
- `--cart-rom <file>` (only emitted for cartridge-enabled systems)

ROM rules:
- `target_region` must exist and be read-only.
- `offset` is optional (default `0`) and must be non-negative.
- placement must fit target region and not overlap other ROM images.
- `file` resolves relative to `system.yaml` directory (or absolute path).
- ROMs must be provided through system/cartridge runtime loading (for example `--system-dir` and `--cart-rom`), not hardcoded `fopen(...)` paths inside YAML behavior snippets.

`system.yaml` is the single source of component connectivity.

### Connection entry

```yaml
connections:
  - from:
      component: "ula0"
      kind: "signal"      # signal|callback
      name: "frame_boundary"
    to:
      component: "video0"
      kind: "handler"     # handler|callback
      name: "on_frame_boundary"
```

Rules:
- `callback -> callback`
- `signal -> handler`
- arity must match
- literal pseudo-component `"host"` is not supported; use declared host IDs

## 3) `ic.yaml`

One IC component per file.

Required top-level keys:
- `metadata` (`id`, `type`, `model`)
- `state[]`
- `interfaces`
- `behavior`
- `coding`

Optional:
- `clock_hz`
- `maps` (`ports`, `memory`) for interception ownership/overlap checks

## 4) `device.yaml`

One peripheral component per file.

Required top-level keys:
- `metadata` (`id`, `type`, `model`)
- `state[]`
- `interfaces`
- `behavior`
- `coding`

Optional:
- `clock_hz`

## 5) `host.yaml`

One host component per file.

Required top-level keys:
- `metadata` (`id`, `type`, `model`)
- `state[]`
- `interfaces`
- `behavior`
- `coding`

Optional:
- `clock_hz`
- `input.keyboard` declarative key mapping

Rules:
- Host YAML is HAL-only and must not encode backend implementation selectors.
- Backend selection remains compile-time in current rollout and is provided by codegen (`--host-backend`).

Keyboard input mapping (optional, v1):

```yaml
input:
  keyboard:
    focus_required: true
    bindings:
      - host_key: BACKSPACE
        presses:
          - { row: 0, bit: 0 }
          - { row: 4, bit: 0 }
```

Rules:
- Host keyboard mappings are backend-agnostic at the YAML contract level.
- `bindings[].host_key` must use canonical host key names (for example `BACKSPACE`, `ENTER`, `UP`, `A`).
- `bindings[].presses` must be non-empty.
- `presses[].row` range `0..31`, `presses[].bit` range `0..7`.
- duplicate `host_key` entries are rejected.

Compatibility:
- SDL remains a default host backend implementation, but it is not part of the YAML input contract.
- Backend selection is compile-time via CLI/codegen (not runtime plugin loading) in the current rollout.

See `docs/HOST_HAL_PLAN.md` for phased migration status and exit criteria.

## 6) `cartridge.yaml`

One cartridge mapper component per file (single active cartridge per run).

Required top-level keys:
- `metadata` (`id`, `type`, `model`)
- `state[]`
- `interfaces`
- `behavior`
- `coding`

Optional:
- `clock_hz`
- `maps.ports` (`read[]` and `write[]` entries)
- `maps.memory.ranges[]`

Composition constraints:
- if `system.components.cartridge` is set, both `--cartridge-map` and `--cartridge-rom` are required.
- provided cartridge map ID must match `system.components.cartridge` exactly.
- systems without cartridge slot reject `--cartridge-map` / `--cartridge-rom`.

## 7) `interfaces` and `behavior`

### Interfaces

```yaml
interfaces:
  callbacks:
    - name: "read_matrix"
      args: [u8]
      returns: u8
  handlers:
    - name: "on_border_changed"
      args: [u8]
  signals:
    - name: "border_present"
      args: [u8]
```

### Behavior

```yaml
behavior:
  snippets:
    init: |
      /* lifecycle snippet */
    step_post: |
      /* called after instruction execution */
    mem_read_pre: |
      /* called before memory read */
    port_write_pre: |
      /* called before port write */
  callback_handlers:
    read_matrix: |
      return 0xFFu;
  handler_bodies:
    on_border_changed: |
      /* handle routed signal */
```

Snippet context provided by generated runtime:
- always: `CPUState *cpu`, `ComponentState_<id> *comp`
- callback/handler snippets: `const uint64_t *args`, `uint8_t argc`
- memory snippets: `uint16_t addr` (and `uint8_t value` for writes)
- port snippets: `uint16_t port`, `uint8_t value` (for write/pre and read/post)
- step snippets: `DecodedInstruction *inst`, `uint16_t pc_before`

Generic routing helpers inside snippets:
- `cpu_component_call(cpu, "<component_id>", "<callback>", args, argc)`
- `cpu_component_emit_signal(cpu, "<component_id>", "<signal>", args, argc)`

## 8) `coding` section

Required in behavior-capable YAML files:

```yaml
coding:
  headers: ["stdint.h", "my_header.h"]
  include_paths: ["./include"]
  linked_libraries:
    - name: "m"
    - path: "./lib/libcustom.a"
  library_paths: ["./lib"]
```

Generation merge semantics:
- order: processor, `--ic` order, `--device` order, `--host` order, then cartridge
- deterministic union with exact-value de-dup
- first occurrence preserved
- relative paths resolved from each YAML file directory

Host backend behavior (current rollout):
- `--host-backend` drives default platform setup in codegen.
- `--host-backend sdl2` auto-wires SDL build linkage and CPU-side SDL header inclusion.
- `--host-backend glfw` auto-wires GLFW build linkage.
- In-repo host YAML examples therefore keep `coding.linked_libraries: []` for backend libs and avoid explicit `SDL2/SDL.h` in `coding.headers`.
- Explicit `coding.headers` / `coding.linked_libraries` are still supported for non-backend-specific dependencies.

## 9) CLI

```bash
pasm generate --processor <processor.yaml> --system <system.yaml> [--ic <ic.yaml> ...] [--device <device.yaml> ...] [--host <host.yaml> ...] [--host-backend sdl2|glfw|stub] [--cartridge-map <cartridge.yaml>] [--cartridge-rom <rom_file>] --output <dir> [--dispatch switch|threaded|both] [--validate-only]
pasm validate --processor <processor.yaml> --system <system.yaml> [--ic <ic.yaml> ...] [--device <device.yaml> ...] [--host <host.yaml> ...] [--host-backend sdl2|glfw|stub] [--cartridge-map <cartridge.yaml>] [--cartridge-rom <rom_file>]
pasm info --processor <processor.yaml> --system <system.yaml> [--ic <ic.yaml> ...] [--device <device.yaml> ...] [--host <host.yaml> ...] [--host-backend sdl2|glfw|stub] [--cartridge-map <cartridge.yaml>] [--cartridge-rom <rom_file>]
```

Aliases:
- `pasm gen` is equivalent to `pasm generate`.

`--isa` is removed.

## 10) Cross-file validation summary

- `memory.default_size <= 2^processor.metadata.address_bits`
- memory regions fit within `default_size`
- system hook names must be supported
- `system.components.ics/devices/hosts` must match loaded files exactly
- `system.components.cartridge` must match loaded cartridge map ID when present
- connection endpoints must exist and have compatible arity
- IC/cartridge memory map overlaps are hard-fail
- port map overlaps are validated per direction (`read` and `write` independently)
- component-enabled generation requires instruction timing profiles
