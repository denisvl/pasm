# Generator Refactor: Split Compilation Units + Linked Processor Library

## Summary
Refactor code generation so output is split into independent C source files by responsibility, with processor core compiled as a dedicated library and linked with system/device/host libraries. Roll out across all generators now, using new explicit CMake target names.

## Implementation Changes

1. **Define the new generated module layout**
- Emit separate units for:
  - `processor_core` (decode/execute, CPU state transitions, core ISA helpers)
  - `system_bus` (address dispatch, memory map glue, component routing)
  - `device_*` (one generated file per device/component family where practical)
  - `host_*` (host I/O adapters and host callback glue)
  - `runtime_shared` (shared structs/macros/utilities)
- Keep generated public headers cleanly layered:
  - core-facing API (CPU lifecycle/step/read/write hooks)
  - platform-facing API (system init, host attach, component registration)

2. **Refactor codegen internals to emit partitioned code**
- Split monolithic emitter responsibilities currently centered in CPU implementation generation into distinct emitters/templates.
- Move shared declarations/macros to generated shared headers to avoid cross-unit duplication.
- Ensure each generated `.c` has clear ownership and minimal includes.
- Preserve behavior: no semantic changes to emulation logic in this pass; only source partition + symbol relocation.

3. **Introduce explicit CMake target graph (new names)**
- Generate explicit static libraries:
  - `<cpu>_cpu_core`
  - `<system>_system` (system/devices/host glue)
  - optional `<system>_runtime` if shared utilities need separate linkage
- Executable/test target links these in deterministic order:
  - runtime -> cpu_core -> system (or equivalent required by symbol deps).
- Keep debugger-linked backend compatibility by updating generated build exports and target references to the new graph.

4. **Update generator integration points**
- Update template orchestration so generated file list and CMake lists are derived from module registry (not hardcoded monolith assumptions).
- Ensure all run scripts and generation paths continue to work with the new output structure for every supported system that uses this pipeline.

5. **Docs update (repo-wide, not BBC-specific)**
- Update docs under `docs/` to describe:
  - new generated source structure
  - new library target names and link model
  - how systems compose processor/system/device/host at build time
  - migration note for tooling expecting old target names

## Public Interfaces / Build Contract Changes
- **Build target naming changes** (intentional):
  - old single-emulator lib target usage replaced by explicit split targets.
- **Generated file contract changes**:
  - downstream tools/scripts should not assume one main CPU C file contains all logic.
- **No functional API behavior changes** expected for emulator runtime semantics in this refactor.

## Test Plan
1. **Generation validation**
- Generate all supported systems and verify expected partitioned files and CMake targets exist.
- Validate no duplicate symbol or missing symbol across split units.

2. **Build validation**
- Full clean builds for representative processor families (6502, 6510, Z80, 6809).
- Build linked debugger/TUI path against new target graph.

3. **Smoke runtime checks**
- Boot smoke tests for key systems already used in this repo (NES, Atari 800XL, C64, SMS, MSX1, CoCo1, Atari 2600, SG-1000, BBC Micro).
- Confirm cartridge picker paths still launch and runtime loop starts.

4. **Regression guardrails**
- Re-run existing test suite relevant to codegen/build outputs.
- Add/adjust tests that assert generated CMake includes split targets and that processor core is not merged with host/system code.

## Assumptions
- Split should be **behavior-preserving**; any emulator correctness bugs found during rollout are treated as regressions and fixed before finalize.
- Libraries remain static unless a system already requires otherwise.
- Rollout is **all generators now**, not feature-flagged.
- New explicit target names are accepted and docs/scripts will be updated in the same change.

