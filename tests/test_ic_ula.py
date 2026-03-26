import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

from src import generator as gen_mod
from src.parser import yaml_loader
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _zx_paths() -> tuple[
    pathlib.Path, pathlib.Path, pathlib.Path, list[pathlib.Path], list[pathlib.Path]
]:
    processor_path, system_path = example_pair("z80", system="z80_spectrum48k_default.yaml")
    ic_path = BASE_DIR / "examples" / "ics" / "zx_spectrum_48k_ula.yaml"
    device_paths = [
        BASE_DIR / "examples" / "devices" / "zx48_keyboard.yaml",
        BASE_DIR / "examples" / "devices" / "zx48_video.yaml",
        BASE_DIR / "examples" / "devices" / "zx48_speaker.yaml",
        BASE_DIR / "examples" / "devices" / "zx48_mic.yaml",
    ]
    host_paths = [
        BASE_DIR / "examples" / "hosts" / "zx48_host_sdl2.yaml",
    ]
    return processor_path, system_path, ic_path, device_paths, host_paths


def test_component_graph_validates_with_z80():
    processor_path, system_path, ic_path, device_paths, host_paths = _zx_paths()
    data = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        [str(ic_path)],
        [str(path) for path in device_paths],
        [str(path) for path in host_paths],
    )
    assert len(data["ics"]) == 1
    assert len(data["devices"]) == 4
    assert len(data["hosts"]) == 1
    assert data["components"]["ics"] == ["ula0"]
    assert data["components"]["hosts"] == ["host0"]


def test_system_component_set_mismatch_fails(tmp_path):
    processor_path, system_path, ic_path, device_paths, host_paths = _zx_paths()
    system_data = yaml.safe_load(system_path.read_text(encoding="utf-8"))
    system_data["components"]["devices"] = ["keyboard0", "video0", "speaker0"]
    bad_system = tmp_path / "bad_system.yaml"
    bad_system.write_text(yaml.safe_dump(system_data, sort_keys=False), encoding="utf-8")

    with pytest.raises(Exception, match="components.devices"):
        yaml_loader.load_processor_system(
            str(processor_path),
            str(bad_system),
            [str(ic_path)],
            [str(path) for path in device_paths],
            [str(path) for path in host_paths],
        )


def test_invalid_connection_endpoint_fails(tmp_path):
    processor_path, system_path, ic_path, device_paths, host_paths = _zx_paths()
    system_data = yaml.safe_load(system_path.read_text(encoding="utf-8"))
    system_data["connections"][0]["to"]["name"] = "missing_callback"
    system_data["memory"]["rom_images"][0]["file"] = str(
        (BASE_DIR / "examples" / "roms" / "zx48_dummy.rom").resolve()
    )
    bad_system = tmp_path / "bad_connection.yaml"
    bad_system.write_text(yaml.safe_dump(system_data, sort_keys=False), encoding="utf-8")

    with pytest.raises(Exception, match="not declared"):
        yaml_loader.load_processor_system(
            str(processor_path),
            str(bad_system),
            [str(ic_path)],
            [str(path) for path in device_paths],
            [str(path) for path in host_paths],
        )


def test_component_generation_emits_generic_component_runtime(tmp_path):
    processor_path, system_path, ic_path, device_paths, host_paths = _zx_paths()
    outdir = tmp_path / "z80_component_gen"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        ic_paths=[str(ic_path)],
        device_paths=[str(path) for path in device_paths],
        host_paths=[str(path) for path in host_paths],
    )

    header = (outdir / "src" / "Z80.h").read_text(encoding="utf-8")
    impl = (outdir / "src" / "Z80.c").read_text(encoding="utf-8")

    assert "typedef uint64_t (*CPUHostEndpointHandler)" not in header
    assert "z80_set_host_endpoint_handler" not in header
    assert "z80_set_host_endpoint_handler" not in impl
    assert "ComponentState_host0" in header
    assert "comp_host0" in header
    assert "ULAKeyboardReadFn" not in header
    assert "IC_EVENT_ULA" not in header


