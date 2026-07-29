from __future__ import annotations

import ctypes
import enum
import asyncio
import json
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from collections import OrderedDict
from typing import Any, Callable, TypeVar


EMU_AUTOMATION_ABI_VERSION = 2
EMU_AUTOMATION_OK = 0
EMU_AUTOMATION_TIMEOUT = 7
EMU_AUTOMATION_STRUCT_VERSION = 2
EMU_AUTOMATION_RESET_COLD = 0
EMU_AUTOMATION_RESET_WARM = 1
EMU_AUTOMATION_INPUT_RELEASE = 0
EMU_AUTOMATION_INPUT_PRESS = 1
EMU_AUTOMATION_TIMING_IMMEDIATE = 0
EMU_AUTOMATION_TIMING_FRAME = 1
EMU_AUTOMATION_TIMING_CYCLE = 2
EMU_AUTOMATION_TIMING_DELAY_FRAMES = 3
EMU_AUTOMATION_TIMING_DELAY_CYCLES = 4
EMU_AUTOMATION_KEY_MODIFIER_SHIFT = 1 << 0
EMU_AUTOMATION_KEY_MODIFIER_CTRL = 1 << 1
EMU_AUTOMATION_KEY_MODIFIER_ALT = 1 << 2
EMU_AUTOMATION_KEY_MODIFIER_META = 1 << 3
EMU_AUTOMATION_EVENT_NONE = 0
EMU_AUTOMATION_EVENT_FRAME_COMPLETED = 1
EMU_AUTOMATION_EVENT_MACHINE_RESET = 2
EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED = 3
EMU_AUTOMATION_EVENT_INPUT_SUBMITTED = 4
EMU_AUTOMATION_EVENT_SCREEN_CHANGED = 5
EMU_AUTOMATION_EVENT_TEXT_CHANGED = 6
EMU_AUTOMATION_EVENT_MEDIA_ACTIVITY = 7
EMU_AUTOMATION_EVENT_DEBUG_MESSAGE = 8
EMU_AUTOMATION_EVENT_ERROR = 9
EMU_AUTOMATION_PIXEL_FORMAT_RGBA8888 = 1
EMU_AUTOMATION_PIXEL_FORMAT_BGRA8888 = 2
EMU_AUTOMATION_PIXEL_FORMAT_RGB565 = 3


class EventType(enum.IntEnum):
    NONE = EMU_AUTOMATION_EVENT_NONE
    FRAME_COMPLETED = EMU_AUTOMATION_EVENT_FRAME_COMPLETED
    MACHINE_RESET = EMU_AUTOMATION_EVENT_MACHINE_RESET
    EXECUTION_STATE_CHANGED = EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED
    INPUT_SUBMITTED = EMU_AUTOMATION_EVENT_INPUT_SUBMITTED
    SCREEN_CHANGED = EMU_AUTOMATION_EVENT_SCREEN_CHANGED
    TEXT_CHANGED = EMU_AUTOMATION_EVENT_TEXT_CHANGED
    MEDIA_ACTIVITY = EMU_AUTOMATION_EVENT_MEDIA_ACTIVITY
    DEBUG_MESSAGE = EMU_AUTOMATION_EVENT_DEBUG_MESSAGE
    ERROR = EMU_AUTOMATION_EVENT_ERROR


class AutomationError(RuntimeError):
    def __init__(self, operation: str, result: int, result_name: str) -> None:
        self.operation = operation
        self.result = result
        self.result_name = result_name
        super().__init__(f"{operation} failed: {result_name} ({result})")


class AutomationTimeoutError(TimeoutError):
    def __init__(
        self,
        description: str,
        frames_elapsed: int,
        *,
        final_observation: Any = None,
        final_observation_summary: str | None = None,
    ) -> None:
        self.description = description
        self.frames_elapsed = frames_elapsed
        self.final_observation = final_observation
        self.final_observation_summary = final_observation_summary or ""
        message = f"Timed out waiting for {description} after {frames_elapsed} frames"
        if self.final_observation_summary:
            message += f"; last observed: {self.final_observation_summary}"
        super().__init__(message)


class ReplayMismatchError(AssertionError):
    def __init__(
        self,
        index: int,
        *,
        expected: dict[str, Any] | None,
        actual: dict[str, Any] | None,
    ) -> None:
        self.index = index
        self.expected = expected
        self.actual = actual
        if expected is None:
            message = f"replay produced unexpected extra event at index {index}: {actual!r}"
        elif actual is None:
            message = f"replay missing expected event at index {index}: {expected!r}"
        else:
            message = (
                f"replay event mismatch at index {index}: "
                f"expected {expected!r}, got {actual!r}"
            )
        super().__init__(message)


T = TypeVar("T")


@dataclass(frozen=True)
class InputTiming:
    kind: int
    value: int = 0

    @classmethod
    def immediate(cls) -> "InputTiming":
        return cls(EMU_AUTOMATION_TIMING_IMMEDIATE, 0)

    @classmethod
    def frame(cls, frame_number: int) -> "InputTiming":
        return cls(EMU_AUTOMATION_TIMING_FRAME, frame_number)

    @classmethod
    def cycle(cls, cycle_number: int) -> "InputTiming":
        return cls(EMU_AUTOMATION_TIMING_CYCLE, cycle_number)

    @classmethod
    def delay_frames(cls, frame_count: int) -> "InputTiming":
        return cls(EMU_AUTOMATION_TIMING_DELAY_FRAMES, frame_count)

    @classmethod
    def delay_cycles(cls, cycle_count: int) -> "InputTiming":
        return cls(EMU_AUTOMATION_TIMING_DELAY_CYCLES, cycle_count)


@dataclass(frozen=True)
class InputTapPreset:
    press_timing: InputTiming = field(default_factory=InputTiming.immediate)
    release_timing: InputTiming = field(default_factory=InputTiming.immediate)

    @classmethod
    def immediate(cls) -> "InputTapPreset":
        return cls()

    @classmethod
    def hold_frames(cls, frame_count: int) -> "InputTapPreset":
        return cls(
            press_timing=InputTiming.immediate(),
            release_timing=InputTiming.delay_frames(frame_count),
        )


@dataclass(frozen=True)
class InputLogStep:
    kind: str
    target_id: str = ""
    action: str = ""
    device_id: str = ""
    timing: InputTiming = field(default_factory=InputTiming.immediate)
    frame_count: int = 0


@dataclass(frozen=True)
class RecordingHeader:
    machine_id: str
    system_id: str
    model_id: str
    adapter_version: str
    configured_memory_bytes: int
    protocol_version: int = 1


