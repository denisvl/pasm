"""Processor/System/IC/Device YAML loader with JSON Schema validation."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

try:
    from jsonschema import Draft7Validator
    from jsonschema import ValidationError
except ImportError:  # pragma: no cover
    from jsonschema import ValidationError

    Draft7Validator = None


HOOK_NAMES = {
    "pre_fetch",
    "post_decode",
    "post_execute",
    "port_read_pre",
    "port_read_post",
    "port_write_pre",
    "port_write_post",
}

DISPLAY_TEMPLATE_TOKEN_RE = re.compile(
    r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([A-Za-z_][A-Za-z0-9_]*))?\}"
)
DISPLAY_RENDER_KINDS = {
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
TABLE_RENDER_KINDS = {"table", "cc_table"}
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

ALLOWED_SDL_SCANCODES = {
    "SDL_SCANCODE_0",
    "SDL_SCANCODE_1",
    "SDL_SCANCODE_2",
    "SDL_SCANCODE_3",
    "SDL_SCANCODE_4",
    "SDL_SCANCODE_5",
    "SDL_SCANCODE_6",
    "SDL_SCANCODE_7",
    "SDL_SCANCODE_8",
    "SDL_SCANCODE_9",
    "SDL_SCANCODE_A",
    "SDL_SCANCODE_AC_BACK",
    "SDL_SCANCODE_AC_BOOKMARKS",
    "SDL_SCANCODE_AC_FORWARD",
    "SDL_SCANCODE_AC_HOME",
    "SDL_SCANCODE_AC_REFRESH",
    "SDL_SCANCODE_AC_SEARCH",
    "SDL_SCANCODE_AC_STOP",
    "SDL_SCANCODE_AGAIN",
    "SDL_SCANCODE_ALTERASE",
    "SDL_SCANCODE_APOSTROPHE",
    "SDL_SCANCODE_APP1",
    "SDL_SCANCODE_APP2",
    "SDL_SCANCODE_APPLICATION",
    "SDL_SCANCODE_AUDIOFASTFORWARD",
    "SDL_SCANCODE_AUDIOMUTE",
    "SDL_SCANCODE_AUDIONEXT",
    "SDL_SCANCODE_AUDIOPLAY",
    "SDL_SCANCODE_AUDIOPREV",
    "SDL_SCANCODE_AUDIOREWIND",
    "SDL_SCANCODE_AUDIOSTOP",
    "SDL_SCANCODE_B",
    "SDL_SCANCODE_BACKSLASH",
    "SDL_SCANCODE_BACKSPACE",
    "SDL_SCANCODE_BRIGHTNESSDOWN",
    "SDL_SCANCODE_BRIGHTNESSUP",
    "SDL_SCANCODE_C",
    "SDL_SCANCODE_CALCULATOR",
    "SDL_SCANCODE_CALL",
    "SDL_SCANCODE_CANCEL",
    "SDL_SCANCODE_CAPSLOCK",
    "SDL_SCANCODE_CLEAR",
    "SDL_SCANCODE_CLEARAGAIN",
    "SDL_SCANCODE_COMMA",
    "SDL_SCANCODE_COMPUTER",
    "SDL_SCANCODE_COPY",
    "SDL_SCANCODE_CRSEL",
    "SDL_SCANCODE_CURRENCYSUBUNIT",
    "SDL_SCANCODE_CURRENCYUNIT",
    "SDL_SCANCODE_CUT",
    "SDL_SCANCODE_D",
    "SDL_SCANCODE_DECIMALSEPARATOR",
    "SDL_SCANCODE_DELETE",
    "SDL_SCANCODE_DISPLAYSWITCH",
    "SDL_SCANCODE_DOWN",
    "SDL_SCANCODE_E",
    "SDL_SCANCODE_EJECT",
    "SDL_SCANCODE_END",
    "SDL_SCANCODE_ENDCALL",
    "SDL_SCANCODE_EQUALS",
    "SDL_SCANCODE_ESCAPE",
    "SDL_SCANCODE_EXECUTE",
    "SDL_SCANCODE_EXSEL",
    "SDL_SCANCODE_F",
    "SDL_SCANCODE_F1",
    "SDL_SCANCODE_F10",
    "SDL_SCANCODE_F11",
    "SDL_SCANCODE_F12",
    "SDL_SCANCODE_F13",
    "SDL_SCANCODE_F14",
    "SDL_SCANCODE_F15",
    "SDL_SCANCODE_F16",
    "SDL_SCANCODE_F17",
    "SDL_SCANCODE_F18",
    "SDL_SCANCODE_F19",
    "SDL_SCANCODE_F2",
    "SDL_SCANCODE_F20",
    "SDL_SCANCODE_F21",
    "SDL_SCANCODE_F22",
    "SDL_SCANCODE_F23",
    "SDL_SCANCODE_F24",
    "SDL_SCANCODE_F3",
    "SDL_SCANCODE_F4",
    "SDL_SCANCODE_F5",
    "SDL_SCANCODE_F6",
    "SDL_SCANCODE_F7",
    "SDL_SCANCODE_F8",
    "SDL_SCANCODE_F9",
    "SDL_SCANCODE_FIND",
    "SDL_SCANCODE_G",
    "SDL_SCANCODE_GRAVE",
    "SDL_SCANCODE_H",
    "SDL_SCANCODE_HELP",
    "SDL_SCANCODE_HOME",
    "SDL_SCANCODE_I",
    "SDL_SCANCODE_INSERT",
    "SDL_SCANCODE_INTERNATIONAL1",
    "SDL_SCANCODE_INTERNATIONAL2",
    "SDL_SCANCODE_INTERNATIONAL3",
    "SDL_SCANCODE_INTERNATIONAL4",
    "SDL_SCANCODE_INTERNATIONAL5",
    "SDL_SCANCODE_INTERNATIONAL6",
    "SDL_SCANCODE_INTERNATIONAL7",
    "SDL_SCANCODE_INTERNATIONAL8",
    "SDL_SCANCODE_INTERNATIONAL9",
    "SDL_SCANCODE_J",
    "SDL_SCANCODE_K",
    "SDL_SCANCODE_KBDILLUMDOWN",
    "SDL_SCANCODE_KBDILLUMTOGGLE",
    "SDL_SCANCODE_KBDILLUMUP",
    "SDL_SCANCODE_KP_0",
    "SDL_SCANCODE_KP_00",
    "SDL_SCANCODE_KP_000",
    "SDL_SCANCODE_KP_1",
    "SDL_SCANCODE_KP_2",
    "SDL_SCANCODE_KP_3",
    "SDL_SCANCODE_KP_4",
    "SDL_SCANCODE_KP_5",
    "SDL_SCANCODE_KP_6",
    "SDL_SCANCODE_KP_7",
    "SDL_SCANCODE_KP_8",
    "SDL_SCANCODE_KP_9",
    "SDL_SCANCODE_KP_A",
    "SDL_SCANCODE_KP_AMPERSAND",
    "SDL_SCANCODE_KP_AT",
    "SDL_SCANCODE_KP_B",
    "SDL_SCANCODE_KP_BACKSPACE",
    "SDL_SCANCODE_KP_BINARY",
    "SDL_SCANCODE_KP_C",
    "SDL_SCANCODE_KP_CLEAR",
    "SDL_SCANCODE_KP_CLEARENTRY",
    "SDL_SCANCODE_KP_COLON",
    "SDL_SCANCODE_KP_COMMA",
    "SDL_SCANCODE_KP_D",
    "SDL_SCANCODE_KP_DBLAMPERSAND",
    "SDL_SCANCODE_KP_DBLVERTICALBAR",
    "SDL_SCANCODE_KP_DECIMAL",
    "SDL_SCANCODE_KP_DIVIDE",
    "SDL_SCANCODE_KP_E",
    "SDL_SCANCODE_KP_ENTER",
    "SDL_SCANCODE_KP_EQUALS",
    "SDL_SCANCODE_KP_EQUALSAS400",
    "SDL_SCANCODE_KP_EXCLAM",
    "SDL_SCANCODE_KP_F",
    "SDL_SCANCODE_KP_GREATER",
    "SDL_SCANCODE_KP_HASH",
    "SDL_SCANCODE_KP_HEXADECIMAL",
    "SDL_SCANCODE_KP_LEFTBRACE",
    "SDL_SCANCODE_KP_LEFTPAREN",
    "SDL_SCANCODE_KP_LESS",
    "SDL_SCANCODE_KP_MEMADD",
    "SDL_SCANCODE_KP_MEMCLEAR",
    "SDL_SCANCODE_KP_MEMDIVIDE",
    "SDL_SCANCODE_KP_MEMMULTIPLY",
    "SDL_SCANCODE_KP_MEMRECALL",
    "SDL_SCANCODE_KP_MEMSTORE",
    "SDL_SCANCODE_KP_MEMSUBTRACT",
    "SDL_SCANCODE_KP_MINUS",
    "SDL_SCANCODE_KP_MULTIPLY",
    "SDL_SCANCODE_KP_OCTAL",
    "SDL_SCANCODE_KP_PERCENT",
    "SDL_SCANCODE_KP_PERIOD",
    "SDL_SCANCODE_KP_PLUS",
    "SDL_SCANCODE_KP_PLUSMINUS",
    "SDL_SCANCODE_KP_POWER",
    "SDL_SCANCODE_KP_RIGHTBRACE",
    "SDL_SCANCODE_KP_RIGHTPAREN",
    "SDL_SCANCODE_KP_SPACE",
    "SDL_SCANCODE_KP_TAB",
    "SDL_SCANCODE_KP_VERTICALBAR",
    "SDL_SCANCODE_KP_XOR",
    "SDL_SCANCODE_L",
    "SDL_SCANCODE_LALT",
    "SDL_SCANCODE_LANG1",
    "SDL_SCANCODE_LANG2",
    "SDL_SCANCODE_LANG3",
    "SDL_SCANCODE_LANG4",
    "SDL_SCANCODE_LANG5",
    "SDL_SCANCODE_LANG6",
    "SDL_SCANCODE_LANG7",
    "SDL_SCANCODE_LANG8",
    "SDL_SCANCODE_LANG9",
    "SDL_SCANCODE_LCTRL",
    "SDL_SCANCODE_LEFT",
    "SDL_SCANCODE_LEFTBRACKET",
    "SDL_SCANCODE_LGUI",
    "SDL_SCANCODE_LOCKINGCAPSLOCK",
    "SDL_SCANCODE_LOCKINGNUMLOCK",
    "SDL_SCANCODE_LOCKINGSCROLLLOCK",
    "SDL_SCANCODE_LSHIFT",
    "SDL_SCANCODE_M",
    "SDL_SCANCODE_MAIL",
    "SDL_SCANCODE_MEDIASELECT",
    "SDL_SCANCODE_MENU",
    "SDL_SCANCODE_MINUS",
    "SDL_SCANCODE_MODE",
    "SDL_SCANCODE_MUTE",
    "SDL_SCANCODE_N",
    "SDL_SCANCODE_NONUSBACKSLASH",
    "SDL_SCANCODE_NONUSHASH",
    "SDL_SCANCODE_NUMLOCKCLEAR",
    "SDL_SCANCODE_O",
    "SDL_SCANCODE_OPER",
    "SDL_SCANCODE_OUT",
    "SDL_SCANCODE_P",
    "SDL_SCANCODE_PAGEDOWN",
    "SDL_SCANCODE_PAGEUP",
    "SDL_SCANCODE_PASTE",
    "SDL_SCANCODE_PAUSE",
    "SDL_SCANCODE_PERIOD",
    "SDL_SCANCODE_POWER",
    "SDL_SCANCODE_PRINTSCREEN",
    "SDL_SCANCODE_PRIOR",
    "SDL_SCANCODE_Q",
    "SDL_SCANCODE_R",
    "SDL_SCANCODE_RALT",
    "SDL_SCANCODE_RCTRL",
    "SDL_SCANCODE_RETURN",
    "SDL_SCANCODE_RETURN2",
    "SDL_SCANCODE_RGUI",
    "SDL_SCANCODE_RIGHT",
    "SDL_SCANCODE_RIGHTBRACKET",
    "SDL_SCANCODE_RSHIFT",
    "SDL_SCANCODE_S",
    "SDL_SCANCODE_SCROLLLOCK",
    "SDL_SCANCODE_SELECT",
    "SDL_SCANCODE_SEMICOLON",
    "SDL_SCANCODE_SEPARATOR",
    "SDL_SCANCODE_SLASH",
    "SDL_SCANCODE_SLEEP",
    "SDL_SCANCODE_SOFTLEFT",
    "SDL_SCANCODE_SOFTRIGHT",
    "SDL_SCANCODE_SPACE",
    "SDL_SCANCODE_STOP",
    "SDL_SCANCODE_SYSREQ",
    "SDL_SCANCODE_T",
    "SDL_SCANCODE_TAB",
    "SDL_SCANCODE_THOUSANDSSEPARATOR",
    "SDL_SCANCODE_U",
    "SDL_SCANCODE_UNDO",
    "SDL_SCANCODE_UNKNOWN",
    "SDL_SCANCODE_UP",
    "SDL_SCANCODE_V",
    "SDL_SCANCODE_VOLUMEDOWN",
    "SDL_SCANCODE_VOLUMEUP",
    "SDL_SCANCODE_W",
    "SDL_SCANCODE_WWW",
    "SDL_SCANCODE_X",
    "SDL_SCANCODE_Y",
    "SDL_SCANCODE_Z",
}

ALLOWED_HOST_KEYS = frozenset(
    key[len("SDL_SCANCODE_") :] for key in ALLOWED_SDL_SCANCODES
)
CANONICAL_HOST_KEY_RE = re.compile(r"^[A-Z0-9_]+$")
CANONICAL_BACKEND_TARGET_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SUPPORTED_HOST_BACKEND_TARGETS = frozenset({"sdl2", "glfw", "stub"})


def get_schema_path(kind: str) -> Path:
    """Get path to a schema file."""
    base = Path(__file__).parent.parent.parent / "schemas"
    if kind == "processor":
        return base / "processor_schema.json"
    if kind == "system":
        return base / "system_schema.json"
    if kind == "ic":
        return base / "ic_schema.json"
    if kind == "device":
        return base / "device_schema.json"
    if kind == "host":
        return base / "host_schema.json"
    if kind == "cartridge":
        return base / "cartridge_schema.json"
    raise ValueError(f"Unknown schema kind: {kind}")


def load_schema(kind: str) -> Dict[str, Any]:
    """Load a JSON schema."""
    with open(get_schema_path(kind), "r", encoding="utf-8") as f:
        return json.load(f)


def expand_register_ranges(registers: list) -> list:
    """Expand register ranges like 'R0..R7' into individual registers."""
    expanded = []
    for reg in registers:
        name = reg.get("name", "")
        if ".." in name:
            base, end = name.split("..")
            prefix = ""
            for i, char in enumerate(base):
                if char.isalpha():
                    prefix = base[: i + 1]
                    break
            start_num = int(base[len(prefix) :])
            end_num = int(end[len(prefix) :])
            for i in range(start_num, end_num + 1):
                reg_copy = copy.deepcopy(reg)
                reg_copy["name"] = f"{prefix}{i}"
                expanded.append(reg_copy)
        else:
            expanded.append(reg)
    return expanded


def _iter_errors(validator: Any, data: Dict[str, Any]) -> list:
    if validator is None:
        return []
    return list(validator.iter_errors(data))


def _format_schema_errors(prefix: str, errors: list) -> str:
    lines = []
    for error in errors:
        path = " -> ".join(str(p) for p in error.path) if error.path else "root"
        lines.append(f"{path}: {error.message}")
    return f"{prefix} validation failed:\n" + "\n".join(lines)


def _validate_flags_layout(flags: list) -> None:
    """Validate hard-cutover flag layout requirements."""
    seen_bits: set[int] = set()
    seen_names: set[str] = set()
    for idx, flag in enumerate(flags):
        name = str(flag.get("name", "")).upper()
        bit = int(flag.get("bit", -1))
        if name in seen_names:
            raise ValidationError(
                f"Processor validation failed:\nflags -> {idx}: duplicate flag name '{name}'"
            )
        seen_names.add(name)
        if bit in seen_bits:
            raise ValidationError(
                f"Processor validation failed:\nflags -> {idx}: duplicate bit position {bit}"
            )
        seen_bits.add(bit)


def _validate_register_parts(registers: list) -> None:
    """Validate inline register subdivision metadata."""
    for reg_idx, reg in enumerate(registers):
        parts = reg.get("parts")
        if not parts:
            continue

        reg_bits = int(reg.get("bits", 0))
        seen_names: set[str] = set()
        occupied_bits: set[int] = set()

        for part_idx, part in enumerate(parts):
            part_name = str(part.get("name", ""))
            part_lsb = int(part.get("lsb", 0))
            part_bits = int(part.get("bits", 0))
            part_msb = part_lsb + part_bits - 1

            if part_name in seen_names:
                raise ValidationError(
                    "Processor validation failed:\n"
                    f"registers -> {reg_idx} -> parts -> {part_idx}: "
                    f"duplicate part name '{part_name}'"
                )
            seen_names.add(part_name)

            if part_msb >= reg_bits:
                raise ValidationError(
                    "Processor validation failed:\n"
                    f"registers -> {reg_idx} -> parts -> {part_idx}: "
                    f"part range [{part_msb}:{part_lsb}] exceeds parent width {reg_bits}"
                )

            for bit in range(part_lsb, part_lsb + part_bits):
                if bit in occupied_bits:
                    raise ValidationError(
                        "Processor validation failed:\n"
                        f"registers -> {reg_idx} -> parts -> {part_idx}: "
                        f"overlapping bit {bit}"
                    )
                occupied_bits.add(bit)


def _validate_endpoint_names(kind: str, component_data: Dict[str, Any]) -> None:
    interfaces = component_data.get("interfaces", {})
    for section in ("callbacks", "handlers", "signals"):
        seen: set[str] = set()
        for idx, endpoint in enumerate(interfaces.get(section, [])):
            name = str(endpoint.get("name", ""))
            if name in seen:
                comp_id = str(component_data.get("metadata", {}).get("id", kind))
                raise ValidationError(
                    f"{kind} validation failed:\n"
                    f"metadata.id={comp_id}: duplicate interfaces.{section}[{idx}].name '{name}'"
                )
            seen.add(name)


def _validate_host_keyboard_input(host_data: Dict[str, Any]) -> None:
    input_cfg = host_data.get("input")
    if input_cfg is None:
        return
    if not isinstance(input_cfg, dict):
        raise ValidationError("Host validation failed:\ninput must be an object")

    keyboard_cfg = input_cfg.get("keyboard")
    if keyboard_cfg is None:
        return
    if not isinstance(keyboard_cfg, dict):
        raise ValidationError("Host validation failed:\ninput.keyboard must be an object")

    source_raw = keyboard_cfg.get("source")
    source = str(source_raw).strip() if source_raw is not None else ""
    if source == "":
        source = "host_key"
    if source != "host_key":
        raise ValidationError(
            "Host validation failed:\ninput.keyboard.source must be 'host_key'"
        )

    focus_required = keyboard_cfg.get("focus_required", True)
    if not isinstance(focus_required, bool):
        raise ValidationError(
            "Host validation failed:\ninput.keyboard.focus_required must be a boolean"
        )

    bindings = keyboard_cfg.get("bindings")
    if not isinstance(bindings, list):
        raise ValidationError(
            "Host validation failed:\ninput.keyboard.bindings must be a list"
        )

    seen_host_keys: set[str] = set()
    for binding_idx, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            raise ValidationError(
                "Host validation failed:\n"
                f"input.keyboard.bindings[{binding_idx}] must be an object"
            )

        host_key = str(binding.get("host_key", "")).strip()
        if not host_key:
            raise ValidationError(
                "Host validation failed:\n"
                f"input.keyboard.bindings[{binding_idx}].host_key must be non-empty"
            )
        if host_key.startswith("SDL_SCANCODE_"):
            raise ValidationError(
                "Host validation failed:\n"
                f"input.keyboard.bindings[{binding_idx}] host_key '{host_key}' must be canonical "
                "(A-Z, 0-9, underscore)"
            )
        if CANONICAL_HOST_KEY_RE.fullmatch(host_key) is None:
            raise ValidationError(
                "Host validation failed:\n"
                f"input.keyboard.bindings[{binding_idx}] host_key '{host_key}' must be canonical "
                "(A-Z, 0-9, underscore)"
            )
        if host_key not in ALLOWED_HOST_KEYS:
            raise ValidationError(
                "Host validation failed:\n"
                f"input.keyboard.bindings[{binding_idx}] host_key '{host_key}' is not supported"
            )

        if host_key in seen_host_keys:
            raise ValidationError(
                "Host validation failed:\n"
                f"input.keyboard.bindings[{binding_idx}] duplicate host_key '{host_key}'"
            )
        seen_host_keys.add(host_key)

        presses = binding.get("presses")
        if not isinstance(presses, list) or not presses:
            raise ValidationError(
                "Host validation failed:\n"
                f"input.keyboard.bindings[{binding_idx}].presses must be a non-empty list"
            )
        for press_idx, press in enumerate(presses):
            if not isinstance(press, dict):
                raise ValidationError(
                    "Host validation failed:\n"
                    f"input.keyboard.bindings[{binding_idx}].presses[{press_idx}] must be an object"
                )
            row = press.get("row")
            bit = press.get("bit")
            if not isinstance(row, int) or not isinstance(bit, int):
                raise ValidationError(
                    "Host validation failed:\n"
                    f"input.keyboard.bindings[{binding_idx}].presses[{press_idx}] row/bit must be integers"
                )
            if row < 0 or row > 31:
                raise ValidationError(
                    "Host validation failed:\n"
                    f"input.keyboard.bindings[{binding_idx}].presses[{press_idx}].row out of range (0..31)"
                )
            if bit < 0 or bit > 7:
                raise ValidationError(
                    "Host validation failed:\n"
                    f"input.keyboard.bindings[{binding_idx}].presses[{press_idx}].bit out of range (0..7)"
                )


def _normalize_and_validate_host_backend(host_data: Dict[str, Any]) -> None:
    backend = host_data.get("backend")
    if backend is None:
        return

    if not isinstance(backend, dict):
        raise ValidationError(
            "Host validation failed:\nbackend must be an object when provided"
        )
    target = str(backend.get("target", "")).strip()
    if not target:
        raise ValidationError(
            "Host validation failed:\nbackend.target must be a non-empty string"
        )
    if CANONICAL_BACKEND_TARGET_RE.fullmatch(target) is None:
        raise ValidationError(
            "Host validation failed:\nbackend.target must match ^[a-z][a-z0-9_]*$"
        )
    if target not in SUPPORTED_HOST_BACKEND_TARGETS:
        raise ValidationError(
            "Host validation failed:\n"
            f"backend.target '{target}' is not supported; expected one of "
            f"{sorted(SUPPORTED_HOST_BACKEND_TARGETS)}"
        )
    host_data["backend"] = {"target": target}


def _normalize_host_backend_target_selection(
    host_data_list: List[Dict[str, Any]], host_backend_target: str | None
) -> str:
    declared_targets: list[str] = []
    for host_data in host_data_list:
        backend = host_data.get("backend")
        if isinstance(backend, dict):
            target = str(backend.get("target", "")).strip().lower()
            if target:
                declared_targets.append(target)

    if not host_data_list:
        if host_backend_target:
            target = str(host_backend_target).strip().lower()
            if CANONICAL_BACKEND_TARGET_RE.fullmatch(target) is None:
                raise ValidationError(
                    "Composition validation failed:\n"
                    "--host-backend must match ^[a-z][a-z0-9_]*$"
                )
            if target not in SUPPORTED_HOST_BACKEND_TARGETS:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"unsupported --host-backend '{target}'; expected one of "
                    f"{sorted(SUPPORTED_HOST_BACKEND_TARGETS)}"
                )
        return ""

    unique_declared = sorted(set(declared_targets))
    if len(unique_declared) > 1:
        raise ValidationError(
            "Composition validation failed:\n"
            f"multiple host backend targets are not supported: {unique_declared}"
        )
    inferred_target = unique_declared[0] if unique_declared else ""
    if inferred_target and inferred_target not in SUPPORTED_HOST_BACKEND_TARGETS:
        raise ValidationError(
            "Composition validation failed:\n"
            f"unsupported host backend target '{inferred_target}'; expected one of "
            f"{sorted(SUPPORTED_HOST_BACKEND_TARGETS)}"
        )

    if host_backend_target is None:
        return inferred_target
    target = str(host_backend_target).strip().lower()
    if not target:
        raise ValidationError(
            "Composition validation failed:\n"
            "--host-backend must be a non-empty string"
        )
    if CANONICAL_BACKEND_TARGET_RE.fullmatch(target) is None:
        raise ValidationError(
            "Composition validation failed:\n"
            "--host-backend must match ^[a-z][a-z0-9_]*$"
        )
    if target not in SUPPORTED_HOST_BACKEND_TARGETS:
        raise ValidationError(
            "Composition validation failed:\n"
            f"unsupported --host-backend '{target}'; expected one of "
            f"{sorted(SUPPORTED_HOST_BACKEND_TARGETS)}"
        )
    if inferred_target and target != inferred_target:
        raise ValidationError(
            "Composition validation failed:\n"
            f"--host-backend '{target}' conflicts with host backend.target '{inferred_target}'"
        )
    return target


def _instruction_field_widths(inst: Dict[str, Any]) -> Dict[str, int]:
    widths = dict(BASE_DECODED_FIELD_WIDTHS)
    encoding = inst.get("encoding", {})
    for field in encoding.get("fields", []):
        name = str(field.get("name", "")).strip()
        if not name:
            continue
        width = field.get("width")
        if width is None:
            position = field.get("position", [0, 0])
            try:
                msb = int(position[0])
                lsb = int(position[1])
            except (TypeError, ValueError, IndexError):
                continue
            width = (msb - lsb + 1)
        try:
            widths[name] = max(1, int(width))
        except (TypeError, ValueError):
            continue
    return widths


class ProcessorSystemLoader:
    """Load and validate processor/system/ic/device definitions, then compose them."""

    def __init__(self):
        self.processor_schema = load_schema("processor")
        self.system_schema = load_schema("system")
        self.ic_schema = load_schema("ic")
        self.device_schema = load_schema("device")
        self.host_schema = load_schema("host")
        self.cartridge_schema = load_schema("cartridge")
        if Draft7Validator:
            self.processor_validator = Draft7Validator(self.processor_schema)
            self.system_validator = Draft7Validator(self.system_schema)
            self.ic_validator = Draft7Validator(self.ic_schema)
            self.device_validator = Draft7Validator(self.device_schema)
            self.host_validator = Draft7Validator(self.host_schema)
            self.cartridge_validator = Draft7Validator(self.cartridge_schema)
        else:
            self.processor_validator = None
            self.system_validator = None
            self.ic_validator = None
            self.device_validator = None
            self.host_validator = None
            self.cartridge_validator = None

    def _resolve_existing_file(self, path: str) -> Path:
        path_obj = Path(path)
        if path_obj.exists() and path_obj.is_file():
            return path_obj.resolve()
        parent = path_obj.parent
        if parent.exists():
            matches = [p.resolve() for p in parent.rglob(path_obj.name) if p.is_file()]
            if len(matches) == 1:
                return matches[0]
        return path_obj

    def _load_yaml(self, path: str, kind: str) -> Dict[str, Any]:
        path_obj = self._resolve_existing_file(path)
        if not path_obj.exists() or not path_obj.is_file():
            raise FileNotFoundError(f"{kind} file not found: {path}")
        with open(path_obj, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data is None:
            raise ValueError(f"Empty {kind} file: {path}")
        if not isinstance(data, dict):
            raise ValueError(f"{kind} YAML root must be an object: {path}")
        return data

    def _validate_coding_block(self, coding: Dict[str, Any], context: str) -> None:
        if not isinstance(coding, dict):
            raise ValidationError(f"{context} validation failed:\ncoding must be an object")

        for field in ("headers", "include_paths", "library_paths"):
            values = coding.get(field, [])
            if not isinstance(values, list) or not all(
                isinstance(item, str) and item.strip() for item in values
            ):
                raise ValidationError(
                    f"{context} validation failed:\ncoding.{field} must be a list of non-empty strings"
                )

        libs = coding.get("linked_libraries", [])
        if not isinstance(libs, list):
            raise ValidationError(
                f"{context} validation failed:\ncoding.linked_libraries must be a list"
            )
        for idx, lib in enumerate(libs):
            if not isinstance(lib, dict):
                raise ValidationError(
                    f"{context} validation failed:\n"
                    f"coding.linked_libraries[{idx}] must be an object"
                )
            name = lib.get("name")
            path = lib.get("path")
            if bool(name) == bool(path):
                raise ValidationError(
                    f"{context} validation failed:\n"
                    f"coding.linked_libraries[{idx}] must define exactly one of 'name' or 'path'"
                )
            if name is not None and (not isinstance(name, str) or not name.strip()):
                raise ValidationError(
                    f"{context} validation failed:\n"
                    f"coding.linked_libraries[{idx}].name must be a non-empty string"
                )
            if path is not None and (not isinstance(path, str) or not path.strip()):
                raise ValidationError(
                    f"{context} validation failed:\n"
                    f"coding.linked_libraries[{idx}].path must be a non-empty string"
                )

    def _resolve_coding_paths(self, coding: Dict[str, Any], source_path: str) -> Dict[str, Any]:
        base_dir = Path(source_path).resolve().parent

        def _resolve_paths(items: list[str]) -> list[str]:
            resolved = []
            for item in items:
                path = Path(item)
                if path.is_absolute():
                    resolved.append(str(path))
                else:
                    resolved.append(str((base_dir / path).resolve()))
            return resolved

        resolved_libs = []
        for lib in coding.get("linked_libraries", []):
            if "name" in lib:
                resolved_libs.append({"name": str(lib["name"])})
            else:
                path = Path(str(lib["path"]))
                if path.is_absolute():
                    resolved_libs.append({"path": str(path)})
                else:
                    resolved_libs.append({"path": str((base_dir / path).resolve())})

        return {
            "headers": [str(item) for item in coding.get("headers", [])],
            "include_paths": _resolve_paths([str(item) for item in coding.get("include_paths", [])]),
            "linked_libraries": resolved_libs,
            "library_paths": _resolve_paths([str(item) for item in coding.get("library_paths", [])]),
        }

    def _merge_coding(self, sources: List[Dict[str, Any]]) -> Dict[str, Any]:
        merged = {
            "headers": [],
            "include_paths": [],
            "linked_libraries": [],
            "library_paths": [],
        }
        seen_scalars = {
            "headers": set(),
            "include_paths": set(),
            "library_paths": set(),
        }
        seen_libs: set[str] = set()

        for source in sources:
            for field in ("headers", "include_paths", "library_paths"):
                for value in source.get(field, []):
                    if value not in seen_scalars[field]:
                        seen_scalars[field].add(value)
                        merged[field].append(value)

            for lib in source.get("linked_libraries", []):
                key = json.dumps(lib, sort_keys=True)
                if key not in seen_libs:
                    seen_libs.add(key)
                    merged["linked_libraries"].append(copy.deepcopy(lib))

        return merged

    def _normalize_port_map(
        self, port_map: Dict[str, Any], bus_bits: int, comp_id: str, direction: str, idx: int
    ) -> set[int]:
        max_port = 1 << bus_bits
        mask = int(port_map.get("mask", 0))
        value = int(port_map.get("value", 0))
        if mask < 0 or value < 0:
            raise ValidationError(
                "Composition validation failed:\n"
                f"metadata.id={comp_id}: maps.ports.{direction}[{idx}] mask/value must be non-negative"
            )
        if bus_bits > 16:
            raise ValidationError(
                "Composition validation failed:\n"
                f"metadata.id={comp_id}: port bus wider than 16 bits is not supported in v1"
            )

        matched: set[int] = set()
        for port in range(max_port):
            if (port & mask) == value:
                matched.add(port)
        return matched

    def _validate_timing_profiles_required(
        self, processor_data: Dict[str, Any], require_profiles: bool
    ) -> None:
        if not require_profiles:
            return

        for idx, inst in enumerate(processor_data.get("instructions", [])):
            profile = inst.get("timing_profile")
            if not isinstance(profile, dict):
                raise ValidationError(
                    "Composition validation failed:\n"
                    "Component-enabled generation requires instruction timing_profile.\n"
                    f"Missing in instructions[{idx}] ({inst.get('name', 'UNKNOWN')})"
                )
            total_tstates = int(profile.get("total_tstates", 0))
            cycles = int(inst.get("cycles", 0))
            if total_tstates != cycles:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"instructions[{idx}] ({inst.get('name', 'UNKNOWN')}): "
                    f"timing_profile.total_tstates ({total_tstates}) must equal cycles ({cycles})"
                )
            for ev_idx, bus_event in enumerate(profile.get("bus_events", [])):
                t_offset = int(bus_event.get("t_offset", -1))
                if t_offset < 0 or t_offset >= total_tstates:
                    raise ValidationError(
                        "Composition validation failed:\n"
                        f"instructions[{idx}] ({inst.get('name', 'UNKNOWN')}) "
                        f"timing_profile.bus_events[{ev_idx}].t_offset ({t_offset}) out of range [0, {total_tstates})"
                    )

    def _extract_endpoint_arity(self, component_data: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
        interfaces = component_data.get("interfaces", {})
        arity: Dict[str, Dict[str, int]] = {
            "callback": {},
            "handler": {},
            "signal": {},
        }

        for endpoint in interfaces.get("callbacks", []):
            arity["callback"][str(endpoint.get("name", ""))] = len(endpoint.get("args", []))
        for endpoint in interfaces.get("handlers", []):
            arity["handler"][str(endpoint.get("name", ""))] = len(endpoint.get("args", []))
        for endpoint in interfaces.get("signals", []):
            arity["signal"][str(endpoint.get("name", ""))] = len(endpoint.get("args", []))
        return arity

    def _validate_component_behavior(self, kind: str, component_data: Dict[str, Any]) -> None:
        behavior = component_data.get("behavior", {})
        snippets = behavior.get("snippets", {})
        callback_handlers = behavior.get("callback_handlers", {})
        handler_bodies = behavior.get("handler_bodies", {})

        if not isinstance(snippets, dict):
            raise ValidationError(f"{kind} validation failed:\nbehavior.snippets must be an object")
        if not isinstance(callback_handlers, dict):
            raise ValidationError(
                f"{kind} validation failed:\nbehavior.callback_handlers must be an object"
            )
        if not isinstance(handler_bodies, dict):
            raise ValidationError(
                f"{kind} validation failed:\nbehavior.handler_bodies must be an object"
            )

        for label, mapping in (
            ("behavior.snippets", snippets),
            ("behavior.callback_handlers", callback_handlers),
            ("behavior.handler_bodies", handler_bodies),
        ):
            for key, value in mapping.items():
                if not isinstance(value, str):
                    raise ValidationError(
                        f"{kind} validation failed:\n{label}.{key} must be a C snippet string"
                    )

        arity = self._extract_endpoint_arity(component_data)
        for name in callback_handlers.keys():
            if name not in arity["callback"]:
                raise ValidationError(
                    f"{kind} validation failed:\n"
                    f"behavior.callback_handlers.{name} does not match interfaces.callbacks"
                )
        for name in handler_bodies.keys():
            if name not in arity["handler"]:
                raise ValidationError(
                    f"{kind} validation failed:\n"
                    f"behavior.handler_bodies.{name} does not match interfaces.handlers"
                )

    def validate_ic(self, ic_data: Dict[str, Any]) -> Dict[str, Any]:
        errors = _iter_errors(self.ic_validator, ic_data)
        if errors:
            raise ValidationError(_format_schema_errors("IC", errors))

        self._validate_coding_block(ic_data.get("coding", {}), "IC")
        self._validate_component_behavior("IC", ic_data)
        _validate_endpoint_names("IC", ic_data)

        return ic_data

    def validate_device(self, device_data: Dict[str, Any]) -> Dict[str, Any]:
        errors = _iter_errors(self.device_validator, device_data)
        if errors:
            raise ValidationError(_format_schema_errors("Device", errors))

        self._validate_coding_block(device_data.get("coding", {}), "Device")
        self._validate_component_behavior("Device", device_data)
        _validate_endpoint_names("Device", device_data)

        return device_data

    def validate_host(self, host_data: Dict[str, Any]) -> Dict[str, Any]:
        errors = _iter_errors(self.host_validator, host_data)
        if errors:
            raise ValidationError(_format_schema_errors("Host", errors))

        self._validate_coding_block(host_data.get("coding", {}), "Host")
        self._validate_component_behavior("Host", host_data)
        _validate_endpoint_names("Host", host_data)
        _validate_host_keyboard_input(host_data)
        _normalize_and_validate_host_backend(host_data)

        return host_data

    def _validate_cartridge_state_contract(self, cartridge_data: Dict[str, Any]) -> None:
        state_entries = cartridge_data.get("state", [])
        state_names = {str(entry.get("name", "")) for entry in state_entries}
        missing = [name for name in ("rom_data", "rom_size") if name not in state_names]
        if missing:
            cart_id = str(cartridge_data.get("metadata", {}).get("id", "cartridge"))
            raise ValidationError(
                "Cartridge validation failed:\n"
                f"metadata.id={cart_id}: missing required state field(s): {', '.join(missing)}"
            )

    def validate_cartridge(self, cartridge_data: Dict[str, Any]) -> Dict[str, Any]:
        errors = _iter_errors(self.cartridge_validator, cartridge_data)
        if errors:
            raise ValidationError(_format_schema_errors("Cartridge", errors))

        self._validate_coding_block(cartridge_data.get("coding", {}), "Cartridge")
        self._validate_component_behavior("Cartridge", cartridge_data)
        _validate_endpoint_names("Cartridge", cartridge_data)
        self._validate_cartridge_state_contract(cartridge_data)
        return cartridge_data

    def _validate_instruction_display_specs(self, processor_data: Dict[str, Any]) -> None:
        for idx, inst in enumerate(processor_data.get("instructions", [])):
            name = str(inst.get("name", f"INST_{idx}"))
            fields = _instruction_field_widths(inst)
            display_template = inst.get("display_template")
            display_operands = inst.get("display_operands", {})

            if display_operands is None:
                display_operands = {}
            if not isinstance(display_operands, dict):
                raise ValidationError(
                    "Processor validation failed:\n"
                    f"instructions -> {idx} ({name}): display_operands must be an object"
                )

            for field_name, spec in display_operands.items():
                if field_name not in fields:
                    raise ValidationError(
                        "Processor validation failed:\n"
                        f"instructions -> {idx} ({name}): "
                        f"display_operands.{field_name} references unknown decoded field"
                    )
                if not isinstance(spec, dict):
                    raise ValidationError(
                        "Processor validation failed:\n"
                        f"instructions -> {idx} ({name}): "
                        f"display_operands.{field_name} must be an object"
                    )
                kind = str(spec.get("kind", "")).strip()
                if kind not in DISPLAY_RENDER_KINDS:
                    raise ValidationError(
                        "Processor validation failed:\n"
                        f"instructions -> {idx} ({name}): "
                        f"display_operands.{field_name}.kind '{kind}' is not supported"
                    )
                if kind in TABLE_RENDER_KINDS:
                    table = spec.get("table")
                    if not isinstance(table, list) or not table or not all(
                        isinstance(item, str) and item for item in table
                    ):
                        raise ValidationError(
                            "Processor validation failed:\n"
                            f"instructions -> {idx} ({name}): "
                            f"display_operands.{field_name}.table must be a non-empty string list"
                        )

            if display_template is None:
                continue
            if not isinstance(display_template, str):
                raise ValidationError(
                    "Processor validation failed:\n"
                    f"instructions -> {idx} ({name}): display_template must be a string"
                )

            template_skeleton = DISPLAY_TEMPLATE_TOKEN_RE.sub("", display_template)
            if "{" in template_skeleton or "}" in template_skeleton:
                raise ValidationError(
                    "Processor validation failed:\n"
                    f"instructions -> {idx} ({name}): display_template contains malformed token braces"
                )

            for token_match in DISPLAY_TEMPLATE_TOKEN_RE.finditer(display_template):
                field_name, formatter = token_match.groups()
                if field_name not in fields:
                    raise ValidationError(
                        "Processor validation failed:\n"
                        f"instructions -> {idx} ({name}): "
                        f"display_template token '{field_name}' references unknown decoded field"
                    )
                if formatter and formatter not in DISPLAY_RENDER_KINDS:
                    raise ValidationError(
                        "Processor validation failed:\n"
                        f"instructions -> {idx} ({name}): "
                        f"display_template formatter '{formatter}' is not supported"
                    )

    def validate_processor(self, processor_data: Dict[str, Any]) -> Dict[str, Any]:
        errors = _iter_errors(self.processor_validator, processor_data)
        if errors:
            raise ValidationError(_format_schema_errors("Processor", errors))

        if "registers" in processor_data:
            processor_data["registers"] = expand_register_ranges(processor_data["registers"])

        _validate_flags_layout(processor_data.get("flags", []))
        _validate_register_parts(processor_data.get("registers", []))
        self._validate_coding_block(processor_data.get("coding", {}), "Processor")
        self._validate_instruction_display_specs(processor_data)

        return processor_data

    def validate_system(self, system_data: Dict[str, Any]) -> Dict[str, Any]:
        errors = _iter_errors(self.system_validator, system_data)
        if errors:
            raise ValidationError(_format_schema_errors("System", errors))

        hooks = system_data.get("hooks", {})
        invalid_hooks = sorted(name for name in hooks.keys() if name not in HOOK_NAMES)
        if invalid_hooks:
            raise ValidationError(
                "System validation failed:\n"
                f"hooks: unsupported hook names: {', '.join(invalid_hooks)}"
            )

        return system_data

    def _region_is_read_only(self, region: Dict[str, Any]) -> bool:
        if bool(region.get("read_only", False)):
            return True
        if "read_write" in region and not bool(region.get("read_write")):
            return True
        return False

    @staticmethod
    def _host_id_aliases(component_id: str) -> List[str]:
        cid = str(component_id).strip()
        aliases: List[str] = []
        if not cid:
            return aliases
        aliases.append(cid)
        if cid.endswith("_sdl2"):
            aliases.append(cid[: -len("_sdl2")])
        else:
            aliases.append(f"{cid}_sdl2")
        return aliases

    def _resolve_system_rom_images(
        self, system_data: Dict[str, Any], system_path: str
    ) -> List[Dict[str, Any]]:
        base_dir = Path(system_path).resolve().parent
        resolved: List[Dict[str, Any]] = []
        for rom in system_data.get("memory", {}).get("rom_images", []):
            rom_copy = copy.deepcopy(rom)
            raw_file = str(rom_copy.get("file", "")).strip()
            path_obj = Path(raw_file)
            if path_obj.is_absolute():
                rom_copy["_resolved_file"] = str(path_obj)
            else:
                rom_copy["_resolved_file"] = str((base_dir / path_obj).resolve())
            resolved.append(rom_copy)
        return resolved

    def _resolve_cli_file(self, path: str, base_dir: Path) -> Path:
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return (base_dir / path_obj).resolve()

    def _validate_readable_file(
        self,
        path: str,
        *,
        error_prefix: str = "Composition validation failed",
        base_dir: Path | None = None,
    ) -> str:
        if not path or not str(path).strip():
            raise ValidationError(f"{error_prefix}:\npath must be non-empty")
        if base_dir is None:
            resolved = Path(path).resolve()
        else:
            resolved = self._resolve_cli_file(path, base_dir)
        if not resolved.exists() or not resolved.is_file():
            raise ValidationError(f"{error_prefix}:\nfile not found: {resolved}")
        return str(resolved)

    def _validate_rom_images(
        self,
        memory: Dict[str, Any],
        default_size: int,
    ) -> List[Dict[str, Any]]:
        regions = list(memory.get("regions", []))
        region_by_name: Dict[str, Dict[str, Any]] = {
            str(region.get("name", "")): region for region in regions
        }
        placed_ranges: List[Tuple[int, int, str]] = []
        validated_roms: List[Dict[str, Any]] = []

        for idx, rom in enumerate(memory.get("rom_images", [])):
            rom_name = str(rom.get("name", f"rom_{idx}"))
            target_region_name = str(rom.get("target_region", ""))
            target_region = region_by_name.get(target_region_name)
            if target_region is None:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"system.memory.rom_images[{idx}] target_region '{target_region_name}' does not exist"
                )
            offset = int(rom.get("offset", 0))
            if offset < 0:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"system.memory.rom_images[{idx}].offset must be non-negative"
                )

            region_start = int(target_region.get("start", 0))
            region_size = int(target_region.get("size", 0))
            if region_start < 0 or region_size < 0 or region_start + region_size > default_size:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"target region '{target_region_name}' is outside memory.default_size bounds"
                )

            resolved_file = str(rom.get("_resolved_file", ""))
            if not resolved_file:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"system.memory.rom_images[{idx}] failed to resolve rom file path"
                )

            rom_path = Path(resolved_file)
            if not rom_path.exists() or not rom_path.is_file():
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"system.memory.rom_images[{idx}] file not found: {resolved_file}"
                )

            file_size = int(rom_path.stat().st_size)
            if offset + file_size > region_size:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"system.memory.rom_images[{idx}] ({rom_name}) exceeds target_region '{target_region_name}' size"
                )

            address = region_start + offset
            end = address + file_size
            if end > default_size:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"system.memory.rom_images[{idx}] ({rom_name}) exceeds memory.default_size"
                )

            placed_ranges.append((address, end, rom_name))
            validated = copy.deepcopy(rom)
            validated["offset"] = offset
            validated["address"] = address
            validated["size"] = file_size
            validated_roms.append(validated)

        placed_ranges.sort(key=lambda item: (item[0], item[1]))
        for idx in range(1, len(placed_ranges)):
            prev_start, prev_end, prev_name = placed_ranges[idx - 1]
            cur_start, cur_end, cur_name = placed_ranges[idx]
            if cur_start < prev_end:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"system.memory.rom_images overlap: '{prev_name}' [{prev_start:#06x},{prev_end:#06x}) "
                    f"vs '{cur_name}' [{cur_start:#06x},{cur_end:#06x})"
                )

        return validated_roms

    def _validate_connection_graph(
        self,
        system_data: Dict[str, Any],
        endpoint_arity: Dict[str, Dict[str, Dict[str, int]]],
    ) -> None:
        for idx, conn in enumerate(system_data.get("connections", [])):
            from_ep = conn.get("from", {})
            to_ep = conn.get("to", {})
            from_component = str(from_ep.get("component", ""))
            to_component = str(to_ep.get("component", ""))
            from_kind = str(from_ep.get("kind", ""))
            to_kind = str(to_ep.get("kind", ""))
            from_name = str(from_ep.get("name", ""))
            to_name = str(to_ep.get("name", ""))

            if from_component == "host" or to_component == "host":
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"connections[{idx}]: literal component 'host' is removed; use a declared host component id"
                )

            if from_kind == "callback" and to_kind != "callback":
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"connections[{idx}]: callback sources must target callbacks"
                )
            if from_kind == "signal" and to_kind != "handler":
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"connections[{idx}]: signal sources must target handlers"
                )

            if from_component not in endpoint_arity:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"connections[{idx}]: unknown source component '{from_component}'"
                )
            if from_name not in endpoint_arity[from_component].get(from_kind, {}):
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"connections[{idx}]: source endpoint {from_component}.{from_kind}.{from_name} not declared"
                )

            if to_component not in endpoint_arity:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"connections[{idx}]: unknown target component '{to_component}'"
                )
            if to_name not in endpoint_arity[to_component].get(to_kind, {}):
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"connections[{idx}]: target endpoint {to_component}.{to_kind}.{to_name} not declared"
                )

            from_count = endpoint_arity[from_component][from_kind][from_name]
            to_count = endpoint_arity[to_component][to_kind][to_name]
            if from_count != to_count:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"connections[{idx}]: arity mismatch {from_component}.{from_kind}.{from_name} ({from_count}) "
                    f"-> {to_component}.{to_kind}.{to_name} ({to_count})"
                )

    def compose(
        self,
        processor_data: Dict[str, Any],
        system_data: Dict[str, Any],
        ic_data_list: List[Dict[str, Any]] | None = None,
        device_data_list: List[Dict[str, Any]] | None = None,
        host_data_list: List[Dict[str, Any]] | None = None,
        cartridge_data: Dict[str, Any] | None = None,
        cartridge_rom_path: str | None = None,
        coding_sources: List[Dict[str, Any]] | None = None,
        host_backend_target: str = "",
    ) -> Dict[str, Any]:
        if ic_data_list is None:
            ic_data_list = []
        if device_data_list is None:
            device_data_list = []
        if host_data_list is None:
            host_data_list = []
        if cartridge_data is None:
            cartridge_data = {}
        if coding_sources is None:
            coding_sources = []

        address_bits = int(processor_data.get("metadata", {}).get("address_bits", 0))
        max_memory_size = 1 << address_bits
        memory = system_data.get("memory", {})
        default_size = int(memory.get("default_size", 0))
        ports_cfg = processor_data.get("ports", {})
        port_bits = int(ports_cfg.get("address_bits", 8))
        max_port = 1 << port_bits

        if default_size <= 0:
            raise ValidationError(
                "Composition validation failed:\n"
                "system.memory.default_size must be > 0"
            )
        if default_size > max_memory_size:
            raise ValidationError(
                "Composition validation failed:\n"
                f"system.memory.default_size ({default_size}) exceeds processor address space ({max_memory_size})"
            )

        for idx, region in enumerate(memory.get("regions", [])):
            start = int(region.get("start", 0))
            size = int(region.get("size", 0))
            if start < 0:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"system.memory.regions[{idx}].start must be non-negative"
                )
            if size < 0:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"system.memory.regions[{idx}].size must be non-negative"
                )
            if start + size > default_size:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"system.memory.regions[{idx}] exceeds default_size ({default_size})"
                )

        has_components = bool(
            ic_data_list or device_data_list or host_data_list or cartridge_data
        )
        self._validate_timing_profiles_required(processor_data, has_components)

        system_components = system_data.get("components", {})
        configured_ic_ids = [str(item) for item in system_components.get("ics", [])]
        configured_device_ids = [str(item) for item in system_components.get("devices", [])]
        configured_host_ids = [str(item) for item in system_components.get("hosts", [])]
        configured_cartridge_id = str(system_components.get("cartridge", "")).strip()
        loaded_ic_ids = [str(ic.get("metadata", {}).get("id", "")) for ic in ic_data_list]
        loaded_device_ids = [str(dev.get("metadata", {}).get("id", "")) for dev in device_data_list]
        loaded_host_ids = [str(host.get("metadata", {}).get("id", "")) for host in host_data_list]
        loaded_cartridge_id = str(cartridge_data.get("metadata", {}).get("id", "")).strip()

        host_id_map: Dict[str, str] = {}
        for configured_id in configured_host_ids:
            if configured_id in loaded_host_ids:
                host_id_map[configured_id] = configured_id
                continue
            matches = [
                loaded_id
                for loaded_id in loaded_host_ids
                if configured_id in self._host_id_aliases(loaded_id)
                or loaded_id in self._host_id_aliases(configured_id)
            ]
            if len(matches) == 1:
                host_id_map[configured_id] = matches[0]

        if any(host_id_map.get(cid, cid) != cid for cid in configured_host_ids):
            system_data = copy.deepcopy(system_data)
            system_components = system_data.setdefault("components", {})
            system_components["hosts"] = [
                host_id_map.get(component_id, component_id)
                for component_id in configured_host_ids
            ]
            for conn in system_data.get("connections", []):
                from_ep = conn.get("from", {})
                to_ep = conn.get("to", {})
                from_component = str(from_ep.get("component", ""))
                to_component = str(to_ep.get("component", ""))
                if from_component in host_id_map:
                    from_ep["component"] = host_id_map[from_component]
                if to_component in host_id_map:
                    to_ep["component"] = host_id_map[to_component]
            configured_host_ids = [
                str(item) for item in system_components.get("hosts", [])
            ]

        if set(configured_ic_ids) != set(loaded_ic_ids):
            raise ValidationError(
                "Composition validation failed:\n"
                "system.components.ics must match loaded --ic files exactly"
            )
        if set(configured_device_ids) != set(loaded_device_ids):
            raise ValidationError(
                "Composition validation failed:\n"
                "system.components.devices must match loaded --device files exactly"
            )
        if set(configured_host_ids) != set(loaded_host_ids):
            configured_aliases = {
                alias
                for cid in configured_host_ids
                for alias in self._host_id_aliases(cid)
            }
            loaded_aliases = {
                alias
                for cid in loaded_host_ids
                for alias in self._host_id_aliases(cid)
            }
            if configured_aliases.isdisjoint(loaded_aliases):
                raise ValidationError(
                    "Composition validation failed:\n"
                    "system.components.hosts must match loaded --host files exactly"
                )
        if configured_cartridge_id:
            if loaded_cartridge_id:
                if configured_cartridge_id != loaded_cartridge_id:
                    raise ValidationError(
                        "Composition validation failed:\n"
                        "system.components.cartridge must match loaded --cartridge-map metadata.id"
                    )
                if not cartridge_rom_path:
                    raise ValidationError(
                        "Composition validation failed:\n"
                        "system.components.cartridge requires --cartridge-rom"
                    )
            elif cartridge_rom_path:
                raise ValidationError(
                    "Composition validation failed:\n"
                    "system.components.cartridge requires --cartridge-map when --cartridge-rom is provided"
                )
        else:
            if loaded_cartridge_id or cartridge_rom_path:
                raise ValidationError(
                    "Composition validation failed:\n"
                    "system has no cartridge slot but --cartridge-map/--cartridge-rom was provided"
                )

        seen_component_ids: set[str] = set()
        all_loaded_ids = loaded_ic_ids + loaded_device_ids + loaded_host_ids
        if loaded_cartridge_id:
            all_loaded_ids.append(loaded_cartridge_id)
        for comp_id in all_loaded_ids:
            if not comp_id:
                raise ValidationError(
                    "Composition validation failed:\ncomponent metadata.id must not be empty"
                )
            if comp_id in seen_component_ids:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"duplicate component metadata.id '{comp_id}'"
                )
            seen_component_ids.add(comp_id)

        # Port/memory interception overlap validation.
        claimed_mem_ranges: list[tuple[int, int, str]] = []
        # Port ownership is direction-sensitive. SMS-style buses legitimately
        # share numeric ports between read and write paths.
        claimed_ports: dict[tuple[str, int], str] = {}
        mapped_components = list(ic_data_list)
        if loaded_cartridge_id:
            mapped_components.append(cartridge_data)
        for mapped in mapped_components:
            comp_id = str(mapped.get("metadata", {}).get("id", "component"))
            for range_idx, mem_range in enumerate(
                mapped.get("maps", {}).get("memory", {}).get("ranges", [])
            ):
                start = int(mem_range.get("start", 0))
                size = int(mem_range.get("size", 0))
                end = start + size
                if start < 0 or size < 0 or end > default_size:
                    raise ValidationError(
                        "Composition validation failed:\n"
                        f"component '{comp_id}' maps.memory.ranges[{range_idx}] exceeds system memory bounds"
                    )
                claimed_mem_ranges.append((start, end, comp_id))

            for direction in ("read", "write"):
                for map_idx, port_map in enumerate(
                    mapped.get("maps", {}).get("ports", {}).get(direction, [])
                ):
                    matched_ports = self._normalize_port_map(
                        port_map, port_bits, comp_id, direction, map_idx
                    )
                    for port in matched_ports:
                        owner = claimed_ports.get((direction, port))
                        if owner is not None and owner != comp_id:
                            raise ValidationError(
                                "Composition validation failed:\n"
                                f"component port mapping overlap ({direction}) at port 0x{port:04X}: "
                                f"'{owner}' vs '{comp_id}'"
                            )
                        if port >= max_port:
                            raise ValidationError(
                                "Composition validation failed:\n"
                                f"component '{comp_id}' port mapping exceeds processor port width"
                            )
                        claimed_ports[(direction, port)] = comp_id

        claimed_mem_ranges.sort(key=lambda item: (item[0], item[1]))
        for idx in range(1, len(claimed_mem_ranges)):
            prev_start, prev_end, prev_id = claimed_mem_ranges[idx - 1]
            cur_start, cur_end, cur_id = claimed_mem_ranges[idx]
            if cur_start < prev_end and cur_id != prev_id:
                raise ValidationError(
                    "Composition validation failed:\n"
                    f"component memory interception overlap: '{prev_id}' [{prev_start:#06x},{prev_end:#06x}) "
                    f"vs '{cur_id}' [{cur_start:#06x},{cur_end:#06x})"
                )

        validated_rom_images = self._validate_rom_images(memory, default_size)

        endpoint_arity: Dict[str, Dict[str, Dict[str, int]]] = {}
        for component in ic_data_list + device_data_list + host_data_list:
            component_id = str(component.get("metadata", {}).get("id", ""))
            arity = self._extract_endpoint_arity(component)
            endpoint_arity[component_id] = arity
            if component in host_data_list:
                for alias_id in self._host_id_aliases(component_id):
                    endpoint_arity.setdefault(alias_id, arity)
        if loaded_cartridge_id:
            endpoint_arity[loaded_cartridge_id] = self._extract_endpoint_arity(cartridge_data)

        self._validate_connection_graph(system_data, endpoint_arity)

        combined = {
            "metadata": copy.deepcopy(processor_data.get("metadata", {})),
            "registers": copy.deepcopy(processor_data.get("registers", [])),
            "flags": copy.deepcopy(processor_data.get("flags", [])),
            "instructions": copy.deepcopy(processor_data.get("instructions", [])),
            "coding": self._merge_coding(coding_sources),
            "memory": {
                "address_bits": address_bits,
                "default_size": default_size,
                "regions": copy.deepcopy(memory.get("regions", [])),
                "rom_images": copy.deepcopy(validated_rom_images),
            },
            "ports": copy.deepcopy(processor_data.get("ports", {})),
            "interrupts": copy.deepcopy(processor_data.get("interrupts", {})),
            "hooks": copy.deepcopy(system_data.get("hooks", {})),
            "ics": copy.deepcopy(ic_data_list),
            "devices": copy.deepcopy(device_data_list),
            "hosts": copy.deepcopy(host_data_list),
            "cartridge": copy.deepcopy(cartridge_data) if loaded_cartridge_id else {},
            "cartridge_rom": {
                "path": str(cartridge_rom_path or ""),
            },
            "components": copy.deepcopy(system_data.get("components", {})),
            "connections": copy.deepcopy(system_data.get("connections", [])),
            "audio": copy.deepcopy(system_data.get("audio", {})),
            "system": {
                "metadata": copy.deepcopy(system_data.get("metadata", {})),
                "clock_hz": int(system_data.get("clock_hz", 0)),
                "reset_delay_seconds": int(system_data.get("reset_delay_seconds", 0)),
                "integrations": copy.deepcopy(system_data.get("integrations", {})),
            },
            "host_backend_target": str(host_backend_target or ""),
        }

        return combined

    def load(
        self,
        processor_path: str,
        system_path: str,
        ic_paths: List[str] | None = None,
        device_paths: List[str] | None = None,
        host_paths: List[str] | None = None,
        cartridge_path: str | None = None,
        cartridge_rom_path: str | None = None,
        host_backend_target: str | None = None,
    ) -> Dict[str, Any]:
        if ic_paths is None:
            ic_paths = []
        if device_paths is None:
            device_paths = []
        if host_paths is None:
            host_paths = []

        resolved_processor_path = str(self._resolve_existing_file(processor_path))
        resolved_system_path = str(self._resolve_existing_file(system_path))
        resolved_ic_paths = [str(self._resolve_existing_file(path)) for path in ic_paths]
        resolved_device_paths = [
            str(self._resolve_existing_file(path)) for path in device_paths
        ]
        resolved_host_paths = [str(self._resolve_existing_file(path)) for path in host_paths]

        processor_data = self._load_yaml(resolved_processor_path, "processor")
        system_data = self._load_yaml(resolved_system_path, "system")
        ic_data_list = [self._load_yaml(path, "ic") for path in resolved_ic_paths]
        device_data_list = [self._load_yaml(path, "device") for path in resolved_device_paths]
        host_data_list = [self._load_yaml(path, "host") for path in resolved_host_paths]
        cartridge_data = {}
        if cartridge_path:
            resolved_cartridge_path = str(self._resolve_existing_file(cartridge_path))
            cartridge_data = self._load_yaml(resolved_cartridge_path, "cartridge")
        else:
            resolved_cartridge_path = None

        processor_data = self.validate_processor(processor_data)
        system_data = self.validate_system(system_data)
        ic_data_list = [self.validate_ic(ic_data) for ic_data in ic_data_list]
        device_data_list = [self.validate_device(device_data) for device_data in device_data_list]
        host_data_list = [self.validate_host(host_data) for host_data in host_data_list]
        selected_host_backend_target = _normalize_host_backend_target_selection(
            host_data_list, host_backend_target
        )
        if cartridge_data:
            cartridge_data = self.validate_cartridge(cartridge_data)
        rom_images_resolved = self._resolve_system_rom_images(
            system_data, resolved_system_path
        )
        system_data = copy.deepcopy(system_data)
        system_data.setdefault("memory", {})
        system_data["memory"]["rom_images"] = rom_images_resolved
        system_base_dir = Path(resolved_system_path).resolve().parent
        resolved_cartridge_rom_path = ""
        if cartridge_rom_path:
            resolved_cartridge_rom_path = self._validate_readable_file(
                cartridge_rom_path,
                error_prefix="Composition validation failed",
                base_dir=system_base_dir,
            )

        coding_sources: List[Dict[str, Any]] = [
            self._resolve_coding_paths(
                processor_data.get("coding", {}), resolved_processor_path
            )
        ]
        coding_sources.extend(
            self._resolve_coding_paths(ic_data.get("coding", {}), ic_path)
            for ic_data, ic_path in zip(ic_data_list, resolved_ic_paths)
        )
        coding_sources.extend(
            self._resolve_coding_paths(device_data.get("coding", {}), device_path)
            for device_data, device_path in zip(device_data_list, resolved_device_paths)
        )
        coding_sources.extend(
            self._resolve_coding_paths(host_data.get("coding", {}), host_path)
            for host_data, host_path in zip(host_data_list, resolved_host_paths)
        )
        if cartridge_data and resolved_cartridge_path:
            coding_sources.append(
                self._resolve_coding_paths(
                    cartridge_data.get("coding", {}), resolved_cartridge_path
                )
            )

        return self.compose(
            processor_data,
            system_data,
            ic_data_list,
            device_data_list,
            host_data_list,
            cartridge_data,
            resolved_cartridge_rom_path,
            coding_sources,
            selected_host_backend_target,
        )

    def get_summary(self, combined_data: Dict[str, Any]) -> Dict[str, Any]:
        meta = combined_data.get("metadata", {})
        system = combined_data.get("system", {})
        sys_meta = system.get("metadata", {})
        interrupts = combined_data.get("interrupts", {})

        return {
            "name": meta.get("name", "Unknown"),
            "system_name": sys_meta.get("name", "UnknownSystem"),
            "version": meta.get("version", "1.0"),
            "bits": meta.get("bits", 8),
            "address_bits": meta.get("address_bits", 16),
            "endian": meta.get("endian", "little"),
            "num_registers": len(combined_data.get("registers", [])),
            "num_flags": len(combined_data.get("flags", [])),
            "num_instructions": len(combined_data.get("instructions", [])),
            "undefined_opcode_policy": meta.get("undefined_opcode_policy", "trap"),
            "clock_hz": int(system.get("clock_hz", 0)),
            "reset_delay_seconds": int(system.get("reset_delay_seconds", 0)),
            "hooks": combined_data.get("hooks", {}),
            "has_interrupts": "interrupts" in combined_data
            and bool(combined_data.get("interrupts")),
            "interrupt_model": interrupts.get("model"),
            "has_ports": "ports" in combined_data and bool(combined_data.get("ports")),
            "memory_default_size": int(
                combined_data.get("memory", {}).get("default_size", 0)
            ),
            "num_ics": len(combined_data.get("ics", [])),
            "num_devices": len(combined_data.get("devices", [])),
            "num_hosts": len(combined_data.get("hosts", [])),
            "num_cartridges": 1 if combined_data.get("cartridge") else 0,
            "num_rom_images": len(combined_data.get("memory", {}).get("rom_images", [])),
            "ic_ids": [
                ic.get("metadata", {}).get("id", "") for ic in combined_data.get("ics", [])
            ],
            "device_ids": [
                dev.get("metadata", {}).get("id", "")
                for dev in combined_data.get("devices", [])
            ],
            "host_ids": [
                host.get("metadata", {}).get("id", "")
                for host in combined_data.get("hosts", [])
            ],
            "cartridge_id": combined_data.get("cartridge", {}).get("metadata", {}).get("id", ""),
            "cartridge_rom_path": combined_data.get("cartridge_rom", {}).get("path", ""),
        }


class ISALoader:
    """Removed single-file loader entrypoint (hard cutover)."""

    def __init__(self):
        raise RuntimeError(
            "Single-file ISA loading was removed. "
            "Use ProcessorSystemLoader with processor.yaml + system.yaml."
        )


def load_processor_system(
    processor_path: str,
    system_path: str,
    ic_paths: List[str] | None = None,
    device_paths: List[str] | None = None,
    host_paths: List[str] | None = None,
    cartridge_path: str | None = None,
    cartridge_rom_path: str | None = None,
    host_backend_target: str | None = None,
) -> Dict[str, Any]:
    """Convenience function to load and validate processor+system files."""
    loader = ProcessorSystemLoader()
    return loader.load(
        processor_path,
        system_path,
        ic_paths=ic_paths,
        device_paths=device_paths,
        host_paths=host_paths,
        cartridge_path=cartridge_path,
        cartridge_rom_path=cartridge_rom_path,
        host_backend_target=host_backend_target,
    )


def validate_processor_system(
    processor_path: str,
    system_path: str,
    ic_paths: List[str] | None = None,
    device_paths: List[str] | None = None,
    host_paths: List[str] | None = None,
    cartridge_path: str | None = None,
    cartridge_rom_path: str | None = None,
    host_backend_target: str | None = None,
) -> bool:
    """Validate processor+system files without generating code."""
    loader = ProcessorSystemLoader()
    try:
        loader.load(
            processor_path,
            system_path,
            ic_paths=ic_paths,
            device_paths=device_paths,
            host_paths=host_paths,
            cartridge_path=cartridge_path,
            cartridge_rom_path=cartridge_rom_path,
            host_backend_target=host_backend_target,
        )
        return True
    except (ValidationError, FileNotFoundError, yaml.YAMLError, ValueError) as e:
        print(f"Validation failed: {e}")
        return False


def load_isa(path: str) -> Dict[str, Any]:
    """Removed single-file convenience function (hard cutover)."""
    raise RuntimeError(
        "load_isa(path) is no longer supported. "
        "Use load_processor_system(processor_path, system_path)."
    )


def validate_isa(path: str) -> bool:
    """Removed single-file validation convenience function (hard cutover)."""
    raise RuntimeError(
        "validate_isa(path) is no longer supported. "
        "Use validate_processor_system(processor_path, system_path)."
    )
