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


def test_mos6509_yaml_validates():
    processor_path, system_path = example_pair("mos6509")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))
    assert data["metadata"]["name"] == "MOS6509"
    assert data["memory"]["default_size"] == 1048576
    reg_names = {reg["name"] for reg in data["registers"]}
    assert {"A", "X", "Y", "SP", "PC", "BANK_EXEC", "BANK_INDIR"} <= reg_names
    opcode_by_name = {
        inst["name"]: int(inst["encoding"]["opcode"]) for inst in data["instructions"]
    }
    assert opcode_by_name["LDA_INDY"] == 0xB1
    assert opcode_by_name["STA_INDY"] == 0x91


def test_generate_mos6509():
    processor_path, system_path = example_pair("mos6509")
    outdir = _make_workdir("mos6509_basic_")
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))
    src_dir = outdir / "src"
    assert (src_dir / "MOS6509.c").exists()
    assert (src_dir / "MOS6509.h").exists()
    assert (src_dir / "MOS6509_decoder.c").exists()

