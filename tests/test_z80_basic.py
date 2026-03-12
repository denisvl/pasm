import pathlib
import shutil
import subprocess
import textwrap

import pytest

from src import generator as gen_mod
from src.analyzer.instruction_analyzer import audit_opcode_spaces
from src.codegen.cpu_decoder import generate_decoder
from src.parser import yaml_loader


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def test_z80_yaml_validates():
    isa_path = BASE_DIR / "examples" / "z80.yaml"
    data = yaml_loader.load_isa(str(isa_path))
    assert data["metadata"]["name"] == "Z80"
    assert data["memory"]["default_size"] == 65536
    assert data["interrupts"]["model"] == "z80"
    assert any(inst["name"] == "LD_A_N" for inst in data["instructions"])
    assert len(data["instructions"]) >= 311
    assert all(isinstance(inst.get("display"), str) and inst["display"] for inst in data["instructions"])
    names = {inst["name"] for inst in data["instructions"]}
    display_by_name = {inst["name"]: inst["display"] for inst in data["instructions"]}
    assert display_by_name["RLC_IYD"] == "RLC (IY+d)"
    assert display_by_name["JP_IX"] == "JP (IX)"
    assert display_by_name["JP_IY"] == "JP (IY)"
    assert display_by_name["IN_A_N"] == "IN A, (n)"
    assert display_by_name["OUT_N_A"] == "OUT (n), A"
    assert display_by_name["IN_R_C"] == "IN r, (C)"
    assert display_by_name["OUT_C_R"] == "OUT (C), r"
    assert display_by_name["BIT_R"] == "BIT b, r"
    assert display_by_name["SET_R"] == "SET b, r"
    assert display_by_name["RES_R"] == "RES b, r"
    assert display_by_name["ROT_SHIFT_IXD_R"] == "ROT/SHIFT (IX+d), r"
    assert display_by_name["ROT_SHIFT_IYD_R"] == "ROT/SHIFT (IY+d), r"
    assert display_by_name["BIT_IXD_R"] == "BIT b, (IX+d), r"
    assert display_by_name["BIT_IYD_R"] == "BIT b, (IY+d), r"
    assert display_by_name["SET_IXD_R"] == "SET b, (IX+d), r"
    assert display_by_name["SET_IYD_R"] == "SET b, (IY+d), r"
    assert display_by_name["RES_IXD_R"] == "RES b, (IX+d), r"
    assert display_by_name["RES_IYD_R"] == "RES b, (IY+d), r"
    assert "LD_B_N" in names
    assert "ADD_A_N" in names
    assert "SUB_A_N" in names
    assert "ADC_A_N" in names
    assert "SBC_A_N" in names
    assert "SUB_A_R" in names
    assert "ADD_HL_BC" in names
    assert "ADD_HL_DE" in names
    assert "ADD_HL_HL" in names
    assert "ADD_HL_SP" in names
    assert "ADD_IX_BC" in names
    assert "ADD_IX_DE" in names
    assert "ADD_IX_IX" in names
    assert "ADD_IX_SP" in names
    assert "ADD_IY_BC" in names
    assert "ADD_IY_DE" in names
    assert "ADD_IY_IY" in names
    assert "ADD_IY_SP" in names
    assert "INC_HLI" in names
    assert "DEC_HLI" in names
    assert "INC_SS" in names
    assert "DEC_SS" in names
    assert "INC_IX" in names
    assert "DEC_IX" in names
    assert "INC_IY" in names
    assert "DEC_IY" in names
    assert "ADC_HL_BC" in names
    assert "ADC_HL_DE" in names
    assert "ADC_HL_HL" in names
    assert "ADC_HL_SP" in names
    assert "SBC_HL_BC" in names
    assert "SBC_HL_DE" in names
    assert "SBC_HL_HL" in names
    assert "SBC_HL_SP" in names
    assert "SCF" in names
    assert "CCF" in names
    assert "CPL" in names
    assert "DAA" in names
    assert "NEG" in names
    assert "RRD" in names
    assert "RLD" in names
    assert "AND_A_N" in names
    assert "XOR_A_N" in names
    assert "OR_A_N" in names
    assert "CP_A_N" in names
    assert "JP_NZ_NN" in names
    assert "JP_NC_NN" in names
    assert "JP_C_NN" in names
    assert "JP_PO_NN" in names
    assert "JP_PE_NN" in names
    assert "JP_P_NN" in names
    assert "JP_M_NN" in names
    assert "JP_HLI" in names
    assert "JP_IX" in names
    assert "JP_IY" in names
    assert "LD_IXD_A" in names
    assert "LD_A_IXD" in names
    assert "LD_IYD_A" in names
    assert "LD_A_IYD" in names
    assert "LD_R_IXD" in names
    assert "LD_R_IYD" in names
    assert "LD_IXD_R" in names
    assert "LD_IYD_R" in names
    assert "LD_IXD_N" in names
    assert "LD_IYD_N" in names
    assert "ADD_A_IXD" in names
    assert "ADC_A_IXD" in names
    assert "SUB_IXD" in names
    assert "SBC_A_IXD" in names
    assert "AND_IXD" in names
    assert "XOR_IXD" in names
    assert "OR_IXD" in names
    assert "CP_IXD" in names
    assert "ADD_A_IYD" in names
    assert "ADC_A_IYD" in names
    assert "SUB_IYD" in names
    assert "SBC_A_IYD" in names
    assert "AND_IYD" in names
    assert "XOR_IYD" in names
    assert "OR_IYD" in names
    assert "CP_IYD" in names
    assert "INC_IXD" in names
    assert "DEC_IXD" in names
    assert "INC_IYD" in names
    assert "DEC_IYD" in names
    assert "LD_IX_NN" in names
    assert "LD_IY_NN" in names
    assert "LD_SP_NN" in names
    assert "LD_SP_HL" in names
    assert "LD_SP_IX" in names
    assert "LD_SP_IY" in names
    assert "LD_BC_NN" in names
    assert "LD_DE_NN" in names
    assert "LD_HL_NN" in names
    assert "LD_BCI_A" in names
    assert "LD_DEI_A" in names
    assert "LD_NN_A" in names
    assert "LD_A_NN" in names
    assert "LD_A_BCI" in names
    assert "LD_A_DEI" in names
    assert "LD_HLI_N" in names
    assert "LD_I_A" in names
    assert "LD_A_I" in names
    assert "LD_R_A" in names
    assert "LD_A_R" in names
    assert "LD_NN_HL" in names
    assert "LD_HL_NN_IND" in names
    assert "LD_NN_IX" in names
    assert "LD_IX_NN_IND" in names
    assert "LD_NN_IY" in names
    assert "LD_IY_NN_IND" in names
    assert "LD_NN_BC_ED" in names
    assert "LD_NN_DE_ED" in names
    assert "LD_NN_HL_ED" in names
    assert "LD_NN_SP_ED" in names
    assert "LD_BC_NN_IND_ED" in names
    assert "LD_DE_NN_IND_ED" in names
    assert "LD_HL_NN_IND_ED" in names
    assert "LD_SP_NN_IND_ED" in names
    assert "PUSH_BC" in names
    assert "PUSH_DE" in names
    assert "PUSH_HL" in names
    assert "PUSH_AF" in names
    assert "PUSH_IX" in names
    assert "PUSH_IY" in names
    assert "POP_BC" in names
    assert "POP_DE" in names
    assert "POP_HL" in names
    assert "POP_AF" in names
    assert "POP_IX" in names
    assert "POP_IY" in names
    assert "HALT" in names
    assert "HALT_DD" in names
    assert "HALT_FD" in names
    assert "LD_R_R" in names
    for op in ("RLC", "RRC", "RL", "RR", "SLA", "SLL", "SRA", "SRL"):
        assert f"{op}_R" in names
        assert f"{op}_HLI" in names
        assert f"{op}_IXD" in names
        assert f"{op}_IYD" in names
    assert "BIT_R" in names
    assert "SET_R" in names
    assert "RES_R" in names
    assert "ROT_SHIFT_IXD_R" in names
    assert "ROT_SHIFT_IYD_R" in names
    assert "BIT_IXD_R" in names
    assert "BIT_IYD_R" in names
    assert "SET_IXD_R" in names
    assert "SET_IYD_R" in names
    assert "RES_IXD_R" in names
    assert "RES_IYD_R" in names
    for bit in range(8):
        assert f"BIT_{bit}_IXD" in names
        assert f"SET_{bit}_IXD" in names
        assert f"RES_{bit}_IXD" in names
        assert f"BIT_{bit}_IYD" in names
        assert f"SET_{bit}_IYD" in names
        assert f"RES_{bit}_IYD" in names
    assert "IND" in names
    assert "INIR" in names
    assert "IN_R_C" in names
    assert "OUTD" in names
    assert "OUT_C_R" in names
    assert "OTIR" in names
    assert "EXX" in names
    assert "EX_DE_HL" in names
    assert "EX_SP_HL" in names
    assert "EX_SP_IX" in names
    assert "EX_SP_IY" in names
    assert "CPIR" in names
    assert "CPD" in names
    assert "CPDR" in names
    assert "LDD" in names
    assert "LDDR" in names
    assert "LDI" in names
    assert "RRC_A" in names
    assert "RL_A" in names
    assert "RR_A" in names
    assert "SLA_A" in names
    assert "SET_0_A" in names
    assert "BIT_1_A" in names
    assert "SET_1_A" in names
    assert "RES_1_A" in names
    assert "BIT_2_A" in names
    assert "SET_2_A" in names
    assert "RES_2_A" in names
    assert "BIT_3_A" in names
    assert "SET_3_A" in names
    assert "RES_3_A" in names
    assert "BIT_4_A" in names
    assert "SET_4_A" in names
    assert "RES_4_A" in names
    assert "BIT_5_A" in names
    assert "SET_5_A" in names
    assert "RES_5_A" in names
    assert "BIT_6_A" in names
    assert "SET_6_A" in names
    assert "RES_6_A" in names
    assert "BIT_7_A" in names
    assert "SET_7_A" in names
    assert "RES_7_A" in names
    assert "BIT_0_HLI" in names
    assert "BIT_1_HLI" in names
    assert "BIT_2_HLI" in names
    assert "BIT_3_HLI" in names
    assert "BIT_4_HLI" in names
    assert "BIT_5_HLI" in names
    assert "BIT_6_HLI" in names
    assert "BIT_7_HLI" in names
    assert "SET_0_HLI" in names
    assert "SET_1_HLI" in names
    assert "SET_2_HLI" in names
    assert "SET_3_HLI" in names
    assert "SET_4_HLI" in names
    assert "SET_5_HLI" in names
    assert "SET_6_HLI" in names
    assert "SET_7_HLI" in names
    assert "RES_0_HLI" in names
    assert "RES_1_HLI" in names
    assert "RES_2_HLI" in names
    assert "RES_3_HLI" in names
    assert "RES_4_HLI" in names
    assert "RES_5_HLI" in names
    assert "RES_6_HLI" in names
    assert "RES_7_HLI" in names
    assert "DJNZ_D" in names
    assert "JR_Z_D" in names
    assert "JR_NZ_D" in names
    assert "JR_C_D" in names
    assert "JR_NC_D" in names
    assert "CALL_Z_NN" in names
    assert "CALL_NZ_NN" in names
    assert "CALL_C_NN" in names
    assert "CALL_NC_NN" in names
    assert "CALL_PO_NN" in names
    assert "CALL_PE_NN" in names
    assert "CALL_P_NN" in names
    assert "CALL_M_NN" in names
    assert "RET_Z" in names
    assert "RET_NZ" in names
    assert "RET_C" in names
    assert "RET_NC" in names
    assert "RET_PO" in names
    assert "RET_PE" in names
    assert "RET_P" in names
    assert "RET_M" in names
    assert "RETN" in names
    assert "RETI" in names
    assert "DI" in names
    assert "EI" in names
    assert "IM_0" in names
    assert "IM_1" in names
    assert "IM_2" in names
    assert "OUTI" in names
    assert "INDR" in names
    assert "OTDR" in names
    assert "RST_00" in names
    assert "RST_08" in names
    assert "RST_10" in names
    assert "RST_18" in names
    assert "RST_20" in names
    assert "RST_28" in names
    assert "RST_30" in names
    assert "RST_38" in names


