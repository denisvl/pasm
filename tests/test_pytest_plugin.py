from __future__ import annotations

from pathlib import Path

import pytest

from src.pasm_automation.pytest_plugin import _failure_sections, _resolve_generated_artifact


class _DummyConfig:
    def __init__(self, **options):
        self._options = options

    def getoption(self, name: str):
        return self._options.get(name)


class _DummyNode:
    def __init__(self, kwargs: dict[str, object] | None = None):
        self._kwargs = kwargs or {}

    def get_closest_marker(self, name: str):
        if name != "automation_generated" or not self._kwargs:
            return None

        class _Marker:
            def __init__(self, kwargs):
                self.kwargs = kwargs

        return _Marker(self._kwargs)


class _DummyRequest:
    def __init__(self, config: _DummyConfig, kwargs: dict[str, object] | None = None):
        self.config = config
        self.node = _DummyNode(kwargs)


class _FakeView:
    def __init__(self, region_id: str):
        self.region_id = region_id

    def __repr__(self) -> str:
        return f"_FakeView(region_id={self.region_id!r})"


class _FakeSnapshot:
    def __init__(self, plain: str):
        self.plain = plain


class _FakeMachine:
    def describe(self):
        return {"machine_id": "fake"}

    def capabilities(self):
        return {"feature_bits": 7}

    def read_frame_metadata(self):
        return {"frame_number": 42}

    def read_program_counter(self):
        return 0x1234

    def text_views(self):
        return [_FakeView("primary_text")]

    def capture_text_grid(self, region_id: str):
        assert region_id == "primary_text"
        return _FakeSnapshot("READY")


def test_resolve_generated_artifact_uses_marker(tmp_path: Path) -> None:
    output_dir = tmp_path / "apple2_interactive"
    build_dir = output_dir / "build"
    build_dir.mkdir(parents=True)
    (output_dir / "debugger_link.json").write_text('{"cpu_name":"MOS6502"}', encoding="utf-8")
    artifact = build_dir / "mos6502_test"
    artifact.write_text("", encoding="utf-8")
    artifact.chmod(0o755)

    request = _DummyRequest(
        _DummyConfig(
            **{
                "--automation-generated-output": None,
                "--automation-generated-build-dir": None,
                "--automation-generated-binary": None,
            }
        ),
        {"output_dir": str(output_dir)},
    )

    resolved = _resolve_generated_artifact(request)
    assert resolved == artifact.resolve()


def test_failure_sections_include_machine_state() -> None:
    sections = dict(_failure_sections(_FakeMachine()))
    assert "fake" in sections["automation machine"]
    assert "feature_bits" in sections["automation capabilities"]
    assert "0x1234" in sections["automation pc"]
    assert "READY" in sections["automation text snapshot"]
