# Emulator Automation JSON Lines Command Schema

This document defines the initial JSON Lines command schema for the emulator
automation transport. It is intentionally transport-neutral at the semantic
layer and uses one JSON object per line on the wire.

This file covers command and response messages only. Event messages are left to
the Phase 8 event-schema task.

## Status

Phase 8 draft, command schema only.

## Transport framing

- Each request is a single UTF-8 JSON object on one line.
- Each response is a single UTF-8 JSON object on one line.
- Request and response ordering may differ; clients must match by `id`.
- Events are out of scope for this file.

## Protocol version

Every request may include `protocol_version`. If omitted, the default is `1`.

```json
{"id":"req-1","protocol_version":1,"method":"machine.describe"}
```

## Request envelope

Every command request uses this envelope:

```json
{
  "id": "string-or-integer",
  "protocol_version": 1,
  "method": "namespace.operation",
  "params": {},
  "submitted_at": "optional client timestamp"
}
```

Fields:

- `id`: required, caller-chosen correlation id, string or integer
- `protocol_version`: optional integer, current value `1`
- `method`: required string
- `params`: optional object, defaults to `{}`
- `submitted_at`: optional opaque timestamp string from the client

Validation rules:

- Unknown top-level fields should be ignored for forward compatibility.
- `params` must be an object when present.
- `method` must be an exact method name, not a free-form expression.

## Response envelope

Every command response uses exactly one of `result` or `error`.

```json
{
  "id": "string-or-integer",
  "ok": true,
  "result": {}
}
```

```json
{
  "id": "string-or-integer",
  "ok": false,
  "error": {
    "code": "unsupported",
    "message": "human-readable error",
    "details": {}
  }
}
```

Fields:

- `id`: required, copied from the request
- `ok`: required boolean
- `result`: required when `ok` is `true`
- `error`: required when `ok` is `false`

Error object fields:

- `code`: stable machine-readable error code
- `message`: short human-readable summary
- `details`: optional object with structured context

## Error codes

Initial protocol error codes map directly to the C automation result names:

- `ok`
- `unsupported`
- `invalid_argument`
- `invalid_state`
- `not_running`
- `already_running`
- `not_ready`
- `timeout`
- `mapping_unavailable`
- `character_unsupported`
- `device_unavailable`
- `resource_unavailable`
- `transport_error`
- `serialization_error`
- `adapter_error`
- `internal_error`

Protocol-level errors not tied to the machine may also use:

- `unknown_method`
- `invalid_request`
- `invalid_params`

## Method naming

Methods follow `domain.action` naming.

Initial domains:

- `machine`
- `screen`
- `input`
- `execution`
- `wait`
- `events`

## Initial method set

This is the initial Phase 8 command surface. It mirrors the current stable C,
Python, and Rust automation core rather than future inspection or replay work.

### `machine.describe`

Request:

```json
{"id":1,"method":"machine.describe"}
```

Result:

```json
{
  "machine_id": "apple2e",
  "system_id": "apple2",
  "model_id": "apple2e",
  "region": "ntsc",
  "video_standard": "ntsc",
  "adapter_version": "string",
  "configured_memory_bytes": 65536,
  "capabilities": {
    "feature_bits": 769
  }
}
```

### `machine.capabilities`

Request:

```json
{"id":2,"method":"machine.capabilities"}
```

Result:

```json
{
  "feature_bits": 769
}
```

### `screen.framebuffer`

Request:

```json
{"id":3,"method":"screen.framebuffer"}
```

Result:

- `frame`
- `width`
- `height`
- `stride_bytes`
- `pixel_format`
- `visible_area`
- `pixel_aspect_numerator`
- `pixel_aspect_denominator`
- `pixels_base64`

Notes:

- Raw framebuffer bytes are base64-encoded for JSON transport.
- `pixel_format` uses the same stable numeric enum as the C ABI.

### `screen.text_views`

Request:

```json
{"id":4,"method":"screen.text_views"}
```

Result:

```json
{
  "views": [
    {
      "region_id": "main",
      "columns": 40,
      "rows": 24,
      "row_stride": 40,
      "charset_id": "ascii",
      "native_encoding": "screen_code",
      "unicode_map": "ascii"
    }
  ]
}
```

### `screen.text_grid`

Request:

