"""Debug features generator."""

from typing import Dict, Any


def generate_debug_header(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate debug header file."""

    cpu_prefix = cpu_name.lower()

    return f"""#ifndef {cpu_name.upper()}_DEBUG_H
#define {cpu_name.upper()}_DEBUG_H

/* Debug functions are in {cpu_name}.h and {cpu_name}.c */

#endif
"""


def generate_debug_impl(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate debug implementation file."""

    cpu_prefix = cpu_name.lower()

    return """/* Debug functions are implemented in the main cpu.c */
"""
