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


def _trs80_interactive_paths():
    processor_path, _ = example_pair("z80", system="z80_trs80_model4_default.yaml")
    system_path = (
        BASE_DIR / "examples" / "systems" / "trs80_model4" / "z80_trs80_model4_interactive.yaml"
    )
    ic_paths = [
        BASE_DIR / "examples" / "ics" / "trs80_model4" / "trs80_model4_peripherals.yaml",
    ]
    device_paths = [
        BASE_DIR / "examples" / "devices" / "trs80_model4" / "trs80_keyboard.yaml",
        BASE_DIR / "examples" / "devices" / "trs80_model4" / "trs80_video.yaml",
        BASE_DIR / "examples" / "devices" / "trs80_model4" / "trs80_speaker.yaml",
    ]
    host_paths = [
        BASE_DIR / "examples" / "hosts" / "trs80_model4" / "trs80_host_sdl2_interactive.yaml",
    ]
    return processor_path, system_path, ic_paths, device_paths, host_paths


def test_trs80_keyboard_matrix_codegen_uses_address_synthesized_logic(tmp_path):
    processor_path, system_path, ic_paths, device_paths, host_paths = _trs80_interactive_paths()
    outdir = tmp_path / "trs80_model4_kb_build"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        ic_paths=[str(path) for path in ic_paths],
        device_paths=[str(path) for path in device_paths],
        host_paths=[str(path) for path in host_paths],
    )
    c_src = (outdir / "src" / "Z80.c").read_text(encoding="utf-8")

    # Matrix is synthesized from address-selected row lines into column bits.
    assert "uint8_t row_lines = (uint8_t)(addr & 0xFFu);" in c_src
    assert "if ((row_lines & (uint8_t)(1u << row)) != 0u)" in c_src
    assert "uint8_t col_pressed = 0u;" in c_src
    assert "if ((row_values[row] & (uint8_t)(1u << col)) == 0u)" in c_src
    assert "v |= (uint8_t)(1u << col);" in c_src

    # Host SDL key rows stay active-low; masked non-existent keys remain unpressed.
    assert "row_values[row] = (uint8_t)((host_row & kb_mask[row]) | ((uint8_t)(~kb_mask[row])));" in c_src

    # Legacy one-hot mirror helper path should stay removed.
    assert "kb_column_addr" not in c_src


def test_trs80_interactive_host_bindings_cover_caps_and_punctuation():
    processor_path, system_path, ic_paths, device_paths, host_paths = _trs80_interactive_paths()
    data = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        [str(path) for path in ic_paths],
        [str(path) for path in device_paths],
        [str(path) for path in host_paths],
    )
    host = next(comp for comp in data["hosts"] if comp["metadata"]["id"] == "host_trs80_sdl2")
    assert host["input"]["keyboard"]["focus_required"] is True
    bindings = host["input"]["keyboard"]["bindings"]
    binding_map = {b["host_key"]: {(p["row"], p["bit"]) for p in b["presses"]} for b in bindings}

    assert (0, 0) in binding_map["F5"]
    assert (0, 0) in binding_map["LEFTBRACKET"]

    assert (5, 2) in binding_map["MINUS"]
    assert (5, 3) in binding_map["SEMICOLON"]
    assert (5, 5) in binding_map["EQUALS"]

    assert (7, 2) in binding_map["RCTRL"]
    assert (7, 3) in binding_map["F4"]
    assert (7, 3) in binding_map["CAPSLOCK"]
    assert (6, 0) in binding_map["KP_ENTER"]
    assert (6, 5) in binding_map["BACKSPACE"]
    assert (6, 5) in binding_map["DELETE"]
    assert (5, 1) in binding_map["KP_9"]


