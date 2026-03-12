"""CPU header file generator."""

import json
import re
from typing import Dict, List, Any

from .interrupts import resolve_interrupt_model


def generate_cpu_header(isa_data: Dict[str, Any], cpu_name: str) -> str:
    """Generate the CPU header file."""

    cpu_prefix = cpu_name.lower()
    guard_name = cpu_name.upper()

    # Generate types code
    types_code = _generate_types(isa_data)

    # Generate state fields
    state_fields = _generate_state_fields(isa_data)
    interrupt_state_fields = _generate_interrupt_state_fields(isa_data)
    interrupt_api = _generate_interrupt_api(isa_data, cpu_prefix)

    # Generate register enum
    register_enum = _generate_register_enum(isa_data)

    # Generate flag bits
    flag_bits = _generate_flag_bits(isa_data, cpu_prefix)
    system_constants = _generate_system_constants(isa_data)

    # Format the template
    from .templates import CPU_HEADER_TEMPLATE

    return CPU_HEADER_TEMPLATE.format(
        guard_name=guard_name,
        cpu_prefix=cpu_prefix,
        cpu_name=cpu_name,
        types_code=types_code,
        state_fields=state_fields,
        interrupt_state_fields=interrupt_state_fields,
        register_enum=register_enum,
        flag_bits=flag_bits,
        system_constants=system_constants,
        interrupt_api=interrupt_api,
        isa_name=isa_data.get("metadata", {}).get("name", "Unknown"),
    )


def _generate_types(isa_data: Dict[str, Any]) -> str:
    """Generate type definitions."""
    lines = []
    bits = isa_data.get("metadata", {}).get("bits", 8)

    if bits <= 8:
        lines.append("typedef uint8_t reg_t;")
    elif bits <= 16:
        lines.append("typedef uint16_t reg_t;")
    else:
        lines.append("typedef uint32_t reg_t;")

    return "\n".join(lines)


def _generate_state_fields(isa_data: Dict[str, Any]) -> str:
    """Generate CPU state structure fields."""
    lines = []
    lines.append("    /* Registers */")
    declared_fields = set()

    # Group registers by type
    registers = isa_data.get("registers", [])

    # Keep a flat register bank indexed by REG_* enum values.
    if registers:
        lines.append(f"    uint8_t registers[{len(registers)}];  /* Register bank */")
        declared_fields.add("registers")

    # Special registers
    for reg in registers:
        reg_type = reg.get("type", "general")
        if reg_type == "program_counter":
            bits = reg.get("bits", 16)
            type_name = f"uint{bits}_t"
            lines.append(f"    {type_name} pc;")
            declared_fields.add("pc")
        elif reg_type == "stack_pointer":
            bits = reg.get("bits", 16)
            type_name = f"uint{bits}_t"
            lines.append(f"    {type_name} sp;")
            declared_fields.add("sp")
        elif reg_type == "index":
            bits = reg.get("bits", 16)
            type_name = f"uint{bits}_t"
            field_name = _to_c_ident(reg["name"])
            lines.append(f"    {type_name} {field_name};")
            declared_fields.add(field_name)
        elif reg_type == "special":
            bits = reg.get("bits", 8)
            type_name = f"uint{bits}_t"
            field_name = _to_c_ident(reg["name"])
            lines.append(f"    {type_name} {field_name};")
            declared_fields.add(field_name)

    register_names = {reg.get("name", "").upper() for reg in registers}

    # Flags (YAML-defined bit layout in a raw+named union)
    flags = isa_data.get("flags", [])
    if flags:
        lines.extend(_generate_flag_union_field("flags", flags, indent="    "))
        declared_fields.add("flags")
        if "A_PRIME" in register_names:
            # Optional shadow flag bank used by architectures with AF-style alternates.
            lines.extend(_generate_flag_union_field("flags_prime", flags, indent="    "))
            declared_fields.add("flags_prime")

    subdivision_view_lines = _generate_register_subdivision_views(
        registers, declared_fields
    )
    if subdivision_view_lines:
        lines.append("")
        lines.append("    /* Register subdivision views */")
        lines.extend(subdivision_view_lines)

    return "\n".join(lines)


