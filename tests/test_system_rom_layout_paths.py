from pathlib import Path

import yaml


BASE_DIR = Path(__file__).resolve().parents[1]


def test_system_rom_images_use_per_system_rom_subfolders():
    offenders = []
    systems_root = BASE_DIR / "examples" / "systems"

    for path in systems_root.rglob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        memory = data.get("memory")
        if not isinstance(memory, dict):
            continue
        rom_images = memory.get("rom_images")
        if not isinstance(rom_images, list):
            continue

        for idx, entry in enumerate(rom_images):
            if not isinstance(entry, dict):
                continue
            rom_file = entry.get("file")
            if not isinstance(rom_file, str):
                continue
            rom_file = rom_file.strip()
            if not rom_file:
                continue

            # System manifests live under examples/systems/<system>/...
            # and must point to examples/roms/<system>/...
            if not rom_file.startswith("../../roms/"):
                offenders.append(
                    f"{path.relative_to(BASE_DIR)} rom_images[{idx}].file='{rom_file}' "
                    "must start with '../../roms/'"
                )
                continue

            rest = rom_file[len("../../roms/") :]
            if "/" not in rest:
                offenders.append(
                    f"{path.relative_to(BASE_DIR)} rom_images[{idx}].file='{rom_file}' "
                    "must include a system subfolder under examples/roms/"
                )

    assert not offenders, (
        "System ROM paths must use per-system rom subfolders:\n" + "\n".join(offenders)
    )
