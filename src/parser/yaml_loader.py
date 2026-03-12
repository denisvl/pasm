"""Processor/System YAML loader with JSON Schema validation."""

import copy
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

try:
    from jsonschema import Draft7Validator
    from jsonschema import ValidationError
except ImportError:
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


def get_schema_path(kind: str) -> Path:
    """Get path to a schema file."""
    base = Path(__file__).parent.parent.parent / "schemas"
    if kind == "processor":
        return base / "processor_schema.json"
    if kind == "system":
        return base / "system_schema.json"
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


class ProcessorSystemLoader:
    """Load and validate processor/system definitions, then compose them."""

    def __init__(self):
        self.processor_schema = load_schema("processor")
        self.system_schema = load_schema("system")
        if Draft7Validator:
            self.processor_validator = Draft7Validator(self.processor_schema)
            self.system_validator = Draft7Validator(self.system_schema)
        else:
            self.processor_validator = None
            self.system_validator = None

    def _load_yaml(self, path: str, kind: str) -> Dict[str, Any]:
        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"{kind} file not found: {path}")
        with open(path_obj, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data is None:
            raise ValueError(f"Empty {kind} file: {path}")
        if not isinstance(data, dict):
            raise ValueError(f"{kind} YAML root must be an object: {path}")
        return data

    def validate_processor(self, processor_data: Dict[str, Any]) -> Dict[str, Any]:
        errors = _iter_errors(self.processor_validator, processor_data)
        if errors:
            raise ValidationError(_format_schema_errors("Processor", errors))

        if "registers" in processor_data:
            processor_data["registers"] = expand_register_ranges(processor_data["registers"])

        _validate_flags_layout(processor_data.get("flags", []))
        _validate_register_parts(processor_data.get("registers", []))

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

    def compose(
        self, processor_data: Dict[str, Any], system_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        address_bits = int(processor_data.get("metadata", {}).get("address_bits", 0))
        max_memory_size = 1 << address_bits
        memory = system_data.get("memory", {})
        default_size = int(memory.get("default_size", 0))

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

        combined = {
            "metadata": copy.deepcopy(processor_data.get("metadata", {})),
            "registers": copy.deepcopy(processor_data.get("registers", [])),
            "flags": copy.deepcopy(processor_data.get("flags", [])),
            "instructions": copy.deepcopy(processor_data.get("instructions", [])),
            "memory": {
                "address_bits": address_bits,
                "default_size": default_size,
                "regions": copy.deepcopy(memory.get("regions", [])),
            },
            "ports": copy.deepcopy(processor_data.get("ports", {})),
            "interrupts": copy.deepcopy(processor_data.get("interrupts", {})),
            "hooks": copy.deepcopy(system_data.get("hooks", {})),
            "system": {
                "metadata": copy.deepcopy(system_data.get("metadata", {})),
                "clock_hz": int(system_data.get("clock_hz", 0)),
                "integrations": copy.deepcopy(system_data.get("integrations", {})),
            },
        }

        return combined

    def load(self, processor_path: str, system_path: str) -> Dict[str, Any]:
        processor_data = self._load_yaml(processor_path, "processor")
        system_data = self._load_yaml(system_path, "system")

        processor_data = self.validate_processor(processor_data)
        system_data = self.validate_system(system_data)
        return self.compose(processor_data, system_data)

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
            "hooks": combined_data.get("hooks", {}),
            "has_interrupts": "interrupts" in combined_data
            and bool(combined_data.get("interrupts")),
            "interrupt_model": interrupts.get("model"),
            "has_ports": "ports" in combined_data and bool(combined_data.get("ports")),
            "memory_default_size": int(
                combined_data.get("memory", {}).get("default_size", 0)
            ),
        }


class ISALoader:
    """Removed single-file loader entrypoint (hard cutover)."""

    def __init__(self):
        raise RuntimeError(
            "Single-file ISA loading was removed. "
            "Use ProcessorSystemLoader with processor.yaml + system.yaml."
        )


def load_processor_system(processor_path: str, system_path: str) -> Dict[str, Any]:
    """Convenience function to load and validate processor+system files."""
    loader = ProcessorSystemLoader()
    return loader.load(processor_path, system_path)


def validate_processor_system(processor_path: str, system_path: str) -> bool:
    """Validate processor+system files without generating code."""
    loader = ProcessorSystemLoader()
    try:
        loader.load(processor_path, system_path)
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
