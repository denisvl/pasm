import os
import pathlib
import shutil
import subprocess
import json

import pytest
import yaml

from src import generator as gen_mod
from src.codegen.build_system import generate_cmake, generate_makefile
from src.codegen.cpu_decoder import generate_decoder
from src.codegen.cpu_header import generate_cpu_header
from src.codegen.cpu_impl import generate_cpu_impl
from src.parser import yaml_loader
from tests.support import example_pair, write_pair_from_legacy


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _base_isa(name: str) -> dict:
    return {
        "metadata": {
            "name": name,
            "version": "1.0",
            "bits": 8,
            "address_bits": 16,
            "endian": "little",
        },
        "registers": [
            {"name": "R0", "type": "general", "bits": 8},
            {"name": "R1", "type": "general", "bits": 8},
            {"name": "PC", "type": "program_counter", "bits": 16},
            {"name": "SP", "type": "stack_pointer", "bits": 16},
        ],
        "flags": [{"name": "Z", "bit": 0}, {"name": "C", "bit": 1}, {"name": "N", "bit": 2}],
        "memory": {"address_bits": 16, "default_size": 65536},
        "instructions": [
            {
                "name": "NOP",
                "category": "control",
                "encoding": {"opcode": 0x00, "mask": 0xFF, "length": 1},
                "cycles": 1,
                "behavior": "(void)cpu;",
            }
        ],
    }


def test_behavior_validation_rejects_legacy_operand_access():
    isa = _base_isa("LegacyInst8")
    isa["instructions"] = [
        {
            "name": "LEGACY",
            "category": "arithmetic",
            "encoding": {
                "opcode": 0x10,
                "mask": 0xFF,
                "length": 2,
                "fields": [{"name": "imm", "position": [15, 8], "type": "immediate"}],
            },
            "cycles": 2,
            "behavior": """
cpu->registers[REG_R0] = inst.imm;
""",
        }
    ]

    with pytest.raises(ValueError, match="pointer-style operands"):
        generate_cpu_impl(isa, "LegacyInst8")


def test_behavior_validation_rejects_legacy_helper_access():
    isa = _base_isa("LegacyHelper8")
    isa["instructions"] = [
        {
            "name": "LEGACY",
            "category": "arithmetic",
            "encoding": {"opcode": 0x10, "mask": 0xFF, "length": 1},
            "cycles": 2,
            "behavior": "cpu->flags.Z = (cpu_read_byte(cpu, 0) == 0);",
        }
    ]

    with pytest.raises(ValueError, match="CPU-prefixed helpers"):
        generate_cpu_impl(isa, "LegacyHelper8")


def test_behavior_validation_rejects_unknown_flag():
    isa = _base_isa("BadFlag8")
    isa["instructions"] = [
        {
            "name": "BAD",
            "category": "arithmetic",
            "encoding": {"opcode": 0x10, "mask": 0xFF, "length": 1},
            "cycles": 1,
            "behavior": "cpu->flags.Q = 1;",
        }
    ]

    with pytest.raises(ValueError, match="Unknown flag"):
        generate_cpu_impl(isa, "BadFlag8")


def test_decoder_masks_are_rendered_as_hex_bitmasks():
    isa = _base_isa("Decode8")
    isa["instructions"] = [
        {
            "name": "IMM8",
            "category": "data_transfer",
            "encoding": {
                "opcode": 0x10,
                "mask": 0xFF,
                "length": 2,
                "fields": [{"name": "imm", "position": [7, 0], "type": "immediate"}],
            },
            "cycles": 1,
            "behavior": "(void)cpu;",
        },
        {
            "name": "ADDR16",
            "category": "control",
            "encoding": {
                "opcode": 0x20,
                "mask": 0xFF,
                "length": 3,
                "fields": [{"name": "addr", "position": [23, 8], "type": "address"}],
            },
            "cycles": 1,
            "behavior": "(void)cpu;",
        },
    ]

    _, decoder_impl = generate_decoder(isa, "Decode8")
    assert "0xFF;" in decoder_impl
    assert "0xFFFF;" in decoder_impl
    assert "0x255" not in decoder_impl
    assert "0x65535" not in decoder_impl


def test_cmake_template_does_not_reference_runtime_stub():
    isa = _base_isa("Build8")
    cmake = generate_cmake(isa, "Build8")
    assert "_runtime.c" not in cmake


def test_cmake_emits_linkable_emulator_library_target():
    isa = _base_isa("BuildLib8")
    cmake = generate_cmake(isa, "BuildLib8")
    assert "add_library(buildlib8_emu STATIC ${EMU_SOURCES})" in cmake
    assert "add_executable(buildlib8_test src/main.c)" in cmake
    assert "target_link_libraries(buildlib8_test PRIVATE buildlib8_emu)" in cmake


def test_makefile_emits_linkable_emulator_library_target():
    isa = _base_isa("BuildLib8")
    makefile = generate_makefile(isa, "BuildLib8")
    assert "EMU_LIB = libbuildlib8_emu.a" in makefile
    assert "$(TARGET): $(MAIN_OBJ) $(EMU_LIB)" in makefile
    assert "$(EMU_LIB): $(OBJECTS)" in makefile


def test_build_system_normalizes_windows_paths_for_cross_platform_outputs():
    isa = _base_isa("BuildPath8")
    isa["coding"] = {
        "headers": [],
        "include_paths": [r"D:\Projects\pasm\examples\hosts\include"],
        "linked_libraries": [
            {"name": "SDL2"},
            {"path": r"D:\Development\vcpkg\installed\x64-windows\lib\SDL2.lib"},
        ],
        "library_paths": [r"D:\Development\vcpkg\installed\x64-windows\lib"],
    }

    cmake = generate_cmake(isa, "BuildPath8")
    makefile = generate_makefile(isa, "BuildPath8")

    assert r"D:\Projects\pasm\examples\hosts\include" not in cmake
    assert r"D:\Development\vcpkg\installed\x64-windows\lib\SDL2.lib" not in cmake
    assert r"D:\Development\vcpkg\installed\x64-windows\lib" not in cmake
    assert '"D:/Projects/pasm/examples/hosts/include"' in cmake
    assert '"D:/Development/vcpkg/installed/x64-windows/lib/SDL2.lib"' in cmake
    assert '"D:/Development/vcpkg/installed/x64-windows/lib"' in cmake
    assert '-I"D:/Projects/pasm/examples/hosts/include"' in makefile
    assert '-L"D:/Development/vcpkg/installed/x64-windows/lib"' in makefile
    assert '"D:/Development/vcpkg/installed/x64-windows/lib/SDL2.lib"' in makefile


def test_memory_read_only_regions_emit_write_guards():
    isa = _base_isa("MemGuard8")
    isa["memory"]["regions"] = [
        {"name": "RAM", "start": 0x0000, "size": 0x8000, "read_write": True},
        {"name": "ROM", "start": 0x8000, "size": 0x8000, "read_only": True},
    ]

    code = generate_cpu_impl(isa, "MemGuard8")
    assert "Block writes to read-only region: ROM" in code
    assert "if (addr >= 0x8000u) {" in code
    assert "cpu->error_code = CPU_ERROR_INVALID_MEMORY;" in code


