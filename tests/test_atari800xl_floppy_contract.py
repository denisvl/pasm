from pathlib import Path


def test_atari800xl_systems_expose_atr_floppy_runtime():
    systems = (
        "examples/systems/atari800xl/atari800xl_default.yaml",
        "examples/systems/atari800xl/atari800xl_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "floppy: atari_1050_sio" in s
        assert "media_picker:" in s
        assert "open_action_id: EMU_MEDIA_PICKER" in s
        assert "directory: examples/floppies/atari800xl" in s
        assert "source_type: ../../floppy_sources/atr_file.yaml" in s
        assert "source_component: atari_atr_image_backend" in s
        assert "drive_type: ../../floppy_drives/atari_1050.yaml" in s
        assert "component: atari_1050_sio" in s


def test_atari800xl_runner_loads_floppy_devices():
    script = Path("scripts/run_atari800xl_debugger.sh").read_text(encoding="utf-8")
    assert 'DEVICE_ATR_BACKEND="examples/devices/common/atari_atr_image_backend.yaml"' in script
    assert 'DEVICE_ATARI_1050_SIO="examples/devices/atari800xl/atari_1050_sio.yaml"' in script
    assert '--device "${DEVICE_ATR_BACKEND}"' in script
    assert '--device "${DEVICE_ATARI_1050_SIO}"' in script
    assert 'RUN_FLOPPY_ARGS+=(--floppy "${FLOPPY}")' in script
    assert 'if [[ ! -f "${AUTO_CASSETTE_RUNTIME}" ]]; then' in script
    assert 'echo "Error: boot cassette not found (${BOOT_CASSETTE} -> ${AUTO_CASSETTE_RUNTIME})." >&2' in script
    assert "exit 2" in script
    assert 'PASM_CASSETTE_AUTO_BOOT="$([[ -n "${AUTO_CASSETTE_RUNTIME}" ]] && printf 1 || printf 0)"' in script
    assert 'PASM_EMU_CASSETTE_AUTO_PLAY="$([[ -n "${AUTO_CASSETTE_RUNTIME}" ]] && printf 1 || printf 0)"' in script


def test_atari_atr_backend_understands_atr_layout():
    backend = Path("examples/devices/common/atari_atr_image_backend.yaml").read_text(
        encoding="utf-8"
    )
    assert "image[0] != 0x96u || image[1] != 0x02u" in backend
    assert "sector_size == 256u" in backend
    assert "sector <= 3u" in backend
    assert "read_atr_sector" in backend


def test_atari800xl_core_traps_siov_to_floppy_device():
    antic = Path("examples/ics/atari800xl/atari800xl_antic.yaml").read_text(
        encoding="utf-8"
    )
    assert "cpu->pc == 0xE459u" in antic
    assert '"atari_1050_sio"' in antic
    assert '"sio_command"' in antic
    assert "0x0300u" in antic
    assert "0x030Bu" in antic
    assert "PACTL bit 3 directly drives the cassette motor" in antic
    assert 'motor_on = (uint8_t)(((comp->pia_cra & 0x08u) == 0u) ? 1u : 0u);' in antic
    assert '"atari_pia PACTL write cycle=%llu prev=%02X value=%02X motor_bit=%u motor_on=%u irqen_bit=%u status_bit=%u\\n"' in antic
    assert "{ 0x02FCu, (uint64_t)live_code }; /* CH shadow */" in antic
    assert "atari_prompt_key cycle=%llu pc=%04X key=%02X\\n" in antic
    assert "value &= 0x3Fu;" in antic
    assert "comp->pia_cra = (uint8_t)((comp->pia_cra & 0xC0u) | value);" in antic
    assert "comp->pia_cra = (uint8_t)(comp->pia_cra & 0x3Fu);" in antic
    assert "comp->pokey_serin = 0x00u;" in antic
    assert "comp->pokey_irqst = 0xFFu;" in antic
    assert "comp->pokey_skstat = 0xEFu;" in antic


def test_atari_cas_source_reports_total_duration():
    cas = Path("examples/devices/common/cassette_cas_source.yaml").read_text(
        encoding="utf-8"
    )
    assert "uint64_t total_secs = 0u;" in cas
    assert "total_secs = comp->total_samples / (uint64_t)comp->signal_sample_rate;" in cas
    assert 'packed |= (total_secs & 0xFFFFu) << 32u;' in cas


def test_atari_cassette_adapter_delivers_bytes_on_zero_boundary():
    adapter = Path("examples/devices/atari800xl/atari800xl_cassette_adapter.yaml").read_text(
        encoding="utf-8"
    )
    assert "while (comp->atari_cas_event_time_left <= 0)" in adapter


def test_atari_host_queues_return_after_console_override_for_auto_boot():
    host = Path("examples/hosts/atari800xl/atari800xl_host_hal_interactive.yaml").read_text(
        encoding="utf-8"
    )
    assert "RETURN KBCODE+1" in host
    assert "comp->auto_boot_space_pending" in host
    assert "cpu->pc >= 0xC000u" in host


def test_codegen_seeds_cassette_auto_load_in_runtime_apply_path():
    impl = Path("src/codegen/cpu_impl.py").read_text(encoding="utf-8")
    assert 'int cpu_component_cassette_picker_apply_pending_load(CPUState *cpu) {' in impl
    assert 'const char *auto_path = cpu_host_hal_getenv(\\"PASM_EMU_CASSETTE_AUTO_PATH\\");' in impl
    assert 'g_runtime_cassette_picker.pending_load = 1u;' in impl
