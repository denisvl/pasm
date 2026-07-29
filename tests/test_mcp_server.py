from pathlib import Path

import anyio

from src.pasm_automation.ctypes_api import Capabilities, MachineDescriptor
from src.pasm_automation.mcp_server import (
    MachineSessionStore,
    create_server,
    resolve_generated_machine_artifact,
)


class FakeMachine:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def describe(self) -> MachineDescriptor:
        return MachineDescriptor(
            machine_id="fake-machine",
            system_id="fake-system",
            model_id="fake-model",
            region="ntsc",
            video_standard="ntsc",
            adapter_version="1.0",
            configured_memory_bytes=65536,
            capabilities=Capabilities(feature_bits=0x1234),
        )

    def capabilities(self) -> Capabilities:
        return Capabilities(feature_bits=0x1234)


def test_mcp_server_registers_planned_dotted_tool_names() -> None:
    store = MachineSessionStore()
    store._machines["sess"] = FakeMachine()
    server, _app = create_server(store=store)

    async def run() -> list[str]:
        tools = await server.list_tools()
        return sorted(tool.name for tool in tools)

    tool_names = anyio.run(run)
    assert "machine.open" in tool_names
    assert "machine.open.generated" in tool_names
    assert "machine.describe" in tool_names
    assert "machine.input.keyboard" in tool_names
    assert "machine.screen.text_grid" in tool_names
    assert "machine.record.sequence" in tool_names
    assert "machine.inspect.memory.read" in tool_names
    assert "machine.debug.breakpoint.set" in tool_names


def test_resolve_generated_machine_artifact_prefers_manifest_cpu_binary(tmp_path: Path) -> None:
    output_dir = tmp_path / "apple2_interactive"
    build_dir = output_dir / "build"
    build_dir.mkdir(parents=True)
    (output_dir / "debugger_link.json").write_text(
        '{"cpu_name":"MOS6502"}',
        encoding="utf-8",
    )
    expected = build_dir / "mos6502_test"
    expected.write_text("", encoding="utf-8")
    expected.chmod(0o755)

    resolved = resolve_generated_machine_artifact(output_dir)
    assert resolved == expected.resolve()


def test_resolve_generated_machine_artifact_uses_explicit_binary_name(tmp_path: Path) -> None:
    output_dir = tmp_path / "custom_output"
    build_dir = output_dir / "cmake-build"
    build_dir.mkdir(parents=True)
    expected = build_dir / "custom_runner"
    expected.write_text("", encoding="utf-8")
    expected.chmod(0o755)

    resolved = resolve_generated_machine_artifact(
        output_dir,
        binary_name="custom_runner",
        build_dir=build_dir,
    )
    assert resolved == expected.resolve()
