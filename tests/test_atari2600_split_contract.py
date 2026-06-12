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


def test_atari2600_tia_audio_zero_volume_is_centered_silence():
    tia = Path("examples/ics/atari2600/atari2600_tia.yaml").read_text(encoding="utf-8")
    assert "if (volume_sum == 0u)" in tia
    assert "comp->audio_level = 128u;" in tia
    assert "comp->audio_level = (uint8_t)((mix * 255u) / 30u);" not in tia


def test_atari2600_tia_audio_divider_is_clocked_at_audio_rate():
    tia = Path("examples/ics/atari2600/atari2600_tia.yaml").read_text(encoding="utf-8")
    assert "uint8_t phase0_tick = (uint8_t)(comp->aud_clock == 9u || comp->aud_clock == 81u);" in tia
    assert (
        "uint8_t audio_tick = (uint8_t)(comp->aud_clock == 37u || comp->aud_clock == 149u);"
        in tia
    )
    assert "if (phase0_tick != 0u)" in tia
    assert "if (audio_tick != 0u)" in tia


def test_atari2600_system_audio_rate_matches_tia_sample_clock():
    for rel in [
        "examples/systems/atari2600/atari2600_default.yaml",
        "examples/systems/atari2600/atari2600_interactive.yaml",
    ]:
        system = Path(rel).read_text(encoding="utf-8")
        assert "sample_rate: 31400" in system
        assert "sample_rate: 44100" not in system
