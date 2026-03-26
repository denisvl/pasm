"""CPU decoder generator."""

from typing import Dict, List, Any

from .templates import get_template


def generate_decoder(isa_data: Dict[str, Any], cpu_name: str) -> tuple:
    """Generate decoder header and implementation."""

    cpu_prefix = cpu_name.lower()
    guard_name = cpu_name.upper()

    # Generate decoded fields
    decoded_fields = _generate_decoded_fields(isa_data)

    # Generate category enum
    category_enum = _generate_category_enum(isa_data)

    # Generate decode logic
    decode_logic = _generate_decode_logic(isa_data, cpu_prefix)

    # Header
    header_template = get_template("decoder_header")
    isa_name = isa_data.get("metadata", {}).get("name", cpu_name)
    header = header_template.format(
        guard_name=guard_name,
        cpu_name=cpu_name,
        cpu_prefix=cpu_prefix,
        decoded_fields=decoded_fields,
        category_enum=category_enum,
        isa_name=isa_name,
    )

    # Implementation
    impl_template = get_template("decoder_impl")
    impl = impl_template.format(
        cpu_name=cpu_name,
        cpu_prefix=cpu_prefix,
        decode_logic=decode_logic,
        isa_name=isa_name,
    )

    return header, impl


def _generate_decoded_fields(isa_data: Dict[str, Any]) -> str:
    """Generate decoded instruction structure fields."""
    lines: List[str] = []
    seen_names = set()

    base_fields = [
        ("r", "uint8_t", "Register operand"),
        ("rs", "uint8_t", "Source register"),
        ("rt", "uint8_t", "Target register"),
        ("rd", "uint8_t", "Destination register"),
        ("imm", "uint16_t", "Immediate value"),
        ("disp", "int16_t", "Displacement"),
        ("addr", "uint16_t", "Address"),
        ("cc", "uint8_t", "Condition code"),
        ("length", "uint8_t", "Instruction length in bytes"),
        ("cycles", "uint8_t", "Instruction cycles"),
    ]

    for name, ctype, desc in base_fields:
        lines.append(f"{ctype} {name};  /* {desc} */")
        seen_names.add(name)

    # Include ISA-specific decoded fields (e.g. n, nn, etc.).
    for inst in isa_data.get("instructions", []):
        encoding = inst.get("encoding", {})
        for field in encoding.get("fields", []):
            name = field.get("name", "")
            if not name or name in seen_names:
                continue
            position = field.get("position", [0, 0])
            msb, lsb = position[0], position[1]
            width = int(field.get("width", msb - lsb + 1))
            if width <= 8:
                ctype = "uint8_t"
            elif width <= 16:
                ctype = "uint16_t"
            else:
                ctype = "uint32_t"
            lines.append(f"{ctype} {name};  /* ISA field */")
            seen_names.add(name)

    return "\n    ".join(lines)


def _generate_category_enum(isa_data: Dict[str, Any]) -> str:
    """Generate instruction category enum."""
    lines = ["typedef enum {"]

    categories = {"MISC"}
    for inst in isa_data.get("instructions", []):
        cat = inst.get("category", "misc").upper()
        categories.add(cat)

    for cat in sorted(categories):
        lines.append(f"    CAT_{cat},")

    lines.append("} InstructionCategory;")

    return "\n".join(lines)


