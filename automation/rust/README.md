# Rust Automation Crates

This workspace contains the initial Rust bindings for the PASM emulator
automation ABI.

## Crates

- `emu-automation-sys`: raw `extern "C"` bindings to the stable C ABI.
- `emu-automation`: safe ownership and snapshot wrappers over the raw ABI.

## Current Safe API Surface

- machine ownership through `Machine::from_raw_owned`
- describe/capabilities
- pause/resume/reset
- frame stepping and frame runs
- keyboard and controller input
- framebuffer capture
- text-view enumeration
- text-grid capture
- frame-driven waits

The ergonomic entry points mirror the Python layer:

```rust
machine.keyboard().tap("RETURN", None)?;
machine.run().frames(10)?;
let frame = machine.screen().framebuffer()?;
let text = machine.screen().text(Some("main"))?;
let ready = machine.screen().wait_for_text("READY", Some("main"), 120, 1)?;
```

Condition composition also supports multi-condition grouping:

```rust
let ready_or_prompt = emu_automation::Condition::any(vec![
    machine.conditions().screen_contains("READY", Some("main")),
    machine.conditions().screen_contains("OK", Some("main")),
]);
let result = machine.wait().until(ready_or_prompt, 180, 1)?;
```

Wait helpers return `WaitError`, which distinguishes timeout from an
underlying automation call failure.

Stable waits are also available:

```rust
let stable_text = machine
    .screen()
    .wait_for_stable_text(Some("main"), 4, 120, 1)?;
let stable_framebuffer = machine
    .screen()
    .wait_for_stable_framebuffer(2, 30, 1)?;
```

These waits compare visible content and ignore per-capture frame metadata.

## Event Polling

```rust
machine.run().frames(2)?;

if let Some(event) = machine.screen().poll_event(0)? {
    assert_eq!(event.sequence_number, 1);
}
```

Polling returns `Ok(None)` when no event newer than `after_sequence` is
available. The current event surface is still intentionally narrow, but the
tested polling path now covers machine reset, execution-state changed, frame
completed, input-submitted, text-changed, and screen-changed events.

For ergonomic draining, use the poll iterator:

```rust
let mut events = machine.screen().events(0);
let available = events.collect_available()?;
for event in available {
    println!("{}", event.sequence_number);
}

let count = events.dispatch_available(|event| {
    println!("{:?}", event.event_type);
})?;
```

For receiver-style consumption with deterministic frame advancement:

```rust
let mut receiver = machine.screen().events(0).into_receiver(1);
let event = receiver.recv(120)?;
```

The stable C ABI now also exposes a callback-style `dispatch available events`
helper, which the Python binding uses directly. The Rust safe wrapper still
leans on the explicit poller/receiver layer.

Manual subscriptions are also available:

```rust
let mut sub = machine.screen().subscribe(
    sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
    0,
    |event| println!("{}", event.sequence_number),
)?;
let count = sub.dispatch_available(0)?;
assert!(count > 0);
```

Current callback/subscription contract:

- callbacks run synchronously on the thread that calls the dispatch function
- the core does not start background threads or event pumps
- recursively dispatching the same subscription from inside its callback is invalid
- shared cross-thread access to the same machine or subscription handle is unsupported unless the embedding layer serializes it externally

You can also wait directly on an event type:

```rust
let event = machine.screen().wait_for_event(
    sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_SCREEN_CHANGED,
    0,
    120,
    1,
)?;
let text_event = machine.screen().wait_for_text_changed(0, 120, 1)?;
```

## Timed Input Sequences

```rust
use emu_automation::{InputSequence, Timing};

let mut sequence = InputSequence::new();
sequence
    .key_down("RETURN", None, Timing::Immediate)
    .wait_frames(2)
    .key_up("RETURN", None, Timing::DelayFrames(1))
    .controller_down("fire_1", Some("joystick_port_1"), Timing::Frame(120));
sequence.play(&machine)?;

let jsonl = sequence.to_jsonl();
let replayed = InputSequence::from_jsonl(&jsonl)?;
replayed.play(&machine)?;
```

## Real Adapter Example

The crate now includes a real-adapter example:

```bash
cargo run -p emu-automation --example real_adapter_text_wait -- /path/to/built/emulator
```

The example opens a built automation-enabled emulator artifact, prints machine
metadata, and waits for text on the first exposed text-grid region.

## Optional Serde Support

Enable serde derives on the public value/snapshot types with:

```toml
emu-automation = { path = "automation/rust/emu-automation", features = ["serde"] }
```

## Current Limitations

- Dynamic shared-library loading is implemented for Unix and Windows.
  The Unix loader is exercised by the current test suite in this repository;
  the Windows path is compiled behind `cfg(windows)` but not executed in this
  Linux environment.
- Logical text typing is available when the loaded adapter exposes per-machine
  character map metadata with modifier key ids. Coverage is still strongest on
  the mock path and ASCII-like native keycode mappings.
- No event subscription model yet.
- Event subscriptions now exist as manual-dispatch handles. They do not start
  threads or background pumps, and the current wrapper does not promise any
  cross-thread callback behavior.
- Event polling is currently limited to the small envelope exercised by the
  reset/state/frame/input/text/screen mock path.
