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
    system_path = BASE_DIR / "examples" / "systems" / "c64_cartridge_interactive.yaml"
    ic_paths = [
        BASE_DIR / "examples" / "ics" / "c64" / "c64_pla_906114.yaml",
        BASE_DIR / "examples" / "ics" / "c64" / "c64_vic_ii_6569.yaml",
        BASE_DIR / "examples" / "ics" / "c64" / "c64_sid_6581.yaml",
        BASE_DIR / "examples" / "ics" / "c64" / "c64_cia1_6526.yaml",
        BASE_DIR / "examples" / "ics" / "c64" / "c64_cia2_6526.yaml",
        BASE_DIR / "examples" / "ics" / "c64" / "c64_color_ram_2114.yaml",
        BASE_DIR / "examples" / "ics" / "c64" / "c64_main_ram.yaml",
    ]
    device_paths = [
        BASE_DIR / "examples" / "devices" / "c64_keyboard.yaml",
        BASE_DIR / "examples" / "devices" / "c64_joystick.yaml",
        BASE_DIR / "examples" / "devices" / "c64_video.yaml",
        BASE_DIR / "examples" / "devices" / "c64_speaker.yaml",
    ]
    host_paths = [
        BASE_DIR / "examples" / "hosts" / "c64" / "c64_host_hal_interactive.yaml",
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
    assert [ic["metadata"]["id"] for ic in data["ics"]] == [
        "c64_pla",
        "c64_vic_ii",
        "c64_sid",
        "c64_cia1",
        "c64_cia2",
        "c64_color_ram",
        "c64_main_ram",
    ]
    assert [dev["metadata"]["id"] for dev in data["devices"]] == [
        "keyboard_c64",
        "joystick_c64",
        "video_c64",
        "speaker",
        "tv",
    ]
    assert [host["metadata"]["id"] for host in data["hosts"]] == ["host_c64"]


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
    assert (src_dir / "MOS6510_core.c").exists()
    assert (src_dir / "MOS6510.h").exists()
    assert (src_dir / "MOS6510_decoder.c").exists()

    cpu_h = (src_dir / "MOS6510.h").read_text(encoding="utf-8")
    pla_impl = (src_dir / "c64_ic_c64_pla.c").read_text(encoding="utf-8")

    assert "ComponentState_c64_pla" in cpu_h
    assert "ComponentState_c64_main_ram" in cpu_h
    assert "cpu_component_emit_signal(cpu, \"c64_pla\", \"frame_ready\"" in pla_impl
