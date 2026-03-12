import pathlib

from src import generator as gen_mod
from src.parser import yaml_loader
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def test_mos6502_yaml_validates():
    processor_path, system_path = example_pair("mos6502")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))
    assert data["metadata"]["name"] == "MOS6502"
    assert data["metadata"]["undefined_opcode_policy"] == "trap"
    assert data["memory"]["default_size"] == 65536
    names = {inst["name"] for inst in data["instructions"]}
    assert {"NOP", "LDA_IMM", "TAX", "INX", "JMP_ABS", "BRK"} <= names


def test_generate_mos6502(tmp_path):
    processor_path, system_path = example_pair("mos6502")
    outdir = tmp_path / "mos6502_basic"

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    src_dir = outdir / "src"
    assert (src_dir / "MOS6502.c").exists()
    assert (src_dir / "MOS6502.h").exists()
    assert (src_dir / "MOS6502_decoder.c").exists()
