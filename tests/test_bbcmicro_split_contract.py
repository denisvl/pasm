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
    assert 'DEVICE_FLOPPY_BACKEND="examples/devices/common/floppy_raw_sector_image_backend.yaml"' in script
    assert '--device "${DEVICE_FLOPPY_BACKEND}"' in script
    assert 'RUN_ARGS+=(--floppy "${FLOPPY}")' in script


def test_bbcmicro_systems_expose_floppy_runtime():
    systems = (
        "examples/systems/bbcmicro/bbc_micro_default.yaml",
        "examples/systems/bbcmicro/bbc_micro_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "floppy: bbc_micro_crtc_6845" in s
        assert "media_picker:" in s
        assert "open_action_id: EMU_MEDIA_PICKER" in s
        assert "directory: examples/floppies/bbcmicro" in s
        assert "source_type: ../../floppy_sources/ssd_file.yaml" in s
        assert "source_type: ../../floppy_sources/dsd_file.yaml" in s
        assert "source_type: ../../floppy_sources/adl_file.yaml" in s
        assert "source_component: floppy_raw_sector_image_backend" in s


def test_bbcmicro_dfs_sideways_slot_is_e():
    crtc = Path("examples/ics/bbcmicro/bbc_micro_crtc_6845.yaml").read_text(
        encoding="utf-8"
    )
    assert "BASIC in slot F, DFS in slot E." in crtc
    assert "if ((comp->romsel & 0x0Fu) == 0x0Eu)" in crtc
    assert 'cpu->memory[0x024Au] = 0x0Eu;' in crtc
