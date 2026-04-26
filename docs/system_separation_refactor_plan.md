# Apple II-Style Functional Separation Refactor Plan

## Goal
Standardize system composition so input/output responsibilities are separated into dedicated components:
- keyboard
- controller/gameport
- video
- speaker

with host-backend abstraction preserved.

## Scope
### Phase 1 (template, highest priority)
- `atari800xl`

### Phase 2
- `atari2600`
- `nes`

### Phase 3
- `coco1`
- `msx1`
- `zx_spectrum48k`
- `cpc464` (pending callback surface)
- `trs80_model4` (pending callback surface)
- `bbcmicro` (deferred per user request)

### Baseline references
- `apple2` (reference architecture)
- `c64` (already split)

## Design
1. Add dedicated adapter devices for keyboard/controller paths where ICs currently call host callbacks directly.
2. Rewire system YAML `connections` so IC callbacks target adapter devices.
3. Connect adapter-device host callbacks to host component callbacks.
4. Keep runtime behavior and schemas unchanged.

## Implementation Status
### Completed in this pass
- Phase 1 (`atari800xl`): wired keyboard + controller adapter devices.
- Phase 2 (`atari2600`, `nes`): wired controller adapter devices.
- Phase 3 subset (`coco1`, `msx1`, `zx_spectrum48k`): wired gameport/controller adapter devices.
- Updated generation scripts to include new `--device` arguments.

### Deferred / pending
- `bbcmicro`: skipped for now (per user request).
- `cpc464`, `trs80_model4`: no explicit controller callback surface in current IC contracts; requires contract extension before adding controller adapter boundary.

## Validation
- YAML parse validation passed for all modified files.
- Codegen smoke tests passed for:
  - `atari800xl_interactive`
  - `atari2600_interactive`
  - `nes_interactive`
  - `coco1_interactive`
  - `msx1_interactive`
  - `zx_spectrum48k_interactive`
