import pathlib
import subprocess
import sys

import pytest
from src.parser import yaml_loader
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def test_minimal8_loads_and_validates():
    processor_path, system_path = example_pair("minimal8")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))
    assert data["metadata"]["name"] == "Minimal8"
    assert data["memory"]["address_bits"] == 16
    assert len(data["instructions"]) > 0


def test_simple8_loads_and_validates():
    processor_path, system_path = example_pair("simple8")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))
    assert data["metadata"]["name"] == "Simple8"
    assert len(data["registers"]) >= 8
    assert any(inst["name"] == "HALT" for inst in data["instructions"])


def test_single_file_loader_is_removed():
    with pytest.raises(RuntimeError, match="no longer supported"):
        yaml_loader.load_isa("examples/simple8.yaml")


def test_system_requires_clock_hz(tmp_path):
    processor_path, _ = example_pair("minimal8")
    bad_system = tmp_path / "bad_system.yaml"
    bad_system.write_text(
        "metadata:\n  name: MissingClock\nmemory:\n  default_size: 65536\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="clock_hz"):
        yaml_loader.load_processor_system(str(processor_path), str(bad_system))


def test_system_rejects_unknown_hook_names(tmp_path):
    processor_path, _ = example_pair("minimal8")
    bad_system = tmp_path / "bad_hook_system.yaml"
    bad_system.write_text(
        (
            "metadata:\n"
            "  name: BadHooks\n"
            "clock_hz: 1000000\n"
            "memory:\n"
            "  default_size: 65536\n"
            "hooks:\n"
            "  invalid_hook:\n"
            "    enabled: true\n"
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="invalid_hook|unsupported hook"):
        yaml_loader.load_processor_system(str(processor_path), str(bad_system))


def test_composition_rejects_memory_outside_address_space(tmp_path):
    processor_path, system_path = example_pair("minimal8")
    system_text = pathlib.Path(system_path).read_text(encoding="utf-8")
    oversized = system_text.replace("default_size: 65536", "default_size: 131072")
    bad_system = tmp_path / "oversized_system.yaml"
    bad_system.write_text(oversized, encoding="utf-8")
    with pytest.raises(Exception, match="exceeds processor address space"):
        yaml_loader.load_processor_system(str(processor_path), str(bad_system))


def test_cli_rejects_single_file_flag():
    proc = subprocess.run(
        [sys.executable, "-m", "src.main", "validate", "--isa", "examples/simple8.yaml"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "single-file ISA input was removed" in proc.stderr