def _generate_decode_logic(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate the decode logic."""
    lines = []

    instructions = isa_data.get("instructions", [])
    isa_name = str(isa_data.get("metadata", {}).get("name", "")).lower()
    is_mc6809 = "6809" in isa_name
    is_big_endian = str(isa_data.get("metadata", {}).get("endian", "little")).lower() == "big"

    # Track prefixes used (non-zero only)
    prefixes = set()
    for inst in instructions:
        enc = inst.get("encoding", {})
        if "prefix" in enc:
            prefixes.add(enc["prefix"])

    # Group by prefix; key 0 means \"no prefix\"
    by_prefix: Dict[int, List[Dict[str, Any]]] = {0: []}
    for p in prefixes:
        if p != 0:
            by_prefix[p] = []

    for inst in instructions:
        enc = inst.get("encoding", {})
        prefix = enc.get("prefix", 0)
        if prefix not in by_prefix:
            by_prefix[prefix] = []
        by_prefix[prefix].append(inst)

    # Handle prefixed instructions first, then non-prefixed ones
    if prefixes:
        lines.append("    if (prefix != 0) {")
        lines.append("        switch (prefix) {")

        for prefix in sorted(prefixes):
            if prefix == 0:
                continue
            lines.append(f"            case 0x{prefix:02X}: {{")

            # Decode prefixed instructions
            for inst in by_prefix.get(prefix, []):
                _add_decode_case(lines, inst, prefix, is_mc6809, is_big_endian)

            lines.append("                break;")
            lines.append("            }")

        lines.append("            default:")
        lines.append("                break;")
        lines.append("        }")
        lines.append("    }")

    # Decode non-prefixed instructions only when no prefix was consumed.
    lines.append("    if (prefix == 0) {")
    for inst in by_prefix.get(0, []):
        _add_decode_case(lines, inst, 0, is_mc6809, is_big_endian)
    lines.append("    }")

    # Default case
    lines.append("")
    lines.append("    /* Default: unknown opcode */")
    lines.append("    inst.opcode = (uint8_t)(raw & 0xFF);")
    lines.append("    inst.category = CAT_MISC;")
    lines.append("    inst.pc = pc;")
    lines.append("    inst.length = (prefix != 0) ? 2 : 1;")
    lines.append("    inst.cycles = 4;")
    lines.append("    inst.valid = false;")

    if 0xDD in prefixes or 0xFD in prefixes:
        lines.append("")
        lines.append("    /* DD/FD fallback: treat unsupported prefixed forms as base aliases. */")
        lines.append("    if (prefix == 0xDD || prefix == 0xFD) {")
        lines.append(f"        DecodedInstruction base = {cpu_prefix}_decode(raw, 0, pc);")
        lines.append("        if (base.valid) {")
        lines.append("            base.length = (uint8_t)(base.length + 1);")
        lines.append("            return base;")
        lines.append("        }")
        lines.append("        if ((raw & 0x00FF) != 0xCB) {")
        lines.append("            inst.length = 2;")
        lines.append("            return inst;")
        lines.append("        }")
        lines.append("        inst.length = 4;")
        lines.append("        return inst;")
        lines.append("    }")

    return "\n".join(lines)


def _add_decode_case(
    lines: List[str], inst: Dict[str, Any], prefix: int, is_mc6809: bool, is_big_endian: bool
):
    """Add a decode case for an instruction."""
    name = inst.get("name", "UNKNOWN")
    category = inst.get("category", "misc").upper()
    encoding = inst.get("encoding", {})

    opcode = encoding.get("opcode", 0)
    mask = encoding.get("mask", 0xFF)
    subop = encoding.get("subop")
    subop_mask = encoding.get("subop_mask", 0xFF)
    length = encoding.get("length", inst.get("length", 1))
    cycles = inst.get("cycles", 1)

    fields = encoding.get("fields", [])

    lines.append(f"                /* {name} */")

    if subop is not None:
        if prefix != 0 and opcode == 0xCB and length >= 4:
            # DD/FD CB d op form: subop is in the third byte after prefix.
            if subop_mask != 0xFF:
                lines.append(
                    f"                if (((raw) & 0x00FF) == 0x{opcode:02X} && ((((raw >> 16) & 0x00FF) & 0x{subop_mask:02X}) == 0x{subop & subop_mask:02X})) {{"
                )
            else:
                lines.append(
                    f"                if (((raw) & 0x00FF) == 0x{opcode:02X} && ((raw >> 16) & 0x00FF) == 0x{subop:02X}) {{"
                )
        else:
            # Two-byte opcode: low byte == opcode, high byte == subop
            if subop_mask != 0xFF:
                lines.append(
                    f"                if (((raw) & 0x00FF) == 0x{opcode:02X} && ((((raw >> 8) & 0x00FF) & 0x{subop_mask:02X}) == 0x{subop & subop_mask:02X})) {{"
                )
            else:
                lines.append(
                    f"                if (((raw) & 0x00FF) == 0x{opcode:02X} && ((raw >> 8) & 0x00FF) == 0x{subop:02X}) {{"
                )
    elif mask == 0xFF:
        # Simple 8- or 16-bit opcode match
        lines.append(f"                if ((raw & 0x00FF) == 0x{opcode & 0xFF:02X}) {{")
    else:
        # Masked match for bit-field encoded instructions
        mask_val = mask
        lines.append(
            f"                if ((raw & 0x{mask_val:04X}) == 0x{opcode:04X}) {{"
        )

    lines.append(f"                    inst.opcode = 0x{opcode & 0xFF:02X};")
    lines.append(f"                    inst.category = CAT_{category};")
    lines.append(f"                    inst.pc = pc;")
    lines.append(f"                    inst.cycles = {cycles};")

    # Extract fields
    for field in fields:
        field_name = field.get("name", "")
        position = field.get("position", [0, 0])
        msb, lsb = position[0], position[1]
        width = msb - lsb + 1

        if field.get("type") == "immediate" or field.get("type") == "address":
            mask = ((1 << width) - 1)
            lines.append(
                f"                    inst.{field_name} = (raw >> {lsb}) & 0x{mask:X};"
            )
            if is_big_endian and width > 8 and (width % 8) == 0:
                byte_count = width // 8
                lines.append("                    {")
                lines.append(f"                        uint32_t be_tmp = (uint32_t)inst.{field_name};")
                lines.append("                        uint32_t be_swapped = 0u;")
                for byte_idx in range(byte_count):
                    src_shift = 8 * byte_idx
                    dst_shift = 8 * (byte_count - 1 - byte_idx)
                    lines.append(
                        f"                        be_swapped |= ((be_tmp >> {src_shift}) & 0xFFu) << {dst_shift};"
                    )
                lines.append(
                    f"                        inst.{field_name} = (be_swapped & 0x{mask:X}u);"
                )
                lines.append("                    }")
        else:
            lines.append(
                f"                    inst.{field_name} = (raw >> {lsb}) & 0x{((1 << width) - 1):X};"
            )

    has_postbyte = any(str(field.get("name", "")) == "postbyte" for field in fields)
    if is_mc6809 and has_postbyte:
        lines.append("                    {")
        lines.append("                        uint8_t pb_len = (uint8_t)((raw >> 8) & 0xFFu);")
        lines.append("                        uint8_t idx_extra = 0u;")
        lines.append("                        if ((pb_len & 0x80u) != 0u) {")
        lines.append("                            uint8_t mode = (uint8_t)(pb_len & 0x1Fu);")
        lines.append("                            uint8_t m = mode;")
        lines.append("                            if ((mode & 0x10u) != 0u) m = (uint8_t)(mode & 0x0Fu);")
        lines.append("                            if (m == 0x08u || m == 0x0Cu) idx_extra = 1u;")
        lines.append("                            else if (m == 0x09u || m == 0x0Du || m == 0x0Fu) idx_extra = 2u;")
        lines.append("                        }")
        lines.append(f"                        inst.length = (uint8_t)({length}u + idx_extra);")
        lines.append("                    }")
    else:
        lines.append(f"                    inst.length = {length};")

    lines.append("                    return inst;")
    lines.append("                }")
