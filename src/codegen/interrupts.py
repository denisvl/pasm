"""Interrupt model helpers for code generation."""

from typing import Any, Dict, List

INTERRUPT_MODE_IDS = {"IM0": 0, "IM1": 1, "IM2": 2}


def configured_interrupt_modes(isa_data: Dict[str, Any]) -> List[int]:
    """Resolve configured interrupt modes to numeric IDs in declaration order."""
    resolved: List[int] = []
    modes = isa_data.get("interrupts", {}).get("modes", [])
    for mode in modes:
        mode_name = mode.get("name", "") if isinstance(mode, dict) else str(mode)
        mode_id = INTERRUPT_MODE_IDS.get(mode_name.upper())
        if mode_id is None or mode_id in resolved:
            continue
        resolved.append(mode_id)
    return resolved


def resolve_interrupt_model(isa_data: Dict[str, Any]) -> str:
    """Resolve the YAML-declared interrupt model."""
    interrupts = isa_data.get("interrupts")
    if not isinstance(interrupts, dict):
        return "none"

    configured = str(interrupts.get("model", "")).strip().lower()
    if configured:
        return configured
    return "none"


def generate_interrupt_impl(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Emit interrupt API implementation for split system glue units."""
    # Local import avoids cpu_impl <-> interrupts import cycle.
    from .cpu_impl import _generate_interrupt_impl

    return _generate_interrupt_impl(isa_data, cpu_name.lower())
