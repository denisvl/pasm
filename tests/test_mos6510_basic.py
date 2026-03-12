import pathlib
import shutil

from src import generator as gen_mod
from src.parser import yaml_loader


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def test_mos6510_yaml_validates():
    isa_path = BASE_DIR / "examples" / "mos6510.yaml"
    data = yaml_loader.load_isa(str(isa_path))
    assert data["metadata"]["name"] == "MOS6510"
    assert data["metadata"]["undefined_opcode_policy"] == "trap"
    assert data["memory"]["default_size"] == 65536
    reg_names = {reg["name"] for reg in data["registers"]}
    assert {"A", "X", "Y", "SP", "PC", "IO_DDR", "IO_DATA"} <= reg_names
    names = {inst["name"] for inst in data["instructions"]}
    assert {"NOP", "LDA_IMM", "LDA_ZP", "STA_ZP", "TAX", "INX", "JMP_ABS", "BRK"} <= names


def test_generate_mos6510():
    isa_path = BASE_DIR / "examples" / "mos6510.yaml"
    outdir = BASE_DIR / "generated" / "mos6510_basic"
    if outdir.exists():
        shutil.rmtree(outdir)

    gen_mod.generate(str(isa_path), str(outdir))

    src_dir = outdir / "src"
    assert (src_dir / "MOS6510.c").exists()
    assert (src_dir / "MOS6510.h").exists()
    assert (src_dir / "MOS6510_decoder.c").exists()
