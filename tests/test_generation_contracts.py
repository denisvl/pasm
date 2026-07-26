import os
import pathlib
import shutil
import subprocess
import sys
import json
import re

import pytest
import yaml

from src import generator as gen_mod
from src.codegen.build_system import generate_cmake, generate_makefile
from src.codegen.cpu_decoder import generate_decoder
from src.codegen.cpu_debug_abi import generate_debug_abi
from src.codegen.cpu_header import generate_cpu_header
from src.codegen.cpu_impl import generate_cpu_impl
from src.codegen.cpu_impl import generate_cartridge_picker_runtime_glue
from src.codegen.cpu_impl import generate_cpu_impl
from src.codegen.cpu_impl import generate_host_hal_impl_glue
from src.codegen.cpu_impl import generate_input_runtime_glue
from src.codegen.cpu_impl import generate_input_runtime_contract_support
from src.codegen.split_units import (
    extract_split_section,
    extract_split_sections,
    extract_host_hal_function_prototypes,
    generate_component_runtime_dispatch_glue,
    generate_host_picker_glue,
    promote_host_hal_symbols,
)
from src.codegen.dispatch_contract import generate_dispatch_contract_decls
from src.parser import yaml_loader
from tests.support import example_pair, write_pair_from_legacy


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _sms_interactive_ic_paths() -> list[str]:
    return [
        str(BASE_DIR / "examples" / "ics" / "sms" / "sms_cpu_bus.yaml"),
        str(BASE_DIR / "examples" / "ics" / "sms" / "sms_main_ram.yaml"),
        str(BASE_DIR / "examples" / "ics" / "sms" / "sms_vdp_sega315_5124.yaml"),
        str(BASE_DIR / "examples" / "ics" / "sms" / "sms_joypad_io.yaml"),
        str(BASE_DIR / "examples" / "ics" / "sms" / "sms_psg_sn76489.yaml"),
    ]


def _msx1_cartridge_interactive_ic_paths() -> list[pathlib.Path]:
    return [
        BASE_DIR / "examples" / "ics" / "msx1" / "msx1_vdp_tms9918a.yaml",
        BASE_DIR / "examples" / "ics" / "msx1" / "msx1_ppi_8255.yaml",
        BASE_DIR / "examples" / "ics" / "msx1" / "msx1_psg_ay8910.yaml",
        BASE_DIR / "examples" / "ics" / "msx1" / "msx1_main_ram.yaml",
    ]


