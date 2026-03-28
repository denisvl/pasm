# Host HAL Migration Plan

Last updated on: March 28, 2026

## Current Status Snapshot

- Phase 1 (compatibility): largely implemented.
- Phase 2 (backend abstraction): implemented for supported targets (`sdl2`, `glfw`, `stub`).
- Phase 3 (legacy removal): completed in schema/parser/docs.

## Goals

- Define a backend-agnostic Host HAL contract so host YAML does not encode SDL-specific APIs.
- Keep SDL as the default backend implementation while enabling future backends.
- Support a safe migration path from legacy SDL-keyboard mappings to canonical `host_key` mappings.

## Non-Goals

- Runtime plugin loading of host backends in this phase.
- Full documentation sweep outside core spec/planning docs.

## Rollout Phases (Dual Path)

1. Phase 1: Compatibility layer
- Keep existing SDL behavior operational.
- Accept canonical `host_key` mappings.

2. Phase 2: Backend abstraction completion
- Move host input/presentation/audio/timing calls behind backend-neutral interfaces.
- Keep compile-time backend selection (SDL as default target).

3. Phase 3: Legacy removal
- Remove legacy SDL-only keyboard mapping syntax from parser/schema/docs.
- Keep canonical host key mapping as the only supported YAML contract.

## Task Checklist

### Schema
- [x] Extend host input schema to support canonical `host_key` model.
- [x] Mark SDL-specific source/key patterns as deprecated during transition.
- [x] Add host backend target metadata (`backend.target`) for compile-time backend selection.
- [x] Remove legacy SDL-only constraints in Phase 3.

### Parser
- [x] Add canonical host key validation.
- [x] Remove legacy SDL keyboard syntax acceptance (`sdl_scancode` / `SDL_SCANCODE_*`).
- [x] Keep duplicate binding and bit/row range validation behavior.
- [x] Normalize/validate host backend target (`backend.target`, explicit and required).
- [x] Enforce a single host backend target per composed build (mixed backend targets rejected).
  - Parser now requires explicit `backend.target` (no model-name inference fallback).
  - Host keyboard validation now uses a backend-neutral canonical key allowlist (`host_key`) directly, without SDL-prefixed compatibility-key conversion during validation.

### Codegen
- [x] Route host keyboard input through backend-neutral key handling.
- [x] Stop emitting backend-specific key assumptions in generated logic.
  - Declarative keyboard bindings now store canonical host keys in generated tables.
  - Generated key lookup now uses backend-neutral scancode aliases (`CPU_HOST_SCANCODE(...)`) instead of direct `SDL_SCANCODE_*` literals at call sites.
  - SDL scancode usage is isolated to backend-specific compatibility definitions during migration.
  - `CPU_HOST_KEYCODE_*` compatibility aliases now derive from `cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(...))` instead of backend-specific keycode literals, reducing backend-keycode assumptions.
  - Generated key-resolution helper is unified at call site and guarded by backend capability (`CPU_HOST_HAS_SCANCODE_MAP`) instead of split backend-specific helper names.
  - CPU codegen host-keyboard ingestion now fails fast on invalid host input contracts (non-`host_key` source, non-canonical keys, malformed press rows/bits) instead of silently dropping invalid bindings.
  - CPU generation now enforces a strict single supported backend target set (`sdl2`/`stub`/`glfw`) and rejects mixed or unsupported backend targets.
  - CPU generation no longer infers backend target from host model naming; `backend.target` is the source of truth.
  - Added regression coverage to keep in-repo SDL2 host YAML snippets free of direct `SDL_*` symbol usage.

### Build
- [x] Keep compile-time backend selection model.
- [x] Move SDL linking decisions behind backend-target configuration.
  - Backend-target-driven SDL setup/linking is implemented for `backend.target: sdl2` (auto-setup no longer inferred from `linked_libraries` names alone).
  - Build generation now enforces a strict single backend target matrix (`sdl2`/`stub`/`glfw`) and rejects mixed or unsupported backend target sets.
  - `glfw` now has backend-target-driven build setup/link handling (`find_package(glfw3 ...)` and auto link target fallback) without SDL auto-setup/linking.
  - CPU code generation now auto-includes SDL headers for `backend.target: sdl2`, so in-repo SDL2 host YAML snippets no longer need explicit `SDL2/SDL.h` coding headers.
  - In-repo SDL2 host YAML snippets now rely on backend-target-driven link setup (no explicit `linked_libraries: SDL2` entries required).
  - Scope for this phase is complete for the currently supported targets (`sdl2`, `stub`, `glfw`).
- [x] Migrate in-repo host YAML files to explicit `backend.target` metadata (`sdl2`/`stub`).