## Progress (Current)
- Done:
  - Core split ownership tightened:
    - `src/{CPU}_core.c` is now generated as the real core implementation TU.
    - Legacy `src/{CPU}.c` monolithic compatibility shim generation has been removed.
  - Split file/target layout is active across generators:
    - CPU core: `{CPU}_core.c` + `{CPU}_decoder.c` -> `<cpu>_cpu_core`
    - System side: `<system>_runtime.c`, `<system>_debug_abi.c`, `<system>_system_bus.c`, `<system>_system_glue.c`, `<system>_host_glue.c`, `<system>_device_glue.c` -> `<system>_system`
  - Generator now prunes stale split-unit artifacts from previous naming/layouts.
  - Naming normalization for generated system prefixes is in place (`src/codegen/split_layout.py`).
  - Generation contract tests passing for current split behavior.
  - Build graph alignment completed for generated executables in both build systems:
    - CMake `*_test` now links split targets (`<system>_system` + `<cpu>_cpu_core`) directly.
    - Makefile `$(TARGET)` already links split archives directly; formatting/definition issues in split source lists were corrected.
    - Static-link ordering for split archives is now explicit and robust in both generators:
      - CMake test link line uses `cpu_core -> system -> cpu_core`.
      - Makefile test link line uses `$(CPU_CORE_LIB) $(SYSTEM_LIB) $(CPU_CORE_LIB)`.
  - Legacy `*_emu` compatibility library generation removed from generated CMake/Makefile outputs.
    - Split-only contract is now authoritative (`<cpu>_cpu_core` + `<system>_system`).
  - Debugger linked backend build script now enforces split-artifact linkage from `debugger_link.json` (`system_static` + `cpu_core_static`) with no legacy single-library fallback.
  - `debugger_link.json` publishes split system linkage as the canonical build contract (`cmake_library_target` / `library_basename` + `split_artifacts`).
  - Runtime ownership extraction progressed:
    - `*_runtime.c` now owns both system ROM loader and cartridge loader API bodies.
    - CPU execution path no longer calls picker internals or host-picker bridge APIs directly.
    - Core now calls neutral split contract `cpu_components_runtime_pre_step(cpu)`, implemented in `*_system_glue.c`, which owns cartridge pending-swap application when enabled.
  - Interrupt API ownership extraction completed:
    - interrupt API bodies are emitted in `*_system_glue.c` (not in monolithic `CPU.c`),
    - regression coverage added in generation contracts for this boundary.
  - Split metadata now reflects actual ownership:
    - `split_units.cpu_core_sources` includes `*_debug_abi.c` alongside `*_core.c` and `*_decoder.c`.
  - Dispatch contract declarations are now centralized in a dedicated codegen module:
    - `src/codegen/dispatch_contract.py` owns `ComponentConnection` + routing/dispatch API declarations.
    - `cpu_header` consumes this module and injects declarations into `cpu.h` via a template placeholder.
    - generation contract tests now guard this shared contract path.
  - Nested split-marker infrastructure added in codegen (`PASM_SPLIT` supports nested subsection extraction/filtering).
  - `INPUT_RUNTIME` now contains explicit nested `HOST_HAL_IMPL` markers, enabling targeted extraction in the next ownership move.
  - Split unit emitters are now centralized in a dedicated module:
    - `src/codegen/split_units.py` owns generation of `*_runtime.c`, `*_system_glue.c`, and `*_host_glue.c`.
    - `src/generator.py` now orchestrates via this module instead of embedding large split-unit bodies inline.
  - `split_units` now consumes public codegen interfaces instead of private helper symbols for runtime/interrupt ownership glue.
  - Split layout naming now has an explicit unit registry:
    - `src/codegen/split_layout.py` defines `SplitUnitSpec` + `SYSTEM_UNITS` as the single source of truth for split unit suffix/order/ownership metadata.
    - existing suffix consumers remain compatible through derived `SYSTEM_UNIT_SUFFIXES`.
  - Host HAL extraction prep scaffolding is now explicit and test-covered:
    - core helper generation emits `PASM_SPLIT_BEGIN/END:HOST_HAL_IMPL` markers around backend HAL sections,
    - `src/codegen/split_units.py` exposes section extraction helpers (`extract_split_section(s)`),
    - generation contract tests assert marker emission and extraction behavior.

