# Emulator Automation JSON Lines Event Schema

This document defines the initial JSON Lines event schema for the emulator
automation transport. It pairs with
[docs/emulator_automation_jsonlines_command_schema.md](/home/dvlop/projects/pasm/docs/emulator_automation_jsonlines_command_schema.md)
and covers unsolicited event messages only.

This file does not define request/response commands. It defines the shape of
event lines emitted by a JSON Lines transport when event delivery is enabled.

## Status

Phase 8 draft, event schema only.

## Transport framing

- Each event is a single UTF-8 JSON object on one line.
- Events may appear interleaved with command responses.
- Clients must distinguish events from responses by top-level fields.
- Events are not correlated to a request `id`.

## Protocol version

Every event includes `protocol_version`.

```json
{
  "protocol_version": 1,
  "kind": "event",
  "event": {
    "type": "frame_completed"
  }
}
```

## Top-level event envelope

Every event line uses this envelope:

```json
{
  "protocol_version": 1,
  "kind": "event",
  "stream": "machine",
  "timestamp": "optional transport timestamp",
  "event": {}
}
```

Fields:

- `protocol_version`: required integer, current value `1`
- `kind`: required string, always `"event"`
- `stream`: optional string, default `"machine"`
- `timestamp`: optional transport timestamp string
- `event`: required object containing the canonical event payload

Validation rules:

- Unknown top-level fields should be ignored for forward compatibility.
- `event` must be an object.
- `kind` must be exactly `"event"`.

## Canonical event object

Every event payload uses this common shape:

```json
{
  "sequence_number": 42,
  "type": "text_changed",
  "frame": {
    "frame_number": 123,
    "emulated_cycles": 45678,
    "emulated_time_ns": 0,
    "execution_state": "paused"
  },
  "device_id": "",
  "control_id": "",
  "region_id": "",
  "change": {
    "x": 0,
    "y": 0,
    "width": 0,
    "height": 0,
    "cell_count": 0
  },
  "text_deltas": [],
  "message": "",
  "input_action": "release"
}
```

Fields:

- `sequence_number`: required unsigned integer, monotonically increasing within one machine session
- `type`: required symbolic event name
- `frame`: required frame metadata object
- `device_id`: optional string, empty when not applicable
- `control_id`: optional string, empty when not applicable
- `region_id`: optional string, empty when not applicable
- `change`: required object for change-oriented events, zeros when not applicable
- `text_deltas`: required array, empty when not applicable
- `message`: optional string, empty when not applicable
- `input_action`: optional symbolic input action, defaults to `release` when not applicable

## Event type names

Allowed symbolic `type` values in protocol version `1`:

- `frame_completed`
- `machine_reset`
- `execution_state_changed`
- `input_submitted`
- `screen_changed`
- `text_changed`
- `media_activity`
- `debug_message`
- `error`

These names map directly to the current canonical event model in the C, Python,
and Rust bindings.

## Shared structured types

### Frame metadata

```json
{
  "frame_number": 123,
  "emulated_cycles": 45678,
  "emulated_time_ns": 0,
  "execution_state": "paused"
}
```

Allowed `execution_state` values:

- `stopped`
- `running`
- `paused`
- `resetting`
- `error`

### Change metadata

```json
{
  "x": 0,
  "y": 0,
  "width": 2,
  "height": 1,
  "cell_count": 2
}
```

This object is always present. For events without a screen/text change, all
fields are `0`.

### Text delta object

`text_deltas` contains per-cell structured deltas for `text_changed` events.

```json
{
  "x": 0,
  "y": 0,
  "before": {
    "native_code": 32,
    "unicode_codepoint": 32,
    "glyph_id": "ascii",
    "foreground_color": -1,
    "background_color": -1,
    "attribute_flags": 0,
    "charset_id": "ascii",
    "source_address": 1024,
    "confidence": 255
  },
  "after": {
    "native_code": 66,
    "unicode_codepoint": 66,
    "glyph_id": "ascii",
    "foreground_color": -1,
    "background_color": -1,
    "attribute_flags": 0,
    "charset_id": "ascii",
    "source_address": 1024,
    "confidence": 255
  }
}
```

Each `before` and `after` cell includes:

- `native_code`
- `unicode_codepoint`
- `glyph_id`
- `foreground_color`
- `background_color`
- `attribute_flags`
- `charset_id`
- `source_address`
- `confidence`

Plain-text renderings are intentionally omitted here because they can be
derived from `unicode_codepoint` and would duplicate the canonical cell data.

### Input action names

Allowed symbolic `input_action` values:

- `release`
- `press`

## Event-specific expectations

### `frame_completed`

- `frame` is meaningful
- `change` is zeroed
- `text_deltas` is empty
- `message` is empty

Example:

