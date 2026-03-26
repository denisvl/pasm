import pathlib
import shutil
import subprocess
import textwrap
import uuid

import pytest

from src import generator as gen_mod
from src.parser import yaml_loader
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _make_workdir(prefix: str) -> pathlib.Path:
    root = BASE_DIR / "generated" / "_pytest_work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


def test_mc6809_yaml_instruction_matrix_validates():
    processor_path, system_path = example_pair("mc6809")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))

    assert data["metadata"]["name"] == "MC6809"
    assert data["metadata"]["endian"] == "big"
    assert data["metadata"]["undefined_opcode_policy"] == "nop"
    assert data["interrupts"]["model"] == "mc6809"
    assert data["memory"]["default_size"] == 65536

    names = [inst["name"] for inst in data["instructions"]]
    name_set = set(names)
    assert "EXEC" not in name_set
    assert len(names) == len(name_set), "Instruction names must be unique"
    assert all(isinstance(inst.get("display"), str) and inst["display"] for inst in data["instructions"])
    assert all(not n.startswith("UD_") for n in names), "Undefined opcode placeholders should not be present"
    assert all(str(inst.get("behavior", "")).strip() for inst in data["instructions"])

    expected = {
        "NOP",
        "BRA_REL",
        "BCC_REL",
        "BCS_REL",
        "BHI_REL",
        "BLS_REL",
        "BPL_REL",
        "BMI_REL",
        "BVC_REL",
        "BVS_REL",
        "BGE_REL",
        "BLT_REL",
        "BGT_REL",
        "BLE_REL",
        "BNE_REL",
        "BEQ_REL",
        "RTS",
        "RTI_MIN",
        "PSHS",
        "PULS",
        "PSHU",
        "PULU",
        "ORCC_IMM",
        "ANDCC_IMM",
        "ABX",
        "JMP_EXT",
        "BSR_REL",
        "JSR_EXT",
        "SUBA_IMM",
        "CMPA_IMM",
        "ANDA_IMM",
        "EORA_IMM",
        "ORA_IMM",
        "ADDA_IMM",
        "SUBB_IMM",
        "CMPB_IMM",
        "ANDB_IMM",
        "EORB_IMM",
        "ORB_IMM",
        "ADDB_IMM",
        "LDA_IMM",
        "LDB_IMM",
        "LDX_IMM",
        "LDU_IMM",
        "LDA_DIR",
        "STA_DIR",
        "LDB_DIR",
        "STB_DIR",
        "LDA_EXT",
        "STA_EXT",
        "LDB_EXT",
        "STB_EXT",
        "LDY_IMM_P2",
        "LDS_IMM_P2",
        "SUBA_DIR",
        "ADDB_EXT",
        "SUBD_DIR",
        "ADDD_EXT",
        "CMPX_DIR",
        "STX_EXT",
        "LDU_DIR",
        "STU_EXT",
        "LDY_DIR_P2",
        "STS_EXT_P2",
        "CMPD_IDX5_P10",
        "CMPY_IDX5_P10",
        "LDY_IDX5_P2",
        "STY_IDX5_P2",
        "LDS_IDX5_P2",
        "STS_IDX5_P2",
        "LBNE_REL16_P2",
        "LBLE_REL16_P2",
        "CMPU_DIR_P11",
        "CMPS_EXT_P11",
        "CMPU_IDX5_P11",
        "CMPS_IDX5_P11",
        "NEG_DIR",
        "LSR_EXT",
        "CLR_DIR",
        "CLR_EXT",
        "DAA",
        "EXG",
        "TFR",
        "MUL",
        "ABA",
        "SYNC",
        "CWAI",
        "SWI",
        "SWI2_P2",
        "SWI3_P3",
        "LSRA",
        "RORA",
        "ASRA",
        "ASLA",
        "ROLA",
        "LSRB",
        "RORB",
        "ASRB",
        "ASLB",
        "ROLB",
        "LDA_IDX5",
        "STA_IDX5",
        "LDB_IDX5",
        "STB_IDX5",
        "LDX_IDX5",
        "STX_IDX5",
        "LSR_IDX5",
        "JMP_IDX5",
        "SUBA_IDX5",
        "ADCA_IDX5",
        "CMPX_IDX5",
        "JSR_IDX5",
        "SUBB_IDX5",
        "ADCB_IDX5",
        "LDD_IDX5",
        "STD_IDX5",
        "LDU_IDX5",
        "STU_IDX5",
        "LEAX_IDX5",
        "LEAY_IDX5",
        "LEAS_IDX5",
        "LEAU_IDX5",
        "INC_IDX5",
        "JSR_DIR",
        "SUBD_IDX5",
        "ADDD_IDX5",
    }
    assert expected <= name_set

    categories = {inst["category"] for inst in data["instructions"]}
    assert {"control", "data_transfer", "arithmetic"} <= categories