### Runtime
- [x] Define Host HAL calls for events, frame present, audio output, timing, and focus hooks.
  - Implemented generated Host HAL helpers for event pump, tick time, focus query, keyboard state/env/text-input/window raise, render present/clear/copy/texture update/output-size, audio queue/clear/query, common lifecycle teardown calls, and init/create/open/pause/alloc primitives.
  - Added HAL wrappers for scancode-to-keycode conversion and texture blend-mode setup, and migrated in-repo host call sites to those wrappers.
  - Added HAL event accessor helpers (type/scancode/repeat), and migrated in-repo host call sites to avoid direct event struct field reads.
  - Added HAL wrappers/macros for host logging + last-error lookup, audio dequeue, subsystem init, window-size query, scancode/key-name lookup, and key-modifier state; migrated in-repo host snippets away from direct SDL calls for these surfaces.
  - Replaced direct `SDLK_*` / `KMOD_*` usage in in-repo host snippets with backend-neutral aliases (`CPU_HOST_KEYCODE_*`, `CPU_HOST_MOD_*`) plus HAL event-mod accessors.
  - In-repo SDL2 host snippets now use HAL aliases/wrappers for both SDL pointer types and SDL constants (including scancode constants).
  - GLFW now has generated runtime helper hooks for core lifecycle/event/timing/focus entry points.
  - GLFW helper path now emits a backend-neutral quit event when `glfwWindowShouldClose(...)` is observed.
  - GLFW helper path now provides real window-size query via `glfwGetWindowSize(...)` (instead of always returning failure).
  - GLFW helper path now provides backend-neutral scancode mapping/key-state polling and emits key up/down events via transition detection in the HAL poll loop.
  - GLFW helper path now provides backend-neutral modifier-state reporting (`CTRL`/`SHIFT`/`LCTRL`) for both event and polled mod-state APIs.
  - GLFW scancode map coverage now includes additional in-repo host binding keys (for example `APPLICATION`, `NONUS*`, `F1..F8`, `CAPSLOCK`, `PAGEUP`, `RETURN2`).
  - GLFW helper path now provides meaningful backend-neutral key/scancode name strings (with `UNKNOWN` fallback) instead of empty-string stubs.
  - GLFW keycode semantics now align with key-from-scancode output (`CPU_HOST_KEYCODE_*` map to GLFW keycodes), fixing non-SDL quote/semicolon layout checks.
  - GLFW key/scancode conversion-name helpers now also guard init/events subsystem state and return neutral defaults (`0`/`"UNKNOWN"`) when unavailable.
  - GLFW helper path now emits synthetic key repeat events (`key.repeat = 1`) for held keys via deterministic repeat cadence in the poll loop.
  - GLFW event modifier state is now carried per-event in generated event payloads (not only via transient global cache).
  - GLFW helper path now provides an internal backend-neutral audio byte queue for `audio_open`/`queue`/`queued_bytes`/`clear`/`dequeue`/`close` so host audio flow is no longer hard no-op on non-SDL builds.
  - GLFW helper path now provides internal renderer/texture backing stores so `update_texture`/`render_clear`/`render_copy` are functional memory operations instead of pure stubs.
  - GLFW helper lifecycle now tracks init state and validates allowed init/subsystem flags consistently, with guarded terminate behavior.
  - GLFW create/open helpers now consistently gate on init state (window, renderer, texture, audio open), matching backend lifecycle expectations.
  - GLFW quit path now clears cached window/input state pointers and key caches to avoid stale-state reuse after terminate.
  - GLFW event/timing/input helpers now short-circuit safely when HAL is not initialized (pump/poll/ticks/focus/keyboard/focus-window operations).
  - GLFW render helpers now also guard on init state (`render_present`, size queries, texture/update/copy/clear/draw-color paths) for safe post-quit behavior.
  - GLFW audio queue helpers now also guard on init state (`queue`/`queued_bytes`/`clear`/`dequeue`/`close`) for safe lifecycle boundaries.
  - GLFW lifecycle reset logic is now consolidated via internal reset helpers for audio/input state, reducing duplicated teardown code paths.
  - GLFW quit/quit-subsystem paths now destroy the tracked primary window before state reset/terminate, preventing window-resource leakage across lifecycle restarts.
  - GLFW window creation now applies safe defaults (`"PASM"`, `640x480`) when callers pass empty titles or non-positive dimensions.
  - GLFW window creation now honors `CPU_HOST_WINDOW_RESIZABLE` through backend-neutral window flags instead of ignoring the host flag set.
  - GLFW window creation now validates backend-neutral window flags and rejects unsupported bits instead of silently ignoring them.
  - GLFW window-bound helpers (`set_window_title`, `raise/show/focus`, `get_window_size`) now fallback to the tracked primary window when `NULL` is passed, improving HAL call robustness.
  - GLFW renderer creation now also supports `NULL` window arguments by falling back to the tracked primary window (consistent with other window-bound HAL helpers).
  - GLFW renderer creation now validates backend-neutral renderer flags and rejects unsupported bits instead of silently ignoring them.
  - GLFW renderer creation now fails fast (free + `NULL`) when initial renderer size sync fails, avoiding half-initialized renderer objects.
  - GLFW texture/renderer allocation sizing now uses explicit checked multiply guards (`w64/h64` + overflow division checks) before `w*h*4` byte computation.
  - GLFW texture creation now validates backend-neutral texture contract inputs (`CPU_HOST_PIXELFORMAT_ARGB8888`, `CPU_HOST_TEXTUREACCESS_STREAMING`) instead of silently accepting unsupported formats/access modes.
  - GLFW texture allocation now validates computed buffer size against overflow/zero-byte edge cases before allocation.
  - GLFW audio-open path now enforces a non-empty desired audio spec (`want` present with valid `freq/channels/samples`) instead of accepting invalid/no-spec opens.
  - GLFW audio-open size derivation now guards `samples * channels * bytes_per_sample` overflow before committing `have->size`.
  - GLFW audio-open now resets prior internal queue state on reopen for deterministic lifecycle behavior.
  - GLFW audio-queue growth now guards queue-size/capacity arithmetic against overflow (`need64` + `SIZE_MAX` checks) before realloc/memcpy.
  - GLFW tick-time helper now guards non-finite/non-positive clock outputs before ms conversion, avoiding invalid casts from backend time state.
  - GLFW event accessor helpers now type-check for key events before reading key payload fields, avoiding unsafe union reads for non-key events (for example `QUIT`).
  - GLFW modifier-state helper now checks backend init state before issuing key queries, preventing stale-window key polling after teardown.
  - GLFW renderer backbuffer resize path now guards `w * h * 4` allocation arithmetic against overflow before realloc.
  - GLFW render-copy now re-clamps source region bounds after destination-origin clipping shifts (`dx/dy < 0`) to prevent out-of-range source reads.
  - GLFW render clear/copy now explicitly require non-null renderer frame storage after sync, preventing accidental writes through null frame buffers.
  - GLFW render clear/copy now validate framebuffer length consistency against `w*h*4` before pixel writes/copies.
  - GLFW render clear now fills exactly the logical framebuffer area (`w*h`) rather than any stale oversized allocation tail.
  - GLFW texture/upload and render-copy bound clipping now use 64-bit sum checks for rectangle arithmetic (`x+w`, `sx+sw`, `dx+cw`) to avoid signed-overflow edge cases.
  - GLFW texture upload/copy now validate positive texture/renderer dimensions before memory operations, tightening behavior under corrupted state.
  - GLFW key-state polling and modifier detection now treat `GLFW_REPEAT` as pressed, aligning hold behavior across event/polled input paths.
  - GLFW window-size query helpers now validate returned dimensions (`> 0`) before reporting success.
  - GLFW window-size query helpers now proactively zero output dimensions on entry, avoiding stale caller-visible values on error paths.
  - GLFW texture upload now validates full source/destination span bounds (row stride + start offset coverage) before row memcpy loops.
  - GLFW render-copy now validates full source/destination span bounds for blit rows before memcpy loops, mirroring upload-side safety checks.
  - GLFW texture objects now track allocated pixel-byte length and validate `w*h*4 <= pixels_len` before upload/copy memory access.
  - GLFW render-copy now rejects invalid destination rectangles (`dst_rect.w/h <= 0`) instead of silently entering clipped no-op paths.
  - GLFW audio queue/dequeue now validate internal queue invariants (`len <= cap` and non-null buffer when `len > 0`) before memory operations.
  - GLFW queued-bytes/clear helpers now apply the same queue invariants (`len <= cap`, non-null buffer for non-empty queue) before reporting or mutating state.
  - GLFW audio helpers now also reject non-empty-capacity states with null queue buffer (`cap > 0 && buf == NULL`) across queue/dequeue/query/clear paths.
  - GLFW renderer resize path now zero-initializes the synchronized frame buffer for deterministic first-frame behavior after size changes.
  - GLFW texture blend helper now enforces init-state gating before accepting texture operations, aligning with other render-path lifecycle checks.
  - Stub backend memory helpers now use libc (`malloc`/`free`/`memset`) instead of forced null/no-op behavior, reducing backend-specific brittleness in headless flows.
  - Stub backend input-name helpers now return explicit neutral defaults (`keyboard_state` non-null empty buffer, key/scancode names as `"UNKNOWN"`), improving backend-neutral call safety.
  - Stub size-query helpers now proactively zero output dimensions before returning failure (`renderer_output_size`/`get_window_size`), preventing stale caller-visible values.
  - Stub backend now emits a stateful in-memory HAL path in one pass: init/subsystem flag validation, lifecycle state tracking, minimal window/renderer/texture objects, and functional host-audio queue/open/dequeue behavior (still backend-neutral/no real I/O).
  - Stub window-bound helpers now support tracked primary-window fallback (`NULL` window arguments), and stub destroy/quit paths now apply lifecycle/video guards with primary-window cleanup to align teardown semantics with SDL/GLFW.
  - Stub audio queue/dequeue/query/clear helpers now validate internal queue invariants (`len <= cap`, non-null buffer for non-empty/non-zero-capacity states), aligning defensive behavior with GLFW.
  - GLFW and Stub now both track enabled host subsystems (`VIDEO`/`AUDIO`/`EVENTS`) and gate helper behavior accordingly, tightening cross-backend lifecycle consistency.
  - SDL helper path now also tracks enabled host subsystems and gates video/audio/events helper entry points, aligning lifecycle semantics with GLFW/Stub.
  - SDL event accessor helpers now type-check key-event kinds before reading key payload fields, and SDL size-query helpers now zero outputs on entry for safer failure behavior.
  - SDL input-name helpers now normalize empty backend names to `"UNKNOWN"`, and SDL keyboard-state helper now avoids a hard `key_count`-nonnull requirement for backend-neutral usage.
  - SDL keyboard-state helper now returns a stable empty-state buffer (with `key_count=0`) when input state is unavailable, avoiding null-state handling divergence vs GLFW/Stub.
  - SDL key/scancode conversion/name helpers now also guard init/events subsystem state and return neutral defaults (`0`/`"UNKNOWN"`) when unavailable.
  - SDL window/renderer size helpers now also reject non-positive dimensions after backend calls, matching GLFW/Stub defensive size semantics.
  - SDL create-window/renderer helpers now enforce HAL-safe defaults and flag validation (`"PASM"`, `640x480`, supported flag masks), aligning creation semantics with GLFW/Stub paths.
  - SDL now tracks a primary window pointer for null-window fallback in window-bound helpers (focus/title/raise/show/size, renderer-create) and clears it during lifecycle teardown.
  - SDL destroy helpers now also honor init/video-subsystem lifecycle gating, avoiding backend calls after teardown and aligning behavior with GLFW/Stub guard patterns.
  - SDL audio-open now enforces desired-spec validation (`want` present with valid `freq/channels/samples`) and rejects capture-open requests in this HAL path, matching current GLFW/Stub audio-contract assumptions.
  - Runtime lifecycle semantics are now aligned across supported backends (`sdl2`, `glfw`, `stub`) with subsystem-gated helper behavior and neutral fallback returns.
