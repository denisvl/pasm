# Emulator Automation Python API

This module is a thin `ctypes` binding over the stable automation C ABI.
It copies snapshots into Python-owned objects before releasing adapter-owned C
memory, so callers can keep returned dataclasses without managing C lifetimes.

## Loading a Library

```python
from src.pasm_automation import create

with create(
    "generated/apple2_interactive/build/libapple2.so",
    "mos6502_automation_create",
) as machine:
    machine.reset("cold")
    machine.run.frames(10)
```

Generated adapters expose CPU-specific create symbols such as
`mos6502_automation_create`. If you need direct access to the shared library or
an existing machine handle, use `load_library(...)` or `attach(...)`.

## Screen Capture

```python
framebuffer = machine.screen.framebuffer()
pixels = framebuffer.pixels
framebuffer.save_png("framebuffer.png")

views = machine.screen.text_views()
text = machine.screen.text(views[0].region_id)
print(text.plain)
```

Text snapshots preserve native character codes, Unicode codepoints, source
addresses, charset ids, attributes, confidence, and plain UTF-8 text.

## Input and Execution

```python
machine.pause()
machine.reset("cold")
machine.resume()
machine.keyboard.tap("RETURN")
machine.keyboard.tap("SPACE", preset=InputTapPreset.hold_frames(2))
machine.controller.press("fire_1", device_id="joystick_port_1")
machine.controller.tap("fire_1", device_id="joystick_port_1", preset=InputTapPreset.hold_frames(2))
machine.run.frame()
machine.run.frames(60)
```

All C ABI result failures raise `AutomationError`. Frame-based wait timeouts
raise `AutomationTimeoutError`.

## Input Sequences

```python
from src.pasm_automation import InputTapPreset, InputTiming

sequence = machine.sequence()
sequence.key_down("RETURN", timing=InputTiming.immediate())
sequence.wait_frames(2)
sequence.key_up("RETURN", timing=InputTiming.delay_frames(1))
sequence.tap_key("SPACE", preset=InputTapPreset.hold_frames(2))
sequence.controller_down(
    "fire_1",
    device_id="joystick_port_1",
    timing=InputTiming.frame(120),
)
sequence.tap_controller(
    "fire_1",
    device_id="joystick_port_1",
    preset=InputTapPreset.hold_frames(2),
)
sequence.play()
```

Sequence builders currently schedule explicit key/controller events plus
frame waits over the existing C ABI. Logical text typing is still deferred
until adapters expose machine-specific character maps cleanly.

Direct typing is now available when the loaded adapter exposes character
mappings:

```python
machine.keyboard.type_text("A\r")

sequence = machine.sequence()
sequence.type_text("RUN\r")
sequence.play()
```

Modifier-driven characters use the adapter-provided modifier key ids rather
than assuming fixed key names.

## Frame-Based Waits

```python
snapshot = machine.screen.wait_for_text(
    "READY",
    region_id="primary_text",
    timeout_frames=120,
)
```

Wait helpers advance emulated frames through `run_frames`; they do not use
wall-clock sleeps.

Stable waits are also available:

```python
stable_text = machine.screen.wait_for_stable_text(
    region_id="primary_text",
    stable_frames=4,
    timeout_frames=120,
)
stable_framebuffer = machine.screen.wait_for_stable_framebuffer(
    stable_frames=2,
    timeout_frames=30,
)
```

Stable comparisons ignore frame metadata and compare visible content only.

## Fluent Wait Conditions

```python
result = (
    machine.wait.any(
        machine.conditions.screen_contains("READY.", region_id="primary_text"),
        machine.conditions.screen_contains("ERROR", region_id="primary_text"),
    )
    .timeout_frames(300)
    .run()
)
```

Conditions can also be composed with `machine.wait.all(...)`, and there is a
direct shortcut for the common case:

```python
machine.wait.screen_contains(
    "READY.",
    region_id="primary_text",
    timeout_frames=300,
)
```

## Event Polling

```python
from src.pasm_automation import EventType

machine.run.frames(2)

event = machine.poll_event(0)
assert event is not None
assert event.sequence_number == 1
assert event.type == EventType.FRAME_COMPLETED
```

The tested polling path currently covers:

- machine reset
- execution-state changed
- frame completed
- input submitted
- text changed
- screen changed

`poll_event(...)` returns `None` when no event newer than `after_sequence` is
available yet. The current implementation is still intentionally narrow, but
the tested polling path now covers:

- machine reset
- execution-state changed
- frame completed
- input submitted

For ergonomic draining, use the iterator wrapper:

```python
events = machine.events()
available = events.collect_available()
for event in available:
    print(event.sequence_number, event.event_type)

events.dispatch_available(lambda event: print(event.type))
```

For async consumers, use the async iterator:

```python
events = machine.screen.async_events(step_frames=1)
event = await events.recv(timeout_frames=120)
```

For direct callback-style dispatch through the C/core helper:

```python
after_sequence, count = machine.dispatch_events(
    lambda event: print(event.type),
    after_sequence=0,
)
```

For persistent manual subscriptions:

```python
with machine.subscribe(
    lambda event: print(event.type),
    event_type=EventType.FRAME_COMPLETED,
    after_sequence=0,
) as subscription:
    count = subscription.dispatch_available()
    print(count, subscription.after_sequence)
```

Current callback/subscription contract:

- callbacks run synchronously on the thread that called the dispatch function
- the core does not create background threads or pumps
- dispatching the same subscription recursively from inside its callback is invalid
- cross-thread use of the same machine or subscription handle is unsupported unless the embedding layer serializes access itself

You can also wait directly on an event type:

```python
from src.pasm_automation import EventType

event = machine.screen.wait_for_event(
    EventType.SCREEN_CHANGED,
    timeout_frames=120,
)

event = machine.wait.screen_changed(timeout_frames=120)
text_event = machine.screen.wait_for_text_changed(timeout_frames=120)
text_event = machine.wait.text_changed(timeout_frames=120)
```

## Pytest Fixtures

Load the plugin explicitly:

```bash
uv run pytest -p src.pasm_automation.pytest_plugin \
  --automation-library generated/apple2_interactive/build/libapple2.so \
  --automation-create-symbol mos6502_automation_create
```

Then use:

```python
def test_boot_text(automation_machine):
    automation_machine.reset("cold")
    assert "READY" in automation_machine.screen.wait_for_text(
        "READY",
        region_id="primary_text",
        timeout_frames=120,
    ).plain
```

## Example Script

```bash
uv run python examples/automation/capture_text_and_screenshot.py \
  generated/apple2_interactive/build/libapple2.so \
  --create-symbol mos6502_automation_create \
  --text-region primary_text \
  --frames 10 \
  --screenshot framebuffer.png
```

For per-family known-good flows across Python, Rust, and MCP consumers, see
[emulator_automation_example_flows.md](./emulator_automation_example_flows.md).
