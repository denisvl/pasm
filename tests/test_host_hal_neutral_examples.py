from pathlib import Path
import re


BASE_DIR = Path(__file__).resolve().parents[1]


def test_example_sdl2_hosts_use_hal_aliases_not_direct_sdl_symbols():
    offenders = []
    pattern = re.compile(r"\bSDL_[A-Z0-9_]+\b")

    for path in (BASE_DIR / "examples" / "hosts").rglob("*sdl2*.yaml"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(BASE_DIR)))

    assert not offenders, (
        "SDL2 host examples should use HAL aliases/wrappers instead of direct SDL_* symbols:\n"
        + "\n".join(offenders)
    )


def test_example_sdl2_hosts_do_not_use_raw_sdl_key_or_mod_constants():
    offenders = []
    pattern = re.compile(r"\b(SDLK_|KMOD_)[A-Z0-9_]+\b")

    for path in (BASE_DIR / "examples" / "hosts").rglob("*sdl2*.yaml"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(BASE_DIR)))

    assert not offenders, (
        "SDL2 host examples should use backend-neutral key/mod aliases instead of SDLK_/KMOD_ constants:\n"
        + "\n".join(offenders)
    )


def test_example_sdl2_hosts_do_not_require_sdl2_header_or_link_entries():
    offenders = []
    header_pat = re.compile(r"\bSDL2/SDL\.h\b")
    lib_pat = re.compile(r'^\s*-\s*name:\s*"SDL2"\s*$', re.MULTILINE)

    for path in (BASE_DIR / "examples" / "hosts").rglob("*sdl2*.yaml"):
        text = path.read_text(encoding="utf-8")
        if header_pat.search(text) or lib_pat.search(text):
            offenders.append(str(path.relative_to(BASE_DIR)))

    assert not offenders, (
        "SDL2 host examples should rely on backend.target-driven include/link setup, not explicit SDL2 coding entries:\n"
        + "\n".join(offenders)
    )


def test_example_sdl2_hosts_do_not_use_raw_audio_format_constants():
    offenders = []
    pattern = re.compile(r"\bAUDIO_[A-Z0-9_]+\b")

    for path in (BASE_DIR / "examples" / "hosts").rglob("*sdl2*.yaml"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(BASE_DIR)))

    assert not offenders, (
        "SDL2 host examples should use backend-neutral audio format aliases instead of AUDIO_* constants:\n"
        + "\n".join(offenders)
    )


def test_example_sdl2_hosts_do_not_depend_on_raw_event_struct_layout():
    offenders = []
    patterns = [
        "ev.type",
        "ev.key.repeat",
        "ev.key.keysym.scancode",
    ]

    for path in (BASE_DIR / "examples" / "hosts").rglob("*sdl2*.yaml"):
        text = path.read_text(encoding="utf-8")
        if any(token in text for token in patterns):
            offenders.append(str(path.relative_to(BASE_DIR)))

    assert not offenders, (
        "SDL2 host examples should use HAL event accessors instead of direct event struct fields:\n"
        + "\n".join(offenders)
    )
