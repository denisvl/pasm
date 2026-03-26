import pathlib

import pytest
import yaml


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
PROCESSOR_DIR = BASE_DIR / "examples" / "processors"


def _load_processor(name: str) -> dict:
    path = PROCESSOR_DIR / f"{name}.yaml"
    assert path.exists(), f"Processor file not found: {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _instruction_keys(processor: dict) -> list[tuple[int, int, dict]]:
    keys: list[tuple[int, int, dict]] = []
    for inst in processor["instructions"]:
        encoding = inst.get("encoding", {})
        if "opcode" not in encoding:
            continue
        keys.append((int(encoding.get("prefix", 0)), int(encoding["opcode"]), inst))
    return keys


@pytest.mark.parametrize("processor_name", ["mos6502", "mos6510", "mos6509", "mc6809"])
def test_instruction_entries_have_required_shape(processor_name: str):
    processor = _load_processor(processor_name)
    assert len(processor["instructions"]) > 0

    for inst in processor["instructions"]:
        encoding = inst.get("encoding", {})
        assert "opcode" in encoding, f"{processor_name}:{inst['name']} missing encoding.opcode"
        assert "mask" in encoding, f"{processor_name}:{inst['name']} missing encoding.mask"
        assert "length" in encoding, f"{processor_name}:{inst['name']} missing encoding.length"
        assert "cycles" in inst, f"{processor_name}:{inst['name']} missing cycles"
        behavior = inst.get("behavior", "")
        assert behavior.strip(), f"{processor_name}:{inst['name']} has empty behavior"


@pytest.mark.parametrize("processor_name", ["mos6502", "mos6510", "mos6509", "mc6809"])
def test_instruction_opcode_keys_are_unique(processor_name: str):
    processor = _load_processor(processor_name)
    keys = _instruction_keys(processor)
    seen: set[tuple[int, int]] = set()
    dups: list[tuple[int, int]] = []
    for prefix, opcode, _inst in keys:
        key = (prefix, opcode)
        if key in seen:
            dups.append(key)
        seen.add(key)
    assert not dups, f"{processor_name} duplicate opcode keys: {dups}"


@pytest.mark.parametrize("processor_name", ["mos6502", "mos6510", "mos6509"])
def test_mos65xx_cover_full_256_opcode_space(processor_name: str):
    processor = _load_processor(processor_name)
    keys = _instruction_keys(processor)
    prefixes = {prefix for prefix, _opcode, _inst in keys}
    assert prefixes == {0}, f"{processor_name} should only define base opcode space"

    opcodes = {opcode for _prefix, opcode, _inst in keys}
    assert opcodes == set(range(256)), f"{processor_name} does not fully cover 0x00-0xFF"
    assert len(keys) == 256, f"{processor_name} should have exactly 256 instruction entries"


@pytest.mark.parametrize("processor_name", ["mos6502", "mos6510", "mos6509"])
def test_mos65xx_include_undocumented_opcodes(processor_name: str):
    processor = _load_processor(processor_name)
    undocumented = [
        inst
        for inst in processor["instructions"]
        if "(UD)" in inst.get("display", "") or "_UD" in inst.get("name", "")
    ]
    # NMOS 65xx tables should include a large undocumented set.
    assert len(undocumented) >= 100, (
        f"{processor_name} undocumented coverage is unexpectedly low: {len(undocumented)}"
    )


@pytest.mark.parametrize("processor_name", ["mos6502", "mos6510", "mos6509", "mc6809"])
def test_non_nop_instructions_do_not_use_placeholder_behavior(processor_name: str):
    processor = _load_processor(processor_name)
    for _prefix, _opcode, inst in _instruction_keys(processor):
        behavior = inst.get("behavior", "").strip()
        if behavior != "(void)cpu;":
            continue
        assert inst["name"].startswith("NOP") or inst["name"] == "SYNC", (
            f"{processor_name}:{inst['name']} uses placeholder behavior unexpectedly"
        )


def test_mc6809_prefix_spaces_match_expected_tables():
    processor = _load_processor("mc6809")
    keys = _instruction_keys(processor)

    spaces: dict[int, set[int]] = {}
    for prefix, opcode, _inst in keys:
        spaces.setdefault(prefix, set()).add(opcode)

    expected_counts = {0x00: 222, 0x10: 38, 0x11: 9}
    assert set(spaces) == set(expected_counts), f"mc6809 unexpected prefix spaces: {sorted(spaces)}"
    for prefix, expected in expected_counts.items():
        assert len(spaces[prefix]) == expected, (
            f"mc6809 prefix 0x{prefix:02X} expected {expected} opcodes, got {len(spaces[prefix])}"
        )


def test_mc6809_interrupt_path_instructions_present():
    processor = _load_processor("mc6809")
    names = {inst["name"] for inst in processor["instructions"]}
    required = {"SYNC", "CWAI", "SWI", "SWI2_P2", "SWI3_P3", "RTI_MIN"}
    missing = sorted(required - names)
    assert not missing, f"mc6809 missing interrupt-path instructions: {missing}"
