from pathlib import Path


def test_coco1_systems_expose_floppy_runtime():
    systems = (
        "examples/systems/coco1/coco1_default.yaml",
        "examples/systems/coco1/coco1_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "- wd1793_fdc" in s
        assert "floppy: wd1793_fdc" in s
        assert "media_picker:" in s
        assert "open_action_id: EMU_MEDIA_PICKER" in s
        assert "directory: examples/floppies/coco1" in s
        assert "source_component: trs80_floppy_image_backend" in s
        assert "drive_type: ../../floppy_drives/coco_fd501.yaml" in s
        assert "component: wd1793_fdc" in s


def test_coco1_runners_load_floppy_components():
    sh = Path("scripts/run_coco_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_FDC="examples/ics/common/wd1793.yaml"' in sh
    assert 'DEVICE_FLOPPY_BACKEND="examples/devices/common/trs80_floppy_image_backend.yaml"' in sh
    assert '--ic "${IC_FDC}"' in sh
    assert '--device "${DEVICE_FLOPPY_BACKEND}"' in sh
    assert 'RUN_FLOPPY_ARGS+=(--floppy "${FLOPPY}")' in sh
    assert 'DISK_ROM="${DISK_ROM:-}"' in sh

    bat = Path("scripts/run_coco_debugger.bat").read_text(encoding="utf-8")
    assert 'set "IC_FDC=examples/ics/common/wd1793.yaml"' in bat
    assert 'set "DEVICE_FLOPPY_BACKEND=examples/devices/common/trs80_floppy_image_backend.yaml"' in bat


def test_coco1_sam_routes_fd501_registers_and_nmi():
    sam = Path("examples/ics/coco1/coco1_sam_6883.yaml").read_text(encoding="utf-8")
    assert "name: fdc_irq_seen" in sam
    assert 'cpu_component_dispatch_callback(cpu, "wd1793_fdc", "fdc_port_read"' in sam
    assert 'cpu_component_dispatch_callback(cpu, "wd1793_fdc", "fdc_port_write"' in sam
    assert 'cpu_component_dispatch_callback(cpu, "wd1793_fdc", "fdc_step_tick"' in sam
    assert 'cpu_component_dispatch_callback(cpu, "wd1793_fdc", "query_irq_state"' in sam
    assert 'uint64_t irq_args[1] = { 1u };' in sam


def test_wd1793_exports_irq_query_callback():
    fdc = Path("examples/ics/common/wd1793.yaml").read_text(encoding="utf-8")
    assert "name: query_irq_state" in fdc
    assert "fdc_irq_pending" in fdc
    assert "fdc_nmi_mask" in fdc
