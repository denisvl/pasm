"""CPU implementation file generator."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .interrupts import configured_interrupt_modes, resolve_interrupt_model
from .templates import get_template


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
    )


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
    lines.append("    struct timespec req;")
    lines.append("    req.tv_sec = (time_t)seconds;")
    lines.append("    req.tv_nsec = 0;")
    lines.append("    while (nanosleep(&req, &req) == -1 && errno == EINTR) {}")
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
            "/* No IC runtime API */",
        )
    connections = list(isa_data.get("connections", []))
    host_component_ids = {
        str(component.get("metadata", {}).get("id", ""))
        for component in isa_data.get("hosts", [])
    }

    def _ident(name: str) -> str:
        return _to_c_ident(name)

    def _component_keyboard_input(component: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        input_cfg = component.get("input", {})
        if not isinstance(input_cfg, dict):
            return None
        keyboard_cfg = input_cfg.get("keyboard")
        if not isinstance(keyboard_cfg, dict):
            return None
        if str(keyboard_cfg.get("source", "")).strip() != "sdl_scancode":
            return None
        bindings = keyboard_cfg.get("bindings", [])
        if not isinstance(bindings, list) or not bindings:
            return None

        normalized_bindings: List[Dict[str, Any]] = []
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            host_key = str(binding.get("host_key", "")).strip()
            presses = binding.get("presses", [])
            if not host_key or not isinstance(presses, list) or not presses:
                continue
            normalized_presses: List[Tuple[int, int]] = []
            for press in presses:
                if not isinstance(press, dict):
                    continue
                row = int(press.get("row", -1))
                bit = int(press.get("bit", -1))
                if row < 0 or row > 31 or bit < 0 or bit > 7:
                    continue
                normalized_presses.append((row, bit))
            if not normalized_presses:
                continue
            normalized_bindings.append(
                {
                    "host_key": host_key,
                    "presses": normalized_presses,
                }
            )
        if not normalized_bindings:
            return None
        return {
            "focus_required": bool(keyboard_cfg.get("focus_required", True)),
            "bindings": normalized_bindings,
        }

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
        "} ComponentKeyboardPress;",
        "",
        "typedef struct {",
        "    int host_key;",
        "    const ComponentKeyboardPress *presses;",
        "    uint8_t press_count;",
        "} ComponentKeyboardBinding;",
        "",
        "typedef struct {",
        "    const char *component_id;",
        "    uint8_t focus_required;",
        "    const ComponentKeyboardBinding *bindings;",
        "    size_t binding_count;",
        "} ComponentKeyboardMap;",
        "",
    ]

    keyboard_maps: List[Tuple[str, str, bool, List[Dict[str, Any]]]] = []
    for component in components:
        comp_id = str(component.get("metadata", {}).get("id", "component"))
        comp_ident = _ident(comp_id)
        keyboard_input = _component_keyboard_input(component)
        if keyboard_input is None:
            continue
        keyboard_maps.append(
            (
                comp_id,
                comp_ident,
                bool(keyboard_input.get("focus_required", True)),
                list(keyboard_input.get("bindings", [])),
            )
        )

    if keyboard_maps:
        for comp_id, comp_ident, _, bindings in keyboard_maps:
            for bind_idx, binding in enumerate(bindings):
                presses = binding.get("presses", [])
                helper_lines.append(
                    f"static const ComponentKeyboardPress component_{comp_ident}_keyboard_presses_{bind_idx}[] = {{"
                )
                for row, bit in presses:
                    helper_lines.append(f"    {{ {int(row)}u, {int(bit)}u }},")
                helper_lines.append("};")
            helper_lines.append(
                f"static const ComponentKeyboardBinding component_{comp_ident}_keyboard_bindings[] = {{"
            )
            for bind_idx, binding in enumerate(bindings):
                host_key = _escape_c_string(str(binding.get("host_key", "")))
                press_count = len(binding.get("presses", []))
                helper_lines.append(
                    "    { "
                    f"{host_key}, "
                    f"component_{comp_ident}_keyboard_presses_{bind_idx}, "
                    f"{press_count}u "
                    "},"
                )
            helper_lines.append("};")
        helper_lines.append("static const ComponentKeyboardMap g_component_keyboard_maps[] = {")
        for comp_id, comp_ident, focus_required, _ in keyboard_maps:
            helper_lines.append(
                "    { "
                f"\"{_escape_c_string(comp_id)}\", "
                f"{'1u' if focus_required else '0u'}, "
                f"component_{comp_ident}_keyboard_bindings, "
                f"(sizeof(component_{comp_ident}_keyboard_bindings) / sizeof(component_{comp_ident}_keyboard_bindings[0])) "
                "},"
            )
        helper_lines.append("};")
    else:
        helper_lines.append(
            "static const ComponentKeyboardMap g_component_keyboard_maps[] = { { \"\", 0u, NULL, 0u } };"
        )

    helper_lines.extend(
        [
            "static const ComponentKeyboardMap *cpu_component_find_keyboard_map(const char *component_id) {",
            "    size_t map_count = sizeof(g_component_keyboard_maps) / sizeof(g_component_keyboard_maps[0]);",
            "    for (size_t i = 0; i < map_count; i++) {",
            "        const ComponentKeyboardMap *map = &g_component_keyboard_maps[i];",
            "        if (!map->component_id || !map->component_id[0]) continue;",
            "        if (strcmp(map->component_id, component_id) == 0) return map;",
            "    }",
            "    return NULL;",
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
            "    const ComponentKeyboardMap *map = cpu_component_find_keyboard_map(component_id);",
            "    (void)cpu;",
            "    if (!map || !rows || row_count == 0u || !host_keys || host_key_count == 0u) return;",
            "    if (map->focus_required && has_focus == 0u) return;",
            "    for (size_t bind_idx = 0; bind_idx < map->binding_count; bind_idx++) {",
            "        const ComponentKeyboardBinding *binding = &map->bindings[bind_idx];",
            "        if (binding->host_key < 0 || (size_t)binding->host_key >= host_key_count) continue;",
            "        if (host_keys[binding->host_key] == 0u) continue;",
            "        for (size_t press_idx = 0; press_idx < binding->press_count; press_idx++) {",
            "            const ComponentKeyboardPress *press = &binding->presses[press_idx];",
            "            if ((size_t)press->row >= row_count || press->bit >= 8u) continue;",
            "            rows[press->row] &= (uint8_t)~(1u << press->bit);",
            "        }",
            "    }",
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
    isa_name = str(isa_data.get("metadata", {}).get("name", "")).lower()
    if "6809" in isa_name:
        numeric_style = "asm_dollar"
    elif "6502" in isa_name or "6510" in isa_name or "6509" in isa_name:
        numeric_style = "asm_dollar"
    elif "z80" in isa_name:
        numeric_style = "z80_h"
    else:
        numeric_style = "c_hex"
    explicit_prefixes = sorted(
        {
            int(inst.get("encoding", {}).get("prefix"))
            for inst in instructions
            if "prefix" in inst.get("encoding", {}) and int(inst.get("encoding", {}).get("prefix")) != 0
        }
    )

    # Group by category to keep generated branch structure compact.
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for inst in instructions:
        categories.setdefault(inst.get("category", "misc"), []).append(inst)

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
                    lines, render_inst, numeric_style=numeric_style, indent="                    "
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

    lines.append("    if (cpu->interrupt_pending && !cpu->interrupts_enabled && !cpu->halted) {")
    lines.append("        cpu->interrupt_pending = false;")
    lines.append("    }")
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
    lines.append(f"        if ({cpu_prefix}_step(cpu) != 0) break;")
    lines.append("    }")
    lines.append("}")

    return "\n".join(lines)
