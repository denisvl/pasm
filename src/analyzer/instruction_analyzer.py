"""Instruction-level analysis helpers.

This module is intentionally lightweight for now. It provides a small public
surface that future passes can extend without changing call-sites.
"""

from typing import Any, Dict, List, Set


def summarize_instruction_categories(isa_data: Dict[str, Any]) -> Dict[str, int]:
    """Return a count of instructions by category."""
    summary: Dict[str, int] = {}
    for inst in isa_data.get("instructions", []):
        category = inst.get("category", "misc")
        summary[category] = summary.get(category, 0) + 1
    return summary


def list_instruction_names(isa_data: Dict[str, Any]) -> List[str]:
    """Return instruction names in declaration order."""
    return [inst.get("name", "UNKNOWN") for inst in isa_data.get("instructions", [])]


def audit_opcode_spaces(isa_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Audit opcode-space coverage for prefix-sensitive architectures like Z80.

    Returns coverage metadata for:
    `base`, `cb`, `ed`, `dd`, `fd`, `ddcb`, `fdcb`.
    """
    coverage: Dict[str, Set[int]] = {
        "base": set(),
        "cb": set(),
        "ed": set(),
        "dd": set(),
        "fd": set(),
        "ddcb": set(),
        "fdcb": set(),
    }

    for inst in isa_data.get("instructions", []):
        encoding = inst.get("encoding", {})
        opcode = int(encoding.get("opcode", 0))
        mask = int(encoding.get("mask", 0xFF)) & 0xFFFF
        prefix = encoding.get("prefix")
        subop = encoding.get("subop")
        subop_mask = int(encoding.get("subop_mask", 0xFF)) & 0xFF
        length = int(encoding.get("length", inst.get("length", 1)))

        if prefix in (0xDD, 0xFD) and opcode == 0xCB and subop is not None and length >= 4:
            target = "ddcb" if prefix == 0xDD else "fdcb"
            for op in range(256):
                if (op & subop_mask) == (int(subop) & subop_mask):
                    coverage[target].add(op)
            continue

        if prefix in (0xDD, 0xFD):
            target = "dd" if prefix == 0xDD else "fd"
            for op in range(256):
                if (op & (mask & 0xFF)) == (opcode & 0xFF):
                    coverage[target].add(op)
            continue

        if prefix in (0xCB, 0xED):
            target = "cb" if prefix == 0xCB else "ed"
            for op in range(256):
                if (op & (mask & 0xFF)) == (opcode & 0xFF):
                    coverage[target].add(op)
            continue

        # Two-byte CB/ED forms encoded as little-endian opcode constants.
        if opcode > 0xFF and (opcode & 0xFF) in (0xCB, 0xED):
            target = "cb" if (opcode & 0xFF) == 0xCB else "ed"
            for op in range(256):
                full = (op << 8) | (opcode & 0xFF)
                if (full & mask) == opcode:
                    coverage[target].add(op)
            continue

        if subop is not None and opcode in (0xCB, 0xED):
            target = "cb" if opcode == 0xCB else "ed"
            for op in range(256):
                if (op & subop_mask) == (int(subop) & subop_mask):
                    coverage[target].add(op)
            continue

        for op in range(256):
            if (op & (mask & 0xFF)) == (opcode & 0xFF):
                coverage["base"].add(op)

    result: Dict[str, Dict[str, Any]] = {}
    for space_name, covered in coverage.items():
        missing = sorted(op for op in range(256) if op not in covered)
        result[space_name] = {
            "covered": len(covered),
            "missing": missing,
        }
    return result
