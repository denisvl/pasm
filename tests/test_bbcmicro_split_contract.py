from pathlib import Path


def test_bbcmicro_systems_use_split_ics_and_no_legacy_io():
    systems = (
        "examples/systems/bbcmicro/bbc_micro_default.yaml",
        "examples/systems/bbcmicro/bbc_micro_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "- bbc_micro_crtc_6845" in s
        assert "- bbc_micro_video_ula" in s
        assert "- bbc_micro_system_via_6522" in s
        assert "- bbc_micro_user_via_6522" in s
        assert "- bbc_micro_teletext_saa5050" in s
        assert "- bbc_micro_adc_upd7002" in s
        assert "- bbc_micro_acia_6850" in s
        assert "- bbc_micro_mmu_paged_rom" in s
        assert "- sn76489_psg0" in s
        assert "- bbc_micro_main_ram" in s
        assert "bbc_micro_io" not in s


def test_bbcmicro_runner_loads_main_ram_ic():
    script = Path("scripts/run_bbc_micro_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_MAIN_RAM="examples/ics/bbcmicro/bbc_micro_main_ram.yaml"' in script
    assert '--ic "${IC_MAIN_RAM}"' in script
