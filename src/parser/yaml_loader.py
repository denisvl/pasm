"""YAML ISA loader with JSON Schema validation."""

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

try:
    from jsonschema import ValidationError
    from jsonschema import validators
    from jsonschema import Draft7Validator
except ImportError:
    from jsonschema import ValidationError

    validators = None
    Draft7Validator = None


def get_schema_path() -> Path:
    """Get path to the ISA schema file."""
    return Path(__file__).parent.parent.parent / "schemas" / "isa_schema.json"


def load_schema() -> Dict[str, Any]:
    """Load the JSON schema."""
    with open(get_schema_path(), "r") as f:
        return json.load(f)


def expand_register_ranges(registers: list) -> list:
    """Expand register ranges like 'R0..R7' into individual registers."""
    expanded = []
    for reg in registers:
        name = reg.get("name", "")
        if ".." in name:
            base, end = name.split("..")
            prefix = ""
            for i in range(len(base)):
                if base[i].isalpha():
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
        bit = flag.get("bit")
        if name in seen_names:
            raise ValidationError(
                f"ISA validation failed:\nflags -> {idx}: duplicate flag name '{name}'"
            )
        seen_names.add(name)
        if bit in seen_bits:
            raise ValidationError(
                f"ISA validation failed:\nflags -> {idx}: duplicate bit position {bit}"
            )
        seen_bits.add(int(bit))


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
                    "ISA validation failed:\n"
                    f"registers -> {reg_idx} -> parts -> {part_idx}: "
                    f"duplicate part name '{part_name}'"
                )
            seen_names.add(part_name)

            if part_msb >= reg_bits:
                raise ValidationError(
                    "ISA validation failed:\n"
                    f"registers -> {reg_idx} -> parts -> {part_idx}: "
                    f"part range [{part_msb}:{part_lsb}] exceeds parent width {reg_bits}"
                )

            for bit in range(part_lsb, part_lsb + part_bits):
                if bit in occupied_bits:
                    raise ValidationError(
                        "ISA validation failed:\n"
                        f"registers -> {reg_idx} -> parts -> {part_idx}: "
                        f"overlapping bit {bit}"
                    )
                occupied_bits.add(bit)


class ISALoader:
    """Load and validate ISA definitions from YAML files."""

    def __init__(self):
        self.schema = load_schema()
        if Draft7Validator:
            self.validator = Draft7Validator(self.schema)
        else:
            self.validator = None

    def load(self, path: str) -> Dict[str, Any]:
        """Load and validate an ISA YAML file."""
        path_obj = Path(path)

        if not path_obj.exists():
            raise FileNotFoundError(f"ISA file not found: {path}")

        with open(path_obj, "r") as f:
            isa_data = yaml.safe_load(f)

        if isa_data is None:
            raise ValueError(f"Empty ISA file: {path}")

        return self.validate(isa_data)

    def validate(self, isa_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate ISA data against the schema."""
        if self.validator is not None:
            errors = list(self.validator.iter_errors(isa_data))

            if errors:
                error_messages = []
                for error in errors:
                    path = (
                        " -> ".join(str(p) for p in error.path)
                        if error.path
                        else "root"
                    )
                    error_messages.append(f"{path}: {error.message}")

                raise ValidationError(
                    f"ISA validation failed:\n" + "\n".join(error_messages)
                )

        # Expand register ranges
        if "registers" in isa_data:
            isa_data["registers"] = expand_register_ranges(isa_data["registers"])

        # Hard-cutover semantic validation for YAML-defined layouts.
        _validate_flags_layout(isa_data.get("flags", []))
        _validate_register_parts(isa_data.get("registers", []))

        return isa_data

    def get_summary(self, isa_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get a summary of the ISA."""
        meta = isa_data.get("metadata", {})
        interrupts = isa_data.get("interrupts", {})

        return {
            "name": meta.get("name", "Unknown"),
            "version": meta.get("version", "1.0"),
            "bits": meta.get("bits", 8),
            "address_bits": meta.get("address_bits", 16),
            "endian": meta.get("endian", "little"),
            "num_registers": len(isa_data.get("registers", [])),
            "num_flags": len(isa_data.get("flags", [])),
            "num_instructions": len(isa_data.get("instructions", [])),
            "undefined_opcode_policy": meta.get("undefined_opcode_policy", "trap"),
            "hooks": isa_data.get("hooks", {}),
            "has_interrupts": "interrupts" in isa_data,
            "interrupt_model": interrupts.get("model"),
            "has_ports": "ports" in isa_data,
        }


def load_isa(path: str) -> Dict[str, Any]:
    """Convenience function to load and validate an ISA file."""
    loader = ISALoader()
    return loader.load(path)


def validate_isa(path: str) -> bool:
    """Validate an ISA file without loading it fully."""
    loader = ISALoader()
    try:
        loader.load(path)
        return True
    except (ValidationError, FileNotFoundError, yaml.YAMLError) as e:
        print(f"Validation failed: {e}")
        return False
