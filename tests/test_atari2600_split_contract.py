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


def test_atari2600_tia_fire_latch_mode_is_controlled_by_vblank_writes():
    tia = Path("examples/ics/atari2600/atari2600_tia.yaml").read_text(encoding="utf-8")
    assert "inpt4_latch_mode" in tia
    assert "inpt5_latch_mode" in tia
    assert "if (comp->inpt4_latch_mode != 0u)" in tia
    assert "comp->inpt4_latch = (uint8_t)(comp->inpt4_latch & trig4);" in tia
    assert "comp->inpt4_latch_mode = 0u;" in tia
    assert "comp->inpt4_latch = 0x80u;" in tia
    assert "Update trigger latches: when VBLANK bit 6 is set" not in tia


def test_atari2600_hmove_hblank_updates_player_render_state():
    tia = Path("examples/ics/atari2600/atari2600_tia.yaml").read_text(encoding="utf-8")
    assert "uint8_t p0_decode_hm = player_decodes" in tia
    assert "uint8_t p1_decode_hm = player_decodes" in tia
    assert "comp->p0_render_counter = -5;" in tia
    assert "comp->p1_render_counter = -5;" in tia
    assert "During HBLANK HMOVE, adjust position counter only" not in tia


def test_atari2600_hmove_comb_is_cleared_once_when_hmove_starts():
    tia = Path("examples/ics/atari2600/atari2600_tia.yaml").read_text(encoding="utf-8")
    assert "if (comp->extended_hblank == 0u && comp->frame_started != 0u && ((comp->vblank & 0x02u) == 0u) && cc < 68u)" in tia
    assert "for (uint32_t i = 0u; i < 8u; ++i)" in tia
    assert "framebuf[y * 160u + i] = 0xFF000000u;" in tia
    assert "x < (uint32_t)comp->hmove_blank" not in tia


def test_atari2600_player_resp_uses_current_tia_clock():
    tia = Path("examples/ics/atari2600/atari2600_tia.yaml").read_text(encoding="utf-8")
    assert "case 0x10u: {\n                  uint32_t cc = comp->color_clock;" in tia
    assert "case 0x11u: {\n                  uint32_t cc = comp->color_clock;" in tia
    assert "CPU-side memory hook sees them" not in tia
