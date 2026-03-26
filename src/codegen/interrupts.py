"""Interrupt model helpers for code generation."""

from typing import Any, Dict, List


INTERRUPT_MODE_IDS = {"IM0": 0, "IM1": 1, "IM2": 2}
SUPPORTED_INTERRUPT_MODELS = {"none", "fixed_vector", "z80", "mos6502", "mc6809"}


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
    """Resolve interrupt model with backwards-compatible defaults."""
    interrupts = isa_data.get("interrupts")
    if not isinstance(interrupts, dict):
        return "none"

    configured = str(interrupts.get("model", "")).strip().lower()
    if configured:
        if configured not in SUPPORTED_INTERRUPT_MODELS:
            raise ValueError(
                "Unsupported interrupts.model: "
                f"{configured}. Expected one of {sorted(SUPPORTED_INTERRUPT_MODELS)}"
            )
        return configured

    # Backwards-compatible inference:
    # - IM* mode declarations imply Z80-style dispatch.
    # - Otherwise use a fixed vector model.
    if configured_interrupt_modes(isa_data):
        return "z80"
    return "fixed_vector"
