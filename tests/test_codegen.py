import pathlib
import re

from src import generator as gen_mod
from tests.support import example_pair


def test_generate_minimal8(tmp_path):
    processor_path, system_path = example_pair("minimal8")
    outdir = tmp_path / "minimal8_test"

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    src_dir = outdir / "src"
    assert (src_dir / "Minimal8_core.c").exists()
    assert (src_dir / "Minimal8.h").exists()
    assert (src_dir / "Minimal8_decoder.c").exists()
    assert (src_dir / "minimal8_runtime.c").exists()
    assert (src_dir / "minimal8_system_glue.c").exists()
    assert (outdir / "CMakeLists.txt").exists()
    assert (outdir / "Makefile").exists()


def test_generate_simple8_full(tmp_path):
    processor_path, system_path = example_pair("simple8")
    outdir = tmp_path / "simple8_test"

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    src_dir = outdir / "src"
    # Core files
    assert (src_dir / "Simple8_core.c").exists()
    assert (src_dir / "Simple8.h").exists()
    assert (src_dir / "Simple8_decoder.c").exists()
    assert (src_dir / "simple8_runtime.c").exists()
    assert (src_dir / "simple8_system_glue.c").exists()
    # Hooks are disabled in simple8.yaml
    assert not (src_dir / "Simple8_hooks.c").exists()
    # Include dir and defs header
    include_dir = outdir / "include"
    assert (include_dir / "cpu_defs.h").exists()


def test_generate_trs80_model4_moves_reset_delay_out_of_core(tmp_path):
    processor_path, system_path = example_pair(
        "z80", "trs80_model4_interactive.yaml"
    )
    outdir = tmp_path / "trs80_reset_delay_test"
    examples_dir = processor_path.parents[1]
    trs80_ics = examples_dir / "ics" / "trs80_model4"
    common_ics = examples_dir / "ics" / "common"
    ic_paths = [
        str(trs80_ics / "trs80_model4_peripherals.yaml"),
        str(trs80_ics / "trs80_model4_gate_array.yaml"),
        str(trs80_ics / "trs80_model4_main_ram.yaml"),
        str(common_ics / "wd1793.yaml"),
        str(trs80_ics / "trs80_model4_ppi.yaml"),
        str(trs80_ics / "trs80_model4_serial.yaml"),
        str(trs80_ics / "trs80_model4_video.yaml"),
        str(trs80_ics / "trs80_model4_irq.yaml"),
        str(trs80_ics / "trs80_model4_cassette.yaml"),
    ]
    device_paths = [
        str(examples_dir / "devices" / "trs80_keyboard.yaml"),
        str(examples_dir / "devices" / "trs80_video.yaml"),
        str(examples_dir / "devices" / "trs80_speaker.yaml"),
        str(examples_dir / "devices" / "common" / "trs80_floppy_image_backend.yaml"),
    ]
    host_paths = [
        str(examples_dir / "hosts" / "trs80_host_hal_interactive.yaml"),
    ]

    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        ic_paths=ic_paths,
        device_paths=device_paths,
        host_paths=host_paths,
    )

    cpu_impl = (outdir / "src" / "Z80_core.c").read_text(encoding="utf-8")
    system_glue = (outdir / "src" / "trs80_model4_system_glue.c").read_text(
        encoding="utf-8"
    )
    assert "cpu_sleep_seconds(" not in cpu_impl
    assert "if (cpu->reset_delay_pending)" not in cpu_impl
    assert "cpu->reset_delay_pending = false;" in system_glue


def test_codegen_has_no_cpu_name_substring_heuristics():
    codegen_dir = pathlib.Path("src/codegen")
    pattern = re.compile(r'if\s+["\'](?:6809|6502|6510|6509|z80|68000|m68k|2a03)["\']\s+in\s+\w+')
    offenders = []
    for py_file in sorted(codegen_dir.glob("*.py")):
        text = py_file.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            offenders.append(f"{py_file}:{match.start()}")
    assert offenders == []


def test_generate_c64_1541_subsystem_descriptor(tmp_path):
    subsystem_path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "examples"
        / "subsystems"
        / "c64_1541_subsystem.yaml"
    )
    outdir = tmp_path / "c64_1541_subsystem"

    gen_mod.generate_from_subsystem(str(subsystem_path), str(outdir))

    src_dir = outdir / "src"
    assert (src_dir / "MOS6502_core.c").exists()
    assert (src_dir / "MOS6502.h").exists()
    assert (src_dir / "MOS6502_decoder.c").exists()
    assert (src_dir / "c1541_runtime.c").exists()
    assert (src_dir / "c1541_system_glue.c").exists()
    assert (outdir / "CMakeLists.txt").exists()
    assert (outdir / "Makefile").exists()


def test_generate_c64_with_attached_1541_subsystem_build(tmp_path):
    root = pathlib.Path(__file__).resolve().parents[1]
    processor_path = root / "examples" / "processors" / "mos6510.yaml"
    system_path = root / "examples" / "systems" / "c64" / "c64_interactive.yaml"
    outdir = tmp_path / "c64_with_subsystem"
    examples_dir = root / "examples"

    ic_paths = [
        str(examples_dir / "ics" / "c64" / "c64_pla_906114.yaml"),
        str(examples_dir / "ics" / "c64" / "c64_vic_ii_6569.yaml"),
        str(examples_dir / "ics" / "c64" / "c64_sid_6581.yaml"),
        str(examples_dir / "ics" / "c64" / "c64_cia1_6526.yaml"),
        str(examples_dir / "ics" / "c64" / "c64_cia2_6526.yaml"),
        str(examples_dir / "ics" / "c64" / "c64_color_ram_2114.yaml"),
        str(examples_dir / "ics" / "c64" / "c64_main_ram.yaml"),
    ]
    device_paths = [
        str(examples_dir / "devices" / "c64" / "c64_datasette.yaml"),
        str(examples_dir / "devices" / "c64" / "c64_iec_bus.yaml"),
        str(examples_dir / "devices" / "c64" / "c64_1541.yaml"),
        str(examples_dir / "devices" / "c64" / "c64_1541_media.yaml"),
        str(examples_dir / "devices" / "c64" / "c64_1541_dos.yaml"),
        str(examples_dir / "devices" / "c64" / "c64_1541_core.yaml"),
        str(examples_dir / "devices" / "common" / "c64_d64_image_backend.yaml"),
        str(examples_dir / "devices" / "c64" / "c64_keyboard.yaml"),
        str(examples_dir / "devices" / "c64" / "c64_joystick.yaml"),
        str(examples_dir / "devices" / "c64" / "c64_video.yaml"),
        str(examples_dir / "devices" / "common" / "tv_crt_mono.yaml"),
    ]
    host_paths = [
        str(examples_dir / "hosts" / "c64" / "c64_host_hal_interactive.yaml"),
    ]

    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        ic_paths=ic_paths,
        device_paths=device_paths,
        host_paths=host_paths,
    )

    subsystem_dir = outdir / "subsystems" / "c64_1541_subsystem"
    assert (subsystem_dir / "src" / "MOS6502_core.c").exists()
    assert (subsystem_dir / "debugger_link.json").exists()

    cmake_text = (outdir / "CMakeLists.txt").read_text(encoding="utf-8")
    assert 'add_subdirectory("subsystems/c64_1541_subsystem")' in cmake_text
    assert "target_link_libraries(c64_system PUBLIC" in cmake_text
    assert "c1541_system" in cmake_text

    manifest = (outdir / "debugger_link.json").read_text(encoding="utf-8")
    assert '"subsystems"' in manifest
    assert '"id": "c64_1541_subsystem"' in manifest

