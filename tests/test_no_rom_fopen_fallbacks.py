from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


def test_examples_yaml_do_not_hardcode_rom_fopen_paths():
    offenders = []
    for path in (BASE_DIR / "examples").rglob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        if 'fopen("examples/roms/' in text:
            offenders.append(str(path.relative_to(BASE_DIR)))

    assert not offenders, (
        "Hardcoded ROM fopen path found in YAML behavior; use system/cartridge "
        "ROM loading via runtime CLI instead:\n" + "\n".join(offenders)
    )