- Completed closure notes:
  - Host HAL/backend helper extraction is finalized under split ownership:
    - host HAL implementation ownership in `*_host_glue.c`,
    - support contracts/types/prototypes in system-side glue as needed.
  - Cartridge-picker/keyboard/controller runtime ownership is finalized in system-side units:
    - core excludes `INPUT_RUNTIME`, `CARTRIDGE_PICKER_RUNTIME`, `COMPONENT_RUNTIME`,
    - ownership and includes live in split system glue/runtime units.
  - Staged/duplicate split shims have been removed:
    - no remaining `COMPONENT_DISPATCH`-triggered core-side runtime symbol promotion.
  - Routing/dispatch/connections ownership is fully system-side:
    - `cpu_component_call`, `cpu_component_emit_signal`, dispatch helpers, and connection table/count are emitted from `system_glue`.
  - Split-only build contract is verified for active interactive outputs:
    - generated interactive `Makefile` targets link split libs (`CPU_CORE_LIB` + `SYSTEM_LIB`) with explicit ordering,
    - interactive `debugger_link.json` manifests publish `split_artifacts` (`cpu_core_static`, `system_static`).
    - Monolithic `_emu` detections are confined to legacy/scratch generated directories and not part of active interactive outputs.
  - Validation summary (latest):
    - split regression tests: green (`tests/test_generation_contracts.py` + `tests/test_codegen.py`: `152 passed`),
    - representative split builds: green (NES, C64, SMS, MSX1, CoCo1, CPC464, BBC Micro).

## Added Scope: Memory/Bus Ownership (CPU Reusability)
- CPU core must be reusable across systems without embedding per-system memory map logic.
- Core memory APIs should only do:
  - call split bus hooks,
  - fallback to generic flat memory checks/access.
- System-specific mapping must live in split system-owned units (`*_system_bus.c`).

### Contract
- `uint8_t cpu_components_bus_read(CPUState *cpu, uint16_t addr, uint8_t *handled)`
- `uint8_t cpu_components_bus_write(CPUState *cpu, uint16_t addr, uint8_t value, uint8_t *handled)`

### Progress Update
- Implemented bus hook declarations in split dispatch contract.
- Updated core memory access template to delegate to bus hooks first.
- Implemented generation of `*_system_bus.c` hook bodies from IC/system memory mapping snippets.

## Added Scope: Port I/O Ownership (CPU Reusability)
- CPU core must not embed per-system port dispatch logic (VDP/PIA/PSG/etc).
- Core port APIs should only do:
  - call split port hooks,
  - fallback to generic `port_memory` behavior.
- System-specific port mapping must live in split system-owned units (`*_system_bus.c`).

### Contract
- `uint8_t cpu_components_port_read(CPUState *cpu, uint16_t port, uint8_t *handled)`
- `void cpu_components_port_write(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled)`

### Progress Update
- Added port hook declarations to dispatch contract generation.
- Updated core port access template to delegate to port hooks first.
- Implemented generation of `*_system_bus.c` port hook bodies from IC/system port snippets.
- Verified representative builds after extraction:
  - `z80_sms_sdl`, `z80_msx1_sdl`, `mos6502_nes_interactive`, `atari800xl_interactive` (compile/link green).
- Added per-IC source unit emission and build integration:
  - new generated files: `{system}_ic_{ic_id}.c`
  - split layout/build now compiles and links IC units via `<system>_system`
- Migrated IC bus/port handlers out of generic system bus glue into per-IC units.
- Migrated IC lifecycle hooks (`init/reset/destroy`) ownership to per-IC units, with system-level lifecycle wrappers acting as dispatch only.

## Remaining for Full CPU Reuse Goal
- Move/reset-delay timing driver policy out of CPU core step path (currently `reset_delay_pending` handling stays in core step generation).
- Keep core lifecycle/step flow limited to ISA execution + declared neutral callbacks only.

## Added Scope: Per-IC Source Unit Generation
Goal: generate distinct source units for each IC used by a system, so IC logic is independently compiled and linked instead of coalesced into generic system glue files.

### Target Layout
- Keep existing split CPU units:
  - `{CPU}_core.c`, `{CPU}_decoder.c`, `{CPU}_debug_abi.c`
- Keep system orchestration units:
  - `{system}_runtime.c`
  - `{system}_system_bus.c`
  - `{system}_system_glue.c`
  - `{system}_host_glue.c`
  - `{system}_device_glue.c`
