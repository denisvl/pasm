"""Execution hooks generator."""

from typing import Dict, Any

from .templates import get_template

HOOK_NAMES = (
    "pre_fetch",
    "post_decode",
    "post_execute",
    "port_read_pre",
    "port_read_post",
    "port_write_pre",
    "port_write_post",
)


def generate_hooks(isa_data: Dict[str, Any], cpu_name: str) -> tuple:
    """Generate hooks header and implementation if enabled."""

    hooks_config = isa_data.get("hooks", {})

    # Check if any hooks are enabled
    has_hooks = any(
        hooks_config.get(h, {}).get("enabled", False)
        for h in HOOK_NAMES
    )

    if not has_hooks:
        return None, None

    cpu_prefix = cpu_name.lower()

    # Header
    header_template = get_template("hooks_header")
    header = header_template.format(
        cpu_name=cpu_name,
        cpu_prefix=cpu_prefix,
        guard_name=cpu_name.upper(),
        isa_name=isa_data.get("metadata", {}).get("name", cpu_name),
    )

    # Implementation
    impl_template = get_template("hooks_impl")
    impl = impl_template.format(
        cpu_name=cpu_name,
        cpu_prefix=cpu_prefix,
        isa_name=isa_data.get("metadata", {}).get("name", cpu_name),
    )

    return header, impl


def get_hooks_enabled(isa_data: Dict[str, Any]) -> Dict[str, bool]:
    """Get which hooks are enabled."""
    hooks_config = isa_data.get("hooks", {})
    return {name: hooks_config.get(name, {}).get("enabled", False) for name in HOOK_NAMES}
