import pathlib
import shutil
import subprocess

import pytest

from src import generator as gen_mod
from src.parser import yaml_loader
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _msx_paths():
    processor_path, system_path = example_pair("z80", system="z80_msx1_default.yaml")
    ic_paths = [
        BASE_DIR / "examples" / "ics" / "msx1_vdp_tms9918a.yaml",
        BASE_DIR / "examples" / "ics" / "msx1_ppi_8255.yaml",
        BASE_DIR / "examples" / "ics" / "msx1_psg_ay8910.yaml",
    ]
    device_paths = [
        BASE_DIR / "examples" / "devices" / "msx_keyboard.yaml",
        BASE_DIR / "examples" / "devices" / "msx_video.yaml",
        BASE_DIR / "examples" / "devices" / "msx_speaker.yaml",
    ]
    host_paths = [
        BASE_DIR / "examples" / "hosts" / "msx_host_stub.yaml",
    ]
    return processor_path, system_path, ic_paths, device_paths, host_paths


def _msx_interactive_paths():
    processor_path, _ = example_pair("z80", system="z80_msx1_default.yaml")
    system_path = BASE_DIR / "examples" / "systems" / "z80_msx1_interactive.yaml"
    ic_paths = [
        BASE_DIR / "examples" / "ics" / "msx1_vdp_tms9918a.yaml",
        BASE_DIR / "examples" / "ics" / "msx1_ppi_8255.yaml",
        BASE_DIR / "examples" / "ics" / "msx1_psg_ay8910.yaml",
    ]
    device_paths = [
        BASE_DIR / "examples" / "devices" / "msx_keyboard.yaml",
        BASE_DIR / "examples" / "devices" / "msx_video.yaml",
        BASE_DIR / "examples" / "devices" / "msx_speaker.yaml",
    ]
    host_paths = [
        BASE_DIR / "examples" / "hosts" / "msx_host_sdl2_interactive.yaml",
    ]
    return processor_path, system_path, ic_paths, device_paths, host_paths


def test_msx1_component_graph_validates():
    processor_path, system_path, ic_paths, device_paths, host_paths = _msx_paths()
    data = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        [str(path) for path in ic_paths],
        [str(path) for path in device_paths],
        [str(path) for path in host_paths],
    )
    assert data["system"]["metadata"]["name"] == "Z80MSX1DefaultSystem"
    assert [ic["metadata"]["id"] for ic in data["ics"]] == ["vdp0", "ppi0", "psg0"]
    assert [dev["metadata"]["id"] for dev in data["devices"]] == [
        "keyboard_msx",
        "video_msx",
        "speaker_msx",
    ]
    assert [host["metadata"]["id"] for host in data["hosts"]] == ["host_msx"]


def test_msx1_interactive_component_graph_validates():
    processor_path, system_path, ic_paths, device_paths, host_paths = _msx_interactive_paths()
    data = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        [str(path) for path in ic_paths],
        [str(path) for path in device_paths],
        [str(path) for path in host_paths],
    )
    assert data["system"]["metadata"]["name"] == "Z80MSX1InteractiveSystem"
    assert [host["metadata"]["id"] for host in data["hosts"]] == ["host_msx_sdl2"]


def test_msx1_ppi_keyboard_row_decode_and_bsr_generation(tmp_path):
    processor_path, system_path, ic_paths, device_paths, host_paths = _msx_interactive_paths()
    outdir = tmp_path / "msx1_interactive_build"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        ic_paths=[str(path) for path in ic_paths],
        device_paths=[str(path) for path in device_paths],
        host_paths=[str(path) for path in host_paths],
    )
    c_src = (outdir / "src" / "Z80.c").read_text(encoding="utf-8")
    assert "comp->port_c" in c_src
    assert "if ((value & 0x80u) != 0u)" in c_src
    assert "uint8_t bit = (uint8_t)((value >> 1) & 0x07u);" in c_src
    assert "uint8_t lo = (uint8_t)(comp->port_c & 0x0Fu);" in c_src
    assert "uint8_t hi = (uint8_t)((comp->port_c >> 4) & 0x0Fu);" in c_src
    assert "value = comp->port_c;" in c_src
    assert "uint8_t value = (port < cpu->port_size) ? cpu->port_memory[port] : 0xFF;" in c_src
    assert "SDL_SCANCODE_LEFT" in c_src
    assert "SDL_SCANCODE_RIGHT" in c_src
    assert "SDL_SCANCODE_RETURN" in c_src
    assert "cpu->interrupt_vector = 0xFFu;" in c_src
    assert "cpu->interrupt_pending = true;" in c_src


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_msx1_generate_and_compile_smoke(tmp_path):
    processor_path, system_path, ic_paths, device_paths, host_paths = _msx_paths()
    outdir = tmp_path / "msx1_build"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        ic_paths=[str(path) for path in ic_paths],
        device_paths=[str(path) for path in device_paths],
        host_paths=[str(path) for path in host_paths],
    )

    build_dir = outdir / "build"
    subprocess.check_call(
        ["cmake", "-S", str(outdir), "-B", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    subprocess.check_call(
        ["cmake", "--build", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