def test_generate_z80_minimal():
    isa_path = BASE_DIR / "examples" / "z80.yaml"
    outdir = BASE_DIR / "generated" / "z80_basic"
    if outdir.exists():
        shutil.rmtree(outdir)

    gen_mod.generate(str(isa_path), str(outdir))

    src_dir = outdir / "src"
    assert (src_dir / "Z80.c").exists()
    assert (src_dir / "Z80.h").exists()
    assert (src_dir / "Z80_decoder.c").exists()


def test_z80_covers_expected_categories():
    isa_path = BASE_DIR / "examples" / "z80.yaml"
    data = yaml_loader.load_isa(str(isa_path))
    categories = {inst["category"] for inst in data["instructions"]}
    assert {"data_transfer", "arithmetic", "logic", "rotate", "bit", "control"} <= categories


def test_z80_opcode_space_audit_reports_prefixed_space_coverage():
    isa_path = BASE_DIR / "examples" / "z80.yaml"
    data = yaml_loader.load_isa(str(isa_path))
    audit = audit_opcode_spaces(data)

    assert set(audit.keys()) == {"base", "cb", "ed", "dd", "fd", "ddcb", "fdcb"}
    assert audit["base"]["missing"] == [0xDD, 0xED, 0xFD]
    assert audit["ddcb"]["covered"] == 256
    assert audit["fdcb"]["covered"] == 256
    assert audit["cb"]["covered"] > 0
    assert audit["ed"]["covered"] > 0


