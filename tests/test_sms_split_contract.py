from pathlib import Path

from src import generator as gen_mod


def test_sms_systems_use_split_ics():
    systems = (
        "examples/systems/sms/sms_default.yaml",
        "examples/systems/sms/sms_interactive.yaml",
        "examples/systems/sms/sms_bios_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "- sms_bus0" in s
        assert "- sms_ram0" in s
        assert "- sms_vdp0" in s
        assert "- sms_joy0" in s
        assert "- sms_psg0" in s


def test_sms_runners_load_split_ics():
    sh = Path("scripts/run_sms_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_BUS="examples/ics/sms/sms_cpu_bus.yaml"' in sh
    assert 'IC_RAM="examples/ics/sms/sms_main_ram.yaml"' in sh
    assert 'IC_VDP="examples/ics/sms/sms_vdp_sega315_5124.yaml"' in sh
    assert 'IC_JOY="examples/ics/sms/sms_joypad_io.yaml"' in sh
    assert 'IC_PSG="examples/ics/sms/sms_psg_sn76489.yaml"' in sh
    assert '--ic "${IC_BUS}"' in sh
    assert '--ic "${IC_RAM}"' in sh

    bat = Path("scripts/run_sms_debugger.bat").read_text(encoding="utf-8")
    assert 'set "IC_BUS=examples/ics/sms/sms_cpu_bus.yaml"' in bat
    assert 'set "IC_RAM=examples/ics/sms/sms_main_ram.yaml"' in bat
    assert 'set "IC_PSG=examples/ics/sms/sms_psg_sn76489.yaml"' in bat


def test_sms_split_generation_smoke(tmp_path):
    base = Path(__file__).resolve().parents[1]
    processor = base / "examples" / "processors" / "z80.yaml"
    system = base / "examples" / "systems" / "sms" / "sms_default.yaml"
    out_dir = tmp_path / "sms_default_split"
    ic_paths = [
        base / "examples" / "ics" / "sms" / "sms_cpu_bus.yaml",
        base / "examples" / "ics" / "sms" / "sms_main_ram.yaml",
        base / "examples" / "ics" / "sms" / "sms_vdp_sega315_5124.yaml",
        base / "examples" / "ics" / "sms" / "sms_joypad_io.yaml",
        base / "examples" / "ics" / "sms" / "sms_psg_sn76489.yaml",
    ]
    device_paths = [
        base / "examples" / "devices" / "sms" / "sms_controller.yaml",
        base / "examples" / "devices" / "sms" / "sms_video.yaml",
        base / "examples" / "devices" / "sms" / "sms_speaker.yaml",
    ]
    host_paths = [base / "examples" / "hosts" / "sms" / "sms_host_stub.yaml"]
    cart_map = base / "examples" / "cartridges" / "sms" / "sms_mapper_sega.yaml"
    cart_rom = base / "examples" / "roms" / "sms" / "sega.rom"

    gen_mod.generate(
        str(processor),
        str(system),
        str(out_dir),
        ic_paths=[str(p) for p in ic_paths],
        device_paths=[str(p) for p in device_paths],
        host_paths=[str(p) for p in host_paths],
        cartridge_map_path=str(cart_map),
        cartridge_rom_path=str(cart_rom),
    )

    assert (out_dir / "src" / "Z80_core.c").exists()
