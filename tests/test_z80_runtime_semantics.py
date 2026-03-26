import os
import pathlib
import re
import shutil
import subprocess

import pytest

from src import generator as gen_mod
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _parse_r0(stdout: str) -> int:
    match = re.search(r"R0:\s*0x([0-9A-Fa-f]{2})", stdout)
    assert match, f"Could not parse R0 from output:\n{stdout}"
    return int(match.group(1), 16)


def _parse_reg(stdout: str, idx: int) -> int:
    match = re.search(rf"R{idx}:\s*0x([0-9A-Fa-f]{{2}})", stdout)
    assert match, f"Could not parse R{idx} from output:\n{stdout}"
    return int(match.group(1), 16)


def _parse_flags(stdout: str) -> int:
    match = re.search(r"Flags:\s*0x([0-9A-Fa-f]{2})", stdout)
    assert match, f"Could not parse Flags from output:\n{stdout}"
    return int(match.group(1), 16)


def _parse_sp(stdout: str) -> int:
    match = re.search(r"SP:\s*0x([0-9A-Fa-f]{4})", stdout)
    assert match, f"Could not parse SP from output:\n{stdout}"
    return int(match.group(1), 16)


def _parse_pc(stdout: str) -> int:
    match = re.search(r"PC:\s*0x([0-9A-Fa-f]{4})", stdout)
    assert match, f"Could not parse PC from output:\n{stdout}"
    return int(match.group(1), 16)


def _parse_executed_cycles(stdout: str) -> int:
    match = re.search(r"Executed\s+(\d+)\s+cycles", stdout)
    assert match, f"Could not parse executed cycles from output:\n{stdout}"
    return int(match.group(1))


def _is_even_parity(value: int) -> bool:
    return (value & 0xFF).bit_count() % 2 == 0


def _assert_rotate_shift_flags(flags: int, expected_value: int, expected_carry: bool) -> None:
    assert ((flags & 0x20) != 0) == expected_carry  # FLAG_C
    assert ((flags & 0x02) != 0) == (expected_value == 0)  # FLAG_Z
    assert ((flags & 0x01) != 0) == ((expected_value & 0x80) != 0)  # FLAG_S
    assert (flags & 0x04) == 0  # FLAG_H
    assert ((flags & 0x08) != 0) == _is_even_parity(expected_value)  # FLAG_P
    assert (flags & 0x10) == 0  # FLAG_N


def _assert_bit_flags(flags: int, *, expect_z: bool, expect_s: bool, expect_carry: bool) -> None:
    assert ((flags & 0x20) != 0) == expect_carry  # FLAG_C unchanged
    assert ((flags & 0x02) != 0) == expect_z  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H always set
    assert ((flags & 0x08) != 0) == expect_z  # FLAG_P mirrors Z
    assert (flags & 0x10) == 0  # FLAG_N always reset
    assert ((flags & 0x01) != 0) == expect_s  # FLAG_S (bit 7 test only)


