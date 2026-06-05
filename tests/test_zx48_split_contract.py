from pathlib import Path

from src import generator as gen_mod


def test_zx48_systems_include_ram_split_ics():
    for rel in (
        "examples/systems/zx_spectrum48k/spectrum48k_default.yaml",
        "examples/systems/zx_spectrum48k/spectrum48k_interactive.yaml",
    ):
        s = Path(rel).read_text(encoding="utf-8")
        assert "- ula0" in s
        assert "- zx48_loram" in s
        assert "- zx48_hiram" in s


def test_zx48_runners_load_ram_split_ics_and_controller():
    sh = Path("scripts/run_zx48_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_LORAM="examples/ics/zx_spectrum48k/zx_spectrum_48k_loram.yaml"' in sh
    assert 'IC_HIRAM="examples/ics/zx_spectrum48k/zx_spectrum_48k_hiram.yaml"' in sh
    assert '--ic "${IC_LORAM}"' in sh
    assert '--ic "${IC_HIRAM}"' in sh

    bat = Path("scripts/run_zx48_debugger.bat").read_text(encoding="utf-8")
    assert 'set "IC_LORAM=examples/ics/zx_spectrum48k/zx_spectrum_48k_loram.yaml"' in bat
    assert 'set "IC_HIRAM=examples/ics/zx_spectrum48k/zx_spectrum_48k_hiram.yaml"' in bat
    assert '--ic "%IC_LORAM%"' in bat
    assert '--ic "%IC_HIRAM%"' in bat
    assert 'set "DEVICE_CTRL=examples/devices/zx_spectrum48k/zx48_controller.yaml"' in bat
    assert '--device "%DEVICE_CTRL%"' in bat


def test_zx48_ula_delegates_ram_access_to_split_ics():
    ula = Path("examples/ics/zx_spectrum48k/zx_spectrum_48k_ula.yaml").read_text(encoding="utf-8")
    assert '"zx48_loram", "ram_read"' in ula
    assert '"zx48_loram", "ram_write"' in ula
    assert '"zx48_hiram", "ram_read"' in ula
    assert '"zx48_hiram", "ram_write"' in ula
    # Split invariant: ULA no longer directly reads/writes RAM bytes in handlers.
    assert "cpu->memory[addr]" not in ula


def test_zx48_ram_ic_ranges_are_isolated():
    loram = Path("examples/ics/zx_spectrum48k/zx_spectrum_48k_loram.yaml").read_text(encoding="utf-8")
    hiram = Path("examples/ics/zx_spectrum48k/zx_spectrum_48k_hiram.yaml").read_text(encoding="utf-8")

    assert "addr < 0x4000u || addr >= 0x8000u" in loram
    assert "addr < 0x8000u" in hiram


def test_zx48_split_generation_smoke(tmp_path):
    base = Path(__file__).resolve().parents[1]
    processor = base / "examples" / "processors" / "z80.yaml"
    ic_paths = [
        base / "examples" / "ics" / "zx_spectrum48k" / "zx_spectrum_48k_ula.yaml",
        base / "examples" / "ics" / "zx_spectrum48k" / "zx_spectrum_48k_loram.yaml",
        base / "examples" / "ics" / "zx_spectrum48k" / "zx_spectrum_48k_hiram.yaml",
    ]
    device_paths = [
        base / "examples" / "devices" / "zx_spectrum48k" / "zx48_keyboard.yaml",
        base / "examples" / "devices" / "zx_spectrum48k" / "zx48_controller.yaml",
        base / "examples" / "devices" / "zx_spectrum48k" / "zx48_video.yaml",
        base / "examples" / "devices" / "zx_spectrum48k" / "zx48_beeper.yaml",
        base / "examples" / "devices" / "zx_spectrum48k" / "zx48_mic.yaml",
    ]
    systems = (
        (
            base / "examples" / "systems" / "zx_spectrum48k" / "spectrum48k_default.yaml",
            [base / "examples" / "hosts" / "zx_spectrum48k" / "zx48_host_hal.yaml"],
            tmp_path / "zx48_default_split",
        ),
        (
            base / "examples" / "systems" / "zx_spectrum48k" / "spectrum48k_interactive.yaml",
            [base / "examples" / "hosts" / "zx_spectrum48k" / "zx48_host_hal_interactive.yaml"],
            tmp_path / "zx48_interactive_split",
        ),
    )
    for system, host_paths, out_dir in systems:
        gen_mod.generate(
            str(processor),
            str(system),
            str(out_dir),
            ic_paths=[str(p) for p in ic_paths],
            device_paths=[str(p) for p in device_paths],
            host_paths=[str(p) for p in host_paths],
        )
        assert (out_dir / "src" / "Z80_core.c").exists()
