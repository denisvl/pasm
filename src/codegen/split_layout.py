"""Shared split-unit naming/layout helpers for generated outputs."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List


@dataclass(frozen=True)
class SplitUnitSpec:
    """Generated split translation-unit metadata."""

    suffix: str
    owner: str


SYSTEM_UNITS = (
    SplitUnitSpec("runtime", "system"),
    SplitUnitSpec("system_bus", "system"),
    SplitUnitSpec("picker_glue", "system"),
    SplitUnitSpec("system_glue", "system"),
    SplitUnitSpec("host_glue", "host"),
    SplitUnitSpec("device_glue", "device"),
)

# Backward-compatible suffix export for existing call sites/tests.
SYSTEM_UNIT_SUFFIXES = tuple(unit.suffix for unit in SYSTEM_UNITS)


def target_ident(raw: str, fallback: str) -> str:
    """Canonical snake_case identifier for generated build/file names."""
    text = str(raw or "").strip()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    for suffix in ("_interactive_system", "_default_system", "_system"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].rstrip("_")
            break
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"{fallback}_{text}"
    return text


def system_ident(system_name: str, cpu_prefix: str) -> str:
    """Canonical system prefix with CPU-name noise removed."""
    out = target_ident(system_name, "system")
    if cpu_prefix and out.startswith(f"{cpu_prefix}_"):
        out = out[len(cpu_prefix) + 1 :]
    # Normalize common platform branding tokens.
    out = out.replace("co_co", "coco")
    if out.startswith("spectrum48_k"):
        out = out.replace("spectrum48_k", "zx_spectrum_48k", 1)
    elif out.startswith("spectrum_48_k"):
        out = out.replace("spectrum_48_k", "zx_spectrum_48k", 1)
    out = re.sub(r"_+", "_", out).strip("_")
    return out or "system"


def system_unit_basenames(system_prefix: str) -> List[str]:
    """Ordered system-side split compilation units."""
    return [f"{system_prefix}_{unit.suffix}" for unit in SYSTEM_UNITS]


def system_unit_sources(system_prefix: str) -> List[str]:
    """Ordered system-side split C source file paths (without debug ABI/hook units)."""
    return [f"src/{name}.c" for name in system_unit_basenames(system_prefix)]


def ic_unit_basenames(isa_data: Dict[str, Any], system_prefix: str) -> List[str]:
    """Deterministic per-IC split unit basenames for declared IC components."""
    basenames: List[str] = []
    for comp in list(isa_data.get("ics", []) or []):
        if not isinstance(comp, dict):
            continue
        comp_id = str((comp.get("metadata") or {}).get("id", "")).strip()
        comp_ident = target_ident(comp_id, "ic")
        basenames.append(f"{system_prefix}_ic_{comp_ident}")
    return basenames


def all_system_sources(isa_data: Dict[str, Any], system_prefix: str) -> List[str]:
    """Ordered system-side split sources including per-IC units."""
    base = system_unit_sources(system_prefix)
    ic_sources = [f"src/{name}.c" for name in ic_unit_basenames(isa_data, system_prefix)]
    return base + ic_sources
