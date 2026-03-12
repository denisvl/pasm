import pathlib
import shutil

from src import generator as gen_mod
from src.parser import yaml_loader


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def test_mos6502_yaml_validates():
    isa_path = BASE_DIR / "examples" / "mos6502.yaml"
    data = yaml_loader.load_isa(str(isa_path))
    assert data["metadata"]["name"] == "MOS6502"
    assert data["metadata"]["undefined_opcode_policy"] == "trap"
    assert data["memory"]["default_size"] == 65536
    names = {inst["name"] for inst in data["instructions"]}
    assert {"NOP", "LDA_IMM", "TAX", "INX", "JMP_ABS", "BRK"} <= names


def test_generate_mos6502():
    isa_path = BASE_DIR / "examples" / "mos6502.yaml"
    outdir = BASE_DIR / "generated" / "mos6502_basic"
    if outdir.exists():
        shutil.rmtree(outdir)

    gen_mod.generate(str(isa_path), str(outdir))

    src_dir = outdir / "src"
    assert (src_dir / "MOS6502.c").exists()
    assert (src_dir / "MOS6502.h").exists()
    assert (src_dir / "MOS6502_decoder.c").exists()
