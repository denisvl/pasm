from pathlib import Path


def test_msx1_systems_include_main_ram_split_ic():
    systems = (
        "examples/systems/msx1/msx1_default.yaml",
        "examples/systems/msx1/msx1_interactive.yaml",
        "examples/systems/msx1/msx1_cartridge_default.yaml",
        "examples/systems/msx1/msx1_cartridge_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "- vdp0" in s
        assert "- ppi0" in s
        assert "- psg0" in s
        assert "- msx1_main_ram" in s


def test_msx1_runner_loads_main_ram_ic():
    script = Path("scripts/run_msx_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_MAIN_RAM="examples/ics/msx1/msx1_main_ram.yaml"' in script
    assert '--ic "${IC_MAIN_RAM}"' in script