def test_z80_decode_determinism_contract_is_present():
    isa_path = BASE_DIR / "examples" / "z80.yaml"
    data = yaml_loader.load_isa(str(isa_path))
    _, decoder_impl = generate_decoder(data, "Z80")

    assert data["metadata"]["undefined_opcode_policy"] == "trap"
    assert "inst.length = (prefix != 0) ? 2 : 1;" in decoder_impl
    assert "inst.valid = false;" in decoder_impl
    assert "DD/FD fallback: treat unsupported prefixed forms as base aliases." in decoder_impl


@pytest.mark.skipif(
    (shutil.which("cc") is None and shutil.which("gcc") is None),
    reason="C compiler not available on PATH",
)
def test_z80_generated_decoder_covers_all_prefixed_opcode_spaces(tmp_path):
    isa_path = BASE_DIR / "examples" / "z80.yaml"
    outdir = tmp_path / "z80_decoder_scan"
    gen_mod.generate(str(isa_path), str(outdir))

    scan_c = outdir / "scan_decode.c"
    scan_c.write_text(
        textwrap.dedent(
            """
            #include <stdio.h>
            #include <stdint.h>
            #include "Z80_decoder.h"

            static int count_base(void) {
                int ok = 0;
                for (int op = 0; op < 256; op++) {
                    uint32_t raw = (uint32_t)op;
                    if (z80_decode(raw, 0, 0).valid) ok++;
                }
                return ok;
            }

            static int count_cb(void) {
                int ok = 0;
                for (int op = 0; op < 256; op++) {
                    uint32_t raw = 0xCBu | ((uint32_t)op << 8);
                    if (z80_decode(raw, 0, 0).valid) ok++;
                }
                return ok;
            }

            static int count_ed(void) {
                int ok = 0;
                for (int op = 0; op < 256; op++) {
                    uint32_t raw = 0xEDu | ((uint32_t)op << 8);
                    if (z80_decode(raw, 0, 0).valid) ok++;
                }
                return ok;
            }

            static int count_pref(uint8_t pref) {
                int ok = 0;
                for (int op = 0; op < 256; op++) {
                    uint32_t raw = (uint32_t)op;
                    if (z80_decode(raw, pref, 0).valid) ok++;
                }
                return ok;
            }

            static int count_ddcb(uint8_t pref) {
                int ok = 0;
                for (int op = 0; op < 256; op++) {
                    uint32_t raw = 0xCBu | ((uint32_t)op << 16);
                    if (z80_decode(raw, pref, 0).valid) ok++;
                }
                return ok;
            }

            int main(void) {
                printf("base=%d\\n", count_base());
                printf("cb=%d\\n", count_cb());
                printf("ed=%d\\n", count_ed());
                printf("dd=%d\\n", count_pref(0xDD));
                printf("fd=%d\\n", count_pref(0xFD));
                printf("ddcb=%d\\n", count_ddcb(0xDD));
                printf("fdcb=%d\\n", count_ddcb(0xFD));
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
            str(outdir / "src" / "Z80_decoder.c"),
            str(scan_c),
            "-o",
            str(binary),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    proc = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    lines = dict(line.split("=", 1) for line in proc.stdout.strip().splitlines())

    # DD/FD remain control bytes in base stream; ED now resolves via undocumented ED NOP path.
    assert int(lines["base"]) == 254
    assert int(lines["cb"]) == 256
    assert int(lines["ed"]) == 256
    assert int(lines["dd"]) == 256
    assert int(lines["fd"]) == 256
    assert int(lines["ddcb"]) == 256
    assert int(lines["fdcb"]) == 256

