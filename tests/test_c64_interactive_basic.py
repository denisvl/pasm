import pathlib
import uuid

from src import generator as gen_mod
from src.parser import yaml_loader


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _make_workdir(prefix: str) -> pathlib.Path:
    root = BASE_DIR / ".tmp_test_work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


def _c64_interactive_paths():
    processor_path = BASE_DIR / "examples" / "processors" / "mos6510.yaml"
    system_path = BASE_DIR / "examples" / "systems" / "c64_interactive.yaml"
    ic_paths = [
        BASE_DIR / "examples" / "ics" / "c64_io.yaml",
    ]
    device_paths = [
        BASE_DIR / "examples" / "devices" / "c64_keyboard.yaml",
        BASE_DIR / "examples" / "devices" / "c64_video.yaml",
        BASE_DIR / "examples" / "devices" / "c64_speaker.yaml",
    ]
    host_paths = [
        BASE_DIR / "examples" / "hosts" / "c64_host_sdl2_interactive.yaml",
    ]
    return processor_path, system_path, ic_paths, device_paths, host_paths


def test_c64_interactive_component_graph_validates():
    processor_path, system_path, ic_paths, device_paths, host_paths = _c64_interactive_paths()
    data = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        [str(path) for path in ic_paths],
        [str(path) for path in device_paths],
        [str(path) for path in host_paths],
    )
    assert data["metadata"]["name"] == "MOS6510"
    assert data["system"]["metadata"]["name"] == "C64InteractiveSystem"
    assert [ic["metadata"]["id"] for ic in data["ics"]] == ["c64_io"]
    assert [dev["metadata"]["id"] for dev in data["devices"]] == [
        "keyboard_c64",
        "video_c64",
        "speaker_c64",
    ]
    assert [host["metadata"]["id"] for host in data["hosts"]] == ["host_c64_sdl2"]


def test_generate_c64_interactive_with_components():
    processor_path, system_path, ic_paths, device_paths, host_paths = _c64_interactive_paths()
    outdir = _make_workdir("c64_interactive_")

    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        ic_paths=[str(path) for path in ic_paths],
        device_paths=[str(path) for path in device_paths],
        host_paths=[str(path) for path in host_paths],
    )

    src_dir = outdir / "src"
    assert (src_dir / "MOS6510.c").exists()
    assert (src_dir / "MOS6510.h").exists()
    assert (src_dir / "MOS6510_decoder.c").exists()

    impl = (src_dir / "MOS6510.c").read_text(encoding="utf-8")
    assert "ComponentState_c64_io" in impl
    assert "mos6510_interrupt(cpu, 0u);" in impl
    assert "cpu_component_emit_signal(cpu, \"c64_io\", \"frame_ready\"" in impl
    assert "cpu_component_apply_declared_keymap(" in impl
    assert "SDL_SCANCODE_LSHIFT" in impl
