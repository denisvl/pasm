from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from .ctypes_api import AutomationLibrary, Machine
from .mcp_server import resolve_generated_machine_artifact


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("pasm automation")
    group.addoption(
        "--automation-library",
        action="store",
        default=None,
        help="Path to a shared library exposing the emulator automation C ABI.",
    )
    group.addoption(
        "--automation-create-symbol",
        action="store",
        default="emu_automation_create",
        help="C symbol used to create an automation machine handle.",
    )
    group.addoption(
        "--automation-generated-output",
        action="store",
        default=None,
        help="Generated PASM output directory to resolve into a built automation artifact.",
    )
    group.addoption(
        "--automation-generated-build-dir",
        action="store",
        default=None,
        help="Optional build directory override inside a generated PASM output.",
    )
    group.addoption(
        "--automation-generated-binary",
        action="store",
        default=None,
        help="Optional generated emulator binary name override.",
    )
    group.addoption(
        "--automation-screenshot-on-failure",
        action="store_true",
        default=False,
        help="Capture a framebuffer PNG for failed tests when an automation machine fixture is active.",
    )
    group.addoption(
        "--automation-screenshot-dir",
        action="store",
        default="artifacts/automation_failures",
        help="Directory used for automation failure screenshots.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "automation_generated(output_dir, build_dir=None, binary_name=None, create_symbol=None): "
        "resolve a built PASM generated output directory into an automation artifact for this test",
    )


def _marker_kwargs(request: pytest.FixtureRequest) -> dict[str, Any]:
    marker = request.node.get_closest_marker("automation_generated")
    return dict(marker.kwargs) if marker is not None else {}


def _resolve_generated_artifact(request: pytest.FixtureRequest) -> Path | None:
    marker = _marker_kwargs(request)
    output_dir = marker.get("output_dir") or request.config.getoption("--automation-generated-output")
    if not output_dir:
        return None
    build_dir = marker.get("build_dir") or request.config.getoption("--automation-generated-build-dir")
    binary_name = marker.get("binary_name") or request.config.getoption("--automation-generated-binary")
    return resolve_generated_machine_artifact(
        output_dir,
        build_dir=build_dir,
        binary_name=binary_name,
    )


def _resolve_create_symbol(request: pytest.FixtureRequest) -> str:
    marker = _marker_kwargs(request)
    return str(marker.get("create_symbol") or request.config.getoption("--automation-create-symbol"))


@pytest.fixture
def automation_library(request: pytest.FixtureRequest) -> AutomationLibrary:
    library_path = request.config.getoption("--automation-library")
    if not library_path:
        generated_artifact = _resolve_generated_artifact(request)
        if generated_artifact is not None:
            library_path = str(generated_artifact)
    if not library_path:
        pytest.skip("--automation-library was not provided")
    return AutomationLibrary(library_path)


@pytest.fixture
def automation_machine(
    automation_library: AutomationLibrary,
    request: pytest.FixtureRequest,
) -> Machine:
    create_symbol = _resolve_create_symbol(request)
    with automation_library.create_machine(create_symbol) as machine:
        yield machine


@pytest.fixture
def automation_generated_artifact(request: pytest.FixtureRequest) -> Path:
    artifact = _resolve_generated_artifact(request)
    if artifact is None:
        pytest.skip("no automation generated output was configured")
    return artifact


@pytest.fixture
def automation_generated_machine(
    request: pytest.FixtureRequest,
    automation_generated_artifact: Path,
) -> Machine:
    library = AutomationLibrary(str(automation_generated_artifact))
    create_symbol = _resolve_create_symbol(request)
    with library.create_machine(create_symbol) as machine:
        yield machine


def _active_machine(item: pytest.Item) -> Machine | None:
    for name in ("automation_generated_machine", "automation_machine"):
        if name in item.funcargs:
            machine = item.funcargs[name]
            if isinstance(machine, Machine):
                return machine
    return None


def _failure_screenshot_path(item: pytest.Item, machine: Machine) -> str | None:
    if not item.config.getoption("--automation-screenshot-on-failure"):
        return None
    try:
        framebuffer = machine.capture_framebuffer()
    except Exception:
        return None
    out_dir = Path(item.config.getoption("--automation-screenshot-dir")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    name = item.nodeid.replace("/", "_").replace("::", "__").replace("\\", "_")
    path = out_dir / f"{name}.png"
    framebuffer.save_png(path)
    return str(path)


def _failure_sections(machine: Machine) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    try:
        descriptor = machine.describe()
        sections.append(("automation machine", repr(descriptor)))
    except Exception as exc:
        sections.append(("automation machine", f"describe() failed: {exc}"))
    try:
        capabilities = machine.capabilities()
        sections.append(("automation capabilities", repr(capabilities)))
    except Exception as exc:
        sections.append(("automation capabilities", f"capabilities() failed: {exc}"))
    try:
        metadata = machine.read_frame_metadata()
        sections.append(("automation frame", repr(metadata)))
    except Exception as exc:
        sections.append(("automation frame", f"read_frame_metadata() failed: {exc}"))
    try:
        pc = machine.read_program_counter()
        sections.append(("automation pc", f"0x{pc:X}"))
    except Exception as exc:
        sections.append(("automation pc", f"read_program_counter() failed: {exc}"))
    try:
        views = machine.text_views()
        sections.append(("automation text views", repr(views)))
        if views:
            snapshot = machine.capture_text_grid(views[0].region_id)
            sections.append(("automation text snapshot", snapshot.plain))
    except Exception as exc:
        sections.append(("automation text snapshot", f"text capture failed: {exc}"))
    return sections


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or report.passed:
        return
    machine = _active_machine(item)
    if machine is None:
        return
    for title, content in _failure_sections(machine):
        item.add_report_section(report.when, title, content)
    screenshot_path = _failure_screenshot_path(item, machine)
    if screenshot_path is not None:
        item.add_report_section(report.when, "automation screenshot", screenshot_path)
