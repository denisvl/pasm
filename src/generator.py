"""Main code generator orchestrator."""

import os
import json
from pathlib import Path
from typing import Dict, Any, List
import sys

# Ensure parent directory is in path
pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from src.parser.yaml_loader import ProcessorSystemLoader
from src.codegen.cpu_header import generate_cpu_header
from src.codegen.cpu_impl import generate_cpu_impl
from src.codegen.cpu_decoder import generate_decoder
from src.codegen.cpu_debug_abi import generate_debug_abi
from src.codegen.cpu_hooks import HOOK_NAMES, generate_hooks
from src.codegen.build_system import generate_cmake, generate_makefile
from src.codegen.test_harness import generate_test_c
from src.logging_utils import logger


class EmulatorGenerator:
    """Main generator class for creating CPU emulators."""

    def __init__(
        self,
        processor_path: str,
        system_path: str,
        ic_paths: List[str] | None = None,
        device_paths: List[str] | None = None,
        host_paths: List[str] | None = None,
        cartridge_map_path: str | None = None,
        cartridge_rom_path: str | None = None,
        host_backend_target: str | None = None,
    ):
        """Initialize generator with processor/system YAML paths."""
        if ic_paths is None:
            ic_paths = []
        if device_paths is None:
            device_paths = []
        if host_paths is None:
            host_paths = []
        self.loader = ProcessorSystemLoader()
        self.isa_data = self.loader.load(
            processor_path,
            system_path,
            ic_paths=ic_paths,
            device_paths=device_paths,
            host_paths=host_paths,
            cartridge_path=cartridge_map_path,
            cartridge_rom_path=cartridge_rom_path,
            host_backend_target=host_backend_target,
        )
        self.processor_path = Path(processor_path)
        self.system_path = Path(system_path)
        self.ic_paths = [Path(path) for path in ic_paths]
        self.device_paths = [Path(path) for path in device_paths]
        self.host_paths = [Path(path) for path in host_paths]
        self.cartridge_map_path = Path(cartridge_map_path) if cartridge_map_path else None
        self.cartridge_rom_path = cartridge_rom_path or ""

        # Get CPU name from metadata
        self.cpu_name = self.isa_data.get("metadata", {}).get("name", "CPU")
        self.cpu_prefix = self.cpu_name.lower()

    def generate(self, output_dir: str, dispatch_mode: str = "switch") -> None:
        """Generate the emulator to the output directory.

        :param output_dir: Target directory for generated C files and build scripts.
        :param dispatch_mode: Dispatch strategy
            (``switch``, ``threaded``, or ``both``).
        """

        if dispatch_mode not in {"switch", "threaded", "both"}:
            raise ValueError(f"Unsupported dispatch mode: {dispatch_mode}")

        output_path = Path(output_dir)

        # Create directory structure
        src_dir = output_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        include_dir = output_path / "include"
        include_dir.mkdir(parents=True, exist_ok=True)

        tests_dir = output_path / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        system_name = (
            self.isa_data.get("system", {}).get("metadata", {}).get("name", "system")
        )
        logger.info(
            f"Generating {self.cpu_name} emulator "
            f"({system_name}, {len(self.isa_data.get('ics', []))} IC(s), "
            f"{len(self.isa_data.get('devices', []))} device(s), "
            f"{len(self.isa_data.get('hosts', []))} host(s), "
            f"{1 if self.isa_data.get('cartridge') else 0} cartridge(s)) to {output_dir}"
        )

        # Generate main CPU header
        logger.info("  - Generating cpu.h...")
        header_code = generate_cpu_header(self.isa_data, self.cpu_name)
        (src_dir / f"{self.cpu_name}.h").write_text(header_code)

        # Generate CPU implementation
        logger.info("  - Generating cpu.c...")
        impl_code = generate_cpu_impl(
            self.isa_data, self.cpu_name, dispatch_mode=dispatch_mode
        )
        (src_dir / f"{self.cpu_name}.c").write_text(impl_code)

        # Generate decoder
        logger.info("  - Generating cpu_decoder.h/c...")
        decoder_header, decoder_impl = generate_decoder(self.isa_data, self.cpu_name)
        (src_dir / f"{self.cpu_name}_decoder.h").write_text(decoder_header)
        (src_dir / f"{self.cpu_name}_decoder.c").write_text(decoder_impl)

        # Generate debug ABI bridge
        logger.info("  - Generating cpu_debug_abi.h/c...")
        debug_header, debug_impl = generate_debug_abi(self.isa_data, self.cpu_name)
        (src_dir / f"{self.cpu_name}_debug_abi.h").write_text(debug_header)
        (src_dir / f"{self.cpu_name}_debug_abi.c").write_text(debug_impl)

        # Generate hooks if enabled in ISA
        hooks_header, hooks_impl = None, None
        hooks_config = self.isa_data.get("hooks", {})
        hooks_enabled_in_isa = any(
            hooks_config.get(name, {}).get("enabled", False) for name in HOOK_NAMES
        )
        if hooks_enabled_in_isa:
            hooks_header, hooks_impl = generate_hooks(self.isa_data, self.cpu_name)

        if hooks_header:
            logger.info("  - Generating cpu_hooks.h/c...")
            (src_dir / f"{self.cpu_name}_hooks.h").write_text(hooks_header)
            (src_dir / f"{self.cpu_name}_hooks.c").write_text(hooks_impl)
        hooks_generated = hooks_header is not None

        # Generate main.c
        logger.info("  - Generating main.c...")
        main_code = self._generate_main()
        (src_dir / "main.c").write_text(main_code)

        # Generate minimal C test harness scaffold
        logger.info("  - Generating tests/test_cpu.c...")
        test_c_code = generate_test_c(self.isa_data, self.cpu_name)
        (tests_dir / "test_cpu.c").write_text(test_c_code)

        # Generate build system (always generated; may be extended to depend on
        # features/dispatch_mode in the future)
        logger.info("  - Generating CMakeLists.txt...")
        cmake_code = generate_cmake(
            self.isa_data,
            self.cpu_name,
            include_hooks=hooks_generated,
            dispatch_mode=dispatch_mode,
        )
        (output_path / "CMakeLists.txt").write_text(cmake_code)

        logger.info("  - Generating Makefile...")
        makefile_code = generate_makefile(
            self.isa_data,
            self.cpu_name,
            include_hooks=hooks_generated,
            dispatch_mode=dispatch_mode,
        )
        (output_path / "Makefile").write_text(makefile_code)

        # Generate include/cpu_defs.h
        defs_code = self._generate_defs_header()
        (include_dir / "cpu_defs.h").write_text(defs_code)

        # Generate debugger linkage manifest used by external debugger frontends.
        logger.info("  - Generating debugger_link.json...")
        debugger_manifest = self._generate_debugger_link_manifest()
        (output_path / "debugger_link.json").write_text(
            json.dumps(debugger_manifest, indent=2) + "\n"
        )

        logger.info("\nEmulator generated successfully!")
        logger.info(f"  CPU: {self.cpu_name}")
        logger.info(f"  Registers: {len(self.isa_data.get('registers', []))}")
        logger.info(f"  Instructions: {len(self.isa_data.get('instructions', []))}")

        hooks = self.isa_data.get("hooks", {})
        if any(h.get("enabled") for h in hooks.values()):
            logger.info("  Hooks: enabled")

    def _generate_main(self) -> str:
        """Generate main.c template."""

        memory_default_size = int(self.isa_data.get("memory", {}).get("default_size", 65536))
        host_backend_target = str(self.isa_data.get("host_backend_target", "")).strip().lower()
        interactive_host_backend = host_backend_target in {"sdl2", "glfw"}
        has_keyboard_callbacks = any(
            any(
                str(cb.get("name", "")).strip() in {"keyboard_matrix", "keyboard_ascii"}
                for cb in list((host.get("interfaces") or {}).get("callbacks", []))
            )
            for host in list(self.isa_data.get("hosts", []))
            if isinstance(host, dict)
        )
        keyboard_map_required = interactive_host_backend and has_keyboard_callbacks
        default_cart_rom = (
            str(self.isa_data.get("cartridge_rom", {}).get("path", ""))
            .replace("\\", "\\\\")
            .replace('"', '\\"')
        )
        has_cartridge = bool(self.isa_data.get("cartridge"))
        cart_usage_line = (
            '    printf("  --cart-rom <file>  Load cartridge ROM file (overrides generated default)\\n");'
            if has_cartridge
            else ""
        )
        cart_cli_parse = (
            '        } else if (strcmp(argv[i], "--cart-rom") == 0 && i + 1 < argc) {\n'
            "            cart_rom_file = argv[++i];\n"
            if has_cartridge
            else ""
        )
        cart_default_decl = (
            f'    const char *cart_rom_file = "{default_cart_rom}";' if has_cartridge else ""
        )
        cart_load_block = (
            "    if (cart_rom_file && cart_rom_file[0]) {\n"
            f"        if ({self.cpu_prefix}_load_cartridge_rom(cpu, cart_rom_file) != 0) {{\n"
            '            fprintf(stderr, "Failed to load cartridge ROM: %s\\n", cart_rom_file);\n'
            "            return 1;\n"
            "        }\n"
            f"        {self.cpu_prefix}_reset(cpu);\n"
            '        printf("Loaded cartridge ROM: %s\\n", cart_rom_file);\n'
            "    }\n"
            if has_cartridge
            else ""
        )
        keyboard_usage_line = (
            '    printf("  --keyboard-map <file>  Load runtime keyboard map YAML\\n");'
            if keyboard_map_required
            else ""
        )
        keyboard_cli_parse = (
            '        } else if (strcmp(argv[i], "--keyboard-map") == 0 && i + 1 < argc) {\n'
            "            keyboard_map_file = argv[++i];\n"
            if keyboard_map_required
            else ""
        )
        keyboard_required_check = (
            "    if (keyboard_map_file == NULL || keyboard_map_file[0] == '\\0') {\n"
            '        fprintf(stderr, "Missing required --keyboard-map <file>\\n");\n'
            "        return 1;\n"
            "    }\n"
            if keyboard_map_required
            else ""
        )
        keyboard_load_block = (
            "    if (keyboard_map_file && keyboard_map_file[0]) {\n"
            f"        if ({self.cpu_prefix}_load_keyboard_map(cpu, keyboard_map_file) != 0) {{\n"
            '            fprintf(stderr, "Failed to load keyboard map: %s\\n", keyboard_map_file);\n'
            "            return 1;\n"
            "        }\n"
            '        printf("Loaded keyboard map: %s\\n", keyboard_map_file);\n'
            "    }\n"
            if keyboard_map_required
            else ""
        )

        template = """/*
 * Auto-generated main.c
 * Generated by PASM
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "{cpu_name}.h"

void print_usage(const char *prog) {{
    printf("Usage: %s [options]\\n", prog);
    printf("Options:\\n");
    printf("  --system-dir <dir>  Load system ROM manifests relative to this directory\\n");
{keyboard_usage_line}
    printf("  --rom <file>    Load ROM file\\n");
{cart_usage_line}
    printf("  --addr <addr>   Load address (default: 0x0000)\\n");
    printf("  --run           Run emulator\\n");
    printf("  --cycles <n>    Run for n cycles\\n");
    printf("  --test <name>   Run test\\n");
    printf("  --help          Show this help\\n");
}}

int main(int argc, char *argv[]) {{
    CPUState *cpu = {cpu_prefix}_create({memory_default_size});
    if (!cpu) {{
        fprintf(stderr, "Failed to create CPU\\n");
        return 1;
    }}
    
    bool run_emulator = false;
    uint64_t max_cycles = 0;
    const char *system_dir = NULL;
    const char *keyboard_map_file = NULL;
    const char *rom_file = NULL;
{cart_default_decl}
    uint16_t load_addr = 0;
    const char *test_name = NULL;
    
    for (int i = 1; i < argc; i++) {{
        if (strcmp(argv[i], "--system-dir") == 0 && i + 1 < argc) {{
            system_dir = argv[++i];
{keyboard_cli_parse}        }} else if (strcmp(argv[i], "--rom") == 0 && i + 1 < argc) {{
            rom_file = argv[++i];
{cart_cli_parse}        }} else if (strcmp(argv[i], "--addr") == 0 && i + 1 < argc) {{
            load_addr = (uint16_t)strtol(argv[++i], NULL, 0);
        }} else if (strcmp(argv[i], "--run") == 0) {{
            run_emulator = true;
        }} else if (strcmp(argv[i], "--cycles") == 0 && i + 1 < argc) {{
            max_cycles = strtoull(argv[++i], NULL, 0);
        }} else if (strcmp(argv[i], "--test") == 0 && i + 1 < argc) {{
            test_name = argv[++i];
        }} else if (strcmp(argv[i], "--help") == 0) {{
            print_usage(argv[0]);
            return 0;
        }}
    }}
{keyboard_required_check}
    
    if (system_dir) {{
        if ({cpu_prefix}_load_system_roms(cpu, system_dir) != 0) {{
            fprintf(stderr, "Failed to load system ROMs from: %s\\n", system_dir);
            return 1;
        }}
        {cpu_prefix}_reset(cpu);
        printf("Loaded system ROMs from: %s\\n", system_dir);
    }}
    
{keyboard_load_block}{cart_load_block}    if (rom_file) {{
        if ({cpu_prefix}_load_rom(cpu, rom_file, load_addr) != 0) {{
            fprintf(stderr, "Failed to load ROM: %s\\n", rom_file);
            return 1;
        }}
        cpu->pc = load_addr;
        printf("Loaded ROM: %s at 0x%04X\\n", rom_file, load_addr);
    }}
    
    if (test_name) {{
        printf("Running test: %s\\n", test_name);
        if (strcmp(test_name, "basic") == 0) {{
            {cpu_prefix}_run_until(cpu, 100);
            printf("Executed %llu cycles\\n", cpu->total_cycles);
            {cpu_prefix}_dump_registers(cpu);
        }}
    }} else if (run_emulator || max_cycles > 0) {{
        if (max_cycles > 0) {{
            {cpu_prefix}_run_until(cpu, max_cycles);
            printf("Executed %llu cycles\\n", cpu->total_cycles);
        }} else {{
            {cpu_prefix}_run(cpu);
        }}
    }} else {{
        print_usage(argv[0]);
    }}
    
    {cpu_prefix}_dump_registers(cpu);
    {cpu_prefix}_destroy(cpu);
    return 0;
}}
"""

        return template.format(
            cpu_name=self.cpu_name,
            cpu_prefix=self.cpu_prefix,
            memory_default_size=memory_default_size,
            keyboard_usage_line=keyboard_usage_line,
            cart_usage_line=cart_usage_line,
            cart_default_decl=cart_default_decl,
            keyboard_cli_parse=keyboard_cli_parse,
            cart_cli_parse=cart_cli_parse,
            keyboard_required_check=keyboard_required_check,
            keyboard_load_block=keyboard_load_block,
            cart_load_block=cart_load_block,
        )

    def _generate_defs_header(self) -> str:
        """Generate cpu_defs.h include file."""

        return f"""/*
 * Auto-generated CPU definitions
 * Generated by PASM
 */

#ifndef CPU_DEFS_H
#define CPU_DEFS_H

#include "{self.cpu_name}.h"

#endif /* CPU_DEFS_H */
"""

    def _generate_debugger_link_manifest(self) -> Dict[str, Any]:
        """Generate debugger linkage metadata for Rust/C host frontends."""

        metadata = self.isa_data.get("metadata", {})
        system_meta = self.isa_data.get("system", {}).get("metadata", {})
        memory = self.isa_data.get("memory", {})
        coding = self.isa_data.get("coding", {})
        linked_libraries = coding.get("linked_libraries", [])
        link_library_names: List[str] = []
        link_library_files: List[str] = []
        for lib in linked_libraries:
            if isinstance(lib, dict):
                if "name" in lib:
                    link_library_names.append(str(lib["name"]))
                elif "path" in lib:
                    link_library_files.append(str(lib["path"]))
            elif isinstance(lib, str):
                link_library_names.append(lib)

        host_backend_target = str(self.isa_data.get("host_backend_target", "")).strip().lower()
        # Keep debugger-link behavior aligned with codegen/build backends.
        if host_backend_target == "sdl2" and "SDL2" not in link_library_names:
            link_library_names.append("SDL2")
        if host_backend_target == "glfw" and "glfw" not in link_library_names:
            link_library_names.append("glfw")

        return {
            "schema_version": 1,
            "processor_name": metadata.get("name", self.cpu_name),
            "processor_version": metadata.get("version", ""),
            "system_name": system_meta.get("name", "system"),
            "cpu_name": self.cpu_name,
            "cpu_prefix": self.cpu_prefix,
            "cmake_library_target": f"{self.cpu_prefix}_emu",
            "library_basename": f"{self.cpu_prefix}_emu",
            "artifacts": {
                "static": f"lib{self.cpu_prefix}_emu.a",
                "shared_linux": f"lib{self.cpu_prefix}_emu.so",
                "shared_macos": f"lib{self.cpu_prefix}_emu.dylib",
                "shared_windows": f"{self.cpu_prefix}_emu.dll",
                "import_windows": f"{self.cpu_prefix}_emu.lib",
            },
            "headers": {
                "cpu": f"src/{self.cpu_name}.h",
                "debug_abi": f"src/{self.cpu_name}_debug_abi.h",
            },
            "link": {
                "library_paths": list(coding.get("library_paths", [])),
                "library_names": link_library_names,
                "library_files": link_library_files,
            },
            "memory_default_size": int(memory.get("default_size", 65536)),
            "cartridge": {
                "enabled": bool(self.isa_data.get("cartridge")),
                "id": self.isa_data.get("cartridge", {}).get("metadata", {}).get("id", ""),
                "default_rom_path": self.isa_data.get("cartridge_rom", {}).get("path", ""),
            },
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the ISA."""
        return self.loader.get_summary(self.isa_data)


def generate(
    processor_path: str,
    system_path: str,
    output_dir: str,
    ic_paths: List[str] | None = None,
    device_paths: List[str] | None = None,
    host_paths: List[str] | None = None,
    cartridge_map_path: str | None = None,
    cartridge_rom_path: str | None = None,
    host_backend_target: str | None = None,
    dispatch_mode: str = "switch",
) -> None:
    """Convenience function to generate an emulator from processor+system YAML files."""
    generator = EmulatorGenerator(
        processor_path,
        system_path,
        ic_paths=ic_paths,
        device_paths=device_paths,
        host_paths=host_paths,
        cartridge_map_path=cartridge_map_path,
        cartridge_rom_path=cartridge_rom_path,
        host_backend_target=host_backend_target,
    )
    generator.generate(output_dir, dispatch_mode=dispatch_mode)
