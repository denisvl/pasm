import pathlib

from src.parser import yaml_loader
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _zx48_interactive_paths():
    processor_path, _ = example_pair("z80", system="spectrum48k_default.yaml")
    system_path = BASE_DIR / "examples" / "systems" / "zx_spectrum48k" / "spectrum48k_interactive.yaml"
    ic_paths = [
        BASE_DIR / "examples" / "ics" / "zx_spectrum48k" / "zx_spectrum_48k_ula.yaml",
        BASE_DIR / "examples" / "ics" / "zx_spectrum48k" / "zx_spectrum_48k_loram.yaml",
        BASE_DIR / "examples" / "ics" / "zx_spectrum48k" / "zx_spectrum_48k_hiram.yaml",
    ]
    device_paths = [
        BASE_DIR / "examples" / "devices" / "zx_spectrum48k" / "zx48_keyboard.yaml",
        BASE_DIR / "examples" / "devices" / "zx_spectrum48k" / "zx48_controller.yaml",
        BASE_DIR / "examples" / "devices" / "zx_spectrum48k" / "zx48_video.yaml",
        BASE_DIR / "examples" / "devices" / "zx_spectrum48k" / "zx48_beeper.yaml",
        BASE_DIR / "examples" / "devices" / "zx_spectrum48k" / "zx48_mic.yaml",
    ]
    host_paths = [
        BASE_DIR / "examples" / "hosts" / "zx_spectrum48k" / "zx48_host_hal_interactive.yaml",
    ]
    return processor_path, system_path, ic_paths, device_paths, host_paths


def test_zx48_interactive_cassette_sources_include_tap_and_tzx():
    processor_path, system_path, ic_paths, device_paths, host_paths = _zx48_interactive_paths()
    data = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        [str(path) for path in ic_paths],
        [str(path) for path in device_paths],
        [str(path) for path in host_paths],
    )
    assert data["cassette"]["allowed_extensions"] == ["yaml", "wav", "tap", "tzx"]
    assert [src["source_component"] for src in data["cassette"]["sources"]] == [
        "cassette_line_in_source",
        "cassette_wav_source",
        "cassette_zx_tap_source",
        "cassette_cdt_source",
    ]
    assert "cassette_zx_tap_source" in [dev["metadata"]["id"] for dev in data["devices"]]
    assert "cassette_cdt_source" in [dev["metadata"]["id"] for dev in data["devices"]]