@pytest.mark.skipif(
    (shutil.which("cc") is None and shutil.which("gcc") is None and shutil.which("clang") is None),
    reason="C compiler not available on PATH",
)
def test_runtime_blocks_writes_to_read_only_regions(tmp_path):
    isa = _base_isa("MemRuntime8")
    isa["memory"]["regions"] = [
        {"name": "RAM", "start": 0x0000, "size": 0x8000, "read_write": True},
        {"name": "ROM", "start": 0x8000, "size": 0x8000, "read_only": True},
    ]
    processor_path, system_path = write_pair_from_legacy(tmp_path, "mem_runtime8", isa)

    outdir = tmp_path / "mem_runtime8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    harness_c = outdir / "rom_guard_harness.c"
    harness_c.write_text(
        """
#include <stdio.h>
#include "MemRuntime8.h"

int main(void) {
    CPUState *cpu = memruntime8_create(65536);
    if (!cpu) return 2;

    memruntime8_write_byte(cpu, 0x1000, 0xA5);
    unsigned int ram = (unsigned int)memruntime8_read_byte(cpu, 0x1000);
    int err_after_ram = cpu->error_code;

    cpu->error_code = CPU_ERROR_NONE;
    memruntime8_write_byte(cpu, 0x8000, 0x5A);
    unsigned int rom = (unsigned int)memruntime8_read_byte(cpu, 0x8000);
    int err_after_rom = cpu->error_code;

    printf("RAM=%02X\\n", ram);
    printf("ROM=%02X\\n", rom);
    printf("ERR_RAM=%d\\n", err_after_ram);
    printf("ERR_ROM=%d\\n", err_after_rom);

    memruntime8_destroy(cpu);
    return 0;
}
""",
        encoding="utf-8",
    )

    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    binary_name = "rom_guard_harness.exe" if os.name == "nt" else "rom_guard_harness"
    binary = outdir / binary_name
    subprocess.check_call(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-I",
            str(outdir / "src"),
            str(outdir / "src" / "MemRuntime8.c"),
            str(outdir / "src" / "MemRuntime8_decoder.c"),
            str(harness_c),
            "-o",
            str(binary),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    proc = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    assert "RAM=A5" in proc.stdout
    assert "ROM=00" in proc.stdout
    assert "ERR_RAM=0" in proc.stdout
    assert "ERR_ROM=2" in proc.stdout


def test_system_rom_loader_api_is_emitted(tmp_path):
    isa = _base_isa("RomApi8")
    isa["memory"]["regions"] = [
        {"name": "ROM", "start": 0x8000, "size": 0x8000, "read_only": True},
    ]
    processor_path, system_path = write_pair_from_legacy(
        tmp_path,
        "rom_api8",
        isa,
        system_overrides={
            "memory": {
                "regions": isa["memory"]["regions"],
            }
        },
    )
    system_data = yaml.safe_load(pathlib.Path(system_path).read_text(encoding="utf-8"))
    system_data["memory"]["rom_images"] = [
        {
            "name": "test_rom",
            "file": "rom.bin",
            "target_region": "ROM",
            "offset": 0,
        }
    ]
    pathlib.Path(system_path).write_text(
        yaml.safe_dump(system_data, sort_keys=False), encoding="utf-8"
    )
    (tmp_path / "rom.bin").write_bytes(b"\x01\x02\x03")

    outdir = tmp_path / "rom_api8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))
    header = (outdir / "src" / "RomApi8.h").read_text(encoding="utf-8")
    impl = (outdir / "src" / "RomApi8.c").read_text(encoding="utf-8")

    assert "int romapi8_load_system_roms(CPUState *cpu, const char *system_base_dir);" in header
    assert "static const SystemRomImage g_system_rom_images[]" in impl
    assert "int romapi8_load_system_roms(CPUState *cpu, const char *system_base_dir)" in impl


def test_cartridge_loader_api_is_emitted():
    isa = _base_isa("CartApi8")
    isa["cartridge"] = {
        "metadata": {"id": "cart0", "type": "cartridge_mapper", "model": "none"},
        "state": [
            {"name": "rom_data", "type": "uint8_t *", "initial": "NULL"},
            {"name": "rom_size", "type": "uint32_t", "initial": "0"},
        ],
        "interfaces": {"callbacks": [], "handlers": [], "signals": []},
        "behavior": {
            "snippets": {
                "mem_read_pre": (
                    "if (addr < 0xC000u && comp->rom_data != NULL && comp->rom_size > 0u) {\n"
                    "    uint32_t off = (uint32_t)addr;\n"
                    "    if (off < comp->rom_size) return comp->rom_data[off];\n"
                    "    return 0xFFu;\n"
                    "}"
                )
            },
            "callback_handlers": {},
            "handler_bodies": {},
        },
        "coding": {
            "headers": [],
            "include_paths": [],
            "linked_libraries": [],
            "library_paths": [],
        },
    }
    isa["cartridge_rom"] = {"path": "/tmp/test.rom"}
    header = generate_cpu_header(isa, "CartApi8")
    impl = generate_cpu_impl(isa, "CartApi8")

    assert "int cartapi8_load_cartridge_rom(CPUState *cpu, const char *path);" in header
    assert "int cartapi8_load_cartridge_rom(CPUState *cpu, const char *path)" in impl
    assert "comp->rom_data = buf;" in impl
    assert "comp->rom_size = (uint32_t)file_size;" in impl


def test_generator_emits_debug_abi_files(tmp_path):
    isa = _base_isa("DbgApi8")
    processor_path, system_path = write_pair_from_legacy(tmp_path, "dbg_api8", isa)
    outdir = tmp_path / "dbg_api8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    dbg_h = outdir / "src" / "DbgApi8_debug_abi.h"
    dbg_c = outdir / "src" / "DbgApi8_debug_abi.c"
    assert dbg_h.exists()
    assert dbg_c.exists()
    header = dbg_h.read_text(encoding="utf-8")
    impl = dbg_c.read_text(encoding="utf-8")
    assert "int dbgapi8_dbg_snapshot_counts(CPUState *cpu, PASMDebugCounts *out_counts);" in header
    assert "int dbgapi8_dbg_snapshot_fill(" in header
    assert "CPUState *pasm_dbg_create(size_t memory_size);" in header
    assert "int pasm_dbg_snapshot_fill(" in header
    assert "int pasm_dbg_set_pc(CPUState *cpu, uint64_t address);" in header
    assert '#include "DbgApi8_debug_abi.h"' in impl
    assert "CPUState *pasm_dbg_create(size_t memory_size)" in impl
    assert "int pasm_dbg_snapshot_fill(" in impl
    assert "int pasm_dbg_set_pc(CPUState *cpu, uint64_t address)" in impl


def test_debug_abi_disasm_row_formats_only_instruction_length_bytes(tmp_path):
    isa = _base_isa("DbgBytes8")
    isa["instructions"] = [
        {
            "name": "NOP",
            "category": "control",
            "encoding": {"opcode": 0x00, "mask": 0xFF, "length": 1},
            "cycles": 1,
            "behavior": "(void)cpu;",
        },
        {
            "name": "LDI",
            "category": "data_transfer",
            "encoding": {
                "opcode": 0x3E,
                "mask": 0xFF,
                "length": 2,
                "fields": [{"name": "n", "position": [15, 8], "type": "immediate"}],
            },
            "cycles": 1,
            "behavior": "(void)cpu;",
        },
    ]
    processor_path, system_path = write_pair_from_legacy(tmp_path, "dbg_bytes8", isa)
    outdir = tmp_path / "dbg_bytes8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    impl = (outdir / "src" / "DbgBytes8_debug_abi.c").read_text(encoding="utf-8")
    assert "len = dbg_instruction_len(cpu, addr);" in impl
    assert "for (uint8_t i = 0u; i < len" in impl
    assert "\"%02X %02X %02X %02X\"" not in impl


def test_debug_abi_uses_register_display_name_when_present(tmp_path):
    isa = _base_isa("DbgLabel8")
    isa["registers"][0]["display_name"] = "ACC"
    processor_path, system_path = write_pair_from_legacy(tmp_path, "dbg_label8", isa)
    outdir = tmp_path / "dbg_label8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    impl = (outdir / "src" / "DbgLabel8_debug_abi.c").read_text(encoding="utf-8")
    assert 'dbg_copy(r->name, sizeof(r->name), "ACC");' in impl


def test_debug_abi_special_registers_use_register_bank_values(tmp_path):
    isa = _base_isa("DbgSpecial8")
    isa["registers"].append({"name": "I", "type": "special", "bits": 8})
    processor_path, system_path = write_pair_from_legacy(tmp_path, "dbg_special8", isa)
    outdir = tmp_path / "dbg_special8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    impl = (outdir / "src" / "DbgSpecial8_debug_abi.c").read_text(encoding="utf-8")
    assert "uint64_t val = (uint64_t)(cpu->registers[REG_I]);" in impl


def test_generator_emits_debugger_link_manifest(tmp_path):
    isa = _base_isa("DbgLink8")
    processor_path, system_path = write_pair_from_legacy(tmp_path, "dbg_link8", isa)
    outdir = tmp_path / "dbg_link8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    manifest_path = outdir / "debugger_link.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["cpu_name"] == "DbgLink8"
    assert manifest["cpu_prefix"] == "dbglink8"
    assert manifest["library_basename"] == "dbglink8_emu"
    assert manifest["headers"]["debug_abi"] == "src/DbgLink8_debug_abi.h"
    assert "link" in manifest
    assert isinstance(manifest["link"]["library_names"], list)


@pytest.mark.skipif(
    (shutil.which("cc") is None and shutil.which("gcc") is None and shutil.which("clang") is None),
    reason="C compiler not available on PATH",
)
def test_runtime_loads_system_rom_images(tmp_path):
    isa = _base_isa("RomLoad8")
    isa["memory"]["regions"] = [
        {"name": "ROM", "start": 0x8000, "size": 0x8000, "read_only": True},
    ]
    processor_path, system_path = write_pair_from_legacy(
        tmp_path,
        "rom_load8",
        isa,
        system_overrides={
            "memory": {
                "regions": isa["memory"]["regions"],
            }
        },
    )
    system_data = yaml.safe_load(pathlib.Path(system_path).read_text(encoding="utf-8"))
    system_data["memory"]["rom_images"] = [
        {
            "name": "test_rom",
            "file": "rom.bin",
            "target_region": "ROM",
            "offset": 2,
        }
    ]
    pathlib.Path(system_path).write_text(
        yaml.safe_dump(system_data, sort_keys=False), encoding="utf-8"
    )
    (tmp_path / "rom.bin").write_bytes(bytes([0x11, 0x22, 0x33]))

    outdir = tmp_path / "rom_load8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    harness_c = outdir / "rom_loader_harness.c"
    harness_c.write_text(
        """
#include <stdio.h>
#include "RomLoad8.h"

int main(void) {
    CPUState *cpu = romload8_create(65536);
    if (!cpu) return 2;
    if (romload8_load_system_roms(cpu, ".") != 0) return 3;

    printf("R0=%02X\\n", (unsigned int)romload8_read_byte(cpu, 0x8002));
    printf("R1=%02X\\n", (unsigned int)romload8_read_byte(cpu, 0x8003));
    printf("R2=%02X\\n", (unsigned int)romload8_read_byte(cpu, 0x8004));

    romload8_destroy(cpu);
    return 0;
}
""",
        encoding="utf-8",
    )

    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    binary_name = "rom_loader_harness.exe" if os.name == "nt" else "rom_loader_harness"
    binary = outdir / binary_name
    subprocess.check_call(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-I",
            str(outdir / "src"),
            str(outdir / "src" / "RomLoad8.c"),
            str(outdir / "src" / "RomLoad8_decoder.c"),
            str(harness_c),
            "-o",
            str(binary),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    proc = subprocess.run([str(binary)], check=True, capture_output=True, text=True, cwd=tmp_path)
    assert "R0=11" in proc.stdout
    assert "R1=22" in proc.stdout
    assert "R2=33" in proc.stdout


def test_generated_main_resets_after_system_rom_load_and_preserves_direct_rom_entry(tmp_path):
    isa = _base_isa("MainBoot8")
    isa["interrupts"] = {"model": "mos6502"}
    isa["registers"] = [
        {"name": "A", "type": "general", "bits": 8},
        {"name": "X", "type": "general", "bits": 8},
        {"name": "Y", "type": "general", "bits": 8},
        {"name": "PC", "type": "program_counter", "bits": 16},
        {"name": "SP", "type": "stack_pointer", "bits": 8},
    ]
    isa["flags"] = [
        {"name": "C", "bit": 0},
        {"name": "Z", "bit": 1},
        {"name": "I", "bit": 2},
        {"name": "D", "bit": 3},
        {"name": "B", "bit": 4},
        {"name": "V", "bit": 6},
        {"name": "N", "bit": 7},
    ]
    isa["memory"]["regions"] = [
        {"name": "RAM", "start": 0x0000, "size": 0xD000, "read_write": True},
        {"name": "ROM", "start": 0xD000, "size": 0x3000, "read_only": True},
    ]
    processor_path, system_path = write_pair_from_legacy(
        tmp_path,
        "main_boot8",
        isa,
        system_overrides={
            "memory": {
                "regions": isa["memory"]["regions"],
                "rom_images": [
                    {
                        "name": "boot_rom",
                        "file": "boot.bin",
                        "target_region": "ROM",
                        "offset": 0,
                    }
                ],
            }
        },
    )
    (tmp_path / "boot.bin").write_bytes(b"\x00" * 0x3000)

    outdir = tmp_path / "main_boot8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    main_c = (outdir / "src" / "main.c").read_text(encoding="utf-8")
    assert "if (mainboot8_load_system_roms(cpu, system_dir) != 0) {" in main_c
    assert "mainboot8_reset(cpu);" in main_c
    assert "cpu->pc = load_addr;" in main_c


@pytest.mark.parametrize(
    ("hooks", "expect_hooks_file", "expect_post_execute_call"),
    [
        ({}, False, False),
        ({"pre_fetch": {"enabled": True}}, True, False),
        ({"post_decode": {"enabled": True}}, True, False),
        ({"post_execute": {"enabled": True}}, True, True),
        (
            {
                "pre_fetch": {"enabled": True},
                "post_decode": {"enabled": True},
                "post_execute": {"enabled": True},
            },
            True,
            True,
        ),
    ],
)
def test_hook_generation_matrix(tmp_path, hooks, expect_hooks_file, expect_post_execute_call):
    isa = _base_isa("Hook8")
    isa["hooks"] = hooks

    processor_path, system_path = write_pair_from_legacy(tmp_path, "hook8", isa)

    outdir = tmp_path / "hook8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    hooks_file = outdir / "src" / "Hook8_hooks.c"
    assert hooks_file.exists() == expect_hooks_file

    impl_c = (outdir / "src" / "Hook8.c").read_text()
    has_post_execute = (
        "HOOK_POST_EXECUTE" in impl_c
        and "CPUHookEvent event" in impl_c
        and "func(cpu, &event, cpu->hooks[HOOK_POST_EXECUTE].context)" in impl_c
    )
    assert has_post_execute == expect_post_execute_call


def test_hook_api_uses_event_callback_contract(tmp_path):
    isa = _base_isa("HookApi8")
    isa["hooks"] = {"post_execute": {"enabled": True}}
    processor_path, system_path = write_pair_from_legacy(tmp_path, "hookapi8", isa)
    outdir = tmp_path / "hookapi8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    header = (outdir / "src" / "HookApi8.h").read_text()
    hooks_h = (outdir / "src" / "HookApi8_hooks.h").read_text()
    assert "HOOK_PORT_READ_PRE" in header
    assert "HOOK_PORT_WRITE_POST" in header
    assert "HOOK_COUNT = 7" in header
    assert "typedef struct {" in header and "CPUHookEvent;" in header
    assert "CPUHookFunc" in hooks_h


def test_dispatch_includes_pc_progression_guard():
    isa = _base_isa("Flow8")
    code = generate_cpu_impl(isa, "Flow8")
    assert "cpu->pc_modified = false;" in code
    assert "if (!cpu->pc_modified)" in code
    assert "cpu->pc = (uint16_t)(pc_before + inst.length);" in code
    assert "if (cpu->tracing_enabled)" in code
    assert "flow8_trace_instruction(cpu, &inst);" in code


def test_behavior_normalization_wraps_pc_assignments():
    isa = _base_isa("FlowNorm8")
    isa["instructions"] = [
        {
            "name": "JUMP",
            "category": "control",
            "encoding": {
                "opcode": 0xC3,
                "mask": 0xFF,
                "length": 3,
                "fields": [{"name": "addr", "position": [23, 8], "type": "address"}],
            },
            "cycles": 1,
            "behavior": "cpu->pc = inst->addr;",
        }
    ]

    code = generate_cpu_impl(isa, "FlowNorm8")
    assert "cpu->pc = inst->addr;" in code
    assert "cpu->pc_modified = true;" in code


def test_debug_api_symbols_are_generated(tmp_path):
    processor_path, system_path = example_pair("minimal8")
    outdir = tmp_path / "debug_api"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    header = (outdir / "src" / "Minimal8.h").read_text()
    impl = (outdir / "src" / "Minimal8.c").read_text()

    assert "minimal8_dump_stack(CPUState *cpu, int depth);" in header
    assert "minimal8_list_breakpoints(CPUState *cpu);" in header
    assert "minimal8_trace_instruction(CPUState *cpu, DecodedInstruction *inst);" in header
    assert "char *minimal8_disassemble_instruction(uint16_t pc, uint32_t raw);" in header

    assert "void minimal8_dump_stack(CPUState *cpu, int depth)" in impl
    assert "void minimal8_list_breakpoints(CPUState *cpu)" in impl
    assert "void minimal8_trace_instruction(CPUState *cpu, DecodedInstruction *inst)" in impl
    assert "char *minimal8_disassemble_instruction(uint16_t pc, uint32_t raw)" in impl
    assert 'mnemonic = "NOP";' in impl
    assert 'mnemonic = "INC";' in impl


def test_disassembler_prefers_display_text_when_present():
    isa = _base_isa("Display8")
    isa["instructions"] = [
        {
            "name": "RLC_IYD",
            "display": "RLC (IY+d)",
            "category": "rotate",
            "encoding": {
                "prefix": 0xFD,
                "opcode": 0xCB,
                "subop": 0x06,
                "length": 4,
                "fields": [{"name": "disp", "position": [15, 8], "type": "immediate"}],
            },
            "cycles": 1,
            "behavior": "(void)cpu;",
        }
    ]

    impl = generate_cpu_impl(isa, "Display8")
    assert (
        'mnemonic = "RLC (IY+d)";' in impl
        or 'snprintf(rendered, sizeof(rendered), "RLC (IY+%s)"' in impl
    )
    assert 'mnemonic = "RLC_IYD";' not in impl


def test_disassembler_supports_display_templates_with_operand_tables():
    isa = _base_isa("DisplayTpl8")
    isa["instructions"] = [
        {
            "name": "LD_R_R",
            "display": "LD r, r'",
            "display_template": "LD {rd:table}, {rs:table}",
            "display_operands": {
                "rd": {"kind": "table", "table": ["B", "C", "D", "E", "H", "L", "(HL)", "A"]},
                "rs": {"kind": "table", "table": ["B", "C", "D", "E", "H", "L", "(HL)", "A"]},
            },
            "category": "data_transfer",
            "encoding": {
                "opcode": 0x40,
                "mask": 0xC0,
                "length": 1,
                "fields": [
                    {"name": "rd", "position": [5, 3], "type": "register"},
                    {"name": "rs", "position": [2, 0], "type": "register"},
                ],
            },
            "cycles": 1,
            "behavior": "(void)cpu;",
        }
    ]

    impl = generate_cpu_impl(isa, "DisplayTpl8")
    assert "op_table_LD_R_R_rd_0" in impl
    assert "op_table_LD_R_R_rs_1" in impl
    assert 'snprintf(rendered, sizeof(rendered), "LD %s, %s"' in impl
    assert 'mnemonic = "LD r, r\'";' not in impl


def test_disassembler_supports_mc6809_stack_mask_display_formatter():
    isa = _base_isa("Display6809Mask")
    isa["instructions"] = [
        {
            "name": "PSHS",
            "display": "PSHS m",
            "display_template": "PSHS {mask:mc6809_pshs_mask}",
            "category": "control",
            "encoding": {
                "opcode": 0x34,
                "mask": 0xFF,
                "length": 2,
                "fields": [{"name": "mask", "position": [15, 8], "type": "immediate"}],
            },
            "cycles": 1,
            "behavior": "(void)cpu;",
        }
    ]

    impl = generate_cpu_impl(isa, "Display6809Mask")
    assert "dbg_mc6809_format_stack_mask" in impl
    assert '"U", 0u, op_buf_0' in impl
    assert 'snprintf(rendered, sizeof(rendered), "PSHS %s"' in impl


def test_disassembler_infers_mos6502_immediate_and_zero_page_templates():
    isa = _base_isa("MOS6502Display8")
    isa["instructions"] = [
        {
            "name": "LDA_IMM",
            "display": "LDA #n",
            "category": "data_transfer",
            "encoding": {
                "opcode": 0xA9,
                "mask": 0xFF,
                "length": 2,
                "fields": [{"name": "imm", "position": [15, 8], "type": "immediate"}],
            },
            "cycles": 2,
            "behavior": "(void)cpu;",
        },
        {
            "name": "LDA_ZP",
            "display": "LDA n",
            "category": "data_transfer",
            "encoding": {
                "opcode": 0xA5,
                "mask": 0xFF,
                "length": 2,
                "fields": [{"name": "zp", "position": [15, 8], "type": "address"}],
            },
            "cycles": 3,
            "behavior": "(void)cpu;",
        },
        {
            "name": "LDA_INDY",
            "display": "LDA (n),Y",
            "category": "data_transfer",
            "encoding": {
                "opcode": 0xB1,
                "mask": 0xFF,
                "length": 2,
                "fields": [{"name": "zp", "position": [15, 8], "type": "address"}],
            },
            "cycles": 5,
            "behavior": "(void)cpu;",
        },
        {
            "name": "JMP_ABS",
            "display": "JMP nn",
            "category": "control",
            "encoding": {
                "opcode": 0x4C,
                "mask": 0xFF,
                "length": 3,
                "fields": [{"name": "addr", "position": [23, 8], "type": "address"}],
            },
            "cycles": 3,
            "behavior": "(void)cpu;",
        },
    ]

    impl = generate_cpu_impl(isa, "MOS6502Display8")
    assert 'snprintf(rendered, sizeof(rendered), "LDA #%s"' in impl
    assert 'snprintf(rendered, sizeof(rendered), "LDA %s"' in impl
    assert 'snprintf(rendered, sizeof(rendered), "LDA (%s),Y"' in impl
    assert 'snprintf(rendered, sizeof(rendered), "JMP %s"' in impl
    assert 'snprintf(op_buf_0, sizeof(op_buf_0), "$%02X"' in impl
    assert 'snprintf(op_buf_0, sizeof(op_buf_0), "$%04X"' in impl
    assert 'mnemonic = "LDA #n";' not in impl
    assert 'mnemonic = "LDA n";' not in impl
    assert 'mnemonic = "LDA (n),Y";' not in impl
    assert 'mnemonic = "JMP nn";' not in impl
    assert 'snprintf(op_buf_0, sizeof(op_buf_0), "0x%02X"' not in impl
    assert 'snprintf(op_buf_0, sizeof(op_buf_0), "0x%04X"' not in impl


def test_disassembler_rejects_unknown_display_template_field():
    isa = _base_isa("DisplayBadField8")
    isa["instructions"] = [
        {
            "name": "BAD",
            "display_template": "BAD {missing}",
            "category": "control",
            "encoding": {"opcode": 0x00, "mask": 0xFF, "length": 1},
            "cycles": 1,
            "behavior": "(void)cpu;",
        }
    ]

    with pytest.raises(ValueError, match="unknown decoded field"):
        generate_cpu_impl(isa, "DisplayBadField8")


def test_shadow_flags_bank_is_generated_for_prime_register_sets():
    isa = _base_isa("Shadow8")
    isa["registers"].append({"name": "A_PRIME", "type": "general", "bits": 8})
    header = generate_cpu_header(isa, "Shadow8")
    impl = generate_cpu_impl(isa, "Shadow8")

    assert "} flags_prime;" in header
    assert "cpu->flags_prime.raw = 0;" in impl


def test_shadow_flags_bank_is_omitted_without_prime_registers():
    isa = _base_isa("NoShadow8")
    header = generate_cpu_header(isa, "NoShadow8")
    impl = generate_cpu_impl(isa, "NoShadow8")

    assert "} flags_prime;" not in header
    assert "cpu->flags_prime.raw = 0;" not in impl


def test_flags_require_explicit_bit_positions(tmp_path):
    isa = _base_isa("FlagBits8")
    isa["flags"] = [{"name": "Z"}]
    processor_path, system_path = write_pair_from_legacy(tmp_path, "flagbits", isa)

    with pytest.raises(Exception, match="required property"):
        gen_mod.generate(
            str(processor_path), str(system_path), str(tmp_path / "flagbits_out")
        )


def test_duplicate_flag_bit_positions_are_rejected(tmp_path):
    isa = _base_isa("FlagDup8")
    isa["flags"] = [{"name": "Z", "bit": 0}, {"name": "C", "bit": 0}]
    processor_path, system_path = write_pair_from_legacy(tmp_path, "flagdup", isa)

    with pytest.raises(Exception, match="duplicate bit position"):
        gen_mod.generate(
            str(processor_path), str(system_path), str(tmp_path / "flagdup_out")
        )


def test_register_parts_overlap_is_rejected(tmp_path):
    isa = _base_isa("PartsOverlap8")
    isa["registers"].append(
        {
            "name": "AX",
            "type": "general",
            "bits": 8,
            "parts": [
                {"name": "LO", "lsb": 0, "bits": 4},
                {"name": "MID", "lsb": 2, "bits": 4},
            ],
        }
    )
    processor_path, system_path = write_pair_from_legacy(tmp_path, "parts_overlap", isa)

    with pytest.raises(Exception, match="overlapping bit"):
        gen_mod.generate(
            str(processor_path), str(system_path), str(tmp_path / "parts_overlap_out")
        )


def test_register_parts_out_of_range_is_rejected(tmp_path):
    isa = _base_isa("PartsRange8")
    isa["registers"].append(
        {
            "name": "AX",
            "type": "general",
            "bits": 8,
            "parts": [{"name": "HI", "lsb": 7, "bits": 2}],
        }
    )
    processor_path, system_path = write_pair_from_legacy(tmp_path, "parts_range", isa)

    with pytest.raises(Exception, match="exceeds parent width"):
        gen_mod.generate(
            str(processor_path), str(system_path), str(tmp_path / "parts_range_out")
        )


def test_register_parts_emit_yaml_driven_view_fields():
    isa = _base_isa("PartsEmit8")
    isa["registers"].append(
        {
            "name": "AX",
            "type": "general",
            "bits": 16,
            "parts": [
                {"name": "AL", "lsb": 0, "bits": 8},
                {"name": "AH", "lsb": 8, "bits": 8},
            ],
        }
    )
    header = generate_cpu_header(isa, "PartsEmit8")
    assert "AX subdivision view (from YAML parts)" in header
    assert "unsigned long long AL : 8;" in header
    assert "unsigned long long AH : 8;" in header
    assert "} ax;" in header


def test_header_emits_no_flag_helper_macros_or_inline_helpers():
    isa = _base_isa("NoHelpers8")
    header = generate_cpu_header(isa, "NoHelpers8")
    assert "CPU_FLAG_SET_" not in header
    assert "CPU_FLAG_GET_" not in header
    assert "CPU_SET_PC(" not in header
    assert "static inline" not in header
    assert "uint8_t raw;" in header
    assert "unsigned int Z : 1;" in header
    assert "unsigned int C : 1;" in header


def test_header_includes_supported_compiler_gate():
    isa = _base_isa("CompilerGate8")
    header = generate_cpu_header(isa, "CompilerGate8")
    assert "Unsupported compiler: generated code supports MSVC, Clang, and GCC." in header


def test_header_emits_system_metadata_constants():
    isa = _base_isa("SystemMeta8")
    isa["system"] = {
        "metadata": {"name": "DemoSystem", "version": "2.0"},
        "clock_hz": 2000000,
        "integrations": {"demo": {"mode": "test"}},
    }
    header = generate_cpu_header(isa, "SystemMeta8")
    assert '#define CPU_SYSTEM_NAME "DemoSystem"' in header
    assert '#define CPU_SYSTEM_VERSION "2.0"' in header
    assert "#define CPU_SYSTEM_CLOCK_HZ 2000000ULL" in header
    assert "CPU_SYSTEM_INTEGRATIONS_JSON" in header


def test_undefined_opcode_policy_defaults_to_trap():
    isa = _base_isa("TrapDefault8")
    code = generate_cpu_impl(isa, "TrapDefault8")
    assert "cpu->error_code = CPU_ERROR_INVALID_OPCODE;" in code
    invalid_block = code.split("if (!inst.valid) {", 1)[1].split("}", 1)[0]
    assert "cpu->total_cycles += inst.cycles;" not in invalid_block


def test_undefined_opcode_policy_nop_emits_skip_path():
    isa = _base_isa("NopUndef8")
    isa["metadata"]["undefined_opcode_policy"] = "nop"
    code = generate_cpu_impl(isa, "NopUndef8")
    assert "cpu->pc = (uint16_t)(pc_before + inst.length);" in code
    assert "cpu->total_cycles += inst.cycles;" in code
    assert "cpu->error_code = CPU_ERROR_INVALID_OPCODE;" not in code


def test_port_io_hook_points_are_emitted_when_enabled():
    isa = _base_isa("PortHook8")
    isa["hooks"] = {
        "port_read_pre": {"enabled": True},
        "port_read_post": {"enabled": True},
        "port_write_pre": {"enabled": True},
        "port_write_post": {"enabled": True},
    }
    code = generate_cpu_impl(isa, "PortHook8")
    assert "HOOK_PORT_READ_PRE" in code
    assert "HOOK_PORT_READ_POST" in code
    assert "HOOK_PORT_WRITE_PRE" in code
    assert "HOOK_PORT_WRITE_POST" in code
    assert "event = {" in code
    assert ".port = port," in code
    assert ".value = value," in code


@pytest.mark.parametrize(
    ("enabled_hooks", "expected", "unexpected"),
    [
        ({"port_read_pre"}, {"HOOK_PORT_READ_PRE"}, {"HOOK_PORT_READ_POST", "HOOK_PORT_WRITE_PRE", "HOOK_PORT_WRITE_POST"}),
        ({"port_read_post"}, {"HOOK_PORT_READ_POST"}, {"HOOK_PORT_READ_PRE", "HOOK_PORT_WRITE_PRE", "HOOK_PORT_WRITE_POST"}),
        ({"port_write_pre"}, {"HOOK_PORT_WRITE_PRE"}, {"HOOK_PORT_READ_PRE", "HOOK_PORT_READ_POST", "HOOK_PORT_WRITE_POST"}),
        ({"port_write_post"}, {"HOOK_PORT_WRITE_POST"}, {"HOOK_PORT_READ_PRE", "HOOK_PORT_READ_POST", "HOOK_PORT_WRITE_PRE"}),
        (
            {"port_read_pre", "port_read_post", "port_write_pre", "port_write_post"},
            {"HOOK_PORT_READ_PRE", "HOOK_PORT_READ_POST", "HOOK_PORT_WRITE_PRE", "HOOK_PORT_WRITE_POST"},
            set(),
        ),
    ],
)
def test_port_hook_generation_matrix(enabled_hooks, expected, unexpected):
    isa = _base_isa("PortMatrix8")
    isa["hooks"] = {name: {"enabled": (name in enabled_hooks)} for name in ("port_read_pre", "port_read_post", "port_write_pre", "port_write_post")}
    code = generate_cpu_impl(isa, "PortMatrix8")
    for marker in expected:
        assert marker in code
    for marker in unexpected:
        assert marker not in code


def test_decoder_unknown_defaults_include_length_and_cycles():
    isa = _base_isa("Unknown8")
    _, decoder = generate_decoder(isa, "Unknown8")
    assert "inst.length = (prefix != 0) ? 2 : 1;" in decoder
    assert "inst.cycles = 4;" in decoder


def test_decoder_emits_dd_fd_fallback_alias_block():
    isa = _base_isa("DDAlias8")
    isa["instructions"].append(
        {
            "name": "PFX_NOP",
            "category": "control",
            "encoding": {"prefix": 0xDD, "opcode": 0x00, "mask": 0xFF, "length": 2},
            "cycles": 1,
            "behavior": "(void)cpu;",
        }
    )
    _, decoder = generate_decoder(isa, "DDAlias8")
    assert "DD/FD fallback: treat unsupported prefixed forms as base aliases." in decoder
    assert "DecodedInstruction base = ddalias8_decode(raw, 0, pc);" in decoder
    assert "base.length = (uint8_t)(base.length + 1);" in decoder


def test_interrupt_dispatch_block_is_generated_when_interrupts_declared():
    isa = _base_isa("Int8")
    isa["interrupts"] = {"modes": [{"name": "IM0"}]}
    code = generate_cpu_impl(isa, "Int8")
    assert "cpu->interrupt_pending && cpu->interrupts_enabled" in code
    assert "switch (irq_mode)" in code
    assert "cpu->interrupts_enabled = false;" in code


def test_breakpoint_check_precedes_interrupt_dispatch():
    isa = _base_isa("IntBpOrder8")
    isa["interrupts"] = {"modes": [{"name": "IM1"}]}
    code = generate_cpu_impl(isa, "IntBpOrder8")
    bp_idx = code.find("if (cpu_check_breakpoints(cpu)) {")
    irq_idx = code.find("if (cpu->interrupt_pending && cpu->interrupts_enabled) {")
    assert bp_idx >= 0
    assert irq_idx >= 0
    assert bp_idx < irq_idx


def test_interrupt_api_queues_pending_even_when_irq_disabled():
    isa = _base_isa("IntApi8")
    isa["interrupts"] = {"modes": [{"name": "IM1"}]}
    code = generate_cpu_impl(isa, "IntApi8")
    assert "if (!cpu->interrupts_enabled) return;" not in code
    assert "cpu->interrupt_pending = true;" in code


def test_interrupt_mode_gating_and_im2_vector_table_lookup():
    isa = _base_isa("IntMode8")
    isa["registers"].append({"name": "I", "type": "special", "bits": 8})
    isa["interrupts"] = {"modes": [{"name": "IM1"}, {"name": "IM2"}]}
    code = generate_cpu_impl(isa, "IntMode8")
    assert "if (irq_mode != 1 && irq_mode != 2) irq_mode = 1;" in code
    assert "switch (irq_mode) {\n            case 0:" not in code
    assert "case 1:" in code
    assert "case 2:" in code
    assert "cpu->registers[REG_I]" in code
    assert "intmode8_read_word(cpu, vector_addr);" in code


def test_interrupt_header_z80_emits_mode_state_and_api():
    isa = _base_isa("HdrZ808")
    isa["interrupts"] = {"model": "z80", "modes": [{"name": "IM1"}]}
    header = generate_cpu_header(isa, "HdrZ808")
    assert "uint8_t interrupt_mode;" in header
    assert "uint8_t interrupt_vector;" in header
    assert "hdrz808_set_interrupt_mode(CPUState *cpu, uint8_t mode);" in header


def test_interrupt_header_fixed_vector_omits_mode_state_and_api():
    isa = _base_isa("HdrFix8")
    isa["interrupts"] = {"model": "fixed_vector", "fixed_vector": 0x0100}
    header = generate_cpu_header(isa, "HdrFix8")
    assert "uint8_t interrupt_mode;" not in header
    assert "uint8_t interrupt_vector;" in header
    assert "hdrfix8_set_interrupt_mode(CPUState *cpu, uint8_t mode);" not in header


def test_interrupt_model_none_emits_no_state_and_noop_api_impl():
    isa = _base_isa("HdrNone8")
    isa["interrupts"] = {"model": "none"}
    header = generate_cpu_header(isa, "HdrNone8")
    impl = generate_cpu_impl(isa, "HdrNone8")
    assert "uint8_t interrupt_mode;" not in header
    assert "uint8_t interrupt_vector;" not in header
    assert "hdrnone8_set_interrupt_mode(CPUState *cpu, uint8_t mode);" not in header
    assert "(void)vector;" in impl
    assert "(void)enabled;" in impl
    assert "cpu->interrupt_vector = vector;" not in impl


def test_interrupt_model_none_omits_dispatch_even_when_section_present():
    isa = _base_isa("NoIrqModel8")
    isa["interrupts"] = {"model": "none"}
    code = generate_cpu_impl(isa, "NoIrqModel8")
    assert "cpu->interrupt_pending && cpu->interrupts_enabled" not in code


def test_interrupt_model_fixed_vector_generates_direct_jump():
    isa = _base_isa("FixedIrq8")
    isa["interrupts"] = {"model": "fixed_vector", "fixed_vector": 0x1234}
    code = generate_cpu_impl(isa, "FixedIrq8")
    assert "cpu->interrupt_pending && cpu->interrupts_enabled" in code
    assert "cpu->pc = 0x1234;" in code
    assert "switch (irq_mode)" not in code


def test_interrupt_model_mos6502_generates_page1_stack_and_vectors():
    isa = _base_isa("MosIrq8")
    isa["flags"] = [
        {"name": "C", "bit": 0},
        {"name": "Z", "bit": 1},
        {"name": "I", "bit": 2},
        {"name": "D", "bit": 3},
        {"name": "B", "bit": 4},
        {"name": "V", "bit": 6},
        {"name": "N", "bit": 7},
    ]
    isa["interrupts"] = {"model": "mos6502"}
    code = generate_cpu_impl(isa, "MosIrq8")
    assert "0x0100u | sp8" in code
    assert "cpu->sp = 0xFDu;" in code
    assert "cpu->flags.I = true;" in code
    assert "cpu->pc = mosirq8_read_word(cpu, 0xFFFCu);" in code
    assert "read_word(cpu, 0xFFFAu)" in code
    assert "read_word(cpu, 0xFFFEu)" in code


def test_interrupt_model_mc6809_generates_ffi_vectors():
    isa = _base_isa("M6809Irq8")
    isa["flags"] = [
        {"name": "C", "bit": 0},
        {"name": "V", "bit": 1},
        {"name": "Z", "bit": 2},
        {"name": "N", "bit": 3},
        {"name": "I", "bit": 4},
        {"name": "H", "bit": 5},
        {"name": "F", "bit": 6},
        {"name": "E", "bit": 7},
    ]
    isa["interrupts"] = {"model": "mc6809"}
    code = generate_cpu_impl(isa, "M6809Irq8")
    assert "vector_addr = 0xFFF8u;" in code
    assert "vector_addr = 0xFFFCu;" in code
    assert "vector_addr = 0xFFF6u;" in code
    assert "bool full_frame = true;" in code
    assert "cpu->flags.E = true;" in code
    assert "cpu->flags.E = false;" in code
    assert "if (full_frame) {" in code
    assert "cpu->registers[REG_DP]" in code
    assert "(uint8_t)(cpu->u & 0xFFu)" in code
    assert "cpu->flags.F = true;" in code


def test_interrupt_model_validation_rejects_unknown_model():
    isa = _base_isa("BadIrq8")
    isa["interrupts"] = {"model": "custom_model"}
    with pytest.raises(ValueError, match="Unsupported interrupts.model"):
        generate_cpu_impl(isa, "BadIrq8")


def test_interrupt_dispatch_block_is_omitted_without_interrupts_section():
    isa = _base_isa("NoInt8")
    code = generate_cpu_impl(isa, "NoInt8")
    assert "cpu->interrupt_pending && cpu->interrupts_enabled" not in code


def test_dispatch_conditions_guard_non_prefixed_ops_from_prefixed_matches():
    isa = _base_isa("PrefGuard8")
    isa["instructions"] = [
        {
            "name": "BASE",
            "category": "data_transfer",
            "encoding": {"opcode": 0x77, "mask": 0xFF, "length": 1},
            "cycles": 1,
            "behavior": "(void)cpu;",
        },
        {
            "name": "PFX",
            "category": "data_transfer",
            "encoding": {"prefix": 0xDD, "opcode": 0x77, "mask": 0xFF, "length": 2},
            "cycles": 1,
            "behavior": "(void)cpu;",
        },
    ]
    code = generate_cpu_impl(isa, "PrefGuard8")
    assert "(inst.prefix == 0x00 && (inst.opcode == 0x77))" in code
    assert "(inst.prefix == 0xDD && (inst.opcode == 0x77))" in code


def test_dispatch_and_decoder_support_ddcb_disp_subop_form():
    isa = _base_isa("DDCB8")
    isa["instructions"] = [
        {
            "name": "RLC_IXD",
            "category": "rotate",
            "encoding": {
                "prefix": 0xDD,
                "opcode": 0xCB,
                "subop": 0x06,
                "length": 4,
                "fields": [{"name": "disp", "position": [15, 8], "type": "immediate"}],
            },
            "cycles": 1,
            "behavior": "(void)cpu;",
        }
    ]

    code = generate_cpu_impl(isa, "DDCB8")
    _, decoder = generate_decoder(isa, "DDCB8")

    assert "((inst.raw >> 16) & 0x00FF) == 0x06" in code
    assert "((raw >> 16) & 0x00FF) == 0x06" in decoder
    assert "inst.disp = (raw >> 8) & 0xFF;" in decoder


def test_dispatch_and_decoder_support_masked_ddcb_disp_subop_form():
    isa = _base_isa("DDCBMask8")
    isa["instructions"] = [
        {
            "name": "BIT_IXD_R",
            "category": "bit",
            "encoding": {
                "prefix": 0xDD,
                "opcode": 0xCB,
                "subop": 0x40,
                "subop_mask": 0xC0,
                "length": 4,
                "fields": [
                    {"name": "disp", "position": [15, 8], "type": "immediate"},
                    {"name": "bit", "position": [21, 19], "type": "immediate"},
                    {"name": "r", "position": [18, 16], "type": "register"},
                ],
            },
            "cycles": 1,
            "behavior": "(void)cpu;",
        }
    ]

    code = generate_cpu_impl(isa, "DDCBMask8")
    _, decoder = generate_decoder(isa, "DDCBMask8")

    assert "((inst.raw >> 16) & 0x00FF) & 0xC0" in code
    assert "== 0x40" in code
    assert "((raw >> 16) & 0x00FF) & 0xC0" in decoder
    assert "inst.bit = (raw >> 19) & 0x7;" in decoder
    assert "inst.r = (raw >> 16) & 0x7;" in decoder


def test_threaded_dispatch_mode_generates_computed_goto_path(tmp_path):
    processor_path, system_path = example_pair("minimal8")
    outdir = tmp_path / "dispatch_threaded"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        dispatch_mode="threaded",
    )
    impl_c = (outdir / "src" / "Minimal8.c").read_text()
    assert "goto *dispatch_table[dispatch_id];" in impl_c
    assert "DISPATCH_0:" in impl_c


def test_both_dispatch_mode_generates_toggle_macro_path(tmp_path):
    processor_path, system_path = example_pair("minimal8")
    outdir = tmp_path / "dispatch_both"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        dispatch_mode="both",
    )
    impl_c = (outdir / "src" / "Minimal8.c").read_text()
    cmake_text = (outdir / "CMakeLists.txt").read_text()
    assert "CPU_USE_THREADED_DISPATCH" in impl_c
    assert "USE_THREADED_DISPATCH" in cmake_text