def _base_isa(name: str) -> dict:
    return {
        "metadata": {
            "name": name,
            "version": "1.0",
            "bits": 8,
            "address_bits": 16,
            "endian": "little",
            "codegen": {
                "architecture_id": "unknown",
                "numeric_style": "c_hex",
                "flags_dump_style": "raw",
                "decode_quirks": {"mc6809_indexed_postbyte_length": False},
                "display_kinds_enabled": [],
            },
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
    assert "_runtime.c" in cmake
    assert "_debug_abi.c" in cmake
    assert "_system_bus.c" in cmake
    assert "_host_glue.c" in cmake


def test_cmake_emits_linkable_emulator_library_target():
    isa = _base_isa("BuildLib8")
    cmake = generate_cmake(isa, "BuildLib8")
    assert "add_library(buildlib8_emu STATIC ${EMU_SOURCES})" not in cmake
    assert "add_executable(buildlib8_test src/main.c)" in cmake
    assert "target_link_libraries(buildlib8_test PRIVATE" in cmake
    assert "buildlib8_cpu_core" in cmake
    assert "_system" in cmake
    assert (
        "target_link_libraries(buildlib8_test PRIVATE buildlib8_cpu_core system_system buildlib8_cpu_core)"
        in cmake
    )
    assert "src/system_runtime.c" in cmake
    assert "src/system_system_bus.c" in cmake
    assert "src/system_system_glue.c" in cmake
    assert "src/system_host_glue.c" in cmake
    assert "src/system_device_glue.c" in cmake


def test_cmake_emits_visual_studio_debugger_properties_for_cli_target():
    isa = _base_isa("VsDebug8")
    cmake = generate_cmake(isa, "VsDebug8")

    assert "if(WIN32)" in cmake
    assert "set_target_properties(vsdebug8_test PROPERTIES" in cmake
    assert 'VS_DEBUGGER_COMMAND_ARGUMENTS "--test basic"' in cmake
    assert 'VS_DEBUGGER_WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"' in cmake
    assert 'VS_DEBUGGER_ENVIRONMENT "${PASM_VS_DEBUGGER_ENVIRONMENT}"' in cmake
    assert "PASM_VS_VCPKG_ROOT_HINT" in cmake
    assert "/installed/${PASM_VCPKG_TRIPLET}/debug/bin" in cmake


def test_cmake_uses_run_arguments_for_interactive_visual_studio_debugging():
    isa = _base_isa("VsInteractive8")
    isa["hosts"] = [
        {
            "metadata": {"id": "host0", "type": "host_adapter", "model": "test_host_hal"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {
                "headers": [],
                "include_paths": [],
                "linked_libraries": [],
                "library_paths": [],
            },
        }
    ]

    cmake = generate_cmake(isa, "VsInteractive8")

    assert 'VS_DEBUGGER_COMMAND_ARGUMENTS "--run"' in cmake


def test_generator_emits_visual_studio_debug_helper_script(tmp_path):
    isa = _base_isa("VsScript8")
    processor_path, system_path = write_pair_from_legacy(tmp_path, "vs_script", isa)
    outdir = tmp_path / "vs_script_out"

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    script = (outdir / "open_vs_debug.bat").read_text(encoding="utf-8")
    assert 'set "GENERATOR=Visual Studio 17 2022"' in script
    assert 'set "PLATFORM=x64"' in script
    assert 'cmake -S "%ROOT%" -B "%BUILD_DIR%" -G "%GENERATOR%" -A "%PLATFORM%"' in script
    assert "-DCMAKE_TOOLCHAIN_FILE=%VCPKG_ROOT%\\scripts\\buildsystems\\vcpkg.cmake" in script
    assert "-DVCPKG_TARGET_TRIPLET=%PASM_VCPKG_TRIPLET%" in script
    assert 'set "SLN=%BUILD_DIR%\\vsscript8_emulator.sln"' in script
    assert 'start "" "%SLN%"' in script


def test_makefile_emits_linkable_emulator_library_target():
    isa = _base_isa("BuildLib8")
    makefile = generate_makefile(isa, "BuildLib8")
    assert "EMU_LIB = libbuildlib8_emu.a" not in makefile
    assert "$(TARGET): $(MAIN_OBJ) $(SYSTEM_LIB) $(CPU_CORE_LIB)" in makefile
    assert (
        "$(CC) $(LDFLAGS) -o $@ $(MAIN_OBJ) $(CPU_CORE_LIB) $(SYSTEM_LIB) $(CPU_CORE_LIB)"
        in makefile
    )
    assert "$(EMU_LIB): $(EMU_OBJECTS)" not in makefile
    assert "src/system_runtime.c" in makefile
    assert "src/system_system_bus.c" in makefile
    assert "src/system_system_glue.c" in makefile
    assert "src/system_host_glue.c" in makefile
    assert "src/system_device_glue.c" in makefile


def test_split_units_module_uses_public_codegen_interfaces():
    split_units = (BASE_DIR / "src" / "codegen" / "split_units.py").read_text(
        encoding="utf-8"
    )
    assert "from .cpu_runtime import" in split_units
    assert "from .interrupts import generate_interrupt_impl" in split_units
    assert "from .cpu_impl import (" not in split_units
    assert "_generate_system_rom_loader" not in split_units
    assert "_generate_cartridge_rom_loader" not in split_units
    assert "_generate_interrupt_impl" not in split_units


def test_split_units_own_component_dispatch_with_contract_support():
    split_units = (BASE_DIR / "src" / "codegen" / "split_units.py").read_text(
        encoding="utf-8"
    )
    assert "generate_component_runtime_dispatch_glue" in split_units
    assert "generate_component_lifecycle_dispatch_glue" in split_units
    assert "generate_component_dispatch_glue" in split_units
    assert "generate_component_routing_glue" in split_units
    assert "generate_component_connections_glue" in split_units
    assert "generate_host_hal_contract_support" in split_units
    assert "generate_input_runtime_glue" in split_units


def test_generator_excludes_component_dispatch_from_core():
    generator_src = (BASE_DIR / "src" / "generator.py").read_text(encoding="utf-8")
    assert '"COMPONENT_DISPATCH"' in generator_src


def test_cpu_header_uses_shared_dispatch_contract_module():
    cpu_header_src = (BASE_DIR / "src" / "codegen" / "cpu_header.py").read_text(
        encoding="utf-8"
    )
    templates_src = (BASE_DIR / "src" / "codegen" / "templates.py").read_text(
        encoding="utf-8"
    )
    assert "from .dispatch_contract import generate_dispatch_contract_decls" in cpu_header_src
    assert "dispatch_contract=dispatch_contract" in cpu_header_src
    assert "{dispatch_contract}" in templates_src


def test_dispatch_contract_decls_include_split_symbols():
    decls = generate_dispatch_contract_decls()
    assert "typedef struct {" in decls
    assert "ComponentConnection" in decls
    assert "extern const ComponentConnection g_component_connections[]" in decls
    assert "extern const size_t g_component_connections_count" in decls
    assert "uint64_t cpu_component_call(" in decls
    assert "void cpu_component_emit_signal(" in decls


def test_input_runtime_markers_and_extraction():
    processor = BASE_DIR / "examples" / "processors" / "mos6502.yaml"
    system = BASE_DIR / "examples" / "systems" / "atari800xl" / "atari800xl_interactive.yaml"
    ic_paths = [
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_antic.yaml"),
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_gtia.yaml"),
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_pokey.yaml"),
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_pia_6520.yaml"),
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_mmu.yaml"),
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_main_ram.yaml"),
    ]
    device_paths = [
        str(BASE_DIR / "examples" / "devices" / "atari800xl" / "atari800xl_keyboard.yaml"),
        str(BASE_DIR / "examples" / "devices" / "atari800xl" / "atari800xl_controller.yaml"),
        str(BASE_DIR / "examples" / "devices" / "atari800xl" / "atari800xl_video.yaml"),
        str(BASE_DIR / "examples" / "devices" / "atari800xl" / "atari800xl_speaker.yaml"),
    ]
    host_paths = [str(BASE_DIR / "examples" / "hosts" / "atari800xl" / "atari800xl_host_hal_interactive.yaml")]
    isa_data = gen_mod.EmulatorGenerator(
        str(processor),
        str(system),
        ic_paths=ic_paths,
        device_paths=device_paths,
        host_paths=host_paths,
    ).isa_data
    impl = generate_cpu_impl(
        isa_data,
        "MOS6502",
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = extract_split_sections(impl, "INPUT_RUNTIME")
    assert blocks
    extracted = generate_input_runtime_glue(isa_data, "MOS6502")
    assert "RuntimeKeyboardBinding" in extracted
    assert "RuntimeControllerBinding" in extracted


def test_input_runtime_contract_support_extracts_decls():
    processor = BASE_DIR / "examples" / "processors" / "mos6502.yaml"
    system = BASE_DIR / "examples" / "systems" / "atari800xl" / "atari800xl_interactive.yaml"
    ic_paths = [
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_antic.yaml"),
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_gtia.yaml"),
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_pokey.yaml"),
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_pia_6520.yaml"),
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_mmu.yaml"),
        str(BASE_DIR / "examples" / "ics" / "atari800xl" / "atari800xl_main_ram.yaml"),
    ]
    device_paths = [
        str(BASE_DIR / "examples" / "devices" / "atari800xl" / "atari800xl_keyboard.yaml"),
        str(BASE_DIR / "examples" / "devices" / "atari800xl" / "atari800xl_controller.yaml"),
        str(BASE_DIR / "examples" / "devices" / "atari800xl" / "atari800xl_video.yaml"),
        str(BASE_DIR / "examples" / "devices" / "atari800xl" / "atari800xl_speaker.yaml"),
    ]
    host_paths = [str(BASE_DIR / "examples" / "hosts" / "atari800xl" / "atari800xl_host_hal_interactive.yaml")]
    isa_data = gen_mod.EmulatorGenerator(
        str(processor),
        str(system),
        ic_paths=ic_paths,
        device_paths=device_paths,
        host_paths=host_paths,
    ).isa_data
    support = generate_input_runtime_contract_support(isa_data, "MOS6502")
    assert "typedef struct {" in support
    assert "RuntimeKeyboardBinding;" in support
    assert "RuntimeControllerBinding;" in support
    assert "extern RuntimeKeyboardMap g_runtime_keyboard_map;" in support
    assert "extern RuntimeControllerMap g_runtime_controller_map;" in support
    assert "cpu_component_keyboard_ascii_pop(void);" in support


def test_input_runtime_contract_support_includes_declared_keymap_helper(tmp_path):
    processor = BASE_DIR / "examples" / "processors" / "z80.yaml"
    system = BASE_DIR / "examples" / "systems" / "msx1" / "msx1_cartridge_interactive.yaml"
    ics = _msx1_cartridge_interactive_ic_paths()
    devices = [
        BASE_DIR / "examples" / "devices" / "msx1" / "msx_keyboard.yaml",
        BASE_DIR / "examples" / "devices" / "msx1" / "msx_controller.yaml",
        BASE_DIR / "examples" / "devices" / "msx1" / "msx_video.yaml",
        BASE_DIR / "examples" / "devices" / "msx1" / "msx_speaker.yaml",
    ]
    host = BASE_DIR / "examples" / "hosts" / "msx1" / "msx_host_hal_interactive.yaml"
    rom = tmp_path / "dummy_msx.rom"
    rom.write_bytes(b"\x00" * 0x4000)

    isa_data = yaml_loader.load_processor_system(
        str(processor),
        str(system),
        [str(p) for p in ics],
        [str(p) for p in devices],
        [str(host)],
        cartridge_path=str(BASE_DIR / "examples" / "cartridges" / "msx1" / "msx_mapper_none.yaml"),
        cartridge_rom_path=str(rom),
        host_backend_target="sdl2",
    )
    support = generate_input_runtime_contract_support(isa_data, "Z80")
    assert "cpu_component_apply_declared_keymap(" in support


def test_split_units_module_exposes_dispatcher():
    split_units = (BASE_DIR / "src" / "codegen" / "split_units.py").read_text(
        encoding="utf-8"
    )
    assert "def emit_split_unit(" in split_units
    assert 'if suffix == "runtime":' in split_units
    assert 'if suffix == "system_glue":' in split_units
    assert 'if suffix == "host_glue":' in split_units


def test_ic_step_and_lifecycle_ownership_split_into_ic_units(tmp_path):
    processor = BASE_DIR / "examples" / "processors" / "z80.yaml"
    system = BASE_DIR / "examples" / "systems" / "sms" / "sms_interactive.yaml"
    ic_paths = _sms_interactive_ic_paths()
    device_paths = [
        str(BASE_DIR / "examples" / "devices" / "sms" / "sms_video.yaml"),
        str(BASE_DIR / "examples" / "devices" / "sms" / "sms_speaker.yaml"),
        str(BASE_DIR / "examples" / "devices" / "sms" / "sms_controller.yaml"),
    ]
    host_paths = [str(BASE_DIR / "examples" / "hosts" / "sms" / "sms_host_hal_interactive.yaml")]
    outdir = tmp_path / "sms_split_out"
    rom = tmp_path / "dummy.sms"
    rom.write_bytes(b"\x00" * 0x8000)
    gen = gen_mod.EmulatorGenerator(
        str(processor),
        str(system),
        ic_paths=ic_paths,
        device_paths=device_paths,
        host_paths=host_paths,
        cartridge_map_path=str(BASE_DIR / "examples" / "cartridges" / "sms" / "sms_mapper_sega.yaml"),
        cartridge_rom_path=str(rom),
    )
    gen.generate(str(outdir))

    src = outdir / "src"
    system_glue = (src / "sms_system_glue.c").read_text(encoding="utf-8")
    ic_units = sorted(src.glob("sms_ic_*.c"))
    assert ic_units, "expected per-IC source units"

    # system glue owns dispatch wrappers only
    assert "void cpu_components_step_pre(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before)" in system_glue
    assert "void cpu_components_step_post(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before)" in system_glue
    assert "cpu_component_ic_sms_vdp0_step_pre" in system_glue
    assert "cpu_component_ic_sms_vdp0_step_post" in system_glue
    assert "cpu_component_ic_sms_vdp0_lifecycle_create" in system_glue
    assert "cpu_component_ic_sms_vdp0_lifecycle_reset" in system_glue
    assert "cpu_component_ic_sms_vdp0_lifecycle_destroy" in system_glue

    # IC units own concrete hook/lifecycle implementation.
    vdp = (src / "sms_ic_sms_vdp0.c").read_text(encoding="utf-8")
    assert "void cpu_component_ic_sms_vdp0_step_pre(" in vdp
    assert "void cpu_component_ic_sms_vdp0_step_post(" in vdp
    assert "void cpu_component_ic_sms_vdp0_lifecycle_create(" in vdp
    assert "void cpu_component_ic_sms_vdp0_lifecycle_reset(" in vdp
    assert "void cpu_component_ic_sms_vdp0_lifecycle_destroy(" in vdp


def test_generated_cpu_core_has_no_ic_implementation_leakage(tmp_path):
    processor = BASE_DIR / "examples" / "processors" / "z80.yaml"
    system = BASE_DIR / "examples" / "systems" / "sms" / "sms_interactive.yaml"
    ic_paths = _sms_interactive_ic_paths()
    device_paths = [
        str(BASE_DIR / "examples" / "devices" / "sms" / "sms_video.yaml"),
        str(BASE_DIR / "examples" / "devices" / "sms" / "sms_speaker.yaml"),
        str(BASE_DIR / "examples" / "devices" / "sms" / "sms_controller.yaml"),
    ]
    host_paths = [str(BASE_DIR / "examples" / "hosts" / "sms" / "sms_host_hal_interactive.yaml")]
    outdir = tmp_path / "sms_split_out_core_contract"
    rom = tmp_path / "dummy.sms"
    rom.write_bytes(b"\x00" * 0x8000)
    gen = gen_mod.EmulatorGenerator(
        str(processor),
        str(system),
        ic_paths=ic_paths,
        device_paths=device_paths,
        host_paths=host_paths,
        cartridge_map_path=str(BASE_DIR / "examples" / "cartridges" / "sms" / "sms_mapper_sega.yaml"),
        cartridge_rom_path=str(rom),
    )
    gen.generate(str(outdir))

    core = (outdir / "src" / "Z80_core.c").read_text(encoding="utf-8")
    # Core may call lifecycle dispatch, but must not own IC implementation symbols.
    assert "cpu_component_lifecycle_create(" in core
    assert "cpu_component_lifecycle_reset(" in core
    assert "cpu_component_lifecycle_destroy(" in core
    assert "cpu_component_ic_" not in core
    assert "ComponentState_sms_" not in core


def test_system_glue_owns_dispatch_not_ic_stateful_impl(tmp_path):
    processor = BASE_DIR / "examples" / "processors" / "z80.yaml"
    system = BASE_DIR / "examples" / "systems" / "sms" / "sms_interactive.yaml"
    ic_paths = _sms_interactive_ic_paths()
    device_paths = [
        str(BASE_DIR / "examples" / "devices" / "sms" / "sms_video.yaml"),
        str(BASE_DIR / "examples" / "devices" / "sms" / "sms_speaker.yaml"),
        str(BASE_DIR / "examples" / "devices" / "sms" / "sms_controller.yaml"),
    ]
    host_paths = [str(BASE_DIR / "examples" / "hosts" / "sms" / "sms_host_hal_interactive.yaml")]
    outdir = tmp_path / "sms_split_out_glue_contract"
    rom = tmp_path / "dummy.sms"
    rom.write_bytes(b"\x00" * 0x8000)
    gen = gen_mod.EmulatorGenerator(
        str(processor),
        str(system),
        ic_paths=ic_paths,
        device_paths=device_paths,
        host_paths=host_paths,
        cartridge_map_path=str(BASE_DIR / "examples" / "cartridges" / "sms" / "sms_mapper_sega.yaml"),
        cartridge_rom_path=str(rom),
    )
    gen.generate(str(outdir))

    glue = (outdir / "src" / "sms_system_glue.c").read_text(encoding="utf-8")
    # Dispatch-only wrappers should call IC functions.
    assert "cpu_component_ic_sms_vdp0_step_pre(cpu, inst, pc_before);" in glue
    assert "cpu_component_ic_sms_vdp0_step_post(cpu, inst, pc_before);" in glue
    # Stateful IC implementation snippets must not be embedded in step dispatch wrappers.
    pre_block = glue.split("void cpu_components_step_pre(", 1)[1].split("}\n", 1)[0]
    post_block = glue.split("void cpu_components_step_post(", 1)[1].split("}\n", 1)[0]
    assert "ComponentState_sms_vdp0 *comp = &cpu->comp_sms_vdp0;" not in pre_block
    assert "ComponentState_sms_joy0 *comp = &cpu->comp_sms_joy0;" not in pre_block
    assert "ComponentState_sms_psg0 *comp = &cpu->comp_sms_psg0;" not in pre_block
    assert "ComponentState_sms_vdp0 *comp = &cpu->comp_sms_vdp0;" not in post_block
    assert "ComponentState_sms_joy0 *comp = &cpu->comp_sms_joy0;" not in post_block
    assert "ComponentState_sms_psg0 *comp = &cpu->comp_sms_psg0;" not in post_block
    assert "cpu_component_cartridge_picker_update(cpu, 1u);" not in post_block


def test_generator_emits_split_link_order_in_generated_cmake(tmp_path):
    isa = _base_isa("LinkGuard8")
    output = tmp_path / "out"
    processor, system = write_pair_from_legacy(tmp_path, "link_guard", isa)

    g = gen_mod.EmulatorGenerator(str(processor), str(system))
    g.generate(str(output))

    cmake = (output / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "add_library(linkguard8_cpu_core STATIC ${CPU_CORE_SOURCES})" in cmake
    m = re.search(r"add_library\(([^ )]+_system) STATIC \$\{SYSTEM_SOURCES\}\)", cmake)
    assert m is not None
    system_target = m.group(1)
    assert (
        f"target_link_libraries(linkguard8_test PRIVATE "
        f"linkguard8_cpu_core {system_target} linkguard8_cpu_core)"
    ) in cmake


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


def test_build_system_uses_backend_target_for_sdl2_linkage():
    isa = _base_isa("BackendTarget8")
    isa["hosts"] = [
        {
            "metadata": {"id": "host0", "type": "host_adapter", "model": "test_host_hal"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {
                "headers": [],
                "include_paths": [],
                "linked_libraries": [],
                "library_paths": [],
            },
        }
    ]
    isa["coding"] = {
        "headers": [],
        "include_paths": [],
        "linked_libraries": [],
        "library_paths": [],
    }

    cmake = generate_cmake(isa, "BackendTarget8")
    makefile = generate_makefile(isa, "BackendTarget8")

    assert "find_package(SDL2 CONFIG QUIET)" in cmake
    assert "${PASM_SDL2_LINK_TARGET}" in cmake
    assert "-lSDL2" in makefile


def test_build_system_does_not_auto_link_sdl2_for_stub_backend():
    isa = _base_isa("BackendStub8")
    isa["hosts"] = [
        {
            "metadata": {"id": "host0", "type": "host_adapter", "model": "test_host_stub"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {
                "headers": [],
                "include_paths": [],
                "linked_libraries": [],
                "library_paths": [],
            },
        }
    ]
    isa["coding"] = {
        "headers": [],
        "include_paths": [],
        "linked_libraries": [],
        "library_paths": [],
    }

    cmake = generate_cmake(isa, "BackendStub8")
    makefile = generate_makefile(isa, "BackendStub8")

    assert "find_package(SDL2 CONFIG QUIET)" in cmake
    assert "${PASM_SDL2_LINK_TARGET}" in cmake
    assert "PASM_SDL2_LIB = -lSDL2" in makefile
    assert "-lSDL2" in makefile


def test_build_system_links_sdl2_for_glfw_backend():
    isa = _base_isa("BackendGlfw8")
    isa["hosts"] = [
        {
            "metadata": {"id": "host0", "type": "host_adapter", "model": "test_host_glfw"},
            "backend": {"target": "glfw"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {
                "headers": [],
                "include_paths": [],
                "linked_libraries": [],
                "library_paths": [],
            },
        }
    ]
    isa["coding"] = {
        "headers": [],
        "include_paths": [],
        "linked_libraries": [],
        "library_paths": [],
    }

    cmake = generate_cmake(isa, "BackendGlfw8")
    makefile = generate_makefile(isa, "BackendGlfw8")

    assert "find_package(glfw3 CONFIG QUIET)" in cmake
    assert "find_package(OpenGL REQUIRED)" in cmake
    assert "find_library(PASM_GLFW_LIBRARY NAMES glfw3dll glfw3 glfw" in cmake
    assert "${PASM_GLFW_LINK_TARGET}" in cmake
    assert "${PASM_OPENGL_LINK_TARGET}" in cmake
    assert "$<$<PLATFORM_ID:Windows>:winmm>" in cmake
    assert "find_path(PASM_ALSA_INCLUDE_DIR alsa/asoundlib.h)" in cmake
    assert "find_library(PASM_ALSA_LIBRARY NAMES asound)" in cmake
    assert "Install libasound2-dev on Debian/Ubuntu or alsa-lib-devel on Fedora/RHEL" in cmake
    assert "$<$<PLATFORM_ID:Linux>:${PASM_ALSA_LINK_TARGET}>" in cmake
    assert "PASM_GLFW_LIB = -lglfw3dll" in makefile
    assert "PASM_GLFW_LIB = -lglfw" in makefile
    assert "PASM_OPENGL_LIB = -lGL" in makefile
    assert "PASM_OPENGL_LIB = -lopengl32" in makefile
    assert "PASM_WINMM_LIB = -lwinmm" in makefile
    assert "PASM_ALSA_LIB = -lasound" in makefile
    assert "find_package(SDL2 CONFIG QUIET)" in cmake
    assert "${PASM_SDL2_LINK_TARGET}" in cmake
    assert "PASM_SDL2_LIB = -lSDL2" in makefile
    assert "-lSDL2" in makefile


def test_build_system_does_not_infer_sdl2_backend_from_linked_library_name():
    isa = _base_isa("BackendNoInfer8")
    isa["hosts"] = [
        {
            "metadata": {"id": "host0", "type": "host_adapter", "model": "test_host_stub"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {
                "headers": [],
                "include_paths": [],
                "linked_libraries": [],
                "library_paths": [],
            },
        }
    ]
    isa["coding"] = {
        "headers": [],
        "include_paths": [],
        "linked_libraries": [{"name": "SDL2"}],
        "library_paths": [],
    }

    cmake = generate_cmake(isa, "BackendNoInfer8")
    makefile = generate_makefile(isa, "BackendNoInfer8")

    # Backend target controls auto dependency setup; explicit link entries stay explicit.
    assert "find_package(SDL2 CONFIG QUIET)" not in cmake
    assert "${PASM_SDL2_LINK_TARGET}" not in cmake
    assert "target_link_libraries(backendnoinfer8_test PRIVATE\n    SDL2\n)" in cmake
    assert "target_link_libraries(backendnoinfer8_emu PRIVATE\n    SDL2\n)" not in cmake
    assert "-lSDL2" in makefile


def test_build_system_rejects_mixed_backend_targets():
    isa = _base_isa("BackendMixed8")
    isa["hosts"] = [
        {
            "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test_host_hal"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        },
        {
            "metadata": {"id": "host_stub", "type": "host_adapter", "model": "test_host_stub"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        },
    ]

    with pytest.raises(ValueError, match="multiple host backend targets"):
        generate_cmake(isa, "BackendMixed8")
    with pytest.raises(ValueError, match="multiple host backend targets"):
        generate_makefile(isa, "BackendMixed8")


def test_build_system_rejects_unsupported_backend_target():
    isa = _base_isa("BackendUnsupported8")
    isa["hosts"] = [
        {
            "metadata": {"id": "host_unknown", "type": "host_adapter", "model": "test_host_unknown"},
            "backend": {"target": "wayland"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]

    with pytest.raises(ValueError, match="unsupported host backend target"):
        generate_cmake(isa, "BackendUnsupported8")
    with pytest.raises(ValueError, match="unsupported host backend target"):
        generate_makefile(isa, "BackendUnsupported8")


def test_cpu_codegen_rejects_mixed_backend_targets():
    data = _base_isa("CpuBackendMixed8")
    data["hosts"] = [
        {
            "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test_host_hal"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        },
        {
            "metadata": {"id": "host_stub", "type": "host_adapter", "model": "test_host_stub"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        },
    ]

    with pytest.raises(ValueError, match="multiple host backend targets"):
        generate_cpu_impl(data, "Z80")


def test_cpu_codegen_rejects_unsupported_backend_target():
    data = _base_isa("CpuBackendUnsupported8")
    data["hosts"] = [
        {
            "metadata": {"id": "host_unknown", "type": "host_adapter", "model": "test_host_unknown"},
            "backend": {"target": "wayland"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]

    with pytest.raises(ValueError, match="unsupported host backend target"):
        generate_cpu_impl(data, "Z80")


def test_cpu_codegen_accepts_glfw_backend_as_non_sdl_runtime_path():
    data = _base_isa("CpuBackendGlfw8")
    data["hosts"] = [
        {
            "metadata": {"id": "host_glfw", "type": "host_adapter", "model": "test_host_glfw"},
            "backend": {"target": "glfw"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]

    code = generate_cpu_impl(data, "Z80")
    assert "#define CPU_HOST_HAS_SCANCODE_MAP 1" in code
    assert "#define CPU_HOST_SCANCODE(name) CPU_GLFW_SC_##name" in code
    assert "#define CPU_HOST_MOD_CTRL 0x0001u" in code
    assert "#define CPU_HOST_MOD_SHIFT 0x0002u" in code
    assert "#define CPU_HOST_MOD_LCTRL 0x0004u" in code
    assert "return SDL_PollEvent((SDL_Event *)event);" not in code


def test_cpu_codegen_auto_includes_sdl_header_for_sdl2_backend():
    data = _base_isa("CpuBackendSdl2Includes8")
    data["hosts"] = [
        {
            "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test_host_hal"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    data["coding"] = {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []}

    code = generate_host_hal_impl_glue(data, "Z80")
    assert "typedef SDL_Event CPUHostEvent;" in code
    assert "static int cpu_host_hal_init(uint32_t flags)" in code


def test_cpu_codegen_does_not_auto_include_sdl_header_for_stub_backend():
    data = _base_isa("CpuBackendStubIncludes8")
    data["hosts"] = [
        {
            "metadata": {"id": "host_stub", "type": "host_adapter", "model": "test_host_stub"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    data["coding"] = {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []}

    code = generate_cpu_impl(data, "Z80")
    assert "#include <SDL2/SDL.h>" not in code


def test_cpu_codegen_does_not_infer_backend_from_host_model_name():
    data = _base_isa("CpuBackendNoModelInference8")
    data["hosts"] = [
        {
            "metadata": {"id": "host_model_sdl2", "type": "host_adapter", "model": "test_host_hal"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]

    code = generate_cpu_impl(data, "Z80")
    assert "#define CPU_HOST_HAS_SCANCODE_MAP 0" in code
    assert "return SDL_PollEvent((SDL_Event *)event);" not in code


def test_cpu_codegen_ignores_legacy_host_keyboard_declarations():
    data = _base_isa("CpuHostSourceStrict8")
    data["hosts"] = [
        {
            "metadata": {"id": "host_bad_source", "type": "host_adapter", "model": "test_host_stub"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "input": {
                "keyboard": {
                    "source": "sdl_scancode",
                    "focus_required": True,
                    "bindings": [{"host_key": "A", "presses": [{"row": 0, "bit": 0}]}],
                }
            },
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "cpu_component_scancode_for_host_key(" in code
    assert "g_component_keyboard_maps" not in code


def test_cpu_codegen_emits_runtime_keyboard_loader_apis():
    data = _base_isa("CpuHostBindingStrict8")
    data["hosts"] = [
        {
            "metadata": {"id": "host_bad_binding", "type": "host_adapter", "model": "test_host_stub"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "input": {
                "keyboard": {
                    "focus_required": True,
                    "bindings": [{"host_key": "bad-key", "presses": [{"row": 0, "bit": 0}]}],
                }
            },
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "load_keyboard_map(CPUState *cpu, const char *path)" in code
    assert "cpu_component_keyboard_ascii_feed(" in code
    assert "mapper_key_id:" in code


def test_memory_read_only_regions_emit_write_guards():
    isa = _base_isa("MemGuard8")
    isa["memory"]["regions"] = [
        {"name": "RAM", "start": 0x0000, "size": 0x8000, "read_write": True},
        {"name": "ROM", "start": 0x8000, "size": 0x8000, "read_only": True},
    ]

    code = generate_cpu_impl(isa, "MemGuard8")
    assert "Ignore writes to read-only region: ROM" in code
    assert "if (addr >= 0x8000u) {" in code


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
    split_runtime = next((outdir / "src").glob("*_runtime.c"))
    split_system_bus = next((outdir / "src").glob("*_system_bus.c"))
    split_system_glue = next((outdir / "src").glob("*_system_glue.c"))
    split_host_glue = next((outdir / "src").glob("*_host_glue.c"))
    split_device_glue = next((outdir / "src").glob("*_device_glue.c"))
    subprocess.check_call(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-D_POSIX_C_SOURCE=199309L",
            "-I",
            str(outdir / "src"),
            str(outdir / "src" / "MemRuntime8_core.c"),
            str(outdir / "src" / "MemRuntime8_decoder.c"),
            str(split_runtime),
            str(split_system_bus),
            str(split_system_glue),
            str(split_host_glue),
            str(split_device_glue),
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
    assert "ERR_ROM=0" in proc.stdout


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
    cpu_impl = (outdir / "src" / "RomApi8_core.c").read_text(encoding="utf-8")
    runtime_impl = next((outdir / "src").glob("*_runtime.c")).read_text(encoding="utf-8")

    assert "int romapi8_load_system_roms(CPUState *cpu, const char *system_base_dir);" in header
    assert "int romapi8_load_system_roms(CPUState *cpu, const char *system_base_dir)" not in cpu_impl
    assert "static const SystemRomImage g_system_rom_images[]" in runtime_impl
    assert "int romapi8_load_system_roms(CPUState *cpu, const char *system_base_dir)" in runtime_impl


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


def test_generator_moves_cartridge_loader_into_runtime_unit(tmp_path):
    isa = _base_isa("CartRuntime8")
    isa["cartridge"] = {
        "metadata": {"id": "cart0", "type": "cartridge_mapper", "model": "none"},
        "state": [
            {"name": "rom_data", "type": "uint8_t *", "initial": "NULL"},
            {"name": "rom_size", "type": "uint32_t", "initial": "0"},
        ],
        "interfaces": {"callbacks": [], "handlers": [], "signals": []},
        "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
        "coding": {
            "headers": [],
            "include_paths": [],
            "linked_libraries": [],
            "library_paths": [],
        },
    }
    isa["cartridge_rom"] = {"path": "/tmp/test.rom"}
    processor_path, system_path = write_pair_from_legacy(tmp_path, "cart_runtime8", isa)
    outdir = tmp_path / "cart_runtime8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    cpu_impl = (outdir / "src" / "CartRuntime8_core.c").read_text(encoding="utf-8")
    runtime_impl = next((outdir / "src").glob("*_runtime.c")).read_text(encoding="utf-8")
    assert "int cartruntime8_load_cartridge_rom(CPUState *cpu, const char *path)" not in cpu_impl
    assert "int cartruntime8_load_cartridge_rom(CPUState *cpu, const char *path)" in runtime_impl
    assert "int cartruntime8_set_cartridge_dir(CPUState *cpu, const char *path)" not in cpu_impl
    assert "int cartruntime8_set_cartridge_dir(CPUState *cpu, const char *path)" in runtime_impl


def test_step_uses_runtime_pre_step_contract_instead_of_picker_swap():
    isa = _base_isa("CartBridge8")
    isa["cartridge"] = {
        "metadata": {"id": "cart0", "type": "cartridge_mapper", "model": "none"},
        "state": [
            {"name": "rom_data", "type": "uint8_t *", "initial": "NULL"},
            {"name": "rom_size", "type": "uint32_t", "initial": "0"},
        ],
        "interfaces": {"callbacks": [], "handlers": [], "signals": []},
        "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
        "coding": {
            "headers": [],
            "include_paths": [],
            "linked_libraries": [],
            "library_paths": [],
        },
    }
    impl = generate_cpu_impl(isa, "CartBridge8")
    assert "if (cpu_components_runtime_pre_step(cpu) != 0) {" in impl
    assert "if (cpu_component_cartridge_picker_apply_pending_swap(cpu) != 0) {\n        return 0;" not in impl


def test_generator_moves_interrupt_api_into_system_glue_unit(tmp_path):
    isa = _base_isa("IntGlue8")
    isa["interrupts"] = {"model": "mos6502"}
    processor_path, system_path = write_pair_from_legacy(tmp_path, "int_glue8", isa)
    outdir = tmp_path / "int_glue8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    cpu_impl = (outdir / "src" / "IntGlue8_core.c").read_text(encoding="utf-8")
    system_glue_impl = next((outdir / "src").glob("*_system_glue.c")).read_text(
        encoding="utf-8"
    )

    assert "void intglue8_interrupt(CPUState *cpu, uint8_t vector)" not in cpu_impl
    assert "void intglue8_set_irq(CPUState *cpu, bool enabled)" not in cpu_impl

    assert "void intglue8_interrupt(CPUState *cpu, uint8_t vector)" in system_glue_impl
    assert "void intglue8_set_irq(CPUState *cpu, bool enabled)" in system_glue_impl


def test_generator_moves_host_picker_wrappers_into_host_glue_unit(tmp_path):
    isa = _base_isa("HostGlue8")
    # Enable cartridge metadata so picker paths are generated.
    isa["cartridge"] = {"metadata": {"id": "cart", "type": "cartridge_map", "model": "test"}}
    processor_path, system_path = write_pair_from_legacy(tmp_path, "hostglue8", isa)
    outdir = tmp_path / "hostglue8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    core_impl = (outdir / "src" / "HostGlue8_core.c").read_text(encoding="utf-8")
    host_glue_impl = next((outdir / "src").glob("*_host_glue.c")).read_text(
        encoding="utf-8"
    )

    assert "int cpu_component_host_picker_set_dir(const char *path)" not in core_impl
    assert "int cpu_component_host_picker_set_dir(const char *path)" in host_glue_impl
    assert "int cpu_component_host_picker_apply_pending(CPUState *cpu)" not in host_glue_impl


def test_host_picker_glue_uses_strict_picker_symbols_when_cartridge_enabled():
    isa = _base_isa("HostStrict8")
    isa["cartridge"] = {"metadata": {"id": "cart", "type": "cartridge_map", "model": "test"}}
    host_glue_impl = generate_host_picker_glue(isa, "HostStrict8")

    assert "PASM_SPLIT_WEAK" not in host_glue_impl
    assert "extern int cpu_component_cartridge_picker_set_dir" in host_glue_impl
    assert "if (!cpu_component_cartridge_picker_set_dir)" not in host_glue_impl
    assert "if (!cpu_component_cartridge_picker_apply_pending_swap)" not in host_glue_impl
    assert "if (!cpu_component_cartridge_picker_is_active)" not in host_glue_impl


def test_component_runtime_dispatch_glue_keeps_picker_out_of_step_post():
    isa = _base_isa("HostStep8")
    isa["cartridge"] = {"metadata": {"id": "cart", "type": "cartridge_map", "model": "test"}}
    glue = generate_component_runtime_dispatch_glue(isa)

    assert "if (cpu_component_cartridge_picker_apply_pending_swap(cpu) != 0) {" in glue
    post_block = glue.split("void cpu_components_step_post(", 1)[1].split("}\n", 1)[0]
    assert "cpu_component_cartridge_picker_update(cpu, 1u);" not in post_block
    assert "cpu_component_cartridge_picker_is_active() != 0u" not in post_block


def test_video_frame_handler_polls_picker_at_frame_cadence():
    isa = _base_isa("HostFrame8")
    isa["cartridge"] = {
        "metadata": {"id": "cart", "type": "cartridge_map", "model": "test"},
        "state": [
            {"name": "rom_data", "type": "uint8_t *", "initial": "NULL"},
            {"name": "rom_size", "type": "uint32_t", "initial": "0"},
        ],
        "interfaces": {"callbacks": [], "handlers": [], "signals": []},
        "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
        "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
    }
    isa["hosts"] = [
        {
            "metadata": {"id": "host0"},
            "interfaces": {"callbacks": [], "handlers": [{"name": "video_frame", "args": ["u32", "u64", "u32", "u32"]}], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {"video_frame": ""}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    impl = generate_cpu_impl(isa, "HostFrame8")

    assert "cpu_component_host_picker_step(cpu, 1u);" in impl
    assert "cpu_component_cartridge_picker_draw_overlay(cpu, picker_pixels, picker_w, picker_h);" in impl


def test_cpu_core_emits_host_hal_split_markers(tmp_path):
    isa = _base_isa("HostHalMark8")
    isa["host_backend_target"] = "sdl2"
    isa["hosts"] = [{"metadata": {"id": "host_dummy"}}]
    core_impl = generate_cpu_impl(
        isa,
        "HostHalMark8",
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    assert "/* PASM_SPLIT_BEGIN:HOST_HAL_IMPL */" in core_impl
    assert "/* PASM_SPLIT_END:HOST_HAL_IMPL */" in core_impl


def test_extract_split_section_host_hal_impl():
    text = "\n".join(
        [
            "alpha",
            "/* PASM_SPLIT_BEGIN:HOST_HAL_IMPL */",
            "line_one();",
            "line_two();",
            "/* PASM_SPLIT_END:HOST_HAL_IMPL */",
            "omega",
        ]
    )
    body = extract_split_section(text, "HOST_HAL_IMPL")
    assert body == "line_one();\nline_two();"


def test_extract_split_section_finds_generated_host_hal_impl():
    isa = _base_isa("HostHalBody8")
    isa["host_backend_target"] = "sdl2"
    isa["hosts"] = [{"metadata": {"id": "host_dummy"}}]
    core_impl = generate_cpu_impl(
        isa,
        "HostHalBody8",
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    bodies = extract_split_sections(core_impl, "HOST_HAL_IMPL")
    merged = "\n".join(bodies)
    assert merged
    assert "typedef SDL_Event CPUHostEvent;" in merged
    assert "#define CPU_HOST_EVENT_KEYDOWN SDL_KEYDOWN" in merged
    assert "static int cpu_host_hal_init(uint32_t flags)" in merged
    assert "static void *cpu_host_hal_create_window(" in merged


def test_promote_host_hal_symbols_rewrites_only_host_hal_static_lines():
    src = "\n".join(
        [
            "static int cpu_host_hal_init(uint32_t flags) { return (int)flags; }",
            "static uint8_t cpu_host_hal_sdl_inited = 0u;",
            "static int helper_keep_static(void) { return 0; }",
        ]
    )
    out = promote_host_hal_symbols(src)
    assert "int cpu_host_hal_init(uint32_t flags)" in out
    assert "uint8_t cpu_host_hal_sdl_inited = 0u;" in out
    assert "static int helper_keep_static(void)" in out


def test_extract_host_hal_function_prototypes_from_promoted_text():
    promoted = "\n".join(
        [
            "int cpu_host_hal_init(uint32_t flags) {",
            "    return (int)flags;",
            "}",
            "void *cpu_host_hal_create_window(const char *title, int x, int y, int w, int h, uint32_t flags) {",
            "    return (void *)0;",
            "}",
            "static int helper_keep_static(void) {",
            "    return 0;",
            "}",
        ]
    )
    protos = extract_host_hal_function_prototypes(promoted)
    assert "int cpu_host_hal_init(uint32_t flags);" in protos
    assert "void *cpu_host_hal_create_window(const char *title, int x, int y, int w, int h, uint32_t flags);" in protos
    assert not any("helper_keep_static" in p for p in protos)


def test_cpu_impl_can_strip_host_hal_sections_from_helpers():
    isa = _base_isa("HostHalStrip8")
    isa["host_backend_target"] = "sdl2"
    isa["hosts"] = [{"metadata": {"id": "host_dummy"}}]
    core_impl = generate_cpu_impl(
        isa,
        "HostHalStrip8",
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
        exclude_split_sections=["HOST_HAL_IMPL"],
    )
    assert "PASM_SPLIT_BEGIN:HOST_HAL_IMPL" not in core_impl
    assert "PASM_SPLIT_END:HOST_HAL_IMPL" not in core_impl
    assert "static int cpu_host_hal_init(uint32_t flags)" not in core_impl
    # Core should no longer re-inject HAL typedefs/prototypes after split extraction.
    assert "typedef SDL_AudioSpec CPUHostAudioSpec;" not in core_impl
    assert "int cpu_host_hal_init(uint32_t flags);" not in core_impl
    # Host HAL helper forward declarations should not leak into core.
    assert "cpu_host_hal_key_from_scancode" not in core_impl
    assert "cpu_host_hal_scancode_from_key" not in core_impl


def test_cpu_impl_excludes_picker_runtime_font_scale_from_core():
    isa = _base_isa("PickerSplit8")
    isa["host_backend_target"] = "sdl2"
    isa["hosts"] = [{"metadata": {"id": "host_dummy"}}]
    isa["system"] = {"ui": {"cartridge_picker_font_scale": 2}}
    isa["cartridge"] = {"metadata": {"id": "cart"}}

    core_impl = generate_cpu_impl(
        isa,
        "PickerSplit8",
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
        exclude_split_sections=["CARTRIDGE_PICKER_RUNTIME"],
    )
    picker_glue = generate_cartridge_picker_runtime_glue(isa, "PickerSplit8")

    assert "g_runtime_cartridge_picker_font_scale" not in core_impl
    assert "g_runtime_cartridge_picker_font_scale" in picker_glue


def test_cpu_impl_excludes_picker_fs_headers_from_core():
    isa = _base_isa("PickerFsSplit8")
    isa["host_backend_target"] = "sdl2"
    isa["hosts"] = [{"metadata": {"id": "host_dummy"}}]
    isa["cartridge"] = {"metadata": {"id": "cart"}}

    core_impl = generate_cpu_impl(
        isa,
        "PickerFsSplit8",
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
        exclude_split_sections=[
            "INPUT_RUNTIME",
            "CARTRIDGE_PICKER_RUNTIME",
            "COMPONENT_RUNTIME",
            "HOST_HAL_IMPL",
        ],
    )

    assert "#include <errno.h>" not in core_impl
    assert "#include <limits.h>" not in core_impl
    assert "#include <sys/stat.h>" not in core_impl
    assert "#include <dirent.h>" not in core_impl


def test_cpu_impl_generates_cassette_source_type_runtime_glue():
    isa = _base_isa("CassetteSourceSplit8")
    isa["host_backend_target"] = "sdl2"
    isa["hosts"] = [{"metadata": {"id": "host_dummy"}}]
    isa["system"] = {"ui": {}}
    isa["cassette"] = {
        "component": "cassette_transport",
        "directory": "examples/cassettes/demo",
        "allowed_extensions": ["yaml", "wav", "uef"],
        "sources": [
                {
                    "source_type": "examples/cassette_sources/wav_file.yaml",
                    "source_model": "common_wav_file_source",
                    "kind": "file",
                    "component": "cassette_transport",
                    "source_component": "cassette_wav_source",
                    "allowed_extensions": ["yaml", "wav"],
                    "label": "Tape File",
                },
                {
                    "source_type": "examples/cassette_sources/line_in.yaml",
                    "source_model": "common_line_in_source",
                    "kind": "line_in",
                    "component": "cassette_transport",
                    "label": "Line In",
                },
                {
                    "source_type": "examples/cassette_sources/uef_file.yaml",
                    "source_model": "common_uef_file_source",
                    "kind": "file",
                    "component": "cassette_transport",
                    "source_component": "cassette_uef_source",
                    "allowed_extensions": ["uef"],
                    "label": "UEF Tape",
                },
        ],
        "controls": {
            "picker_action_id": "EMU_CASSETTE_PICKER",
            "play_action_id": "EMU_CASSETTE_PLAY",
            "pause_action_id": "EMU_CASSETTE_PAUSE",
            "stop_action_id": "EMU_CASSETTE_STOP",
            "record_action_id": "EMU_CASSETTE_RECORD",
            "volume_up_action_id": "EMU_CASSETTE_VOL_UP",
            "volume_down_action_id": "EMU_CASSETTE_VOL_DOWN",
            "bass_up_action_id": "EMU_CASSETTE_BASS_UP",
            "bass_down_action_id": "EMU_CASSETTE_BASS_DOWN",
            "treble_up_action_id": "EMU_CASSETTE_TREBLE_UP",
            "treble_down_action_id": "EMU_CASSETTE_TREBLE_DOWN",
        },
    }

    impl = generate_cpu_impl(
        isa,
        "CassetteSourceSplit8",
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )

    assert 'component_id = cpu_component_cassette_component_for_ext(de->d_name, &source_index);' in impl
    assert 'static const char *cpu_component_cassette_model_for_ext(const char *name) {' in impl
    assert 'static const char *cpu_component_cassette_component_for_source_index(uint8_t source_index) {' in impl
    assert 'static const char *cpu_component_cassette_source_component_for_source_index(uint8_t source_index) {' in impl
    assert 'static uint8_t cpu_component_cassette_kind_for_source_index(uint8_t source_index) {' in impl
    assert 'static const char *cpu_component_cassette_model_for_source_index(uint8_t source_index) {' in impl
    assert 'if (ea->source_kind != eb->source_kind) return (ea->source_kind == 1u) ? -1 : 1;' in impl
    assert 'if (source_index == 1u) return 1u;' in impl
    assert 'if (strcmp(ext, "wav") == 0) return cpu_component_cassette_model_for_source_index(0u);' in impl
    assert 'if (strcmp(ext, "uef") == 0) return cpu_component_cassette_model_for_source_index(2u);' in impl
    assert 'uint8_t active_source_kind;' in impl
    assert 'uint8_t active_source_index;' in impl
    assert 'uint8_t pending_source_index;' in impl
    assert 'uint64_t args[1] = { (uint64_t)(uintptr_t)"" };' in impl
    assert 'snprintf(entry->file_name, sizeof(entry->file_name), "%s", "Line In");' in impl
    assert 'snprintf(entry->source_model, sizeof(entry->source_model), "%s", cpu_component_cassette_model_for_source_index(1u));' in impl
    assert 'snprintf(entry->component_id, sizeof(entry->component_id), "%s", cpu_component_cassette_component_for_source_index(1u));' in impl
    assert 'snprintf(entry->source_component_id, sizeof(entry->source_component_id), "%s", cpu_component_cassette_source_component_for_source_index(1u));' in impl
    assert 'if (source_model != NULL) snprintf(entry->source_model, sizeof(entry->source_model), "%s", source_model); else entry->source_model[0] = \'\\0\';' in impl
    assert 'g_runtime_cassette_picker.active_source_kind = cpu_component_cassette_kind_for_source_index(auto_source_index);' in impl
    assert 'g_runtime_cassette_picker.pending_source_index = auto_source_index;' in impl
    assert 'g_runtime_cassette_picker.pending_source_kind = cpu_component_cassette_kind_for_source_index(auto_source_index);' in impl
    assert 'g_runtime_cassette_picker.active_source_kind = sel->source_kind;' in impl
    assert 'g_runtime_cassette_picker.pending_source_index = sel->source_index;' in impl
    assert 'g_runtime_cassette_picker.active_source_kind = g_runtime_cassette_picker.pending_source_kind;' in impl
    assert 'g_runtime_cassette_picker.active_source_index = g_runtime_cassette_picker.pending_source_index;' in impl
    assert 'snprintf(g_runtime_cassette_picker.active_source_model, sizeof(g_runtime_cassette_picker.active_source_model), "%s", sel->source_model);' in impl
    assert 'snprintf(g_runtime_cassette_picker.active_source_component_id, sizeof(g_runtime_cassette_picker.active_source_component_id), "%s", sel->source_component_id);' in impl
    assert 'uint64_t select_args[4] = {' in impl
    assert '(uint64_t)(uintptr_t)g_runtime_cassette_picker.active_source_component_id' in impl
    assert 'if (cpu_component_dispatch_callback(cpu, g_runtime_cassette_picker.active_component_id, "select_source", select_args, 4) == 0u) {' in impl
    assert 'snprintf(g_runtime_cassette_picker.active_component_id, sizeof(g_runtime_cassette_picker.active_component_id), "%s", sel->component_id);' in impl


def test_extract_split_section_finds_component_dispatch_block():
    isa = _base_isa("CompRuntime8")
    isa["devices"] = [
        {
            "metadata": {"id": "dev_a"},
            "interfaces": {
                "callbacks": [{"name": "tick"}],
                "handlers": [{"name": "sig"}],
            },
            "behavior": {
                "callback_handlers": {"tick": "__result = 7;"},
                "handler_bodies": {"sig": "(void)args;"},
                "step_pre": "(void)cpu;",
                "step_post": "(void)cpu;",
            },
            "state": [],
        }
    ]
    core_impl = generate_cpu_impl(
        isa,
        "CompRuntime8",
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = extract_split_sections(core_impl, "COMPONENT_DISPATCH")
    merged = "\n".join(blocks)
    assert merged
    assert "uint64_t cpu_component_dispatch_callback(" in merged
    assert "void cpu_component_dispatch_handler(" in merged
    assert "void cpu_component_emit_signal(" in merged


def test_extract_split_section_finds_component_routing_block():
    isa = _base_isa("CompRouting8")
    isa["devices"] = [
        {
            "metadata": {"id": "dev_route"},
            "interfaces": {"callbacks": [{"name": "tick"}], "handlers": [{"name": "sig"}]},
            "behavior": {"callback_handlers": {"tick": "__result = 3;"}, "handler_bodies": {"sig": "(void)args;"}},
            "state": [],
        }
    ]
    core_impl = generate_cpu_impl(
        isa,
        "CompRouting8",
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
    )
    blocks = extract_split_sections(core_impl, "COMPONENT_ROUTING")
    merged = "\n".join(blocks)
    assert merged
    assert "uint64_t cpu_component_call(" in merged
    assert "void cpu_component_emit_signal(" in merged
    assert "cpu_component_dispatch_callback(" in merged
    assert "cpu_component_dispatch_handler(" in merged


def test_cpu_impl_can_strip_component_dispatch_from_helpers():
    isa = _base_isa("CompRuntimeStrip8")
    isa["devices"] = [
        {
            "metadata": {"id": "dev_b"},
            "interfaces": {"callbacks": [{"name": "tick"}]},
            "behavior": {"callback_handlers": {"tick": "__result = 1;"}},
            "state": [],
        }
    ]
    core_impl = generate_cpu_impl(
        isa,
        "CompRuntimeStrip8",
        dispatch_mode="switch",
        include_loader_impls=False,
        include_interrupt_impls=False,
        exclude_split_sections=["COMPONENT_DISPATCH"],
    )
    assert "PASM_SPLIT_BEGIN:COMPONENT_DISPATCH" not in core_impl
    assert "PASM_SPLIT_END:COMPONENT_DISPATCH" not in core_impl
    assert "uint64_t cpu_component_dispatch_callback(" not in core_impl
    assert "void cpu_components_step_post(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before) {" in core_impl
    # Core remains buildable without embedded dispatch bodies; declarations now live in generated header.
    assert "void cpu_components_step_pre(CPUState *cpu, DecodedInstruction *inst, uint16_t pc_before);" in core_impl


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
    assert "int pasm_dbg_pump_host_events(CPUState *cpu);" in header
    assert '#include "DbgApi8_debug_abi.h"' in impl
    assert "CPUState *pasm_dbg_create(size_t memory_size)" in impl
    assert "int pasm_dbg_snapshot_fill(" in impl
    assert "int pasm_dbg_set_pc(CPUState *cpu, uint64_t address)" in impl
    assert "int pasm_dbg_pump_host_events(CPUState *cpu)" in impl
    assert "return dbgapi8_dbg_pump_host_events(cpu);" in impl


def test_debug_abi_pumps_host_hal_when_host_present():
    isa = _base_isa("DbgPump8")
    isa["hosts"] = [
        {
            "metadata": {"id": "host_glfw", "type": "host_adapter", "model": "test"},
            "backend": {"target": "glfw"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    header, impl = generate_debug_abi(isa, "DbgPump8")
    assert "int dbgpump8_dbg_pump_host_events(CPUState *cpu);" in header
    assert "extern void cpu_host_hal_pump_events(void);" in impl
    assert "cpu_host_hal_pump_events();" in impl
    assert "return dbgpump8_dbg_pump_host_events(cpu);" in impl


def test_generated_header_exposes_split_dispatch_contracts(tmp_path):
    isa = _base_isa("SplitContract8")
    processor_path, system_path = write_pair_from_legacy(tmp_path, "split_contract8", isa)
    outdir = tmp_path / "split_contract8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    hdr = (outdir / "src" / "SplitContract8.h").read_text(encoding="utf-8")
    assert "typedef struct {" in hdr
    assert "} ComponentConnection;" in hdr
    assert "uint64_t cpu_component_call(" in hdr
    assert "void cpu_component_emit_signal(" in hdr
    assert "uint64_t cpu_component_dispatch_callback(" in hdr
    assert "void cpu_component_dispatch_handler(" in hdr
    assert "extern const ComponentConnection g_component_connections[];" in hdr
    assert "extern const size_t g_component_connections_count;" in hdr


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
    assert manifest["system_prefix"] == "dbg_link8_test"
    assert manifest["cmake_library_target"] == "dbg_link8_test_system"
    assert manifest["library_basename"] == "dbg_link8_test_system"
    assert manifest["split_targets"]["cpu_core"] == "dbglink8_cpu_core"
    assert manifest["split_targets"]["system"] == "dbg_link8_test_system"
    assert "compat" not in manifest
    assert manifest["split_artifacts"]["cpu_core_static"] in {
        "libdbglink8_cpu_core.a",
        "dbglink8_cpu_core.lib",
    }
    assert manifest["split_artifacts"]["system_static"] in {
        "libdbg_link8_test_system.a",
        "dbg_link8_test_system.lib",
    }
    assert manifest["split_units"]["cpu_core_sources"] == [
        "src/DbgLink8_core.c",
        "src/DbgLink8_decoder.c",
        "src/DbgLink8_debug_abi.c",
    ]
    assert "src/dbg_link8_test_runtime.c" in manifest["split_units"]["system_sources"]
    assert "src/dbg_link8_test_debug_abi.c" not in manifest["split_units"]["system_sources"]
    assert manifest["headers"]["debug_abi"] == "src/DbgLink8_debug_abi.h"
    assert "link" in manifest
    assert isinstance(manifest["link"]["library_names"], list)


def test_generator_prunes_stale_split_units(tmp_path):
    isa = _base_isa("Prune8")
    processor_path, system_path = write_pair_from_legacy(tmp_path, "prune8", isa)
    outdir = tmp_path / "prune8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    stale = outdir / "src" / "legacy_runtime.c"
    stale.write_text("/* stale */\n", encoding="utf-8")
    assert stale.exists()

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))
    assert not stale.exists()


def test_generator_prunes_stale_split_unit_headers(tmp_path):
    isa = _base_isa("PruneHdr8")
    processor_path, system_path = write_pair_from_legacy(tmp_path, "prune_hdr8", isa)
    outdir = tmp_path / "prune_hdr8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    stale_h = outdir / "src" / "legacy_runtime.h"
    stale_h.write_text("/* stale header */\n", encoding="utf-8")
    assert stale_h.exists()

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))
    assert not stale_h.exists()


def test_generator_keeps_current_split_runtime_header(tmp_path):
    isa = _base_isa("KeepHdr8")
    processor_path, system_path = write_pair_from_legacy(tmp_path, "keep_hdr8", isa)
    outdir = tmp_path / "keep_hdr8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    runtime_h = outdir / "src" / "keep_hdr8_test_runtime.h"
    runtime_h.write_text("/* current split header */\n", encoding="utf-8")
    assert runtime_h.exists()

    # Add an unrelated stale split header and ensure only stale one is removed.
    stale_h = outdir / "src" / "legacy_runtime.h"
    stale_h.write_text("/* stale header */\n", encoding="utf-8")
    assert stale_h.exists()

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))
    assert runtime_h.exists()
    assert not stale_h.exists()


def test_generator_prunes_stale_system_debug_abi_units(tmp_path):
    isa = _base_isa("PruneDbgAbi8")
    processor_path, system_path = write_pair_from_legacy(tmp_path, "prune_dbg_abi8", isa)
    outdir = tmp_path / "prune_dbg_abi8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    stale_c = outdir / "src" / "prune_dbg_abi8_debug_abi.c"
    stale_h = outdir / "src" / "prune_dbg_abi8_debug_abi.h"
    stale_c.write_text("/* stale */\n", encoding="utf-8")
    stale_h.write_text("/* stale */\n", encoding="utf-8")
    assert stale_c.exists()
    assert stale_h.exists()

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))
    assert not stale_c.exists()
    assert not stale_h.exists()

    # CPU-owned debug ABI units must remain.
    assert (outdir / "src" / "PruneDbgAbi8_debug_abi.c").exists()
    assert (outdir / "src" / "PruneDbgAbi8_debug_abi.h").exists()


def test_generator_emits_real_core_tu_without_legacy_cpu_shim(tmp_path):
    isa = _base_isa("SplitCore8")
    processor_path, system_path = write_pair_from_legacy(tmp_path, "split_core8", isa)
    outdir = tmp_path / "split_core8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    core_impl = (outdir / "src" / "SplitCore8_core.c").read_text(encoding="utf-8")
    assert "CPUState *splitcore8_create(size_t memory_size)" in core_impl
    assert not (outdir / "src" / "SplitCore8.c").exists()


def test_generator_prunes_stale_legacy_cpu_shim(tmp_path):
    isa = _base_isa("NoShim8")
    processor_path, system_path = write_pair_from_legacy(tmp_path, "no_shim8", isa)
    outdir = tmp_path / "no_shim8_out"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    stale = outdir / "src" / "NoShim8.c"
    stale.write_text("/* stale shim */\n", encoding="utf-8")
    assert stale.exists()

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))
    assert not stale.exists()


def test_debugger_link_manifest_includes_backend_target_libraries(tmp_path):
    isa = _base_isa("DbgLinkHal8")
    isa["instructions"][0]["timing_profile"] = {"total_tstates": 1, "bus_events": []}
    processor_path, system_path = write_pair_from_legacy(
        tmp_path,
        "dbg_link_hal8",
        isa,
        system_overrides={"components": {"ics": [], "devices": [], "hosts": ["host_hal"]}},
    )
    host_yaml = tmp_path / "host_hal.yaml"
    host_data = {
        "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test_host_hal"},
        "backend": {"target": "sdl2"},
        "state": [],
        "interfaces": {"callbacks": [], "handlers": [], "signals": []},
        "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
        "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
    }
    host_yaml.write_text(yaml.safe_dump(host_data, sort_keys=False), encoding="utf-8")

    outdir = tmp_path / "dbg_link_hal8_out"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        host_paths=[str(host_yaml)],
    )

    manifest_path = outdir / "debugger_link.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "SDL2" in manifest["link"]["library_names"]

    host_data["backend"] = {"target": "glfw"}
    host_yaml.write_text(yaml.safe_dump(host_data, sort_keys=False), encoding="utf-8")
    outdir_glfw = tmp_path / "dbg_link_hal8_glfw_out"
    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir_glfw),
        host_paths=[str(host_yaml)],
    )
    manifest_glfw = json.loads((outdir_glfw / "debugger_link.json").read_text(encoding="utf-8"))
    assert "SDL2" in manifest_glfw["link"]["library_names"]
    assert ("glfw3dll" if os.name == "nt" else "glfw") in manifest_glfw["link"]["library_names"]
    assert ("opengl32" if os.name == "nt" else "GL") in manifest_glfw["link"]["library_names"]
    if os.name == "nt":
        assert "winmm" in manifest_glfw["link"]["library_names"]
    if sys.platform.startswith("linux"):
        assert "asound" in manifest_glfw["link"]["library_names"]


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
    split_runtime = next((outdir / "src").glob("*_runtime.c"))
    split_system_bus = next((outdir / "src").glob("*_system_bus.c"))
    split_system_glue = next((outdir / "src").glob("*_system_glue.c"))
    split_host_glue = next((outdir / "src").glob("*_host_glue.c"))
    split_device_glue = next((outdir / "src").glob("*_device_glue.c"))
    subprocess.check_call(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-D_POSIX_C_SOURCE=199309L",
            "-I",
            str(outdir / "src"),
            str(outdir / "src" / "RomLoad8_core.c"),
            str(outdir / "src" / "RomLoad8_decoder.c"),
            str(split_runtime),
            str(split_system_bus),
            str(split_system_glue),
            str(split_host_glue),
            str(split_device_glue),
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

    impl_c = (outdir / "src" / "Hook8_core.c").read_text()
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
    impl = (outdir / "src" / "Minimal8_core.c").read_text()

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
    isa["metadata"]["codegen"]["display_kinds_enabled"] = ["mc6809_pshs_mask"]
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
    isa["metadata"]["codegen"]["architecture_id"] = "mos6502"
    isa["metadata"]["codegen"]["numeric_style"] = "asm_dollar"
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
    isa["interrupts"] = {"model": "z80", "modes": [{"name": "IM0"}]}
    code = generate_cpu_impl(isa, "Int8")
    assert "cpu->interrupt_pending && cpu->interrupts_enabled" in code
    assert "switch (irq_mode)" in code
    assert "cpu->interrupts_enabled = false;" in code


def test_breakpoint_check_precedes_interrupt_dispatch():
    isa = _base_isa("IntBpOrder8")
    isa["interrupts"] = {"model": "z80", "modes": [{"name": "IM1"}]}
    code = generate_cpu_impl(isa, "IntBpOrder8")
    bp_idx = code.find("if (cpu_check_breakpoints(cpu)) {")
    irq_idx = code.find("if (cpu->interrupt_pending && cpu->interrupts_enabled) {")
    assert bp_idx >= 0
    assert irq_idx >= 0
    assert bp_idx < irq_idx


def test_interrupt_api_queues_pending_even_when_irq_disabled():
    isa = _base_isa("IntApi8")
    isa["interrupts"] = {"model": "z80", "modes": [{"name": "IM1"}]}
    code = generate_cpu_impl(isa, "IntApi8")
    assert "if (!cpu->interrupts_enabled) return;" not in code
    assert "cpu->interrupt_pending = true;" in code


def test_interrupt_mode_gating_and_im2_vector_table_lookup():
    isa = _base_isa("IntMode8")
    isa["registers"].append({"name": "I", "type": "special", "bits": 8})
    isa["interrupts"] = {"model": "z80", "modes": [{"name": "IM1"}, {"name": "IM2"}]}
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
    assert "cpu->sp =" in code
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
    impl_c = (outdir / "src" / "Minimal8_core.c").read_text()
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
    impl_c = (outdir / "src" / "Minimal8_core.c").read_text()
    cmake_text = (outdir / "CMakeLists.txt").read_text()
    assert "CPU_USE_THREADED_DISPATCH" in impl_c
    assert "USE_THREADED_DISPATCH" in cmake_text


def test_interactive_host_uses_declarative_keyboard_map_generation():
    data = _base_isa("HostKeyMap8")
    data["hosts"] = [
        {
            "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {
                "headers": [],
                "include_paths": [],
                "linked_libraries": [],
                "library_paths": [],
            },
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "cpu_component_apply_declared_keymap(" in code
    assert "if (g_runtime_keyboard_map.focus_required && has_focus == 0u) return;" in code
    assert "cpu_component_scancode_for_host_key(" in code
    assert "#if CPU_HOST_HAS_SCANCODE_MAP" in code
    assert "CPU_HOST_SCANCODE(BACKSPACE)" in code
    assert "CPU_HOST_SCANCODE(LEFT)" in code
    assert "component_host_hal_keyboard_bindings" not in code
    assert "CPU_HOST_SCANCODE(BACKSPACE)" in code
    assert "CPU_HOST_SCANCODE(LEFT)" in code
    assert "ks[SDL_SCANCODE_A]" not in code


def test_interactive_host_canonical_keys_map_to_sdl_scancodes_in_codegen():
    data = _base_isa("CanonicalHostKey8")
    data["hosts"] = [
        {
            "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {
                "headers": [],
                "include_paths": [],
                "linked_libraries": [],
                "library_paths": [],
            },
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "cpu_component_scancode_for_host_key(" in code
    assert "#if CPU_HOST_HAS_SCANCODE_MAP" in code
    assert "CPU_HOST_SCANCODE(BACKSPACE)" in code


def test_interactive_host_stub_backend_does_not_emit_sdl_scancodes():
    data = _base_isa("StubHostKey8")
    data["hosts"] = [
        {
            "metadata": {"id": "host_stub", "type": "host_adapter", "model": "test"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {
                "headers": [],
                "include_paths": [],
                "linked_libraries": [],
                "library_paths": [],
            },
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "cpu_component_scancode_for_host_key(" in code
    assert "#if CPU_HOST_HAS_SCANCODE_MAP" in code
    assert "CPU_HOST_SCANCODE(BACKSPACE)" in code
    assert "SDL_SCANCODE_BACKSPACE" not in code


def test_runtime_hal_helpers_emit_sdl2_impl_for_sdl2_backend():
    data = _base_isa("HostHalSdl2")
    data["hosts"] = [
        {
            "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static uint8_t cpu_host_hal_sdl_inited = 0u;" in code
    assert "static uint32_t cpu_host_hal_sdl_subsystems = 0u;" in code
    assert "static SDL_Window *cpu_host_hal_sdl_primary_window = NULL;" in code
    assert "static void cpu_host_hal_pump_events(void)" in code
    assert "if (cpu_host_hal_sdl_inited == 0u) return;" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return;" in code
    assert "SDL_PumpEvents();" in code
    assert "static uint32_t cpu_host_hal_ticks_ms(void)" in code
    assert "if (cpu_host_hal_sdl_inited == 0u) return 0u;" in code
    assert "return SDL_GetTicks();" in code
    assert "static uint8_t cpu_host_hal_window_has_focus(void *window)" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return 0u;" in code
    assert "if (!window) window = (void *)cpu_host_hal_sdl_primary_window;" in code
    assert "SDL_GetKeyboardFocus()" in code


def test_runtime_hal_helpers_emit_noop_impl_for_stub_backend():
    data = _base_isa("HostHalStub")
    data["hosts"] = [
        {
            "metadata": {"id": "host_stub", "type": "host_adapter", "model": "test"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static void cpu_host_hal_pump_events(void)" in code
    assert "static uint32_t cpu_host_hal_ticks_ms(void)" in code
    assert "static uint8_t cpu_host_hal_window_has_focus(void *window)" in code
    assert "return 0u;" in code
    assert "SDL_PumpEvents();" not in code
    assert "SDL_GetTicks();" not in code
    assert "SDL_GetKeyboardFocus()" not in code


def test_runtime_hal_helpers_emit_glfw_impl_for_glfw_backend():
    data = _base_isa("HostHalGlfw")
    data["hosts"] = [
        {
            "metadata": {"id": "host_glfw", "type": "host_adapter", "model": "test"},
            "backend": {"target": "glfw"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static void cpu_host_hal_pump_events(void)" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return;" in code
    assert "glfwPollEvents();" in code
    assert "static uint32_t cpu_host_hal_ticks_ms(void)" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return 0u;" in code
    assert "double t = glfwGetTime();" in code
    assert "if (!(t > 0.0)) return 0u;" in code
    assert "static uint8_t cpu_host_hal_window_has_focus(void *window)" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return 0u;" in code
    assert "if (!window) window = (void *)cpu_host_hal_glfw_primary_window;" in code
    assert "glfwGetWindowAttrib((GLFWwindow *)window, GLFW_FOCUSED)" in code
    assert "if (!glfwInit()) {" in code
    assert "cpu_host_hal_log(\"host_init video unavailable; continuing without GLFW window path\");" in code
    assert "cpu_host_hal_glfw_inited = 1u;" in code
    assert "static GLFWwindow *cpu_host_hal_glfw_primary_window = NULL;" in code
    assert "static uint8_t cpu_host_hal_glfw_inited = 0u;" in code
    assert "static uint32_t cpu_host_hal_glfw_subsystems = 0u;" in code
    assert "cpu_host_hal_glfw_subsystems |= flags;" in code
    assert "cpu_host_hal_glfw_primary_window = NULL;" in code
    assert "cpu_host_hal_glfw_poll_cursor = 0;" in code
    assert "cpu_host_hal_glfw_quit_emitted = 0u;" in code
    assert "glfwWindowShouldClose(cpu_host_hal_glfw_primary_window) != 0" in code
    assert "event->type = CPU_HOST_EVENT_QUIT;" in code
    assert "cpu_host_hal_glfw_quit_emitted = 1u;" in code
    assert "glfwGetWindowSize((GLFWwindow *)window, out_w, out_h);" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return;" in code
    assert "glfwMakeContextCurrent(window);" in code
    assert "glfwSwapBuffers(window);" in code
    assert "if (!window) window = (void *)cpu_host_hal_glfw_primary_window;" in code
    assert "cpu_host_hal_glfw_key_for_scancode(sc)" in code
    assert "static const char *cpu_host_hal_glfw_scancode_name(int scancode)" in code
    assert "case CPU_GLFW_SC_APPLICATION: return \"APPLICATION\";" in code
    assert "default: return \"UNKNOWN\";" in code
    assert "event->type = (down != 0u) ? CPU_HOST_EVENT_KEYDOWN : CPU_HOST_EVENT_KEYUP;" in code
    assert "down = (uint8_t)((key == GLFW_PRESS || key == GLFW_REPEAT) ? 1u : 0u);" in code
    assert "cpu_host_hal_glfw_hold_ticks[sc] = (uint16_t)(down != 0u ? 1u : 0u);" in code
    assert "if (held > 18u && (((uint16_t)(held - 18u) % 3u) == 0u)) {" in code
    assert "event->key.repeat = 1u;" in code
    assert "cpu_host_hal_glfw_event_mod_state = cpu_host_hal_glfw_mod_state();" in code
    assert "event->key.mod_state = cpu_host_hal_glfw_event_mod_state;" in code
    assert "static uint32_t cpu_host_hal_glfw_mod_state(void)" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return 0u;" in code
    assert "if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;" in code
    assert "return event->type;" in code
    assert "if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0;" in code
    assert "return (int32_t)event->key.keysym.scancode;" in code
    assert "if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0u;" in code
    assert "return event->key.repeat;" in code
    assert "if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return cpu_host_hal_glfw_event_mod_state;" in code
    assert "return event->key.mod_state;" in code
    assert "return cpu_host_hal_glfw_mod_state();" in code
    assert "CPU_GLFW_SC_APPLICATION" in code
    assert "CPU_GLFW_SC_INTERNATIONAL1" in code
    assert "CPU_GLFW_SC_NONUSBACKSLASH" in code
    assert "CPU_GLFW_SC_F8" in code
    assert "#define GLFW_KEY_F6 295" in code
    assert "#define GLFW_KEY_F7 296" in code
    assert "#define GLFW_KEY_F8 297" in code
    assert "#define CPU_HOST_KEYCODE_QUOTE ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(APOSTROPHE)))" in code
    assert "#define CPU_HOST_KEYCODE_SEMICOLON ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(SEMICOLON)))" in code
    assert "case CPU_GLFW_SC_APPLICATION: return GLFW_KEY_MENU;" in code
    assert "case CPU_GLFW_SC_INTERNATIONAL1: return GLFW_KEY_WORLD_1;" in code
    assert "case CPU_GLFW_SC_NONUSBACKSLASH: return GLFW_KEY_WORLD_1;" in code
    assert "return cpu_host_hal_glfw_scancode_name((int)scancode);" in code
    assert "static const char *cpu_host_hal_glfw_key_name(int keycode)" in code
    assert "case GLFW_KEY_0: return \"0\";" in code
    assert "case GLFW_KEY_APOSTROPHE: return \"APOSTROPHE\";" in code
    assert "case GLFW_KEY_F1: return \"F1\";" in code
    assert "case GLFW_KEY_F8: return \"F8\";" in code
    assert "case GLFW_KEY_KP_ENTER: return \"KP_ENTER\";" in code
    assert "return cpu_host_hal_glfw_key_name((int)keycode);" in code
    assert "static const uint8_t *cpu_host_hal_keyboard_state(int *key_count)" in code
    assert "if (key_count) *key_count = CPU_GLFW_SC_COUNT;" in code
    assert "static uint16_t cpu_host_hal_glfw_hold_ticks[CPU_GLFW_SC_COUNT];" in code
    assert 'case CPU_GLFW_SC_INTERNATIONAL1: return "INTERNATIONAL1";' in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return 0;" in code
    assert "if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0;" in code
    assert "return (int32_t)cpu_host_hal_glfw_key_for_scancode(scancode);" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return \"UNKNOWN\";" in code
    assert "if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return \"UNKNOWN\";" in code
    assert "static int cpu_host_hal_set_texture_blend_none(void *texture)" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return -1;" in code
    assert "if ((cpu_host_hal_glfw_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;" in code
    assert "if (!texture) return -1;" in code
    assert "if ((flags & ~(CPU_HOST_INIT_VIDEO | CPU_HOST_INIT_AUDIO | CPU_HOST_INIT_EVENTS)) != 0u) return -1;" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return -1;" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return NULL;" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return 0u;" in code
    assert "cpu_host_hal_glfw_keys[sc] = (uint8_t)((key == GLFW_PRESS || key == GLFW_REPEAT) ? 1u : 0u);" in code
    assert "if ((flags & ~CPU_HOST_RENDERER_ACCELERATED) != 0u) return NULL;" in code
    assert "if (!window) window = (void *)cpu_host_hal_glfw_primary_window;" in code
    assert "if (format != CPU_HOST_PIXELFORMAT_ARGB8888) return NULL;" in code
    assert "if (access != CPU_HOST_TEXTUREACCESS_STREAMING) return NULL;" in code
    assert "uint64_t need64;" in code
    assert "w64 = (uint64_t)(uint32_t)w;" in code
    assert "h64 = (uint64_t)(uint32_t)h;" in code
    assert "if (w64 != 0u && h64 > (0xFFFFFFFFFFFFFFFFu / w64)) {" in code
    assert "if (need64 > (0xFFFFFFFFFFFFFFFFu / 4u)) {" in code
    assert "need64 *= 4u;" in code
    assert "if (need64 == 0u || need64 > (uint64_t)SIZE_MAX) {" in code
    assert code.count("if (cpu_host_hal_glfw_inited == 0u) return NULL;") >= 3
    assert "if (cpu_host_hal_glfw_inited == 0u) return 0;" in code
    assert code.count("if (cpu_host_hal_glfw_inited == 0u) return -1;") >= 4
    assert "const char *win_title = (title && title[0] != '\\0') ? title : \"PASM\";" in code
    assert "if (w <= 0) w = 640;" in code
    assert "if (h <= 0) h = 480;" in code
    assert "if ((flags & ~CPU_HOST_WINDOW_RESIZABLE) != 0u) return NULL;" in code
    assert "#define GLFW_TRUE 1" in code
    assert "#define GLFW_FALSE 0" in code
    assert "#define GLFW_RESIZABLE 0x00020003" in code
    assert "glfwWindowHint(GLFW_RESIZABLE, (flags & CPU_HOST_WINDOW_RESIZABLE) != 0u ? GLFW_TRUE : GLFW_FALSE);" in code
    assert "if (cpu_host_hal_glfw_inited != 0u && cpu_host_hal_glfw_primary_window != NULL) {" in code
    assert "glfwDestroyWindow(cpu_host_hal_glfw_primary_window);" in code
    assert "cpu_host_hal_glfw_subsystems = 0u;" in code
    assert "if (!out_w || !out_h) return -1;" in code
    assert "typedef struct {" in code
    assert "} CPUHostGlfwRenderer;" in code
    assert "} CPUHostGlfwTexture;" in code
    assert "rr = (CPUHostGlfwRenderer *)calloc(1u, sizeof(*rr));" in code
    assert "if (cpu_host_hal_glfw_renderer_sync_size(rr) != 0) {" in code
    assert "free(rr);" in code
    assert "return NULL;" in code
    assert "return rr;" in code
    assert "tex = (CPUHostGlfwTexture *)calloc(1u, sizeof(*tex));" in code
    assert "tex->pixels_len = need;" in code
    assert "return tex;" in code
    assert "SDL_PumpEvents();" not in code


def test_cpu_host_keycode_aliases_are_backend_neutral_across_targets():
    def _gen_for_target(target: str) -> str:
        data = _base_isa(f"HostKeyAlias_{target}")
        data["hosts"] = [
            {
                "metadata": {"id": f"host_{target}", "type": "host_adapter", "model": "test"},
                "backend": {"target": target},
                "state": [],
                "interfaces": {"callbacks": [], "handlers": [], "signals": []},
                "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
                "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
            }
        ]
        return generate_cpu_impl(data, "Z80")

    expected_quote = "#define CPU_HOST_KEYCODE_QUOTE ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(APOSTROPHE)))"
    expected_semicolon = "#define CPU_HOST_KEYCODE_SEMICOLON ((int32_t)cpu_host_hal_key_from_scancode(CPU_HOST_SCANCODE(SEMICOLON)))"

    for target in ("sdl2", "glfw", "stub"):
        code = _gen_for_target(target)
        assert expected_quote in code
        assert expected_semicolon in code


def test_runtime_hal_frame_audio_helpers_emit_sdl2_impl():
    data = _base_isa("HostHalFrameAudioSdl2")
    data["hosts"] = [
        {
            "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static void cpu_host_hal_render_present(void *renderer)" in code
    assert "SDL_RenderPresent((SDL_Renderer *)renderer);" in code
    assert "static int cpu_host_hal_audio_queue(uint32_t dev, const void *data, uint32_t len_bytes)" in code
    assert "return SDL_QueueAudio(dev, data, len_bytes);" in code
    assert "static uint32_t cpu_host_hal_audio_queued_bytes(uint32_t dev)" in code
    assert "return SDL_GetQueuedAudioSize(dev);" in code
    assert "static void cpu_host_hal_audio_clear(uint32_t dev)" in code
    assert "SDL_ClearQueuedAudio(dev);" in code


def test_runtime_hal_frame_audio_helpers_emit_noop_impl_for_stub():
    data = _base_isa("HostHalFrameAudioStub")
    data["hosts"] = [
        {
            "metadata": {"id": "host_stub", "type": "host_adapter", "model": "test"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static void cpu_host_hal_render_present(void *renderer)" in code
    assert "static int cpu_host_hal_audio_queue(uint32_t dev, const void *data, uint32_t len_bytes)" in code
    assert "static uint32_t cpu_host_hal_audio_queued_bytes(uint32_t dev)" in code
    assert "static void cpu_host_hal_audio_clear(uint32_t dev)" in code
    assert "static uint8_t *cpu_host_hal_stub_audio_buf = NULL;" in code
    assert "static uint32_t cpu_host_hal_stub_audio_len = 0u;" in code
    assert "static uint32_t cpu_host_hal_stub_audio_cap = 0u;" in code
    assert "static uint8_t cpu_host_hal_stub_audio_opened = 0u;" in code
    assert "static void cpu_host_hal_stub_reset_audio_state(void)" in code
    assert "if (cpu_host_hal_stub_inited == 0u) return -1;" in code
    assert "if (dev != 1u || !data || len_bytes == 0u || cpu_host_hal_stub_audio_opened == 0u) return -1;" in code
    assert "if (cpu_host_hal_stub_audio_len > cpu_host_hal_stub_audio_cap) return -1;" in code
    assert "if (cpu_host_hal_stub_audio_cap != 0u && cpu_host_hal_stub_audio_buf == NULL) return -1;" in code
    assert "if (cpu_host_hal_stub_audio_len != 0u && cpu_host_hal_stub_audio_buf == NULL) return -1;" in code
    assert "if (cpu_host_hal_stub_inited == 0u) return 0u;" in code
    assert "if (dev != 1u || cpu_host_hal_stub_audio_opened == 0u) return 0u;" in code
    assert "if (cpu_host_hal_stub_audio_len > cpu_host_hal_stub_audio_cap) return 0u;" in code
    assert "if (cpu_host_hal_stub_audio_cap != 0u && cpu_host_hal_stub_audio_buf == NULL) return 0u;" in code
    assert "if (cpu_host_hal_stub_audio_len != 0u && cpu_host_hal_stub_audio_buf == NULL) return 0u;" in code
    assert "if (iscapture != 0) return 0u;" in code
    assert "cpu_host_hal_stub_audio_opened = 1u;" in code
    assert "static uint32_t cpu_host_hal_audio_dequeue(uint32_t dev, void *data, uint32_t len_bytes)" in code
    assert "n = (cpu_host_hal_stub_audio_len < len_bytes) ? cpu_host_hal_stub_audio_len : len_bytes;" in code
    assert "memmove(" in code
    assert "static int cpu_host_hal_get_window_size(void *window, int *out_w, int *out_h)" in code
    assert "if (out_w) *out_w = 0;" in code
    assert "if (out_h) *out_h = 0;" in code
    assert "if (cpu_host_hal_stub_inited == 0u) return 0;" in code
    assert "if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0;" in code
    assert "CPUHostStubWindow *ww = (window != NULL) ? (CPUHostStubWindow *)window : cpu_host_hal_stub_primary_window;" in code
    assert "SDL_RenderPresent(" not in code
    assert "SDL_QueueAudio(" not in code
    assert "SDL_GetQueuedAudioSize(" not in code
    assert "SDL_ClearQueuedAudio(" not in code


def test_runtime_hal_frame_audio_helpers_emit_glfw_buffer_impl():
    data = _base_isa("HostHalFrameAudioGlfw")
    data["hosts"] = [
        {
            "metadata": {"id": "host_glfw", "type": "host_adapter", "model": "test"},
            "backend": {"target": "glfw"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static void cpu_host_hal_glfw_reset_audio_state(void)" in code
    assert "static void cpu_host_hal_glfw_audio_thread_drain(uint32_t timeout_ms)" in code
    assert "cpu_host_hal_glfw_audio_thread_drain(200u);" in code
    assert "snd_pcm_drain(cpu_host_hal_glfw_alsa_pcm);" in code
    assert "cpu_host_hal_glfw_reset_audio_state();" in code
    assert "static uint8_t *cpu_host_hal_glfw_audio_buf = NULL;" in code
    assert "static uint32_t cpu_host_hal_glfw_audio_len = 0u;" in code
    assert "static uint32_t cpu_host_hal_glfw_audio_cap = 0u;" in code
    assert "static uint8_t cpu_host_hal_glfw_audio_opened = 0u;" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return -1;" in code
    assert "if (dev == 0u || !data || len_bytes == 0u || cpu_host_hal_glfw_audio_opened == 0u) return -1;" in code
    assert "if (!want) return 0u;" in code
    assert "if (want->freq <= 0 || want->channels == 0u || want->samples == 0u) return 0u;" in code
    assert "cpu_host_hal_glfw_reset_audio_state();" in code
    assert "uint64_t bytes64;" in code
    assert "if (have) {" in code
    assert "*have = *want;" in code
    assert "uint64_t need64;" in code
    assert "need64 = (uint64_t)cpu_host_hal_glfw_audio_len + (uint64_t)len_bytes;" in code
    assert "if (need64 == 0u || need64 > 0xFFFFFFFFu || need64 > (uint64_t)SIZE_MAX) return -1;" in code
    assert "need = (uint32_t)need64;" in code
    assert "if (cpu_host_hal_glfw_audio_len > cpu_host_hal_glfw_audio_cap) return -1;" in code
    assert "if (cpu_host_hal_glfw_audio_cap != 0u && cpu_host_hal_glfw_audio_buf == NULL) return -1;" in code
    assert "if (cpu_host_hal_glfw_audio_len != 0u && cpu_host_hal_glfw_audio_buf == NULL) return -1;" in code
    assert "if (new_cap < need || (uint64_t)new_cap > (uint64_t)SIZE_MAX) return -1;" in code
    assert "new_buf = (uint8_t *)realloc(cpu_host_hal_glfw_audio_buf, (size_t)new_cap);" in code
    assert "cpu_host_hal_glfw_audio_len = need;" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return 0u;" in code
    assert "if (dev == 0u || cpu_host_hal_glfw_audio_opened == 0u) return 0u;" in code
    assert "if (cpu_host_hal_glfw_audio_len > cpu_host_hal_glfw_audio_cap) return 0u;" in code
    assert "if (cpu_host_hal_glfw_audio_cap != 0u && cpu_host_hal_glfw_audio_buf == NULL) return 0u;" in code
    assert "if (cpu_host_hal_glfw_audio_len != 0u && cpu_host_hal_glfw_audio_buf == NULL) return 0u;" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return;" in code
    assert "snd_pcm_drop(cpu_host_hal_glfw_alsa_pcm);" in code
    assert "snd_pcm_prepare(cpu_host_hal_glfw_alsa_pcm);" in code
    assert "cpu_host_hal_glfw_audio_len = 0u;" in code
    assert "if (out_w) *out_w = 0;" in code
    assert "if (out_h) *out_h = 0;" in code
    assert "if (*out_w <= 0 || *out_h <= 0) return -1;" in code
    assert "if (want) *have = *want;" not in code
    assert "if (iscapture != 0) return 0u;" in code
    assert "bytes64 = (uint64_t)have->samples * (uint64_t)have->channels * 2u;" in code
    assert "if (bytes64 > 0xFFFFFFFFu) return 0u;" in code
    assert "have->size = (uint32_t)bytes64;" in code
    assert "cpu_host_hal_glfw_audio_opened = 1u;" in code
    assert "return 1u;" in code
    assert "cpu_host_hal_glfw_reset_audio_state();" in code
    assert code.count("cpu_host_hal_glfw_reset_audio_state();") >= 3
    assert "n = (cpu_host_hal_glfw_audio_len < len_bytes) ? cpu_host_hal_glfw_audio_len : len_bytes;" in code
    assert "if (cpu_host_hal_glfw_audio_len > cpu_host_hal_glfw_audio_cap) return 0u;" in code
    assert "if (cpu_host_hal_glfw_audio_len != 0u && cpu_host_hal_glfw_audio_buf == NULL) return 0u;" in code
    assert "memmove(" in code


def test_runtime_hal_lifecycle_helpers_emit_sdl2_impl():
    data = _base_isa("HostHalLifecycleSdl2")
    data["hosts"] = [
        {
            "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static int cpu_host_hal_poll_event(CPUHostEvent *event)" in code
    assert "return SDL_PollEvent((SDL_Event *)event);" in code
    assert "static uint32_t cpu_host_hal_event_type(const CPUHostEvent *event)" in code
    assert "static int32_t cpu_host_hal_event_scancode(const CPUHostEvent *event)" in code
    assert "if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0;" in code
    assert "static int32_t cpu_host_hal_event_keycode(const CPUHostEvent *event)" in code
    assert "return (int32_t)event->key.keysym.sym;" in code
    assert "static uint8_t cpu_host_hal_event_key_repeat(const CPUHostEvent *event)" in code
    assert "if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0u;" in code
    assert "static uint32_t cpu_host_hal_event_mod_state(const CPUHostEvent *event)" in code
    assert "if (event->type != CPU_HOST_EVENT_KEYDOWN && event->type != CPU_HOST_EVENT_KEYUP) return 0u;" in code
    assert "static void cpu_host_hal_set_window_title(void *window, const char *title)" in code
    assert "SDL_SetWindowTitle((SDL_Window *)window, title);" in code
    assert "static void cpu_host_hal_destroy_texture(void *texture)" in code
    assert "if (cpu_host_hal_sdl_inited == 0u) return;" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;" in code
    assert "SDL_DestroyTexture((SDL_Texture *)texture);" in code
    assert "static void cpu_host_hal_destroy_renderer(void *renderer)" in code
    assert "SDL_DestroyRenderer((SDL_Renderer *)renderer);" in code
    assert "static void cpu_host_hal_destroy_window(void *window)" in code
    assert "if (cpu_host_hal_sdl_inited == 0u) return;" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;" in code
    assert "SDL_DestroyWindow((SDL_Window *)window);" in code
    assert "static void cpu_host_hal_audio_close(uint32_t dev)" in code
    assert "SDL_CloseAudioDevice(dev);" in code
    assert "static void cpu_host_hal_quit_subsystems(void)" in code
    assert "uint32_t to_quit = cpu_host_hal_sdl_subsystems & (CPU_HOST_INIT_VIDEO | CPU_HOST_INIT_AUDIO | CPU_HOST_INIT_EVENTS);" in code
    assert "if (to_quit != 0u) SDL_QuitSubSystem(to_quit);" in code
    assert "cpu_host_hal_sdl_subsystems &= ~to_quit;" in code
    assert "cpu_host_hal_sdl_primary_window = NULL;" in code
    assert "static void cpu_host_hal_quit(void)" in code
    assert "SDL_Quit();" in code
    assert "cpu_host_hal_sdl_subsystems = 0u;" in code
    assert "cpu_host_hal_sdl_inited = 0u;" in code
    assert "cpu_host_hal_sdl_primary_window = NULL;" in code


def test_runtime_hal_lifecycle_helpers_emit_noop_impl_for_stub():
    data = _base_isa("HostHalLifecycleStub")
    data["hosts"] = [
        {
            "metadata": {"id": "host_stub", "type": "host_adapter", "model": "test"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static int cpu_host_hal_poll_event(CPUHostEvent *event)" in code
    assert "static uint32_t cpu_host_hal_event_type(const CPUHostEvent *event)" in code
    assert "static int32_t cpu_host_hal_event_scancode(const CPUHostEvent *event)" in code
    assert "static int32_t cpu_host_hal_event_keycode(const CPUHostEvent *event)" in code
    assert "static uint8_t cpu_host_hal_event_key_repeat(const CPUHostEvent *event)" in code
    assert "static void cpu_host_hal_set_window_title(void *window, const char *title)" in code
    assert "static void cpu_host_hal_destroy_texture(void *texture)" in code
    assert "static void cpu_host_hal_destroy_renderer(void *renderer)" in code
    assert "static void cpu_host_hal_destroy_window(void *window)" in code
    assert "static void cpu_host_hal_audio_close(uint32_t dev)" in code
    assert "static void cpu_host_hal_quit_subsystems(void)" in code
    assert "static void cpu_host_hal_quit(void)" in code
    assert "static uint8_t cpu_host_hal_stub_inited = 0u;" in code
    assert "static uint32_t cpu_host_hal_stub_subsystems = 0u;" in code
    assert "static CPUHostStubWindow *cpu_host_hal_stub_primary_window = NULL;" in code
    assert "if (cpu_host_hal_stub_inited == 0u) return;" in code
    assert "if ((cpu_host_hal_stub_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;" in code
    assert "if (cpu_host_hal_stub_primary_window == (CPUHostStubWindow *)window) {" in code
    assert "cpu_host_hal_stub_primary_window = NULL;" in code
    assert "if (cpu_host_hal_stub_primary_window != NULL) {" in code
    assert "free(cpu_host_hal_stub_primary_window);" in code
    assert "if ((flags & ~(CPU_HOST_INIT_VIDEO | CPU_HOST_INIT_AUDIO | CPU_HOST_INIT_EVENTS)) != 0u) return -1;" in code
    assert "cpu_host_hal_stub_inited = 1u;" in code
    assert "cpu_host_hal_stub_subsystems |= flags;" in code
    assert "cpu_host_hal_stub_inited = 0u;" in code
    assert "cpu_host_hal_stub_subsystems = 0u;" in code
    assert "cpu_host_hal_stub_reset_audio_state();" in code
    assert "SDL_PollEvent(" not in code
    assert "SDL_SetWindowTitle(" not in code
    assert "SDL_DestroyTexture(" not in code
    assert "SDL_DestroyRenderer(" not in code
    assert "SDL_DestroyWindow(" not in code
    assert "SDL_CloseAudioDevice(" not in code
    assert "SDL_QuitSubSystem(" not in code
    assert "SDL_Quit();" not in code


def test_runtime_hal_init_create_helpers_emit_sdl2_impl():
    data = _base_isa("HostHalInitSdl2")
    data["hosts"] = [
        {
            "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static int cpu_host_hal_init(uint32_t flags)" in code
    assert "if (cpu_host_hal_sdl_inited == 0u) {" in code
    assert "if (SDL_Init(flags) != 0) return -1;" in code
    assert "cpu_host_hal_sdl_inited = 1u;" in code
    assert "cpu_host_hal_sdl_subsystems |= flags;" in code
    assert "if (flags != 0u) {" in code
    assert "if (SDL_InitSubSystem(flags) != 0) return -1;" in code
    assert "return 0;" in code
    assert "static void *cpu_host_hal_create_window(" in code
    assert "SDL_Window *window;" in code
    assert "const char *win_title = (title && title[0] != '\\0') ? title : \"PASM\";" in code
    assert "if ((flags & ~CPU_HOST_WINDOW_RESIZABLE) != 0u) return NULL;" in code
    assert "if (w <= 0) w = 640;" in code
    assert "if (h <= 0) h = 480;" in code
    assert "window = SDL_CreateWindow(win_title, x, y, w, h, flags);" in code
    assert "if (window != NULL && cpu_host_hal_sdl_primary_window == NULL) {" in code
    assert "cpu_host_hal_sdl_primary_window = window;" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return NULL;" in code
    assert "SDL_CreateWindow(" in code
    assert "static void *cpu_host_hal_create_renderer(" in code
    assert "if (!window) window = (void *)cpu_host_hal_sdl_primary_window;" in code
    assert "if ((flags & ~CPU_HOST_RENDERER_ACCELERATED) != 0u) return NULL;" in code
    assert "SDL_CreateRenderer(" in code
    assert "static void *cpu_host_hal_create_texture(" in code
    assert "SDL_CreateTexture(" in code
    assert "static uint32_t cpu_host_hal_audio_open(" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return 0u;" in code
    assert "if (iscapture != 0) return 0u;" in code
    assert "if (!want) return 0u;" in code
    assert "if (want->freq <= 0 || want->channels == 0u || want->samples == 0u) return 0u;" in code
    assert "SDL_OpenAudioDevice(" in code
    assert "static void cpu_host_hal_audio_pause(uint32_t dev, int pause_on)" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_AUDIO) == 0u) return;" in code
    assert "SDL_PauseAudioDevice(dev, pause_on);" in code
    assert "static void *cpu_host_hal_alloc(size_t size_bytes)" in code
    assert "return SDL_malloc(size_bytes);" in code
    assert "static void cpu_host_hal_free(void *ptr)" in code
    assert "SDL_free(ptr);" in code
    assert "static void cpu_host_hal_memset(void *dst, int value, size_t size_bytes)" in code
    assert "SDL_memset(dst, value, size_bytes);" in code


def test_runtime_hal_init_create_helpers_emit_noop_impl_for_stub():
    data = _base_isa("HostHalInitStub")
    data["hosts"] = [
        {
            "metadata": {"id": "host_stub", "type": "host_adapter", "model": "test"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static int cpu_host_hal_init(uint32_t flags)" in code
    assert "static void *cpu_host_hal_create_window(" in code
    assert "static void *cpu_host_hal_create_renderer(" in code
    assert "static void *cpu_host_hal_create_texture(" in code
    assert "static uint32_t cpu_host_hal_audio_open(" in code
    assert "static void cpu_host_hal_audio_pause(uint32_t dev, int pause_on)" in code
    assert "static void *cpu_host_hal_alloc(size_t size_bytes)" in code
    assert "static void cpu_host_hal_free(void *ptr)" in code
    assert "static void cpu_host_hal_memset(void *dst, int value, size_t size_bytes)" in code
    assert "if (cpu_host_hal_stub_inited == 0u) return NULL;" in code
    assert "if ((flags & ~CPU_HOST_WINDOW_RESIZABLE) != 0u) return NULL;" in code
    assert "if (w <= 0) w = 640;" in code
    assert "if (h <= 0) h = 480;" in code
    assert "window = (CPUHostStubWindow *)calloc(1u, sizeof(*window));" in code
    assert "if (cpu_host_hal_stub_primary_window == NULL) {" in code
    assert "cpu_host_hal_stub_primary_window = window;" in code
    assert "renderer = (CPUHostStubRenderer *)calloc(1u, sizeof(*renderer));" in code
    assert "if (window == NULL) window = (void *)cpu_host_hal_stub_primary_window;" in code
    assert "texture = (CPUHostStubTexture *)calloc(1u, sizeof(*texture));" in code
    assert "if (format != CPU_HOST_PIXELFORMAT_ARGB8888) return NULL;" in code
    assert "if (access != CPU_HOST_TEXTUREACCESS_STREAMING) return NULL;" in code
    assert "return malloc(size_bytes);" in code
    assert "free(ptr);" in code
    assert "if (!dst || size_bytes == 0u) return;" in code
    assert "memset(dst, value, size_bytes);" in code
    assert "SDL_Init(" not in code
    assert "SDL_CreateWindow(" not in code
    assert "SDL_CreateRenderer(" not in code
    assert "SDL_CreateTexture(" not in code
    assert "SDL_OpenAudioDevice(" not in code
    assert "SDL_PauseAudioDevice(" not in code
    assert "SDL_malloc(" not in code
    assert "SDL_free(" not in code
    assert "SDL_memset(" not in code


def test_runtime_hal_render_helpers_emit_sdl2_impl():
    data = _base_isa("HostHalRenderSdl2")
    data["hosts"] = [
        {
            "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static int cpu_host_hal_renderer_output_size(void *renderer, int *out_w, int *out_h)" in code
    assert "if (out_w) *out_w = 0;" in code
    assert "if (out_h) *out_h = 0;" in code
    assert "if (SDL_GetRendererOutputSize((SDL_Renderer *)renderer, out_w, out_h) != 0) return -1;" in code
    assert "if (*out_w <= 0 || *out_h <= 0) return -1;" in code
    assert "static int cpu_host_hal_update_texture(void *texture, const CPUHostRect *rect, const void *pixels, int pitch)" in code
    assert "SDL_UpdateTexture((SDL_Texture *)texture, (const SDL_Rect *)rect, pixels, pitch);" in code
    assert "static void cpu_host_hal_render_set_draw_color(void *renderer, uint8_t r, uint8_t g, uint8_t b, uint8_t a)" in code
    assert "SDL_SetRenderDrawColor((SDL_Renderer *)renderer, r, g, b, a);" in code
    assert "static int cpu_host_hal_render_clear(void *renderer)" in code
    assert "SDL_RenderClear((SDL_Renderer *)renderer);" in code
    assert "static int cpu_host_hal_render_copy(void *renderer, void *texture, const CPUHostRect *src_rect, const CPUHostRect *dst_rect)" in code
    assert "SDL_RenderCopy(" in code
    assert "static int cpu_host_hal_renderer_supports_shaders(void *renderer)" in code
    assert "static void *cpu_host_hal_shader_create(void *renderer, const char *vertex_source, const char *fragment_source)" in code
    assert "static void cpu_host_hal_shader_destroy(void *shader)" in code
    assert "static int cpu_host_hal_render_copy_shader(void *renderer, void *texture, const CPUHostRect *src_rect, const CPUHostRect *dst_rect, void *shader, int texture_w, int texture_h, int output_w, int output_h)" in code


def test_runtime_hal_render_helpers_emit_noop_impl_for_stub():
    data = _base_isa("HostHalRenderStub")
    data["hosts"] = [
        {
            "metadata": {"id": "host_stub", "type": "host_adapter", "model": "test"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static int cpu_host_hal_renderer_output_size(void *renderer, int *out_w, int *out_h)" in code
    assert "if (out_w) *out_w = 0;" in code
    assert "if (out_h) *out_h = 0;" in code
    assert "if (cpu_host_hal_stub_inited == 0u || rr == NULL || rr->window == NULL || !out_w || !out_h) return -1;" in code
    assert "static int cpu_host_hal_update_texture(void *texture, const CPUHostRect *rect, const void *pixels, int pitch)" in code
    assert "if (cpu_host_hal_stub_inited == 0u) return -1;" in code
    assert "if (tt == NULL || pixels == NULL || pitch <= 0) return -1;" in code
    assert "static void cpu_host_hal_render_set_draw_color(void *renderer, uint8_t r, uint8_t g, uint8_t b, uint8_t a)" in code
    assert "rr->clear_color = ((uint32_t)a << 24) | ((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)b;" in code
    assert "static int cpu_host_hal_render_clear(void *renderer)" in code
    assert "if (cpu_host_hal_stub_inited == 0u || rr == NULL) return -1;" in code
    assert "static int cpu_host_hal_render_copy(void *renderer, void *texture, const CPUHostRect *src_rect, const CPUHostRect *dst_rect)" in code
    assert "if (cpu_host_hal_stub_inited == 0u || rr == NULL || tt == NULL) return -1;" in code
    assert "static int cpu_host_hal_renderer_supports_shaders(void *renderer)" in code
    assert "static void *cpu_host_hal_shader_create(void *renderer, const char *vertex_source, const char *fragment_source)" in code
    assert "static void cpu_host_hal_shader_destroy(void *shader)" in code
    assert "static int cpu_host_hal_render_copy_shader(void *renderer, void *texture, const CPUHostRect *src_rect, const CPUHostRect *dst_rect, void *shader, int texture_w, int texture_h, int output_w, int output_h)" in code
    assert "SDL_GetRendererOutputSize(" not in code
    assert "SDL_UpdateTexture(" not in code
    assert "SDL_SetRenderDrawColor(" not in code
    assert "SDL_RenderClear(" not in code
    assert "SDL_RenderCopy(" not in code


def test_runtime_hal_render_helpers_emit_glfw_buffer_impl():
    data = _base_isa("HostHalRenderGlfw")
    data["hosts"] = [
        {
            "metadata": {"id": "host_glfw", "type": "host_adapter", "model": "test"},
            "backend": {"target": "glfw"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static int cpu_host_hal_glfw_renderer_sync_size(CPUHostGlfwRenderer *renderer)" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return -1;" in code
    assert "uint64_t need64;" in code
    assert "w64 = (uint64_t)(uint32_t)w;" in code
    assert "h64 = (uint64_t)(uint32_t)h;" in code
    assert "if (w64 != 0u && h64 > (0xFFFFFFFFFFFFFFFFu / w64)) return -1;" in code
    assert "if (need64 > (0xFFFFFFFFFFFFFFFFu / 4u)) return -1;" in code
    assert "need64 *= 4u;" in code
    assert "if (need64 == 0u || need64 > (uint64_t)SIZE_MAX) return -1;" in code
    assert "uint64_t expect64;" in code
    assert "uint64_t tex_bytes64;" in code
    assert "uint64_t row_bytes64;" in code
    assert "uint64_t src_start64;" in code
    assert "uint64_t dst_start64;" in code
    assert "expect64 = (uint64_t)(uint32_t)rr->w * (uint64_t)(uint32_t)rr->h * 4u;" in code
    assert "if (expect64 == 0u || expect64 > (uint64_t)SIZE_MAX) return -1;" in code
    assert "if (rr->frame_len < (size_t)expect64) return -1;" in code
    assert "size_t pixels_len;" in code
    assert "count = (size_t)expect64 / 4u;" in code
    assert "memset(renderer->frame_rgba, 0, renderer->frame_len);" in code
    assert "CPUHostGlfwRenderer *rr = (CPUHostGlfwRenderer *)renderer;" in code
    assert "CPUHostGlfwTexture *tex = (CPUHostGlfwTexture *)texture;" in code
    assert "if (cpu_host_hal_glfw_inited == 0u) return;" in code
    assert "rr->clear_color = ((uint32_t)a << 24) | ((uint32_t)r << 16) | ((uint32_t)g << 8) | (uint32_t)b;" in code
    assert "pix = (uint32_t *)rr->frame_rgba;" in code
    assert "for (size_t i = 0u; i < count; ++i) pix[i] = rr->clear_color;" in code
    assert "uint64_t row_bytes64;" in code
    assert "uint64_t tex_bytes64;" in code
    assert "uint64_t dst_start64;" in code
    assert "uint64_t dst_stride64;" in code
    assert "uint64_t dst_span64;" in code
    assert "uint64_t src_span64;" in code
    assert "int64_t sum64;" in code
    assert "row_bytes64 = (uint64_t)(uint32_t)w * 4u;" in code
    assert "if (row_bytes64 > (uint64_t)INT_MAX) return -1;" in code
    assert "if ((uint64_t)(uint32_t)pitch < row_bytes64) return -1;" in code
    assert "tex_bytes64 = (uint64_t)(uint32_t)tex->w * (uint64_t)(uint32_t)tex->h * 4u;" in code
    assert "if ((uint64_t)tex->pixels_len < tex_bytes64) return -1;" in code
    assert "if (dst_span64 > (tex_bytes64 - dst_start64)) return -1;" in code
    assert "src_span64 = ((uint64_t)(uint32_t)(h - 1) * (uint64_t)(uint32_t)pitch) + row_bytes64;" in code
    assert "if (src_span64 == 0u || src_span64 > (uint64_t)SIZE_MAX) return -1;" in code
    assert "if (tex->w <= 0 || tex->h <= 0) return -1;" in code
    assert "sum64 = (int64_t)x + (int64_t)w;" in code
    assert "if (sum64 > (int64_t)tex->w) w = tex->w - x;" in code
    assert "if (!rr->frame_rgba) return -1;" in code
    assert "if (rr->w <= 0 || rr->h <= 0) return -1;" in code
    assert "if (sx >= tex->w || sy >= tex->h) return 0;" in code
    assert "sum64 = (int64_t)sx + (int64_t)sw;" in code
    assert "if (sum64 > (int64_t)tex->w) sw = tex->w - sx;" in code
    assert "if (dw <= 0 || dh <= 0) return -1;" in code
    assert "sum64 = (int64_t)dy + (int64_t)ch;" in code
    assert "if (sum64 > (int64_t)rr->h) ch = rr->h - dy;" in code
    assert "cpu_glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, rr->w, rr->h, 0, GL_BGRA, GL_UNSIGNED_BYTE, rr->frame_rgba);" in code
    assert "rr->present_texture_w != rr->w || rr->present_texture_h != rr->h" in code
    assert "dst_span64 = ((uint64_t)(uint32_t)(ch - 1) * ((uint64_t)(uint32_t)rr->w * 4u)) + ((uint64_t)(uint32_t)cw * 4u);" in code
    assert "if (dst_span64 > (expect64 - dst_start64)) return -1;" in code
    assert "if (sw <= 0 || sh <= 0) return 0;" in code
    assert "int src_y = sy + (int)((((int64_t)(row + copy_y0)) * (int64_t)sh) / (int64_t)dh);" in code
    assert "int src_x = sx + (int)((((int64_t)(col + copy_x0)) * (int64_t)sw) / (int64_t)dw);" in code
    assert "dst_px[col] = src_row[src_x];" in code
    assert "static int cpu_host_hal_renderer_supports_shaders(void *renderer)" in code
    assert "static void *cpu_host_hal_shader_create(void *renderer, const char *vertex_source, const char *fragment_source)" in code
    assert "static void cpu_host_hal_shader_destroy(void *shader)" in code
    assert "static int cpu_host_hal_render_copy_shader(void *renderer, void *texture, const CPUHostRect *src_rect, const CPUHostRect *dst_rect, void *shader, int texture_w, int texture_h, int output_w, int output_h)" in code
    assert "glfwGetProcAddress" in code
    assert "shader->vertex_shader = cpu_host_hal_glfw_compile_shader(GL_VERTEX_SHADER, vertex_source);" in code
    assert "shader->fragment_shader = cpu_host_hal_glfw_compile_shader(GL_FRAGMENT_SHADER, fragment_source);" in code
    assert "cpu_glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, texture_w, texture_h, 0, GL_BGRA, GL_UNSIGNED_BYTE, tex->pixels);" in code
    assert "cpu_glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, texture_w, texture_h, GL_BGRA, GL_UNSIGNED_BYTE, tex->pixels);" in code
    assert "ss->texture_w != texture_w || ss->texture_h != texture_h" in code
    assert "cpu_glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);" in code
    assert "free(tex->pixels);" in code
    assert "tex->pixels_len = 0u;" in code
    assert "free(rr->frame_rgba);" in code


def test_runtime_hal_input_misc_helpers_emit_sdl2_impl():
    data = _base_isa("HostHalInputMiscSdl2")
    data["hosts"] = [
        {
            "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test"},
            "backend": {"target": "sdl2"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static const char *cpu_host_hal_getenv(const char *name)" in code
    assert "return SDL_getenv(name);" in code
    assert "static const uint8_t *cpu_host_hal_keyboard_state(int *key_count)" in code
    assert "static const uint8_t empty_state[1] = {0u};" in code
    assert "if (cpu_host_hal_sdl_inited == 0u) {" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) {" in code
    assert "if (key_count) *key_count = 0;" in code
    assert "return empty_state;" in code
    assert "const uint8_t *state;" in code
    assert "state = SDL_GetKeyboardState(key_count);" in code
    assert "if (!state) {" in code
    assert "return state;" in code
    assert "static int32_t cpu_host_hal_key_from_scancode(int scancode)" in code
    assert "if (cpu_host_hal_sdl_inited == 0u) return 0;" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return 0;" in code
    assert "return (int32_t)SDL_GetKeyFromScancode((SDL_Scancode)scancode);" in code
    assert "static void cpu_host_hal_start_text_input(void)" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return;" in code
    assert "SDL_StartTextInput();" in code
    assert "static void cpu_host_hal_stop_text_input(void)" in code
    assert "SDL_StopTextInput();" in code
    assert "static void cpu_host_hal_raise_window(void *window)" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return;" in code
    assert "if (!window) window = (void *)cpu_host_hal_sdl_primary_window;" in code
    assert "SDL_RaiseWindow((SDL_Window *)window);" in code
    assert "static int cpu_host_hal_set_texture_blend_none(void *texture)" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_VIDEO) == 0u) return -1;" in code
    assert "return SDL_SetTextureBlendMode((SDL_Texture *)texture, SDL_BLENDMODE_NONE);" in code
    assert "static int cpu_host_hal_get_window_size(void *window, int *out_w, int *out_h)" in code
    assert "if (out_w) *out_w = 0;" in code
    assert "if (out_h) *out_h = 0;" in code
    assert "if (!window) window = (void *)cpu_host_hal_sdl_primary_window;" in code
    assert "if (*out_w <= 0 || *out_h <= 0) return -1;" in code
    assert "static const char *cpu_host_hal_scancode_name(int32_t scancode)" in code
    assert "if (cpu_host_hal_sdl_inited == 0u) return \"UNKNOWN\";" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return \"UNKNOWN\";" in code
    assert "const char *name = SDL_GetScancodeName((SDL_Scancode)scancode);" in code
    assert "if (!name || name[0] == '\\0') return \"UNKNOWN\";" in code
    assert "static const char *cpu_host_hal_key_name(int32_t keycode)" in code
    assert "if (cpu_host_hal_sdl_inited == 0u) return \"UNKNOWN\";" in code
    assert "if ((cpu_host_hal_sdl_subsystems & CPU_HOST_INIT_EVENTS) == 0u) return \"UNKNOWN\";" in code
    assert "const char *name = SDL_GetKeyName((SDL_Keycode)keycode);" in code
    assert "if (!name || name[0] == '\\0') return \"UNKNOWN\";" in code


def test_runtime_hal_input_misc_helpers_emit_noop_impl_for_stub():
    data = _base_isa("HostHalInputMiscStub")
    data["hosts"] = [
        {
            "metadata": {"id": "host_stub", "type": "host_adapter", "model": "test"},
            "backend": {"target": "stub"},
            "state": [],
            "interfaces": {"callbacks": [], "handlers": [], "signals": []},
            "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
            "coding": {"headers": [], "include_paths": [], "linked_libraries": [], "library_paths": []},
        }
    ]
    code = generate_cpu_impl(data, "Z80")
    assert "static const char *cpu_host_hal_getenv(const char *name)" in code
    assert "static const uint8_t *cpu_host_hal_keyboard_state(int *key_count)" in code
    assert "static int32_t cpu_host_hal_key_from_scancode(int scancode)" in code
    assert "static void cpu_host_hal_start_text_input(void)" in code
    assert "static void cpu_host_hal_stop_text_input(void)" in code
    assert "static void cpu_host_hal_raise_window(void *window)" in code
    assert "static int cpu_host_hal_set_texture_blend_none(void *texture)" in code
    assert "static const uint8_t empty_state[1] = {0u};" in code
    assert "return empty_state;" in code
    assert "return \"UNKNOWN\";" in code
    assert "SDL_getenv(" not in code
    assert "SDL_GetKeyboardState(" not in code
    assert "SDL_StartTextInput(" not in code
    assert "SDL_StopTextInput(" not in code
    assert "SDL_RaiseWindow(" not in code


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
    assert "set(CPU_CORE_SOURCES" in cmake_text
    assert "src/HookEnabled8_hooks.c" in cmake_text
    host_glue_text = next((outdir / "src").glob("*_host_glue.c")).read_text(encoding="utf-8")
    assert '#include "HookEnabled8_hooks.c"' not in host_glue_text

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
