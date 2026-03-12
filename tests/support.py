"""Shared helpers for dual-file processor/system test inputs."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(__file__).resolve().parents[1]


def example_pair(name: str, system: str = "default") -> tuple[Path, Path]:
    """Return canonical example processor/system file paths."""
    processor = BASE_DIR / "examples" / "processors" / f"{name}.yaml"
    if system == "default":
        system_path = BASE_DIR / "examples" / "systems" / f"{name}_default.yaml"
    else:
        system_path = BASE_DIR / "examples" / "systems" / system
    return processor, system_path


def _split_legacy_isa(isa: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a legacy combined ISA dict into processor/system dicts."""
    processor = {
        "metadata": copy.deepcopy(isa.get("metadata", {})),
        "registers": copy.deepcopy(isa.get("registers", [])),
        "flags": copy.deepcopy(isa.get("flags", [])),
        "instructions": copy.deepcopy(isa.get("instructions", [])),
    }
    if "ports" in isa:
        processor["ports"] = copy.deepcopy(isa.get("ports"))
    if "interrupts" in isa:
        processor["interrupts"] = copy.deepcopy(isa.get("interrupts"))

    memory = isa.get("memory", {})
    system = {
        "metadata": {
            "name": f"{processor.get('metadata', {}).get('name', 'System')}TestSystem",
            "version": processor.get("metadata", {}).get("version", "1.0"),
        },
        "clock_hz": int(isa.get("clock_hz", 1_000_000)),
        "memory": {
            "default_size": int(memory.get("default_size", 65536)),
            "regions": copy.deepcopy(memory.get("regions", [])),
        },
        "hooks": copy.deepcopy(isa.get("hooks", {})),
        "integrations": copy.deepcopy(isa.get("integrations", {})),
    }
    return processor, system


def write_pair_from_legacy(
    tmp_path: Path,
    stem: str,
    isa: dict[str, Any],
    *,
    system_overrides: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write processor/system YAML files converted from legacy combined ISA data."""
    processor, system = _split_legacy_isa(isa)
    if system_overrides:
        _deep_update(system, system_overrides)

    processor_path = tmp_path / f"{stem}_processor.yaml"
    system_path = tmp_path / f"{stem}_system.yaml"
    processor_path.write_text(yaml.safe_dump(processor, sort_keys=False), encoding="utf-8")
    system_path.write_text(yaml.safe_dump(system, sort_keys=False), encoding="utf-8")
    return processor_path, system_path


def _deep_update(dst: dict[str, Any], src: dict[str, Any]) -> None:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_update(dst[key], value)
        else:
            dst[key] = copy.deepcopy(value)
