"""MCP server exposing PASM emulator automation to coding agents."""

from __future__ import annotations

import argparse
import base64
import json
import os
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import ctypes_api

SERVER_NAME = "pasm-automation"
SERVER_VERSION = "0.1.0"


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode("ascii"), "size": len(value)}
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, Path):
        return str(value)
    return value


def _timing_from_payload(payload: dict[str, Any] | None) -> ctypes_api.InputTiming | None:
    if payload is None:
        return None
    return ctypes_api.InputTiming(int(payload.get("kind", 0)), int(payload.get("value", 0)))


def _preset_from_payload(payload: dict[str, Any] | None) -> ctypes_api.InputTapPreset | None:
    if payload is None:
        return None
    return ctypes_api.InputTapPreset(
        press_timing=_timing_from_payload(payload.get("press_timing")) or ctypes_api.InputTiming.immediate(),
        release_timing=_timing_from_payload(payload.get("release_timing")) or ctypes_api.InputTiming.immediate(),
    )


def _event_type_from_payload(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(getattr(ctypes_api.EventType, value.upper()))
    raise ValueError("event_type must be an integer or a known event-type name")


class MachineSessionStore:
    def __init__(self) -> None:
        self._machines: dict[str, ctypes_api.Machine] = {}
        self._recordings: dict[str, ctypes_api.SessionRecording] = {}

    def create_machine(self, *, library: str, create_symbol: str = "emu_automation_create") -> str:
        machine = ctypes_api.create(library, create_symbol=create_symbol)
        session_id = str(uuid.uuid4())
        self._machines[session_id] = machine
        return session_id

    def attach_machine(self, *, library: str, handle: int, owned: bool = True) -> str:
        machine = ctypes_api.attach(library, handle, owned=owned)
        session_id = str(uuid.uuid4())
        self._machines[session_id] = machine
        return session_id

    def get_machine(self, session_id: str) -> ctypes_api.Machine:
        try:
            return self._machines[session_id]
        except KeyError as exc:
            raise ValueError(f"unknown machine session_id: {session_id}") from exc

    def close_machine(self, session_id: str) -> None:
        machine = self.get_machine(session_id)
        machine.close()
        del self._machines[session_id]

    def put_recording(self, recording: ctypes_api.SessionRecording) -> str:
        recording_id = str(uuid.uuid4())
        self._recordings[recording_id] = recording
        return recording_id

    def get_recording(self, recording_id: str) -> ctypes_api.SessionRecording:
        try:
            return self._recordings[recording_id]
        except KeyError as exc:
            raise ValueError(f"unknown recording_id: {recording_id}") from exc


def _candidate_executable_names(cpu_name: str | None) -> list[str]:
    names: list[str] = []
    if cpu_name:
        names.append(f"{cpu_name.lower()}_test")
    names.extend(
        [
            "mos6502_test",
            "mos6510_test",
            "mc6809_test",
            "z80_test",
        ]
    )
    unique: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            unique.append(name)
            seen.add(name)
    return unique


def resolve_generated_machine_artifact(
    output_dir: str | Path,
    *,
    binary_name: str | None = None,
    build_dir: str | Path | None = None,
) -> Path:
    root = Path(output_dir).resolve()
    manifest_path = root / "debugger_link.json"
    cpu_name: str | None = None
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_cpu_name = payload.get("cpu_name")
        if isinstance(raw_cpu_name, str) and raw_cpu_name.strip():
            cpu_name = raw_cpu_name.strip()

    build_root = Path(build_dir).resolve() if build_dir is not None else root / "build"
    suffixes = ["", ".exe"] if os.name == "nt" else ["", ".bin"]

    candidate_names: list[str] = []
    if binary_name:
        candidate_names.append(binary_name)
    else:
        candidate_names.extend(_candidate_executable_names(cpu_name))

    for candidate in candidate_names:
        for suffix in suffixes:
            path = build_root / f"{candidate}{suffix}"
            if path.is_file():
                return path

    discovered = sorted(
        path
        for path in build_root.iterdir()
        if path.is_file() and (os.access(path, os.X_OK) or path.suffix.lower() == ".exe")
    ) if build_root.is_dir() else []
    if len(discovered) == 1:
        return discovered[0]

    if not build_root.exists():
        raise ValueError(f"generated build directory not found: {build_root}")
    if discovered:
        sample = ", ".join(path.name for path in discovered[:8])
        raise ValueError(
            f"could not resolve generated emulator artifact in {build_root}; "
            f"set binary_name explicitly. Found: {sample}"
        )
    raise ValueError(f"no executable emulator artifact found in {build_root}")


class AutomationMcpApp:
    def __init__(self, *, store: MachineSessionStore | None = None) -> None:
        self.store = store or MachineSessionStore()
        self.server = MCPServer(
            name=SERVER_NAME,
            title="PASM Automation",
            description="Structured emulator automation tools for PASM-generated machines.",
            instructions=(
                "Use explicit tool calls with structured arguments. Prefer capability discovery "
                "before using machine-specific inspection and debug operations."
            ),
            version=SERVER_VERSION,
        )
        self._register_tools()

    def _machine(self, session_id: str) -> ctypes_api.Machine:
        return self.store.get_machine(session_id)

    def _register_tools(self) -> None:
        @self.server.tool(name="machine.open", structured_output=True)
        def machine_open(library: str, create_symbol: str = "emu_automation_create") -> dict[str, str]:
            session_id = self.store.create_machine(library=library, create_symbol=create_symbol)
            return {"session_id": session_id}

        @self.server.tool(name="machine.open.generated", structured_output=True)
        def machine_open_generated(
            output_dir: str,
            create_symbol: str = "emu_automation_create",
            binary_name: str | None = None,
            build_dir: str | None = None,
        ) -> dict[str, str]:
            artifact = resolve_generated_machine_artifact(
                output_dir,
                binary_name=binary_name,
                build_dir=build_dir,
            )
            session_id = self.store.create_machine(library=str(artifact), create_symbol=create_symbol)
            return {"session_id": session_id, "library": str(artifact)}

        @self.server.tool(name="machine.attach", structured_output=True)
        def machine_attach(library: str, handle: int, owned: bool = True) -> dict[str, str]:
            session_id = self.store.attach_machine(library=library, handle=handle, owned=owned)
            return {"session_id": session_id}

        @self.server.tool(name="machine.close", structured_output=True)
        def machine_close(session_id: str) -> dict[str, bool]:
            self.store.close_machine(session_id)
            return {"ok": True}

        @self.server.tool(name="machine.describe", structured_output=True)
        def machine_describe(session_id: str) -> dict[str, Any]:
            return _serialize(self._machine(session_id).describe())

        @self.server.tool(name="machine.capabilities", structured_output=True)
        def machine_capabilities(session_id: str) -> dict[str, Any]:
            return _serialize(self._machine(session_id).capabilities())

        @self.server.tool(name="machine.character_mappings", structured_output=True)
        def machine_character_mappings(session_id: str) -> list[dict[str, Any]]:
            return _serialize(self._machine(session_id).character_mappings())

        @self.server.tool(name="machine.pause", structured_output=True)
        def machine_pause(session_id: str) -> dict[str, bool]:
            self._machine(session_id).pause()
            return {"ok": True}

        @self.server.tool(name="machine.resume", structured_output=True)
        def machine_resume(session_id: str) -> dict[str, bool]:
            self._machine(session_id).resume()
            return {"ok": True}

        @self.server.tool(name="machine.reset", structured_output=True)
        def machine_reset(session_id: str, kind: str = "cold") -> dict[str, bool]:
            self._machine(session_id).reset(kind)
            return {"ok": True}

        @self.server.tool(name="machine.step_frame", structured_output=True)
        def machine_step_frame(session_id: str) -> dict[str, bool]:
            self._machine(session_id).step_frame()
            return {"ok": True}

        @self.server.tool(name="machine.run_frames", structured_output=True)
        def machine_run_frames(session_id: str, frame_count: int) -> dict[str, Any]:
            self._machine(session_id).run_frames(frame_count)
            return {"ok": True, "frame_count": frame_count}

        @self.server.tool(name="machine.input.keyboard", structured_output=True)
        def machine_input_keyboard(
            session_id: str,
            mode: str,
            key_id: str | None = None,
            text: str | None = None,
            device_id: str | None = None,
            timing: dict[str, Any] | None = None,
            preset: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            machine = self._machine(session_id)
            if mode == "press":
                if not key_id:
                    raise ValueError("key_id is required for keyboard press")
                t = _timing_from_payload(timing) or ctypes_api.InputTiming.immediate()
                machine.key(key_id, action="press", device_id=device_id, timing_kind=t.kind, timing_value=t.value)
                return {"ok": True}
            if mode == "release":
                if not key_id:
                    raise ValueError("key_id is required for keyboard release")
                t = _timing_from_payload(timing) or ctypes_api.InputTiming.immediate()
                machine.key(key_id, action="release", device_id=device_id, timing_kind=t.kind, timing_value=t.value)
                return {"ok": True}
            if mode == "tap":
                if not key_id:
                    raise ValueError("key_id is required for keyboard tap")
                machine.tap_key(key_id, device_id=device_id, preset=_preset_from_payload(preset))
                return {"ok": True}
            if mode == "type_text":
                if text is None:
                    raise ValueError("text is required for type_text")
                machine.type_text(text, device_id=device_id, preset=_preset_from_payload(preset))
                return {"ok": True}
            if mode == "release_all":
                return {"released": machine.release_all_keys(device_id=device_id)}
            raise ValueError(f"unsupported keyboard mode: {mode}")

        @self.server.tool(name="machine.input.controller", structured_output=True)
        def machine_input_controller(
            session_id: str,
            mode: str,
            control_id: str | None = None,
            device_id: str | None = None,
            timing: dict[str, Any] | None = None,
            preset: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            machine = self._machine(session_id)
            if mode == "press":
                if not control_id:
                    raise ValueError("control_id is required for controller press")
                t = _timing_from_payload(timing) or ctypes_api.InputTiming.immediate()
                machine.controller_button(
                    control_id, action="press", device_id=device_id, timing_kind=t.kind, timing_value=t.value
                )
                return {"ok": True}
            if mode == "release":
                if not control_id:
                    raise ValueError("control_id is required for controller release")
                t = _timing_from_payload(timing) or ctypes_api.InputTiming.immediate()
                machine.controller_button(
                    control_id, action="release", device_id=device_id, timing_kind=t.kind, timing_value=t.value
                )
                return {"ok": True}
            if mode == "tap":
                if not control_id:
                    raise ValueError("control_id is required for controller tap")
                machine.tap_controller_button(control_id, device_id=device_id, preset=_preset_from_payload(preset))
                return {"ok": True}
            if mode == "release_all":
                return {"released": machine.release_all_controller_buttons(device_id=device_id)}
            raise ValueError(f"unsupported controller mode: {mode}")

        @self.server.tool(name="machine.screen.text_views", structured_output=True)
        def machine_screen_text_views(session_id: str) -> list[dict[str, Any]]:
            return _serialize(self._machine(session_id).text_views())

        @self.server.tool(name="machine.screen.text_grid", structured_output=True)
        def machine_screen_text_grid(session_id: str, region_id: str | None = None) -> dict[str, Any]:
            return _serialize(self._machine(session_id).capture_text_grid(region_id))

        @self.server.tool(name="machine.screen.framebuffer", structured_output=True)
        def machine_screen_framebuffer(session_id: str, include_pixels: bool = False) -> dict[str, Any]:
            snapshot = self._machine(session_id).capture_framebuffer()
            payload = {
                "frame": _serialize(snapshot.frame),
                "width": snapshot.width,
                "height": snapshot.height,
                "stride_bytes": snapshot.stride_bytes,
                "pixel_format": snapshot.pixel_format,
                "visible_area": _serialize(snapshot.visible_area),
                "pixel_aspect_numerator": snapshot.pixel_aspect_numerator,
                "pixel_aspect_denominator": snapshot.pixel_aspect_denominator,
                "pixel_size": len(snapshot.pixels),
            }
            if include_pixels:
                payload["pixels"] = _serialize(snapshot.pixels)
            return payload

        @self.server.tool(name="machine.events.poll", structured_output=True)
        def machine_events_poll(session_id: str, after_sequence: int = 0) -> dict[str, Any] | None:
            return _serialize(self._machine(session_id).poll_event(after_sequence))

        @self.server.tool(name="machine.events.drain", structured_output=True)
        def machine_events_drain(session_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
            return _serialize(self._machine(session_id).drain_events(after_sequence))

        @self.server.tool(name="machine.wait.for_text", structured_output=True)
        def machine_wait_for_text(
            session_id: str,
            text: str,
            timeout_frames: int,
            region_id: str | None = None,
            step_frames: int = 1,
        ) -> dict[str, Any]:
            return _serialize(
                self._machine(session_id).wait_for_text(
                    text, region_id=region_id, timeout_frames=timeout_frames, step_frames=step_frames
                )
            )

        @self.server.tool(name="machine.wait.for_text_disappearance", structured_output=True)
        def machine_wait_for_text_disappearance(
            session_id: str,
            text: str,
            timeout_frames: int,
            region_id: str | None = None,
            step_frames: int = 1,
        ) -> dict[str, Any]:
            return _serialize(
                self._machine(session_id).wait_for_text_disappearance(
                    text, region_id=region_id, timeout_frames=timeout_frames, step_frames=step_frames
                )
            )

        @self.server.tool(name="machine.wait.for_memory_value", structured_output=True)
        def machine_wait_for_memory_value(
            session_id: str,
            address: int,
            value_base64: str,
            timeout_frames: int,
            step_frames: int = 1,
        ) -> dict[str, Any]:
            value = base64.b64decode(value_base64.encode("ascii"))
            return _serialize(
                self._machine(session_id).wait_for_memory_value(
                    address, value, timeout_frames=timeout_frames, step_frames=step_frames
                )
            )

        @self.server.tool(name="machine.wait.for_program_counter", structured_output=True)
        def machine_wait_for_program_counter(
            session_id: str,
            program_counter: int,
            timeout_frames: int | None = None,
            timeout_cycles: int | None = None,
            timeout_emulated_time_ns: int | None = None,
            step_frames: int = 1,
        ) -> dict[str, Any]:
            return _serialize(
                self._machine(session_id).wait_for_program_counter(
                    program_counter,
                    timeout_frames=timeout_frames,
                    timeout_cycles=timeout_cycles,
                    timeout_emulated_time_ns=timeout_emulated_time_ns,
                    step_frames=step_frames,
                )
            )

        @self.server.tool(name="machine.wait.for_breakpoint", structured_output=True)
        def machine_wait_for_breakpoint(
            session_id: str,
            program_counter: int | None = None,
            timeout_frames: int | None = None,
            timeout_cycles: int | None = None,
            timeout_emulated_time_ns: int | None = None,
            step_frames: int = 1,
        ) -> dict[str, Any]:
            return _serialize(
                self._machine(session_id).wait_for_breakpoint(
                    program_counter=program_counter,
                    timeout_frames=timeout_frames,
                    timeout_cycles=timeout_cycles,
                    timeout_emulated_time_ns=timeout_emulated_time_ns,
                    step_frames=step_frames,
                )
            )

        @self.server.tool(name="machine.wait.for_watchpoint", structured_output=True)
        def machine_wait_for_watchpoint(
            session_id: str,
            program_counter: int | None = None,
            timeout_frames: int | None = None,
            timeout_cycles: int | None = None,
            timeout_emulated_time_ns: int | None = None,
            step_frames: int = 1,
        ) -> dict[str, Any]:
            return _serialize(
                self._machine(session_id).wait_for_watchpoint(
                    program_counter=program_counter,
                    timeout_frames=timeout_frames,
                    timeout_cycles=timeout_cycles,
                    timeout_emulated_time_ns=timeout_emulated_time_ns,
                    step_frames=step_frames,
                )
            )

        @self.server.tool(name="machine.wait.for_event", structured_output=True)
        def machine_wait_for_event(
            session_id: str,
            event_type: int | str,
            timeout_frames: int,
            after_sequence: int = 0,
            step_frames: int = 1,
        ) -> dict[str, Any]:
            return _serialize(
                self._machine(session_id).wait_for_event(
                    _event_type_from_payload(event_type),
                    after_sequence=after_sequence,
                    timeout_frames=timeout_frames,
                    step_frames=step_frames,
                )
            )

        @self.server.tool(name="machine.record.sequence", structured_output=True)
        def machine_record_sequence(
            session_id: str,
            steps: list[dict[str, Any]],
            after_sequence: int = 0,
        ) -> dict[str, Any]:
            machine = self._machine(session_id)
            sequence = ctypes_api.InputSequence.from_log_payload(machine, steps)
            recording = machine.record(sequence, after_sequence=after_sequence)
            recording_id = self.store.put_recording(recording)
            return {
                "recording_id": recording_id,
                "header": _serialize(recording.header),
                "input_steps": _serialize(recording.input_steps),
                "events": _serialize(recording.events),
                "jsonl": recording.to_jsonl(),
            }

        @self.server.tool(name="machine.replay.recording", structured_output=True)
        def machine_replay_recording(
            session_id: str,
            recording_id: str,
            verify_events: bool = True,
            after_sequence: int = 0,
        ) -> dict[str, Any]:
            machine = self._machine(session_id)
            observed = machine.replay_recording(
                self.store.get_recording(recording_id),
                verify_events=verify_events,
                after_sequence=after_sequence,
            )
            return {"events": _serialize(observed)}

        @self.server.tool(name="machine.inspect.memory.read", structured_output=True)
        def machine_inspect_memory_read(session_id: str, address: int, size: int) -> dict[str, Any]:
            return _serialize(self._machine(session_id).read_memory(address, size))

        @self.server.tool(name="machine.inspect.memory.write", structured_output=True)
        def machine_inspect_memory_write(session_id: str, address: int, data_base64: str) -> dict[str, Any]:
            payload = base64.b64decode(data_base64.encode("ascii"))
            self._machine(session_id).write_memory(address, payload)
            return {"ok": True, "size": len(payload)}

        @self.server.tool(name="machine.inspect.program_counter", structured_output=True)
        def machine_inspect_program_counter(session_id: str) -> dict[str, Any]:
            return {"program_counter": self._machine(session_id).read_program_counter()}

        @self.server.tool(name="machine.inspect.frame_metadata", structured_output=True)
        def machine_inspect_frame_metadata(session_id: str) -> dict[str, Any]:
            return _serialize(self._machine(session_id).read_frame_metadata())

        @self.server.tool(name="machine.inspect.current_instruction", structured_output=True)
        def machine_inspect_current_instruction(session_id: str) -> dict[str, Any]:
            return _serialize(self._machine(session_id).read_current_instruction())

        @self.server.tool(name="machine.inspect.registers.read", structured_output=True)
        def machine_inspect_registers_read(session_id: str) -> list[dict[str, Any]]:
            return _serialize(self._machine(session_id).read_registers())

        @self.server.tool(name="machine.inspect.registers.write", structured_output=True)
        def machine_inspect_registers_write(session_id: str, register_name: str, value: int) -> dict[str, bool]:
            self._machine(session_id).write_register(register_name, value)
            return {"ok": True}

        @self.server.tool(name="machine.debug.breakpoint.set", structured_output=True)
        def machine_debug_breakpoint_set(session_id: str, address: int, enabled: bool = True) -> dict[str, bool]:
            self._machine(session_id).set_breakpoint(address, enabled=enabled)
            return {"ok": True}


def create_server(*, store: MachineSessionStore | None = None) -> tuple[MCPServer, AutomationMcpApp]:
    app = AutomationMcpApp(store=store)
    return app.server, app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PASM automation MCP server.")
    parser.parse_args(argv)
    server, _app = create_server()
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