- Add new IC-specific units (one per declared IC instance):
  - `{system}_ic_{ic_instance}.c`
  - optional `{system}_ic_{ic_instance}.h` only when private declarations need exposure

### Ownership Rules
- IC behavior/state transitions live in `{system}_ic_{ic_instance}.c`:
  - IC read/write handlers
  - IC tick/step callbacks
  - IC-local helper functions/macros
- `*_system_bus.c` remains dispatcher-only:
  - address/port decode and routing to IC/unit entry points
  - no embedded IC logic blocks
- CPU core remains system-agnostic:
  - no `ComponentState_*`/IC symbols in `*_core.c`
  - only neutral bus/port/lifecycle contracts

### Build Graph Changes
- Keep two-link-target model for now:
  - `<cpu>_cpu_core`
  - `<system>_system`
- Extend `<system>_system` source list to include all `{system}_ic_*.c` units.
- `debugger_link.json` continues to publish split artifacts, now with IC units folded into `system_sources`.

### Naming/Generation Contract
- File names must use underscore style for readability.
- IC source file naming is deterministic from IC instance id after normalization.
- No legacy/monolithic fallback generation for IC code paths.

### Migration Plan
1. Extract IC code blocks from current system glue/bus emitters into dedicated IC emitters.
2. Emit IC declarations/prototypes required by dispatcher from shared system glue header area.
3. Update split unit registry (`split_layout.py`) to include dynamic IC unit list.
4. Update CMake/Makefile generators to compile/link IC units automatically.
5. Update generation contract tests:
   - assert presence of `{system}_ic_*.c` for systems with ICs
   - assert `*_system_bus.c` contains dispatch/routing only
   - assert no IC implementation leakage into CPU core
6. Re-run representative multi-family builds and runtime smoke tests.

### Validation Checklist (must pass before closure)
- Build passes:
  - MOS6502/MOS6510/Z80/MC6809 representative systems
- Runtime smoke passes:
  - NES, Atari 800XL, C64, SMS, MSX1, SG-1000, CoCo1, CPC464, BBC Micro, ZX48
- Contract tests pass and enforce:
  - CPU core purity (no IC/system symbols)
  - IC-per-unit generation
  - dispatcher-only bus/port units

### Current Status (2026-05-08)
- `COMPONENT_LIFECYCLE` is no longer emitted in CPU core TUs.
- Per-IC lifecycle symbols are generated and linked for systems declaring ICs.
- CoCo1 strict split wiring is stabilized:
  - `pia0_read_reg` callback is wired in both `coco1_default.yaml` and `coco1_interactive.yaml`.
  - SAM IRQ/FIRQ signaling now uses the SAM interrupt bridge callback (`raise_interrupt`) instead of direct inline interrupt calls in IC logic snippets.
  - CoCo split regression coverage was updated to assert bridge-based interrupt routing and callback ownership.
- Representative compile/link checks are green after this migration:
  - `z80_sms_sdl`
  - `z80_amstrad_cpc464_sdl`
  - `mos6502_nes_interactive`
- Remaining migration work:
  - move IC `step_pre/step_post` ownership from generic `*_system_glue.c` runtime block into per-IC units ✅
  - keep non-IC runtime flow (`runtime_pre_step`, picker/runtime policies) in system-owned glue only ✅
  - add/expand tests enforcing per-IC ownership boundaries for lifecycle + step hooks ✅

### CoCo1 Closure (2026-05-19)
- CoCo1 split is considered closed for this phase:
  - ICs are emitted as dedicated units (`coco1_ic_*.c`) with SAM/PIA/VDG/cartridge expansion separated.
  - PIA0 read path wiring (`pia0_read_reg`) remains explicitly connected in both default and interactive profiles.
  - IRQ/FIRQ routing remains bridge-owned at system glue boundary (`component_coco1_sam_6883_callback_raise_interrupt`), with no direct CPU interrupt call from IC-generated C body.
  - CoCo regression tests for split wiring and IRQ routes are green.
  - Scripted generate/build flow for both `default` and `interactive` profiles is green; `default` runner now passes keyboard map explicitly.
