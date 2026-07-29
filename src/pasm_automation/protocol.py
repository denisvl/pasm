from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .ctypes_api import (
    AutomationEvent,
    EventType,
    FrameMetadata,
    InputTiming,
    TextCell,
    TextDelta,
    EMU_AUTOMATION_INPUT_PRESS,
    EMU_AUTOMATION_INPUT_RELEASE,
)


PROTOCOL_VERSION = 1

_EVENT_TYPE_TO_NAME = {
    EventType.FRAME_COMPLETED: "frame_completed",
    EventType.MACHINE_RESET: "machine_reset",
    EventType.EXECUTION_STATE_CHANGED: "execution_state_changed",
    EventType.INPUT_SUBMITTED: "input_submitted",
    EventType.SCREEN_CHANGED: "screen_changed",
    EventType.TEXT_CHANGED: "text_changed",
    EventType.MEDIA_ACTIVITY: "media_activity",
    EventType.DEBUG_MESSAGE: "debug_message",
    EventType.ERROR: "error",
}
_EVENT_NAME_TO_TYPE = {name: int(event_type) for event_type, name in _EVENT_TYPE_TO_NAME.items()}

_EXECUTION_STATE_TO_NAME = {
    0: "stopped",
    1: "running",
    2: "paused",
    3: "resetting",
    4: "error",
}
_EXECUTION_NAME_TO_STATE = {name: value for value, name in _EXECUTION_STATE_TO_NAME.items()}

_INPUT_ACTION_TO_NAME = {
    EMU_AUTOMATION_INPUT_RELEASE: "release",
    EMU_AUTOMATION_INPUT_PRESS: "press",
}
_INPUT_NAME_TO_ACTION = {name: value for value, name in _INPUT_ACTION_TO_NAME.items()}


@dataclass(frozen=True)
class ProtocolRequest:
    id: str | int
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    protocol_version: int = PROTOCOL_VERSION
    submitted_at: str | None = None


@dataclass(frozen=True)
class ProtocolError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProtocolResponse:
    id: str | int
    ok: bool
    result: dict[str, Any] | None = None
    error: ProtocolError | None = None


@dataclass(frozen=True)
class ProtocolEventEnvelope:
    event: AutomationEvent
    protocol_version: int = PROTOCOL_VERSION
    stream: str = "machine"
    timestamp: str | None = None


def request_to_payload(request: ProtocolRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": request.id,
        "protocol_version": request.protocol_version,
        "method": request.method,
        "params": request.params,
    }
    if request.submitted_at is not None:
        payload["submitted_at"] = request.submitted_at
    return payload


def request_to_jsonl(request: ProtocolRequest) -> str:
    return _encode_jsonl(request_to_payload(request))


def response_to_payload(response: ProtocolResponse) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": response.id,
        "ok": response.ok,
    }
    if response.ok:
        payload["result"] = {} if response.result is None else response.result
    else:
        if response.error is None:
            raise ValueError("error response requires error payload")
        payload["error"] = {
            "code": response.error.code,
            "message": response.error.message,
            "details": response.error.details,
        }
    return payload


def response_to_jsonl(response: ProtocolResponse) -> str:
    return _encode_jsonl(response_to_payload(response))


def event_to_payload(event: AutomationEvent) -> dict[str, Any]:
    return {
        "sequence_number": event.sequence_number,
        "type": event_type_name(event.event_type),
        "frame": frame_to_payload(event.frame),
        "input_accepted": frame_to_payload(event.input_accepted),
        "input_applied": frame_to_payload(event.input_applied),
        "device_id": event.device_id,
        "control_id": event.control_id,
        "region_id": event.region_id,
        "change": {
            "x": event.change_x,
            "y": event.change_y,
            "width": event.change_width,
            "height": event.change_height,
            "cell_count": event.change_cell_count,
        },
        "text_deltas": [text_delta_to_payload(delta) for delta in event.text_deltas],
        "message": event.message,
        "input_action": input_action_name(event.input_action),
        "input_timing": {
            "kind": event.input_timing.kind,
            "value": event.input_timing.value,
        },
        "execution_state_change": {
            "previous": event.previous_execution_state,
            "current": event.current_execution_state,
        },
    }


def event_envelope_to_payload(envelope: ProtocolEventEnvelope) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "protocol_version": envelope.protocol_version,
        "kind": "event",
        "stream": envelope.stream,
        "event": event_to_payload(envelope.event),
    }
    if envelope.timestamp is not None:
        payload["timestamp"] = envelope.timestamp
    return payload


def event_to_jsonl(event: AutomationEvent, *, stream: str = "machine", timestamp: str | None = None) -> str:
    return _encode_jsonl(
        event_envelope_to_payload(
            ProtocolEventEnvelope(event=event, stream=stream, timestamp=timestamp)
        )
    )


def parse_jsonl_line(line: str) -> dict[str, Any]:
    payload = json.loads(line)
    if not isinstance(payload, dict):
        raise ValueError("JSON Lines payload must be an object")
    return payload


