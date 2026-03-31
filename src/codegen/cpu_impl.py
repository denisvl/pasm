"""CPU implementation file generator."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

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
    "G",
    "GRAVE",
    "H",
    "HOME",
    "I",
    "INSERT",
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
    "PAGEUP",
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
    isa_data: Dict[str, Any], cpu_name: str, dispatch_mode: str = "switch"
) -> str:
    """Generate the CPU implementation file."""

    cpu_prefix = cpu_name.lower()

    # Generate helper functions
    helpers_code = _generate_helpers(isa_data, cpu_prefix)
    coding_includes = _generate_coding_includes(isa_data)

    # Generate instruction implementations
    instructions_code = _generate_instructions(isa_data, cpu_prefix)

    # Generate dispatch
    dispatch_code = _generate_dispatch(isa_data, cpu_prefix, dispatch_mode)
    disassembler_code = _generate_disassembler(isa_data, cpu_prefix)
    interrupt_reset = _generate_interrupt_reset(isa_data, cpu_prefix)
    register_field_reset = _generate_register_field_reset(isa_data)
    shadow_flags_reset = _generate_shadow_flags_reset(isa_data)
    interrupt_impl = _generate_interrupt_impl(isa_data, cpu_prefix)
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
    system_rom_loader = _generate_system_rom_loader(isa_data, cpu_prefix)
    cartridge_rom_loader = _generate_cartridge_rom_loader(isa_data, cpu_prefix)
    reset_delay_seconds = max(
        0, int(isa_data.get("system", {}).get("reset_delay_seconds", 0))
    )
    debug_flags_expr = _generate_debug_flags_expr(isa_data)

    hooks_impl = "/* Hook API is emitted in *_hooks.c when enabled. */"

    # Get metadata for template
    isa_name = isa_data.get("metadata", {}).get("name", cpu_name)
    register_count = len(isa_data.get("registers", []))

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
        register_field_reset=register_field_reset,
        shadow_flags_reset=shadow_flags_reset,
        interrupt_impl=interrupt_impl,
        port_read_hook_pre=port_read_hook_pre,
        port_read_hook_post=port_read_hook_post,
        port_write_hook_pre=port_write_hook_pre,
        port_write_hook_post=port_write_hook_post,
        memory_write_guard=memory_write_guard,
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
        hooks_impl=hooks_impl,
        isa_name=isa_name,
        register_count=register_count,
        reset_delay_seconds=reset_delay_seconds,
        debug_flags_expr=debug_flags_expr,
    )


def _generate_debug_flags_expr(isa_data: Dict[str, Any]) -> str:
    """Generate expression used by dump_registers() when printing flags."""
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


def _generate_coding_includes(isa_data: Dict[str, Any]) -> str:
    headers = isa_data.get("coding", {}).get("headers", [])
    backend_target = _single_host_backend_target(isa_data)
    auto_headers: List[str] = []
    if backend_target == "sdl2":
        auto_headers.append("SDL2/SDL.h")
    if not headers and not auto_headers:
        return ""

    lines: List[str] = []
    seen: set[str] = set()
    for header in [*auto_headers, *headers]:
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
        if kind == "hex8":
            if numeric_style == "asm_dollar":
                lines.append(
                    f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "$%02X", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
                )
            elif numeric_style == "z80_h":
                lines.append(
                    f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "%02Xh", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
                )
            else:
                lines.append(
                    f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "0x%02X", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
                )
        elif kind == "hex8_plain":
            lines.append(
                f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "%02X", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
            )
        elif kind == "hex16":
            if numeric_style == "asm_dollar":
                lines.append(
                    f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "$%04X", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
                )
            elif numeric_style == "z80_h":
                lines.append(
                    f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "%04Xh", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
                )
            else:
                lines.append(
                    f'{indent}    (void)snprintf({buf_name}, sizeof({buf_name}), "0x%04X", (unsigned int)(((uint32_t){field_ref}) & 0x{mask:X}u));'
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
    interrupt_model = resolve_interrupt_model(isa_data)

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

    # Cross-platform reset sleep helper.
    lines.append("static void cpu_sleep_seconds(uint32_t seconds) {")
    lines.append("    if (seconds == 0u) return;")
    lines.append("#if defined(_WIN32)")
    lines.append("    Sleep((DWORD)(seconds * 1000u));")
    lines.append("#else")
    lines.append("    unsigned int remaining = (unsigned int)seconds;")
    lines.append("    while (remaining != 0u) remaining = sleep(remaining);")
    lines.append("#endif")
    lines.append("}")
    lines.append("")

    if interrupt_model != "none":
        lines.append("static FILE *cpu_irq_trace_file(void) {")
        lines.append("    static int initialized = -1;")
        lines.append("    static FILE *fp = NULL;")
        lines.append("    if (initialized < 0) {")
        lines.append('        const char *env = getenv("PASM_IRQ_TRACE");')
        lines.append(
            "        initialized = (env != NULL && env[0] != '\\0' && env[0] != '0') ? 1 : 0;"
        )
        lines.append("        if (initialized != 0) {")
        lines.append('            const char *path = getenv("PASM_IRQ_TRACE_FILE");')
        lines.append(
            '            if (path == NULL || path[0] == \'\\0\') path = "pasm_irq_trace.log";'
        )
        lines.append('            fp = fopen(path, "a");')
        lines.append("            if (fp == NULL) initialized = 0;")
        lines.append("        }")
        lines.append("    }")
        lines.append("    return (initialized != 0) ? fp : NULL;")
        lines.append("}")
        lines.append("")
        lines.append(
            "static void cpu_irq_trace(CPUState *cpu, const char *phase, uint8_t vector, uint16_t vector_addr) {"
        )
        lines.append("    FILE *fp = cpu_irq_trace_file();")
        lines.append("    if (fp == NULL || cpu == NULL) return;")
        lines.append(
            '    fprintf(fp, "irq %s cyc=%llu pc=%04X sp=%04X vec=%02X vaddr=%04X pend=%u en=%u flags=%02X\\n",'
        )
        lines.append('            (phase != NULL) ? phase : "?",')
        lines.append("            (unsigned long long)cpu->total_cycles,")
        lines.append("            (unsigned int)(cpu->pc & 0xFFFFu),")
        lines.append("            (unsigned int)(cpu->sp & 0xFFFFu),")
        lines.append("            (unsigned int)vector,")
        lines.append("            (unsigned int)(vector_addr & 0xFFFFu),")
        lines.append("            (unsigned int)(cpu->interrupt_pending ? 1u : 0u),")
        lines.append("            (unsigned int)(cpu->interrupts_enabled ? 1u : 0u),")
        lines.append("            (unsigned int)cpu->flags.raw);")
        lines.append("    fflush(fp);")
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

    # Basic Z80-style condition helper.
    lines.append("static bool cpu_check_condition(CPUState *cpu, uint8_t cc) {")
    lines.append("    switch (cc) {")
    lines.append(f"        case 0: return !({z_expr});")
    lines.append(f"        case 1: return {z_expr};")
    lines.append(f"        case 2: return !({c_expr});")
    lines.append(f"        case 3: return {c_expr};")
    lines.append(f"        case 4: return !({p_expr});")
    lines.append(f"        case 5: return {p_expr};")
    lines.append(f"        case 6: return !({s_expr});")
    lines.append(f"        case 7: return {s_expr};")
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

    if interrupt_model == "mos6502":
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
        )

    comp_id = str(cartridge.get("metadata", {}).get("id", "cartridge"))
    comp_ident = _to_c_ident(comp_id)
    state_names = {str(field.get("name", "")) for field in cartridge.get("state", [])}
    if "rom_data" not in state_names or "rom_size" not in state_names:
        raise ValueError(
            f"Cartridge '{comp_id}' must declare state fields rom_data and rom_size"
        )

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
        "    snprintf(",
        "        cpu->loaded_rom_debug,",
        "        sizeof(cpu->loaded_rom_debug),",
        f"        \"name={_escape_c_string(comp_id)} path=%s\",",
        "        path",
        "    );",
        "    return 0;",
        "}",
    ]
    return "\n".join(lines) + "\n"


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
        "typedef struct {",
        "    const char *from_component;",
        "    const char *from_kind;",
        "    const char *from_name;",
        "    const char *to_component;",
        "    const char *to_kind;",
        "    const char *to_name;",
        "} ComponentConnection;",
        "",
        "static uint64_t cpu_component_call(",
        "    CPUState *cpu,",
        "    const char *source_component,",
        "    const char *callback_name,",
        "    const uint64_t *args,",
        "    uint8_t argc",
        ");",
        "",
        "static void cpu_component_emit_signal(",
        "    CPUState *cpu,",
        "    const char *source_component,",
        "    const char *signal_name,",
        "    const uint64_t *args,",
        "    uint8_t argc",
        ");",
        "",
        "typedef struct {",
        "    uint8_t row;",
        "    uint8_t bit;",
        "} RuntimeKeyboardPress;",
        "",
        "typedef struct {",
        "    int32_t scancode;",
        "    RuntimeKeyboardPress *presses;",
        "    uint8_t press_count;",
        "    uint8_t press_cap;",
        "    uint8_t has_ascii;",
        "    uint8_t has_ascii_shift;",
        "    uint8_t has_ascii_ctrl;",
        "    uint8_t ascii;",
        "    uint8_t ascii_shift;",
        "    uint8_t ascii_ctrl;",
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
        "static int32_t cpu_host_hal_key_from_scancode(int scancode);",
        "",
    ]

    if host_uses_sdl2_backend:
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
                "#define CPU_HOST_AUDIO_ALLOW_FREQUENCY_CHANGE SDL_AUDIO_ALLOW_FREQUENCY_CHANGE",
                "#define CPU_HOST_AUDIO_FORMAT_S16 AUDIO_S16SYS",
                "#define CPU_HOST_SCANCODE(name) SDL_SCANCODE_##name",
                "#define CPU_HOST_HAS_SCANCODE_MAP 1",
                "#define CPU_HOST_KEYCODE_QUOTE ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(APOSTROPHE)))",
                "#define CPU_HOST_KEYCODE_SEMICOLON ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(SEMICOLON)))",
                "#define CPU_HOST_MOD_CTRL KMOD_CTRL",
                "#define CPU_HOST_MOD_SHIFT KMOD_SHIFT",
                "#define CPU_HOST_MOD_LCTRL KMOD_LCTRL",
                "#define cpu_host_hal_log(...) SDL_Log(__VA_ARGS__)",
                "#define cpu_host_hal_last_error() SDL_GetError()",
                "static void cpu_host_audio_spec_zero(CPUHostAudioSpec *spec) {",
                "    if (!spec) return;",
                "    SDL_zero(*spec);",
                "}",
                "",
            ]
        )
    elif host_uses_glfw_backend:
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
                "} CPUHostGlfwRenderer;",
                "typedef struct {",
                "    int w;",
                "    int h;",
                "    uint8_t *pixels;",
                "    size_t pixels_len;",
                "} CPUHostGlfwTexture;",
                "extern int glfwInit(void);",
                "extern void glfwTerminate(void);",
                "extern void glfwPollEvents(void);",
                "extern double glfwGetTime(void);",
                "extern int glfwGetWindowAttrib(GLFWwindow *window, int attrib);",
                "extern int glfwGetKey(GLFWwindow *window, int key);",
                "extern void glfwSetWindowTitle(GLFWwindow *window, const char *title);",
                "extern void glfwDestroyWindow(GLFWwindow *window);",
                "extern GLFWwindow *glfwCreateWindow(int width, int height, const char *title, void *monitor, void *share);",
                "extern void glfwShowWindow(GLFWwindow *window);",
                "extern void glfwFocusWindow(GLFWwindow *window);",
                "extern int glfwWindowShouldClose(GLFWwindow *window);",
                "extern void glfwGetWindowSize(GLFWwindow *window, int *width, int *height);",
                "extern void glfwSwapBuffers(GLFWwindow *window);",
                "#define GLFW_FOCUSED 0x00020001",
                "#define GLFW_PRESS 1",
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
                "#define GLFW_KEY_PAGE_UP 266",
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
                "    CPU_GLFW_SC_G,",
                "    CPU_GLFW_SC_GRAVE,",
                "    CPU_GLFW_SC_H,",
                "    CPU_GLFW_SC_HOME,",
                "    CPU_GLFW_SC_I,",
                "    CPU_GLFW_SC_INSERT,",
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
                "    CPU_GLFW_SC_PAGEUP,",
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
                "#define CPU_HOST_AUDIO_FORMAT_S16 0x8010u",
                "#define CPU_HOST_SCANCODE(name) CPU_GLFW_SC_##name",
                "#define CPU_HOST_HAS_SCANCODE_MAP 1",
                "#define CPU_HOST_KEYCODE_QUOTE ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(APOSTROPHE)))",
                "#define CPU_HOST_KEYCODE_SEMICOLON ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(SEMICOLON)))",
                "#define CPU_HOST_MOD_CTRL 0x0001u",
                "#define CPU_HOST_MOD_SHIFT 0x0002u",
                "#define CPU_HOST_MOD_LCTRL 0x0004u",
                "#define cpu_host_hal_log(...) do { fprintf(stderr, __VA_ARGS__); fprintf(stderr, \"\\n\"); } while (0)",
                "#define cpu_host_hal_last_error() \"\"",
                "static void cpu_host_audio_spec_zero(CPUHostAudioSpec *spec) {",
                "    if (!spec) return;",
                "    memset(spec, 0, sizeof(*spec));",
                "}",
                "",
            ]
        )
    else:
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

    if host_uses_sdl2_backend:
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
                "    if (cpu_host_hal_sdl_inited == 0u) return -1;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return -1;",
                "    if (dev == 0u || !data || len_bytes == 0u) return -1;",
                "    return SDL_QueueAudio(dev, data, len_bytes);",
                "}",
                "",
                "static uint32_t cpu_host_hal_audio_queued_bytes(uint32_t dev) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    if (dev == 0u) return 0u;",
                "    return SDL_GetQueuedAudioSize(dev);",
                "}",
                "",
                "static void cpu_host_hal_audio_clear(uint32_t dev) {",
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "    if (dev == 0u) return;",
                "    SDL_ClearQueuedAudio(dev);",
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
                "    if (iscapture != 0) return 0u;",
                "    if (!want) return 0u;",
                "    if (want->freq <= 0 || want->channels == 0u || want->samples == 0u) return 0u;",
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
                "    if (cpu_host_hal_sdl_inited == 0u) return;",
                "    if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!window) window = (void *)cpu_host_hal_sdl_primary_window;",
                "    if (!window) return;",
                "    SDL_RaiseWindow((SDL_Window *)window);",
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
    elif host_uses_glfw_backend:
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
                "static uint8_t cpu_host_hal_glfw_inited = 0u;",
                "static uint32_t cpu_host_hal_glfw_subsystems = 0u;",
                "",
                "static void cpu_host_hal_glfw_reset_audio_state(void) {",
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
                "        case CPU_GLFW_SC_G: return GLFW_KEY_G;",
                "        case CPU_GLFW_SC_GRAVE: return GLFW_KEY_GRAVE_ACCENT;",
                "        case CPU_GLFW_SC_H: return GLFW_KEY_H;",
                "        case CPU_GLFW_SC_HOME: return GLFW_KEY_HOME;",
                "        case CPU_GLFW_SC_I: return GLFW_KEY_I;",
                "        case CPU_GLFW_SC_INSERT: return GLFW_KEY_INSERT;",
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
                "        case CPU_GLFW_SC_PAGEUP: return GLFW_KEY_PAGE_UP;",
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
                "        case CPU_GLFW_SC_A: return \"A\";",
                "        case CPU_GLFW_SC_B: return \"B\";",
                "        case CPU_GLFW_SC_C: return \"C\";",
                "        case CPU_GLFW_SC_D: return \"D\";",
                "        case CPU_GLFW_SC_E: return \"E\";",
                "        case CPU_GLFW_SC_F: return \"F\";",
                "        case CPU_GLFW_SC_G: return \"G\";",
                "        case CPU_GLFW_SC_H: return \"H\";",
                "        case CPU_GLFW_SC_I: return \"I\";",
                "        case CPU_GLFW_SC_J: return \"J\";",
                "        case CPU_GLFW_SC_K: return \"K\";",
                "        case CPU_GLFW_SC_L: return \"L\";",
                "        case CPU_GLFW_SC_M: return \"M\";",
                "        case CPU_GLFW_SC_N: return \"N\";",
                "        case CPU_GLFW_SC_O: return \"O\";",
                "        case CPU_GLFW_SC_P: return \"P\";",
                "        case CPU_GLFW_SC_Q: return \"Q\";",
                "        case CPU_GLFW_SC_R: return \"R\";",
                "        case CPU_GLFW_SC_S: return \"S\";",
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
                "        case CPU_GLFW_SC_APPLICATION: return \"APPLICATION\";",
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
                "    if (window != NULL) glfwSwapBuffers(window);",
                "}",
                "",
                "static int cpu_host_hal_audio_queue(uint32_t dev, const void *data, uint32_t len_bytes) {",
                "    uint64_t need64;",
                "    uint32_t need;",
                "    uint32_t new_cap;",
                "    uint8_t *new_buf;",
                "    if (cpu_host_hal_glfw_inited == 0u) return -1;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return -1;",
                "    if (dev != 1u || !data || len_bytes == 0u || cpu_host_hal_glfw_audio_opened == 0u) return -1;",
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
                "    if (cpu_host_hal_glfw_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    if (dev != 1u || cpu_host_hal_glfw_audio_opened == 0u) return 0u;",
                "    if (cpu_host_hal_glfw_audio_len > cpu_host_hal_glfw_audio_cap) return 0u;",
                "    if (cpu_host_hal_glfw_audio_cap != 0u && cpu_host_hal_glfw_audio_buf == NULL) return 0u;",
                "    if (cpu_host_hal_glfw_audio_len != 0u && cpu_host_hal_glfw_audio_buf == NULL) return 0u;",
                "    return cpu_host_hal_glfw_audio_len;",
                "}",
                "",
                "static void cpu_host_hal_audio_clear(uint32_t dev) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "    if (dev != 1u || cpu_host_hal_glfw_audio_opened == 0u) return;",
                "    if (cpu_host_hal_glfw_audio_len > cpu_host_hal_glfw_audio_cap) return;",
                "    if (cpu_host_hal_glfw_audio_cap != 0u && cpu_host_hal_glfw_audio_buf == NULL) return;",
                "    if (cpu_host_hal_glfw_audio_len != 0u && cpu_host_hal_glfw_audio_buf == NULL) return;",
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
                "    if (dx < 0) { sx -= dx; sw += dx; dx = 0; }",
                "    if (dy < 0) { sy -= dy; sh += dy; dy = 0; }",
                "    if (sx >= tex->w || sy >= tex->h) return 0;",
                "    sum64 = (int64_t)sx + (int64_t)sw;",
                "    if (sum64 > (int64_t)tex->w) sw = tex->w - sx;",
                "    sum64 = (int64_t)sy + (int64_t)sh;",
                "    if (sum64 > (int64_t)tex->h) sh = tex->h - sy;",
                "    if (sw <= 0 || sh <= 0) return 0;",
                "    if (dx >= rr->w || dy >= rr->h) return 0;",
                "    cw = sw;",
                "    ch = sh;",
                "    if (dw > 0 && dw < cw) cw = dw;",
                "    if (dh > 0 && dh < ch) ch = dh;",
                "    sum64 = (int64_t)dx + (int64_t)cw;",
                "    if (sum64 > (int64_t)rr->w) cw = rr->w - dx;",
                "    sum64 = (int64_t)dy + (int64_t)ch;",
                "    if (sum64 > (int64_t)rr->h) ch = rr->h - dy;",
                "    if (cw <= 0 || ch <= 0) return 0;",
                "    row_bytes64 = (uint64_t)(uint32_t)cw * 4u;",
                "    if (row_bytes64 == 0u || row_bytes64 > (uint64_t)SIZE_MAX) return -1;",
                "    tex_bytes64 = (uint64_t)(uint32_t)tex->w * (uint64_t)(uint32_t)tex->h * 4u;",
                "    if (tex_bytes64 == 0u || tex_bytes64 > (uint64_t)SIZE_MAX) return -1;",
                "    if ((uint64_t)tex->pixels_len < tex_bytes64) return -1;",
                "    src_start64 = (((uint64_t)(uint32_t)sy * (uint64_t)(uint32_t)tex->w) + (uint64_t)(uint32_t)sx) * 4u;",
                "    if (src_start64 > tex_bytes64) return -1;",
                "    src_stride64 = (uint64_t)(uint32_t)tex->w * 4u;",
                "    src_span64 = ((uint64_t)(uint32_t)(ch - 1) * src_stride64) + row_bytes64;",
                "    if (src_span64 > (tex_bytes64 - src_start64)) return -1;",
                "    dst_start64 = (((uint64_t)(uint32_t)dy * (uint64_t)(uint32_t)rr->w) + (uint64_t)(uint32_t)dx) * 4u;",
                "    if (dst_start64 > expect64) return -1;",
                "    dst_stride64 = (uint64_t)(uint32_t)rr->w * 4u;",
                "    dst_span64 = ((uint64_t)(uint32_t)(ch - 1) * dst_stride64) + row_bytes64;",
                "    if (dst_span64 > (expect64 - dst_start64)) return -1;",
                "    for (int row = 0; row < ch; ++row) {",
                "        memcpy(",
                "            rr->frame_rgba + (((size_t)(dy + row) * (size_t)rr->w + (size_t)dx) * 4u),",
                "            tex->pixels + (((size_t)(sy + row) * (size_t)tex->w + (size_t)sx) * 4u),",
                "            (size_t)cw * 4u",
                "        );",
                "    }",
                "    return 0;",
                "}",
                "",
                "static int cpu_host_hal_poll_event(CPUHostEvent *event) {",
                "    int key;",
                "    if (!event) return 0;",
                "    if (cpu_host_hal_glfw_inited == 0u) return 0;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0;",
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
                "    if (dev != 1u || cpu_host_hal_glfw_audio_opened == 0u) return;",
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
                "        if (!glfwInit()) return -1;",
                "        cpu_host_hal_glfw_inited = 1u;",
                "    }",
                "    cpu_host_hal_glfw_subsystems |= flags;",
                "    return 0;",
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
                "    if (cpu_host_hal_glfw_inited == 0u) return 0u;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;",
                "    if (iscapture != 0) return 0u;",
                "    if (!want) return 0u;",
                "    if (want->freq <= 0 || want->channels == 0u || want->samples == 0u) return 0u;",
                "    cpu_host_hal_glfw_reset_audio_state();",
                "    if (have) {",
                "        *have = *want;",
                "        if (have->size == 0u && have->samples != 0u && have->channels != 0u) {",
                "            bytes64 = (uint64_t)have->samples * (uint64_t)have->channels * 2u;",
                "            if (bytes64 > 0xFFFFFFFFu) return 0u;",
                "            have->size = (uint32_t)bytes64;",
                "        }",
                "    }",
                "    cpu_host_hal_glfw_audio_opened = 1u;",
                "    cpu_host_hal_glfw_audio_len = 0u;",
                "    return 1u;",
                "}",
                "",
                "static void cpu_host_hal_audio_pause(uint32_t dev, int pause_on) {",
                "    (void)dev;",
                "    (void)pause_on;",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
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
                "static int32_t cpu_host_hal_key_from_scancode(int scancode) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return 0;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0;",
                "    return (int32_t)cpu_host_hal_glfw_key_for_scancode(scancode);",
                "}",
                "",
                "static void cpu_host_hal_start_text_input(void) {",
                "}",
                "",
                "static void cpu_host_hal_stop_text_input(void) {",
                "}",
                "",
                "static void cpu_host_hal_raise_window(void *window) {",
                "    if (cpu_host_hal_glfw_inited == 0u) return;",
                "    if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    if (!window) window = (void *)cpu_host_hal_glfw_primary_window;",
                "    if (!window) return;",
                "    glfwFocusWindow((GLFWwindow *)window);",
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
                "    if (dev != 1u || !data || len_bytes == 0u || cpu_host_hal_glfw_audio_opened == 0u) return 0u;",
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
    else:
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
                "    if (dev != 1u || !data || len_bytes == 0u || cpu_host_hal_stub_audio_opened == 0u) return -1;",
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
                "    if (dev != 1u || cpu_host_hal_stub_audio_opened == 0u) return 0u;",
                "    if (cpu_host_hal_stub_audio_len > cpu_host_hal_stub_audio_cap) return 0u;",
                "    if (cpu_host_hal_stub_audio_cap != 0u && cpu_host_hal_stub_audio_buf == NULL) return 0u;",
                "    if (cpu_host_hal_stub_audio_len != 0u && cpu_host_hal_stub_audio_buf == NULL) return 0u;",
                "    return cpu_host_hal_stub_audio_len;",
                "}",
                "",
                "static void cpu_host_hal_audio_clear(uint32_t dev) {",
                "    if (cpu_host_hal_stub_inited == 0u) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;",
                "    if (dev != 1u || cpu_host_hal_stub_audio_opened == 0u) return;",
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
                "    if (dev != 1u || cpu_host_hal_stub_audio_opened == 0u) return;",
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
                "static int32_t cpu_host_hal_key_from_scancode(int scancode) {",
                "    (void)scancode;",
                "    return 0;",
                "}",
                "",
                "static void cpu_host_hal_start_text_input(void) {",
                "}",
                "",
                "static void cpu_host_hal_stop_text_input(void) {",
                "}",
                "",
                "static void cpu_host_hal_raise_window(void *window) {",
                "    CPUHostStubWindow *ww = (window != NULL) ? (CPUHostStubWindow *)window : cpu_host_hal_stub_primary_window;",
                "    if (cpu_host_hal_stub_inited == 0u || ww == NULL) return;",
                "    if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;",
                "    ww->focused = 1u;",
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
                "    if (dev != 1u || !data || len_bytes == 0u || cpu_host_hal_stub_audio_opened == 0u) return 0u;",
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

    helper_lines.append(
        "static int32_t cpu_component_scancode_for_host_key(const char *host_key) {"
    )
    helper_lines.append("#if CPU_HOST_HAS_SCANCODE_MAP")
    helper_lines.append("    if (!host_key || !host_key[0]) return -1;")
    helper_lines.append("    if (0) return -1;")
    for key in sorted(ALLOWED_HOST_KEYS):
        if host_uses_sdl2_backend and key in SDL_UNSUPPORTED_SCANCODE_KEYS:
            continue
        if host_uses_glfw_backend and key not in GLFW_SCANCODE_KEYS:
            continue
        key_escaped = _escape_c_string(str(key))
        helper_lines.append(
            f"    else if (strcmp(host_key, \"{key_escaped}\") == 0) return (int32_t)CPU_HOST_SCANCODE({key});"
        )
    helper_lines.append("    return -1;")
    helper_lines.append("#else")
    helper_lines.append("    (void)host_key;")
    helper_lines.append("    return -1;")
    helper_lines.append("#endif")
    helper_lines.append("}")
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
            "static RuntimeKeyboardBinding *cpu_component_runtime_binding_for_scancode(int32_t scancode, uint8_t create_if_missing) {",
            "    for (size_t i = 0; i < g_runtime_keyboard_map.binding_count; ++i) {",
            "        if (g_runtime_keyboard_map.bindings[i].scancode == scancode) {",
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
            "        return b;",
            "    }",
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
            "        if (strcmp(s, \"bindings:\") == 0) continue;",
            "        if (strcmp(s, \"presses:\") == 0) continue;",
            "        if (strcmp(s, \"-\") == 0) continue;",
            "        if (strncmp(s, \"kind:\", 5) == 0) {",
            "            s = cpu_component_trim(s + 5);",
            "            if (strcmp(s, \"matrix\") == 0) g_runtime_keyboard_map.kind = 1u;",
            "            else if (strcmp(s, \"ascii\") == 0) g_runtime_keyboard_map.kind = 2u;",
            "            else { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"focus_required:\", 15) == 0) {",
            "            s = cpu_component_trim(s + 15);",
            "            if (strcmp(s, \"true\") == 0) g_runtime_keyboard_map.focus_required = 1u;",
            "            else if (strcmp(s, \"false\") == 0) g_runtime_keyboard_map.focus_required = 0u;",
            "            else { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            continue;",
            "        }",
            "        if (strncmp(s, \"- host_key:\", 11) == 0 || strncmp(s, \"host_key:\", 9) == 0) {",
            "            int32_t sc;",
            "            s = cpu_component_unquote(cpu_component_trim(s + ((s[0] == '-') ? 11 : 9)));",
            "            sc = cpu_component_scancode_for_host_key(s);",
            "            if (sc < 0) { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
            "            current = cpu_component_runtime_binding_for_scancode(sc, 1u);",
            "            if (current == NULL) { fclose(f); cpu_component_runtime_keyboard_clear(); return -1; }",
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
            "        if (g_runtime_keyboard_map.kind == 1u) {",
            "            if (b->has_ascii != 0u || b->has_ascii_shift != 0u || b->has_ascii_ctrl != 0u) {",
            "                cpu_component_runtime_keyboard_clear();",
            "                return -1;",
            "            }",
            "            if (b->press_count == 0u) { cpu_component_runtime_keyboard_clear(); return -1; }",
            "            for (uint8_t p = 0u; p < b->press_count; ++p) {",
            "                if (b->presses[p].bit > 7u) { cpu_component_runtime_keyboard_clear(); return -1; }",
            "            }",
            "        } else {",
            "            if (b->press_count != 0u) {",
            "                cpu_component_runtime_keyboard_clear();",
            "                return -1;",
            "            }",
            "            if (b->has_ascii == 0u && b->has_ascii_shift == 0u && b->has_ascii_ctrl == 0u) {",
            "                cpu_component_runtime_keyboard_clear();",
            "                return -1;",
            "            }",
            "        }",
            "    }",
            "    g_runtime_keyboard_map.loaded = 1u;",
            "    return 0;",
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
            "    for (size_t i = 0; i < g_runtime_keyboard_map.binding_count; ++i) {",
            "        const RuntimeKeyboardBinding *b = &g_runtime_keyboard_map.bindings[i];",
            "        if (b->scancode < 0 || (size_t)b->scancode >= host_key_count) continue;",
            "        if (host_keys[b->scancode] == 0u) continue;",
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
            "    uint8_t shifted,",
            "    uint8_t controlled,",
            "    uint8_t has_focus",
            ") {",
            "    if (g_runtime_keyboard_map.loaded == 0u || g_runtime_keyboard_map.kind != 2u) return;",
            "    if (g_runtime_keyboard_map.focus_required && has_focus == 0u) return;",
            "    for (size_t i = 0; i < g_runtime_keyboard_map.binding_count; ++i) {",
            "        const RuntimeKeyboardBinding *b = &g_runtime_keyboard_map.bindings[i];",
            "        uint8_t out = 0u;",
            "        if (b->scancode != scancode) continue;",
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
            "",
        ]
    )

    if connections:
        helper_lines.append("static const ComponentConnection g_component_connections[] = {")
        for conn in connections:
            from_ep = conn.get("from", {})
            to_ep = conn.get("to", {})
            helper_lines.append(
                "    { "
                f"\"{_escape_c_string(str(from_ep.get('component', '')))}\", "
                f"\"{_escape_c_string(str(from_ep.get('kind', '')))}\", "
                f"\"{_escape_c_string(str(from_ep.get('name', '')))}\", "
                f"\"{_escape_c_string(str(to_ep.get('component', '')))}\", "
                f"\"{_escape_c_string(str(to_ep.get('kind', '')))}\", "
                f"\"{_escape_c_string(str(to_ep.get('name', '')))}\" "
                "},"
            )
        helper_lines.append("};")
    else:
        helper_lines.append(
            "static const ComponentConnection g_component_connections[] = { { \"\", \"\", \"\", \"\", \"\", \"\" } };"
        )
    callback_dispatch_lines: List[str] = [
        "static uint64_t cpu_component_dispatch_callback(",
        "    CPUState *cpu,",
        "    const char *component_id,",
        "    const char *callback_name,",
        "    const uint64_t *args,",
        "    uint8_t argc",
        ") {",
    ]
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
            if body:
                for raw_line in body.splitlines():
                    helper_lines.append(f"    {raw_line.rstrip()}" if raw_line.strip() else "")
            helper_lines.append("    return __result;")
            helper_lines.append("}")
            helper_lines.append("")
            callback_dispatch_lines.append(
                f"    if (strcmp(component_id, \"{_escape_c_string(comp_id)}\") == 0 && "
                f"strcmp(callback_name, \"{_escape_c_string(cb_name)}\") == 0) "
                f"return component_{comp_ident}_callback_{cb_ident}(cpu, args, argc);"
            )
    callback_dispatch_lines.append("    return 0;")
    callback_dispatch_lines.append("}")
    callback_dispatch_lines.append("")
    helper_lines.extend(callback_dispatch_lines)

    handler_dispatch_lines: List[str] = [
        "static void cpu_component_dispatch_handler(",
        "    CPUState *cpu,",
        "    const char *component_id,",
        "    const char *handler_name,",
        "    const uint64_t *args,",
        "    uint8_t argc",
        ") {",
    ]
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
            if body:
                for raw_line in body.splitlines():
                    helper_lines.append(f"    {raw_line.rstrip()}" if raw_line.strip() else "")
            helper_lines.append("}")
            helper_lines.append("")
            handler_dispatch_lines.append(
                f"    if (strcmp(component_id, \"{_escape_c_string(comp_id)}\") == 0 && "
                f"strcmp(handler_name, \"{_escape_c_string(handler_name)}\") == 0) "
                f"{{ component_{comp_ident}_handler_{handler_ident}(cpu, args, argc); return; }}"
            )
    handler_dispatch_lines.append("    (void)cpu;")
    handler_dispatch_lines.append("    (void)component_id;")
    handler_dispatch_lines.append("    (void)handler_name;")
    handler_dispatch_lines.append("    (void)args;")
    handler_dispatch_lines.append("    (void)argc;")
    handler_dispatch_lines.append("}")
    handler_dispatch_lines.append("")
    helper_lines.extend(handler_dispatch_lines)

    helper_lines.extend(
        [
            "static uint64_t cpu_component_call(",
            "    CPUState *cpu,",
            "    const char *source_component,",
            "    const char *callback_name,",
            "    const uint64_t *args,",
            "    uint8_t argc",
            ") {",
            "    size_t connection_count = sizeof(g_component_connections) / sizeof(g_component_connections[0]);",
            "    for (size_t i = 0; i < connection_count; i++) {",
            "        const ComponentConnection *conn = &g_component_connections[i];",
            "        if (strcmp(conn->from_component, source_component) != 0) continue;",
            "        if (strcmp(conn->from_kind, \"callback\") != 0) continue;",
            "        if (strcmp(conn->from_name, callback_name) != 0) continue;",
            "        return cpu_component_dispatch_callback(cpu, conn->to_component, conn->to_name, args, argc);",
            "    }",
            "    return 0;",
            "}",
            "",
            "static void cpu_component_emit_signal(",
            "    CPUState *cpu,",
            "    const char *source_component,",
            "    const char *signal_name,",
            "    const uint64_t *args,",
            "    uint8_t argc",
            ") {",
            "    size_t connection_count = sizeof(g_component_connections) / sizeof(g_component_connections[0]);",
            "    for (size_t i = 0; i < connection_count; i++) {",
            "        const ComponentConnection *conn = &g_component_connections[i];",
            "        if (strcmp(conn->from_component, source_component) != 0) continue;",
            "        if (strcmp(conn->from_kind, \"signal\") != 0) continue;",
            "        if (strcmp(conn->from_name, signal_name) != 0) continue;",
            "        cpu_component_dispatch_handler(cpu, conn->to_component, conn->to_name, args, argc);",
            "    }",
            "}",
            "",
            "static void cpu_components_step_pre(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before) {",
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
            "static void cpu_components_step_post(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before) {",
            "    (void)inst;",
            "    (void)pc_before;",
        ]
    )
    for component in components:
        block = _snippet_block(component, "step_post")
        if block:
            helper_lines.append(block)
    helper_lines.append("}")

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

    lines.append(
        f"void {cpu_prefix}_trace_instruction(CPUState *cpu, DecodedInstruction *inst) {{"
    )
    lines.append("    (void)cpu;")
    lines.append("    if (!inst) return;")
    lines.append("    uint32_t raw_for_disasm = inst->raw;")
    lines.append("    if (inst->prefix != 0) {")
    lines.append("        raw_for_disasm = ((uint32_t)inst->prefix) | (inst->raw << 8);")
    lines.append("    }")
    lines.append(
        f'    printf("[TRACE] %s\\n", {cpu_prefix}_disassemble_instruction(inst->pc, raw_for_disasm));'
    )
    lines.append("}")

    return "\n".join(lines)


def _generate_interrupt_reset(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate interrupt reset block based on interrupt model."""
    model = resolve_interrupt_model(isa_data)

    if model == "none":
        return "    /* Interrupt model: none */"

    lines: List[str] = []
    if model == "z80":
        lines.append("    cpu->interrupt_mode = 0;")

    lines.extend(["    cpu->interrupt_vector = 0;"])
    if model == "mos6502":
        lines.append("    cpu->sp = 0xFDu;")
        lines.append("    cpu->flags.I = true;")
        lines.append(f"    cpu->pc = {cpu_prefix}_read_word(cpu, 0xFFFCu);")
    elif model == "mc6809":
        # MC6809 RESET masks both IRQ (I) and FIRQ (F).
        lines.append("    cpu->flags.I = true;")
        lines.append("    cpu->flags.F = true;")
    lines.extend(
        [
            "    cpu->interrupts_enabled = false;",
            "    cpu->interrupt_pending = false;",
        ]
    )
    return "\n".join(lines)


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
    lines.append("    cpu->interrupt_vector = vector;")
    lines.append("    cpu->interrupt_pending = true;")
    lines.append('    cpu_irq_trace(cpu, "request", vector, 0u);')
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
    interrupt_model = resolve_interrupt_model(isa_data) if has_interrupts else "none"
    interrupt_modes = configured_interrupt_modes(isa_data)
    if not interrupt_modes:
        interrupt_modes = [1]
    default_interrupt_mode = interrupt_modes[0]
    interrupts_config = isa_data.get("interrupts", {})
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
    reset_delay_seconds = max(
        0, int(isa_data.get("system", {}).get("reset_delay_seconds", 0))
    )

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
    lines.append("    if (cpu->reset_delay_pending) {")
    lines.append("        cpu->reset_delay_pending = false;")
    if reset_delay_seconds > 0:
        lines.append(f"        cpu_sleep_seconds({reset_delay_seconds}u);")
    lines.append("    }")
    lines.append("")

    lines.append("    if (cpu_check_breakpoints(cpu)) {")
    lines.append("        cpu->running = false;")
    lines.append("        return 0;")
    lines.append("    }")
    lines.append("")
    if has_interrupts and interrupt_model != "none":
        if interrupt_model == "mos6502":
            lines.append(
                "    if (cpu->interrupt_pending && (cpu->interrupt_vector == 0xFFu || cpu->interrupts_enabled)) {"
            )
            lines.append("        uint8_t irq_vector = cpu->interrupt_vector;")
            lines.append("        cpu->interrupt_pending = false;")
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
            lines.append(
                '        cpu_irq_trace(cpu, "take", irq_vector, (irq_vector == 0xFFu) ? 0xFFFAu : 0xFFFEu);'
            )
            lines.append("        cpu->total_cycles += 7u;")
            lines.append("        return 0;")
            lines.append("    }")
            lines.append("")
        elif interrupt_model == "mc6809":
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
            lines.append('            cpu_irq_trace(cpu, "take", irq_kind, vector_addr);')
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
            if interrupt_model == "fixed_vector":
                lines.append(f"        cpu->pc = 0x{fixed_vector & 0xFFFF:04X};")
            elif interrupt_model == "z80":
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
                    f"Unsupported interrupt model for generation: {interrupt_model}"
                )
            lines.append('        cpu_irq_trace(cpu, "take", cpu->interrupt_vector, cpu->pc);')
            lines.append("        cpu->total_cycles += irq_cycles;")
            lines.append("        return 0;")
            lines.append("    }")
            lines.append("")

    lines.append("    if (cpu->halted) {")
    lines.append("        if (cpu->interrupt_pending && !cpu->interrupts_enabled) {")
    lines.append("            cpu->interrupt_pending = false;")
    lines.append("            cpu->halted = false;")
    lines.append("            return 0;")
    lines.append("        }")
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
            '        fprintf(stderr, "Invalid opcode at 0x%04X: 0x%06X\\n", pc_before, (unsigned int)raw);'
        )
        lines.append("        return -1;")
    lines.append("    }")
    lines.append("")
    lines.append("    if (cpu->tracing_enabled) {")
    lines.append(f"        {cpu_prefix}_trace_instruction(cpu, &inst);")
    lines.append("    }")
    lines.append("")
    if interrupt_model == "mos6502":
        lines.append("    uint8_t x_before = cpu->registers[REG_X];")
        lines.append("    uint8_t y_before = cpu->registers[REG_Y];")
        lines.append("    uint8_t c_before = cpu->flags.C ? 1u : 0u;")
        lines.append("    uint8_t z_before = cpu->flags.Z ? 1u : 0u;")
        lines.append("    uint8_t n_before = cpu->flags.N ? 1u : 0u;")
        lines.append("    uint8_t v_before = cpu->flags.V ? 1u : 0u;")
        lines.append("")
    lines.append("    bool executed = false;")
    lines.append("    cpu->pc_modified = false;")
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
    lines.append("")
    if interrupt_model == "mos6502":
        lines.append("    cpu_apply_mos6502_runtime_cycles(cpu, &inst, pc_before, x_before, y_before, c_before, z_before, n_before, v_before);")
        lines.append("")
    if has_components:
        lines.append("    cpu_components_step_post(cpu, &inst, pc_before);")
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
    lines.append("        if (cpu->halted && !cpu->interrupt_pending) break;")
    lines.append(f"        if ({cpu_prefix}_step(cpu) != 0) break;")
    lines.append("    }")
    lines.append("}")

    return "\n".join(lines)
