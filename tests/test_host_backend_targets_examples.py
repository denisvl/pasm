from pathlib import Path

import yaml


BASE_DIR = Path(__file__).resolve().parents[1]


def test_example_hosts_define_explicit_backend_target():
    offenders = []
    for path in (BASE_DIR / "examples" / "hosts").rglob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        backend = data.get("backend")
        target = backend.get("target") if isinstance(backend, dict) else None
        if not isinstance(target, str) or not target.strip():
            offenders.append(str(path.relative_to(BASE_DIR)))

    assert not offenders, (
        "Every example host YAML must define backend.target explicitly:\n"
        + "\n".join(offenders)
    )


def test_example_hosts_do_not_use_legacy_sdl_keyboard_fields():
    offenders = []
    for path in (BASE_DIR / "examples" / "hosts").rglob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        if "source: sdl_scancode" in text or "host_key: SDL_SCANCODE_" in text:
            offenders.append(str(path.relative_to(BASE_DIR)))

    assert not offenders, (
        "Example host YAML must use canonical host_key mappings (no legacy SDL keyboard fields):\n"
        + "\n".join(offenders)
    )
