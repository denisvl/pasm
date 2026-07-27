# Emulator Automation Phase 0 Inventory

This note records the initial implementation inventory for
`docs/emulator_automation_implementation_plan.md`.

## Existing Integration Points

- Emulator lifecycle is already exposed through the generated debugger ABI:
  `pasm_dbg_create`, `pasm_dbg_destroy`, `pasm_dbg_reset`, and loader helpers for
  system ROMs, cartridges, floppy media, keyboard maps, and controller maps.
- Execution control exists through `pasm_dbg_run`, `pasm_dbg_run_slice`,
  `pasm_dbg_run_for_cycles`, `pasm_dbg_pause`, stepping functions, and
  `pasm_dbg_jump_frame`.
- Debug observation exists through `pasm_dbg_snapshot_counts` and
  `pasm_dbg_snapshot_fill`. The snapshot already carries target name, status,
  selected thread, clock, PC, SP, cycle counters, and frame index.
- Memory inspection exists through `pasm_dbg_read_memory`.
- Host keyboard and controller mapping infrastructure exists in generated
  runtime glue and host HAL YAML. Current input is primarily host-state driven,
  so automation input should enter near the runtime keyboard/controller map
  boundary instead of directly mutating device internals.
- Framebuffer generation exists in video callbacks passed to host HAL
  `video_frame` handlers. Initial framebuffer automation should preserve the
  latest canonical frame before or alongside host rendering.

## Pilot Recommendation

Use the Apple II interactive generated system as the first adapter target. It
has exercised debugger and interactive scripts, keyboard input, framebuffer
rendering, and a comparatively simple initial input surface.

The first adapter should start at maturity Level 1:

- machine descriptor and capability discovery
- pause, resume, reset
- run for frames using the existing frame counter
- framebuffer snapshot from the latest video callback
- keyboard key down/up through the declared keyboard map path
- controller button down/up where a controller map is present

## Gaps

- No stable automation ABI existed before this change.
- No generic adapter handle existed outside the debugger-specific ABI.
- Frame stepping is not yet a canonical safe-point service; the current bridge
  can jump or run slices/cycles, but per-frame execution needs adapter-specific
  mapping.
- Framebuffer storage is not yet standardized in generated systems.
- Input injection needs a machine-facing queue/state layer so automation does
  not depend on actual host keyboard state.
- Event publishing is not yet represented outside debugger polling.
- Text-mode metadata should use generic address-layout primitives such as
  `linear` and `bit_interleaved_rows`; avoid machine-named layouts and
  free-form address expressions.
- Text-grid clients should enumerate views before capture using the C ABI
  descriptor functions, then pass the selected `region_id` to the capture API.
