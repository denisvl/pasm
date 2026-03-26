import os
import pathlib
import re
import shutil
import subprocess
import uuid

import pytest

from src import generator as gen_mod
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


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


@pytest.fixture(scope="module")
def mos6509_binary():
    outdir = _make_workdir("mos6509_runtime_") / "generated"
    processor_path, system_path = example_pair("mos6509")
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

    binary_name = "mos6509_test.exe" if os.name == "nt" else "mos6509_test"
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


def _run_rom(binary: pathlib.Path, image: bytes, cycles: int = 120) -> str:
    rom = _make_workdir("mos6509_rom_") / "prog.rom"
    rom.write_bytes(image)
    proc = subprocess.run(
        [str(binary), "--rom", str(rom), "--cycles", str(cycles)],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_zp_00_01_overlay_bank_registers(mos6509_binary):
    # Keep BANK_EXEC at 0 while checking overlay behavior.
    # LDA #$03 ; STA $01
    # LDA $00 ; TAX
    # LDA $01 ; BRK
    image = bytes([0xA9, 0x03, 0x85, 0x01, 0xA5, 0x00, 0xAA, 0xA5, 0x01, 0x00])
    stdout = _run_rom(mos6509_binary, image)
    assert _parse_reg(stdout, 1) == 0x00
    assert _parse_reg(stdout, 0) == 0x03


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_indy_uses_bank_indir_for_read_and_write(mos6509_binary):
    # Pointer at $40/$41 -> $1234
    # Write 0x11 through bank 0, then 0x5A through bank 1.
    # Read bank 0 into X, bank 1 into A.
    image = bytes(
        [
            0xA9, 0x34, 0x85, 0x40,       # LDA #$34 ; STA $40
            0xA9, 0x12, 0x85, 0x41,       # LDA #$12 ; STA $41
            0xA9, 0x00, 0x85, 0x01,       # BANK_INDIR=0
            0xA9, 0x11, 0x91, 0x40,       # STA ($40),Y   -> bank0:$1234
            0xA9, 0x01, 0x85, 0x01,       # BANK_INDIR=1
            0xA9, 0x5A, 0x91, 0x40,       # STA ($40),Y   -> bank1:$1234
            0xA9, 0x00, 0x85, 0x01,       # BANK_INDIR=0
            0xB1, 0x40, 0xAA,             # LDA ($40),Y ; TAX (X=0x11)
            0xA9, 0x01, 0x85, 0x01,       # BANK_INDIR=1
            0xB1, 0x40,                   # LDA ($40),Y (A=0x5A)
            0x00,                         # BRK
        ]
    )
    stdout = _run_rom(mos6509_binary, image)
    assert _parse_reg(stdout, 1) == 0x11
    assert _parse_reg(stdout, 0) == 0x5A


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_bank_exec_changes_opcode_fetch_bank(mos6509_binary):
    # bank0:
    #   LDA #$01
    #   STA $00        ; BANK_EXEC = 1
    #   LDA #$77       ; should NOT execute if fetch now comes from bank1
    #   BRK
    #
    # bank1 at same PC location contains BRK (memory defaults to 0x00), so
    # execution should stop before loading 0x77 into A.
    image = bytes([0xA9, 0x01, 0x85, 0x00, 0xA9, 0x77, 0x00])
    stdout = _run_rom(mos6509_binary, image, cycles=40)
    assert _parse_reg(stdout, 0) != 0x77
