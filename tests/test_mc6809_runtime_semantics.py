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
    root = BASE_DIR / "generated" / "_pytest_work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


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


@pytest.fixture(scope="module")
def mc6809_binary():
    outdir = _make_workdir("mc6809_runtime_") / "generated"
    processor_path, system_path = example_pair("mc6809")
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

    binary_name = "mc6809_test.exe" if os.name == "nt" else "mc6809_test"
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


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_lda_ldb_immediate(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "lda_ldb_imm.rom"
    rom.write_bytes(bytes([0x86, 0x12, 0xC6, 0x34]))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "4"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x12
    assert _parse_reg(proc.stdout, 1) == 0x34


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_bra_relative_skips_instruction(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "bra_rel.rom"
    # BRA +2 ; LDA #0x11 ; LDA #0x77
    rom.write_bytes(bytes([0x20, 0x02, 0x86, 0x11, 0x86, 0x77]))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "5"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x77


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_beq_then_bne_control_flow(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "beq_bne.rom"
    # CLRA ; BEQ +2 ; LDA #0x11 ; LDA #0x22 ; BNE +2 ; LDA #0x33 ; LDA #0x44
    rom.write_bytes(bytes([0x4F, 0x27, 0x02, 0x86, 0x11, 0x86, 0x22, 0x26, 0x02, 0x86, 0x33, 0x86, 0x44]))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "14"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x44


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_jsr_and_rts_round_trip(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "jsr_rts.rom"
    image = bytearray([0x12] * 16)
    # 0000: JSR 0008
    image[0:3] = bytes([0xBD, 0x00, 0x08])
    # 0003: LDA #0x55
    image[3:5] = bytes([0x86, 0x55])
    image[5] = 0x12  # NOP
    # 0008: LDA #0xAA ; RTS
    image[8:11] = bytes([0x86, 0xAA, 0x39])
    rom.write_bytes(bytes(image))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "19"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x55


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_direct_store_and_reload_path(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "dir_store_load.rom"
    # LDA #0xA5 ; STA <0x40 ; CLRA ; LDA <0x40
    rom.write_bytes(bytes([0x86, 0xA5, 0x97, 0x40, 0x4F, 0x96, 0x40]))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "12"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0xA5


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_ldx_immediate_big_endian_sign_flag(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "ldx_endian.rom"
    # LDX #0x8001
    rom.write_bytes(bytes([0x8E, 0x80, 0x01]))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "3"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert (flags & 0x08) != 0  # N
    assert (flags & 0x04) == 0  # Z


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_10ce_sets_stack_pointer_big_endian(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "lds_prefix_10.rom"
    # 10 CE 12 34 => LDS #0x1234
    rom.write_bytes(bytes([0x10, 0xCE, 0x12, 0x34]))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "4"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_sp(proc.stdout) == 0x1234


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_pshs_and_puls_round_trip_registers(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "pshs_puls.rom"
    # LDA #0x12 ; LDB #0x34 ; PSHS A,B ; CLRA ; CLRB ; PULS A,B
    rom.write_bytes(bytes([0x86, 0x12, 0xC6, 0x34, 0x34, 0x06, 0x4F, 0x5F, 0x35, 0x06]))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "24"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x12
    assert _parse_reg(proc.stdout, 1) == 0x34


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_orcc_and_andcc_control_branch_carry(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "orcc_andcc_branch.rom"
    # ORCC #1 ; BCS +3 ; LDA #11 ; BRA +2 ; LDA #22
    # ANDCC #FE ; BCC +3 ; LDA #33 ; BRA +2 ; LDA #44
    rom.write_bytes(
        bytes([0x1A, 0x01, 0x25, 0x03, 0x86, 0x11, 0x20, 0x02, 0x86, 0x22, 0x1C, 0xFE, 0x24, 0x03, 0x86, 0x33, 0x20, 0x02, 0x86, 0x44])
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "50"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x44


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_b_register_immediate_alu_chain(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "b_alu_chain.rom"
    # LDB #10 ; ADDB #22 ; SUBB #12 ; CMPB #20 ; ANDB #0F ; ORB #80 ; EORB #FF
    rom.write_bytes(bytes([0xC6, 0x10, 0xCB, 0x22, 0xC0, 0x12, 0xC1, 0x20, 0xC4, 0x0F, 0xCA, 0x80, 0xC8, 0xFF]))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "20"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 1) == 0x7F
    assert (flags & 0x08) == 0  # N
    assert (flags & 0x04) == 0  # Z


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_direct_extended_alu_and_long_branch_prefix10(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "dir_ext_lbne.rom"
    # LDA #05 ; STA <40 ; LDA #09 ; SUBA <40 -> A=04
    # LDB #03 ; STB >2001 ; LDB #01 ; ADDB >2001 -> B=04
    # LBNE +3 ; LDB #FF ; NOP ; LDB #55 ; BRA -2 (stable loop)
    rom.write_bytes(
        bytes(
            [
                0x86, 0x05,
                0x97, 0x40,
                0x86, 0x09,
                0x90, 0x40,
                0xC6, 0x03,
                0xF7, 0x20, 0x01,
                0xC6, 0x01,
                0xFB, 0x20, 0x01,
                0x10, 0x26, 0x00, 0x03,
                0xC6, 0xFF,
                0x12,
                0xC6, 0x55,
                0x20, 0xFE,
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x04
    assert _parse_reg(proc.stdout, 1) == 0x55


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_cmps_dir_prefix11_sets_zero_for_equal(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "cmps_dir_p11.rom"
    # LDS #1234 ; store 0x1234 at <50 ; CMPS <50
    # LBNE +3 ; LDB #77 ; BRA +2 ; LDB #11
    rom.write_bytes(
        bytes(
            [
                0x10, 0xCE, 0x12, 0x34,
                0x86, 0x12,
                0x97, 0x50,
                0x86, 0x34,
                0x97, 0x51,
                0x11, 0x9C, 0x50,
                0x10, 0x26, 0x00, 0x03,
                0xC6, 0x77,
                0x20, 0x02,
                0xC6, 0x11,
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "110"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 1) == 0x77


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_memory_unary_direct_and_extended_paths(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "mem_unary_dir_ext.rom"
    # LDA #05 ; STA <40 ; NEG <40 ; LDB <40   => B = FB
    # LDA #81 ; STA >2000 ; LSR >2000 ; LDA >2000 => A = 40 and C=1
    rom.write_bytes(
        bytes(
            [
                0x86, 0x05,
                0x97, 0x40,
                0x00, 0x40,
                0xD6, 0x40,
                0x86, 0x81,
                0xB7, 0x20, 0x00,
                0x74, 0x20, 0x00,
                0xB6, 0x20, 0x00,
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 0) == 0x40
    assert _parse_reg(proc.stdout, 1) == 0xFB
    assert (flags & 0x01) != 0  # C


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_daa_tfr_exg_mul_pipeline(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "daa_tfr_exg_mul.rom"
    # LDA #09 ; ADDA #09 ; DAA -> A=18
    # TFR A,B ; LDA #04 ; EXG A,B -> A=18,B=04 ; MUL -> D=0060
    rom.write_bytes(
        bytes(
            [
                0x86, 0x09,
                0x8B, 0x09,
                0x19,
                0x1F, 0x89,
                0x86, 0x04,
                0x1E, 0x89,
                0x3D,
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "31"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 0) == 0x00
    assert _parse_reg(proc.stdout, 1) == 0x60
    assert (flags & 0x04) == 0  # Z
    assert (flags & 0x01) == 0  # C


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_aba_sets_accumulator_a(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "aba.rom"
    # LDA #0F ; LDB #01 ; ABA ; BRA -2
    rom.write_bytes(bytes([0x86, 0x0F, 0xC6, 0x01, 0x1B, 0x20, 0xFE]))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "20"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 0) == 0x10
    assert (flags & 0x20) != 0  # H


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_swi_vectors_and_stack_push(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "swi.rom"
    image = bytearray([0x00] * 65536)
    # LDS #0800 ; SWI
    image[0x0000] = 0x10
    image[0x0001] = 0xCE
    image[0x0002] = 0x08
    image[0x0003] = 0x00
    image[0x0004] = 0x3F
    # SWI vector -> 0x0200 (BRA -2 loop)
    image[0xFFFA] = 0x02
    image[0xFFFB] = 0x00
    image[0x0200] = 0x20
    image[0x0201] = 0xFE
    rom.write_bytes(bytes(image))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_pc(proc.stdout) == 0x0200
    assert _parse_sp(proc.stdout) == 0x07F4


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_swi2_and_swi3_vectors(mc6809_binary):
    rom2 = _make_workdir("mc6809_rom_") / "swi2.rom"
    image2 = bytearray([0x00] * 65536)
    # LDS #0800 ; SWI2
    image2[0x0000] = 0x10
    image2[0x0001] = 0xCE
    image2[0x0002] = 0x08
    image2[0x0003] = 0x00
    image2[0x0004] = 0x10
    image2[0x0005] = 0x3F
    # SWI2 vector -> 0x0300 (BRA -2 loop)
    image2[0xFFF4] = 0x03
    image2[0xFFF5] = 0x00
    image2[0x0300] = 0x20
    image2[0x0301] = 0xFE
    rom2.write_bytes(bytes(image2))

    proc2 = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom2), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_pc(proc2.stdout) == 0x0300
    assert _parse_sp(proc2.stdout) == 0x07F4

    rom3 = _make_workdir("mc6809_rom_") / "swi3.rom"
    image3 = bytearray([0x00] * 65536)
    # LDS #0800 ; SWI3
    image3[0x0000] = 0x10
    image3[0x0001] = 0xCE
    image3[0x0002] = 0x08
    image3[0x0003] = 0x00
    image3[0x0004] = 0x11
    image3[0x0005] = 0x3F
    # SWI3 vector -> 0x0400 (BRA -2 loop)
    image3[0xFFF2] = 0x04
    image3[0xFFF3] = 0x00
    image3[0x0400] = 0x20
    image3[0x0401] = 0xFE
    rom3.write_bytes(bytes(image3))

    proc3 = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom3), "--cycles", "40"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_pc(proc3.stdout) == 0x0400
    assert _parse_sp(proc3.stdout) == 0x07F4


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_swi_rti_restores_full_register_frame(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "swi_rti_full.rom"
    image = bytearray([0x00] * 65536)
    # LDS #0800 ; LDA #AA ; LDB #55 ; SWI ; BRA -2
    image[0x0000:0x000B] = bytes(
        [0x10, 0xCE, 0x08, 0x00, 0x86, 0xAA, 0xC6, 0x55, 0x3F, 0x20, 0xFE]
    )
    # SWI vector -> 0x0200, handler: CLRA ; CLRB ; RTI
    image[0xFFFA] = 0x02
    image[0xFFFB] = 0x00
    image[0x0200:0x0203] = bytes([0x4F, 0x5F, 0x3B])
    rom.write_bytes(bytes(image))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_pc(proc.stdout) == 0x0009
    assert _parse_reg(proc.stdout, 0) == 0xAA
    assert _parse_reg(proc.stdout, 1) == 0x55


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_swi2_swi3_do_not_force_i_or_f_masks(mc6809_binary):
    def _run(prefix: int, vec_hi: int, vec_lo: int) -> subprocess.CompletedProcess[str]:
        rom = _make_workdir("mc6809_rom_") / f"swi{prefix:02x}_mask.rom"
        image = bytearray([0x00] * 65536)
        # LDS #0800 ; ANDCC #AF (clear I/F) ; SWI2|SWI3 ; BRA -2
        image[0x0000:0x000A] = bytes([0x10, 0xCE, 0x08, 0x00, 0x1C, 0xAF, prefix, 0x3F, 0x20, 0xFE])
        image[vec_hi] = 0x02
        image[vec_lo] = 0x00
        image[0x0200] = 0x3B  # RTI
        rom.write_bytes(bytes(image))
        return subprocess.run(
            [str(mc6809_binary), "--rom", str(rom), "--cycles", "120"],
            check=True,
            capture_output=True,
            text=True,
        )

    proc2 = _run(0x10, 0xFFF4, 0xFFF5)
    flags2 = _parse_flags(proc2.stdout)
    assert (flags2 & 0x10) == 0  # I
    assert (flags2 & 0x40) == 0  # F

    proc3 = _run(0x11, 0xFFF2, 0xFFF3)
    flags3 = _parse_flags(proc3.stdout)
    assert (flags3 & 0x10) == 0  # I
    assert (flags3 & 0x40) == 0  # F


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_idx5_load_store_and_unary_paths(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "idx5_paths.rom"
    # LDX #2000
    # LDA #33 ; STA 2,X (A7 02)
    # CLRA ; LDA 2,X (A6 02)
    # LDB #81 ; STB 3,X (E7 03) ; LSR 3,X (64 03) ; LDB 3,X (E6 03)
    # BRA -2
    rom.write_bytes(
        bytes(
            [
                0x8E, 0x20, 0x00,
                0x86, 0x33,
                0xA7, 0x02,
                0x4F,
                0xA6, 0x02,
                0xC6, 0x81,
                0xE7, 0x03,
                0x64, 0x03,
                0xE6, 0x03,
                0x20, 0xFE,
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 0) == 0x33
    assert _parse_reg(proc.stdout, 1) == 0x40
    assert (flags & 0x01) != 0  # C from LSR


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_idx5_ldx_stx_using_u_base(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "idx5_ldx_stx_u.rom"
    # LDU #2000 ; LDX #3456 ; STX 1,U (AF 41) ; LDX #0000 ; LDX 1,U (AE 41)
    # STX <50 ; LDA <50 ; LDB <51 ; BRA -2
    rom.write_bytes(
        bytes(
            [
                0xCE, 0x20, 0x00,
                0x8E, 0x34, 0x56,
                0xAF, 0x41,
                0x8E, 0x00, 0x00,
                0xAE, 0x41,
                0x9F, 0x50,
                0x96, 0x50,
                0xD6, 0x51,
                0x20, 0xFE,
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x34
    assert _parse_reg(proc.stdout, 1) == 0x56


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_idx5_a_group_alu_cmpx_and_flags(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "idx5_a_group.rom"
    rom.write_bytes(
        bytes(
            [
                0x8E, 0x20, 0x00,  # LDX #2000
                0x86, 0x22,        # LDA #22
                0xA7, 0x01,        # STA 1,X
                0x86, 0x30,        # LDA #30
                0xA0, 0x01,        # SUBA 1,X
                0xAB, 0x01,        # ADDA 1,X
                0xA4, 0x01,        # ANDA 1,X
                0xAA, 0x01,        # ORA 1,X
                0xA8, 0x01,        # EORA 1,X
                0x86, 0x01,        # LDA #01
                0x1A, 0x01,        # ORCC #01 (set C)
                0xA9, 0x01,        # ADCA 1,X
                0xA2, 0x01,        # SBCA 1,X
                0xA5, 0x01,        # BITA 1,X
                0xCE, 0x21, 0x00,  # LDU #2100
                0x86, 0x34,        # LDA #34
                0xA7, 0x41,        # STA 1,U
                0x86, 0x56,        # LDA #56
                0xA7, 0x42,        # STA 2,U
                0x8E, 0x34, 0x56,  # LDX #3456
                0xAC, 0x41,        # CMPX 1,U
                0x20, 0xFE,        # BRA -2
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "140"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 0) == 0x56
    assert (flags & 0x04) != 0  # Z from CMPX


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_idx5_b_group_and_d_u_paths(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "idx5_b_group.rom"
    rom.write_bytes(
        bytes(
            [
                0x8E, 0x20, 0x00,  # LDX #2000
                0xC6, 0x40,        # LDB #40
                0xE7, 0x01,        # STB 1,X
                0xC6, 0x50,        # LDB #50
                0xE1, 0x01,        # CMPB 1,X
                0xE2, 0x01,        # SBCB 1,X
                0xE5, 0x01,        # BITB 1,X
                0xC6, 0x02,        # LDB #02
                0xE0, 0x01,        # SUBB 1,X
                0xE4, 0x01,        # ANDB 1,X
                0xE8, 0x01,        # EORB 1,X
                0xEA, 0x01,        # ORB 1,X
                0xE9, 0x01,        # ADCB 1,X
                0xEB, 0x01,        # ADDB 1,X
                0x86, 0x12,        # LDA #12
                0xC6, 0x34,        # LDB #34
                0xED, 0x03,        # STD 3,X
                0xEC, 0x03,        # LDD 3,X
                0xCE, 0xBE, 0xEF,  # LDU #BEEF
                0xEF, 0x05,        # STU 5,X
                0xCE, 0x00, 0x00,  # LDU #0000
                0xEE, 0x05,        # LDU 5,X
                0x1F, 0x30,        # TFR U,D
                0x20, 0xFE,        # BRA -2
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "200"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0xBE
    assert _parse_reg(proc.stdout, 1) == 0xEF


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_jsr_idx5_round_trip(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "jsr_idx5.rom"
    image = bytearray([0x12] * 0x30)
    image[0x00:0x03] = bytes([0x8E, 0x00, 0x10])  # LDX #0010
    image[0x03:0x05] = bytes([0xAD, 0x00])        # JSR 0,X
    image[0x05:0x07] = bytes([0x86, 0x55])        # LDA #55
    image[0x07:0x09] = bytes([0x20, 0xFE])        # BRA -2
    image[0x10:0x13] = bytes([0x86, 0xAA, 0x39])  # sub: LDA #AA ; RTS
    rom.write_bytes(bytes(image))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x55


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_lea_idx5_variants_and_inc_idx5(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "lea_inc_idx5.rom"
    # LDX #2000 ; LDU #3000 ; LEAX 1,U ; LEAY 2,U ; LEAS 3,U ; LEAU 4,X ; STX <50 ; STY <52 ; LDA #7F ; STA 1,X ; INC 1,X ; LDB 1,X ; BRA -2
    rom.write_bytes(
        bytes(
            [
                0x8E, 0x20, 0x00,
                0xCE, 0x30, 0x00,
                0x30, 0x41,
                0x31, 0x42,
                0x32, 0x43,
                0x33, 0x04,
                0x9F, 0x50,
                0x10, 0x9F, 0x52,
                0x86, 0x7F,
                0xA7, 0x01,
                0x6C, 0x01,
                0xE6, 0x01,
                0x20, 0xFE,
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "170"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 1) == 0x80
    assert (flags & 0x08) != 0  # N from final LDB 0x80


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_jsr_dir_round_trip(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "jsr_dir.rom"
    image = bytearray([0x12] * 0x60)
    # LDA #00 ; JSR <30 ; LDA #55 ; BRA -2
    image[0x00:0x08] = bytes([0x86, 0x00, 0x9D, 0x30, 0x86, 0x55, 0x20, 0xFE])
    # sub @ 0x30: LDA #AA ; RTS
    image[0x30:0x33] = bytes([0x86, 0xAA, 0x39])
    rom.write_bytes(bytes(image))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x55


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_prefixed_indexed_16bit_paths(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "pref_idx16.rom"
    rom.write_bytes(
        bytes(
            [
                0x8E, 0x01, 0x00,              # LDX #0100
                0xCC, 0x12, 0x34,              # LDD #1234
                0xED, 0x04,                    # STD 4,X
                0xCC, 0xBE, 0xEF,              # LDD #BEEF
                0xED, 0x06,                    # STD 6,X
                0xCC, 0xCA, 0xFE,              # LDD #CAFE
                0xED, 0x08,                    # STD 8,X
                0x10, 0xAE, 0x04,              # LDY 4,X
                0x10, 0xEE, 0x06,              # LDS 6,X
                0x10, 0xAC, 0x04,              # CMPY 4,X
                0x10, 0xA3, 0x08,              # CMPD 8,X
                0xCE, 0xCA, 0xFE,              # LDU #CAFE
                0x11, 0xA3, 0x08,              # CMPU 8,X
                0x10, 0xAF, 0x0A,              # STY 10,X
                0x10, 0xEF, 0x0C,              # STS 12,X
                0x11, 0xAC, 0x0C,              # CMPS 12,X
                0x1F, 0x20,                    # TFR Y,D
                0x20, 0xFE,                    # BRA -2
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "220"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 0) == 0x12
    assert _parse_reg(proc.stdout, 1) == 0x34
    assert (flags & 0x04) != 0  # Z set by final CMPS indexed compare


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_accumulator_shift_rotate_variants(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "acc_shift_rotate.rom"
    rom.write_bytes(
        bytes(
            [
                0x86, 0x81,  # LDA #81
                0x44,        # LSRA
                0x46,        # RORA
                0x47,        # ASRA
                0x48,        # ASLA
                0x49,        # ROLA
                0xC6, 0x03,  # LDB #03
                0x54,        # LSRB
                0x56,        # RORB
                0x57,        # ASRB
                0x58,        # ASLB
                0x59,        # ROLB
                0x20, 0xFE,  # BRA -2
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 0) == 0x41
    assert _parse_reg(proc.stdout, 1) == 0x01
    assert (flags & 0x01) != 0  # C
    assert (flags & 0x04) == 0  # Z


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_subd_addd_idx5_paths(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "subd_addd_idx5.rom"
    rom.write_bytes(
        bytes(
            [
                0x8E, 0x01, 0x00,  # LDX #0100
                0xCC, 0x20, 0x00,  # LDD #2000
                0xED, 0x04,        # STD 4,X
                0xCC, 0x00, 0x10,  # LDD #0010
                0xA3, 0x04,        # SUBD 4,X
                0xE3, 0x04,        # ADDD 4,X
                0x20, 0xFE,        # BRA -2
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "110"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert _parse_reg(proc.stdout, 0) == 0x00
    assert _parse_reg(proc.stdout, 1) == 0x10
    assert (flags & 0x01) != 0  # C from final ADDD overflow past 0xFFFF


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_idx5_indirect_offset_reads_pointer_target(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "idx5_indirect.rom"
    rom.write_bytes(
        bytes(
            [
                0x8E, 0x01, 0x00,        # LDX #0100
                0xCC, 0x20, 0x00,        # LDD #2000
                0xFD, 0x01, 0x01,        # STD $0101  (pointer at X+1 -> 2000)
                0x86, 0xAB,              # LDA #AB
                0xB7, 0x20, 0x00,        # STA $2000
                0x86, 0x00,              # LDA #00
                0xA6, 0x98, 0x01,        # LDA [1,X]  (indirect indexed)
                0x20, 0xFE,              # BRA -2
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "120"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0xAB


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_idx5_auto_inc_dec_writeback(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "idx5_auto_inc_dec.rom"
    image = bytearray([0x12] * 0x0200)
    image[0x00:0x03] = bytes([0x8E, 0x01, 0x00])  # LDX #0100
    image[0x03:0x05] = bytes([0xA6, 0x80])        # LDA ,X+
    image[0x05:0x07] = bytes([0xA6, 0x80])        # LDA ,X+
    image[0x07:0x09] = bytes([0xA6, 0x82])        # LDA ,-X
    image[0x09:0x0B] = bytes([0xA6, 0x83])        # LDA ,--X
    image[0x0B:0x0D] = bytes([0x9F, 0x60])        # STX <60
    image[0x0D:0x0F] = bytes([0xD6, 0x60])        # LDB <60 (X hi)
    image[0x0F:0x11] = bytes([0x96, 0x61])        # LDA <61 (X lo)
    image[0x11:0x13] = bytes([0x20, 0xFE])        # BRA -2
    image[0x00FF] = 0xA0
    image[0x0100] = 0xA1
    image[0x0101] = 0xA2
    rom.write_bytes(bytes(image))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "80"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0xFF
    assert _parse_reg(proc.stdout, 1) == 0x00


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_idx5_indirect_auto_inc_updates_index_register(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "idx5_indirect_autoinc.rom"
    image = bytearray([0x12] * 0x0400)
    image[0x00:0x03] = bytes([0x8E, 0x01, 0x20])  # LDX #0120
    image[0x03:0x05] = bytes([0xA6, 0x91])        # LDA [,X++]
    image[0x05:0x07] = bytes([0x97, 0x62])        # STA <62
    image[0x07:0x09] = bytes([0x9F, 0x60])        # STX <60
    image[0x09:0x0B] = bytes([0xD6, 0x62])        # LDB <62 (loaded value)
    image[0x0B:0x0D] = bytes([0x96, 0x60])        # LDA <60 (X hi)
    image[0x0D:0x0F] = bytes([0x81, 0x01])        # CMPA #01
    image[0x0F:0x11] = bytes([0x26, 0x04])        # BNE fail
    image[0x11:0x13] = bytes([0x96, 0x61])        # LDA <61 (X lo)
    image[0x13:0x15] = bytes([0x20, 0xFE])        # BRA -2
    image[0x15:0x17] = bytes([0x86, 0xEE])        # fail: LDA #EE
    image[0x17:0x19] = bytes([0x20, 0xFE])        # BRA -2
    image[0x0120] = 0x02
    image[0x0121] = 0x00
    image[0x0200] = 0xB7
    rom.write_bytes(bytes(image))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "90"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x22
    assert _parse_reg(proc.stdout, 1) == 0xB7


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_idx5_pcr_offset8_reads_from_instruction_stream_relative(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "idx5_pcr8.rom"
    # LDA 4,PCR ; BRA -2 ; DB 99h
    rom.write_bytes(bytes([0xA6, 0x8C, 0x02, 0x20, 0xFE, 0x99]))

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "60"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x99


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_idx5_indirect_extended_reads_pointer_target(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "idx5_indirect_ext.rom"
    # LDD #2000 ; STD $0080 ; LDA #5A ; STA $2000 ; LDA #00 ; LDA [$0080] ; BRA -2
    rom.write_bytes(
        bytes(
            [
                0xCC, 0x20, 0x00,
                0xFD, 0x00, 0x80,
                0x86, 0x5A,
                0xB7, 0x20, 0x00,
                0x86, 0x00,
                0xA6, 0x9F, 0x00, 0x80,
                0x20, 0xFE,
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "140"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x5A


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_prefixed_ldy_idx5_indirect_extended_round_trip(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "p10_ldy_idx5_indirect_ext.rom"
    # LDD #2100 ; STD $0080 ; LDD #1234 ; STD $2100 ; LDY [$0080] ; TFR Y,D ; BRA -2
    rom.write_bytes(
        bytes(
            [
                0xCC, 0x21, 0x00,
                0xFD, 0x00, 0x80,
                0xCC, 0x12, 0x34,
                0xFD, 0x21, 0x00,
                0x10, 0xAE, 0x9F, 0x00, 0x80,
                0x1F, 0x20,
                0x20, 0xFE,
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "180"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert _parse_reg(proc.stdout, 0) == 0x12
    assert _parse_reg(proc.stdout, 1) == 0x34


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_prefixed_cmpu_idx5_indirect_extended_sets_zero(mc6809_binary):
    rom = _make_workdir("mc6809_rom_") / "p11_cmpu_idx5_indirect_ext.rom"
    # LDD #2200 ; STD $0080 ; LDD #1234 ; STD $2200 ; LDU #1234 ; CMPU [$0080] ; BRA -2
    rom.write_bytes(
        bytes(
            [
                0xCC, 0x22, 0x00,
                0xFD, 0x00, 0x80,
                0xCC, 0x12, 0x34,
                0xFD, 0x22, 0x00,
                0xCE, 0x12, 0x34,
                0x11, 0xA3, 0x9F, 0x00, 0x80,
                0x20, 0xFE,
            ]
        )
    )

    proc = subprocess.run(
        [str(mc6809_binary), "--rom", str(rom), "--cycles", "200"],
        check=True,
        capture_output=True,
        text=True,
    )
    flags = _parse_flags(proc.stdout)
    assert (flags & 0x04) != 0  # Z
