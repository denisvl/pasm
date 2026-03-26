import pathlib
import uuid

from src import generator as gen_mod
from src.parser import yaml_loader
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _make_workdir(prefix: str) -> pathlib.Path:
    root = BASE_DIR / ".tmp_test_work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


def test_mos6510_yaml_validates():
    processor_path, system_path = example_pair("mos6510")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))
    assert data["metadata"]["name"] == "MOS6510"
    assert data["metadata"]["undefined_opcode_policy"] == "trap"
    assert data["memory"]["default_size"] == 65536
    reg_names = {reg["name"] for reg in data["registers"]}
    assert {"A", "X", "Y", "SP", "PC", "IO_DDR", "IO_DATA"} <= reg_names
    names = {inst["name"] for inst in data["instructions"]}
    assert {
        "NOP",
        "LDA_IMM",
        "LDA_ZP",
        "LDA_INDY",
        "STA_ZP",
        "STA_INDY",
        "TAX",
        "INX",
        "JMP_ABS",
        "BRK",
        "LAX_ZP_UD",
        "LAX_INDY_UD",
        "LAX_ABS_UD",
        "SAX_ZP_UD",
        "SAX_ABS_UD",
        "DCP_ZP_UD",
        "DCP_ABS_UD",
        "ISC_ZP_UD",
        "ISC_ABS_UD",
        "SLO_ZP_UD",
        "SLO_ABS_UD",
        "RLA_ZP_UD",
        "RLA_ABS_UD",
        "SRE_ZP_UD",
        "SRE_ABS_UD",
        "RRA_ZP_UD",
        "RRA_ABS_UD",
        "ANC_IMM_UD",
        "ANC2_IMM_UD",
        "ALR_IMM_UD",
        "ARR_IMM_UD",
        "AXS_IMM_UD",
        "XAA_IMM_UD",
        "LXA_IMM_UD",
        "LAS_ABSY_UD",
        "AHX_INDY_UD",
        "AHX_ABSY_UD",
        "SHY_ABSX_UD",
        "SHX_ABSY_UD",
        "TAS_ABSY_UD",
    } <= names


def test_generate_mos6510():
    processor_path, system_path = example_pair("mos6510")
    outdir = _make_workdir("mos6510_basic_")

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    src_dir = outdir / "src"
    assert (src_dir / "MOS6510.c").exists()
    assert (src_dir / "MOS6510.h").exists()
    assert (src_dir / "MOS6510_decoder.c").exists()


def test_mos6510_opcode_bindings_for_indirect_y_and_unofficial():
    processor_path, system_path = example_pair("mos6510")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))
    opcode_by_name = {
        inst["name"]: int(inst["encoding"]["opcode"]) for inst in data["instructions"]
    }
    assert opcode_by_name["LDA_INDY"] == 0xB1
    assert opcode_by_name["STA_INDY"] == 0x91
    assert opcode_by_name["LAX_INDY_UD"] == 0xB3
    assert opcode_by_name["LAX_ABS_UD"] == 0xAF
    assert opcode_by_name["SAX_ABS_UD"] == 0x8F
    assert opcode_by_name["DCP_ABS_UD"] == 0xCF
    assert opcode_by_name["ISC_ABS_UD"] == 0xEF
    assert opcode_by_name["SLO_ABS_UD"] == 0x0F
    assert opcode_by_name["RLA_ABS_UD"] == 0x2F
    assert opcode_by_name["SRE_ABS_UD"] == 0x4F
    assert opcode_by_name["RRA_ABS_UD"] == 0x6F
    assert opcode_by_name["RLA_ZP_UD"] == 0x27
    assert opcode_by_name["SRE_ZP_UD"] == 0x47
    assert opcode_by_name["RRA_ZP_UD"] == 0x67
    assert opcode_by_name["ANC_IMM_UD"] == 0x0B
    assert opcode_by_name["ANC2_IMM_UD"] == 0x2B
    assert opcode_by_name["ALR_IMM_UD"] == 0x4B
    assert opcode_by_name["ARR_IMM_UD"] == 0x6B
    assert opcode_by_name["AXS_IMM_UD"] == 0xCB
    assert opcode_by_name["XAA_IMM_UD"] == 0x8B
    assert opcode_by_name["LXA_IMM_UD"] == 0xAB
    assert opcode_by_name["LAS_ABSY_UD"] == 0xBB
    assert opcode_by_name["AHX_INDY_UD"] == 0x93
    assert opcode_by_name["AHX_ABSY_UD"] == 0x9F
    assert opcode_by_name["SHY_ABSX_UD"] == 0x9C
    assert opcode_by_name["SHX_ABSY_UD"] == 0x9E
    assert opcode_by_name["TAS_ABSY_UD"] == 0x9B


def test_mos6510_unofficial_opcode_matrix_subset():
    processor_path, system_path = example_pair("mos6510")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))
    actual = {
        int(inst["encoding"]["opcode"])
        for inst in data["instructions"]
        if inst["name"].endswith("_UD")
    }
    expected = {
        0x03, 0x07, 0x0B, 0x0F, 0x13, 0x17, 0x1B, 0x1F,
        0x23, 0x27, 0x2B, 0x2F, 0x33, 0x37, 0x3B, 0x3F,
        0x43, 0x47, 0x4B, 0x4F, 0x53, 0x57, 0x5B, 0x5F,
        0x63, 0x67, 0x6B, 0x6F, 0x73, 0x77, 0x7B, 0x7F,
        0x83, 0x87, 0x8B, 0x8F,
        0x93, 0x97, 0x9B, 0x9C, 0x9E, 0x9F,
        0xA3, 0xA7, 0xAB, 0xAF, 0xB3, 0xB7, 0xBB, 0xBF,
        0xC3, 0xC7, 0xCB, 0xCF, 0xD3, 0xD7, 0xDB, 0xDF,
        0xE3, 0xE7, 0xEF, 0xF3, 0xF7, 0xFB, 0xFF,
    }
    assert expected <= actual


def test_mos6510_unofficial_control_and_sbc_presence():
    processor_path, system_path = example_pair("mos6510")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))
    actual = {
        int(inst["encoding"]["opcode"])
        for inst in data["instructions"]
        if inst["name"].endswith("_UD")
    }
    expected = {
        0x02, 0x12, 0x22, 0x32, 0x42, 0x52, 0x62, 0x72, 0x92, 0xB2, 0xD2, 0xF2,
        0x1A, 0x3A, 0x5A, 0x7A, 0xDA, 0xFA,
        0x80, 0x82, 0x89, 0xC2, 0xE2,
        0x04, 0x44, 0x64,
        0x14, 0x34, 0x54, 0x74, 0xD4, 0xF4,
        0x0C,
        0x1C, 0x3C, 0x5C, 0x7C, 0xDC, 0xFC,
        0xEB,
    }
    assert expected <= actual