@dataclass(frozen=True)
class SessionRecording:
    header: RecordingHeader
    input_steps: tuple[InputLogStep, ...]
    events: tuple["AutomationEvent", ...]

    def to_jsonl(self) -> str:
        lines = [
            json.dumps(
                {
                    "kind": "recording_header",
                    "protocol_version": self.header.protocol_version,
                    "machine_id": self.header.machine_id,
                    "system_id": self.header.system_id,
                    "model_id": self.header.model_id,
                    "adapter_version": self.header.adapter_version,
                    "configured_memory_bytes": self.header.configured_memory_bytes,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        ]
        for step in self.input_steps:
            lines.append(
                json.dumps(
                    {
                        "kind": "input_step",
                        "step": {
                            "kind": step.kind,
                            "target_id": step.target_id,
                            "action": step.action,
                            "device_id": step.device_id,
                            "timing": {
                                "kind": step.timing.kind,
                                "value": step.timing.value,
                            },
                            "frame_count": step.frame_count,
                        },
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        for event in self.events:
            lines.append(
                json.dumps(
                    {
                        "kind": "event",
                        "event": _event_to_recording_payload(event),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        return "".join(f"{line}\n" for line in lines)

    @classmethod
    def from_jsonl(
        cls,
        machine: "Machine",
        text: str,
    ) -> "SessionRecording":
        header: RecordingHeader | None = None
        steps: list[InputLogStep] = []
        events: list[AutomationEvent] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("recording line must decode to an object")
            kind = str(payload.get("kind", ""))
            if kind == "recording_header":
                header = RecordingHeader(
                    machine_id=str(payload.get("machine_id", "")),
                    system_id=str(payload.get("system_id", "")),
                    model_id=str(payload.get("model_id", "")),
                    adapter_version=str(payload.get("adapter_version", "")),
                    configured_memory_bytes=int(payload.get("configured_memory_bytes", 0)),
                    protocol_version=int(payload.get("protocol_version", 1)),
                )
            elif kind == "input_step":
                step_payload = payload.get("step", {})
                if not isinstance(step_payload, dict):
                    raise ValueError("recording input_step.step must be an object")
                sequence = InputSequence.from_log_payload(machine, [step_payload])
                steps.extend(sequence.steps())
            elif kind == "event":
                event_payload = payload.get("event", {})
                if not isinstance(event_payload, dict):
                    raise ValueError("recording event.event must be an object")
                events.append(_event_from_recording_payload(event_payload))
            else:
                raise ValueError(f"unsupported recording line kind: {kind}")
        if header is None:
            descriptor = machine.describe()
            header = RecordingHeader(
                machine_id=descriptor.machine_id,
                system_id=descriptor.system_id,
                model_id=descriptor.model_id,
                adapter_version=descriptor.adapter_version,
                configured_memory_bytes=descriptor.configured_memory_bytes,
            )
        return cls(header=header, input_steps=tuple(steps), events=tuple(events))

    def replay(
        self,
        machine: "Machine",
        *,
        verify_events: bool = True,
        after_sequence: int = 0,
    ) -> tuple["AutomationEvent", ...]:
        sequence = InputSequence.from_log_payload(
            machine,
            [
                {
                    "kind": step.kind,
                    "target_id": step.target_id,
                    "action": step.action,
                    "device_id": step.device_id,
                    "timing": {"kind": step.timing.kind, "value": step.timing.value},
                    "frame_count": step.frame_count,
                }
                for step in self.input_steps
            ],
        )
        sequence.play()
        observed = tuple(machine.drain_events(after_sequence))
        if verify_events:
            expected_payloads = [_event_to_recording_payload(event) for event in self.events]
            actual_payloads = [_event_to_recording_payload(event) for event in observed]
            max_len = max(len(expected_payloads), len(actual_payloads))
            for index in range(max_len):
                expected = expected_payloads[index] if index < len(expected_payloads) else None
                actual = actual_payloads[index] if index < len(actual_payloads) else None
                if expected != actual:
                    raise ReplayMismatchError(index, expected=expected, actual=actual)
        return observed


_EVENT_TYPE_TO_NAME = {
    EventType.NONE: "none",
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


def _frame_to_recording_payload(frame: "FrameMetadata") -> dict[str, int]:
    return {
        "frame_number": frame.frame_number,
        "emulated_cycles": frame.emulated_cycles,
        "emulated_time_ns": frame.emulated_time_ns,
        "execution_state": frame.execution_state,
    }


def _frame_from_recording_payload(payload: dict[str, Any]) -> "FrameMetadata":
    return FrameMetadata(
        frame_number=int(payload.get("frame_number", 0)),
        emulated_cycles=int(payload.get("emulated_cycles", 0)),
        emulated_time_ns=int(payload.get("emulated_time_ns", 0)),
        execution_state=int(payload.get("execution_state", 0)),
    )


def _text_cell_to_recording_payload(cell: "TextCell") -> dict[str, Any]:
    return {
        "native_code": cell.native_code,
        "unicode_codepoint": cell.unicode_codepoint,
        "text": cell.text,
        "glyph_id": cell.glyph_id,
        "foreground_color": cell.foreground_color,
        "background_color": cell.background_color,
        "attribute_flags": cell.attribute_flags,
        "charset_id": cell.charset_id,
        "source_address": cell.source_address,
        "confidence": cell.confidence,
    }


def _text_cell_from_recording_payload(payload: dict[str, Any]) -> "TextCell":
    return TextCell(
        native_code=int(payload.get("native_code", 0)),
        unicode_codepoint=int(payload.get("unicode_codepoint", 0)),
        text=str(payload.get("text", "")),
        glyph_id=str(payload.get("glyph_id", "")),
        foreground_color=int(payload.get("foreground_color", 0)),
        background_color=int(payload.get("background_color", 0)),
        attribute_flags=int(payload.get("attribute_flags", 0)),
        charset_id=str(payload.get("charset_id", "")),
        source_address=int(payload.get("source_address", 0)),
        confidence=int(payload.get("confidence", 0)),
    )


def _text_delta_to_recording_payload(delta: "TextDelta") -> dict[str, Any]:
    return {
        "x": delta.x,
        "y": delta.y,
        "before": _text_cell_to_recording_payload(delta.before),
        "after": _text_cell_to_recording_payload(delta.after),
    }


def _text_delta_from_recording_payload(payload: dict[str, Any]) -> "TextDelta":
    before = payload.get("before", {})
    after = payload.get("after", {})
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("recording text delta before/after must be objects")
    return TextDelta(
        x=int(payload.get("x", 0)),
        y=int(payload.get("y", 0)),
        before=_text_cell_from_recording_payload(before),
        after=_text_cell_from_recording_payload(after),
    )


def _event_to_recording_payload(event: "AutomationEvent") -> dict[str, Any]:
    return {
        "sequence_number": event.sequence_number,
        "type": _EVENT_TYPE_TO_NAME.get(EventType(event.event_type), "unknown"),
        "frame": _frame_to_recording_payload(event.frame),
        "input_accepted": _frame_to_recording_payload(event.input_accepted),
        "input_applied": _frame_to_recording_payload(event.input_applied),
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
        "message": event.message,
        "text_deltas": [_text_delta_to_recording_payload(delta) for delta in event.text_deltas],
        "input_action": event.input_action,
        "input_timing": {
            "kind": event.input_timing.kind,
            "value": event.input_timing.value,
        },
        "execution_state_change": {
            "previous": event.previous_execution_state,
            "current": event.current_execution_state,
        },
    }


def _event_from_recording_payload(payload: dict[str, Any]) -> "AutomationEvent":
    frame_payload = payload.get("frame", {})
    input_accepted_payload = payload.get("input_accepted", {})
    input_applied_payload = payload.get("input_applied", {})
    change_payload = payload.get("change", {})
    input_timing_payload = payload.get("input_timing", {})
    state_change_payload = payload.get("execution_state_change", {})
    deltas_payload = payload.get("text_deltas", [])
    if not isinstance(frame_payload, dict):
        raise ValueError("recording event frame must be an object")
    if not isinstance(input_accepted_payload, dict):
        raise ValueError("recording event input_accepted must be an object")
    if not isinstance(input_applied_payload, dict):
        raise ValueError("recording event input_applied must be an object")
    if not isinstance(change_payload, dict):
        raise ValueError("recording event change must be an object")
    if not isinstance(input_timing_payload, dict):
        raise ValueError("recording event input_timing must be an object")
    if not isinstance(state_change_payload, dict):
        raise ValueError("recording event execution_state_change must be an object")
    if not isinstance(deltas_payload, list):
        raise ValueError("recording event text_deltas must be a list")
    event_type_name = str(payload.get("type", "none"))
    return AutomationEvent(
        sequence_number=int(payload.get("sequence_number", 0)),
        event_type=_EVENT_NAME_TO_TYPE.get(event_type_name, EMU_AUTOMATION_EVENT_NONE),
        frame=_frame_from_recording_payload(frame_payload),
        input_accepted=_frame_from_recording_payload(input_accepted_payload),
        input_applied=_frame_from_recording_payload(input_applied_payload),
        device_id=str(payload.get("device_id", "")),
        control_id=str(payload.get("control_id", "")),
        region_id=str(payload.get("region_id", "")),
        change_x=int(change_payload.get("x", 0)),
        change_y=int(change_payload.get("y", 0)),
        change_width=int(change_payload.get("width", 0)),
        change_height=int(change_payload.get("height", 0)),
        change_cell_count=int(change_payload.get("cell_count", 0)),
        message=str(payload.get("message", "")),
        text_deltas=tuple(_text_delta_from_recording_payload(delta) for delta in deltas_payload),
        input_action=int(payload.get("input_action", EMU_AUTOMATION_INPUT_RELEASE)),
        input_timing=InputTiming(
            int(input_timing_payload.get("kind", EMU_AUTOMATION_TIMING_IMMEDIATE)),
            int(input_timing_payload.get("value", 0)),
        ),
        previous_execution_state=int(state_change_payload.get("previous", 0)),
        current_execution_state=int(state_change_payload.get("current", 0)),
    )


class _Capabilities(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("feature_bits", ctypes.c_uint64),
    ]


class _MachineDescriptor(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("machine_id", ctypes.c_char_p),
        ("system_id", ctypes.c_char_p),
        ("model_id", ctypes.c_char_p),
        ("region", ctypes.c_char_p),
        ("video_standard", ctypes.c_char_p),
        ("adapter_version", ctypes.c_char_p),
        ("configured_memory_bytes", ctypes.c_uint64),
        ("capabilities", _Capabilities),
    ]


class _CharacterMappingDescriptor(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("device_id", ctypes.c_char_p),
        ("unicode_codepoint", ctypes.c_uint32),
        ("native_code", ctypes.c_uint32),
        ("key_id", ctypes.c_char_p),
        ("required_modifier_bits", ctypes.c_uint32),
        ("shift_key_id", ctypes.c_char_p),
        ("ctrl_key_id", ctypes.c_char_p),
        ("alt_key_id", ctypes.c_char_p),
        ("meta_key_id", ctypes.c_char_p),
    ]


class _FrameMetadata(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("frame_number", ctypes.c_uint64),
        ("emulated_cycles", ctypes.c_uint64),
        ("emulated_time_ns", ctypes.c_uint64),
        ("execution_state", ctypes.c_int),
    ]


class _Rect(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int32),
        ("y", ctypes.c_int32),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
    ]


class _FramebufferSnapshot(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("frame", _FrameMetadata),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("stride_bytes", ctypes.c_uint32),
        ("pixel_format", ctypes.c_int),
        ("visible_area", _Rect),
        ("pixel_aspect_numerator", ctypes.c_uint32),
        ("pixel_aspect_denominator", ctypes.c_uint32),
        ("pixels", ctypes.POINTER(ctypes.c_uint8)),
        ("pixel_size", ctypes.c_size_t),
        ("adapter_owned", ctypes.c_void_p),
    ]


class _TextCell(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("native_code", ctypes.c_uint32),
        ("unicode_codepoint", ctypes.c_uint32),
        ("glyph_id", ctypes.c_char_p),
        ("foreground_color", ctypes.c_int32),
        ("background_color", ctypes.c_int32),
        ("attribute_flags", ctypes.c_uint32),
        ("charset_id", ctypes.c_char_p),
        ("source_address", ctypes.c_uint64),
        ("confidence", ctypes.c_uint8),
    ]


class _TextDelta(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("x", ctypes.c_uint32),
        ("y", ctypes.c_uint32),
        ("before", _TextCell),
        ("after", _TextCell),
    ]


class _TextViewDescriptor(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("region_id", ctypes.c_char_p),
        ("columns", ctypes.c_uint32),
        ("rows", ctypes.c_uint32),
        ("row_stride", ctypes.c_uint32),
        ("charset_id", ctypes.c_char_p),
        ("native_encoding", ctypes.c_char_p),
        ("unicode_map", ctypes.c_char_p),
    ]


class _TextGridSnapshot(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("frame", _FrameMetadata),
        ("region_id", ctypes.c_char_p),
        ("columns", ctypes.c_uint32),
        ("rows", ctypes.c_uint32),
        ("row_stride", ctypes.c_uint32),
        ("cells", ctypes.POINTER(_TextCell)),
        ("cell_count", ctypes.c_size_t),
        ("plain_utf8", ctypes.c_char_p),
        ("plain_utf8_size", ctypes.c_size_t),
        ("adapter_owned", ctypes.c_void_p),
    ]


class _Timing(ctypes.Structure):
    _fields_ = [
        ("kind", ctypes.c_int),
        ("value", ctypes.c_uint64),
    ]


class _KeyEvent(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("device_id", ctypes.c_char_p),
        ("key_id", ctypes.c_char_p),
        ("action", ctypes.c_int),
        ("timing", _Timing),
    ]


class _ControllerButtonEvent(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("device_id", ctypes.c_char_p),
        ("control_id", ctypes.c_char_p),
        ("action", ctypes.c_int),
        ("timing", _Timing),
    ]


class _AutomationEvent(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("sequence_number", ctypes.c_uint64),
        ("event_type", ctypes.c_int),
        ("frame", _FrameMetadata),
        ("input_accepted", _FrameMetadata),
        ("input_applied", _FrameMetadata),
        ("device_id", ctypes.c_char_p),
        ("control_id", ctypes.c_char_p),
        ("region_id", ctypes.c_char_p),
        ("change_x", ctypes.c_uint32),
        ("change_y", ctypes.c_uint32),
        ("change_width", ctypes.c_uint32),
        ("change_height", ctypes.c_uint32),
        ("change_cell_count", ctypes.c_uint32),
        ("text_deltas", ctypes.POINTER(_TextDelta)),
        ("text_delta_count", ctypes.c_size_t),
        ("message", ctypes.c_char_p),
        ("input_action", ctypes.c_int),
        ("input_timing", _Timing),
        ("previous_execution_state", ctypes.c_int),
        ("current_execution_state", ctypes.c_int),
        ("adapter_owned", ctypes.c_void_p),
    ]


class _RegisterValue(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("name", ctypes.c_char * 32),
        ("hex_value", ctypes.c_char * 32),
        ("dec_value", ctypes.c_char * 32),
        ("has_dec", ctypes.c_uint8),
        ("changed", ctypes.c_uint8),
    ]


class _InstructionInfo(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("struct_version", ctypes.c_uint32),
        ("address", ctypes.c_uint64),
        ("bytes", ctypes.c_char * 32),
        ("text", ctypes.c_char * 96),
        ("symbol", ctypes.c_char * 64),
        ("has_symbol", ctypes.c_uint8),
        ("is_current_ip", ctypes.c_uint8),
        ("has_breakpoint", ctypes.c_uint8),
        ("branch_target", ctypes.c_uint64),
        ("has_branch_target", ctypes.c_uint8),
        ("changed_since_last_step", ctypes.c_uint8),
    ]


_EventCallback = ctypes.CFUNCTYPE(None, ctypes.POINTER(_AutomationEvent), ctypes.c_void_p)


@dataclass(frozen=True)
class Capabilities:
    feature_bits: int


@dataclass(frozen=True)
class MachineDescriptor:
    machine_id: str
    system_id: str
    model_id: str
    region: str
    video_standard: str
    adapter_version: str
    configured_memory_bytes: int
    capabilities: Capabilities


@dataclass(frozen=True)
class CharacterMappingDescriptor:
    device_id: str
    unicode_codepoint: int
    native_code: int
    key_id: str
    required_modifier_bits: int
    shift_key_id: str
    ctrl_key_id: str
    alt_key_id: str
    meta_key_id: str


@dataclass(frozen=True)
class FrameMetadata:
    frame_number: int
    emulated_cycles: int
    emulated_time_ns: int
    execution_state: int


@dataclass(frozen=True)
class RegisterValue:
    name: str
    hex_value: str
    dec_value: str
    has_dec: bool
    changed: bool


@dataclass(frozen=True)
class InstructionInfo:
    address: int
    bytes_text: str
    text: str
    symbol: str
    has_symbol: bool
    is_current_ip: bool
    has_breakpoint: bool
    branch_target: int
    has_branch_target: bool
    changed_since_last_step: bool


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class FramebufferSnapshot:
    frame: FrameMetadata
    width: int
    height: int
    stride_bytes: int
    pixel_format: int
    visible_area: Rect
    pixel_aspect_numerator: int
    pixel_aspect_denominator: int
    pixels: bytes

    def to_rgba8888(self) -> bytes:
        row_bytes = self.width * 4
        if self.stride_bytes < row_bytes:
            raise ValueError("framebuffer stride is smaller than a packed RGBA row")

        if self.pixel_format == EMU_AUTOMATION_PIXEL_FORMAT_RGBA8888:
            return b"".join(
                self.pixels[row_start : row_start + row_bytes]
                for row_start in self._row_starts()
            )

        if self.pixel_format == EMU_AUTOMATION_PIXEL_FORMAT_BGRA8888:
            rows = []
            for row_start in self._row_starts():
                row = self.pixels[row_start : row_start + row_bytes]
                converted = bytearray(row_bytes)
                for offset in range(0, row_bytes, 4):
                    converted[offset] = row[offset + 2]
                    converted[offset + 1] = row[offset + 1]
                    converted[offset + 2] = row[offset]
                    converted[offset + 3] = row[offset + 3]
                rows.append(bytes(converted))
            return b"".join(rows)

        if self.pixel_format == EMU_AUTOMATION_PIXEL_FORMAT_RGB565:
            row_bytes = self.width * 2
            if self.stride_bytes < row_bytes:
                raise ValueError("framebuffer stride is smaller than a packed RGB565 row")
            output = bytearray(self.width * self.height * 4)
            out_offset = 0
            for row_start in self._row_starts():
                row = self.pixels[row_start : row_start + row_bytes]
                for offset in range(0, row_bytes, 2):
                    value = row[offset] | (row[offset + 1] << 8)
                    red = (value >> 11) & 0x1F
                    green = (value >> 5) & 0x3F
                    blue = value & 0x1F
                    output[out_offset] = (red << 3) | (red >> 2)
                    output[out_offset + 1] = (green << 2) | (green >> 4)
                    output[out_offset + 2] = (blue << 3) | (blue >> 2)
                    output[out_offset + 3] = 255
                    out_offset += 4
            return bytes(output)

        raise ValueError(f"unsupported framebuffer pixel format: {self.pixel_format}")

    def save_png(self, path: str | Path) -> None:
        rgba = self.to_rgba8888()
        scanline_size = self.width * 4
        filtered = bytearray()
        for row in range(self.height):
            filtered.append(0)
            offset = row * scanline_size
            filtered.extend(rgba[offset : offset + scanline_size])

        png = bytearray(b"\x89PNG\r\n\x1a\n")
        png.extend(
            _png_chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", self.width, self.height, 8, 6, 0, 0, 0),
            )
        )
        png.extend(_png_chunk(b"IDAT", zlib.compress(bytes(filtered))))
        png.extend(_png_chunk(b"IEND", b""))
        Path(path).write_bytes(bytes(png))

    def _row_starts(self) -> range:
        required_size = self.stride_bytes * self.height
        if len(self.pixels) < required_size:
            raise ValueError("framebuffer pixel data is smaller than stride * height")
        return range(0, required_size, self.stride_bytes)


@dataclass(frozen=True)
class TextViewDescriptor:
    region_id: str
    columns: int
    rows: int
    row_stride: int
    charset_id: str
    native_encoding: str
    unicode_map: str


@dataclass(frozen=True)
class TextCell:
    native_code: int
    unicode_codepoint: int
    text: str
    glyph_id: str
    foreground_color: int
    background_color: int
    attribute_flags: int
    charset_id: str
    source_address: int
    confidence: int


@dataclass(frozen=True)
class TextDelta:
    x: int
    y: int
    before: TextCell
    after: TextCell


@dataclass(frozen=True)
class TextGridSnapshot:
    region_id: str
    columns: int
    rows: int
    row_stride: int
    plain: str
    cells: tuple[TextCell, ...]
    frame_number: int
    emulated_cycles: int
    emulated_time_ns: int
    execution_state: int


@dataclass(frozen=True)
class AutomationEvent:
    sequence_number: int
    event_type: int
    frame: FrameMetadata
    device_id: str
    control_id: str
    region_id: str
    change_x: int
    change_y: int
    change_width: int
    change_height: int
    change_cell_count: int
    input_action: int
    input_timing: InputTiming = field(default_factory=InputTiming.immediate)
    previous_execution_state: int = 0
    current_execution_state: int = 0
    input_accepted: FrameMetadata = field(
        default_factory=lambda: FrameMetadata(0, 0, 0, 0)
    )
    input_applied: FrameMetadata = field(
        default_factory=lambda: FrameMetadata(0, 0, 0, 0)
    )
    message: str = ""
    text_deltas: tuple[TextDelta, ...] = field(default_factory=tuple)

    @property
    def type(self) -> EventType:
        return EventType(self.event_type)


class Subscription:
    def __init__(
        self,
        machine: "Machine",
        handle: ctypes.c_void_p,
        callback_fn: _EventCallback,
        *,
        owned: bool = True,
    ) -> None:
        self._machine = machine
        self._handle = handle
        self._callback_fn = callback_fn
        self._owned = owned
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        if self._owned and self._handle and self._handle.value:
            self._machine._library.cdll.emu_automation_subscription_destroy(self._handle)
        self._closed = True
        self._handle = ctypes.c_void_p()

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    @property
    def after_sequence(self) -> int:
        if self._closed:
            raise RuntimeError("subscription is closed")
        return int(
            self._machine._library.cdll.emu_automation_subscription_after_sequence(self._handle)
        )

    def set_after_sequence(self, after_sequence: int) -> None:
        self._machine._library.check(
            self._machine._library.cdll.emu_automation_subscription_set_after_sequence(
                self._handle,
                ctypes.c_uint64(after_sequence),
            ),
            "emu_automation_subscription_set_after_sequence",
        )

    def dispatch_available(self, *, max_events: int = 0) -> int:
        if max_events < 0:
            raise ValueError("max_events must be non-negative")
        count = ctypes.c_size_t()
        self._machine._library.check(
            self._machine._library.cdll.emu_automation_subscription_dispatch_available(
                self._handle,
                max_events,
                ctypes.byref(count),
            ),
            "emu_automation_subscription_dispatch_available",
        )
        return int(count.value)


class KeyboardInput:
    def __init__(self, machine: "Machine") -> None:
        self._machine = machine

    def press(self, key_id: str, *, device_id: str | None = None) -> None:
        self._machine.key(key_id, action="press", device_id=device_id)

    def release(self, key_id: str, *, device_id: str | None = None) -> None:
        self._machine.key(key_id, action="release", device_id=device_id)

    def tap(
        self,
        key_id: str,
        *,
        device_id: str | None = None,
        preset: InputTapPreset | None = None,
    ) -> None:
        self._machine.tap_key(key_id, device_id=device_id, preset=preset)

    def release_all(self, *, device_id: str | None = None) -> int:
        return self._machine.release_all_keys(device_id=device_id)

    def type_text(
        self,
        text: str,
        *,
        device_id: str | None = None,
        preset: InputTapPreset | None = None,
    ) -> None:
        self._machine.type_text(text, device_id=device_id, preset=preset)


class ControllerInput:
    def __init__(self, machine: "Machine") -> None:
        self._machine = machine

    def press(self, control_id: str, *, device_id: str | None = None) -> None:
        self._machine.controller_button(control_id, action="press", device_id=device_id)

    def release(self, control_id: str, *, device_id: str | None = None) -> None:
        self._machine.controller_button(control_id, action="release", device_id=device_id)

    def tap(
        self,
        control_id: str,
        *,
        device_id: str | None = None,
        preset: InputTapPreset | None = None,
    ) -> None:
        self._machine.tap_controller_button(
            control_id,
            device_id=device_id,
            preset=preset,
        )

    def release_all(self, *, device_id: str | None = None) -> int:
        return self._machine.release_all_controller_buttons(device_id=device_id)


class RunControl:
    def __init__(self, machine: "Machine") -> None:
        self._machine = machine

    def frame(self) -> None:
        self._machine.step_frame()

    def frames(self, frame_count: int) -> None:
        self._machine.run_frames(frame_count)

    def until(
        self,
        predicate: Callable[["Machine"], T | None | bool],
        *,
        timeout_frames: int,
        step_frames: int = 1,
        description: str = "condition",
    ) -> T:
        return self._machine.wait_until(
            predicate,
            timeout_frames=timeout_frames,
            step_frames=step_frames,
            description=description,
        )


class ScreenView:
    def __init__(self, machine: "Machine") -> None:
        self._machine = machine

    def framebuffer(self) -> FramebufferSnapshot:
        return self._machine.capture_framebuffer()

    def text_views(self) -> list[TextViewDescriptor]:
        return self._machine.text_views()

    def text(self, region_id: str | None = None) -> TextGridSnapshot:
        return self._machine.capture_text_grid(region_id)

    def wait_for_text(
        self,
        text: str,
        *,
        region_id: str | None = None,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> TextGridSnapshot:
        return self._machine.wait_for_text(
            text,
            region_id=region_id,
            timeout_frames=timeout_frames,
            step_frames=step_frames,
        )

    def wait_for_text_disappearance(
        self,
        text: str,
        *,
        region_id: str | None = None,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> TextGridSnapshot:
        return self._machine.wait_for_text_disappearance(
            text,
            region_id=region_id,
            timeout_frames=timeout_frames,
            step_frames=step_frames,
        )

    def read_memory(self, address: int, size: int) -> bytes:
        return self._machine.read_memory(address, size)

    def program_counter(self) -> int:
        return self._machine.read_program_counter()

    def frame_metadata(self) -> FrameMetadata:
        return self._machine.read_frame_metadata()

    def wait_for_memory_value(
        self,
        address: int,
        value: bytes | int,
        *,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> bytes:
        return self._machine.wait_for_memory_value(
            address,
            value,
            timeout_frames=timeout_frames,
            step_frames=step_frames,
        )

    def wait_for_program_counter(
        self,
        program_counter: int,
        *,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> int:
        return self._machine.wait_for_program_counter(
            program_counter,
            timeout_frames=timeout_frames,
            timeout_cycles=timeout_cycles,
            timeout_emulated_time_ns=timeout_emulated_time_ns,
            step_frames=step_frames,
        )

    def wait_for_breakpoint(
        self,
        *,
        program_counter: int | None = None,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> FrameMetadata:
        return self._machine.wait_for_breakpoint(
            program_counter=program_counter,
            timeout_frames=timeout_frames,
            timeout_cycles=timeout_cycles,
            timeout_emulated_time_ns=timeout_emulated_time_ns,
            step_frames=step_frames,
        )

    def wait_for_watchpoint(
        self,
        *,
        program_counter: int | None = None,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> FrameMetadata:
        return self._machine.wait_for_watchpoint(
            program_counter=program_counter,
            timeout_frames=timeout_frames,
            timeout_cycles=timeout_cycles,
            timeout_emulated_time_ns=timeout_emulated_time_ns,
            step_frames=step_frames,
        )

    def wait_for_stable_text(
        self,
        *,
        region_id: str | None = None,
        stable_frames: int,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> TextGridSnapshot:
        return self._machine.wait_for_stable_text(
            region_id=region_id,
            stable_frames=stable_frames,
            timeout_frames=timeout_frames,
            step_frames=step_frames,
        )

    def wait_for_stable_framebuffer(
        self,
        *,
        stable_frames: int,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> FramebufferSnapshot:
        return self._machine.wait_for_stable_framebuffer(
            stable_frames=stable_frames,
            timeout_frames=timeout_frames,
            step_frames=step_frames,
        )

    def events(self, after_sequence: int = 0) -> "EventIterator":
        return self._machine.events(after_sequence)

    def async_events(
        self,
        after_sequence: int = 0,
        *,
        step_frames: int = 1,
        idle_sleep_seconds: float = 0.0,
    ) -> "AsyncEventIterator":
        return self._machine.async_events(
            after_sequence,
            step_frames=step_frames,
            idle_sleep_seconds=idle_sleep_seconds,
        )

    def wait_for_event(
        self,
        event_type: int | EventType,
        *,
        after_sequence: int = 0,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> AutomationEvent:
        return self._machine.wait_for_event(
            int(event_type),
            after_sequence=after_sequence,
            timeout_frames=timeout_frames,
            step_frames=step_frames,
        )

    def wait_for_text_changed(
        self,
        *,
        after_sequence: int = 0,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> AutomationEvent:
        return self.wait_for_event(
            EventType.TEXT_CHANGED,
            after_sequence=after_sequence,
            timeout_frames=timeout_frames,
            step_frames=step_frames,
        )

    def wait_for_media_activity(
        self,
        *,
        after_sequence: int = 0,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> AutomationEvent:
        return self.wait_for_event(
            EventType.MEDIA_ACTIVITY,
            after_sequence=after_sequence,
            timeout_frames=timeout_frames,
            step_frames=step_frames,
        )


class InspectionView:
    def __init__(self, machine: "Machine") -> None:
        self._machine = machine

    def read_memory(self, address: int, size: int) -> bytes:
        return self._machine.read_memory(address, size)

    def write_memory(self, address: int, data: bytes | bytearray) -> None:
        self._machine.write_memory(address, data)

    def registers(self) -> tuple[RegisterValue, ...]:
        return self._machine.read_registers()

    def current_instruction(self) -> InstructionInfo:
        return self._machine.read_current_instruction()

    def write_register(self, register_name: str, value: int) -> None:
        self._machine.write_register(register_name, value)

    def program_counter(self) -> int:
        return self._machine.read_program_counter()

    def frame_metadata(self) -> FrameMetadata:
        return self._machine.read_frame_metadata()

    def wait_for_memory_value(
        self,
        address: int,
        value: bytes | int,
        *,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> bytes:
        return self._machine.wait_for_memory_value(
            address,
            value,
            timeout_frames=timeout_frames,
            timeout_cycles=timeout_cycles,
            timeout_emulated_time_ns=timeout_emulated_time_ns,
            step_frames=step_frames,
        )

    def wait_for_program_counter(
        self,
        program_counter: int,
        *,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> int:
        return self._machine.wait_for_program_counter(
            program_counter,
            timeout_frames=timeout_frames,
            timeout_cycles=timeout_cycles,
            timeout_emulated_time_ns=timeout_emulated_time_ns,
            step_frames=step_frames,
        )


class DebugView:
    def __init__(self, machine: "Machine") -> None:
        self._machine = machine

    def wait_for_breakpoint(
        self,
        *,
        program_counter: int | None = None,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> FrameMetadata:
        return self._machine.wait_for_breakpoint(
            program_counter=program_counter,
            timeout_frames=timeout_frames,
            timeout_cycles=timeout_cycles,
            timeout_emulated_time_ns=timeout_emulated_time_ns,
            step_frames=step_frames,
        )

    def set_breakpoint(self, address: int, *, enabled: bool = True) -> None:
        self._machine.set_breakpoint(address, enabled=enabled)

    def wait_for_watchpoint(
        self,
        *,
        program_counter: int | None = None,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> FrameMetadata:
        return self._machine.wait_for_watchpoint(
            program_counter=program_counter,
            timeout_frames=timeout_frames,
            timeout_cycles=timeout_cycles,
            timeout_emulated_time_ns=timeout_emulated_time_ns,
            step_frames=step_frames,
        )


class WaitCondition:
    def __init__(
        self,
        machine: "Machine",
        predicate: Callable[["Machine"], T | None],
        *,
        description: str,
        final_observation: Callable[[], Any] | None = None,
        final_observation_summary: Callable[[Any], str] | None = None,
    ) -> None:
        self._machine = machine
        self._predicate = predicate
        self._description = description
        self._final_observation = final_observation
        self._final_observation_summary = final_observation_summary
        self._timeout_frames: int | None = None
        self._timeout_cycles: int | None = None
        self._timeout_emulated_time_ns: int | None = None
        self._step_frames = 1

    def timeout_frames(self, frame_count: int) -> "WaitCondition":
        self._timeout_frames = frame_count
        return self

    def timeout_cycles(self, cycle_count: int | None) -> "WaitCondition":
        self._timeout_cycles = cycle_count
        return self

    def timeout_emulated_time_ns(self, time_ns: int | None) -> "WaitCondition":
        self._timeout_emulated_time_ns = time_ns
        return self

    def step_frames(self, frame_count: int) -> "WaitCondition":
        self._step_frames = frame_count
        return self

    def run(self) -> T:
        if (
            self._timeout_frames is None
            and self._timeout_cycles is None
            and self._timeout_emulated_time_ns is None
        ):
            raise ValueError(
                "one of timeout_frames, timeout_cycles, or timeout_emulated_time_ns "
                "must be configured before run()"
            )
        return self._machine.wait_until(
            self._predicate,
            timeout_frames=self._timeout_frames,
            timeout_cycles=self._timeout_cycles,
            timeout_emulated_time_ns=self._timeout_emulated_time_ns,
            step_frames=self._step_frames,
            description=self._description,
            final_observation=self._final_observation,
            final_observation_summary=self._final_observation_summary,
        )


class ConditionFactory:
    def __init__(self, machine: "Machine") -> None:
        self._machine = machine

    def screen_contains(self, text: str, *, region_id: str | None = None) -> WaitCondition:
        region = region_id if region_id is not None else "default text region"
        state: dict[str, TextGridSnapshot | None] = {"snapshot": None}

        def predicate(machine: Machine) -> TextGridSnapshot | None:
            snapshot = machine.capture_text_grid(region_id)
            state["snapshot"] = snapshot
            return snapshot if text in snapshot.plain else None

        return WaitCondition(
            self._machine,
            predicate,
            description=f"text {text!r} in {region}",
            final_observation=lambda: state["snapshot"],
            final_observation_summary=_summarize_observation,
        )

    def text_disappears(self, text: str, *, region_id: str | None = None) -> WaitCondition:
        region = region_id if region_id is not None else "default text region"
        state: dict[str, TextGridSnapshot | None] = {"snapshot": None}

        def predicate(machine: Machine) -> TextGridSnapshot | None:
            snapshot = machine.capture_text_grid(region_id)
            state["snapshot"] = snapshot
            return snapshot if text not in snapshot.plain else None

        return WaitCondition(
            self._machine,
            predicate,
            description=f"text {text!r} absent in {region}",
            final_observation=lambda: state["snapshot"],
            final_observation_summary=_summarize_observation,
        )

    def stable_text(self, *, region_id: str | None = None, stable_frames: int) -> WaitCondition:
        state = {"last_key": None, "last_frame": None, "stable_for": 0}
        region = region_id if region_id is not None else "default text region"
        latest: dict[str, TextGridSnapshot | None] = {"snapshot": None}

        def predicate(machine: Machine) -> TextGridSnapshot | None:
            snapshot = machine.capture_text_grid(region_id)
            latest["snapshot"] = snapshot
            key = _text_grid_key(snapshot)
            if stable_frames == 0:
                return snapshot
            if state["last_key"] is None:
                state["last_key"] = key
                state["last_frame"] = snapshot.frame_number
                return None
            frame_delta = max(0, snapshot.frame_number - int(state["last_frame"]))
            if key == state["last_key"]:
                state["stable_for"] = int(state["stable_for"]) + frame_delta
                if int(state["stable_for"]) >= stable_frames:
                    return snapshot
            else:
                state["last_key"] = key
                state["stable_for"] = 0
            state["last_frame"] = snapshot.frame_number
            return None

        return WaitCondition(
            self._machine,
            predicate,
            description=f"stable text in {region}",
            final_observation=lambda: latest["snapshot"],
            final_observation_summary=_summarize_observation,
        )

    def stable_framebuffer(self, *, stable_frames: int) -> WaitCondition:
        state = {"last_key": None, "last_frame": None, "stable_for": 0}
        latest: dict[str, FramebufferSnapshot | None] = {"snapshot": None}

        def predicate(machine: Machine) -> FramebufferSnapshot | None:
            snapshot = machine.capture_framebuffer()
            latest["snapshot"] = snapshot
            key = _framebuffer_key(snapshot)
            if stable_frames == 0:
                return snapshot
            if state["last_key"] is None:
                state["last_key"] = key
                state["last_frame"] = snapshot.frame.frame_number
                return None
            frame_delta = max(0, snapshot.frame.frame_number - int(state["last_frame"]))
            if key == state["last_key"]:
                state["stable_for"] = int(state["stable_for"]) + frame_delta
                if int(state["stable_for"]) >= stable_frames:
                    return snapshot
            else:
                state["last_key"] = key
                state["stable_for"] = 0
            state["last_frame"] = snapshot.frame.frame_number
            return None

        return WaitCondition(
            self._machine,
            predicate,
            description="stable framebuffer",
            final_observation=lambda: latest["snapshot"],
            final_observation_summary=_summarize_observation,
        )

    def event_type(
        self,
        event_type: int | EventType,
        *,
        after_sequence: int = 0,
    ) -> WaitCondition:
        expected = int(event_type)
        state = {"after_sequence": after_sequence}
        latest: dict[str, AutomationEvent | None] = {"event": None}

        def predicate(machine: Machine) -> AutomationEvent | None:
            while True:
                event = machine.poll_event(int(state["after_sequence"]))
                if event is None:
                    return None
                state["after_sequence"] = event.sequence_number
                latest["event"] = event
                if event.event_type == expected:
                    return event
            return None

        return WaitCondition(
            self._machine,
            predicate,
            description=f"event type {expected}",
            final_observation=lambda: latest["event"],
            final_observation_summary=_summarize_observation,
        )

    def screen_changed(self, *, after_sequence: int = 0) -> WaitCondition:
        return self.event_type(EventType.SCREEN_CHANGED, after_sequence=after_sequence)

    def text_changed(self, *, after_sequence: int = 0) -> WaitCondition:
        return self.event_type(EventType.TEXT_CHANGED, after_sequence=after_sequence)

    def media_activity(self, *, after_sequence: int = 0) -> WaitCondition:
        return self.event_type(EventType.MEDIA_ACTIVITY, after_sequence=after_sequence)

    def memory_value(self, address: int, value: bytes | int) -> WaitCondition:
        expected = bytes([value]) if isinstance(value, int) else bytes(value)
        latest: dict[str, bytes | None] = {"value": None}

        def predicate(machine: Machine) -> bytes | None:
            current = machine.read_memory(address, len(expected))
            latest["value"] = current
            return current if current == expected else None

        return WaitCondition(
            self._machine,
            predicate,
            description=f"memory 0x{address:X} == {expected.hex()}",
            final_observation=lambda: latest["value"],
            final_observation_summary=_summarize_observation,
        )

    def program_counter(self, program_counter: int) -> WaitCondition:
        expected = int(program_counter)
        latest: dict[str, int | None] = {"program_counter": None}

        def predicate(machine: Machine) -> int | None:
            current = machine.read_program_counter()
            latest["program_counter"] = current
            return current if current == expected else None

        return WaitCondition(
            self._machine,
            predicate,
            description=f"program counter == 0x{expected:X}",
            final_observation=lambda: latest["program_counter"],
            final_observation_summary=_summarize_observation,
        )

    def breakpoint(self, *, program_counter: int | None = None) -> WaitCondition:
        latest: dict[str, FrameMetadata | None] = {"metadata": None}
        expected_pc = int(program_counter) if program_counter is not None else None

        def predicate(machine: Machine) -> FrameMetadata | None:
            metadata = machine.read_frame_metadata()
            latest["metadata"] = metadata
            if metadata.execution_state != 2:
                return None
            if expected_pc is not None and machine.read_program_counter() != expected_pc:
                return None
            return metadata

        description = "debug pause"
        if expected_pc is not None:
            description = f"debug pause at program counter 0x{expected_pc:04X}"
        return WaitCondition(
            self._machine,
            predicate,
            description=description,
            final_observation=lambda: latest["metadata"],
            final_observation_summary=_summarize_observation,
        )

    def watchpoint(self, *, program_counter: int | None = None) -> WaitCondition:
        return self.breakpoint(program_counter=program_counter)


class WaitControl:
    def __init__(self, machine: "Machine") -> None:
        self._machine = machine

    def any(self, *conditions: WaitCondition) -> WaitCondition:
        if not conditions:
            raise ValueError("at least one condition is required")

        def predicate(machine: Machine):
            for condition in conditions:
                result = condition._predicate(machine)
                if result is not None:
                    return result
            return None

        return WaitCondition(
            self._machine,
            predicate,
            description="any condition",
        )

    def all(self, *conditions: WaitCondition) -> WaitCondition:
        if not conditions:
            raise ValueError("at least one condition is required")

        def predicate(machine: Machine):
            results = []
            for condition in conditions:
                result = condition._predicate(machine)
                if result is None:
                    return None
                results.append(result)
            return tuple(results)

        return WaitCondition(
            self._machine,
            predicate,
            description="all conditions",
        )

    def screen_contains(
        self,
        text: str,
        *,
        region_id: str | None = None,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> TextGridSnapshot:
        return (
            self._machine.conditions.screen_contains(text, region_id=region_id)
            .timeout_frames(timeout_frames)
            .step_frames(step_frames)
            .run()
        )

    def text_disappears(
        self,
        text: str,
        *,
        region_id: str | None = None,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> TextGridSnapshot:
        return (
            self._machine.conditions.text_disappears(text, region_id=region_id)
            .timeout_frames(timeout_frames)
            .step_frames(step_frames)
            .run()
        )

    def screen_changed(
        self,
        *,
        after_sequence: int = 0,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> AutomationEvent:
        return (
            self._machine.conditions.screen_changed(after_sequence=after_sequence)
            .timeout_frames(timeout_frames)
            .step_frames(step_frames)
            .run()
        )

    def text_changed(
        self,
        *,
        after_sequence: int = 0,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> AutomationEvent:
        return (
            self._machine.conditions.text_changed(after_sequence=after_sequence)
            .timeout_frames(timeout_frames)
            .step_frames(step_frames)
            .run()
        )

    def media_activity(
        self,
        *,
        after_sequence: int = 0,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> AutomationEvent:
        return (
            self._machine.conditions.media_activity(after_sequence=after_sequence)
            .timeout_frames(timeout_frames)
            .step_frames(step_frames)
            .run()
        )

    def memory_value(
        self,
        address: int,
        value: bytes | int,
        *,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> bytes:
        return (
            self._machine.conditions.memory_value(address, value)
            .timeout_frames(timeout_frames)
            .timeout_cycles(timeout_cycles)
            .timeout_emulated_time_ns(timeout_emulated_time_ns)
            .step_frames(step_frames)
            .run()
        )

    def program_counter(
        self,
        program_counter: int,
        *,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> int:
        return (
            self._machine.conditions.program_counter(program_counter)
            .timeout_frames(timeout_frames)
            .timeout_cycles(timeout_cycles)
            .timeout_emulated_time_ns(timeout_emulated_time_ns)
            .step_frames(step_frames)
            .run()
        )

    def breakpoint(
        self,
        *,
        program_counter: int | None = None,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> FrameMetadata:
        return (
            self._machine.conditions.breakpoint(program_counter=program_counter)
            .timeout_frames(timeout_frames)
            .timeout_cycles(timeout_cycles)
            .timeout_emulated_time_ns(timeout_emulated_time_ns)
            .step_frames(step_frames)
            .run()
        )

    def watchpoint(
        self,
        *,
        program_counter: int | None = None,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> FrameMetadata:
        return (
            self._machine.conditions.watchpoint(program_counter=program_counter)
            .timeout_frames(timeout_frames)
            .timeout_cycles(timeout_cycles)
            .timeout_emulated_time_ns(timeout_emulated_time_ns)
            .step_frames(step_frames)
            .run()
        )


class EventIterator:
    def __init__(self, machine: "Machine", after_sequence: int = 0) -> None:
        self._machine = machine
        self._after_sequence = after_sequence

    @property
    def after_sequence(self) -> int:
        return self._after_sequence

    def poll(self) -> AutomationEvent | None:
        event = self._machine.poll_event(self._after_sequence)
        if event is not None:
            self._after_sequence = event.sequence_number
        return event

    def collect_available(self) -> list[AutomationEvent]:
        events: list[AutomationEvent] = []
        while True:
            event = self.poll()
            if event is None:
                return events
            events.append(event)

    def dispatch_available(self, callback: Callable[[AutomationEvent], Any]) -> int:
        count = 0
        while True:
            event = self.poll()
            if event is None:
                return count
            callback(event)
            count += 1

    def __iter__(self) -> "EventIterator":
        return self

    def __next__(self) -> AutomationEvent:
        event = self.poll()
        if event is None:
            raise StopIteration
        return event


class AsyncEventIterator:
    def __init__(
        self,
        machine: "Machine",
        after_sequence: int = 0,
        *,
        step_frames: int = 1,
        idle_sleep_seconds: float = 0.0,
    ) -> None:
        if step_frames <= 0:
            raise ValueError("step_frames must be positive")
        self._machine = machine
        self._after_sequence = after_sequence
        self._step_frames = step_frames
        self._idle_sleep_seconds = idle_sleep_seconds

    @property
    def after_sequence(self) -> int:
        return self._after_sequence

    async def poll(self) -> AutomationEvent | None:
        event = self._machine.poll_event(self._after_sequence)
        if event is not None:
            self._after_sequence = event.sequence_number
        return event

    async def recv(
        self,
        *,
        timeout_frames: int | None = None,
    ) -> AutomationEvent:
        if timeout_frames is not None and timeout_frames < 0:
            raise ValueError("timeout_frames must be non-negative")
        frames_elapsed = 0
        while True:
            event = await self.poll()
            if event is not None:
                return event
            if timeout_frames is not None and frames_elapsed >= timeout_frames:
                raise AutomationTimeoutError("async event", frames_elapsed)
            self._machine.run_frames(self._step_frames)
            frames_elapsed += self._step_frames
            await asyncio.sleep(self._idle_sleep_seconds)

    async def collect_available(self) -> list[AutomationEvent]:
        events: list[AutomationEvent] = []
        while True:
            event = await self.poll()
            if event is None:
                return events
            events.append(event)

    async def dispatch_available(self, callback: Callable[[AutomationEvent], Any]) -> int:
        count = 0
        while True:
            event = await self.poll()
            if event is None:
                return count
            callback(event)
            count += 1

    def __aiter__(self) -> "AsyncEventIterator":
        return self

    async def __anext__(self) -> AutomationEvent:
        event = await self.poll()
        if event is None:
            raise StopAsyncIteration
        return event


class InputSequence:
    def __init__(self, machine: "Machine") -> None:
        self._machine = machine
        self._steps: list[InputLogStep] = []

    def key_down(
        self,
        key_id: str,
        *,
        device_id: str | None = None,
        timing: InputTiming | None = None,
    ) -> "InputSequence":
        timing = timing or InputTiming.immediate()
        self._steps.append(
            InputLogStep(
                kind="key",
                target_id=key_id,
                action="press",
                device_id=device_id or "",
                timing=timing,
            )
        )
        return self

    def key_up(
        self,
        key_id: str,
        *,
        device_id: str | None = None,
        timing: InputTiming | None = None,
    ) -> "InputSequence":
        timing = timing or InputTiming.immediate()
        self._steps.append(
            InputLogStep(
                kind="key",
                target_id=key_id,
                action="release",
                device_id=device_id or "",
                timing=timing,
            )
        )
        return self

    def controller_down(
        self,
        control_id: str,
        *,
        device_id: str | None = None,
        timing: InputTiming | None = None,
    ) -> "InputSequence":
        timing = timing or InputTiming.immediate()
        self._steps.append(
            InputLogStep(
                kind="controller_button",
                target_id=control_id,
                action="press",
                device_id=device_id or "",
                timing=timing,
            )
        )
        return self

    def controller_up(
        self,
        control_id: str,
        *,
        device_id: str | None = None,
        timing: InputTiming | None = None,
    ) -> "InputSequence":
        timing = timing or InputTiming.immediate()
        self._steps.append(
            InputLogStep(
                kind="controller_button",
                target_id=control_id,
                action="release",
                device_id=device_id or "",
                timing=timing,
            )
        )
        return self

    def tap_key(
        self,
        key_id: str,
        *,
        device_id: str | None = None,
        press_timing: InputTiming | None = None,
        release_timing: InputTiming | None = None,
        preset: InputTapPreset | None = None,
    ) -> "InputSequence":
        if preset is not None:
            press_timing = preset.press_timing
            release_timing = preset.release_timing
        self.key_down(key_id, device_id=device_id, timing=press_timing)
        self.key_up(key_id, device_id=device_id, timing=release_timing)
        return self

    def type_text(
        self,
        text: str,
        *,
        device_id: str | None = None,
        preset: InputTapPreset | None = None,
    ) -> "InputSequence":
        preset = preset or InputTapPreset.immediate()
        for char in text:
            mapping = self._machine._character_mapping_for_char(char, device_id=device_id)
            if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_SHIFT:
                if not mapping.shift_key_id:
                    raise ValueError(f"no shift key mapping for character {char!r}")
                self.key_down(mapping.shift_key_id, device_id=device_id)
            if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_CTRL:
                if not mapping.ctrl_key_id:
                    raise ValueError(f"no ctrl key mapping for character {char!r}")
                self.key_down(mapping.ctrl_key_id, device_id=device_id)
            if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_ALT:
                if not mapping.alt_key_id:
                    raise ValueError(f"no alt key mapping for character {char!r}")
                self.key_down(mapping.alt_key_id, device_id=device_id)
            if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_META:
                if not mapping.meta_key_id:
                    raise ValueError(f"no meta key mapping for character {char!r}")
                self.key_down(mapping.meta_key_id, device_id=device_id)
            self.tap_key(mapping.key_id, device_id=device_id, preset=preset)
            if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_META:
                self.key_up(mapping.meta_key_id, device_id=device_id)
            if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_ALT:
                self.key_up(mapping.alt_key_id, device_id=device_id)
            if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_CTRL:
                self.key_up(mapping.ctrl_key_id, device_id=device_id)
            if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_SHIFT:
                self.key_up(mapping.shift_key_id, device_id=device_id)
        return self

    def tap_controller(
        self,
        control_id: str,
        *,
        device_id: str | None = None,
        press_timing: InputTiming | None = None,
        release_timing: InputTiming | None = None,
        preset: InputTapPreset | None = None,
    ) -> "InputSequence":
        if preset is not None:
            press_timing = preset.press_timing
            release_timing = preset.release_timing
        self.controller_down(control_id, device_id=device_id, timing=press_timing)
        self.controller_up(control_id, device_id=device_id, timing=release_timing)
        return self

    def wait_frames(self, frame_count: int) -> "InputSequence":
        if frame_count < 0:
            raise ValueError("frame_count must be non-negative")
        self._steps.append(InputLogStep(kind="wait_frames", frame_count=frame_count))
        return self

    def release_all_keys(self, *, device_id: str | None = None) -> "InputSequence":
        self._steps.append(
            InputLogStep(kind="release_all_keys", action="release", device_id=device_id or "")
        )
        return self

    def release_all_controller_buttons(self, *, device_id: str | None = None) -> "InputSequence":
        self._steps.append(
            InputLogStep(
                kind="release_all_controller_buttons",
                action="release",
                device_id=device_id or "",
            )
        )
        return self

    def steps(self) -> tuple[InputLogStep, ...]:
        return tuple(self._steps)

    def to_log_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "kind": step.kind,
                "target_id": step.target_id,
                "action": step.action,
                "device_id": step.device_id,
                "timing": {"kind": step.timing.kind, "value": step.timing.value},
                "frame_count": step.frame_count,
            }
            for step in self._steps
        ]

    def to_jsonl(self) -> str:
        lines = []
        for step in self.to_log_payload():
            lines.append(json.dumps(step, separators=(",", ":"), sort_keys=True))
        return "".join(f"{line}\n" for line in lines)

    @classmethod
    def from_log_payload(
        cls, machine: "Machine", payload: list[dict[str, Any]]
    ) -> "InputSequence":
        sequence = cls(machine)
        for step in payload:
            kind = str(step.get("kind", ""))
            timing_payload = step.get("timing", {})
            if not isinstance(timing_payload, dict):
                raise ValueError("input log timing must be an object")
            timing = InputTiming(
                int(timing_payload.get("kind", 0)),
                int(timing_payload.get("value", 0)),
            )
            target_id = str(step.get("target_id", ""))
            action = str(step.get("action", ""))
            device_id = str(step.get("device_id", "")) or None
            frame_count = int(step.get("frame_count", 0))
            if kind == "key":
                if action == "press":
                    sequence.key_down(target_id, device_id=device_id, timing=timing)
                elif action == "release":
                    sequence.key_up(target_id, device_id=device_id, timing=timing)
                else:
                    raise ValueError(f"unsupported key action in input log: {action}")
            elif kind == "controller_button":
                if action == "press":
                    sequence.controller_down(target_id, device_id=device_id, timing=timing)
                elif action == "release":
                    sequence.controller_up(target_id, device_id=device_id, timing=timing)
                else:
                    raise ValueError(
                        f"unsupported controller action in input log: {action}"
                    )
            elif kind == "wait_frames":
                sequence.wait_frames(frame_count)
            elif kind == "release_all_keys":
                sequence.release_all_keys(device_id=device_id)
            elif kind == "release_all_controller_buttons":
                sequence.release_all_controller_buttons(device_id=device_id)
            else:
                raise ValueError(f"unsupported input log step kind: {kind}")
        return sequence

    @classmethod
    def from_jsonl(cls, machine: "Machine", text: str) -> "InputSequence":
        payload: list[dict[str, Any]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("input log line must decode to an object")
            payload.append(item)
        return cls.from_log_payload(machine, payload)

    def play(self) -> None:
        for step in self._steps:
            if step.kind == "key":
                self._machine.key(
                    step.target_id,
                    action=step.action,
                    device_id=step.device_id or None,
                    timing_kind=step.timing.kind,
                    timing_value=step.timing.value,
                )
            elif step.kind == "controller_button":
                self._machine.controller_button(
                    step.target_id,
                    action=step.action,
                    device_id=step.device_id or None,
                    timing_kind=step.timing.kind,
                    timing_value=step.timing.value,
                )
            elif step.kind == "wait_frames":
                self._machine.run_frames(step.frame_count)
            elif step.kind == "release_all_keys":
                self._machine.release_all_keys(device_id=step.device_id or None)
            elif step.kind == "release_all_controller_buttons":
                self._machine.release_all_controller_buttons(
                    device_id=step.device_id or None
                )
            else:
                raise ValueError(f"unsupported input step kind: {step.kind}")

    run = play


def _decode(value: bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace")


def _codepoint_to_text(codepoint: int) -> str:
    if codepoint == 0:
        return ""
    try:
        return chr(codepoint)
    except ValueError:
        return "\ufffd"


def _copy_text_cell(raw: _TextCell) -> TextCell:
    return TextCell(
        native_code=int(raw.native_code),
        unicode_codepoint=int(raw.unicode_codepoint),
        text=_codepoint_to_text(int(raw.unicode_codepoint)),
        glyph_id=_decode(raw.glyph_id),
        foreground_color=int(raw.foreground_color),
        background_color=int(raw.background_color),
        attribute_flags=int(raw.attribute_flags),
        charset_id=_decode(raw.charset_id),
        source_address=int(raw.source_address),
        confidence=int(raw.confidence),
    )


def _copy_text_deltas(raw: _AutomationEvent) -> tuple[TextDelta, ...]:
    deltas: list[TextDelta] = []
    if raw.text_deltas:
        for index in range(int(raw.text_delta_count)):
            delta = raw.text_deltas[index]
            deltas.append(
                TextDelta(
                    x=int(delta.x),
                    y=int(delta.y),
                    before=_copy_text_cell(delta.before),
                    after=_copy_text_cell(delta.after),
                )
            )
    return tuple(deltas)


def _encode_optional(value: str | None) -> bytes | None:
    return value.encode("utf-8") if value is not None else None


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    body = chunk_type + payload
    return (
        struct.pack(">I", len(payload))
        + body
        + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    )


def _summarize_observation(observation: Any) -> str:
    if observation is None:
        return ""
    if isinstance(observation, TextGridSnapshot):
        plain = observation.plain.replace("\n", "\\n")
        return f"text frame={observation.frame_number} plain={plain!r}"
    if isinstance(observation, FrameMetadata):
        return (
            f"frame={observation.frame_number} "
            f"cycles={observation.emulated_cycles} "
            f"state={observation.execution_state}"
        )
    if isinstance(observation, FramebufferSnapshot):
        return (
            f"framebuffer frame={observation.frame.frame_number} "
            f"size={observation.width}x{observation.height} "
            f"format={observation.pixel_format}"
        )
    if isinstance(observation, AutomationEvent):
        return (
            f"event sequence={observation.sequence_number} "
            f"type={EventType(observation.event_type).name.lower()} "
            f"frame={observation.frame.frame_number}"
        )
    if isinstance(observation, (bytes, bytearray)):
        return bytes(observation).hex()
    if isinstance(observation, int):
        return f"0x{observation:X}"
    return repr(observation)


def _text_grid_key(snapshot: TextGridSnapshot) -> tuple:
    return (
        snapshot.region_id,
        snapshot.columns,
        snapshot.rows,
        snapshot.row_stride,
        snapshot.plain,
        snapshot.cells,
    )


def _framebuffer_key(snapshot: FramebufferSnapshot) -> tuple:
    return (
        snapshot.width,
        snapshot.height,
        snapshot.stride_bytes,
        snapshot.pixel_format,
        snapshot.visible_area,
        snapshot.pixel_aspect_numerator,
        snapshot.pixel_aspect_denominator,
        snapshot.pixels,
    )


def _reset_kind(kind: str | int) -> int:
    if isinstance(kind, int):
        return kind
    values = {
        "cold": EMU_AUTOMATION_RESET_COLD,
        "warm": EMU_AUTOMATION_RESET_WARM,
    }
    try:
        return values[kind]
    except KeyError as exc:
        raise ValueError(f"unknown reset kind: {kind}") from exc


def _input_action(action: str | int) -> int:
    if isinstance(action, int):
        return action
    values = {
        "release": EMU_AUTOMATION_INPUT_RELEASE,
        "press": EMU_AUTOMATION_INPUT_PRESS,
    }
    try:
        return values[action]
    except KeyError as exc:
        raise ValueError(f"unknown input action: {action}") from exc


class AutomationLibrary:
    def __init__(self, library: str | Path | ctypes.CDLL) -> None:
        self._lib = library if isinstance(library, ctypes.CDLL) else ctypes.CDLL(str(library))
        self._bind()
        version = int(self._lib.emu_automation_abi_version())
        if version != EMU_AUTOMATION_ABI_VERSION:
            raise RuntimeError(
                f"Unsupported automation ABI version {version}; "
                f"expected {EMU_AUTOMATION_ABI_VERSION}"
            )

    @property
    def cdll(self) -> ctypes.CDLL:
        return self._lib

    def machine(self, handle: int | ctypes.c_void_p, *, owned: bool = True) -> "Machine":
        pointer = ctypes.c_void_p(handle) if isinstance(handle, int) else handle
        if not pointer or not pointer.value:
            raise ValueError("machine handle is null")
        return Machine(self, pointer, owned=owned)

    def create_machine(
        self,
        create_symbol: str = "emu_automation_create",
        *,
        owned: bool = True,
    ) -> "Machine":
        create = getattr(self._lib, create_symbol)
        create.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        create.restype = ctypes.c_int
        handle = ctypes.c_void_p()
        self.check(create(ctypes.byref(handle)), create_symbol)
        return self.machine(handle, owned=owned)

    def result_name(self, result: int) -> str:
        return _decode(self._lib.emu_automation_result_name(int(result)))

    def check(self, result: int, operation: str) -> None:
        if int(result) != EMU_AUTOMATION_OK:
            raise AutomationError(operation, int(result), self.result_name(int(result)))

    def _bind(self) -> None:
        lib = self._lib
        lib.emu_automation_abi_version.argtypes = []
        lib.emu_automation_abi_version.restype = ctypes.c_uint32
        lib.emu_automation_result_name.argtypes = [ctypes.c_int]
        lib.emu_automation_result_name.restype = ctypes.c_char_p
        lib.emu_automation_machine_destroy.argtypes = [ctypes.c_void_p]
        lib.emu_automation_machine_destroy.restype = None
        lib.emu_automation_machine_describe.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_MachineDescriptor),
        ]
        lib.emu_automation_machine_describe.restype = ctypes.c_int
        lib.emu_automation_machine_capabilities.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_Capabilities),
        ]
        lib.emu_automation_machine_capabilities.restype = ctypes.c_int
        lib.emu_automation_machine_character_mapping_count.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        lib.emu_automation_machine_character_mapping_count.restype = ctypes.c_int
        lib.emu_automation_machine_character_mapping_descriptor.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(_CharacterMappingDescriptor),
        ]
        lib.emu_automation_machine_character_mapping_descriptor.restype = ctypes.c_int
        lib.emu_automation_machine_pause.argtypes = [ctypes.c_void_p]
        lib.emu_automation_machine_pause.restype = ctypes.c_int
        lib.emu_automation_machine_resume.argtypes = [ctypes.c_void_p]
        lib.emu_automation_machine_resume.restype = ctypes.c_int
        lib.emu_automation_machine_reset.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.emu_automation_machine_reset.restype = ctypes.c_int
        lib.emu_automation_machine_step_frame.argtypes = [ctypes.c_void_p]
        lib.emu_automation_machine_step_frame.restype = ctypes.c_int
        lib.emu_automation_machine_run_frames.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
        lib.emu_automation_machine_run_frames.restype = ctypes.c_int
        lib.emu_automation_screen_framebuffer.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_FramebufferSnapshot),
        ]
        lib.emu_automation_screen_framebuffer.restype = ctypes.c_int
        lib.emu_automation_framebuffer_release.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_FramebufferSnapshot),
        ]
        lib.emu_automation_framebuffer_release.restype = None
        lib.emu_automation_screen_text_view_count.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        lib.emu_automation_screen_text_view_count.restype = ctypes.c_int
        lib.emu_automation_screen_text_view_descriptor.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(_TextViewDescriptor),
        ]
        lib.emu_automation_screen_text_view_descriptor.restype = ctypes.c_int
        lib.emu_automation_screen_text_grid.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.POINTER(_TextGridSnapshot),
        ]
        lib.emu_automation_screen_text_grid.restype = ctypes.c_int
        lib.emu_automation_memory_read.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        lib.emu_automation_memory_read.restype = ctypes.c_int
        lib.emu_automation_memory_write.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.c_size_t,
        ]
        lib.emu_automation_memory_write.restype = ctypes.c_int
        lib.emu_automation_execution_program_counter.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint64),
        ]
        lib.emu_automation_execution_program_counter.restype = ctypes.c_int
        lib.emu_automation_execution_frame_metadata.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_FrameMetadata),
        ]
        lib.emu_automation_execution_frame_metadata.restype = ctypes.c_int
        lib.emu_automation_execution_current_instruction.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_InstructionInfo),
        ]
        lib.emu_automation_execution_current_instruction.restype = ctypes.c_int
        lib.emu_automation_register_count.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        lib.emu_automation_register_count.restype = ctypes.c_int
        lib.emu_automation_register_read.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_RegisterValue),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        lib.emu_automation_register_read.restype = ctypes.c_int
        lib.emu_automation_register_write.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint64,
        ]
        lib.emu_automation_register_write.restype = ctypes.c_int
        lib.emu_automation_breakpoint_set.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.c_uint8,
        ]
        lib.emu_automation_breakpoint_set.restype = ctypes.c_int
        lib.emu_automation_text_grid_release.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_TextGridSnapshot),
        ]
        lib.emu_automation_text_grid_release.restype = None
        lib.emu_automation_input_key.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_KeyEvent),
        ]
        lib.emu_automation_input_key.restype = ctypes.c_int
        lib.emu_automation_input_controller_button.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_ControllerButtonEvent),
        ]
        lib.emu_automation_input_controller_button.restype = ctypes.c_int
        lib.emu_automation_events_poll.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.POINTER(_AutomationEvent),
        ]
        lib.emu_automation_events_poll.restype = ctypes.c_int
        lib.emu_automation_events_dispatch_available.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_size_t,
            _EventCallback,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        lib.emu_automation_events_dispatch_available.restype = ctypes.c_int
        lib.emu_automation_events_dispatch_matching.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_int,
            ctypes.c_size_t,
            _EventCallback,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        lib.emu_automation_events_dispatch_matching.restype = ctypes.c_int
        lib.emu_automation_subscription_create.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_uint64,
            _EventCallback,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        lib.emu_automation_subscription_create.restype = ctypes.c_int
        lib.emu_automation_subscription_dispatch_available.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        lib.emu_automation_subscription_dispatch_available.restype = ctypes.c_int
        lib.emu_automation_subscription_after_sequence.argtypes = [ctypes.c_void_p]
        lib.emu_automation_subscription_after_sequence.restype = ctypes.c_uint64
        lib.emu_automation_subscription_set_after_sequence.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
        ]
        lib.emu_automation_subscription_set_after_sequence.restype = ctypes.c_int
        lib.emu_automation_subscription_destroy.argtypes = [ctypes.c_void_p]
        lib.emu_automation_subscription_destroy.restype = None
        lib.emu_automation_event_release.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_AutomationEvent),
        ]
        lib.emu_automation_event_release.restype = None


