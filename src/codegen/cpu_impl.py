"""CPU implementation file generator."""

import re
from typing import Any, Dict, List, Set, Tuple

from .interrupts import configured_interrupt_modes, resolve_interrupt_model
from .templates import get_template


def generate_cpu_impl(
    isa_data: Dict[str, Any], cpu_name: str, dispatch_mode: str = "switch"
) -> str:
    """Generate the CPU implementation file."""

    cpu_prefix = cpu_name.lower()

    # Generate helper functions
    helpers_code = _generate_helpers(isa_data, cpu_prefix)

    # Generate instruction implementations
    instructions_code = _generate_instructions(isa_data, cpu_prefix)

    # Generate dispatch
    dispatch_code = _generate_dispatch(isa_data, cpu_prefix, dispatch_mode)
    disassembler_code = _generate_disassembler(isa_data, cpu_prefix)
    interrupt_reset = _generate_interrupt_reset(isa_data)
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

    hooks_impl = "/* Hook API is emitted in *_hooks.c when enabled. */"

    # Get metadata for template
    isa_name = isa_data.get("metadata", {}).get("name", cpu_name)

    # Format template
    template = get_template("cpu_impl")

    return template.format(
        cpu_name=cpu_name,
        cpu_prefix=cpu_prefix,
        helpers_code=helpers_code,
        instructions_code=instructions_code,
        dispatch_code=dispatch_code,
        disassembler_code=disassembler_code,
        interrupt_reset=interrupt_reset,
        shadow_flags_reset=shadow_flags_reset,
        interrupt_impl=interrupt_impl,
        port_read_hook_pre=port_read_hook_pre,
        port_read_hook_post=port_read_hook_post,
        port_write_hook_pre=port_write_hook_pre,
        port_write_hook_post=port_write_hook_post,
        memory_write_guard=memory_write_guard,
        hooks_impl=hooks_impl,
        isa_name=isa_name,
    )


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

    return "\n".join(lines)


def _generate_memory_write_guard(isa_data: Dict[str, Any]) -> str:
    """Generate memory write protection checks for read-only regions."""
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

        lines.append(f"    /* Block writes to read-only region: {region_name} */")
        lines.append(f"    if {condition} {{")
        lines.append("        cpu->error_code = CPU_ERROR_INVALID_MEMORY;")
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
        cycles = inst.get("cycles", 1)

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

        lines.append(f"    cpu->total_cycles += {cycles};")
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

    # Group by category to keep generated branch structure compact.
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for inst in instructions:
        categories.setdefault(inst.get("category", "misc"), []).append(inst)

    lines.append(
        f"char *{cpu_prefix}_disassemble_instruction(uint16_t pc, uint32_t raw) {{"
    )
    lines.append("    static char buf[160];")
    lines.append("    uint8_t prefix = 0;")
    lines.append("    uint32_t decode_raw = raw;")
    lines.append("    uint8_t b0 = (uint8_t)(raw & 0xFF);")
    lines.append("    if (b0 == 0xCB || b0 == 0xDD || b0 == 0xED || b0 == 0xFD) {")
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
            display = _escape_c_string(inst.get("display", name))
            lines.append(f"                if ({_dispatch_condition(inst)}) {{")
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
        '    (void)snprintf(buf, sizeof(buf), "PC=%04X %s OP=%02X PREF=%02X LEN=%u CYC=%u r=%u imm=%u addr=%u disp=%d cc=%u",'
    )
    lines.append("                   pc,")
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


def _generate_interrupt_reset(isa_data: Dict[str, Any]) -> str:
    """Generate interrupt reset block based on interrupt model."""
    model = resolve_interrupt_model(isa_data)

    if model == "none":
        return "    /* Interrupt model: none */"

    lines: List[str] = []
    if model == "z80":
        lines.append("    cpu->interrupt_mode = 0;")

    lines.extend(
        [
            "    cpu->interrupt_vector = 0;",
            "    cpu->interrupts_enabled = false;",
            "    cpu->interrupt_pending = false;",
        ]
    )
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
    has_interrupt_i_register = "I" in register_names

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

    if has_interrupts and interrupt_model != "none":
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
            raise ValueError(f"Unsupported interrupt model for generation: {interrupt_model}")
        lines.append("        cpu->total_cycles += irq_cycles;")
        lines.append("        return 0;")
        lines.append("    }")
        lines.append("")

    lines.append("    if (cpu->halted) return 0;")
    lines.append("")
    lines.append("    if (cpu_check_breakpoints(cpu)) {")
    lines.append("        cpu->running = false;")
    lines.append("        return 0;")
    lines.append("    }")
    lines.append("")

    lines.append("    uint16_t pc_before = cpu->pc;")
    lines.append("    uint8_t prefix = 0;")
    lines.append("    uint32_t raw = 0;")
    lines.append(f"    uint8_t b0 = {cpu_prefix}_read_byte(cpu, pc_before);")
    lines.append("")

    if prefix_values:
        prefix_cond = " || ".join(f"b0 == 0x{value:02X}" for value in prefix_values)
        lines.append(f"    if ({prefix_cond}) {{")
        lines.append("        prefix = b0;")
        lines.append(f"        raw = {cpu_prefix}_read_byte(cpu, (uint16_t)(pc_before + 1));")
        lines.append(
            f"        raw |= ((uint32_t){cpu_prefix}_read_byte(cpu, (uint16_t)(pc_before + 2))) << 8;"
        )
        lines.append(
            f"        raw |= ((uint32_t){cpu_prefix}_read_byte(cpu, (uint16_t)(pc_before + 3))) << 16;"
        )
        lines.append("    } else {")
        lines.append("        raw = b0;")
        lines.append(
            f"        raw |= ((uint32_t){cpu_prefix}_read_byte(cpu, (uint16_t)(pc_before + 1))) << 8;"
        )
        lines.append(
            f"        raw |= ((uint32_t){cpu_prefix}_read_byte(cpu, (uint16_t)(pc_before + 2))) << 16;"
        )
        lines.append(
            f"        raw |= ((uint32_t){cpu_prefix}_read_byte(cpu, (uint16_t)(pc_before + 3))) << 24;"
        )
        lines.append("    }")
    else:
        lines.append("    raw = b0;")
        lines.append(
            f"    raw |= ((uint32_t){cpu_prefix}_read_byte(cpu, (uint16_t)(pc_before + 1))) << 8;"
        )
        lines.append(
            f"    raw |= ((uint32_t){cpu_prefix}_read_byte(cpu, (uint16_t)(pc_before + 2))) << 16;"
        )
        lines.append(
            f"    raw |= ((uint32_t){cpu_prefix}_read_byte(cpu, (uint16_t)(pc_before + 3))) << 24;"
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
    lines.append("    bool executed = false;")
    lines.append("    cpu->pc_modified = false;")
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

    lines.append("    if (!cpu->pc_modified) {")
    lines.append("        cpu->pc = (uint16_t)(pc_before + inst.length);")
    lines.append("    }")
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
    if has_interrupts and interrupt_model != "none":
        lines.append(
            "        if (cpu->halted && !(cpu->interrupt_pending && cpu->interrupts_enabled)) break;"
        )
    else:
        lines.append("        if (cpu->halted) break;")
    lines.append(f"        if ({cpu_prefix}_step(cpu) != 0) break;")
    lines.append("    }")
    lines.append("}")

    return "\n".join(lines)
