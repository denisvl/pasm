import json
import os
import pathlib
import re
import shutil
import subprocess
import uuid

import pytest
import yaml

from src import generator as gen_mod
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "tests" / "data"
CPUS = ("mos6502", "mos6510", "mos6509", "mc6809")


def _make_workdir(prefix: str) -> pathlib.Path:
    root = BASE_DIR / ".tmp_opcode_behavior"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


def _load_processor_yaml(cpu_name: str) -> dict:
    path = BASE_DIR / "examples" / "processors" / f"{cpu_name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=CPUS)
def cpu_binary_and_instructions(request):
    cpu_name = str(request.param)
    outdir = _make_workdir(f"{cpu_name}_opcode_behavior_") / "generated"
    processor_path, system_path = example_pair(cpu_name)
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    build_dir = outdir / "build"
    subprocess.check_call(
        ["cmake", "-S", str(outdir), "-B", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    subprocess.check_call(
        ["cmake", "--build", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    binary_name = f"{cpu_name}_test.exe" if os.name == "nt" else f"{cpu_name}_test"
    candidates = [
        build_dir / binary_name,
        build_dir / "Debug" / binary_name,
        build_dir / "Release" / binary_name,
    ]
    binary = next((cand for cand in candidates if cand.exists()), None)
    if binary is None:
        for cand in build_dir.rglob(binary_name):
            if "CompilerIdC" not in str(cand):
                binary = cand
                break
    assert binary is not None, f"Expected binary not found under: {build_dir}"

    processor = _load_processor_yaml(cpu_name)
    instructions = sorted(
        processor["instructions"],
        key=lambda inst: (
            int(inst.get("encoding", {}).get("prefix", 0)),
            int(inst.get("encoding", {}).get("opcode", 0)),
            inst["name"],
        ),
    )
    return cpu_name, binary, instructions


def _instruction_stream(inst: dict) -> bytes:
    encoding = inst["encoding"]
    stream = bytearray()
    if "prefix" in encoding:
        stream.append(int(encoding["prefix"]) & 0xFF)
    stream.append(int(encoding["opcode"]) & 0xFF)
    # Use zeroed operands so branch displacements and addresses stay deterministic.
    while len(stream) < int(encoding["length"]):
        stream.append(0x00)
    return bytes(stream)


def _rom_image_for(cpu_name: str, inst: dict) -> bytes:
    stream = _instruction_stream(inst)
    image = bytearray([0x00] * 65536)
    image[0 : len(stream)] = stream
    if cpu_name.startswith("mos65"):
        # BRK sentinel if control reaches the next byte.
        image[len(stream)] = 0x00
    else:
        # BRA -2 sentinel loop for MC6809.
        image[len(stream)] = 0x20
        image[len(stream) + 1] = 0xFE
    return bytes(image)


def _parse_snapshot(stdout: str) -> dict:
    regs: dict[int, int] = {}
    for match in re.finditer(r"R(\d+):\s*0x([0-9A-Fa-f]{2})", stdout):
        regs[int(match.group(1))] = int(match.group(2), 16)

    snapshot = {
        "regs": [regs[idx] for idx in sorted(regs)],
    }

    flags = re.findall(r"Flags:\s*0x([0-9A-Fa-f]{2})", stdout)
    if flags:
        snapshot["flags"] = int(flags[-1], 16)

    sp = re.findall(r"SP:\s*0x([0-9A-Fa-f]{4})", stdout)
    if sp:
        snapshot["sp"] = int(sp[-1], 16)

    pc = re.findall(r"PC:\s*0x([0-9A-Fa-f]{4})", stdout)
    if pc:
        snapshot["pc"] = int(pc[-1], 16)

    cycles = re.findall(r"Executed\s+(\d+)\s+cycles", stdout)
    if cycles:
        snapshot["executed_cycles"] = int(cycles[-1])

    return snapshot


def _collect_behavior_snapshot(cpu_name: str, binary: pathlib.Path, instructions: list[dict]) -> dict:
    snapshots: dict[str, dict] = {}
    for inst in instructions:
        encoding = inst["encoding"]
        key = (
            f"{int(encoding.get('prefix', 0)):02X}:"
            f"{int(encoding['opcode']):02X}:"
            f"{inst['name']}"
        )
        rom = _make_workdir(f"{cpu_name}_opcode_rom_") / f"{key.replace(':', '_')}.rom"
        rom.write_bytes(_rom_image_for(cpu_name, inst))
        cycles = max(1, int(inst.get("cycles", 1)))
        proc = subprocess.run(
            [str(binary), "--rom", str(rom), "--cycles", str(cycles)],
            check=True,
            capture_output=True,
            text=True,
        )
        snapshots[key] = _parse_snapshot(proc.stdout)
    return snapshots


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_opcode_behavior_regression(cpu_binary_and_instructions):
    cpu_name, binary, instructions = cpu_binary_and_instructions
    actual = _collect_behavior_snapshot(cpu_name, binary, instructions)

    reference_path = DATA_DIR / f"{cpu_name}_opcode_behavior_reference.json"
    regenerate = os.environ.get("PASM_REGENERATE_OPCODE_BEHAVIOR_REFERENCE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if regenerate:
        reference_path.parent.mkdir(parents=True, exist_ok=True)
        reference_path.write_text(
            json.dumps(actual, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.fail(
            f"Regenerated opcode behavior reference at {reference_path}; "
            "re-run tests without regeneration enabled."
        )

    assert reference_path.exists(), (
        f"Missing opcode behavior reference: {reference_path}. "
        "Generate it with PASM_REGENERATE_OPCODE_BEHAVIOR_REFERENCE=1."
    )
    expected = json.loads(reference_path.read_text(encoding="utf-8"))
    assert actual == expected
