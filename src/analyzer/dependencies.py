"""Simple dependency extraction for ISA behavior snippets."""

import re
from typing import Any, Dict, List, Set


HELPER_CALL_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")


def collect_behavior_helpers(isa_data: Dict[str, Any]) -> Dict[str, List[str]]:
    """Collect helper-like function calls used by each instruction behavior."""
    dependencies: Dict[str, List[str]] = {}

    for inst in isa_data.get("instructions", []):
        name = inst.get("name", "UNKNOWN")
        behavior = inst.get("behavior", "")
        helpers: Set[str] = set()
        for match in HELPER_CALL_RE.finditer(behavior):
            helper_name = match.group(1)
            if helper_name not in {"if", "while", "for", "switch", "return", "sizeof"}:
                helpers.add(helper_name)
        dependencies[name] = sorted(helpers)

    return dependencies
