from pathlib import Path


def test_c64_interactive_systems_use_split_ics():
    systems = (
        "examples/systems/c64/c64_interactive.yaml",
        "examples/systems/c64/c64_cartridge_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "- c64_vic_ii" in s
        assert "- c64_sid" in s
        assert "- c64_cia1" in s
        assert "- c64_cia2" in s
        assert "- c64_color_ram" in s
        assert "- c64_pla" in s
        assert "- c64_main_ram" in s


def test_c64_runners_load_split_ram_and_joystick():
    sh = Path("scripts/run_c64_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_MAIN_RAM="examples/ics/c64/c64_main_ram.yaml"' in sh
    assert '--ic "${IC_MAIN_RAM}"' in sh
    assert '--device "${DEVICE_JOY}"' in sh

    bat = Path("scripts/run_c64_debugger.bat").read_text(encoding="utf-8")
    assert 'set "IC_MAIN_RAM=examples/ics/c64/c64_main_ram.yaml"' in bat
    assert '--ic "%IC_MAIN_RAM%" ^' in bat
    assert '--device "%DEVICE_JOY%" ^' in bat
