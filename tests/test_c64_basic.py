import pathlib
import uuid

from src import generator as gen_mod
from src.parser import yaml_loader


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _make_workdir(prefix: str) -> pathlib.Path:
    root = BASE_DIR / "generated" / "_pytest_work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


def test_c64_system_validates_with_mos6510_processor():
    processor_path = BASE_DIR / "examples" / "processors" / "mos6510.yaml"
    system_path = BASE_DIR / "examples" / "systems" / "c64_default.yaml"
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))

    assert data["metadata"]["name"] == "MOS6510"
    assert data["system"]["metadata"]["name"] == "C64DefaultSystem"
    assert data["memory"]["default_size"] == 65536

    regions = {region["name"] for region in data["memory"]["regions"]}
    assert {"ROM_BASIC", "ROM_CHAR", "ROM_KERNAL"} <= regions

    rom_names = {image["name"] for image in data["memory"]["rom_images"]}
    assert {"c64_basic_rom", "c64_char_rom", "c64_kernal_rom"} <= rom_names


def test_generate_c64_with_mos6510():
    processor_path = BASE_DIR / "examples" / "processors" / "mos6510.yaml"
    system_path = BASE_DIR / "examples" / "systems" / "c64_default.yaml"
    outdir = _make_workdir("c64_basic_")

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    src_dir = outdir / "src"
    assert (src_dir / "MOS6510.c").exists()
    assert (src_dir / "MOS6510.h").exists()
    assert (src_dir / "MOS6510_decoder.c").exists()

    impl = (src_dir / "MOS6510.c").read_text(encoding="utf-8")
    assert "ROM_BASIC" in impl
    assert "ROM_CHAR" in impl
    assert "ROM_KERNAL" in impl