- [x] Implement SDL adapter against the HAL contract.
  - SDL-backed implementations are generated for the HAL helper surface.
  - In-repo SDL2 host snippets are wrapper/alias-based with regression coverage enforcing no direct `SDL_*`/`SDLK_*`/`KMOD_*` usage in host YAML behavior snippets.

### Docs
- [x] Add this migration tracker.
- [x] Update `docs/ISA_FORMAT.md` host input contract to canonical model + compatibility note.
- [x] Add host backend model note in `docs/PLAN.md`.
- [x] Document backend-target-driven host include/link behavior in `docs/ISA_FORMAT.md` (`sdl2`/`glfw` auto setup; backend libs not required in host `coding` entries).

## Migration Status Table

| Legacy YAML field/value | Canonical model | Migration status |
|---|---|---|
| `input.keyboard.source: sdl_scancode` | No backend-specific source required in host YAML | Removed from schema/parser acceptance |
| `bindings[].host_key: SDL_SCANCODE_*` | `bindings[].host_key: <canonical host key>` | Removed from schema/parser acceptance |
| SDL-only key allowlist semantics | Backend-neutral host key validation | Implemented for supported targets |

## Exit Criteria For Removing Legacy SDL Input

- Canonical host key schema/parser/codegen path is complete and tested.
- [x] All in-repo host YAML files migrated to canonical `host_key` (with regression coverage).
- [x] CI/docs no longer reference SDL-specific host keyboard source requirements as accepted contract.

## Example Migration

Before (legacy SDL-specific mapping):

```yaml
input:
  keyboard:
    source: sdl_scancode
    bindings:
      - host_key: SDL_SCANCODE_BACKSPACE
        presses:
          - { row: 0, bit: 0 }
```

After (canonical backend-agnostic mapping):

```yaml
input:
  keyboard:
    focus_required: true
    bindings:
      - host_key: BACKSPACE
        presses:
          - { row: 0, bit: 0 }
```