def _generate_interrupt_state_fields(isa_data: Dict[str, Any]) -> str:
    """Generate interrupt-related state fields based on interrupt model."""
    model = resolve_interrupt_model(isa_data)

    if model == "none":
        return "    /* Interrupt model: none */"

    lines = []
    if model == "z80":
        lines.append("    uint8_t interrupt_mode;")

    lines.extend(
        [
            "    uint8_t interrupt_vector;",
            "    bool interrupts_enabled;",
            "    bool interrupt_pending;",
        ]
    )
    return "\n".join(lines)


def _generate_interrupt_api(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate interrupt API declarations based on interrupt model."""
    model = resolve_interrupt_model(isa_data)

    lines = [f"void {cpu_prefix}_interrupt(CPUState *cpu, uint8_t vector);"]
    if model == "z80":
        lines.append(f"void {cpu_prefix}_set_interrupt_mode(CPUState *cpu, uint8_t mode);")
    lines.append(f"void {cpu_prefix}_set_irq(CPUState *cpu, bool enabled);")

    return "\n".join(lines)


def _generate_register_enum(isa_data: Dict[str, Any]) -> str:
    """Generate register enum."""
    lines = ["typedef enum {"]

    registers = isa_data.get("registers", [])

    # Add registers with numeric indices
    for i, reg in enumerate(registers):
        name = reg.get("name", "").upper()
        # Replace special characters
        name = name.replace("'", "_PRIME")
        lines.append(f"    REG_{name} = {i},")

    lines.append("} Register;")

    return "\n".join(lines)


def _generate_flag_bits(isa_data: Dict[str, Any], cpu_prefix: str) -> str:
    """Generate flag bit definitions."""
    lines = ["/* Flag bit positions */", "typedef enum {"]

    flags = isa_data.get("flags", [])
    for flag in flags:
        name = flag.get("name", "").upper()
        bit = int(flag.get("bit", 0))
        lines.append(f"    FLAG_{name} = (1u << {bit}),")

    lines.append("} FlagBits;")

    return "\n".join(lines)


def _generate_system_constants(isa_data: Dict[str, Any]) -> str:
    """Generate system metadata constants/comments from system.yaml."""
    system = isa_data.get("system", {})
    system_meta = system.get("metadata", {})
    system_name = _escape_c_string(str(system_meta.get("name", "UnknownSystem")))
    system_version = _escape_c_string(str(system_meta.get("version", "")))
    clock_hz = int(system.get("clock_hz", 0))
    integrations_json = _escape_c_string(
        json.dumps(system.get("integrations", {}), sort_keys=True)
    )
    lines = [
        f'#define CPU_SYSTEM_NAME "{system_name}"',
        f'#define CPU_SYSTEM_VERSION "{system_version}"',
        f"#define CPU_SYSTEM_CLOCK_HZ {clock_hz}ULL",
        f"/* CPU_SYSTEM_INTEGRATIONS_JSON: {integrations_json} */",
    ]
    return "\n".join(lines)


def _to_c_ident(name: str) -> str:
    """Convert ISA-provided names into lowercase C identifiers."""
    ident = re.sub(r"[^0-9A-Za-z_]", "_", str(name).strip())
    ident = ident.lower()
    if not ident:
        return "reg"
    if ident[0].isdigit():
        ident = f"reg_{ident}"
    return ident


def _escape_c_string(value: str) -> str:
    """Escape a string for safe use in C string literals/comments."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _storage_type_for_bits(bits: int) -> str:
    """Select a raw integer storage type for a bitfield view."""
    if bits <= 8:
        return "uint8_t"
    if bits <= 16:
        return "uint16_t"
    if bits <= 32:
        return "uint32_t"
    return "uint64_t"


def _generate_flag_union_field(
    field_name: str, flags: List[Dict[str, Any]], indent: str = ""
) -> List[str]:
    """Generate a raw+named flag union field using YAML bit positions."""
    lines: List[str] = []
    bit_to_name = {int(flag["bit"]): str(flag["name"]) for flag in flags}

    lines.append(f"{indent}union {{")
    lines.append(f"{indent}    struct {{")
    for bit in range(8):
        flag_name = bit_to_name.get(bit)
        if flag_name:
            lines.append(f"{indent}        unsigned int {flag_name} : 1;")
        else:
            lines.append(f"{indent}        unsigned int _reserved_{bit} : 1;")
    lines.append(f"{indent}    }};")
    lines.append(f"{indent}    uint8_t raw;")
    lines.append(f"{indent}}} {field_name};")
    return lines


def _generate_register_subdivision_views(
    registers: List[Dict[str, Any]], declared_fields: set[str]
) -> List[str]:
    """Generate YAML-declared register subdivision views (parts)."""
    lines: List[str] = []
    for reg in registers:
        parent_name = str(reg.get("name", "")).upper().replace("'", "_PRIME")
        parts = reg.get("parts", [])
        if not parts:
            continue
        reg_bits = int(reg.get("bits", 0))

        field_name = _to_c_ident(parent_name)
        if field_name in declared_fields:
            field_name = f"{field_name}_view"

        bit_to_name = {}
        for part in parts:
            part_name = str(part.get("name", ""))
            part_lsb = int(part.get("lsb", 0))
            part_bits = int(part.get("bits", 0))
            for bit in range(part_lsb, part_lsb + part_bits):
                bit_to_name[bit] = part_name

        lines.append(f"    /* {parent_name} subdivision view (from YAML parts) */")
        lines.append("    union {")
        lines.append("        struct {")
        bit = 0
        while bit < reg_bits:
            part_name = bit_to_name.get(bit)
            run = 1
            while bit + run < reg_bits and bit_to_name.get(bit + run) == part_name:
                run += 1
            if part_name:
                lines.append(f"            unsigned long long {part_name} : {run};")
            else:
                lines.append(f"            unsigned long long _reserved_{bit} : {run};")
            bit += run
        lines.append("        } bytes;")
        lines.append(f"        {_storage_type_for_bits(reg_bits)} raw;")
        lines.append(f"    }} {field_name};")

        declared_fields.add(field_name)

    return lines


def _generate_hooks_api_and_forward(
    hooks_config: Dict[str, Any], cpu_prefix: str
) -> tuple:
    """Generate hooks API and forward declarations."""
    has_any_hook = False

    # Check if any hooks are enabled
    for hook_name in ["pre_fetch", "post_decode", "post_execute"]:
        if hooks_config.get(hook_name, {}).get("enabled", False):
            has_any_hook = True
            break

    if not has_any_hook:
        return "/* No hooks configured */", "/* No forward declarations needed */"

    # Forward declarations
    forward_lines = [
        "/* Forward declarations for hooks */",
        "typedef struct CPUState CPUState;",
        "",
    ]

    if (
        hooks_config.get("pre_fetch", {}).get("enabled")
        or hooks_config.get("post_decode", {}).get("enabled")
        or hooks_config.get("post_execute", {}).get("enabled")
    ):
        forward_lines.extend(
            [
                "typedef enum {",
                "    HOOK_PRE_FETCH = 0,",
                "    HOOK_POST_DECODE = 1,",
                "    HOOK_POST_EXECUTE = 2,",
                "    HOOK_PORT_READ_PRE = 3,",
                "    HOOK_PORT_READ_POST = 4,",
                "    HOOK_PORT_WRITE_PRE = 5,",
                "    HOOK_PORT_WRITE_POST = 6,",
                "    HOOK_COUNT = 7",
                "} HookType;",
                "",
                "typedef struct {",
                "    HookType type;",
                "    uint16_t pc;",
                "    uint8_t prefix;",
                "    uint8_t opcode;",
                "    uint16_t port;",
                "    uint8_t value;",
                "    uint32_t raw;",
                "} CPUHookEvent;",
                "",
                "typedef void (*CPUHookFunc)(CPUState *cpu, const CPUHookEvent *event, void *context);",
                "",
                "typedef struct {",
                "    CPUHookFunc func;",
                "    void *context;",
                "    bool enabled;",
                "} CPUHook;",
            ]
        )

    forward_decls = "\n".join(forward_lines)

    # API
    lines = []
    lines.append("/* Hook API */")
    lines.append(
        f"void {cpu_prefix}_hook_set(CPUState *cpu, HookType type, CPUHookFunc func, void *context);"
    )
    lines.append(
        f"void {cpu_prefix}_hook_enable(CPUState *cpu, HookType type, bool enable);"
    )
    lines.append(f"void {cpu_prefix}_hook_clear(CPUState *cpu, HookType type);")

    return "\n".join(lines), forward_decls
