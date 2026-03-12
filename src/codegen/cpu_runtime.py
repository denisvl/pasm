"""Runtime functions generator."""

from typing import Dict, Any


def generate_runtime_header(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate runtime header file."""

    cpu_prefix = cpu_name.lower()

    content = f"""#ifndef {cpu_name.upper()}_RUNTIME_H
#define {cpu_name.upper()}_RUNTIME_H

/* Runtime functions are in {cpu_name}.h and {cpu_name}.c */

#endif
"""
    return content


def generate_runtime_impl(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate runtime implementation file."""

    cpu_prefix = cpu_name.lower()

    content = """/* Runtime functions are implemented in the main cpu.c */
"""
    return content
