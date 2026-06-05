"""Split-unit emitters for system-side generated C translation units."""

import re
import textwrap
from typing import Any, Dict, List

from .cpu_impl import generate_cartridge_picker_runtime_glue
from .cpu_impl import generate_component_connections_glue
from .cpu_impl import generate_component_dispatch_glue
from .cpu_impl import generate_component_routing_glue
from .cpu_impl import generate_host_hal_contract_support
from .cpu_impl import generate_host_hal_impl_glue
from .cpu_impl import generate_input_runtime_glue
from .cpu_runtime import generate_cartridge_rom_loader, generate_system_rom_loader
from .interrupts import generate_interrupt_impl


def emit_split_unit(isa_data: Dict[str, Any], cpu_name: str, suffix: str) -> str:
    """Emit a split unit body by suffix ownership."""
    if suffix == "runtime":
        return generate_runtime_glue(isa_data, cpu_name)
    if suffix == "system_glue":
        return generate_system_interrupt_glue(isa_data, cpu_name)
    if suffix == "host_glue":
        return generate_host_picker_glue(isa_data, cpu_name)
    if suffix == "system_bus":
        return generate_system_bus_glue(isa_data, cpu_name)
    return (
        "/* Auto-generated split unit scaffold. */\n"
        f'#include "{cpu_name}.h"\n'
    )


def emit_ic_unit(isa_data: Dict[str, Any], cpu_name: str, component: Dict[str, Any]) -> str:
    """Emit a per-IC split compilation unit."""
    comp_id = str((component.get("metadata") or {}).get("id", "ic")).strip() or "ic"
    comp_ident = _to_ident(comp_id)
    read_body = _rewrite_memory_read_block(_component_snippet_block(component, "mem_read_pre"))
    write_body = _rewrite_memory_write_block(_component_snippet_block(component, "mem_write_pre"))
    port_read_pre = _rewrite_port_read_block(_component_snippet_block(component, "port_read_pre"))
    port_read_post = _rewrite_port_read_block(_component_snippet_block(component, "port_read_post"))
    port_write_pre = _rewrite_port_write_block(_component_snippet_block(component, "port_write_pre"))
    port_write_post = _rewrite_port_write_block(_component_snippet_block(component, "port_write_post"))
    lifecycle_create = _ic_lifecycle_create_block(component)
    lifecycle_reset = _ic_lifecycle_reset_block(component)
    lifecycle_destroy = _ic_lifecycle_destroy_block(component)
    step_pre = _component_snippet_block(component, "step_pre")
    step_post = _component_snippet_block(component, "step_post")
    needs_pasm_overlay_include = any(
        "pasm_overlay_" in snippet
        for snippet in (
            read_body,
            write_body,
            port_read_pre,
            port_read_post,
            port_write_pre,
            port_write_post,
            lifecycle_create,
            lifecycle_reset,
            lifecycle_destroy,
            step_pre,
            step_post,
        )
    )
    lines = [
        "/* Auto-generated split unit: per-IC ownership scaffold. */",
        f"/* IC id: {comp_id} */",
        f'#include "{cpu_name}.h"',
        '#include <pasm_overlay_draw.h>' if needs_pasm_overlay_include else "",
        "",
        f"uint8_t cpu_component_ic_{comp_ident}_bus_read(CPUState *cpu, uint16_t addr, uint8_t *handled) {{",
        "    if (handled != NULL) *handled = 0u;",
        f"{read_body}",
        "    return 0u;",
        "}",
        "",
        f"uint8_t cpu_component_ic_{comp_ident}_bus_write(CPUState *cpu, uint16_t addr, uint8_t value, uint8_t *handled) {{",
        "    if (handled != NULL) *handled = 0u;",
        f"{write_body}",
        "    return 0u;",
        "}",
        "",
        f"uint8_t cpu_component_ic_{comp_ident}_port_read_pre(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled) {{",
        "    if (handled != NULL) *handled = 0u;",
        f"{port_read_pre}",
        "    return value;",
        "}",
        "",
        f"uint8_t cpu_component_ic_{comp_ident}_port_read_post(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled) {{",
        "    if (handled != NULL) *handled = 0u;",
        f"{port_read_post}",
        "    return value;",
        "}",
        "",
        f"void cpu_component_ic_{comp_ident}_port_write_pre(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled) {{",
        "    if (handled != NULL) *handled = 0u;",
        f"{port_write_pre}",
        "    (void)value;",
        "}",
        "",
        f"void cpu_component_ic_{comp_ident}_port_write_post(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled) {{",
        "    if (handled != NULL) *handled = 0u;",
        f"{port_write_post}",
        "    (void)value;",
        "}",
        "",
        f"void cpu_component_ic_{comp_ident}_lifecycle_create(CPUState *cpu) {{",
        f"{lifecycle_create}",
        "}",
        "",
        f"void cpu_component_ic_{comp_ident}_lifecycle_reset(CPUState *cpu) {{",
        f"{lifecycle_reset}",
        "}",
        "",
        f"void cpu_component_ic_{comp_ident}_lifecycle_destroy(CPUState *cpu) {{",
        f"{lifecycle_destroy}",
        "}",
        "",
        f"void cpu_component_ic_{comp_ident}_step_pre(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before) {{",
        "    (void)inst;",
        "    (void)pc_before;",
        f"{step_pre}",
        "}",
        "",
        f"void cpu_component_ic_{comp_ident}_step_post(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before) {{",
        "    (void)inst;",
        "    (void)pc_before;",
        f"{step_post}",
        "}",
        "",
    ]
    return "\n".join(lines)