@pytest.fixture(scope="module")
def z80_binary(tmp_path_factory):
    outdir = tmp_path_factory.mktemp("z80_runtime") / "generated"
    processor_path, system_path = example_pair("z80")

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

    binary_name = "z80_test.exe" if os.name == "nt" else "z80_test"
    binary = build_dir / binary_name
    assert binary.exists(), f"Expected binary not found: {binary}"
    return binary


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_and_rlc_update_a_register(z80_binary, tmp_path):
    rom = tmp_path / "ld_rlc.rom"
    # LD A,0x12 ; RLC A
    rom.write_bytes(bytes([0x3E, 0x12, 0x07]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "11"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x24


@pytest.mark.parametrize(
    ("rom_bytes", "expected_a"),
    [
        (bytes([0xAF, 0x3E, 0x80, 0x07, 0x76]), 0x01),  # RLCA (modeled as RLC A)
        (bytes([0xAF, 0x3E, 0x01, 0x0F, 0x76]), 0x80),  # RRCA (modeled as RRC A)
        (bytes([0xAF, 0x3E, 0x80, 0x37, 0x17, 0x76]), 0x01),  # RLA (modeled as RL A)
        (bytes([0xAF, 0x3E, 0x01, 0x37, 0x1F, 0x76]), 0x80),  # RRA (modeled as RR A)
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_non_cb_rotate_a_preserves_z_and_clears_hn(z80_binary, tmp_path, rom_bytes, expected_a):
    rom = tmp_path / "rotate_a_flags.rom"
    # Common precondition: XOR A sets Z=1. These non-CB rotates must preserve Z.
    rom.write_bytes(rom_bytes)

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == expected_a
    assert (flags & 0x02) != 0  # FLAG_Z preserved from XOR A
    assert (flags & 0x04) == 0  # FLAG_H cleared
    assert (flags & 0x10) == 0  # FLAG_N cleared
    assert (flags & 0x20) != 0  # FLAG_C set by chosen operands


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jp_nn_branches_to_target(z80_binary, tmp_path):
    rom = tmp_path / "jp_nn.rom"
    # JP 0x0005 ; LD A,0x11 ; LD A,0x77
    rom.write_bytes(bytes([0xC3, 0x05, 0x00, 0x3E, 0x11, 0x3E, 0x77]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "17"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x77


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_add_a_n_updates_register(z80_binary, tmp_path):
    rom = tmp_path / "add_a_n.rom"
    # LD A,0x10 ; ADD A,0x22
    rom.write_bytes(bytes([0x3E, 0x10, 0xC6, 0x22]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "14"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x32


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_adc_a_n_uses_carry_input(z80_binary, tmp_path):
    rom = tmp_path / "adc_a_n.rom"
    # LD A,0xFF ; ADD A,0x01 (sets C) ; ADC A,0x00
    rom.write_bytes(bytes([0x3E, 0xFF, 0xC6, 0x01, 0xCE, 0x00]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "30"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x01


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_sbc_a_n_uses_carry_input(z80_binary, tmp_path):
    rom = tmp_path / "sbc_a_n.rom"
    # LD A,0x00 ; SUB A,0x01 (sets C) ; SBC A,0x01
    rom.write_bytes(bytes([0x3E, 0x00, 0xD6, 0x01, 0xDE, 0x01]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "30"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0xFD


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_add_a_n_sets_overflow_and_halfcarry_flags(z80_binary, tmp_path):
    rom = tmp_path / "add_a_n_flags.rom"
    # LD A,0x7F ; ADD A,0x01 ; HALT
    rom.write_bytes(bytes([0x3E, 0x7F, 0xC6, 0x01, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "60"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x80
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x20) == 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_adc_a_r_with_carry_sets_overflow_and_halfcarry_flags(z80_binary, tmp_path):
    rom = tmp_path / "adc_a_r_flags.rom"
    # LD A,0x7F ; LD B,0x00 ; SCF ; ADC A,B ; HALT
    rom.write_bytes(bytes([0x3E, 0x7F, 0x06, 0x00, 0x37, 0x88, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x80
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x20) == 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_sub_a_n_sets_overflow_and_halfborrow_flags(z80_binary, tmp_path):
    rom = tmp_path / "sub_a_n_flags.rom"
    # LD A,0x80 ; SUB A,0x01 ; HALT
    rom.write_bytes(bytes([0x3E, 0x80, 0xD6, 0x01, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "60"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x7F
    assert (flags & 0x01) == 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) != 0  # FLAG_N
    assert (flags & 0x20) == 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_sbc_a_r_with_carry_sets_borrow_and_halfborrow_flags(z80_binary, tmp_path):
    rom = tmp_path / "sbc_a_r_flags.rom"
    # LD A,0x00 ; LD B,0x00 ; SCF ; SBC A,B ; HALT
    rom.write_bytes(bytes([0x3E, 0x00, 0x06, 0x00, 0x37, 0x98, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0xFF
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) == 0  # FLAG_P (no overflow)
    assert (flags & 0x10) != 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C


@pytest.mark.parametrize("prefix", [0xDD, 0xFD])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_add_a_indexed_sets_overflow_and_halfcarry_flags(z80_binary, tmp_path, prefix):
    rom = tmp_path / f"add_a_indexed_flags_{prefix:02x}.rom"
    # (0x2005)=0x01 ; LD A,0x7F ; LD II,0x2000 ; ADD A,(II+5) ; HALT
    rom.write_bytes(
        bytes(
            [
                0x21,
                0x05,
                0x20,
                0x36,
                0x01,
                0x3E,
                0x7F,
                prefix,
                0x21,
                0x00,
                0x20,
                prefix,
                0x86,
                0x05,
                0x76,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "140"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x80
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x20) == 0  # FLAG_C


@pytest.mark.parametrize("prefix", [0xDD, 0xFD])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_sbc_a_indexed_with_carry_sets_borrow_and_halfborrow_flags(
    z80_binary, tmp_path, prefix
):
    rom = tmp_path / f"sbc_a_indexed_flags_{prefix:02x}.rom"
    # (0x2005)=0x00 ; LD A,0x00 ; LD II,0x2000 ; SCF ; SBC A,(II+5) ; HALT
    rom.write_bytes(
        bytes(
            [
                0x21,
                0x05,
                0x20,
                0x36,
                0x00,
                0x3E,
                0x00,
                prefix,
                0x21,
                0x00,
                0x20,
                0x37,
                prefix,
                0x9E,
                0x05,
                0x76,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "150"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0xFF
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) == 0  # FLAG_P (no overflow)
    assert (flags & 0x10) != 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_adc_hl_bc_sets_overflow_and_halfcarry_flags(z80_binary, tmp_path):
    rom = tmp_path / "adc_hl_bc_flags.rom"
    # HL=0x7FFF ; BC=0x0001 ; ADC HL,BC -> 0x8000 (overflow, half-carry, no carry-out)
    rom.write_bytes(bytes([0x26, 0x7F, 0x2E, 0xFF, 0x06, 0x00, 0x0E, 0x01, 0xED, 0x4A, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 5) == 0x80  # H
    assert _parse_reg(proc.stdout, 6) == 0x00  # L
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x20) == 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_adc_hl_sp_sets_carry_and_zero_without_overflow(z80_binary, tmp_path):
    rom = tmp_path / "adc_hl_sp_carry_zero.rom"
    # HL=0xFFFF ; SP=0x0001 ; ADC HL,SP -> 0x0000 (carry, zero, half-carry, no overflow)
    rom.write_bytes(bytes([0x26, 0xFF, 0x2E, 0xFF, 0x31, 0x01, 0x00, 0xED, 0x7A, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 5) == 0x00  # H
    assert _parse_reg(proc.stdout, 6) == 0x00  # L
    assert (flags & 0x01) == 0  # FLAG_S
    assert (flags & 0x02) != 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) == 0  # FLAG_P (no overflow)
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_sbc_hl_bc_sets_overflow_and_halfborrow_flags(z80_binary, tmp_path):
    rom = tmp_path / "sbc_hl_bc_flags.rom"
    # HL=0x8000 ; BC=0x0001 ; SBC HL,BC -> 0x7FFF (overflow, half-borrow, no borrow-out)
    rom.write_bytes(bytes([0x26, 0x80, 0x2E, 0x00, 0x06, 0x00, 0x0E, 0x01, 0xED, 0x42, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 5) == 0x7F  # H
    assert _parse_reg(proc.stdout, 6) == 0xFF  # L
    assert (flags & 0x01) == 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) != 0  # FLAG_N
    assert (flags & 0x20) == 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_sbc_hl_bc_with_carry_in_sets_borrow_and_sign(z80_binary, tmp_path):
    rom = tmp_path / "sbc_hl_bc_carry_in.rom"
    # HL=0x0000 ; BC=0x0000 ; SCF ; SBC HL,BC -> 0xFFFF (borrow, sign, half-borrow, no overflow)
    rom.write_bytes(bytes([0x26, 0x00, 0x2E, 0x00, 0x06, 0x00, 0x0E, 0x00, 0x37, 0xED, 0x42, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 5) == 0xFF  # H
    assert _parse_reg(proc.stdout, 6) == 0xFF  # L
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) == 0  # FLAG_P (no overflow)
    assert (flags & 0x10) != 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_and_a_n_updates_accumulator_and_zero_flag(z80_binary, tmp_path):
    rom = tmp_path / "and_a_n.rom"
    # LD A,0xF0 ; AND A,0x0F
    rom.write_bytes(bytes([0x3E, 0xF0, 0xE6, 0x0F]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "20"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_xor_a_n_updates_accumulator(z80_binary, tmp_path):
    rom = tmp_path / "xor_a_n.rom"
    # LD A,0xFF ; XOR A,0x0F
    rom.write_bytes(bytes([0x3E, 0xFF, 0xEE, 0x0F]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "20"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0xF0


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_or_a_n_updates_accumulator(z80_binary, tmp_path):
    rom = tmp_path / "or_a_n.rom"
    # LD A,0x10 ; OR A,0x03
    rom.write_bytes(bytes([0x3E, 0x10, 0xF6, 0x03]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "20"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x13


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cp_a_n_sets_flags_without_modifying_a(z80_binary, tmp_path):
    rom = tmp_path / "cp_a_n.rom"
    # LD A,0x22 ; CP A,0x22
    rom.write_bytes(bytes([0x3E, 0x22, 0xFE, 0x22]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "20"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x22
    assert (flags & 0x02) != 0  # FLAG_Z
    assert (flags & 0x10) != 0  # FLAG_N


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_and_a_n_sets_halfcarry_and_parity_flags(z80_binary, tmp_path):
    rom = tmp_path / "and_a_n_flags.rom"
    # LD A,0x03 ; AND A,0x03 ; HALT
    rom.write_bytes(bytes([0x3E, 0x03, 0xE6, 0x03, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x03
    assert (flags & 0x04) != 0  # FLAG_H set by AND
    assert (flags & 0x08) != 0  # FLAG_P set (even parity)
    assert (flags & 0x20) == 0  # FLAG_C clear
    assert (flags & 0x10) == 0  # FLAG_N clear


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_xor_a_n_sets_parity_and_clears_halfcarry(z80_binary, tmp_path):
    rom = tmp_path / "xor_a_n_flags.rom"
    # LD A,0x0F ; XOR A,0x03 -> 0x0C ; HALT
    rom.write_bytes(bytes([0x3E, 0x0F, 0xEE, 0x03, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x0C
    assert (flags & 0x08) != 0  # FLAG_P set (even parity)
    assert (flags & 0x04) == 0  # FLAG_H clear
    assert (flags & 0x20) == 0  # FLAG_C clear
    assert (flags & 0x10) == 0  # FLAG_N clear


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_or_a_n_clears_parity_on_odd_result(z80_binary, tmp_path):
    rom = tmp_path / "or_a_n_parity.rom"
    # LD A,0x01 ; OR A,0x00 -> odd parity ; HALT
    rom.write_bytes(bytes([0x3E, 0x01, 0xF6, 0x00, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x01
    assert (flags & 0x08) == 0  # FLAG_P clear (odd parity)
    assert (flags & 0x04) == 0  # FLAG_H clear
    assert (flags & 0x20) == 0  # FLAG_C clear
    assert (flags & 0x10) == 0  # FLAG_N clear


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cp_a_n_sets_overflow_and_halfborrow_flags(z80_binary, tmp_path):
    rom = tmp_path / "cp_a_n_overflow_halfborrow.rom"
    # LD A,0x80 ; CP A,0x01 ; HALT  -> 0x80 - 0x01 = 0x7F (overflow, half-borrow)
    rom.write_bytes(bytes([0x3E, 0x80, 0xFE, 0x01, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x80  # CP does not modify A
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x04) != 0  # FLAG_H (half-borrow)
    assert (flags & 0x20) == 0  # FLAG_C clear
    assert (flags & 0x10) != 0  # FLAG_N set


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cp_iyd_sets_overflow_and_halfborrow_flags(z80_binary, tmp_path):
    rom = tmp_path / "cp_iyd_overflow_halfborrow.rom"
    # Prepare (IY+5)=0x01, then LD A,0x80 ; CP (IY+5) ; HALT
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x01,
                0x26,
                0x20,
                0x2E,
                0x05,
                0x77,
                0x3E,
                0x80,
                0xFD,
                0x21,
                0x00,
                0x20,
                0xFD,
                0xBE,
                0x05,
                0x76,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x80  # CP does not modify A
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x04) != 0  # FLAG_H (half-borrow)
    assert (flags & 0x20) == 0  # FLAG_C clear
    assert (flags & 0x10) != 0  # FLAG_N set


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_i_a_and_ld_a_i_round_trip(z80_binary, tmp_path):
    rom = tmp_path / "ld_i_a_ld_a_i.rom"
    # LD A,0x5A ; LD I,A ; LD A,0x00 ; LD A,I
    rom.write_bytes(bytes([0x3E, 0x5A, 0xED, 0x47, 0x3E, 0x00, 0xED, 0x57]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "50"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x5A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_r_a_and_ld_a_r_round_trip(z80_binary, tmp_path):
    rom = tmp_path / "ld_r_a_ld_a_r.rom"
    # LD A,0x3C ; LD R,A ; LD A,0x00 ; LD A,R
    rom.write_bytes(bytes([0x3E, 0x3C, 0xED, 0x4F, 0x3E, 0x00, 0xED, 0x5F]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "50"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x3C


@pytest.mark.parametrize(("store_subop", "load_subop"), [(0x47, 0x57), (0x4F, 0x5F)])
@pytest.mark.parametrize(("irq_opcode", "expect_p"), [(0xFB, True), (0xF3, False)])
@pytest.mark.parametrize(("value", "expect_z", "expect_s"), [(0x80, False, True), (0x00, True, False)])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_a_i_r_flags_follow_irq_state_and_preserve_carry(
    z80_binary, tmp_path, store_subop, load_subop, irq_opcode, expect_p, value, expect_z, expect_s
):
    rom = tmp_path / f"ld_a_ir_flags_{store_subop:02x}_{irq_opcode:02x}_{value:02x}.rom"
    rom.write_bytes(
        bytes(
            [
                0x3E,
                value,  # LD A,value
                0xED,
                store_subop,  # LD I/R,A
                0x37,  # SCF (carry should be preserved)
                irq_opcode,  # EI or DI
                0x3E,
                0xAA,  # LD A, junk
                0xED,
                load_subop,  # LD A,I/R
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == value
    assert ((flags & 0x02) != 0) == expect_z
    assert ((flags & 0x01) != 0) == expect_s
    assert ((flags & 0x08) != 0) == expect_p
    assert (flags & 0x04) == 0  # FLAG_H
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C preserved from SCF


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_add_hl_ss_accumulates_16bit_pairs(z80_binary, tmp_path):
    rom = tmp_path / "add_hl_ss.rom"
    # LD HL,0x1000 ; LD DE,0x0002 ; ADD HL,DE ; ADD HL,HL ; LD SP,0x0003 ; ADD HL,SP ; LD BC,0x0001 ; ADD HL,BC
    rom.write_bytes(bytes([0x21, 0x00, 0x10, 0x11, 0x02, 0x00, 0x19, 0x29, 0x31, 0x03, 0x00, 0x39, 0x01, 0x01, 0x00, 0x09]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "100"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_reg(proc.stdout, 5) == 0x20  # H
    assert _parse_reg(proc.stdout, 6) == 0x08  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_add_hl_bc_sets_halfcarry_without_carry(z80_binary, tmp_path):
    rom = tmp_path / "add_hl_bc_halfcarry.rom"
    # HL=0x0FFF ; BC=0x0001 ; ADD HL,BC -> 0x1000 with H=1 and C=0
    rom.write_bytes(bytes([0x21, 0xFF, 0x0F, 0x01, 0x01, 0x00, 0x09, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 5) == 0x10  # H
    assert _parse_reg(proc.stdout, 6) == 0x00  # L
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x20) == 0  # FLAG_C
    assert (flags & 0x10) == 0  # FLAG_N


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_add_hl_sp_sets_halfcarry_and_carry(z80_binary, tmp_path):
    rom = tmp_path / "add_hl_sp_carry.rom"
    # HL=0xFFFF ; SP=0x0001 ; ADD HL,SP -> 0x0000 with H=1 and C=1
    rom.write_bytes(bytes([0x21, 0xFF, 0xFF, 0x31, 0x01, 0x00, 0x39, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 5) == 0x00  # H
    assert _parse_reg(proc.stdout, 6) == 0x00  # L
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x20) != 0  # FLAG_C
    assert (flags & 0x10) == 0  # FLAG_N


@pytest.mark.parametrize("prefix", [0xDD, 0xFD])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_add_ii_ss_accumulates_16bit_pairs(z80_binary, tmp_path, prefix):
    rom = tmp_path / f"add_ii_ss_{prefix:02x}.rom"
    # LD II,0x1000 ; LD DE,0x0002 ; ADD II,DE ; ADD II,II ; LD SP,0x0003 ; ADD II,SP ; LD BC,0x0001 ; ADD II,BC ; LD SP,II
    rom.write_bytes(
        bytes(
            [
                prefix,
                0x21,
                0x00,
                0x10,
                0x11,
                0x02,
                0x00,
                prefix,
                0x19,
                prefix,
                0x29,
                0x31,
                0x03,
                0x00,
                prefix,
                0x39,
                0x01,
                0x01,
                0x00,
                prefix,
                0x09,
                prefix,
                0xF9,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "140"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_sp(proc.stdout) == 0x2008


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_add_ix_de_sets_halfcarry_without_carry(z80_binary, tmp_path):
    rom = tmp_path / "add_ix_de_halfcarry.rom"
    # IX=0x0FFF ; DE=0x0001 ; ADD IX,DE ; LD SP,IX
    rom.write_bytes(bytes([0xDD, 0x21, 0xFF, 0x0F, 0x11, 0x01, 0x00, 0xDD, 0x19, 0xDD, 0xF9, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_sp(proc.stdout) == 0x1000
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x20) == 0  # FLAG_C
    assert (flags & 0x10) == 0  # FLAG_N


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_add_iy_sp_sets_halfcarry_and_carry(z80_binary, tmp_path):
    rom = tmp_path / "add_iy_sp_carry.rom"
    # IY=0xFFFF ; SP=0x0001 ; ADD IY,SP ; LD SP,IY
    rom.write_bytes(bytes([0xFD, 0x21, 0xFF, 0xFF, 0x31, 0x01, 0x00, 0xFD, 0x39, 0xFD, 0xF9, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_sp(proc.stdout) == 0x0000
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x20) != 0  # FLAG_C
    assert (flags & 0x10) == 0  # FLAG_N


@pytest.mark.parametrize("prefix", [0xDD, 0xFD])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_inc_dec_ii_wrap_round_trip(z80_binary, tmp_path, prefix):
    rom = tmp_path / f"inc_dec_ii_{prefix:02x}.rom"
    # LD II,0xFFFF ; INC II ; DEC II ; LD SP,II
    rom.write_bytes(bytes([prefix, 0x21, 0xFF, 0xFF, prefix, 0x23, prefix, 0x2B, prefix, 0xF9]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_sp(proc.stdout) == 0xFFFF


@pytest.mark.parametrize("prefix", [0xDD, 0xFD])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_nn_ii_and_ld_ii_nn_ind_round_trip(z80_binary, tmp_path, prefix):
    rom = tmp_path / f"ld_nn_ii_roundtrip_{prefix:02x}.rom"
    # LD II,0x1234 ; LD (0x2040),II ; LD II,0 ; LD II,(0x2040) ; LD SP,II
    rom.write_bytes(
        bytes(
            [
                prefix,
                0x21,
                0x34,
                0x12,
                prefix,
                0x22,
                0x40,
                0x20,
                prefix,
                0x21,
                0x00,
                0x00,
                prefix,
                0x2A,
                0x40,
                0x20,
                prefix,
                0xF9,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "150"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_sp(proc.stdout) == 0x1234


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ex_de_hl_swaps_register_pairs(z80_binary, tmp_path):
    rom = tmp_path / "ex_de_hl.rom"
    # LD DE,0x1234 ; LD HL,0xABCD ; EX DE,HL ; LD A,H
    rom.write_bytes(bytes([0x11, 0x34, 0x12, 0x21, 0xCD, 0xAB, 0xEB, 0x7C]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "60"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x12
    assert _parse_reg(proc.stdout, 3) == 0xAB  # D
    assert _parse_reg(proc.stdout, 4) == 0xCD  # E
    assert _parse_reg(proc.stdout, 5) == 0x12  # H
    assert _parse_reg(proc.stdout, 6) == 0x34  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ex_af_af_prime_swaps_accumulator_and_flags(z80_binary, tmp_path):
    rom = tmp_path / "ex_af_af_prime.rom"
    # LD A,0x12 ; SCF ; EX AF,AF' ; SCF ; CPL ; EX AF,AF' ; HALT
    rom.write_bytes(bytes([0x3E, 0x12, 0x37, 0x08, 0x37, 0x2F, 0x08, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x12
    assert (flags & 0x20) != 0  # FLAG_C restored from shadow AF'
    assert (flags & 0x04) == 0  # FLAG_H not leaked from active AF
    assert (flags & 0x10) == 0  # FLAG_N not leaked from active AF


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_scf_ccf_cpl_update_flags_and_accumulator(z80_binary, tmp_path):
    rom = tmp_path / "scf_ccf_cpl.rom"
    # LD A,0x55 ; SCF ; CCF ; CPL
    rom.write_bytes(bytes([0x3E, 0x55, 0x37, 0x3F, 0x2F]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "30"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0xAA
    assert (flags & 0x20) == 0  # FLAG_C clear after SCF then CCF
    assert (flags & 0x04) != 0  # FLAG_H set by CCF(old C=1), also set by CPL
    assert (flags & 0x10) != 0  # FLAG_N set by CPL


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ccf_sets_halfcarry_from_previous_carry(z80_binary, tmp_path):
    rom = tmp_path / "ccf_old_carry_set.rom"
    # SCF ; CCF ; HALT
    rom.write_bytes(bytes([0x37, 0x3F, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert (flags & 0x20) == 0  # FLAG_C toggled from 1 to 0
    assert (flags & 0x04) != 0  # FLAG_H = old carry = 1
    assert (flags & 0x10) == 0  # FLAG_N cleared


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ccf_clears_halfcarry_when_previous_carry_clear(z80_binary, tmp_path):
    rom = tmp_path / "ccf_old_carry_clear.rom"
    # CCF ; HALT
    rom.write_bytes(bytes([0x3F, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "30"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert (flags & 0x20) != 0  # FLAG_C toggled from 0 to 1
    assert (flags & 0x04) == 0  # FLAG_H = old carry = 0
    assert (flags & 0x10) == 0  # FLAG_N cleared


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_daa_adjusts_bcd_after_add(z80_binary, tmp_path):
    rom = tmp_path / "daa.rom"
    # LD A,0x09 ; ADD A,0x01 ; DAA
    rom.write_bytes(bytes([0x3E, 0x09, 0xC6, 0x01, 0x27]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "30"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x10
    assert (flags & 0x20) == 0  # FLAG_C
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) == 0  # FLAG_P (odd parity)
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x01) == 0  # FLAG_S


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_daa_adjusts_bcd_after_subtract(z80_binary, tmp_path):
    rom = tmp_path / "daa_sub.rom"
    # LD A,0x10 ; SUB A,0x01 ; DAA
    rom.write_bytes(bytes([0x3E, 0x10, 0xD6, 0x01, 0x27]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "30"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x09
    assert (flags & 0x20) == 0  # FLAG_C
    assert (flags & 0x10) != 0  # FLAG_N preserved for subtraction
    assert (flags & 0x04) == 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (even parity)
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x01) == 0  # FLAG_S


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_neg_inverts_accumulator_and_sets_carry_when_nonzero(z80_binary, tmp_path):
    rom = tmp_path / "neg.rom"
    # LD A,0x01 ; NEG
    rom.write_bytes(bytes([0x3E, 0x01, 0xED, 0x44]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "20"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0xFF
    assert (flags & 0x20) != 0  # FLAG_C
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) == 0  # FLAG_P
    assert (flags & 0x10) != 0  # FLAG_N


@pytest.mark.parametrize("subop", [0x44, 0x4C, 0x54, 0x5C, 0x64, 0x6C, 0x74, 0x7C])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_neg_alias_opcodes_decode_and_match_semantics(z80_binary, tmp_path, subop):
    rom = tmp_path / f"neg_alias_{subop:02x}.rom"
    rom.write_bytes(bytes([0x3E, 0x01, 0xED, subop]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "20"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0xFF
    assert (flags & 0x20) != 0  # FLAG_C
    assert (flags & 0x10) != 0  # FLAG_N


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_neg_sets_overflow_on_most_negative_value(z80_binary, tmp_path):
    rom = tmp_path / "neg_overflow.rom"
    # LD A,0x80 ; NEG
    rom.write_bytes(bytes([0x3E, 0x80, 0xED, 0x44]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "20"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x80
    assert (flags & 0x20) != 0  # FLAG_C
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x04) == 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) != 0  # FLAG_N


@pytest.mark.parametrize("subop", [0x46, 0x4E, 0x66, 0x6E, 0x56, 0x76, 0x5E, 0x7E])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_im_alias_opcodes_decode_and_continue_execution(z80_binary, tmp_path, subop):
    rom = tmp_path / f"im_alias_{subop:02x}.rom"
    # IM x alias ; LD A,0x66
    rom.write_bytes(bytes([0xED, subop, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "30"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_rrd_rotates_nibbles_between_a_and_hli(z80_binary, tmp_path):
    rom = tmp_path / "rrd.rom"
    # LD HL,0x2040 ; LD A,0x34 ; LD (HL),A ; LD A,0x12 ; SCF ; RRD ; LD B,A ; LD A,(HL)
    rom.write_bytes(bytes([0x21, 0x40, 0x20, 0x3E, 0x34, 0x77, 0x3E, 0x12, 0x37, 0xED, 0x67, 0x47, 0x7E]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "100"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 1) == 0x14  # B got post-RRD A
    assert _parse_r0(proc.stdout) == 0x23      # A loaded from updated (HL)
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x01) == 0  # FLAG_S
    assert (flags & 0x04) == 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (0x14 even parity)
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C preserved from SCF


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_rld_rotates_nibbles_between_a_and_hli(z80_binary, tmp_path):
    rom = tmp_path / "rld.rom"
    # LD HL,0x2040 ; LD A,0x34 ; LD (HL),A ; LD A,0x12 ; SCF ; RLD ; LD B,A ; LD A,(HL)
    rom.write_bytes(bytes([0x21, 0x40, 0x20, 0x3E, 0x34, 0x77, 0x3E, 0x12, 0x37, 0xED, 0x6F, 0x47, 0x7E]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "100"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 1) == 0x13  # B got post-RLD A
    assert _parse_r0(proc.stdout) == 0x42      # A loaded from updated (HL)
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x01) == 0  # FLAG_S
    assert (flags & 0x04) == 0  # FLAG_H
    assert (flags & 0x08) == 0  # FLAG_P (0x13 odd parity)
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C preserved from SCF


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_dd_nn_loads_register_pairs(z80_binary, tmp_path):
    rom = tmp_path / "ld_dd_nn.rom"
    # LD BC,0x1234 ; LD DE,0x5678 ; LD HL,0x9ABC ; LD A,B
    rom.write_bytes(bytes([0x01, 0x34, 0x12, 0x11, 0x78, 0x56, 0x21, 0xBC, 0x9A, 0x78]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x12
    assert _parse_reg(proc.stdout, 1) == 0x12  # B
    assert _parse_reg(proc.stdout, 2) == 0x34  # C
    assert _parse_reg(proc.stdout, 3) == 0x56  # D
    assert _parse_reg(proc.stdout, 4) == 0x78  # E
    assert _parse_reg(proc.stdout, 5) == 0x9A  # H
    assert _parse_reg(proc.stdout, 6) == 0xBC  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_sp_hl_transfers_hl_into_stack_pointer(z80_binary, tmp_path):
    rom = tmp_path / "ld_sp_hl.rom"
    # LD HL,0x3456 ; LD SP,HL ; LD BC,0x1234 ; PUSH BC ; LD BC,0 ; POP BC ; LD A,B
    rom.write_bytes(
        bytes([0x21, 0x56, 0x34, 0xF9, 0x01, 0x34, 0x12, 0xC5, 0x01, 0x00, 0x00, 0xC1, 0x78])
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_sp(proc.stdout) == 0x3456
    assert _parse_r0(proc.stdout) == 0x12


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_sp_ix_transfers_ix_into_stack_pointer(z80_binary, tmp_path):
    rom = tmp_path / "ld_sp_ix.rom"
    # LD IX,0x4567 ; LD SP,IX
    rom.write_bytes(bytes([0xDD, 0x21, 0x67, 0x45, 0xDD, 0xF9]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "30"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_sp(proc.stdout) == 0x4567


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_sp_iy_transfers_iy_into_stack_pointer(z80_binary, tmp_path):
    rom = tmp_path / "ld_sp_iy.rom"
    # LD IY,0x6789 ; LD SP,IY
    rom.write_bytes(bytes([0xFD, 0x21, 0x89, 0x67, 0xFD, 0xF9]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "30"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_sp(proc.stdout) == 0x6789


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_push_pop_ix_round_trip_restores_index_register(z80_binary, tmp_path):
    rom = tmp_path / "push_pop_ix.rom"
    # Seed [0x2233]=0x5A, round-trip IX through stack, then read [IX+0].
    rom.write_bytes(
        bytes(
            [
                0x21,
                0x33,
                0x22,
                0x3E,
                0x5A,
                0x77,
                0x31,
                0x00,
                0x24,
                0xDD,
                0x21,
                0x33,
                0x22,
                0xDD,
                0xE5,
                0xDD,
                0x21,
                0x00,
                0x00,
                0xDD,
                0xE1,
                0x3E,
                0x00,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "180"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_sp(proc.stdout) == 0x2400
    assert _parse_r0(proc.stdout) == 0x5A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_push_pop_iy_round_trip_restores_index_register(z80_binary, tmp_path):
    rom = tmp_path / "push_pop_iy.rom"
    # Seed [0x2334]=0x3C, round-trip IY through stack, then read [IY+0].
    rom.write_bytes(
        bytes(
            [
                0x21,
                0x34,
                0x23,
                0x3E,
                0x3C,
                0x77,
                0x31,
                0x10,
                0x24,
                0xFD,
                0x21,
                0x34,
                0x23,
                0xFD,
                0xE5,
                0xFD,
                0x21,
                0x00,
                0x00,
                0xFD,
                0xE1,
                0x3E,
                0x00,
                0xFD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "180"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_sp(proc.stdout) == 0x2410
    assert _parse_r0(proc.stdout) == 0x3C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_nn_a_then_ld_a_nn_round_trips_memory(z80_binary, tmp_path):
    rom = tmp_path / "ld_nn_a_ld_a_nn.rom"
    # LD A,0x5A ; LD (0x2042),A ; LD A,0x00 ; LD A,(0x2042)
    rom.write_bytes(bytes([0x3E, 0x5A, 0x32, 0x42, 0x20, 0x3E, 0x00, 0x3A, 0x42, 0x20]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "44"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x5A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_nn_hl_and_ld_hl_nn_ind_round_trip_pair(z80_binary, tmp_path):
    rom = tmp_path / "ld_nn_hl_ld_hl_nn_ind.rom"
    # LD HL,0x1234 ; LD (0x2040),HL ; LD HL,0 ; LD HL,(0x2040)
    rom.write_bytes(bytes([0x21, 0x34, 0x12, 0x22, 0x40, 0x20, 0x21, 0x00, 0x00, 0x2A, 0x40, 0x20]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "70"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_reg(proc.stdout, 5) == 0x12  # H
    assert _parse_reg(proc.stdout, 6) == 0x34  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_nn_ss_ed_and_ld_ss_nn_ed_round_trip_bc(z80_binary, tmp_path):
    rom = tmp_path / "ld_nn_ss_ed_ld_ss_nn_ed_bc.rom"
    # LD BC,0x1234 ; LD (0x2040),BC ; LD BC,0 ; LD BC,(0x2040) ; LD A,B
    rom.write_bytes(bytes([0x01, 0x34, 0x12, 0xED, 0x43, 0x40, 0x20, 0x01, 0x00, 0x00, 0xED, 0x4B, 0x40, 0x20, 0x78]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x12
    assert _parse_reg(proc.stdout, 2) == 0x34  # C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_nn_ss_ed_and_ld_ss_nn_ed_round_trip_sp(z80_binary, tmp_path):
    rom = tmp_path / "ld_nn_ss_ed_ld_ss_nn_ed_sp.rom"
    # LD SP,0x5678 ; LD (0x2042),SP ; LD SP,0 ; LD SP,(0x2042)
    rom.write_bytes(bytes([0x31, 0x78, 0x56, 0xED, 0x73, 0x42, 0x20, 0x31, 0x00, 0x00, 0xED, 0x7B, 0x42, 0x20]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_sp(proc.stdout) == 0x5678


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_nn_ss_ed_and_ld_ss_nn_ed_round_trip_de(z80_binary, tmp_path):
    rom = tmp_path / "ld_nn_ss_ed_ld_ss_nn_ed_de.rom"
    # LD DE,0x89AB ; LD (0x2044),DE ; LD DE,0 ; LD DE,(0x2044) ; LD A,D
    rom.write_bytes(bytes([0x11, 0xAB, 0x89, 0xED, 0x53, 0x44, 0x20, 0x11, 0x00, 0x00, 0xED, 0x5B, 0x44, 0x20, 0x7A]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x89
    assert _parse_reg(proc.stdout, 4) == 0xAB  # E


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_nn_ss_ed_and_ld_ss_nn_ed_round_trip_hl(z80_binary, tmp_path):
    rom = tmp_path / "ld_nn_ss_ed_ld_ss_nn_ed_hl.rom"
    # LD HL,0x4567 ; LD (0x2046),HL ; LD HL,0 ; LD HL,(0x2046) ; LD A,H
    rom.write_bytes(bytes([0x21, 0x67, 0x45, 0xED, 0x63, 0x46, 0x20, 0x21, 0x00, 0x00, 0xED, 0x6B, 0x46, 0x20, 0x7C]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x45
    assert _parse_reg(proc.stdout, 6) == 0x67  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_bc_de_indirect_and_accumulator_round_trip(z80_binary, tmp_path):
    rom = tmp_path / "ld_bc_de_indirect_roundtrip.rom"
    # LD BC,0x2040 ; LD DE,0x2041 ; LD A,0x5A ; LD (BC),A ; LD A,0 ; LD A,(BC) ; LD (DE),A ; LD A,0 ; LD A,(DE)
    rom.write_bytes(
        bytes([0x01, 0x40, 0x20, 0x11, 0x41, 0x20, 0x3E, 0x5A, 0x02, 0x3E, 0x00, 0x0A, 0x12, 0x3E, 0x00, 0x1A])
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x5A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_hli_n_writes_immediate_then_ld_a_hli_reads_it(z80_binary, tmp_path):
    rom = tmp_path / "ld_hli_n_then_ld_a_hli.rom"
    # LD HL,0x2042 ; LD (HL),0x7B ; LD A,(HL)
    rom.write_bytes(bytes([0x21, 0x42, 0x20, 0x36, 0x7B, 0x7E]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x7B


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_inc_dec_ss_update_16bit_pairs_and_stack_pointer(z80_binary, tmp_path):
    rom = tmp_path / "inc_dec_ss.rom"
    # LD BC,0x00FF ; INC BC ; DEC BC ; LD SP,0x3456 ; INC SP ; DEC SP
    rom.write_bytes(bytes([0x01, 0xFF, 0x00, 0x03, 0x0B, 0x31, 0x56, 0x34, 0x33, 0x3B]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "60"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 2) == 0xFF  # C
    assert _parse_sp(proc.stdout) == 0x3456


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_inc_dec_r_decode_uses_bits_5_to_3_register_selector(z80_binary, tmp_path):
    rom = tmp_path / "inc_dec_r_selector.rom"
    # LD C,0x10 ; INC C (0x0C) ; DEC C (0x0D) ; LD A,C
    rom.write_bytes(bytes([0x0E, 0x10, 0x0C, 0x0D, 0x79]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "30"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x10


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_inc_r_sets_overflow_halfcarry_and_preserves_carry(z80_binary, tmp_path):
    rom = tmp_path / "inc_r_flags.rom"
    # LD B,0x7F ; SCF ; INC B ; LD A,B ; HALT
    rom.write_bytes(bytes([0x06, 0x7F, 0x37, 0x04, 0x78, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "60"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x80
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C preserved


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_dec_r_sets_overflow_halfborrow_and_preserves_carry(z80_binary, tmp_path):
    rom = tmp_path / "dec_r_flags.rom"
    # LD B,0x80 ; SCF ; DEC B ; LD A,B ; HALT
    rom.write_bytes(bytes([0x06, 0x80, 0x37, 0x05, 0x78, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "60"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x7F
    assert (flags & 0x01) == 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) != 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C preserved


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_inc_hli_sets_overflow_halfcarry_and_preserves_carry(z80_binary, tmp_path):
    rom = tmp_path / "inc_hli_flags.rom"
    # LD HL,0x2040 ; LD (HL),0x7F ; SCF ; INC (HL) ; LD A,(HL) ; HALT
    rom.write_bytes(bytes([0x21, 0x40, 0x20, 0x36, 0x7F, 0x37, 0x34, 0x7E, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x80
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C preserved


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_inc_ixd_sets_overflow_halfcarry_and_preserves_carry(z80_binary, tmp_path):
    rom = tmp_path / "inc_ixd_flags.rom"
    # LD IX,0x2000 ; LD (IX+5),0x7F ; SCF ; INC (IX+5) ; LD A,(IX+5) ; HALT
    rom.write_bytes(bytes([0xDD, 0x21, 0x00, 0x20, 0xDD, 0x36, 0x05, 0x7F, 0x37, 0xDD, 0x34, 0x05, 0xDD, 0x7E, 0x05, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "150"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x80
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C preserved


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_dec_iyd_sets_overflow_halfborrow_and_preserves_carry(z80_binary, tmp_path):
    rom = tmp_path / "dec_iyd_flags.rom"
    # LD IY,0x2100 ; LD (IY+6),0x80 ; SCF ; DEC (IY+6) ; LD A,(IY+6) ; HALT
    rom.write_bytes(bytes([0xFD, 0x21, 0x00, 0x21, 0xFD, 0x36, 0x06, 0x80, 0x37, 0xFD, 0x35, 0x06, 0xFD, 0x7E, 0x06, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "150"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x7F
    assert (flags & 0x01) == 0  # FLAG_S
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) != 0  # FLAG_P (overflow)
    assert (flags & 0x10) != 0  # FLAG_N
    assert (flags & 0x20) != 0  # FLAG_C preserved


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_push_pop_bc_round_trip(z80_binary, tmp_path):
    rom = tmp_path / "push_pop_bc.rom"
    # LD SP,0x2102 ; LD BC,0x1234 ; PUSH BC ; LD BC,0 ; POP BC ; LD A,B
    rom.write_bytes(bytes([0x31, 0x02, 0x21, 0x01, 0x34, 0x12, 0xC5, 0x01, 0x00, 0x00, 0xC1, 0x78]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "70"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x12
    assert _parse_reg(proc.stdout, 1) == 0x12  # B
    assert _parse_reg(proc.stdout, 2) == 0x34  # C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_push_pop_af_restores_accumulator_and_flags(z80_binary, tmp_path):
    rom = tmp_path / "push_pop_af.rom"
    # LD SP,0x2102 ; LD A,1 ; SUB A,1 ; PUSH AF ; LD A,0xFF ; ADD A,1 ; POP AF
    rom.write_bytes(bytes([0x31, 0x02, 0x21, 0x3E, 0x01, 0xD6, 0x01, 0xF5, 0x3E, 0xFF, 0xC6, 0x01, 0xF1]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z restored
    assert (flags & 0x10) != 0  # FLAG_N restored
    assert (flags & 0x20) == 0  # FLAG_C remains clear from SUB 1,1


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_inc_dec_hli_updates_memory_and_flags(z80_binary, tmp_path):
    rom = tmp_path / "inc_dec_hli.rom"
    # LD HL,0x2040 ; LD A,0 ; LD (HL),A ; INC (HL) ; DEC (HL) ; LD A,(HL)
    rom.write_bytes(bytes([0x21, 0x40, 0x20, 0x3E, 0x00, 0x77, 0x34, 0x35, 0x7E]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "60"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x00
    assert (_parse_flags(proc.stdout) & 0x10) != 0  # FLAG_N set by DEC


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_adc_hl_bc_uses_carry_and_updates_hl(z80_binary, tmp_path):
    rom = tmp_path / "adc_hl_bc.rom"
    # LD A,0xFF ; ADD A,0x01 (C=1) ; LD HL,0x1000 ; LD BC,0x0001 ; ADC HL,BC
    rom.write_bytes(bytes([0x3E, 0xFF, 0xC6, 0x01, 0x21, 0x00, 0x10, 0x01, 0x01, 0x00, 0xED, 0x4A]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "70"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_reg(proc.stdout, 5) == 0x10  # H
    assert _parse_reg(proc.stdout, 6) == 0x02  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_sbc_hl_bc_uses_carry_and_updates_hl(z80_binary, tmp_path):
    rom = tmp_path / "sbc_hl_bc.rom"
    # LD A,0x00 ; SUB A,0x01 (C=1) ; LD HL,0x1003 ; LD BC,0x0001 ; SBC HL,BC
    rom.write_bytes(bytes([0x3E, 0x00, 0xD6, 0x01, 0x21, 0x03, 0x10, 0x01, 0x01, 0x00, 0xED, 0x42]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "70"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_reg(proc.stdout, 5) == 0x10  # H
    assert _parse_reg(proc.stdout, 6) == 0x01  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jp_hli_branches_to_hl_target(z80_binary, tmp_path):
    rom = tmp_path / "jp_hli.rom"
    # LD HL,0x0007 ; JP (HL) ; LD A,0x11 ; NOP ; LD A,0x66
    rom.write_bytes(bytes([0x21, 0x07, 0x00, 0xE9, 0x3E, 0x11, 0x00, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jp_ix_branches_to_ix_target(z80_binary, tmp_path):
    rom = tmp_path / "jp_ix.rom"
    # LD IX,0x0008 ; JP (IX) ; LD A,0x11 ; LD A,0x66
    rom.write_bytes(bytes([0xDD, 0x21, 0x08, 0x00, 0xDD, 0xE9, 0x3E, 0x11, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jp_iy_branches_to_iy_target(z80_binary, tmp_path):
    rom = tmp_path / "jp_iy.rom"
    # LD IY,0x0008 ; JP (IY) ; LD A,0x11 ; LD A,0x66
    rom.write_bytes(bytes([0xFD, 0x21, 0x08, 0x00, 0xFD, 0xE9, 0x3E, 0x11, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_inc_dec_ixd_updates_indexed_memory(z80_binary, tmp_path):
    rom = tmp_path / "inc_dec_ixd.rom"
    # LD IX,0x2000 ; LD A,0 ; LD (IX+5),A ; INC (IX+5) ; DEC (IX+5) ; LD A,(IX+5)
    rom.write_bytes(bytes([0xDD, 0x21, 0x00, 0x20, 0x3E, 0x00, 0xDD, 0x77, 0x05, 0xDD, 0x34, 0x05, 0xDD, 0x35, 0x05, 0xDD, 0x7E, 0x05]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "140"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x10) != 0  # FLAG_N set by DEC


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_inc_dec_iyd_updates_indexed_memory(z80_binary, tmp_path):
    rom = tmp_path / "inc_dec_iyd.rom"
    # LD IY,0x2100 ; LD A,0 ; LD (IY+6),A ; INC (IY+6) ; DEC (IY+6) ; LD A,(IY+6)
    rom.write_bytes(bytes([0xFD, 0x21, 0x00, 0x21, 0x3E, 0x00, 0xFD, 0x77, 0x06, 0xFD, 0x34, 0x06, 0xFD, 0x35, 0x06, 0xFD, 0x7E, 0x06]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "140"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x10) != 0  # FLAG_N set by DEC


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_r_r_transfers_between_registers(z80_binary, tmp_path):
    rom = tmp_path / "ld_r_r.rom"
    # LD B,0xAB ; LD A,B
    rom.write_bytes(bytes([0x06, 0xAB, 0x78]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "11"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0xAB
    assert _parse_reg(proc.stdout, 1) == 0xAB


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_r_hli_reads_memory_operand(z80_binary, tmp_path):
    rom = tmp_path / "ld_r_hli.rom"
    # LD H,0x20 ; LD L,0x40 ; LD A,0x5C ; LD (HL),A ; LD B,(HL) ; LD A,B
    rom.write_bytes(bytes([0x26, 0x20, 0x2E, 0x40, 0x3E, 0x5C, 0x77, 0x46, 0x78]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x5C
    assert _parse_reg(proc.stdout, 1) == 0x5C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ld_hli_r_writes_memory_operand(z80_binary, tmp_path):
    rom = tmp_path / "ld_hli_r.rom"
    # LD H,0x20 ; LD L,0x41 ; LD B,0x3D ; LD (HL),B ; LD A,(HL)
    rom.write_bytes(bytes([0x26, 0x20, 0x2E, 0x41, 0x06, 0x3D, 0x70, 0x7E]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "36"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x3D


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_halt_stops_execution(z80_binary, tmp_path):
    rom = tmp_path / "halt.rom"
    # HALT ; LD A,0x77
    rom.write_bytes(bytes([0x76, 0x3E, 0x77]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "20"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x00


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_add_a_r_uses_low_opcode_bits_for_register_select(z80_binary, tmp_path):
    rom = tmp_path / "add_a_r_select.rom"
    # LD A,0x10 ; LD B,0x22 ; ADD A,B (0x80)
    rom.write_bytes(bytes([0x3E, 0x10, 0x06, 0x22, 0x80]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "18"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x32


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_sub_a_r_uses_low_opcode_bits_for_register_select(z80_binary, tmp_path):
    rom = tmp_path / "sub_a_r_select.rom"
    # LD A,0x22 ; LD B,0x11 ; SUB B (0x90)
    rom.write_bytes(bytes([0x3E, 0x22, 0x06, 0x11, 0x90]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "18"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x11


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jp_nz_nn_branches_when_zero_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "jp_nz_nn.rom"
    # JP NZ,0x0005 ; LD A,0x11 ; LD A,0x66
    rom.write_bytes(bytes([0xC2, 0x05, 0x00, 0x3E, 0x11, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "17"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jp_nc_nn_branches_when_carry_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "jp_nc_nn.rom"
    # JP NC,0x0005 ; LD A,0x11 ; LD A,0x66
    rom.write_bytes(bytes([0xD2, 0x05, 0x00, 0x3E, 0x11, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "17"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jp_c_nn_branches_when_carry_is_set(z80_binary, tmp_path):
    rom = tmp_path / "jp_c_nn.rom"
    # SCF ; JP C,0x0006 ; LD A,0x11 ; LD A,0x66
    rom.write_bytes(bytes([0x37, 0xDA, 0x06, 0x00, 0x3E, 0x11, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "21"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_dd_prefixed_ix_indexed_store_and_load(z80_binary, tmp_path):
    rom = tmp_path / "ix_indexed_roundtrip.rom"
    # LD IX,0x0020 ; LD A,0x5A ; LD (IX+0x10),A ; LD A,0x00 ; LD A,(IX+0x10)
    rom.write_bytes(
        bytes([0xDD, 0x21, 0x20, 0x00, 0x3E, 0x5A, 0xDD, 0x77, 0x10, 0x3E, 0x00, 0xDD, 0x7E, 0x10])
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "66"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x5A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_fd_prefixed_iy_indexed_store_and_load(z80_binary, tmp_path):
    rom = tmp_path / "iy_indexed_roundtrip.rom"
    # LD IY,0x0030 ; LD A,0x3C ; LD (IY+0x12),A ; LD A,0x00 ; LD A,(IY+0x12)
    rom.write_bytes(
        bytes([0xFD, 0x21, 0x30, 0x00, 0x3E, 0x3C, 0xFD, 0x77, 0x12, 0x3E, 0x00, 0xFD, 0x7E, 0x12])
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "66"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x3C


@pytest.mark.parametrize("prefix", [0xDD, 0xFD])
@pytest.mark.parametrize(
    ("load_opcode", "copy_opcode"),
    [
        (0x46, 0x78),  # LD B,(II+d) ; LD A,B
        (0x4E, 0x79),  # LD C,(II+d) ; LD A,C
        (0x56, 0x7A),  # LD D,(II+d) ; LD A,D
        (0x5E, 0x7B),  # LD E,(II+d) ; LD A,E
        (0x66, 0x7C),  # LD H,(II+d) ; LD A,H
        (0x6E, 0x7D),  # LD L,(II+d) ; LD A,L
        (0x7E, None),  # LD A,(II+d)
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_indexed_load_into_register_matrix(z80_binary, tmp_path, prefix, load_opcode, copy_opcode):
    rom = tmp_path / f"indexed_load_{prefix:02x}_{load_opcode:02x}.rom"
    program = [
        prefix,
        0x21,
        0x00,
        0x20,  # LD II,0x2000
        0x3E,
        0x5A,  # LD A,0x5A
        prefix,
        0x77,
        0x05,  # LD (II+5),A
        prefix,
        load_opcode,
        0x05,  # LD r,(II+5)
    ]
    if copy_opcode is not None:
        program.append(copy_opcode)  # LD A,r
    rom.write_bytes(bytes(program))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "140"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x5A


@pytest.mark.parametrize("prefix", [0xDD, 0xFD])
@pytest.mark.parametrize(
    ("store_opcode", "init_opcode", "value"),
    [
        (0x70, 0x06, 0x11),  # LD (II+d),B
        (0x71, 0x0E, 0x22),  # LD (II+d),C
        (0x72, 0x16, 0x33),  # LD (II+d),D
        (0x73, 0x1E, 0x44),  # LD (II+d),E
        (0x74, 0x26, 0x55),  # LD (II+d),H
        (0x75, 0x2E, 0x66),  # LD (II+d),L
        (0x77, 0x3E, 0x77),  # LD (II+d),A
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_indexed_store_from_register_matrix(z80_binary, tmp_path, prefix, store_opcode, init_opcode, value):
    rom = tmp_path / f"indexed_store_{prefix:02x}_{store_opcode:02x}.rom"
    rom.write_bytes(
        bytes(
            [
                prefix,
                0x21,
                0x00,
                0x20,  # LD II,0x2000
                init_opcode,
                value,  # LD r,value
                prefix,
                store_opcode,
                0x05,  # LD (II+5),r
                0x3E,
                0x00,
                prefix,
                0x7E,
                0x05,  # LD A,(II+5)
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "160"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == value


@pytest.mark.parametrize("prefix", [0xDD, 0xFD])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_indexed_immediate_store_round_trip(z80_binary, tmp_path, prefix):
    rom = tmp_path / f"indexed_store_immediate_{prefix:02x}.rom"
    # LD II,0x2000 ; LD (II+5),0xA5 ; LD A,0 ; LD A,(II+5)
    rom.write_bytes(bytes([prefix, 0x21, 0x00, 0x20, prefix, 0x36, 0x05, 0xA5, 0x3E, 0x00, prefix, 0x7E, 0x05]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0xA5


@pytest.mark.parametrize("prefix", [0xDD, 0xFD])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_prefixed_halt_does_not_consume_displacement_byte(z80_binary, tmp_path, prefix):
    rom = tmp_path / f"prefixed_halt_{prefix:02x}.rom"
    # II HALT ; LD A,0x66 (must not execute)
    rom.write_bytes(bytes([prefix, 0x76, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "20"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x00
    assert _parse_pc(proc.stdout) == 0x0002


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ixd_alu_sequence_covers_all_indexed_ops(z80_binary, tmp_path):
    rom = tmp_path / "ixd_alu_sequence.rom"
    # Seed (IX+5)=3 then run ADD/ADC/SUB/SBC/AND/XOR/OR/CP with (IX+5).
    rom.write_bytes(
        bytes(
            [
                0xDD,
                0x21,
                0x00,
                0x20,
                0x3E,
                0x03,
                0xDD,
                0x77,
                0x05,
                0x3E,
                0x01,
                0xDD,
                0x86,
                0x05,
                0xDD,
                0x8E,
                0x05,
                0xDD,
                0x96,
                0x05,
                0xDD,
                0x9E,
                0x05,
                0xDD,
                0xA6,
                0x05,
                0xDD,
                0xAE,
                0x05,
                0xDD,
                0xB6,
                0x05,
                0xDD,
                0xBE,
                0x05,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "220"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x03
    assert (flags & 0x02) != 0  # FLAG_Z
    assert (flags & 0x10) != 0  # FLAG_N
    assert (flags & 0x20) == 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_iyd_alu_sequence_covers_all_indexed_ops(z80_binary, tmp_path):
    rom = tmp_path / "iyd_alu_sequence.rom"
    # Seed (IY+6)=5 then run ADD/ADC/SUB/SBC/AND/XOR/OR/CP with (IY+6).
    rom.write_bytes(
        bytes(
            [
                0xFD,
                0x21,
                0x00,
                0x21,
                0x3E,
                0x05,
                0xFD,
                0x77,
                0x06,
                0x3E,
                0x02,
                0xFD,
                0x86,
                0x06,
                0xFD,
                0x8E,
                0x06,
                0xFD,
                0x96,
                0x06,
                0xFD,
                0x9E,
                0x06,
                0xFD,
                0xA6,
                0x06,
                0xFD,
                0xAE,
                0x06,
                0xFD,
                0xB6,
                0x06,
                0xFD,
                0xBE,
                0x06,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "220"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x05
    assert (flags & 0x02) != 0  # FLAG_Z
    assert (flags & 0x10) != 0  # FLAG_N
    assert (flags & 0x20) == 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_dd_cb_d_rlc_rotates_indexed_memory(z80_binary, tmp_path):
    rom = tmp_path / "ddcb_rlc_ixd.rom"
    # LD IX,0x0020 ; LD A,0x81 ; LD (IX+0x05),A ; DD CB 05 06 ; LD A,0x00 ; LD A,(IX+0x05)
    rom.write_bytes(
        bytes(
            [
                0xDD,
                0x21,
                0x20,
                0x00,
                0x3E,
                0x81,
                0xDD,
                0x77,
                0x05,
                0xDD,
                0xCB,
                0x05,
                0x06,
                0x3E,
                0x00,
                0xDD,
                0x7E,
                0x05,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "89"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x03


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_fd_cb_d_rlc_rotates_indexed_memory(z80_binary, tmp_path):
    rom = tmp_path / "fdcb_rlc_iyd.rom"
    # LD IY,0x0030 ; LD A,0x40 ; LD (IY+0x07),A ; FD CB 07 06 ; LD A,0x00 ; LD A,(IY+0x07)
    rom.write_bytes(
        bytes(
            [
                0xFD,
                0x21,
                0x30,
                0x00,
                0x3E,
                0x40,
                0xFD,
                0x77,
                0x07,
                0xFD,
                0xCB,
                0x07,
                0x06,
                0x3E,
                0x00,
                0xFD,
                0x7E,
                0x07,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "89"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x80


@pytest.mark.parametrize(
    ("subop", "seed", "set_carry", "expected_value", "expected_carry"),
    [
        (0x06, 0x81, False, 0x03, True),   # RLC (HL)
        (0x0E, 0x01, False, 0x80, True),   # RRC (HL)
        (0x16, 0x80, True, 0x01, True),    # RL (HL)
        (0x1E, 0x01, True, 0x80, True),    # RR (HL)
        (0x26, 0x40, False, 0x80, False),  # SLA (HL)
        (0x36, 0x80, False, 0x01, True),   # SLL (HL)
        (0x2E, 0x81, False, 0xC0, True),   # SRA (HL)
        (0x3E, 0x01, False, 0x00, True),   # SRL (HL)
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cb_hli_rotate_shift_matrix_updates_memory(
    z80_binary, tmp_path, subop, seed, set_carry, expected_value, expected_carry
):
    rom = tmp_path / f"cb_hli_{subop:02x}_{seed:02x}.rom"
    program = [
        0xAF,  # XOR A clears carry in this runtime model
    ]
    if set_carry:
        program.append(0x37)  # SCF sets carry
    program.extend(
        [
            0x21,
            0x40,
            0x20,  # LD HL,0x2040
            0x3E,
            seed,  # LD A,seed
            0x77,  # LD (HL),A
            0xCB,
            subop,  # <ROT/SHIFT> (HL)
            0x3E,
            0x00,  # LD A,0
            0x7E,  # LD A,(HL)
        ]
    )
    rom.write_bytes(bytes(program))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == expected_value
    _assert_rotate_shift_flags(flags, expected_value, expected_carry)


@pytest.mark.parametrize(
    ("subop", "seed", "set_carry", "expected_value", "expected_carry"),
    [
        (0x00, 0x81, False, 0x03, True),   # RLC B
        (0x08, 0x01, False, 0x80, True),   # RRC B
        (0x10, 0x80, True, 0x01, True),    # RL B
        (0x18, 0x01, True, 0x80, True),    # RR B
        (0x20, 0x40, False, 0x80, False),  # SLA B
        (0x30, 0x80, False, 0x01, True),   # SLL B
        (0x28, 0x81, False, 0xC0, True),   # SRA B
        (0x38, 0x01, False, 0x00, True),   # SRL B
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cb_r_rotate_shift_matrix_updates_register(
    z80_binary, tmp_path, subop, seed, set_carry, expected_value, expected_carry
):
    rom = tmp_path / f"cb_r_{subop:02x}_{seed:02x}.rom"
    program = [
        0xAF,  # XOR A clears carry in this runtime model
    ]
    if set_carry:
        program.append(0x37)  # SCF sets carry
    program.extend(
        [
            0x06,
            seed,  # LD B,seed
            0xCB,
            subop,  # <ROT/SHIFT> B
            0x78,  # LD A,B
        ]
    )
    rom.write_bytes(bytes(program))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 1) == expected_value
    assert _parse_r0(proc.stdout) == expected_value
    _assert_rotate_shift_flags(flags, expected_value, expected_carry)


@pytest.mark.parametrize("bit", range(8))
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cb_r_bit_set_res_matrix_updates_register(z80_binary, tmp_path, bit):
    rom = tmp_path / f"cb_r_bit{bit}_set_res.rom"
    set_subop = 0xC0 + (bit << 3)  # SET b,B
    bit_subop = 0x40 + (bit << 3)  # BIT b,B
    res_subop = 0x80 + (bit << 3)  # RES b,B
    rom.write_bytes(
        bytes(
            [
                0x06,
                0x00,  # LD B,0
                0xCB,
                set_subop,
                0xCB,
                bit_subop,
                0xCB,
                res_subop,
                0xCB,
                bit_subop,
                0x78,  # LD A,B
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "100"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 1) == 0x00  # B cleared by RES
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT after RES
    assert (flags & 0x01) == 0  # FLAG_S clear when tested bit is clear
    assert (flags & 0x04) != 0  # FLAG_H set by BIT
    assert (flags & 0x08) != 0  # FLAG_P mirrors Z
    assert (flags & 0x10) == 0  # FLAG_N reset by BIT


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cb_bit7_sets_sign_and_preserves_carry(z80_binary, tmp_path):
    rom = tmp_path / "cb_bit7_sign_carry.rom"
    rom.write_bytes(
        bytes(
            [
                0x06,
                0x80,  # LD B,0x80
                0x37,  # SCF
                0xCB,
                0x78,  # BIT 7,B
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    _assert_bit_flags(flags, expect_z=False, expect_s=True, expect_carry=True)


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cb_bit_r_uses_decoded_register_field(z80_binary, tmp_path):
    rom = tmp_path / "cb_bit_r_field_decode.rom"
    rom.write_bytes(
        bytes(
            [
                0x06,
                0x01,  # LD B,1
                0x0E,
                0x00,  # LD C,0
                0xCB,
                0x41,  # BIT 0,C
                0x78,  # LD A,B (should remain 1)
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x01
    assert (flags & 0x02) != 0  # Z reflects C (0), not B (1)


@pytest.mark.parametrize(
    ("prefix", "disp", "base_lo", "base_hi", "name"),
    [
        (0xDD, 0x05, 0x20, 0x00, "ixd"),
        (0xFD, 0x06, 0x30, 0x00, "iyd"),
    ],
)
@pytest.mark.parametrize(
    ("subop", "seed", "set_carry", "expected_value", "expected_carry"),
    [
        (0x0E, 0x01, False, 0x80, True),   # RRC
        (0x16, 0x80, True, 0x01, True),    # RL (uses carry-in)
        (0x1E, 0x01, True, 0x80, True),    # RR (uses carry-in)
        (0x26, 0x40, False, 0x80, False),  # SLA
        (0x36, 0x80, False, 0x01, True),   # SLL
        (0x2E, 0x81, False, 0xC0, True),   # SRA
        (0x3E, 0x01, False, 0x00, True),   # SRL
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ddfd_cb_d_rotate_shift_matrix_updates_indexed_memory(
    z80_binary, tmp_path, prefix, disp, base_lo, base_hi, name, subop, seed, set_carry, expected_value, expected_carry
):
    rom = tmp_path / f"{name}_cb_{subop:02x}_{seed:02x}.rom"
    program = [
        0xAF,  # XOR A clears carry in this model
    ]
    if set_carry:
        program.append(0x37)  # SCF sets carry
    program.extend(
        [
            prefix,
            0x21,
            base_lo,
            base_hi,
            0x3E,
            seed,
            prefix,
            0x77,
            disp,
            prefix,
            0xCB,
            disp,
            subop,
            0x3E,
            0x00,
            prefix,
            0x7E,
            disp,
        ]
    )
    rom.write_bytes(bytes(program))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "140"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == expected_value
    _assert_rotate_shift_flags(flags, expected_value, expected_carry)


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_dd_cb_d_bit_set_res_updates_indexed_memory(z80_binary, tmp_path):
    rom = tmp_path / "ddcb_bit_set_res_ixd.rom"
    # LD IX,0x2000 ; LD A,0 ; LD (IX+5),A ; SET 0,(IX+5) ; BIT 0,(IX+5) ; RES 0,(IX+5) ; BIT 0,(IX+5) ; LD A,(IX+5)
    rom.write_bytes(
        bytes(
            [
                0xDD,
                0x21,
                0x00,
                0x20,
                0x3E,
                0x00,
                0xDD,
                0x77,
                0x05,
                0xDD,
                0xCB,
                0x05,
                0xC6,
                0xDD,
                0xCB,
                0x05,
                0x46,
                0xDD,
                0xCB,
                0x05,
                0x86,
                0xDD,
                0xCB,
                0x05,
                0x46,
                0x3E,
                0x00,
                0xDD,
                0x7E,
                0x05,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "260"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_fd_cb_d_bit_set_res_updates_indexed_memory(z80_binary, tmp_path):
    rom = tmp_path / "fdcb_bit_set_res_iyd.rom"
    # LD IY,0x2100 ; LD A,0 ; LD (IY+6),A ; SET 0,(IY+6) ; BIT 0,(IY+6) ; RES 0,(IY+6) ; BIT 0,(IY+6) ; LD A,(IY+6)
    rom.write_bytes(
        bytes(
            [
                0xFD,
                0x21,
                0x00,
                0x21,
                0x3E,
                0x00,
                0xFD,
                0x77,
                0x06,
                0xFD,
                0xCB,
                0x06,
                0xC6,
                0xFD,
                0xCB,
                0x06,
                0x46,
                0xFD,
                0xCB,
                0x06,
                0x86,
                0xFD,
                0xCB,
                0x06,
                0x46,
                0x3E,
                0x00,
                0xFD,
                0x7E,
                0x06,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "260"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT


@pytest.mark.parametrize(
    ("prefix", "index_name", "base_lo", "base_hi", "disp"),
    [
        (0xDD, "ixd", 0x00, 0x22, 0x05),
        (0xFD, "iyd", 0x00, 0x23, 0x06),
    ],
)
@pytest.mark.parametrize("bit", range(1, 8))
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ddfd_cb_d_bit_set_res_matrix_updates_indexed_memory(
    z80_binary, tmp_path, prefix, index_name, base_lo, base_hi, disp, bit
):
    rom = tmp_path / f"{index_name}_bit{bit}_set_res.rom"
    set_subop = 0xC6 + (bit << 3)
    bit_subop = 0x46 + (bit << 3)
    res_subop = 0x86 + (bit << 3)
    rom.write_bytes(
        bytes(
            [
                prefix,
                0x21,
                base_lo,
                base_hi,
                0x3E,
                0x00,
                prefix,
                0x77,
                disp,
                prefix,
                0xCB,
                disp,
                set_subop,
                prefix,
                0xCB,
                disp,
                bit_subop,
                prefix,
                0xCB,
                disp,
                res_subop,
                prefix,
                0xCB,
                disp,
                bit_subop,
                0x3E,
                0x00,
                prefix,
                0x7E,
                disp,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "260"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT after RES


@pytest.mark.parametrize(
    ("prefix", "index_name", "base_lo", "base_hi", "disp"),
    [
        (0xDD, "ixd", 0x40, 0x22, 0x05),
        (0xFD, "iyd", 0x50, 0x23, 0x06),
    ],
)
@pytest.mark.parametrize(
    ("subop_base", "seed", "set_carry", "expected_value", "expected_carry"),
    [
        (0x00, 0x81, False, 0x03, True),   # RLC (IX/IY+d),C
        (0x08, 0x01, False, 0x80, True),   # RRC (IX/IY+d),C
        (0x10, 0x80, True, 0x01, True),    # RL (IX/IY+d),C
        (0x18, 0x01, True, 0x80, True),    # RR (IX/IY+d),C
        (0x20, 0x40, False, 0x80, False),  # SLA (IX/IY+d),C
        (0x30, 0x80, False, 0x01, True),   # SLL (IX/IY+d),C
        (0x28, 0x81, False, 0xC0, True),   # SRA (IX/IY+d),C
        (0x38, 0x01, False, 0x00, True),   # SRL (IX/IY+d),C
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ddfd_cb_d_rotate_shift_register_target_updates_reg_and_memory(
    z80_binary,
    tmp_path,
    prefix,
    index_name,
    base_lo,
    base_hi,
    disp,
    subop_base,
    seed,
    set_carry,
    expected_value,
    expected_carry,
):
    rom = tmp_path / f"{index_name}_cb_reg_{subop_base:02x}_{seed:02x}.rom"
    subop = subop_base + 1  # r=C
    program = [
        0xAF,  # XOR A clears carry in this runtime model
    ]
    if set_carry:
        program.append(0x37)  # SCF sets carry
    program.extend(
        [
            prefix,
            0x21,
            base_lo,
            base_hi,
            0x3E,
            seed,
            prefix,
            0x77,
            disp,
            prefix,
            0xCB,
            disp,
            subop,
            0x79,  # LD A,C
            0x3E,
            0x00,
            prefix,
            0x7E,
            disp,  # LD A,(IX/IY+d)
        ]
    )
    rom.write_bytes(bytes(program))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "180"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 2) == expected_value  # C
    assert _parse_r0(proc.stdout) == expected_value
    _assert_rotate_shift_flags(flags, expected_value, expected_carry)


@pytest.mark.parametrize(
    ("prefix", "index_name", "base_lo", "base_hi", "disp"),
    [
        (0xDD, "ixd", 0x20, 0x24, 0x05),
        (0xFD, "iyd", 0x30, 0x25, 0x06),
    ],
)
@pytest.mark.parametrize("bit", range(8))
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ddfd_cb_d_set_res_register_target_updates_reg_and_memory(
    z80_binary, tmp_path, prefix, index_name, base_lo, base_hi, disp, bit
):
    rom = tmp_path / f"{index_name}_cb_set_res_reg_bit{bit}.rom"
    set_subop = 0xC0 + (bit << 3) + 1  # SET b,(IX/IY+d),C
    res_subop = 0x80 + (bit << 3) + 1  # RES b,(IX/IY+d),C
    expected_set = 1 << bit
    rom.write_bytes(
        bytes(
            [
                prefix,
                0x21,
                base_lo,
                base_hi,
                0x3E,
                0x00,
                prefix,
                0x77,
                disp,  # LD (IX/IY+d),0
                prefix,
                0xCB,
                disp,
                set_subop,
                0x79,  # LD A,C
                0x47,  # LD B,A (capture SET result)
                prefix,
                0xCB,
                disp,
                res_subop,
                0x3E,
                0x00,
                prefix,
                0x7E,
                disp,  # LD A,(IX/IY+d)
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "220"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_reg(proc.stdout, 1) == expected_set  # B saved from C after SET
    assert _parse_reg(proc.stdout, 2) == 0x00  # C cleared by RES
    assert _parse_r0(proc.stdout) == 0x00  # Memory reflects RES result


@pytest.mark.parametrize(
    ("prefix", "index_name", "base_lo", "base_hi", "disp"),
    [
        (0xDD, "ixd", 0x60, 0x26, 0x05),
        (0xFD, "iyd", 0x70, 0x27, 0x06),
    ],
)
@pytest.mark.parametrize(
    ("seed", "expect_z"),
    [
        (0x00, True),
        (0x08, False),
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ddfd_cb_d_bit_register_target_uses_bit_field_without_writing_target(
    z80_binary, tmp_path, prefix, index_name, base_lo, base_hi, disp, seed, expect_z
):
    rom = tmp_path / f"{index_name}_cb_bit_reg_seed{seed:02x}.rom"
    bit_subop = 0x40 + (3 << 3) + 1  # BIT 3,(IX/IY+d),C
    rom.write_bytes(
        bytes(
            [
                prefix,
                0x21,
                base_lo,
                base_hi,
                0x0E,
                0xAA,  # LD C,0xAA sentinel
                0x37,  # SCF (carry must be preserved by BIT)
                0x3E,
                seed,
                prefix,
                0x77,
                disp,
                prefix,
                0xCB,
                disp,
                bit_subop,
                0x79,  # LD A,C (C should be unchanged)
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "150"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 2) == 0xAA  # C unchanged
    assert _parse_r0(proc.stdout) == 0xAA
    _assert_bit_flags(flags, expect_z=expect_z, expect_s=False, expect_carry=True)


@pytest.mark.parametrize(
    ("prefix", "index_name", "base_lo", "base_hi", "disp"),
    [
        (0xDD, "ixd", 0x28, 0x24, 0x05),
        (0xFD, "iyd", 0x38, 0x25, 0x06),
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ddfd_cb_d_bit7_register_target_sets_sign_and_preserves_carry(
    z80_binary, tmp_path, prefix, index_name, base_lo, base_hi, disp
):
    rom = tmp_path / f"{index_name}_cb_bit7_reg_flags.rom"
    bit7_subop = 0x40 + (7 << 3) + 1  # BIT 7,(IX/IY+d),C
    rom.write_bytes(
        bytes(
            [
                prefix,
                0x21,
                base_lo,
                base_hi,
                0x0E,
                0x55,  # LD C,0x55 sentinel
                0x37,  # SCF
                0x3E,
                0x80,
                prefix,
                0x77,
                disp,
                prefix,
                0xCB,
                disp,
                bit7_subop,
                0x79,  # LD A,C
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "160"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 2) == 0x55  # C unchanged
    assert _parse_r0(proc.stdout) == 0x55
    _assert_bit_flags(flags, expect_z=False, expect_s=True, expect_carry=True)


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ini_transfers_port_to_memory_and_advances_hl(z80_binary, tmp_path):
    rom = tmp_path / "ini_transfer.rom"
    # LD A,0x6B ; OUT (0x22),A ; LD B,0x01 ; LD C,0x22 ; INI ; LD A,0x00 ; LD A,(IX+0)
    rom.write_bytes(
        bytes([0x3E, 0x6B, 0xD3, 0x22, 0x06, 0x01, 0x0E, 0x22, 0xED, 0xA2, 0x3E, 0x00, 0xDD, 0x7E, 0x00])
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "74"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x6B
    assert _parse_reg(proc.stdout, 1) == 0x00  # B decremented
    assert _parse_reg(proc.stdout, 5) == 0x00  # H
    assert _parse_reg(proc.stdout, 6) == 0x01  # L incremented
    assert (flags & 0x02) != 0  # FLAG_Z (B reached zero)
    assert (flags & 0x10) == 0  # FLAG_N mirrors transferred value bit 7
    assert (flags & 0x08) != 0  # FLAG_P from undocumented parity seed
    assert (flags & 0x04) == 0  # FLAG_H clear for this transfer
    assert (flags & 0x20) == 0  # FLAG_C clear for this transfer


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ind_transfers_port_to_memory_and_decrements_hl(z80_binary, tmp_path):
    rom = tmp_path / "ind_transfer.rom"
    # LD A,0x2C ; OUT (0x40),A ; LD B,0x01 ; LD C,0x40 ; IND ; LD A,0x00 ; LD A,(IX+0)
    rom.write_bytes(
        bytes([0x3E, 0x2C, 0xD3, 0x40, 0x06, 0x01, 0x0E, 0x40, 0xED, 0xAA, 0x3E, 0x00, 0xDD, 0x7E, 0x00])
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "74"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x2C
    assert _parse_reg(proc.stdout, 1) == 0x00  # B decremented
    assert _parse_reg(proc.stdout, 5) == 0xFF  # H
    assert _parse_reg(proc.stdout, 6) == 0xFF  # L decremented
    assert (flags & 0x02) != 0  # FLAG_Z (B reached zero)
    assert (flags & 0x10) == 0  # FLAG_N mirrors transferred value bit 7
    assert (flags & 0x08) != 0  # FLAG_P from undocumented parity seed
    assert (flags & 0x04) == 0  # FLAG_H clear for this transfer
    assert (flags & 0x20) == 0  # FLAG_C clear for this transfer


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ini_sets_halfcarry_and_carry_on_overflow(z80_binary, tmp_path):
    rom = tmp_path / "ini_hc_carry.rom"
    # LD A,0xFE ; OUT (0x02),A ; LD B,0x01 ; LD C,0x02 ; INI
    rom.write_bytes(bytes([0x3E, 0xFE, 0xD3, 0x02, 0x06, 0x01, 0x0E, 0x02, 0xED, 0xA2]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "48"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 1) == 0x00  # B decremented
    assert (flags & 0x04) != 0  # FLAG_H set on overflow
    assert (flags & 0x20) != 0  # FLAG_C mirrors H for block I/O
    assert (flags & 0x10) != 0  # FLAG_N mirrors transferred value bit 7
    assert (flags & 0x08) == 0  # FLAG_P from undocumented parity seed


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ini_non_terminal_parity_uses_seed_formula(z80_binary, tmp_path):
    rom = tmp_path / "ini_non_terminal_parity.rom"
    # LD A,0x03 ; OUT (0x10),A ; LD B,0x02 ; LD C,0x10 ; INI
    rom.write_bytes(bytes([0x3E, 0x03, 0xD3, 0x10, 0x06, 0x02, 0x0E, 0x10, 0xED, 0xA2]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "48"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 1) == 0x01  # B decremented but non-zero
    assert (flags & 0x02) == 0  # FLAG_Z clear while B != 0
    assert (flags & 0x08) != 0  # FLAG_P computed from parity seed, not just B != 0
    assert (flags & 0x10) == 0  # FLAG_N mirrors transferred value bit 7
    assert (flags & 0x04) == 0  # FLAG_H clear for this transfer
    assert (flags & 0x20) == 0  # FLAG_C clear for this transfer


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_outd_writes_memory_to_port_and_decrements_hl(z80_binary, tmp_path):
    rom = tmp_path / "outd_transfer.rom"
    # LD C,0x44 ; LD B,0x01 ; OUTD ; IN A,(0x44)
    rom.write_bytes(bytes([0x0E, 0x44, 0x06, 0x01, 0xED, 0xAB, 0xDB, 0x44]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "41"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x0E
    assert _parse_reg(proc.stdout, 1) == 0x00  # B decremented
    assert _parse_reg(proc.stdout, 5) == 0xFF  # H
    assert _parse_reg(proc.stdout, 6) == 0xFF  # L decremented
    assert (flags & 0x02) != 0  # FLAG_Z (B reached zero)
    assert (flags & 0x10) == 0  # FLAG_N mirrors transferred value bit 7
    assert (flags & 0x08) != 0  # FLAG_P from undocumented parity seed
    assert (flags & 0x04) != 0  # FLAG_H set for this transfer
    assert (flags & 0x20) != 0  # FLAG_C mirrors H for block I/O


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_outi_sets_flags_from_transferred_value_and_new_l(z80_binary, tmp_path):
    rom = tmp_path / "outi_flags.rom"
    # LD H,0x20 ; LD L,0xF0 ; LD A,0x80 ; LD (HL),A ; LD C,0x40 ; LD B,0x01 ; OUTI ; LD A,0x00 ; IN A,(0x40)
    rom.write_bytes(
        bytes([0x26, 0x20, 0x2E, 0xF0, 0x3E, 0x80, 0x77, 0x0E, 0x40, 0x06, 0x01, 0xED, 0xA3, 0x3E, 0x00, 0xDB, 0x40])
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "76"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x80
    assert _parse_reg(proc.stdout, 1) == 0x00  # B decremented
    assert _parse_reg(proc.stdout, 5) == 0x20  # H
    assert _parse_reg(proc.stdout, 6) == 0xF1  # L incremented
    assert (flags & 0x02) != 0  # FLAG_Z (B reached zero)
    assert (flags & 0x10) != 0  # FLAG_N mirrors transferred value bit 7
    assert (flags & 0x08) == 0  # FLAG_P from undocumented parity seed
    assert (flags & 0x04) != 0  # FLAG_H set from value + new L overflow
    assert (flags & 0x20) != 0  # FLAG_C mirrors H for block I/O


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_out_then_in_round_trip_port_value(z80_binary, tmp_path):
    rom = tmp_path / "io_roundtrip.rom"
    # LD A,0x5A ; OUT (0x10),A ; LD A,0x00 ; IN A,(0x10)
    rom.write_bytes(bytes([0x3E, 0x5A, 0xD3, 0x10, 0x3E, 0x00, 0xDB, 0x10]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "36"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x5A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_in_a_n_preserves_flags(z80_binary, tmp_path):
    rom = tmp_path / "in_a_n_preserve_flags.rom"
    # XOR A (sets Z/P); SCF (sets C, leaves Z/P); OUT (0x40),0x55 ; IN A,(0x40)
    rom.write_bytes(
        bytes(
            [
                0xAF,  # XOR A
                0x37,  # SCF
                0x3E,
                0x55,
                0xD3,
                0x40,  # OUT (0x40),A
                0xDB,
                0x40,  # IN A,(0x40)
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "60"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x55
    assert (flags & 0x20) != 0  # FLAG_C preserved from SCF
    assert (flags & 0x02) != 0  # FLAG_Z preserved from XOR A
    assert (flags & 0x08) != 0  # FLAG_P preserved from XOR A
    assert (flags & 0x04) == 0  # FLAG_H
    assert (flags & 0x10) == 0  # FLAG_N
    assert (flags & 0x01) == 0  # FLAG_S


@pytest.mark.parametrize(
    ("subop", "copy_opcode", "expected_reg_idx"),
    [
        (0x40, 0x78, 1),  # IN B,(C) then LD A,B
        (0x48, 0x79, 2),  # IN C,(C) then LD A,C
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_in_r_c_reads_port_into_selected_register(
    z80_binary, tmp_path, subop, copy_opcode, expected_reg_idx
):
    rom = tmp_path / f"in_r_c_{subop:02x}.rom"
    value = 0x6D
    port = 0x24
    rom.write_bytes(
        bytes(
            [
                0x3E,
                value,  # LD A,value
                0xD3,
                port,  # OUT (port),A
                0x0E,
                port,  # LD C,port
                0x06,
                0x00,  # LD B,0
                0xED,
                subop,  # IN r,(C)
                copy_opcode,  # LD A,r
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == value
    assert _parse_reg(proc.stdout, expected_reg_idx) == value


@pytest.mark.parametrize(
    ("subop", "program", "expected_value"),
    [
        # LD B,0x77 ; LD C,0x34 ; OUT (C),B ; LD A,0 ; IN A,(0x34)
        (0x41, [0x06, 0x77, 0x0E, 0x34, 0xED, 0x41, 0x3E, 0x00, 0xDB, 0x34], 0x77),
        # LD C,0x66 ; OUT (C),C ; LD A,0 ; IN A,(0x66)
        (0x49, [0x0E, 0x66, 0xED, 0x49, 0x3E, 0x00, 0xDB, 0x66], 0x66),
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_out_c_r_writes_selected_register_to_port(
    z80_binary, tmp_path, subop, program, expected_value
):
    rom = tmp_path / f"out_c_r_{subop:02x}.rom"
    rom.write_bytes(bytes(program))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == expected_value


@pytest.mark.parametrize(
    ("value", "expect_z", "expect_s", "expect_p"),
    [
        (0x00, True, False, True),
        (0x80, False, True, False),
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_in_r_c_updates_zero_and_sign_flags(
    z80_binary, tmp_path, value, expect_z, expect_s, expect_p
):
    rom = tmp_path / f"in_r_c_flags_{value:02x}.rom"
    rom.write_bytes(
        bytes(
            [
                0x3E,
                value,  # LD A,value
                0xD3,
                0x2A,  # OUT (0x2A),A
                0x0E,
                0x2A,  # LD C,0x2A
                0x37,  # SCF (carry should be preserved)
                0xED,
                0x40,  # IN B,(C)
                0x78,  # LD A,B
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == value
    assert ((flags & 0x02) != 0) == expect_z
    assert ((flags & 0x01) != 0) == expect_s
    assert ((flags & 0x08) != 0) == expect_p
    assert (flags & 0x04) == 0
    assert (flags & 0x10) == 0
    assert (flags & 0x20) != 0


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_out_c_r_with_r6_writes_zero_to_port(z80_binary, tmp_path):
    rom = tmp_path / "out_c_0_undocumented.rom"
    # LD A,0xA5 ; OUT (0x55),A ; LD C,0x55 ; ED 71 ; LD A,0x00 ; IN A,(0x55)
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0xA5,
                0xD3,
                0x55,
                0x0E,
                0x55,
                0xED,
                0x71,
                0x3E,
                0x00,
                0xDB,
                0x55,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x00


@pytest.mark.parametrize(
    ("value", "expect_z", "expect_s", "expect_p"),
    [
        (0x00, True, False, True),
        (0x80, False, True, False),
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_in_r_c_with_r6_updates_flags_without_writing_registers(
    z80_binary, tmp_path, value, expect_z, expect_s, expect_p
):
    rom = tmp_path / f"in_c_undocumented_{value:02x}.rom"
    # LD B,0x33 ; LD A,value ; OUT (0x2B),A ; LD C,0x2B ; ED 70 ; LD A,B
    rom.write_bytes(
        bytes(
            [
                0x06,
                0x33,
                0x3E,
                value,
                0xD3,
                0x2B,
                0x0E,
                0x2B,
                0x37,  # SCF (carry should be preserved)
                0xED,
                0x70,
                0x78,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "95"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 1) == 0x33  # B unchanged
    assert _parse_r0(proc.stdout) == 0x33      # A loaded from unchanged B
    assert ((flags & 0x02) != 0) == expect_z
    assert ((flags & 0x01) != 0) == expect_s
    assert ((flags & 0x08) != 0) == expect_p
    assert (flags & 0x04) == 0
    assert (flags & 0x10) == 0
    assert (flags & 0x20) != 0


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_rl_then_rr_round_trips_accumulator(z80_binary, tmp_path):
    rom = tmp_path / "rl_rr.rom"
    # LD A,0x81 ; RL A ; RR A
    rom.write_bytes(bytes([0x3E, 0x81, 0x17, 0x1F]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "15"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x81


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_sla_a_shifts_left_and_sets_carry(z80_binary, tmp_path):
    rom = tmp_path / "sla_a.rom"
    # LD A,0x81 ; SLA A (CB 27)
    rom.write_bytes(bytes([0x3E, 0x81, 0xCB, 0x27]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "15"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x02
    assert (flags & 0x20) != 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ldd_transfers_byte_and_decrements_pairs(z80_binary, tmp_path):
    rom = tmp_path / "ldd_transfer.rom"
    # LD A,0x5A ; LD H,0x20 ; LD L,0x10 ; LD (HL),A
    # LD D,0x20 ; LD E,0x20 ; LD B,0 ; LD C,1 ; LDD
    # LD IX,0x2020 ; LD A,(IX+0)
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x5A,
                0x26,
                0x20,
                0x2E,
                0x10,
                0x77,
                0x16,
                0x20,
                0x1E,
                0x20,
                0x06,
                0x00,
                0x0E,
                0x01,
                0xED,
                0xA8,
                0xDD,
                0x21,
                0x20,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "105"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x5A
    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 2) == 0x00  # C
    assert _parse_reg(proc.stdout, 3) == 0x20  # D
    assert _parse_reg(proc.stdout, 4) == 0x1F  # E
    assert _parse_reg(proc.stdout, 5) == 0x20  # H
    assert _parse_reg(proc.stdout, 6) == 0x0F  # L
    assert (flags & 0x04) == 0  # FLAG_H
    assert (flags & 0x08) == 0  # FLAG_P
    assert (flags & 0x10) == 0  # FLAG_N


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_lddr_repeats_until_bc_zero(z80_binary, tmp_path):
    rom = tmp_path / "lddr_repeat.rom"
    # Seed 0x2011=0xAA and 0x2010=0xBB, then copy two bytes down to 0x2121/0x2120 via LDDR.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x11,
                0x3E,
                0xAA,
                0x77,
                0x26,
                0x20,
                0x2E,
                0x10,
                0x3E,
                0xBB,
                0x77,
                0x26,
                0x20,
                0x2E,
                0x11,
                0x16,
                0x21,
                0x1E,
                0x21,
                0x06,
                0x00,
                0x0E,
                0x02,
                0xED,
                0xB8,
                0xDD,
                0x21,
                0x20,
                0x21,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "173"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0xBB
    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 2) == 0x00  # C
    assert _parse_reg(proc.stdout, 3) == 0x21  # D
    assert _parse_reg(proc.stdout, 4) == 0x1F  # E
    assert _parse_reg(proc.stdout, 5) == 0x20  # H
    assert _parse_reg(proc.stdout, 6) == 0x0F  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ldir_repeats_until_bc_zero_and_advances_pairs(z80_binary, tmp_path):
    rom = tmp_path / "ldir_repeat.rom"
    # Seed 0x2010=0xAA and 0x2011=0xBB, then copy two bytes up to 0x2120/0x2121 via LDIR.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x10,
                0x3E,
                0xAA,
                0x77,
                0x26,
                0x20,
                0x2E,
                0x11,
                0x3E,
                0xBB,
                0x77,
                0x26,
                0x20,
                0x2E,
                0x10,
                0x16,
                0x21,
                0x1E,
                0x20,
                0x06,
                0x00,
                0x0E,
                0x02,
                0xED,
                0xB0,
                0xDD,
                0x21,
                0x21,
                0x21,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "180"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0xBB
    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 2) == 0x00  # C
    assert _parse_reg(proc.stdout, 3) == 0x21  # D
    assert _parse_reg(proc.stdout, 4) == 0x22  # E
    assert _parse_reg(proc.stdout, 5) == 0x20  # H
    assert _parse_reg(proc.stdout, 6) == 0x12  # L
    assert (flags & 0x04) == 0  # FLAG_H
    assert (flags & 0x08) == 0  # FLAG_P
    assert (flags & 0x10) == 0  # FLAG_N


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cpdr_repeats_until_match_and_sets_zero(z80_binary, tmp_path):
    rom = tmp_path / "cpdr_repeat.rom"
    # Seed 0x2001=0x33 and 0x2000=0x22, then CPDR with A=0x22 and BC=2.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x01,
                0x3E,
                0x33,
                0x77,
                0x26,
                0x20,
                0x2E,
                0x00,
                0x3E,
                0x22,
                0x77,
                0x26,
                0x20,
                0x2E,
                0x01,
                0x06,
                0x00,
                0x0E,
                0x02,
                0xED,
                0xB9,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "126"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert (flags & 0x02) != 0  # FLAG_Z
    assert (flags & 0x10) != 0  # FLAG_N
    assert (flags & 0x04) == 0  # FLAG_H clear for equal compare
    assert (flags & 0x08) == 0  # FLAG_P clear when BC reaches zero
    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 2) == 0x00  # C
    assert _parse_reg(proc.stdout, 5) == 0x1F  # H
    assert _parse_reg(proc.stdout, 6) == 0xFF  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cpi_sets_half_borrow_and_counter_flags(z80_binary, tmp_path):
    rom = tmp_path / "cpi_flags.rom"
    # A=0x10, (HL)=0x01 -> result 0x0F (S=0, Z=0, H=1, N=1), BC goes 1->0 so P clears.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x00,  # LD HL,0x2000
                0x3E,
                0x01,  # LD A,0x01
                0x77,  # LD (HL),A
                0x3E,
                0x10,  # LD A,0x10
                0x06,
                0x00,
                0x0E,
                0x01,  # LD BC,0x0001
                0xED,
                0xA1,  # CPI
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert (flags & 0x01) == 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) == 0  # FLAG_P
    assert (flags & 0x10) != 0  # FLAG_N
    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 2) == 0x00  # C
    assert _parse_reg(proc.stdout, 5) == 0x20  # H
    assert _parse_reg(proc.stdout, 6) == 0x01  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cpd_sets_sign_and_half_borrow_flags(z80_binary, tmp_path):
    rom = tmp_path / "cpd_flags.rom"
    # A=0x00, (HL)=0x01 -> result 0xFF (S=1, Z=0, H=1, N=1), BC goes 1->0 so P clears.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x01,  # LD HL,0x2001
                0x3E,
                0x01,  # LD A,0x01
                0x77,  # LD (HL),A
                0x3E,
                0x00,  # LD A,0x00
                0x06,
                0x00,
                0x0E,
                0x01,  # LD BC,0x0001
                0xED,
                0xA9,  # CPD
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x04) != 0  # FLAG_H
    assert (flags & 0x08) == 0  # FLAG_P
    assert (flags & 0x10) != 0  # FLAG_N
    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 2) == 0x00  # C
    assert _parse_reg(proc.stdout, 5) == 0x20  # H
    assert _parse_reg(proc.stdout, 6) == 0x00  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_indr_repeats_until_b_reaches_zero(z80_binary, tmp_path):
    rom = tmp_path / "indr_repeat.rom"
    # LD A,0x7C ; OUT (0x44),A ; LD B,2 ; LD C,0x44 ; LD HL,0x2001 ; INDR ; LD IX,0x2000 ; LD A,(IX+0)
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x7C,
                0xD3,
                0x44,
                0x06,
                0x02,
                0x0E,
                0x44,
                0x26,
                0x20,
                0x2E,
                0x01,
                0xED,
                0xBA,
                0xDD,
                0x21,
                0x00,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "121"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x7C
    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 5) == 0x1F  # H
    assert _parse_reg(proc.stdout, 6) == 0xFF  # L
    assert (flags & 0x02) != 0  # FLAG_Z (B reached zero)
    assert (flags & 0x10) == 0  # FLAG_N mirrors transferred value bit 7
    assert (flags & 0x08) == 0  # FLAG_P clear when B == 0
    assert (flags & 0x04) == 0  # FLAG_H clear for final transfer
    assert (flags & 0x20) == 0  # FLAG_C clear for final transfer


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_inir_repeats_until_b_reaches_zero(z80_binary, tmp_path):
    rom = tmp_path / "inir_repeat.rom"
    # LD A,0x7C ; OUT (0x44),A ; LD B,2 ; LD C,0x44 ; LD HL,0x2000 ; INIR ; LD IX,0x2001 ; LD A,(IX+0)
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x7C,
                0xD3,
                0x44,
                0x06,
                0x02,
                0x0E,
                0x44,
                0x26,
                0x20,
                0x2E,
                0x00,
                0xED,
                0xB2,
                0xDD,
                0x21,
                0x01,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "121"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x7C
    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 5) == 0x20  # H
    assert _parse_reg(proc.stdout, 6) == 0x02  # L
    assert (flags & 0x02) != 0  # FLAG_Z (B reached zero)
    assert (flags & 0x10) == 0  # FLAG_N mirrors transferred value bit 7
    assert (flags & 0x08) == 0  # FLAG_P clear when B == 0
    assert (flags & 0x04) == 0  # FLAG_H clear for final transfer
    assert (flags & 0x20) == 0  # FLAG_C clear for final transfer


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_otdr_repeats_until_b_reaches_zero(z80_binary, tmp_path):
    rom = tmp_path / "otdr_repeat.rom"
    # Seed 0x2001=0xAB and 0x2000=0xCD, then OTDR with B=2,C=0x33 and read final port value.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x01,
                0x3E,
                0xAB,
                0x77,
                0x26,
                0x20,
                0x2E,
                0x00,
                0x3E,
                0xCD,
                0x77,
                0x26,
                0x20,
                0x2E,
                0x01,
                0x06,
                0x02,
                0x0E,
                0x33,
                0xED,
                0xBB,
                0x3E,
                0x00,
                0xDB,
                0x33,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "144"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0xCD
    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 5) == 0x1F  # H
    assert _parse_reg(proc.stdout, 6) == 0xFF  # L
    assert (flags & 0x10) != 0  # FLAG_N
    assert (flags & 0x08) == 0  # FLAG_P clear when B == 0
    assert (flags & 0x04) != 0  # FLAG_H set for final transfer
    assert (flags & 0x20) != 0  # FLAG_C mirrors H for block I/O


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_otir_repeats_until_b_reaches_zero(z80_binary, tmp_path):
    rom = tmp_path / "otir_repeat.rom"
    # Seed 0x2000=0x11 and 0x2001=0x22, then OTIR with B=2,C=0x33 and read final port value.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x00,
                0x3E,
                0x11,
                0x77,
                0x26,
                0x20,
                0x2E,
                0x01,
                0x3E,
                0x22,
                0x77,
                0x26,
                0x20,
                0x2E,
                0x00,
                0x06,
                0x02,
                0x0E,
                0x33,
                0xED,
                0xB3,
                0x3E,
                0x00,
                0xDB,
                0x33,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "144"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x22
    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 5) == 0x20  # H
    assert _parse_reg(proc.stdout, 6) == 0x02  # L
    assert (flags & 0x10) == 0  # FLAG_N mirrors transferred value bit 7
    assert (flags & 0x08) == 0  # FLAG_P clear when B == 0
    assert (flags & 0x04) == 0  # FLAG_H clear for final transfer
    assert (flags & 0x20) == 0  # FLAG_C clear for final transfer


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ldir_repeat_costs_21_more_cycles_than_terminating_pass(z80_binary, tmp_path):
    terminal = tmp_path / "ldir_terminal.rom"
    repeat = tmp_path / "ldir_repeat_once.rom"
    terminal.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23, 0x3E, 0x22, 0x77,  # INC HL ; LD A,0x22 ; LD (HL),A
                0x2B,  # DEC HL back to 0x2000
                0x11, 0x10, 0x20,  # LD DE,0x2010
                0x06, 0x00, 0x0E, 0x01,  # LD BC,0x0001
                0xED, 0xB0,  # LDIR (terminates)
                0x76,  # HALT
            ]
        )
    )
    repeat.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23, 0x3E, 0x22, 0x77,  # INC HL ; LD A,0x22 ; LD (HL),A
                0x2B,  # DEC HL back to 0x2000
                0x11, 0x10, 0x20,  # LD DE,0x2010
                0x06, 0x00, 0x0E, 0x02,  # LD BC,0x0002
                0xED, 0xB0,  # LDIR (repeats once)
                0x76,  # HALT
            ]
        )
    )

    proc_term = subprocess.run(
        [str(z80_binary), "--rom", str(terminal), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_rep = subprocess.run(
        [str(z80_binary), "--rom", str(repeat), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_rep.stdout) - _parse_executed_cycles(proc_term.stdout) == 21


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_lddr_repeat_costs_21_more_cycles_than_terminating_pass(z80_binary, tmp_path):
    terminal = tmp_path / "lddr_terminal.rom"
    repeat = tmp_path / "lddr_repeat_once.rom"
    terminal.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23, 0x3E, 0x22, 0x77,  # INC HL ; LD A,0x22 ; LD (HL),A
                0x11, 0x10, 0x20,  # LD DE,0x2010
                0x21, 0x01, 0x20,  # LD HL,0x2001
                0x06, 0x00, 0x0E, 0x01,  # LD BC,0x0001
                0xED, 0xB8,  # LDDR (terminates)
                0x76,  # HALT
            ]
        )
    )
    repeat.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23, 0x3E, 0x22, 0x77,  # INC HL ; LD A,0x22 ; LD (HL),A
                0x11, 0x10, 0x20,  # LD DE,0x2010
                0x21, 0x01, 0x20,  # LD HL,0x2001
                0x06, 0x00, 0x0E, 0x02,  # LD BC,0x0002
                0xED, 0xB8,  # LDDR (repeats once)
                0x76,  # HALT
            ]
        )
    )

    proc_term = subprocess.run(
        [str(z80_binary), "--rom", str(terminal), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_rep = subprocess.run(
        [str(z80_binary), "--rom", str(repeat), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_rep.stdout) - _parse_executed_cycles(proc_term.stdout) == 21


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cpir_repeat_costs_21_more_cycles_than_terminating_pass(z80_binary, tmp_path):
    terminal = tmp_path / "cpir_terminal.rom"
    repeat = tmp_path / "cpir_repeat_once.rom"
    terminal.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23,  # INC HL
                0x3E, 0x22, 0x77,  # LD A,0x22 ; LD (HL),A
                0x2B,  # DEC HL
                0x3E, 0x11,  # LD A,0x11 (match first)
                0x06, 0x00, 0x0E, 0x01,  # LD BC,0x0001
                0xED, 0xB1,  # CPIR (terminates)
                0x76,  # HALT
            ]
        )
    )
    repeat.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23,  # INC HL
                0x3E, 0x22, 0x77,  # LD A,0x22 ; LD (HL),A
                0x2B,  # DEC HL
                0x3E, 0x22,  # LD A,0x22 (match second)
                0x06, 0x00, 0x0E, 0x02,  # LD BC,0x0002
                0xED, 0xB1,  # CPIR (repeats once)
                0x76,  # HALT
            ]
        )
    )

    proc_term = subprocess.run(
        [str(z80_binary), "--rom", str(terminal), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_rep = subprocess.run(
        [str(z80_binary), "--rom", str(repeat), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_rep.stdout) - _parse_executed_cycles(proc_term.stdout) == 21


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_cpdr_repeat_costs_21_more_cycles_than_terminating_pass(z80_binary, tmp_path):
    terminal = tmp_path / "cpdr_terminal.rom"
    repeat = tmp_path / "cpdr_repeat_once.rom"
    terminal.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23,  # INC HL
                0x3E, 0x22, 0x77,  # LD A,0x22 ; LD (HL),A
                0x21, 0x01, 0x20,  # LD HL,0x2001
                0x3E, 0x22,  # LD A,0x22 (match first)
                0x06, 0x00, 0x0E, 0x01,  # LD BC,0x0001
                0xED, 0xB9,  # CPDR (terminates)
                0x76,  # HALT
            ]
        )
    )
    repeat.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23,  # INC HL
                0x3E, 0x22, 0x77,  # LD A,0x22 ; LD (HL),A
                0x21, 0x01, 0x20,  # LD HL,0x2001
                0x3E, 0x11,  # LD A,0x11 (match second)
                0x06, 0x00, 0x0E, 0x02,  # LD BC,0x0002
                0xED, 0xB9,  # CPDR (repeats once)
                0x76,  # HALT
            ]
        )
    )

    proc_term = subprocess.run(
        [str(z80_binary), "--rom", str(terminal), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_rep = subprocess.run(
        [str(z80_binary), "--rom", str(repeat), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_rep.stdout) - _parse_executed_cycles(proc_term.stdout) == 21


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_inir_repeat_costs_21_more_cycles_than_terminating_pass(z80_binary, tmp_path):
    terminal = tmp_path / "inir_terminal.rom"
    repeat = tmp_path / "inir_repeat_once.rom"
    terminal.write_bytes(
        bytes(
            [
                0x3E, 0x7C, 0xD3, 0x44,  # LD A,0x7C ; OUT (0x44),A
                0x06, 0x01, 0x0E, 0x44,  # LD B,1 ; LD C,0x44
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0xED, 0xB2,  # INIR (terminates)
                0x76,  # HALT
            ]
        )
    )
    repeat.write_bytes(
        bytes(
            [
                0x3E, 0x7C, 0xD3, 0x44,  # LD A,0x7C ; OUT (0x44),A
                0x06, 0x02, 0x0E, 0x44,  # LD B,2 ; LD C,0x44
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0xED, 0xB2,  # INIR (repeats once)
                0x76,  # HALT
            ]
        )
    )

    proc_term = subprocess.run(
        [str(z80_binary), "--rom", str(terminal), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_rep = subprocess.run(
        [str(z80_binary), "--rom", str(repeat), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_rep.stdout) - _parse_executed_cycles(proc_term.stdout) == 21


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_indr_repeat_costs_21_more_cycles_than_terminating_pass(z80_binary, tmp_path):
    terminal = tmp_path / "indr_terminal.rom"
    repeat = tmp_path / "indr_repeat_once.rom"
    terminal.write_bytes(
        bytes(
            [
                0x3E, 0x7C, 0xD3, 0x44,  # LD A,0x7C ; OUT (0x44),A
                0x06, 0x01, 0x0E, 0x44,  # LD B,1 ; LD C,0x44
                0x21, 0x01, 0x20,  # LD HL,0x2001
                0xED, 0xBA,  # INDR (terminates)
                0x76,  # HALT
            ]
        )
    )
    repeat.write_bytes(
        bytes(
            [
                0x3E, 0x7C, 0xD3, 0x44,  # LD A,0x7C ; OUT (0x44),A
                0x06, 0x02, 0x0E, 0x44,  # LD B,2 ; LD C,0x44
                0x21, 0x01, 0x20,  # LD HL,0x2001
                0xED, 0xBA,  # INDR (repeats once)
                0x76,  # HALT
            ]
        )
    )

    proc_term = subprocess.run(
        [str(z80_binary), "--rom", str(terminal), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_rep = subprocess.run(
        [str(z80_binary), "--rom", str(repeat), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_rep.stdout) - _parse_executed_cycles(proc_term.stdout) == 21


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_otir_repeat_costs_21_more_cycles_than_terminating_pass(z80_binary, tmp_path):
    terminal = tmp_path / "otir_terminal.rom"
    repeat = tmp_path / "otir_repeat_once.rom"
    terminal.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23, 0x3E, 0x22, 0x77,  # INC HL ; LD A,0x22 ; LD (HL),A
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x06, 0x01, 0x0E, 0x33,  # LD B,1 ; LD C,0x33
                0xED, 0xB3,  # OTIR (terminates)
                0x76,  # HALT
            ]
        )
    )
    repeat.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23, 0x3E, 0x22, 0x77,  # INC HL ; LD A,0x22 ; LD (HL),A
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x06, 0x02, 0x0E, 0x33,  # LD B,2 ; LD C,0x33
                0xED, 0xB3,  # OTIR (repeats once)
                0x76,  # HALT
            ]
        )
    )

    proc_term = subprocess.run(
        [str(z80_binary), "--rom", str(terminal), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_rep = subprocess.run(
        [str(z80_binary), "--rom", str(repeat), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_rep.stdout) - _parse_executed_cycles(proc_term.stdout) == 21


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_otdr_repeat_costs_21_more_cycles_than_terminating_pass(z80_binary, tmp_path):
    terminal = tmp_path / "otdr_terminal.rom"
    repeat = tmp_path / "otdr_repeat_once.rom"
    terminal.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23, 0x3E, 0x22, 0x77,  # INC HL ; LD A,0x22 ; LD (HL),A
                0x21, 0x01, 0x20,  # LD HL,0x2001
                0x06, 0x01, 0x0E, 0x33,  # LD B,1 ; LD C,0x33
                0xED, 0xBB,  # OTDR (terminates)
                0x76,  # HALT
            ]
        )
    )
    repeat.write_bytes(
        bytes(
            [
                0x21, 0x00, 0x20,  # LD HL,0x2000
                0x3E, 0x11, 0x77,  # LD A,0x11 ; LD (HL),A
                0x23, 0x3E, 0x22, 0x77,  # INC HL ; LD A,0x22 ; LD (HL),A
                0x21, 0x01, 0x20,  # LD HL,0x2001
                0x06, 0x02, 0x0E, 0x33,  # LD B,2 ; LD C,0x33
                0xED, 0xBB,  # OTDR (repeats once)
                0x76,  # HALT
            ]
        )
    )

    proc_term = subprocess.run(
        [str(z80_binary), "--rom", str(terminal), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_rep = subprocess.run(
        [str(z80_binary), "--rom", str(repeat), "--cycles", "1000"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_rep.stdout) - _parse_executed_cycles(proc_term.stdout) == 21


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ldi_transfers_byte_and_advances_pairs(z80_binary, tmp_path):
    rom = tmp_path / "ldi_transfer.rom"
    # Seed src=0x2010 with 0x9A, then LDI to dst=0x2120 and read back via IX.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x9A,
                0x26,
                0x20,
                0x2E,
                0x10,
                0x77,
                0x16,
                0x21,
                0x1E,
                0x20,
                0x06,
                0x00,
                0x0E,
                0x01,
                0xED,
                0xA0,
                0xDD,
                0x21,
                0x20,
                0x21,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "105"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x9A
    assert _parse_reg(proc.stdout, 1) == 0x00  # B
    assert _parse_reg(proc.stdout, 2) == 0x00  # C
    assert _parse_reg(proc.stdout, 3) == 0x21  # D
    assert _parse_reg(proc.stdout, 4) == 0x21  # E
    assert _parse_reg(proc.stdout, 5) == 0x20  # H
    assert _parse_reg(proc.stdout, 6) == 0x11  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ex_sp_hl_swaps_stack_top_with_hl(z80_binary, tmp_path):
    rom = tmp_path / "ex_sp_hl.rom"
    # Seed stack bytes [0x2100]=0x78,[0x2101]=0x56; set HL=0x1234; EX (SP),HL.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x21,
                0x2E,
                0x00,
                0x3E,
                0x78,
                0x77,
                0x26,
                0x21,
                0x2E,
                0x01,
                0x3E,
                0x56,
                0x77,
                0x31,
                0x00,
                0x21,
                0x26,
                0x12,
                0x2E,
                0x34,
                0xE3,
                0xDD,
                0x21,
                0x00,
                0x21,
                0xDD,
                0x7E,
                0x00,
                0xDD,
                0x7E,
                0x01,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "180"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x12
    assert _parse_reg(proc.stdout, 5) == 0x56  # H
    assert _parse_reg(proc.stdout, 6) == 0x78  # L


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_c_d_branches_when_carry_is_set(z80_binary, tmp_path):
    rom = tmp_path / "jr_c.rom"
    # LD A,0 ; SUB A,1 (sets C) ; JR C,+2 ; LD A,0x11 ; LD A,0x66
    rom.write_bytes(bytes([0x3E, 0x00, 0xD6, 0x01, 0x38, 0x02, 0x3E, 0x11, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_c_d_does_not_branch_when_carry_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "jr_c_not_taken.rom"
    # LD A,1 ; ADD A,1 (C clear) ; JR C,+2 ; LD A,0x11 ; HALT ; LD A,0x66
    rom.write_bytes(bytes([0x3E, 0x01, 0xC6, 0x01, 0x38, 0x02, 0x3E, 0x11, 0x76, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "50"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x11


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_z_d_branches_when_zero_is_set(z80_binary, tmp_path):
    rom = tmp_path / "jr_z.rom"
    # LD A,1 ; SUB A,1 (sets Z) ; JR Z,+2 ; LD A,0x11 ; LD A,0x66
    rom.write_bytes(bytes([0x3E, 0x01, 0xD6, 0x01, 0x28, 0x02, 0x3E, 0x11, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_z_d_does_not_branch_when_zero_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "jr_z_not_taken.rom"
    # LD A,1 ; ADD A,1 (Z clear) ; JR Z,+2 ; LD A,0x11 ; HALT ; LD A,0x66
    rom.write_bytes(bytes([0x3E, 0x01, 0xC6, 0x01, 0x28, 0x02, 0x3E, 0x11, 0x76, 0x3E, 0x66]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "50"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x11


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_nz_d_branches_when_zero_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "jr_nz.rom"
    # LD A,1 ; ADD A,1 (clears Z) ; JR NZ,+2 ; LD A,0x11 ; LD A,0x77
    rom.write_bytes(bytes([0x3E, 0x01, 0xC6, 0x01, 0x20, 0x02, 0x3E, 0x11, 0x3E, 0x77]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x77


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_nz_d_does_not_branch_when_zero_is_set(z80_binary, tmp_path):
    rom = tmp_path / "jr_nz_not_taken.rom"
    # LD A,1 ; SUB A,1 (Z set) ; JR NZ,+2 ; LD A,0x11 ; HALT ; LD A,0x77
    rom.write_bytes(bytes([0x3E, 0x01, 0xD6, 0x01, 0x20, 0x02, 0x3E, 0x11, 0x76, 0x3E, 0x77]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "50"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x11


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_nz_d_after_cp_a_h_branches_when_not_equal(z80_binary, tmp_path):
    rom = tmp_path / "jr_nz_after_cp_a_h_taken.rom"
    # LD A,0x41 ; LD H,0x42 ; CP A,H ; JR NZ,+2 ; LD B,0x11 ; HALT ; LD B,0x77 ; HALT
    rom.write_bytes(bytes([0x3E, 0x41, 0x26, 0x42, 0xBC, 0x20, 0x02, 0x06, 0x11, 0x76, 0x06, 0x77, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "60"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (_parse_flags(proc.stdout) & 0x02) == 0  # FLAG_Z clear after CP A,H mismatch
    assert _parse_reg(proc.stdout, 1) == 0x00  # Branch skips LD B,0x11 and halts before LD B,0x77


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_nz_d_after_cp_a_h_does_not_branch_when_equal(z80_binary, tmp_path):
    rom = tmp_path / "jr_nz_after_cp_a_h_not_taken.rom"
    # LD A,0x42 ; LD H,0x42 ; CP A,H ; JR NZ,+2 ; LD B,0x11 ; HALT ; LD B,0x77 ; HALT
    rom.write_bytes(bytes([0x3E, 0x42, 0x26, 0x42, 0xBC, 0x20, 0x02, 0x06, 0x11, 0x76, 0x06, 0x77, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "60"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (_parse_flags(proc.stdout) & 0x02) != 0  # FLAG_Z set after CP A,H match
    assert _parse_reg(proc.stdout, 1) == 0x11  # Not taken path executes LD B,0x11


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_nc_d_branches_when_carry_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "jr_nc.rom"
    # LD A,1 ; ADD A,1 (clears C) ; JR NC,+2 ; LD A,0x11 ; LD A,0x77
    rom.write_bytes(bytes([0x3E, 0x01, 0xC6, 0x01, 0x30, 0x02, 0x3E, 0x11, 0x3E, 0x77]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x77


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_nc_d_does_not_branch_when_carry_is_set(z80_binary, tmp_path):
    rom = tmp_path / "jr_nc_not_taken.rom"
    # LD A,0 ; SUB A,1 (C set) ; JR NC,+2 ; LD A,0x11 ; HALT ; LD A,0x77
    rom.write_bytes(bytes([0x3E, 0x00, 0xD6, 0x01, 0x30, 0x02, 0x3E, 0x11, 0x76, 0x3E, 0x77]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "50"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x11


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_d_branches_unconditionally(z80_binary, tmp_path):
    rom = tmp_path / "jr_d.rom"
    # JR +2 ; LD A,0x11 ; LD A,0x77
    rom.write_bytes(bytes([0x18, 0x02, 0x3E, 0x11, 0x3E, 0x77]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "30"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x77


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jr_nz_taken_vs_not_taken_cycle_delta(z80_binary, tmp_path):
    rom_taken = tmp_path / "jr_nz_taken_cycles.rom"
    rom_not_taken = tmp_path / "jr_nz_not_taken_cycles.rom"
    # Both paths execute the same instruction stream; only JR NZ timing differs.
    # taken: LD A,1 ; CP A,0 ; JR NZ,+0 ; HALT
    rom_taken.write_bytes(bytes([0x3E, 0x01, 0xFE, 0x00, 0x20, 0x00, 0x76]))
    # not taken: LD A,1 ; CP A,1 ; JR NZ,+0 ; HALT
    rom_not_taken.write_bytes(bytes([0x3E, 0x01, 0xFE, 0x01, 0x20, 0x00, 0x76]))

    proc_taken = subprocess.run(
        [str(z80_binary), "--rom", str(rom_taken), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_not_taken = subprocess.run(
        [str(z80_binary), "--rom", str(rom_not_taken), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_taken.stdout) == 30
    assert _parse_executed_cycles(proc_not_taken.stdout) == 25
    assert _parse_executed_cycles(proc_taken.stdout) - _parse_executed_cycles(proc_not_taken.stdout) == 5


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_djnz_taken_vs_not_taken_cycle_delta(z80_binary, tmp_path):
    rom_taken = tmp_path / "djnz_taken_cycles.rom"
    rom_not_taken = tmp_path / "djnz_not_taken_cycles.rom"
    # taken: LD B,2 ; DJNZ +0 ; HALT
    rom_taken.write_bytes(bytes([0x06, 0x02, 0x10, 0x00, 0x76]))
    # not taken: LD B,1 ; DJNZ +0 ; HALT
    rom_not_taken.write_bytes(bytes([0x06, 0x01, 0x10, 0x00, 0x76]))

    proc_taken = subprocess.run(
        [str(z80_binary), "--rom", str(rom_taken), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_not_taken = subprocess.run(
        [str(z80_binary), "--rom", str(rom_not_taken), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_taken.stdout) == 24
    assert _parse_executed_cycles(proc_not_taken.stdout) == 19
    assert _parse_executed_cycles(proc_taken.stdout) - _parse_executed_cycles(proc_not_taken.stdout) == 5


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_call_nn_and_ret_return_to_next_instruction(z80_binary, tmp_path):
    rom = tmp_path / "call_ret.rom"
    # CALL 0x0008 ; LD A,0x55 ; JP 0x000B ; [sub] LD A,0x99 ; RET ; NOP
    rom.write_bytes(bytes([0xCD, 0x08, 0x00, 0x3E, 0x55, 0xC3, 0x0B, 0x00, 0x3E, 0x99, 0xC9, 0x00]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x55


@pytest.mark.parametrize("subop", [0x45, 0x55, 0x65, 0x75])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_retn_alias_opcodes_return_to_caller(z80_binary, tmp_path, subop):
    rom = tmp_path / f"retn_alias_{subop:02x}.rom"
    # CALL 0x0008 ; LD A,0x55 ; JP 0x000D ; [sub] LD A,0x99 ; RETN(alias) ; NOP...
    rom.write_bytes(bytes([0xCD, 0x08, 0x00, 0x3E, 0x55, 0xC3, 0x0D, 0x00, 0x3E, 0x99, 0xED, subop, 0x00, 0x00]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x55


@pytest.mark.parametrize("subop", [0x4D, 0x5D, 0x6D, 0x7D])
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_reti_alias_opcodes_return_to_caller(z80_binary, tmp_path, subop):
    rom = tmp_path / f"reti_alias_{subop:02x}.rom"
    # CALL 0x0008 ; LD A,0x55 ; JP 0x000D ; [sub] LD A,0x99 ; RETI(alias) ; NOP...
    rom.write_bytes(bytes([0xCD, 0x08, 0x00, 0x3E, 0x55, 0xC3, 0x0D, 0x00, 0x3E, 0x99, 0xED, subop, 0x00, 0x00]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x55


@pytest.mark.parametrize(
    ("opcode", "vector"),
    [
        (0xCF, 0x0008),  # RST 08
        (0xD7, 0x0010),  # RST 10
        (0xDF, 0x0018),  # RST 18
        (0xE7, 0x0020),  # RST 20
        (0xEF, 0x0028),  # RST 28
        (0xF7, 0x0030),  # RST 30
        (0xFF, 0x0038),  # RST 38
    ],
)
@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_rst_vector_matrix_returns_to_caller(z80_binary, tmp_path, opcode, vector):
    rom = tmp_path / f"rst_{vector:04x}_ret.rom"
    image = bytearray([0x00] * 0x60)
    # Bootstrap to main at 0x0040 so vector region is isolated.
    image[0x00:0x03] = bytes([0xC3, 0x40, 0x00])  # JP 0x0040
    # Vector routine: LD A,0x77 ; RET
    image[vector : vector + 3] = bytes([0x3E, 0x77, 0xC9])
    # Main: LD SP,0x2100 ; LD A,0x11 ; RST xx ; LD A,0x22
    image[0x40:0x48] = bytes([0x31, 0x00, 0x21, 0x3E, 0x11, opcode, 0x3E, 0x22])
    rom.write_bytes(bytes(image))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x22
    assert _parse_sp(proc.stdout) == 0x2100


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_rst_00_vectors_to_zero_and_pushes_return_address(z80_binary, tmp_path):
    rom = tmp_path / "rst_00_loop.rom"
    # RST 00 self-vectors at 0x0000. In this minimal ROM it loops and keeps pushing return addresses.
    rom.write_bytes(bytes([0x31, 0x00, 0x21, 0x3E, 0x11, 0xC7]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "70"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x11
    # RST 00 loops back to address 0x0000 in this ROM image.
    assert _parse_pc(proc.stdout) <= 0x0005


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_call_z_nn_branches_when_zero_is_set(z80_binary, tmp_path):
    rom = tmp_path / "call_z.rom"
    # LD A,1 ; SUB A,1 ; CALL Z,0x000B ; JP 0x0010 ; [sub] LD A,0x66 ; RET
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x01,
                0xD6,
                0x01,
                0xCC,
                0x0B,
                0x00,
                0xC3,
                0x10,
                0x00,
                0x00,
                0x3E,
                0x66,
                0xC9,
                0x00,
                0x00,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_call_nz_nn_branches_when_zero_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "call_nz.rom"
    # LD A,2 ; SUB A,1 (Z clear) ; CALL NZ,0x000B ; JP 0x0010 ; [sub] LD A,0x66 ; RET
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x02,
                0xD6,
                0x01,
                0xC4,
                0x0B,
                0x00,
                0xC3,
                0x10,
                0x00,
                0x00,
                0x3E,
                0x66,
                0xC9,
                0x00,
                0x00,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_call_z_taken_vs_not_taken_cycle_delta(z80_binary, tmp_path):
    rom_taken = tmp_path / "call_z_taken_cycles.rom"
    rom_not_taken = tmp_path / "call_z_not_taken_cycles.rom"
    # taken: LD A,1 ; CP A,1 ; CALL Z,0x0008 ; HALT ; HALT
    rom_taken.write_bytes(bytes([0x3E, 0x01, 0xFE, 0x01, 0xCC, 0x08, 0x00, 0x76, 0x76]))
    # not taken: LD A,1 ; CP A,0 ; CALL Z,0x0008 ; HALT ; HALT
    rom_not_taken.write_bytes(bytes([0x3E, 0x01, 0xFE, 0x00, 0xCC, 0x08, 0x00, 0x76, 0x76]))

    proc_taken = subprocess.run(
        [str(z80_binary), "--rom", str(rom_taken), "--cycles", "100"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_not_taken = subprocess.run(
        [str(z80_binary), "--rom", str(rom_not_taken), "--cycles", "100"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_taken.stdout) == 35
    assert _parse_executed_cycles(proc_not_taken.stdout) == 28
    assert _parse_executed_cycles(proc_taken.stdout) - _parse_executed_cycles(proc_not_taken.stdout) == 7


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_call_c_nn_and_ret_c_round_trip(z80_binary, tmp_path):
    rom = tmp_path / "call_c_ret_c.rom"
    # Set C, CALL C to subroutine; RET C should return before overwrite side-effect.
    program = [
        0x3E,
        0x00,
        0xD6,
        0x01,  # C set
        0xDC,
        0x20,
        0x00,  # CALL C,0x0020
        0xDD,
        0x21,
        0x60,
        0x20,  # LD IX,0x2060
        0xDD,
        0x7E,
        0x00,  # LD A,(IX+0)
    ]
    while len(program) < 0x20:
        program.append(0x00)
    program.extend(
        [
            0x3E,
            0x77,
            0x26,
            0x20,
            0x2E,
            0x60,
            0x77,  # write 0x77 marker
            0xD8,  # RET C
            0x3E,
            0xAA,
            0x77,  # would overwrite marker if RET C failed
            0xC9,
        ]
    )
    rom.write_bytes(bytes(program))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "220"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x77


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_call_nc_nn_and_ret_nc_round_trip(z80_binary, tmp_path):
    rom = tmp_path / "call_nc_ret_nc.rom"
    # Clear C, CALL NC to subroutine; RET NC should return before overwrite side-effect.
    program = [
        0x3E,
        0x01,
        0xD6,
        0x00,  # C clear
        0xD4,
        0x20,
        0x00,  # CALL NC,0x0020
        0xDD,
        0x21,
        0x61,
        0x20,  # LD IX,0x2061
        0xDD,
        0x7E,
        0x00,  # LD A,(IX+0)
    ]
    while len(program) < 0x20:
        program.append(0x00)
    program.extend(
        [
            0x3E,
            0x66,
            0x26,
            0x20,
            0x2E,
            0x61,
            0x77,  # write 0x66 marker
            0xD0,  # RET NC
            0x3E,
            0xAA,
            0x77,  # would overwrite marker if RET NC failed
            0xC9,
        ]
    )
    rom.write_bytes(bytes(program))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "220"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ret_z_returns_early_and_preserves_zero_flag_for_caller(z80_binary, tmp_path):
    rom = tmp_path / "ret_z.rom"
    # Caller sets Z=1 and calls subroutine. RET Z should return before SUB clears Z.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x01,
                0xD6,
                0x01,
                0xCD,
                0x11,
                0x00,
                0xCA,
                0x18,
                0x00,
                0x3E,
                0x11,
                0xC3,
                0x1A,
                0x00,
                0x00,
                0x00,
                0xC8,
                0x3E,
                0x01,
                0xD6,
                0x00,
                0xC9,
                0x00,
                0x3E,
                0x66,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ret_z_taken_and_not_taken_cycle_counts(z80_binary, tmp_path):
    rom_taken = tmp_path / "ret_z_taken_cycles.rom"
    rom_not_taken = tmp_path / "ret_z_not_taken_cycles.rom"
    # Main: LD A,1 ; CP A,n ; CALL 0x0009 ; HALT ; NOP ; Sub: RET Z ; RET
    rom_taken.write_bytes(bytes([0x3E, 0x01, 0xFE, 0x01, 0xCD, 0x09, 0x00, 0x76, 0x00, 0xC8, 0xC9]))
    rom_not_taken.write_bytes(bytes([0x3E, 0x01, 0xFE, 0x00, 0xCD, 0x09, 0x00, 0x76, 0x00, 0xC8, 0xC9]))

    proc_taken = subprocess.run(
        [str(z80_binary), "--rom", str(rom_taken), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )
    proc_not_taken = subprocess.run(
        [str(z80_binary), "--rom", str(rom_not_taken), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_executed_cycles(proc_taken.stdout) == 46
    assert _parse_executed_cycles(proc_not_taken.stdout) == 50


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ret_nz_returns_when_zero_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "ret_nz.rom"
    # Build Z=0 then CALL subroutine; RET NZ should exit before memory write side-effect.
    program = [
        0x3E,
        0x02,
        0xD6,
        0x01,  # Z clear
        0xCD,
        0x20,
        0x00,  # CALL 0x0020
        0xDD,
        0x21,
        0x62,
        0x20,  # LD IX,0x2062
        0xDD,
        0x7E,
        0x00,  # LD A,(IX+0)
    ]
    while len(program) < 0x20:
        program.append(0x00)
    program.extend(
        [
            0xC0,  # RET NZ
            0x3E,
            0xAA,
            0x26,
            0x20,
            0x2E,
            0x62,
            0x77,  # only written if RET NZ fails
            0xC9,
        ]
    )
    rom.write_bytes(bytes(program))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "220"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x00


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ex_sp_ix_swaps_ix_and_stack_pair(z80_binary, tmp_path):
    rom = tmp_path / "ex_sp_ix.rom"
    # Stack top starts as 0x2034, IX starts as 0x2000.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x7B,
                0x26,
                0x20,
                0x2E,
                0x34,
                0x77,
                0x26,
                0x21,
                0x2E,
                0x00,
                0x3E,
                0x34,
                0x77,
                0x26,
                0x21,
                0x2E,
                0x01,
                0x3E,
                0x20,
                0x77,
                0x31,
                0x00,
                0x21,
                0xDD,
                0x21,
                0x00,
                0x20,
                0xDD,
                0xE3,
                0xDD,
                0x7E,
                0x00,
                0xFD,
                0x21,
                0x00,
                0x21,
                0xFD,
                0x7E,
                0x00,
                0xFD,
                0x7E,
                0x01,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "260"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x20


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ex_sp_iy_swaps_iy_and_stack_pair(z80_binary, tmp_path):
    rom = tmp_path / "ex_sp_iy.rom"
    # Stack top starts as 0x2056, IY starts as 0x2000.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x6A,
                0x26,
                0x20,
                0x2E,
                0x56,
                0x77,
                0x26,
                0x21,
                0x2E,
                0x00,
                0x3E,
                0x56,
                0x77,
                0x26,
                0x21,
                0x2E,
                0x01,
                0x3E,
                0x20,
                0x77,
                0x31,
                0x00,
                0x21,
                0xFD,
                0x21,
                0x00,
                0x20,
                0xFD,
                0xE3,
                0xFD,
                0x7E,
                0x00,
                0xDD,
                0x21,
                0x00,
                0x21,
                0xDD,
                0x7E,
                0x00,
                0xDD,
                0x7E,
                0x01,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "260"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x20


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jp_m_nn_branches_when_sign_is_set(z80_binary, tmp_path):
    rom = tmp_path / "jp_m.rom"
    # LD A,0 ; SUB A,1 (sets S) ; JP M,0x000C ; LD A,0x11 ; JP 0x000E ; LD A,0x77
    rom.write_bytes(bytes([0x3E, 0x00, 0xD6, 0x01, 0xFA, 0x0C, 0x00, 0x3E, 0x11, 0xC3, 0x0E, 0x00, 0x3E, 0x77, 0x00]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "50"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x77


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_call_m_nn_and_ret_m_round_trip(z80_binary, tmp_path):
    rom = tmp_path / "call_m_ret_m.rom"
    # Set S via SUB, CALL M into subroutine, then RET M should return to caller.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x00,
                0xD6,
                0x01,
                0xFC,
                0x0C,
                0x00,
                0xC3,
                0x12,
                0x00,
                0x00,
                0x00,
                0x3E,
                0x66,
                0xF8,
                0x3E,
                0x11,
                0xC9,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "110"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jp_p_nn_branches_when_sign_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "jp_p.rom"
    # LD A,1 ; SUB A,0 (S clear) ; JP P,0x000C ; LD A,0x11 ; JP 0x000E ; LD A,0x77
    rom.write_bytes(bytes([0x3E, 0x01, 0xD6, 0x00, 0xF2, 0x0C, 0x00, 0x3E, 0x11, 0xC3, 0x0E, 0x00, 0x3E, 0x77, 0x00]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "50"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x77


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_call_p_nn_and_ret_p_round_trip(z80_binary, tmp_path):
    rom = tmp_path / "call_p_ret_p.rom"
    # Set S clear via SUB, CALL P into subroutine, then RET P should return to caller.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x01,
                0xD6,
                0x00,
                0xF4,
                0x0C,
                0x00,
                0xC3,
                0x12,
                0x00,
                0x00,
                0x00,
                0x3E,
                0x66,
                0xF0,
                0x3E,
                0x11,
                0xC9,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "110"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x66


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ret_p_returns_when_sign_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "ret_p.rom"
    # Build S=0 then CALL subroutine; RET P should exit before memory write side-effect.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x01,
                0xD6,
                0x00,
                0xCD,
                0x15,
                0x00,
                0xDD,
                0x21,
                0x60,
                0x20,
                0xDD,
                0x7E,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0xF0,
                0x3E,
                0xAA,
                0x26,
                0x20,
                0x2E,
                0x60,
                0x77,
                0xC9,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "220"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x00


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit_0_hli_sets_zero_flag_for_clear_bit(z80_binary, tmp_path):
    rom = tmp_path / "bit_0_hli.rom"
    # Write 0 to (HL), test BIT 0,(HL), and read back byte through IX.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x40,
                0x3E,
                0x00,
                0x77,
                0xCB,
                0x46,
                0xDD,
                0x21,
                0x40,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_set_and_res_0_hli_update_memory(z80_binary, tmp_path):
    rom = tmp_path / "set_res_0_hli.rom"
    # SET then RES bit 0 in (HL), BIT verifies clear, then read back via IX.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x40,
                0x3E,
                0x00,
                0x77,
                0xCB,
                0xC6,
                0xCB,
                0x86,
                0xCB,
                0x46,
                0xDD,
                0x21,
                0x40,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set after BIT 0,(HL)


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jp_pe_nn_branches_when_parity_is_set(z80_binary, tmp_path):
    rom = tmp_path / "jp_pe.rom"
    # Build P=1 via CPI with BC=2 (BC->1 => P set), then JP PE should branch.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x00,
                0x26,
                0x20,
                0x2E,
                0x40,
                0x77,
                0x3E,
                0x00,
                0x06,
                0x00,
                0x0E,
                0x02,
                0xED,
                0xA1,
                0xEA,
                0x15,
                0x00,
                0x3E,
                0x11,
                0xC3,
                0x17,
                0x00,
                0x3E,
                0x77,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x77


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_call_pe_nn_and_ret_pe_round_trip(z80_binary, tmp_path):
    rom = tmp_path / "call_pe_ret_pe.rom"
    # P=1 via CPI; CALL PE enters subroutine and RET PE returns immediately.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x00,
                0x26,
                0x20,
                0x2E,
                0x40,
                0x77,
                0x3E,
                0x00,
                0x06,
                0x00,
                0x0E,
                0x02,
                0xED,
                0xA1,
                0x3E,
                0x55,
                0xEC,
                0x1E,
                0x00,
                0xC3,
                0x24,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0xE8,
                0x3E,
                0x11,
                0xC9,
                0x00,
                0x00,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "160"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x55


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit1_set1_res1_a_updates_flags_and_register(z80_binary, tmp_path):
    rom = tmp_path / "bit1_a.rom"
    # SET 1,A then BIT 1,A (Z clear), then RES 1,A and BIT 1,A (Z set).
    rom.write_bytes(bytes([0x3E, 0x00, 0xCB, 0xCF, 0xCB, 0x4F, 0xCB, 0x8F, 0xCB, 0x4F]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 1,A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit1_set1_res1_hli_updates_memory(z80_binary, tmp_path):
    rom = tmp_path / "bit1_hli.rom"
    # Set and clear bit1 in (HL), verify with BIT 1,(HL), then read memory via IX.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x40,
                0x3E,
                0x00,
                0x77,
                0xCB,
                0xCE,
                0xCB,
                0x4E,
                0xCB,
                0x8E,
                0xCB,
                0x4E,
                0xDD,
                0x21,
                0x40,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "150"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 1,(HL)


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_jp_po_nn_branches_when_parity_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "jp_po.rom"
    # Build P=0 via CPI with BC=1 (BC->0 => P clear), then JP PO should branch.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x00,
                0x26,
                0x20,
                0x2E,
                0x40,
                0x77,
                0x3E,
                0x00,
                0x06,
                0x00,
                0x0E,
                0x01,
                0xED,
                0xA1,
                0xE2,
                0x15,
                0x00,
                0x3E,
                0x11,
                0xC3,
                0x17,
                0x00,
                0x3E,
                0x77,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x77


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_call_po_nn_branches_when_parity_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "call_po.rom"
    # Build P=0; CALL PO writes 0x77 into memory in subroutine; caller reads it back.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x00,
                0x26,
                0x20,
                0x2E,
                0x40,
                0x77,
                0x3E,
                0x00,
                0x06,
                0x00,
                0x0E,
                0x01,
                0xED,
                0xA1,
                0xE4,
                0x20,
                0x00,
                0xDD,
                0x21,
                0x50,
                0x20,
                0xDD,
                0x7E,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x3E,
                0x77,
                0x26,
                0x20,
                0x2E,
                0x50,
                0x77,
                0xC9,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "220"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x77


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ret_po_returns_when_parity_is_clear(z80_binary, tmp_path):
    rom = tmp_path / "ret_po.rom"
    # Build P=0 then CALL subroutine; RET PO should exit before memory write side-effect.
    rom.write_bytes(
        bytes(
            [
                0x3E,
                0x00,
                0x26,
                0x20,
                0x2E,
                0x40,
                0x77,
                0x3E,
                0x00,
                0x06,
                0x00,
                0x0E,
                0x01,
                0xED,
                0xA1,
                0xCD,
                0x20,
                0x00,
                0xDD,
                0x21,
                0x60,
                0x20,
                0xDD,
                0x7E,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0x00,
                0xE0,
                0x3E,
                0xAA,
                0x26,
                0x20,
                0x2E,
                0x60,
                0x77,
                0xC9,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "220"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x00


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit2_set2_res2_a_updates_flags_and_register(z80_binary, tmp_path):
    rom = tmp_path / "bit2_a.rom"
    # SET 2,A then BIT 2,A (Z clear), then RES 2,A and BIT 2,A (Z set).
    rom.write_bytes(bytes([0x3E, 0x00, 0xCB, 0xD7, 0xCB, 0x57, 0xCB, 0x97, 0xCB, 0x57]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 2,A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit2_set2_res2_hli_updates_memory(z80_binary, tmp_path):
    rom = tmp_path / "bit2_hli.rom"
    # Set and clear bit2 in (HL), verify with BIT 2,(HL), then read memory via IX.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x40,
                0x3E,
                0x00,
                0x77,
                0xCB,
                0xD6,
                0xCB,
                0x56,
                0xCB,
                0x96,
                0xCB,
                0x56,
                0xDD,
                0x21,
                0x40,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "160"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 2,(HL)


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit3_set3_res3_a_updates_flags_and_register(z80_binary, tmp_path):
    rom = tmp_path / "bit3_a.rom"
    # SET 3,A then BIT 3,A (Z clear), then RES 3,A and BIT 3,A (Z set).
    rom.write_bytes(bytes([0x3E, 0x00, 0xCB, 0xDF, 0xCB, 0x5F, 0xCB, 0x9F, 0xCB, 0x5F]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 3,A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit3_set3_res3_hli_updates_memory(z80_binary, tmp_path):
    rom = tmp_path / "bit3_hli.rom"
    # Set and clear bit3 in (HL), verify with BIT 3,(HL), then read memory via IX.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x40,
                0x3E,
                0x00,
                0x77,
                0xCB,
                0xDE,
                0xCB,
                0x5E,
                0xCB,
                0x9E,
                0xCB,
                0x5E,
                0xDD,
                0x21,
                0x40,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "160"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 3,(HL)


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit4_set4_res4_a_updates_flags_and_register(z80_binary, tmp_path):
    rom = tmp_path / "bit4_a.rom"
    # SET 4,A then BIT 4,A (Z clear), then RES 4,A and BIT 4,A (Z set).
    rom.write_bytes(bytes([0x3E, 0x00, 0xCB, 0xE7, 0xCB, 0x67, 0xCB, 0xA7, 0xCB, 0x67]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 4,A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit4_set4_res4_hli_updates_memory(z80_binary, tmp_path):
    rom = tmp_path / "bit4_hli.rom"
    # Set and clear bit4 in (HL), verify with BIT 4,(HL), then read memory via IX.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x40,
                0x3E,
                0x00,
                0x77,
                0xCB,
                0xE6,
                0xCB,
                0x66,
                0xCB,
                0xA6,
                0xCB,
                0x66,
                0xDD,
                0x21,
                0x40,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "160"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 4,(HL)


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit5_set5_res5_a_updates_flags_and_register(z80_binary, tmp_path):
    rom = tmp_path / "bit5_a.rom"
    # SET 5,A then BIT 5,A (Z clear), then RES 5,A and BIT 5,A (Z set).
    rom.write_bytes(bytes([0x3E, 0x00, 0xCB, 0xEF, 0xCB, 0x6F, 0xCB, 0xAF, 0xCB, 0x6F]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 5,A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit5_set5_res5_hli_updates_memory(z80_binary, tmp_path):
    rom = tmp_path / "bit5_hli.rom"
    # Set and clear bit5 in (HL), verify with BIT 5,(HL), then read memory via IX.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x40,
                0x3E,
                0x00,
                0x77,
                0xCB,
                0xEE,
                0xCB,
                0x6E,
                0xCB,
                0xAE,
                0xCB,
                0x6E,
                0xDD,
                0x21,
                0x40,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "160"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 5,(HL)


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit6_set6_res6_a_updates_flags_and_register(z80_binary, tmp_path):
    rom = tmp_path / "bit6_a.rom"
    # SET 6,A then BIT 6,A (Z clear), then RES 6,A and BIT 6,A (Z set).
    rom.write_bytes(bytes([0x3E, 0x00, 0xCB, 0xF7, 0xCB, 0x77, 0xCB, 0xB7, 0xCB, 0x77]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 6,A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit6_set6_res6_hli_updates_memory(z80_binary, tmp_path):
    rom = tmp_path / "bit6_hli.rom"
    # Set and clear bit6 in (HL), verify with BIT 6,(HL), then read memory via IX.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x40,
                0x3E,
                0x00,
                0x77,
                0xCB,
                0xF6,
                0xCB,
                0x76,
                0xCB,
                0xB6,
                0xCB,
                0x76,
                0xDD,
                0x21,
                0x40,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "160"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 6,(HL)


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit7_set7_res7_a_updates_flags_and_register(z80_binary, tmp_path):
    rom = tmp_path / "bit7_a.rom"
    # SET 7,A then BIT 7,A (Z clear), then RES 7,A and BIT 7,A (Z set).
    rom.write_bytes(bytes([0x3E, 0x00, 0xCB, 0xFF, 0xCB, 0x7F, 0xCB, 0xBF, 0xCB, 0x7F]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 7,A


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_bit7_set7_res7_hli_updates_memory(z80_binary, tmp_path):
    rom = tmp_path / "bit7_hli.rom"
    # Set and clear bit7 in (HL), verify with BIT 7,(HL), then read memory via IX.
    rom.write_bytes(
        bytes(
            [
                0x26,
                0x20,
                0x2E,
                0x40,
                0x3E,
                0x00,
                0x77,
                0xCB,
                0xFE,
                0xCB,
                0x7E,
                0xCB,
                0xBE,
                0xCB,
                0x7E,
                0xDD,
                0x21,
                0x40,
                0x20,
                0xDD,
                0x7E,
                0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "160"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x00
    assert (flags & 0x02) != 0  # FLAG_Z set by final BIT 7,(HL)


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_undocumented_ld_a_ixh_and_ld_a_ixl(z80_binary, tmp_path):
    rom = tmp_path / "ld_a_ixh_ixl.rom"
    # LD IX,0x1234 ; LD A,IXH ; LD A,IXL
    rom.write_bytes(bytes([0xDD, 0x21, 0x34, 0x12, 0xDD, 0x7C, 0xDD, 0x7D, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x34


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_undocumented_ld_a_iyh_and_ld_a_iyl(z80_binary, tmp_path):
    rom = tmp_path / "ld_a_iyh_iyl.rom"
    # LD IY,0x5678 ; LD A,IYH ; LD A,IYL
    rom.write_bytes(bytes([0xFD, 0x21, 0x78, 0x56, 0xFD, 0x7C, 0xFD, 0x7D, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0x78


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_undocumented_inc_dec_ld_ixh_ixl(z80_binary, tmp_path):
    rom = tmp_path / "inc_dec_ld_ixh_ixl.rom"
    # LD IX,0x0000 ; LD IXH,0x10 ; INC IXH ; DEC IXH ; LD IXL,0xFE ; INC IXL ; LD A,IXH ; LD A,IXL
    rom.write_bytes(
        bytes(
            [
                0xDD, 0x21, 0x00, 0x00,
                0xDD, 0x26, 0x10,
                0xDD, 0x24,
                0xDD, 0x25,
                0xDD, 0x2E, 0xFE,
                0xDD, 0x2C,
                0xDD, 0x7C,
                0xDD, 0x7D,
                0x76,
            ]
        )
    )

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "160"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert _parse_r0(proc.stdout) == 0xFF


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_undocumented_add_a_ixh(z80_binary, tmp_path):
    rom = tmp_path / "add_a_ixh.rom"
    # LD IX,0x4000 ; LD A,0x40 ; ADD A,IXH => 0x80 (signed overflow)
    rom.write_bytes(bytes([0xDD, 0x21, 0x00, 0x40, 0x3E, 0x40, 0xDD, 0x84, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )

    flags = _parse_flags(proc.stdout)
    assert _parse_r0(proc.stdout) == 0x80
    assert (flags & 0x01) != 0  # FLAG_S
    assert (flags & 0x02) == 0  # FLAG_Z
    assert (flags & 0x08) != 0  # FLAG_P overflow
    assert (flags & 0x20) == 0  # FLAG_C


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_repeated_dd_prefix_is_accepted(z80_binary, tmp_path):
    rom = tmp_path / "repeated_dd.rom"
    # DD DD LD IX,0x1234 ; LD A,IXH
    rom.write_bytes(bytes([0xDD, 0xDD, 0x21, 0x34, 0x12, 0xDD, 0x7C, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_r0(proc.stdout) == 0x12


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_repeated_fd_prefix_is_accepted(z80_binary, tmp_path):
    rom = tmp_path / "repeated_fd.rom"
    # FD FD LD IY,0x5678 ; LD A,IYH
    rom.write_bytes(bytes([0xFD, 0xFD, 0x21, 0x78, 0x56, 0xFD, 0x7C, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_r0(proc.stdout) == 0x56


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_ed_undocumented_opcode_acts_as_nop(z80_binary, tmp_path):
    rom = tmp_path / "ed_undoc_nop.rom"
    # ED 00 (undocumented NOP) ; LD A,0x42
    rom.write_bytes(bytes([0xED, 0x00, 0x3E, 0x42, 0x76]))

    proc = subprocess.run(
        [str(z80_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_r0(proc.stdout) == 0x42
