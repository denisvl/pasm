from pathlib import Path

from src import generator as gen_mod


def test_sg1000_systems_use_split_ics():
    systems = (
        "examples/systems/sg1000/sg1000_default.yaml",
        "examples/systems/sg1000/sg1000_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "- sg_bus0" in s
        assert "- sg_ram0" in s
        assert "- sg_vdp0" in s
        assert "- sg_joy0" in s
        assert "- sg_psg0" in s


def test_sg1000_runner_loads_split_ics():
    sh = Path("scripts/run_sg1000_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_BUS="examples/ics/sg1000/sg1000_cpu_bus.yaml"' in sh
    assert 'IC_RAM="examples/ics/sg1000/sg1000_main_ram.yaml"' in sh
    assert 'IC_VDP="examples/ics/sg1000/sg1000_vdp_tms9918a.yaml"' in sh
    assert 'IC_JOY="examples/ics/sg1000/sg1000_joypad_io.yaml"' in sh
    assert 'IC_PSG="examples/ics/sg1000/sg1000_psg_sn76489.yaml"' in sh
    assert "--ic \"${IC_BUS}\"" in sh
    assert "--ic \"${IC_RAM}\"" in sh
    assert "--ic \"${IC_VDP}\"" in sh
    assert "--ic \"${IC_JOY}\"" in sh
    assert "--ic \"${IC_PSG}\"" in sh

    bat = Path("scripts/run_sg1000_debugger.bat").read_text(encoding="utf-8")
    assert "--ic examples/ics/sg1000/sg1000_cpu_bus.yaml" in bat
    assert "--ic examples/ics/sg1000/sg1000_main_ram.yaml" in bat
    assert "--ic examples/ics/sg1000/sg1000_vdp_tms9918a.yaml" in bat
    assert "--ic examples/ics/sg1000/sg1000_joypad_io.yaml" in bat
    assert "--ic examples/ics/sg1000/sg1000_psg_sn76489.yaml" in bat


def test_sg1000_split_generation_smoke_default_and_interactive(tmp_path):
    base = Path(__file__).resolve().parents[1]
    processor = base / "examples" / "processors" / "z80.yaml"
    ic_paths = [
        base / "examples" / "ics" / "sg1000" / "sg1000_cpu_bus.yaml",
        base / "examples" / "ics" / "sg1000" / "sg1000_main_ram.yaml",
        base / "examples" / "ics" / "sg1000" / "sg1000_vdp_tms9918a.yaml",
        base / "examples" / "ics" / "sg1000" / "sg1000_joypad_io.yaml",
        base / "examples" / "ics" / "sg1000" / "sg1000_psg_sn76489.yaml",
    ]
    device_paths = [
        base / "examples" / "devices" / "sms" / "sms_video.yaml",
        base / "examples" / "devices" / "sms" / "sms_speaker.yaml",
    ]
    host_stub = [base / "examples" / "hosts" / "sg1000" / "sg1000_host_stub.yaml"]
    cart_map = base / "examples" / "cartridges" / "sg1000" / "sg1000_mapper_none.yaml"
    cart_rom = base / "examples" / "roms" / "sg1000" / "Hang-On II (Japan).sg"

    default_out = tmp_path / "sg1000_default_split"
    interactive_out = tmp_path / "sg1000_interactive_split"

    gen_mod.generate(
        str(processor),
        str(base / "examples" / "systems" / "sg1000" / "sg1000_default.yaml"),
        str(default_out),
        ic_paths=[str(p) for p in ic_paths],
        device_paths=[str(p) for p in device_paths],
        host_paths=[str(p) for p in host_stub],
        cartridge_map_path=str(cart_map),
        cartridge_rom_path=str(cart_rom),
    )
    gen_mod.generate(
        str(processor),
        str(base / "examples" / "systems" / "sg1000" / "sg1000_interactive.yaml"),
        str(interactive_out),
        ic_paths=[str(p) for p in ic_paths],
        device_paths=[str(p) for p in device_paths],
        host_paths=[str(base / "examples" / "hosts" / "sg1000" / "sg1000_host_hal_interactive.yaml")],
        cartridge_map_path=str(cart_map),
        cartridge_rom_path=str(cart_rom),
    )

    assert (default_out / "src" / "Z80_core.c").exists()
    assert (interactive_out / "src" / "Z80_core.c").exists()
