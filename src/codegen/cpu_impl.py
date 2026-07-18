"""CPU implementation file generator."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple
import textwrap

from .interrupts import configured_interrupt_modes, resolve_interrupt_model
from .templates import get_template
from ..parser.yaml_loader import ALLOWED_HOST_KEYS


DISPLAY_TEMPLATE_TOKEN_RE = re.compile(
    r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([A-Za-z_][A-Za-z0-9_]*))?\}"
)
SUPPORTED_DISPLAY_KINDS = {
    "table",
    "cc_table",
    "hex8",
    "hex16",
    "hex32",
    "hex8_plain",
    "hex16_plain",
    "hex8_asm",
    "hex16_asm",
    "signed8",
    "signed16",
    "unsigned",
    "mc6809_idx",
    "mc6809_pshs_mask",
    "mc6809_puls_mask",
    "mc6809_pshu_mask",
    "mc6809_pulu_mask",
}
TABLE_DISPLAY_KINDS = {"table", "cc_table"}
GENERIC_DISPLAY_KINDS = {
    "table",
    "cc_table",
    "hex8",
    "hex16",
    "hex32",
    "hex8_plain",
    "hex16_plain",
    "hex8_asm",
    "hex16_asm",
    "signed8",
    "signed16",
    "unsigned",
}
MC6809_SPECIAL_DISPLAY_KINDS = {
    "mc6809_idx",
    "mc6809_pshs_mask",
    "mc6809_puls_mask",
    "mc6809_pshu_mask",
    "mc6809_pulu_mask",
}
SDL_UNSUPPORTED_SCANCODE_KEYS = {
    "LOCKINGCAPSLOCK",
    "LOCKINGNUMLOCK",
    "LOCKINGSCROLLLOCK",
}
GLFW_SCANCODE_KEYS = {
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "A",
    "APOSTROPHE",
    "APPLICATION",
    "B",
    "BACKSLASH",
    "BACKSPACE",
    "C",
    "CAPSLOCK",
    "COMMA",
    "D",
    "DELETE",
    "DOWN",
    "E",
    "END",
    "EQUALS",
    "ESCAPE",
    "F",
    "F1",
    "F2",
    "F3",
    "F4",
    "F5",
    "F6",
    "F7",
    "F8",
    "F9",
    "F10",
    "F11",
    "F12",
    "G",
    "GRAVE",
    "H",
    "HOME",
    "I",
    "INSERT",
    "INTERNATIONAL1",
    "J",
    "K",
    "KP_0",
    "KP_1",
    "KP_2",
    "KP_3",
    "KP_4",
    "KP_5",
    "KP_6",
    "KP_7",
    "KP_8",
    "KP_9",
    "KP_ENTER",
    "KP_PERIOD",
    "L",
    "LALT",
    "LCTRL",
    "LEFT",
    "LEFTBRACKET",
    "LSHIFT",
    "M",
    "MINUS",
    "N",
    "NONUSBACKSLASH",
    "NONUSHASH",
    "O",
    "P",
    "PAGEDOWN",
    "PAGEUP",
    "PAUSE",
    "PERIOD",
    "Q",
    "R",
    "RALT",
    "RCTRL",
    "RETURN",
    "RETURN2",
    "RIGHT",
    "RIGHTBRACKET",
    "RSHIFT",
    "S",
    "SEMICOLON",
    "SLASH",
    "SPACE",
    "T",
    "TAB",
    "U",
    "UP",
    "V",
    "W",
    "X",
    "Y",
    "Z",
}
BASE_DECODED_FIELD_WIDTHS = {
    "r": 8,
    "rs": 8,
    "rt": 8,
    "rd": 8,
    "imm": 16,
    "disp": 16,
    "addr": 16,
    "cc": 8,
    "length": 8,
    "cycles": 8,
    "opcode": 8,
    "prefix": 8,
    "pc": 16,
    "raw": 32,
}
CANONICAL_HOST_KEY_RE = re.compile(r"^[A-Z0-9_]+$")


def _require_codegen_config(isa_data: Dict[str, Any]) -> Dict[str, Any]:
    metadata = isa_data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("ISA metadata must be an object")
    codegen = metadata.get("codegen")
    if not isinstance(codegen, dict):
        raise ValueError("ISA metadata.codegen must be an object")
    return codegen


def _codegen_numeric_style(isa_data: Dict[str, Any]) -> str:
    style = str(_require_codegen_config(isa_data).get("numeric_style", "")).strip()
    if style not in {"c_hex", "asm_dollar", "z80_h"}:
        raise ValueError(
            "metadata.codegen.numeric_style must be one of: c_hex, asm_dollar, z80_h"
        )
    return style


def _codegen_numeric_formats(isa_data: Dict[str, Any]) -> Dict[str, str]:
    codegen = _require_codegen_config(isa_data)
    raw = codegen.get("numeric_formats")
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    style = _codegen_numeric_style(isa_data)
    if style == "asm_dollar":
        return {"hex8": "$%02X", "hex16": "$%04X"}
    if style == "z80_h":
        return {"hex8": "%02Xh", "hex16": "%04Xh"}
    return {"hex8": "0x%02X", "hex16": "0x%04X"}


def _codegen_flags_dump_style(isa_data: Dict[str, Any]) -> str:
    style = str(_require_codegen_config(isa_data).get("flags_dump_style", "")).strip()
    if style not in {"raw", "z80_compact"}:
        raise ValueError(
            "metadata.codegen.flags_dump_style must be one of: raw, z80_compact"
        )
    return style


def _codegen_enabled_display_kinds(isa_data: Dict[str, Any]) -> Set[str]:
    raw = _require_codegen_config(isa_data).get("display_kinds_enabled")
    if not isinstance(raw, list):
        raise ValueError("metadata.codegen.display_kinds_enabled must be an array")
    kinds = {str(kind).strip() for kind in raw}
    invalid = sorted(kind for kind in kinds if kind not in SUPPORTED_DISPLAY_KINDS)
    if invalid:
        raise ValueError(
            "metadata.codegen.display_kinds_enabled contains unsupported kinds: "
            + ", ".join(invalid)
        )
    return kinds | GENERIC_DISPLAY_KINDS


def _single_host_backend_target(isa_data: Dict[str, Any]) -> str:
    target = str(isa_data.get("host_backend_target", "")).strip().lower()
    hosts = isa_data.get("hosts", []) or []
    has_hosts = bool(hosts)
    if not target:
        if not has_hosts:
            return ""
        declared_targets = sorted(
            {
                str((host.get("backend") or {}).get("target", "")).strip().lower()
                for host in hosts
                if isinstance(host, dict)
            }
            - {""}
        )
        if not declared_targets:
            return ""
        if len(declared_targets) != 1:
            raise ValueError(
                f"multiple host backend targets are not supported for CPU generation: {declared_targets}"
            )
        target = declared_targets[0]
    if target not in {"sdl2", "stub", "glfw"}:
        raise ValueError(f"unsupported host backend target for CPU generation: {target}")
    return target


def generate_cpu_impl(
    isa_data: Dict[str, Any],
    cpu_name: str,
    dispatch_mode: str = "switch",
    include_loader_impls: bool = True,
    include_interrupt_impls: bool = True,
    exclude_split_sections: Optional[List[str]] = None,
) -> str:
    """Generate the CPU implementation file."""

    cpu_prefix = cpu_name.lower()

    # Generate helper functions
    helpers_code = _generate_helpers(isa_data, cpu_prefix)
    excluded = set(exclude_split_sections or [])
    for section in (exclude_split_sections or []):
        helpers_code = _remove_split_sections(helpers_code, section)
    coding_includes = _generate_coding_includes(isa_data)

    # Generate instruction implementations
    instructions_code = _generate_instructions(isa_data, cpu_prefix)

    # Generate dispatch
    dispatch_code = _generate_dispatch(isa_data, cpu_prefix, dispatch_mode)
    disassembler_code = _generate_disassembler(isa_data, cpu_prefix)
    interrupt_reset = _generate_interrupt_reset(isa_data, cpu_prefix)
    interrupt_reset_post = _generate_interrupt_reset_post(isa_data, cpu_prefix)
    register_field_reset = _generate_register_field_reset(isa_data)
    shadow_flags_reset = _generate_shadow_flags_reset(isa_data)
    interrupt_impl = (
        _generate_interrupt_impl(isa_data, cpu_prefix) if include_interrupt_impls else ""
    )
    hooks = isa_data.get("hooks", {})
    (
        port_read_hook_pre,
        port_read_hook_post,
        port_write_hook_pre,
        port_write_hook_post,
    ) = _generate_port_hook_snippets(hooks)
    memory_write_guard = _generate_memory_write_guard(isa_data)
    (
        ic_helpers_code,
        ic_init,
        ic_reset,
        ic_destroy,
        ic_mem_read_pre,
        ic_mem_write_pre,
        ic_port_read_pre,
        ic_port_read_post,
        ic_port_write_pre,
        ic_port_write_post,
        ic_impl,
    ) = _generate_ic_runtime_blocks(isa_data, cpu_prefix)

    def _indent_block(block: str, spaces: int = 4) -> str:
        content = block.strip("\n")
        if not content.strip():
            return ""
        return textwrap.indent(content, " " * spaces)

    lifecycle_helpers = [
        "void cpu_component_lifecycle_create(CPUState *cpu);",
        "void cpu_component_lifecycle_destroy(CPUState *cpu);",
        "void cpu_component_lifecycle_reset(CPUState *cpu);",
        "/* PASM_SPLIT_BEGIN:COMPONENT_LIFECYCLE */",
        "void cpu_component_lifecycle_create(CPUState *cpu) {",
    ]
    if ic_init.strip():
        lifecycle_helpers.append(_indent_block(ic_init))
    else:
        lifecycle_helpers.append("    (void)cpu;")
    lifecycle_helpers.extend(
        [
            "}",
            "",
            "void cpu_component_lifecycle_destroy(CPUState *cpu) {",
        ]
    )
    if ic_destroy.strip():
        lifecycle_helpers.append(_indent_block(ic_destroy))
    else:
        lifecycle_helpers.append("    (void)cpu;")
    lifecycle_helpers.extend(
        [
            "}",
            "",
            "void cpu_component_lifecycle_reset(CPUState *cpu) {",
        ]
    )
    if ic_reset.strip():
        lifecycle_helpers.append(_indent_block(ic_reset))
    else:
        lifecycle_helpers.append("    (void)cpu;")
    lifecycle_helpers.extend(["}", "/* PASM_SPLIT_END:COMPONENT_LIFECYCLE */", ""])
    ic_helpers_code = "\n".join(lifecycle_helpers) + "\n" + ic_helpers_code
    ic_init = "    cpu_component_lifecycle_create(cpu);"
    ic_destroy = "        cpu_component_lifecycle_destroy(cpu);"
    ic_reset = "    cpu_component_lifecycle_reset(cpu);"
    host_hal_core_prelude = ""
    host_hal_prototypes = []
    for section in excluded:
        ic_helpers_code = _remove_split_sections(ic_helpers_code, section)
    # COMPONENT_DISPATCH and INPUT_RUNTIME are now split-owned in system_glue.
    # Keep core emission untouched here; no linkage-promotion rewrite is needed.
    # HOST_HAL ownership now lives outside core; no HAL contract reinjection here.
    prefix_chunks: List[str] = []
    if host_hal_core_prelude.strip():
        prefix_chunks.append(host_hal_core_prelude.strip())
    if host_hal_prototypes:
        proto_lines = "\n".join(host_hal_prototypes).strip()
        if proto_lines:
            prefix_chunks.append(proto_lines)
    if prefix_chunks:
        ic_helpers_code = "\n\n".join(prefix_chunks) + "\n\n" + ic_helpers_code.lstrip()
    system_rom_loader = (
        _generate_system_rom_loader(isa_data, cpu_prefix) if include_loader_impls else ""
    )
    cartridge_rom_loader = (
        _generate_cartridge_rom_loader(isa_data, cpu_prefix) if include_loader_impls else ""
    )
    floppy_media_loader = (
        _generate_floppy_media_loader(isa_data, cpu_prefix) if include_loader_impls else ""
    )
    debug_flags_expr = _generate_debug_flags_expr(isa_data)

    hooks_impl = "/* Hook API is emitted in *_hooks.c when enabled. */"

    # Get metadata for template
    isa_name = isa_data.get("metadata", {}).get("name", cpu_name)
    register_count = len(isa_data.get("registers", []))
    ports_cfg = isa_data.get("ports", {})
    port_size = int(ports_cfg.get("size") or (1 << int(ports_cfg.get("address_bits", 16))))
    if port_size <= 0:
        port_size = 65536

    # Format template
    template = get_template("cpu_impl")

    return template.format(
        cpu_name=cpu_name,
        cpu_prefix=cpu_prefix,
        coding_includes=coding_includes,
        helpers_code=helpers_code,
        ic_helpers_code=ic_helpers_code,
        instructions_code=instructions_code,
        dispatch_code=dispatch_code,
        disassembler_code=disassembler_code,
        interrupt_reset=interrupt_reset,
        interrupt_reset_post=interrupt_reset_post,
        register_field_reset=register_field_reset,
        shadow_flags_reset=shadow_flags_reset,
        interrupt_impl=interrupt_impl,
        port_read_hook_pre=port_read_hook_pre,
        port_read_hook_post=port_read_hook_post,
        port_write_hook_pre=port_write_hook_pre,
        port_write_hook_post=port_write_hook_post,
        memory_write_guard=memory_write_guard,
        memory_read_trace="",
        ic_init=ic_init,
        ic_reset=ic_reset,
        ic_destroy=ic_destroy,
        ic_mem_read_pre=ic_mem_read_pre,
        ic_mem_write_pre=ic_mem_write_pre,
        ic_port_read_pre=ic_port_read_pre,
        ic_port_read_post=ic_port_read_post,
        ic_port_write_pre=ic_port_write_pre,
        ic_port_write_post=ic_port_write_post,
        word_access_impl=_generate_word_access_impl(isa_data, cpu_prefix),
        ic_impl=ic_impl,
        system_rom_loader=system_rom_loader,
        cartridge_rom_loader=cartridge_rom_loader,
        floppy_media_loader=floppy_media_loader,
        hooks_impl=hooks_impl,
        isa_name=isa_name,
        register_count=register_count,
        port_size=port_size,
        debug_flags_expr=debug_flags_expr,
    )


def _generate_debug_flags_expr(isa_data: Dict[str, Any]) -> str:
    """Generate expression used by dump_registers() when printing flags."""
    expr = _require_codegen_config(isa_data).get("debug_flags_expr")
    if isinstance(expr, str) and expr.strip():
        return expr.strip()

    style = _codegen_flags_dump_style(isa_data)
    if style == "raw":
        return "cpu->flags.raw"
    if style == "z80_compact":
        return (
        "(uint8_t)((((cpu->flags.raw >> 7) & 1u) << 0) | "
        "(((cpu->flags.raw >> 6) & 1u) << 1) | "
        "(((cpu->flags.raw >> 4) & 1u) << 2) | "
        "(((cpu->flags.raw >> 2) & 1u) << 3) | "
        "(((cpu->flags.raw >> 1) & 1u) << 4) | "
        "(((cpu->flags.raw >> 0) & 1u) << 5))"
        )
    raise ValueError(f"Unsupported metadata.codegen.flags_dump_style: {style}")


def _generate_word_access_impl(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate endian-correct 16-bit memory access helpers."""
    endian = str(isa_data.get("metadata", {}).get("endian", "little")).strip().lower()
    lines: List[str] = []
    lines.append(f"uint16_t {cpu_prefix}_read_word(CPUState *cpu, uint16_t addr) {{")
    if endian == "big":
        lines.append(f"    uint16_t hi = {cpu_prefix}_read_byte(cpu, addr);")
        lines.append(f"    uint16_t lo = {cpu_prefix}_read_byte(cpu, (uint16_t)(addr + 1u));")
        lines.append("    return (uint16_t)((hi << 8) | lo);")
    else:
        lines.append(f"    uint16_t lo = {cpu_prefix}_read_byte(cpu, addr);")
        lines.append(f"    uint16_t hi = {cpu_prefix}_read_byte(cpu, (uint16_t)(addr + 1u));")
        lines.append("    return (uint16_t)(lo | (hi << 8));")
    lines.append("}")
    lines.append("")
    lines.append(
        f"void {cpu_prefix}_write_word(CPUState *cpu, uint16_t addr, uint16_t value) {{"
    )
    if endian == "big":
        lines.append(
            f"    {cpu_prefix}_write_byte(cpu, addr, (uint8_t)((value >> 8) & 0xFFu));"
        )
        lines.append(
            f"    {cpu_prefix}_write_byte(cpu, (uint16_t)(addr + 1u), (uint8_t)(value & 0xFFu));"
        )
    else:
        lines.append(f"    {cpu_prefix}_write_byte(cpu, addr, (uint8_t)(value & 0xFFu));")
        lines.append(
            f"    {cpu_prefix}_write_byte(cpu, (uint16_t)(addr + 1u), (uint8_t)((value >> 8) & 0xFFu));"
        )
    lines.append("}")
    return "\n".join(lines)


def _extract_split_sections(text: str, section: str) -> List[str]:
    begin = f"/* PASM_SPLIT_BEGIN:{section} */"
    end = f"/* PASM_SPLIT_END:{section} */"
    blocks: List[str] = []
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


def _extract_host_hal_function_prototypes(blocks: List[str]) -> List[str]:
    protos: List[str] = []
    seen: set[str] = set()
    sig_re = re.compile(
        r"^(?P<prefix>(?:static\s+)?(?:inline\s+)?[\w\s\*]+?)\s*"
        r"(?P<name>cpu_host_hal_[A-Za-z0-9_]+)\s*\((?P<args>[^)]*)\)\s*\{\s*$"
    )
    for block in blocks:
        for raw in block.splitlines():
            line = raw.strip()
            if not line:
                continue
            m = sig_re.match(line)
            if not m:
                continue
            prefix = m.group("prefix").strip()
            # Core needs external declarations; never emit static here.
            if prefix.startswith("static "):
                prefix = prefix[len("static ") :].strip()
            joiner = "" if prefix.endswith("*") else " "
            sig = f"{prefix}{joiner}{m.group('name')}({m.group('args').strip()});"
            if sig not in seen:
                seen.add(sig)
                protos.append(sig)
    return protos


def _extract_host_hal_core_support(blocks: List[str]) -> Tuple[str, List[str]]:
    """Extract core-side HAL support text + callable declarations.

    When HOST_HAL implementation is split out, core still needs:
    - HAL typedefs/macros/constants used in host runtime glue paths
    - non cpu_host_hal_* local helpers (e.g. spec-zero helpers)
    - non-static declarations for cpu_host_hal_* functions invoked by core
    """
    func_sig_re = re.compile(
        r"^(?P<indent>\s*)(?P<prefix>(?:static\s+)?(?:inline\s+)?[\w\s\*]+?)\s*"
        r"(?P<name>cpu_host_hal_[A-Za-z0-9_]+)\s*\((?P<args>[^)]*)\)\s*\{\s*$"
    )
    var_decl_re = re.compile(
        r"^\s*static\s+.*\bcpu_host_hal_[A-Za-z0-9_]+\b.*;\s*$"
    )

    support_lines: List[str] = []
    prototypes: List[str] = []
    seen_protos: set[str] = set()

    for block in blocks:
        lines = block.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            m = func_sig_re.match(line.strip())
            if m:
                prefix = m.group("prefix").strip()
                if prefix.startswith("static "):
                    prefix = prefix[len("static ") :].strip()
                joiner = "" if prefix.endswith("*") else " "
                proto = f"{prefix}{joiner}{m.group('name')}({m.group('args').strip()});"
                if proto not in seen_protos:
                    seen_protos.add(proto)
                    prototypes.append(proto)

                # Skip the full function body from core support text.
                brace_depth = line.count("{") - line.count("}")
                i += 1
                while i < len(lines) and brace_depth > 0:
                    brace_depth += lines[i].count("{") - lines[i].count("}")
                    i += 1
                continue

            if var_decl_re.match(line):
                i += 1
                continue

            support_lines.append(line)
            i += 1

    # Normalize surrounding blank lines while preserving local formatting.
    support_text = "\n".join(support_lines).strip()
    return support_text, prototypes


def _remove_split_sections(text: str, section: str) -> str:
    begin = f"/* PASM_SPLIT_BEGIN:{section} */"
    end = f"/* PASM_SPLIT_END:{section} */"
    out = text
    cursor = 0
    while True:
        start = out.find(begin, cursor)
        if start < 0:
            break
        stop = out.find(end, start + len(begin))
        if stop < 0:
            break
        out = out[:start] + out[stop + len(end) :]
        cursor = start
    return out


def generate_host_hal_impl_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate marker-extracted host HAL implementation text for split host_glue ownership."""
    impl = generate_cpu_impl(
        isa_data,
        cpu_name,
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = _extract_split_sections(impl, "HOST_HAL_IMPL")
    if not blocks:
        return "/* No HOST_HAL_IMPL section emitted */\n"
    return (
        "#include <limits.h>\n"
        + "\n\n".join(blocks).strip()
        + "\n"
    )


def generate_host_hal_contract_support(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate non-owning host HAL support text required by split system_glue.

    Includes typedefs/macros/non-cpu_host_hal helpers and callable prototypes,
    but omits cpu_host_hal_* function bodies and static storage ownership.
    """
    impl = generate_cpu_impl(
        isa_data,
        cpu_name,
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = _extract_split_sections(impl, "HOST_HAL_IMPL")
    if not blocks:
        return ""
    support_text, prototypes = _extract_host_hal_core_support(blocks)
    helper_prototypes = [
        "int cpu_host_hal_gamepad_count(void);",
        "int cpu_host_hal_gamepad_button(int pad_index, int button_id);",
        "int cpu_host_hal_gamepad_axis(int pad_index, int axis_id);",
        "int cpu_host_hal_joystick_count(void);",
        "int cpu_host_hal_joystick_button(int joy_index, int button);",
        "int cpu_host_hal_joystick_axis(int joy_index, int axis);",
        "uint8_t cpu_host_hal_joystick_hat(int joy_index, int hat);",
    ]
    chunks: List[str] = []
    if support_text.strip():
        chunks.append(support_text.strip())
    if prototypes:
        chunks.append("\n".join(prototypes).strip())
    chunks.append("\n".join(helper_prototypes))
    return "\n\n".join(chunks).strip() + ("\n" if chunks else "")


def generate_component_dispatch_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate extracted component dispatch helpers for split system_glue ownership."""
    impl = generate_cpu_impl(
        isa_data,
        cpu_name,
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = _extract_split_sections(impl, "COMPONENT_DISPATCH")
    if not blocks:
        return "/* No COMPONENT_DISPATCH section emitted */\n"
    merged = "\n\n".join(blocks).strip()
    # Routing can be emitted independently; keep dispatch-body extraction focused.
    merged = _remove_split_sections(merged, "COMPONENT_ROUTING").strip()
    if not merged:
        return "/* No COMPONENT_DISPATCH body emitted */\n"
    return merged + "\n"


def generate_component_routing_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate extracted callback/signal routing helpers for split system_glue ownership."""
    impl = generate_cpu_impl(
        isa_data,
        cpu_name,
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = _extract_split_sections(impl, "COMPONENT_ROUTING")
    if not blocks:
        return "/* No COMPONENT_ROUTING section emitted */\n"
    return "\n\n".join(blocks).strip() + "\n"


def generate_component_connections_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate extracted component connection table ownership for split system_glue."""
    impl = generate_cpu_impl(
        isa_data,
        cpu_name,
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = _extract_split_sections(impl, "COMPONENT_CONNECTIONS")
    if not blocks:
        return "/* No COMPONENT_CONNECTIONS section emitted */\n"
    return "\n\n".join(blocks).strip() + "\n"


def generate_component_runtime_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate extracted full component runtime block for split system ownership."""
    impl = generate_cpu_impl(
        isa_data,
        cpu_name,
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = _extract_split_sections(impl, "COMPONENT_RUNTIME")
    if not blocks:
        return "/* No COMPONENT_RUNTIME section emitted */\n"
    return "\n\n".join(blocks).strip() + "\n"


def generate_component_lifecycle_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate extracted component lifecycle helpers for split ownership."""
    impl = generate_cpu_impl(
        isa_data,
        cpu_name,
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = _extract_split_sections(impl, "COMPONENT_LIFECYCLE")
    if not blocks:
        return "/* No COMPONENT_LIFECYCLE section emitted */\n"
    return "\n\n".join(blocks).strip() + "\n"


def generate_cartridge_picker_runtime_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate extracted cartridge picker runtime block for split ownership."""
    impl = generate_cpu_impl(
        isa_data,
        cpu_name,
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = _extract_split_sections(impl, "CARTRIDGE_PICKER_RUNTIME")
    if not blocks:
        return "/* No CARTRIDGE_PICKER_RUNTIME section emitted */\n"
    ui = isa_data.get("system", {}).get("ui", {}) or {}
    try:
        picker_scale = int(ui.get("cartridge_picker_font_scale", 1))
    except (TypeError, ValueError):
        picker_scale = 1
    if picker_scale < 0:
        picker_scale = 0
    merged = "\n\n".join(blocks).strip()
    return (
        "#include <errno.h>\n"
        "#include <limits.h>\n"
        "#include <sys/stat.h>\n"
        "#if !defined(_WIN32)\n"
        "#include <dirent.h>\n"
        "#endif\n"
        f"static const int g_runtime_cartridge_picker_font_scale = {picker_scale};\n\n"
        + merged
        + "\n"
    )


def generate_input_runtime_glue(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Extract runtime keyboard/controller helper block for future split ownership."""
    impl = generate_cpu_impl(
        isa_data,
        cpu_name,
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = _extract_split_sections(impl, "INPUT_RUNTIME")
    if not blocks:
        return "/* No INPUT_RUNTIME section emitted */\n"
    merged = "\n\n".join(blocks).strip()
    merged = _remove_split_sections(merged, "HOST_HAL_IMPL").strip()
    merged = re.sub(
        r"(?m)^(\s*)static(\s+(?:inline\s+)?[\w\s\*]*\bcpu_host_hal_[A-Za-z0-9_]+\s*\([^;]*\)\s*;)",
        r"\1\2",
        merged,
    )
    if not merged:
        return "/* No INPUT_RUNTIME body emitted */\n"
    return (
        "#include <errno.h>\n"
        "#include <limits.h>\n"
        "#include <sys/stat.h>\n"
        "#if !defined(_WIN32)\n"
        "#include <dirent.h>\n"
        "#endif\n\n"
        + merged
        + "\n"
    )


def generate_input_runtime_contract_support(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate declaration-only support for INPUT_RUNTIME cross-TU ownership moves.

    This extracts type/variable/function declarations from INPUT_RUNTIME while
    omitting function bodies and static storage ownership.
    """
    impl = generate_cpu_impl(
        isa_data,
        cpu_name,
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = _extract_split_sections(impl, "INPUT_RUNTIME")
    if not blocks:
        return "/* No INPUT_RUNTIME support emitted */\n"

    lines_out: List[str] = []
    typedef_block: List[str] = []
    in_typedef = False
    brace_depth = 0
    vars_seen: Set[str] = set()
    funcs_seen: Set[str] = set()

    static_var_re = re.compile(
        r"^\s*static\s+([A-Za-z_][\w\s\*]*?)\s+([A-Za-z_]\w*)\s*=\s*\{?.*;\s*$"
    )
    func_re = re.compile(
        r"^\s*(?:static\s+)?([A-Za-z_][\w\s\*]*?)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*\{\s*$",
        re.DOTALL,
    )

    def _flush_typedef():
        nonlocal typedef_block
        if typedef_block:
            block_text = "\n".join(typedef_block)
            if "RuntimeKeyboard" in block_text or "RuntimeController" in block_text:
                lines_out.extend(typedef_block)
                lines_out.append("")
            typedef_block = []

    for block in blocks:
        for raw in block.splitlines():
            line = raw.rstrip()
            stripped = line.strip()
            if not stripped:
                continue

            if in_typedef:
                typedef_block.append(line)
                brace_depth += line.count("{") - line.count("}")
                if brace_depth <= 0 and stripped.endswith(";"):
                    in_typedef = False
                    _flush_typedef()
                continue

            if stripped.startswith("typedef "):
                in_typedef = True
                brace_depth = line.count("{") - line.count("}")
                typedef_block.append(line)
                if brace_depth <= 0 and stripped.endswith(";"):
                    in_typedef = False
                    _flush_typedef()
                continue

            m_var = static_var_re.match(line)
            if m_var:
                type_name = m_var.group(1).strip()
                var_name = m_var.group(2).strip()
                if not var_name.startswith("g_runtime_"):
                    continue
                if var_name not in vars_seen:
                    vars_seen.add(var_name)
                    spacer = "" if type_name.endswith("*") else " "
                    lines_out.append(f"extern {type_name}{spacer}{var_name};")
                continue

            # Support both single-line and multi-line static function signatures.
            m_func = func_re.match(line)
            if not m_func and not stripped.endswith(";") and "(" in stripped:
                sig_lines = [line]
                open_paren = line.count("(")
                close_paren = line.count(")")
                j = 0
                # Walk forward inside this block until we close the signature and hit '{'.
                tail_lines = block.splitlines()
                # Find current line index by matching raw line position in this block.
                # This is local/cheap for contract extraction and keeps logic self-contained.
                try:
                    j = tail_lines.index(raw) + 1
                except ValueError:
                    j = 0
                while j < len(tail_lines):
                    nxt = tail_lines[j].rstrip()
                    sig_lines.append(nxt)
                    open_paren += nxt.count("(")
                    close_paren += nxt.count(")")
                    if open_paren > 0 and open_paren == close_paren and nxt.strip().endswith("{"):
                        break
                    j += 1
                sig_blob = "\n".join(sig_lines).strip()
                m_func = func_re.match(sig_blob)
            if m_func:
                ret_type = m_func.group(1).strip()
                fn_name = m_func.group(2).strip()
                args = m_func.group(3).strip()
                if not (
                    fn_name.startswith("cpu_component_")
                    or fn_name.endswith("_load_keyboard_map")
                    or fn_name.endswith("_load_controller_map")
                ):
                    continue
                if fn_name not in funcs_seen:
                    funcs_seen.add(fn_name)
                    spacer = "" if ret_type.endswith("*") else " "
                    lines_out.append(f"{ret_type}{spacer}{fn_name}({args});")
                continue

    if in_typedef:
        _flush_typedef()

    if not lines_out:
        return "/* No INPUT_RUNTIME support emitted */\n"
    return "\n".join(lines_out).strip() + "\n"


def _generate_coding_includes(isa_data: Dict[str, Any]) -> str:
    headers = isa_data.get("coding", {}).get("headers", [])
    if not headers:
        return ""

    lines: List[str] = []
    seen: set[str] = set()
    for header in headers:
        h = str(header).strip()
        if not h or h in seen:
            continue
        seen.add(h)
        if h.startswith("<") or h.startswith('"'):
            lines.append(f"#include {h}")
        else:
            lines.append(f"#include <{h}>")
    return "\n".join(lines)


def _flag_expr(flag_name: str, available_flags: Set[str]) -> str:
    upper_name = flag_name.upper()
    if upper_name in available_flags:
        return f"cpu->flags.{upper_name}"
    return "false"


def _escape_c_string(value: str) -> str:
    """Escape a Python string for safe embedding in generated C string literals."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _escape_printf_format(value: str) -> str:
    return value.replace("%", "%%")


def _instruction_field_widths(inst: Dict[str, Any]) -> Dict[str, int]:
    widths = dict(BASE_DECODED_FIELD_WIDTHS)
    encoding = inst.get("encoding", {})
    for field in encoding.get("fields", []):
        field_name = str(field.get("name", "")).strip()
        if not field_name:
            continue
        width = field.get("width")
        if width is None:
            pos = field.get("position", [0, 0])
            if (
                not isinstance(pos, list)
                or len(pos) < 2
                or not isinstance(pos[0], int)
                or not isinstance(pos[1], int)
            ):
                continue
            width = pos[0] - pos[1] + 1
        try:
            widths[field_name] = max(1, int(width))
        except (TypeError, ValueError):
            continue
    return widths


def _default_field_mask(field_width: int) -> int:
    if field_width <= 0:
        return 0xFFFFFFFF
    if field_width >= 32:
        return 0xFFFFFFFF
    return (1 << field_width) - 1


def _parse_display_template(
    template: str, inst_name: str
) -> Tuple[List[str], List[Tuple[str, Optional[str]]]]:
    segments: List[str] = []
    tokens: List[Tuple[str, Optional[str]]] = []
    cursor = 0
    for match in DISPLAY_TEMPLATE_TOKEN_RE.finditer(template):
        start, end = match.span()
        segments.append(template[cursor:start])
        tokens.append((match.group(1), match.group(2)))
        cursor = end
    segments.append(template[cursor:])

    skeleton = DISPLAY_TEMPLATE_TOKEN_RE.sub("", template)
    if "{" in skeleton or "}" in skeleton:
        raise ValueError(
            f"Instruction '{inst_name}': malformed display_template token braces."
        )

    return segments, tokens


def _resolve_display_operand_spec(
    inst: Dict[str, Any],
    field_name: str,
    formatter: Optional[str],
    field_widths: Dict[str, int],
) -> Tuple[str, int, List[str]]:
    inst_name = str(inst.get("name", "UNKNOWN"))
    operand_specs = inst.get("display_operands", {}) or {}
    spec = operand_specs.get(field_name, {}) or {}
    if not isinstance(spec, dict):
        raise ValueError(
            f"Instruction '{inst_name}': display_operands.{field_name} must be an object."
        )

    kind = formatter or str(spec.get("kind", "unsigned")).strip()
    if kind not in SUPPORTED_DISPLAY_KINDS:
        raise ValueError(
            f"Instruction '{inst_name}': unsupported display formatter/kind '{kind}'."
        )

    mask_raw = spec.get("mask")
    if mask_raw is None:
        mask = _default_field_mask(field_widths.get(field_name, 32))
    else:
        try:
            mask = int(mask_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Instruction '{inst_name}': invalid display_operands.{field_name}.mask."
            ) from exc
        if mask < 0:
            raise ValueError(
                f"Instruction '{inst_name}': display_operands.{field_name}.mask must be non-negative."
            )

    table = spec.get("table", [])
    if kind in TABLE_DISPLAY_KINDS:
        if (
            not isinstance(table, list)
            or not table
            or not all(isinstance(item, str) and item for item in table)
        ):
            raise ValueError(
                f"Instruction '{inst_name}': {kind} rendering for '{field_name}' requires non-empty table."
            )
        return kind, mask, list(table)

    if kind == "mc6809_idx":
        return kind, mask, []

    return kind, mask, []


def _append_instruction_template_render(
    lines: List[str],
    inst: Dict[str, Any],
    numeric_style: str = "c_hex",
    numeric_formats: Optional[Dict[str, str]] = None,
    allowed_kinds: Optional[Set[str]] = None,
    indent: str = "                    ",
) -> None:
    inst_name = str(inst.get("name", "UNKNOWN"))
    template = inst.get("display_template")
    if not isinstance(template, str) or not template:
        return

    field_widths = _instruction_field_widths(inst)
    segments, tokens = _parse_display_template(template, inst_name)

    for field_name, _ in tokens:
        if field_name not in field_widths:
            raise ValueError(
                f"Instruction '{inst_name}': display_template token '{field_name}' references unknown decoded field."
            )

    if not tokens:
        escaped = _escape_c_string(template)
        lines.append(f'{indent}mnemonic = "{escaped}";')
        return

    lines.append(f"{indent}{{")
    lines.append(f"{indent}    bool render_ok = true;")
    operand_names: List[str] = []
    for idx, (field_name, formatter) in enumerate(tokens):
        kind, mask, table = _resolve_display_operand_spec(
            inst, field_name, formatter, field_widths
        )
        if allowed_kinds is not None and kind not in allowed_kinds:
            raise ValueError(
                f"Instruction '{inst_name}': formatter '{kind}' is not enabled by metadata.codegen.display_kinds_enabled."
            )
        op_name = f"op_{idx}"
        operand_names.append(op_name)
        buf_name = f"op_buf_{idx}"
        field_ref = f"inst.{field_name}"
        lines.append(f'{indent}    const char *{op_name} = "<?>";')

        if kind in TABLE_DISPLAY_KINDS:
            table_name = f"op_table_{inst_name}_{field_name}_{idx}"
            table_values = ", ".join(f'"{_escape_c_string(item)}"' for item in table)
            lines.append(
                f"{indent}    static const char *{table_name}[] = {{{table_values}}};"
            )
            lines.append(
                f"{indent}    uint32_t {field_name}_idx_{idx} = ((uint32_t){field_ref}) & 0x{mask:X}u;"
            )
            lines.append(
                f"{indent}    if ({field_name}_idx_{idx} < (uint32_t)(sizeof({table_name}) / sizeof({table_name}[0]))) {{"
            )
            lines.append(f"{indent}        {op_name} = {table_name}[{field_name}_idx_{idx}];")
            lines.append(f"{indent}    }} else {{")
            lines.append(f"{indent}        render_ok = false;")
            lines.append(f"{indent}    }}")
            continue

        lines.append(f"{indent}    char {buf_name}[40];")
        numeric_formats = numeric_formats or {}
        if kind == "hex8":
            fmt = _escape_c_string(numeric_formats.get("hex8", "0x%02X"))
            lines.append(
                f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "{fmt}", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
            )
        elif kind == "hex8_plain":
            lines.append(
                f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "%02X", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
            )
        elif kind == "hex16":
            fmt = _escape_c_string(numeric_formats.get("hex16", "0x%04X"))
            lines.append(
                f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "{fmt}", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
            )
        elif kind == "hex16_plain":
            lines.append(
                f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "%04X", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
            )
        elif kind == "hex8_asm":
            lines.append(
                f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "$%02X", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
            )
        elif kind == "hex16_asm":
            lines.append(
                f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "$%04X", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
            )
        elif kind == "hex32":
            lines.append(
                f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "0x%08X", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
            )
        elif kind == "signed8":
            lines.append(
                f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "%+d", (int)((int8_t)(((uint32_t){field_ref}) & 0x{mask:X}u)));'
            )
        elif kind == "signed16":
            lines.append(
                f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "%+d", (int)((int16_t)(((uint32_t){field_ref}) & 0x{mask:X}u)));'
            )
        elif kind == "mc6809_idx":
            lines.append(
                f"{indent}    dbg_mc6809_format_indexed((uint8_t)(((uint32_t){field_ref}) & 0x{mask:X}u), pc, raw, prefix, {buf_name}, sizeof({buf_name}));"
            )
        elif kind == "mc6809_pshs_mask":
            lines.append(
                f'{indent}    dbg_mc6809_format_stack_mask((uint8_t)(((uint32_t){field_ref}) & 0x{mask:X}u), "U", 0u, {buf_name}, sizeof({buf_name}));'
            )
        elif kind == "mc6809_puls_mask":
            lines.append(
                f'{indent}    dbg_mc6809_format_stack_mask((uint8_t)(((uint32_t){field_ref}) & 0x{mask:X}u), "U", 1u, {buf_name}, sizeof({buf_name}));'
            )
        elif kind == "mc6809_pshu_mask":
            lines.append(
                f'{indent}    dbg_mc6809_format_stack_mask((uint8_t)(((uint32_t){field_ref}) & 0x{mask:X}u), "S", 0u, {buf_name}, sizeof({buf_name}));'
            )
        elif kind == "mc6809_pulu_mask":
            lines.append(
                f'{indent}    dbg_mc6809_format_stack_mask((uint8_t)(((uint32_t){field_ref}) & 0x{mask:X}u), "S", 1u, {buf_name}, sizeof({buf_name}));'
            )
        else:  # unsigned
            lines.append(
                f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "%u", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
            )
        lines.append(f"{indent}    {op_name} = {buf_name};")

    fmt_parts: List[str] = []
    for idx, segment in enumerate(segments):
        fmt_parts.append(_escape_printf_format(segment))
        if idx < len(tokens):
            fmt_parts.append("%s")
    fmt_string = _escape_c_string("".join(fmt_parts))
    operand_args = ", ".join(operand_names)
    lines.append(f"{indent}    if (render_ok) {{")
    lines.append(
        f'{indent}        (void)snprintf(rendered, sizeof(rendered), "{fmt_string}", {operand_args});'
    )
    lines.append(f"{indent}        mnemonic = rendered;")
    lines.append(f"{indent}    }}")
    lines.append(f"{indent}}}")


def _infer_display_template(
    inst: Dict[str, Any], immediate_style: str = "c_hex"
) -> Optional[str]:
    if inst.get("display_template"):
        return None

    display = str(inst.get("display", "")).strip()
    if not display:
        return None

    field_names = {
        str(field.get("name", "")).strip()
        for field in inst.get("encoding", {}).get("fields", [])
        if str(field.get("name", "")).strip()
    }

    template = display
    changed = False

    def _replace_literal(old: str, new: str) -> None:
        nonlocal template, changed
        if old in template:
            template = template.replace(old, new)
            changed = True

    def _replace_regex(pattern: str, replacement: str) -> None:
        nonlocal template, changed
        template, count = re.subn(pattern, replacement, template)
        if count > 0:
            changed = True

    hex8_kind = "hex8_asm" if immediate_style == "asm_dollar" else "hex8"
    hex16_kind = "hex16_asm" if immediate_style == "asm_dollar" else "hex16"

    if "n" in field_names:
        _replace_literal("#n", f"#{{n:{hex8_kind}}}")
    if "nn" in field_names:
        _replace_literal("#nn", f"#{{nn:{hex16_kind}}}")
    if "imm" in field_names:
        _replace_literal("#n", f"#{{imm:{hex8_kind}}}")

    if "addr" in field_names:
        _replace_literal("(nn)", f"({{addr:{hex16_kind}}})")
        _replace_regex(r"(?<![#\{])\bnn\b", f"{{addr:{hex16_kind}}}")

    if "n" in field_names:
        _replace_literal("(n)", f"({{n:{hex8_kind}}})")
        _replace_regex(r"(?<![#\{])\bn\b", f"{{n:{hex8_kind}}}")
    if "zp" in field_names:
        _replace_literal("(n)", f"({{zp:{hex8_kind}}})")
        _replace_regex(r"(?<![#\{])\bn\b", f"{{zp:{hex8_kind}}}")

    if "disp" in field_names:
        _replace_literal("(IX+d)", "(IX+{disp:signed8})")
        _replace_literal("(IY+d)", "(IY+{disp:signed8})")
        _replace_regex(r"\bd\b", "{disp:signed8}")

    # MC6809 direct-page offset byte rendered as zero-extended 16-bit.
    if "offset" in field_names:
        _replace_literal("<n", "{offset:hex16_plain}")
        _replace_regex(r"\br\b", "{offset:signed8}")

    if "offset16" in field_names:
        _replace_regex(r"\brr\b", "{offset16:signed16}")

    # MC6809 indexed postbyte decoding.
    if "postbyte" in field_names:
        _replace_literal("[idx]", "{postbyte:mc6809_idx}")

    if "addr" in field_names:
        # Replace standalone "addr" placeholders only (avoid rewriting inside "{addr:...}" tokens).
        _replace_regex(r"(?<![\{#])\baddr\b", "{addr:hex16_plain}")

    if "bit" in field_names:
        _replace_regex(r"\bb\b", "{bit:unsigned}")

    return template if changed else None


def _instruction_render_kinds(
    inst: Dict[str, Any], allowed_kinds: Set[str]
) -> Set[str]:
    kinds: Set[str] = set()
    template = inst.get("display_template")
    if not isinstance(template, str) or not template:
        return kinds
    inst_name = str(inst.get("name", "UNKNOWN"))
    field_widths = _instruction_field_widths(inst)
    _, tokens = _parse_display_template(template, inst_name)
    for field_name, formatter in tokens:
        kind, _, _ = _resolve_display_operand_spec(inst, field_name, formatter, field_widths)
        if kind not in allowed_kinds:
            raise ValueError(
                f"Instruction '{inst_name}': formatter '{kind}' is not enabled by metadata.codegen.display_kinds_enabled."
            )
        kinds.add(kind)
    for field_name, spec in (inst.get("display_operands", {}) or {}).items():
        if not isinstance(spec, dict):
            raise ValueError(
                f"Instruction '{inst_name}': display_operands.{field_name} must be an object."
            )
        kind = str(spec.get("kind", "unsigned")).strip()
        if kind and kind not in allowed_kinds:
            raise ValueError(
                f"Instruction '{inst_name}': display_operands.{field_name}.kind '{kind}' is not enabled by metadata.codegen.display_kinds_enabled."
            )
    return kinds


def _hook_enabled(hooks: Dict[str, Any], hook_name: str) -> bool:
    return bool(hooks.get(hook_name, {}).get("enabled", False))


def _generate_port_hook_snippets(hooks: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """Generate optional hook snippets for port read/write helpers."""
    if _hook_enabled(hooks, "port_read_pre"):
        read_pre = (
            "    if (cpu->hooks[HOOK_PORT_READ_PRE].enabled && cpu->hooks[HOOK_PORT_READ_PRE].func) {\n"
            "        CPUHookEvent event = {\n"
            "            .type = HOOK_PORT_READ_PRE,\n"
            "            .pc = cpu->hook_pc,\n"
            "            .prefix = cpu->hook_prefix,\n"
            "            .opcode = cpu->hook_opcode,\n"
            "            .port = port,\n"
            "            .value = 0,\n"
            "            .raw = cpu->hook_raw,\n"
            "        };\n"
            "        cpu->hooks[HOOK_PORT_READ_PRE].func(cpu, &event, cpu->hooks[HOOK_PORT_READ_PRE].context);\n"
            "    }"
        )
    else:
        read_pre = ""

    if _hook_enabled(hooks, "port_read_post"):
        read_post = (
            "    if (cpu->hooks[HOOK_PORT_READ_POST].enabled && cpu->hooks[HOOK_PORT_READ_POST].func) {\n"
            "        CPUHookEvent event = {\n"
            "            .type = HOOK_PORT_READ_POST,\n"
            "            .pc = cpu->hook_pc,\n"
            "            .prefix = cpu->hook_prefix,\n"
            "            .opcode = cpu->hook_opcode,\n"
            "            .port = port,\n"
            "            .value = value,\n"
            "            .raw = cpu->hook_raw,\n"
            "        };\n"
            "        cpu->hooks[HOOK_PORT_READ_POST].func(cpu, &event, cpu->hooks[HOOK_PORT_READ_POST].context);\n"
            "    }"
        )
    else:
        read_post = ""

    if _hook_enabled(hooks, "port_write_pre"):
        write_pre = (
            "    if (cpu->hooks[HOOK_PORT_WRITE_PRE].enabled && cpu->hooks[HOOK_PORT_WRITE_PRE].func) {\n"
            "        CPUHookEvent event = {\n"
            "            .type = HOOK_PORT_WRITE_PRE,\n"
            "            .pc = cpu->hook_pc,\n"
            "            .prefix = cpu->hook_prefix,\n"
            "            .opcode = cpu->hook_opcode,\n"
            "            .port = port,\n"
            "            .value = value,\n"
            "            .raw = cpu->hook_raw,\n"
            "        };\n"
            "        cpu->hooks[HOOK_PORT_WRITE_PRE].func(cpu, &event, cpu->hooks[HOOK_PORT_WRITE_PRE].context);\n"
            "    }"
        )
    else:
        write_pre = ""

    if _hook_enabled(hooks, "port_write_post"):
        write_post = (
            "    if (cpu->hooks[HOOK_PORT_WRITE_POST].enabled && cpu->hooks[HOOK_PORT_WRITE_POST].func) {\n"
            "        CPUHookEvent event = {\n"
            "            .type = HOOK_PORT_WRITE_POST,\n"
            "            .pc = cpu->hook_pc,\n"
            "            .prefix = cpu->hook_prefix,\n"
            "            .opcode = cpu->hook_opcode,\n"
            "            .port = port,\n"
            "            .value = value,\n"
            "            .raw = cpu->hook_raw,\n"
            "        };\n"
            "        cpu->hooks[HOOK_PORT_WRITE_POST].func(cpu, &event, cpu->hooks[HOOK_PORT_WRITE_POST].context);\n"
            "    }"
        )
    else:
        write_post = ""

    return read_pre, read_post, write_pre, write_post


def _generate_helpers(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate helper functions."""
    lines: List[str] = []
    codegen = _require_codegen_config(isa_data)
    helper_features = codegen.get("helper_features", {}) if isinstance(codegen.get("helper_features"), dict) else {}

    registers = isa_data.get("registers", [])
    register_count = len(registers)

    if register_count > 0:
        lines.append(
            f"static uint8_t {cpu_prefix}_get_r8(CPUState *cpu, uint8_t idx) {{"
        )
        lines.append(f"    return cpu->registers[idx % {register_count}];")
        lines.append("}")
        lines.append("")
        lines.append(
            f"static void {cpu_prefix}_set_r8(CPUState *cpu, uint8_t idx, uint8_t val) {{"
        )
        lines.append(f"    cpu->registers[idx % {register_count}] = val;")
        lines.append("}")
        lines.append("")

    # Parity helper
    lines.append("static bool cpu_parity(uint8_t val) {")
    lines.append("    val ^= val >> 4;")
    lines.append("    val ^= val >> 2;")
    lines.append("    val ^= val >> 1;")
    lines.append("    return (val & 1) == 0;")
    lines.append("}")
    lines.append("")

    register_names = {
        str(register.get("name", "")).upper() for register in isa_data.get("registers", [])
    }
    has_bank_exec = "BANK_EXEC" in register_names

    if has_bank_exec:
        lines.append("static uint8_t cpu_fetch_byte(CPUState *cpu, uint16_t addr) {")
        lines.append(
            "    uint32_t phys = (((uint32_t)cpu->registers[REG_BANK_EXEC]) << 16) | (uint32_t)addr;"
        )
        lines.append("    if (phys < (uint32_t)cpu->memory_size) {")
        lines.append("        return cpu->memory[phys];")
        lines.append("    }")
        lines.append(f"    return {cpu_prefix}_read_byte(cpu, addr);")
        lines.append("}")
        lines.append("")

    available_flags = {f.get("name", "").upper() for f in isa_data.get("flags", [])}
    z_expr = _flag_expr("Z", available_flags)
    c_expr = _flag_expr("C", available_flags)
    p_expr = _flag_expr("P", available_flags)
    s_expr = _flag_expr("S", available_flags)

    condition_cases = helper_features.get("condition_cases")
    if condition_cases is None:
        condition_cases = ["!($Z)", "$Z", "!($C)", "$C", "!($P)", "$P", "!($S)", "$S"]
    if isinstance(condition_cases, list):
        lines.append("static bool cpu_check_condition(CPUState *cpu, uint8_t cc) {")
        lines.append("    switch (cc) {")
        expr_map = {"Z": z_expr, "C": c_expr, "P": p_expr, "S": s_expr}
        for idx, case in enumerate(condition_cases):
            expr = str(case).strip()
            for name, value in expr_map.items():
                expr = expr.replace(f"${name}", value)
            lines.append(f"        case {idx}: return {expr};")
        lines.append("    }")
        lines.append("    return false;")
        lines.append("}")
        lines.append("")

    # Breakpoint check helper
    lines.append("static bool cpu_check_breakpoints(CPUState *cpu) {")
    lines.append("    for (int i = 0; i < cpu->num_break_points; i++) {")
    lines.append("        if (cpu->break_points[i] == cpu->pc) return true;")
    lines.append("    }")
    lines.append("    return false;")
    lines.append("}")
    lines.append("")

    if helper_features.get("runtime_cycle_penalties") == "mos6502_page_cross":
        lines.append("static void cpu_apply_mos6502_runtime_cycles(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before, uint8_t x_before, uint8_t y_before, uint8_t c_before, uint8_t z_before, uint8_t n_before, uint8_t v_before) {")
        lines.append("    switch (inst->opcode) {")
        lines.append("        /* Branches: +1 when taken, +1 more when target crosses page. */")
        lines.append("        case 0x10u: case 0x30u: case 0x50u: case 0x70u:")
        lines.append("        case 0x90u: case 0xB0u: case 0xD0u: case 0xF0u: {")
        lines.append("            uint8_t taken = 0u;")
        lines.append("            switch (inst->opcode) {")
        lines.append("                case 0x10u: taken = (uint8_t)(n_before == 0u); break; /* BPL */")
        lines.append("                case 0x30u: taken = (uint8_t)(n_before != 0u); break; /* BMI */")
        lines.append("                case 0x50u: taken = (uint8_t)(v_before == 0u); break; /* BVC */")
        lines.append("                case 0x70u: taken = (uint8_t)(v_before != 0u); break; /* BVS */")
        lines.append("                case 0x90u: taken = (uint8_t)(c_before == 0u); break; /* BCC */")
        lines.append("                case 0xB0u: taken = (uint8_t)(c_before != 0u); break; /* BCS */")
        lines.append("                case 0xD0u: taken = (uint8_t)(z_before == 0u); break; /* BNE */")
        lines.append("                case 0xF0u: taken = (uint8_t)(z_before != 0u); break; /* BEQ */")
        lines.append("                default: break;")
        lines.append("            }")
        lines.append("            if (taken != 0u) {")
        lines.append("                uint16_t seq_pc = (uint16_t)(pc_before + inst->length);")
        lines.append("                uint16_t target_pc = (uint16_t)(seq_pc + (int16_t)(int8_t)inst->rel);")
        lines.append("                inst->cycles = (uint8_t)(inst->cycles + 1u);")
        lines.append("                if (((seq_pc ^ target_pc) & 0xFF00u) != 0u) {")
        lines.append("                    inst->cycles = (uint8_t)(inst->cycles + 1u);")
        lines.append("                }")
        lines.append("            }")
        lines.append("            return;")
        lines.append("        }")
        lines.append("")
        lines.append("        /* ABS,X read-like ops: +1 on page cross. */")
        lines.append("        case 0x1Cu: case 0x1Du: case 0x3Cu: case 0x3Du:")
        lines.append("        case 0x5Cu: case 0x5Du: case 0x7Cu: case 0x7Du:")
        lines.append("        case 0xBCu: case 0xBDu: case 0xDCu: case 0xDDu:")
        lines.append("        case 0xFCu: case 0xFDu: {")
        lines.append("            uint16_t ea = (uint16_t)(inst->addr + (uint16_t)x_before);")
        lines.append("            if (((inst->addr ^ ea) & 0xFF00u) != 0u) {")
        lines.append("                inst->cycles = (uint8_t)(inst->cycles + 1u);")
        lines.append("            }")
        lines.append("            return;")
        lines.append("        }")
        lines.append("")
        lines.append("        /* ABS,Y read-like ops: +1 on page cross. */")
        lines.append("        case 0x19u: case 0x39u: case 0x59u: case 0x79u:")
        lines.append("        case 0xB9u: case 0xBBu: case 0xBEu: case 0xBFu:")
        lines.append("        case 0xD9u: case 0xF9u: {")
        lines.append("            uint16_t ea = (uint16_t)(inst->addr + (uint16_t)y_before);")
        lines.append("            if (((inst->addr ^ ea) & 0xFF00u) != 0u) {")
        lines.append("                inst->cycles = (uint8_t)(inst->cycles + 1u);")
        lines.append("            }")
        lines.append("            return;")
        lines.append("        }")
        lines.append("")
        lines.append("        /* (ZP),Y read-like ops: +1 on page cross. */")
        lines.append("        case 0x11u: case 0x31u: case 0x51u: case 0x71u:")
        lines.append("        case 0xB1u: case 0xB3u: case 0xD1u: case 0xF1u: {")
        lines.append(f"            uint8_t lo = {cpu_prefix}_read_byte(cpu, (uint16_t)inst->zp);")
        lines.append(f"            uint8_t hi = {cpu_prefix}_read_byte(cpu, (uint16_t)((uint8_t)(inst->zp + 1u)));")
        lines.append("            uint16_t base = (uint16_t)(((uint16_t)hi << 8) | (uint16_t)lo);")
        lines.append("            uint16_t ea = (uint16_t)(base + (uint16_t)y_before);")
        lines.append("            if (((base ^ ea) & 0xFF00u) != 0u) {")
        lines.append("                inst->cycles = (uint8_t)(inst->cycles + 1u);")
        lines.append("            }")
        lines.append("            return;")
        lines.append("        }")
        lines.append("")
        lines.append("        default:")
        lines.append("            return;")
        lines.append("    }")
        lines.append("}")

    return "\n".join(lines)


def _generate_memory_write_guard(isa_data: Dict[str, Any]) -> str:
    """Generate memory write checks for read-only regions.

    Hardware typically ignores writes to ROM-backed regions. Treating these as
    fatal memory errors can break normal boot flows that probe memory layout.
    """
    memory = isa_data.get("memory", {})
    regions = memory.get("regions", [])
    if not regions:
        return ""

    lines: List[str] = []

    for region in regions:
        if _is_region_writable(region):
            continue

        clipped_start, clipped_end = _clip_region_bounds(
            int(region.get("start", 0)), int(region.get("size", 0))
        )
        if clipped_start >= clipped_end:
            continue

        region_name = _escape_c_string(str(region.get("name", "ROM")))

        max_addr_exclusive = 0x10000
        if clipped_start == 0 and clipped_end == max_addr_exclusive:
            condition = "true"
        elif clipped_start == 0:
            condition = f"(addr < 0x{clipped_end:04X}u)"
        elif clipped_end == max_addr_exclusive:
            condition = f"(addr >= 0x{clipped_start:04X}u)"
        else:
            condition = (
                f"(addr >= 0x{clipped_start:04X}u && addr < 0x{clipped_end:04X}u)"
            )

        lines.append(f"    /* Ignore writes to read-only region: {region_name} */")
        lines.append(f"    if {condition} {{")
        lines.append("        return;")
        lines.append("    }")

    return "\n".join(lines)


def _is_region_writable(region: Dict[str, Any]) -> bool:
    if bool(region.get("read_only", False)):
        return False
    if "read_write" in region and not bool(region.get("read_write")):
        return False
    return True


def _clip_region_bounds(start: int, size: int) -> Tuple[int, int]:
    max_addr_exclusive = 0x10000  # runtime memory API is currently uint16_t addressed.
    if size <= 0:
        return (0, 0)
    end = start + size
    if end <= start:
        return (0, 0)
    clipped_start = max(0, start)
    clipped_end = min(max_addr_exclusive, end)
    if clipped_start >= clipped_end:
        return (0, 0)
    return (clipped_start, clipped_end)


def _generate_system_rom_loader(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate a runtime helper that loads system-declared ROM images."""
    rom_images = list(isa_data.get("memory", {}).get("rom_images", []))
    if not rom_images:
        return (
            f"int {cpu_prefix}_load_system_roms(CPUState *cpu, const char *system_base_dir) {{\n"
            "    if (!cpu) return -1;\n"
            "    (void)system_base_dir;\n"
            "    cpu->loaded_rom_debug[0] = '\\0';\n"
            "    return 0;\n"
            "}\n"
        )

    lines: List[str] = [
        "typedef struct {",
        "    const char *name;",
        "    const char *path;",
        "    uint16_t address;",
        "    uint32_t max_size;",
        "} SystemRomImage;",
        "",
        "static const SystemRomImage g_system_rom_images[] = {",
    ]
    for rom in rom_images:
        name = _escape_c_string(str(rom.get("name", "rom")))
        path = _escape_c_string(str(rom.get("file", "")))
        address = int(rom.get("address", 0)) & 0xFFFF
        max_size = int(rom.get("size", 0))
        lines.append(
            "    { "
            f"\"{name}\", "
            f"\"{path}\", "
            f"0x{address:04X}u, "
            f"{max_size}u "
            "},"
        )
    lines.extend(
        [
            "};",
            "",
            "static bool cpu_path_is_absolute(const char *path) {",
            "    if (!path || !path[0]) return false;",
            "    if (path[0] == '/' || path[0] == '\\\\') return true;",
            "    if (((path[0] >= 'A' && path[0] <= 'Z') || (path[0] >= 'a' && path[0] <= 'z')) && path[1] == ':') return true;",
            "    return false;",
            "}",
            "",
            f"int {cpu_prefix}_load_system_roms(CPUState *cpu, const char *system_base_dir) {{",
            "    if (!cpu) return -1;",
            "    char full_path[1024];",
            "    size_t rom_count = sizeof(g_system_rom_images) / sizeof(g_system_rom_images[0]);",
            "    for (size_t i = 0; i < rom_count; i++) {",
            "        const SystemRomImage *rom = &g_system_rom_images[i];",
            "        const char *path_to_open = rom->path;",
            "",
            "        if (!cpu_path_is_absolute(rom->path) && system_base_dir && system_base_dir[0]) {",
            "            size_t base_len = strlen(system_base_dir);",
            "            bool needs_sep = !(system_base_dir[base_len - 1] == '/' || system_base_dir[base_len - 1] == '\\\\');",
            "            int n = snprintf(full_path, sizeof(full_path), \"%s%s%s\", system_base_dir, needs_sep ? \"/\" : \"\", rom->path);",
            "            if (n < 0 || (size_t)n >= sizeof(full_path)) return -1;",
            "            path_to_open = full_path;",
            "        }",
            "",
            "        FILE *f = fopen(path_to_open, \"rb\");",
            "        if (!f) return -1;",
            "        if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return -1; }",
            "        long file_size = ftell(f);",
            "        if (file_size < 0) { fclose(f); return -1; }",
            "        if (fseek(f, 0, SEEK_SET) != 0) { fclose(f); return -1; }",
            "",
            "        if ((uint64_t)file_size > rom->max_size) { fclose(f); return -1; }",
            "        if ((uint64_t)rom->address + (uint64_t)file_size > cpu->memory_size) { fclose(f); return -1; }",
            "",
            "        size_t read_len = fread(&cpu->memory[rom->address], 1, (size_t)file_size, f);",
            "        fclose(f);",
            "        if (read_len != (size_t)file_size) return -1;",
            "        if (i == 0u) {",
            "            if (rom_count > 1u) {",
            "                snprintf(",
            "                    cpu->loaded_rom_debug,",
            "                    sizeof(cpu->loaded_rom_debug),",
            "                    \"name=%s path=%s (+%llu more)\",",
            "                    rom->name,",
            "                    path_to_open,",
            "                    (unsigned long long)(rom_count - 1u)",
            "                );",
            "            } else {",
            "                snprintf(",
            "                    cpu->loaded_rom_debug,",
            "                    sizeof(cpu->loaded_rom_debug),",
            "                    \"name=%s path=%s\",",
            "                    rom->name,",
            "                    path_to_open",
            "                );",
            "            }",
            "        }",
            "    }",
            "    return 0;",
            "}",
        ]
    )
    return "\n".join(lines) + "\n"


def _generate_cartridge_rom_loader(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate runtime cartridge ROM loader API."""
    cartridge = isa_data.get("cartridge", {}) or {}
    if not cartridge:
        return (
            f"int {cpu_prefix}_load_cartridge_rom(CPUState *cpu, const char *path) {{\n"
            "    (void)cpu;\n"
            "    (void)path;\n"
            "    return -1;\n"
            "}\n"
            f"int {cpu_prefix}_set_cartridge_dir(CPUState *cpu, const char *path) {{\n"
            "    (void)cpu;\n"
            "    (void)path;\n"
            "    return -1;\n"
            "}\n"
        )

    comp_id = str(cartridge.get("metadata", {}).get("id", "cartridge"))
    comp_ident = _to_c_ident(comp_id)
    state_names = {str(field.get("name", "")) for field in cartridge.get("state", [])}
    if "rom_data" not in state_names or "rom_size" not in state_names:
        raise ValueError(
            f"Cartridge '{comp_id}' must declare state fields rom_data and rom_size"
        )
    has_enabled_flag = "cart_enabled" in state_names
    has_image_parsed = "image_parsed" in state_names
    has_image_off = "image_off" in state_names
    has_image_len = "image_len" in state_names

    lines: List[str] = [
        f"int {cpu_prefix}_load_cartridge_rom(CPUState *cpu, const char *path) {{",
        "    FILE *f;",
        "    long file_size;",
        "    uint8_t *buf;",
        f"    ComponentState_{comp_ident} *comp;",
        "    size_t read_len;",
        "",
        "    if (!cpu || !path || !path[0]) return -1;",
        "    comp = &cpu->comp_" + comp_ident + ";",
        "    f = fopen(path, \"rb\");",
        "    if (!f) return -1;",
        "    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return -1; }",
        "    file_size = ftell(f);",
        "    if (file_size < 0) { fclose(f); return -1; }",
        "    if (fseek(f, 0, SEEK_SET) != 0) { fclose(f); return -1; }",
        "    buf = (uint8_t *)malloc((size_t)file_size);",
        "    if (!buf) { fclose(f); return -1; }",
        "    read_len = fread(buf, 1, (size_t)file_size, f);",
        "    fclose(f);",
        "    if (read_len != (size_t)file_size) { free(buf); return -1; }",
        "    if (comp->rom_data != NULL) {",
        "        free(comp->rom_data);",
        "        comp->rom_data = NULL;",
        "    }",
        "    comp->rom_data = buf;",
        "    comp->rom_size = (uint32_t)file_size;",
        *(
            ["    comp->image_parsed = 0u;"]
            if has_image_parsed
            else []
        ),
        *(
            ["    comp->image_off = 0u;"]
            if has_image_off
            else []
        ),
        *(
            ["    comp->image_len = 0u;"]
            if has_image_len
            else []
        ),
        *(
            ["    comp->cart_enabled = 1u;"]
            if has_enabled_flag
            else []
        ),
        "    snprintf(",
        "        cpu->loaded_rom_debug,",
        "        sizeof(cpu->loaded_rom_debug),",
        f"        \"name={_escape_c_string(comp_id)} path=%s\",",
        "        path",
        "    );",
        "    return 0;",
        "}",
        "",
        f"int {cpu_prefix}_set_cartridge_dir(CPUState *cpu, const char *path) {{",
        "    (void)cpu;",
        "    return cpu_component_host_picker_set_dir(path);",
        "}",
    ]
    return "\n".join(lines) + "\n"


def _generate_floppy_media_loader(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate runtime floppy media loader API."""
    floppy_cfg = isa_data.get("floppy", {}) or {}
    drives_cfg = floppy_cfg.get("drives", []) if floppy_cfg else []
    if not isinstance(drives_cfg, list):
        drives_cfg = []
    floppy_component_id = ""
    if drives_cfg and isinstance(drives_cfg[0], dict):
        floppy_component_id = str(drives_cfg[0].get("component", "") or "")
    if not floppy_component_id:
        floppy_component_id = str(floppy_cfg.get("component", "") or "")
    if not floppy_component_id:
        return (
            f"int {cpu_prefix}_load_floppy_media(CPUState *cpu, const char *path) {{\n"
            "    (void)cpu;\n"
            "    (void)path;\n"
            "    return -1;\n"
            "}\n"
        )
    return (
        f"int {cpu_prefix}_load_floppy_media(CPUState *cpu, const char *path) {{\n"
        "    if (!cpu || !path || !path[0]) return -1;\n"
        "    return cpu_component_floppy_picker_load_path(cpu, path);\n"
        "}\n"
    )


def _to_c_ident(name: str) -> str:
    ident = re.sub(r"[^0-9A-Za-z_]", "_", str(name).strip())
    ident = ident.lower()
    if not ident:
        return "component"
    if ident[0].isdigit():
        return f"component_{ident}"
    return ident


def _generate_ic_runtime_blocks(
    isa_data: Dict[str, Any], cpu_prefix: str
) -> Tuple[str, str, str, str, str, str, str, str, str, str, str]:
    """Generate generic component runtime snippets for template insertion."""
    components = (
        list(isa_data.get("ics", []))
        + list(isa_data.get("devices", []))
        + list(isa_data.get("hosts", []))
    )
    cartridge = isa_data.get("cartridge", {}) or {}
    has_runtime_cartridge = bool(cartridge)
    cassette_cfg = isa_data.get("cassette", {}) or {}
    has_runtime_cassette = bool(cassette_cfg)
    floppy_cfg = isa_data.get("floppy", {}) or {}
    has_runtime_floppy = bool(floppy_cfg)
    default_cart_exts = [
        "rom",
        "bin",
        "a26",
        "nes",
        "sms",
        "gg",
        "sg",
        "mx1",
        "col",
        "atr",
        "car",
        "cas",
        "tap",
        "d64",
    ]
    cart_exts_raw = cartridge.get("allowed_extensions", []) if cartridge else []
    cart_exts: List[str] = []
    if isinstance(cart_exts_raw, list):
        for item in cart_exts_raw:
            ext = str(item).strip().lower()
            if ext.startswith("."):
                ext = ext[1:]
            if not ext or len(ext) >= 16:
                continue
            if not re.fullmatch(r"[a-z0-9_+-]+", ext):
                continue
            if ext not in cart_exts:
                cart_exts.append(ext)
    if not cart_exts:
        cart_exts = default_cart_exts
    cassette_component_id = str(cassette_cfg.get("component", "cassette_transport"))
    cassette_exts_raw = cassette_cfg.get("allowed_extensions", []) if cassette_cfg else []
    cassette_exts: List[str] = []
    for ext in cassette_exts_raw:
        ext_s = str(ext).strip().lower()
        if ext_s.startswith("."):
            ext_s = ext_s[1:]
        if ext_s and ext_s not in cassette_exts:
            cassette_exts.append(ext_s)
    if not cassette_exts:
        cassette_exts = ["yaml", "wav"]
    cassette_sources_cfg = cassette_cfg.get("sources", []) if cassette_cfg else []
    cassette_sources: List[Dict[str, Any]] = []
    if isinstance(cassette_sources_cfg, list):
        for idx, source in enumerate(cassette_sources_cfg):
            if not isinstance(source, dict):
                continue
            source_kind = str(source.get("kind", "")).strip().lower()
            if source_kind not in {"file", "line_in"}:
                continue
            source_component = str(source.get("component", cassette_component_id)).strip() or cassette_component_id
            source_backend_component = str(source.get("source_component", source_component)).strip() or source_component
            source_label = str(source.get("label", "")).strip()
            source_model = str(source.get("source_model", "")).strip()
            if not source_label:
                source_label = "Line In" if source_kind == "line_in" else source_component
            source_exts: List[str] = []
            if source_kind == "file":
                raw_exts = source.get("allowed_extensions", [])
                if isinstance(raw_exts, list):
                    for item in raw_exts:
                        ext = str(item).strip().lower()
                        if ext.startswith("."):
                            ext = ext[1:]
                        if ext and ext not in source_exts:
                            source_exts.append(ext)
            cassette_sources.append(
                {
                    "index": idx,
                    "kind": source_kind,
                    "component": source_component,
                    "source_component": source_backend_component,
                    "label": source_label,
                    "model": source_model,
                    "allowed_extensions": source_exts,
                }
            )
    if not cassette_sources:
        cassette_sources = [
            {
                "index": 0,
                "kind": "file",
                "component": cassette_component_id,
                "source_component": cassette_component_id,
                "label": "Tape",
                "model": "",
                "allowed_extensions": cassette_exts,
            }
        ]
    cassette_file_sources = [source for source in cassette_sources if source["kind"] == "file"]
    cassette_line_in_sources = [source for source in cassette_sources if source["kind"] == "line_in"]
    cassette_all_exts: List[str] = []
    for source in cassette_file_sources:
        for ext in source["allowed_extensions"]:
            if ext not in cassette_all_exts:
                cassette_all_exts.append(ext)
    if not cassette_all_exts:
        cassette_all_exts = cassette_exts
    media_picker_cfg = isa_data.get("media_picker", {}) or {}
    media_picker_action = str(media_picker_cfg.get("open_action_id", "EMU_MEDIA_PICKER"))
    cassette_controls = cassette_cfg.get("controls", {}) or {}
    cassette_picker_action = str(cassette_controls.get("picker_action_id", media_picker_action))
    cassette_play_action = str(cassette_controls.get("play_action_id", "EMU_CASSETTE_PLAY"))
    cassette_pause_action = str(cassette_controls.get("pause_action_id", "EMU_CASSETTE_PAUSE"))
    cassette_stop_action = str(cassette_controls.get("stop_action_id", "EMU_CASSETTE_STOP"))
    cassette_record_action = str(cassette_controls.get("record_action_id", "EMU_CASSETTE_RECORD"))
    cassette_vol_up_action = str(cassette_controls.get("volume_up_action_id", "EMU_CASSETTE_VOL_UP"))
    cassette_vol_down_action = str(cassette_controls.get("volume_down_action_id", "EMU_CASSETTE_VOL_DOWN"))
    cassette_bass_up_action = str(cassette_controls.get("bass_up_action_id", "EMU_CASSETTE_BASS_UP"))
    cassette_bass_down_action = str(cassette_controls.get("bass_down_action_id", "EMU_CASSETTE_BASS_DOWN"))
    cassette_treble_up_action = str(cassette_controls.get("treble_up_action_id", "EMU_CASSETTE_TREBLE_UP"))
    cassette_treble_down_action = str(cassette_controls.get("treble_down_action_id", "EMU_CASSETTE_TREBLE_DOWN"))
    cassette_play_sets_motor = bool(cassette_controls.get("play_sets_motor", True))
    floppy_sources_cfg = floppy_cfg.get("sources", []) if has_runtime_floppy else []
    if not isinstance(floppy_sources_cfg, list):
        floppy_sources_cfg = []
    floppy_sources: List[Dict[str, Any]] = []
    for idx, source in enumerate(floppy_sources_cfg):
        if not isinstance(source, dict):
            continue
        source_kind = str(source.get("kind", "file") or "file").strip().lower()
        if source_kind != "file":
            continue
        source_type = source.get("source_type", {}) or {}
        source_model = ""
        if isinstance(source_type, dict):
            metadata = source_type.get("metadata", {}) or {}
            source_model = str(metadata.get("name", "") or "")
        source_label = str(source.get("label", "") or "")
        source_exts: List[str] = []
        raw_exts = source.get("allowed_extensions", [])
        if isinstance(raw_exts, list):
            for item in raw_exts:
                ext = str(item).strip().lower()
                if ext.startswith("."):
                    ext = ext[1:]
                if ext and ext not in source_exts:
                    source_exts.append(ext)
        floppy_sources.append(
            {
                "index": idx,
                "kind": source_kind,
                "label": source_label,
                "model": source_model,
                "allowed_extensions": source_exts,
            }
        )
    floppy_all_exts: List[str] = []
    for source in floppy_sources:
        for ext in source["allowed_extensions"]:
            if ext not in floppy_all_exts:
                floppy_all_exts.append(ext)
    floppy_drives_cfg = floppy_cfg.get("drives", []) if has_runtime_floppy else []
    if not isinstance(floppy_drives_cfg, list):
        floppy_drives_cfg = []
    floppy_component_id = ""
    if floppy_drives_cfg and isinstance(floppy_drives_cfg[0], dict):
        floppy_component_id = str(floppy_drives_cfg[0].get("component", "") or "")
    if not floppy_component_id:
        floppy_component_id = str(floppy_cfg.get("component", "") or "")
    floppy_picker_action = str((floppy_cfg.get("controls", {}) or {}).get("picker_action_id", media_picker_action))
    if cartridge:
        components.append(cartridge)
    if not components:
        empty = "    /* No IC runtime configured */"
        return (
            "/* No IC runtime helpers */",
            empty,
            empty,
            "    /* No IC destroy hooks */",
            "",
            "",
            "",
            "",
            "",
            "",
            (
                f"int {cpu_prefix}_load_keyboard_map(CPUState *cpu, const char *path) {{\n"
                "    (void)cpu;\n"
                "    (void)path;\n"
                "    return -1;\n"
                "}\n"
            ),
        )
    connections = list(isa_data.get("connections", []))
    host_component_ids = {
        str(component.get("metadata", {}).get("id", ""))
        for component in isa_data.get("hosts", [])
    }
    host_backend_target = _single_host_backend_target(isa_data)
    host_uses_sdl2_backend = host_backend_target == "sdl2"
    host_uses_glfw_backend = host_backend_target == "glfw"

    def _ident(name: str) -> str:
        return _to_c_ident(name)

    def _snippet_block(component: Dict[str, Any], snippet_key: str, indent: str = "    ") -> str:
        behavior = component.get("behavior", {})
        snippets = behavior.get("snippets", {})
        snippet = str(snippets.get(snippet_key, "")).rstrip()
        if not snippet:
            return ""
        comp_id = str(component.get("metadata", {}).get("id", "component"))
        comp_ident = _ident(comp_id)
        lines = [
            f"{indent}{{",
            f"{indent}    ComponentState_{comp_ident} *comp = &cpu->comp_{comp_ident};",
            f'{indent}    cpu->active_component_id = "{_escape_c_string(comp_id)}";',
        ]
        for raw_line in snippet.splitlines():
            if raw_line.strip():
                lines.append(f"{indent}    {raw_line.rstrip()}")
            else:
                lines.append("")
        lines.append(f"{indent}}}")
        return "\n".join(lines)

    helper_lines: List[str] = [
        "void cpu_components_step_pre(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before);",
        "void cpu_components_step_post(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before);",
        "int cpu_components_runtime_pre_step(CPUState *cpu);",
        "",
        "/* PASM_SPLIT_BEGIN:INPUT_RUNTIME */",
        "typedef struct {",
        "    uint8_t row;",
        "    uint8_t bit;",
        "} RuntimeKeyboardPress;",
        "",
        "typedef struct {",
        "    int32_t scancode;",
        "    uint8_t source_kind; /* 1=scancode, 2=host_key */",
        "    uint8_t shift_mode; /* 0=any, 1=up, 2=down */",
        "    RuntimeKeyboardPress *presses;",
        "    uint8_t press_count;",
        "    uint8_t press_cap;",
        "    uint8_t has_ascii;",
        "    uint8_t has_ascii_shift;",
        "    uint8_t has_ascii_ctrl;",
        "    uint8_t ascii;",
        "    uint8_t ascii_shift;",
        "    uint8_t ascii_ctrl;",
        "    uint8_t is_shift_modifier;",
        "    uint8_t is_ctrl_modifier;",
        "    char host_key_name[64];",
        "    char mapper_key_id[128];",
        "    char emulator_key_id[64];",
        "} RuntimeKeyboardBinding;",
        "",
        "typedef struct {",
        "    uint8_t loaded;",
        "    uint8_t kind; /* 1=matrix, 2=ascii */",
        "    uint8_t focus_required;",
        "    RuntimeKeyboardBinding *bindings;",
        "    size_t binding_count;",
        "    size_t binding_cap;",
        "    uint8_t ascii_queue[64];",
        "    uint8_t ascii_q_head;",
        "    uint8_t ascii_q_len;",
        "} RuntimeKeyboardMap;",
        "",
        "static RuntimeKeyboardMap g_runtime_keyboard_map = {0};",
        "",
        "#define CPU_HOST_HAT_UP 0x01u",
        "#define CPU_HOST_HAT_RIGHT 0x02u",
        "#define CPU_HOST_HAT_DOWN 0x04u",
        "#define CPU_HOST_HAT_LEFT 0x08u",
        "",
        "static int cpu_host_hal_gamepad_count(void);",
        "static int cpu_host_hal_gamepad_button(int pad_index, int button_id);",
        "static int cpu_host_hal_gamepad_axis(int pad_index, int axis_id);",
        "static int cpu_host_hal_joystick_count(void);",
        "static int cpu_host_hal_joystick_button(int joy_index, int button);",
        "static int cpu_host_hal_joystick_axis(int joy_index, int axis);",
        "static uint8_t cpu_host_hal_joystick_hat(int joy_index, int hat);",
        "",
    ]

    if host_uses_sdl2_backend:
        helper_lines.append("/* PASM_SPLIT_BEGIN:HOST_HAL_IMPL */")
        helper_lines.extend(
            [
                "typedef SDL_Event CPUHostEvent;",
                "typedef SDL_Rect CPUHostRect;",
                "typedef SDL_AudioSpec CPUHostAudioSpec;",
                "#define CPU_HOST_EVENT_QUIT SDL_QUIT",
                "#define CPU_HOST_EVENT_KEYDOWN SDL_KEYDOWN",
                "#define CPU_HOST_EVENT_KEYUP SDL_KEYUP",
                "#define CPU_HOST_INIT_VIDEO SDL_INIT_VIDEO",
                "#define CPU_HOST_INIT_AUDIO SDL_INIT_AUDIO",
                "#define CPU_HOST_INIT_EVENTS SDL_INIT_EVENTS",
                "#define CPU_HOST_WINDOWPOS_CENTERED SDL_WINDOWPOS_CENTERED",
                "#define CPU_HOST_WINDOW_RESIZABLE SDL_WINDOW_RESIZABLE",
                "#define CPU_HOST_RENDERER_ACCELERATED SDL_RENDERER_ACCELERATED",
                "#define CPU_HOST_PIXELFORMAT_ARGB8888 SDL_PIXELFORMAT_ARGB8888",
                "#define CPU_HOST_TEXTUREACCESS_STREAMING SDL_TEXTUREACCESS_STREAMING",
                "#ifndef CPU_HOST_AUDIO_ALLOW_FREQUENCY_CHANGE",
                "#define CPU_HOST_AUDIO_ALLOW_FREQUENCY_CHANGE SDL_AUDIO_ALLOW_FREQUENCY_CHANGE",
                "#endif",
                "#ifndef CPU_HOST_AUDIO_ALLOW_FORMAT_CHANGE",
                "#define CPU_HOST_AUDIO_ALLOW_FORMAT_CHANGE SDL_AUDIO_ALLOW_FORMAT_CHANGE",
                "#endif",
                "#ifndef CPU_HOST_AUDIO_ALLOW_CHANNELS_CHANGE",
                "#define CPU_HOST_AUDIO_ALLOW_CHANNELS_CHANGE SDL_AUDIO_ALLOW_CHANNELS_CHANGE",
                "#endif",
                "#ifndef CPU_HOST_AUDIO_ALLOW_SAMPLES_CHANGE",
                "#define CPU_HOST_AUDIO_ALLOW_SAMPLES_CHANGE SDL_AUDIO_ALLOW_SAMPLES_CHANGE",
                "#endif",
                "#define CPU_HOST_AUDIO_FORMAT_S16 AUDIO_S16SYS",
                "#define CPU_HOST_SCANCODE(name) SDL_SCANCODE_##name",
                "#define CPU_HOST_HAS_SCANCODE_MAP 1",
                "#define CPU_HOST_KEYCODE_QUOTE ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(APOSTROPHE)))",
                "#define CPU_HOST_KEYCODE_SEMICOLON ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(SEMICOLON)))",
                "#define CPU_HOST_MOD_CTRL KMOD_CTRL",
                "#define CPU_HOST_MOD_SHIFT KMOD_SHIFT",
                "#define CPU_HOST_MOD_LCTRL KMOD_LCTRL",
                "#include <stdarg.h>",
                "extern int SDL_QueueAudio(uint32_t dev, const void *data, uint32_t len);",
                "extern uint32_t SDL_GetQueuedAudioSize(uint32_t dev);",
                "extern void SDL_ClearQueuedAudio(uint32_t dev);",
                "extern void SDL_PauseAudioDevice(uint32_t dev, int pause_on);",
                "extern uint32_t SDL_OpenAudioDevice(const char *device, int iscapture, const CPUHostAudioSpec *desired, CPUHostAudioSpec *obtained, int allowed_changes);",
                "extern void SDL_CloseAudioDevice(uint32_t dev);",
                "#define cpu_host_hal_log(...) SDL_Log(__VA_ARGS__)",
                "#define cpu_host_hal_last_error() SDL_GetError()",
                "static void cpu_host_audio_spec_zero(CPUHostAudioSpec *spec) {",
                "    if (!spec) return;",
                "    SDL_zero(*spec);",
                "}",
                "",
            ]
        )
        helper_lines.append("/* PASM_SPLIT_END:HOST_HAL_IMPL */")
    elif host_uses_glfw_backend:
        helper_lines.append("/* PASM_SPLIT_BEGIN:HOST_HAL_IMPL */")
        helper_lines.extend(
            [
                "typedef struct {",
                "    uint32_t type;",
                "    struct {",
                "        uint8_t repeat;",
                "        uint32_t mod_state;",
                "        struct {",
                "            uint32_t scancode;",
                "        } keysym;",
                "    } key;",
                "} CPUHostEvent;",
                "typedef struct {",
                "    int x;",
                "    int y;",
                "    int w;",
                "    int h;",
                "} CPUHostRect;",
                "typedef struct {",
                "    int freq;",
                "    uint16_t format;",
                "    uint8_t channels;",
                "    uint8_t silence;",
                "    uint16_t samples;",
                "    uint16_t padding;",
                "    uint32_t size;",
                "    void *callback;",
                "    void *userdata;",
                "} CPUHostAudioSpec;",
                "typedef struct GLFWwindow GLFWwindow;",
                "typedef struct {",
                "    GLFWwindow *window;",
                "    int w;",
                "    int h;",
                "    uint32_t clear_color;",
                "    uint8_t *frame_rgba;",
                "    size_t frame_len;",
                "    uint8_t frame_rgba_dirty;",
                "    unsigned int present_program;",
                "    unsigned int present_vertex_shader;",
                "    unsigned int present_fragment_shader;",
                "    unsigned int present_vao;",
                "    unsigned int present_vbo;",
                "    unsigned int present_texture;",
                "    int present_texture_w;",
                "    int present_texture_h;",
                "} CPUHostGlfwRenderer;",
                "typedef struct {",
                "    int w;",
                "    int h;",
                "    uint8_t *pixels;",
                "    size_t pixels_len;",
                "} CPUHostGlfwTexture;",
                "typedef struct {",
                "    unsigned int program;",
                "    unsigned int vertex_shader;",
                "    unsigned int fragment_shader;",
                "    unsigned int vao;",
                "    unsigned int vbo;",
                "    unsigned int texture;",
                "    int texture_w;",
                "    int texture_h;",
                "} CPUHostGlfwShader;",
                "typedef unsigned int GLenum;",
                "typedef unsigned int GLuint;",
                "typedef int GLint;",
                "typedef int GLsizei;",
                "typedef char GLchar;",
                "typedef float GLfloat;",
                "typedef unsigned char GLboolean;",
                "typedef ptrdiff_t GLsizeiptr;",
                "typedef void (*CPUHostGLProc)(void);",
                "#ifndef SDL_INIT_AUDIO",
                "#define SDL_INIT_AUDIO 0x00000010u",
                "#endif",
                "extern int SDL_Init(uint32_t flags);",
                "extern void SDL_QuitSubSystem(uint32_t flags);",
                "extern const char *SDL_GetError(void);",
                "extern int SDL_GetNumAudioDrivers(void);",
                "extern const char *SDL_GetAudioDriver(int index);",
                "extern const char *SDL_GetCurrentAudioDriver(void);",
                "extern int SDL_GetNumAudioDevices(int iscapture);",
                "extern const char *SDL_GetAudioDeviceName(int index, int iscapture);",
                "extern int SDL_QueueAudio(uint32_t dev, const void *data, uint32_t len);",
                "extern uint32_t SDL_GetQueuedAudioSize(uint32_t dev);",
                "extern void SDL_ClearQueuedAudio(uint32_t dev);",
                "extern void SDL_PauseAudioDevice(uint32_t dev, int pause_on);",
                "extern uint32_t SDL_OpenAudioDevice(const char *device, int iscapture, const CPUHostAudioSpec *desired, CPUHostAudioSpec *obtained, int allowed_changes);",
                "extern void SDL_CloseAudioDevice(uint32_t dev);",
                "extern int glfwInit(void);",
                "extern void glfwTerminate(void);",
                "extern void glfwPollEvents(void);",
                "extern double glfwGetTime(void);",
                "extern int glfwGetWindowAttrib(GLFWwindow *window, int attrib);",
                "extern int glfwGetKey(GLFWwindow *window, int key);",
                "extern void glfwSetWindowTitle(GLFWwindow *window, const char *title);",
                "extern void glfwDestroyWindow(GLFWwindow *window);",
                "extern void glfwWindowHint(int hint, int value);",
                "extern GLFWwindow *glfwCreateWindow(int width, int height, const char *title, void *monitor, void *share);",
                "extern void glfwShowWindow(GLFWwindow *window);",
                "extern void glfwFocusWindow(GLFWwindow *window);",
                "extern void glfwSetWindowSize(GLFWwindow *window, int width, int height);",
                "extern int glfwWindowShouldClose(GLFWwindow *window);",
                "extern void glfwGetWindowSize(GLFWwindow *window, int *width, int *height);",
                "extern void glfwSwapBuffers(GLFWwindow *window);",
                "extern void glfwSwapInterval(int interval);",
                "extern void glfwMakeContextCurrent(GLFWwindow *window);",
                "extern CPUHostGLProc glfwGetProcAddress(const char *procname);",
                "extern int glfwJoystickPresent(int jid);",
                "extern const float *glfwGetJoystickAxes(int jid, int *count);",
                "extern const unsigned char *glfwGetJoystickButtons(int jid, int *count);",
                "extern const unsigned char *glfwGetJoystickHats(int jid, int *count);",
                "extern const char *glfwGetJoystickGUID(int jid);",
                "extern int glfwJoystickIsGamepad(int jid);",
                "typedef struct GLFWgamepadstate { unsigned char buttons[15]; float axes[6]; } GLFWgamepadstate;",
                "extern int glfwGetGamepadState(int jid, GLFWgamepadstate *state);",
                "#define GLFW_FOCUSED 0x00020001",
                "#define GLFW_CONTEXT_VERSION_MAJOR 0x00022002",
                "#define GLFW_CONTEXT_VERSION_MINOR 0x00022003",
                "#define GLFW_OPENGL_PROFILE 0x00022008",
                "#define GLFW_OPENGL_CORE_PROFILE 0x00032001",
                "#define GLFW_PRESS 1",
                "#define GLFW_REPEAT 2",
                "#define GLFW_JOYSTICK_1 0",
                "#define GLFW_JOYSTICK_LAST 15",
                "#define GLFW_GAMEPAD_AXIS_LEFT_X 0",
                "#define GLFW_GAMEPAD_AXIS_LEFT_Y 1",
                "#define GLFW_GAMEPAD_AXIS_RIGHT_X 2",
                "#define GLFW_GAMEPAD_AXIS_RIGHT_Y 3",
                "#define GLFW_GAMEPAD_AXIS_LEFT_TRIGGER 4",
                "#define GLFW_GAMEPAD_AXIS_RIGHT_TRIGGER 5",
                "#define GLFW_GAMEPAD_BUTTON_A 0",
                "#define GLFW_GAMEPAD_BUTTON_B 1",
                "#define GLFW_GAMEPAD_BUTTON_X 2",
                "#define GLFW_GAMEPAD_BUTTON_Y 3",
                "#define GLFW_GAMEPAD_BUTTON_LEFT_BUMPER 4",
                "#define GLFW_GAMEPAD_BUTTON_RIGHT_BUMPER 5",
                "#define GLFW_GAMEPAD_BUTTON_BACK 6",
                "#define GLFW_GAMEPAD_BUTTON_START 7",
                "#define GLFW_GAMEPAD_BUTTON_GUIDE 8",
                "#define GLFW_GAMEPAD_BUTTON_LEFT_THUMB 9",
                "#define GLFW_GAMEPAD_BUTTON_RIGHT_THUMB 10",
                "#define GLFW_GAMEPAD_BUTTON_DPAD_UP 11",
                "#define GLFW_GAMEPAD_BUTTON_DPAD_RIGHT 12",
                "#define GLFW_GAMEPAD_BUTTON_DPAD_DOWN 13",
                "#define GLFW_GAMEPAD_BUTTON_DPAD_LEFT 14",
                "#define GLFW_TRUE 1",
                "#define GLFW_FALSE 0",
                "#define GLFW_RESIZABLE 0x00020003",
                "#define GLFW_HAT_UP 0x01",
                "#define GLFW_HAT_RIGHT 0x02",
                "#define GLFW_HAT_DOWN 0x04",
                "#define GLFW_HAT_LEFT 0x08",
                "#define GLFW_KEY_SPACE 32",
                "#define GLFW_KEY_APOSTROPHE 39",
                "#define GLFW_KEY_COMMA 44",
                "#define GLFW_KEY_MINUS 45",
                "#define GLFW_KEY_PERIOD 46",
                "#define GLFW_KEY_SLASH 47",
                "#define GLFW_KEY_0 48",
                "#define GLFW_KEY_1 49",
                "#define GLFW_KEY_2 50",
                "#define GLFW_KEY_3 51",
                "#define GLFW_KEY_4 52",
                "#define GLFW_KEY_5 53",
                "#define GLFW_KEY_6 54",
                "#define GLFW_KEY_7 55",
                "#define GLFW_KEY_8 56",
                "#define GLFW_KEY_9 57",
                "#define GLFW_KEY_SEMICOLON 59",
                "#define GLFW_KEY_EQUAL 61",
                "#define GLFW_KEY_A 65",
                "#define GLFW_KEY_B 66",
                "#define GLFW_KEY_C 67",
                "#define GLFW_KEY_D 68",
                "#define GLFW_KEY_E 69",
                "#define GLFW_KEY_F 70",
                "#define GLFW_KEY_G 71",
                "#define GLFW_KEY_H 72",
                "#define GLFW_KEY_I 73",
                "#define GLFW_KEY_J 74",
                "#define GLFW_KEY_K 75",
                "#define GLFW_KEY_L 76",
                "#define GLFW_KEY_M 77",
                "#define GLFW_KEY_N 78",
                "#define GLFW_KEY_O 79",
                "#define GLFW_KEY_P 80",
                "#define GLFW_KEY_Q 81",
                "#define GLFW_KEY_R 82",
                "#define GLFW_KEY_S 83",
                "#define GLFW_KEY_T 84",
                "#define GLFW_KEY_U 85",
                "#define GLFW_KEY_V 86",
                "#define GLFW_KEY_W 87",
                "#define GLFW_KEY_X 88",
                "#define GLFW_KEY_Y 89",
                "#define GLFW_KEY_Z 90",
                "#define GLFW_KEY_LEFT_BRACKET 91",
                "#define GLFW_KEY_BACKSLASH 92",
                "#define GLFW_KEY_RIGHT_BRACKET 93",
                "#define GLFW_KEY_GRAVE_ACCENT 96",
                "#define GLFW_KEY_ESCAPE 256",
                "#define GLFW_KEY_ENTER 257",
                "#define GLFW_KEY_TAB 258",
                "#define GLFW_KEY_BACKSPACE 259",
                "#define GLFW_KEY_INSERT 260",
                "#define GLFW_KEY_DELETE 261",
                "#define GLFW_KEY_RIGHT 262",
                "#define GLFW_KEY_LEFT 263",
                "#define GLFW_KEY_DOWN 264",
                "#define GLFW_KEY_UP 265",
                "#define GLFW_KEY_PAGE_DOWN 267",
                "#define GLFW_KEY_PAGE_UP 266",
                "#define GLFW_KEY_PAUSE 284",
                "#define GLFW_KEY_HOME 268",
                "#define GLFW_KEY_END 269",
                "#define GLFW_KEY_CAPS_LOCK 280",
                "#define GLFW_KEY_F1 290",
                "#define GLFW_KEY_F2 291",
                "#define GLFW_KEY_F3 292",
                "#define GLFW_KEY_F4 293",
                "#define GLFW_KEY_F5 294",
                "#define GLFW_KEY_F6 295",
                "#define GLFW_KEY_F7 296",
                "#define GLFW_KEY_F8 297",
                "#define GLFW_KEY_F9 298",
                "#define GLFW_KEY_F10 299",
                "#define GLFW_KEY_F11 300",
                "#define GLFW_KEY_F12 301",
                "#define GLFW_KEY_KP_0 320",
                "#define GLFW_KEY_KP_1 321",
                "#define GLFW_KEY_KP_2 322",
                "#define GLFW_KEY_KP_3 323",
                "#define GLFW_KEY_KP_4 324",
                "#define GLFW_KEY_KP_5 325",
                "#define GLFW_KEY_KP_6 326",
                "#define GLFW_KEY_KP_7 327",
                "#define GLFW_KEY_KP_8 328",
                "#define GLFW_KEY_KP_9 329",
                "#define GLFW_KEY_KP_DECIMAL 330",
                "#define GLFW_KEY_KP_ENTER 335",
                "#define GLFW_KEY_LEFT_SHIFT 340",
                "#define GLFW_KEY_LEFT_CONTROL 341",
                "#define GLFW_KEY_LEFT_ALT 342",
                "#define GLFW_KEY_RIGHT_SHIFT 344",
                "#define GLFW_KEY_RIGHT_CONTROL 345",
                "#define GLFW_KEY_RIGHT_ALT 346",
                "#define GLFW_KEY_MENU 348",
                "#define GLFW_KEY_WORLD_1 161",
                "#define GLFW_KEY_WORLD_2 162",
                "enum {",
                "    CPU_GLFW_SC_0 = 0,",
                "    CPU_GLFW_SC_1,",
                "    CPU_GLFW_SC_2,",
                "    CPU_GLFW_SC_3,",
                "    CPU_GLFW_SC_4,",
                "    CPU_GLFW_SC_5,",
                "    CPU_GLFW_SC_6,",
                "    CPU_GLFW_SC_7,",
                "    CPU_GLFW_SC_8,",
                "    CPU_GLFW_SC_9,",
                "    CPU_GLFW_SC_A,",
                "    CPU_GLFW_SC_APOSTROPHE,",
                "    CPU_GLFW_SC_B,",
                "    CPU_GLFW_SC_BACKSLASH,",
                "    CPU_GLFW_SC_BACKSPACE,",
                "    CPU_GLFW_SC_C,",
                "    CPU_GLFW_SC_CAPSLOCK,",
                "    CPU_GLFW_SC_COMMA,",
                "    CPU_GLFW_SC_D,",
                "    CPU_GLFW_SC_DOWN,",
                "    CPU_GLFW_SC_E,",
                "    CPU_GLFW_SC_EQUALS,",
                "    CPU_GLFW_SC_ESCAPE,",
                "    CPU_GLFW_SC_F,",
                "    CPU_GLFW_SC_F1,",
                "    CPU_GLFW_SC_F2,",
                "    CPU_GLFW_SC_F3,",
                "    CPU_GLFW_SC_F4,",
                "    CPU_GLFW_SC_F5,",
                "    CPU_GLFW_SC_F6,",
                "    CPU_GLFW_SC_F7,",
                "    CPU_GLFW_SC_F8,",
                "    CPU_GLFW_SC_F9,",
                "    CPU_GLFW_SC_F10,",
                "    CPU_GLFW_SC_F11,",
                "    CPU_GLFW_SC_F12,",
                "    CPU_GLFW_SC_G,",
                "    CPU_GLFW_SC_GRAVE,",
                "    CPU_GLFW_SC_H,",
                "    CPU_GLFW_SC_HOME,",
                "    CPU_GLFW_SC_I,",
                "    CPU_GLFW_SC_INSERT,",
                "    CPU_GLFW_SC_INTERNATIONAL1,",
                "    CPU_GLFW_SC_J,",
                "    CPU_GLFW_SC_K,",
                "    CPU_GLFW_SC_KP_0,",
                "    CPU_GLFW_SC_KP_1,",
                "    CPU_GLFW_SC_KP_2,",
                "    CPU_GLFW_SC_KP_3,",
                "    CPU_GLFW_SC_KP_4,",
                "    CPU_GLFW_SC_KP_5,",
                "    CPU_GLFW_SC_KP_6,",
                "    CPU_GLFW_SC_KP_7,",
                "    CPU_GLFW_SC_KP_8,",
                "    CPU_GLFW_SC_KP_9,",
                "    CPU_GLFW_SC_KP_ENTER,",
                "    CPU_GLFW_SC_KP_PERIOD,",
                "    CPU_GLFW_SC_L,",
                "    CPU_GLFW_SC_LALT,",
                "    CPU_GLFW_SC_LCTRL,",
                "    CPU_GLFW_SC_LEFT,",
                "    CPU_GLFW_SC_LEFTBRACKET,",
                "    CPU_GLFW_SC_LSHIFT,",
                "    CPU_GLFW_SC_M,",
                "    CPU_GLFW_SC_MINUS,",
                "    CPU_GLFW_SC_N,",
                "    CPU_GLFW_SC_NONUSBACKSLASH,",
                "    CPU_GLFW_SC_NONUSHASH,",
                "    CPU_GLFW_SC_O,",
                "    CPU_GLFW_SC_P,",
                "    CPU_GLFW_SC_PAGEDOWN,",
                "    CPU_GLFW_SC_PAGEUP,",
                "    CPU_GLFW_SC_PAUSE,",
                "    CPU_GLFW_SC_PERIOD,",
                "    CPU_GLFW_SC_Q,",
                "    CPU_GLFW_SC_R,",
                "    CPU_GLFW_SC_RALT,",
                "    CPU_GLFW_SC_RCTRL,",
                "    CPU_GLFW_SC_RETURN,",
                "    CPU_GLFW_SC_RETURN2,",
                "    CPU_GLFW_SC_RIGHT,",
                "    CPU_GLFW_SC_RIGHTBRACKET,",
                "    CPU_GLFW_SC_RSHIFT,",
                "    CPU_GLFW_SC_S,",
                "    CPU_GLFW_SC_SEMICOLON,",
                "    CPU_GLFW_SC_SLASH,",
                "    CPU_GLFW_SC_SPACE,",
                "    CPU_GLFW_SC_T,",
                "    CPU_GLFW_SC_TAB,",
                "    CPU_GLFW_SC_U,",
                "    CPU_GLFW_SC_UP,",
                "    CPU_GLFW_SC_V,",
                "    CPU_GLFW_SC_W,",
                "    CPU_GLFW_SC_X,",
                "    CPU_GLFW_SC_Y,",
                "    CPU_GLFW_SC_Z,",
                "    CPU_GLFW_SC_APPLICATION,",
                "    CPU_GLFW_SC_DELETE,",
                "    CPU_GLFW_SC_END,",
                "    CPU_GLFW_SC_COUNT",
                "};",
                "#define CPU_HOST_EVENT_QUIT 0x100u",
                "#define CPU_HOST_EVENT_KEYDOWN 0x300u",
                "#define CPU_HOST_EVENT_KEYUP 0x301u",
                "#define CPU_HOST_INIT_VIDEO 0x00000020u",
                "#define CPU_HOST_INIT_AUDIO 0x00000010u",
                "#define CPU_HOST_INIT_EVENTS 0x00004000u",
                "#define CPU_HOST_WINDOWPOS_CENTERED 0",
                "#define CPU_HOST_WINDOW_RESIZABLE 0x00000020u",
                "#define CPU_HOST_RENDERER_ACCELERATED 0x00000002u",
                "#define CPU_HOST_PIXELFORMAT_ARGB8888 372645892u",
                "#define CPU_HOST_TEXTUREACCESS_STREAMING 1",
                "#define CPU_HOST_AUDIO_ALLOW_FREQUENCY_CHANGE 0x00000001",
                "#define CPU_HOST_AUDIO_ALLOW_FORMAT_CHANGE 0x00000002",
                "#define CPU_HOST_AUDIO_ALLOW_CHANNELS_CHANGE 0x00000004",
                "#define CPU_HOST_AUDIO_ALLOW_SAMPLES_CHANGE 0x00000008",
                "#define CPU_HOST_AUDIO_FORMAT_S16 0x8010u",
                "#define CPU_HOST_SCANCODE(name) CPU_GLFW_SC_##name",
                "#define CPU_HOST_HAS_SCANCODE_MAP 1",
                "#define CPU_HOST_KEYCODE_QUOTE ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(APOSTROPHE)))",
                "#define CPU_HOST_KEYCODE_SEMICOLON ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(SEMICOLON)))",
                "#define CPU_HOST_MOD_CTRL 0x0001u",
                "#define CPU_HOST_MOD_SHIFT 0x0002u",
                "#define CPU_HOST_MOD_LCTRL 0x0004u",
                "#define GL_FALSE 0",
                "#define GL_TRUE 1",
                "#define GL_TEXTURE_2D 0x0DE1u",
                "#define GL_RGBA 0x1908u",
                "#define GL_BGRA 0x80E1u",
                "#define GL_UNSIGNED_BYTE 0x1401u",
                "#define GL_FLOAT 0x1406u",
                "#define GL_ARRAY_BUFFER 0x8892u",
                "#define GL_STATIC_DRAW 0x88E4u",
                "#define GL_VERTEX_SHADER 0x8B31u",
                "#define GL_FRAGMENT_SHADER 0x8B30u",
                "#define GL_COMPILE_STATUS 0x8B81u",
                "#define GL_LINK_STATUS 0x8B82u",
                "#define GL_TEXTURE0 0x84C0u",
                "#define GL_TEXTURE_MIN_FILTER 0x2801u",
                "#define GL_TEXTURE_MAG_FILTER 0x2800u",
                "#define GL_TEXTURE_WRAP_S 0x2802u",
                "#define GL_TEXTURE_WRAP_T 0x2803u",
                "#define GL_NEAREST 0x2600u",
                "#define GL_LINEAR 0x2601u",
                "#define GL_CLAMP_TO_EDGE 0x812Fu",
                "#define GL_TRIANGLE_STRIP 0x0005u",
                "#define GL_COLOR_BUFFER_BIT 0x00004000u",
                "#define cpu_host_hal_log(...) do { fprintf(stderr, __VA_ARGS__); fprintf(stderr, \"\\n\"); } while (0)",
                "#define cpu_host_hal_last_error() \"\"",
                "static void cpu_host_audio_spec_zero(CPUHostAudioSpec *spec) {",
                "    if (!spec) return;",
                "    memset(spec, 0, sizeof(*spec));",
                "}",
                "",
            ]
        )
        helper_lines.append("/* PASM_SPLIT_END:HOST_HAL_IMPL */")
    else:
        helper_lines.append("/* PASM_SPLIT_BEGIN:HOST_HAL_IMPL */")
        helper_lines.extend(
            [
                "typedef struct {",
                "    uint32_t type;",
                "    struct {",
                "        uint8_t repeat;",
                "        uint32_t mod_state;",
                "        struct {",
                "            uint32_t scancode;",
                "        } keysym;",
                "    } key;",
                "} CPUHostEvent;",
                "typedef struct {",
                "    int x;",
                "    int y;",
                "    int w;",
                "    int h;",
                "} CPUHostRect;",
                "typedef struct {",
                "    int freq;",
                "    uint16_t format;",
                "    uint8_t channels;",
                "    uint8_t silence;",
                "    uint16_t samples;",
                "    uint16_t padding;",
                "    uint32_t size;",
                "    void *callback;",
                "    void *userdata;",
                "} CPUHostAudioSpec;",
                "#define CPU_HOST_EVENT_QUIT 0x100u",
                "#define CPU_HOST_EVENT_KEYDOWN 0x300u",
                "#define CPU_HOST_EVENT_KEYUP 0x301u",
                "#define CPU_HOST_INIT_VIDEO 0x00000020u",
                "#define CPU_HOST_INIT_AUDIO 0x00000010u",
                "#define CPU_HOST_INIT_EVENTS 0x00004000u",
                "#define CPU_HOST_WINDOWPOS_CENTERED 0",
                "#define CPU_HOST_WINDOW_RESIZABLE 0x00000020u",
                "#define CPU_HOST_RENDERER_ACCELERATED 0x00000002u",
                "#define CPU_HOST_PIXELFORMAT_ARGB8888 372645892u",
                "#define CPU_HOST_TEXTUREACCESS_STREAMING 1",
                "#define CPU_HOST_AUDIO_ALLOW_FREQUENCY_CHANGE 0x00000001",
                "#define CPU_HOST_AUDIO_ALLOW_FORMAT_CHANGE 0x00000002",
                "#define CPU_HOST_AUDIO_ALLOW_CHANNELS_CHANGE 0x00000004",
                "#define CPU_HOST_AUDIO_ALLOW_SAMPLES_CHANGE 0x00000008",
                "#define CPU_HOST_AUDIO_FORMAT_S16 0x8010u",
                "#define CPU_HOST_SCANCODE(name) 0u",
                "#define CPU_HOST_HAS_SCANCODE_MAP 0",
                "#define CPU_HOST_KEYCODE_QUOTE ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(APOSTROPHE)))",
                "#define CPU_HOST_KEYCODE_SEMICOLON ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(SEMICOLON)))",
                "#define CPU_HOST_MOD_CTRL 0u",
                "#define CPU_HOST_MOD_SHIFT 0u",
                "#define CPU_HOST_MOD_LCTRL 0u",
                "#define cpu_host_hal_log(...) do { fprintf(stderr, __VA_ARGS__); fprintf(stderr, \"\\n\"); } while (0)",
                "#define cpu_host_hal_last_error() \"\"",
                "static void cpu_host_audio_spec_zero(CPUHostAudioSpec *spec) {",
                "    if (!spec) return;",
                "    memset(spec, 0, sizeof(*spec));",
                "}",
                "",
            ]
        )
        helper_lines.append("/* PASM_SPLIT_END:HOST_HAL_IMPL */")

    if host_uses_sdl2_backend:
        helper_lines.append("/* PASM_SPLIT_BEGIN:HOST_HAL_IMPL */")
        helper_lines.extend(
            [
                "static uint8_t cpu_host_hal_sdl_inited = 0u;",
                "static uint32_t cpu_host_hal_sdl_subsystems = 0u;",
                "static SDL_Window *cpu_host_hal_sdl_primary_window = NULL;",
                "",
                "static void cpu_host_hal_pump_events(void) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return;",
                "    SDL_PumpEvents();",
                "}",
                "",
                "static uint32_t cpu_host_hal_ticks_ms(void) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return 0u;",
                "    return SDL_GetTicks();",
                "}",
                "",
                "static uint8_t cpu_host_hal_window_has_focus(void *window) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return 0u;",
                "    if (!window) window = (void *)cpu_host_hal_sdl_primary_window;",
                "    if (!window) return 0u;",
                "    return (SDL_GetKeyboardFocus() == (SDL_Window *)window) ? 1u : 0u;",
                "}",
                "",
                "static void cpu_host_hal_render_present(void *renderer) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!renderer) return;",
                "    SDL_RenderPresent((SDL_Renderer *)renderer);",
                "}",
                "",
                "static int cpu_host_hal_audio_queue(uint32_t dev, const void *data, uint32_t len_bytes) {",
                "    uint64_t need64;",
                "    uint32_t need;",
                "    uint32_t new_cap;",
                "    uint8_t *new_buf;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return -1;",
                "    if (dev == 0u || !data || len_bytes == 0u || cpu_host_hal_glfw_audio_opened == 0u) return -1;",
                "#ifdef _WIN32",
                "    if (cpu_host_hal_glfw_waveout != NULL) {",
                "        uint32_t tries;",
                "        for (tries = 0u; tries < 4u; ++tries) {",
                "            uint32_t idx = (cpu_host_hal_glfw_wave_next + tries) & 3u;",
                "            WAVEHDR *hdr = &cpu_host_hal_glfw_wave_headers[idx];",
                "            if ((hdr->dwFlags & WHDR_INQUEUE) != 0u) continue;",
                "            if ((hdr->dwFlags & WHDR_PREPARED) != 0u) {",
                "                waveOutUnprepareHeader(cpu_host_hal_glfw_waveout, hdr, sizeof(*hdr));",
                "                hdr->dwFlags = 0u;",
                "            }",
                "            if (len_bytes > cpu_host_hal_glfw_wave_buffer_bytes) return -1;",
                "            memcpy(cpu_host_hal_glfw_wave_buffers[idx], data, (size_t)len_bytes);",
                "            memset(hdr, 0, sizeof(*hdr));",
                "            hdr->lpData = (LPSTR)cpu_host_hal_glfw_wave_buffers[idx];",
                "            hdr->dwBufferLength = (DWORD)len_bytes;",
                "            if (waveOutPrepareHeader(cpu_host_hal_glfw_waveout, hdr, sizeof(*hdr)) != MMSYSERR_NOERROR) return -1;",
                "            if (waveOutWrite(cpu_host_hal_glfw_waveout, hdr, sizeof(*hdr)) != MMSYSERR_NOERROR) {",
                "                waveOutUnprepareHeader(cpu_host_hal_glfw_waveout, hdr, sizeof(*hdr));",
                "                return -1;",
                "            }",
                "            cpu_host_hal_glfw_wave_next = (idx + 1u) & 3u;",
                "            return 0;",
                "        }",
                "        return 0;",
                "    }",
                "#endif",
                "#ifdef __linux__",
                "    if (cpu_host_hal_glfw_sdl_audio_dev != 0u) {",
                "        return SDL_QueueAudio(cpu_host_hal_glfw_sdl_audio_dev, data, len_bytes);",
                "    }",
                "    if (cpu_host_hal_glfw_alsa_pcm != NULL) {",
                "        pthread_mutex_lock(&cpu_host_hal_glfw_audio_mutex);",
                "        if (cpu_host_hal_glfw_audio_len > cpu_host_hal_glfw_audio_cap) {",
                "            pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "            return -1;",
                "        }",
                "        if (cpu_host_hal_glfw_audio_cap != 0u && cpu_host_hal_glfw_audio_buf == NULL) {",
                "            pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "            return -1;",
                "        }",
                "        if (cpu_host_hal_glfw_audio_len != 0u && cpu_host_hal_glfw_audio_buf == NULL) {",
                "            pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "            return -1;",
                "        }",
                "        need64 = (uint64_t)cpu_host_hal_glfw_audio_len + (uint64_t)len_bytes;",
                "        if (need64 == 0u || need64 > 0xFFFFFFFFu || need64 > (uint64_t)SIZE_MAX) {",
                "            pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "            return -1;",
                "        }",
                "        need = (uint32_t)need64;",
                "        if (need > cpu_host_hal_glfw_audio_cap) {",
                "            new_cap = (cpu_host_hal_glfw_audio_cap == 0u) ? 4096u : cpu_host_hal_glfw_audio_cap;",
                "            while (new_cap < need) {",
                "                if (new_cap > 0x7FFFFFFFu) {",
                "                    new_cap = need;",
                "                    break;",
                "                }",
                "                new_cap <<= 1u;",
                "            }",
                "            if (new_cap < need || (uint64_t)new_cap > (uint64_t)SIZE_MAX) {",
                "                pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "                return -1;",
                "            }",
                "            new_buf = (uint8_t *)realloc(cpu_host_hal_glfw_audio_buf, (size_t)new_cap);",
                "            if (!new_buf) {",
                "                pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "                return -1;",
                "            }",
                "            cpu_host_hal_glfw_audio_buf = new_buf;",
                "            cpu_host_hal_glfw_audio_cap = new_cap;",
                "        }",
                "        memcpy(",
                "            cpu_host_hal_glfw_audio_buf + cpu_host_hal_glfw_audio_len,",
                "            data,",
                "            (size_t)len_bytes",
                "        );",
                "        cpu_host_hal_glfw_audio_len = need;",
                "        pthread_cond_signal(&cpu_host_hal_glfw_audio_cond);",
                "        pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "        return 0;",
                "    }",
                "#endif",
                "    if (cpu_host_hal_glfw_audio_len > cpu_host_hal_glfw_audio_cap) return -1;",
                "    if (cpu_host_hal_glfw_audio_cap != 0u && cpu_host_hal_glfw_audio_buf == NULL) return -1;",
                "    if (cpu_host_hal_glfw_audio_len != 0u && cpu_host_hal_glfw_audio_buf == NULL) return -1;",
                "    need64 = (uint64_t)cpu_host_hal_glfw_audio_len + (uint64_t)len_bytes;",
                "    if (need64 == 0u || need64 > 0xFFFFFFFFu || need64 > (uint64_t)SIZE_MAX) return -1;",
                "    need = (uint32_t)need64;",
                "    if (need > cpu_host_hal_glfw_audio_cap) {",
                "        new_cap = (cpu_host_hal_glfw_audio_cap == 0u) ? 4096u : cpu_host_hal_glfw_audio_cap;",
                "        while (new_cap < need) {",
                "            if (new_cap > 0x7FFFFFFFu) {",
                "                new_cap = need;",
                "                break;",
                "            }",
                "            new_cap <<= 1u;",
                "        }",
                "        if (new_cap < need || (uint64_t)new_cap > (uint64_t)SIZE_MAX) return -1;",
                "        new_buf = (uint8_t *)realloc(cpu_host_hal_glfw_audio_buf, (size_t)new_cap);",
                "        if (!new_buf) return -1;",
                "        cpu_host_hal_glfw_audio_buf = new_buf;",
                "        cpu_host_hal_glfw_audio_cap = new_cap;",
                "    }",
                "    memcpy(",
                "        cpu_host_hal_glfw_audio_buf + cpu_host_hal_glfw_audio_len,",
                "        data,",
                "        (size_t)len_bytes",
                "    );",
                "    cpu_host_hal_glfw_audio_len = need;",
                "    return 0;",
                "}",
                "",
                "static uint32_t cpu_host_hal_audio_queued_bytes(uint32_t dev) {",
                "    uint32_t queued = 0u;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    if (dev == 0u || cpu_host_hal_glfw_audio_opened == 0u) return 0u;",
                "#ifdef __linux__",
                "    if (cpu_host_hal_glfw_sdl_audio_dev != 0u) {",
                "        return SDL_GetQueuedAudioSize(cpu_host_hal_glfw_sdl_audio_dev);",
                "    }",
                "#endif",
                "#ifdef _WIN32",
                "    if (cpu_host_hal_glfw_waveout != NULL) {",
                "        uint32_t i;",
                "        for (i = 0u; i < 4u; ++i) {",
                "            if ((cpu_host_hal_glfw_wave_headers[i].dwFlags & WHDR_INQUEUE) != 0u) {",
                "                queued += (uint32_t)cpu_host_hal_glfw_wave_headers[i].dwBufferLength;",
                "            }",
                "        }",
                "        return queued;",
                "    }",
                "#endif",
                "    if (cpu_host_hal_glfw_sdl_audio_dev != 0u) {",
                "        SDL_ClearQueuedAudio(cpu_host_hal_glfw_sdl_audio_dev);",
                "        return;",
                "    }",
                "#ifdef __linux__",
                "    if (cpu_host_hal_glfw_alsa_pcm != NULL) {",
                "        pthread_mutex_lock(&cpu_host_hal_glfw_audio_mutex);",
                "        queued = cpu_host_hal_glfw_audio_len;",
                "        pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "        snd_pcm_sframes_t delay = 0;",
                "        if (snd_pcm_delay(cpu_host_hal_glfw_alsa_pcm, &delay) >= 0 && delay > 0) {",
                "            queued += (uint32_t)delay;",
                "            queued *= (uint32_t)(cpu_host_hal_glfw_alsa_channels ? cpu_host_hal_glfw_alsa_channels : 1u);",
                "            queued *= 2u;",
                "        }",
                "        return queued;",
                "    }",
                "#endif",
                "    return cpu_host_hal_glfw_audio_len;",
                "}",
                "",
                "static void cpu_host_hal_audio_clear(uint32_t dev) {",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "    if (dev == 0u || cpu_host_hal_glfw_audio_opened == 0u) return;",
                "#ifdef __linux__",
                "    if (cpu_host_hal_glfw_sdl_audio_dev != 0u) {",
                "        SDL_ClearQueuedAudio(cpu_host_hal_glfw_sdl_audio_dev);",
                "        return;",
                "    }",
                "#endif",
                "#ifdef _WIN32",
                "    if (cpu_host_hal_glfw_waveout != NULL) {",
                "        uint32_t i;",
                "        waveOutReset(cpu_host_hal_glfw_waveout);",
                "        for (i = 0u; i < 4u; ++i) {",
                "            if ((cpu_host_hal_glfw_wave_headers[i].dwFlags & WHDR_PREPARED) != 0u) {",
                "                waveOutUnprepareHeader(cpu_host_hal_glfw_waveout, &cpu_host_hal_glfw_wave_headers[i], sizeof(cpu_host_hal_glfw_wave_headers[i]));",
                "                cpu_host_hal_glfw_wave_headers[i].dwFlags = 0u;",
                "            }",
                "        }",
                "        cpu_host_hal_glfw_wave_next = 0u;",
                "        return;",
                "    }",
                "#endif",
                "#ifdef __linux__",
                "    if (cpu_host_hal_glfw_alsa_pcm != NULL) {",
                "        pthread_mutex_lock(&cpu_host_hal_glfw_audio_mutex);",
                "        cpu_host_hal_glfw_audio_len = 0u;",
                "        pthread_cond_signal(&cpu_host_hal_glfw_audio_cond);",
                "        pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "        snd_pcm_drop(cpu_host_hal_glfw_alsa_pcm);",
                "        snd_pcm_prepare(cpu_host_hal_glfw_alsa_pcm);",
                "        return;",
                "    }",
                "#endif",
                "    cpu_host_hal_glfw_audio_len = 0u;",
                "}",
                "",
                "static int cpu_host_hal_renderer_output_size(void *renderer, int *out_w, int *out_h) {",

                "    if (out_w) *out_w = 0;",
                "    if (out_h) *out_h = 0;",
                "    if (cpu_host_hal_sdl_inited == 0u) return -1;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!renderer || !out_w || !out_h) return -1;",
                "    if (SDL_GetRendererOutputSize((SDL_Renderer *)renderer, out_w, out_h) != 0) return -1;",
                "    if (*out_w <= 0 || *out_h <= 0) return -1;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_update_texture(void *texture, const CPUHostRect *rect, const void *pixels, int pitch) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return -1;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!texture || !pixels) return -1;",
                "    return SDL_UpdateTexture((SDL_Texture *)texture, (const SDL_Rect *)rect, pixels, pitch);",
                "}",
                "",
                "static void cpu_host_hal_render_set_draw_color(void *renderer, uint8_t r, uint8_t g, uint8_t b, uint8_t a) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!renderer) return;",
                "    SDL_SetRenderDrawColor((SDL_Renderer *)renderer, r, g, b, a);",
                "}",
                "",
                "static int cpu_host_hal_render_clear(void *renderer) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return -1;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!renderer) return -1;",
                "    return SDL_RenderClear((SDL_Renderer *)renderer);",
                "}",
                "",
                "static int cpu_host_hal_render_copy(void *renderer, void *texture, const CPUHostRect *src_rect, const CPUHostRect *dst_rect) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return -1;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!renderer || !texture) return -1;",
                "    return SDL_RenderCopy(",
                "        (SDL_Renderer *)renderer,",
                "        (SDL_Texture *)texture,",
                "        (const SDL_Rect *)src_rect,",
                "        (const SDL_Rect *)dst_rect",
                "    );",
                "}",
                "",
                "static int cpu_host_hal_renderer_supports_shaders(void *renderer) {",
                "    (void)renderer;",
                "    return 0;",
                "}",
                "",
                "static void *cpu_host_hal_shader_create(void *renderer, const char *vertex_source, const char *fragment_source) {",
                "    (void)renderer;",
                "    (void)vertex_source;",
                "    (void)fragment_source;",
                "    return NULL;",
                "}",
                "",
                "static void cpu_host_hal_shader_destroy(void *shader) {",
                "    (void)shader;",
                "}",
                "",
                "static int cpu_host_hal_render_copy_shader(void *renderer, void *texture, const CPUHostRect *src_rect, const CPUHostRect *dst_rect, void *shader, int texture_w, int texture_h, int output_w, int output_h) {",
                "    (void)texture_w;",
                "    (void)texture_h;",
                "    (void)output_w;",
                "    (void)output_h;",
                "    if (shader == NULL) return -1;",
                "    return cpu_host_hal_render_copy(renderer, texture, src_rect, dst_rect);",
                "}",
                "",
                "static int cpu_host_hal_poll_event(CPUHostEvent *event) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return 0;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0;",
                "    if (!event) return 0;",
                "    return SDL_PollEvent((SDL_Event *)event);",
                "}",
                "",
                "static uint32_t cpu_host_hal_event_type(const CPUHostEvent *event) {",
                "    if (!event) return 0u;",
                "    return event->type;",
                "}",
                "",
                "static int32_t cpu_host_hal_event_scancode(const CPUHostEvent *event) {",
                "    if (!event) return 0;",
                "    if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0;",
                "    return (int32_t)event->key.keysym.scancode;",
                "}",
                "",
                "static int32_t cpu_host_hal_event_keycode(const CPUHostEvent *event) {",
                "    if (!event) return 0;",
                "    if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0;",
                "    return (int32_t)event->key.keysym.sym;",
                "}",
                "",
                "static uint8_t cpu_host_hal_event_key_repeat(const CPUHostEvent *event) {",
                "    if (!event) return 0u;",
                "    if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0u;",
                "    return (uint8_t)event->key.repeat;",
                "}",
                "",
                "static uint32_t cpu_host_hal_event_mod_state(const CPUHostEvent *event) {",
                "    if (!event) return 0u;",
                "    if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0u;",
                "    return (uint32_t)event->key.keysym.mod;",
                "}",
                "",
                "static void cpu_host_hal_set_window_title(void *window, const char *title) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!window) window = (void *)cpu_host_hal_sdl_primary_window;",
                "    if (!window || !title) return;",
                "    SDL_SetWindowTitle((SDL_Window *)window, title);",
                "}",
                "",
                "static void cpu_host_hal_destroy_texture(void *texture) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!texture) return;",
                "    SDL_DestroyTexture((SDL_Texture *)texture);",
                "}",
                "",
                "static void cpu_host_hal_destroy_renderer(void *renderer) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!renderer) return;",
                "    SDL_DestroyRenderer((SDL_Renderer *)renderer);",
                "}",
                "",
                "static void cpu_host_hal_destroy_window(void *window) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!window) return;",
                "    if (cpu_host_hal_sdl_primary_window == (SDL_Window *)window) {",
                "        cpu_host_hal_sdl_primary_window = NULL;",
                "    }",
                "    SDL_DestroyWindow((SDL_Window *)window);",
                "}",
                "",
                "static void cpu_host_hal_audio_close(uint32_t dev) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "    if (dev == 0u) return;",
                "    SDL_CloseAudioDevice(dev);",
                "}",
                "",
                "static void cpu_host_hal_quit_subsystems(void) {",
                "    uint32_t to_quit = cpu_host_hal_sdl_subsystems & (CPU_HOST_INIT_VIDEO | CPU_HOST_INIT_AUDIO | CPU_HOST_INIT_EVENTS);",
                "    if (to_quit != 0u) SDL_QuitSubSystem(to_quit);",
                "    cpu_host_hal_sdl_subsystems &= ~to_quit;",
                "    cpu_host_hal_sdl_primary_window = NULL;",
                "}",
                "",
                "static void cpu_host_hal_quit(void) {",
                "    SDL_Quit();",
                "    cpu_host_hal_sdl_subsystems = 0u;",
                "    cpu_host_hal_sdl_inited = 0u;",
                "    cpu_host_hal_sdl_primary_window = NULL;",
                "}",
                "",
                "static int cpu_host_hal_init(uint32_t flags) {",
                "    if ((flags & ~(CPU_HOST_INIT_VIDEO | CPU_HOST_INIT_AUDIO | CPU_HOST_INIT_EVENTS)) != 0u) return -1;",
                "    if (cpu_host_hal_sdl_inited == 0u) {",
                "        if (SDL_Init(flags) != 0) return -1;",
                "        cpu_host_hal_sdl_inited = 1u;",
                "        cpu_host_hal_sdl_subsystems |= flags;",
                "        return 0;",
                "    }",
                "    if (flags != 0u) {",
                "        if (SDL_InitSubSystem(flags) != 0) return -1;",
                "        cpu_host_hal_sdl_subsystems |= flags;",
                "    }",
                "    return 0;",
                "}",
                "",
                "static uint32_t cpu_host_hal_isqrt_u32(uint32_t value) {",
                "    uint32_t result = 0u;",
                "    uint32_t bit = 1u << 30;",
                "    while (bit > value) bit >>= 2;",
                "    while (bit != 0u) {",
                "        if (value >= result + bit) {",
                "            value -= result + bit;",
                "            result = (result >> 1) + bit;",
                "        } else {",
                "            result >>= 1;",
                "        }",
                "        bit >>= 2;",
                "    }",
                "    return result;",
                "}",
                "",
                "static void cpu_host_hal_display_window_size(uint32_t display_w, uint32_t display_h, uint32_t aspect_w, uint32_t aspect_h, uint32_t inches, int fallback_w, int fallback_h, int *out_w, int *out_h) {",
                "    uint64_t diag;",
                "    uint64_t target_w;",
                "    uint64_t target_h;",
                "    uint64_t max_w;",
                "    uint64_t max_h;",
                "    if (aspect_w == 0u || aspect_h == 0u) { aspect_w = (fallback_w > 0) ? (uint32_t)fallback_w : 4u; aspect_h = (fallback_h > 0) ? (uint32_t)fallback_h : 3u; }",
                "    if (display_w == 0u) display_w = (fallback_w > 0) ? (uint32_t)fallback_w : 640u;",
                "    if (display_h == 0u) display_h = (fallback_h > 0) ? (uint32_t)fallback_h : 480u;",
                "    max_w = display_w;",
                "    max_h = ((uint64_t)display_w * (uint64_t)aspect_h) / (uint64_t)aspect_w;",
                "    if (max_h == 0u || max_h > display_h) {",
                "        max_h = display_h;",
                "        max_w = ((uint64_t)display_h * (uint64_t)aspect_w) / (uint64_t)aspect_h;",
                "    }",
                "    if (max_w == 0u) max_w = display_w;",
                "    if (max_h == 0u) max_h = display_h;",
                "    diag = (uint64_t)cpu_host_hal_isqrt_u32((uint32_t)(aspect_w * aspect_w + aspect_h * aspect_h));",
                "    if (diag == 0u) diag = 5u;",
                "    if (inches == 0u) inches = 14u;",
                "    target_w = ((uint64_t)inches * 48u * (uint64_t)aspect_w) / diag;",
                "    target_h = ((uint64_t)inches * 48u * (uint64_t)aspect_h) / diag;",
                "    if (target_w == 0u || target_h == 0u) { target_w = max_w; target_h = max_h; }",
                "    if (target_w > max_w) { target_w = max_w; target_h = (target_w * (uint64_t)aspect_h) / (uint64_t)aspect_w; }",
                "    if (target_h > max_h) { target_h = max_h; target_w = (target_h * (uint64_t)aspect_w) / (uint64_t)aspect_h; }",
                "    if (target_w < 160u) { target_w = 160u; target_h = (target_w * (uint64_t)aspect_h) / (uint64_t)aspect_w; }",
                "    if (target_h < 120u) { target_h = 120u; target_w = (target_h * (uint64_t)aspect_w) / (uint64_t)aspect_h; }",
                "    if (out_w) *out_w = (int)((target_w > 0u) ? target_w : 640u);",
                "    if (out_h) *out_h = (int)((target_h > 0u) ? target_h : 480u);",
                "}",
                "",
                "static void *cpu_host_hal_create_window(const char *title, int x, int y, int w, int h, uint32_t flags) {",
                "    SDL_Window *window;",
                "    const char *win_title = (title && title[0] != '\\0') ? title : \"PASM\";",
                "    if (cpu_host_hal_sdl_inited == 0u) return NULL;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return NULL;",
                "    if ((flags & ~CPU_HOST_WINDOW_RESIZABLE) != 0u) return NULL;",
                "    if (w <= 0) w = 640;",
                "    if (h <= 0) h = 480;",
                "    window = SDL_CreateWindow(win_title, x, y, w, h, flags);",
                "    if (window != NULL && cpu_host_hal_sdl_primary_window == NULL) {",
                "        cpu_host_hal_sdl_primary_window = window;",
                "    }",
                "    return (void *)window;",
                "}",
                "",
                "static void *cpu_host_hal_create_renderer(void *window, int index, uint32_t flags) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return NULL;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return NULL;",
                "    if (!window) window = (void *)cpu_host_hal_sdl_primary_window;",
                "    if (!window) return NULL;",
                "    if ((flags & ~CPU_HOST_RENDERER_ACCELERATED) != 0u) return NULL;",
                "    return (void *)SDL_CreateRenderer((SDL_Window *)window, index, flags);",
                "}",
                "",
                "static void *cpu_host_hal_create_texture(void *renderer, uint32_t format, int access, int w, int h) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return NULL;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return NULL;",
                "    if (!renderer) return NULL;",
                "    return (void *)SDL_CreateTexture((SDL_Renderer *)renderer, format, access, w, h);",
                "}",
                "",
                "static uint32_t cpu_host_hal_audio_open(const char *device, int iscapture, const CPUHostAudioSpec *want, CPUHostAudioSpec *have, int allowed_changes) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    if (!want) return 0u;",
                "    if (want->freq <= 0 || want->channels == 0u || want->samples == 0u) return 0u;",
                "#ifdef __linux__",
                "    cpu_host_hal_glfw_alsa_stderr_redirect();",
                "    snd_lib_error_set_handler(cpu_host_hal_glfw_alsa_error_handler);",
                "#endif",
                "    return SDL_OpenAudioDevice(",
                "        device,",
                "        iscapture,",
                "        (const SDL_AudioSpec *)want,",
                "        (SDL_AudioSpec *)have,",
                "        allowed_changes",
                "    );",
                "}",
                "",
                "static void cpu_host_hal_audio_pause(uint32_t dev, int pause_on) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "    if (dev == 0u) return;",
                "    SDL_PauseAudioDevice(dev, pause_on);",
                "}",
                "",
                "static void *cpu_host_hal_alloc(size_t size_bytes) {",
                "    return SDL_malloc(size_bytes);",
                "}",
                "",
                "static void cpu_host_hal_free(void *ptr) {",
                "    if (!ptr) return;",
                "    SDL_free(ptr);",
                "}",
                "",
                "static void cpu_host_hal_memset(void *dst, int value, size_t size_bytes) {",
                "    if (!dst || size_bytes == 0u) return;",
                "    SDL_memset(dst, value, size_bytes);",
                "}",
                "",
                "static const char *cpu_host_hal_getenv(const char *name) {",
                "    if (!name) return NULL;",
                "    return SDL_getenv(name);",
                "}",
                "",
                "static const uint8_t *cpu_host_hal_keyboard_state(int *key_count) {",
                "    static const uint8_t empty_state[1] = {0u};",
                "    const uint8_t *state;",
                "    if (cpu_host_hal_sdl_inited == 0u) {",
                "        if (key_count) *key_count = 0;",
                "        return empty_state;",
                "    }",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) {",
                "        if (key_count) *key_count = 0;",
                "        return empty_state;",
                "    }",
                "    state = SDL_GetKeyboardState(key_count);",
                "    if (!state) {",
                "        if (key_count) *key_count = 0;",
                "        return empty_state;",
                "    }",
                "    return state;",
                "}",
                "",
                "static int32_t cpu_host_hal_key_from_scancode(int scancode) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return 0;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0;",
                "    return (int32_t)SDL_GetKeyFromScancode((SDL_Scancode)scancode);",
                "}",
                "",
                "static int32_t cpu_host_hal_scancode_from_key(int32_t keycode) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return -1;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return -1;",
                "    return (int32_t)SDL_GetScancodeFromKey((SDL_Keycode)keycode);",
                "}",
                "",
                "static void cpu_host_hal_start_text_input(void) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return;",
                "    SDL_StartTextInput();",
                "}",
                "",
                "static void cpu_host_hal_stop_text_input(void) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return;",
                "    SDL_StopTextInput();",
                "}",
                "",
                "static void cpu_host_hal_raise_window(void *window) {",
                "    (void)window;",
                "    /* Do not steal focus implicitly. */",
                "}",
                "",
                "static void cpu_host_hal_show_window(void *window) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!window) window = (void *)cpu_host_hal_sdl_primary_window;",
                "    if (!window) return;",
                "    SDL_ShowWindow((SDL_Window *)window);",
                "}",
                "",
                "static int cpu_host_hal_set_window_input_focus(void *window) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return -1;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!window) window = (void *)cpu_host_hal_sdl_primary_window;",
                "    if (!window) return -1;",
                "    return SDL_SetWindowInputFocus((SDL_Window *)window);",
                "}",
                "",
                "static int cpu_host_hal_set_texture_blend_none(void *texture) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return -1;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!texture) return -1;",
                "    return SDL_SetTextureBlendMode((SDL_Texture *)texture, SDL_BLENDMODE_NONE);",
                "}",
                "",
                "static int cpu_host_hal_init_subsystem(uint32_t flags) {",
                "    if ((flags & ~(CPU_HOST_INIT_VIDEO | CPU_HOST_INIT_AUDIO | CPU_HOST_INIT_EVENTS)) != 0u) return -1;",
                "    if (cpu_host_hal_sdl_inited == 0u) return -1;",
                "    if (flags != 0u && SDL_InitSubSystem(flags) != 0) return -1;",
                "    cpu_host_hal_sdl_subsystems |= flags;",
                "    return 0;",
                "}",
                "",
                "static uint32_t cpu_host_hal_audio_dequeue(uint32_t dev, void *data, uint32_t len_bytes) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    if (dev == 0u || !data || len_bytes == 0u) return 0u;",
                "    return SDL_DequeueAudio(dev, data, len_bytes);",
                "}",
                "",
                "static int cpu_host_hal_get_window_size(void *window, int *out_w, int *out_h) {",
                "    if (out_w) *out_w = 0;",
                "    if (out_h) *out_h = 0;",
                "    if (cpu_host_hal_sdl_inited == 0u) return -1;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!window) window = (void *)cpu_host_hal_sdl_primary_window;",
                "    if (!window || !out_w || !out_h) return -1;",
                "    SDL_GetWindowSize((SDL_Window *)window, out_w, out_h);",
                "    if (*out_w <= 0 || *out_h <= 0) return -1;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_set_window_size(void *window, int w, int h) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return -1;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!window) window = (void *)cpu_host_hal_sdl_primary_window;",
                "    if (!window) return -1;",
                "    if (w <= 0 || h <= 0) return -1;",
                "    SDL_SetWindowSize((SDL_Window *)window, w, h);",
                "    return 0;",
                "}",
                "",
                "static const char *cpu_host_hal_scancode_name(int32_t scancode) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return \"UNKNOWN\";",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return \"UNKNOWN\";",
                "    const char *name = SDL_GetScancodeName((SDL_Scancode)scancode);",
                "    if (!name || name[0] == '\\0') return \"UNKNOWN\";",
                "    return name;",
                "}",
                "",
                "static uint32_t cpu_host_hal_get_mod_state(void) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0u;",
                "    return (uint32_t)SDL_GetModState();",
                "}",
                "",
                "static const char *cpu_host_hal_key_name(int32_t keycode) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return \"UNKNOWN\";",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return \"UNKNOWN\";",
                "    const char *name = SDL_GetKeyName((SDL_Keycode)keycode);",
                "    if (!name || name[0] == '\\0') return \"UNKNOWN\";",
                "    return name;",
                "}",
                "",
            ]
        )
        helper_lines.append("/* PASM_SPLIT_END:HOST_HAL_IMPL */")
    elif host_uses_glfw_backend:
        helper_lines.append("/* PASM_SPLIT_BEGIN:HOST_HAL_IMPL */")
        helper_lines.extend(
            [
                "static GLFWwindow *cpu_host_hal_glfw_primary_window = NULL;",
                "static uint8_t cpu_host_hal_glfw_quit_emitted = 0u;",
                "static uint8_t cpu_host_hal_glfw_prev_keys[CPU_GLFW_SC_COUNT];",
                "static uint8_t cpu_host_hal_glfw_keys[CPU_GLFW_SC_COUNT];",
                "static uint16_t cpu_host_hal_glfw_hold_ticks[CPU_GLFW_SC_COUNT];",
                "static uint32_t cpu_host_hal_glfw_event_mod_state = 0u;",
                "static int cpu_host_hal_glfw_poll_cursor = 0;",
                "static uint8_t *cpu_host_hal_glfw_audio_buf = NULL;",
                "static uint32_t cpu_host_hal_glfw_audio_len = 0u;",
                "static uint32_t cpu_host_hal_glfw_audio_cap = 0u;",
                "static uint8_t cpu_host_hal_glfw_audio_opened = 0u;",
                "static uint32_t cpu_host_hal_glfw_sdl_audio_dev = 0u;",
                "static uint8_t cpu_host_hal_glfw_sdl_inited = 0u;",
                "#ifdef _WIN32",
                "#include <windows.h>",
                "#include <mmsystem.h>",
                "static HWAVEOUT cpu_host_hal_glfw_waveout = NULL;",
                "static WAVEHDR cpu_host_hal_glfw_wave_headers[4];",
                "static uint8_t *cpu_host_hal_glfw_wave_buffers[4];",
                "static uint32_t cpu_host_hal_glfw_wave_buffer_bytes = 0u;",
                "static uint32_t cpu_host_hal_glfw_wave_next = 0u;",
                "#endif",
                "#ifdef __linux__",
                "#include <alsa/asoundlib.h>",
                "#include <pthread.h>",
                "#include <unistd.h>",
                "static snd_pcm_t *cpu_host_hal_glfw_alsa_pcm = NULL;",
                "static uint32_t cpu_host_hal_glfw_alsa_channels = 0u;",
                "static pthread_t cpu_host_hal_glfw_audio_thread;",
                "static pthread_mutex_t cpu_host_hal_glfw_audio_mutex = PTHREAD_MUTEX_INITIALIZER;",
                "static pthread_cond_t cpu_host_hal_glfw_audio_cond = PTHREAD_COND_INITIALIZER;",
                "static uint8_t cpu_host_hal_glfw_audio_thread_started = 0u;",
                "static uint8_t cpu_host_hal_glfw_audio_thread_stop_flag = 0u;",
                "#endif",
                "static uint8_t cpu_host_hal_glfw_inited = 0u;",
                "static uint32_t cpu_host_hal_glfw_subsystems = 0u;",
                "static uint8_t cpu_host_hal_glfw_gl_loaded = 0u;",
                "static GLuint (*cpu_glCreateShader)(GLenum type) = NULL;",
                "static void (*cpu_glShaderSource)(GLuint shader, GLsizei count, const GLchar * const *string, const GLint *length) = NULL;",
                "static void (*cpu_glCompileShader)(GLuint shader) = NULL;",
                "static void (*cpu_glGetShaderiv)(GLuint shader, GLenum pname, GLint *params) = NULL;",
                "static GLuint (*cpu_glCreateProgram)(void) = NULL;",
                "static void (*cpu_glAttachShader)(GLuint program, GLuint shader) = NULL;",
                "static void (*cpu_glLinkProgram)(GLuint program) = NULL;",
                "static void (*cpu_glGetProgramiv)(GLuint program, GLenum pname, GLint *params) = NULL;",
                "static void (*cpu_glDeleteShader)(GLuint shader) = NULL;",
                "static void (*cpu_glDeleteProgram)(GLuint program) = NULL;",
                "static void (*cpu_glUseProgram)(GLuint program) = NULL;",
                "static void (*cpu_glGenVertexArrays)(GLsizei n, GLuint *arrays) = NULL;",
                "static void (*cpu_glBindVertexArray)(GLuint array) = NULL;",
                "static void (*cpu_glDeleteVertexArrays)(GLsizei n, const GLuint *arrays) = NULL;",
                "static void (*cpu_glGenBuffers)(GLsizei n, GLuint *buffers) = NULL;",
                "static void (*cpu_glBindBuffer)(GLenum target, GLuint buffer) = NULL;",
                "static void (*cpu_glBufferData)(GLenum target, GLsizeiptr size, const void *data, GLenum usage) = NULL;",
                "static void (*cpu_glDeleteBuffers)(GLsizei n, const GLuint *buffers) = NULL;",
                "static void (*cpu_glEnableVertexAttribArray)(GLuint index) = NULL;",
                "static void (*cpu_glVertexAttribPointer)(GLuint index, GLint size, GLenum type, GLboolean normalized, GLsizei stride, const void *pointer) = NULL;",
                "static void (*cpu_glGenTextures)(GLsizei n, GLuint *textures) = NULL;",
                "static void (*cpu_glBindTexture)(GLenum target, GLuint texture) = NULL;",
                "static void (*cpu_glTexParameteri)(GLenum target, GLenum pname, GLint param) = NULL;",
                "static void (*cpu_glTexImage2D)(GLenum target, GLint level, GLint internalformat, GLsizei width, GLsizei height, GLint border, GLenum format, GLenum type, const void *pixels) = NULL;",
                "static void (*cpu_glTexSubImage2D)(GLenum target, GLint level, GLint xoffset, GLint yoffset, GLsizei width, GLsizei height, GLenum format, GLenum type, const void *pixels) = NULL;",
                "static void (*cpu_glDeleteTextures)(GLsizei n, const GLuint *textures) = NULL;",
                "static void (*cpu_glActiveTexture)(GLenum texture) = NULL;",
                "static GLint (*cpu_glGetUniformLocation)(GLuint program, const GLchar *name) = NULL;",
                "static void (*cpu_glUniform1i)(GLint location, GLint v0) = NULL;",
                "static void (*cpu_glUniform2f)(GLint location, GLfloat v0, GLfloat v1) = NULL;",
                "static void (*cpu_glUniformMatrix4fv)(GLint location, GLsizei count, GLboolean transpose, const GLfloat *value) = NULL;",
                "static void (*cpu_glViewport)(GLint x, GLint y, GLsizei width, GLsizei height) = NULL;",
                "static void (*cpu_glClearColor)(GLfloat red, GLfloat green, GLfloat blue, GLfloat alpha) = NULL;",
                "static void (*cpu_glClear)(GLenum mask) = NULL;",
                "static void (*cpu_glDrawArrays)(GLenum mode, GLint first, GLsizei count) = NULL;",
                "",
                "static int cpu_host_hal_glfw_load_gl(void) {",
                "    if (cpu_host_hal_glfw_gl_loaded != 0u) return 0;",
                "    cpu_glCreateShader = (GLuint (*)(GLenum))glfwGetProcAddress(\"glCreateShader\");",
                "    if (cpu_glCreateShader == NULL) return -1;",
                "    cpu_glShaderSource = (void (*)(GLuint, GLsizei, const GLchar * const *, const GLint *))glfwGetProcAddress(\"glShaderSource\");",
                "    if (cpu_glShaderSource == NULL) return -1;",
                "    cpu_glCompileShader = (void (*)(GLuint))glfwGetProcAddress(\"glCompileShader\");",
                "    if (cpu_glCompileShader == NULL) return -1;",
                "    cpu_glGetShaderiv = (void (*)(GLuint, GLenum, GLint *))glfwGetProcAddress(\"glGetShaderiv\");",
                "    if (cpu_glGetShaderiv == NULL) return -1;",
                "    cpu_glCreateProgram = (GLuint (*)(void))glfwGetProcAddress(\"glCreateProgram\");",
                "    if (cpu_glCreateProgram == NULL) return -1;",
                "    cpu_glAttachShader = (void (*)(GLuint, GLuint))glfwGetProcAddress(\"glAttachShader\");",
                "    if (cpu_glAttachShader == NULL) return -1;",
                "    cpu_glLinkProgram = (void (*)(GLuint))glfwGetProcAddress(\"glLinkProgram\");",
                "    if (cpu_glLinkProgram == NULL) return -1;",
                "    cpu_glGetProgramiv = (void (*)(GLuint, GLenum, GLint *))glfwGetProcAddress(\"glGetProgramiv\");",
                "    if (cpu_glGetProgramiv == NULL) return -1;",
                "    cpu_glDeleteShader = (void (*)(GLuint))glfwGetProcAddress(\"glDeleteShader\");",
                "    if (cpu_glDeleteShader == NULL) return -1;",
                "    cpu_glDeleteProgram = (void (*)(GLuint))glfwGetProcAddress(\"glDeleteProgram\");",
                "    if (cpu_glDeleteProgram == NULL) return -1;",
                "    cpu_glUseProgram = (void (*)(GLuint))glfwGetProcAddress(\"glUseProgram\");",
                "    if (cpu_glUseProgram == NULL) return -1;",
                "    cpu_glGenVertexArrays = (void (*)(GLsizei, GLuint *))glfwGetProcAddress(\"glGenVertexArrays\");",
                "    cpu_glBindVertexArray = (void (*)(GLuint))glfwGetProcAddress(\"glBindVertexArray\");",
                "    cpu_glDeleteVertexArrays = (void (*)(GLsizei, const GLuint *))glfwGetProcAddress(\"glDeleteVertexArrays\");",
                "    cpu_glGenBuffers = (void (*)(GLsizei, GLuint *))glfwGetProcAddress(\"glGenBuffers\");",
                "    if (cpu_glGenBuffers == NULL) return -1;",
                "    cpu_glBindBuffer = (void (*)(GLenum, GLuint))glfwGetProcAddress(\"glBindBuffer\");",
                "    if (cpu_glBindBuffer == NULL) return -1;",
                "    cpu_glBufferData = (void (*)(GLenum, GLsizeiptr, const void *, GLenum))glfwGetProcAddress(\"glBufferData\");",
                "    if (cpu_glBufferData == NULL) return -1;",
                "    cpu_glDeleteBuffers = (void (*)(GLsizei, const GLuint *))glfwGetProcAddress(\"glDeleteBuffers\");",
                "    if (cpu_glDeleteBuffers == NULL) return -1;",
                "    cpu_glEnableVertexAttribArray = (void (*)(GLuint))glfwGetProcAddress(\"glEnableVertexAttribArray\");",
                "    if (cpu_glEnableVertexAttribArray == NULL) return -1;",
                "    cpu_glVertexAttribPointer = (void (*)(GLuint, GLint, GLenum, GLboolean, GLsizei, const void *))glfwGetProcAddress(\"glVertexAttribPointer\");",
                "    if (cpu_glVertexAttribPointer == NULL) return -1;",
                "    cpu_glGenTextures = (void (*)(GLsizei, GLuint *))glfwGetProcAddress(\"glGenTextures\");",
                "    if (cpu_glGenTextures == NULL) return -1;",
                "    cpu_glBindTexture = (void (*)(GLenum, GLuint))glfwGetProcAddress(\"glBindTexture\");",
                "    if (cpu_glBindTexture == NULL) return -1;",
                "    cpu_glTexParameteri = (void (*)(GLenum, GLenum, GLint))glfwGetProcAddress(\"glTexParameteri\");",
                "    if (cpu_glTexParameteri == NULL) return -1;",
                "    cpu_glTexImage2D = (void (*)(GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void *))glfwGetProcAddress(\"glTexImage2D\");",
                "    if (cpu_glTexImage2D == NULL) return -1;",
                "    cpu_glTexSubImage2D = (void (*)(GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void *))glfwGetProcAddress(\"glTexSubImage2D\");",
                "    if (cpu_glTexSubImage2D == NULL) return -1;",
                "    cpu_glDeleteTextures = (void (*)(GLsizei, const GLuint *))glfwGetProcAddress(\"glDeleteTextures\");",
                "    if (cpu_glDeleteTextures == NULL) return -1;",
                "    cpu_glActiveTexture = (void (*)(GLenum))glfwGetProcAddress(\"glActiveTexture\");",
                "    if (cpu_glActiveTexture == NULL) return -1;",
                "    cpu_glGetUniformLocation = (GLint (*)(GLuint, const GLchar *))glfwGetProcAddress(\"glGetUniformLocation\");",
                "    if (cpu_glGetUniformLocation == NULL) return -1;",
                "    cpu_glUniform1i = (void (*)(GLint, GLint))glfwGetProcAddress(\"glUniform1i\");",
                "    if (cpu_glUniform1i == NULL) return -1;",
                "    cpu_glUniform2f = (void (*)(GLint, GLfloat, GLfloat))glfwGetProcAddress(\"glUniform2f\");",
                "    if (cpu_glUniform2f == NULL) return -1;",
                "    cpu_glUniformMatrix4fv = (void (*)(GLint, GLsizei, GLboolean, const GLfloat *))glfwGetProcAddress(\"glUniformMatrix4fv\");",
                "    if (cpu_glUniformMatrix4fv == NULL) return -1;",
                "    cpu_glViewport = (void (*)(GLint, GLint, GLsizei, GLsizei))glfwGetProcAddress(\"glViewport\");",
                "    if (cpu_glViewport == NULL) return -1;",
                "    cpu_glClearColor = (void (*)(GLfloat, GLfloat, GLfloat, GLfloat))glfwGetProcAddress(\"glClearColor\");",
                "    if (cpu_glClearColor == NULL) return -1;",
                "    cpu_glClear = (void (*)(GLenum))glfwGetProcAddress(\"glClear\");",
                "    if (cpu_glClear == NULL) return -1;",
                "    cpu_glDrawArrays = (void (*)(GLenum, GLint, GLsizei))glfwGetProcAddress(\"glDrawArrays\");",
                "    if (cpu_glDrawArrays == NULL) return -1;",
                "    cpu_host_hal_glfw_gl_loaded = 1u;",
                "    return 0;",
                "}",
                "",
                "static void cpu_host_hal_shader_destroy(void *shader);",
                "",
                "#ifdef __linux__",
                "static void *cpu_host_hal_glfw_audio_thread_main(void *arg) {",
                "    uint8_t chunk[16384];",
                "    (void)arg;",
                "    for (;;) {",
                "        size_t copy_bytes = 0u;",
                "        uint32_t frame_bytes = 0u;",
                "        pthread_mutex_lock(&cpu_host_hal_glfw_audio_mutex);",
                "        while (cpu_host_hal_glfw_audio_thread_stop_flag == 0u && (cpu_host_hal_glfw_alsa_pcm == NULL || cpu_host_hal_glfw_alsa_channels == 0u || cpu_host_hal_glfw_audio_len == 0u)) {",
                "            pthread_cond_wait(&cpu_host_hal_glfw_audio_cond, &cpu_host_hal_glfw_audio_mutex);",
                "        }",
                "        if (cpu_host_hal_glfw_audio_thread_stop_flag != 0u) {",
                "            pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "            break;",
                "        }",
                "        if (cpu_host_hal_glfw_alsa_pcm == NULL || cpu_host_hal_glfw_alsa_channels == 0u || cpu_host_hal_glfw_audio_buf == NULL) {",
                "            pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "            continue;",
                "        }",
                "        frame_bytes = cpu_host_hal_glfw_alsa_channels * 2u;",
                "        if (frame_bytes == 0u) {",
                "            pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "            continue;",
                "        }",
                "        copy_bytes = cpu_host_hal_glfw_audio_len;",
                "        if (copy_bytes > sizeof(chunk)) copy_bytes = sizeof(chunk);",
                "        copy_bytes -= (copy_bytes % (size_t)frame_bytes);",
                "        if (copy_bytes == 0u) {",
                "            pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "            continue;",
                "        }",
                "        memcpy(chunk, cpu_host_hal_glfw_audio_buf, copy_bytes);",
                "        memmove(cpu_host_hal_glfw_audio_buf, cpu_host_hal_glfw_audio_buf + copy_bytes, (size_t)(cpu_host_hal_glfw_audio_len - (uint32_t)copy_bytes));",
                "        cpu_host_hal_glfw_audio_len -= (uint32_t)copy_bytes;",
                "        pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "        {",
                "            const uint8_t *ptr = chunk;",
                "            snd_pcm_sframes_t frames = (snd_pcm_sframes_t)(copy_bytes / (size_t)frame_bytes);",
                "            while (frames > 0) {",
                "                snd_pcm_sframes_t n = snd_pcm_writei(cpu_host_hal_glfw_alsa_pcm, ptr, (snd_pcm_uframes_t)frames);",
                "                if (n == -EPIPE) {",
                "                    snd_pcm_prepare(cpu_host_hal_glfw_alsa_pcm);",
                "                    continue;",
                "                }",
                "                if (n == -EAGAIN || n == -ESTRPIPE) {",
                "                    snd_pcm_wait(cpu_host_hal_glfw_alsa_pcm, 10);",
                "                    continue;",
                "                }",
                "                if (n < 0 || n == 0) {",
                "                    break;",
                "                }",
                "                ptr += (size_t)n * (size_t)frame_bytes;",
                "                frames -= n;",
                "            }",
                "        }",
                "    }",
                "    return NULL;",
                "}",
                "",
                "static int cpu_host_hal_glfw_audio_thread_start(void) {",
                "    if (cpu_host_hal_glfw_audio_thread_started != 0u) return 0;",
                "    cpu_host_hal_glfw_audio_thread_stop_flag = 0u;",
                "    if (pthread_create(&cpu_host_hal_glfw_audio_thread, NULL, cpu_host_hal_glfw_audio_thread_main, NULL) != 0) {",
                "        cpu_host_hal_glfw_audio_thread_stop_flag = 0u;",
                "        return -1;",
                "    }",
                "    cpu_host_hal_glfw_audio_thread_started = 1u;",
                "    return 0;",
                "}",
                "",
                "static void cpu_host_hal_glfw_audio_thread_stop(void) {",
                "    if (cpu_host_hal_glfw_audio_thread_started == 0u) {",
                "        cpu_host_hal_glfw_audio_thread_stop_flag = 0u;",
                "        return;",
                "    }",
                "    pthread_mutex_lock(&cpu_host_hal_glfw_audio_mutex);",
                "    cpu_host_hal_glfw_audio_thread_stop_flag = 1u;",
                "    pthread_cond_broadcast(&cpu_host_hal_glfw_audio_cond);",
                "    pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "    pthread_join(cpu_host_hal_glfw_audio_thread, NULL);",
                "    cpu_host_hal_glfw_audio_thread_started = 0u;",
                "    cpu_host_hal_glfw_audio_thread_stop_flag = 0u;",
                "}",
                "",
                "static void cpu_host_hal_glfw_audio_thread_drain(uint32_t timeout_ms) {",
                "    uint32_t waited_ms = 0u;",
                "    if (cpu_host_hal_glfw_audio_thread_started == 0u || cpu_host_hal_glfw_alsa_pcm == NULL) return;",
                "    for (;;) {",
                "        uint32_t pending = 0u;",
                "        pthread_mutex_lock(&cpu_host_hal_glfw_audio_mutex);",
                "        pending = cpu_host_hal_glfw_audio_len;",
                "        if (pending != 0u) pthread_cond_signal(&cpu_host_hal_glfw_audio_cond);",
                "        pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "        if (pending == 0u || waited_ms >= timeout_ms) break;",
                "        usleep(1000u);",
                "        waited_ms += 1u;",
                "    }",
                "    snd_pcm_drain(cpu_host_hal_glfw_alsa_pcm);",
                "}",
                "#endif",
                "",
                "static void cpu_host_hal_glfw_reset_audio_state(void) {",
                "#ifdef _WIN32",
                "    if (cpu_host_hal_glfw_waveout != NULL) {",
                "        uint32_t i;",
                "        waveOutReset(cpu_host_hal_glfw_waveout);",
                "        for (i = 0u; i < 4u; ++i) {",
                "            if ((cpu_host_hal_glfw_wave_headers[i].dwFlags & WHDR_PREPARED) != 0u) {",
                "                waveOutUnprepareHeader(cpu_host_hal_glfw_waveout, &cpu_host_hal_glfw_wave_headers[i], sizeof(cpu_host_hal_glfw_wave_headers[i]));",
                "            }",
                "            free(cpu_host_hal_glfw_wave_buffers[i]);",
                "            cpu_host_hal_glfw_wave_buffers[i] = NULL;",
                "            memset(&cpu_host_hal_glfw_wave_headers[i], 0, sizeof(cpu_host_hal_glfw_wave_headers[i]));",
                "        }",
                "        waveOutClose(cpu_host_hal_glfw_waveout);",
                "        cpu_host_hal_glfw_waveout = NULL;",
                "    }",
                "    cpu_host_hal_glfw_wave_buffer_bytes = 0u;",
                "    cpu_host_hal_glfw_wave_next = 0u;",
                "#endif",
                "    if (cpu_host_hal_glfw_sdl_audio_dev != 0u) {",
                "        SDL_PauseAudioDevice(cpu_host_hal_glfw_sdl_audio_dev, 1);",
                "        SDL_CloseAudioDevice(cpu_host_hal_glfw_sdl_audio_dev);",
                "        cpu_host_hal_glfw_sdl_audio_dev = 0u;",
                "    }",
                "    if (cpu_host_hal_glfw_sdl_inited != 0u) {",
                "        SDL_QuitSubSystem(SDL_INIT_AUDIO);",
                "        cpu_host_hal_glfw_sdl_inited = 0u;",
                "    }",
                "#ifdef __linux__",
                "    cpu_host_hal_glfw_audio_thread_drain(200u);",
                "    cpu_host_hal_glfw_audio_thread_stop();",
                "    if (cpu_host_hal_glfw_alsa_pcm != NULL) {",
                "        snd_pcm_drop(cpu_host_hal_glfw_alsa_pcm);",
                "        snd_pcm_close(cpu_host_hal_glfw_alsa_pcm);",
                "        cpu_host_hal_glfw_alsa_pcm = NULL;",
                "    }",
                "    cpu_host_hal_glfw_alsa_channels = 0u;",
                "#endif",
                "    free(cpu_host_hal_glfw_audio_buf);",
                "    cpu_host_hal_glfw_audio_buf = NULL;",
                "    cpu_host_hal_glfw_audio_len = 0u;",
                "    cpu_host_hal_glfw_audio_cap = 0u;",
                "    cpu_host_hal_glfw_audio_opened = 0u;",
                "}",
                "",
                "static void cpu_host_hal_glfw_reset_input_state(void) {",
                "    cpu_host_hal_glfw_poll_cursor = 0;",
                "    cpu_host_hal_glfw_quit_emitted = 0u;",
                "    memset(cpu_host_hal_glfw_prev_keys, 0, sizeof(cpu_host_hal_glfw_prev_keys));",
                "    memset(cpu_host_hal_glfw_keys, 0, sizeof(cpu_host_hal_glfw_keys));",
                "    memset(cpu_host_hal_glfw_hold_ticks, 0, sizeof(cpu_host_hal_glfw_hold_ticks));",
                "    cpu_host_hal_glfw_event_mod_state = 0u;",
                "}",
                "",
                "static void cpu_host_hal_glfw_alsa_error_handler(const char *file, int line, const char *function, int err, const char *fmt, va_list ap) {",
                "    (void)file;",
                "    (void)line;",
                "    (void)function;",
                "    (void)err;",
                "    (void)fmt;",
                "    (void)ap;",
                "}",
                "",
                "static void cpu_host_hal_glfw_alsa_stderr_redirect(void) {",
                "#ifdef __linux__",
                "    static int redirected = 0;",
                "    if (redirected != 0) return;",
                "    redirected = 1;",
                "    {",
                "        FILE *fp = fopen(\"/dev/null\", \"a\");",
                "        if (fp != NULL) {",
                "            fflush(stderr);",
                "            dup2(fileno(fp), fileno(stderr));",
                "            if (fp != stderr) fclose(fp);",
                "        }",
                "    }",
                "#endif",
                "}",
                "",
                "static int cpu_host_hal_glfw_renderer_sync_size(CPUHostGlfwRenderer *renderer) {",
                "    int w;",
                "    int h;",
                "    uint64_t w64;",
                "    uint64_t h64;",
                "    uint64_t need64;",
                "    size_t need;",
                "    uint8_t *new_buf;",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!renderer || !renderer->window) return -1;",
                "    glfwGetWindowSize(renderer->window, &w, &h);",
                "    if (w <= 0 || h <= 0) return -1;",
                "    if (renderer->w == w && renderer->h == h && renderer->frame_rgba != NULL) return 0;",
                "    w64 = (uint64_t)(uint32_t)w;",
                "    h64 = (uint64_t)(uint32_t)h;",
                "    if (w64 != 0u && h64 > (0xFFFFFFFFFFFFFFFFu / w64)) return -1;",
                "    need64 = w64 * h64;",
                "    if (need64 > (0xFFFFFFFFFFFFFFFFu / 4u)) return -1;",
                "    need64 *= 4u;",
                "    if (need64 == 0u || need64 > (uint64_t)SIZE_MAX) return -1;",
                "    need = (size_t)need64;",
                "    new_buf = (uint8_t *)realloc(renderer->frame_rgba, need);",
                "    if (!new_buf) return -1;",
                "    renderer->frame_rgba = new_buf;",
                "    renderer->frame_len = need;",
                "    renderer->w = w;",
                "    renderer->h = h;",
                "    memset(renderer->frame_rgba, 0, renderer->frame_len);",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_glfw_key_for_scancode(int scancode) {",
                "    switch (scancode) {",
                "        case CPU_GLFW_SC_0: return GLFW_KEY_0;",
                "        case CPU_GLFW_SC_1: return GLFW_KEY_1;",
                "        case CPU_GLFW_SC_2: return GLFW_KEY_2;",
                "        case CPU_GLFW_SC_3: return GLFW_KEY_3;",
                "        case CPU_GLFW_SC_4: return GLFW_KEY_4;",
                "        case CPU_GLFW_SC_5: return GLFW_KEY_5;",
                "        case CPU_GLFW_SC_6: return GLFW_KEY_6;",
                "        case CPU_GLFW_SC_7: return GLFW_KEY_7;",
                "        case CPU_GLFW_SC_8: return GLFW_KEY_8;",
                "        case CPU_GLFW_SC_9: return GLFW_KEY_9;",
                "        case CPU_GLFW_SC_A: return GLFW_KEY_A;",
                "        case CPU_GLFW_SC_APOSTROPHE: return GLFW_KEY_APOSTROPHE;",
                "        case CPU_GLFW_SC_B: return GLFW_KEY_B;",
                "        case CPU_GLFW_SC_BACKSLASH: return GLFW_KEY_BACKSLASH;",
                "        case CPU_GLFW_SC_BACKSPACE: return GLFW_KEY_BACKSPACE;",
                "        case CPU_GLFW_SC_C: return GLFW_KEY_C;",
                "        case CPU_GLFW_SC_CAPSLOCK: return GLFW_KEY_CAPS_LOCK;",
                "        case CPU_GLFW_SC_COMMA: return GLFW_KEY_COMMA;",
                "        case CPU_GLFW_SC_D: return GLFW_KEY_D;",
                "        case CPU_GLFW_SC_DOWN: return GLFW_KEY_DOWN;",
                "        case CPU_GLFW_SC_E: return GLFW_KEY_E;",
                "        case CPU_GLFW_SC_EQUALS: return GLFW_KEY_EQUAL;",
                "        case CPU_GLFW_SC_ESCAPE: return GLFW_KEY_ESCAPE;",
                "        case CPU_GLFW_SC_F: return GLFW_KEY_F;",
                "        case CPU_GLFW_SC_F1: return GLFW_KEY_F1;",
                "        case CPU_GLFW_SC_F2: return GLFW_KEY_F2;",
                "        case CPU_GLFW_SC_F3: return GLFW_KEY_F3;",
                "        case CPU_GLFW_SC_F4: return GLFW_KEY_F4;",
                "        case CPU_GLFW_SC_F5: return GLFW_KEY_F5;",
                "        case CPU_GLFW_SC_F6: return GLFW_KEY_F6;",
                "        case CPU_GLFW_SC_F7: return GLFW_KEY_F7;",
                "        case CPU_GLFW_SC_F8: return GLFW_KEY_F8;",
                "        case CPU_GLFW_SC_F9: return GLFW_KEY_F9;",
                "        case CPU_GLFW_SC_F10: return GLFW_KEY_F10;",
                "        case CPU_GLFW_SC_F11: return GLFW_KEY_F11;",
                "        case CPU_GLFW_SC_F12: return GLFW_KEY_F12;",
                "        case CPU_GLFW_SC_G: return GLFW_KEY_G;",
                "        case CPU_GLFW_SC_GRAVE: return GLFW_KEY_GRAVE_ACCENT;",
                "        case CPU_GLFW_SC_H: return GLFW_KEY_H;",
                "        case CPU_GLFW_SC_HOME: return GLFW_KEY_HOME;",
                "        case CPU_GLFW_SC_I: return GLFW_KEY_I;",
                "        case CPU_GLFW_SC_INSERT: return GLFW_KEY_INSERT;",
                "        case CPU_GLFW_SC_INTERNATIONAL1: return GLFW_KEY_WORLD_1;",
                "        case CPU_GLFW_SC_J: return GLFW_KEY_J;",
                "        case CPU_GLFW_SC_K: return GLFW_KEY_K;",
                "        case CPU_GLFW_SC_KP_0: return GLFW_KEY_KP_0;",
                "        case CPU_GLFW_SC_KP_1: return GLFW_KEY_KP_1;",
                "        case CPU_GLFW_SC_KP_2: return GLFW_KEY_KP_2;",
                "        case CPU_GLFW_SC_KP_3: return GLFW_KEY_KP_3;",
                "        case CPU_GLFW_SC_KP_4: return GLFW_KEY_KP_4;",
                "        case CPU_GLFW_SC_KP_5: return GLFW_KEY_KP_5;",
                "        case CPU_GLFW_SC_KP_6: return GLFW_KEY_KP_6;",
                "        case CPU_GLFW_SC_KP_7: return GLFW_KEY_KP_7;",
                "        case CPU_GLFW_SC_KP_8: return GLFW_KEY_KP_8;",
                "        case CPU_GLFW_SC_KP_9: return GLFW_KEY_KP_9;",
                "        case CPU_GLFW_SC_KP_ENTER: return GLFW_KEY_KP_ENTER;",
                "        case CPU_GLFW_SC_KP_PERIOD: return GLFW_KEY_KP_DECIMAL;",
                "        case CPU_GLFW_SC_L: return GLFW_KEY_L;",
                "        case CPU_GLFW_SC_LALT: return GLFW_KEY_LEFT_ALT;",
                "        case CPU_GLFW_SC_LCTRL: return GLFW_KEY_LEFT_CONTROL;",
                "        case CPU_GLFW_SC_LEFT: return GLFW_KEY_LEFT;",
                "        case CPU_GLFW_SC_LEFTBRACKET: return GLFW_KEY_LEFT_BRACKET;",
                "        case CPU_GLFW_SC_LSHIFT: return GLFW_KEY_LEFT_SHIFT;",
                "        case CPU_GLFW_SC_M: return GLFW_KEY_M;",
                "        case CPU_GLFW_SC_MINUS: return GLFW_KEY_MINUS;",
                "        case CPU_GLFW_SC_N: return GLFW_KEY_N;",
                "        case CPU_GLFW_SC_NONUSBACKSLASH: return GLFW_KEY_WORLD_1;",
                "        case CPU_GLFW_SC_NONUSHASH: return GLFW_KEY_WORLD_2;",
                "        case CPU_GLFW_SC_O: return GLFW_KEY_O;",
                "        case CPU_GLFW_SC_P: return GLFW_KEY_P;",
                "        case CPU_GLFW_SC_PAGEDOWN: return GLFW_KEY_PAGE_DOWN;",
                "        case CPU_GLFW_SC_PAGEUP: return GLFW_KEY_PAGE_UP;",
                "        case CPU_GLFW_SC_PAUSE: return GLFW_KEY_PAUSE;",
                "        case CPU_GLFW_SC_PERIOD: return GLFW_KEY_PERIOD;",
                "        case CPU_GLFW_SC_Q: return GLFW_KEY_Q;",
                "        case CPU_GLFW_SC_R: return GLFW_KEY_R;",
                "        case CPU_GLFW_SC_RALT: return GLFW_KEY_RIGHT_ALT;",
                "        case CPU_GLFW_SC_RCTRL: return GLFW_KEY_RIGHT_CONTROL;",
                "        case CPU_GLFW_SC_RETURN: return GLFW_KEY_ENTER;",
                "        case CPU_GLFW_SC_RETURN2: return GLFW_KEY_ENTER;",
                "        case CPU_GLFW_SC_RIGHT: return GLFW_KEY_RIGHT;",
                "        case CPU_GLFW_SC_RIGHTBRACKET: return GLFW_KEY_RIGHT_BRACKET;",
                "        case CPU_GLFW_SC_RSHIFT: return GLFW_KEY_RIGHT_SHIFT;",
                "        case CPU_GLFW_SC_S: return GLFW_KEY_S;",
                "        case CPU_GLFW_SC_SEMICOLON: return GLFW_KEY_SEMICOLON;",
                "        case CPU_GLFW_SC_SLASH: return GLFW_KEY_SLASH;",
                "        case CPU_GLFW_SC_SPACE: return GLFW_KEY_SPACE;",
                "        case CPU_GLFW_SC_T: return GLFW_KEY_T;",
                "        case CPU_GLFW_SC_TAB: return GLFW_KEY_TAB;",
                "        case CPU_GLFW_SC_U: return GLFW_KEY_U;",
                "        case CPU_GLFW_SC_UP: return GLFW_KEY_UP;",
                "        case CPU_GLFW_SC_V: return GLFW_KEY_V;",
                "        case CPU_GLFW_SC_W: return GLFW_KEY_W;",
                "        case CPU_GLFW_SC_X: return GLFW_KEY_X;",
                "        case CPU_GLFW_SC_Y: return GLFW_KEY_Y;",
                "        case CPU_GLFW_SC_Z: return GLFW_KEY_Z;",
                "        case CPU_GLFW_SC_APPLICATION: return GLFW_KEY_MENU;",
                "        case CPU_GLFW_SC_DELETE: return GLFW_KEY_DELETE;",
                "        case CPU_GLFW_SC_END: return GLFW_KEY_END;",
                "        default: return -1;",
                "    }",
                "}",
                "",
                "static const char *cpu_host_hal_glfw_scancode_name(int scancode) {",
                "    switch (scancode) {",
                "        case CPU_GLFW_SC_0: return \"0\";",
                "        case CPU_GLFW_SC_1: return \"1\";",
                "        case CPU_GLFW_SC_2: return \"2\";",
                "        case CPU_GLFW_SC_3: return \"3\";",
                "        case CPU_GLFW_SC_4: return \"4\";",
                "        case CPU_GLFW_SC_5: return \"5\";",
                "        case CPU_GLFW_SC_6: return \"6\";",
                "        case CPU_GLFW_SC_7: return \"7\";",
                "        case CPU_GLFW_SC_8: return \"8\";",
                "        case CPU_GLFW_SC_9: return \"9\";",
                "        case CPU_GLFW_SC_A: return \"A\";",
                "        case CPU_GLFW_SC_APOSTROPHE: return \"APOSTROPHE\";",
                "        case CPU_GLFW_SC_B: return \"B\";",
                "        case CPU_GLFW_SC_BACKSLASH: return \"BACKSLASH\";",
                "        case CPU_GLFW_SC_CAPSLOCK: return \"CAPSLOCK\";",
                "        case CPU_GLFW_SC_C: return \"C\";",
                "        case CPU_GLFW_SC_COMMA: return \"COMMA\";",
                "        case CPU_GLFW_SC_D: return \"D\";",
                "        case CPU_GLFW_SC_E: return \"E\";",
                "        case CPU_GLFW_SC_EQUALS: return \"EQUALS\";",
                "        case CPU_GLFW_SC_F: return \"F\";",
                "        case CPU_GLFW_SC_F1: return \"F1\";",
                "        case CPU_GLFW_SC_F2: return \"F2\";",
                "        case CPU_GLFW_SC_F3: return \"F3\";",
                "        case CPU_GLFW_SC_F4: return \"F4\";",
                "        case CPU_GLFW_SC_F5: return \"F5\";",
                "        case CPU_GLFW_SC_F6: return \"F6\";",
                "        case CPU_GLFW_SC_F7: return \"F7\";",
                "        case CPU_GLFW_SC_F8: return \"F8\";",
                "        case CPU_GLFW_SC_F9: return \"F9\";",
                "        case CPU_GLFW_SC_F10: return \"F10\";",
                "        case CPU_GLFW_SC_F11: return \"F11\";",
                "        case CPU_GLFW_SC_F12: return \"F12\";",
                "        case CPU_GLFW_SC_G: return \"G\";",
                "        case CPU_GLFW_SC_GRAVE: return \"GRAVE\";",
                "        case CPU_GLFW_SC_H: return \"H\";",
                "        case CPU_GLFW_SC_HOME: return \"HOME\";",
                "        case CPU_GLFW_SC_I: return \"I\";",
                "        case CPU_GLFW_SC_INSERT: return \"INSERT\";",
                "        case CPU_GLFW_SC_J: return \"J\";",
                "        case CPU_GLFW_SC_K: return \"K\";",
                "        case CPU_GLFW_SC_KP_0: return \"KP_0\";",
                "        case CPU_GLFW_SC_KP_1: return \"KP_1\";",
                "        case CPU_GLFW_SC_KP_2: return \"KP_2\";",
                "        case CPU_GLFW_SC_KP_3: return \"KP_3\";",
                "        case CPU_GLFW_SC_KP_4: return \"KP_4\";",
                "        case CPU_GLFW_SC_KP_5: return \"KP_5\";",
                "        case CPU_GLFW_SC_KP_6: return \"KP_6\";",
                "        case CPU_GLFW_SC_KP_7: return \"KP_7\";",
                "        case CPU_GLFW_SC_KP_8: return \"KP_8\";",
                "        case CPU_GLFW_SC_KP_9: return \"KP_9\";",
                "        case CPU_GLFW_SC_KP_ENTER: return \"KP_ENTER\";",
                "        case CPU_GLFW_SC_KP_PERIOD: return \"KP_PERIOD\";",
                "        case CPU_GLFW_SC_L: return \"L\";",
                "        case CPU_GLFW_SC_M: return \"M\";",
                "        case CPU_GLFW_SC_MINUS: return \"MINUS\";",
                "        case CPU_GLFW_SC_N: return \"N\";",
                "        case CPU_GLFW_SC_NONUSBACKSLASH: return \"NONUSBACKSLASH\";",
                "        case CPU_GLFW_SC_NONUSHASH: return \"NONUSHASH\";",
                "        case CPU_GLFW_SC_O: return \"O\";",
                "        case CPU_GLFW_SC_P: return \"P\";",
                "        case CPU_GLFW_SC_PAGEDOWN: return \"PAGEDOWN\";",
                "        case CPU_GLFW_SC_PAGEUP: return \"PAGEUP\";",
                "        case CPU_GLFW_SC_PERIOD: return \"PERIOD\";",
                "        case CPU_GLFW_SC_Q: return \"Q\";",
                "        case CPU_GLFW_SC_R: return \"R\";",
                "        case CPU_GLFW_SC_RETURN2: return \"RETURN2\";",
                "        case CPU_GLFW_SC_S: return \"S\";",
                "        case CPU_GLFW_SC_SEMICOLON: return \"SEMICOLON\";",
                "        case CPU_GLFW_SC_SLASH: return \"SLASH\";",
                "        case CPU_GLFW_SC_T: return \"T\";",
                "        case CPU_GLFW_SC_U: return \"U\";",
                "        case CPU_GLFW_SC_V: return \"V\";",
                "        case CPU_GLFW_SC_W: return \"W\";",
                "        case CPU_GLFW_SC_X: return \"X\";",
                "        case CPU_GLFW_SC_Y: return \"Y\";",
                "        case CPU_GLFW_SC_Z: return \"Z\";",
                "        case CPU_GLFW_SC_SPACE: return \"SPACE\";",
                "        case CPU_GLFW_SC_RETURN: return \"RETURN\";",
                "        case CPU_GLFW_SC_BACKSPACE: return \"BACKSPACE\";",
                "        case CPU_GLFW_SC_TAB: return \"TAB\";",
                "        case CPU_GLFW_SC_ESCAPE: return \"ESCAPE\";",
                "        case CPU_GLFW_SC_LEFT: return \"LEFT\";",
                "        case CPU_GLFW_SC_RIGHT: return \"RIGHT\";",
                "        case CPU_GLFW_SC_UP: return \"UP\";",
                "        case CPU_GLFW_SC_DOWN: return \"DOWN\";",
                "        case CPU_GLFW_SC_LCTRL: return \"LCTRL\";",
                "        case CPU_GLFW_SC_RCTRL: return \"RCTRL\";",
                "        case CPU_GLFW_SC_LSHIFT: return \"LSHIFT\";",
                "        case CPU_GLFW_SC_RSHIFT: return \"RSHIFT\";",
                "        case CPU_GLFW_SC_LALT: return \"LALT\";",
                "        case CPU_GLFW_SC_RALT: return \"RALT\";",
                "        case CPU_GLFW_SC_LEFTBRACKET: return \"LEFTBRACKET\";",
                "        case CPU_GLFW_SC_RIGHTBRACKET: return \"RIGHTBRACKET\";",
                "        case CPU_GLFW_SC_INTERNATIONAL1: return \"INTERNATIONAL1\";",
                "        case CPU_GLFW_SC_APPLICATION: return \"APPLICATION\";",
                "        case CPU_GLFW_SC_PAUSE: return \"PAUSE\";",
                "        case CPU_GLFW_SC_DELETE: return \"DELETE\";",
                "        case CPU_GLFW_SC_END: return \"END\";",
                "        default: return \"UNKNOWN\";",
                "    }",
                "}",
                "",
                "static const char *cpu_host_hal_glfw_key_name(int keycode) {",
                "    switch (keycode) {",
                "        case GLFW_KEY_0: return \"0\";",
                "        case GLFW_KEY_1: return \"1\";",
                "        case GLFW_KEY_2: return \"2\";",
                "        case GLFW_KEY_3: return \"3\";",
                "        case GLFW_KEY_4: return \"4\";",
                "        case GLFW_KEY_5: return \"5\";",
                "        case GLFW_KEY_6: return \"6\";",
                "        case GLFW_KEY_7: return \"7\";",
                "        case GLFW_KEY_8: return \"8\";",
                "        case GLFW_KEY_9: return \"9\";",
                "        case GLFW_KEY_APOSTROPHE: return \"APOSTROPHE\";",
                "        case GLFW_KEY_COMMA: return \"COMMA\";",
                "        case GLFW_KEY_MINUS: return \"MINUS\";",
                "        case GLFW_KEY_PERIOD: return \"PERIOD\";",
                "        case GLFW_KEY_SLASH: return \"SLASH\";",
                "        case GLFW_KEY_SEMICOLON: return \"SEMICOLON\";",
                "        case GLFW_KEY_EQUAL: return \"EQUALS\";",
                "        case GLFW_KEY_LEFT_BRACKET: return \"LEFTBRACKET\";",
                "        case GLFW_KEY_BACKSLASH: return \"BACKSLASH\";",
                "        case GLFW_KEY_RIGHT_BRACKET: return \"RIGHTBRACKET\";",
                "        case GLFW_KEY_GRAVE_ACCENT: return \"GRAVE\";",
                "        case GLFW_KEY_A: return \"A\";",
                "        case GLFW_KEY_B: return \"B\";",
                "        case GLFW_KEY_C: return \"C\";",
                "        case GLFW_KEY_D: return \"D\";",
                "        case GLFW_KEY_E: return \"E\";",
                "        case GLFW_KEY_F: return \"F\";",
                "        case GLFW_KEY_G: return \"G\";",
                "        case GLFW_KEY_H: return \"H\";",
                "        case GLFW_KEY_I: return \"I\";",
                "        case GLFW_KEY_J: return \"J\";",
                "        case GLFW_KEY_K: return \"K\";",
                "        case GLFW_KEY_L: return \"L\";",
                "        case GLFW_KEY_M: return \"M\";",
                "        case GLFW_KEY_N: return \"N\";",
                "        case GLFW_KEY_O: return \"O\";",
                "        case GLFW_KEY_P: return \"P\";",
                "        case GLFW_KEY_Q: return \"Q\";",
                "        case GLFW_KEY_R: return \"R\";",
                "        case GLFW_KEY_S: return \"S\";",
                "        case GLFW_KEY_T: return \"T\";",
                "        case GLFW_KEY_U: return \"U\";",
                "        case GLFW_KEY_V: return \"V\";",
                "        case GLFW_KEY_W: return \"W\";",
                "        case GLFW_KEY_X: return \"X\";",
                "        case GLFW_KEY_Y: return \"Y\";",
                "        case GLFW_KEY_Z: return \"Z\";",
                "        case GLFW_KEY_ENTER: return \"RETURN\";",
                "        case GLFW_KEY_BACKSPACE: return \"BACKSPACE\";",
                "        case GLFW_KEY_TAB: return \"TAB\";",
                "        case GLFW_KEY_ESCAPE: return \"ESCAPE\";",
                "        case GLFW_KEY_LEFT: return \"LEFT\";",
                "        case GLFW_KEY_RIGHT: return \"RIGHT\";",
                "        case GLFW_KEY_UP: return \"UP\";",
                "        case GLFW_KEY_DOWN: return \"DOWN\";",
                "        case GLFW_KEY_INSERT: return \"INSERT\";",
                "        case GLFW_KEY_DELETE: return \"DELETE\";",
                "        case GLFW_KEY_HOME: return \"HOME\";",
                "        case GLFW_KEY_END: return \"END\";",
                "        case GLFW_KEY_PAGE_DOWN: return \"PAGEDOWN\";",
                "        case GLFW_KEY_PAGE_UP: return \"PAGEUP\";",
                "        case GLFW_KEY_CAPS_LOCK: return \"CAPSLOCK\";",
                "        case GLFW_KEY_F1: return \"F1\";",
                "        case GLFW_KEY_F2: return \"F2\";",
                "        case GLFW_KEY_F3: return \"F3\";",
                "        case GLFW_KEY_F4: return \"F4\";",
                "        case GLFW_KEY_F5: return \"F5\";",
                "        case GLFW_KEY_F6: return \"F6\";",
                "        case GLFW_KEY_F7: return \"F7\";",
                "        case GLFW_KEY_F8: return \"F8\";",
                "        case GLFW_KEY_F9: return \"F9\";",
                "        case GLFW_KEY_F10: return \"F10\";",
                "        case GLFW_KEY_F11: return \"F11\";",
                "        case GLFW_KEY_F12: return \"F12\";",
                "        case GLFW_KEY_LEFT_CONTROL: return \"LCTRL\";",
                "        case GLFW_KEY_RIGHT_CONTROL: return \"RCTRL\";",
                "        case GLFW_KEY_LEFT_SHIFT: return \"LSHIFT\";",
                "        case GLFW_KEY_RIGHT_SHIFT: return \"RSHIFT\";",
                "        case GLFW_KEY_LEFT_ALT: return \"LALT\";",
                "        case GLFW_KEY_RIGHT_ALT: return \"RALT\";",
                "        case GLFW_KEY_KP_0: return \"KP_0\";",
                "        case GLFW_KEY_KP_1: return \"KP_1\";",
                "        case GLFW_KEY_KP_2: return \"KP_2\";",
                "        case GLFW_KEY_KP_3: return \"KP_3\";",
                "        case GLFW_KEY_KP_4: return \"KP_4\";",
                "        case GLFW_KEY_KP_5: return \"KP_5\";",
                "        case GLFW_KEY_KP_6: return \"KP_6\";",
                "        case GLFW_KEY_KP_7: return \"KP_7\";",
                "        case GLFW_KEY_KP_8: return \"KP_8\";",
                "        case GLFW_KEY_KP_9: return \"KP_9\";",
                "        case GLFW_KEY_KP_DECIMAL: return \"KP_PERIOD\";",
                "        case GLFW_KEY_KP_ENTER: return \"KP_ENTER\";",
                "        case GLFW_KEY_MENU: return \"APPLICATION\";",
                "        default: return \"UNKNOWN\";",
                "    }",
                "}",
                "",
                "static uint32_t cpu_host_hal_glfw_mod_state(void) {",
                "    uint32_t mods = 0u;",
                "    int lctrl = 0;",
                "    int rctrl = 0;",
                "    int lshift = 0;",
                "    int rshift = 0;",
                "    if (cpu_host_hal_glfw_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0u;",
                "    if (cpu_host_hal_glfw_primary_window == NULL) return 0u;",
                "    lctrl = glfwGetKey(cpu_host_hal_glfw_primary_window, GLFW_KEY_LEFT_CONTROL);",
                "    rctrl = glfwGetKey(cpu_host_hal_glfw_primary_window, GLFW_KEY_RIGHT_CONTROL);",
                "    if ((lctrl == GLFW_PRESS || lctrl == GLFW_REPEAT) ||",
                "        (rctrl == GLFW_PRESS || rctrl == GLFW_REPEAT)) {",
                "        mods |= CPU_HOST_MOD_CTRL;",
                "    }",
                "    lshift = glfwGetKey(cpu_host_hal_glfw_primary_window, GLFW_KEY_LEFT_SHIFT);",
                "    rshift = glfwGetKey(cpu_host_hal_glfw_primary_window, GLFW_KEY_RIGHT_SHIFT);",
                "    if ((lshift == GLFW_PRESS || lshift == GLFW_REPEAT) ||",
                "        (rshift == GLFW_PRESS || rshift == GLFW_REPEAT)) {",
                "        mods |= CPU_HOST_MOD_SHIFT;",
                "    }",
                "    if (lctrl == GLFW_PRESS || lctrl == GLFW_REPEAT) {",
                "        mods |= CPU_HOST_MOD_LCTRL;",
                "    }",
                "    return mods;",
                "}",
                "",
                "static void cpu_host_hal_pump_events(void) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return;",
                "    glfwPollEvents();",
                "}",
                "",
                "static uint32_t cpu_host_hal_ticks_ms(void) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return 0u;",
                "    double t = glfwGetTime();",
                "    if (!(t > 0.0)) return 0u;",
                "    if (t >= 4294967.295) return 0xFFFFFFFFu;",
                "    return (uint32_t)(t * 1000.0);",
                "}",
                "",
                "static uint8_t cpu_host_hal_window_has_focus(void *window) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return 0u;",
                "    if (!window) window = (void *)cpu_host_hal_glfw_primary_window;",
                "    if (!window) return 0u;",
                "    return (glfwGetWindowAttrib((GLFWwindow *)window, GLFW_FOCUSED) != 0) ? 1u : 0u;",
                "}",
                "",
                "static void cpu_host_hal_render_present(void *renderer) {",
                "    CPUHostGlfwRenderer *rr = (CPUHostGlfwRenderer *)renderer;",
                "    GLFWwindow *window = (rr && rr->window) ? rr->window : cpu_host_hal_glfw_primary_window;",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (window != NULL) {",
                "        glfwMakeContextCurrent(window);",
                "        if (rr != NULL && rr->frame_rgba_dirty != 0u && rr->frame_rgba != NULL && rr->w > 0 && rr->h > 0 && cpu_host_hal_glfw_load_gl() == 0) {",
                "            if (rr->present_program == 0u) {",
                "                static const char *vs_src =",
                "                    \"#version 120\\n\"",
                "                    \"attribute vec4 VertexCoord;\\n\"",
                "                    \"attribute vec4 TexCoord;\\n\"",
                "                    \"varying vec2 vTexCoord;\\n\"",
                "                    \"void main() { gl_Position = VertexCoord; vTexCoord = TexCoord.xy; }\\n\";",
                "                static const char *fs_src =",
                "                    \"#version 120\\n\"",
                "                    \"varying vec2 vTexCoord;\\n\"",
                "                    \"uniform sampler2D Texture;\\n\"",
                "                    \"void main() { gl_FragColor = texture2D(Texture, vTexCoord); }\\n\";",
                "                static const GLfloat quad[] = {",
                "                    -1.0f, -1.0f, 0.0f, 1.0f, 0.0f, 1.0f,",
                "                     1.0f, -1.0f, 0.0f, 1.0f, 1.0f, 1.0f,",
                "                    -1.0f,  1.0f, 0.0f, 1.0f, 0.0f, 0.0f,",
                "                     1.0f,  1.0f, 0.0f, 1.0f, 1.0f, 0.0f",
                "                };",
                "                GLint ok = 0;",
                "                rr->present_vertex_shader = cpu_glCreateShader(GL_VERTEX_SHADER);",
                "                rr->present_fragment_shader = cpu_glCreateShader(GL_FRAGMENT_SHADER);",
                "                if (rr->present_vertex_shader != 0u && rr->present_fragment_shader != 0u) {",
                "                    cpu_glShaderSource(rr->present_vertex_shader, 1, (const GLchar * const *)&vs_src, NULL);",
                "                    cpu_glCompileShader(rr->present_vertex_shader);",
                "                    cpu_glGetShaderiv(rr->present_vertex_shader, GL_COMPILE_STATUS, &ok);",
                "                    if (ok != 0) {",
                "                        cpu_glShaderSource(rr->present_fragment_shader, 1, (const GLchar * const *)&fs_src, NULL);",
                "                        cpu_glCompileShader(rr->present_fragment_shader);",
                "                        cpu_glGetShaderiv(rr->present_fragment_shader, GL_COMPILE_STATUS, &ok);",
                "                    }",
                "                    if (ok != 0) {",
                "                        rr->present_program = cpu_glCreateProgram();",
                "                        if (rr->present_program != 0u) {",
                "                            cpu_glAttachShader(rr->present_program, rr->present_vertex_shader);",
                "                            cpu_glAttachShader(rr->present_program, rr->present_fragment_shader);",
                "                            cpu_glLinkProgram(rr->present_program);",
                "                            cpu_glGetProgramiv(rr->present_program, GL_LINK_STATUS, &ok);",
                "                            if (ok == 0) { cpu_glDeleteProgram(rr->present_program); rr->present_program = 0u; }",
                "                        }",
                "                    }",
                "                }",
                "                if (rr->present_program != 0u) {",
                "                    if (cpu_glGenVertexArrays != NULL) cpu_glGenVertexArrays(1, &rr->present_vao);",
                "                    cpu_glGenBuffers(1, &rr->present_vbo);",
                "                    if (cpu_glBindVertexArray != NULL && rr->present_vao != 0u) cpu_glBindVertexArray(rr->present_vao);",
                "                    cpu_glBindBuffer(GL_ARRAY_BUFFER, rr->present_vbo);",
                "                    cpu_glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)sizeof(quad), quad, GL_STATIC_DRAW);",
                "                    cpu_glEnableVertexAttribArray(0u);",
                "                    cpu_glVertexAttribPointer(0u, 4, GL_FLOAT, GL_FALSE, (GLsizei)(6u * sizeof(GLfloat)), (const void *)0);",
                "                    cpu_glEnableVertexAttribArray(1u);",
                "                    cpu_glVertexAttribPointer(1u, 2, GL_FLOAT, GL_FALSE, (GLsizei)(6u * sizeof(GLfloat)), (const void *)(4u * sizeof(GLfloat)));",
                "                    if (cpu_glBindVertexArray != NULL && rr->present_vao != 0u) cpu_glBindVertexArray(0u);",
                "                    cpu_glGenTextures(1, &rr->present_texture);",
                "                    cpu_glBindTexture(GL_TEXTURE_2D, rr->present_texture);",
                "                    cpu_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);",
                "                    cpu_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);",
                "                    cpu_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);",
                "                    cpu_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);",
                "                }",
                "            }",
                "            if (rr->present_program != 0u && rr->present_texture != 0u) {",
                "                GLint loc;",
                "                cpu_glViewport(0, 0, rr->w, rr->h);",
                "                cpu_glClearColor(0.0f, 0.0f, 0.0f, 1.0f);",
                "                cpu_glClear(GL_COLOR_BUFFER_BIT);",
                "                cpu_glUseProgram(rr->present_program);",
                "                cpu_glActiveTexture(GL_TEXTURE0);",
                "                cpu_glBindTexture(GL_TEXTURE_2D, rr->present_texture);",
                "                if (rr->present_texture_w != rr->w || rr->present_texture_h != rr->h) {",
                "                    cpu_glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, rr->w, rr->h, 0, GL_BGRA, GL_UNSIGNED_BYTE, rr->frame_rgba);",
                "                    rr->present_texture_w = rr->w;",
                "                    rr->present_texture_h = rr->h;",
                "                } else {",
                "                    cpu_glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, rr->w, rr->h, GL_BGRA, GL_UNSIGNED_BYTE, rr->frame_rgba);",
                "                }",
                "                loc = cpu_glGetUniformLocation(rr->present_program, \"Texture\");",
                "                if (loc >= 0) cpu_glUniform1i(loc, 0);",
                "                if (cpu_glBindVertexArray != NULL && rr->present_vao != 0u) cpu_glBindVertexArray(rr->present_vao);",
                "                cpu_glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);",
                "                if (cpu_glBindVertexArray != NULL && rr->present_vao != 0u) cpu_glBindVertexArray(0u);",
                "                cpu_glUseProgram(0u);",
                "                rr->frame_rgba_dirty = 0u;",
                "            }",
                "        }",
                "        glfwSwapBuffers(window);",
                "    }",
                "}",
                "",
                "static int cpu_host_hal_audio_queue(uint32_t dev, const void *data, uint32_t len_bytes) {",
                "    uint64_t need64;",
                "    uint32_t need;",
                "    uint32_t new_cap;",
                "    uint8_t *new_buf;",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return -1;",
                "    if (dev == 0u || !data || len_bytes == 0u || cpu_host_hal_glfw_audio_opened == 0u) return -1;",
                "#ifdef _WIN32",
                "    if (cpu_host_hal_glfw_waveout != NULL) {",
                "        uint32_t tries;",
                "        for (tries = 0u; tries < 4u; ++tries) {",
                "            uint32_t idx = (cpu_host_hal_glfw_wave_next + tries) & 3u;",
                "            WAVEHDR *hdr = &cpu_host_hal_glfw_wave_headers[idx];",
                "            if ((hdr->dwFlags & WHDR_INQUEUE) != 0u) continue;",
                "            if ((hdr->dwFlags & WHDR_PREPARED) != 0u) {",
                "                waveOutUnprepareHeader(cpu_host_hal_glfw_waveout, hdr, sizeof(*hdr));",
                "                hdr->dwFlags = 0u;",
                "            }",
                "            if (len_bytes > cpu_host_hal_glfw_wave_buffer_bytes) return -1;",
                "            memcpy(cpu_host_hal_glfw_wave_buffers[idx], data, (size_t)len_bytes);",
                "            memset(hdr, 0, sizeof(*hdr));",
                "            hdr->lpData = (LPSTR)cpu_host_hal_glfw_wave_buffers[idx];",
                "            hdr->dwBufferLength = (DWORD)len_bytes;",
                "            if (waveOutPrepareHeader(cpu_host_hal_glfw_waveout, hdr, sizeof(*hdr)) != MMSYSERR_NOERROR) return -1;",
                "            if (waveOutWrite(cpu_host_hal_glfw_waveout, hdr, sizeof(*hdr)) != MMSYSERR_NOERROR) {",
                "                waveOutUnprepareHeader(cpu_host_hal_glfw_waveout, hdr, sizeof(*hdr));",
                "                return -1;",
                "            }",
                "            cpu_host_hal_glfw_wave_next = (idx + 1u) & 3u;",
                "            return 0;",
                "        }",
                "        return 0;",
                "    }",
                "#endif",
                "#ifdef __linux__",
                "    if (cpu_host_hal_glfw_alsa_pcm != NULL) {",
                "        const uint8_t *ptr = (const uint8_t *)data;",
                "        uint32_t frame_bytes = cpu_host_hal_glfw_alsa_channels * 2u;",
                "        snd_pcm_sframes_t frames;",
                "        if (frame_bytes == 0u || (len_bytes % frame_bytes) != 0u) return -1;",
                "        frames = (snd_pcm_sframes_t)(len_bytes / frame_bytes);",
                "        pthread_mutex_lock(&cpu_host_hal_glfw_audio_mutex);",
                "        while (frames > 0) {",
                "            snd_pcm_sframes_t n = snd_pcm_writei(cpu_host_hal_glfw_alsa_pcm, ptr, (snd_pcm_uframes_t)frames);",
                "            if (n == -EPIPE) {",
                "                snd_pcm_prepare(cpu_host_hal_glfw_alsa_pcm);",
                "                continue;",
                "            }",
                "            if (n == -EAGAIN || n == -ESTRPIPE) {",
                "                snd_pcm_wait(cpu_host_hal_glfw_alsa_pcm, 10);",
                "                continue;",
                "            }",
                "            if (n < 0 || n == 0) {",
                "                pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "                return -1;",
                "            }",
                "            if (snd_pcm_state(cpu_host_hal_glfw_alsa_pcm) == SND_PCM_STATE_PREPARED) {",
                "                (void)snd_pcm_start(cpu_host_hal_glfw_alsa_pcm);",
                "            }",
                "            ptr += (size_t)n * (size_t)frame_bytes;",
                "            frames -= n;",
                "        }",
                "        pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "        return 0;",
                "    }",
                "#endif",
                "    if (cpu_host_hal_glfw_audio_len > cpu_host_hal_glfw_audio_cap) return -1;",
                "    if (cpu_host_hal_glfw_audio_cap != 0u && cpu_host_hal_glfw_audio_buf == NULL) return -1;",
                "    if (cpu_host_hal_glfw_audio_len != 0u && cpu_host_hal_glfw_audio_buf == NULL) return -1;",
                "    need64 = (uint64_t)cpu_host_hal_glfw_audio_len + (uint64_t)len_bytes;",
                "    if (need64 == 0u || need64 > 0xFFFFFFFFu || need64 > (uint64_t)SIZE_MAX) return -1;",
                "    need = (uint32_t)need64;",
                "    if (need > cpu_host_hal_glfw_audio_cap) {",
                "        new_cap = (cpu_host_hal_glfw_audio_cap == 0u) ? 4096u : cpu_host_hal_glfw_audio_cap;",
                "        while (new_cap < need) {",
                "            if (new_cap > 0x7FFFFFFFu) {",
                "                new_cap = need;",
                "                break;",
                "            }",
                "            new_cap <<= 1u;",
                "        }",
                "        if (new_cap < need || (uint64_t)new_cap > (uint64_t)SIZE_MAX) return -1;",
                "        new_buf = (uint8_t *)realloc(cpu_host_hal_glfw_audio_buf, (size_t)new_cap);",
                "        if (!new_buf) return -1;",
                "        cpu_host_hal_glfw_audio_buf = new_buf;",
                "        cpu_host_hal_glfw_audio_cap = new_cap;",
                "    }",
                "    memcpy(",
                "        cpu_host_hal_glfw_audio_buf + cpu_host_hal_glfw_audio_len,",
                "        data,",
                "        (size_t)len_bytes",
                "    );",
                "    cpu_host_hal_glfw_audio_len = need;",
                "#ifdef __linux__",
                "    if (cpu_host_hal_glfw_alsa_pcm != NULL) {",
                "        pthread_mutex_lock(&cpu_host_hal_glfw_audio_mutex);",
                "        pthread_cond_signal(&cpu_host_hal_glfw_audio_cond);",
                "        pthread_mutex_unlock(&cpu_host_hal_glfw_audio_mutex);",
                "    }",
                "#endif",
                "    return 0;",
                "}",
                "",
                "static uint32_t cpu_host_hal_audio_queued_bytes(uint32_t dev) {",
                "    uint32_t queued = 0u;",
                "    if (cpu_host_hal_glfw_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    if (dev == 0u || cpu_host_hal_glfw_audio_opened == 0u) return 0u;",
                "#ifdef _WIN32",
                "    if (cpu_host_hal_glfw_waveout != NULL) {",
                "        uint32_t i;",
                "        for (i = 0u; i < 4u; ++i) {",
                "            if ((cpu_host_hal_glfw_wave_headers[i].dwFlags & WHDR_INQUEUE) != 0u) {",
                "                queued += (uint32_t)cpu_host_hal_glfw_wave_headers[i].dwBufferLength;",
                "            }",
                "        }",
                "        return queued;",
                "    }",
                "#endif",
                "#ifdef __linux__",
                "    if (cpu_host_hal_glfw_alsa_pcm != NULL) {",
                "        return 0u;",
                "    }",
                "#endif",
                "    return cpu_host_hal_glfw_audio_len;",
                "}",
                "",
                "static void cpu_host_hal_audio_clear(uint32_t dev) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "    if (dev == 0u || cpu_host_hal_glfw_audio_opened == 0u) return;",
                "#ifdef _WIN32",
                "    if (cpu_host_hal_glfw_waveout != NULL) {",
                "        uint32_t i;",
                "        waveOutReset(cpu_host_hal_glfw_waveout);",
                "        for (i = 0u; i < 4u; ++i) {",
                "            if ((cpu_host_hal_glfw_wave_headers[i].dwFlags & WHDR_PREPARED) != 0u) {",
                "                waveOutUnprepareHeader(cpu_host_hal_glfw_waveout, &cpu_host_hal_glfw_wave_headers[i], sizeof(cpu_host_hal_glfw_wave_headers[i]));",
                "                cpu_host_hal_glfw_wave_headers[i].dwFlags = 0u;",
                "            }",
                "        }",
                "        cpu_host_hal_glfw_wave_next = 0u;",
                "        return;",
                "    }",
                "#endif",
                "#ifdef __linux__",
                "    if (cpu_host_hal_glfw_alsa_pcm != NULL) {",
                "        snd_pcm_drop(cpu_host_hal_glfw_alsa_pcm);",
                "        snd_pcm_prepare(cpu_host_hal_glfw_alsa_pcm);",
                "        return;",
                "    }",
                "#endif",
                "    cpu_host_hal_glfw_audio_len = 0u;",
                "}",
                "",
                "static int cpu_host_hal_renderer_output_size(void *renderer, int *out_w, int *out_h) {",
                "    CPUHostGlfwRenderer *r = (CPUHostGlfwRenderer *)renderer;",
                "    GLFWwindow *window = (r && r->window) ? r->window : cpu_host_hal_glfw_primary_window;",
                "    if (out_w) *out_w = 0;",
                "    if (out_h) *out_h = 0;",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!out_w || !out_h || window == NULL) return -1;",
                "    glfwGetWindowSize(window, out_w, out_h);",
                "    if (*out_w <= 0 || *out_h <= 0) return -1;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_update_texture(void *texture, const CPUHostRect *rect, const void *pixels, int pitch) {",
                "    CPUHostGlfwTexture *tex = (CPUHostGlfwTexture *)texture;",
                "    uint64_t row_bytes64;",
                "    uint64_t tex_bytes64;",
                "    uint64_t dst_start64;",
                "    uint64_t dst_stride64;",
                "    uint64_t dst_span64;",
                "    uint64_t src_span64;",
                "    int64_t sum64;",
                "    int x = 0;",
                "    int y = 0;",
                "    int w;",
                "    int h;",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!tex || !tex->pixels || !pixels || pitch <= 0) return -1;",
                "    if (tex->w <= 0 || tex->h <= 0) return -1;",
                "    w = tex->w;",
                "    h = tex->h;",
                "    if (rect) {",
                "        x = rect->x;",
                "        y = rect->y;",
                "        w = rect->w;",
                "        h = rect->h;",
                "        if (x < 0 || y < 0 || w <= 0 || h <= 0) return -1;",
                "        sum64 = (int64_t)x + (int64_t)w;",
                "        if (sum64 > (int64_t)tex->w) w = tex->w - x;",
                "        sum64 = (int64_t)y + (int64_t)h;",
                "        if (sum64 > (int64_t)tex->h) h = tex->h - y;",
                "    }",
                "    if (w <= 0 || h <= 0) return -1;",
                "    row_bytes64 = (uint64_t)(uint32_t)w * 4u;",
                "    if (row_bytes64 > (uint64_t)INT_MAX) return -1;",
                "    if ((uint64_t)(uint32_t)pitch < row_bytes64) return -1;",
                "    tex_bytes64 = (uint64_t)(uint32_t)tex->w * (uint64_t)(uint32_t)tex->h * 4u;",
                "    if (tex_bytes64 == 0u || tex_bytes64 > (uint64_t)SIZE_MAX) return -1;",
                "    if ((uint64_t)tex->pixels_len < tex_bytes64) return -1;",
                "    dst_start64 = (((uint64_t)(uint32_t)y * (uint64_t)(uint32_t)tex->w) + (uint64_t)(uint32_t)x) * 4u;",
                "    if (dst_start64 > tex_bytes64) return -1;",
                "    dst_stride64 = (uint64_t)(uint32_t)tex->w * 4u;",
                "    dst_span64 = ((uint64_t)(uint32_t)(h - 1) * dst_stride64) + row_bytes64;",
                "    if (dst_span64 > (tex_bytes64 - dst_start64)) return -1;",
                "    src_span64 = ((uint64_t)(uint32_t)(h - 1) * (uint64_t)(uint32_t)pitch) + row_bytes64;",
                "    if (src_span64 == 0u || src_span64 > (uint64_t)SIZE_MAX) return -1;",
                "    for (int row = 0; row < h; ++row) {",
                "        memcpy(",
                "            tex->pixels + (((size_t)(y + row) * (size_t)tex->w + (size_t)x) * 4u),",
                "            ((const uint8_t *)pixels) + ((size_t)row * (size_t)pitch),",
                "            (size_t)w * 4u",
                "        );",
                "    }",
                "    return 0;",
                "}",
                "",
                "static void cpu_host_hal_render_set_draw_color(void *renderer, uint8_t r, uint8_t g, uint8_t b, uint8_t a) {",
                "    CPUHostGlfwRenderer *rr = (CPUHostGlfwRenderer *)renderer;",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!rr) return;",
                "    rr->clear_color = ((uint32_t)a << 24) | ((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)b;",
                "}",
                "",
                "static int cpu_host_hal_render_clear(void *renderer) {",
                "    CPUHostGlfwRenderer *rr = (CPUHostGlfwRenderer *)renderer;",
                "    uint64_t expect64;",
                "    uint32_t *pix;",
                "    size_t count;",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!rr) return -1;",
                "    if (cpu_host_hal_glfw_renderer_sync_size(rr) != 0) return -1;",
                "    if (!rr->frame_rgba) return -1;",
                "    expect64 = (uint64_t)(uint32_t)rr->w * (uint64_t)(uint32_t)rr->h * 4u;",
                "    if (expect64 == 0u || expect64 > (uint64_t)SIZE_MAX) return -1;",
                "    if (rr->frame_len < (size_t)expect64) return -1;",
                "    pix = (uint32_t *)rr->frame_rgba;",
                "    count = (size_t)expect64 / 4u;",
                "    for (size_t i = 0u; i < count; ++i) pix[i] = rr->clear_color;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_render_copy(void *renderer, void *texture, const CPUHostRect *src_rect, const CPUHostRect *dst_rect) {",
                "    CPUHostGlfwRenderer *rr = (CPUHostGlfwRenderer *)renderer;",
                "    CPUHostGlfwTexture *tex = (CPUHostGlfwTexture *)texture;",
                "    uint64_t expect64;",
                "    uint64_t tex_bytes64;",
                "    uint64_t row_bytes64;",
                "    uint64_t src_start64;",
                "    uint64_t src_stride64;",
                "    uint64_t src_span64;",
                "    uint64_t dst_start64;",
                "    uint64_t dst_stride64;",
                "    uint64_t dst_span64;",
                "    int64_t sum64;",
                "    int sx = 0;",
                "    int sy = 0;",
                "    int sw;",
                "    int sh;",
                "    int dx = 0;",
                "    int dy = 0;",
                "    int dw;",
                "    int dh;",
                "    int cw;",
                "    int ch;",
                "    int copy_x0 = 0;",
                "    int copy_y0 = 0;",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!rr || !tex || !tex->pixels) return -1;",
                "    if (tex->w <= 0 || tex->h <= 0) return -1;",
                "    if (cpu_host_hal_glfw_renderer_sync_size(rr) != 0) return -1;",
                "    if (!rr->frame_rgba) return -1;",
                "    if (rr->w <= 0 || rr->h <= 0) return -1;",
                "    expect64 = (uint64_t)(uint32_t)rr->w * (uint64_t)(uint32_t)rr->h * 4u;",
                "    if (expect64 == 0u || expect64 > (uint64_t)SIZE_MAX) return -1;",
                "    if (rr->frame_len < (size_t)expect64) return -1;",
                "    sw = tex->w;",
                "    sh = tex->h;",
                "    if (src_rect) {",
                "        sx = src_rect->x;",
                "        sy = src_rect->y;",
                "        sw = src_rect->w;",
                "        sh = src_rect->h;",
                "        if (sx < 0 || sy < 0 || sw <= 0 || sh <= 0) return -1;",
                "    }",
                "    sum64 = (int64_t)sx + (int64_t)sw;",
                "    if (sum64 > (int64_t)tex->w) sw = tex->w - sx;",
                "    sum64 = (int64_t)sy + (int64_t)sh;",
                "    if (sum64 > (int64_t)tex->h) sh = tex->h - sy;",
                "    if (sw <= 0 || sh <= 0) return -1;",
                "    dw = sw;",
                "    dh = sh;",
                "    if (dst_rect) {",
                "        dx = dst_rect->x;",
                "        dy = dst_rect->y;",
                "        dw = dst_rect->w;",
                "        dh = dst_rect->h;",
                "        if (dw <= 0 || dh <= 0) return -1;",
                "    }",
                "    if (dx < 0) { copy_x0 = -dx; dx = 0; }",
                "    if (dy < 0) { copy_y0 = -dy; dy = 0; }",
                "    if (sx >= tex->w || sy >= tex->h) return 0;",
                "    sum64 = (int64_t)sx + (int64_t)sw;",
                "    if (sum64 > (int64_t)tex->w) sw = tex->w - sx;",
                "    sum64 = (int64_t)sy + (int64_t)sh;",
                "    if (sum64 > (int64_t)tex->h) sh = tex->h - sy;",
                "    if (sw <= 0 || sh <= 0) return 0;",
                "    if (dx >= rr->w || dy >= rr->h) return 0;",
                "    cw = dw - copy_x0;",
                "    ch = dh - copy_y0;",
                "    sum64 = (int64_t)dx + (int64_t)cw;",
                "    if (sum64 > (int64_t)rr->w) cw = rr->w - dx;",
                "    sum64 = (int64_t)dy + (int64_t)ch;",
                "    if (sum64 > (int64_t)rr->h) ch = rr->h - dy;",
                "    if (cw <= 0 || ch <= 0) return 0;",
                "    tex_bytes64 = (uint64_t)(uint32_t)tex->w * (uint64_t)(uint32_t)tex->h * 4u;",
                "    if (tex_bytes64 == 0u || tex_bytes64 > (uint64_t)SIZE_MAX) return -1;",
                "    if ((uint64_t)tex->pixels_len < tex_bytes64) return -1;",
                "    dst_start64 = (((uint64_t)(uint32_t)dy * (uint64_t)(uint32_t)rr->w) + (uint64_t)(uint32_t)dx) * 4u;",
                "    if (dst_start64 > expect64) return -1;",
                "    dst_span64 = ((uint64_t)(uint32_t)(ch - 1) * ((uint64_t)(uint32_t)rr->w * 4u)) + ((uint64_t)(uint32_t)cw * 4u);",
                "    if (dst_span64 > (expect64 - dst_start64)) return -1;",
                "    for (int row = 0; row < ch; ++row) {",
                "        int src_y = sy + (int)((((int64_t)(row + copy_y0)) * (int64_t)sh) / (int64_t)dh);",
                "        uint32_t *dst_px = (uint32_t *)(void *)(rr->frame_rgba + (((size_t)(dy + row) * (size_t)rr->w + (size_t)dx) * 4u));",
                "        const uint32_t *src_row = (const uint32_t *)(const void *)(tex->pixels + ((size_t)src_y * (size_t)tex->w * 4u));",
                "        for (int col = 0; col < cw; ++col) {",
                "            int src_x = sx + (int)((((int64_t)(col + copy_x0)) * (int64_t)sw) / (int64_t)dw);",
                "            dst_px[col] = src_row[src_x];",
                "        }",
                "    }",
                "    rr->frame_rgba_dirty = 1u;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_renderer_supports_shaders(void *renderer) {",
                "    CPUHostGlfwRenderer *rr = (CPUHostGlfwRenderer *)renderer;",
                "    if (cpu_host_hal_glfw_inited == 0u) return 0;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return 0;",
                "    if (rr == NULL || rr->window == NULL) return 0;",
                "    glfwMakeContextCurrent(rr->window);",
                "    return (cpu_host_hal_glfw_load_gl() == 0) ? 1 : 0;",
                "}",
                "",
                "static GLuint cpu_host_hal_glfw_compile_shader(GLenum type, const char *source) {",
                "    GLuint shader;",
                "    GLint ok = 0;",
                "    if (source == NULL || source[0] == '\\0') return 0u;",
                "    shader = cpu_glCreateShader(type);",
                "    if (shader == 0u) return 0u;",
                "    cpu_glShaderSource(shader, 1, (const GLchar * const *)&source, NULL);",
                "    cpu_glCompileShader(shader);",
                "    cpu_glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);",
                "    if (ok == 0) {",
                "        cpu_glDeleteShader(shader);",
                "        return 0u;",
                "    }",
                "    return shader;",
                "}",
                "",
                "static void *cpu_host_hal_shader_create(void *renderer, const char *vertex_source, const char *fragment_source) {",
                "    CPUHostGlfwRenderer *rr = (CPUHostGlfwRenderer *)renderer;",
                "    CPUHostGlfwShader *shader;",
                "    GLint ok = 0;",
                "    static const GLfloat quad[] = {",
                "        -1.0f, -1.0f, 0.0f, 1.0f, 0.0f, 1.0f,",
                "         1.0f, -1.0f, 0.0f, 1.0f, 1.0f, 1.0f,",
                "        -1.0f,  1.0f, 0.0f, 1.0f, 0.0f, 0.0f,",
                "         1.0f,  1.0f, 0.0f, 1.0f, 1.0f, 0.0f",
                "    };",
                "    if (rr == NULL || rr->window == NULL) return NULL;",
                "    glfwMakeContextCurrent(rr->window);",
                "    if (cpu_host_hal_glfw_load_gl() != 0) return NULL;",
                "    shader = (CPUHostGlfwShader *)calloc(1u, sizeof(*shader));",
                "    if (shader == NULL) return NULL;",
                "    shader->vertex_shader = cpu_host_hal_glfw_compile_shader(GL_VERTEX_SHADER, vertex_source);",
                "    shader->fragment_shader = cpu_host_hal_glfw_compile_shader(GL_FRAGMENT_SHADER, fragment_source);",
                "    if (shader->vertex_shader == 0u || shader->fragment_shader == 0u) {",
                "        cpu_host_hal_shader_destroy(shader);",
                "        return NULL;",
                "    }",
                "    shader->program = cpu_glCreateProgram();",
                "    if (shader->program == 0u) {",
                "        cpu_host_hal_shader_destroy(shader);",
                "        return NULL;",
                "    }",
                "    cpu_glAttachShader(shader->program, shader->vertex_shader);",
                "    cpu_glAttachShader(shader->program, shader->fragment_shader);",
                "    cpu_glLinkProgram(shader->program);",
                "    cpu_glGetProgramiv(shader->program, GL_LINK_STATUS, &ok);",
                "    if (ok == 0) {",
                "        cpu_host_hal_shader_destroy(shader);",
                "        return NULL;",
                "    }",
                "    if (cpu_glGenVertexArrays != NULL) cpu_glGenVertexArrays(1, &shader->vao);",
                "    cpu_glGenBuffers(1, &shader->vbo);",
                "    if (cpu_glBindVertexArray != NULL && shader->vao != 0u) cpu_glBindVertexArray(shader->vao);",
                "    cpu_glBindBuffer(GL_ARRAY_BUFFER, shader->vbo);",
                "    cpu_glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)sizeof(quad), quad, GL_STATIC_DRAW);",
                "    cpu_glEnableVertexAttribArray(0u);",
                "    cpu_glVertexAttribPointer(0u, 4, GL_FLOAT, GL_FALSE, (GLsizei)(6u * sizeof(GLfloat)), (const void *)0);",
                "    cpu_glEnableVertexAttribArray(1u);",
                "    cpu_glVertexAttribPointer(1u, 2, GL_FLOAT, GL_FALSE, (GLsizei)(6u * sizeof(GLfloat)), (const void *)(4u * sizeof(GLfloat)));",
                "    if (cpu_glBindVertexArray != NULL && shader->vao != 0u) cpu_glBindVertexArray(0u);",
                "    cpu_glGenTextures(1, &shader->texture);",
                "    cpu_glBindTexture(GL_TEXTURE_2D, shader->texture);",
                "    cpu_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);",
                "    cpu_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);",
                "    cpu_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);",
                "    cpu_glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);",
                "    return shader;",
                "}",
                "",
                "static void cpu_host_hal_shader_destroy(void *shader) {",
                "    CPUHostGlfwShader *ss = (CPUHostGlfwShader *)shader;",
                "    if (ss == NULL) return;",
                "    if (cpu_host_hal_glfw_gl_loaded != 0u) {",
                "        if (ss->texture != 0u) cpu_glDeleteTextures(1, &ss->texture);",
                "        if (ss->vbo != 0u) cpu_glDeleteBuffers(1, &ss->vbo);",
                "        if (ss->vao != 0u && cpu_glDeleteVertexArrays != NULL) cpu_glDeleteVertexArrays(1, &ss->vao);",
                "        if (ss->program != 0u) cpu_glDeleteProgram(ss->program);",
                "        if (ss->vertex_shader != 0u) cpu_glDeleteShader(ss->vertex_shader);",
                "        if (ss->fragment_shader != 0u) cpu_glDeleteShader(ss->fragment_shader);",
                "    }",
                "    free(ss);",
                "}",
                "",
                "static int cpu_host_hal_render_copy_shader(void *renderer, void *texture, const CPUHostRect *src_rect, const CPUHostRect *dst_rect, void *shader, int texture_w, int texture_h, int output_w, int output_h) {",
                "    CPUHostGlfwRenderer *rr = (CPUHostGlfwRenderer *)renderer;",
                "    CPUHostGlfwTexture *tex = (CPUHostGlfwTexture *)texture;",
                "    CPUHostGlfwShader *ss = (CPUHostGlfwShader *)shader;",
                "    GLfloat mvp[16] = {",
                "        1.0f, 0.0f, 0.0f, 0.0f,",
                "        0.0f, 1.0f, 0.0f, 0.0f,",
                "        0.0f, 0.0f, 1.0f, 0.0f,",
                "        0.0f, 0.0f, 0.0f, 1.0f",
                "    };",
                "    GLint loc;",
                "    int dx = 0;",
                "    int dy = 0;",
                "    int dw = output_w;",
                "    int dh = output_h;",
                "    (void)src_rect;",
                "    if (rr == NULL || rr->window == NULL || tex == NULL || tex->pixels == NULL || ss == NULL) return -1;",
                "    if (texture_w <= 0) texture_w = tex->w;",
                "    if (texture_h <= 0) texture_h = tex->h;",
                "    if (output_w <= 0 || output_h <= 0 || texture_w <= 0 || texture_h <= 0) return -1;",
                "    if (dst_rect != NULL) {",
                "        dx = dst_rect->x;",
                "        dy = dst_rect->y;",
                "        dw = dst_rect->w;",
                "        dh = dst_rect->h;",
                "    }",
                "    if (dw <= 0 || dh <= 0) return -1;",
                "    glfwMakeContextCurrent(rr->window);",
                "    if (cpu_host_hal_glfw_load_gl() != 0) return -1;",
                "    cpu_glViewport(0, 0, output_w, output_h);",
                "    cpu_glClearColor(0.0f, 0.0f, 0.0f, 1.0f);",
                "    cpu_glClear(GL_COLOR_BUFFER_BIT);",
                "    cpu_glViewport(dx, output_h - dy - dh, dw, dh);",
                "    cpu_glUseProgram(ss->program);",
                "    cpu_glActiveTexture(GL_TEXTURE0);",
                "    cpu_glBindTexture(GL_TEXTURE_2D, ss->texture);",
                "    if (ss->texture_w != texture_w || ss->texture_h != texture_h) {",
                "        cpu_glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, texture_w, texture_h, 0, GL_BGRA, GL_UNSIGNED_BYTE, tex->pixels);",
                "        ss->texture_w = texture_w;",
                "        ss->texture_h = texture_h;",
                "    } else {",
                "        cpu_glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, texture_w, texture_h, GL_BGRA, GL_UNSIGNED_BYTE, tex->pixels);",
                "    }",
                "    loc = cpu_glGetUniformLocation(ss->program, \"Texture\");",
                "    if (loc >= 0) cpu_glUniform1i(loc, 0);",
                "    loc = cpu_glGetUniformLocation(ss->program, \"screenTexture\");",
                "    if (loc >= 0) cpu_glUniform1i(loc, 0);",
                "    loc = cpu_glGetUniformLocation(ss->program, \"TextureSize\");",
                "    if (loc >= 0) cpu_glUniform2f(loc, (GLfloat)texture_w, (GLfloat)texture_h);",
                "    loc = cpu_glGetUniformLocation(ss->program, \"sourceResolution\");",
                "    if (loc >= 0) cpu_glUniform2f(loc, (GLfloat)texture_w, (GLfloat)texture_h);",
                "    loc = cpu_glGetUniformLocation(ss->program, \"OutputSize\");",
                "    if (loc >= 0) cpu_glUniform2f(loc, (GLfloat)output_w, (GLfloat)output_h);",
                "    loc = cpu_glGetUniformLocation(ss->program, \"MVPMatrix\");",
                "    if (loc >= 0) cpu_glUniformMatrix4fv(loc, 1, GL_FALSE, mvp);",
                "    if (cpu_glBindVertexArray != NULL && ss->vao != 0u) cpu_glBindVertexArray(ss->vao);",
                "    cpu_glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);",
                "    if (cpu_glBindVertexArray != NULL && ss->vao != 0u) cpu_glBindVertexArray(0u);",
                "    cpu_glUseProgram(0u);",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_poll_event(CPUHostEvent *event) {",
                "    int key;",
                "    if (!event) return 0;",
                "    if (cpu_host_hal_glfw_inited == 0u) return 0;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0;",
                "    glfwPollEvents();",
                "    if (cpu_host_hal_glfw_primary_window != NULL &&",
                "        glfwWindowShouldClose(cpu_host_hal_glfw_primary_window) != 0 &&",
                "        cpu_host_hal_glfw_quit_emitted == 0u) {",
                "        event->type = CPU_HOST_EVENT_QUIT;",
                "        event->key.repeat = 0u;",
                "        event->key.mod_state = 0u;",
                "        event->key.keysym.scancode = 0u;",
                "        cpu_host_hal_glfw_quit_emitted = 1u;",
                "        return 1;",
                "    }",
                "    if (cpu_host_hal_glfw_primary_window == NULL) return 0;",
                "    while (cpu_host_hal_glfw_poll_cursor < CPU_GLFW_SC_COUNT) {",
                "        int sc = cpu_host_hal_glfw_poll_cursor++;",
                "        int glfw_key = cpu_host_hal_glfw_key_for_scancode(sc);",
                "        uint8_t down = 0u;",
                "        if (glfw_key >= 0) {",
                "            key = glfwGetKey(cpu_host_hal_glfw_primary_window, glfw_key);",
                "            down = (uint8_t)((key == GLFW_PRESS || key == GLFW_REPEAT) ? 1u : 0u);",
                "        }",
                "        if (down != cpu_host_hal_glfw_prev_keys[sc]) {",
                "            cpu_host_hal_glfw_prev_keys[sc] = down;",
                "            cpu_host_hal_glfw_hold_ticks[sc] = (uint16_t)(down != 0u ? 1u : 0u);",
                "            event->type = (down != 0u) ? CPU_HOST_EVENT_KEYDOWN : CPU_HOST_EVENT_KEYUP;",
                "            event->key.repeat = 0u;",
                "            event->key.keysym.scancode = (uint32_t)sc;",
                "            cpu_host_hal_glfw_event_mod_state = cpu_host_hal_glfw_mod_state();",
                "            event->key.mod_state = cpu_host_hal_glfw_event_mod_state;",
                "            return 1;",
                "        }",
                "        if (down != 0u) {",
                "            uint16_t held = cpu_host_hal_glfw_hold_ticks[sc];",
                "            if (held < 0xFFFFu) held = (uint16_t)(held + 1u);",
                "            cpu_host_hal_glfw_hold_ticks[sc] = held;",
                "            if (held > 18u && (((uint16_t)(held - 18u) % 3u) == 0u)) {",
                "                event->type = CPU_HOST_EVENT_KEYDOWN;",
                "                event->key.repeat = 1u;",
                "                event->key.keysym.scancode = (uint32_t)sc;",
                "                cpu_host_hal_glfw_event_mod_state = cpu_host_hal_glfw_mod_state();",
                "                event->key.mod_state = cpu_host_hal_glfw_event_mod_state;",
                "                return 1;",
                "            }",
                "        }",
                "    }",
                "    cpu_host_hal_glfw_poll_cursor = 0;",
                "    return 0;",
                "}",
                "",
                "static uint32_t cpu_host_hal_event_type(const CPUHostEvent *event) {",
                "    if (!event) return 0u;",
                "    return event->type;",
                "}",
                "",
                "static int32_t cpu_host_hal_event_scancode(const CPUHostEvent *event) {",
                "    if (!event) return 0;",
                "    if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0;",
                "    return (int32_t)event->key.keysym.scancode;",
                "}",
                "",
                "static int32_t cpu_host_hal_event_keycode(const CPUHostEvent *event) {",
                "    if (!event) return 0;",
                "    if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0;",
                "    return cpu_host_hal_glfw_key_for_scancode((int)event->key.keysym.scancode);",
                "}",
                "",
                "static uint8_t cpu_host_hal_event_key_repeat(const CPUHostEvent *event) {",
                "    if (!event) return 0u;",
                "    if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0u;",
                "    return event->key.repeat;",
                "}",
                "",
                "static uint32_t cpu_host_hal_event_mod_state(const CPUHostEvent *event) {",
                "    if (!event) return cpu_host_hal_glfw_event_mod_state;",
                "    if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return cpu_host_hal_glfw_event_mod_state;",
                "    return event->key.mod_state;",
                "}",
                "",
                "static void cpu_host_hal_set_window_title(void *window, const char *title) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!title) return;",
                "    if (!window) window = (void *)cpu_host_hal_glfw_primary_window;",
                "    if (!window) return;",
                "    glfwSetWindowTitle((GLFWwindow *)window, title);",
                "}",
                "",
                "static void cpu_host_hal_destroy_texture(void *texture) {",
                "    CPUHostGlfwTexture *tex = (CPUHostGlfwTexture *)texture;",
                "    if (!tex) return;",
                "    free(tex->pixels);",
                "    tex->pixels = NULL;",
                "    tex->pixels_len = 0u;",
                "    free(tex);",
                "}",
                "",
                "static void cpu_host_hal_destroy_renderer(void *renderer) {",
                "    CPUHostGlfwRenderer *rr = (CPUHostGlfwRenderer *)renderer;",
                "    if (!rr) return;",
                "    if (cpu_host_hal_glfw_gl_loaded != 0u) {",
                "        if (rr->present_texture != 0u) cpu_glDeleteTextures(1, &rr->present_texture);",
                "        if (rr->present_vbo != 0u) cpu_glDeleteBuffers(1, &rr->present_vbo);",
                "        if (rr->present_vao != 0u && cpu_glDeleteVertexArrays != NULL) cpu_glDeleteVertexArrays(1, &rr->present_vao);",
                "        if (rr->present_program != 0u) cpu_glDeleteProgram(rr->present_program);",
                "        if (rr->present_vertex_shader != 0u) cpu_glDeleteShader(rr->present_vertex_shader);",
                "        if (rr->present_fragment_shader != 0u) cpu_glDeleteShader(rr->present_fragment_shader);",
                "    }",
                "    free(rr->frame_rgba);",
                "    rr->frame_rgba = NULL;",
                "    rr->frame_len = 0u;",
                "    free(rr);",
                "}",
                "",
                "static void cpu_host_hal_destroy_window(void *window) {",
                "    if (!window) return;",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if (cpu_host_hal_glfw_primary_window == (GLFWwindow *)window) {",
                "        cpu_host_hal_glfw_primary_window = NULL;",
                "        cpu_host_hal_glfw_reset_input_state();",
                "    }",
                "    glfwDestroyWindow((GLFWwindow *)window);",
                "}",
                "",
                "static void cpu_host_hal_audio_close(uint32_t dev) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "    if (dev == 0u || cpu_host_hal_glfw_audio_opened == 0u) return;",
                "    cpu_host_hal_glfw_reset_audio_state();",
                "}",
                "",
                "static void cpu_host_hal_quit_subsystems(void) {",
                "    if (cpu_host_hal_glfw_inited != 0u && cpu_host_hal_glfw_primary_window != NULL) {",
                "        glfwDestroyWindow(cpu_host_hal_glfw_primary_window);",
                "        cpu_host_hal_glfw_primary_window = NULL;",
                "    }",
                "    cpu_host_hal_glfw_reset_audio_state();",
                "    cpu_host_hal_glfw_reset_input_state();",
                "    cpu_host_hal_glfw_subsystems = 0u;",
                "}",
                "",
                "static void cpu_host_hal_quit(void) {",
                "    cpu_host_hal_glfw_reset_audio_state();",
                "    if (cpu_host_hal_glfw_inited != 0u && cpu_host_hal_glfw_primary_window != NULL) {",
                "        glfwDestroyWindow(cpu_host_hal_glfw_primary_window);",
                "        cpu_host_hal_glfw_primary_window = NULL;",
                "    }",
                "    cpu_host_hal_glfw_reset_input_state();",
                "    cpu_host_hal_glfw_subsystems = 0u;",
                "    if (cpu_host_hal_glfw_inited != 0u) {",
                "        glfwTerminate();",
                "        cpu_host_hal_glfw_inited = 0u;",
                "    }",
                "}",
                "",
                "static int cpu_host_hal_init(uint32_t flags) {",
                "    if ((flags & ~(CPU_HOST_INIT_VIDEO | CPU_HOST_INIT_AUDIO | CPU_HOST_INIT_EVENTS)) != 0u) return -1;",
                "    if (cpu_host_hal_glfw_inited == 0u) {",
                "        if ((flags & CPU_HOST_INIT_VIDEO) != 0u) {",
                "            if (!glfwInit()) {",
                "                cpu_host_hal_log(\"host_init video unavailable; continuing without GLFW window path\");",
                "            } else {",
                "                cpu_host_hal_glfw_inited = 1u;",
                "            }",
                "        } else {",
                "            cpu_host_hal_glfw_inited = 1u;",
                "        }",
                "    }",
                "    cpu_host_hal_glfw_subsystems |= flags;",
                "    return 0;",
                "}",
                "",
                "static uint32_t cpu_host_hal_isqrt_u32(uint32_t value) {",
                "    uint32_t result = 0u;",
                "    uint32_t bit = 1u << 30;",
                "    while (bit > value) bit >>= 2;",
                "    while (bit != 0u) {",
                "        if (value >= result + bit) {",
                "            value -= result + bit;",
                "            result = (result >> 1) + bit;",
                "        } else {",
                "            result >>= 1;",
                "        }",
                "        bit >>= 2;",
                "    }",
                "    return result;",
                "}",
                "",
                "static void cpu_host_hal_display_window_size(uint32_t display_w, uint32_t display_h, uint32_t aspect_w, uint32_t aspect_h, uint32_t inches, int fallback_w, int fallback_h, int *out_w, int *out_h) {",
                "    uint64_t diag;",
                "    uint64_t target_w;",
                "    uint64_t target_h;",
                "    uint64_t max_w;",
                "    uint64_t max_h;",
                "    if (aspect_w == 0u || aspect_h == 0u) { aspect_w = (fallback_w > 0) ? (uint32_t)fallback_w : 4u; aspect_h = (fallback_h > 0) ? (uint32_t)fallback_h : 3u; }",
                "    if (display_w == 0u) display_w = (fallback_w > 0) ? (uint32_t)fallback_w : 640u;",
                "    if (display_h == 0u) display_h = (fallback_h > 0) ? (uint32_t)fallback_h : 480u;",
                "    max_w = display_w;",
                "    max_h = ((uint64_t)display_w * (uint64_t)aspect_h) / (uint64_t)aspect_w;",
                "    if (max_h == 0u || max_h > display_h) {",
                "        max_h = display_h;",
                "        max_w = ((uint64_t)display_h * (uint64_t)aspect_w) / (uint64_t)aspect_h;",
                "    }",
                "    if (max_w == 0u) max_w = display_w;",
                "    if (max_h == 0u) max_h = display_h;",
                "    diag = (uint64_t)cpu_host_hal_isqrt_u32((uint32_t)(aspect_w * aspect_w + aspect_h * aspect_h));",
                "    if (diag == 0u) diag = 5u;",
                "    if (inches == 0u) inches = 14u;",
                "    target_w = ((uint64_t)inches * 48u * (uint64_t)aspect_w) / diag;",
                "    target_h = ((uint64_t)inches * 48u * (uint64_t)aspect_h) / diag;",
                "    if (target_w == 0u || target_h == 0u) { target_w = max_w; target_h = max_h; }",
                "    if (target_w > max_w) { target_w = max_w; target_h = (target_w * (uint64_t)aspect_h) / (uint64_t)aspect_w; }",
                "    if (target_h > max_h) { target_h = max_h; target_w = (target_h * (uint64_t)aspect_w) / (uint64_t)aspect_h; }",
                "    if (target_w < 160u) { target_w = 160u; target_h = (target_w * (uint64_t)aspect_h) / (uint64_t)aspect_w; }",
                "    if (target_h < 120u) { target_h = 120u; target_w = (target_h * (uint64_t)aspect_w) / (uint64_t)aspect_h; }",
                "    if (out_w) *out_w = (int)((target_w > 0u) ? target_w : 640u);",
                "    if (out_h) *out_h = (int)((target_h > 0u) ? target_h : 480u);",
                "}",
                "",
                "static void *cpu_host_hal_create_window(const char *title, int x, int y, int w, int h, uint32_t flags) {",
                "    GLFWwindow *window = NULL;",
                "    const char *win_title = (title && title[0] != '\\0') ? title : \"PASM\";",
                "    if (cpu_host_hal_glfw_inited == 0u) return NULL;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return NULL;",
                "    (void)x;",
                "    (void)y;",
                "    if ((flags & ~CPU_HOST_WINDOW_RESIZABLE) != 0u) return NULL;",
                "    if (w <= 0) w = 640;",
                "    if (h <= 0) h = 480;",
                "    glfwWindowHint(GLFW_RESIZABLE, (flags & CPU_HOST_WINDOW_RESIZABLE) != 0u ? GLFW_TRUE : GLFW_FALSE);",
                "    window = glfwCreateWindow(w, h, win_title, NULL, NULL);",
                "    if (window != NULL) {",
                "        glfwMakeContextCurrent(window);",
                "        glfwSwapInterval(0);",
                "        (void)cpu_host_hal_glfw_load_gl();",
                "    }",
                "    if (window != NULL && cpu_host_hal_glfw_primary_window == NULL) {",
                "        cpu_host_hal_glfw_primary_window = window;",
                "        cpu_host_hal_glfw_reset_input_state();",
                "    }",
                "    return (void *)window;",
                "}",
                "",
                "static void *cpu_host_hal_create_renderer(void *window, int index, uint32_t flags) {",
                "    CPUHostGlfwRenderer *rr;",
                "    if (cpu_host_hal_glfw_inited == 0u) return NULL;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return NULL;",
                "    if (!window) window = (void *)cpu_host_hal_glfw_primary_window;",
                "    if (!window) return NULL;",
                "    (void)index;",
                "    if ((flags & ~CPU_HOST_RENDERER_ACCELERATED) != 0u) return NULL;",
                "    rr = (CPUHostGlfwRenderer *)calloc(1u, sizeof(*rr));",
                "    if (!rr) return NULL;",
                "    rr->window = (GLFWwindow *)window;",
                "    rr->clear_color = 0xFF000000u;",
                "    if (cpu_host_hal_glfw_renderer_sync_size(rr) != 0) {",
                "        free(rr);",
                "        return NULL;",
                "    }",
                "    return rr;",
                "}",
                "",
                "static void *cpu_host_hal_create_texture(void *renderer, uint32_t format, int access, int w, int h) {",
                "    CPUHostGlfwTexture *tex;",
                "    uint64_t w64;",
                "    uint64_t h64;",
                "    uint64_t need64;",
                "    size_t need;",
                "    if (cpu_host_hal_glfw_inited == 0u) return NULL;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return NULL;",
                "    if (!renderer || w <= 0 || h <= 0) return NULL;",
                "    if (format != CPU_HOST_PIXELFORMAT_ARGB8888) return NULL;",
                "    if (access != CPU_HOST_TEXTUREACCESS_STREAMING) return NULL;",
                "    tex = (CPUHostGlfwTexture *)calloc(1u, sizeof(*tex));",
                "    if (!tex) return NULL;",
                "    tex->w = w;",
                "    tex->h = h;",
                "    w64 = (uint64_t)(uint32_t)w;",
                "    h64 = (uint64_t)(uint32_t)h;",
                "    if (w64 != 0u && h64 > (0xFFFFFFFFFFFFFFFFu / w64)) {",
                "        free(tex);",
                "        return NULL;",
                "    }",
                "    need64 = w64 * h64;",
                "    if (need64 > (0xFFFFFFFFFFFFFFFFu / 4u)) {",
                "        free(tex);",
                "        return NULL;",
                "    }",
                "    need64 *= 4u;",
                "    if (need64 == 0u || need64 > (uint64_t)SIZE_MAX) {",
                "        free(tex);",
                "        return NULL;",
                "    }",
                "    need = (size_t)need64;",
                "    tex->pixels = (uint8_t *)calloc(need, 1u);",
                "    if (!tex->pixels) {",
                "        free(tex);",
                "        return NULL;",
                "    }",
                "    tex->pixels_len = need;",
                "    return tex;",
                "}",
                "",
                "static uint32_t cpu_host_hal_audio_open(const char *device, int iscapture, const CPUHostAudioSpec *want, CPUHostAudioSpec *have, int allowed_changes) {",
                "    uint64_t bytes64;",
                "    (void)device;",
                "    (void)allowed_changes;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    if (iscapture != 0) return 0u;",
                "    if (!want) return 0u;",
                "    if (want->freq <= 0 || want->channels == 0u || want->samples == 0u) return 0u;",
                "    cpu_host_hal_glfw_reset_audio_state();",
                "    bytes64 = (uint64_t)want->samples * (uint64_t)want->channels * 2u;",
                "    if (bytes64 < 4096u) bytes64 = 4096u;",
                "    if (bytes64 > 0xFFFFFFFFu || bytes64 > (uint64_t)SIZE_MAX) return 0u;",
                "    cpu_host_hal_glfw_audio_cap = (uint32_t)bytes64;",
                "    cpu_host_hal_glfw_audio_buf = (uint8_t *)calloc((size_t)cpu_host_hal_glfw_audio_cap, 1u);",
                "    if (cpu_host_hal_glfw_audio_buf == NULL) {",
                "        cpu_host_hal_glfw_audio_cap = 0u;",
                "        return 0u;",
                "    }",
                "#if !defined(__linux__)",
                "    {",
                "        CPUHostAudioSpec sdl_want;",
                "        CPUHostAudioSpec sdl_have;",
                "        cpu_host_audio_spec_zero(&sdl_want);",
                "        cpu_host_audio_spec_zero(&sdl_have);",
                "        sdl_want.freq = want->freq;",
                "        sdl_want.format = want->format;",
                "        sdl_want.channels = want->channels;",
                "        sdl_want.samples = want->samples;",
                "        sdl_want.callback = NULL;",
                "        if (cpu_host_hal_glfw_sdl_inited == 0u) {",
                "            if (SDL_Init(SDL_INIT_AUDIO) != 0) {",
                "                (void)SDL_GetError();",
                "            } else {",
                "                cpu_host_hal_glfw_sdl_inited = 1u;",
                "            }",
                "        }",
                "        cpu_host_hal_glfw_sdl_audio_dev = SDL_OpenAudioDevice(NULL, 0, &sdl_want, &sdl_have, allowed_changes);",
                "        if (cpu_host_hal_glfw_sdl_audio_dev != 0u) {",
                "            if (have) *have = sdl_have;",
                "            cpu_host_hal_glfw_audio_opened = 1u;",
                "            cpu_host_hal_glfw_audio_len = 0u;",
                "            SDL_PauseAudioDevice(cpu_host_hal_glfw_sdl_audio_dev, 0);",
                "            return cpu_host_hal_glfw_sdl_audio_dev;",
                "        } else {",
                "            (void)SDL_GetError();",
                "        }",
                "    }",
                "#endif",
                "#ifdef _WIN32",
                "    {",
                "        WAVEFORMATEX fmt;",
                "        uint32_t i;",
                "        memset(&fmt, 0, sizeof(fmt));",
                "        fmt.wFormatTag = WAVE_FORMAT_PCM;",
                "        fmt.nChannels = (WORD)want->channels;",
                "        fmt.nSamplesPerSec = (DWORD)want->freq;",
                "        fmt.wBitsPerSample = 16u;",
                "        fmt.nBlockAlign = (WORD)(fmt.nChannels * (fmt.wBitsPerSample / 8u));",
                "        fmt.nAvgBytesPerSec = fmt.nSamplesPerSec * fmt.nBlockAlign;",
                "        cpu_host_hal_glfw_wave_buffer_bytes = cpu_host_hal_glfw_audio_cap;",
                "        if (waveOutOpen(&cpu_host_hal_glfw_waveout, WAVE_MAPPER, &fmt, 0, 0, CALLBACK_NULL) != MMSYSERR_NOERROR) {",
                "            cpu_host_hal_glfw_waveout = NULL;",
                "        } else {",
                "            for (i = 0u; i < 4u; ++i) {",
                "                cpu_host_hal_glfw_wave_buffers[i] = (uint8_t *)calloc((size_t)cpu_host_hal_glfw_wave_buffer_bytes, 1u);",
                "                if (!cpu_host_hal_glfw_wave_buffers[i]) {",
                "                    cpu_host_hal_glfw_reset_audio_state();",
                "                    return 0u;",
                "                }",
                "            }",
                "        }",
                "    }",
                "#endif",
                "#ifdef __linux__",
                "    {",
                "        unsigned int rate;",
                "        uint8_t opened_live_pcm = 0u;",
                "        const char *alsa_candidates[] = {",
                "                (device && device[0] != '\\0') ? device : NULL,",
                "                \"default\",",
                "                \"pipewire\",",
                "                \"sysdefault\",",
                "                \"plughw:0,0\",",
                "                \"hw:0,0\",",
                "            };",
                "        size_t cand_count = sizeof(alsa_candidates) / sizeof(alsa_candidates[0]);",
                "        size_t cand_idx;",
                "        for (cand_idx = 0u; cand_idx < cand_count; ++cand_idx) {",
                "            const char *pcm_name = alsa_candidates[cand_idx];",
                "            if (pcm_name == NULL) continue;",
                "            {",
                "                int pcm_open_rc = snd_pcm_open(&cpu_host_hal_glfw_alsa_pcm, pcm_name, SND_PCM_STREAM_PLAYBACK, 0);",
                "                if (pcm_open_rc < 0) {",
                "                    (void)snd_strerror(pcm_open_rc);",
                "                    continue;",
                "                }",
                "                rate = (unsigned int)want->freq;",
                "                if (snd_pcm_set_params(",
                "                        cpu_host_hal_glfw_alsa_pcm,",
                "                        SND_PCM_FORMAT_S16_LE,",
                "                        SND_PCM_ACCESS_RW_INTERLEAVED,",
                "                        (unsigned int)want->channels,",
                "                        rate,",
                "                        1,",
                "                        200000u",
                "                    ) < 0) {",
                "                    snd_pcm_close(cpu_host_hal_glfw_alsa_pcm);",
                "                    cpu_host_hal_glfw_alsa_pcm = NULL;",
                "                    continue;",
                "                }",
                "                cpu_host_hal_glfw_alsa_channels = (uint32_t)want->channels;",
                "                opened_live_pcm = 1u;",
                "                break;",
                "            }",
                "        }",
                "        if (opened_live_pcm != 0u) {",
                "            cpu_host_hal_glfw_audio_opened = 1u;",
                "            cpu_host_hal_glfw_audio_len = 0u;",
                "        }",
                "        if (opened_live_pcm == 0u) {",
                "            cpu_host_hal_glfw_reset_audio_state();",
                "            return 0u;",
                "        }",
                "    }",
                "#endif",
                "    if (have) {",
                "        *have = *want;",
                "        if (have->size == 0u && have->samples != 0u && have->channels != 0u) {",
                "            bytes64 = (uint64_t)have->samples * (uint64_t)have->channels * 2u;",
                "            if (bytes64 > 0xFFFFFFFFu) return 0u;",
                "            have->size = (uint32_t)bytes64;",
                "        }",
                "#ifdef _WIN32",
                "        if (cpu_host_hal_glfw_wave_buffer_bytes != 0u) have->size = cpu_host_hal_glfw_wave_buffer_bytes;",
                "#endif",
                "    }",
                "    cpu_host_hal_glfw_audio_opened = 1u;",
                "    cpu_host_hal_glfw_audio_len = 0u;",
                "    return 1u;",
                "}",
                "",
                "static void cpu_host_hal_audio_pause(uint32_t dev, int pause_on) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "    if (dev == 0u || cpu_host_hal_glfw_audio_opened == 0u) return;",
                "#ifdef _WIN32",
                "    if (cpu_host_hal_glfw_waveout != NULL) {",
                "        if (pause_on != 0) waveOutPause(cpu_host_hal_glfw_waveout);",
                "        else waveOutRestart(cpu_host_hal_glfw_waveout);",
                "    }",
                "#elif defined(__linux__)",
                "    if (cpu_host_hal_glfw_alsa_pcm != NULL) {",
                "        if (pause_on != 0) snd_pcm_pause(cpu_host_hal_glfw_alsa_pcm, 1);",
                "        else {",
                "            if (snd_pcm_pause(cpu_host_hal_glfw_alsa_pcm, 0) < 0) snd_pcm_prepare(cpu_host_hal_glfw_alsa_pcm);",
                "        }",
                "    }",
                "#else",
                "    (void)pause_on;",
                "#endif",
                "}",
                "",
                "static void *cpu_host_hal_alloc(size_t size_bytes) {",
                "    return malloc(size_bytes);",
                "}",
                "",
                "static void cpu_host_hal_free(void *ptr) {",
                "    free(ptr);",
                "}",
                "",
                "static void cpu_host_hal_memset(void *dst, int value, size_t size_bytes) {",
                "    if (!dst || size_bytes == 0u) return;",
                "    memset(dst, value, size_bytes);",
                "}",
                "",
                "static const char *cpu_host_hal_getenv(const char *name) {",
                "    if (!name) return NULL;",
                "    return getenv(name);",
                "}",
                "",
                "static const uint8_t *cpu_host_hal_keyboard_state(int *key_count) {",
                    "    if (key_count) *key_count = CPU_GLFW_SC_COUNT;",
                "    if (cpu_host_hal_glfw_inited == 0u) {",
                "        memset(cpu_host_hal_glfw_keys, 0, sizeof(cpu_host_hal_glfw_keys));",
                "        return cpu_host_hal_glfw_keys;",
                "    }",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) {",
                "        memset(cpu_host_hal_glfw_keys, 0, sizeof(cpu_host_hal_glfw_keys));",
                "        return cpu_host_hal_glfw_keys;",
                "    }",
                "    if (cpu_host_hal_glfw_primary_window == NULL) {",
                "        memset(cpu_host_hal_glfw_keys, 0, sizeof(cpu_host_hal_glfw_keys));",
                "        return cpu_host_hal_glfw_keys;",
                "    }",
                "    for (int sc = 0; sc < CPU_GLFW_SC_COUNT; ++sc) {",
                "        int glfw_key = cpu_host_hal_glfw_key_for_scancode(sc);",
                "        int key = (glfw_key >= 0) ? glfwGetKey(cpu_host_hal_glfw_primary_window, glfw_key) : 0;",
                "        cpu_host_hal_glfw_keys[sc] = (uint8_t)((key == GLFW_PRESS || key == GLFW_REPEAT) ? 1u : 0u);",
                "    }",
                "    return cpu_host_hal_glfw_keys;",
                "}",
                "",
                "/* Controller/joystick input abstraction (GLFW backend). */",
                "static int cpu_host_hal_glfw_joy_id_for_index(int want_index, int require_gamepad) {",
                "    int idx = 0;",
                "    for (int jid = GLFW_JOYSTICK_1; jid <= GLFW_JOYSTICK_LAST; ++jid) {",
                "        if (!glfwJoystickPresent(jid)) continue;",
                "        if (require_gamepad && !glfwJoystickIsGamepad(jid)) continue;",
                "        if (idx == want_index) return jid;",
                "        idx += 1;",
                "    }",
                "    return -1;",
                "}",
                "",
                "static int cpu_host_hal_gamepad_count(void) {",
                "    int count = 0;",
                "    for (int jid = GLFW_JOYSTICK_1; jid <= GLFW_JOYSTICK_LAST; ++jid) {",
                "        if (!glfwJoystickPresent(jid)) continue;",
                "        if (glfwJoystickIsGamepad(jid)) count += 1;",
                "    }",
                "    return count;",
                "}",
                "",
                "static int cpu_host_hal_gamepad_button(int pad_index, int button_id) {",
                "    int jid = cpu_host_hal_glfw_joy_id_for_index(pad_index, 1);",
                "    GLFWgamepadstate st;",
                "    int gb = -1;",
                "    if (jid < 0) return 0;",
                "    if (!glfwGetGamepadState(jid, &st)) return 0;",
                "    switch (button_id) {",
                "        case 0: gb = GLFW_GAMEPAD_BUTTON_A; break;",
                "        case 1: gb = GLFW_GAMEPAD_BUTTON_B; break;",
                "        case 2: gb = GLFW_GAMEPAD_BUTTON_X; break;",
                "        case 3: gb = GLFW_GAMEPAD_BUTTON_Y; break;",
                "        case 4: gb = GLFW_GAMEPAD_BUTTON_BACK; break;",
                "        case 5: gb = GLFW_GAMEPAD_BUTTON_GUIDE; break;",
                "        case 6: gb = GLFW_GAMEPAD_BUTTON_START; break;",
                "        case 7: gb = GLFW_GAMEPAD_BUTTON_LEFT_THUMB; break;",
                "        case 8: gb = GLFW_GAMEPAD_BUTTON_RIGHT_THUMB; break;",
                "        case 9: gb = GLFW_GAMEPAD_BUTTON_LEFT_BUMPER; break;",
                "        case 10: gb = GLFW_GAMEPAD_BUTTON_RIGHT_BUMPER; break;",
                "        case 11: gb = GLFW_GAMEPAD_BUTTON_DPAD_UP; break;",
                "        case 12: gb = GLFW_GAMEPAD_BUTTON_DPAD_DOWN; break;",
                "        case 13: gb = GLFW_GAMEPAD_BUTTON_DPAD_LEFT; break;",
                "        case 14: gb = GLFW_GAMEPAD_BUTTON_DPAD_RIGHT; break;",
                "        default: gb = -1; break;",
                "    }",
                "    if (gb < 0 || gb >= 15) return 0;",
                "    return (st.buttons[gb] != 0) ? 1 : 0;",
                "}",
                "",
                "static int cpu_host_hal_gamepad_axis(int pad_index, int axis_id) {",
                "    int jid = cpu_host_hal_glfw_joy_id_for_index(pad_index, 1);",
                "    GLFWgamepadstate st;",
                "    int ax = -1;",
                "    float v;",
                "    if (jid < 0) return 0;",
                "    if (!glfwGetGamepadState(jid, &st)) return 0;",
                "    switch (axis_id) {",
                "        case 0: ax = GLFW_GAMEPAD_AXIS_LEFT_X; break;",
                "        case 1: ax = GLFW_GAMEPAD_AXIS_LEFT_Y; break;",
                "        case 2: ax = GLFW_GAMEPAD_AXIS_RIGHT_X; break;",
                "        case 3: ax = GLFW_GAMEPAD_AXIS_RIGHT_Y; break;",
                "        case 4: ax = GLFW_GAMEPAD_AXIS_LEFT_TRIGGER; break;",
                "        case 5: ax = GLFW_GAMEPAD_AXIS_RIGHT_TRIGGER; break;",
                "        default: ax = -1; break;",
                "    }",
                "    if (ax < 0 || ax >= 6) return 0;",
                "    v = st.axes[ax];",
                "    if (v > 1.0f) v = 1.0f;",
                "    if (v < -1.0f) v = -1.0f;",
                "    if (v >= 0.0f) return (int)(v * 32767.0f);",
                "    return (int)(v * 32768.0f);",
                "}",
                "",
                "static int cpu_host_hal_joystick_count(void) {",
                "    int count = 0;",
                "    for (int jid = GLFW_JOYSTICK_1; jid <= GLFW_JOYSTICK_LAST; ++jid) {",
                "        if (glfwJoystickPresent(jid)) count += 1;",
                "    }",
                "    return count;",
                "}",
                "",
                "static int cpu_host_hal_joystick_button(int joy_index, int button) {",
                "    int jid = cpu_host_hal_glfw_joy_id_for_index(joy_index, 0);",
                "    int count = 0;",
                "    const unsigned char *btns;",
                "    if (jid < 0) return 0;",
                "    btns = glfwGetJoystickButtons(jid, &count);",
                "    if (btns == NULL || button < 0 || button >= count) return 0;",
                "    return (btns[button] != 0) ? 1 : 0;",
                "}",
                "",
                "static int cpu_host_hal_joystick_axis(int joy_index, int axis) {",
                "    int jid = cpu_host_hal_glfw_joy_id_for_index(joy_index, 0);",
                "    int count = 0;",
                "    const float *axes;",
                "    float v;",
                "    if (jid < 0) return 0;",
                "    axes = glfwGetJoystickAxes(jid, &count);",
                "    if (axes == NULL || axis < 0 || axis >= count) return 0;",
                "    v = axes[axis];",
                "    if (v > 1.0f) v = 1.0f;",
                "    if (v < -1.0f) v = -1.0f;",
                "    if (v >= 0.0f) return (int)(v * 32767.0f);",
                "    return (int)(v * 32768.0f);",
                "}",
                "",
                "static uint8_t cpu_host_hal_joystick_hat(int joy_index, int hat) {",
                "    int jid = cpu_host_hal_glfw_joy_id_for_index(joy_index, 0);",
                "    int count = 0;",
                "    const unsigned char *hats;",
                "    unsigned char hv;",
                "    uint8_t out = 0u;",
                "    if (jid < 0) return 0u;",
                "    hats = glfwGetJoystickHats(jid, &count);",
                "    if (hats == NULL || hat < 0 || hat >= count) return 0u;",
                "    hv = hats[hat];",
                "    if ((hv & GLFW_HAT_UP) != 0u) out |= CPU_HOST_HAT_UP;",
                "    if ((hv & GLFW_HAT_RIGHT) != 0u) out |= CPU_HOST_HAT_RIGHT;",
                "    if ((hv & GLFW_HAT_DOWN) != 0u) out |= CPU_HOST_HAT_DOWN;",
                "    if ((hv & GLFW_HAT_LEFT) != 0u) out |= CPU_HOST_HAT_LEFT;",
                "    return out;",
                "}",
                "",
                "static int32_t cpu_host_hal_key_from_scancode(int scancode) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return 0;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0;",
                "    return (int32_t)cpu_host_hal_glfw_key_for_scancode(scancode);",
                "}",
                "",
                "static int32_t cpu_host_hal_scancode_from_key(int32_t keycode) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return -1;",
                "    for (int sc = 0; sc < CPU_GLFW_SC_COUNT; ++sc) {",
                "        if ((int32_t)cpu_host_hal_glfw_key_for_scancode(sc) == keycode) return (int32_t)sc;",
                "    }",
                "    return -1;",
                "}",
                "",
                "static void cpu_host_hal_start_text_input(void) {",
                "}",
                "",
                "static void cpu_host_hal_stop_text_input(void) {",
                "}",
                "",
                "static void cpu_host_hal_raise_window(void *window) {",
                "    (void)window;",
                "    /* Do not steal focus implicitly. */",
                "}",
                "",
                "static void cpu_host_hal_show_window(void *window) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!window) window = (void *)cpu_host_hal_glfw_primary_window;",
                "    if (!window) return;",
                "    glfwShowWindow((GLFWwindow *)window);",
                "}",
                "",
                "static int cpu_host_hal_set_window_input_focus(void *window) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!window) window = (void *)cpu_host_hal_glfw_primary_window;",
                "    if (!window) return -1;",
                "    glfwFocusWindow((GLFWwindow *)window);",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_set_texture_blend_none(void *texture) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!texture) return -1;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_init_subsystem(uint32_t flags) {",
                "    if ((flags & ~(CPU_HOST_INIT_VIDEO | CPU_HOST_INIT_AUDIO | CPU_HOST_INIT_EVENTS)) != 0u) return -1;",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    cpu_host_hal_glfw_subsystems |= flags;",
                "    return 0;",
                "}",
                "",
                "static uint32_t cpu_host_hal_audio_dequeue(uint32_t dev, void *data, uint32_t len_bytes) {",
                "    uint32_t n;",
                "    if (cpu_host_hal_glfw_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    if (dev == 0u || !data || len_bytes == 0u || cpu_host_hal_glfw_audio_opened == 0u) return 0u;",
                "#ifdef _WIN32",
                "    if (cpu_host_hal_glfw_waveout != NULL) return 0u;",
                "#endif",
                "    if (cpu_host_hal_glfw_audio_len > cpu_host_hal_glfw_audio_cap) return 0u;",
                "    if (cpu_host_hal_glfw_audio_cap != 0u && cpu_host_hal_glfw_audio_buf == NULL) return 0u;",
                "    if (cpu_host_hal_glfw_audio_len != 0u && cpu_host_hal_glfw_audio_buf == NULL) return 0u;",
                "    n = (cpu_host_hal_glfw_audio_len < len_bytes) ? cpu_host_hal_glfw_audio_len : len_bytes;",
                "    if (n == 0u) return 0u;",
                "    memcpy(data, cpu_host_hal_glfw_audio_buf, (size_t)n);",
                "    cpu_host_hal_glfw_audio_len -= n;",
                "    if (cpu_host_hal_glfw_audio_len != 0u) {",
                "        memmove(",
                "            cpu_host_hal_glfw_audio_buf,",
                "            cpu_host_hal_glfw_audio_buf + n,",
                "            (size_t)cpu_host_hal_glfw_audio_len",
                "        );",
                "    }",
                "    return n;",
                "}",
                "",
                "static int cpu_host_hal_get_window_size(void *window, int *out_w, int *out_h) {",
                "    if (out_w) *out_w = 0;",
                "    if (out_h) *out_h = 0;",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!out_w || !out_h) return -1;",
                "    if (!window) window = (void *)cpu_host_hal_glfw_primary_window;",
                "    if (!window) return -1;",
                "    glfwGetWindowSize((GLFWwindow *)window, out_w, out_h);",
                "    if (*out_w <= 0 || *out_h <= 0) return -1;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_set_window_size(void *window, int w, int h) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (!window) window = (void *)cpu_host_hal_glfw_primary_window;",
                "    if (!window) return -1;",
                "    if (w <= 0 || h <= 0) return -1;",
                "    glfwSetWindowSize((GLFWwindow *)window, w, h);",
                "    return 0;",
                "}",
                "",
                "static const char *cpu_host_hal_scancode_name(int32_t scancode) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return \"UNKNOWN\";",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return \"UNKNOWN\";",
                "    return cpu_host_hal_glfw_scancode_name((int)scancode);",
                "}",
                "",
                "static uint32_t cpu_host_hal_get_mod_state(void) {",
                "    return cpu_host_hal_glfw_mod_state();",
                "}",
                "",
                "static const char *cpu_host_hal_key_name(int32_t keycode) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return \"UNKNOWN\";",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return \"UNKNOWN\";",
                "    return cpu_host_hal_glfw_key_name((int)keycode);",
                "}",
                "",
            ]
        )
        helper_lines.append("/* PASM_SPLIT_END:HOST_HAL_IMPL */")
    else:
        helper_lines.append("/* PASM_SPLIT_BEGIN:HOST_HAL_IMPL */")
        helper_lines.extend(
            [
                "typedef struct {",
                "    int w;",
                "    int h;",
                "    uint8_t focused;",
                "} CPUHostStubWindow;",
                "",
                "typedef struct {",
                "    CPUHostStubWindow *window;",
                "    uint32_t clear_color;",
                "} CPUHostStubRenderer;",
                "",
                "typedef struct {",
                "    int w;",
                "    int h;",
                "} CPUHostStubTexture;",
                "",
                "static uint8_t cpu_host_hal_stub_inited = 0u;",
                "static uint32_t cpu_host_hal_stub_subsystems = 0u;",
                "static CPUHostStubWindow *cpu_host_hal_stub_primary_window = NULL;",
                "static uint8_t *cpu_host_hal_stub_audio_buf = NULL;",
                "static uint32_t cpu_host_hal_stub_audio_len = 0u;",
                "static uint32_t cpu_host_hal_stub_audio_cap = 0u;",
                "static uint8_t cpu_host_hal_stub_audio_opened = 0u;",
                "",
                "static void cpu_host_hal_stub_reset_audio_state(void) {",
                "    free(cpu_host_hal_stub_audio_buf);",
                "    cpu_host_hal_stub_audio_buf = NULL;",
                "    cpu_host_hal_stub_audio_len = 0u;",
                "    cpu_host_hal_stub_audio_cap = 0u;",
                "    cpu_host_hal_stub_audio_opened = 0u;",
                "}",
                "",
                "static void cpu_host_hal_pump_events(void) {",
                "    if (cpu_host_hal_stub_inited == 0u) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return;",
                "}",
                "",
                "static uint32_t cpu_host_hal_ticks_ms(void) {",
                "    if (cpu_host_hal_stub_inited == 0u) return 0u;",
                "    return 0u;",
                "}",
                "",
                "static uint8_t cpu_host_hal_window_has_focus(void *window) {",
                "    CPUHostStubWindow *ww = (window != NULL) ? (CPUHostStubWindow *)window : cpu_host_hal_stub_primary_window;",
                "    if (cpu_host_hal_stub_inited == 0u || ww == NULL) return 0u;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return 0u;",
                "    return ww->focused;",
                "}",
                "",
                "static void cpu_host_hal_render_present(void *renderer) {",
                "    (void)renderer;",
                "    if (cpu_host_hal_stub_inited == 0u) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "}",
                "",
                "static int cpu_host_hal_audio_queue(uint32_t dev, const void *data, uint32_t len_bytes) {",
                "    uint64_t need64;",
                "    uint32_t need;",
                "    uint32_t new_cap;",
                "    uint8_t *new_buf;",
                "    if (cpu_host_hal_stub_inited == 0u) return -1;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return -1;",
                "    if (dev == 0u || !data || len_bytes == 0u || cpu_host_hal_stub_audio_opened == 0u) return -1;",
                "    if (cpu_host_hal_stub_audio_len > cpu_host_hal_stub_audio_cap) return -1;",
                "    if (cpu_host_hal_stub_audio_cap != 0u && cpu_host_hal_stub_audio_buf == NULL) return -1;",
                "    if (cpu_host_hal_stub_audio_len != 0u && cpu_host_hal_stub_audio_buf == NULL) return -1;",
                "    need64 = (uint64_t)cpu_host_hal_stub_audio_len + (uint64_t)len_bytes;",
                "    if (need64 == 0u || need64 > 0xFFFFFFFFu || need64 > (uint64_t)SIZE_MAX) return -1;",
                "    need = (uint32_t)need64;",
                "    if (need > cpu_host_hal_stub_audio_cap) {",
                "        new_cap = (cpu_host_hal_stub_audio_cap == 0u) ? 4096u : cpu_host_hal_stub_audio_cap;",
                "        while (new_cap < need) {",
                "            if (new_cap > 0x7FFFFFFFu) {",
                "                new_cap = need;",
                "                break;",
                "            }",
                "            new_cap <<= 1u;",
                "        }",
                "        if (new_cap < need || (uint64_t)new_cap > (uint64_t)SIZE_MAX) return -1;",
                "        new_buf = (uint8_t *)realloc(cpu_host_hal_stub_audio_buf, (size_t)new_cap);",
                "        if (!new_buf) return -1;",
                "        cpu_host_hal_stub_audio_buf = new_buf;",
                "        cpu_host_hal_stub_audio_cap = new_cap;",
                "    }",
                "    memcpy(",
                "        cpu_host_hal_stub_audio_buf + cpu_host_hal_stub_audio_len,",
                "        data,",
                "        (size_t)len_bytes",
                "    );",
                "    cpu_host_hal_stub_audio_len = need;",
                "    return 0;",
                "}",
                "",
                "static uint32_t cpu_host_hal_audio_queued_bytes(uint32_t dev) {",
                "    if (cpu_host_hal_stub_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    if (dev == 0u || cpu_host_hal_stub_audio_opened == 0u) return 0u;",
                "    if (cpu_host_hal_stub_audio_len > cpu_host_hal_stub_audio_cap) return 0u;",
                "    if (cpu_host_hal_stub_audio_cap != 0u && cpu_host_hal_stub_audio_buf == NULL) return 0u;",
                "    if (cpu_host_hal_stub_audio_len != 0u && cpu_host_hal_stub_audio_buf == NULL) return 0u;",
                "    return cpu_host_hal_stub_audio_len;",
                "}",
                "",
                "static void cpu_host_hal_audio_clear(uint32_t dev) {",
                "    if (cpu_host_hal_stub_inited == 0u) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "    if (dev == 0u || cpu_host_hal_stub_audio_opened == 0u) return;",
                "    if (cpu_host_hal_stub_audio_len > cpu_host_hal_stub_audio_cap) return;",
                "    if (cpu_host_hal_stub_audio_cap != 0u && cpu_host_hal_stub_audio_buf == NULL) return;",
                "    if (cpu_host_hal_stub_audio_len != 0u && cpu_host_hal_stub_audio_buf == NULL) return;",
                "    cpu_host_hal_stub_audio_len = 0u;",
                "}",
                "",
                "static int cpu_host_hal_renderer_output_size(void *renderer, int *out_w, int *out_h) {",
                "    CPUHostStubRenderer *rr = (CPUHostStubRenderer *)renderer;",
                "    if (out_w) *out_w = 0;",
                "    if (out_h) *out_h = 0;",
                "    if (cpu_host_hal_stub_inited == 0u || rr == NULL || rr->window == NULL || !out_w || !out_h) return -1;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (rr->window->w <= 0 || rr->window->h <= 0) return -1;",
                "    *out_w = rr->window->w;",
                "    *out_h = rr->window->h;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_update_texture(void *texture, const CPUHostRect *rect, const void *pixels, int pitch) {",
                "    CPUHostStubTexture *tt = (CPUHostStubTexture *)texture;",
                "    if (cpu_host_hal_stub_inited == 0u) return -1;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (tt == NULL || pixels == NULL || pitch <= 0) return -1;",
                "    if (tt->w <= 0 || tt->h <= 0) return -1;",
                "    if (rect != NULL) {",
                "        if (rect->x < 0 || rect->y < 0 || rect->w <= 0 || rect->h <= 0) return -1;",
                "    }",
                "    return 0;",
                "}",
                "",
                "static void cpu_host_hal_render_set_draw_color(void *renderer, uint8_t r, uint8_t g, uint8_t b, uint8_t a) {",
                "    CPUHostStubRenderer *rr = (CPUHostStubRenderer *)renderer;",
                "    if (cpu_host_hal_stub_inited == 0u || rr == NULL) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    rr->clear_color = ((uint32_t)a << 24) | ((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)b;",
                "}",
                "",
                "static int cpu_host_hal_render_clear(void *renderer) {",
                "    CPUHostStubRenderer *rr = (CPUHostStubRenderer *)renderer;",
                "    if (cpu_host_hal_stub_inited == 0u || rr == NULL) return -1;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_render_copy(void *renderer, void *texture, const CPUHostRect *src_rect, const CPUHostRect *dst_rect) {",
                "    CPUHostStubRenderer *rr = (CPUHostStubRenderer *)renderer;",
                "    CPUHostStubTexture *tt = (CPUHostStubTexture *)texture;",
                "    if (cpu_host_hal_stub_inited == 0u || rr == NULL || tt == NULL) return -1;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (src_rect != NULL && (src_rect->w <= 0 || src_rect->h <= 0)) return -1;",
                "    if (dst_rect != NULL && (dst_rect->w <= 0 || dst_rect->h <= 0)) return -1;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_renderer_supports_shaders(void *renderer) {",
                "    (void)renderer;",
                "    return 0;",
                "}",
                "",
                "static void *cpu_host_hal_shader_create(void *renderer, const char *vertex_source, const char *fragment_source) {",
                "    (void)renderer;",
                "    (void)vertex_source;",
                "    (void)fragment_source;",
                "    return NULL;",
                "}",
                "",
                "static void cpu_host_hal_shader_destroy(void *shader) {",
                "    (void)shader;",
                "}",
                "",
                "static int cpu_host_hal_render_copy_shader(void *renderer, void *texture, const CPUHostRect *src_rect, const CPUHostRect *dst_rect, void *shader, int texture_w, int texture_h, int output_w, int output_h) {",
                "    (void)texture_w;",
                "    (void)texture_h;",
                "    (void)output_w;",
                "    (void)output_h;",
                "    if (shader == NULL) return -1;",
                "    return cpu_host_hal_render_copy(renderer, texture, src_rect, dst_rect);",
                "}",
                "",
                "static int cpu_host_hal_poll_event(CPUHostEvent *event) {",
                "    (void)event;",
                "    if (cpu_host_hal_stub_inited == 0u) return 0;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0;",
                "    return 0;",
                "}",
                "",
                "static uint32_t cpu_host_hal_event_type(const CPUHostEvent *event) {",
                "    (void)event;",
                "    return 0u;",
                "}",
                "",
                "static int32_t cpu_host_hal_event_scancode(const CPUHostEvent *event) {",
                "    (void)event;",
                "    return 0;",
                "}",
                "",
                "static int32_t cpu_host_hal_event_keycode(const CPUHostEvent *event) {",
                "    (void)event;",
                "    return 0;",
                "}",
                "",
                "static uint8_t cpu_host_hal_event_key_repeat(const CPUHostEvent *event) {",
                "    (void)event;",
                "    return 0u;",
                "}",
                "",
                "static uint32_t cpu_host_hal_event_mod_state(const CPUHostEvent *event) {",
                "    (void)event;",
                "    return 0u;",
                "}",
                "",
                "static void cpu_host_hal_set_window_title(void *window, const char *title) {",
                "    (void)title;",
                "    CPUHostStubWindow *ww = (window != NULL) ? (CPUHostStubWindow *)window : cpu_host_hal_stub_primary_window;",
                "    if (cpu_host_hal_stub_inited == 0u || ww == NULL) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "}",
                "",
                "static void cpu_host_hal_destroy_texture(void *texture) {",
                "    if (cpu_host_hal_stub_inited == 0u) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (texture == NULL) return;",
                "    free(texture);",
                "}",
                "",
                "static void cpu_host_hal_destroy_renderer(void *renderer) {",
                "    if (cpu_host_hal_stub_inited == 0u) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (renderer == NULL) return;",
                "    free(renderer);",
                "}",
                "",
                "static void cpu_host_hal_destroy_window(void *window) {",
                "    if (cpu_host_hal_stub_inited == 0u) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (window == NULL) return;",
                "    if (cpu_host_hal_stub_primary_window == (CPUHostStubWindow *)window) {",
                "        cpu_host_hal_stub_primary_window = NULL;",
                "    }",
                "    free(window);",
                "}",
                "",
                "static void cpu_host_hal_audio_close(uint32_t dev) {",
                "    if (cpu_host_hal_stub_inited == 0u) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "    if (dev == 0u || cpu_host_hal_stub_audio_opened == 0u) return;",
                "    cpu_host_hal_stub_reset_audio_state();",
                "}",
                "",
                "static void cpu_host_hal_quit_subsystems(void) {",
                "    cpu_host_hal_stub_reset_audio_state();",
                "    if (cpu_host_hal_stub_primary_window != NULL) {",
                "        free(cpu_host_hal_stub_primary_window);",
                "        cpu_host_hal_stub_primary_window = NULL;",
                "    }",
                "    cpu_host_hal_stub_subsystems = 0u;",
                "}",
                "",
                "static void cpu_host_hal_quit(void) {",
                "    cpu_host_hal_stub_reset_audio_state();",
                "    if (cpu_host_hal_stub_primary_window != NULL) {",
                "        free(cpu_host_hal_stub_primary_window);",
                "        cpu_host_hal_stub_primary_window = NULL;",
                "    }",
                "    cpu_host_hal_stub_subsystems = 0u;",
                "    cpu_host_hal_stub_inited = 0u;",
                "}",
                "",
                "static int cpu_host_hal_init(uint32_t flags) {",
                "    if ((flags & ~(CPU_HOST_INIT_VIDEO | CPU_HOST_INIT_AUDIO | CPU_HOST_INIT_EVENTS)) != 0u) return -1;",
                "    cpu_host_hal_stub_inited = 1u;",
                "    cpu_host_hal_stub_subsystems |= flags;",
                "    return 0;",
                "}",
                "",
                "static uint32_t cpu_host_hal_isqrt_u32(uint32_t value) {",
                "    uint32_t result = 0u;",
                "    uint32_t bit = 1u << 30;",
                "    while (bit > value) bit >>= 2;",
                "    while (bit != 0u) {",
                "        if (value >= result + bit) {",
                "            value -= result + bit;",
                "            result = (result >> 1) + bit;",
                "        } else {",
                "            result >>= 1;",
                "        }",
                "        bit >>= 2;",
                "    }",
                "    return result;",
                "}",
                "",
                "static void cpu_host_hal_display_window_size(uint32_t display_w, uint32_t display_h, uint32_t aspect_w, uint32_t aspect_h, uint32_t inches, int fallback_w, int fallback_h, int *out_w, int *out_h) {",
                "    uint64_t diag;",
                "    uint64_t target_w;",
                "    uint64_t target_h;",
                "    uint64_t max_w;",
                "    uint64_t max_h;",
                "    if (aspect_w == 0u || aspect_h == 0u) { aspect_w = (fallback_w > 0) ? (uint32_t)fallback_w : 4u; aspect_h = (fallback_h > 0) ? (uint32_t)fallback_h : 3u; }",
                "    if (display_w == 0u) display_w = (fallback_w > 0) ? (uint32_t)fallback_w : 640u;",
                "    if (display_h == 0u) display_h = (fallback_h > 0) ? (uint32_t)fallback_h : 480u;",
                "    max_w = display_w;",
                "    max_h = ((uint64_t)display_w * (uint64_t)aspect_h) / (uint64_t)aspect_w;",
                "    if (max_h == 0u || max_h > display_h) {",
                "        max_h = display_h;",
                "        max_w = ((uint64_t)display_h * (uint64_t)aspect_w) / (uint64_t)aspect_h;",
                "    }",
                "    if (max_w == 0u) max_w = display_w;",
                "    if (max_h == 0u) max_h = display_h;",
                "    diag = (uint64_t)cpu_host_hal_isqrt_u32((uint32_t)(aspect_w * aspect_w + aspect_h * aspect_h));",
                "    if (diag == 0u) diag = 5u;",
                "    if (inches == 0u) inches = 14u;",
                "    target_w = ((uint64_t)inches * 48u * (uint64_t)aspect_w) / diag;",
                "    target_h = ((uint64_t)inches * 48u * (uint64_t)aspect_h) / diag;",
                "    if (target_w == 0u || target_h == 0u) { target_w = max_w; target_h = max_h; }",
                "    if (target_w > max_w) { target_w = max_w; target_h = (target_w * (uint64_t)aspect_h) / (uint64_t)aspect_w; }",
                "    if (target_h > max_h) { target_h = max_h; target_w = (target_h * (uint64_t)aspect_w) / (uint64_t)aspect_h; }",
                "    if (target_w < 160u) { target_w = 160u; target_h = (target_w * (uint64_t)aspect_h) / (uint64_t)aspect_w; }",
                "    if (target_h < 120u) { target_h = 120u; target_w = (target_h * (uint64_t)aspect_w) / (uint64_t)aspect_h; }",
                "    if (out_w) *out_w = (int)((target_w > 0u) ? target_w : 640u);",
                "    if (out_h) *out_h = (int)((target_h > 0u) ? target_h : 480u);",
                "}",
                "",
                "static void *cpu_host_hal_create_window(const char *title, int x, int y, int w, int h, uint32_t flags) {",
                "    CPUHostStubWindow *window;",
                "    if (cpu_host_hal_stub_inited == 0u) return NULL;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return NULL;",
                "    (void)title;",
                "    (void)x;",
                "    (void)y;",
                "    if ((flags & ~CPU_HOST_WINDOW_RESIZABLE) != 0u) return NULL;",
                "    if (w <= 0) w = 640;",
                "    if (h <= 0) h = 480;",
                "    window = (CPUHostStubWindow *)calloc(1u, sizeof(*window));",
                "    if (!window) return NULL;",
                "    window->w = w;",
                "    window->h = h;",
                "    window->focused = 1u;",
                "    if (cpu_host_hal_stub_primary_window == NULL) {",
                "        cpu_host_hal_stub_primary_window = window;",
                "    }",
                "    return (void *)window;",
                "}",
                "",
                "static void *cpu_host_hal_create_renderer(void *window, int index, uint32_t flags) {",
                "    CPUHostStubRenderer *renderer;",
                "    if (cpu_host_hal_stub_inited == 0u) return NULL;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return NULL;",
                "    if (window == NULL) window = (void *)cpu_host_hal_stub_primary_window;",
                "    if (window == NULL) return NULL;",
                "    (void)index;",
                "    if ((flags & ~CPU_HOST_RENDERER_ACCELERATED) != 0u) return NULL;",
                "    renderer = (CPUHostStubRenderer *)calloc(1u, sizeof(*renderer));",
                "    if (!renderer) return NULL;",
                "    renderer->window = (CPUHostStubWindow *)window;",
                "    renderer->clear_color = 0xFF000000u;",
                "    return (void *)renderer;",
                "}",
                "",
                "static void *cpu_host_hal_create_texture(void *renderer, uint32_t format, int access, int w, int h) {",
                "    CPUHostStubTexture *texture;",
                "    if (cpu_host_hal_stub_inited == 0u) return NULL;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return NULL;",
                "    if (renderer == NULL || w <= 0 || h <= 0) return NULL;",
                "    if (format != CPU_HOST_PIXELFORMAT_ARGB8888) return NULL;",
                "    if (access != CPU_HOST_TEXTUREACCESS_STREAMING) return NULL;",
                "    texture = (CPUHostStubTexture *)calloc(1u, sizeof(*texture));",
                "    if (!texture) return NULL;",
                "    texture->w = w;",
                "    texture->h = h;",
                "    return (void *)texture;",
                "}",
                "",
                "static uint32_t cpu_host_hal_audio_open(const char *device, int iscapture, const CPUHostAudioSpec *want, CPUHostAudioSpec *have, int allowed_changes) {",
                "    uint64_t bytes64;",
                "    if (cpu_host_hal_stub_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    (void)device;",
                "    (void)allowed_changes;",
                "    if (iscapture != 0) return 0u;",
                "    if (!want) return 0u;",
                "    if (want->freq <= 0 || want->channels == 0u || want->samples == 0u) return 0u;",
                "    cpu_host_hal_stub_reset_audio_state();",
                "    if (have) {",
                "        *have = *want;",
                "        if (have->size == 0u && have->samples != 0u && have->channels != 0u) {",
                "            bytes64 = (uint64_t)have->samples * (uint64_t)have->channels * 2u;",
                "            if (bytes64 > 0xFFFFFFFFu) return 0u;",
                "            have->size = (uint32_t)bytes64;",
                "        }",
                "    }",
                "    cpu_host_hal_stub_audio_opened = 1u;",
                "    return 1u;",
                "}",
                "",
                "static void cpu_host_hal_audio_pause(uint32_t dev, int pause_on) {",
                "    (void)dev;",
                "    (void)pause_on;",
                "    if (cpu_host_hal_stub_inited == 0u) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "}",
                "",
                "static void *cpu_host_hal_alloc(size_t size_bytes) {",
                "    return malloc(size_bytes);",
                "}",
                "",
                "static void cpu_host_hal_free(void *ptr) {",
                "    free(ptr);",
                "}",
                "",
                "static void cpu_host_hal_memset(void *dst, int value, size_t size_bytes) {",
                "    if (!dst || size_bytes == 0u) return;",
                "    memset(dst, value, size_bytes);",
                "}",
                "",
                "static const char *cpu_host_hal_getenv(const char *name) {",
                "    (void)name;",
                "    return NULL;",
                "}",
                "",
                "static const uint8_t *cpu_host_hal_keyboard_state(int *key_count) {",
                "    static const uint8_t empty_state[1] = {0u};",
                "    if (key_count) *key_count = 0;",
                "    return empty_state;",
                "}",
                "",
                "static int cpu_host_hal_gamepad_count(void) {",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_gamepad_button(int pad_index, int button_id) {",
                "    (void)pad_index; (void)button_id;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_gamepad_axis(int pad_index, int axis_id) {",
                "    (void)pad_index; (void)axis_id;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_joystick_count(void) {",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_joystick_button(int joy_index, int button) {",
                "    (void)joy_index; (void)button;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_joystick_axis(int joy_index, int axis) {",
                "    (void)joy_index; (void)axis;",
                "    return 0;",
                "}",
                "",
                "static uint8_t cpu_host_hal_joystick_hat(int joy_index, int hat) {",
                "    (void)joy_index; (void)hat;",
                "    return 0u;",
                "}",
                "",
                "static int32_t cpu_host_hal_key_from_scancode(int scancode) {",
                "    (void)scancode;",
                "    return 0;",
                "}",
                "",
                "static int32_t cpu_host_hal_scancode_from_key(int32_t keycode) {",
                "    (void)keycode;",
                "    return -1;",
                "}",
                "",
                "static void cpu_host_hal_start_text_input(void) {",
                "}",
                "",
                "static void cpu_host_hal_stop_text_input(void) {",
                "}",
                "",
                "static void cpu_host_hal_raise_window(void *window) {",
                "    (void)window;",
                "    /* Do not steal focus implicitly. */",
                "}",
                "",
                "static void cpu_host_hal_show_window(void *window) {",
                "    (void)window;",
                "    if (cpu_host_hal_stub_inited == 0u) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "}",
                "",
                "static int cpu_host_hal_set_window_input_focus(void *window) {",
                "    CPUHostStubWindow *ww = (window != NULL) ? (CPUHostStubWindow *)window : cpu_host_hal_stub_primary_window;",
                "    if (cpu_host_hal_stub_inited == 0u || ww == NULL) return -1;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    ww->focused = 1u;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_set_texture_blend_none(void *texture) {",
                "    if (cpu_host_hal_stub_inited == 0u || texture == NULL) return -1;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_init_subsystem(uint32_t flags) {",
                "    if ((flags & ~(CPU_HOST_INIT_VIDEO | CPU_HOST_INIT_AUDIO | CPU_HOST_INIT_EVENTS)) != 0u) return -1;",
                "    if (cpu_host_hal_stub_inited == 0u) return -1;",
                "    cpu_host_hal_stub_subsystems |= flags;",
                "    return 0;",
                "}",
                "",
                "static uint32_t cpu_host_hal_audio_dequeue(uint32_t dev, void *data, uint32_t len_bytes) {",
                "    uint32_t n;",
                "    if (cpu_host_hal_stub_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    if (dev == 0u || !data || len_bytes == 0u || cpu_host_hal_stub_audio_opened == 0u) return 0u;",
                "    if (cpu_host_hal_stub_audio_len > cpu_host_hal_stub_audio_cap) return 0u;",
                "    if (cpu_host_hal_stub_audio_cap != 0u && cpu_host_hal_stub_audio_buf == NULL) return 0u;",
                "    if (cpu_host_hal_stub_audio_len != 0u && cpu_host_hal_stub_audio_buf == NULL) return 0u;",
                "    n = (cpu_host_hal_stub_audio_len < len_bytes) ? cpu_host_hal_stub_audio_len : len_bytes;",
                "    if (n == 0u) return 0u;",
                "    memcpy(data, cpu_host_hal_stub_audio_buf, (size_t)n);",
                "    cpu_host_hal_stub_audio_len -= n;",
                "    if (cpu_host_hal_stub_audio_len != 0u) {",
                "        memmove(",
                "            cpu_host_hal_stub_audio_buf,",
                "            cpu_host_hal_stub_audio_buf + n,",
                "            (size_t)cpu_host_hal_stub_audio_len",
                "        );",
                "    }",
                "    return n;",
                "}",
                "",
                "static int cpu_host_hal_get_window_size(void *window, int *out_w, int *out_h) {",
                "    CPUHostStubWindow *ww = (window != NULL) ? (CPUHostStubWindow *)window : cpu_host_hal_stub_primary_window;",
                "    if (out_w) *out_w = 0;",
                "    if (out_h) *out_h = 0;",
                "    if (cpu_host_hal_stub_inited == 0u || ww == NULL || !out_w || !out_h) return -1;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (ww->w <= 0 || ww->h <= 0) return -1;",
                "    *out_w = ww->w;",
                "    *out_h = ww->h;",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_set_window_size(void *window, int w, int h) {",
                "    CPUHostStubWindow *ww = (window != NULL) ? (CPUHostStubWindow *)window : cpu_host_hal_stub_primary_window;",
                "    if (cpu_host_hal_stub_inited == 0u || ww == NULL) return -1;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;",
                "    if (w <= 0 || h <= 0) return -1;",
                "    ww->w = w;",
                "    ww->h = h;",
                "    return 0;",
                "}",
                "",
                "static const char *cpu_host_hal_scancode_name(int32_t scancode) {",
                "    (void)scancode;",
                "    return \"UNKNOWN\";",
                "}",
                "",
                "static uint32_t cpu_host_hal_get_mod_state(void) {",
                "    return 0u;",
                "}",
                "",
                "static const char *cpu_host_hal_key_name(int32_t keycode) {",
                "    (void)keycode;",
                "    return \"UNKNOWN\";",
                "}",
                "",
            ]
        )
        helper_lines.append("/* PASM_SPLIT_END:HOST_HAL_IMPL */")

    helper_lines.append("static uint64_t cpu_component_host_key_hash(const char *s) {")
    helper_lines.append("    uint64_t h = 1469598103934665603ull;")
    helper_lines.append("    const unsigned char *p = (const unsigned char *)s;")
    helper_lines.append("    if (p == NULL) return 0ull;")
    helper_lines.append("    while (*p != 0u) {")
    helper_lines.append("        h ^= (uint64_t)(*p++);")
    helper_lines.append("        h *= 1099511628211ull;")
    helper_lines.append("    }")
    helper_lines.append("    return h;")
    helper_lines.append("}")
    helper_lines.append("static int32_t cpu_component_scancode_for_host_key(const char *host_key) {")
    helper_lines.append("#if CPU_HOST_HAS_SCANCODE_MAP")
    helper_lines.append("    if (!host_key || !host_key[0]) return -1;")
    helper_lines.append("    switch (cpu_component_host_key_hash(host_key)) {")
    fnv_map: Dict[int, str] = {}
    for key in sorted(ALLOWED_HOST_KEYS):
        if host_uses_sdl2_backend and key in SDL_UNSUPPORTED_SCANCODE_KEYS:
            continue
        if host_uses_glfw_backend and key not in GLFW_SCANCODE_KEYS:
            continue
        key_bytes = str(key).encode("ascii", "strict")
        h = 1469598103934665603
        for b in key_bytes:
            h ^= b
            h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
        if h in fnv_map and fnv_map[h] != key:
            raise RuntimeError(
                f"FNV64 collision for host keys '{fnv_map[h]}' and '{key}'"
            )
        fnv_map[h] = key
        helper_lines.append(
            f"        case 0x{h:016X}ull: return (int32_t)CPU_HOST_SCANCODE({key});"
        )
    helper_lines.append("        default: return -1;")
    helper_lines.append("    }")
    helper_lines.append("    return -1;")
    helper_lines.append("#else")
    helper_lines.append("    (void)host_key;")
    helper_lines.append("    return -1;")
    helper_lines.append("#endif")
    helper_lines.append("}")
    helper_lines.append("static int32_t cpu_component_scancode_for_host_token(char *token) {")
    helper_lines.append("    char *s = token;")
    helper_lines.append("    char *end = NULL;")
    helper_lines.append("    char *p = NULL;")
    helper_lines.append("    size_t n = 0u;")
    helper_lines.append("    uint8_t quoted = 0u;")
    helper_lines.append("    long v = -1;")
    helper_lines.append("    if (s == NULL || s[0] == '\\0') return -1;")
    helper_lines.append("    n = strlen(s);")
    helper_lines.append("    if (n >= 2u && ((s[0] == '\\'' && s[n - 1u] == '\\'') || (s[0] == '\"' && s[n - 1u] == '\"'))) {")
    helper_lines.append("        quoted = 1u;")
    helper_lines.append("        s[n - 1u] = '\\0';")
    helper_lines.append("        s = s + 1;")
    helper_lines.append("    }")
    helper_lines.append("    if (quoted == 0u) {")
    helper_lines.append(
        "        if (s[0] == 'K' && s[1] == 'E' && s[2] == 'Y' && s[3] == '_') {"
    )
    helper_lines.append("            v = strtol(s + 4, &end, 10);")
    helper_lines.append("            if (end != (s + 4)) {")
    helper_lines.append("                p = end;")
    helper_lines.append("                while (*p == ' ' || *p == '\\t' || *p == '\\r' || *p == '\\n') p++;")
    helper_lines.append("                if (*p == '\\0' && v >= 0 && v <= 4095) return (int32_t)v;")
    helper_lines.append("            }")
    helper_lines.append("        }")
    helper_lines.append("        v = strtol(s, &end, 0);")
    helper_lines.append("        if (end != s) {")
    helper_lines.append("            p = end;")
    helper_lines.append("            while (*p == ' ' || *p == '\\t' || *p == '\\r' || *p == '\\n') p++;")
    helper_lines.append("            if (*p == '\\0' && v >= 0 && v <= 4095) return (int32_t)v;")
    helper_lines.append("        }")
    helper_lines.append("    }")
    helper_lines.append("    return cpu_component_scancode_for_host_key(s);")
    helper_lines.append("}")
    helper_lines.append("static uint64_t cpu_component_hash_str(const char *s);")
    helper_lines.extend(
        [
            "",
            "static void cpu_component_runtime_keyboard_clear(void) {",
            "    if (g_runtime_keyboard_map.bindings != NULL) {",
            "        for (size_t i = 0; i < g_runtime_keyboard_map.binding_count; ++i) {",
            "            RuntimeKeyboardBinding *b = &g_runtime_keyboard_map.bindings[i];",
            "            if (b->presses != NULL) free(b->presses);",
            "            b->presses = NULL;",
            "            b->press_count = 0u;",
            "            b->press_cap = 0u;",
            "        }",
            "        free(g_runtime_keyboard_map.bindings);",
            "    }",
            "    memset(&g_runtime_keyboard_map, 0, sizeof(g_runtime_keyboard_map));",
            "}",
            "",
            "static uint8_t cpu_component_keyboard_host_shift_down(const uint8_t *host_keys, size_t host_key_count) {",
            "    if (host_keys == NULL || host_key_count == 0u) return 0u;",
            "    if ((size_t)CPU_HOST_SCANCODE(LSHIFT) < host_key_count && host_keys[CPU_HOST_SCANCODE(LSHIFT)] != 0u) return 1u;",
            "    if ((size_t)CPU_HOST_SCANCODE(RSHIFT) < host_key_count && host_keys[CPU_HOST_SCANCODE(RSHIFT)] != 0u) return 1u;",
            "    return 0u;",
            "}",
            "",
            "static RuntimeKeyboardBinding *cpu_component_runtime_binding_for_host_key(const char *host_key_name, uint8_t shift_mode, uint8_t create_if_missing) {",
            "    if (host_key_name == NULL || host_key_name[0] == '\\0') return NULL;",
            "    for (size_t i = 0; i < g_runtime_keyboard_map.binding_count; ++i) {",
            "        if (g_runtime_keyboard_map.bindings[i].source_kind == 2u && g_runtime_keyboard_map.bindings[i].shift_mode == shift_mode && strcmp(g_runtime_keyboard_map.bindings[i].host_key_name, host_key_name) == 0) {",
            "            if (create_if_missing != 0u) return NULL;",
            "            return &g_runtime_keyboard_map.bindings[i];",
            "        }",
            "    }",
            "    if (create_if_missing == 0u) return NULL;",
            "    if (g_runtime_keyboard_map.binding_count >= g_runtime_keyboard_map.binding_cap) {",
            "        size_t new_cap = (g_runtime_keyboard_map.binding_cap == 0u) ? 32u : (g_runtime_keyboard_map.binding_cap * 2u);",
            "        RuntimeKeyboardBinding *nb = (RuntimeKeyboardBinding *)realloc(g_runtime_keyboard_map.bindings, new_cap * sizeof(RuntimeKeyboardBinding));",
            "        if (nb == NULL) return NULL;",
            "        memset(nb + g_runtime_keyboard_map.binding_cap, 0, (new_cap - g_runtime_keyboard_map.binding_cap) * sizeof(RuntimeKeyboardBinding));",
            "        g_runtime_keyboard_map.bindings = nb;",
            "        g_runtime_keyboard_map.binding_cap = new_cap;",
            "    }",
            "    {",
            "        RuntimeKeyboardBinding *b = &g_runtime_keyboard_map.bindings[g_runtime_keyboard_map.binding_count++];",
            "        memset(b, 0, sizeof(*b));",
            "        b->scancode = -1;",
            "        b->source_kind = 2u;",
            "        b->shift_mode = shift_mode;",
            "        (void)snprintf(b->host_key_name, sizeof(b->host_key_name), \"%s\", host_key_name);",
            "        return b;",
            "    }",
            "}",
            "",
            "static RuntimeKeyboardBinding *cpu_component_runtime_binding_for_scancode(int32_t scancode, uint8_t shift_mode, uint8_t create_if_missing) {",
            "    for (size_t i = 0; i < g_runtime_keyboard_map.binding_count; ++i) {",
            "        if (g_runtime_keyboard_map.bindings[i].source_kind == 1u && g_runtime_keyboard_map.bindings[i].shift_mode == shift_mode && g_runtime_keyboard_map.bindings[i].scancode == scancode) {",
            "            if (create_if_missing != 0u) return NULL;",
            "            return &g_runtime_keyboard_map.bindings[i];",
            "        }",
            "    }",
            "    if (create_if_missing == 0u) return NULL;",
            "    if (g_runtime_keyboard_map.binding_count >= g_runtime_keyboard_map.binding_cap) {",
            "        size_t new_cap = (g_runtime_keyboard_map.binding_cap == 0u) ? 32u : (g_runtime_keyboard_map.binding_cap * 2u);",
            "        RuntimeKeyboardBinding *nb = (RuntimeKeyboardBinding *)realloc(g_runtime_keyboard_map.bindings, new_cap * sizeof(RuntimeKeyboardBinding));",
            "        if (nb == NULL) return NULL;",
            "        memset(nb + g_runtime_keyboard_map.binding_cap, 0, (new_cap - g_runtime_keyboard_map.binding_cap) * sizeof(RuntimeKeyboardBinding));",
            "        g_runtime_keyboard_map.bindings = nb;",
            "        g_runtime_keyboard_map.binding_cap = new_cap;",
            "    }",
            "    {",
            "        RuntimeKeyboardBinding *b = &g_runtime_keyboard_map.bindings[g_runtime_keyboard_map.binding_count++];",
            "        memset(b, 0, sizeof(*b));",
            "        b->scancode = scancode;",
            "        b->source_kind = 1u;",
            "        b->shift_mode = shift_mode;",
            "        return b;",
            "    }",
            "}",
            "",
            "static uint8_t cpu_runtime_keyboard_binding_pressed(const RuntimeKeyboardBinding *b, const uint8_t *host_keys, size_t host_key_count) {",
            "    uint8_t shift_down;",
            "    if (b == NULL || host_keys == NULL || host_key_count == 0u) return 0u;",
            "    shift_down = cpu_component_keyboard_host_shift_down(host_keys, host_key_count);",
            "    if (b->shift_mode == 1u && shift_down != 0u) return 0u;",
            "    if (b->shift_mode == 2u && shift_down == 0u) return 0u;",
            "    if (b->source_kind == 1u) {",
            "        if (b->scancode < 0 || (size_t)b->scancode >= host_key_count) return 0u;",
            "        return (uint8_t)(host_keys[b->scancode] != 0u);",
            "    }",
            "    if (b->source_kind == 2u) {",
            "        if (b->host_key_name[0] == '\\0') return 0u;",
            "        for (size_t i = 0; i < host_key_count; ++i) {",
            "            const char *key_name;",
            "            if (host_keys[i] == 0u) continue;",
            "            key_name = cpu_host_hal_key_name(cpu_host_hal_key_from_scancode((int)i));",
            "            if (key_name != NULL && strcmp(key_name, b->host_key_name) == 0) return 1u;",
            "        }",
            "    }",
            "    return 0u;",
            "}",
            "",
            "static int cpu_component_runtime_add_press(RuntimeKeyboardBinding *binding, uint8_t row, uint8_t bit) {",
            "    if (binding == NULL) return -1;",
            "    if (row > 31u || bit > 7u) return -1;",
            "    for (uint8_t i = 0u; i < binding->press_count; ++i) {",
            "        if (binding->presses[i].row == row && binding->presses[i].bit == bit) return 0;",
            "    }",
            "    if (binding->press_count >= binding->press_cap) {",
            "        uint8_t new_cap = (binding->press_cap == 0u) ? 4u : (uint8_t)(binding->press_cap * 2u);",
            "        RuntimeKeyboardPress *np = (RuntimeKeyboardPress *)realloc(binding->presses, (size_t)new_cap * sizeof(RuntimeKeyboardPress));",
            "        if (np == NULL) return -1;",
            "        binding->presses = np;",
            "        binding->press_cap = new_cap;",
            "    }",
            "    binding->presses[binding->press_count].row = row;",
            "    binding->presses[binding->press_count].bit = bit;",
            "    binding->press_count += 1u;",
            "    return 0;",
            "}",
            "",
            "static void cpu_component_keyboard_ascii_queue_push(uint8_t value) {",
            "    if (value == 0u) return;",
            "    if (g_runtime_keyboard_map.ascii_q_len >= sizeof(g_runtime_keyboard_map.ascii_queue)) return;",
            "    {",
            "        uint8_t pos = (uint8_t)((g_runtime_keyboard_map.ascii_q_head + g_runtime_keyboard_map.ascii_q_len) % sizeof(g_runtime_keyboard_map.ascii_queue));",
            "        g_runtime_keyboard_map.ascii_queue[pos] = value;",
            "        g_runtime_keyboard_map.ascii_q_len += 1u;",
            "    }",
            "}",
            "",
            "static uint8_t cpu_component_keyboard_ascii_queue_pop(void) {",
            "    uint8_t value;",
            "    if (g_runtime_keyboard_map.ascii_q_len == 0u) return 0u;",
            "    value = g_runtime_keyboard_map.ascii_queue[g_runtime_keyboard_map.ascii_q_head];",
            "    g_runtime_keyboard_map.ascii_q_head = (uint8_t)((g_runtime_keyboard_map.ascii_q_head + 1u) % sizeof(g_runtime_keyboard_map.ascii_queue));",
            "    g_runtime_keyboard_map.ascii_q_len -= 1u;",
            "    return value;",
            "}",
            "",
            "static char *cpu_component_trim(char *s) {",
            "    char *end;",
            "    while (s && *s && (*s == ' ' || *s == '\\t' || *s == '\\r' || *s == '\\n')) s++;",
            "    if (!s || !*s) return s;",
            "    end = s + strlen(s);",
            "    while (end > s && (end[-1] == ' ' || end[-1] == '\\t' || end[-1] == '\\r' || end[-1] == '\\n')) end--;",
            "    *end = '\\0';",
            "    return s;",
            "}",
            "",
            "static int cpu_component_parse_u8(const char *text, uint8_t *out) {",
            "    char *end = NULL;",
            "    long v;",
            "    if (!text || !out) return -1;",
            "    v = strtol(text, &end, 0);",
            "    if (end == text || *cpu_component_trim(end) != '\\0') return -1;",
            "    if (v < 0 || v > 255) return -1;",
            "    *out = (uint8_t)v;",
            "    return 0;",
            "}",
            "",
            "static char *cpu_component_unquote(char *s) {",
            "    size_t n;",
            "    if (s == NULL) return NULL;",
            "    s = cpu_component_trim(s);",
            "    n = strlen(s);",
            "    if (n >= 2u) {",
            "        if ((s[0] == '\\'' && s[n - 1u] == '\\'') || (s[0] == '\"' && s[n - 1u] == '\"')) {",
            "            s[n - 1u] = '\\0';",
            "            return s + 1;",
            "        }",
            "    }",
            "    return s;",
            "}",
            "",
            "int " + cpu_prefix + "_load_keyboard_map(CPUState *cpu, const char *path) {",
            "    FILE *f;",
            "    char line[512];",
            "    RuntimeKeyboardBinding *current = NULL;",
            "    (void)cpu;",
            "    if (path == NULL || path[0] == '\\0') return -1;",
            "    f = fopen(path, \"r\");",
            "    if (f == NULL) return -1;",
            "    cpu_component_runtime_keyboard_clear();",
            "    g_runtime_keyboard_map.focus_required = 1u;",
            "    while (fgets(line, sizeof(line), f) != NULL) {",
            "        char *hash = strchr(line, '#');",
            "        char *s;",
            "        if (hash) *hash = '\\0';",
            "        s = cpu_component_trim(line);",
            "        if (s == NULL || s[0] == '\\0') continue;",
            "        if (strcmp(s, \"keyboard:\") == 0) continue;",
            "        if (strcmp(s, \"system_keys:\") == 0) continue;",
            "        if (strcmp(s, \"bindings:\") == 0) continue;",
            "        if (strcmp(s, \"presses:\") == 0) continue;",
            "        if (strcmp(s, \"-\") == 0) continue;",
            "        /* UI-only metadata entries. */",
            "        if (strncmp(s, \"- id:\", 5) == 0 || strncmp(s, \"id:\", 3) == 0) continue;",
            "        if (strncmp(s, \"visual_feedback:\", 16) == 0) continue;",
            "        if (strncmp(s, \"kind:\", 5) == 0) {",
            "            s = cpu_component_trim(s + 5);",
            "            if (strcmp(s, \"matrix\") == 0) g_runtime_keyboard_map.kind = 1u;",
            "            else if (strcmp(s, \"ascii\") == 0) g_runtime_keyboard_map.kind = 2u;",
            "            else { fprintf(stderr, \"Keyboard map parse error: invalid kind: '%s'\\n\", s); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"focus_required:\", 15) == 0) {",
            "            s = cpu_component_trim(s + 15);",
            "            if (strcmp(s, \"true\") == 0) g_runtime_keyboard_map.focus_required = 1u;",
            "            else if (strcmp(s, \"false\") == 0) g_runtime_keyboard_map.focus_required = 0u;",
            "            else { fprintf(stderr, \"Keyboard map parse error: invalid focus_required: '%s'\\n\", s); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"- host_scancode:\", 16) == 0 || strncmp(s, \"host_scancode:\", 14) == 0) {",
            "            int32_t sc;",
            "            const int pref = (strncmp(s, \"- host_scancode:\", 16) == 0) ? 16 : 14;",
            "            s = cpu_component_trim(s + pref);",
            "            sc = cpu_component_scancode_for_host_token(s);",
            "            if (sc < 0) { fprintf(stderr, \"Keyboard map parse error: unknown host_scancode token: '%s'\\n\", s); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current = cpu_component_runtime_binding_for_scancode(sc, 0u, 1u);",
            "            if (current == NULL) { fprintf(stderr, \"Keyboard map parse error: duplicate host_scancode token: '%s'\\n\", s); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            {",
            "                const char *n = cpu_component_unquote(s);",
            "                if (strcmp(n, \"LSHIFT\") == 0 || strcmp(n, \"RSHIFT\") == 0) current->is_shift_modifier = 1u;",
            "                if (strcmp(n, \"LCTRL\") == 0 || strcmp(n, \"RCTRL\") == 0) current->is_ctrl_modifier = 1u;",
            "                if (sc == (int32_t)CPU_HOST_SCANCODE(LSHIFT) || sc == (int32_t)CPU_HOST_SCANCODE(RSHIFT)) current->is_shift_modifier = 1u;",
            "                if (sc == (int32_t)CPU_HOST_SCANCODE(LCTRL) || sc == (int32_t)CPU_HOST_SCANCODE(RCTRL)) current->is_ctrl_modifier = 1u;",
            "            }",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"- host_scancode_shifted:\", 24) == 0 || strncmp(s, \"host_scancode_shifted:\", 22) == 0) {",
            "            int32_t sc;",
            "            const int pref = (strncmp(s, \"- host_scancode_shifted:\", 24) == 0) ? 24 : 22;",
            "            s = cpu_component_trim(s + pref);",
            "            sc = cpu_component_scancode_for_host_token(s);",
            "            if (sc < 0) { fprintf(stderr, \"Keyboard map parse error: unknown host_scancode_shifted token: '%s'\\n\", s); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current = cpu_component_runtime_binding_for_scancode(sc, 2u, 1u);",
            "            if (current == NULL) { fprintf(stderr, \"Keyboard map parse error: duplicate host_scancode_shifted token: '%s'\\n\", s); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"- host_scancode_unshifted:\", 26) == 0 || strncmp(s, \"host_scancode_unshifted:\", 24) == 0) {",
            "            int32_t sc;",
            "            const int pref = (strncmp(s, \"- host_scancode_unshifted:\", 26) == 0) ? 26 : 24;",
            "            s = cpu_component_trim(s + pref);",
            "            sc = cpu_component_scancode_for_host_token(s);",
            "            if (sc < 0) { fprintf(stderr, \"Keyboard map parse error: unknown host_scancode_unshifted token: '%s'\\n\", s); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current = cpu_component_runtime_binding_for_scancode(sc, 1u, 1u);",
            "            if (current == NULL) { fprintf(stderr, \"Keyboard map parse error: duplicate host_scancode_unshifted token: '%s'\\n\", s); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"- host_key:\", 11) == 0 || strncmp(s, \"host_key:\", 9) == 0) {",
            "            const int pref = (strncmp(s, \"- host_key:\", 11) == 0) ? 11 : 9;",
            "            const char *n;",
            "            s = cpu_component_trim(s + pref);",
            "            n = cpu_component_unquote(s);",
            "            if (n == NULL || n[0] == '\\0') { fprintf(stderr, \"Keyboard map parse error: empty host_key\\n\"); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current = cpu_component_runtime_binding_for_host_key(n, 0u, 1u);",
            "            if (current == NULL) { fprintf(stderr, \"Keyboard map parse error: duplicate host_key token: '%s'\\n\", n); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            if (strcmp(n, \"LEFT_SHIFT\") == 0 || strcmp(n, \"RIGHT_SHIFT\") == 0 || strcmp(n, \"LSHIFT\") == 0 || strcmp(n, \"RSHIFT\") == 0) current->is_shift_modifier = 1u;",
            "            if (strcmp(n, \"LEFT_CONTROL\") == 0 || strcmp(n, \"RIGHT_CONTROL\") == 0 || strcmp(n, \"LCTRL\") == 0 || strcmp(n, \"RCTRL\") == 0) current->is_ctrl_modifier = 1u;",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"- host_key_shifted:\", 19) == 0 || strncmp(s, \"host_key_shifted:\", 17) == 0) {",
            "            const int pref = (strncmp(s, \"- host_key_shifted:\", 19) == 0) ? 19 : 17;",
            "            const char *n;",
            "            s = cpu_component_trim(s + pref);",
            "            n = cpu_component_unquote(s);",
            "            if (n == NULL || n[0] == '\\0') { fprintf(stderr, \"Keyboard map parse error: empty host_key_shifted\\n\"); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current = cpu_component_runtime_binding_for_host_key(n, 2u, 1u);",
            "            if (current == NULL) { fprintf(stderr, \"Keyboard map parse error: duplicate host_key_shifted token: '%s'\\n\", n); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"- host_key_unshifted:\", 21) == 0 || strncmp(s, \"host_key_unshifted:\", 19) == 0) {",
            "            const int pref = (strncmp(s, \"- host_key_unshifted:\", 21) == 0) ? 21 : 19;",
            "            const char *n;",
            "            s = cpu_component_trim(s + pref);",
            "            n = cpu_component_unquote(s);",
            "            if (n == NULL || n[0] == '\\0') { fprintf(stderr, \"Keyboard map parse error: empty host_key_unshifted\\n\"); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current = cpu_component_runtime_binding_for_host_key(n, 1u, 1u);",
            "            if (current == NULL) { fprintf(stderr, \"Keyboard map parse error: duplicate host_key_unshifted token: '%s'\\n\", n); fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            continue;",
            "        }",
            "        if (current == NULL) continue;",
            "        if (strncmp(s, \"- row:\", 6) == 0 || strncmp(s, \"row:\", 4) == 0) {",
            "            uint8_t row = 0u;",
            "            const char *row_text = cpu_component_trim(s + ((s[0] == '-') ? 6 : 4));",
            "            if (cpu_component_parse_u8(row_text, &row) != 0) { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            if (cpu_component_runtime_add_press(current, row, 0u) != 0) { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current->presses[current->press_count - 1u].bit = 255u;",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"bit:\", 4) == 0) {",
            "            uint8_t bit = 0u;",
            "            if (current->press_count == 0u) { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            if (cpu_component_parse_u8(cpu_component_trim(s + 4), &bit) != 0 || bit > 7u) { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current->presses[current->press_count - 1u].bit = bit;",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"ascii:\", 6) == 0) {",
            "            uint8_t v = 0u;",
            "            if (cpu_component_parse_u8(cpu_component_trim(s + 6), &v) != 0) { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current->ascii = v;",
            "            current->has_ascii = 1u;",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"ascii_shift:\", 12) == 0) {",
            "            uint8_t v = 0u;",
            "            if (cpu_component_parse_u8(cpu_component_trim(s + 12), &v) != 0) { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current->ascii_shift = v;",
            "            current->has_ascii_shift = 1u;",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"ascii_ctrl:\", 11) == 0) {",
            "            uint8_t v = 0u;",
            "            if (cpu_component_parse_u8(cpu_component_trim(s + 11), &v) != 0) { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current->ascii_ctrl = v;",
            "            current->has_ascii_ctrl = 1u;",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"mapper_key_id:\", 14) == 0) {",
            "            const char *mid = cpu_component_unquote(cpu_component_trim(s + 14));",
            "            if (mid == NULL || mid[0] == '\\0') { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            (void)snprintf(current->mapper_key_id, sizeof(current->mapper_key_id), \"%s\", mid);",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"emulator_key_id:\", 15) == 0) {",
                "            const char *eid = cpu_component_unquote(cpu_component_trim(s + 15));",
                "            if (eid == NULL || eid[0] == '\\0') { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
                "            (void)snprintf(current->emulator_key_id, sizeof(current->emulator_key_id), \"%s\", eid);",
                "            continue;",
            "        }",
            "        if (strncmp(s, \"system_key_id:\", 14) == 0) {",
            "            const char *eid = cpu_component_unquote(cpu_component_trim(s + 14));",
            "            if (eid == NULL || eid[0] == '\\0') { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            (void)snprintf(current->emulator_key_id, sizeof(current->emulator_key_id), \"%s\", eid);",
            "            continue;",
            "        }",
            "        fprintf(stderr, \"Keyboard map parse error: unrecognized line: '%s'\\n\", s);",
            "        fclose(f);",
            "        cpu_component_runtime_keyboard_clear();",
            "        return -1;",
            "    }",
            "    fclose(f);",
            "    if (g_runtime_keyboard_map.kind == 0u || g_runtime_keyboard_map.binding_count == 0u) {",
            "        cpu_component_runtime_keyboard_clear();",
            "        return -1;",
            "    }",
            "    for (size_t i = 0; i < g_runtime_keyboard_map.binding_count; ++i) {",
            "        RuntimeKeyboardBinding *b = &g_runtime_keyboard_map.bindings[i];",
            "        uint8_t has_mapper = (b->mapper_key_id[0] != '\\0') ? 1u : 0u;",
            "        uint8_t has_emulator = (b->emulator_key_id[0] != '\\0') ? 1u : 0u;",
            "        if ((uint8_t)(has_mapper + has_emulator) != 1u) {",
            "            cpu_component_runtime_keyboard_clear();",
            "            return -1;",
            "        }",
            "        if (g_runtime_keyboard_map.kind == 1u) {",
            "            if (has_mapper != 0u) {",
            "                if (b->has_ascii != 0u || b->has_ascii_shift != 0u || b->has_ascii_ctrl != 0u) {",
            "                    cpu_component_runtime_keyboard_clear();",
            "                    return -1;",
            "                }",
            "                if (b->press_count == 0u) { cpu_component_runtime_keyboard_clear(); return -1; }",
            "                for (uint8_t p = 0u; p < b->press_count; ++p) {",
            "                    if (b->presses[p].bit > 7u) { cpu_component_runtime_keyboard_clear(); return -1; }",
            "                }",
            "            }",
            "        } else {",
            "            if (has_mapper != 0u) {",
            "                if (b->press_count != 0u) {",
            "                    cpu_component_runtime_keyboard_clear();",
            "                    return -1;",
            "                }",
            "                if (b->has_ascii == 0u && b->has_ascii_shift == 0u && b->has_ascii_ctrl == 0u) {",
            "                    cpu_component_runtime_keyboard_clear();",
            "                    return -1;",
            "                }",
            "            } else {",
            "                /* emulator bindings don't require ascii payload */",
            "            }",
            "        }",
            "    }",
            "    g_runtime_keyboard_map.loaded = 1u;",
            "    return 0;",
            "}",
            "",
            "typedef struct {",
            "    uint8_t port;",
            "    char id[64];",
            "    uint64_t id_hash;",
            "    uint8_t pressed;",
            "    float axis;",
            "} RuntimeControllerTarget;",
            "",
            "typedef struct {",
            "    uint8_t port;",
            "    char target_id[64];",
            "    uint8_t source_kind; /* 1=scancode 2=pad_btn 3=pad_axis 4=joy_btn 5=joy_axis 6=joy_hat */",
            "    int32_t scancode;",
            "    int16_t control;",
            "    int16_t extra;",
            "    float threshold;",
            "    float deadzone;",
            "    float scale;",
            "    uint8_t invert;",
            "} RuntimeControllerBinding;",
            "",
            "typedef struct {",
            "    uint8_t loaded;",
            "    uint8_t focus_required;",
            "    uint8_t port_connected[16];",
            "    uint8_t port_count;",
            "    RuntimeControllerBinding *bindings;",
            "    size_t binding_count;",
            "    size_t binding_cap;",
            "    RuntimeControllerTarget *targets;",
            "    size_t target_count;",
            "    size_t target_cap;",
            "} RuntimeControllerMap;",
            "",
            "static RuntimeControllerMap g_runtime_controller_map = {0};",
            "",
            "static void cpu_component_runtime_controller_clear(void) {",
            "    if (g_runtime_controller_map.bindings != NULL) {",
            "        free(g_runtime_controller_map.bindings);",
            "        g_runtime_controller_map.bindings = NULL;",
            "    }",
            "    if (g_runtime_controller_map.targets != NULL) {",
            "        free(g_runtime_controller_map.targets);",
            "        g_runtime_controller_map.targets = NULL;",
            "    }",
            "    memset(&g_runtime_controller_map, 0, sizeof(g_runtime_controller_map));",
            "}",
            "",
            "static uint8_t cpu_component_controller_port_from_target(const char *id) {",
            "    if (id == NULL || id[0] == '\\0') return 1u;",
            "    if (id[0] == 'P' && id[1] >= '1' && id[1] <= '9' && id[2] == '_') {",
            "        return (uint8_t)(id[1] - '0');",
            "    }",
            "    return 1u;",
            "}",
            "",
            "static RuntimeControllerTarget *cpu_component_controller_target_get(const char *id, uint8_t create) {",
            "    if (id == NULL || id[0] == '\\0') return NULL;",
            "    const uint64_t id_hash = cpu_component_hash_str(id);",
            "    for (size_t i = 0; i < g_runtime_controller_map.target_count; ++i) {",
            "        if (g_runtime_controller_map.targets[i].id_hash == id_hash) {",
            "            return &g_runtime_controller_map.targets[i];",
            "        }",
            "    }",
            "    if (create == 0u) return NULL;",
            "    if (g_runtime_controller_map.target_count >= g_runtime_controller_map.target_cap) {",
            "        size_t new_cap = (g_runtime_controller_map.target_cap == 0u) ? 32u : (g_runtime_controller_map.target_cap * 2u);",
            "        RuntimeControllerTarget *nt = (RuntimeControllerTarget *)realloc(g_runtime_controller_map.targets, new_cap * sizeof(RuntimeControllerTarget));",
            "        if (nt == NULL) return NULL;",
            "        memset(nt + g_runtime_controller_map.target_cap, 0, (new_cap - g_runtime_controller_map.target_cap) * sizeof(RuntimeControllerTarget));",
            "        g_runtime_controller_map.targets = nt;",
            "        g_runtime_controller_map.target_cap = new_cap;",
            "    }",
            "    {",
            "        RuntimeControllerTarget *t = &g_runtime_controller_map.targets[g_runtime_controller_map.target_count++];",
            "        memset(t, 0, sizeof(*t));",
            "        t->port = cpu_component_controller_port_from_target(id);",
            "        snprintf(t->id, sizeof(t->id), \"%s\", id);",
            "        t->id_hash = id_hash;",
            "        t->pressed = 0u;",
            "        t->axis = 0.0f;",
            "        return t;",
            "    }",
            "}",
            "",
            "static RuntimeControllerBinding *cpu_component_controller_binding_add(void) {",
            "    if (g_runtime_controller_map.binding_count >= g_runtime_controller_map.binding_cap) {",
            "        size_t new_cap = (g_runtime_controller_map.binding_cap == 0u) ? 64u : (g_runtime_controller_map.binding_cap * 2u);",
            "        RuntimeControllerBinding *nb = (RuntimeControllerBinding *)realloc(g_runtime_controller_map.bindings, new_cap * sizeof(RuntimeControllerBinding));",
            "        if (nb == NULL) return NULL;",
            "        memset(nb + g_runtime_controller_map.binding_cap, 0, (new_cap - g_runtime_controller_map.binding_cap) * sizeof(RuntimeControllerBinding));",
            "        g_runtime_controller_map.bindings = nb;",
            "        g_runtime_controller_map.binding_cap = new_cap;",
            "    }",
            "    return &g_runtime_controller_map.bindings[g_runtime_controller_map.binding_count++];",
            "}",
            "",
            "static int cpu_component_parse_bool(const char *s, uint8_t *out) {",
            "    if (!s || !out) return -1;",
            "    if (strcmp(s, \"true\") == 0) { *out = 1u; return 0; }",
            "    if (strcmp(s, \"false\") == 0) { *out = 0u; return 0; }",
            "    return -1;",
            "}",
            "",
            "/* Canonical gamepad control IDs (backend-agnostic). */",
            "enum {",
            "    CPU_HOST_GAMEPAD_BTN_A = 0,",
            "    CPU_HOST_GAMEPAD_BTN_B = 1,",
            "    CPU_HOST_GAMEPAD_BTN_X = 2,",
            "    CPU_HOST_GAMEPAD_BTN_Y = 3,",
            "    CPU_HOST_GAMEPAD_BTN_BACK = 4,",
            "    CPU_HOST_GAMEPAD_BTN_GUIDE = 5,",
            "    CPU_HOST_GAMEPAD_BTN_START = 6,",
            "    CPU_HOST_GAMEPAD_BTN_LEFTSTICK = 7,",
            "    CPU_HOST_GAMEPAD_BTN_RIGHTSTICK = 8,",
            "    CPU_HOST_GAMEPAD_BTN_LEFTSHOULDER = 9,",
            "    CPU_HOST_GAMEPAD_BTN_RIGHTSHOULDER = 10,",
            "    CPU_HOST_GAMEPAD_BTN_DPAD_UP = 11,",
            "    CPU_HOST_GAMEPAD_BTN_DPAD_DOWN = 12,",
            "    CPU_HOST_GAMEPAD_BTN_DPAD_LEFT = 13,",
            "    CPU_HOST_GAMEPAD_BTN_DPAD_RIGHT = 14",
            "};",
            "enum {",
            "    CPU_HOST_GAMEPAD_AXIS_LEFTX = 0,",
            "    CPU_HOST_GAMEPAD_AXIS_LEFTY = 1,",
            "    CPU_HOST_GAMEPAD_AXIS_RIGHTX = 2,",
            "    CPU_HOST_GAMEPAD_AXIS_RIGHTY = 3,",
            "    CPU_HOST_GAMEPAD_AXIS_TRIGGERLEFT = 4,",
            "    CPU_HOST_GAMEPAD_AXIS_TRIGGERRIGHT = 5",
            "};",
            "",
            "static int cpu_component_strieq(const char *a, const char *b) {",
            "    if (!a || !b) return 0;",
            "    while (*a && *b) {",
            "        char ca = *a; char cb = *b;",
            "        if (ca >= 'A' && ca <= 'Z') ca = (char)(ca - 'A' + 'a');",
            "        if (cb >= 'A' && cb <= 'Z') cb = (char)(cb - 'A' + 'a');",
            "        if (ca != cb) return 0;",
            "        ++a; ++b;",
            "    }",
            "    return (*a == '\\0' && *b == '\\0') ? 1 : 0;",
            "}",
            "",
            "static int cpu_component_gamepad_button_from_string(const char *s) {",
            "    if (!s) return -1;",
            "    if (cpu_component_strieq(s, \"a\")) return CPU_HOST_GAMEPAD_BTN_A;",
            "    if (cpu_component_strieq(s, \"b\")) return CPU_HOST_GAMEPAD_BTN_B;",
            "    if (cpu_component_strieq(s, \"x\")) return CPU_HOST_GAMEPAD_BTN_X;",
            "    if (cpu_component_strieq(s, \"y\")) return CPU_HOST_GAMEPAD_BTN_Y;",
            "    if (cpu_component_strieq(s, \"back\")) return CPU_HOST_GAMEPAD_BTN_BACK;",
            "    if (cpu_component_strieq(s, \"guide\") || cpu_component_strieq(s, \"home\")) return CPU_HOST_GAMEPAD_BTN_GUIDE;",
            "    if (cpu_component_strieq(s, \"start\")) return CPU_HOST_GAMEPAD_BTN_START;",
            "    if (cpu_component_strieq(s, \"leftstick\") || cpu_component_strieq(s, \"left_thumb\")) return CPU_HOST_GAMEPAD_BTN_LEFTSTICK;",
            "    if (cpu_component_strieq(s, \"rightstick\") || cpu_component_strieq(s, \"right_thumb\")) return CPU_HOST_GAMEPAD_BTN_RIGHTSTICK;",
            "    if (cpu_component_strieq(s, \"leftshoulder\") || cpu_component_strieq(s, \"leftbumper\") || cpu_component_strieq(s, \"left_shoulder\")) return CPU_HOST_GAMEPAD_BTN_LEFTSHOULDER;",
            "    if (cpu_component_strieq(s, \"rightshoulder\") || cpu_component_strieq(s, \"rightbumper\") || cpu_component_strieq(s, \"right_shoulder\")) return CPU_HOST_GAMEPAD_BTN_RIGHTSHOULDER;",
            "    if (cpu_component_strieq(s, \"dpup\") || cpu_component_strieq(s, \"dpad_up\")) return CPU_HOST_GAMEPAD_BTN_DPAD_UP;",
            "    if (cpu_component_strieq(s, \"dpdown\") || cpu_component_strieq(s, \"dpad_down\")) return CPU_HOST_GAMEPAD_BTN_DPAD_DOWN;",
            "    if (cpu_component_strieq(s, \"dpleft\") || cpu_component_strieq(s, \"dpad_left\")) return CPU_HOST_GAMEPAD_BTN_DPAD_LEFT;",
            "    if (cpu_component_strieq(s, \"dpright\") || cpu_component_strieq(s, \"dpad_right\")) return CPU_HOST_GAMEPAD_BTN_DPAD_RIGHT;",
            "    return -1;",
            "}",
            "",
            "static int cpu_component_gamepad_axis_from_string(const char *s) {",
            "    if (!s) return -1;",
            "    if (cpu_component_strieq(s, \"leftx\") || cpu_component_strieq(s, \"left_x\")) return CPU_HOST_GAMEPAD_AXIS_LEFTX;",
            "    if (cpu_component_strieq(s, \"lefty\") || cpu_component_strieq(s, \"left_y\")) return CPU_HOST_GAMEPAD_AXIS_LEFTY;",
            "    if (cpu_component_strieq(s, \"rightx\") || cpu_component_strieq(s, \"right_x\")) return CPU_HOST_GAMEPAD_AXIS_RIGHTX;",
            "    if (cpu_component_strieq(s, \"righty\") || cpu_component_strieq(s, \"right_y\")) return CPU_HOST_GAMEPAD_AXIS_RIGHTY;",
            "    if (cpu_component_strieq(s, \"triggerleft\") || cpu_component_strieq(s, \"lefttrigger\") || cpu_component_strieq(s, \"left_trigger\")) return CPU_HOST_GAMEPAD_AXIS_TRIGGERLEFT;",
            "    if (cpu_component_strieq(s, \"triggerright\") || cpu_component_strieq(s, \"righttrigger\") || cpu_component_strieq(s, \"right_trigger\")) return CPU_HOST_GAMEPAD_AXIS_TRIGGERRIGHT;",
            "    return -1;",
            "}",
            "",
            "int " + cpu_prefix + "_load_controller_map(CPUState *cpu, const char *path) {",
            "    FILE *f;",
            "    char line[512];",
            "    RuntimeControllerBinding *current = NULL;",
            "    uint8_t in_ports = 0u;",
            "    uint8_t in_bindings = 0u;",
            "    uint8_t in_host_gamepad = 0u;",
            "    uint8_t in_host_joystick = 0u;",
            "    uint8_t current_port = 1u;",
            "    uint8_t current_port_connected = 1u;",
            "    (void)cpu;",
            "    if (path == NULL || path[0] == '\\0') return -1;",
            "    f = fopen(path, \"r\");",
            "    if (f == NULL) return -1;",
            "    cpu_component_runtime_controller_clear();",
            "    g_runtime_controller_map.focus_required = 0u;",
            "    for (size_t i = 0; i < 16u; ++i) g_runtime_controller_map.port_connected[i] = 1u;",
            "    while (fgets(line, sizeof(line), f) != NULL) {",
            "        char *hash = strchr(line, '#');",
            "        char *s;",
            "        if (hash) *hash = '\\0';",
            "        s = cpu_component_trim(line);",
            "        if (s == NULL || s[0] == '\\0') continue;",
            "        if (strcmp(s, \"controller_map:\") == 0) continue;",
            "        if (strcmp(s, \"ports:\") == 0) { in_ports = 1u; in_bindings = 0u; continue; }",
            "        if (strcmp(s, \"bindings:\") == 0) { in_ports = 0u; in_bindings = 1u; continue; }",
            "        if (strncmp(s, \"focus_required:\", 15) == 0) {",
            "            uint8_t b = 0u;",
            "            s = cpu_component_trim(s + 15);",
            "            if (cpu_component_parse_bool(s, &b) != 0) { fclose(f); cpu_component_runtime_controller_clear(); return -1; }",
            "            g_runtime_controller_map.focus_required = b;",
            "            continue;",
            "        }",
            "        if (in_ports) {",
            "            if (strncmp(s, \"- port:\", 7) == 0 || strncmp(s, \"port:\", 5) == 0) {",
            "                uint8_t p = 1u;",
            "                const char *pt = cpu_component_trim(s + ((s[0] == '-') ? 7 : 5));",
            "                if (cpu_component_parse_u8(pt, &p) != 0) continue;",
            "                current_port = p;",
            "                current_port_connected = 1u;",
            "                if (p >= 1u && p <= 16u) {",
            "                    if (p > g_runtime_controller_map.port_count) g_runtime_controller_map.port_count = p;",
            "                }",
            "                continue;",
            "            }",
            "            if (strncmp(s, \"connected:\", 10) == 0) {",
            "                uint8_t b = 1u;",
            "                s = cpu_component_trim(s + 10);",
            "                if (cpu_component_parse_bool(s, &b) != 0) continue;",
            "                current_port_connected = b;",
            "                if (current_port >= 1u && current_port <= 16u) g_runtime_controller_map.port_connected[current_port - 1u] = b;",
            "                continue;",
            "            }",
            "            continue;",
            "        }",
            "        if (!in_bindings) continue;",
            "        if (strncmp(s, \"- target_control_id:\", 20) == 0 || strncmp(s, \"target_control_id:\", 18) == 0) {",
                "            const int pref = (s[0] == '-') ? 20 : 18;",
                "            s = cpu_component_unquote(cpu_component_trim(s + pref));",
                "            current = cpu_component_controller_binding_add();",
                "            if (current == NULL) { fclose(f); cpu_component_runtime_controller_clear(); return -1; }",
                "            memset(current, 0, sizeof(*current));",
                "            snprintf(current->target_id, sizeof(current->target_id), \"%s\", s);",
                "            current->port = cpu_component_controller_port_from_target(current->target_id);",
                "            current->threshold = 0.5f;",
                "            current->deadzone = 0.15f;",
                "            current->scale = 1.0f;",
                "            current->invert = 0u;",
                "            in_host_gamepad = 0u;",
                "            in_host_joystick = 0u;",
                "            continue;",
            "        }",
            "        if (current == NULL) continue;",
            "        if (strncmp(s, \"- host_scancode:\", 16) == 0 || strncmp(s, \"host_scancode:\", 14) == 0 || strncmp(s, \"- host_key:\", 11) == 0 || strncmp(s, \"host_key:\", 9) == 0) {",
            "            const int pref = (strncmp(s, \"- host_scancode:\", 16) == 0) ? 16 : ((strncmp(s, \"host_scancode:\", 14) == 0) ? 14 : ((s[0] == '-') ? 11 : 9));",
            "            s = cpu_component_unquote(cpu_component_trim(s + pref));",
            "            current->source_kind = 1u;",
            "            current->scancode = cpu_component_scancode_for_host_token(s);",
            "            if (current->scancode < 0) { fprintf(stderr, \"Controller map parse error: unknown host_scancode token: '%s'\\n\", s); fclose(f); cpu_component_runtime_controller_clear(); return -1; }",
            "            continue;",
            "        }",
            "        if (strcmp(s, \"host_gamepad:\") == 0 || strcmp(s, \"- host_gamepad:\") == 0) { in_host_gamepad = 1u; in_host_joystick = 0u; continue; }",
            "        if (strcmp(s, \"host_joystick:\") == 0 || strcmp(s, \"- host_joystick:\") == 0) { in_host_gamepad = 0u; in_host_joystick = 1u; continue; }",
            "        if (in_host_gamepad) {",
            "            if (strncmp(s, \"control:\", 8) == 0) {",
            "                char *ct = cpu_component_unquote(cpu_component_trim(s + 8));",
            "                int btn = cpu_component_gamepad_button_from_string(ct);",
            "                int ax = cpu_component_gamepad_axis_from_string(ct);",
            "                if (btn >= 0) { current->source_kind = 2u; current->control = (int16_t)btn; }",
            "                else if (ax >= 0) { current->source_kind = 3u; current->control = (int16_t)ax; }",
            "                else { current->source_kind = 2u; current->control = (int16_t)atoi(ct); }",
            "                continue;",
            "            }",
            "            if (strncmp(s, \"direction:\", 10) == 0) {",
            "                char *dt = cpu_component_unquote(cpu_component_trim(s + 10));",
            "                if (dt && dt[0] == '+') current->extra = 1;",
            "                else if (dt && dt[0] == '-') current->extra = -1;",
            "                current->source_kind = 3u;",
            "                continue;",
            "            }",
            "            if (strncmp(s, \"threshold:\", 10) == 0) { current->threshold = (float)atof(cpu_component_trim(s + 10)); continue; }",
            "            if (strncmp(s, \"deadzone:\", 9) == 0) { current->deadzone = (float)atof(cpu_component_trim(s + 9)); continue; }",
            "            if (strncmp(s, \"scale:\", 6) == 0) { current->scale = (float)atof(cpu_component_trim(s + 6)); continue; }",
            "            if (strncmp(s, \"invert:\", 7) == 0) { uint8_t b=0u; if (cpu_component_parse_bool(cpu_component_trim(s+7), &b)==0) current->invert=b; continue; }",
            "        }",
            "        if (in_host_joystick) {",
            "            if (strncmp(s, \"button:\", 7) == 0) { current->source_kind = 4u; current->control = (int16_t)atoi(cpu_component_trim(s + 7)); continue; }",
            "            if (strncmp(s, \"axis:\", 5) == 0) { current->source_kind = 5u; current->control = (int16_t)atoi(cpu_component_trim(s + 5)); continue; }",
            "            if (strncmp(s, \"hat:\", 4) == 0) { current->source_kind = 6u; current->control = (int16_t)atoi(cpu_component_trim(s + 4)); continue; }",
            "            if (strncmp(s, \"hat_dir:\", 8) == 0) {",
            "                char *dt = cpu_component_unquote(cpu_component_trim(s + 8));",
            "                if (strcmp(dt, \"up\") == 0) current->extra = (int16_t)CPU_HOST_HAT_UP;",
            "                else if (strcmp(dt, \"down\") == 0) current->extra = (int16_t)CPU_HOST_HAT_DOWN;",
            "                else if (strcmp(dt, \"left\") == 0) current->extra = (int16_t)CPU_HOST_HAT_LEFT;",
            "                else if (strcmp(dt, \"right\") == 0) current->extra = (int16_t)CPU_HOST_HAT_RIGHT;",
            "                continue;",
            "            }",
            "            if (strncmp(s, \"direction:\", 10) == 0) {",
            "                char *dt = cpu_component_unquote(cpu_component_trim(s + 10));",
            "                if (dt && dt[0] == '+') current->extra = 1;",
            "                else if (dt && dt[0] == '-') current->extra = -1;",
            "                continue;",
            "            }",
            "            if (strncmp(s, \"threshold:\", 10) == 0) { current->threshold = (float)atof(cpu_component_trim(s + 10)); continue; }",
            "            if (strncmp(s, \"deadzone:\", 9) == 0) { current->deadzone = (float)atof(cpu_component_trim(s + 9)); continue; }",
            "            if (strncmp(s, \"scale:\", 6) == 0) { current->scale = (float)atof(cpu_component_trim(s + 6)); continue; }",
            "            if (strncmp(s, \"invert:\", 7) == 0) { uint8_t b=0u; if (cpu_component_parse_bool(cpu_component_trim(s+7), &b)==0) current->invert=b; continue; }",
            "        }",
            "    }",
            "    fclose(f);",
            "    for (size_t i = 0; i < g_runtime_controller_map.binding_count; ++i) {",
            "        if (g_runtime_controller_map.bindings[i].source_kind == 0u) {",
            "            fprintf(stderr, \"Controller map parse error: binding '%s' is missing host source (need host_scancode/host_gamepad/host_joystick)\\n\", g_runtime_controller_map.bindings[i].target_id);",
            "            cpu_component_runtime_controller_clear();",
            "            return -1;",
            "        }",
            "    }",
            "    for (size_t i = 0; i < g_runtime_controller_map.binding_count; ++i) {",
            "        cpu_component_controller_target_get(g_runtime_controller_map.bindings[i].target_id, 1u);",
            "    }",
            "    g_runtime_controller_map.loaded = 1u;",
            "    return 0;",
            "}",
            "",
            "static float cpu_component_norm_axis_s16(int v) {",
                "    if (v >= 0) return (float)v / 32767.0f;",
                "    return (float)v / 32768.0f;",
            "}",
            "",
            "static float cpu_component_axis_apply(const RuntimeControllerBinding *b, float v) {",
            "    if (b->invert != 0u) v = -v;",
            "    if (v > -b->deadzone && v < b->deadzone) v = 0.0f;",
            "    v *= b->scale;",
            "    if (v > 1.0f) v = 1.0f;",
            "    if (v < -1.0f) v = -1.0f;",
            "    return v;",
            "}",
            "",
            "static void cpu_component_controller_map_poll(CPUState *cpu, uint8_t has_focus) {",
            "    (void)cpu;",
            "    if (g_runtime_controller_map.loaded == 0u) return;",
            "    if (g_runtime_controller_map.focus_required != 0u && has_focus == 0u) return;",
            "    for (size_t i = 0; i < g_runtime_controller_map.target_count; ++i) {",
            "        g_runtime_controller_map.targets[i].pressed = 0u;",
            "        g_runtime_controller_map.targets[i].axis = 0.0f;",
            "    }",
            "    if (cpu_component_host_picker_is_active() != 0u) return;",
            "    {",
            "        int key_count = 0;",
            "        const uint8_t *ks = cpu_host_hal_keyboard_state(&key_count);",
            "        for (size_t i = 0; i < g_runtime_controller_map.binding_count; ++i) {",
            "            const RuntimeControllerBinding *b = &g_runtime_controller_map.bindings[i];",
            "            uint8_t port_ok = 1u;",
            "            RuntimeControllerTarget *t;",
            "            uint8_t active = 0u;",
            "            float av = 0.0f;",
            "            if (b->port >= 1u && b->port <= 16u) port_ok = g_runtime_controller_map.port_connected[b->port - 1u];",
            "            if (port_ok == 0u) continue;",
            "            t = cpu_component_controller_target_get(b->target_id, 0u);",
            "            if (t == NULL) continue;",
            "            if (b->source_kind == 1u) {",
            "                if (ks && key_count > 0 && b->scancode >= 0 && b->scancode < key_count) {",
            "                    if (ks[b->scancode] != 0u) active = 1u;",
            "                }",
            "            } else if (b->source_kind == 2u || b->source_kind == 3u) {",
            "                int n = cpu_host_hal_gamepad_count();",
            "                for (int di = 0; di < n; ++di) {",
            "                    if (b->source_kind == 2u) {",
            "                        if (cpu_host_hal_gamepad_button(di, (int)b->control) != 0) { active = 1u; break; }",
            "                    } else {",
            "                        int v = cpu_host_hal_gamepad_axis(di, (int)b->control);",
            "                        float nv = cpu_component_axis_apply(b, cpu_component_norm_axis_s16(v));",
            "                        av = nv;",
            "                        if (b->extra > 0) { if (nv >= b->threshold) { active = 1u; break; } }",
            "                        else if (b->extra < 0) { if (nv <= -b->threshold) { active = 1u; break; } }",
            "                        else { if (nv >= b->threshold || nv <= -b->threshold) { active = 1u; break; } }",
            "                    }",
            "                }",
            "            } else if (b->source_kind == 4u || b->source_kind == 5u || b->source_kind == 6u) {",
            "                int n = cpu_host_hal_joystick_count();",
            "                for (int di = 0; di < n; ++di) {",
            "                    if (b->source_kind == 4u) {",
            "                        if (cpu_host_hal_joystick_button(di, (int)b->control) != 0) active = 1u;",
            "                    } else if (b->source_kind == 5u) {",
            "                        int v = cpu_host_hal_joystick_axis(di, (int)b->control);",
            "                        float nv = cpu_component_axis_apply(b, cpu_component_norm_axis_s16(v));",
            "                        av = nv;",
            "                        if (b->extra > 0) { if (nv >= b->threshold) active = 1u; }",
            "                        else if (b->extra < 0) { if (nv <= -b->threshold) active = 1u; }",
            "                        else { if (nv >= b->threshold || nv <= -b->threshold) active = 1u; }",
            "                    } else {",
            "                        uint8_t hv = cpu_host_hal_joystick_hat(di, (int)b->control);",
            "                        if ((hv & (uint8_t)b->extra) != 0u) active = 1u;",
            "                    }",
            "                    if (active != 0u) break;",
            "                }",
            "            }",
            "            if (active != 0u) {",
            "                t->pressed = 1u;",
            "                if (b->source_kind == 3u || b->source_kind == 5u) {",
            "                    { float aabs = (av < 0.0f) ? -av : av; float tabs = (t->axis < 0.0f) ? -t->axis : t->axis; if (aabs > tabs) t->axis = av; }",
            "                }",
            "            }",
            "        }",
            "    }",
            "}",
            "",
            "static uint8_t cpu_component_controller_pressed(const char *target_id) {",
            "    RuntimeControllerTarget *t = cpu_component_controller_target_get(target_id, 0u);",
            "    if (t == NULL) return 0u;",
            "    return (uint8_t)(t->pressed != 0u ? 1u : 0u);",
            "}",
            "",
            "static uint8_t cpu_component_controller_axis_u8(const char *target_id) {",
            "    RuntimeControllerTarget *t = cpu_component_controller_target_get(target_id, 0u);",
            "    float v;",
            "    int out;",
            "    if (t == NULL) return 128u;",
            "    v = t->axis;",
            "    if (v > 1.0f) v = 1.0f;",
            "    if (v < -1.0f) v = -1.0f;",
            "    out = (int)(((v + 1.0f) * 0.5f) * 255.0f);",
            "    if (out < 0) out = 0;",
            "    if (out > 255) out = 255;",
            "    return (uint8_t)out;",
            "}",
            "",
            "static void cpu_component_apply_declared_keymap(",
            "    CPUState *cpu,",
            "    const char *component_id,",
            "    const uint8_t *host_keys,",
            "    size_t host_key_count,",
            "    uint8_t *rows,",
            "    size_t row_count,",
            "    uint8_t has_focus",
            ") {",
            "    (void)cpu;",
            "    (void)component_id;",
            "    if (g_runtime_keyboard_map.loaded == 0u || g_runtime_keyboard_map.kind != 1u) return;",
            "    if (!rows || row_count == 0u || !host_keys || host_key_count == 0u) return;",
            "    if (g_runtime_keyboard_map.focus_required && has_focus == 0u) return;",
            "    if (cpu_component_host_picker_is_active() != 0u) return;",
            "    for (size_t i = 0; i < g_runtime_keyboard_map.binding_count; ++i) {",
            "        const RuntimeKeyboardBinding *b = &g_runtime_keyboard_map.bindings[i];",
            "        if (cpu_runtime_keyboard_binding_pressed(b, host_keys, host_key_count) == 0u) continue;",
            "        for (uint8_t p = 0u; p < b->press_count; ++p) {",
            "            const RuntimeKeyboardPress *pr = &b->presses[p];",
            "            if ((size_t)pr->row >= row_count || pr->bit > 7u) continue;",
            "            rows[pr->row] &= (uint8_t)~(1u << pr->bit);",
            "        }",
            "    }",
            "}",
            "",
            "static void cpu_component_keyboard_ascii_feed(",
            "    int32_t scancode,",
            "    const uint8_t *host_keys,",
            "    size_t host_key_count,",
            "    uint8_t has_focus",
            ") {",
            "    uint8_t shifted = 0u;",
            "    uint8_t controlled = 0u;",
            "    if (g_runtime_keyboard_map.loaded == 0u || g_runtime_keyboard_map.kind != 2u) return;",
            "    if (!host_keys || host_key_count == 0u) return;",
            "    if (g_runtime_keyboard_map.focus_required && has_focus == 0u) return;",
            "    if (cpu_component_host_picker_is_active() != 0u) return;",
            "    for (size_t i = 0; i < g_runtime_keyboard_map.binding_count; ++i) {",
            "        const RuntimeKeyboardBinding *m = &g_runtime_keyboard_map.bindings[i];",
            "        if (cpu_runtime_keyboard_binding_pressed(m, host_keys, host_key_count) == 0u) continue;",
            "        if (m->is_shift_modifier != 0u) shifted = 1u;",
            "        if (m->is_ctrl_modifier != 0u) controlled = 1u;",
            "    }",
            "    for (size_t i = 0; i < g_runtime_keyboard_map.binding_count; ++i) {",
            "        const RuntimeKeyboardBinding *b = &g_runtime_keyboard_map.bindings[i];",
            "        uint8_t out = 0u;",
            "        if (b->source_kind == 1u) {",
            "            if (b->scancode != scancode) continue;",
            "        } else if (b->source_kind == 2u) {",
            "            const char *key_name = cpu_host_hal_key_name(cpu_host_hal_key_from_scancode(scancode));",
            "            if (key_name == NULL || strcmp(key_name, b->host_key_name) != 0) continue;",
            "        } else {",
            "            continue;",
            "        }",
            "        if (controlled != 0u && b->has_ascii_ctrl != 0u) out = b->ascii_ctrl;",
            "        else if (shifted != 0u && b->has_ascii_shift != 0u) out = b->ascii_shift;",
            "        else if (b->has_ascii != 0u) out = b->ascii;",
            "        cpu_component_keyboard_ascii_queue_push(out);",
            "        return;",
            "    }",
            "}",
            "",
            "static uint8_t cpu_component_keyboard_ascii_pop(void) {",
            "    if (g_runtime_keyboard_map.loaded == 0u || g_runtime_keyboard_map.kind != 2u) return 0u;",
            "    return cpu_component_keyboard_ascii_queue_pop();",
            "}",
            "/* PASM_SPLIT_END:INPUT_RUNTIME */",
            "",
        ]
    )

    helper_lines.append("/* PASM_SPLIT_BEGIN:CARTRIDGE_PICKER_RUNTIME */")
    if has_runtime_cartridge or has_runtime_cassette or has_runtime_floppy:
        helper_lines.extend(
            [
                "enum { CPU_MEDIA_PICKER_NONE = 0u, CPU_MEDIA_PICKER_CARTRIDGE = 1u, CPU_MEDIA_PICKER_CASSETTE = 2u, CPU_MEDIA_PICKER_FLOPPY = 3u };",
                "static uint8_t g_runtime_media_picker_active_kind = CPU_MEDIA_PICKER_NONE;",
                "static uint8_t g_runtime_media_picker_switch_pending = 0u;",
                "static uint8_t g_runtime_media_picker_switch_target = CPU_MEDIA_PICKER_NONE;",
                "static uint8_t cpu_component_media_picker_first_kind(void) {",
                *(
                    ['    return CPU_MEDIA_PICKER_CARTRIDGE;']
                    if has_runtime_cartridge
                    else (['    return CPU_MEDIA_PICKER_CASSETTE;'] if has_runtime_cassette else (['    return CPU_MEDIA_PICKER_FLOPPY;'] if has_runtime_floppy else ['    return CPU_MEDIA_PICKER_NONE;']))
                ),
                "}",
                "static uint8_t cpu_component_media_picker_next_kind(uint8_t current_kind, int direction) {",
                "    static const uint8_t order[] = { CPU_MEDIA_PICKER_CARTRIDGE, CPU_MEDIA_PICKER_CASSETTE, CPU_MEDIA_PICKER_FLOPPY };",
                "    int start = -1;",
                "    int count = (int)(sizeof(order) / sizeof(order[0]));",
                "    for (int i = 0; i < count; ++i) { if (order[i] == current_kind) { start = i; break; } }",
                "    if (start < 0) return cpu_component_media_picker_first_kind();",
                "    for (int step = 1; step <= count; ++step) {",
                "        int idx = (start + ((direction >= 0) ? step : -step) + count * 4) % count;",
                "        uint8_t kind = order[idx];",
                *(
                    ["        if (kind == CPU_MEDIA_PICKER_CARTRIDGE) return kind;"]
                    if has_runtime_cartridge else []
                ),
                *(
                    ["        if (kind == CPU_MEDIA_PICKER_CASSETTE) return kind;"]
                    if has_runtime_cassette else []
                ),
                *(
                    ["        if (kind == CPU_MEDIA_PICKER_FLOPPY) return kind;"]
                    if has_runtime_floppy else []
                ),
                "    }",
                "    return current_kind;",
                "}",
                "",
            ]
        )
    if has_runtime_cartridge:
        helper_lines.extend(
            [
                "typedef struct {",
                "    char rom_path[1024];",
                "    char file_name[256];",
                "    char title[128];",
                "    char release_year[16];",
                "    char description[320];",
                "    char image_path[256];",
                "} RuntimeCartridgeEntry;",
                "",
                "typedef struct {",
                "    uint8_t supported;",
                "    uint8_t active;",
                "    uint8_t action_prev;",
                "    uint8_t nav_up_prev;",
                "    uint8_t nav_down_prev;",
                "    uint8_t nav_enter_prev;",
                "    uint8_t nav_esc_prev;",
                "    uint8_t nav_left_prev;",
                "    uint8_t nav_right_prev;",
                "    uint8_t input_blocked;",
                "    char directory[1024];",
                "    char status[256];",
                "    RuntimeCartridgeEntry *entries;",
                "    size_t entry_count;",
                "    size_t entry_cap;",
                "    size_t selected;",
                "    uint8_t pending_swap;",
                "    char pending_path[1024];",
                "} RuntimeCartridgePicker;",
                "",
                "static RuntimeCartridgePicker g_runtime_cartridge_picker = {",
                "    1u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, \"\", \"\", NULL, 0u, 0u, 0u, 0u, \"\"",
                "};",
                "",
                "static int cpu_component_cartridge_picker_entry_cmp(const void *a, const void *b) {",
                "    const RuntimeCartridgeEntry *ea = (const RuntimeCartridgeEntry *)a;",
                "    const RuntimeCartridgeEntry *eb = (const RuntimeCartridgeEntry *)b;",
                "    return strcmp(ea->file_name, eb->file_name);",
                "}",
                "",
                "static uint8_t cpu_component_rom_ext_allowed(const char *name) {",
                "    const char *dot = strrchr(name, '.');",
                "    char ext[16];",
                "    size_t n;",
                "    if (!dot || dot[1] == '\\0') return 0u;",
                "    dot++;",
                "    n = strlen(dot);",
                "    if (n >= sizeof(ext)) n = sizeof(ext) - 1u;",
                "    for (size_t i = 0; i < n; ++i) {",
                "        char c = dot[i];",
                "        if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a');",
                "        ext[i] = c;",
                "    }",
                "    ext[n] = '\\0';",
                *[
                    f'    if (strcmp(ext, "{_escape_c_string(ext)}") == 0) return 1u;'
                    for ext in cart_exts
                ],
                "    return 0u;",
                "}",
                "",
                "static void cpu_component_cartridge_picker_clear_entries(void) {",
                "    if (g_runtime_cartridge_picker.entries != NULL) {",
                "        free(g_runtime_cartridge_picker.entries);",
                "        g_runtime_cartridge_picker.entries = NULL;",
                "    }",
                "    g_runtime_cartridge_picker.entry_count = 0u;",
                "    g_runtime_cartridge_picker.entry_cap = 0u;",
                "    g_runtime_cartridge_picker.selected = 0u;",
                "}",
                "",
                "static RuntimeCartridgeEntry *cpu_component_cartridge_picker_add_entry(void) {",
                "    if (g_runtime_cartridge_picker.entry_count >= g_runtime_cartridge_picker.entry_cap) {",
                "        size_t new_cap = (g_runtime_cartridge_picker.entry_cap == 0u) ? 64u : (g_runtime_cartridge_picker.entry_cap * 2u);",
                "        RuntimeCartridgeEntry *ne = (RuntimeCartridgeEntry *)realloc(g_runtime_cartridge_picker.entries, new_cap * sizeof(RuntimeCartridgeEntry));",
                "        if (ne == NULL) return NULL;",
                "        memset(ne + g_runtime_cartridge_picker.entry_cap, 0, (new_cap - g_runtime_cartridge_picker.entry_cap) * sizeof(RuntimeCartridgeEntry));",
                "        g_runtime_cartridge_picker.entries = ne;",
                "        g_runtime_cartridge_picker.entry_cap = new_cap;",
                "    }",
                "    return &g_runtime_cartridge_picker.entries[g_runtime_cartridge_picker.entry_count++];",
                "}",
                "",
                "static void cpu_component_cartridge_picker_parse_sidecar(RuntimeCartridgeEntry *entry) {",
                "    char yaml_path[1024];",
                "    FILE *f;",
                "    char line[768];",
                "    char *dot;",
                "    if (entry == NULL) return;",
                "    snprintf(yaml_path, sizeof(yaml_path), \"%s\", entry->rom_path);",
                "    dot = strrchr(yaml_path, '.');",
                "    if (dot != NULL) {",
                "        snprintf(dot, (size_t)(yaml_path + sizeof(yaml_path) - dot), \".yaml\");",
                "    } else {",
                "        size_t n = strlen(yaml_path);",
                "        if (n + 5u >= sizeof(yaml_path)) return;",
                "        strcat(yaml_path, \".yaml\");",
                "    }",
                "    f = fopen(yaml_path, \"r\");",
                "    if (f == NULL) return;",
                "    while (fgets(line, sizeof(line), f) != NULL) {",
                "        char *hash = strchr(line, '#');",
                "        char *s;",
                "        if (hash) *hash = '\\0';",
                "        s = cpu_component_trim(line);",
                "        if (!s || s[0] == '\\0') continue;",
                "        if (strncmp(s, \"title:\", 6) == 0) {",
                "            char *v = cpu_component_unquote(cpu_component_trim(s + 6));",
                "            snprintf(entry->title, sizeof(entry->title), \"%s\", v ? v : \"\");",
                "            continue;",
                "        }",
                "        if (strncmp(s, \"release_year:\", 13) == 0) {",
                "            char *v = cpu_component_unquote(cpu_component_trim(s + 13));",
                "            snprintf(entry->release_year, sizeof(entry->release_year), \"%s\", v ? v : \"\");",
                "            continue;",
                "        }",
                "        if (strncmp(s, \"description:\", 12) == 0) {",
                "            char *v = cpu_component_unquote(cpu_component_trim(s + 12));",
                "            snprintf(entry->description, sizeof(entry->description), \"%s\", v ? v : \"\");",
                "            continue;",
                "        }",
                "        if (strncmp(s, \"image:\", 6) == 0) {",
                "            char *v = cpu_component_unquote(cpu_component_trim(s + 6));",
                "            snprintf(entry->image_path, sizeof(entry->image_path), \"%s\", v ? v : \"\");",
                "            continue;",
                "        }",
                "    }",
                "    fclose(f);",
                "}",
                "",
                "static int cpu_component_cartridge_picker_scan_dir(void) {",
                "#if defined(_WIN32)",
                "    snprintf(g_runtime_cartridge_picker.status, sizeof(g_runtime_cartridge_picker.status), \"cartridge picker unsupported on this backend\");",
                "    return -1;",
                "#else",
                "    DIR *d;",
                "    struct dirent *de;",
                "    cpu_component_cartridge_picker_clear_entries();",
                "    if (g_runtime_cartridge_picker.directory[0] == '\\0') {",
                "        snprintf(g_runtime_cartridge_picker.status, sizeof(g_runtime_cartridge_picker.status), \"missing --cartridge-dir\");",
                "        return -1;",
                "    }",
                "    d = opendir(g_runtime_cartridge_picker.directory);",
                "    if (d == NULL) {",
                "        snprintf(g_runtime_cartridge_picker.status, sizeof(g_runtime_cartridge_picker.status), \"cannot open dir: %s\", g_runtime_cartridge_picker.directory);",
                "        return -1;",
                "    }",
                "    while ((de = readdir(d)) != NULL) {",
                "        RuntimeCartridgeEntry *entry;",
                "        if (de->d_name[0] == '.') continue;",
                "        if (cpu_component_rom_ext_allowed(de->d_name) == 0u) continue;",
                "        entry = cpu_component_cartridge_picker_add_entry();",
                "        if (entry == NULL) {",
                "            closedir(d);",
                "            snprintf(g_runtime_cartridge_picker.status, sizeof(g_runtime_cartridge_picker.status), \"out of memory\");",
                "            return -1;",
                "        }",
                "        snprintf(entry->file_name, sizeof(entry->file_name), \"%s\", de->d_name);",
                "        snprintf(entry->rom_path, sizeof(entry->rom_path), \"%s/%s\", g_runtime_cartridge_picker.directory, de->d_name);",
                "        cpu_component_cartridge_picker_parse_sidecar(entry);",
                "    }",
                "    closedir(d);",
                "    if (g_runtime_cartridge_picker.entry_count == 0u) {",
                "        snprintf(g_runtime_cartridge_picker.status, sizeof(g_runtime_cartridge_picker.status), \"no ROM files found\");",
                "        return -1;",
                "    }",
                "    qsort(",
                "        g_runtime_cartridge_picker.entries,",
                "        g_runtime_cartridge_picker.entry_count,",
                "        sizeof(RuntimeCartridgeEntry),",
                "        cpu_component_cartridge_picker_entry_cmp",
                "    );",
                "    if (g_runtime_cartridge_picker.selected >= g_runtime_cartridge_picker.entry_count) {",
                "        g_runtime_cartridge_picker.selected = 0u;",
                "    }",
                "    snprintf(g_runtime_cartridge_picker.status, sizeof(g_runtime_cartridge_picker.status), \"select cartridge (%u)\", (unsigned)g_runtime_cartridge_picker.entry_count);",
                "    return 0;",
                "#endif",
                "}",
                "",
                "int cpu_component_cartridge_picker_set_dir(const char *path) {",
                "    if (path == NULL || path[0] == '\\0') return -1;",
                "    snprintf(g_runtime_cartridge_picker.directory, sizeof(g_runtime_cartridge_picker.directory), \"%s\", path);",
                "    g_runtime_cartridge_picker.active = 0u;",
                "    g_runtime_cartridge_picker.pending_swap = 0u;",
                "    g_runtime_cartridge_picker.pending_path[0] = '\\0';",
                "    snprintf(g_runtime_cartridge_picker.status, sizeof(g_runtime_cartridge_picker.status), \"cartridge dir set\");",
                "    return 0;",
                "}",
                "",
                "uint8_t cpu_component_cartridge_picker_is_active(void) {",
                "    return g_runtime_cartridge_picker.active;",
                "}",
                "uint8_t cpu_component_cartridge_picker_blocks_input(void) {",
                "    return (uint8_t)(g_runtime_cartridge_picker.active != 0u || g_runtime_cartridge_picker.input_blocked != 0u);",
                "}",
                "",
                "void cpu_component_cartridge_picker_update(CPUState *cpu, uint8_t has_focus) {",
                "    int key_count = 0;",
                "    const uint8_t *ks = cpu_host_hal_keyboard_state(&key_count);",
                "    static int raw_picker_keys_enabled = -1;",
                "    uint8_t trig;",
                "    uint8_t raw_trig = 0u;",
                "    uint8_t up;",
                "    uint8_t down;",
                "    uint8_t enter;",
                "    uint8_t esc;",
                "    if (!cpu) return;",
                "    if (g_runtime_cartridge_picker.supported == 0u) return;",
                "    if (raw_picker_keys_enabled < 0) {",
                "        const char *env = getenv(\"PASM_EMU_CART_PICKER_RAW_KEYS\");",
                "        raw_picker_keys_enabled = (env == NULL || env[0] == '\\0' || env[0] != '0') ? 1 : 0;",
                "    }",
                f'    trig = cpu_component_keyboard_emulator_action_pressed("{_escape_c_string(media_picker_action)}", ks, (size_t)((key_count < 0) ? 0 : key_count), has_focus);',
                "    if (raw_picker_keys_enabled != 0 && ks != NULL && key_count > 0) {",
                "        if ((size_t)CPU_HOST_SCANCODE(F12) < (size_t)key_count && ks[CPU_HOST_SCANCODE(F12)] != 0u) raw_trig = 1u;",
                "    }",
                "    if (raw_trig != 0u) trig = 1u;",
                "    if (trig != 0u && g_runtime_cartridge_picker.action_prev == 0u) {",
                "        if (g_runtime_cartridge_picker.active == 0u) {",
                "            if (cpu_component_cartridge_picker_scan_dir() == 0) {",
                "                g_runtime_cartridge_picker.active = 1u;",
                "            }",
                "        } else {",
                "            g_runtime_cartridge_picker.active = 0u;",
                "            g_runtime_cartridge_picker.input_blocked = 1u;",
                "        }",
                "    }",
                "    g_runtime_cartridge_picker.action_prev = trig;",
                "    if (g_runtime_cartridge_picker.input_blocked != 0u) {",
                "        uint8_t any_nav = 0u;",
                "        if (trig != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(UP) < (size_t)key_count && ks[CPU_HOST_SCANCODE(UP)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(DOWN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(DOWN)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(RETURN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(RETURN)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(KP_ENTER) < (size_t)key_count && ks[CPU_HOST_SCANCODE(KP_ENTER)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(ESCAPE) < (size_t)key_count && ks[CPU_HOST_SCANCODE(ESCAPE)] != 0u) any_nav = 1u;",
                "        if (any_nav == 0u) g_runtime_cartridge_picker.input_blocked = 0u;",
                "    }",
                "    if (g_runtime_cartridge_picker.active == 0u) return;",
                "    if (!ks || key_count <= 0) return;",
                "    up = ((size_t)CPU_HOST_SCANCODE(UP) < (size_t)key_count && ks[CPU_HOST_SCANCODE(UP)] != 0u) ? 1u : 0u;",
                "    down = ((size_t)CPU_HOST_SCANCODE(DOWN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(DOWN)] != 0u) ? 1u : 0u;",
                "    enter = (((size_t)CPU_HOST_SCANCODE(RETURN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(RETURN)] != 0u) || ((size_t)CPU_HOST_SCANCODE(KP_ENTER) < (size_t)key_count && ks[CPU_HOST_SCANCODE(KP_ENTER)] != 0u)) ? 1u : 0u;",
                "    esc = ((size_t)CPU_HOST_SCANCODE(ESCAPE) < (size_t)key_count && ks[CPU_HOST_SCANCODE(ESCAPE)] != 0u) ? 1u : 0u;",
                "    if (up != 0u && g_runtime_cartridge_picker.nav_up_prev == 0u) {",
                "        if (g_runtime_cartridge_picker.entry_count > 0u) {",
                "            if (g_runtime_cartridge_picker.selected == 0u) g_runtime_cartridge_picker.selected = g_runtime_cartridge_picker.entry_count - 1u;",
                "            else g_runtime_cartridge_picker.selected -= 1u;",
                "        }",
                "    }",
                "    if (down != 0u && g_runtime_cartridge_picker.nav_down_prev == 0u) {",
                "        if (g_runtime_cartridge_picker.entry_count > 0u) {",
                "            g_runtime_cartridge_picker.selected = (g_runtime_cartridge_picker.selected + 1u) % g_runtime_cartridge_picker.entry_count;",
                "        }",
                "    }",
                "    if (esc != 0u && g_runtime_cartridge_picker.nav_esc_prev == 0u) {",
                "        g_runtime_cartridge_picker.active = 0u;",
                "        g_runtime_cartridge_picker.input_blocked = 1u;",
                "    }",
                "    if (enter != 0u && g_runtime_cartridge_picker.nav_enter_prev == 0u) {",
                "        if (g_runtime_cartridge_picker.entry_count > 0u) {",
                "            const RuntimeCartridgeEntry *sel = &g_runtime_cartridge_picker.entries[g_runtime_cartridge_picker.selected];",
                "            snprintf(g_runtime_cartridge_picker.pending_path, sizeof(g_runtime_cartridge_picker.pending_path), \"%s\", sel->rom_path);",
                "            g_runtime_cartridge_picker.pending_swap = 1u;",
                "            snprintf(",
                "                cpu->loaded_rom_debug,",
                "                sizeof(cpu->loaded_rom_debug),",
                "                \"name=cartridge path=%s\",",
                "                sel->rom_path",
                "            );",
                "            snprintf(g_runtime_cartridge_picker.status, sizeof(g_runtime_cartridge_picker.status), \"queued: %s\", sel->file_name);",
                "        }",
                "        g_runtime_cartridge_picker.active = 0u;",
                "        g_runtime_cartridge_picker.input_blocked = 1u;",
                "    }",
                "    g_runtime_cartridge_picker.nav_up_prev = up;",
                "    g_runtime_cartridge_picker.nav_down_prev = down;",
                "    g_runtime_cartridge_picker.nav_enter_prev = enter;",
                "    g_runtime_cartridge_picker.nav_esc_prev = esc;",
                "}",
                "",
                "int cpu_component_cartridge_picker_apply_pending_swap(CPUState *cpu) {",
                "    if (!cpu) return -1;",
                "    if (g_runtime_cartridge_picker.pending_swap == 0u) return 0;",
                f"    if ({cpu_prefix}_load_cartridge_rom(cpu, g_runtime_cartridge_picker.pending_path) != 0) {{",
                "        snprintf(g_runtime_cartridge_picker.status, sizeof(g_runtime_cartridge_picker.status), \"load failed: %s\", g_runtime_cartridge_picker.pending_path);",
                "        g_runtime_cartridge_picker.pending_swap = 0u;",
                "        g_runtime_cartridge_picker.pending_path[0] = '\\0';",
                "        return -1;",
                "    }",
                "    {",
                "        const char *sysdir = getenv(\"PASM_SYSTEM_DIR\");",
                "        if (sysdir != NULL && sysdir[0] != '\\0') {",
                "            if (cpu->memory != NULL && cpu->memory_size > 0u) {",
                "                memset(cpu->memory, 0, (size_t)cpu->memory_size);",
                "            }",
                "            if (cpu->port_memory != NULL && cpu->port_size > 0u) {",
                "                memset(cpu->port_memory, 0, (size_t)cpu->port_size);",
                "            }",
                f"            if ({cpu_prefix}_load_system_roms(cpu, sysdir) != 0) {{",
                "                snprintf(g_runtime_cartridge_picker.status, sizeof(g_runtime_cartridge_picker.status), \"system ROM reload failed\");",
                "                g_runtime_cartridge_picker.pending_swap = 0u;",
                "                g_runtime_cartridge_picker.pending_path[0] = '\\0';",
                "                return -1;",
                "            }",
                "        } else {",
                "            snprintf(g_runtime_cartridge_picker.status, sizeof(g_runtime_cartridge_picker.status), \"system dir missing; reusing current memory image\");",
                "        }",
                "    }",
                f"    {cpu_prefix}_reset(cpu);",
                "    cpu->running = true;",
                "    cpu->halted = false;",
                "    cpu->error_code = CPU_ERROR_NONE;",
                "    snprintf(",
                "        cpu->loaded_rom_debug,",
                "        sizeof(cpu->loaded_rom_debug),",
                "        \"name=cartridge path=%s\",",
                "        g_runtime_cartridge_picker.pending_path",
                "    );",
                "    g_runtime_cartridge_picker.pending_swap = 0u;",
                "    g_runtime_cartridge_picker.pending_path[0] = '\\0';",
                "    return 1;",
                "}",
                "",
                "static void cpu_component_cartridge_picker_draw_text(",
                "    uint32_t *pixels,",
                "    uint32_t w,",
                "    uint32_t h,",
                "    int x,",
                "    int y,",
                "    const char *text,",
                "    int scale,",
                "    uint32_t color",
                ") {",
                "    if (!text || text[0] == '\\0') return;",
                "    if (scale > 0) {",
                "        pasm_overlay_draw_text(pixels, w, h, x, y, text, scale, color);",
                "        return;",
                "    }",
                "    {",
                "        int cx = x;",
                "        for (const char *p = text; *p; ++p) {",
                "            const uint8_t *glyph = pasm_overlay_glyph(*p);",
                "            for (int row = 0; row < 7; row += 2) {",
                "                uint8_t bits = glyph[row];",
                "                int ty = y + (row / 2);",
                "                for (int col = 0; col < 5; col += 2) {",
                "                    if ((bits & (uint8_t)(1u << (4 - col))) == 0u) continue;",
                "                    pasm_overlay_put_pixel(pixels, w, h, cx + (col / 2), ty, color);",
                "                }",
                "            }",
                "            cx += 4;",
                "        }",
                "    }",
                "}",
                "",
                "static void cpu_component_cartridge_picker_draw_text_fit(",
                "    uint32_t *pixels,",
                "    uint32_t w,",
                "    uint32_t h,",
                "    int x,",
                "    int y,",
                "    const char *text,",
                "    int scale,",
                "    uint32_t color,",
                "    int max_px",
                ") {",
                "    char buf[320];",
                "    size_t n = 0u;",
                "    int cell_px = (scale > 0) ? (6 * scale) : 4;",
                "    int max_chars;",
                "    if (!text || text[0] == '\\0') return;",
                "    if (cell_px <= 0) cell_px = 1;",
                "    max_chars = (max_px > 0) ? (max_px / cell_px) : 0;",
                "    if (max_chars <= 0) return;",
                "    while (text[n] != '\\0' && n < (size_t)max_chars && n < sizeof(buf) - 1u) {",
                "        buf[n] = text[n];",
                "        n++;",
                "    }",
                "    if (text[n] != '\\0' && n >= 3u) {",
                "        buf[n - 3u] = '.';",
                "        buf[n - 2u] = '.';",
                "        buf[n - 1u] = '.';",
                "    }",
                "    buf[n] = '\\0';",
                "    cpu_component_cartridge_picker_draw_text(pixels, w, h, x, y, buf, scale, color);",
                "}",
                "",
                "static int cpu_component_cartridge_picker_draw_text_wrap(",
                "    uint32_t *pixels,",
                "    uint32_t w,",
                "    uint32_t h,",
                "    int x,",
                "    int y,",
                "    const char *text,",
                "    int scale,",
                "    uint32_t color,",
                "    int max_px,",
                "    int max_lines",
                ") {",
                "    char line[320];",
                "    int cell_px = (scale > 0) ? (6 * scale) : 4;",
                "    int max_chars;",
                "    int lines_drawn = 0;",
                "    const char *p = text;",
                "    if (!text || text[0] == '\\0' || max_lines <= 0) return 0;",
                "    if (cell_px <= 0) cell_px = 1;",
                "    max_chars = (max_px > 0) ? (max_px / cell_px) : 0;",
                "    if (max_chars <= 0) return 0;",
                "    while (*p != '\\0' && lines_drawn < max_lines) {",
                "        int n = 0;",
                "        int last_space = -1;",
                "        const char *seg = p;",
                "        while (seg[n] != '\\0' && seg[n] != '\\n' && n < max_chars && n < (int)sizeof(line) - 1) {",
                "            if (seg[n] == ' ') last_space = n;",
                "            n++;",
                "        }",
                "        if (seg[n] != '\\0' && seg[n] != '\\n' && n == max_chars && last_space > 0) {",
                "            n = last_space;",
                "        }",
                "        if (n <= 0) n = (seg[0] != '\\0') ? 1 : 0;",
                "        if (n <= 0) break;",
                "        memcpy(line, seg, (size_t)n);",
                "        line[n] = '\\0';",
                "        cpu_component_cartridge_picker_draw_text(pixels, w, h, x, y + lines_drawn * ((scale > 0) ? (8 * scale + 1) : 5), line, scale, color);",
                "        lines_drawn++;",
                "        p = seg + n;",
                "        while (*p == ' ') p++;",
                "        if (*p == '\\n') p++;",
                "    }",
                "    return lines_drawn;",
                "}",
                "",
                "void cpu_component_cartridge_picker_draw_overlay(CPUState *cpu, uint32_t *pixels, uint32_t w, uint32_t h) {",
                "    int scale = g_runtime_cartridge_picker_font_scale;",
                "    int x = 10;",
                "    int y = 24;",
                "    int row_h = (scale > 0) ? (8 * scale + 1) : 5;",
                "    int max_rows = 10;",
                "    int right_pad = 14;",
                "    int text_w = (int)w - x - right_pad;",
                "    size_t first;",
                "    (void)cpu;",
                "    if (!pixels || w == 0u || h == 0u) return;",
                "    if (g_runtime_cartridge_picker.active == 0u) return;",
                "    if (g_runtime_cartridge_picker.entry_count == 0u) return;",
                "    pasm_overlay_fill_rect_alpha(pixels, w, h, 6, 20, (int)w - 12, (int)h - 26, 0x00101010u, 190u);",
                "    cpu_component_cartridge_picker_draw_text_fit(pixels, w, h, x, y, \"CARTRIDGE PICKER\", scale, 0xFFFFFFFFu, text_w);",
                "    y += row_h * 2;",
                "    first = (g_runtime_cartridge_picker.selected >= 4u) ? (g_runtime_cartridge_picker.selected - 4u) : 0u;",
                "    for (int i = 0; i < max_rows; ++i) {",
                "        size_t idx = first + (size_t)i;",
                "        char line[320];",
                "        if (idx >= g_runtime_cartridge_picker.entry_count) break;",
                "        const RuntimeCartridgeEntry *e = &g_runtime_cartridge_picker.entries[idx];",
                "        uint32_t fg = (idx == g_runtime_cartridge_picker.selected) ? 0xFF00FF9Fu : 0xFFE0E0E0u;",
                "        if (e->title[0] != '\\0') snprintf(line, sizeof(line), \"%s (%s)\", e->title, (e->release_year[0] ? e->release_year : \"?\"));",
                "        else snprintf(line, sizeof(line), \"%s\", e->file_name);",
                "        cpu_component_cartridge_picker_draw_text_fit(pixels, w, h, x, y + i * row_h, line, scale, fg, text_w);",
                "    }",
                "    {",
                "        const RuntimeCartridgeEntry *sel = &g_runtime_cartridge_picker.entries[g_runtime_cartridge_picker.selected];",
                "        int info_y = y + max_rows * row_h + 8;",
                "        char info[384];",
                "        snprintf(info, sizeof(info), \"FILE: %s\", sel->file_name);",
                "        int file_lines = cpu_component_cartridge_picker_draw_text_wrap(pixels, w, h, x, info_y, info, scale, 0xFFC8C8FFu, text_w, 6);",
                "        if (file_lines <= 0) file_lines = 1;",
                "        if (sel->description[0] != '\\0') {",
                "            cpu_component_cartridge_picker_draw_text_fit(pixels, w, h, x, info_y + (file_lines * row_h), sel->description, scale, 0xFFDDDDDDu, text_w);",
                "        }",
                "        if (sel->image_path[0] != '\\0') {",
                "            char img[320];",
                "            snprintf(img, sizeof(img), \"IMG: %s\", sel->image_path);",
                "            cpu_component_cartridge_picker_draw_text_fit(pixels, w, h, x, info_y + ((file_lines + 1) * row_h), img, scale, 0xFFBBBBBBu, text_w);",
                "        }",
                "    }",
                "    cpu_component_cartridge_picker_draw_text_fit(pixels, w, h, x, (int)h - ((scale > 0) ? (14 * scale) : 8), \"UP/DOWN SELECT  ENTER LOAD+RESET  ESC CANCEL\", scale, 0xFFFFFFA0u, text_w);",
                "}",
                "",
            ]
        )
    else:
        helper_lines.extend(
            [
                "int cpu_component_cartridge_picker_set_dir(const char *path) {",
                "    (void)path;",
                "    return -1;",
                "}",
                "int cpu_component_cartridge_picker_apply_pending_swap(CPUState *cpu) {",
                "    (void)cpu;",
                "    return 0;",
                "}",
                "uint8_t cpu_component_cartridge_picker_is_active(void) { return 0u; }",
                "uint8_t cpu_component_cartridge_picker_blocks_input(void) { return 0u; }",
                "void cpu_component_cartridge_picker_update(CPUState *cpu, uint8_t has_focus) {",
                "    (void)cpu;",
                "    (void)has_focus;",
                "}",
                "void cpu_component_cartridge_picker_draw_overlay(CPUState *cpu, uint32_t *pixels, uint32_t w, uint32_t h) {",
                "    (void)cpu;",
                "    (void)pixels;",
                "    (void)w;",
                "    (void)h;",
                "}",
                "",
            ]
        )

    if has_runtime_cassette:
        helper_lines.extend(
            [
                "typedef struct {",
                "    uint8_t source_kind;",
                "    uint8_t source_index;",
                "    char media_path[1024];",
                "    char file_name[256];",
                "    char component_id[64];",
                "    char source_component_id[64];",
                "    char source_model[64];",
                "    char source_label[64];",
                "} RuntimeCassetteEntry;",
                "",
                "typedef struct {",
                "    uint8_t active;",
                "    uint8_t action_prev;",
                "    uint8_t nav_up_prev;",
                "    uint8_t nav_down_prev;",
                "    uint8_t nav_enter_prev;",
                "    uint8_t nav_esc_prev;",
                "    uint8_t nav_left_prev;",
                "    uint8_t nav_right_prev;",
                "    uint8_t input_blocked;",
                "    uint8_t play_prev;",
                "    uint8_t pause_prev;",
                "    uint8_t stop_prev;",
                "    uint8_t record_prev;",
                "    uint8_t vol_up_prev;",
                "    uint8_t vol_down_prev;",
                "    char directory[1024];",
                "    RuntimeCassetteEntry *entries;",
                "    size_t entry_count;",
                "    size_t entry_cap;",
                "    size_t selected;",
                "    uint8_t active_source_kind;",
                "    uint8_t active_source_index;",
                "    uint8_t pending_load;",
                "    uint8_t pending_source_index;",
                "    uint8_t pending_source_kind;",
                "    char pending_path[1024];",
                "    char active_component_id[64];",
                "    char active_source_component_id[64];",
                "    char active_source_model[64];",
                "    char active_source_label[64];",
                "    char loaded_name[256];",
                "    uint8_t media_loaded;",
                "    uint8_t transport_mode;",
                "    uint8_t motor_on;",
                "    uint16_t current_seconds;",
                "    uint16_t total_seconds;",
                "    uint8_t volume_percent;",
                "    uint64_t status_until_cycle;",
                "    uint64_t status_now_cycle;",
                "    uint8_t last_transport_mode;",
                "} RuntimeCassettePicker;",
                "",
                "static RuntimeCassettePicker g_runtime_cassette_picker = {",
                f"    0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, \"{_escape_c_string(str(cassette_cfg.get('directory', '')))}\", NULL, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, \"\", \"{_escape_c_string(cassette_component_id)}\", \"{_escape_c_string(cassette_component_id)}\", \"\", \"\", \"\", 0u, 0u, 0u, 0u, 100u, 0u, 0u, 0u",
                "};",
                "static int cpu_component_cassette_entry_cmp(const void *a, const void *b) {",
                "    const RuntimeCassetteEntry *ea = (const RuntimeCassetteEntry *)a;",
                "    const RuntimeCassetteEntry *eb = (const RuntimeCassetteEntry *)b;",
                "    if (ea->source_kind != eb->source_kind) return (ea->source_kind == 1u) ? -1 : 1;",
                "    return strcmp(ea->file_name, eb->file_name);",
                "}",
                "static RuntimeCassetteEntry *cpu_component_cassette_add_entry(void) {",
                "    if (g_runtime_cassette_picker.entry_count >= g_runtime_cassette_picker.entry_cap) {",
                "        size_t new_cap = (g_runtime_cassette_picker.entry_cap == 0u) ? 64u : (g_runtime_cassette_picker.entry_cap * 2u);",
                "        RuntimeCassetteEntry *ne = (RuntimeCassetteEntry *)realloc(g_runtime_cassette_picker.entries, new_cap * sizeof(RuntimeCassetteEntry));",
                "        if (ne == NULL) return NULL;",
                "        memset(ne + g_runtime_cassette_picker.entry_cap, 0, (new_cap - g_runtime_cassette_picker.entry_cap) * sizeof(RuntimeCassetteEntry));",
                "        g_runtime_cassette_picker.entries = ne;",
                "        g_runtime_cassette_picker.entry_cap = new_cap;",
                "    }",
                "    return &g_runtime_cassette_picker.entries[g_runtime_cassette_picker.entry_count++];",
                "}",
                "static uint8_t cpu_component_cassette_ext_allowed(const char *name) {",
                "    const char *dot = strrchr(name, '.');",
                "    char ext[16];",
                "    size_t n;",
                "    if (!dot || dot[1] == '\\0') return 0u;",
                "    dot++;",
                "    n = strlen(dot);",
                "    if (n >= sizeof(ext)) n = sizeof(ext) - 1u;",
                "    for (size_t i = 0; i < n; ++i) { char c = dot[i]; if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a'); ext[i] = c; }",
                "    ext[n] = '\\0';",
                *[
                    f'    if (strcmp(ext, "{_escape_c_string(ext)}") == 0) return 1u;'
                    for ext in cassette_all_exts
                ],
                "    return 0u;",
                "}",
                "static const char *cpu_component_cassette_component_for_ext(const char *name, uint8_t *out_source_index) {",
                "    const char *dot = strrchr(name, '.');",
                "    char ext[16];",
                "    size_t n;",
                "    if (out_source_index != NULL) *out_source_index = 0u;",
                "    if (!dot || dot[1] == '\\0') return NULL;",
                "    dot++;",
                "    n = strlen(dot);",
                "    if (n >= sizeof(ext)) n = sizeof(ext) - 1u;",
                "    for (size_t i = 0; i < n; ++i) { char c = dot[i]; if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a'); ext[i] = c; }",
                "    ext[n] = '\\0';",
                *[
                    line
                    for source in cassette_file_sources
                    for ext in source["allowed_extensions"]
                    for line in [
                        f'    if (strcmp(ext, "{_escape_c_string(ext)}") == 0) {{',
                        f'        if (out_source_index != NULL) *out_source_index = {int(source["index"])}u;',
                        f'        return "{_escape_c_string(source["component"])}";',
                        "    }",
                    ]
                ],
                "    return NULL;",
                "}",
                "static const char *cpu_component_cassette_component_for_source_index(uint8_t source_index) {",
                *[
                    f'    if (source_index == {int(source["index"])}u) return "{_escape_c_string(source["component"])}";'
                    for source in cassette_sources
                ],
                f'    return "{_escape_c_string(cassette_component_id)}";',
                "}",
                "static const char *cpu_component_cassette_source_component_for_source_index(uint8_t source_index) {",
                *[
                    f'    if (source_index == {int(source["index"])}u) return "{_escape_c_string(source["source_component"])}";'
                    for source in cassette_sources
                ],
                f'    return "{_escape_c_string(cassette_component_id)}";',
                "}",
                "static uint8_t cpu_component_cassette_kind_for_source_index(uint8_t source_index) {",
                *[
                    f'    if (source_index == {int(source["index"])}u) return {1 if source["kind"] == "line_in" else 0}u;'
                    for source in cassette_sources
                ],
                "    return 0u;",
                "}",
                "static const char *cpu_component_cassette_model_for_source_index(uint8_t source_index) {",
                *[
                    f'    if (source_index == {int(source["index"])}u) return "{_escape_c_string(source["model"])}";'
                    for source in cassette_sources
                ],
                '    return "";',
                "}",
                "static const char *cpu_component_cassette_model_for_ext(const char *name) {",
                "    const char *dot = strrchr(name, '.');",
                "    char ext[16];",
                "    size_t n;",
                "    if (!dot || dot[1] == '\\0') return NULL;",
                "    dot++;",
                "    n = strlen(dot);",
                "    if (n >= sizeof(ext)) n = sizeof(ext) - 1u;",
                "    for (size_t i = 0; i < n; ++i) { char c = dot[i]; if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a'); ext[i] = c; }",
                "    ext[n] = '\\0';",
                *[
                    line
                    for source in cassette_file_sources
                    for ext in source["allowed_extensions"]
                    for line in [
                        f'    if (strcmp(ext, "{_escape_c_string(ext)}") == 0) return cpu_component_cassette_model_for_source_index({int(source["index"])}u);',
                    ]
                ],
                "    return NULL;",
                "}",
                "static const char *cpu_component_cassette_label_for_model(const char *model) {",
                "    if (model == NULL || model[0] == '\\0') return \"Unknown\";",
                *[
                    f'    if (strcmp(model, "{_escape_c_string(source["model"])}") == 0) return "{_escape_c_string(source["label"])}";'
                    for source in cassette_sources
                ],
                "    return \"Unknown\";",
                "}",
                "static int cpu_component_cassette_picker_scan_dir(void) {",
                "#if defined(_WIN32)",
                "    return -1;",
                "#else",
                "    DIR *d;",
                "    struct dirent *de;",
                "    if (g_runtime_cassette_picker.entries != NULL) { free(g_runtime_cassette_picker.entries); g_runtime_cassette_picker.entries = NULL; }",
                "    g_runtime_cassette_picker.entry_count = 0u;",
                "    g_runtime_cassette_picker.entry_cap = 0u;",
                "    if (g_runtime_cassette_picker.directory[0] == '\\0') return -1;",
                "    d = opendir(g_runtime_cassette_picker.directory);",
                "    if (d == NULL) return -1;",
                "    while ((de = readdir(d)) != NULL) {",
                "        RuntimeCassetteEntry *entry;",
                "        const char *component_id;",
                "        const char *source_model;",
                "        uint8_t source_index = 0u;",
                "        if (de->d_name[0] == '.') continue;",
                "        if (cpu_component_cassette_ext_allowed(de->d_name) == 0u) continue;",
                "        component_id = cpu_component_cassette_component_for_ext(de->d_name, &source_index);",
                "        source_model = cpu_component_cassette_model_for_source_index(source_index);",
                "        if (component_id == NULL || component_id[0] == '\\0') continue;",
                "        entry = cpu_component_cassette_add_entry();",
                "        if (entry == NULL) { closedir(d); return -1; }",
                "        entry->source_kind = 0u;",
                "        entry->source_index = source_index;",
                "        snprintf(entry->file_name, sizeof(entry->file_name), \"%s\", de->d_name);",
                "        snprintf(entry->media_path, sizeof(entry->media_path), \"%s/%s\", g_runtime_cassette_picker.directory, de->d_name);",
                "        snprintf(entry->component_id, sizeof(entry->component_id), \"%s\", component_id);",
                "        snprintf(entry->source_component_id, sizeof(entry->source_component_id), \"%s\", cpu_component_cassette_source_component_for_source_index(source_index));",
                "        if (source_model != NULL) snprintf(entry->source_model, sizeof(entry->source_model), \"%s\", source_model); else entry->source_model[0] = '\\0';",
                "        snprintf(entry->source_label, sizeof(entry->source_label), \"%s\", cpu_component_cassette_label_for_model(entry->source_model));",
                "    }",
                "    closedir(d);",
                *[
                    line
                    for source in cassette_line_in_sources
                    for line in [
                        "    {",
                        "        RuntimeCassetteEntry *entry = cpu_component_cassette_add_entry();",
                        "        if (entry == NULL) return -1;",
                        "        entry->source_kind = 1u;",
                        f"        entry->source_index = {int(source['index'])}u;",
                        "        entry->media_path[0] = '\\0';",
                        f'        snprintf(entry->file_name, sizeof(entry->file_name), "%s", "{_escape_c_string(source["label"])}");',
                        f'        snprintf(entry->component_id, sizeof(entry->component_id), "%s", cpu_component_cassette_component_for_source_index({int(source["index"])}u));',
                        f'        snprintf(entry->source_component_id, sizeof(entry->source_component_id), "%s", cpu_component_cassette_source_component_for_source_index({int(source["index"])}u));',
                        f'        snprintf(entry->source_model, sizeof(entry->source_model), "%s", cpu_component_cassette_model_for_source_index({int(source["index"])}u));',
                        f'        snprintf(entry->source_label, sizeof(entry->source_label), "%s", "{_escape_c_string(source["label"])}");',
                        "    }",
                    ]
                ],
                "    if (g_runtime_cassette_picker.entry_count == 0u) return -1;",
                "    qsort(g_runtime_cassette_picker.entries, g_runtime_cassette_picker.entry_count, sizeof(RuntimeCassetteEntry), cpu_component_cassette_entry_cmp);",
                "    return 0;",
                "#endif",
                "}",
                "uint8_t cpu_component_cassette_picker_is_active(void) { return g_runtime_cassette_picker.active; }",
                "uint8_t cpu_component_cassette_picker_blocks_input(void) { return (uint8_t)(g_runtime_cassette_picker.active != 0u || g_runtime_cassette_picker.input_blocked != 0u); }",
                "uint8_t cpu_component_cassette_picker_overlay_visible(void) {",
                "    uint8_t effective_mode = g_runtime_cassette_picker.transport_mode;",
                "    uint8_t has_source = (uint8_t)(g_runtime_cassette_picker.active_source_model[0] != '\\0');",
                (
                    "    if (effective_mode == 1u && g_runtime_cassette_picker.motor_on == 0u) effective_mode = 0u;"
                    if cassette_play_sets_motor
                    else ""
                ),
                "    if (g_runtime_cassette_picker.active != 0u) return 1u;",
                "    if ((g_runtime_cassette_picker.media_loaded != 0u || has_source != 0u) &&",
                "        (effective_mode != 0u || g_runtime_cassette_picker.status_now_cycle < g_runtime_cassette_picker.status_until_cycle)) return 1u;",
                "    return 0u;",
                "}",
                "int cpu_component_cassette_picker_apply_pending_load(CPUState *cpu) {",
                "    if (g_runtime_cassette_picker.pending_load == 0u) return 0;",
                "    if (g_runtime_cassette_picker.active_component_id[0] == '\\0') {",
                f'        snprintf(g_runtime_cassette_picker.active_component_id, sizeof(g_runtime_cassette_picker.active_component_id), "%s", "{_escape_c_string(cassette_component_id)}");',
                "    }",
                "    g_runtime_cassette_picker.active_source_kind = g_runtime_cassette_picker.pending_source_kind;",
                "    g_runtime_cassette_picker.active_source_index = g_runtime_cassette_picker.pending_source_index;",
                "    {",
                "        uint64_t select_args[4] = {",
                "            (uint64_t)g_runtime_cassette_picker.pending_source_kind,",
                "            (uint64_t)g_runtime_cassette_picker.pending_source_index,",
                "            (uint64_t)(uintptr_t)g_runtime_cassette_picker.active_source_model,",
                "            (uint64_t)(uintptr_t)g_runtime_cassette_picker.active_source_component_id",
                "        };",
                '        if (cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "select_source", select_args, 4) == 0u) {',
                "            g_runtime_cassette_picker.pending_load = 0u;",
                "            g_runtime_cassette_picker.pending_source_index = 0u;",
                "            g_runtime_cassette_picker.pending_source_kind = 0u;",
                "            g_runtime_cassette_picker.pending_path[0] = '\\0';",
                "            return -1;",
                "        }",
                "    }",
                "    if (g_runtime_cassette_picker.pending_source_kind == 1u) {",
                '        uint64_t args[1] = { (uint64_t)(uintptr_t)"" };',
                '        if (cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "load_media", args, 1) == 0u) {',
                "            g_runtime_cassette_picker.pending_load = 0u;",
                "            g_runtime_cassette_picker.pending_source_index = 0u;",
                "            g_runtime_cassette_picker.pending_source_kind = 0u;",
                "            return -1;",
                "        }",
                "        g_runtime_cassette_picker.pending_load = 0u;",
                "        g_runtime_cassette_picker.pending_source_index = 0u;",
                "        g_runtime_cassette_picker.pending_source_kind = 0u;",
                "        g_runtime_cassette_picker.pending_path[0] = '\\0';",
                "        g_runtime_cassette_picker.media_loaded = 1u;",
                "        g_runtime_cassette_picker.transport_mode = 0u;",
                "        g_runtime_cassette_picker.motor_on = 0u;",
                "        g_runtime_cassette_picker.current_seconds = 0u;",
                "        g_runtime_cassette_picker.total_seconds = 0u;",
                "        g_runtime_cassette_picker.status_now_cycle = cpu->total_cycles;",
                "        g_runtime_cassette_picker.status_until_cycle = cpu->total_cycles + (uint64_t)(CPU_SYSTEM_CLOCK_HZ * 10u);",
                "        if (g_runtime_cassette_picker.active_source_label[0] != '\\0') {",
                "            snprintf(g_runtime_cassette_picker.loaded_name, sizeof(g_runtime_cassette_picker.loaded_name), \"%s\", g_runtime_cassette_picker.active_source_label);",
                "        }",
                "        return 1;",
                "    }",
                "    {",
                "        uint64_t args[1] = { (uint64_t)(uintptr_t)g_runtime_cassette_picker.pending_path };",
                '        if (cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "load_media", args, 1) == 0u) {',
                "            g_runtime_cassette_picker.pending_load = 0u;",
                "            g_runtime_cassette_picker.pending_source_index = 0u;",
                "            g_runtime_cassette_picker.pending_source_kind = 0u;",
                "            g_runtime_cassette_picker.pending_path[0] = '\\0';",
                "            return -1;",
                "        }",
                '        { uint64_t stop_args[1] = { 0u }; (void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_transport_mode", stop_args, 1); }',
                "    }",
                "    {",
                "        const char *slash = strrchr(g_runtime_cassette_picker.pending_path, '/');",
                "        const char *bslash = strrchr(g_runtime_cassette_picker.pending_path, '\\\\');",
                "        const char *base = g_runtime_cassette_picker.pending_path;",
                "        if (slash != NULL && slash[1] != '\\0') base = slash + 1;",
                "        if (bslash != NULL && bslash[1] != '\\0' && bslash + 1 > base) base = bslash + 1;",
                "        snprintf(g_runtime_cassette_picker.loaded_name, sizeof(g_runtime_cassette_picker.loaded_name), \"%s\", base);",
                "        g_runtime_cassette_picker.media_loaded = 1u;",
                "        g_runtime_cassette_picker.status_now_cycle = cpu->total_cycles;",
                "        g_runtime_cassette_picker.status_until_cycle = cpu->total_cycles + (uint64_t)(CPU_SYSTEM_CLOCK_HZ * 10u);",
                "        {",
                "            const char *auto_play = cpu_host_hal_getenv(\"PASM_EMU_CASSETTE_AUTO_PLAY\");",
                "            if (auto_play != NULL && auto_play[0] != '\\0' && auto_play[0] != '0') {",
                "                uint64_t play_args[1] = { 1u };",
                '                (void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_transport_mode", play_args, 1);',
                *(
                    [
                        '                (void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_motor", play_args, 1);',
                        "                g_runtime_cassette_picker.motor_on = 1u;",
                    ]
                    if cassette_play_sets_motor
                    else [
                        "                g_runtime_cassette_picker.motor_on = 0u;",
                    ]
                ),
                "                g_runtime_cassette_picker.transport_mode = 1u;",
                "            }",
                "        }",
                "    }",
                "    if (g_runtime_cassette_picker.transport_mode != 1u) {",
                "        g_runtime_cassette_picker.transport_mode = 0u;",
                "        g_runtime_cassette_picker.motor_on = 0u;",
                "    }",
                "    g_runtime_cassette_picker.pending_load = 0u;",
                "    g_runtime_cassette_picker.pending_source_index = 0u;",
                "    g_runtime_cassette_picker.pending_source_kind = 0u;",
                "    g_runtime_cassette_picker.pending_path[0] = '\\0';",
                "    return 1;",
                "}",
                "static void cpu_component_cassette_picker_sync_state(CPUState *cpu) {",
                "    uint64_t state;",
                "    uint64_t model_ptr;",
                "    const char *selected_model;",
                "    uint8_t had_source;",
                "    if (!cpu) return;",
                "    if (g_runtime_cassette_picker.active_component_id[0] == '\\0') return;",
                "    had_source = (uint8_t)(g_runtime_cassette_picker.active_source_model[0] != '\\0');",
                '    state = cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "query_transport_state", NULL, 0);',
                "    if (g_runtime_cassette_picker.pending_load == 0u) {",
                '        model_ptr = cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "query_selected_source_model", NULL, 0);',
                "        selected_model = (const char *)(uintptr_t)model_ptr;",
                "        if (selected_model != NULL && selected_model[0] != '\\0') {",
                "            snprintf(g_runtime_cassette_picker.active_source_model, sizeof(g_runtime_cassette_picker.active_source_model), \"%s\", selected_model);",
                "        }",
                "    }",
                "    g_runtime_cassette_picker.media_loaded = (uint8_t)(((state >> 9u) & 0x01u) != 0u);",
                "    g_runtime_cassette_picker.transport_mode = (uint8_t)(state & 0xFFu);",
                "    g_runtime_cassette_picker.motor_on = (uint8_t)(((state >> 8u) & 0x01u) != 0u);",
                "    g_runtime_cassette_picker.current_seconds = (uint16_t)((state >> 16u) & 0xFFFFu);",
                "    g_runtime_cassette_picker.total_seconds = (uint16_t)((state >> 32u) & 0xFFFFu);",
                "    g_runtime_cassette_picker.volume_percent = (uint8_t)((state >> 48u) & 0xFFu);",
                "    if (g_runtime_cassette_picker.media_loaded == 0u && g_runtime_cassette_picker.pending_load == 0u && had_source == 0u && g_runtime_cassette_picker.active_source_model[0] == '\\0') {",
                "        g_runtime_cassette_picker.loaded_name[0] = '\\0';",
                "        g_runtime_cassette_picker.status_until_cycle = 0u;",
                "        g_runtime_cassette_picker.status_now_cycle = 0u;",
                "    }",
                "}",
                "static void cpu_component_cassette_picker_draw_text_fit(",
                "    uint32_t *pixels,",
                "    uint32_t w,",
                "    uint32_t h,",
                "    int x,",
                "    int y,",
                "    const char *text,",
                "    int scale,",
                "    uint32_t color,",
                "    int max_px",
                ") {",
                "    char buf[320];",
                "    size_t n = 0u;",
                "    int cell_px = (scale > 0) ? (6 * scale) : 4;",
                "    int max_chars;",
                "    if (!text || text[0] == '\\0') return;",
                "    if (cell_px <= 0) cell_px = 1;",
                "    max_chars = (max_px > 0) ? (max_px / cell_px) : 0;",
                "    if (max_chars <= 0) return;",
                "    while (text[n] != '\\0' && n < (size_t)max_chars && n < sizeof(buf) - 1u) {",
                "        buf[n] = text[n];",
                "        n++;",
                "    }",
                "    if (text[n] != '\\0' && n >= 3u) {",
                "        buf[n - 3u] = '.';",
                "        buf[n - 2u] = '.';",
                "        buf[n - 1u] = '.';",
                "    }",
                "    buf[n] = '\\0';",
                "    pasm_overlay_draw_text(pixels, w, h, x, y, buf, scale, color);",
                "}",
                "static void cpu_component_cassette_picker_format_time(char *buf, size_t buf_size, uint16_t total_seconds) {",
                "    unsigned mm;",
                "    unsigned ss;",
                "    if (!buf || buf_size == 0u) return;",
                "    mm = (unsigned)(total_seconds / 60u);",
                "    ss = (unsigned)(total_seconds % 60u);",
                "    snprintf(buf, buf_size, \"%02u:%02u\", mm, ss);",
                "}",
                "static void cpu_component_cassette_picker_draw_icon(uint32_t *pixels, uint32_t w, uint32_t h, int x, int y, uint8_t mode, uint32_t color) {",
                "    if (!pixels || w == 0u || h == 0u) return;",
                "    if (mode == 1u) {",
                "        for (int row = 0; row < 7; ++row) {",
                "            int cols = 2 + row / 2;",
                "            for (int col = 0; col < cols; ++col) {",
                "                pasm_overlay_put_pixel(pixels, w, h, x + col, y + row, color);",
                "            }",
                "        }",
                "        return;",
                "    }",
                "    if (mode == 2u) {",
                "        pasm_overlay_fill_rect_alpha(pixels, w, h, x, y, 2, 7, color & 0x00FFFFFFu, (uint8_t)(color >> 24));",
                "        pasm_overlay_fill_rect_alpha(pixels, w, h, x + 4, y, 2, 7, color & 0x00FFFFFFu, (uint8_t)(color >> 24));",
                "        return;",
                "    }",
                "    if (mode == 3u) {",
                "        pasm_overlay_fill_rect_alpha(pixels, w, h, x + 1, y + 1, 5, 5, color & 0x00FFFFFFu, (uint8_t)(color >> 24));",
                "        return;",
                "    }",
                "    pasm_overlay_fill_rect_alpha(pixels, w, h, x + 1, y + 1, 5, 5, color & 0x00FFFFFFu, (uint8_t)(color >> 24));",
                "}",
                "void cpu_component_cassette_picker_update(CPUState *cpu, uint8_t has_focus) {",
                "    int key_count = 0;",
                "    const uint8_t *ks = cpu_host_hal_keyboard_state(&key_count);",
                "    static int raw_picker_keys_enabled = -1;",
                "    static int raw_transport_keys_enabled = -1;",
                "    static int trace_enabled = -1;",
                "    static int auto_media_checked = 0;",
                "    static FILE *trace_fp = NULL;",
                "    uint8_t raw_trig = 0u;",
                "    uint8_t raw_play = 0u;",
                "    uint8_t raw_vol_up = 0u;",
                "    uint8_t raw_vol_down = 0u;",
                "    uint8_t trig, up, down, left, right, enter, esc, play, pausev, stopv, recordv, vol_up, vol_down;",
                "    uint8_t effective_mode;",
                "    if (!cpu) return;",
                "    g_runtime_cassette_picker.status_now_cycle = cpu->total_cycles;",
                "    cpu_component_cassette_picker_sync_state(cpu);",
                "    effective_mode = g_runtime_cassette_picker.transport_mode;",
                (
                    "    if (effective_mode == 1u && g_runtime_cassette_picker.motor_on == 0u) effective_mode = 0u;"
                    if cassette_play_sets_motor
                    else ""
                ),
                "    if (auto_media_checked == 0) {",
                "        const char *auto_path = cpu_host_hal_getenv(\"PASM_EMU_CASSETTE_AUTO_PATH\");",
                "        auto_media_checked = 1;",
                "        if (auto_path != NULL && auto_path[0] != '\\0' && g_runtime_cassette_picker.media_loaded == 0u && g_runtime_cassette_picker.pending_load == 0u) {",
                "            uint8_t auto_source_index = 0u;",
                "            const char *auto_component_id = cpu_component_cassette_component_for_ext(auto_path, &auto_source_index);",
                "            const char *auto_source_model = cpu_component_cassette_model_for_source_index(auto_source_index);",
                "            if (auto_component_id != NULL && auto_component_id[0] != '\\0') {",
                "                snprintf(g_runtime_cassette_picker.active_component_id, sizeof(g_runtime_cassette_picker.active_component_id), \"%s\", auto_component_id);",
                "                snprintf(g_runtime_cassette_picker.active_source_component_id, sizeof(g_runtime_cassette_picker.active_source_component_id), \"%s\", cpu_component_cassette_source_component_for_source_index(auto_source_index));",
                "                if (auto_source_model != NULL) snprintf(g_runtime_cassette_picker.active_source_model, sizeof(g_runtime_cassette_picker.active_source_model), \"%s\", auto_source_model); else g_runtime_cassette_picker.active_source_model[0] = '\\0';",
                "                g_runtime_cassette_picker.active_source_kind = cpu_component_cassette_kind_for_source_index(auto_source_index);",
                "                g_runtime_cassette_picker.pending_source_index = auto_source_index;",
                "                g_runtime_cassette_picker.pending_source_kind = cpu_component_cassette_kind_for_source_index(auto_source_index);",
                "                snprintf(g_runtime_cassette_picker.pending_path, sizeof(g_runtime_cassette_picker.pending_path), \"%s\", auto_path);",
                "                g_runtime_cassette_picker.pending_load = 1u;",
                "            }",
                "        }",
                "    }",
                "    if (!ks || key_count <= 0) return;",
                "    if (raw_picker_keys_enabled < 0) {",
                "        const char *env = getenv(\"PASM_EMU_CASSETTE_PICKER_RAW_KEYS\");",
                "        raw_picker_keys_enabled = (env == NULL || env[0] == '\\0' || env[0] != '0') ? 1 : 0;",
                "    }",
                "    if (raw_transport_keys_enabled < 0) {",
                "        const char *env = getenv(\"PASM_EMU_CASSETTE_TRANSPORT_RAW_KEYS\");",
                "        raw_transport_keys_enabled = (env == NULL || env[0] == '\\0' || env[0] != '0') ? 1 : 0;",
                "    }",
                "    if (trace_enabled < 0) {",
                "        const char *env = cpu_host_hal_getenv(\"PASM_EMU_CASSETTE_TRACE\");",
                "        trace_enabled = (env != NULL && env[0] != '\\0' && env[0] != '0') ? 1 : 0;",
                "        if (trace_enabled != 0) {",
                "            const char *path = cpu_host_hal_getenv(\"PASM_EMU_CASSETTE_TRACE_FILE\");",
                "            if (path != NULL && path[0] != '\\0') trace_fp = fopen(path, \"a\");",
                "            if (trace_fp == NULL) trace_fp = stderr;",
                "        }",
                "    }",
                f'    trig = cpu_component_keyboard_emulator_action_pressed("{_escape_c_string(cassette_picker_action)}", ks, (size_t)key_count, has_focus);',
                "    if (raw_picker_keys_enabled != 0 && ks != NULL && key_count > 0) {",
                "        if ((size_t)CPU_HOST_SCANCODE(F11) < (size_t)key_count && ks[CPU_HOST_SCANCODE(F11)] != 0u) raw_trig = 1u;",
                "    }",
                "    if (raw_trig != 0u) trig = 1u;",
                "    if (trace_enabled != 0) {",
                "        int pressed_count = 0;",
                "        fprintf(trace_fp, \"cassette_trace focus=%u key_count=%d f11=%u f10=%u trig=%u active=%u prev=%u\\n\",",
                "            (unsigned)has_focus, key_count, (unsigned)raw_trig, (unsigned)raw_play, (unsigned)trig,",
                "            (unsigned)g_runtime_cassette_picker.active, (unsigned)g_runtime_cassette_picker.action_prev);",
                "        for (int i = 0; i < key_count; ++i) {",
                "            if (ks[i] == 0u) continue;",
                "            if (pressed_count == 0) fprintf(trace_fp, \"cassette_trace pressed:\");",
                "            {",
                "                int32_t keycode = cpu_host_hal_key_from_scancode(i);",
                "                const char *sc_name = cpu_host_hal_scancode_name(i);",
                "                const char *key_name = cpu_host_hal_key_name(keycode);",
                "                fprintf(trace_fp, \" %s[%s]\", sc_name, key_name);",
                "            }",
                "            pressed_count += 1;",
                "        }",
                "        if (pressed_count > 0) fprintf(trace_fp, \"\\n\");",
                "        fflush(trace_fp);",
                "    }",
                "    if (g_runtime_media_picker_switch_pending != 0u && g_runtime_media_picker_switch_target == CPU_MEDIA_PICKER_CASSETTE && g_runtime_cassette_picker.active == 0u) {",
                "        int scan_rc = cpu_component_cassette_picker_scan_dir();",
                "        if (trace_enabled != 0) { fprintf(trace_fp, \"cassette_trace switch_scan_rc=%d dir=%s entries=%u\\n\", scan_rc, g_runtime_cassette_picker.directory, (unsigned)g_runtime_cassette_picker.entry_count); fflush(trace_fp); }",
                "        if (scan_rc == 0) { g_runtime_cassette_picker.active = 1u; g_runtime_media_picker_active_kind = CPU_MEDIA_PICKER_CASSETTE; g_runtime_cassette_picker.nav_up_prev = 0u; g_runtime_cassette_picker.nav_down_prev = 0u; g_runtime_cassette_picker.nav_left_prev = ((size_t)CPU_HOST_SCANCODE(LEFT) < (size_t)key_count && ks[CPU_HOST_SCANCODE(LEFT)] != 0u) ? 1u : 0u; g_runtime_cassette_picker.nav_right_prev = ((size_t)CPU_HOST_SCANCODE(RIGHT) < (size_t)key_count && ks[CPU_HOST_SCANCODE(RIGHT)] != 0u) ? 1u : 0u; g_runtime_cassette_picker.nav_enter_prev = 0u; g_runtime_cassette_picker.nav_esc_prev = 0u; }",
                "        g_runtime_media_picker_switch_pending = 0u;",
                "        g_runtime_media_picker_switch_target = CPU_MEDIA_PICKER_NONE;",
                "    }",
                "    if (trig != 0u && g_runtime_cassette_picker.action_prev == 0u) {",
                "        if (g_runtime_cassette_picker.active == 0u && g_runtime_media_picker_active_kind == CPU_MEDIA_PICKER_NONE && cpu_component_media_picker_first_kind() == CPU_MEDIA_PICKER_CASSETTE) {",
                "            int scan_rc = cpu_component_cassette_picker_scan_dir();",
                "            if (trace_enabled != 0) { fprintf(trace_fp, \"cassette_trace scan_rc=%d dir=%s entries=%u\\n\", scan_rc, g_runtime_cassette_picker.directory, (unsigned)g_runtime_cassette_picker.entry_count); fflush(trace_fp); }",
                "            if (scan_rc == 0) { g_runtime_cassette_picker.active = 1u; g_runtime_media_picker_active_kind = CPU_MEDIA_PICKER_CASSETTE; g_runtime_cassette_picker.nav_up_prev = 0u; g_runtime_cassette_picker.nav_down_prev = 0u; g_runtime_cassette_picker.nav_left_prev = 0u; g_runtime_cassette_picker.nav_right_prev = 0u; g_runtime_cassette_picker.nav_enter_prev = 0u; g_runtime_cassette_picker.nav_esc_prev = 0u; }",
                "        }",
                "        else if (g_runtime_cassette_picker.active != 0u) { g_runtime_cassette_picker.active = 0u; g_runtime_cassette_picker.input_blocked = 1u; g_runtime_media_picker_active_kind = CPU_MEDIA_PICKER_NONE; g_runtime_cassette_picker.nav_up_prev = 0u; g_runtime_cassette_picker.nav_down_prev = 0u; g_runtime_cassette_picker.nav_left_prev = 0u; g_runtime_cassette_picker.nav_right_prev = 0u; g_runtime_cassette_picker.nav_enter_prev = 0u; g_runtime_cassette_picker.nav_esc_prev = 0u; }",
                "    }",
                "    g_runtime_cassette_picker.action_prev = trig;",
                "    if (g_runtime_cassette_picker.input_blocked != 0u) {",
                "        uint8_t any_nav = 0u;",
                "        if (trig != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(UP) < (size_t)key_count && ks[CPU_HOST_SCANCODE(UP)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(DOWN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(DOWN)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(RETURN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(RETURN)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(KP_ENTER) < (size_t)key_count && ks[CPU_HOST_SCANCODE(KP_ENTER)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(ESCAPE) < (size_t)key_count && ks[CPU_HOST_SCANCODE(ESCAPE)] != 0u) any_nav = 1u;",
                "        if (any_nav == 0u) g_runtime_cassette_picker.input_blocked = 0u;",
                "    }",
                f'    play = cpu_component_keyboard_emulator_action_pressed("{_escape_c_string(cassette_play_action)}", ks, (size_t)key_count, has_focus);',
                "    if (raw_transport_keys_enabled != 0 && ks != NULL && key_count > 0) {",
                "        if ((size_t)CPU_HOST_SCANCODE(F10) < (size_t)key_count && ks[CPU_HOST_SCANCODE(F10)] != 0u) raw_play = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(PAGEUP) < (size_t)key_count && ks[CPU_HOST_SCANCODE(PAGEUP)] != 0u) raw_vol_up = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(END) < (size_t)key_count && ks[CPU_HOST_SCANCODE(END)] != 0u) raw_vol_down = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(PAGEDOWN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(PAGEDOWN)] != 0u) raw_vol_down = 1u;",
                "    }",
                "    if (raw_play != 0u) play = 1u;",
                f'    pausev = cpu_component_keyboard_emulator_action_pressed("{_escape_c_string(cassette_pause_action)}", ks, (size_t)key_count, has_focus);',
                f'    stopv = cpu_component_keyboard_emulator_action_pressed("{_escape_c_string(cassette_stop_action)}", ks, (size_t)key_count, has_focus);',
                f'    recordv = cpu_component_keyboard_emulator_action_pressed("{_escape_c_string(cassette_record_action)}", ks, (size_t)key_count, has_focus);',
                f'    vol_up = cpu_component_keyboard_emulator_action_pressed("{_escape_c_string(cassette_vol_up_action)}", ks, (size_t)key_count, has_focus);',
                f'    vol_down = cpu_component_keyboard_emulator_action_pressed("{_escape_c_string(cassette_vol_down_action)}", ks, (size_t)key_count, has_focus);',
                "    if (raw_vol_up != 0u) vol_up = 1u;",
                "    if (raw_vol_down != 0u) vol_down = 1u;",
                (
                    '    if (play != 0u && g_runtime_cassette_picker.play_prev == 0u) { uint64_t args[1] = { 1u }; (void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_transport_mode", args, 1); '
                    + (
                        '(void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_motor", args, 1); g_runtime_cassette_picker.transport_mode = 1u; g_runtime_cassette_picker.motor_on = 1u; }'
                        if cassette_play_sets_motor
                        else "g_runtime_cassette_picker.transport_mode = 1u; g_runtime_cassette_picker.motor_on = 0u; }"
                    )
                ),
                '    if (pausev != 0u && g_runtime_cassette_picker.pause_prev == 0u) { uint64_t args[1] = { 2u }; (void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_transport_mode", args, 1); g_runtime_cassette_picker.transport_mode = 2u; }',
                '    if (stopv != 0u && g_runtime_cassette_picker.stop_prev == 0u) { uint64_t args[1] = { 0u }; (void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_transport_mode", args, 1); (void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_motor", args, 1); g_runtime_cassette_picker.transport_mode = 0u; g_runtime_cassette_picker.motor_on = 0u; g_runtime_cassette_picker.status_now_cycle = cpu->total_cycles; g_runtime_cassette_picker.status_until_cycle = cpu->total_cycles + (uint64_t)(CPU_SYSTEM_CLOCK_HZ * 10u); }',
                '    if (recordv != 0u && g_runtime_cassette_picker.record_prev == 0u) { uint64_t args[1] = { 3u }; (void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_transport_mode", args, 1); args[0] = 1u; (void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_motor", args, 1); g_runtime_cassette_picker.transport_mode = 3u; g_runtime_cassette_picker.motor_on = 1u; }',
                '    if (vol_up != 0u && g_runtime_cassette_picker.vol_up_prev == 0u) { if (g_runtime_cassette_picker.volume_percent < 100u) g_runtime_cassette_picker.volume_percent = (uint8_t)((g_runtime_cassette_picker.volume_percent + 5u > 100u) ? 100u : g_runtime_cassette_picker.volume_percent + 5u); { uint64_t args[1] = { g_runtime_cassette_picker.volume_percent }; (void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_volume", args, 1); } }',
                '    if (vol_down != 0u && g_runtime_cassette_picker.vol_down_prev == 0u) { g_runtime_cassette_picker.volume_percent = (uint8_t)((g_runtime_cassette_picker.volume_percent >= 5u) ? (g_runtime_cassette_picker.volume_percent - 5u) : 0u); { uint64_t args[1] = { g_runtime_cassette_picker.volume_percent }; (void)cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "set_volume", args, 1); } }',
                "    effective_mode = g_runtime_cassette_picker.transport_mode;",
                (
                    "    if (effective_mode == 1u && g_runtime_cassette_picker.motor_on == 0u) effective_mode = 0u;"
                    if cassette_play_sets_motor
                    else ""
                ),
                "    if ((g_runtime_cassette_picker.last_transport_mode != 0u && effective_mode == 0u) ||",
                "        (g_runtime_cassette_picker.last_transport_mode == 0u && effective_mode != 0u)) {",
                "        g_runtime_cassette_picker.status_now_cycle = cpu->total_cycles;",
                "        g_runtime_cassette_picker.status_until_cycle = cpu->total_cycles + (uint64_t)(CPU_SYSTEM_CLOCK_HZ * 10u);",
                "    }",
                "    g_runtime_cassette_picker.last_transport_mode = effective_mode;",
                "    g_runtime_cassette_picker.play_prev = play;",
                "    g_runtime_cassette_picker.pause_prev = pausev;",
                "    g_runtime_cassette_picker.stop_prev = stopv;",
                "    g_runtime_cassette_picker.record_prev = recordv;",
                "    g_runtime_cassette_picker.vol_up_prev = vol_up;",
                "    g_runtime_cassette_picker.vol_down_prev = vol_down;",
                "    if (g_runtime_cassette_picker.active == 0u) return;",
                "    up = ((size_t)CPU_HOST_SCANCODE(UP) < (size_t)key_count && ks[CPU_HOST_SCANCODE(UP)] != 0u) ? 1u : 0u;",
                "    down = ((size_t)CPU_HOST_SCANCODE(DOWN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(DOWN)] != 0u) ? 1u : 0u;",
                "    left = ((size_t)CPU_HOST_SCANCODE(LEFT) < (size_t)key_count && ks[CPU_HOST_SCANCODE(LEFT)] != 0u) ? 1u : 0u;",
                "    right = ((size_t)CPU_HOST_SCANCODE(RIGHT) < (size_t)key_count && ks[CPU_HOST_SCANCODE(RIGHT)] != 0u) ? 1u : 0u;",
                "    enter = (((size_t)CPU_HOST_SCANCODE(RETURN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(RETURN)] != 0u) || ((size_t)CPU_HOST_SCANCODE(KP_ENTER) < (size_t)key_count && ks[CPU_HOST_SCANCODE(KP_ENTER)] != 0u)) ? 1u : 0u;",
                "    esc = ((size_t)CPU_HOST_SCANCODE(ESCAPE) < (size_t)key_count && ks[CPU_HOST_SCANCODE(ESCAPE)] != 0u) ? 1u : 0u;",
                "    if (left != 0u && g_runtime_cassette_picker.nav_left_prev == 0u) {",
                "        uint8_t target = cpu_component_media_picker_next_kind(CPU_MEDIA_PICKER_CASSETTE, -1);",
                "        if (target != CPU_MEDIA_PICKER_CASSETTE) {",
                "            g_runtime_cassette_picker.active = 0u;",
                "            g_runtime_cassette_picker.input_blocked = 1u;",
                "            g_runtime_cassette_picker.entry_count = 0u;",
                "            g_runtime_cassette_picker.selected = 0u;",
                "            g_runtime_media_picker_active_kind = CPU_MEDIA_PICKER_NONE;",
                "            g_runtime_media_picker_switch_pending = 1u;",
                "            g_runtime_media_picker_switch_target = target;",
                "            g_runtime_cassette_picker.nav_up_prev = 0u;",
                "            g_runtime_cassette_picker.nav_down_prev = 0u;",
                "            g_runtime_cassette_picker.nav_left_prev = 0u;",
                "            g_runtime_cassette_picker.nav_right_prev = 0u;",
                "            g_runtime_cassette_picker.nav_enter_prev = 0u;",
                "            g_runtime_cassette_picker.nav_esc_prev = 0u;",
                "            return;",
                "        }",
                "    }",
                "    if (right != 0u && g_runtime_cassette_picker.nav_right_prev == 0u) {",
                "        uint8_t target = cpu_component_media_picker_next_kind(CPU_MEDIA_PICKER_CASSETTE, 1);",
                "        if (target != CPU_MEDIA_PICKER_CASSETTE) {",
                "            g_runtime_cassette_picker.active = 0u;",
                "            g_runtime_cassette_picker.input_blocked = 1u;",
                "            g_runtime_cassette_picker.entry_count = 0u;",
                "            g_runtime_cassette_picker.selected = 0u;",
                "            g_runtime_media_picker_active_kind = CPU_MEDIA_PICKER_NONE;",
                "            g_runtime_media_picker_switch_pending = 1u;",
                "            g_runtime_media_picker_switch_target = target;",
                "            g_runtime_cassette_picker.nav_up_prev = 0u;",
                "            g_runtime_cassette_picker.nav_down_prev = 0u;",
                "            g_runtime_cassette_picker.nav_left_prev = 0u;",
                "            g_runtime_cassette_picker.nav_right_prev = 0u;",
                "            g_runtime_cassette_picker.nav_enter_prev = 0u;",
                "            g_runtime_cassette_picker.nav_esc_prev = 0u;",
                "            return;",
                "        }",
                "    }",
                "    if (up != 0u && g_runtime_cassette_picker.nav_up_prev == 0u && g_runtime_cassette_picker.entry_count > 0u) {",
                "        if (g_runtime_cassette_picker.selected == 0u) g_runtime_cassette_picker.selected = g_runtime_cassette_picker.entry_count - 1u; else g_runtime_cassette_picker.selected -= 1u;",
                "    }",
                "    if (down != 0u && g_runtime_cassette_picker.nav_down_prev == 0u && g_runtime_cassette_picker.entry_count > 0u) {",
                "        g_runtime_cassette_picker.selected = (g_runtime_cassette_picker.selected + 1u) % g_runtime_cassette_picker.entry_count;",
                "    }",
                "    if (esc != 0u && g_runtime_cassette_picker.nav_esc_prev == 0u) {",
                "        g_runtime_cassette_picker.active = 0u;",
                "        g_runtime_cassette_picker.input_blocked = 1u;",
                "        g_runtime_cassette_picker.entry_count = 0u;",
                "        g_runtime_cassette_picker.selected = 0u;",
                "    }",
                "    if (enter != 0u && g_runtime_cassette_picker.nav_enter_prev == 0u && g_runtime_cassette_picker.entry_count > 0u) {",
                "        const RuntimeCassetteEntry *sel = &g_runtime_cassette_picker.entries[g_runtime_cassette_picker.selected];",
                "        snprintf(g_runtime_cassette_picker.active_component_id, sizeof(g_runtime_cassette_picker.active_component_id), \"%s\", sel->component_id);",
                "        snprintf(g_runtime_cassette_picker.active_source_component_id, sizeof(g_runtime_cassette_picker.active_source_component_id), \"%s\", sel->source_component_id);",
                "        g_runtime_cassette_picker.active_source_kind = sel->source_kind;",
                "        g_runtime_cassette_picker.active_source_index = sel->source_index;",
                "        snprintf(g_runtime_cassette_picker.active_source_model, sizeof(g_runtime_cassette_picker.active_source_model), \"%s\", sel->source_model);",
                "        snprintf(g_runtime_cassette_picker.active_source_label, sizeof(g_runtime_cassette_picker.active_source_label), \"%s\", sel->source_label);",
                "        g_runtime_cassette_picker.pending_source_index = sel->source_index;",
                "        g_runtime_cassette_picker.pending_source_kind = sel->source_kind;",
                "        snprintf(g_runtime_cassette_picker.pending_path, sizeof(g_runtime_cassette_picker.pending_path), \"%s\", sel->media_path);",
                "        snprintf(g_runtime_cassette_picker.loaded_name, sizeof(g_runtime_cassette_picker.loaded_name), \"%s\", (sel->source_kind == 1u) ? sel->source_label : sel->file_name);",
                "        g_runtime_cassette_picker.status_now_cycle = cpu->total_cycles;",
                "        g_runtime_cassette_picker.status_until_cycle = cpu->total_cycles + (uint64_t)(CPU_SYSTEM_CLOCK_HZ * 10u);",
                "        g_runtime_cassette_picker.pending_load = 1u;",
                "        g_runtime_cassette_picker.active = 0u;",
                "        g_runtime_cassette_picker.input_blocked = 1u;",
                "        g_runtime_cassette_picker.entry_count = 0u;",
                "        g_runtime_cassette_picker.selected = 0u;",
                "        g_runtime_cassette_picker.nav_up_prev = 0u;",
                "        g_runtime_cassette_picker.nav_down_prev = 0u;",
                "        g_runtime_cassette_picker.nav_left_prev = 0u;",
                "        g_runtime_cassette_picker.nav_right_prev = 0u;",
                "        g_runtime_cassette_picker.nav_enter_prev = 0u;",
                "        g_runtime_cassette_picker.nav_esc_prev = 0u;",
                "    }",
                "    g_runtime_cassette_picker.nav_up_prev = up;",
                "    g_runtime_cassette_picker.nav_down_prev = down;",
                "    g_runtime_cassette_picker.nav_left_prev = left;",
                "    g_runtime_cassette_picker.nav_right_prev = right;",
                "    g_runtime_cassette_picker.nav_enter_prev = enter;",
                "    g_runtime_cassette_picker.nav_esc_prev = esc;",
                "}",
                "void cpu_component_cassette_picker_draw_overlay(CPUState *cpu, uint32_t *pixels, uint32_t w, uint32_t h) {",
                "    char status_line[256];",
                "    char current_time[16];",
                "    char total_time[16];",
                "    char name_line[256];",
                "    const char *mode_label;",
                "    int picker_text_w;",
                "    int line1_y;",
                "    int line2_y;",
                "    int panel_x;",
                "    int panel_y;",
                "    int panel_w;",
                "    int panel_h;",
                "    cpu_component_cassette_picker_sync_state(cpu);",
                "    if (!pixels || w == 0u || h == 0u) return;",
                "    g_runtime_cassette_picker.status_now_cycle = (cpu != NULL) ? cpu->total_cycles : g_runtime_cassette_picker.status_now_cycle;",
                "    cpu_component_cassette_picker_format_time(current_time, sizeof(current_time), g_runtime_cassette_picker.current_seconds);",
                "    cpu_component_cassette_picker_format_time(total_time, sizeof(total_time), g_runtime_cassette_picker.total_seconds);",
                "    mode_label = cpu_component_cassette_label_for_model(g_runtime_cassette_picker.active_source_model);",
                "    snprintf(status_line, sizeof(status_line), \"MODE:%s  %s / %s  VOL:%u%%\",",
                "        mode_label,",
                "        current_time,",
                "        total_time,",
                "        (unsigned)g_runtime_cassette_picker.volume_percent);",
                "    snprintf(name_line, sizeof(name_line), \"%s\",",
                "        (g_runtime_cassette_picker.loaded_name[0] != '\\0') ? g_runtime_cassette_picker.loaded_name : ((g_runtime_cassette_picker.active_source_label[0] != '\\0') ? g_runtime_cassette_picker.active_source_label : \"<none>\"));",
                "    {",
                "        uint8_t effective_mode = g_runtime_cassette_picker.transport_mode;",
                (
                    "        if (effective_mode == 1u && g_runtime_cassette_picker.motor_on == 0u) effective_mode = 0u;"
                    if cassette_play_sets_motor
                    else ""
                ),
                "    if ((g_runtime_cassette_picker.media_loaded != 0u || g_runtime_cassette_picker.active_source_model[0] != '\\0') &&",
                "        (effective_mode != 0u || g_runtime_cassette_picker.status_now_cycle < g_runtime_cassette_picker.status_until_cycle)) {",
                "        panel_x = 8;",
                "        panel_y = (int)h - 38;",
                "        panel_w = (int)w - 16;",
                "        panel_h = 30;",
                "        line1_y = panel_y + 4;",
                "        line2_y = panel_y + 14;",
                "        pasm_overlay_fill_rect_alpha(pixels, w, h, panel_x, panel_y, panel_w, panel_h, 0x00101010u, 180u);",
                "        cpu_component_cassette_picker_draw_icon(pixels, w, h, panel_x + 4, line1_y, effective_mode, 0xFFE8E8A0u);",
                "        cpu_component_cassette_picker_draw_text_fit(pixels, w, h, panel_x + 14, line1_y, status_line, 1, 0xFFE8E8A0u, panel_w - 18);",
                "        cpu_component_cassette_picker_draw_text_fit(pixels, w, h, panel_x + 4, line2_y, name_line, 1, 0xFFE8E8A0u, panel_w - 8);",
                "    }",
                "    }",
                "    if (g_runtime_cassette_picker.active == 0u || g_runtime_cassette_picker.entry_count == 0u) return;",
                "    pasm_overlay_fill_rect_alpha(pixels, w, h, 10, 28, (int)w - 20, (int)h - 36, 0x00101010u, 190u);",
                "    picker_text_w = (int)w - 40;",
                "    cpu_component_cassette_picker_draw_text_fit(pixels, w, h, 20, 36, \"CASSETTE PICKER\", 1, 0xFFFFFFFFu, picker_text_w);",
                "    for (int i = 0; i < 10; ++i) {",
                "        size_t idx = ((g_runtime_cassette_picker.selected >= 4u) ? (g_runtime_cassette_picker.selected - 4u) : 0u) + (size_t)i;",
                "        if (idx >= g_runtime_cassette_picker.entry_count) break;",
                "        cpu_component_cassette_picker_draw_text_fit(pixels, w, h, 20, 56 + i * 9, g_runtime_cassette_picker.entries[idx].file_name, 1, (idx == g_runtime_cassette_picker.selected) ? 0xFF00FF9Fu : 0xFFE0E0E0u, picker_text_w);",
                "    }",
                "    cpu_component_cassette_picker_draw_text_fit(pixels, w, h, 20, (int)h - 42, \"UP/DOWN SELECT  ENTER LOAD  ESC CANCEL\", 1, 0xFFFFFFA0u, picker_text_w);",
                "}",
                "",
            ]
        )
    else:
        helper_lines.extend(
            [
                "int cpu_component_cassette_picker_apply_pending_load(CPUState *cpu) { (void)cpu; return 0; }",
                "static void cpu_component_cassette_picker_sync_state(CPUState *cpu) { (void)cpu; }",
                "uint8_t cpu_component_cassette_picker_is_active(void) { return 0u; }",
                "uint8_t cpu_component_cassette_picker_overlay_visible(void) { return 0u; }",
                "void cpu_component_cassette_picker_update(CPUState *cpu, uint8_t has_focus) { (void)cpu; (void)has_focus; }",
                "void cpu_component_cassette_picker_draw_overlay(CPUState *cpu, uint32_t *pixels, uint32_t w, uint32_t h) { (void)cpu; (void)pixels; (void)w; (void)h; }",
                "",
            ]
        )

    if has_runtime_floppy:
        helper_lines.extend(
            [
                "typedef struct {",
                "    uint8_t source_index;",
                "    char media_path[1024];",
                "    char file_name[256];",
                "    char source_model[64];",
                "    char source_label[64];",
                "} RuntimeFloppyEntry;",
                "",
                "typedef struct {",
                "    uint8_t active;",
                "    uint8_t action_prev;",
                "    uint8_t nav_up_prev;",
                "    uint8_t nav_down_prev;",
                "    uint8_t nav_enter_prev;",
                "    uint8_t nav_esc_prev;",
                "    uint8_t nav_left_prev;",
                "    uint8_t nav_right_prev;",
                "    uint8_t input_blocked;",
                "    uint8_t pending_load;",
                "    uint8_t pending_eject;",
                "    uint8_t pending_source_index;",
                "    char pending_path[1024];",
                "    char directory[1024];",
                "    RuntimeFloppyEntry *entries;",
                "    size_t entry_count;",
                "    size_t entry_cap;",
                "    size_t selected;",
                "    char component_id[64];",
                "    char loaded_name[256];",
                "    char active_source_model[64];",
                "    char active_source_label[64];",
                "    uint8_t media_loaded;",
                "    uint8_t activity_flags;",
                "    uint64_t status_until_cycle;",
                "    uint64_t status_now_cycle;",
                "} RuntimeFloppyPicker;",
                "",
                "static RuntimeFloppyPicker g_runtime_floppy_picker = {",
                f'    0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u, "", "{_escape_c_string(str(floppy_cfg.get("directory", "")))}", NULL, 0u, 0u, 0u, "{_escape_c_string(floppy_component_id)}", "", "", "", 0u, 0u, 0u, 0u',
                "};",
                "static RuntimeFloppyEntry *cpu_component_floppy_picker_add_entry(void) {",
                "    if (g_runtime_floppy_picker.entry_count >= g_runtime_floppy_picker.entry_cap) {",
                "        size_t new_cap = (g_runtime_floppy_picker.entry_cap == 0u) ? 64u : (g_runtime_floppy_picker.entry_cap * 2u);",
                "        RuntimeFloppyEntry *ne = (RuntimeFloppyEntry *)realloc(g_runtime_floppy_picker.entries, new_cap * sizeof(RuntimeFloppyEntry));",
                "        if (ne == NULL) return NULL;",
                "        memset(ne + g_runtime_floppy_picker.entry_cap, 0, (new_cap - g_runtime_floppy_picker.entry_cap) * sizeof(RuntimeFloppyEntry));",
                "        g_runtime_floppy_picker.entries = ne;",
                "        g_runtime_floppy_picker.entry_cap = new_cap;",
                "    }",
                "    return &g_runtime_floppy_picker.entries[g_runtime_floppy_picker.entry_count++];",
                "}",
                "static uint8_t cpu_component_floppy_ext_allowed(const char *name) {",
                "    const char *dot = strrchr(name, '.');",
                "    char ext[16];",
                "    size_t n;",
                "    if (!dot || dot[1] == '\\0') return 0u;",
                "    dot++;",
                "    n = strlen(dot);",
                "    if (n >= sizeof(ext)) n = sizeof(ext) - 1u;",
                "    for (size_t i = 0; i < n; ++i) { char c = dot[i]; if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a'); ext[i] = c; }",
                "    ext[n] = '\\0';",
                *[
                    f'    if (strcmp(ext, "{_escape_c_string(ext)}") == 0) return 1u;'
                    for ext in floppy_all_exts
                ],
                "    return 0u;",
                "}",
                "static uint8_t cpu_component_floppy_source_index_for_ext(const char *name) {",
                "    const char *dot = strrchr(name, '.');",
                "    char ext[16];",
                "    size_t n;",
                "    if (!dot || dot[1] == '\\0') return 0u;",
                "    dot++;",
                "    n = strlen(dot);",
                "    if (n >= sizeof(ext)) n = sizeof(ext) - 1u;",
                "    for (size_t i = 0; i < n; ++i) { char c = dot[i]; if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a'); ext[i] = c; }",
                "    ext[n] = '\\0';",
                *[
                    line
                    for source in floppy_sources
                    for ext in source["allowed_extensions"]
                    for line in [
                        f'    if (strcmp(ext, "{_escape_c_string(ext)}") == 0) return {int(source["index"])}u;',
                    ]
                ],
                "    return 0u;",
                "}",
                "static const char *cpu_component_floppy_model_for_source_index(uint8_t source_index) {",
                *[
                    f'    if (source_index == {int(source["index"])}u) return "{_escape_c_string(source["model"])}";'
                    for source in floppy_sources
                ],
                '    return "";',
                "}",
                "static const char *cpu_component_floppy_label_for_source_index(uint8_t source_index) {",
                *[
                    f'    if (source_index == {int(source["index"])}u) return "{_escape_c_string(source["label"])}";'
                    for source in floppy_sources
                ],
                '    return "Unknown";',
                "}",
                "static int cpu_component_floppy_picker_scan_dir(void) {",
                "#if defined(_WIN32)",
                "    return -1;",
                "#else",
                "    DIR *d;",
                "    struct dirent *de;",
                "    if (g_runtime_floppy_picker.entries != NULL) { free(g_runtime_floppy_picker.entries); g_runtime_floppy_picker.entries = NULL; }",
                "    g_runtime_floppy_picker.entry_count = 0u;",
                "    g_runtime_floppy_picker.entry_cap = 0u;",
                "    {",
                "        RuntimeFloppyEntry *entry = cpu_component_floppy_picker_add_entry();",
                "        if (entry == NULL) return -1;",
                '        snprintf(entry->file_name, sizeof(entry->file_name), "%s", "<NO DISK>");',
                '        snprintf(entry->source_label, sizeof(entry->source_label), "%s", "Empty Drive");',
                '        entry->source_model[0] = \'\\0\';',
                '        entry->media_path[0] = \'\\0\';',
                "        entry->source_index = 0u;",
                "    }",
                "    if (g_runtime_floppy_picker.directory[0] == '\\0') return 0;",
                "    d = opendir(g_runtime_floppy_picker.directory);",
                "    if (d == NULL) return 0;",
                "    while ((de = readdir(d)) != NULL) {",
                "        RuntimeFloppyEntry *entry;",
                "        uint8_t source_index;",
                "        if (de->d_name[0] == '.') continue;",
                "        if (cpu_component_floppy_ext_allowed(de->d_name) == 0u) continue;",
                "        entry = cpu_component_floppy_picker_add_entry();",
                "        if (entry == NULL) { closedir(d); return -1; }",
                "        source_index = cpu_component_floppy_source_index_for_ext(de->d_name);",
                "        entry->source_index = source_index;",
                "        snprintf(entry->file_name, sizeof(entry->file_name), \"%s\", de->d_name);",
                "        snprintf(entry->media_path, sizeof(entry->media_path), \"%s/%s\", g_runtime_floppy_picker.directory, de->d_name);",
                "        snprintf(entry->source_model, sizeof(entry->source_model), \"%s\", cpu_component_floppy_model_for_source_index(source_index));",
                "        snprintf(entry->source_label, sizeof(entry->source_label), \"%s\", cpu_component_floppy_label_for_source_index(source_index));",
                "    }",
                "    closedir(d);",
                "    return 0;",
                "#endif",
                "}",
                f"int {cpu_prefix}_load_floppy_media(CPUState *cpu, const char *path) {{",
                "    if (cpu == NULL || path == NULL || path[0] == '\\0') return -1;",
                "    return cpu_component_floppy_picker_load_path(cpu, path);",
                "}",
                "int pasm_dbg_load_floppy_media(CPUState *cpu, const char *path) {",
                f"    return {cpu_prefix}_load_floppy_media(cpu, path);",
                "}",
                "int cpu_component_floppy_picker_load_path(CPUState *cpu, const char *path) {",
                "    uint8_t source_index;",
                "    const char *source_model;",
                "    const char *source_label;",
                "    const char *file_name;",
                "    uint64_t load_args[1];",
                "    if (cpu == NULL || path == NULL || path[0] == '\\0') return -1;",
                "    if (g_runtime_floppy_picker.component_id[0] == '\\0') return -1;",
                "    source_index = cpu_component_floppy_source_index_for_ext(path);",
                "    source_model = cpu_component_floppy_model_for_source_index(source_index);",
                "    source_label = cpu_component_floppy_label_for_source_index(source_index);",
                "    if (g_runtime_floppy_picker.media_loaded != 0u) {",
                '        if (cpu_component_dispatch_callback(cpu, g_runtime_floppy_picker.component_id, "unload_media", NULL, 0u) == 0u) return -1;',
                "    }",
                "    load_args[0] = (uint64_t)(uintptr_t)path;",
                '    if (cpu_component_dispatch_callback(cpu, g_runtime_floppy_picker.component_id, "load_media", load_args, 1u) == 0u) return -1;',
                "    g_runtime_floppy_picker.pending_eject = 0u;",
                "    g_runtime_floppy_picker.pending_load = 0u;",
                "    g_runtime_floppy_picker.pending_path[0] = '\\0';",
                "    g_runtime_floppy_picker.pending_source_index = source_index;",
                "    g_runtime_floppy_picker.media_loaded = 1u;",
                "    g_runtime_floppy_picker.activity_flags = 0u;",
                "    if (source_model != NULL) snprintf(g_runtime_floppy_picker.active_source_model, sizeof(g_runtime_floppy_picker.active_source_model), \"%s\", source_model); else g_runtime_floppy_picker.active_source_model[0] = '\\0';",
                "    snprintf(g_runtime_floppy_picker.active_source_label, sizeof(g_runtime_floppy_picker.active_source_label), \"%s\", (source_label != NULL) ? source_label : \"Unknown\");",
                "    file_name = strrchr(path, '/');",
                "#if defined(_WIN32)",
                "    { const char *back = strrchr(path, '\\\\'); if (back != NULL && (file_name == NULL || back > file_name)) file_name = back; }",
                "#endif",
                "    if (file_name != NULL && file_name[0] != '\\0') file_name++; else file_name = path;",
                "    snprintf(g_runtime_floppy_picker.loaded_name, sizeof(g_runtime_floppy_picker.loaded_name), \"%s\", file_name);",
                "    g_runtime_floppy_picker.status_now_cycle = cpu->total_cycles;",
                "    g_runtime_floppy_picker.status_until_cycle = cpu->total_cycles + (uint64_t)(CPU_SYSTEM_CLOCK_HZ * 10u);",
                "    return 0;",
                "}",
                "int cpu_component_floppy_picker_apply_pending_load(CPUState *cpu) {",
                "    static int auto_media_checked = 0;",
                "    if (auto_media_checked == 0) {",
                "        const char *auto_path = cpu_host_hal_getenv(\"PASM_EMU_FLOPPY_AUTO_PATH\");",
                "        auto_media_checked = 1;",
                "        if (auto_path != NULL && auto_path[0] != '\\0' && g_runtime_floppy_picker.media_loaded == 0u && g_runtime_floppy_picker.pending_load == 0u && g_runtime_floppy_picker.component_id[0] != '\\0') {",
                "            uint8_t auto_source_index = cpu_component_floppy_source_index_for_ext(auto_path);",
                "            const char *auto_source_model = cpu_component_floppy_model_for_source_index(auto_source_index);",
                "            const char *auto_source_label = cpu_component_floppy_label_for_source_index(auto_source_index);",
                "            g_runtime_floppy_picker.pending_eject = 0u;",
                "            g_runtime_floppy_picker.pending_load = 1u;",
                "            g_runtime_floppy_picker.pending_source_index = auto_source_index;",
                "            snprintf(g_runtime_floppy_picker.pending_path, sizeof(g_runtime_floppy_picker.pending_path), \"%s\", auto_path);",
                "            snprintf(g_runtime_floppy_picker.loaded_name, sizeof(g_runtime_floppy_picker.loaded_name), \"%s\", auto_path);",
                "            if (auto_source_model != NULL) snprintf(g_runtime_floppy_picker.active_source_model, sizeof(g_runtime_floppy_picker.active_source_model), \"%s\", auto_source_model); else g_runtime_floppy_picker.active_source_model[0] = '\\0';",
                "            snprintf(g_runtime_floppy_picker.active_source_label, sizeof(g_runtime_floppy_picker.active_source_label), \"%s\", (auto_source_label != NULL) ? auto_source_label : \"Unknown\");",
                "        }",
                "    }",
                "    if (g_runtime_floppy_picker.pending_eject != 0u) {",
                "        if (g_runtime_floppy_picker.component_id[0] != '\\0') {",
                '            if (cpu_component_dispatch_callback(cpu, g_runtime_floppy_picker.component_id, "unload_media", NULL, 0u) == 0u) return -1;',
                "        }",
                "        g_runtime_floppy_picker.pending_eject = 0u;",
                "        g_runtime_floppy_picker.pending_load = 0u;",
                "        g_runtime_floppy_picker.media_loaded = 0u;",
                "        g_runtime_floppy_picker.activity_flags = 0u;",
                "        g_runtime_floppy_picker.loaded_name[0] = '\\0';",
                "        g_runtime_floppy_picker.active_source_model[0] = '\\0';",
                "        g_runtime_floppy_picker.active_source_label[0] = '\\0';",
                "        g_runtime_floppy_picker.status_now_cycle = cpu->total_cycles;",
                "        g_runtime_floppy_picker.status_until_cycle = cpu->total_cycles + (uint64_t)(CPU_SYSTEM_CLOCK_HZ * 10u);",
                "        return 1;",
                "    }",
                "    if (g_runtime_floppy_picker.pending_load != 0u) {",
                "        if (g_runtime_floppy_picker.component_id[0] == '\\0') return -1;",
                "        if (cpu_component_floppy_picker_load_path(cpu, g_runtime_floppy_picker.pending_path) != 0) {",
                "            g_runtime_floppy_picker.pending_load = 0u;",
                "            g_runtime_floppy_picker.pending_path[0] = '\\0';",
                "            return -1;",
                "        }",
                "        return 1;",
                "    }",
                "    return 0;",
                "}",
                "uint8_t cpu_component_floppy_picker_is_active(void) { return g_runtime_floppy_picker.active; }",
                "uint8_t cpu_component_floppy_picker_overlay_visible(void) {",
                "    if (g_runtime_floppy_picker.active != 0u) return 1u;",
                "    if ((g_runtime_floppy_picker.loaded_name[0] != '\\0' || g_runtime_floppy_picker.active_source_label[0] != '\\0' || g_runtime_floppy_picker.activity_flags != 0u) && g_runtime_floppy_picker.status_now_cycle < g_runtime_floppy_picker.status_until_cycle) return 1u;",
                "    return 0u;",
                "}",
                "uint8_t cpu_component_floppy_picker_blocks_input(void) { return (uint8_t)(g_runtime_floppy_picker.active != 0u || g_runtime_floppy_picker.input_blocked != 0u); }",
                "static void cpu_component_floppy_picker_draw_text_fit(uint32_t *pixels, uint32_t w, uint32_t h, int x, int y, const char *text, int scale, uint32_t color, int max_px) {",
                "    char buf[320];",
                "    size_t n = 0u;",
                "    int cell_px = (scale > 0) ? (6 * scale) : 4;",
                "    int max_chars;",
                "    if (!text || text[0] == '\\0') return;",
                "    if (cell_px <= 0) cell_px = 1;",
                "    max_chars = (max_px > 0) ? (max_px / cell_px) : 0;",
                "    if (max_chars <= 0) return;",
                "    while (text[n] != '\\0' && n < (size_t)max_chars && n < sizeof(buf) - 1u) { buf[n] = text[n]; n++; }",
                "    if (text[n] != '\\0' && n >= 3u) { buf[n - 3u] = '.'; buf[n - 2u] = '.'; buf[n - 1u] = '.'; }",
                "    buf[n] = '\\0';",
                "    if (scale > 0) pasm_overlay_draw_text(pixels, w, h, x, y, buf, scale, color);",
                "    else {",
                "        int cx = x;",
                "        for (const char *p = buf; *p; ++p) {",
                "            const uint8_t *glyph = pasm_overlay_glyph(*p);",
                "            for (int row = 0; row < 7; row += 2) {",
                "                uint8_t bits = glyph[row];",
                "                int ty = y + (row / 2);",
                "                for (int col = 0; col < 5; col += 2) if ((bits & (uint8_t)(1u << (4 - col))) != 0u) pasm_overlay_put_pixel(pixels, w, h, cx + (col / 2), ty, color);",
                "            }",
                "            cx += 4;",
                "        }",
                "    }",
                "}",
                "void cpu_component_floppy_picker_update(CPUState *cpu, uint8_t has_focus) {",
                "    int key_count = 0;",
                "    const uint8_t *ks = cpu_host_hal_keyboard_state(&key_count);",
                "    uint8_t trig;",
                "    uint8_t up, down, left, right, enter, esc;",
                "    if (!cpu) return;",
                "    g_runtime_floppy_picker.status_now_cycle = cpu->total_cycles;",
                "    if (g_runtime_media_picker_switch_pending != 0u && g_runtime_media_picker_switch_target == CPU_MEDIA_PICKER_FLOPPY && g_runtime_floppy_picker.active == 0u) {",
                "        if (cpu_component_floppy_picker_scan_dir() == 0) { g_runtime_floppy_picker.active = 1u; g_runtime_media_picker_active_kind = CPU_MEDIA_PICKER_FLOPPY; g_runtime_floppy_picker.nav_up_prev = 0u; g_runtime_floppy_picker.nav_down_prev = 0u; g_runtime_floppy_picker.nav_left_prev = ((size_t)CPU_HOST_SCANCODE(LEFT) < (size_t)key_count && ks[CPU_HOST_SCANCODE(LEFT)] != 0u) ? 1u : 0u; g_runtime_floppy_picker.nav_right_prev = ((size_t)CPU_HOST_SCANCODE(RIGHT) < (size_t)key_count && ks[CPU_HOST_SCANCODE(RIGHT)] != 0u) ? 1u : 0u; g_runtime_floppy_picker.nav_enter_prev = 0u; g_runtime_floppy_picker.nav_esc_prev = 0u; }",
                "        g_runtime_media_picker_switch_pending = 0u;",
                "        g_runtime_media_picker_switch_target = CPU_MEDIA_PICKER_NONE;",
                "    }",
                f'    trig = cpu_component_keyboard_emulator_action_pressed("{_escape_c_string(floppy_picker_action)}", ks, (size_t)((key_count < 0) ? 0 : key_count), has_focus);',
                "    if (trig != 0u && g_runtime_floppy_picker.action_prev == 0u) {",
                "        if (g_runtime_floppy_picker.active == 0u && g_runtime_media_picker_active_kind == CPU_MEDIA_PICKER_NONE && cpu_component_media_picker_first_kind() == CPU_MEDIA_PICKER_FLOPPY) {",
                "            if (cpu_component_floppy_picker_scan_dir() == 0) { g_runtime_floppy_picker.active = 1u; g_runtime_media_picker_active_kind = CPU_MEDIA_PICKER_FLOPPY; g_runtime_floppy_picker.nav_up_prev = 0u; g_runtime_floppy_picker.nav_down_prev = 0u; g_runtime_floppy_picker.nav_left_prev = 0u; g_runtime_floppy_picker.nav_right_prev = 0u; g_runtime_floppy_picker.nav_enter_prev = 0u; g_runtime_floppy_picker.nav_esc_prev = 0u; }",
                "        } else {",
                "            g_runtime_floppy_picker.active = 0u;",
                "            g_runtime_floppy_picker.input_blocked = 1u;",
                "            g_runtime_media_picker_active_kind = CPU_MEDIA_PICKER_NONE;",
                "            g_runtime_floppy_picker.nav_up_prev = 0u;",
                "            g_runtime_floppy_picker.nav_down_prev = 0u;",
                "            g_runtime_floppy_picker.nav_left_prev = 0u;",
                "            g_runtime_floppy_picker.nav_right_prev = 0u;",
                "            g_runtime_floppy_picker.nav_enter_prev = 0u;",
                "            g_runtime_floppy_picker.nav_esc_prev = 0u;",
                "        }",
                "    }",
                "    g_runtime_floppy_picker.action_prev = trig;",
                "    if (g_runtime_floppy_picker.input_blocked != 0u) {",
                "        uint8_t any_nav = 0u;",
                "        if (trig != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(UP) < (size_t)key_count && ks[CPU_HOST_SCANCODE(UP)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(DOWN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(DOWN)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(RETURN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(RETURN)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(KP_ENTER) < (size_t)key_count && ks[CPU_HOST_SCANCODE(KP_ENTER)] != 0u) any_nav = 1u;",
                "        if ((size_t)CPU_HOST_SCANCODE(ESCAPE) < (size_t)key_count && ks[CPU_HOST_SCANCODE(ESCAPE)] != 0u) any_nav = 1u;",
                "        if (any_nav == 0u) g_runtime_floppy_picker.input_blocked = 0u;",
                "    }",
                "    if (g_runtime_floppy_picker.active == 0u || !ks || key_count <= 0) return;",
                "    up = ((size_t)CPU_HOST_SCANCODE(UP) < (size_t)key_count && ks[CPU_HOST_SCANCODE(UP)] != 0u) ? 1u : 0u;",
                "    down = ((size_t)CPU_HOST_SCANCODE(DOWN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(DOWN)] != 0u) ? 1u : 0u;",
                "    left = ((size_t)CPU_HOST_SCANCODE(LEFT) < (size_t)key_count && ks[CPU_HOST_SCANCODE(LEFT)] != 0u) ? 1u : 0u;",
                "    right = ((size_t)CPU_HOST_SCANCODE(RIGHT) < (size_t)key_count && ks[CPU_HOST_SCANCODE(RIGHT)] != 0u) ? 1u : 0u;",
                "    enter = (((size_t)CPU_HOST_SCANCODE(RETURN) < (size_t)key_count && ks[CPU_HOST_SCANCODE(RETURN)] != 0u) || ((size_t)CPU_HOST_SCANCODE(KP_ENTER) < (size_t)key_count && ks[CPU_HOST_SCANCODE(KP_ENTER)] != 0u)) ? 1u : 0u;",
                "    esc = ((size_t)CPU_HOST_SCANCODE(ESCAPE) < (size_t)key_count && ks[CPU_HOST_SCANCODE(ESCAPE)] != 0u) ? 1u : 0u;",
                "    if (left != 0u && g_runtime_floppy_picker.nav_left_prev == 0u) {",
                "        uint8_t target = cpu_component_media_picker_next_kind(CPU_MEDIA_PICKER_FLOPPY, -1);",
                "        if (target != CPU_MEDIA_PICKER_FLOPPY) {",
                "            g_runtime_floppy_picker.active = 0u;",
                "            g_runtime_floppy_picker.input_blocked = 1u;",
                "            g_runtime_floppy_picker.entry_count = 0u;",
                "            g_runtime_floppy_picker.selected = 0u;",
                "            g_runtime_media_picker_active_kind = CPU_MEDIA_PICKER_NONE;",
                "            g_runtime_media_picker_switch_pending = 1u;",
                "            g_runtime_media_picker_switch_target = target;",
                "            g_runtime_floppy_picker.nav_up_prev = 0u;",
                "            g_runtime_floppy_picker.nav_down_prev = 0u;",
                "            g_runtime_floppy_picker.nav_left_prev = 0u;",
                "            g_runtime_floppy_picker.nav_right_prev = 0u;",
                "            g_runtime_floppy_picker.nav_enter_prev = 0u;",
                "            g_runtime_floppy_picker.nav_esc_prev = 0u;",
                "            return;",
                "        }",
                "    }",
                "    if (right != 0u && g_runtime_floppy_picker.nav_right_prev == 0u) {",
                "        uint8_t target = cpu_component_media_picker_next_kind(CPU_MEDIA_PICKER_FLOPPY, 1);",
                "        if (target != CPU_MEDIA_PICKER_FLOPPY) {",
                "            g_runtime_floppy_picker.active = 0u;",
                "            g_runtime_floppy_picker.input_blocked = 1u;",
                "            g_runtime_floppy_picker.entry_count = 0u;",
                "            g_runtime_floppy_picker.selected = 0u;",
                "            g_runtime_media_picker_active_kind = CPU_MEDIA_PICKER_NONE;",
                "            g_runtime_media_picker_switch_pending = 1u;",
                "            g_runtime_media_picker_switch_target = target;",
                "            g_runtime_floppy_picker.nav_up_prev = 0u;",
                "            g_runtime_floppy_picker.nav_down_prev = 0u;",
                "            g_runtime_floppy_picker.nav_left_prev = 0u;",
                "            g_runtime_floppy_picker.nav_right_prev = 0u;",
                "            g_runtime_floppy_picker.nav_enter_prev = 0u;",
                "            g_runtime_floppy_picker.nav_esc_prev = 0u;",
                "            return;",
                "        }",
                "    }",
                "    if (up != 0u && g_runtime_floppy_picker.nav_up_prev == 0u && g_runtime_floppy_picker.entry_count > 0u) {",
                "        if (g_runtime_floppy_picker.selected == 0u) g_runtime_floppy_picker.selected = g_runtime_floppy_picker.entry_count - 1u; else g_runtime_floppy_picker.selected -= 1u;",
                "    }",
                "    if (down != 0u && g_runtime_floppy_picker.nav_down_prev == 0u && g_runtime_floppy_picker.entry_count > 0u) {",
                "        g_runtime_floppy_picker.selected = (g_runtime_floppy_picker.selected + 1u) % g_runtime_floppy_picker.entry_count;",
                "    }",
                "    if (esc != 0u && g_runtime_floppy_picker.nav_esc_prev == 0u) {",
                "        g_runtime_floppy_picker.active = 0u;",
                "        g_runtime_floppy_picker.input_blocked = 1u;",
                "        g_runtime_floppy_picker.entry_count = 0u;",
                "        g_runtime_floppy_picker.selected = 0u;",
                "    }",
                "    if (enter != 0u && g_runtime_floppy_picker.nav_enter_prev == 0u && g_runtime_floppy_picker.entry_count > 0u) {",
                "        const RuntimeFloppyEntry *sel = &g_runtime_floppy_picker.entries[g_runtime_floppy_picker.selected];",
                "        if (sel->media_path[0] == '\\0') {",
                "            g_runtime_floppy_picker.pending_eject = 1u;",
                "            g_runtime_floppy_picker.pending_load = 0u;",
                "            g_runtime_floppy_picker.pending_path[0] = '\\0';",
                "            snprintf(g_runtime_floppy_picker.loaded_name, sizeof(g_runtime_floppy_picker.loaded_name), \"%s\", \"<NO DISK>\");",
                "            g_runtime_floppy_picker.active_source_model[0] = '\\0';",
                "            snprintf(g_runtime_floppy_picker.active_source_label, sizeof(g_runtime_floppy_picker.active_source_label), \"%s\", sel->source_label);",
                "            g_runtime_floppy_picker.activity_flags = 0u;",
                "        } else {",
                "            g_runtime_floppy_picker.pending_eject = 0u;",
                "            g_runtime_floppy_picker.pending_load = 1u;",
                "            g_runtime_floppy_picker.pending_source_index = sel->source_index;",
                "            snprintf(g_runtime_floppy_picker.pending_path, sizeof(g_runtime_floppy_picker.pending_path), \"%s\", sel->media_path);",
                "            snprintf(g_runtime_floppy_picker.loaded_name, sizeof(g_runtime_floppy_picker.loaded_name), \"%s\", sel->file_name);",
                "            snprintf(g_runtime_floppy_picker.active_source_model, sizeof(g_runtime_floppy_picker.active_source_model), \"%s\", sel->source_model);",
                "            snprintf(g_runtime_floppy_picker.active_source_label, sizeof(g_runtime_floppy_picker.active_source_label), \"%s\", sel->source_label);",
                "            g_runtime_floppy_picker.activity_flags = 0u;",
                "        }",
                "        g_runtime_floppy_picker.status_now_cycle = cpu->total_cycles;",
                "        g_runtime_floppy_picker.status_until_cycle = cpu->total_cycles + (uint64_t)(CPU_SYSTEM_CLOCK_HZ * 10u);",
                "        g_runtime_floppy_picker.active = 0u;",
                "        g_runtime_floppy_picker.input_blocked = 1u;",
                "        g_runtime_floppy_picker.entry_count = 0u;",
                "        g_runtime_floppy_picker.selected = 0u;",
                "        g_runtime_floppy_picker.nav_up_prev = 0u;",
                "        g_runtime_floppy_picker.nav_down_prev = 0u;",
                "        g_runtime_floppy_picker.nav_left_prev = 0u;",
                "        g_runtime_floppy_picker.nav_right_prev = 0u;",
                "        g_runtime_floppy_picker.nav_enter_prev = 0u;",
                "        g_runtime_floppy_picker.nav_esc_prev = 0u;",
                "    }",
                "    g_runtime_floppy_picker.nav_up_prev = up;",
                "    g_runtime_floppy_picker.nav_down_prev = down;",
                "    g_runtime_floppy_picker.nav_left_prev = left;",
                "    g_runtime_floppy_picker.nav_right_prev = right;",
                "    g_runtime_floppy_picker.nav_enter_prev = enter;",
                "    g_runtime_floppy_picker.nav_esc_prev = esc;",
                "}",
                "void cpu_component_floppy_picker_draw_overlay(CPUState *cpu, uint32_t *pixels, uint32_t w, uint32_t h) {",
                "    char status_line[256];",
                "    char name_line[256];",
                "    int picker_text_w;",
                "    uint8_t activity_flags = 0u;",
                "    (void)cpu;",
                "    if (!pixels || w == 0u || h == 0u) return;",
                "    g_runtime_floppy_picker.status_now_cycle = (cpu != NULL) ? cpu->total_cycles : g_runtime_floppy_picker.status_now_cycle;",
                "    if (cpu != NULL && g_runtime_floppy_picker.component_id[0] != '\\0') {",
                '        uint8_t live_flags = (uint8_t)cpu_component_dispatch_callback(cpu, g_runtime_floppy_picker.component_id, "query_drive_activity", NULL, 0u);',
                "        if (live_flags != 0u) {",
                "            activity_flags = live_flags;",
                "            g_runtime_floppy_picker.status_until_cycle = cpu->total_cycles + (uint64_t)(CPU_SYSTEM_CLOCK_HZ * 10u);",
                "        }",
                "    }",
                "    snprintf(status_line, sizeof(status_line), \"%c%c MODE:%s\",",
                "        (activity_flags & 0x01u) != 0u ? 'R' : '-',",
                "        (activity_flags & 0x02u) != 0u ? 'W' : '-',",
                "        (g_runtime_floppy_picker.active_source_label[0] != '\\0') ? g_runtime_floppy_picker.active_source_label : \"Unknown\");",
                "    snprintf(name_line, sizeof(name_line), \"%s\", (g_runtime_floppy_picker.loaded_name[0] != '\\0') ? g_runtime_floppy_picker.loaded_name : \"<NO DISK>\");",
                "    if ((g_runtime_floppy_picker.loaded_name[0] != '\\0' || g_runtime_floppy_picker.active_source_label[0] != '\\0' || activity_flags != 0u) && g_runtime_floppy_picker.status_now_cycle < g_runtime_floppy_picker.status_until_cycle) {",
                "        int panel_x = 8;",
                "        int panel_y = (int)h - 38;",
                "        int panel_w = (int)w - 16;",
                "        pasm_overlay_fill_rect_alpha(pixels, w, h, panel_x, panel_y, panel_w, 30, 0x00101010u, 180u);",
                "        cpu_component_floppy_picker_draw_text_fit(pixels, w, h, panel_x + 4, panel_y + 4, status_line, 1, 0xFFE8E8A0u, panel_w - 8);",
                "        cpu_component_floppy_picker_draw_text_fit(pixels, w, h, panel_x + 4, panel_y + 14, name_line, 1, 0xFFE8E8A0u, panel_w - 8);",
                "    }",
                "    if (g_runtime_floppy_picker.active == 0u || g_runtime_floppy_picker.entry_count == 0u) return;",
                "    pasm_overlay_fill_rect_alpha(pixels, w, h, 10, 28, (int)w - 20, (int)h - 36, 0x00101010u, 190u);",
                "    picker_text_w = (int)w - 40;",
                "    cpu_component_floppy_picker_draw_text_fit(pixels, w, h, 20, 36, \"FLOPPY PICKER\", 1, 0xFFFFFFFFu, picker_text_w);",
                "    for (int i = 0; i < 10; ++i) {",
                "        size_t idx = ((g_runtime_floppy_picker.selected >= 4u) ? (g_runtime_floppy_picker.selected - 4u) : 0u) + (size_t)i;",
                "        if (idx >= g_runtime_floppy_picker.entry_count) break;",
                "        cpu_component_floppy_picker_draw_text_fit(pixels, w, h, 20, 56 + i * 9, g_runtime_floppy_picker.entries[idx].file_name, 1, (idx == g_runtime_floppy_picker.selected) ? 0xFF00FF9Fu : 0xFFE0E0E0u, picker_text_w);",
                "    }",
                "    cpu_component_floppy_picker_draw_text_fit(pixels, w, h, 20, (int)h - 42, \"UP/DOWN SELECT  ENTER INSERT/EJECT  ESC CANCEL\", 1, 0xFFFFFFA0u, picker_text_w);",
                "}",
                "",
            ]
        )
    else:
        helper_lines.extend(
            [
                f"int {cpu_prefix}_load_floppy_media(CPUState *cpu, const char *path) {{ (void)cpu; (void)path; return -1; }}",
                "int pasm_dbg_load_floppy_media(CPUState *cpu, const char *path) { (void)cpu; (void)path; return -1; }",
                "int cpu_component_floppy_picker_load_path(CPUState *cpu, const char *path) { (void)cpu; (void)path; return -1; }",
                "int cpu_component_floppy_picker_apply_pending_load(CPUState *cpu) { (void)cpu; return 0; }",
                "uint8_t cpu_component_floppy_picker_is_active(void) { return 0u; }",
                "uint8_t cpu_component_floppy_picker_overlay_visible(void) { return 0u; }",
                "uint8_t cpu_component_floppy_picker_blocks_input(void) { return 0u; }",
                "void cpu_component_floppy_picker_update(CPUState *cpu, uint8_t has_focus) { (void)cpu; (void)has_focus; }",
                "void cpu_component_floppy_picker_draw_overlay(CPUState *cpu, uint32_t *pixels, uint32_t w, uint32_t h) { (void)cpu; (void)pixels; (void)w; (void)h; }",
                "",
            ]
        )

    helper_lines.append("/* PASM_SPLIT_END:CARTRIDGE_PICKER_RUNTIME */")
    helper_lines.append("/* PASM_SPLIT_BEGIN:COMPONENT_RUNTIME */")
    helper_lines.append("/* PASM_SPLIT_BEGIN:COMPONENT_CONNECTIONS */")
    def _fnv64_py(text: str) -> int:
        h = 1469598103934665603
        for b in text.encode("utf-8"):
            h ^= b
            h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
        return h

    helper_lines.append("static uint64_t cpu_component_hash_str(const char *s) {")
    helper_lines.append("    uint64_t h = 1469598103934665603ull;")
    helper_lines.append("    const unsigned char *p = (const unsigned char *)s;")
    helper_lines.append("    if (p == NULL) return 0ull;")
    helper_lines.append("    while (*p != 0u) {")
    helper_lines.append("        h ^= (uint64_t)(*p++);")
    helper_lines.append("        h *= 1099511628211ull;")
    helper_lines.append("    }")
    helper_lines.append("    return h;")
    helper_lines.append("}")
    if connections:
        helper_lines.append("const ComponentConnection g_component_connections[] = {")
        for conn in connections:
            from_ep = conn.get("from", {})
            to_ep = conn.get("to", {})
            fk = str(from_ep.get("kind", ""))
            tk = str(to_ep.get("kind", ""))
            fk_id = 1 if fk == "callback" else (2 if fk == "signal" else 0)
            tk_id = 1 if tk == "callback" else (2 if tk == "handler" else 0)
            from_comp = str(from_ep.get("component", ""))
            from_name = str(from_ep.get("name", ""))
            to_comp = str(to_ep.get("component", ""))
            to_name = str(to_ep.get("name", ""))
            helper_lines.append(
                "    { "
                f"\"{_escape_c_string(from_comp)}\", "
                f"\"{_escape_c_string(fk)}\", "
                f"\"{_escape_c_string(from_name)}\", "
                f"\"{_escape_c_string(to_comp)}\", "
                f"\"{_escape_c_string(tk)}\", "
                f"\"{_escape_c_string(to_name)}\", "
                f"0x{_fnv64_py(from_comp):016X}ull, "
                f"0x{_fnv64_py(from_name):016X}ull, "
                f"0x{_fnv64_py(to_comp):016X}ull, "
                f"0x{_fnv64_py(to_name):016X}ull, "
                f"{fk_id}u, "
                f"{tk_id}u "
                "},"
            )
        helper_lines.append("};")
    else:
        helper_lines.append(
            "const ComponentConnection g_component_connections[] = { { \"\", \"\", \"\", \"\", \"\", \"\", 0ull, 0ull, 0ull, 0ull, 0u, 0u } };"
        )
    helper_lines.append(
        "const size_t g_component_connections_count = sizeof(g_component_connections) / sizeof(g_component_connections[0]);"
    )
    helper_lines.append("/* PASM_SPLIT_END:COMPONENT_CONNECTIONS */")
    helper_lines.append("/* PASM_SPLIT_BEGIN:COMPONENT_DISPATCH */")
    callback_dispatch_lines: List[str] = [
        "typedef uint64_t (*ComponentCallbackFn)(CPUState *, const uint64_t *, uint8_t);",
        "static uint64_t g_callback_cache_key[256];",
        "static ComponentCallbackFn g_callback_cache_fn[256];",
        "",
        "uint64_t cpu_component_dispatch_callback(",
        "    CPUState *cpu,",
        "    const char *component_id,",
        "    const char *callback_name,",
        "    const uint64_t *args,",
        "    uint8_t argc",
        ") {",
        "    uint64_t __hk_comp = cpu_component_hash_str(component_id);",
        "    uint64_t __hk_name = cpu_component_hash_str(callback_name);",
        "    uint64_t __key = __hk_comp ^ ((__hk_name << 1u) | (__hk_name >> 63u));",
        "    uintptr_t h = (uintptr_t)(__key & 255u);",
        "    if (g_callback_cache_key[h] == __key && g_callback_cache_fn[h] != NULL) {",
        "        return g_callback_cache_fn[h](cpu, args, argc);",
        "    }",
    ]
    cb_pair_hashes: Dict[int, Tuple[str, str]] = {}
    for component in components:
        comp_id = str(component.get("metadata", {}).get("id", "component"))
        comp_ident = _ident(comp_id)
        callback_handlers = component.get("behavior", {}).get("callback_handlers", {})
        for callback in component.get("interfaces", {}).get("callbacks", []):
            cb_name = str(callback.get("name", "callback"))
            cb_ident = _ident(cb_name)
            body = str(callback_handlers.get(cb_name, "")).rstrip()
            helper_lines.append(
                f"static uint64_t component_{comp_ident}_callback_{cb_ident}(CPUState *cpu, const uint64_t *args, uint8_t argc) {{"
            )
            helper_lines.append("    (void)argc;")
            helper_lines.append(f"    ComponentState_{comp_ident} *comp = &cpu->comp_{comp_ident};")
            helper_lines.append(f'    cpu->active_component_id = "{_escape_c_string(comp_id)}";')
            helper_lines.append("    uint64_t __result = 0;")
            if cb_name == "step_post":
                # helper_lines.append(
                #     "    cpu_component_cartridge_picker_update(cpu, cpu_host_hal_window_has_focus(NULL));"
                # )
                # helper_lines.append(
                #     "    if (cpu_component_cartridge_picker_is_active() != 0u) return __result;"
                # )
                pass
            if body:
                for raw_line in body.splitlines():
                    helper_lines.append(f"    {raw_line.rstrip()}" if raw_line.strip() else "")
            else:
                # Fallback for callbacks without explicit handler code:
                # if there is a declared callback->callback connection for this
                # callback, forward to the target callback. This preserves
                # behavior for call sites that may dispatch callbacks directly.
                helper_lines.append("    for (size_t __i = 0; __i < g_component_connections_count; ++__i) {")
                helper_lines.append("        const ComponentConnection *__conn = &g_component_connections[__i];")
                helper_lines.append("        if (__conn->from_kind_id != 1u) continue;")
                helper_lines.append(f"        if (__conn->from_component_hash != 0x{_fnv64_py(comp_id):016X}ull) continue;")
                helper_lines.append(f"        if (__conn->from_name_hash != 0x{_fnv64_py(cb_name):016X}ull) continue;")
                helper_lines.append(f"        if (__conn->to_component_hash == 0x{_fnv64_py(comp_id):016X}ull && __conn->to_name_hash == 0x{_fnv64_py(cb_name):016X}ull) continue;")
                helper_lines.append("        return cpu_component_dispatch_callback(cpu, __conn->to_component, __conn->to_name, args, argc);")
                helper_lines.append("    }")
                helper_lines.append("    (void)args;")
            helper_lines.append("    return __result;")
            helper_lines.append("}")
            helper_lines.append("")
            pair_h = _fnv64_py(comp_id) ^ (((_fnv64_py(cb_name) << 1) | (_fnv64_py(cb_name) >> 63)) & 0xFFFFFFFFFFFFFFFF)
            if pair_h in cb_pair_hashes and cb_pair_hashes[pair_h] != (comp_id, cb_name):
                raise RuntimeError(
                    f"callback dispatch hash collision: {cb_pair_hashes[pair_h]} vs {(comp_id, cb_name)}"
                )
            cb_pair_hashes[pair_h] = (comp_id, cb_name)
            callback_dispatch_lines.append(
                f"    if (__key == 0x{pair_h:016X}ull) "
                f"{{ g_callback_cache_key[h] = __key; "
                f"g_callback_cache_fn[h] = component_{comp_ident}_callback_{cb_ident}; "
                f"return component_{comp_ident}_callback_{cb_ident}(cpu, args, argc); }}"
            )
    callback_dispatch_lines.append("    return 0;")
    callback_dispatch_lines.append("}")
    callback_dispatch_lines.append("")
    helper_lines.extend(callback_dispatch_lines)

    handler_dispatch_lines: List[str] = [
        "typedef void (*ComponentHandlerFn)(CPUState *, const uint64_t *, uint8_t);",
        "static uint64_t g_handler_cache_key[256];",
        "static ComponentHandlerFn g_handler_cache_fn[256];",
        "",
        "void cpu_component_dispatch_handler(",
        "    CPUState *cpu,",
        "    const char *component_id,",
        "    const char *handler_name,",
        "    const uint64_t *args,",
        "    uint8_t argc",
        ") {",
        "    uint64_t __hk_comp = cpu_component_hash_str(component_id);",
        "    uint64_t __hk_name = cpu_component_hash_str(handler_name);",
        "    uint64_t __key = __hk_comp ^ ((__hk_name << 1u) | (__hk_name >> 63u));",
        "    uintptr_t h = (uintptr_t)(__key & 255u);",
        "    if (g_handler_cache_key[h] == __key && g_handler_cache_fn[h] != NULL) {",
        "        g_handler_cache_fn[h](cpu, args, argc);",
        "        return;",
        "    }",
    ]
    h_pair_hashes: Dict[int, Tuple[str, str]] = {}
    for component in components:
        comp_id = str(component.get("metadata", {}).get("id", "component"))
        comp_ident = _ident(comp_id)
        handler_bodies = component.get("behavior", {}).get("handler_bodies", {})
        for handler in component.get("interfaces", {}).get("handlers", []):
            handler_name = str(handler.get("name", "handler"))
            handler_ident = _ident(handler_name)
            body = str(handler_bodies.get(handler_name, "")).rstrip()
            helper_lines.append(
                f"static void component_{comp_ident}_handler_{handler_ident}(CPUState *cpu, const uint64_t *args, uint8_t argc) {{"
            )
            helper_lines.append("    (void)argc;")
            helper_lines.append(f"    ComponentState_{comp_ident} *comp = &cpu->comp_{comp_ident};")
            helper_lines.append(f'    cpu->active_component_id = "{_escape_c_string(comp_id)}";')
            if handler_name == "video_frame":
                helper_lines.append("    uint64_t overlay_args_local[8];")
                state_fields = {
                    str(field.get("name", "")).strip()
                    for field in component.get("state", []) or []
                    if isinstance(field, dict)
                }
                if "has_keyboard_focus" in state_fields:
                    helper_lines.append("    cpu_component_host_picker_step(cpu, comp->has_keyboard_focus);")
                else:
                    helper_lines.append("    cpu_component_host_picker_step(cpu, 1u);")
                helper_lines.append("        static uint32_t *overlay_pixels = NULL;")
                helper_lines.append("        static size_t overlay_capacity = 0u;")
                helper_lines.append("        uint32_t *video_pixels = NULL;")
                helper_lines.append("        uint32_t picker_w = 0u;")
                helper_lines.append("        uint32_t picker_h = 0u;")
                helper_lines.append("        size_t overlay_need = 0u;")
                helper_lines.append("        uint8_t need_overlay_copy = 0u;")
                helper_lines.append("    if (argc >= 4u) {")
                helper_lines.append("        video_pixels = (uint32_t *)(uintptr_t)args[1];")
                helper_lines.append("        picker_w = (uint32_t)(args[2] & 0xFFFFFFFFu);")
                helper_lines.append("        picker_h = (uint32_t)(args[3] & 0xFFFFFFFFu);")
                helper_lines.append("        need_overlay_copy = (uint8_t)((cpu->debug_overlay_enabled != 0u || cpu_component_cartridge_picker_is_active() != 0u || cpu_component_cassette_picker_overlay_visible() != 0u || cpu_component_floppy_picker_overlay_visible() != 0u) ? 1u : 0u);")
                helper_lines.append("        if (need_overlay_copy != 0u && video_pixels != NULL && picker_w != 0u && picker_h != 0u) {")
                helper_lines.append("            overlay_need = (size_t)picker_w * (size_t)picker_h * sizeof(uint32_t);")
                helper_lines.append("            if (overlay_need > overlay_capacity) {")
                helper_lines.append("                uint32_t *nb = (uint32_t *)realloc(overlay_pixels, overlay_need);")
                helper_lines.append("                if (nb != NULL) {")
                helper_lines.append("                    overlay_pixels = nb;")
                helper_lines.append("                    overlay_capacity = overlay_need;")
                helper_lines.append("                }")
                helper_lines.append("            }")
                helper_lines.append("            if (overlay_pixels != NULL && overlay_capacity >= overlay_need) {")
                helper_lines.append("                memcpy(overlay_pixels, video_pixels, overlay_need);")
                helper_lines.append("                cpu_component_cartridge_picker_draw_overlay(cpu, overlay_pixels, picker_w, picker_h);")
                helper_lines.append("                cpu_component_cassette_picker_draw_overlay(cpu, overlay_pixels, picker_w, picker_h);")
                helper_lines.append("                cpu_component_floppy_picker_draw_overlay(cpu, overlay_pixels, picker_w, picker_h);")
                helper_lines.append("                memcpy(overlay_args_local, args, (size_t)argc * sizeof(uint64_t));")
                helper_lines.append("                overlay_args_local[1] = (uint64_t)(uintptr_t)overlay_pixels;")
                helper_lines.append("                args = overlay_args_local;")
                helper_lines.append("            } else {")
                helper_lines.append("                cpu_component_cartridge_picker_draw_overlay(cpu, video_pixels, picker_w, picker_h);")
                helper_lines.append("                cpu_component_cassette_picker_draw_overlay(cpu, video_pixels, picker_w, picker_h);")
                helper_lines.append("                cpu_component_floppy_picker_draw_overlay(cpu, video_pixels, picker_w, picker_h);")
                helper_lines.append("            }")
                helper_lines.append("        }")
                helper_lines.append("    }")
            if body:
                for raw_line in body.splitlines():
                    helper_lines.append(f"    {raw_line.rstrip()}" if raw_line.strip() else "")
            helper_lines.append("}")
            helper_lines.append("")
            pair_h = _fnv64_py(comp_id) ^ (((_fnv64_py(handler_name) << 1) | (_fnv64_py(handler_name) >> 63)) & 0xFFFFFFFFFFFFFFFF)
            if pair_h in h_pair_hashes and h_pair_hashes[pair_h] != (comp_id, handler_name):
                raise RuntimeError(
                    f"handler dispatch hash collision: {h_pair_hashes[pair_h]} vs {(comp_id, handler_name)}"
                )
            h_pair_hashes[pair_h] = (comp_id, handler_name)
            handler_dispatch_lines.append(
                f"    if (__key == 0x{pair_h:016X}ull) "
                f"{{ g_handler_cache_key[h] = __key; "
                f"g_handler_cache_fn[h] = component_{comp_ident}_handler_{handler_ident}; "
                f"component_{comp_ident}_handler_{handler_ident}(cpu, args, argc); return; }}"
            )
    handler_dispatch_lines.append("    (void)cpu;")
    handler_dispatch_lines.append("    (void)component_id;")
    handler_dispatch_lines.append("    (void)handler_name;")
    handler_dispatch_lines.append("    (void)args;")
    handler_dispatch_lines.append("    (void)argc;")
    handler_dispatch_lines.append("}")
    handler_dispatch_lines.append("")
    helper_lines.extend(handler_dispatch_lines)

    helper_lines.append("/* PASM_SPLIT_BEGIN:COMPONENT_ROUTING */")
    helper_lines.extend(
        [
            "typedef struct {",
            "    uint64_t from_component_hash;",
            "    uint64_t from_name_hash;",
            "    const char *to_component;",
            "    const char *to_name;",
            "} CallbackRouteCacheEntry;",
            "typedef struct {",
            "    uint64_t from_component_hash;",
            "    uint64_t from_name_hash;",
            "    uint16_t first_idx;",
            "    uint16_t count;",
            "} SignalRouteCacheEntry;",
            "static CallbackRouteCacheEntry g_cb_route_cache[256];",
            "static SignalRouteCacheEntry g_sig_route_cache[256];",
            "",
            "uint64_t cpu_component_call(",
            "    CPUState *cpu,",
            "    const char *source_component,",
            "    const char *callback_name,",
            "    const uint64_t *args,",
            "    uint8_t argc",
            ") {",
            "    uint64_t __src_h = cpu_component_hash_str(source_component);",
            "    uint64_t __name_h = cpu_component_hash_str(callback_name);",
            "    uint64_t __rkey = __src_h ^ ((__name_h << 1u) | (__name_h >> 63u));",
            "    uintptr_t h = (uintptr_t)(__rkey & 255u);",
            "    if (g_cb_route_cache[h].from_component_hash == __src_h &&",
            "        g_cb_route_cache[h].from_name_hash == __name_h &&",
            "        g_cb_route_cache[h].to_component != NULL &&",
            "        g_cb_route_cache[h].to_name != NULL) {",
            "        return cpu_component_dispatch_callback(cpu, g_cb_route_cache[h].to_component, g_cb_route_cache[h].to_name, args, argc);",
            "    }",
            "    size_t connection_count = g_component_connections_count;",
            "    for (size_t i = 0; i < connection_count; i++) {",
            "        const ComponentConnection *conn = &g_component_connections[i];",
            "        if (conn->from_kind_id != 1u) continue;",
            "        if (conn->from_component_hash != __src_h) continue;",
            "        if (conn->from_name_hash != __name_h) continue;",
            "        g_cb_route_cache[h].from_component_hash = __src_h;",
            "        g_cb_route_cache[h].from_name_hash = __name_h;",
            "        g_cb_route_cache[h].to_component = conn->to_component;",
            "        g_cb_route_cache[h].to_name = conn->to_name;",
            "        return cpu_component_dispatch_callback(cpu, conn->to_component, conn->to_name, args, argc);",
            "    }",
            "    return 0;",
            "}",
            "",
            "void cpu_component_emit_signal(",
            "    CPUState *cpu,",
            "    const char *source_component,",
            "    const char *signal_name,",
            "    const uint64_t *args,",
            "    uint8_t argc",
            ") {",
            "    uint64_t __src_h = cpu_component_hash_str(source_component);",
            "    uint64_t __name_h = cpu_component_hash_str(signal_name);",
            "    uint64_t __rkey = __src_h ^ ((__name_h << 1u) | (__name_h >> 63u));",
            "    uintptr_t h = (uintptr_t)(__rkey & 255u);",
            "    if (g_sig_route_cache[h].from_component_hash == __src_h &&",
            "        g_sig_route_cache[h].from_name_hash == __name_h &&",
            "        g_sig_route_cache[h].count != 0u) {",
            "        uint16_t first = g_sig_route_cache[h].first_idx;",
            "        uint16_t count = g_sig_route_cache[h].count;",
            "        for (uint16_t k = 0u; k < count; ++k) {",
            "            const ComponentConnection *conn = &g_component_connections[(size_t)first + (size_t)k];",
            "            cpu_component_dispatch_handler(cpu, conn->to_component, conn->to_name, args, argc);",
            "        }",
            "        return;",
            "    }",
            "    size_t connection_count = g_component_connections_count;",
            "    uint16_t first_idx = 0xFFFFu;",
            "    uint16_t count = 0u;",
            "    for (size_t i = 0; i < connection_count; i++) {",
            "        const ComponentConnection *conn = &g_component_connections[i];",
            "        if (conn->from_kind_id != 2u) continue;",
            "        if (conn->from_component_hash != __src_h) continue;",
            "        if (conn->from_name_hash != __name_h) continue;",
            "        if (first_idx == 0xFFFFu) first_idx = (uint16_t)i;",
            "        count = (uint16_t)(count + 1u);",
            "        cpu_component_dispatch_handler(cpu, conn->to_component, conn->to_name, args, argc);",
            "    }",
            "    if (count != 0u) {",
            "        g_sig_route_cache[h].from_component_hash = __src_h;",
            "        g_sig_route_cache[h].from_name_hash = __name_h;",
            "        g_sig_route_cache[h].first_idx = first_idx;",
            "        g_sig_route_cache[h].count = count;",
            "    }",
            "}",
            "",
        ]
    )
    helper_lines.append("/* PASM_SPLIT_END:COMPONENT_ROUTING */")
    helper_lines.append("/* PASM_SPLIT_END:COMPONENT_DISPATCH */")

    helper_lines.extend(
        [
            "int cpu_components_runtime_pre_step(CPUState *cpu) {",
            "    if (cpu != NULL && cpu->reset_delay_pending) {",
            "        cpu->reset_delay_pending = false;",
            "    }",
        ]
    )
    if has_runtime_cartridge:
        helper_lines.extend(
            [
                "    if (cpu_component_cartridge_picker_apply_pending_swap(cpu) != 0) {",
                "        return -1;",
                "    }",
            ]
        )
    if has_runtime_cassette:
        helper_lines.extend(
            [
                "    if (cpu_component_cassette_picker_apply_pending_load(cpu) != 0) {",
                "        return -1;",
                "    }",
            ]
        )
    if has_runtime_floppy:
        helper_lines.extend(
            [
                "    if (cpu_component_floppy_picker_apply_pending_load(cpu) != 0) {",
                "        return -1;",
                "    }",
            ]
        )
    helper_lines.extend(
        [
            "    (void)cpu;",
            "    return 0;",
            "}",
            "",
            "void cpu_components_step_pre(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before) {",
            "    (void)inst;",
            "    (void)pc_before;",
        ]
    )
    for component in components:
        block = _snippet_block(component, "step_pre")
        if block:
            helper_lines.append(block)
    helper_lines.append("}")
    helper_lines.append("")
    helper_lines.extend(
        [
            "void cpu_components_step_post(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before) {",
        ]
    )
    emitted_post = False
    for component in components:
        block = _snippet_block(component, "step_post")
        if block:
            helper_lines.append(block)
            emitted_post = True
    if not emitted_post:
        helper_lines.extend(
            [
                "    (void)cpu;",
                "    (void)inst;",
                "    (void)pc_before;",
            ]
        )
    else:
        helper_lines.extend(
            [
                "    (void)inst;",
                "    (void)pc_before;",
            ]
        )
    helper_lines.append("}")
    helper_lines.append("/* PASM_SPLIT_END:COMPONENT_RUNTIME */")

    init_lines = [
        "    cpu->active_component_id = NULL;",
        "    cpu->component_last_return = 0;",
    ]
    reset_lines = [
        "    cpu->active_component_id = NULL;",
        "    cpu->component_last_return = 0;",
    ]
    destroy_lines = []
    for component in components:
        comp_id = str(component.get("metadata", {}).get("id", "component"))
        comp_ident = _ident(comp_id)
        is_host_component = comp_id in host_component_ids
        for field in component.get("state", []):
            field_name = _ident(str(field.get("name", "field")))
            field_type = str(field.get("type", "")).strip()
            initial = str(field.get("initial", "0")).strip() or "0"
            init_lines.append(f"    cpu->comp_{comp_ident}.{field_name} = {initial};")
            is_pointer_field = "*" in field_type
            preserve_reset_field = field_name in {"rom_data", "rom_size"}
            if (
                not is_host_component
                and not is_pointer_field
                and not preserve_reset_field
            ):
                reset_lines.append(f"    cpu->comp_{comp_ident}.{field_name} = {initial};")

        init_snippet = _snippet_block(component, "init")
        reset_snippet = _snippet_block(component, "reset")
        if init_snippet:
            init_lines.append(init_snippet)
        if reset_snippet:
            reset_lines.append(reset_snippet)
        destroy_snippet = _snippet_block(component, "destroy", indent="        ")
        if destroy_snippet:
            destroy_lines.append(destroy_snippet)

    def _slot(slot_name: str) -> str:
        blocks = [_snippet_block(component, slot_name) for component in components]
        return "\n".join(block for block in blocks if block)

    ic_impl = "/* No public component runtime API */"

    return (
        "\n".join(helper_lines),
        "\n".join(init_lines),
        "\n".join(reset_lines),
        "\n".join(destroy_lines) if destroy_lines else "        /* No component destroy hooks */",
        _slot("mem_read_pre"),
        _slot("mem_write_pre"),
        _slot("port_read_pre"),
        _slot("port_read_post"),
        _slot("port_write_pre"),
        _slot("port_write_post"),
        ic_impl,
    )




def _normalize_behavior(behavior: str, cpu_prefix: str, flag_names: Set[str]) -> str:
    """Validate behavior snippets against the canonical generated API."""

    normalized_lines: List[str] = []
    for raw_line in behavior.strip().splitlines():
        line = raw_line.rstrip()

        if re.search(r"\binst\.[A-Za-z_]", line):
            raise ValueError(
                "Behavior must use pointer-style operands (`inst->field`)."
            )
        if re.search(r"\bcpu_(read|write)_(byte|word|port)\s*\(", line):
            raise ValueError(
                "Behavior must use generated CPU-prefixed helpers "
                f"(`{cpu_prefix}_read_*` / `{cpu_prefix}_write_*`)."
            )

        if "CPU_FLAG_SET_" in line or "CPU_FLAG_GET_" in line:
            raise ValueError(
                "Behavior must use YAML-defined named flags (`cpu->flags.<NAME>`), "
                "not helper macros."
            )
        if "CPU_SET_PC(" in line:
            raise ValueError(
                "Behavior must assign `cpu->pc` directly; `CPU_SET_PC` is not supported."
            )

        if re.search(r"cpu->flags\.[A-Za-z_][A-Za-z0-9_]*\s*(\+\+|--|[+\-*/%&|^]=)", line):
            raise ValueError(
                "Behavior must assign flags with `cpu->flags.<NAME> = ...;` or use `cpu->flags.raw` bitwise operations."
            )

        # Validate named flag writes.
        assign_match = re.match(
            r"^(\s*)cpu->flags\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+);\s*$",
            line,
        )
        if assign_match:
            indent, field_name, expr = assign_match.groups()
            if field_name != "raw":
                upper_flag = field_name.upper()
                if upper_flag not in flag_names:
                    raise ValueError(
                        f"Unknown flag '{field_name}' in behavior line: {raw_line}"
                    )

        # Validate named flag reads.
        for field_name in re.findall(r"cpu->flags\.([A-Za-z_][A-Za-z0-9_]*)", line):
            if field_name == "raw":
                continue
            upper_flag = field_name.upper()
            if upper_flag not in flag_names:
                raise ValueError(
                    f"Unknown flag '{field_name}' in behavior line: {raw_line}"
                )

        # Track explicit PC writes so step() can preserve control-flow semantics.
        pc_assign_match = re.match(r"^(\s*)cpu->pc\s*=\s*(.+);\s*$", line)
        if pc_assign_match:
            indent, expr = pc_assign_match.groups()
            expr_norm = expr.strip()
            if "cpu->pc" in expr_norm:
                expr_norm = re.sub(
                    r"\bcpu->pc\b",
                    "((uint16_t)(cpu->pc + inst->length))",
                    expr_norm,
                )
            normalized_lines.append(f"{indent}cpu->pc = {expr_norm};")
            normalized_lines.append(f"{indent}cpu->pc_modified = true;")
            continue

        if re.search(r"cpu->pc\s*(\+\+|--|[+\-*/%]?=)", line):
            raise ValueError(
                "Behavior must assign PC with `cpu->pc = ...;` so generation can track explicit control-flow."
            )

        normalized_lines.append(line)

    return "\n".join(normalized_lines)


def _generate_instructions(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate instruction implementation functions."""
    lines: List[str] = []

    instructions = isa_data.get("instructions", [])
    flag_names = {f.get("name", "").upper() for f in isa_data.get("flags", [])}

    for inst in instructions:
        name = inst.get("name", "UNKNOWN")
        category = inst.get("category", "misc")
        behavior = inst.get("behavior", "(void)cpu;")
        try:
            normalized_behavior = _normalize_behavior(behavior, cpu_prefix, flag_names)
        except ValueError as exc:
            raise ValueError(f"Instruction '{name}': {exc}") from exc

        lines.append(f"/* {name} - {category} */")
        lines.append(f"static void inst_{name}(CPUState *cpu, DecodedInstruction *inst) {{")

        for line in normalized_behavior.splitlines():
            if line.strip():
                lines.append(f"    {line.strip()}")
            else:
                lines.append("")

        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def _dispatch_condition(inst: Dict[str, Any]) -> str:
    encoding = inst.get("encoding", {})
    opcode = encoding.get("opcode", 0)
    mask = encoding.get("mask", 0xFF)
    subop = encoding.get("subop")
    subop_mask = encoding.get("subop_mask", 0xFF)
    prefix = encoding.get("prefix")
    length = encoding.get("length", inst.get("length", 1))

    if subop is not None:
        if prefix is not None and opcode == 0xCB and length >= 4:
            # DD/FD CB d op form: subop is in the third byte after prefix.
            if subop_mask != 0xFF:
                condition = (
                    f"((inst.raw & 0x00FF) == 0x{opcode:02X} && "
                    f"((((inst.raw >> 16) & 0x00FF) & 0x{subop_mask:02X}) == 0x{subop & subop_mask:02X}))"
                )
            else:
                condition = (
                    f"((inst.raw & 0x00FF) == 0x{opcode:02X} && "
                    f"((inst.raw >> 16) & 0x00FF) == 0x{subop:02X})"
                )
        else:
            if subop_mask != 0xFF:
                condition = (
                    f"((inst.raw & 0x00FF) == 0x{opcode:02X} && "
                    f"((((inst.raw >> 8) & 0x00FF) & 0x{subop_mask:02X}) == 0x{subop & subop_mask:02X}))"
                )
            else:
                condition = (
                    f"((inst.raw & 0x00FF) == 0x{opcode:02X} && "
                    f"((inst.raw >> 8) & 0x00FF) == 0x{subop:02X})"
                )
    elif mask == 0xFF:
        condition = f"(inst.opcode == 0x{opcode & 0xFF:02X})"
    else:
        condition = f"((inst.raw & 0x{mask:04X}) == 0x{opcode:04X})"

    if prefix is not None:
        condition = f"(inst.prefix == 0x{prefix:02X} && {condition})"
    else:
        condition = f"(inst.prefix == 0x00 && {condition})"

    return condition


def _generate_disassembler(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate trace/disassembly helpers with mnemonic lookup."""
    lines: List[str] = []
    instructions = isa_data.get("instructions", [])
    numeric_style = _codegen_numeric_style(isa_data)
    numeric_formats = _codegen_numeric_formats(isa_data)
    allowed_display_kinds = _codegen_enabled_display_kinds(isa_data)
    explicit_prefixes = sorted(
        {
            int(inst.get("encoding", {}).get("prefix"))
            for inst in instructions
            if "prefix" in inst.get("encoding", {}) and int(inst.get("encoding", {}).get("prefix")) != 0
        }
    )
    used_display_kinds: Set[str] = set()
    for inst in instructions:
        render_inst = inst
        inferred_template = _infer_display_template(inst, immediate_style=numeric_style)
        if inferred_template:
            render_inst = dict(inst)
            render_inst["display_template"] = inferred_template
        used_display_kinds |= _instruction_render_kinds(render_inst, allowed_display_kinds)
    needs_mc6809_helpers = bool(used_display_kinds & MC6809_SPECIAL_DISPLAY_KINDS)

    # Group by category to keep generated branch structure compact.
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for inst in instructions:
        categories.setdefault(inst.get("category", "misc"), []).append(inst)

    if needs_mc6809_helpers:
        lines.append("static void dbg_mc6809_format_signed8_hex(int8_t value, char *out, size_t out_sz) {")
        lines.append("    if (value < 0) {")
        lines.append("        uint8_t mag = (uint8_t)(-(int)value);")
        lines.append('        (void)snprintf(out, out_sz, "-$%02X", (unsigned int)mag);')
        lines.append("    } else {")
        lines.append('        (void)snprintf(out, out_sz, "$%02X", (unsigned int)((uint8_t)value));')
        lines.append("    }")
        lines.append("}")
        lines.append("")
        lines.append("static void dbg_mc6809_format_signed16_hex(int16_t value, char *out, size_t out_sz) {")
        lines.append("    if (value < 0) {")
        lines.append("        uint16_t mag = (uint16_t)(-(int32_t)value);")
        lines.append('        (void)snprintf(out, out_sz, "-$%04X", (unsigned int)mag);')
        lines.append("    } else {")
        lines.append('        (void)snprintf(out, out_sz, "$%04X", (unsigned int)((uint16_t)value));')
        lines.append("    }")
        lines.append("}")
        lines.append("")
        lines.append("static void dbg_mc6809_format_stack_mask(uint8_t mask, const char *bit6_name, uint8_t pull_order, char *out, size_t out_sz) {")
        lines.append('    static const char *base_names[8] = {"CC", "A", "B", "DP", "X", "Y", NULL, "PC"};')
        lines.append("    static const uint8_t order_push[8] = {7u, 6u, 5u, 4u, 3u, 2u, 1u, 0u};")
        lines.append("    static const uint8_t order_pull[8] = {0u, 1u, 2u, 3u, 4u, 5u, 6u, 7u};")
        lines.append("    size_t used = 0u;")
        lines.append("    uint8_t wrote = 0u;")
        lines.append("    if (out_sz == 0u) {")
        lines.append("        return;")
        lines.append("    }")
        lines.append("    out[0] = '\\0';")
        lines.append("    for (uint8_t i = 0u; i < 8u; ++i) {")
        lines.append("        uint8_t bit = (pull_order != 0u) ? order_pull[i] : order_push[i];")
        lines.append("        if ((mask & (uint8_t)(1u << bit)) == 0u) {")
        lines.append("            continue;")
        lines.append("        }")
        lines.append("        const char *name = (bit == 6u) ? bit6_name : base_names[bit];")
        lines.append("        if (name == NULL || name[0] == '\\0') {")
        lines.append("            continue;")
        lines.append("        }")
        lines.append(
            '        int n = snprintf(out + used, out_sz - used, (wrote != 0u) ? ",%s" : "%s", name);'
        )
        lines.append("        if (n < 0) {")
        lines.append("            break;")
        lines.append("        }")
        lines.append("        if ((size_t)n >= (out_sz - used)) {")
        lines.append("            out[out_sz - 1u] = '\\0';")
        lines.append("            wrote = 1u;")
        lines.append("            break;")
        lines.append("        }")
        lines.append("        used += (size_t)n;")
        lines.append("        wrote = 1u;")
        lines.append("    }")
        lines.append("    if (wrote == 0u) {")
        lines.append('        (void)snprintf(out, out_sz, "$%02X", (unsigned int)mask);')
        lines.append("    }")
        lines.append("}")
        lines.append("")
        lines.append("static void dbg_mc6809_format_indexed(uint8_t pb, uint16_t pc, uint32_t raw, uint8_t prefix, char *out, size_t out_sz) {")
        lines.append('    static const char *regs[4] = {"X", "Y", "U", "S"};')
        lines.append("    uint8_t rr = (uint8_t)((pb >> 5) & 0x03u);")
        lines.append("    const char *r = regs[rr];")
        lines.append("    uint8_t op_len = (uint8_t)((prefix != 0u) ? 2u : 1u);")
        lines.append("    uint16_t pc_after_pb = (uint16_t)(pc + (uint16_t)op_len + 1u);")
        lines.append("    uint8_t extra1 = 0u;")
        lines.append("    uint8_t extra2 = 0u;")
        lines.append("    uint8_t have_extra1 = 0u;")
        lines.append("    uint8_t have_extra2 = 0u;")
        lines.append("    char off_buf[24];")
        lines.append("")
        lines.append("    if (prefix == 0u) {")
        lines.append("        extra1 = (uint8_t)((raw >> 16) & 0xFFu);")
        lines.append("        extra2 = (uint8_t)((raw >> 24) & 0xFFu);")
        lines.append("        have_extra1 = 1u;")
        lines.append("        have_extra2 = 1u;")
        lines.append("    } else {")
        lines.append("        extra1 = (uint8_t)((raw >> 24) & 0xFFu);")
        lines.append("        have_extra1 = 1u;")
        lines.append("    }")
        lines.append("")
        lines.append("    if ((pb & 0x80u) == 0u) {")
        lines.append("        int8_t off5 = (int8_t)(pb & 0x1Fu);")
        lines.append("        if ((off5 & 0x10) != 0) off5 = (int8_t)(off5 | (int8_t)0xE0);")
        lines.append('        (void)snprintf(out, out_sz, "%d,%s", (int)off5, r);')
        lines.append("        return;")
        lines.append("    }")
        lines.append("    {")
        lines.append("        uint8_t mode = (uint8_t)(pb & 0x1Fu);")
        lines.append("        uint8_t indirect = (uint8_t)((mode & 0x10u) != 0u);")
        lines.append("        uint8_t m = mode;")
        lines.append("        if (indirect != 0u) m = (uint8_t)(mode & 0x0Fu);")
        lines.append("        switch (m) {")
        lines.append("            case 0x00u: (void)snprintf(out, out_sz, (indirect ? \"[,%s+]\" : \",%s+\"), r); return;")
        lines.append("            case 0x01u: (void)snprintf(out, out_sz, (indirect ? \"[,%s++]\" : \",%s++\"), r); return;")
        lines.append("            case 0x02u: (void)snprintf(out, out_sz, (indirect ? \"[,-%s]\" : \",-%s\"), r); return;")
        lines.append("            case 0x03u: (void)snprintf(out, out_sz, (indirect ? \"[,--%s]\" : \",--%s\"), r); return;")
        lines.append("            case 0x04u: (void)snprintf(out, out_sz, (indirect ? \"[,%s]\" : \",%s\"), r); return;")
        lines.append("            case 0x05u: (void)snprintf(out, out_sz, (indirect ? \"[B,%s]\" : \"B,%s\"), r); return;")
        lines.append("            case 0x06u: (void)snprintf(out, out_sz, (indirect ? \"[A,%s]\" : \"A,%s\"), r); return;")
        lines.append("            case 0x08u:")
        lines.append("                if (have_extra1 != 0u) {")
        lines.append("                    dbg_mc6809_format_signed8_hex((int8_t)extra1, off_buf, sizeof(off_buf));")
        lines.append('                    (void)snprintf(out, out_sz, (indirect ? "[%s,%s]" : "%s,%s"), off_buf, r);')
        lines.append("                } else {")
        lines.append('                    (void)snprintf(out, out_sz, (indirect ? "[n,%s]" : "n,%s"), r);')
        lines.append("                }")
        lines.append("                return;")
        lines.append("            case 0x09u:")
        lines.append("                if (have_extra1 != 0u && have_extra2 != 0u) {")
        lines.append("                    int16_t off16 = (int16_t)((uint16_t)(((uint16_t)extra1 << 8) | (uint16_t)extra2));")
        lines.append("                    dbg_mc6809_format_signed16_hex(off16, off_buf, sizeof(off_buf));")
        lines.append('                    (void)snprintf(out, out_sz, (indirect ? "[%s,%s]" : "%s,%s"), off_buf, r);')
        lines.append("                } else {")
        lines.append('                    (void)snprintf(out, out_sz, (indirect ? "[nn,%s]" : "nn,%s"), r);')
        lines.append("                }")
        lines.append("                return;")
        lines.append("            case 0x0Bu: (void)snprintf(out, out_sz, (indirect ? \"[D,%s]\" : \"D,%s\"), r); return;")
        lines.append("            case 0x0Cu:")
        lines.append("                if (have_extra1 != 0u) {")
        lines.append("                    int8_t off8 = (int8_t)extra1;")
        lines.append("                    uint16_t abs = (uint16_t)(pc_after_pb + (int16_t)off8);")
        lines.append("                    dbg_mc6809_format_signed8_hex(off8, off_buf, sizeof(off_buf));")
        lines.append("                    (void)abs;")
        lines.append('                    (void)snprintf(out, out_sz, (indirect ? "[%s,PCR]" : "%s,PCR"), off_buf);')
        lines.append("                } else {")
        lines.append('                    (void)snprintf(out, out_sz, "%s", (indirect ? "[n,PCR]" : "n,PCR"));')
        lines.append("                }")
        lines.append("                return;")
        lines.append("            case 0x0Du:")
        lines.append("                if (have_extra1 != 0u && have_extra2 != 0u) {")
        lines.append("                    int16_t off16 = (int16_t)((uint16_t)(((uint16_t)extra1 << 8) | (uint16_t)extra2));")
        lines.append("                    uint16_t abs = (uint16_t)(pc_after_pb + 2u + off16);")
        lines.append("                    dbg_mc6809_format_signed16_hex(off16, off_buf, sizeof(off_buf));")
        lines.append("                    (void)abs;")
        lines.append('                    (void)snprintf(out, out_sz, (indirect ? "[%s,PCR]" : "%s,PCR"), off_buf);')
        lines.append("                } else {")
        lines.append('                    (void)snprintf(out, out_sz, "%s", (indirect ? "[nn,PCR]" : "nn,PCR"));')
        lines.append("                }")
        lines.append("                return;")
        lines.append("            case 0x0Fu:")
        lines.append("                if (have_extra1 != 0u && have_extra2 != 0u) {")
        lines.append("                    uint16_t ea = (uint16_t)(((uint16_t)extra1 << 8) | (uint16_t)extra2);")
        lines.append('                    (void)snprintf(out, out_sz, (indirect ? "[$%04X]" : "$%04X"), (unsigned int)ea);')
        lines.append("                } else {")
        lines.append('                    (void)snprintf(out, out_sz, "%s", (indirect ? "[nn]" : "nn"));')
        lines.append("                }")
        lines.append("                return;")
        lines.append("            default: break;")
        lines.append("        }")
        lines.append("    }")
        lines.append('    (void)snprintf(out, out_sz, "[idx $%02X]", (unsigned int)pb);')
        lines.append("}")
        lines.append("")
    lines.append(
        f"char *{cpu_prefix}_disassemble_instruction(uint16_t pc, uint32_t raw) {{"
    )
    lines.append("    static char buf[160];")
    lines.append("    char rendered[160];")
    lines.append("    (void)rendered;")
    lines.append("    uint8_t prefix = 0;")
    lines.append("    uint32_t decode_raw = raw;")
    lines.append("    uint8_t b0 = (uint8_t)(raw & 0xFF);")
    if explicit_prefixes:
        prefix_cond = " || ".join(f"b0 == 0x{value:02X}" for value in explicit_prefixes)
        lines.append(f"    if ({prefix_cond}) {{")
        lines.append("        prefix = b0;")
        lines.append("        decode_raw = (raw >> 8);")
        lines.append("    }")
    lines.append("")
    lines.append(
        f"    DecodedInstruction inst = {cpu_prefix}_decode(decode_raw, prefix, pc);"
    )
    lines.append('    const char *mnemonic = "UNKNOWN";')
    lines.append("    if (inst.valid) {")
    lines.append("        switch (inst.category) {")
    for cat, insts in categories.items():
        lines.append(f"            case CAT_{cat.upper()}:")
        for inst in insts:
            name = inst.get("name", "UNKNOWN")
            render_inst = inst
            inferred_template = _infer_display_template(inst, immediate_style=numeric_style)
            if inferred_template:
                render_inst = dict(inst)
                render_inst["display_template"] = inferred_template
            lines.append(f"                if ({_dispatch_condition(inst)}) {{")
            if render_inst.get("display_template"):
                _append_instruction_template_render(
                    lines,
                    render_inst,
                    numeric_style=numeric_style,
                    numeric_formats=numeric_formats,
                    allowed_kinds=allowed_display_kinds,
                    indent="                    ",
                )
            else:
                display = _escape_c_string(inst.get("display", name))
                lines.append(f'                    mnemonic = "{display}";')
            lines.append("                    break;")
            lines.append("                }")
        lines.append("                break;")
    lines.append("            default:")
    lines.append("                break;")
    lines.append("        }")
    lines.append("    }")
    lines.append("")
    lines.append(
        '    (void)snprintf(buf, sizeof(buf), "%s OP=%02X PREF=%02X LEN=%u CYC=%u r=%u imm=%u addr=0x%04X disp=%d cc=%u",'
    )
    lines.append("                   mnemonic,")
    lines.append("                   inst.opcode,")
    lines.append("                   inst.prefix,")
    lines.append("                   (unsigned int)inst.length,")
    lines.append("                   (unsigned int)inst.cycles,")
    lines.append("                   (unsigned int)inst.r,")
    lines.append("                   (unsigned int)inst.imm,")
    lines.append("                   (unsigned int)inst.addr,")
    lines.append("                   (int)inst.disp,")
    lines.append("                   (unsigned int)inst.cc);")
    lines.append("    return buf;")
    lines.append("}")
    lines.append("")

    lines.append("static FILE *cpu_trace_file(void) {")
    lines.append("    static FILE *fp = NULL;")
    lines.append("    if (fp == NULL) {")
    lines.append('        const char *path = getenv("PASM_TRACE_FILE");')
    lines.append('        if (path && path[0]) { fp = fopen(path, "w"); }')
    lines.append("        if (fp == NULL) { fp = stdout; }")
    lines.append("    }")
    lines.append("    return fp;")
    lines.append("}")
    lines.append("")

    lines.append(
        f"void {cpu_prefix}_trace_instruction(CPUState *cpu, DecodedInstruction *inst) {{"
    )
    lines.append("    if (!inst) return;")
    lines.append("    uint32_t raw_for_disasm = inst->raw;")
    lines.append("    if (inst->prefix != 0) {")
    lines.append("        raw_for_disasm = ((uint32_t)inst->prefix) | (inst->raw << 8);")
    lines.append("    }")
    lines.append("")

    # Collect registers for trace
    registers = isa_data.get("registers", [])
    trace_fmt = "[TRACE] PC:0x%04X  %-20s"
    trace_args = ["inst->pc", f"{cpu_prefix}_disassemble_instruction(inst->pc, raw_for_disasm)"]

    for reg in registers:
        name = reg.get("name", "").upper()
        c_name = name.replace("'", "_PRIME")
        reg_type = reg.get("type", "general")
        bits = int(reg.get("bits", 8))
        fmt_width = bits // 4
        if fmt_width == 0: fmt_width = 2

        if reg_type == "program_counter":
            continue

        trace_fmt += f" {name}:0x%0{fmt_width}X"
        if reg_type == "stack_pointer":
            trace_args.append("cpu->sp")
        elif reg_type in ("index", "special"):
            trace_args.append(f"cpu->{name.lower()}")
        else:
            trace_args.append(f"cpu->registers[REG_{c_name}]")

    if isa_data.get("flags"):
        trace_fmt += " P:0x%02X"
        trace_args.append("cpu->flags.raw")

    lines.append("    FILE *fp = cpu_trace_file();")
    lines.append(f'    fprintf(fp, "{trace_fmt}\\n",')
    for i, arg in enumerate(trace_args):
        comma = "," if i < len(trace_args) - 1 else ");"
        lines.append(f"            {arg}{comma}")
    lines.append("    fflush(fp);")
    lines.append("}")

    return "\n".join(lines)


def _generate_interrupt_reset(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate interrupt reset block based on interrupt model."""
    snippets = (isa_data.get("interrupts", {}) or {}).get("reset")
    if isinstance(snippets, list):
        lines = [
            str(snippet).replace("{cpu_prefix}", cpu_prefix).rstrip()
            for snippet in snippets
            if str(snippet).strip()
        ]
        return "\n".join(lines) if lines else "    /* Interrupt model: none */"

    model = resolve_interrupt_model(isa_data)

    if model == "none":
        return "    /* Interrupt model: none */"

    lines: List[str] = []
    if model == "z80":
        lines.append("    cpu->interrupt_mode = 0;")

    lines.extend(["    cpu->interrupt_vector = 0;"])
    if model == "mos6502":
        # Keep the 6502 family reset baseline consistent with existing opcode
        # behavior references (unused/status bit 2 set).
        lines.append("    cpu->sp = 0xFDu;")
        lines.append("    cpu->flags.raw = 0x04u;")
    if model == "mc6809":
        # MC6809 RESET masks both IRQ (I) and FIRQ (F).
        lines.append("    cpu->flags.I = true;")
        lines.append("    cpu->flags.F = true;")
    lines.extend(
        [
            "    cpu->interrupts_enabled = false;",
            "    cpu->interrupt_pending = false;",
        ]
    )
    if model == "mos6502":
        lines.append("    cpu->irq_pending = false;")
        lines.append("    cpu->nmi_pending = false;")
    return "\n".join(lines)


def _generate_interrupt_reset_post(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate reset assignments that must happen after component reset."""
    snippets = (isa_data.get("interrupts", {}) or {}).get("reset_post")
    if isinstance(snippets, list):
        return "\n".join(
            str(snippet).replace("{cpu_prefix}", cpu_prefix).rstrip()
            for snippet in snippets
            if str(snippet).strip()
        )

    model = resolve_interrupt_model(isa_data)
    if model == "mos6502":
        return f"    cpu->pc = {cpu_prefix}_read_word(cpu, 0xFFFCu);"
    return ""


def _generate_register_field_reset(isa_data: Dict[str, Any]) -> str:
    """Generate reset assignments for dedicated register struct fields."""
    registers = isa_data.get("registers", [])
    lines: List[str] = []
    seen: Set[str] = set()
    for reg in registers:
        reg_type = str(reg.get("type", "general"))
        if reg_type not in {"index", "special"}:
            continue
        field = _to_c_ident(str(reg.get("name", "")))
        if not field or field in {"pc", "sp"} or field in seen:
            continue
        seen.add(field)
        lines.append(f"    cpu->{field} = 0;")
    if not lines:
        return "    /* No dedicated register fields */"
    return "\n".join(lines)


def _generate_shadow_flags_reset(isa_data: Dict[str, Any]) -> str:
    """Generate optional shadow-flag reset for architectures with A' shadow bank."""
    registers = isa_data.get("registers", [])
    register_names = {reg.get("name", "").upper() for reg in registers}
    has_flags = bool(isa_data.get("flags", []))
    if has_flags and "A_PRIME" in register_names:
        return "    cpu->flags_prime.raw = 0;"
    return "    /* No shadow flag bank */"


def _generate_interrupt_impl(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate interrupt API implementation based on interrupt model."""
    impl = (isa_data.get("interrupts", {}) or {}).get("api_impl")
    if isinstance(impl, str) and impl.strip():
        return impl.replace("{cpu_prefix}", cpu_prefix).strip()

    model = resolve_interrupt_model(isa_data)
    lines: List[str] = []

    if model == "none":
        lines.append(f"void {cpu_prefix}_interrupt(CPUState *cpu, uint8_t vector) {{")
        lines.append("    (void)cpu;")
        lines.append("    (void)vector;")
        lines.append("}")
        lines.append("")
        lines.append(f"void {cpu_prefix}_set_irq(CPUState *cpu, bool enabled) {{")
        lines.append("    (void)cpu;")
        lines.append("    (void)enabled;")
        lines.append("}")
        return "\n".join(lines)

    lines.append(f"void {cpu_prefix}_interrupt(CPUState *cpu, uint8_t vector) {{")
    if model == "mos6502":
        lines.append("    cpu->interrupt_vector = vector;")
        lines.append("    if (vector == 0xFFu) {")
        lines.append("        cpu->nmi_pending = true;")
        lines.append("    } else {")
        lines.append("        cpu->irq_pending = true;")
        lines.append("    }")
        lines.append("    cpu->interrupt_pending = (bool)(cpu->nmi_pending || cpu->irq_pending);")
    else:
        lines.append("    cpu->interrupt_vector = vector;")
        lines.append("    cpu->interrupt_pending = true;")
    lines.append("}")
    lines.append("")

    if model == "z80":
        lines.append(f"void {cpu_prefix}_set_interrupt_mode(CPUState *cpu, uint8_t mode) {{")
        lines.append("    cpu->interrupt_mode = mode;")
        lines.append("}")
        lines.append("")

    lines.append(f"void {cpu_prefix}_set_irq(CPUState *cpu, bool enabled) {{")
    lines.append("    cpu->interrupts_enabled = enabled;")
    lines.append("}")

    return "\n".join(lines)


def _append_switch_dispatch(
    lines: List[str], categories: Dict[str, List[Dict[str, Any]]]
) -> None:
    """Append switch-based instruction dispatch."""
    lines.append("    switch (inst.category) {")

    for cat, insts in categories.items():
        lines.append(f"        case CAT_{cat.upper()}:")
        for inst in insts:
            name = inst.get("name", "UNKNOWN")
            lines.append(f"            if ({_dispatch_condition(inst)}) {{")
            lines.append(f"                inst_{name}(cpu, &inst);")
            lines.append("                executed = true;")
            lines.append("                break;")
            lines.append("            }")
        lines.append("            break;")

    lines.append("        default:")
    lines.append("            break;")
    lines.append("    }")


def _flatten_instruction_map(
    categories: Dict[str, List[Dict[str, Any]]]
) -> List[Tuple[str, Dict[str, Any]]]:
    flat: List[Tuple[str, Dict[str, Any]]] = []
    for cat, insts in categories.items():
        for inst in insts:
            flat.append((cat, inst))
    return flat


def _append_threaded_dispatch(
    lines: List[str], categories: Dict[str, List[Dict[str, Any]]]
) -> None:
    """Append threaded dispatch using GCC/Clang computed goto."""
    flat = _flatten_instruction_map(categories)

    lines.append("    int dispatch_id = -1;")
    for idx, (cat, inst) in enumerate(flat):
        prefix = "if" if idx == 0 else "else if"
        cond = _dispatch_condition(inst)
        lines.append(
            f"    {prefix} (inst.category == CAT_{cat.upper()} && ({cond})) dispatch_id = {idx};"
        )
    lines.append("")
    lines.append("    if (dispatch_id >= 0) {")
    lines.append("        static void *dispatch_table[] = {")
    for idx, _ in enumerate(flat):
        lines.append(f"            &&DISPATCH_{idx},")
    lines.append("        };")
    lines.append("        goto *dispatch_table[dispatch_id];")
    lines.append("    }")
    lines.append("")

    for idx, (_, inst) in enumerate(flat):
        name = inst.get("name", "UNKNOWN")
        lines.append(f"DISPATCH_{idx}:")
        lines.append(f"    inst_{name}(cpu, &inst);")
        lines.append("    executed = true;")
        lines.append("    goto dispatch_done;")
        lines.append("")

    lines.append("dispatch_done: ;")


def _generate_dispatch(
    isa_data: Dict[str, Any], cpu_prefix: str, dispatch_mode: str = "switch"
) -> str:
    """Generate the main dispatch loop."""
    lines: List[str] = []

    instructions = isa_data.get("instructions", [])
    hooks = isa_data.get("hooks", {})
    undefined_policy = (
        str(
            isa_data.get("metadata", {}).get("undefined_opcode_policy", "trap")
        ).strip().lower()
        or "trap"
    )
    if undefined_policy not in {"trap", "nop"}:
        raise ValueError(
            "Unsupported metadata.undefined_opcode_policy: "
            f"{undefined_policy}. Expected one of ['nop', 'trap']."
        )
    has_interrupts = "interrupts" in isa_data
    has_components = bool(
        isa_data.get("ics")
        or isa_data.get("devices")
        or isa_data.get("hosts")
        or isa_data.get("cartridge")
    )
    has_runtime_cartridge = bool(isa_data.get("cartridge"))
    interrupt_model = resolve_interrupt_model(isa_data) if has_interrupts else "none"
    interrupt_modes = configured_interrupt_modes(isa_data)
    if not interrupt_modes:
        interrupt_modes = [1]
    default_interrupt_mode = interrupt_modes[0]
    interrupts_config = isa_data.get("interrupts", {})
    dispatch_config = (
        interrupts_config.get("dispatch", {}) if isinstance(interrupts_config.get("dispatch"), dict) else {}
    )
    interrupt_dispatch_kind = str(dispatch_config.get("kind", interrupt_model)).strip()
    fixed_vector = int(interrupts_config.get("fixed_vector", 0x0038))
    register_names = {
        register.get("name", "").upper() for register in isa_data.get("registers", [])
    }
    has_bank_exec = "BANK_EXEC" in register_names
    fetch_fn = "cpu_fetch_byte" if has_bank_exec else f"{cpu_prefix}_read_byte"
    flag_names = {flag.get("name", "").upper() for flag in isa_data.get("flags", [])}
    has_interrupt_i_register = "I" in register_names
    has_flag_i = "I" in flag_names
    has_flag_b = "B" in flag_names
    has_flag_f = "F" in flag_names
    has_flag_e = "E" in flag_names
    # Group instructions by category for efficient dispatch
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for inst in instructions:
        cat = inst.get("category", "misc")
        categories.setdefault(cat, []).append(inst)

    prefix_values = sorted(
        {
            int(inst.get("encoding", {}).get("prefix"))
            for inst in instructions
            if "prefix" in inst.get("encoding", {})
        }
    )

    lines.append(f"int {cpu_prefix}_step(CPUState *cpu) {{")
    lines.append("    if (!cpu->running) return 0;")
    lines.append("")
    if has_components:
        lines.append("    if (cpu_components_runtime_pre_step(cpu) != 0) {")
        lines.append("        return 0;")
        lines.append("    }")
        lines.append("")

    lines.append("    if (cpu_check_breakpoints(cpu)) {")
    lines.append("        cpu->running = false;")
    lines.append("        return 0;")
    lines.append("    }")
    lines.append("")
    if has_interrupts and interrupt_dispatch_kind != "none":
        if interrupt_dispatch_kind == "mos6502":
            lines.append(
                "    if (cpu->nmi_pending || (cpu->irq_pending && cpu->interrupts_enabled)) {"
            )
            lines.append("        uint8_t irq_vector = cpu->nmi_pending ? 0xFFu : 0x00u;")
            lines.append("        if (cpu->nmi_pending) cpu->nmi_pending = false; else cpu->irq_pending = false;")
            lines.append("        cpu->interrupt_pending = (bool)(cpu->nmi_pending || cpu->irq_pending);")
            lines.append("        cpu->halted = false;")
            lines.append("        {")
            lines.append("            uint8_t sp8 = (uint8_t)cpu->sp;")
            lines.append("            uint16_t ret_pc = cpu->pc;")
            lines.append(
                f"            {cpu_prefix}_write_byte(cpu, (uint16_t)(0x0100u | sp8), (uint8_t)((ret_pc >> 8) & 0xFFu));"
            )
            lines.append("            sp8 = (uint8_t)(sp8 - 1u);")
            lines.append(
                f"            {cpu_prefix}_write_byte(cpu, (uint16_t)(0x0100u | sp8), (uint8_t)(ret_pc & 0xFFu));"
            )
            lines.append("            sp8 = (uint8_t)(sp8 - 1u);")
            lines.append("            {")
            lines.append("                uint8_t p = cpu->flags.raw;")
            if has_flag_b:
                lines.append("                p = (uint8_t)(p & (uint8_t)~FLAG_B);")
            lines.append("                p = (uint8_t)(p | 0x20u);")
            lines.append(
                f"                {cpu_prefix}_write_byte(cpu, (uint16_t)(0x0100u | sp8), p);"
            )
            lines.append("            }")
            lines.append("            sp8 = (uint8_t)(sp8 - 1u);")
            lines.append("            cpu->sp = sp8;")
            lines.append("        }")
            if has_flag_i:
                lines.append("        cpu->flags.I = true;")
            lines.append("        cpu->interrupts_enabled = false;")
            lines.append(
                f"        cpu->pc = (irq_vector == 0xFFu) ? {cpu_prefix}_read_word(cpu, 0xFFFAu) : {cpu_prefix}_read_word(cpu, 0xFFFEu);"
            )
            lines.append("        cpu->total_cycles += 7u;")
            lines.append("        return 0;")
            lines.append("    }")
            lines.append("")
        elif interrupt_dispatch_kind == "mc6809":
            lines.append("    if (cpu->interrupt_pending) {")
            lines.append("        uint8_t irq_kind = cpu->interrupt_vector;")
            lines.append("        bool take_interrupt = false;")
            lines.append("        if (irq_kind == 0x01u) {")
            lines.append("            /* NMI */")
            lines.append("            take_interrupt = true;")
            lines.append("        } else if (irq_kind == 0x02u) {")
            if has_flag_f:
                lines.append("            /* FIRQ masked by F flag */")
                lines.append("            take_interrupt = (cpu->flags.F == 0u);")
            else:
                lines.append("            take_interrupt = true;")
            lines.append("        } else {")
            if has_flag_i:
                lines.append("            /* IRQ masked by I flag */")
                lines.append("            take_interrupt = (cpu->flags.I == 0u);")
            else:
                lines.append("            take_interrupt = cpu->interrupts_enabled;")
            lines.append("        }")
            lines.append("        if (take_interrupt) {")
            lines.append("            uint16_t vector_addr = 0xFFF8u;")
            lines.append("            uint8_t irq_cycles = 19u;")
            lines.append("            cpu->interrupt_pending = false;")
            lines.append("            cpu->halted = false;")
            lines.append("            bool full_frame = true;")
            lines.append("            if (irq_kind == 0x01u) {")
            lines.append("                vector_addr = 0xFFFCu;")
            lines.append("                irq_cycles = 19u;")
            lines.append("            } else if (irq_kind == 0x02u) {")
            lines.append("                vector_addr = 0xFFF6u;")
            lines.append("                irq_cycles = 10u;")
            lines.append("                full_frame = false;")
            lines.append("            }")
            lines.append("            {")
            lines.append("                uint16_t sp = cpu->sp;")
            if has_flag_e:
                lines.append("                if (full_frame) {")
                lines.append("                    cpu->flags.E = true;")
                lines.append("                } else {")
                lines.append("                    cpu->flags.E = false;")
                lines.append("                }")
            lines.append("                sp = (uint16_t)(sp - 1u);")
            lines.append(
                f"                {cpu_prefix}_write_byte(cpu, sp, (uint8_t)(cpu->pc & 0xFFu));"
            )
            lines.append("                sp = (uint16_t)(sp - 1u);")
            lines.append(
                f"                {cpu_prefix}_write_byte(cpu, sp, (uint8_t)((cpu->pc >> 8) & 0xFFu));"
            )
            lines.append("                if (full_frame) {")
            lines.append("                    sp = (uint16_t)(sp - 1u);")
            lines.append(
                f"                    {cpu_prefix}_write_byte(cpu, sp, (uint8_t)(cpu->u & 0xFFu));"
            )
            lines.append("                    sp = (uint16_t)(sp - 1u);")
            lines.append(
                f"                    {cpu_prefix}_write_byte(cpu, sp, (uint8_t)((cpu->u >> 8) & 0xFFu));"
            )
            lines.append("                    sp = (uint16_t)(sp - 1u);")
            lines.append(
                f"                    {cpu_prefix}_write_byte(cpu, sp, (uint8_t)(cpu->y & 0xFFu));"
            )
            lines.append("                    sp = (uint16_t)(sp - 1u);")
            lines.append(
                f"                    {cpu_prefix}_write_byte(cpu, sp, (uint8_t)((cpu->y >> 8) & 0xFFu));"
            )
            lines.append("                    sp = (uint16_t)(sp - 1u);")
            lines.append(
                f"                    {cpu_prefix}_write_byte(cpu, sp, (uint8_t)(cpu->x & 0xFFu));"
            )
            lines.append("                    sp = (uint16_t)(sp - 1u);")
            lines.append(
                f"                    {cpu_prefix}_write_byte(cpu, sp, (uint8_t)((cpu->x >> 8) & 0xFFu));"
            )
            lines.append("                    sp = (uint16_t)(sp - 1u);")
            lines.append(
                f"                    {cpu_prefix}_write_byte(cpu, sp, cpu->registers[REG_DP]);"
            )
            lines.append("                    sp = (uint16_t)(sp - 1u);")
            lines.append(
                f"                    {cpu_prefix}_write_byte(cpu, sp, cpu->registers[REG_B]);"
            )
            lines.append("                    sp = (uint16_t)(sp - 1u);")
            lines.append(
                f"                    {cpu_prefix}_write_byte(cpu, sp, cpu->registers[REG_A]);"
            )
            lines.append("                }")
            lines.append("                sp = (uint16_t)(sp - 1u);")
            lines.append(f"                {cpu_prefix}_write_byte(cpu, sp, cpu->flags.raw);")
            lines.append("                cpu->sp = sp;")
            lines.append("            }")
            if has_flag_i:
                lines.append("            cpu->flags.I = true;")
            if has_flag_f:
                lines.append("            if (irq_kind == 0x02u || irq_kind == 0x01u) cpu->flags.F = true;")
            lines.append("            cpu->interrupts_enabled = false;")
            lines.append(f"            cpu->pc = {cpu_prefix}_read_word(cpu, vector_addr);")
            lines.append("            cpu->total_cycles += irq_cycles;")
            lines.append("            return 0;")
            lines.append("        }")
            lines.append("    }")
            lines.append("")
        else:
            lines.append("    if (cpu->interrupt_pending && cpu->interrupts_enabled) {")
            lines.append("        cpu->interrupt_pending = false;")
            lines.append("        cpu->halted = false;")
            lines.append("        cpu->interrupts_enabled = false;")
            lines.append("        uint8_t irq_cycles = 13;")
            lines.append("        cpu->sp--;")
            lines.append(
                f"        {cpu_prefix}_write_byte(cpu, cpu->sp, (uint8_t)((cpu->pc >> 8) & 0xFF));"
            )
            lines.append("        cpu->sp--;")
            lines.append(
                f"        {cpu_prefix}_write_byte(cpu, cpu->sp, (uint8_t)(cpu->pc & 0xFF));"
            )
            if interrupt_dispatch_kind == "fixed_vector":
                lines.append(f"        cpu->pc = 0x{fixed_vector & 0xFFFF:04X};")
            elif interrupt_dispatch_kind == "z80":
                lines.append("        uint8_t irq_mode = cpu->interrupt_mode;")
                guard_cond = " && ".join(
                    f"irq_mode != {interrupt_mode}" for interrupt_mode in interrupt_modes
                )
                lines.append(f"        if ({guard_cond}) irq_mode = {default_interrupt_mode};")
                lines.append("        switch (irq_mode) {")
                for interrupt_mode in interrupt_modes:
                    lines.append(f"            case {interrupt_mode}:")
                    if interrupt_mode == 0:
                        lines.append("                {")
                        lines.append("                    uint8_t vector_opcode = cpu->interrupt_vector;")
                        lines.append("                    if ((vector_opcode & 0xC7) == 0xC7) {")
                        lines.append("                        cpu->pc = (uint16_t)(vector_opcode & 0x38);")
                        lines.append("                    } else {")
                        lines.append("                        cpu->pc = 0x0038;")
                        lines.append("                    }")
                        lines.append("                }")
                    elif interrupt_mode == 1:
                        lines.append("                cpu->pc = 0x0038;")
                    elif interrupt_mode == 2:
                        if has_interrupt_i_register:
                            lines.append(
                                "                uint16_t vector_addr = (uint16_t)(((uint16_t)cpu->registers[REG_I] << 8) | cpu->interrupt_vector);"
                            )
                            lines.append(
                                f"                cpu->pc = {cpu_prefix}_read_word(cpu, vector_addr);"
                            )
                        else:
                            lines.append(
                                "                cpu->pc = ((uint16_t)cpu->interrupt_vector) << 8;"
                            )
                        lines.append("                irq_cycles = 19;")
                    lines.append("                break;")
                lines.append("            default:")
                lines.append("                cpu->pc = 0x0038;")
                lines.append("                break;")
                lines.append("        }")
            else:
                raise ValueError(
                    f"Unsupported interrupts.model/dispatch.kind for generation: {interrupt_dispatch_kind}"
                )
            lines.append("        cpu->total_cycles += irq_cycles;")
            lines.append("        return 0;")
            lines.append("    }")
            lines.append("")

    lines.append("    if (cpu->halted) {")
    lines.append("        uint16_t halted_pc = cpu->pc;")
    lines.append("        DecodedInstruction halted_inst = {0};")
    lines.append("        halted_inst.pc = halted_pc;")
    lines.append("        halted_inst.cycles = 4;")
    if has_components:
        lines.append("        cpu_components_step_post(cpu, &halted_inst, halted_pc);")
    lines.append("        cpu->total_cycles += halted_inst.cycles;")
    lines.append("        return 0;")
    lines.append("    }")
    lines.append("")
    lines.append("    uint16_t pc_before = cpu->pc;")
    lines.append("    uint8_t prefix = 0;")
    lines.append("    uint32_t raw = 0;")
    lines.append(f"    uint8_t b0 = {fetch_fn}(cpu, pc_before);")
    lines.append("")

    if prefix_values:
        prefix_cond = " || ".join(f"b0 == 0x{value:02X}" for value in prefix_values)
        lines.append(f"    if ({prefix_cond}) {{")
        lines.append("        prefix = b0;")
        lines.append(f"        raw = {fetch_fn}(cpu, (uint16_t)(pc_before + 1));")
        lines.append(
            f"        raw |= ((uint32_t){fetch_fn}(cpu, (uint16_t)(pc_before + 2))) << 8;"
        )
        lines.append(
            f"        raw |= ((uint32_t){fetch_fn}(cpu, (uint16_t)(pc_before + 3))) << 16;"
        )
        lines.append("    } else {")
        lines.append("        raw = b0;")
        lines.append(
            f"        raw |= ((uint32_t){fetch_fn}(cpu, (uint16_t)(pc_before + 1))) << 8;"
        )
        lines.append(
            f"        raw |= ((uint32_t){fetch_fn}(cpu, (uint16_t)(pc_before + 2))) << 16;"
        )
        lines.append(
            f"        raw |= ((uint32_t){fetch_fn}(cpu, (uint16_t)(pc_before + 3))) << 24;"
        )
        lines.append("    }")
    else:
        lines.append("    raw = b0;")
        lines.append(
            f"    raw |= ((uint32_t){fetch_fn}(cpu, (uint16_t)(pc_before + 1))) << 8;"
        )
        lines.append(
            f"    raw |= ((uint32_t){fetch_fn}(cpu, (uint16_t)(pc_before + 2))) << 16;"
        )
        lines.append(
            f"    raw |= ((uint32_t){fetch_fn}(cpu, (uint16_t)(pc_before + 3))) << 24;"
        )
    lines.append("")
    lines.append("    cpu->hook_pc = pc_before;")
    lines.append("    cpu->hook_prefix = prefix;")
    lines.append("    cpu->hook_opcode = (uint8_t)(raw & 0xFF);")
    lines.append("    cpu->hook_raw = raw;")
    lines.append("")

    if hooks.get("pre_fetch", {}).get("enabled"):
        lines.append(
            "    if (cpu->hooks[HOOK_PRE_FETCH].enabled && cpu->hooks[HOOK_PRE_FETCH].func) {"
        )
        lines.append(
            "        CPUHookEvent event = {"
        )
        lines.append("            .type = HOOK_PRE_FETCH,")
        lines.append("            .pc = pc_before,")
        lines.append("            .prefix = 0,")
        lines.append("            .opcode = b0,")
        lines.append("            .port = 0,")
        lines.append("            .value = 0,")
        lines.append("            .raw = raw,")
        lines.append("        };")
        lines.append(
            "        cpu->hooks[HOOK_PRE_FETCH].func(cpu, &event, cpu->hooks[HOOK_PRE_FETCH].context);"
        )
        lines.append("    }")
        lines.append("")

    lines.append(
        f"    DecodedInstruction inst = {cpu_prefix}_decode(raw, prefix, pc_before);"
    )
    lines.append("")
    lines.append("    cpu->hook_pc = inst.pc;")
    lines.append("    cpu->hook_prefix = inst.prefix;")
    lines.append("    cpu->hook_opcode = inst.opcode;")
    lines.append("    cpu->hook_raw = inst.raw;")
    lines.append("")

    if hooks.get("post_decode", {}).get("enabled"):
        lines.append(
            "    if (cpu->hooks[HOOK_POST_DECODE].enabled && cpu->hooks[HOOK_POST_DECODE].func) {"
        )
        lines.append("        CPUHookEvent event = {")
        lines.append("            .type = HOOK_POST_DECODE,")
        lines.append("            .pc = inst.pc,")
        lines.append("            .prefix = inst.prefix,")
        lines.append("            .opcode = inst.opcode,")
        lines.append("            .port = 0,")
        lines.append("            .value = 0,")
        lines.append("            .raw = inst.raw,")
        lines.append("        };")
        lines.append(
            "        cpu->hooks[HOOK_POST_DECODE].func(cpu, &event, cpu->hooks[HOOK_POST_DECODE].context);"
        )
        lines.append("    }")
        lines.append("")

    lines.append("    if (!inst.valid) {")
    if undefined_policy == "nop":
        lines.append("        cpu->pc = (uint16_t)(pc_before + inst.length);")
        lines.append("        cpu->total_cycles += inst.cycles;")
        lines.append("        return 0;")
    else:
        lines.append("        cpu->running = false;")
        lines.append("        cpu->error_code = CPU_ERROR_INVALID_OPCODE;")
        lines.append(
            '        fprintf(stderr, "KIL instruction at 0x%04X: 0x%02X\\n", pc_before, b0);'
        )
        lines.append("        return -1;")
    lines.append("    }")
    if (cpu_prefix == 'mos6502'):
        lines.append('    if (cpu->tracing_enabled) { mos6502_trace_instruction(cpu, &inst); }')
    lines.append("")
    lines.append("")
    if interrupt_dispatch_kind == "mos6502":
        lines.append("    uint8_t x_before = cpu->registers[REG_X];")
        lines.append("    uint8_t y_before = cpu->registers[REG_Y];")
        lines.append("    uint8_t c_before = cpu->flags.C ? 1u : 0u;")
        lines.append("    uint8_t z_before = cpu->flags.Z ? 1u : 0u;")
        lines.append("    uint8_t n_before = cpu->flags.N ? 1u : 0u;")
        lines.append("    uint8_t v_before = cpu->flags.V ? 1u : 0u;")
        lines.append("")
    lines.append("    bool executed = false;")
    lines.append("    cpu->pc_modified = false;")
    lines.append("    cpu->current_instruction_cycles = inst.cycles;")
    lines.append("    cpu->io_read_phase_ppu_dots = (uint16_t)((uint16_t)inst.cycles * 6u);")
    if has_components:
        lines.append("    cpu_components_step_pre(cpu, &inst, pc_before);")
    if dispatch_mode == "switch":
        _append_switch_dispatch(lines, categories)
    elif dispatch_mode == "threaded":
        lines.append("#if defined(__GNUC__) || defined(__clang__)")
        _append_threaded_dispatch(lines, categories)
        lines.append("#else")
        _append_switch_dispatch(lines, categories)
        lines.append("#endif")
    elif dispatch_mode == "both":
        lines.append(
            "#if defined(CPU_USE_THREADED_DISPATCH) && (defined(__GNUC__) || defined(__clang__))"
        )
        _append_threaded_dispatch(lines, categories)
        lines.append("#else")
        _append_switch_dispatch(lines, categories)
        lines.append("#endif")
    else:
        raise ValueError(f"Unknown dispatch mode: {dispatch_mode}")
    lines.append("")
    lines.append("    if (!executed) {")
    lines.append(
        '        fprintf(stderr, "Unimplemented: category=%d opcode=0x%02X prefix=0x%02X\\n", inst.category, inst.opcode, inst.prefix);'
    )
    lines.append("        cpu->running = false;")
    lines.append("        return -1;")
    lines.append("    }")
    if interrupt_dispatch_kind == "mos6502":
        lines.append("    cpu_apply_mos6502_runtime_cycles(cpu, &inst, pc_before, x_before, y_before, c_before, z_before, n_before, v_before);")
    if has_components:
        lines.append("    if (!cpu->pc_modified) {")
        lines.append("        cpu->pc = (uint16_t)(pc_before + inst.length);")
        lines.append("        cpu->pc_modified = true;")
        lines.append("    }")
        lines.append("    cpu->total_cycles += inst.cycles;")
        lines.append("    cpu_components_step_post(cpu, &inst, pc_before);")
        if interrupt_dispatch_kind == "mos6502":
            lines.append("    /* After step_post, PPU may have signalled NMI - take it immediately. */")
            lines.append("    if (cpu->nmi_pending || (cpu->irq_pending && cpu->interrupts_enabled)) {")
            lines.append("        cpu->current_instruction_cycles = 0u;")
            lines.append("        cpu->io_read_phase_ppu_dots = 0u;")
            lines.append("        return 0;")
            lines.append("    }")
            lines.append("")
    lines.append("    cpu->current_instruction_cycles = 0u;")
    lines.append("    cpu->io_read_phase_ppu_dots = 0u;")
    lines.append("")

    if hooks.get("post_execute", {}).get("enabled"):
        lines.append(
            "    if (cpu->hooks[HOOK_POST_EXECUTE].enabled && cpu->hooks[HOOK_POST_EXECUTE].func) {"
        )
        lines.append("        CPUHookEvent event = {")
        lines.append("            .type = HOOK_POST_EXECUTE,")
        lines.append("            .pc = inst.pc,")
        lines.append("            .prefix = inst.prefix,")
        lines.append("            .opcode = inst.opcode,")
        lines.append("            .port = 0,")
        lines.append("            .value = 0,")
        lines.append("            .raw = inst.raw,")
        lines.append("        };")
        lines.append(
            "        cpu->hooks[HOOK_POST_EXECUTE].func(cpu, &event, cpu->hooks[HOOK_POST_EXECUTE].context);"
        )
        lines.append("    }")
        lines.append("")

    lines.append("    if (cpu->halted && !cpu->pc_modified) {")
    lines.append("        cpu->pc = (uint16_t)(pc_before + inst.length);")
    lines.append("        cpu->pc_modified = true;")
    lines.append("    }")
    lines.append("")
    if not has_components:
        lines.append("    if (!cpu->pc_modified) {")
        lines.append("        cpu->pc = (uint16_t)(pc_before + inst.length);")
        lines.append("    }")
        lines.append("    cpu->total_cycles += inst.cycles;")
    lines.append("")
    lines.append("    return 0;")
    lines.append("}")
    lines.append("")

    lines.append(f"void {cpu_prefix}_run(CPUState *cpu) {{")
    lines.append(f"    {cpu_prefix}_run_until(cpu, 0);")
    lines.append("}")
    lines.append("")

    lines.append(f"void {cpu_prefix}_run_until(CPUState *cpu, uint64_t cycles) {{")
    lines.append("    while (cpu->running) {")
    lines.append("        if (cycles > 0 && cpu->total_cycles >= cycles) break;")
    if interrupt_dispatch_kind == "mos6502":
        lines.append("        if (cpu->halted && !(cpu->nmi_pending || cpu->irq_pending)) break;")
    elif interrupt_dispatch_kind == "none":
        lines.append("        if (cpu->halted) break;")
    else:
        lines.append("        if (cpu->halted && !cpu->interrupt_pending) break;")
    lines.append(f"        if ({cpu_prefix}_step(cpu) != 0) break;")
    lines.append("    }")
    lines.append("}")

    return "\n".join(lines)