def test_mc6809_opcode_sets_match_official_matrix():
    processor_path, system_path = example_pair("mc6809")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))

    base_actual = {
        int(inst["encoding"]["opcode"])
        for inst in data["instructions"]
        if int(inst["encoding"].get("prefix", 0)) == 0
    }
    p10_actual = {
        int(inst["encoding"]["opcode"])
        for inst in data["instructions"]
        if int(inst["encoding"].get("prefix", 0)) == 0x10
    }
    p11_actual = {
        int(inst["encoding"]["opcode"])
        for inst in data["instructions"]
        if int(inst["encoding"].get("prefix", 0)) == 0x11
    }

    base_expected = {
        0x00, 0x03, 0x04, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0C, 0x0D, 0x0E, 0x0F,
        0x12, 0x13, 0x16, 0x17, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F,
        *range(0x20, 0x30), *range(0x30, 0x38), 0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3F,
        0x40, 0x43, 0x44, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x4C, 0x4D, 0x4F,
        0x50, 0x53, 0x54, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x5C, 0x5D, 0x5F,
        0x60, 0x63, 0x64, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x6C, 0x6D, 0x6E, 0x6F,
        0x70, 0x73, 0x74, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x7C, 0x7D, 0x7E, 0x7F,
        *range(0x80, 0x87), 0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x8D, 0x8E,
        *range(0x90, 0xA0), *range(0xA0, 0xB0), *range(0xB0, 0xC0),
        *range(0xC0, 0xC7), 0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCE,
        *range(0xD0, 0x100),
    }
    p10_expected = {
        *range(0x21, 0x30), 0x3F, 0x83, 0x8C, 0x8E, 0x93, 0x9C, 0x9E, 0x9F,
        0xA3, 0xAC, 0xAE, 0xAF, 0xB3, 0xBC, 0xBE, 0xBF, 0xCE, 0xDE, 0xDF,
        0xEE, 0xEF, 0xFE, 0xFF,
    }
    p11_expected = {0x3F, 0x83, 0x8C, 0x93, 0x9C, 0xA3, 0xAC, 0xB3, 0xBC}

    assert base_expected <= base_actual
    assert p10_expected <= p10_actual
    assert p11_expected <= p11_actual

    assert len(base_actual) >= len(base_expected)
    assert len(p10_actual) >= len(p10_expected)
    assert len(p11_actual) >= len(p11_expected)


@pytest.mark.skipif(
    (shutil.which("cc") is None and shutil.which("gcc") is None),
    reason="C compiler not available on PATH",
)
def test_mc6809_generated_decoder_covers_declared_opcode_spaces():
    processor_path, system_path = example_pair("mc6809")
    outdir = _make_workdir("mc6809_decoder_scan_")
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    scan_c = outdir / "scan_decode.c"
    scan_c.write_text(
        textwrap.dedent(
            """
            #include <stdio.h>
            #include <stdint.h>
            #include "MC6809_decoder.h"

            static int count_base(void) {
                int ok = 0;
                for (int op = 0; op < 256; op++) {
                    uint32_t raw = (uint32_t)op;
                    if (mc6809_decode(raw, 0, 0).valid) ok++;
                }
                return ok;
            }

            static int count_pref_10(void) {
                int ok = 0;
                for (int op = 0; op < 256; op++) {
                    uint32_t raw = (uint32_t)op;
                    if (mc6809_decode(raw, 0x10, 0).valid) ok++;
                }
                return ok;
            }

            static int count_pref_11(void) {
                int ok = 0;
                for (int op = 0; op < 256; op++) {
                    uint32_t raw = (uint32_t)op;
                    if (mc6809_decode(raw, 0x11, 0).valid) ok++;
                }
                return ok;
            }

            int main(void) {
                printf("base=%d\\n", count_base());
                printf("p10=%d\\n", count_pref_10());
                printf("p11=%d\\n", count_pref_11());
                return 0;
            }
            """
        ),
        encoding="utf-8",
    )

    compiler = shutil.which("cc") or shutil.which("gcc")
    binary = outdir / "scan_decode"
    subprocess.check_call(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-I",
            str(outdir / "src"),
            str(outdir / "src" / "MC6809_decoder.c"),
            str(scan_c),
            "-o",
            str(binary),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    proc = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    lines = dict(line.split("=", 1) for line in proc.stdout.strip().splitlines())

    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))
    base_expected = len(
        {
            int(inst["encoding"]["opcode"])
            for inst in data["instructions"]
            if int(inst["encoding"].get("prefix", 0)) == 0
        }
    )
    p10_expected = len(
        {
            int(inst["encoding"]["opcode"])
            for inst in data["instructions"]
            if int(inst["encoding"].get("prefix", 0)) == 0x10
        }
    )
    p11_expected = len(
        {
            int(inst["encoding"]["opcode"])
            for inst in data["instructions"]
            if int(inst["encoding"].get("prefix", 0)) == 0x11
        }
    )

    assert int(lines["base"]) == base_expected
    assert int(lines["p10"]) == p10_expected
    assert int(lines["p11"]) == p11_expected