def load_library(library: str | Path | ctypes.CDLL) -> AutomationLibrary:
    return AutomationLibrary(library)


def create(
    library: str | Path | ctypes.CDLL,
    create_symbol: str = "emu_automation_create",
    *,
    owned: bool = True,
) -> "Machine":
    return load_library(library).create_machine(create_symbol, owned=owned)


def attach(
    library: str | Path | ctypes.CDLL,
    handle: int | ctypes.c_void_p,
    *,
    owned: bool = True,
) -> "Machine":
    return load_library(library).machine(handle, owned=owned)


class Machine:
    def __init__(
        self,
        library: AutomationLibrary,
        handle: ctypes.c_void_p,
        *,
        owned: bool = True,
    ) -> None:
        self._library = library
        self._handle = handle
        self._owned = owned
        self._closed = False
        self._pressed_keys: OrderedDict[tuple[str | None, str], None] = OrderedDict()
        self._pressed_controller_buttons: OrderedDict[tuple[str | None, str], None] = OrderedDict()
        self.keyboard = KeyboardInput(self)
        self.controller = ControllerInput(self)
        self.run = RunControl(self)
        self.screen = ScreenView(self)
        self.inspect = InspectionView(self)
        self.debug = DebugView(self)
        self.conditions = ConditionFactory(self)
        self.wait = WaitControl(self)

    def __enter__(self) -> "Machine":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    @property
    def handle(self) -> ctypes.c_void_p:
        if self._closed:
            raise RuntimeError("machine is closed")
        return self._handle

    def close(self) -> None:
        if self._closed:
            return
        if self._owned and self._handle and self._handle.value:
            self._library.cdll.emu_automation_machine_destroy(self._handle)
        self._closed = True
        self._handle = ctypes.c_void_p()

    def describe(self) -> MachineDescriptor:
        raw = _MachineDescriptor()
        self._library.check(
            self._library.cdll.emu_automation_machine_describe(self.handle, ctypes.byref(raw)),
            "emu_automation_machine_describe",
        )
        return MachineDescriptor(
            machine_id=_decode(raw.machine_id),
            system_id=_decode(raw.system_id),
            model_id=_decode(raw.model_id),
            region=_decode(raw.region),
            video_standard=_decode(raw.video_standard),
            adapter_version=_decode(raw.adapter_version),
            configured_memory_bytes=int(raw.configured_memory_bytes),
            capabilities=Capabilities(feature_bits=int(raw.capabilities.feature_bits)),
        )

    def capabilities(self) -> Capabilities:
        raw = _Capabilities()
        self._library.check(
            self._library.cdll.emu_automation_machine_capabilities(
                self.handle,
                ctypes.byref(raw),
            ),
            "emu_automation_machine_capabilities",
        )
        return Capabilities(feature_bits=int(raw.feature_bits))

    def character_mappings(self) -> list[CharacterMappingDescriptor]:
        count = ctypes.c_size_t()
        self._library.check(
            self._library.cdll.emu_automation_machine_character_mapping_count(
                self.handle,
                ctypes.byref(count),
            ),
            "emu_automation_machine_character_mapping_count",
        )
        mappings: list[CharacterMappingDescriptor] = []
        for index in range(int(count.value)):
            raw = _CharacterMappingDescriptor()
            self._library.check(
                self._library.cdll.emu_automation_machine_character_mapping_descriptor(
                    self.handle,
                    index,
                    ctypes.byref(raw),
                ),
                "emu_automation_machine_character_mapping_descriptor",
            )
            mappings.append(
                CharacterMappingDescriptor(
                    device_id=_decode(raw.device_id),
                    unicode_codepoint=int(raw.unicode_codepoint),
                    native_code=int(raw.native_code),
                    key_id=_decode(raw.key_id),
                    required_modifier_bits=int(raw.required_modifier_bits),
                    shift_key_id=_decode(raw.shift_key_id),
                    ctrl_key_id=_decode(raw.ctrl_key_id),
                    alt_key_id=_decode(raw.alt_key_id),
                    meta_key_id=_decode(raw.meta_key_id),
                )
            )
        return mappings

    def _character_mapping_for_char(
        self,
        char: str,
        *,
        device_id: str | None = None,
    ) -> CharacterMappingDescriptor:
        if len(char) != 1:
            raise ValueError("type_text expects single characters during mapping lookup")
        codepoint = ord(char)
        for mapping in self.character_mappings():
            if mapping.unicode_codepoint != codepoint:
                continue
            if device_id is not None and mapping.device_id not in {"", device_id}:
                continue
            return mapping
        raise ValueError(f"no character mapping for {char!r}")

    def pause(self) -> None:
        self._library.check(
            self._library.cdll.emu_automation_machine_pause(self.handle),
            "emu_automation_machine_pause",
        )

    def resume(self) -> None:
        self._library.check(
            self._library.cdll.emu_automation_machine_resume(self.handle),
            "emu_automation_machine_resume",
        )

    def reset(self, kind: str | int = "cold") -> None:
        self._library.check(
            self._library.cdll.emu_automation_machine_reset(self.handle, _reset_kind(kind)),
            "emu_automation_machine_reset",
        )

    def step_frame(self) -> None:
        self._library.check(
            self._library.cdll.emu_automation_machine_step_frame(self.handle),
            "emu_automation_machine_step_frame",
        )

    def run_frames(self, frame_count: int) -> None:
        if frame_count < 0:
            raise ValueError("frame_count must be non-negative")
        self._library.check(
            self._library.cdll.emu_automation_machine_run_frames(
                self.handle,
                ctypes.c_uint64(frame_count),
            ),
            "emu_automation_machine_run_frames",
        )

    def key(
        self,
        key_id: str,
        *,
        action: str | int = "press",
        device_id: str | None = None,
        timing_kind: int = EMU_AUTOMATION_TIMING_IMMEDIATE,
        timing_value: int = 0,
    ) -> None:
        event = _KeyEvent(
            struct_size=ctypes.sizeof(_KeyEvent),
            struct_version=EMU_AUTOMATION_STRUCT_VERSION,
            device_id=_encode_optional(device_id),
            key_id=key_id.encode("utf-8"),
            action=_input_action(action),
            timing=_Timing(kind=timing_kind, value=timing_value),
        )
        self._library.check(
            self._library.cdll.emu_automation_input_key(self.handle, ctypes.byref(event)),
            "emu_automation_input_key",
        )
        token = (device_id, key_id)
        if _input_action(action) == EMU_AUTOMATION_INPUT_PRESS:
            self._pressed_keys[token] = None
        else:
            self._pressed_keys.pop(token, None)

    def tap_key(
        self,
        key_id: str,
        *,
        device_id: str | None = None,
        preset: InputTapPreset | None = None,
    ) -> None:
        preset = preset or InputTapPreset.immediate()
        self.key(
            key_id,
            action="press",
            device_id=device_id,
            timing_kind=preset.press_timing.kind,
            timing_value=preset.press_timing.value,
        )
        self.key(
            key_id,
            action="release",
            device_id=device_id,
            timing_kind=preset.release_timing.kind,
            timing_value=preset.release_timing.value,
        )

    def type_text(
        self,
        text: str,
        *,
        device_id: str | None = None,
        preset: InputTapPreset | None = None,
    ) -> None:
        preset = preset or InputTapPreset.immediate()
        for char in text:
            mapping = self._character_mapping_for_char(char, device_id=device_id)
            pressed_modifiers: list[str] = []
            try:
                if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_SHIFT:
                    if not mapping.shift_key_id:
                        raise ValueError(f"no shift key mapping for character {char!r}")
                    self.key(mapping.shift_key_id, action="press", device_id=device_id)
                    pressed_modifiers.append(mapping.shift_key_id)
                if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_CTRL:
                    if not mapping.ctrl_key_id:
                        raise ValueError(f"no ctrl key mapping for character {char!r}")
                    self.key(mapping.ctrl_key_id, action="press", device_id=device_id)
                    pressed_modifiers.append(mapping.ctrl_key_id)
                if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_ALT:
                    if not mapping.alt_key_id:
                        raise ValueError(f"no alt key mapping for character {char!r}")
                    self.key(mapping.alt_key_id, action="press", device_id=device_id)
                    pressed_modifiers.append(mapping.alt_key_id)
                if mapping.required_modifier_bits & EMU_AUTOMATION_KEY_MODIFIER_META:
                    if not mapping.meta_key_id:
                        raise ValueError(f"no meta key mapping for character {char!r}")
                    self.key(mapping.meta_key_id, action="press", device_id=device_id)
                    pressed_modifiers.append(mapping.meta_key_id)
                self.tap_key(mapping.key_id, device_id=device_id, preset=preset)
            finally:
                for modifier_key_id in reversed(pressed_modifiers):
                    self.key(modifier_key_id, action="release", device_id=device_id)

    def controller_button(
        self,
        control_id: str,
        *,
        action: str | int = "press",
        device_id: str | None = None,
        timing_kind: int = EMU_AUTOMATION_TIMING_IMMEDIATE,
        timing_value: int = 0,
    ) -> None:
        event = _ControllerButtonEvent(
            struct_size=ctypes.sizeof(_ControllerButtonEvent),
            struct_version=EMU_AUTOMATION_STRUCT_VERSION,
            device_id=_encode_optional(device_id),
            control_id=control_id.encode("utf-8"),
            action=_input_action(action),
            timing=_Timing(kind=timing_kind, value=timing_value),
        )
        self._library.check(
            self._library.cdll.emu_automation_input_controller_button(
                self.handle,
                ctypes.byref(event),
            ),
            "emu_automation_input_controller_button",
        )
        token = (device_id, control_id)
        if _input_action(action) == EMU_AUTOMATION_INPUT_PRESS:
            self._pressed_controller_buttons[token] = None
        else:
            self._pressed_controller_buttons.pop(token, None)

    def release_all_keys(self, *, device_id: str | None = None) -> int:
        to_release = [
            (tracked_device_id, key_id)
            for tracked_device_id, key_id in list(self._pressed_keys.keys())
            if device_id is None or tracked_device_id == device_id
        ]
        for tracked_device_id, key_id in reversed(to_release):
            self.key(key_id, action="release", device_id=tracked_device_id)
        return len(to_release)

    def release_all_controller_buttons(self, *, device_id: str | None = None) -> int:
        to_release = [
            (tracked_device_id, control_id)
            for tracked_device_id, control_id in list(self._pressed_controller_buttons.keys())
            if device_id is None or tracked_device_id == device_id
        ]
        for tracked_device_id, control_id in reversed(to_release):
            self.controller_button(control_id, action="release", device_id=tracked_device_id)
        return len(to_release)

    def tap_controller_button(
        self,
        control_id: str,
        *,
        device_id: str | None = None,
        preset: InputTapPreset | None = None,
    ) -> None:
        preset = preset or InputTapPreset.immediate()
        self.controller_button(
            control_id,
            action="press",
            device_id=device_id,
            timing_kind=preset.press_timing.kind,
            timing_value=preset.press_timing.value,
        )
        self.controller_button(
            control_id,
            action="release",
            device_id=device_id,
            timing_kind=preset.release_timing.kind,
            timing_value=preset.release_timing.value,
        )

    def poll_event(self, after_sequence: int = 0) -> AutomationEvent | None:
        raw = _AutomationEvent()
        result = int(
            self._library.cdll.emu_automation_events_poll(
                self.handle,
                ctypes.c_uint64(after_sequence),
                ctypes.byref(raw),
            )
        )
        if result == EMU_AUTOMATION_TIMEOUT:
            return None
        self._library.check(result, "emu_automation_events_poll")
        try:
            return AutomationEvent(
                sequence_number=int(raw.sequence_number),
                event_type=int(raw.event_type),
                frame=FrameMetadata(
                    frame_number=int(raw.frame.frame_number),
                    emulated_cycles=int(raw.frame.emulated_cycles),
                    emulated_time_ns=int(raw.frame.emulated_time_ns),
                    execution_state=int(raw.frame.execution_state),
                ),
                input_accepted=FrameMetadata(
                    frame_number=int(raw.input_accepted.frame_number),
                    emulated_cycles=int(raw.input_accepted.emulated_cycles),
                    emulated_time_ns=int(raw.input_accepted.emulated_time_ns),
                    execution_state=int(raw.input_accepted.execution_state),
                ),
                input_applied=FrameMetadata(
                    frame_number=int(raw.input_applied.frame_number),
                    emulated_cycles=int(raw.input_applied.emulated_cycles),
                    emulated_time_ns=int(raw.input_applied.emulated_time_ns),
                    execution_state=int(raw.input_applied.execution_state),
                ),
                device_id=_decode(raw.device_id),
                control_id=_decode(raw.control_id),
                region_id=_decode(raw.region_id),
                change_x=int(raw.change_x),
                change_y=int(raw.change_y),
                change_width=int(raw.change_width),
                change_height=int(raw.change_height),
                change_cell_count=int(raw.change_cell_count),
                message=_decode(raw.message),
                text_deltas=_copy_text_deltas(raw),
                input_action=int(raw.input_action),
                input_timing=InputTiming(int(raw.input_timing.kind), int(raw.input_timing.value)),
                previous_execution_state=int(raw.previous_execution_state),
                current_execution_state=int(raw.current_execution_state),
            )
        finally:
            self._library.cdll.emu_automation_event_release(self.handle, ctypes.byref(raw))

    def events(self, after_sequence: int = 0) -> EventIterator:
        return EventIterator(self, after_sequence)

    def drain_events(self, after_sequence: int = 0) -> list[AutomationEvent]:
        events: list[AutomationEvent] = []
        next_after_sequence = after_sequence
        while True:
            event = self.poll_event(next_after_sequence)
            if event is None:
                break
            events.append(event)
            next_after_sequence = event.sequence_number
        return events

    def subscribe(
        self,
        callback: Callable[[AutomationEvent], Any],
        *,
        event_type: int | EventType | None = None,
        after_sequence: int = 0,
    ) -> Subscription:
        def bridge(raw_event_ptr: ctypes.POINTER(_AutomationEvent), _user_data: ctypes.c_void_p) -> None:
            raw = raw_event_ptr.contents
            callback(
                AutomationEvent(
                    sequence_number=int(raw.sequence_number),
                    event_type=int(raw.event_type),
                    frame=FrameMetadata(
                        frame_number=int(raw.frame.frame_number),
                        emulated_cycles=int(raw.frame.emulated_cycles),
                        emulated_time_ns=int(raw.frame.emulated_time_ns),
                        execution_state=int(raw.frame.execution_state),
                    ),
                    input_accepted=FrameMetadata(
                        frame_number=int(raw.input_accepted.frame_number),
                        emulated_cycles=int(raw.input_accepted.emulated_cycles),
                        emulated_time_ns=int(raw.input_accepted.emulated_time_ns),
                        execution_state=int(raw.input_accepted.execution_state),
                    ),
                    input_applied=FrameMetadata(
                        frame_number=int(raw.input_applied.frame_number),
                        emulated_cycles=int(raw.input_applied.emulated_cycles),
                        emulated_time_ns=int(raw.input_applied.emulated_time_ns),
                        execution_state=int(raw.input_applied.execution_state),
                    ),
                    device_id=_decode(raw.device_id),
                    control_id=_decode(raw.control_id),
                    region_id=_decode(raw.region_id),
                    change_x=int(raw.change_x),
                    change_y=int(raw.change_y),
                    change_width=int(raw.change_width),
                    change_height=int(raw.change_height),
                    change_cell_count=int(raw.change_cell_count),
                    message=_decode(raw.message),
                    text_deltas=_copy_text_deltas(raw),
                    input_action=int(raw.input_action),
                    input_timing=InputTiming(
                        int(raw.input_timing.kind), int(raw.input_timing.value)
                    ),
                    previous_execution_state=int(raw.previous_execution_state),
                    current_execution_state=int(raw.current_execution_state),
                )
            )

        callback_fn = _EventCallback(bridge)
        handle = ctypes.c_void_p()
        self._library.check(
            self._library.cdll.emu_automation_subscription_create(
                self.handle,
                int(event_type) if event_type is not None else EMU_AUTOMATION_EVENT_NONE,
                ctypes.c_uint64(after_sequence),
                callback_fn,
                None,
                ctypes.byref(handle),
            ),
            "emu_automation_subscription_create",
        )
        return Subscription(self, handle, callback_fn)

    def async_events(
        self,
        after_sequence: int = 0,
        *,
        step_frames: int = 1,
        idle_sleep_seconds: float = 0.0,
        ) -> AsyncEventIterator:
        return AsyncEventIterator(
            self,
            after_sequence,
            step_frames=step_frames,
            idle_sleep_seconds=idle_sleep_seconds,
        )

    def dispatch_events(
        self,
        callback: Callable[[AutomationEvent], Any],
        *,
        after_sequence: int = 0,
        max_events: int = 0,
        event_type: int | EventType | None = None,
    ) -> tuple[int, int]:
        if max_events < 0:
            raise ValueError("max_events must be non-negative")

        def bridge(raw_event_ptr: ctypes.POINTER(_AutomationEvent), _user_data: ctypes.c_void_p) -> None:
            raw = raw_event_ptr.contents
            callback(
                AutomationEvent(
                    sequence_number=int(raw.sequence_number),
                    event_type=int(raw.event_type),
                    frame=FrameMetadata(
                        frame_number=int(raw.frame.frame_number),
                        emulated_cycles=int(raw.frame.emulated_cycles),
                        emulated_time_ns=int(raw.frame.emulated_time_ns),
                        execution_state=int(raw.frame.execution_state),
                    ),
                    input_accepted=FrameMetadata(
                        frame_number=int(raw.input_accepted.frame_number),
                        emulated_cycles=int(raw.input_accepted.emulated_cycles),
                        emulated_time_ns=int(raw.input_accepted.emulated_time_ns),
                        execution_state=int(raw.input_accepted.execution_state),
                    ),
                    input_applied=FrameMetadata(
                        frame_number=int(raw.input_applied.frame_number),
                        emulated_cycles=int(raw.input_applied.emulated_cycles),
                        emulated_time_ns=int(raw.input_applied.emulated_time_ns),
                        execution_state=int(raw.input_applied.execution_state),
                    ),
                    device_id=_decode(raw.device_id),
                    control_id=_decode(raw.control_id),
                    region_id=_decode(raw.region_id),
                    change_x=int(raw.change_x),
                    change_y=int(raw.change_y),
                    change_width=int(raw.change_width),
                    change_height=int(raw.change_height),
                    change_cell_count=int(raw.change_cell_count),
                    message=_decode(raw.message),
                    text_deltas=_copy_text_deltas(raw),
                    input_action=int(raw.input_action),
                    input_timing=InputTiming(
                        int(raw.input_timing.kind), int(raw.input_timing.value)
                    ),
                    previous_execution_state=int(raw.previous_execution_state),
                    current_execution_state=int(raw.current_execution_state),
                )
            )

        callback_fn = _EventCallback(bridge)
        sequence = ctypes.c_uint64(after_sequence)
        dispatch_count = ctypes.c_size_t()
        if event_type is None:
            self._library.check(
                self._library.cdll.emu_automation_events_dispatch_available(
                    self.handle,
                    ctypes.byref(sequence),
                    max_events,
                    callback_fn,
                    None,
                    ctypes.byref(dispatch_count),
                ),
                "emu_automation_events_dispatch_available",
            )
        else:
            self._library.check(
                self._library.cdll.emu_automation_events_dispatch_matching(
                    self.handle,
                    ctypes.byref(sequence),
                    int(event_type),
                    max_events,
                    callback_fn,
                    None,
                    ctypes.byref(dispatch_count),
                ),
                "emu_automation_events_dispatch_matching",
            )
        return int(sequence.value), int(dispatch_count.value)

    def sequence(self) -> InputSequence:
        return InputSequence(self)

    def record(
        self,
        sequence: InputSequence,
        *,
        after_sequence: int = 0,
    ) -> SessionRecording:
        descriptor = self.describe()
        sequence.play()
        return SessionRecording(
            header=RecordingHeader(
                machine_id=descriptor.machine_id,
                system_id=descriptor.system_id,
                model_id=descriptor.model_id,
                adapter_version=descriptor.adapter_version,
                configured_memory_bytes=descriptor.configured_memory_bytes,
            ),
            input_steps=sequence.steps(),
            events=tuple(self.drain_events(after_sequence)),
        )

    def replay_recording(
        self,
        recording: SessionRecording,
        *,
        verify_events: bool = True,
        after_sequence: int = 0,
    ) -> tuple[AutomationEvent, ...]:
        return recording.replay(
            self,
            verify_events=verify_events,
            after_sequence=after_sequence,
        )

    def capture_framebuffer(self) -> FramebufferSnapshot:
        raw = _FramebufferSnapshot()
        self._library.check(
            self._library.cdll.emu_automation_screen_framebuffer(
                self.handle,
                ctypes.byref(raw),
            ),
            "emu_automation_screen_framebuffer",
        )
        try:
            pixels = bytes()
            if raw.pixels and raw.pixel_size:
                pixels = ctypes.string_at(raw.pixels, raw.pixel_size)
            return FramebufferSnapshot(
                frame=FrameMetadata(
                    frame_number=int(raw.frame.frame_number),
                    emulated_cycles=int(raw.frame.emulated_cycles),
                    emulated_time_ns=int(raw.frame.emulated_time_ns),
                    execution_state=int(raw.frame.execution_state),
                ),
                width=int(raw.width),
                height=int(raw.height),
                stride_bytes=int(raw.stride_bytes),
                pixel_format=int(raw.pixel_format),
                visible_area=Rect(
                    x=int(raw.visible_area.x),
                    y=int(raw.visible_area.y),
                    width=int(raw.visible_area.width),
                    height=int(raw.visible_area.height),
                ),
                pixel_aspect_numerator=int(raw.pixel_aspect_numerator),
                pixel_aspect_denominator=int(raw.pixel_aspect_denominator),
                pixels=pixels,
            )
        finally:
            self._library.cdll.emu_automation_framebuffer_release(self.handle, ctypes.byref(raw))

    def read_memory(self, address: int, size: int) -> bytes:
        if size < 0:
            raise ValueError("size must be non-negative")
        if size == 0:
            return b""
        buffer = (ctypes.c_uint8 * size)()
        self._library.check(
            self._library.cdll.emu_automation_memory_read(
                self.handle,
                ctypes.c_uint64(address),
                buffer,
                ctypes.c_size_t(size),
            ),
            "emu_automation_memory_read",
        )
        return bytes(buffer)

    def write_memory(self, address: int, data: bytes | bytearray) -> None:
        payload = bytes(data)
        if not payload:
            return
        buffer = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        self._library.check(
            self._library.cdll.emu_automation_memory_write(
                self.handle,
                ctypes.c_uint64(address),
                buffer,
                ctypes.c_size_t(len(payload)),
            ),
            "emu_automation_memory_write",
        )

    def read_program_counter(self) -> int:
        value = ctypes.c_uint64()
        self._library.check(
            self._library.cdll.emu_automation_execution_program_counter(
                self.handle,
                ctypes.byref(value),
            ),
            "emu_automation_execution_program_counter",
        )
        return int(value.value)

    def read_frame_metadata(self) -> FrameMetadata:
        raw = _FrameMetadata()
        self._library.check(
            self._library.cdll.emu_automation_execution_frame_metadata(
                self.handle,
                ctypes.byref(raw),
            ),
            "emu_automation_execution_frame_metadata",
        )
        return FrameMetadata(
            frame_number=int(raw.frame_number),
            emulated_cycles=int(raw.emulated_cycles),
            emulated_time_ns=int(raw.emulated_time_ns),
            execution_state=int(raw.execution_state),
        )

    def read_current_instruction(self) -> InstructionInfo:
        raw = _InstructionInfo()
        raw.struct_size = ctypes.sizeof(_InstructionInfo)
        raw.struct_version = EMU_AUTOMATION_STRUCT_VERSION
        self._library.check(
            self._library.cdll.emu_automation_execution_current_instruction(
                self.handle,
                ctypes.byref(raw),
            ),
            "emu_automation_execution_current_instruction",
        )
        return InstructionInfo(
            address=int(raw.address),
            bytes_text=_decode(raw.bytes),
            text=_decode(raw.text),
            symbol=_decode(raw.symbol),
            has_symbol=bool(raw.has_symbol),
            is_current_ip=bool(raw.is_current_ip),
            has_breakpoint=bool(raw.has_breakpoint),
            branch_target=int(raw.branch_target),
            has_branch_target=bool(raw.has_branch_target),
            changed_since_last_step=bool(raw.changed_since_last_step),
        )

    def read_registers(self) -> tuple[RegisterValue, ...]:
        count = ctypes.c_size_t()
        self._library.check(
            self._library.cdll.emu_automation_register_count(
                self.handle,
                ctypes.byref(count),
            ),
            "emu_automation_register_count",
        )
        if count.value == 0:
            return ()
        raw_rows = (_RegisterValue * int(count.value))()
        out_count = ctypes.c_size_t()
        self._library.check(
            self._library.cdll.emu_automation_register_read(
                self.handle,
                raw_rows,
                ctypes.c_size_t(len(raw_rows)),
                ctypes.byref(out_count),
            ),
            "emu_automation_register_read",
        )
        return tuple(
            RegisterValue(
                name=_decode(raw.name),
                hex_value=_decode(raw.hex_value),
                dec_value=_decode(raw.dec_value),
                has_dec=bool(raw.has_dec),
                changed=bool(raw.changed),
            )
            for raw in raw_rows[: int(out_count.value)]
        )

    def write_register(self, register_name: str, value: int) -> None:
        self._library.check(
            self._library.cdll.emu_automation_register_write(
                self.handle,
                register_name.encode("utf-8"),
                ctypes.c_uint64(value),
            ),
            "emu_automation_register_write",
        )

    def set_breakpoint(self, address: int, *, enabled: bool = True) -> None:
        self._library.check(
            self._library.cdll.emu_automation_breakpoint_set(
                self.handle,
                ctypes.c_uint64(address),
                ctypes.c_uint8(1 if enabled else 0),
            ),
            "emu_automation_breakpoint_set",
        )

    def wait_until(
        self,
        predicate: Callable[["Machine"], T | None | bool],
        *,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
        description: str = "condition",
        final_observation: Callable[[], Any] | None = None,
        final_observation_summary: Callable[[Any], str] | None = None,
    ) -> T:
        if timeout_frames is not None and timeout_frames < 0:
            raise ValueError("timeout_frames must be non-negative")
        if timeout_cycles is not None and timeout_cycles < 0:
            raise ValueError("timeout_cycles must be non-negative")
        if timeout_emulated_time_ns is not None and timeout_emulated_time_ns < 0:
            raise ValueError("timeout_emulated_time_ns must be non-negative")
        if (
            timeout_frames is None
            and timeout_cycles is None
            and timeout_emulated_time_ns is None
        ):
            raise ValueError(
                "at least one of timeout_frames, timeout_cycles, or "
                "timeout_emulated_time_ns must be provided"
            )
        if step_frames <= 0:
            raise ValueError("step_frames must be positive")

        frames_elapsed = 0
        use_timing_budget = (
            timeout_cycles is not None or timeout_emulated_time_ns is not None
        )
        start_timing = self.read_frame_metadata() if use_timing_budget else None
        while True:
            result = predicate(self)
            if result:
                return result  # type: ignore[return-value]
            timed_out = False
            if timeout_frames is not None and frames_elapsed >= timeout_frames:
                timed_out = True
            if use_timing_budget:
                current_timing = self.read_frame_metadata()
                assert start_timing is not None
                if (
                    timeout_cycles is not None
                    and current_timing.emulated_cycles
                    >= start_timing.emulated_cycles + timeout_cycles
                ):
                    timed_out = True
                if (
                    timeout_emulated_time_ns is not None
                    and current_timing.emulated_time_ns
                    >= start_timing.emulated_time_ns + timeout_emulated_time_ns
                ):
                    timed_out = True
            if timed_out:
                observation = final_observation() if final_observation is not None else None
                summary = (
                    final_observation_summary(observation)
                    if final_observation_summary is not None and observation is not None
                    else None
                )
                raise AutomationTimeoutError(
                    description,
                    frames_elapsed,
                    final_observation=observation,
                    final_observation_summary=summary,
                )
            if timeout_frames is None:
                frames_to_run = step_frames
            else:
                frames_to_run = min(step_frames, timeout_frames - frames_elapsed)
                if frames_to_run <= 0:
                    frames_to_run = step_frames
            self.run_frames(frames_to_run)
            frames_elapsed += frames_to_run

    def wait_for_text(
        self,
        text: str,
        *,
        region_id: str | None = None,
        timeout_frames: int,
        step_frames: int = 1,
        ) -> TextGridSnapshot:
        state: dict[str, TextGridSnapshot | None] = {"snapshot": None}

        def predicate(machine: Machine) -> TextGridSnapshot | None:
            snapshot = machine.capture_text_grid(region_id)
            state["snapshot"] = snapshot
            return snapshot if text in snapshot.plain else None

        region = region_id if region_id is not None else "default text region"
        return self.wait_until(
            predicate,
            timeout_frames=timeout_frames,
            step_frames=step_frames,
            description=f"text {text!r} in {region}",
            final_observation=lambda: state["snapshot"],
            final_observation_summary=_summarize_observation,
        )

    def wait_for_text_disappearance(
        self,
        text: str,
        *,
        region_id: str | None = None,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> TextGridSnapshot:
        state: dict[str, TextGridSnapshot | None] = {"snapshot": None}

        def predicate(machine: Machine) -> TextGridSnapshot | None:
            snapshot = machine.capture_text_grid(region_id)
            state["snapshot"] = snapshot
            return snapshot if text not in snapshot.plain else None

        region = region_id if region_id is not None else "default text region"
        return self.wait_until(
            predicate,
            timeout_frames=timeout_frames,
            step_frames=step_frames,
            description=f"text {text!r} absent in {region}",
            final_observation=lambda: state["snapshot"],
            final_observation_summary=_summarize_observation,
        )

    def wait_for_memory_value(
        self,
        address: int,
        value: bytes | int,
        *,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> bytes:
        expected = bytes([value]) if isinstance(value, int) else bytes(value)
        state: dict[str, bytes | None] = {"value": None}

        def predicate(machine: Machine) -> bytes | None:
            current = machine.read_memory(address, len(expected))
            state["value"] = current
            return current if current == expected else None

        return self.wait_until(
            predicate,
            timeout_frames=timeout_frames,
            timeout_cycles=timeout_cycles,
            timeout_emulated_time_ns=timeout_emulated_time_ns,
            step_frames=step_frames,
            description=f"memory 0x{address:X} == {expected.hex()}",
            final_observation=lambda: state["value"],
            final_observation_summary=_summarize_observation,
        )

    def wait_for_program_counter(
        self,
        program_counter: int,
        *,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> int:
        expected = int(program_counter)
        state: dict[str, int | None] = {"program_counter": None}

        def predicate(machine: Machine) -> int | None:
            current = machine.read_program_counter()
            state["program_counter"] = current
            return current if current == expected else None

        return self.wait_until(
            predicate,
            timeout_frames=timeout_frames,
            timeout_cycles=timeout_cycles,
            timeout_emulated_time_ns=timeout_emulated_time_ns,
            step_frames=step_frames,
            description=f"program counter == 0x{expected:X}",
            final_observation=lambda: state["program_counter"],
            final_observation_summary=_summarize_observation,
        )

    def wait_for_breakpoint(
        self,
        *,
        program_counter: int | None = None,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> FrameMetadata:
        return self.wait_until(
            lambda machine: self.conditions.breakpoint(
                program_counter=program_counter
            )._predicate(machine),
            timeout_frames=timeout_frames,
            timeout_cycles=timeout_cycles,
            timeout_emulated_time_ns=timeout_emulated_time_ns,
            step_frames=step_frames,
            description=(
                f"debug pause at program counter 0x{int(program_counter):04X}"
                if program_counter is not None
                else "debug pause"
            ),
            final_observation=lambda: self.read_frame_metadata(),
            final_observation_summary=_summarize_observation,
        )

    def wait_for_watchpoint(
        self,
        *,
        program_counter: int | None = None,
        timeout_frames: int | None = None,
        timeout_cycles: int | None = None,
        timeout_emulated_time_ns: int | None = None,
        step_frames: int = 1,
    ) -> FrameMetadata:
        return self.wait_for_breakpoint(
            program_counter=program_counter,
            timeout_frames=timeout_frames,
            timeout_cycles=timeout_cycles,
            timeout_emulated_time_ns=timeout_emulated_time_ns,
            step_frames=step_frames,
        )

    def wait_for_stable_text(
        self,
        *,
        region_id: str | None = None,
        stable_frames: int,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> TextGridSnapshot:
        if stable_frames < 0:
            raise ValueError("stable_frames must be non-negative")
        if timeout_frames < 0:
            raise ValueError("timeout_frames must be non-negative")
        if step_frames <= 0:
            raise ValueError("step_frames must be positive")

        snapshot = self.capture_text_grid(region_id)
        if stable_frames == 0:
            return snapshot

        last_key = _text_grid_key(snapshot)
        last_frame = snapshot.frame_number
        stable_for = 0
        frames_elapsed = 0

        while True:
            if frames_elapsed >= timeout_frames:
                region = region_id if region_id is not None else "default text region"
                raise AutomationTimeoutError(
                    f"stable text in {region}",
                    frames_elapsed,
                    final_observation=snapshot,
                    final_observation_summary=_summarize_observation(snapshot),
                )
            frames_to_run = min(step_frames, timeout_frames - frames_elapsed)
            self.run_frames(frames_to_run)
            frames_elapsed += frames_to_run
            snapshot = self.capture_text_grid(region_id)
            current_key = _text_grid_key(snapshot)
            frame_delta = max(0, snapshot.frame_number - last_frame)
            if current_key == last_key:
                stable_for += frame_delta
                if stable_for >= stable_frames:
                    return snapshot
            else:
                last_key = current_key
                stable_for = 0
            last_frame = snapshot.frame_number

    def wait_for_stable_framebuffer(
        self,
        *,
        stable_frames: int,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> FramebufferSnapshot:
        if stable_frames < 0:
            raise ValueError("stable_frames must be non-negative")
        if timeout_frames < 0:
            raise ValueError("timeout_frames must be non-negative")
        if step_frames <= 0:
            raise ValueError("step_frames must be positive")

        snapshot = self.capture_framebuffer()
        if stable_frames == 0:
            return snapshot

        last_key = _framebuffer_key(snapshot)
        last_frame = snapshot.frame.frame_number
        stable_for = 0
        frames_elapsed = 0

        while True:
            if frames_elapsed >= timeout_frames:
                raise AutomationTimeoutError(
                    "stable framebuffer",
                    frames_elapsed,
                    final_observation=snapshot,
                    final_observation_summary=_summarize_observation(snapshot),
                )
            frames_to_run = min(step_frames, timeout_frames - frames_elapsed)
            self.run_frames(frames_to_run)
            frames_elapsed += frames_to_run
            snapshot = self.capture_framebuffer()
            current_key = _framebuffer_key(snapshot)
            frame_delta = max(0, snapshot.frame.frame_number - last_frame)
            if current_key == last_key:
                stable_for += frame_delta
                if stable_for >= stable_frames:
                    return snapshot
            else:
                last_key = current_key
                stable_for = 0
            last_frame = snapshot.frame.frame_number

    def wait_for_event(
        self,
        event_type: int,
        *,
        after_sequence: int = 0,
        timeout_frames: int,
        step_frames: int = 1,
    ) -> AutomationEvent:
        if timeout_frames < 0:
            raise ValueError("timeout_frames must be non-negative")
        if step_frames <= 0:
            raise ValueError("step_frames must be positive")

        sequence = after_sequence
        frames_elapsed = 0
        last_event: AutomationEvent | None = None
        while True:
            event = self.poll_event(sequence)
            if event is not None:
                sequence = event.sequence_number
                last_event = event
                if event.event_type == event_type:
                    return event
                continue
            if frames_elapsed >= timeout_frames:
                raise AutomationTimeoutError(
                    f"event type {event_type}",
                    frames_elapsed,
                    final_observation=last_event,
                    final_observation_summary=_summarize_observation(last_event),
                )
            frames_to_run = min(step_frames, timeout_frames - frames_elapsed)
            self.run_frames(frames_to_run)
            frames_elapsed += frames_to_run

    def text_views(self) -> list[TextViewDescriptor]:
        count = ctypes.c_size_t()
        self._library.check(
            self._library.cdll.emu_automation_screen_text_view_count(
                self.handle,
                ctypes.byref(count),
            ),
            "emu_automation_screen_text_view_count",
        )
        views: list[TextViewDescriptor] = []
        for index in range(int(count.value)):
            raw = _TextViewDescriptor()
            self._library.check(
                self._library.cdll.emu_automation_screen_text_view_descriptor(
                    self.handle,
                    index,
                    ctypes.byref(raw),
                ),
                "emu_automation_screen_text_view_descriptor",
            )
            views.append(
                TextViewDescriptor(
                    region_id=_decode(raw.region_id),
                    columns=int(raw.columns),
                    rows=int(raw.rows),
                    row_stride=int(raw.row_stride),
                    charset_id=_decode(raw.charset_id),
                    native_encoding=_decode(raw.native_encoding),
                    unicode_map=_decode(raw.unicode_map),
                )
            )
        return views

    def capture_text_grid(self, region_id: str | None = None) -> TextGridSnapshot:
        region = region_id.encode("utf-8") if region_id is not None else None
        raw = _TextGridSnapshot()
        self._library.check(
            self._library.cdll.emu_automation_screen_text_grid(
                self.handle,
                region,
                ctypes.byref(raw),
            ),
            "emu_automation_screen_text_grid",
        )
        try:
            return self._copy_text_grid(raw)
        finally:
            self._library.cdll.emu_automation_text_grid_release(self.handle, ctypes.byref(raw))

    def _copy_text_grid(self, raw: _TextGridSnapshot) -> TextGridSnapshot:
        cells: list[TextCell] = []
        if raw.cells:
            for index in range(int(raw.cell_count)):
                cells.append(_copy_text_cell(raw.cells[index]))

        plain = ""
        if raw.plain_utf8:
            plain = ctypes.string_at(raw.plain_utf8, raw.plain_utf8_size).decode(
                "utf-8",
                "replace",
            )

        return TextGridSnapshot(
            region_id=_decode(raw.region_id),
            columns=int(raw.columns),
            rows=int(raw.rows),
            row_stride=int(raw.row_stride),
            plain=plain,
            cells=tuple(cells),
            frame_number=int(raw.frame.frame_number),
            emulated_cycles=int(raw.frame.emulated_cycles),
            emulated_time_ns=int(raw.frame.emulated_time_ns),
            execution_state=int(raw.frame.execution_state),
        )