def test_interactive_host_uses_declarative_keyboard_map_generation():
    data = yaml_loader.load_processor_system(
        str(BASE_DIR / "examples" / "processors" / "z80.yaml"),
        str(BASE_DIR / "examples" / "systems" / "z80_spectrum48k_interactive.yaml"),
        ic_paths=[str(BASE_DIR / "examples" / "ics" / "zx_spectrum_48k_ula.yaml")],
        device_paths=[
            str(BASE_DIR / "examples" / "devices" / "zx48_keyboard.yaml"),
            str(BASE_DIR / "examples" / "devices" / "zx48_video.yaml"),
            str(BASE_DIR / "examples" / "devices" / "zx48_speaker.yaml"),
            str(BASE_DIR / "examples" / "devices" / "zx48_mic.yaml"),
        ],
        host_paths=[str(BASE_DIR / "examples" / "hosts" / "zx48_host_sdl2_interactive.yaml")],
    )
    code = generate_cpu_impl(data, "Z80")
    assert "cpu_component_apply_declared_keymap(" in code
    assert "if (map->focus_required && has_focus == 0u) return;" in code
    assert "SDL_SCANCODE_BACKSPACE" in code
    assert "SDL_SCANCODE_LEFT" in code
    assert "{ SDL_SCANCODE_BACKSPACE, component_host_sdl2_keyboard_presses_" in code
    assert "ks[SDL_SCANCODE_A]" not in code


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
@pytest.mark.parametrize(
    "example_name",
    ["minimal8", "simple8", "z80", "mos6502", "mos6510", "mc6809"],
)
def test_compile_smoke_generated_examples(tmp_path, example_name):
    processor_path, system_path = example_pair(example_name)
    outdir = tmp_path / f"build_{example_name}"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    build_dir = outdir / "build"
    subprocess.check_call(
        ["cmake", "-S", str(outdir), "-B", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    subprocess.check_call(
        ["cmake", "--build", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_compile_smoke_threaded_dispatch(tmp_path):
    processor_path, system_path = example_pair("minimal8")
    outdir = tmp_path / "minimal8_threaded"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        dispatch_mode="threaded",
    )

    build_dir = outdir / "build"
    subprocess.check_call(
        ["cmake", "-S", str(outdir), "-B", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    subprocess.check_call(
        ["cmake", "--build", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_compile_smoke_both_dispatch_with_threaded_enabled(tmp_path):
    processor_path, system_path = example_pair("minimal8")
    outdir = tmp_path / "minimal8_both"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        dispatch_mode="both",
    )

    build_dir = outdir / "build"
    subprocess.check_call(
        [
            "cmake",
            "-S",
            str(outdir),
            "-B",
            str(build_dir),
            "-DUSE_THREADED_DISPATCH=ON",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    subprocess.check_call(
        ["cmake", "--build", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_compile_smoke_with_hooks_enabled(tmp_path):
    isa = _base_isa("HookBuild8")
    isa["hooks"] = {"post_execute": {"enabled": True}}

    processor_path, system_path = write_pair_from_legacy(tmp_path, "hook_build", isa)

    outdir = tmp_path / "hook_build_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    build_dir = outdir / "build"
    subprocess.check_call(
        ["cmake", "-S", str(outdir), "-B", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    subprocess.check_call(
        ["cmake", "--build", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


@pytest.mark.skipif(
    not shutil.which("cmake"),
    reason="cmake not available on PATH",
)
def test_hook_sources_are_referenced_when_hooks_enabled(tmp_path):
    isa = _base_isa("HookEnabled8")
    isa["hooks"] = {"post_execute": {"enabled": True}}

    processor_path, system_path = write_pair_from_legacy(tmp_path, "hook_enabled", isa)

    outdir = tmp_path / "hook_enabled_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    assert (outdir / "src" / "HookEnabled8_hooks.c").exists()
    cmake_text = (outdir / "CMakeLists.txt").read_text()
    assert "HookEnabled8_hooks.c" in cmake_text

    build_dir = outdir / "build"
    subprocess.check_call(
        ["cmake", "-S", str(outdir), "-B", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    subprocess.check_call(
        ["cmake", "--build", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
