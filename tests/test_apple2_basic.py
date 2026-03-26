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


def test_apple2_system_validates_with_mos6502_processor():
    processor_path, _ = example_pair("mos6502")
    system_path = BASE_DIR / "examples" / "systems" / "apple2_default.yaml"
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))

    assert data["metadata"]["name"] == "MOS6502"
    assert data["system"]["metadata"]["name"] == "Apple2DefaultSystem"
    assert data["memory"]["default_size"] == 65536
    assert any(region["name"] == "ROM_SYSTEM" for region in data["memory"]["regions"])
    assert data["memory"]["rom_images"][0]["name"] == "apple2plus_rom"


def test_generate_apple2_with_mos6502():
    processor_path, _ = example_pair("mos6502")
    system_path = BASE_DIR / "examples" / "systems" / "apple2_default.yaml"
    outdir = _make_workdir("apple2_basic_")

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    src_dir = outdir / "src"
    assert (src_dir / "MOS6502.c").exists()
    assert (src_dir / "MOS6502.h").exists()
    assert (src_dir / "MOS6502_decoder.c").exists()
