from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EMU_AUTOMATION_ABI_VERSION = 1
EMU_AUTOMATION_OK = 0
EMU_AUTOMATION_STRUCT_VERSION = 1
EMU_AUTOMATION_RESET_COLD = 0
EMU_AUTOMATION_RESET_WARM = 1
EMU_AUTOMATION_INPUT_RELEASE = 0
EMU_AUTOMATION_INPUT_PRESS = 1
EMU_AUTOMATION_TIMING_IMMEDIATE = 0


class AutomationError(RuntimeError):
    def __init__(self, operation: str, result: int, result_name: str) -> None:
        self.operation = operation
        self.result = result
        self.result_name = result_name
        super().__init__(f"{operation} failed: {result_name} ({result})")


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
class FrameMetadata:
    frame_number: int
    emulated_cycles: int
    emulated_time_ns: int
    execution_state: int


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


def _encode_optional(value: str | None) -> bytes | None:
    return value.encode("utf-8") if value is not None else None


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

    def tap_key(self, key_id: str, *, device_id: str | None = None) -> None:
        self.key(key_id, action="press", device_id=device_id)
        self.key(key_id, action="release", device_id=device_id)

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
                cell = raw.cells[index]
                cells.append(
                    TextCell(
                        native_code=int(cell.native_code),
                        unicode_codepoint=int(cell.unicode_codepoint),
                        text=_codepoint_to_text(int(cell.unicode_codepoint)),
                        glyph_id=_decode(cell.glyph_id),
                        foreground_color=int(cell.foreground_color),
                        background_color=int(cell.background_color),
                        attribute_flags=int(cell.attribute_flags),
                        charset_id=_decode(cell.charset_id),
                        source_address=int(cell.source_address),
                        confidence=int(cell.confidence),
                    )
                )

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
