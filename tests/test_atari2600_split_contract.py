from pathlib import Path


def test_atari2600_systems_use_split_ics():
    for rel in [
        "examples/systems/atari2600/atari2600_default.yaml",
        "examples/systems/atari2600/atari2600_interactive.yaml",
    ]:
        s = Path(rel).read_text(encoding="utf-8")
        assert "- atari2600_tia" in s
        assert "- atari2600_riot" in s
        assert "- atari2600_main_ram" in s
        assert "atari2600_io" not in s


def test_atari2600_runner_uses_split_ics():
    script = Path("scripts/run_atari2600_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_TIA="examples/ics/atari2600/atari2600_tia.yaml"' in script
    assert 'IC_RIOT="examples/ics/atari2600/atari2600_riot_6532.yaml"' in script
    assert '--ic "${IC_TIA}"' in script
    assert '--ic "${IC_RIOT}"' in script

