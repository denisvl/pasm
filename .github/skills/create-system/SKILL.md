---
name: create-system
description: Create or extend a PASM machine/system definition in this repository. Use when adding a new emulated system, hardware variant, clone, cartridge profile, default or interactive profile, or the supporting IC/device/host wiring needed to make that system generate, build, and run correctly.
---

# Create System

Use this skill when the task is to add a new machine under `examples/systems/` or to introduce the supporting repo changes required for that machine to work end to end.

This repo does not treat "create a system" as "write one YAML". A complete change usually includes:

- `examples/systems/<system>/...`
- `examples/roms/<system>/...`
- any new `examples/ics/<system>/...`
- any new `examples/devices/<system>/...`
- any new `examples/hosts/<system>/...`
- runner scripts under `scripts/`
- contract or parser tests under `tests/`
- generation, build, and runtime validation

## First Pass

1. Read [docs/new_systems.md](../../../docs/new_systems.md) to identify the intended scope and whether the system is meant to be:
   - a ROM swap or clone
   - a memory-map variant
   - a cartridge or floppy profile
   - a new architecture that needs new ICs/devices/hosts
2. Find the closest existing implementation under `examples/systems/`, `examples/ics/`, `examples/devices/`, `examples/hosts/`, and `scripts/`.
3. Copy the nearest working family rather than starting from a blank file.

Prefer the lowest-diff implementation that matches the hardware. If the target is mostly a clone, reuse existing ICs/devices/hosts and only fork files that genuinely differ.

## Required Repo Conventions

- System manifests live in `examples/systems/<system>/`.
- ROM references inside system YAML must use `../../roms/<system>/...`.
- Keep profile pairs consistent:
  - `<system>_default.yaml`
  - `<system>_interactive.yaml`
- If the family already uses cartridge variants, preserve that shape:
  - `<system>_cartridge_default.yaml`
  - `<system>_cartridge_interactive.yaml`
- `metadata.name` should be stable, explicit, and match local naming style.
- `integrations.profile` should be unique per profile and follow existing naming.
- Do not invent a new directory pattern when an existing family already defines one.

## System Authoring Workflow

### 1. Choose a Base Family

Pick the nearest implemented machine and inspect:

- system YAMLs in `examples/systems/<family>/`
- IC YAMLs in `examples/ics/<family>/`
- devices in `examples/devices/<family>/`
- hosts in `examples/hosts/<family>/`
- runner scripts in `scripts/run_<family>_*.sh` and `.bat`
- contract tests in `tests/test_*_contract.py` or similar

Typical examples:

- ROM swap / cosmetic clone: `apple2` -> `apple2plus`, `coco1` -> `tdp100`
- same platform with one chip difference: `coco1` -> `coco2`
- same core with profile split: `c64` -> `c64c`, `c64gs`, `csx64`
- console variant with extra I/O: `nes` -> `famicom`

### 2. Decide What Must Be New

Only create new files for the parts that differ.

Reuse existing files when:

- the CPU is unchanged
- the memory map is unchanged
- the same IC behavior is still valid
- the same host or device wiring already matches

Create new IC/device/host YAMLs when:

- memory size changes and the IC hardcodes allocation/reset size
- port or callback behavior changes
- the host input or display contract changes
- the machine needs distinct automation metadata or screen plumbing

If a difference is just a ROM path or profile metadata, keep the change in system YAML only.

### 3. Author the System YAMLs

Each system file must be internally complete and should mirror the family style already used in the repo.

Check at minimum:

- `metadata`
- `clock_hz`
- `reset_delay_seconds` when boot timing needs it
- `memory.default_size`
- `memory.regions`
- `memory.rom_images`
- `hooks`
- `components`
- `connections`
- `integrations.profile`
- `automation`
- `audio` and `display` when applicable

When editing `memory.rom_images`:

- keep ROM files under `examples/roms/<system>/`
- use `target_region` names that exist
- use `file_offset` and `load_size` only when partial-file ROM loads are actually required

When editing `components`:

- keep interactive profiles wired to the required devices/hosts
- keep default profiles minimal when the family does that
- preserve component ids used by automation or connections

When editing `automation`:

- prefer structured screen descriptions (`text_views`, `text_grid`, `framebuffer`)
- declare only capabilities the machine actually supports
- keep readiness recipes realistic enough for automation tests and MCP usage

## Runner Script Requirements

If the new system is something a developer will generate/build/run directly, add matching scripts.

Follow the nearest family script and keep these aligned:

- processor path
- system directory
- selected default/interactive manifest
- IC/device/host arguments
- output directory name under `generated/`
- optional keyboard/controller map wiring

Usually this means adding or updating:

- `scripts/run_<system>_debugger.sh`
- `scripts/run_<system>_debugger.bat`
- optionally `run_<system>_interactive.sh`, `run_<system>_default.sh`, or no-TUI helpers if that family already has them

Do not leave scripts pointing at the old family name after cloning.

## Test Requirements

At minimum, update tests when the new system should be part of repo coverage.

Common places:

- `tests/test_parser.py`
  Add new manifest paths to the parser coverage list when the repo is enumerating all example systems.
- `tests/test_system_rom_layout_paths.py`
  No edit is usually needed, but your ROM paths must satisfy it.
- split/contract tests such as `tests/test_<family>_split_contract.py`
  Add a new file when the family has invariants worth locking down.
- smoke or automation tests if the system should participate in those existing matrices

If you introduce a new IC or profile-specific requirement, add a focused test that proves the invariant instead of relying only on manual validation.

## Validation Sequence

Do not stop after writing YAML.

Run, in order where practical:

1. `pasm validate` for the new processor/system/IC/device/host set
2. `pasm generate ... --output generated/<target>`
3. `cmake -S generated/<target> -B generated/<target>/build`
4. `cmake --build generated/<target>/build`
5. repo tests relevant to the change
6. a runtime smoke check using the nearest existing script or debugger flow

Prefer targeted tests first, then broader ones if the change touches shared machinery.

## Automation and Emulator Interaction

When validating a generated interactive machine, prefer the PASM automation MCP path over terminal key injection or sleep loops.

Use this order when available:

1. open generated machine
2. describe machine
3. inspect capabilities
4. read structured screen state
5. inject structured input
6. wait on deterministic conditions

Prefer text-grid/text-view or framebuffer inspection over screenshots.

## Decision Rules

- If the target machine is a clone, start from the clone source with the fewest semantic differences.
- If a repo invariant is already expressed by an existing test, satisfy it rather than bypassing it.
- If generation/build fails because a cloned file still references the old machine, fix the references before deeper debugging.
- If you touch shared codegen or parser logic, expand validation beyond the single new system.
- Keep tool names, file layout, and profile naming stable unless there is a clear repo-wide reason to change them.

## Done Criteria

A new system is not complete until all of these are true:

- manifests exist under `examples/systems/<system>/`
- ROM paths point to `examples/roms/<system>/...`
- any required IC/device/host files exist and are wired correctly
- scripts reference the new system instead of the source template
- relevant tests are added or updated
- validate/generate/build succeeds
- at least one runtime smoke check has been attempted

If one of those is intentionally skipped, state the gap explicitly in the final response.
