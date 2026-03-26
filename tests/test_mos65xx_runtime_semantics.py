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


def _parse_flags(stdout: str) -> int:
    matches = re.findall(r"Flags:\s*0x([0-9A-Fa-f]{2})", stdout)
    assert matches, f"Could not parse Flags from output:\n{stdout}"
    return int(matches[-1], 16)


def _parse_pc(stdout: str) -> int:
    matches = re.findall(r"PC:\s*0x([0-9A-Fa-f]{4})", stdout)
    assert matches, f"Could not parse PC from output:\n{stdout}"
    return int(matches[-1], 16)


@pytest.fixture(scope="module", params=["mos6502", "mos6510"])
def mos65xx_binary(request):
    cpu = str(request.param)
    outdir = _make_workdir(f"{cpu}_runtime_") / "generated"
    processor_path, system_path = example_pair(cpu)
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

    binary_name = f"{cpu}_test.exe" if os.name == "nt" else f"{cpu}_test"
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
    rom = _make_workdir("mos65_rom_") / "prog.rom"
    rom.write_bytes(image)
    proc = subprocess.run(
        [str(binary), "--rom", str(rom), "--cycles", str(cycles)],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_lax_indx_loads_a_and_x(mos65xx_binary):
    # LDA #$40 ; STA $22
    # LDA #$00 ; STA $23
    # LDA #$5A ; STA ($22),Y
    # LDA #$20 ; TAX
    # LAX ($02,X) ; BRK
    image = bytes(
        [
            0xA9, 0x40,
            0x85, 0x22,
            0xA9, 0x00,
            0x85, 0x23,
            0xA9, 0x5A,
            0x91, 0x22,
            0xA9, 0x20,
            0xAA,
            0xA3, 0x02,
            0x00,
        ]
    )
    stdout = _run_rom(mos65xx_binary, image, cycles=120)
    assert _parse_reg(stdout, 0) == 0x5A  # A
    assert _parse_reg(stdout, 1) == 0x5A  # X


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_rra_zp_uses_rotate_carry_and_adc(mos65xx_binary):
    # LDA #$01
    # ALR #$01      ; C=1, A=0
    # LDA #$01
    # STA $10
    # RRA $10       ; A should become 0x82 with this implementation
    # BRK
    image = bytes([0xA9, 0x01, 0x4B, 0x01, 0xA9, 0x01, 0x85, 0x10, 0x67, 0x10, 0x00])
    stdout = _run_rom(mos65xx_binary, image, cycles=80)
    flags = _parse_flags(stdout)
    assert _parse_reg(stdout, 0) == 0x82
    assert (flags & 0x80) != 0  # N
    assert (flags & 0x01) == 0  # C


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_kil_halts_execution(mos65xx_binary):
    # KIL ; LDA #$99 ; BRK
    image = bytes([0x02, 0xA9, 0x99, 0x00])
    stdout = _run_rom(mos65xx_binary, image, cycles=20)
    assert _parse_pc(stdout) == 0x0001
    assert _parse_reg(stdout, 0) == 0x00


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_unofficial_nop_absx_preserves_state(mos65xx_binary):
    # LDA #$33 ; NOP abs,X ; TAX ; BRK
    image = bytes([0xA9, 0x33, 0x1C, 0x00, 0x00, 0xAA, 0x00])
    stdout = _run_rom(mos65xx_binary, image, cycles=40)
    assert _parse_reg(stdout, 0) == 0x33
    assert _parse_reg(stdout, 1) == 0x33


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_unofficial_sbc_immediate_opcode_eb(mos65xx_binary):
    # LDA #$01 ; ALR #$01 (sets C=1)
    # LDA #$10 ; SBC #$01 (0xEB) ; BRK
    image = bytes([0xA9, 0x01, 0x4B, 0x01, 0xA9, 0x10, 0xEB, 0x01, 0x00])
    stdout = _run_rom(mos65xx_binary, image, cycles=40)
    flags = _parse_flags(stdout)
    assert _parse_reg(stdout, 0) == 0x0F
    assert (flags & 0x01) != 0  # C