def _to_ident(name: str) -> str:
    ident = re.sub(r"[^0-9A-Za-z_]", "_", str(name).strip())
    ident = ident.lower().strip("_")
    if not ident:
        return "ic"
    if ident[0].isdigit():
        return f"ic_{ident}"
    return ident


def _escape_c_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _component_snippet_block(component: Dict[str, Any], snippet_key: str) -> str:
    behavior = component.get("behavior", {})
    snippets = behavior.get("snippets", {})
    snippet = str(snippets.get(snippet_key, "")).rstrip()
    if not snippet:
        return ""
    comp_id = str(component.get("metadata", {}).get("id", "component"))
    comp_ident = _to_ident(comp_id)
    comp_id_escaped = _escape_c_string(comp_id)
    lines = [
        "{",
        f"    ComponentState_{comp_ident} *comp = &cpu->comp_{comp_ident};",
        f'    cpu->active_component_id = "{comp_id_escaped}";',
    ]
    for raw_line in snippet.splitlines():
        if raw_line.strip():
            lines.append(f"    {raw_line.rstrip()}")
        else:
            lines.append("")
    lines.append("}")
    return "\n".join(lines)


def _iter_all_components(isa_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    comps: List[Dict[str, Any]] = []
    for key in ("ics", "devices", "hosts"):
        for comp in list(isa_data.get(key, []) or []):
            if isinstance(comp, dict):
                comps.append(comp)
    cart = isa_data.get("cartridge")
    if isinstance(cart, dict) and cart:
        comps.append(cart)
    return comps


def _rewrite_memory_read_block(block: str) -> str:
    if not block.strip():
        return "    (void)cpu;\n    (void)addr;"
    # Rewrite every return <expr>; to mark handled and return value.
    return re.sub(
        r"return\s+([^;]+);",
        r"do { if (handled != NULL) *handled = 1u; return \1; } while (0);",
        block,
    )


def _rewrite_memory_write_block(block: str) -> str:
    if not block.strip():
        return "    (void)cpu;\n    (void)addr;\n    (void)value;"
    # Rewrite every bare return; to mark handled and return success.
    return re.sub(
        r"return\s*;",
        "do { if (handled != NULL) *handled = 1u; return 1u; } while (0);",
        block,
    )


def _rewrite_port_read_block(block: str) -> str:
    if not block.strip():
        return ""
    block = re.sub(
        r"return\s+([^;]+);",
        r"do { if (handled != NULL) *handled = 1u; return \1; } while (0);",
        block,
    )
    block = re.sub(
        r"return\s*;",
        "do { if (handled != NULL) *handled = 1u; return value; } while (0);",
        block,
    )
    return block


def _rewrite_port_write_block(block: str) -> str:
    if not block.strip():
        return ""
    return re.sub(
        r"return\s*;",
        "do { if (handled != NULL) *handled = 1u; return; } while (0);",
        block,
    )


def _ic_lifecycle_create_block(component: Dict[str, Any]) -> str:
    comp_id = str((component.get("metadata") or {}).get("id", "ic")).strip() or "ic"
    comp_ident = _to_ident(comp_id)
    lines: List[str] = [
        f"    ComponentState_{comp_ident} *comp = &cpu->comp_{comp_ident};",
        f'    cpu->active_component_id = "{_escape_c_string(comp_id)}";',
    ]
    for field in component.get("state", []) or []:
        field_name = _to_ident(str(field.get("name", "field")))
        initial = str(field.get("initial", "0")).strip() or "0"
        lines.append(f"    comp->{field_name} = {initial};")
    snippet = _component_snippet_block(component, "init")
    if snippet:
        lines.append(textwrap.indent(snippet, "    "))
    return "\n".join(lines)


def _ic_lifecycle_reset_block(component: Dict[str, Any]) -> str:
    comp_id = str((component.get("metadata") or {}).get("id", "ic")).strip() or "ic"
    comp_ident = _to_ident(comp_id)
    lines: List[str] = [
        f"    ComponentState_{comp_ident} *comp = &cpu->comp_{comp_ident};",
        f'    cpu->active_component_id = "{_escape_c_string(comp_id)}";',
    ]
    for field in component.get("state", []) or []:
        field_name = _to_ident(str(field.get("name", "field")))
        field_type = str(field.get("type", "")).strip()
        initial = str(field.get("initial", "0")).strip() or "0"
        preserve_reset_field = field_name in {"rom_data", "rom_size"}
        if ("*" not in field_type) and (not preserve_reset_field):
            lines.append(f"    comp->{field_name} = {initial};")
    snippet = _component_snippet_block(component, "reset")
    if snippet:
        lines.append(textwrap.indent(snippet, "    "))
    return "\n".join(lines)


def _ic_lifecycle_destroy_block(component: Dict[str, Any]) -> str:
    snippet = _component_snippet_block(component, "destroy")
    if snippet:
        return textwrap.indent(snippet, "    ")
    return "    (void)cpu;"


def generate_system_bus_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate split system_bus unit ownership for address-space mapping hooks."""
    ics = [c for c in list(isa_data.get("ics", []) or []) if isinstance(c, dict)]
    ic_idents = [_to_ident(str((c.get("metadata") or {}).get("id", "ic"))) for c in ics]
    all_components = _iter_all_components(isa_data)

    external_components: List[Dict[str, Any]] = []
    ic_ident_set = set(ic_idents)
    for comp in all_components:
        comp_id = str((comp.get("metadata") or {}).get("id", "component")).strip() or "component"
        comp_ident = _to_ident(comp_id)
        if comp_ident in ic_ident_set:
            continue
        # Only emit bus/port hooks for components that actually define any.
        has_mem_or_port = bool(
            _component_snippet_block(comp, "mem_read_pre").strip()
            or _component_snippet_block(comp, "mem_write_pre").strip()
            or _component_snippet_block(comp, "port_read_pre").strip()
            or _component_snippet_block(comp, "port_read_post").strip()
            or _component_snippet_block(comp, "port_write_pre").strip()
            or _component_snippet_block(comp, "port_write_post").strip()
        )
        if has_mem_or_port:
            external_components.append(comp)
    decls: List[str] = []
    for ident in ic_idents:
        decls.extend(
            [
                f"uint8_t cpu_component_ic_{ident}_bus_read(CPUState *cpu, uint16_t addr, uint8_t *handled);",
                f"uint8_t cpu_component_ic_{ident}_bus_write(CPUState *cpu, uint16_t addr, uint8_t value, uint8_t *handled);",
                f"uint8_t cpu_component_ic_{ident}_port_read_pre(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled);",
                f"uint8_t cpu_component_ic_{ident}_port_read_post(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled);",
                f"void cpu_component_ic_{ident}_port_write_pre(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled);",
                f"void cpu_component_ic_{ident}_port_write_post(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled);",
            ]
        )
    for comp in external_components:
        comp_id = str((comp.get("metadata") or {}).get("id", "component")).strip() or "component"
        comp_ident = _to_ident(comp_id)
        read_body = _rewrite_memory_read_block(_component_snippet_block(comp, "mem_read_pre"))
        write_body = _rewrite_memory_write_block(_component_snippet_block(comp, "mem_write_pre"))
        port_read_pre = _rewrite_port_read_block(_component_snippet_block(comp, "port_read_pre"))
        port_read_post = _rewrite_port_read_block(_component_snippet_block(comp, "port_read_post"))
        port_write_pre = _rewrite_port_write_block(_component_snippet_block(comp, "port_write_pre"))
        port_write_post = _rewrite_port_write_block(_component_snippet_block(comp, "port_write_post"))
        decls.extend(
            [
                f"static uint8_t cpu_component_ext_{comp_ident}_bus_read(CPUState *cpu, uint16_t addr, uint8_t *handled) {{",
                "    if (handled != NULL) *handled = 0u;",
                read_body,
                "    return 0u;",
                "}",
                "",
                f"static uint8_t cpu_component_ext_{comp_ident}_bus_write(CPUState *cpu, uint16_t addr, uint8_t value, uint8_t *handled) {{",
                "    if (handled != NULL) *handled = 0u;",
                write_body,
                "    return 0u;",
                "}",
                "",
                f"static uint8_t cpu_component_ext_{comp_ident}_port_read_pre(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled) {{",
                "    if (handled != NULL) *handled = 0u;",
                port_read_pre,
                "    return value;",
                "}",
                "",
                f"static uint8_t cpu_component_ext_{comp_ident}_port_read_post(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled) {{",
                "    if (handled != NULL) *handled = 0u;",
                port_read_post,
                "    return value;",
                "}",
                "",
                f"static void cpu_component_ext_{comp_ident}_port_write_pre(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled) {{",
                "    if (handled != NULL) *handled = 0u;",
                port_write_pre,
                "    (void)value;",
                "}",
                "",
                f"static void cpu_component_ext_{comp_ident}_port_write_post(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled) {{",
                "    if (handled != NULL) *handled = 0u;",
                port_write_post,
                "    (void)value;",
                "}",
                "",
            ]
        )
    read_dispatch: List[str] = []
    write_dispatch: List[str] = []
    port_read_pre_dispatch: List[str] = []
    port_read_post_dispatch: List[str] = []
    port_write_pre_dispatch: List[str] = []
    port_write_post_dispatch: List[str] = []
    for ident in ic_idents:
        read_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        uint8_t __ic_value = cpu_component_ic_{ident}_bus_read(cpu, addr, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return __ic_value;",
                "        }",
                "    }",
            ]
        )
        write_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        (void)cpu_component_ic_{ident}_bus_write(cpu, addr, value, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return 1u;",
                "        }",
                "    }",
            ]
        )
        port_read_pre_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        value = cpu_component_ic_{ident}_port_read_pre(cpu, port, value, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return value;",
                "        }",
                "    }",
            ]
        )
        port_read_post_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        value = cpu_component_ic_{ident}_port_read_post(cpu, port, value, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return value;",
                "        }",
                "    }",
            ]
        )
        port_write_pre_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        cpu_component_ic_{ident}_port_write_pre(cpu, port, value, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return;",
                "        }",
                "    }",
            ]
        )
        port_write_post_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        cpu_component_ic_{ident}_port_write_post(cpu, port, value, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return;",
                "        }",
                "    }",
            ]
        )
    for comp in external_components:
        comp_ident = _to_ident(str((comp.get("metadata") or {}).get("id", "component")).strip() or "component")
        read_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        uint8_t __ic_value = cpu_component_ext_{comp_ident}_bus_read(cpu, addr, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return __ic_value;",
                "        }",
                "    }",
            ]
        )
        write_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        (void)cpu_component_ext_{comp_ident}_bus_write(cpu, addr, value, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return 1u;",
                "        }",
                "    }",
            ]
        )
        port_read_pre_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        value = cpu_component_ext_{comp_ident}_port_read_pre(cpu, port, value, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return value;",
                "        }",
                "    }",
            ]
        )
        port_read_post_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        value = cpu_component_ext_{comp_ident}_port_read_post(cpu, port, value, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return value;",
                "        }",
                "    }",
            ]
        )
        port_write_pre_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        cpu_component_ext_{comp_ident}_port_write_pre(cpu, port, value, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return;",
                "        }",
                "    }",
            ]
        )
        port_write_post_dispatch.extend(
            [
                "    {",
                "        uint8_t __ic_handled = 0u;",
                f"        cpu_component_ext_{comp_ident}_port_write_post(cpu, port, value, &__ic_handled);",
                "        if (__ic_handled != 0u) {",
                "            if (handled != NULL) *handled = 1u;",
                "            return;",
                "        }",
                "    }",
            ]
        )
    parts: List[str] = []
    parts.append("/* Auto-generated split unit: system bus ownership. */\n")
    parts.append(f'#include "{cpu_name}.h"\n\n')
    if decls:
        parts.append("\n".join(decls) + "\n\n")
    parts.append("uint8_t cpu_components_bus_read(CPUState *cpu, uint16_t addr, uint8_t *handled) {\n")
    parts.append("    if (handled != NULL) *handled = 0u;\n")
    if read_dispatch:
        parts.append("\n".join(read_dispatch) + "\n")
    parts.append("    return 0u;\n")
    parts.append("}\n\n")
    parts.append("uint8_t cpu_components_bus_write(CPUState *cpu, uint16_t addr, uint8_t value, uint8_t *handled) {\n")
    parts.append("    if (handled != NULL) *handled = 0u;\n")
    if write_dispatch:
        parts.append("\n".join(write_dispatch) + "\n")
    parts.append("    return 0u;\n")
    parts.append("}\n\n")
    parts.append("uint8_t cpu_components_port_read(CPUState *cpu, uint16_t port, uint8_t *handled) {\n")
    parts.append("    if (handled != NULL) *handled = 0u;\n")
    parts.append("    size_t port_index = (cpu->port_size > 0u) ? ((size_t)port % cpu->port_size) : 0u;\n")
    parts.append("    uint8_t value = (cpu->port_size > 0u) ? cpu->port_memory[port_index] : 0xFF;\n")
    if port_read_pre_dispatch:
        parts.append("\n".join(port_read_pre_dispatch) + "\n")
    if port_read_post_dispatch:
        parts.append("\n".join(port_read_post_dispatch) + "\n")
    parts.append("    if (handled != NULL) *handled = 1u;\n")
    parts.append("    return value;\n")
    parts.append("}\n\n")
    parts.append("void cpu_components_port_write(CPUState *cpu, uint16_t port, uint8_t value, uint8_t *handled) {\n")
    parts.append("    if (handled != NULL) *handled = 0u;\n")
    if port_write_pre_dispatch:
        parts.append("\n".join(port_write_pre_dispatch) + "\n")
    parts.append("    if (cpu->port_size == 0u) return;\n")
    parts.append("    size_t port_index = (size_t)port % cpu->port_size;\n")
    parts.append("    cpu->port_memory[port_index] = value;\n")
    if port_write_post_dispatch:
        parts.append("\n".join(port_write_post_dispatch) + "\n")
    parts.append("    if (handled != NULL) *handled = 1u;\n")
    parts.append("    return;\n")
    parts.append("}\n")
    return "".join(parts)


def _single_host_backend_target(isa_data: Dict[str, Any]) -> str:
    target = str(isa_data.get("host_backend_target", "")).strip().lower()
    hosts = isa_data.get("hosts", []) or []
    if not target and hosts:
        declared = sorted(
            {
                str((host.get("backend") or {}).get("target", "")).strip().lower()
                for host in hosts
                if isinstance(host, dict)
            }
            - {""}
        )
        if len(declared) == 1:
            target = declared[0]
    return target


def extract_split_section(text: str, section: str) -> str:
    """Extract marker-delimited section text from generated helper code."""
    blocks = extract_split_sections(text, section)
    return blocks[0] if blocks else ""


def extract_split_sections(text: str, section: str) -> list[str]:
    """Extract all marker-delimited section blocks from generated helper code."""
    begin = f"/* PASM_SPLIT_BEGIN:{section} */"
    end = f"/* PASM_SPLIT_END:{section} */"
    blocks: list[str] = []
    cursor = 0
    while True:
        start = text.find(begin, cursor)
        if start < 0:
            break
        stop = text.find(end, start + len(begin))
        if stop < 0:
            break
        blocks.append(text[start + len(begin) : stop].strip())
        cursor = stop + len(end)
    return blocks


def promote_host_hal_symbols(text: str) -> str:
    """Promote extracted host-hal symbols so host_glue can own/link them later.

    This intentionally only rewrites lines that start with `static` and contain
    host-hal-prefixed symbols, leaving unrelated static helpers untouched.
    """
    out_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("static ") and "cpu_host_hal_" in stripped:
            indent = line[: len(line) - len(stripped)]
            out_lines.append(indent + stripped[len("static ") :])
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def extract_host_hal_function_prototypes(text: str) -> list[str]:
    """Extract function prototypes from promoted host-hal implementation text."""
    prototypes: list[str] = []
    sig_re = re.compile(
        r"^(?P<prefix>(?:static\s+)?(?:inline\s+)?[\w\s\*]+?)\s*"
        r"(?P<name>cpu_host_hal_[A-Za-z0-9_]+)\s*\((?P<args>[^)]*)\)\s*\{\s*$"
    )
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = sig_re.match(line)
        if not m:
            continue
        prefix = m.group("prefix").strip()
        if prefix.startswith("static "):
            prefix = prefix[len("static ") :].strip()
        joiner = "" if prefix.endswith("*") else " "
        prototypes.append(f"{prefix}{joiner}{m.group('name')}({m.group('args').strip()});")
    return prototypes


def generate_host_picker_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate host-side picker bridge wrappers for split host_glue ownership."""
    host_hal_impl = promote_host_hal_symbols(generate_host_hal_impl_glue(isa_data, cpu_name))
    backend_target = _single_host_backend_target(isa_data)
    backend_include = ""
    if backend_target == "sdl2":
        backend_include = "#include <SDL2/SDL.h>\n"
    host_hal_prelude = (
        "#include <stdio.h>\n"
        "#include <stdlib.h>\n"
        "#include <string.h>\n"
        + backend_include
        + "#define CPU_HOST_HAT_UP 0x01u\n"
        + "#define CPU_HOST_HAT_RIGHT 0x02u\n"
        + "#define CPU_HOST_HAT_DOWN 0x04u\n"
        + "#define CPU_HOST_HAT_LEFT 0x08u\n"
        + "\n"
    )
    has_cartridge = bool(isa_data.get("cartridge"))
    if has_cartridge:
        return (
            "/* Auto-generated split unit: host-side glue ownership. */\n"
            f'#include "{cpu_name}.h"\n\n'
            + host_hal_prelude
            + host_hal_impl
            + "\n"
            "extern int cpu_component_cartridge_picker_set_dir(const char *path);\n"
            "extern uint8_t cpu_component_cartridge_picker_is_active(void);\n"
            "extern void cpu_component_cartridge_picker_update(CPUState *cpu, uint8_t has_focus);\n"
            "extern void cpu_component_cartridge_picker_draw_overlay(CPUState *cpu, uint32_t *pixels, uint32_t w, uint32_t h);\n\n"
            "int cpu_component_host_picker_set_dir(const char *path) {\n"
            "    return cpu_component_cartridge_picker_set_dir(path);\n"
            "}\n\n"
            "uint8_t cpu_component_host_picker_is_active(void) {\n"
            "    return cpu_component_cartridge_picker_is_active();\n"
            "}\n\n"
            "void cpu_component_host_picker_step(CPUState *cpu, uint8_t has_focus) {\n"
            "    cpu_component_cartridge_picker_update(cpu, has_focus);\n"
            "}\n\n"
            "void cpu_component_host_picker_draw_overlay(CPUState *cpu, uint32_t *pixels, uint32_t w, uint32_t h) {\n"
            "    cpu_component_cartridge_picker_draw_overlay(cpu, pixels, w, h);\n"
            "}\n"
        )
    return (
        "/* Auto-generated split unit: host-side glue ownership. */\n"
        f'#include "{cpu_name}.h"\n\n'
        + host_hal_prelude
        + host_hal_impl
        + "\n"
        "int cpu_component_host_picker_set_dir(const char *path) {\n"
        "    (void)path;\n"
        "    return -1;\n"
        "}\n\n"
        "uint8_t cpu_component_host_picker_is_active(void) {\n"
        "    return 0u;\n"
        "}\n\n"
        "void cpu_component_host_picker_step(CPUState *cpu, uint8_t has_focus) {\n"
        "    (void)cpu;\n"
        "    (void)has_focus;\n"
        "}\n\n"
        "void cpu_component_host_picker_draw_overlay(CPUState *cpu, uint32_t *pixels, uint32_t w, uint32_t h) {\n"
        "    (void)cpu;\n"
        "    (void)pixels;\n"
        "    (void)w;\n"
        "    (void)h;\n"
        "}\n"
    )


def generate_runtime_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate split runtime unit ownership (ROM/cartridge loaders)."""
    return (
        "/* Auto-generated split unit: system-side runtime ownership. */\n"
        f'#include "{cpu_name}.h"\n\n'
        + generate_system_rom_loader(isa_data, cpu_name)
        + "\n"
        + generate_cartridge_rom_loader(isa_data, cpu_name)
        + "\n"
    )


def generate_system_interrupt_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate split system_glue unit ownership for routing/dispatch/interrupt glue."""
    backend_target = _single_host_backend_target(isa_data)
    backend_include = ""
    if backend_target == "sdl2":
        backend_include = (
            "#include <SDL2/SDL.h>\n"
            "#ifndef CPU_HOST_AUDIO_ALLOW_FREQUENCY_CHANGE\n"
            "#define CPU_HOST_AUDIO_ALLOW_FREQUENCY_CHANGE 0x00000001\n"
            "#endif\n"
            "#ifndef CPU_HOST_AUDIO_ALLOW_FORMAT_CHANGE\n"
            "#define CPU_HOST_AUDIO_ALLOW_FORMAT_CHANGE 0x00000002\n"
            "#endif\n"
            "#ifndef CPU_HOST_AUDIO_ALLOW_CHANNELS_CHANGE\n"
            "#define CPU_HOST_AUDIO_ALLOW_CHANNELS_CHANGE 0x00000004\n"
            "#endif\n"
            "#ifndef CPU_HOST_AUDIO_ALLOW_SAMPLES_CHANGE\n"
            "#define CPU_HOST_AUDIO_ALLOW_SAMPLES_CHANGE 0x00000008\n"
            "#endif\n"
            "#ifndef SDL_AUDIO_ALLOW_ANY_CHANGE\n"
            "#define SDL_AUDIO_ALLOW_ANY_CHANGE ("
            "SDL_AUDIO_ALLOW_FREQUENCY_CHANGE | "
            "SDL_AUDIO_ALLOW_FORMAT_CHANGE | "
            "SDL_AUDIO_ALLOW_CHANNELS_CHANGE | "
            "SDL_AUDIO_ALLOW_SAMPLES_CHANGE)\n"
            "#endif\n\n"
        )
    component_runtime = generate_component_runtime_dispatch_glue(isa_data)
    component_lifecycle = generate_component_lifecycle_dispatch_glue(isa_data)
    component_dispatch = generate_component_dispatch_glue(isa_data, cpu_name)
    component_routing = generate_component_routing_glue(isa_data, cpu_name)
    component_connections = generate_component_connections_glue(isa_data, cpu_name)
    picker_runtime = generate_cartridge_picker_runtime_glue(isa_data, cpu_name)
    host_hal_support = generate_host_hal_contract_support(isa_data, cpu_name)
    input_runtime_impl = generate_input_runtime_glue(isa_data, cpu_name)
    overlay_include = (
        "#include <pasm_overlay.h>\n\n"
        if (
            "pasm_overlay_" in component_runtime
            or "pasm_overlay_" in component_dispatch
            or "pasm_overlay_" in component_routing
            or "pasm_overlay_" in component_connections
            or "pasm_overlay_" in picker_runtime
            or "pasm_overlay_" in input_runtime_impl
        )
        else ""
    )
    return (
        "/* Auto-generated split unit: system-side glue ownership. */\n"
        f'#include "{cpu_name}.h"\n\n'
        + overlay_include
        + backend_include
        + host_hal_support
        + input_runtime_impl
        + picker_runtime
        + component_connections
        + component_dispatch
        + component_routing
        + component_lifecycle
        + component_runtime
        + "\n"
        + generate_interrupt_impl(isa_data, cpu_name)
        + "\n"
    )


def generate_component_lifecycle_dispatch_glue(isa_data: Dict[str, Any]) -> str:
    """Generate lifecycle dispatch wrappers that call per-IC ownership units."""
    ics = [c for c in list(isa_data.get("ics", []) or []) if isinstance(c, dict)]
    idents = [_to_ident(str((c.get("metadata") or {}).get("id", "ic"))) for c in ics]
    ic_ids = {
        str((c.get("metadata") or {}).get("id", "")).strip()
        for c in ics
    }
    host_ids = {
        str((c.get("metadata") or {}).get("id", "")).strip()
        for c in list(isa_data.get("hosts", []) or [])
        if isinstance(c, dict)
    }
    non_ic_components = [
        c for c in _iter_all_components(isa_data)
        if str((c.get("metadata") or {}).get("id", "")).strip() not in ic_ids
    ]
    has_any_components = bool(idents or non_ic_components)
    lines: List[str] = []
    for ident in idents:
        lines.extend(
            [
                f"void cpu_component_ic_{ident}_lifecycle_create(CPUState *cpu);",
                f"void cpu_component_ic_{ident}_lifecycle_reset(CPUState *cpu);",
                f"void cpu_component_ic_{ident}_lifecycle_destroy(CPUState *cpu);",
            ]
        )
    lines.append("")
    lines.extend(
        [
            "void cpu_component_lifecycle_create(CPUState *cpu) {",
        ]
    )
    if has_any_components:
        lines.extend(
            [
                "    cpu->active_component_id = NULL;",
                "    cpu->component_last_return = 0;",
            ]
        )
    if idents:
        for ident in idents:
            lines.append(f"    cpu_component_ic_{ident}_lifecycle_create(cpu);")
    for comp in non_ic_components:
        comp_id = str((comp.get("metadata") or {}).get("id", "")).strip()
        comp_ident = _to_ident(comp_id)
        lines.append(f"    {{ ComponentState_{comp_ident} *comp = &cpu->comp_{comp_ident};")
        lines.append(f'      cpu->active_component_id = "{_escape_c_string(comp_id)}";')
        for field in comp.get("state", []) or []:
            field_name = _to_ident(str(field.get("name", "field")))
            initial = str(field.get("initial", "0")).strip() or "0"
            lines.append(f"      comp->{field_name} = {initial};")
        init_snippet = _component_snippet_block(comp, "init")
        if init_snippet:
            lines.append(textwrap.indent(init_snippet, "      "))
        lines.append("    }")
    if not idents and not non_ic_components:
        lines.append("    (void)cpu;")
    lines.extend(
        [
            "}",
            "",
            "void cpu_component_lifecycle_reset(CPUState *cpu) {",
        ]
    )
    if has_any_components:
        lines.extend(
            [
                "    cpu->active_component_id = NULL;",
                "    cpu->component_last_return = 0;",
            ]
        )
    if idents:
        for ident in idents:
            lines.append(f"    cpu_component_ic_{ident}_lifecycle_reset(cpu);")
    for comp in non_ic_components:
        comp_id = str((comp.get("metadata") or {}).get("id", "")).strip()
        comp_ident = _to_ident(comp_id)
        is_host_component = comp_id in host_ids
        lines.append(f"    {{ ComponentState_{comp_ident} *comp = &cpu->comp_{comp_ident};")
        lines.append(f'      cpu->active_component_id = "{_escape_c_string(comp_id)}";')
        if not is_host_component:
            for field in comp.get("state", []) or []:
                field_name = _to_ident(str(field.get("name", "field")))
                field_type = str(field.get("type", "")).strip()
                initial = str(field.get("initial", "0")).strip() or "0"
                preserve_reset_field = field_name in {"rom_data", "rom_size"}
                if ("*" not in field_type) and (not preserve_reset_field):
                    lines.append(f"      comp->{field_name} = {initial};")
        reset_snippet = _component_snippet_block(comp, "reset")
        if reset_snippet:
            lines.append(textwrap.indent(reset_snippet, "      "))
        lines.append("    }")
    if not idents and not non_ic_components:
        lines.append("    (void)cpu;")
    lines.extend(
        [
            "}",
            "",
            "void cpu_component_lifecycle_destroy(CPUState *cpu) {",
        ]
    )
    if idents:
        for ident in idents:
            lines.append(f"    cpu_component_ic_{ident}_lifecycle_destroy(cpu);")
    for comp in non_ic_components:
        destroy_snippet = _component_snippet_block(comp, "destroy")
        if destroy_snippet:
            lines.append(textwrap.indent(destroy_snippet, "    "))
    if not idents and not non_ic_components:
        lines.append("    (void)cpu;")
    lines.extend(["}", ""])
    return "\n".join(lines)


def generate_component_runtime_dispatch_glue(isa_data: Dict[str, Any]) -> str:
    """Generate runtime/step wrappers that dispatch IC step hooks only."""
    ics = [c for c in list(isa_data.get("ics", []) or []) if isinstance(c, dict)]
    pre_hook_ics = [
        (c, _to_ident(str((c.get("metadata") or {}).get("id", "ic"))))
        for c in ics
        if _component_snippet_block(c, "step_pre")
    ]
    post_hook_ics = [
        (c, _to_ident(str((c.get("metadata") or {}).get("id", "ic"))))
        for c in ics
        if _component_snippet_block(c, "step_post")
    ]
    ic_ids = {
        str((c.get("metadata") or {}).get("id", "")).strip()
        for c in ics
    }
    non_ic_components = [
        c for c in _iter_all_components(isa_data)
        if str((c.get("metadata") or {}).get("id", "")).strip() not in ic_ids
    ]
    has_runtime_cartridge = bool(isa_data.get("cartridge"))
    lines: List[str] = []
    for _, ident in pre_hook_ics:
        lines.append(f"void cpu_component_ic_{ident}_step_pre(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before);")
    for _, ident in post_hook_ics:
        lines.append(f"void cpu_component_ic_{ident}_step_post(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before);")
    lines.extend(
        [
            "",
            "int cpu_components_runtime_pre_step(CPUState *cpu) {",
            "    if (cpu != NULL && cpu->reset_delay_pending) {",
            "        cpu->reset_delay_pending = false;",
            "    }",
        ]
    )
    if has_runtime_cartridge:
        lines.extend(
            [
                "    if (cpu_component_cartridge_picker_apply_pending_swap(cpu) != 0) {",
                "        return -1;",
                "    }",
            ]
        )
    lines.extend(
        [
            "    (void)cpu;",
            "    return 0;",
            "}",
            "",
            "void cpu_components_step_pre(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before) {",
        ]
    )
    emitted_pre = False
    if pre_hook_ics:
        for _, ident in pre_hook_ics:
            lines.append(f"    cpu_component_ic_{ident}_step_pre(cpu, inst, pc_before);")
            emitted_pre = True
    for comp in non_ic_components:
        snippet = _component_snippet_block(comp, "step_pre")
        if snippet:
            lines.append(textwrap.indent(snippet, "    "))
            emitted_pre = True
    if not emitted_pre:
        lines.extend(["    (void)cpu;", "    (void)inst;", "    (void)pc_before;"])
    lines.extend(
        [
            "}",
            "",
            "void cpu_components_step_post(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before) {",
        ]
    )
    if has_runtime_cartridge:
        lines.append("    cpu_component_cartridge_picker_update(cpu, cpu_host_hal_window_has_focus(NULL));")
    emitted_post = has_runtime_cartridge
    if post_hook_ics:
        for _, ident in post_hook_ics:
            lines.append(f"    cpu_component_ic_{ident}_step_post(cpu, inst, pc_before);")
            emitted_post = True
    for comp in non_ic_components:
        snippet = _component_snippet_block(comp, "step_post")
        if snippet:
            lines.append(textwrap.indent(snippet, "    "))
            emitted_post = True
    if not emitted_post:
        lines.extend(["    (void)cpu;", "    (void)inst;", "    (void)pc_before;"])
    else:
        lines.extend(["    (void)inst;", "    (void)pc_before;"])
    lines.extend(["}", ""])
    return "\n".join(lines)