```json
{"id":5,"method":"screen.text_grid","params":{"region_id":"main"}}
```

Result:

- `frame`
- `region_id`
- `columns`
- `rows`
- `row_stride`
- `plain`
- `cells`

Each cell contains:

- `native_code`
- `unicode_codepoint`
- `glyph_id`
- `foreground_color`
- `background_color`
- `attribute_flags`
- `charset_id`
- `source_address`
- `confidence`

### `input.key`

Request:

```json
{
  "id": 6,
  "method": "input.key",
  "params": {
    "device_id": "optional",
    "key_id": "RETURN",
    "action": "press",
    "timing": {"kind":"immediate","value":0}
  }
}
```

Result:

```json
{"accepted":true}
```

### `input.controller_button`

Request:

```json
{
  "id": 7,
  "method": "input.controller_button",
  "params": {
    "device_id": "joystick_port_1",
    "control_id": "fire_1",
    "action": "press",
    "timing": {"kind":"immediate","value":0}
  }
}
```

Result:

```json
{"accepted":true}
```

### `execution.pause`

Request:

```json
{"id":8,"method":"execution.pause"}
```

Result:

```json
{"accepted":true}
```

### `execution.resume`

Request:

```json
{"id":9,"method":"execution.resume"}
```

Result:

```json
{"accepted":true}
```

### `execution.reset`

Request:

```json
{"id":10,"method":"execution.reset","params":{"kind":"cold"}}
```

Allowed `kind` values:

- `cold`
- `warm`

Result:

```json
{"accepted":true}
```

### `execution.step_frame`

Request:

```json
{"id":11,"method":"execution.step_frame"}
```

Result:

```json
{"accepted":true}
```

### `execution.run_frames`

Request:

```json
{"id":12,"method":"execution.run_frames","params":{"frame_count":120}}
```

Result:

```json
{"accepted":true}
```

### `wait.event`

Request:

```json
{
  "id": 13,
  "method": "wait.event",
  "params": {
    "event_type": "screen_changed",
    "after_sequence": 0,
    "timeout_frames": 300,
    "step_frames": 1
  }
}
```

Result:

- event envelope matching the canonical event model

### `wait.text`

Request:

```json
{
  "id": 14,
  "method": "wait.text",
  "params": {
    "text": "READY.",
    "region_id": "main",
    "timeout_frames": 300,
    "step_frames": 1
  }
}
```

Result:

- text-grid snapshot matching `screen.text_grid`

### `wait.stable_text`

Request:

```json
{
  "id": 15,
  "method": "wait.stable_text",
  "params": {
    "region_id": "main",
    "stable_frames": 2,
    "timeout_frames": 300,
    "step_frames": 1
  }
}
```

Result:

- text-grid snapshot matching `screen.text_grid`

### `wait.stable_framebuffer`

Request:

```json
{
  "id": 16,
  "method": "wait.stable_framebuffer",
  "params": {
    "stable_frames": 2,
    "timeout_frames": 300,
    "step_frames": 1
  }
}
```

Result:

- framebuffer snapshot matching `screen.framebuffer`

### `events.poll`

Request:

```json
{"id":17,"method":"events.poll","params":{"after_sequence":0}}
```

Result:

```json
{
  "event": null
}
```

or

```json
{
  "event": {
    "sequence_number": 42,
    "event_type": "text_changed"
  }
}
```

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

### Timing

```json
{"kind":"immediate","value":0}
```

Allowed `kind` values:

- `immediate`
- `frame`
- `cycle`
- `delay_frames`
- `delay_cycles`

### Event type names

Allowed symbolic event names:

- `frame_completed`
- `machine_reset`
- `execution_state_changed`
- `input_submitted`
- `screen_changed`
- `text_changed`
- `media_activity`
- `debug_message`
- `error`

### Execution state names

Allowed symbolic execution states:

- `stopped`
- `running`
- `paused`
- `resetting`
- `error`

## Compatibility rules

- New methods may be added in later protocol versions.
- New result fields may be added; clients should ignore unknown fields.
- Existing field meanings must stay stable within a protocol version.
- Numeric ids and string ids are both valid request identifiers.

## Explicit non-goals for this schema draft

This draft does not define:

- Event streaming messages
- Subscriptions over transport
- Recording and replay commands
- Memory/register inspection commands
- Terminal-client command parsing