```json
{
  "protocol_version": 1,
  "kind": "event",
  "event": {
    "sequence_number": 12,
    "type": "frame_completed",
    "frame": {
      "frame_number": 1822,
      "emulated_cycles": 1093200,
      "emulated_time_ns": 0,
      "execution_state": "paused"
    },
    "device_id": "",
    "control_id": "",
    "region_id": "",
    "change": {"x":0,"y":0,"width":0,"height":0,"cell_count":0},
    "text_deltas": [],
    "message": "",
    "input_action": "release"
  }
}
```

### `machine_reset`

- `frame` usually reflects the post-reset machine state
- `change` is zeroed
- `text_deltas` is empty
- `message` is empty

### `execution_state_changed`

- `frame.execution_state` is meaningful
- `change` is zeroed
- `text_deltas` is empty
- `message` is empty unless an adapter adds a short note later

### `input_submitted`

- `device_id` may be set
- `control_id` may be set
- `input_action` is meaningful
- `change` is zeroed
- `text_deltas` is empty

Example:

```json
{
  "protocol_version": 1,
  "kind": "event",
  "event": {
    "sequence_number": 19,
    "type": "input_submitted",
    "frame": {
      "frame_number": 200,
      "emulated_cycles": 0,
      "emulated_time_ns": 0,
      "execution_state": "running"
    },
    "device_id": "joystick_port_1",
    "control_id": "fire_1",
    "region_id": "",
    "change": {"x":0,"y":0,"width":0,"height":0,"cell_count":0},
    "text_deltas": [],
    "message": "",
    "input_action": "press"
  }
}
```

### `screen_changed`

- `region_id` may be set
- `change` is meaningful
- `text_deltas` is empty in protocol version `1`
- `message` is empty

This matches the current core model: coarse screen-change metadata without a
tile/pixel delta payload yet.

### `text_changed`

- `region_id` may be set
- `change` is meaningful
- `text_deltas` may contain structured per-cell changes
- `message` is empty

Example:

```json
{
  "protocol_version": 1,
  "kind": "event",
  "event": {
    "sequence_number": 21,
    "type": "text_changed",
    "frame": {
      "frame_number": 201,
      "emulated_cycles": 0,
      "emulated_time_ns": 0,
      "execution_state": "paused"
    },
    "device_id": "",
    "control_id": "",
    "region_id": "main",
    "change": {"x":0,"y":0,"width":2,"height":1,"cell_count":2},
    "text_deltas": [
      {
        "x": 0,
        "y": 0,
        "before": {
          "native_code": 0,
          "unicode_codepoint": 65533,
          "glyph_id": "ascii",
          "foreground_color": -1,
          "background_color": -1,
          "attribute_flags": 0,
          "charset_id": "ascii",
          "source_address": 1024,
          "confidence": 64
        },
        "after": {
          "native_code": 66,
          "unicode_codepoint": 66,
          "glyph_id": "ascii",
          "foreground_color": -1,
          "background_color": -1,
          "attribute_flags": 0,
          "charset_id": "ascii",
          "source_address": 1024,
          "confidence": 255
        }
      }
    ],
    "message": "",
    "input_action": "release"
  }
}
```

### `media_activity`

- `message` is the primary payload
- `change` is zeroed
- `text_deltas` is empty

Example:

```json
{
  "protocol_version": 1,
  "kind": "event",
  "event": {
    "sequence_number": 30,
    "type": "media_activity",
    "frame": {
      "frame_number": 0,
      "emulated_cycles": 0,
      "emulated_time_ns": 0,
      "execution_state": "paused"
    },
    "device_id": "",
    "control_id": "",
    "region_id": "",
    "change": {"x":0,"y":0,"width":0,"height":0,"cell_count":0},
    "text_deltas": [],
    "message": "disk activity",
    "input_action": "release"
  }
}
```

### `debug_message`

- `message` is the primary payload
- `change` is zeroed
- `text_deltas` is empty

### `error`

- `message` is the primary payload
- `change` is zeroed
- `text_deltas` is empty

This event is distinct from transport or command failure responses. It is for
asynchronous machine or adapter error reporting.

## Ordering and delivery rules

- `sequence_number` defines the canonical in-session order.
- Events must be emitted in non-decreasing transport order by `sequence_number`.
- Clients should tolerate interleaving of events and command responses.
- Event delivery is best-effort at the transport layer but ordering within one
  delivered stream must remain deterministic.

## Compatibility rules

- New event types may be added in later protocol versions.
- New event fields may be added; clients should ignore unknown fields.
- Existing field meanings must stay stable within a protocol version.
- Empty strings and zeroed objects are preferred over omitted canonical fields
  when an event does not use that part of the payload.

## Explicit non-goals for this schema draft

This draft does not define:

- Subscription control commands
- Event replay or persistence formats
- Pixel/tile delta payloads for `screen_changed`
- Rich machine-specific asynchronous payload extensions
