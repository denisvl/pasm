from pathlib import Path

from src import generator as gen_mod


def test_nes_systems_use_split_ics():
    systems = (
        "examples/systems/nes/nes_default.yaml",
        "examples/systems/nes/nes_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "- nes_cpu_bus" in s
        assert "- nes_controller_ports" in s
        assert "- nes_apu" in s
        assert "- nes_ppu_regs" in s
        assert "- nes_cpu_ram" in s
        assert "- nes_io_ports" in s
        assert "- nes_cart_bridge" in s


def test_nes_runners_load_split_ics():
    sh = Path("scripts/run_nes_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_CTRL="examples/ics/nes/nes_controller_ports.yaml"' in sh
    assert 'IC_BUS="examples/ics/nes/nes_cpu_bus.yaml"' in sh
    assert 'IC_APU="examples/ics/nes/nes_apu.yaml"' in sh
    assert 'IC_PPU_REGS="examples/ics/nes/nes_ppu_regs.yaml"' in sh
    assert 'IC_CPU_RAM="examples/ics/nes/nes_cpu_ram.yaml"' in sh
    assert 'IC_IO_PORTS="examples/ics/nes/nes_io_ports.yaml"' in sh
    assert 'IC_CART_BRIDGE="examples/ics/nes/nes_cart_bridge.yaml"' in sh
    assert '--ic "${IC_CTRL}"' in sh
    assert '--ic "${IC_BUS}"' in sh
    assert '--ic "${IC_APU}"' in sh
    assert '--ic "${IC_PPU_REGS}"' in sh
    assert '--ic "${IC_CPU_RAM}"' in sh
    assert '--ic "${IC_IO_PORTS}"' in sh
    assert '--ic "${IC_CART_BRIDGE}"' in sh

    sh_i = Path("scripts/run_nes_interactive.sh").read_text(encoding="utf-8")
    assert 'IC_CTRL="examples/ics/nes/nes_controller_ports.yaml"' in sh_i
    assert 'IC_BUS="examples/ics/nes/nes_cpu_bus.yaml"' in sh_i
    assert 'IC_APU="examples/ics/nes/nes_apu.yaml"' in sh_i
    assert 'IC_PPU_REGS="examples/ics/nes/nes_ppu_regs.yaml"' in sh_i
    assert 'IC_CPU_RAM="examples/ics/nes/nes_cpu_ram.yaml"' in sh_i
    assert 'IC_IO_PORTS="examples/ics/nes/nes_io_ports.yaml"' in sh_i
    assert 'IC_CART_BRIDGE="examples/ics/nes/nes_cart_bridge.yaml"' in sh_i
    assert '--ic "${IC_CTRL}"' in sh_i
    assert '--ic "${IC_BUS}"' in sh_i
    assert '--ic "${IC_APU}"' in sh_i
    assert '--ic "${IC_PPU_REGS}"' in sh_i
    assert '--ic "${IC_CPU_RAM}"' in sh_i
    assert '--ic "${IC_IO_PORTS}"' in sh_i
    assert '--ic "${IC_CART_BRIDGE}"' in sh_i

    bat = Path("scripts/run_nes_debugger.bat").read_text(encoding="utf-8")
    assert 'set "IC_CTRL=examples/ics/nes/nes_controller_ports.yaml"' in bat
    assert 'set "IC_BUS=examples/ics/nes/nes_cpu_bus.yaml"' in bat
    assert 'set "IC_APU=examples/ics/nes/nes_apu.yaml"' in bat
    assert 'set "IC_PPU_REGS=examples/ics/nes/nes_ppu_regs.yaml"' in bat
    assert 'set "IC_CPU_RAM=examples/ics/nes/nes_cpu_ram.yaml"' in bat
    assert 'set "IC_IO_PORTS=examples/ics/nes/nes_io_ports.yaml"' in bat
    assert 'set "IC_CART_BRIDGE=examples/ics/nes/nes_cart_bridge.yaml"' in bat


def test_nes_split_generation_smoke_default_and_interactive(tmp_path):
    base = Path(__file__).resolve().parents[1]
    processor = base / "examples" / "processors" / "ricoh2a03.yaml"
    ic_paths = [
        base / "examples" / "ics" / "nes" / "nes_cpu_bus.yaml",
        base / "examples" / "ics" / "nes" / "nes_controller_ports.yaml",
        base / "examples" / "ics" / "nes" / "nes_apu.yaml",
        base / "examples" / "ics" / "nes" / "nes_ppu_regs.yaml",
        base / "examples" / "ics" / "nes" / "nes_cpu_ram.yaml",
        base / "examples" / "ics" / "nes" / "nes_io_ports.yaml",
        base / "examples" / "ics" / "nes" / "nes_cart_bridge.yaml",
    ]
    device_paths = [
        base / "examples" / "devices" / "nes" / "nes_controller.yaml",
        base / "examples" / "devices" / "nes" / "nes_video.yaml",
        base / "examples" / "devices" / "nes" / "nes_speaker.yaml",
    ]
    host_stub = [base / "examples" / "hosts" / "nes" / "nes_host_stub.yaml"]
    cart_map = base / "examples" / "cartridges" / "nes" / "nes_mapper_auto.yaml"
    cart_rom = base / "examples" / "roms" / "nes" / "Super Mario Bros. + Duck Hunt (USA).nes"

    default_out = tmp_path / "nes_default_split"
    interactive_out = tmp_path / "nes_interactive_split"

    gen_mod.generate(
        str(processor),
        str(base / "examples" / "systems" / "nes" / "nes_default.yaml"),
        str(default_out),
        ic_paths=[str(p) for p in ic_paths],
        device_paths=[str(p) for p in device_paths],
        host_paths=[str(p) for p in host_stub],
        cartridge_map_path=str(cart_map),
        cartridge_rom_path=str(cart_rom),
    )
    gen_mod.generate(
        str(processor),
        str(base / "examples" / "systems" / "nes" / "nes_interactive.yaml"),
        str(interactive_out),
        ic_paths=[str(p) for p in ic_paths],
        device_paths=[str(p) for p in device_paths],
        host_paths=[str(base / "examples" / "hosts" / "nes" / "nes_host_hal_interactive.yaml")],
        cartridge_map_path=str(cart_map),
        cartridge_rom_path=str(cart_rom),
    )

    assert (default_out / "src" / "MOS6502_core.c").exists()
    assert (interactive_out / "src" / "MOS6502_core.c").exists()
