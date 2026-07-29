# Emulator Automation Remaining Tasks

This file tracks the remaining implementation work for the emulator automation
plan. It is intended to stay practical and implementation-oriented rather than
repeat the full design document.

Scope note: Phase 8 and the originally deferred Recording and Replay /
Inspection / Debug Operations items are now complete. Do not start Language /
UX Follow-Up or post-plan integration work unless explicitly requested.

## Current Status

- [x] Stable C automation ABI for execution control, input, framebuffer
      capture, text-grid capture, and basic event polling
- [x] Python binding for the current stable ABI
- [x] Rust raw FFI crate and safe wrapper
- [x] Frame-driven waits
- [x] Stable framebuffer/text waits
- [x] Python fluent wait conditions
- [x] Input sequence builders in Python and Rust
- [x] Event polling in C, Python, and Rust
- [x] Event iterator/drain helpers in Python and Rust
- [x] Event callback-style drain helpers in Python and Rust
- [x] Event-based waits for screen/text change in Python and Rust
- [x] Rust dynamic shared-library loader on Unix and Windows backends

## Phase 5: Input Sequences and Timing

- [x] Add authentic logical `type_text(...)` using per-machine character maps
      Python and Rust expose logical `type_text(...)`, backed by machine
      character-map metadata through the stable C ABI, and the generated-runtime
      contract now validates loading a real keyboard map in a minimal harness
      without depending on backend-specific scancode translation.
- [x] Extend the C ABI with machine character-map metadata
- [x] Add configurable key-down / inter-key timing presets
- [x] Add release-all helpers for keyboard/controller input
- [x] Record accepted/applied input timestamps in the event model or replay log
- [x] Add replayable input logs
      Python and Rust `InputSequence` types now store structured steps and can
      round-trip replay logs through a shared JSON Lines step format.
- [x] Add deterministic replay validation tests
      Python and Rust both validate that replaying the same JSON Lines input
      log on fresh mock machines yields the same input event schedule.

## Phase 6: Wait Engine and Synchronization

- [x] Wait for text
- [x] Wait for stable screen content
- [x] Wait for event type
- [x] Compose conditions in Python
- [x] Add richer timeout diagnostics with final snapshots/events
- [x] Add wait for media activity
- [x] Add wait for text disappearance
- [x] Add wait for memory value
- [x] Add wait for program counter
      Python now exposes `read_program_counter()`, `wait_for_program_counter(...)`,
      and condition-builder equivalents over a narrow core/adapter program-counter
      capability without opening full register inspection.
- [x] Add wait for breakpoint/watchpoint
      Python now exposes breakpoint/watchpoint waits over execution-state timing
      metadata, with optional PC filtering. In the current automation model
      these waits target debug-induced pauses rather than a richer stop-cause
      taxonomy.
- [x] Add high-level emulated-duration / cycle-based timeout APIs
      Python wait conditions and direct memory/PC waits now accept frame, cycle,
      or emulated-time budgets via a shared execution-timing read surface in the
      core automation ABI and generated debug-ABI adapter.
- [x] Add a Rust condition-composition layer roughly matching Python

## Phase 7: Event System

- [x] Minimal event envelope
- [x] Event polling API
- [x] Python event wrapper
- [x] Rust event wrapper
- [x] Frame-completed events in the tested mock path
- [x] Reset events in the tested mock path
- [x] Execution-state change events in the tested mock path
- [x] Input-submitted events in the tested mock path
- [x] Screen-changed events in the tested mock path
- [x] Text-changed events in the tested mock path
- [x] Python iterator and async iterator wrappers
- [x] Rust iterator/receiver-style wrappers
- [x] Add a core-level callback-style dispatch helper
- [x] Add a true subscription API at the C/core layer
- [x] Define callback lifetime/threading rules
- [x] Add filtering/subscription by event type at the core level
- [x] Add richer event payloads where needed
      Event envelopes now carry explicit execution-state transitions for
      `EXECUTION_STATE_CHANGED`, machine-reset state context, `region_id`,
      changed bounds/count, and typed text deltas for `TEXT_CHANGED`.
