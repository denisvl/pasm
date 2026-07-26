from pathlib import Path

from src import generator as gen_mod


def test_trs80_model4_systems_include_main_ram_split_ic():
    systems = (
        "examples/systems/trs80_model4/trs80_model4_default.yaml",
        "examples/systems/trs80_model4/trs80_model4_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "- trs80_m4io" in s
        assert "- trs80_m4ga" in s
        assert "- trs80_m4ram" in s
        assert "- wd1793_fdc" in s
        assert "- trs80_m4ppi" in s
        assert "- trs80_m4sio" in s
        assert "- trs80_m4video" in s
        assert "- trs80_m4irq" in s
        assert "- trs80_m4cass" in s


def test_trs80_model4_runners_load_main_ram_ic():
    sh = Path("scripts/run_trs80_model4_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_MAIN_RAM="examples/ics/trs80_model4/trs80_model4_main_ram.yaml"' in sh
    assert '--ic "${IC_MAIN_RAM}"' in sh
    assert 'IC_GA="examples/ics/trs80_model4/trs80_model4_gate_array.yaml"' in sh
    assert '--ic "${IC_GA}"' in sh
    assert 'IC_FDC="examples/ics/common/wd1793.yaml"' in sh
    assert '--ic "${IC_FDC}"' in sh
    assert 'DEVICE_FLOPPY_BACKEND="examples/devices/common/trs80_floppy_image_backend.yaml"' in sh
    assert '--device "${DEVICE_FLOPPY_BACKEND}"' in sh
    assert 'IC_PPI="examples/ics/trs80_model4/trs80_model4_ppi.yaml"' in sh
    assert '--ic "${IC_PPI}"' in sh
    assert 'IC_SIO="examples/ics/trs80_model4/trs80_model4_serial.yaml"' in sh
    assert '--ic "${IC_SIO}"' in sh
    assert 'IC_VIDEO="examples/ics/trs80_model4/trs80_model4_video.yaml"' in sh
    assert '--ic "${IC_VIDEO}"' in sh
    assert 'IC_IRQ="examples/ics/trs80_model4/trs80_model4_irq.yaml"' in sh
    assert '--ic "${IC_IRQ}"' in sh
    assert 'IC_CASS="examples/ics/trs80_model4/trs80_model4_cassette.yaml"' in sh
    assert '--ic "${IC_CASS}"' in sh

    bat = Path("scripts/run_trs80_model4_debugger.bat").read_text(encoding="utf-8")
    assert 'set "IC_MAIN_RAM=examples/ics/trs80_model4/trs80_model4_main_ram.yaml"' in bat
    assert '--ic "%IC_MAIN_RAM%"' in bat
    assert 'set "IC_GA=examples/ics/trs80_model4/trs80_model4_gate_array.yaml"' in bat
    assert '--ic "%IC_GA%"' in bat
    assert 'set "IC_FDC=examples/ics/common/wd1793.yaml"' in bat
    assert '--ic "%IC_FDC%"' in bat
    assert 'set "DEVICE_FLOPPY_BACKEND=examples/devices/common/trs80_floppy_image_backend.yaml"' in bat
    assert '--device "%DEVICE_FLOPPY_BACKEND%"' in bat
    assert 'set "IC_PPI=examples/ics/trs80_model4/trs80_model4_ppi.yaml"' in bat
    assert '--ic "%IC_PPI%"' in bat
    assert 'set "IC_SIO=examples/ics/trs80_model4/trs80_model4_serial.yaml"' in bat
    assert '--ic "%IC_SIO%"' in bat
    assert 'set "IC_VIDEO=examples/ics/trs80_model4/trs80_model4_video.yaml"' in bat
    assert '--ic "%IC_VIDEO%"' in bat
    assert 'set "IC_IRQ=examples/ics/trs80_model4/trs80_model4_irq.yaml"' in bat
    assert '--ic "%IC_IRQ%"' in bat
    assert 'set "IC_CASS=examples/ics/trs80_model4/trs80_model4_cassette.yaml"' in bat
    assert '--ic "%IC_CASS%"' in bat


def test_trs80_model4_split_generation_smoke(tmp_path):
    base = Path(__file__).resolve().parents[1]
    processor = base / "examples" / "processors" / "z80.yaml"
    system = base / "examples" / "systems" / "trs80_model4" / "trs80_model4_default.yaml"
    out_dir = tmp_path / "trs80_model4_default_split"

    ic_paths = [
        base / "examples" / "ics" / "trs80_model4" / "trs80_model4_peripherals.yaml",
        base / "examples" / "ics" / "trs80_model4" / "trs80_model4_gate_array.yaml",
        base / "examples" / "ics" / "trs80_model4" / "trs80_model4_main_ram.yaml",
        base / "examples" / "ics" / "common" / "wd1793.yaml",
        base / "examples" / "ics" / "trs80_model4" / "trs80_model4_ppi.yaml",
        base / "examples" / "ics" / "trs80_model4" / "trs80_model4_serial.yaml",
        base / "examples" / "ics" / "trs80_model4" / "trs80_model4_video.yaml",
        base / "examples" / "ics" / "trs80_model4" / "trs80_model4_irq.yaml",
        base / "examples" / "ics" / "trs80_model4" / "trs80_model4_cassette.yaml",
    ]
    device_paths = [
        base / "examples" / "devices" / "trs80_model4" / "trs80_keyboard.yaml",
        base / "examples" / "devices" / "trs80_model4" / "trs80_video.yaml",
        base / "examples" / "devices" / "trs80_model4" / "trs80_speaker.yaml",
        base / "examples" / "devices" / "common" / "trs80_floppy_image_backend.yaml",
    ]
    host_paths = [base / "examples" / "hosts" / "trs80_model4" / "trs80_host_stub.yaml"]

    gen_mod.generate(
        str(processor),
        str(system),
        str(out_dir),
        ic_paths=[str(p) for p in ic_paths],
        device_paths=[str(p) for p in device_paths],
        host_paths=[str(p) for p in host_paths],
    )

    assert (out_dir / "src" / "Z80_core.c").exists()


def test_trs80_model4_irq_boundary_invariants():
    io_ic = Path("examples/ics/trs80_model4/trs80_model4_peripherals.yaml").read_text(encoding="utf-8")
    fdc_ic = Path("examples/ics/common/wd1793.yaml").read_text(encoding="utf-8")
    irq_ic = Path("examples/ics/trs80_model4/trs80_model4_irq.yaml").read_text(encoding="utf-8")

    # Split invariant: IO/FDC no longer perform CPU IRQ side effects directly.
    assert "z80_interrupt(" not in io_ic
    assert "z80_interrupt(" not in fdc_ic

    # Split invariant: IO/FDC should no longer expose/emit legacy irq_edge signals.
    assert 'id: trs80_m4io' in io_ic
    assert "name: irq_edge" not in io_ic
    assert 'id: wd1793_fdc' in fdc_ic
    assert "name: irq_edge" not in fdc_ic

    # Split invariant: centralized IRQ bridge remains the single interrupt source.
    assert 'id: trs80_m4irq' in irq_ic
    assert "z80_interrupt(" in irq_ic
    assert "name: irq_edge" in irq_ic


def test_trs80_model4_system_wiring_invariants():
    for rel in (
        "examples/systems/trs80_model4/trs80_model4_default.yaml",
        "examples/systems/trs80_model4/trs80_model4_interactive.yaml",
    ):
        s = Path(rel).read_text(encoding="utf-8")

        # Video present path must be sourced by video IC (not IO IC).
        assert "component: trs80_m4video" in s
        assert "name: frame_ready" in s
        assert "component: trs80_m4io\n      kind: signal\n      name: frame_ready" not in s

        # Host IRQ path must be sourced only by centralized IRQ IC.
        assert "component: trs80_m4irq" in s
        assert "name: irq_edge" in s
        assert "component: trs80_m4io\n      kind: signal\n      name: irq_edge" not in s
        assert "component: wd1793_fdc\n      kind: signal\n      name: irq_edge" not in s


def test_trs80_model4_io_delegation_invariants():
    io_ic = Path("examples/ics/trs80_model4/trs80_model4_peripherals.yaml").read_text(encoding="utf-8")

    # FC-FF cassette path must be delegated to cassette IC on both read and write.
    assert '"trs80_m4cass", "cass_port_read"' in io_ic
    assert '"trs80_m4cass", "cass_port_write"' in io_ic

    # Frame rendering must be delegated to video IC from IO scheduler.
    assert '"trs80_m4video", "render_frame"' in io_ic


def test_trs80_model4_runner_ic_flags_complete():
    sh = Path("scripts/run_trs80_model4_debugger.sh").read_text(encoding="utf-8")
    for token in (
        '--ic "${IC_MAIN}"',
        '--ic "${IC_GA}"',
        '--ic "${IC_MAIN_RAM}"',
        '--ic "${IC_FDC}"',
        '--ic "${IC_PPI}"',
        '--ic "${IC_SIO}"',
        '--ic "${IC_VIDEO}"',
        '--ic "${IC_IRQ}"',
        '--ic "${IC_CASS}"',
    ):
        assert token in sh

    bat = Path("scripts/run_trs80_model4_debugger.bat").read_text(encoding="utf-8")
    for token in (
        '--ic "%IC_MAIN%"',
        '--ic "%IC_GA%"',
        '--ic "%IC_MAIN_RAM%"',
        '--ic "%IC_FDC%"',
        '--ic "%IC_PPI%"',
        '--ic "%IC_SIO%"',
        '--ic "%IC_VIDEO%"',
        '--ic "%IC_IRQ%"',
        '--ic "%IC_CASS%"',
    ):
        assert token in bat