@pytest.mark.skipif(
    (shutil.which("cc") is None and shutil.which("gcc") is None and shutil.which("clang") is None),
    reason="C compiler not available on PATH",
)
def test_trs80_keyboard_matrix_runtime_row_column_behavior(tmp_path):
    processor_path, _ = example_pair("z80", system="z80_trs80_model4_default.yaml")
    system_path = (
        BASE_DIR / "examples" / "systems" / "trs80_model4" / "z80_trs80_model4_default.yaml"
    )
    ic_paths = [
        BASE_DIR / "examples" / "ics" / "trs80_model4" / "trs80_model4_peripherals.yaml",
    ]
    device_paths = [
        BASE_DIR / "examples" / "devices" / "trs80_model4" / "trs80_keyboard.yaml",
        BASE_DIR / "examples" / "devices" / "trs80_model4" / "trs80_video.yaml",
        BASE_DIR / "examples" / "devices" / "trs80_model4" / "trs80_speaker.yaml",
    ]

    host_yaml = tmp_path / "trs80_host_matrix_test.yaml"
    host_data = {
        "metadata": {
            "id": "host_trs80",
            "type": "host_adapter",
            "model": "trs80_headless_matrix_test",
            "version": "1.0",
        },
        "backend": {"target": "stub"},
        "state": [
            {"name": "row0", "type": "uint8_t", "initial": "0xFF"},
            {"name": "row1", "type": "uint8_t", "initial": "0xFF"},
            {"name": "row2", "type": "uint8_t", "initial": "0xFF"},
            {"name": "row3", "type": "uint8_t", "initial": "0xFF"},
            {"name": "row4", "type": "uint8_t", "initial": "0xFF"},
            {"name": "row5", "type": "uint8_t", "initial": "0xFF"},
            {"name": "row6", "type": "uint8_t", "initial": "0xFF"},
            {"name": "row7", "type": "uint8_t", "initial": "0xFF"},
            {"name": "frame_count", "type": "uint32_t", "initial": "0"},
            {"name": "irq_edges", "type": "uint32_t", "initial": "0"},
            {"name": "audio_samples", "type": "uint32_t", "initial": "0"},
        ],
        "interfaces": {
            "callbacks": [{"name": "keyboard_matrix", "args": ["u8"], "returns": "u8"}],
            "handlers": [
                {"name": "video_frame", "args": ["u32", "u64", "u32", "u32"]},
                {"name": "irq_edge", "args": ["u8"]},
                {"name": "audio_pcm", "args": ["u8", "u64"]},
            ],
            "signals": [],
        },
        "behavior": {
            "snippets": {},
            "callback_handlers": {
                "keyboard_matrix": (
                    "uint8_t row = (argc > 0) ? (uint8_t)(args[0] & 0x0Fu) : 0xFFu;\n"
                    "switch (row) {\n"
                    "    case 0u: return (uint64_t)comp->row0;\n"
                    "    case 1u: return (uint64_t)comp->row1;\n"
                    "    case 2u: return (uint64_t)comp->row2;\n"
                    "    case 3u: return (uint64_t)comp->row3;\n"
                    "    case 4u: return (uint64_t)comp->row4;\n"
                    "    case 5u: return (uint64_t)comp->row5;\n"
                    "    case 6u: return (uint64_t)comp->row6;\n"
                    "    case 7u: return (uint64_t)comp->row7;\n"
                    "    default: return 0xFFu;\n"
                    "}\n"
                )
            },
            "handler_bodies": {
                "video_frame": "comp->frame_count = (uint32_t)(args[0] & 0xFFFFFFFFu);",
                "irq_edge": (
                    "if (argc > 0 && ((args[0] & 0xFFu) != 0u)) { "
                    "comp->irq_edges += 1u; }"
                ),
                "audio_pcm": "comp->audio_samples += 1u;",
            },
        },
        "coding": {
            "headers": [],
            "include_paths": [],
            "linked_libraries": [],
            "library_paths": [],
        },
    }
    host_yaml.write_text(yaml.safe_dump(host_data, sort_keys=False), encoding="utf-8")

    outdir = tmp_path / "trs80_runtime_kb_build"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        ic_paths=[str(path) for path in ic_paths],
        device_paths=[str(path) for path in device_paths],
        host_paths=[str(host_yaml)],
    )

    harness_c = outdir / "trs80_kb_matrix_harness.c"
    harness_c.write_text(
        """
#include <stdio.h>
#include "Z80.h"

int main(void) {
    CPUState *cpu = z80_create(65536);
    if (!cpu) return 2;

    cpu->pc = 0x4000;
    z80_write_byte(cpu, 0x4000, 0x00); /* NOP */

    cpu->comp_host_trs80.row0 = 0xFFu;
    cpu->comp_host_trs80.row1 = 0xFFu;
    cpu->comp_host_trs80.row2 = 0xFFu;
    cpu->comp_host_trs80.row3 = 0xFFu;
    cpu->comp_host_trs80.row4 = 0xFFu;
    cpu->comp_host_trs80.row5 = 0xFFu;
    cpu->comp_host_trs80.row6 = 0xFEu; /* Enter key: row 6, column 0 */
    cpu->comp_host_trs80.row7 = 0xFFu;

    z80_step(cpu);
    printf("ROW0=%02X\\n", (unsigned int)z80_read_byte(cpu, 0x3801));
    printf("ROW6=%02X\\n", (unsigned int)z80_read_byte(cpu, 0x3840));

    cpu->comp_host_trs80.row6 = 0xFFu;
    cpu->comp_host_trs80.row0 = 0xFDu; /* A key: row 0, column 1 */
    z80_step(cpu);
    printf("A_ROW0=%02X\\n", (unsigned int)z80_read_byte(cpu, 0x3801));
    printf("A_ROW6=%02X\\n", (unsigned int)z80_read_byte(cpu, 0x3840));

    z80_destroy(cpu);
    return 0;
}
""",
        encoding="utf-8",
    )

    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    binary_name = "trs80_kb_matrix_harness.exe" if os.name == "nt" else "trs80_kb_matrix_harness"
    binary = outdir / binary_name
    subprocess.check_call(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-D_POSIX_C_SOURCE=199309L",
            "-I",
            str(outdir / "src"),
            "-I",
            str(BASE_DIR / "examples" / "hosts" / "include"),
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
    assert "ROW0=00" in proc.stdout
    assert "ROW6=01" in proc.stdout
    assert "A_ROW0=02" in proc.stdout
    assert "A_ROW6=00" in proc.stdout
