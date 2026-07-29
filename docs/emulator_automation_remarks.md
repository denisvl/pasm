# Emulator Automation Remarks

See also: [emulator_automation_tasks.md](/home/dvlop/projects/pasm/docs/emulator_automation_tasks.md)

## Python Layer Status

- The Python package now covers the current stable C ABI for execution control,
  keyboard/controller input, framebuffer snapshots, text views, and text-grid
  snapshots.
- The higher-level Python API shape now matches the implementation plan:
  `machine.keyboard.tap(...)`, `machine.run.frames(...)`, and
  `machine.screen.framebuffer()/text()/wait_for_text(...)`.
- Python now also has a first fluent wait layer:
  `machine.conditions...` plus `machine.wait.any(...)`,
  `machine.wait.all(...)`, and `machine.wait.screen_contains(...)`.
- Python now also wraps the first event polling hook with `machine.poll_event(...)`.
- Python now also exposes an event-drain helper with `machine.events(...)`.
- Python now also exposes named event constants via `EventType` and a direct
  `machine.wait.screen_changed(...)` helper.
- Python now also exposes direct text-change waits via
  `machine.screen.wait_for_text_changed(...)` and `machine.wait.text_changed(...)`.
- Python event iterators now also support callback-style draining via
  `dispatch_available(...)`.
- Python now also exposes an `AsyncEventIterator` over the same poll-based
  event cursor, with deterministic frame advancement while awaiting events.
- Python now also wraps a core-level callback-style event dispatch helper.
- Python now also wraps explicit subscription handles with manual dispatch and
  cursor control via `machine.subscribe(...)`.
- Snapshot lifetimes are handled conservatively by copying C-owned data into
  Python-owned dataclasses before release.

## Python Layer Gaps

- The pytest plugin is intentionally minimal. It loads a shared library and
  creates a machine, but it does not yet provide per-system fixtures,
  screenshots-on-failure, or richer diagnostics.
- Framebuffer PNG export currently supports `RGBA8888`, `BGRA8888`, and
  `RGB565`. Other pixel formats from the ABI remain unsupported in the Python
  helper.
- The wait helpers are frame-driven and deterministic, but still narrow:
  generic predicates, composable Python conditions, text waits, stable
  text/framebuffer waits, and first event waits exist.
- The C core now exposes a minimal event envelope plus polling hook, and both
  Python and Rust wrap it. The tested path today is deterministic
  reset/state/frame/input polling; richer event categories and subscription
  models are still pending.
- The mock-backed event path now also covers `SCREEN_CHANGED`, and both
  bindings expose a first `wait_for_event(...)` helper on top of deterministic
  polling.
- The event path now also covers `TEXT_CHANGED`, with direct text-change wait
  helpers in Python and Rust.
- The generated debug-ABI automation adapter now emits real
  `MACHINE_RESET`, `EXECUTION_STATE_CHANGED`, `FRAME_COMPLETED`,
  `TEXT_CHANGED`, and `SCREEN_CHANGED` events, with a compiled generator
  contract test covering the default text-view path.
- The C core now also exposes filtered event dispatch by event type, and both
  Python and Rust have targeted coverage over that filtered drain path.
- The C core now also exposes explicit subscription handles with manual
  dispatch and cursor ownership. The current contract is now explicit:
  callbacks run synchronously on the dispatching thread, the core does not
  create background pumps, recursive dispatch of the same subscription is
  invalid, and cross-thread sharing remains unsupported unless the embedding
  layer serializes access itself.
- The event envelope now also carries `region_id`, so `TEXT_CHANGED` and
  `SCREEN_CHANGED` can identify the affected text/view region in both the
  mock paths and the generated debug-ABI adapter path.

## Rust Direction

- Start with a hand-maintained raw FFI crate over the stable C ABI instead of
  introducing `bindgen` immediately.
- Keep the first safe Rust wrapper small and explicit: machine ownership,
  execution control, framebuffer/text-grid capture, and result mapping.
- Defer event APIs, serde support, and sequence builders until the C ABI grows
  to support them cleanly.

## Rust Layer Status

- The Rust workspace now contains both a raw FFI crate and a safe wrapper
  crate.
- The safe wrapper now covers ownership, describe/capabilities, execution
  control, keyboard/controller input, framebuffer capture, text-view
  enumeration, text-grid capture, deterministic frame-driven text waits, and
  stable text/framebuffer waits.
- Rust now also wraps the first event polling hook and treats
  `EMU_AUTOMATION_TIMEOUT` as "no new event yet" for polling semantics.
- Rust now also exposes a small `EventPoller` helper for draining all currently
  available events while tracking the sequence cursor.
- Rust `EventPoller` now also supports callback-style draining via
  `dispatch_available(...)`.
- Rust `EventPoller` now also supports filtered callback-style draining via
  `dispatch_matching(...)`.
- Rust now also exposes an `EventReceiver` wrapper for receiver-style polling
  with deterministic frame advancement.
- The C core now also exposes a callback-style `dispatch available events`
  helper built on the event polling ABI.
- Rust now also exposes explicit subscription handles with manual dispatch and
  cursor control via `screen().subscribe(...)`.
- Python and Rust now both expose explicit input-sequence builders over the
  existing per-event ABI, including frame/cycle timing metadata and frame
  wait steps.
- Rust has a real ABI-backed smoke test that links against the C automation
  core and a mock adapter, so the wrapper is tested across an actual FFI
  boundary.
- The Rust shared-library loader now has both Unix and Windows backends.
  Only the Unix path is exercised locally today; the Windows implementation is
  kept in the same explicit symbol-loading style so it remains portable across
  host environments without introducing free-form platform expressions.