- [x] Add text/tile delta payloads instead of only coarse event kinds
- [x] Add media/debug/error event categories
- [x] Thread the event model through at least one real non-mock adapter path

## Phase 8: JSON Lines Protocol and Terminal Client

- [x] Define JSON Lines command schema
- [x] Define JSON Lines event schema
- [x] Add transport-neutral serializer/deserializer layer
- [x] Add a terminal observation/control client
- [x] Add terminal rendering for text-grid and framebuffer-derived views
- [x] Add event watch tooling in the terminal client

## Recording and Replay

- [x] Define recording file format
      Python now has a structured JSON Lines session-recording format with a
      recording header, replayable input steps, and captured automation events.
- [x] Record input sequences and event stream
      `Machine.record(...)` captures the submitted input sequence plus the
      drained event stream into a `SessionRecording`.
- [x] Replay recordings deterministically
      Python can replay a `SessionRecording` against a fresh machine and verify
      the resulting event stream.
- [x] Add replay-diff diagnostics
      Replay verification now raises `ReplayMismatchError` with the first
      differing event index and expected/actual payloads.

## Inspection / Debug Operations

- [x] Read memory
- [x] Write memory
      Stable C/Python/Rust automation surfaces now expose memory writes through
      the generated debug-ABI bridge and focused mock-backed coverage.
- [x] Read registers
      Stable C/Python/Rust automation surfaces now expose generic register-row
      snapshots backed by the generated debug snapshot ABI.
- [x] Write registers where allowed
      Stable C/Python/Rust automation surfaces now expose generic name-based
      register writes. Current focused coverage exercises `PC` writes through
      the mock path.
- [x] Query current PC / instruction
      Current PC is exposed through the stable automation surface. Instruction
      summaries are now exposed through the stable automation surface via the
      generated disassembly-row bridge.
- [x] Breakpoint / watchpoint capability surface
      The automation ABI now exposes explicit breakpoint capability bits and
      breakpoint set/clear control. Watchpoints remain capability-negative until
      there is real backend support behind them.
- [x] Capability-driven inspection mode separation
      Python now exposes separate `machine.inspect` and `machine.debug` views
      over the underlying machine capabilities.

## Language / UX Follow-Up

### Python

- [ ] Expand the pytest plugin with per-system fixtures
- [ ] Add screenshot-on-failure support
- [ ] Add richer diagnostics for failed waits/assertions
- [ ] Add end-to-end examples against a real adapter

### Rust

- [ ] Add serde support where appropriate
- [ ] Add more ergonomic condition composition
- [ ] Add examples against a real adapter

### Cross-Platform

- [ ] Validate the Rust Windows loader on an actual Windows runtime
- [ ] Add Windows CI coverage for the Rust workspace

## MCP Integration for Coding Agents

- [ ] Add an MCP server crate/package over the existing automation core
- [ ] Expose machine lifecycle and capability discovery MCP tools
- [ ] Expose execution control and input injection MCP tools
- [ ] Expose structured observation tools for framebuffer/text-grid capture
- [ ] Expose wait-condition MCP tools over the existing synchronization layer
- [ ] Expose event polling/subscription MCP tools
- [ ] Expose recording/replay MCP tools
- [ ] Expose inspection/debug MCP tools with capability gating
- [ ] Keep responses structured and avoid free-form command expressions
- [ ] Validate the MCP server on Unix and Windows hosts

## Immediate Next Candidates

- [x] Thread event polling through one real adapter path
- [x] Add core-level callback/subscription API
- [x] Add machine character-map support for authentic `type_text(...)`
- [x] Add memory/PC wait conditions
- [ ] Add coding-agent-facing MCP integration over the automation surface
