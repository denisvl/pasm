import os
import pathlib
import re
import shutil
import subprocess
import uuid

import pytest

from src import generator as gen_mod
from tests.support import BASE_DIR


def _make_workdir(prefix: str) -> pathlib.Path:
    root = BASE_DIR / ".tmp_test_work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


def _parse_reg(stdout: str, idx: int) -> int:
    matches = re.findall(rf"R{idx}:\s*0x([0-9A-Fa-f]{{2}})", stdout)
    assert matches, f"Could not parse R{idx} from output:\n{stdout}"
    return int(matches[-1], 16)


def _parse_flags(stdout: str) -> int:
    matches = re.findall(r"Flags:\s*0x([0-9A-Fa-f]{2})", stdout)
    assert matches, f"Could not parse Flags from output:\n{stdout}"
    return int(matches[-1], 16)


@pytest.fixture(scope="module")
def ricoh2a03_binary():
    outdir = _make_workdir("ricoh2a03_runtime_") / "generated"
    processor_path = BASE_DIR / "examples" / "processors" / "ricoh2a03.yaml"
    system_path = BASE_DIR / "examples" / "systems" / "mos6502" / "mos6502_default.yaml"
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

    binary_name = "mos6502_test.exe" if os.name == "nt" else "mos6502_test"
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
    return binary


def _run_rom(binary: pathlib.Path, image: bytes, cycles: int = 80) -> str:
    rom = _make_workdir("ricoh2a03_rom_") / "prog.rom"
    rom.write_bytes(image)
    proc = subprocess.run(
        [str(binary), "--rom", str(rom), "--cycles", str(cycles)],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_2a03_adc_ignores_decimal_mode(ricoh2a03_binary):
    # SED; LDA #$15; CLC; ADC #$27; BRK
    # 6502 decimal result would be 0x42; 2A03 must keep binary result 0x3C.
    image = bytes([0xF8, 0xA9, 0x15, 0x18, 0x69, 0x27, 0x00])
    stdout = _run_rom(ricoh2a03_binary, image, cycles=40)
    assert _parse_reg(stdout, 0) == 0x3C


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_2a03_sbc_ignores_decimal_mode(ricoh2a03_binary):
    # SED; SEC; LDA #$50; SBC #$01; BRK
    # 6502 decimal result would be 0x49; 2A03 must keep binary result 0x4F.
    image = bytes([0xF8, 0x38, 0xA9, 0x50, 0xE9, 0x01, 0x00])
    stdout = _run_rom(ricoh2a03_binary, image, cycles=40)
    assert _parse_reg(stdout, 0) == 0x4F


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_2a03_d_flag_still_sets_and_clears(ricoh2a03_binary):
    # SED; CLD; BRK
    image = bytes([0xF8, 0xD8, 0x00])
    stdout = _run_rom(ricoh2a03_binary, image, cycles=20)
    flags = _parse_flags(stdout)
    assert (flags & 0x08) == 0
