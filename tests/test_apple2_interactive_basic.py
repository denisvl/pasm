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


def _apple2_interactive_paths():
    processor_path, _ = example_pair("mos6502")
    system_path = BASE_DIR / "examples" / "systems" / "apple2" / "apple2_interactive.yaml"
    ic_paths = [
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_keyboard_encoder_ay_5_3600.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_gameio_ne558.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_video_softswitches.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_speaker_toggle.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_char_generator_rom.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_slot_decoder_ttl.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_main_ram.yaml",
    ]
    device_paths = [
        BASE_DIR / "examples" / "devices" / "apple2" / "apple2_keyboard.yaml",
        BASE_DIR / "examples" / "devices" / "apple2" / "apple2_gameport.yaml",
        BASE_DIR / "examples" / "devices" / "apple2" / "apple2_video.yaml",
        BASE_DIR / "examples" / "devices" / "apple2" / "apple2_speaker.yaml",
    ]
    host_paths = [
        BASE_DIR / "examples" / "hosts" / "apple2" / "apple2_host_hal_interactive.yaml",
    ]
    return processor_path, system_path, ic_paths, device_paths, host_paths


def test_apple2_interactive_component_graph_validates():
    processor_path, system_path, ic_paths, device_paths, host_paths = _apple2_interactive_paths()
    data = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        [str(path) for path in ic_paths],
        [str(path) for path in device_paths],
        [str(path) for path in host_paths],
    )
    assert data["metadata"]["name"] == "MOS6502"
    assert data["system"]["metadata"]["name"] == "Apple2InteractiveSystem"
    assert [ic["metadata"]["id"] for ic in data["ics"]] == [
        "apple2_keyboard_encoder",
        "apple2_gameio",
        "apple2_video_softswitches",
        "apple2_speaker_toggle",
        "apple2_char_rom",
        "apple2_slot_decoder",
        "apple2_main_ram",
    ]
    assert [dev["metadata"]["id"] for dev in data["devices"]] == [
        "keyboard_apple2",
        "gameport_apple2",
        "video_apple2",
        "speaker_apple2",
    ]
    assert [host["metadata"]["id"] for host in data["hosts"]] == ["host_apple2"]


def test_generate_apple2_interactive_with_components():
    processor_path, system_path, ic_paths, device_paths, host_paths = _apple2_interactive_paths()
    outdir = _make_workdir("apple2_interactive_")

    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        ic_paths=[str(path) for path in ic_paths],
        device_paths=[str(path) for path in device_paths],
        host_paths=[str(path) for path in host_paths],
    )

    src_dir = outdir / "src"
    assert (src_dir / "MOS6502_core.c").exists()
    assert (src_dir / "MOS6502.h").exists()
    assert (src_dir / "MOS6502_decoder.c").exists()
    impl = (src_dir / "MOS6502_core.c").read_text(encoding="utf-8")
    system_glue = (src_dir / "apple2_system_glue.c").read_text(encoding="utf-8")
    all_src = "\n".join(p.read_text(encoding="utf-8") for p in sorted(src_dir.glob("*.[ch]")))
    assert "0xC050u" in all_src and "0xC057u" in all_src
    assert "apple2_glyph" in system_glue
    assert "A2_HIRES_ADDR" in system_glue
    assert "cpu_host_hal_event_key_repeat(&ev) == 0" in all_src
    assert "CPU_HOST_MOD_SHIFT" in all_src
    assert "CPU_HOST_MOD_CTRL" in all_src
    assert "CPU_HOST_SCANCODE(A)" in all_src
    assert "CPU_HOST_SCANCODE(Z)" in all_src
    assert 'snprintf(rendered, sizeof(rendered), "LDA #%s"' in all_src
    assert "ch + (uint8_t)(x + y + comp->frame_count)" not in impl
