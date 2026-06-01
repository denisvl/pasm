"""Runtime functions generator."""

from typing import Dict, Any

def generate_runtime_header(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate runtime header file."""

    cpu_prefix = cpu_name.lower()

    content = f"""#ifndef {cpu_name.upper()}_RUNTIME_H
#define {cpu_name.upper()}_RUNTIME_H

/* Runtime functions are in {cpu_name}.h and split runtime units. */

#endif
"""
    return content


def generate_runtime_impl(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate runtime implementation file."""

    cpu_prefix = cpu_name.lower()

    content = """/* Runtime functions are implemented in split runtime units. */
"""
    return content


def generate_system_rom_loader(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Emit system ROM loader implementation for split runtime units."""
    # Local import avoids widening module-level coupling.
    from .cpu_impl import _generate_system_rom_loader

    return _generate_system_rom_loader(isa_data, cpu_name.lower())


def generate_cartridge_rom_loader(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Emit cartridge ROM loader implementation for split runtime units."""
    # Local import avoids widening module-level coupling.
    from .cpu_impl import _generate_cartridge_rom_loader

    return _generate_cartridge_rom_loader(isa_data, cpu_name.lower())
