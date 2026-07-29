from __future__ import annotations

import pytest

from .ctypes_api import AutomationLibrary, Machine


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


@pytest.fixture
def automation_library(request: pytest.FixtureRequest) -> AutomationLibrary:
    library_path = request.config.getoption("--automation-library")
    if not library_path:
        pytest.skip("--automation-library was not provided")
    return AutomationLibrary(library_path)


@pytest.fixture
def automation_machine(
    automation_library: AutomationLibrary,
    request: pytest.FixtureRequest,
) -> Machine:
    create_symbol = request.config.getoption("--automation-create-symbol")
    with automation_library.create_machine(create_symbol) as machine:
        yield machine