@pytest.mark.skipif(
    (shutil.which("cc") is None and shutil.which("gcc") is None and shutil.which("clang") is None),
    reason="C compiler not available on PATH",
)
def test_component_runtime_keyboard_video_audio_and_contention(tmp_path):
    processor_path, system_path, ic_path, device_paths, host_paths = _zx_paths()
    outdir = tmp_path / "z80_component_runtime"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        ic_paths=[str(ic_path)],
        device_paths=[str(path) for path in device_paths],
        host_paths=[str(path) for path in host_paths],
    )

    harness_c = outdir / "component_harness.c"
    harness_c.write_text(
        """
#include <stdint.h>
#include <stdio.h>
#include "Z80.h"

int main(void) {
    CPUState *cpu = z80_create(65536);
    if (!cpu) return 2;

    /* FE write/read sequence. */
    z80_write_byte(cpu, 0x0000, 0x3E); z80_write_byte(cpu, 0x0001, 0x17); /* LD A,17 */
    z80_write_byte(cpu, 0x0002, 0xD3); z80_write_byte(cpu, 0x0003, 0xFE); /* OUT (FE),A */
    z80_write_byte(cpu, 0x0004, 0xDB); z80_write_byte(cpu, 0x0005, 0xFE); /* IN A,(FE) */
    z80_write_byte(cpu, 0x0006, 0x76);                                    /* HALT */

    while (cpu->running && !cpu->halted) {
        if (z80_step(cpu) != 0) break;
    }

    printf("A=%u\\n", (unsigned int)cpu->registers[REG_A]);
    printf("BORDER_EVENTS=%u\\n", cpu->comp_host0.border_events);
    printf("LAST_BORDER=%u\\n", (unsigned int)cpu->comp_host0.last_border);

    /* Contention check. */
    z80_reset(cpu);
    cpu->pc = 0x2000;
    z80_write_byte(cpu, 0x2000, 0x00); /* NOP uncontended */
    uint64_t before = cpu->total_cycles;
    z80_step(cpu);
    uint64_t delta_uncontended = cpu->total_cycles - before;

    z80_reset(cpu);
    cpu->pc = 0x4000;
    z80_write_byte(cpu, 0x4000, 0x00); /* NOP contended */
    before = cpu->total_cycles;
    z80_step(cpu);
    uint64_t delta_contended = cpu->total_cycles - before;

    printf("DELTA_UNCONTENDED=%llu\\n", (unsigned long long)delta_uncontended);
    printf("DELTA_CONTENDED=%llu\\n", (unsigned long long)delta_contended);

    /* Longer run for frame/audio/irq activity. */
    z80_reset(cpu);
    cpu->pc = 0x3000;
    for (int i = 0; i < 80000; i++) {
        if (z80_step(cpu) != 0) break;
    }

    printf("FRAME_EVENTS=%u\\n", cpu->comp_host0.video_frames);
    printf("IRQ_EDGES=%u\\n", cpu->comp_host0.irq_edges);
    printf("AUDIO_SAMPLES=%u\\n", cpu->comp_host0.audio_samples);
    printf("LAST_AUDIO=%u\\n", (unsigned int)cpu->comp_host0.last_audio);

    z80_destroy(cpu);
    return 0;
}
""",
        encoding="utf-8",
    )

    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    binary_name = "component_harness.exe" if os.name == "nt" else "component_harness"
    binary = outdir / binary_name
    subprocess.check_call(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-I",
            str(outdir / "src"),
            str(outdir / "src" / "Z80.c"),
            str(outdir / "src" / "Z80_decoder.c"),
            str(harness_c),
            "-o",
            str(binary),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    proc = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    out = proc.stdout
    assert "A=90" in out
    vals = {}
    for line in out.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            vals[key.strip()] = value.strip()

    assert int(vals["BORDER_EVENTS"]) >= 1
    assert int(vals["DELTA_CONTENDED"]) > int(vals["DELTA_UNCONTENDED"])
    assert int(vals["FRAME_EVENTS"]) >= 1
    assert int(vals["IRQ_EDGES"]) >= 1
    assert int(vals["AUDIO_SAMPLES"]) >= 1
    assert int(vals["LAST_AUDIO"]) in (0, 1)
