from pathlib import Path


def test_cpc464_systems_expose_floppy_runtime():
    systems = (
        "examples/systems/cpc464/cpc464_default.yaml",
        "examples/systems/cpc464/cpc464_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "floppy: cpc_floppy_stub" in s
        assert "media_picker:" in s
        assert "open_action_id: EMU_MEDIA_PICKER" in s
        assert "directory: examples/floppies/cpc464" in s
        assert "source_type: ../../floppy_sources/dsk_file.yaml" in s
        assert "source_component: cpc_dsk_image_backend" in s
        assert "drive_type: ../../floppy_drives/cpc_fd1.yaml" in s
        assert "component: cpc_floppy_stub" in s


def test_cpc464_runner_loads_floppy_devices():
    script = Path("scripts/run_amstrad_cpc464_debugger.sh").read_text(encoding="utf-8")
    assert 'DEVICE_FLOPPY="examples/devices/cpc464/cpc_floppy_stub.yaml"' in script
    assert 'DEVICE_FLOPPY_BACKEND="examples/devices/common/cpc_dsk_image_backend.yaml"' in script
    assert '--device "${DEVICE_FLOPPY}"' in script
    assert '--device "${DEVICE_FLOPPY_BACKEND}"' in script
    assert 'RUN_FLOPPY_ARGS+=(--floppy "${FLOPPY}")' in script
    assert 'DISK_ROM="${DISK_ROM:-examples/roms/cpc464/amsdos.rom}"' in script
    assert 'PASM_CPC_DISK_ROM="${DISK_ROM}"' in script


def test_cpc_floppy_stub_delegates_to_generic_backend():
    stub = Path("examples/devices/cpc464/cpc_floppy_stub.yaml").read_text(encoding="utf-8")
    assert 'type: floppy_drive' in stub
    assert '"cpc_dsk_image_backend"' in stub
    assert '"read_sector"' in stub
    assert "query_geometry" in stub
    assert 'fdc_status_read' in stub
    assert 'fdc_data_read' in stub
    assert 'fdc_data_write' in stub
    assert 'fdc_motor_write' in stub


def test_cpc_dsk_backend_recognizes_cpc_headers():
    backend = Path("examples/devices/common/cpc_dsk_image_backend.yaml").read_text(
        encoding="utf-8"
    )
    assert 'memcmp(image, "MV - CPCEMU Disk-File\\r\\nDisk-Info\\r\\n", 34u)' in backend
    assert 'memcmp(image, "EXTENDED CPC DSK File\\r\\nDisk-Info\\r\\n", 34u)' in backend
    assert '"Track-Info\\r\\n"' in backend


def test_cpc_gate_array_supports_optional_disk_rom_and_rom7_select():
    gate_array = Path("examples/ics/cpc464/cpc_gate_array_40010.yaml").read_text(
        encoding="utf-8"
    )
    assert 'name: disk_rom' in gate_array
    assert 'name: disk_rom_size' in gate_array
    assert 'name: upper_rom_select' in gate_array
    assert 'getenv("PASM_CPC_DISK_ROM")' in gate_array
    assert 'cpu->pc = 0xBCCEu;' in gate_array
    assert "comp->upper_rom_select == 7u" in gate_array
    assert "(port & 0xFF00u) == 0xDF00u" in gate_array
    assert "comp->upper_rom_select = (uint8_t)(value & 0x1Fu);" in gate_array
    assert 'port == 0xFA7Eu' in gate_array
    assert 'port == 0xFB7Eu' in gate_array
    assert 'port == 0xFB7Fu' in gate_array
    assert 'fdc_status_read' in gate_array
    assert 'fdc_data_read' in gate_array
    assert 'fdc_data_write' in gate_array


def test_cpc464_local_rtype_disk_image_is_present_and_decodes_as_standard_dsk():
    image_path = Path("examples/floppies/cpc464/R-Type (1988)(Electric Dreams Software).dsk")
    data = image_path.read_bytes()

    assert data.startswith(b"MV - CPCEMU Disk-File\r\nDisk-Info\r\n")

    track_count = data[0x30]
    side_count = data[0x31]
    track_size = int.from_bytes(data[0x32:0x34], "little")

    assert track_count == 40
    assert side_count == 1
    assert track_size == 0x1300

    first_track = 0x100
    assert data[first_track:first_track + 12] == b"Track-Info\r\n"
    assert data[first_track + 0x14] == 0x02
    assert data[first_track + 0x15] == 0x09

    first_sector_info = first_track + 0x18
    sector_ids = [data[first_sector_info + (i * 8) + 2] for i in range(9)]
    assert sector_ids == [0xC1, 0xC6, 0xC2, 0xC7, 0xC3, 0xC8, 0xC4, 0xC9, 0xC5]