def parse_event_payload(payload: dict[str, Any]) -> AutomationEvent:
    frame_payload = _require_object(payload, "frame")
    input_accepted_payload = _require_object(payload, "input_accepted") if "input_accepted" in payload else {}
    input_applied_payload = _require_object(payload, "input_applied") if "input_applied" in payload else {}
    change_payload = _require_object(payload, "change")
    deltas_payload = payload.get("text_deltas", [])
    if not isinstance(deltas_payload, list):
        raise ValueError("text_deltas must be a list")
    input_timing_payload = payload.get("input_timing", {})
    if not isinstance(input_timing_payload, dict):
        raise ValueError("input_timing must be an object")
    state_change_payload = payload.get("execution_state_change", {})
    if not isinstance(state_change_payload, dict):
        raise ValueError("execution_state_change must be an object")
    return AutomationEvent(
        sequence_number=int(payload["sequence_number"]),
        event_type=event_type_value(payload["type"]),
        frame=frame_from_payload(frame_payload),
        input_accepted=frame_from_payload(input_accepted_payload) if input_accepted_payload else FrameMetadata(0, 0, 0, 0),
        input_applied=frame_from_payload(input_applied_payload) if input_applied_payload else FrameMetadata(0, 0, 0, 0),
        device_id=str(payload.get("device_id", "")),
        control_id=str(payload.get("control_id", "")),
        region_id=str(payload.get("region_id", "")),
        change_x=int(change_payload.get("x", 0)),
        change_y=int(change_payload.get("y", 0)),
        change_width=int(change_payload.get("width", 0)),
        change_height=int(change_payload.get("height", 0)),
        change_cell_count=int(change_payload.get("cell_count", 0)),
        input_action=input_action_value(payload.get("input_action", "release")),
        input_timing=InputTiming(
            int(input_timing_payload.get("kind", 0)),
            int(input_timing_payload.get("value", 0)),
        ),
        previous_execution_state=int(state_change_payload.get("previous", 0)),
        current_execution_state=int(state_change_payload.get("current", 0)),
        message=str(payload.get("message", "")),
        text_deltas=tuple(text_delta_from_payload(delta) for delta in deltas_payload),
    )


def parse_event_envelope(payload: dict[str, Any]) -> ProtocolEventEnvelope:
    if payload.get("kind") != "event":
        raise ValueError("payload is not an event envelope")
    return ProtocolEventEnvelope(
        protocol_version=int(payload.get("protocol_version", PROTOCOL_VERSION)),
        stream=str(payload.get("stream", "machine")),
        timestamp=str(payload["timestamp"]) if "timestamp" in payload else None,
        event=parse_event_payload(_require_object(payload, "event")),
    )


def frame_to_payload(frame: FrameMetadata) -> dict[str, Any]:
    return {
        "frame_number": frame.frame_number,
        "emulated_cycles": frame.emulated_cycles,
        "emulated_time_ns": frame.emulated_time_ns,
        "execution_state": execution_state_name(frame.execution_state),
    }


def frame_from_payload(payload: dict[str, Any]) -> FrameMetadata:
    return FrameMetadata(
        frame_number=int(payload["frame_number"]),
        emulated_cycles=int(payload.get("emulated_cycles", 0)),
        emulated_time_ns=int(payload.get("emulated_time_ns", 0)),
        execution_state=execution_state_value(payload["execution_state"]),
    )


def text_cell_to_payload(cell: TextCell) -> dict[str, Any]:
    return {
        "native_code": cell.native_code,
        "unicode_codepoint": cell.unicode_codepoint,
        "glyph_id": cell.glyph_id,
        "foreground_color": cell.foreground_color,
        "background_color": cell.background_color,
        "attribute_flags": cell.attribute_flags,
        "charset_id": cell.charset_id,
        "source_address": cell.source_address,
        "confidence": cell.confidence,
    }


def text_cell_from_payload(payload: dict[str, Any]) -> TextCell:
    codepoint = int(payload["unicode_codepoint"])
    text = "" if codepoint == 0 else chr(codepoint) if 0 <= codepoint <= 0x10FFFF else "\ufffd"
    return TextCell(
        native_code=int(payload["native_code"]),
        unicode_codepoint=codepoint,
        text=text,
        glyph_id=str(payload.get("glyph_id", "")),
        foreground_color=int(payload.get("foreground_color", 0)),
        background_color=int(payload.get("background_color", 0)),
        attribute_flags=int(payload.get("attribute_flags", 0)),
        charset_id=str(payload.get("charset_id", "")),
        source_address=int(payload.get("source_address", 0)),
        confidence=int(payload.get("confidence", 0)),
    )


def text_delta_to_payload(delta: TextDelta) -> dict[str, Any]:
    return {
        "x": delta.x,
        "y": delta.y,
        "before": text_cell_to_payload(delta.before),
        "after": text_cell_to_payload(delta.after),
    }


def text_delta_from_payload(payload: dict[str, Any]) -> TextDelta:
    return TextDelta(
        x=int(payload["x"]),
        y=int(payload["y"]),
        before=text_cell_from_payload(_require_object(payload, "before")),
        after=text_cell_from_payload(_require_object(payload, "after")),
    )


def event_type_name(event_type: int) -> str:
    try:
        return _EVENT_TYPE_TO_NAME[EventType(event_type)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"unknown event type: {event_type}") from exc


def event_type_value(name: str) -> int:
    try:
        return _EVENT_NAME_TO_TYPE[str(name)]
    except KeyError as exc:
        raise ValueError(f"unknown event type name: {name}") from exc


def execution_state_name(value: int) -> str:
    try:
        return _EXECUTION_STATE_TO_NAME[int(value)]
    except KeyError as exc:
        raise ValueError(f"unknown execution state: {value}") from exc


def execution_state_value(name: str) -> int:
    try:
        return _EXECUTION_NAME_TO_STATE[str(name)]
    except KeyError as exc:
        raise ValueError(f"unknown execution state name: {name}") from exc


def input_action_name(value: int) -> str:
    try:
        return _INPUT_ACTION_TO_NAME[int(value)]
    except KeyError as exc:
        raise ValueError(f"unknown input action: {value}") from exc


def input_action_value(name: str) -> int:
    try:
        return _INPUT_NAME_TO_ACTION[str(name)]
    except KeyError as exc:
        raise ValueError(f"unknown input action name: {name}") from exc


def _require_object(payload: dict[str, Any], field: str) -> dict[str, Any]:
    value = payload[field]
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _encode_jsonl(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
