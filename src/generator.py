"""Main code generator orchestrator."""

import os
from pathlib import Path
from typing import Dict, Any
import sys

# Ensure parent directory is in path
pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from src.parser.yaml_loader import ProcessorSystemLoader
from src.codegen.cpu_header import generate_cpu_header
from src.codegen.cpu_impl import generate_cpu_impl
from src.codegen.cpu_decoder import generate_decoder
from src.codegen.cpu_hooks import HOOK_NAMES, generate_hooks
from src.codegen.build_system import generate_cmake, generate_makefile
from src.codegen.test_harness import generate_test_c


class EmulatorGenerator:
    """Main generator class for creating CPU emulators."""

    def __init__(self, processor_path: str, system_path: str):
        """Initialize generator with processor/system YAML paths."""
        self.loader = ProcessorSystemLoader()
        self.isa_data = self.loader.load(processor_path, system_path)
        self.processor_path = Path(processor_path)
        self.system_path = Path(system_path)

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
        print(f"Generating {self.cpu_name} emulator ({system_name}) to {output_dir}")

        # Generate main CPU header
        print("  - Generating cpu.h...")
        header_code = generate_cpu_header(self.isa_data, self.cpu_name)
        (src_dir / f"{self.cpu_name}.h").write_text(header_code)

        # Generate CPU implementation
        print("  - Generating cpu.c...")
        impl_code = generate_cpu_impl(
            self.isa_data, self.cpu_name, dispatch_mode=dispatch_mode
        )
        (src_dir / f"{self.cpu_name}.c").write_text(impl_code)

        # Generate decoder
        print("  - Generating cpu_decoder.h/c...")
        decoder_header, decoder_impl = generate_decoder(self.isa_data, self.cpu_name)
        (src_dir / f"{self.cpu_name}_decoder.h").write_text(decoder_header)
        (src_dir / f"{self.cpu_name}_decoder.c").write_text(decoder_impl)

        # Generate hooks if enabled in ISA
        hooks_header, hooks_impl = None, None
        hooks_config = self.isa_data.get("hooks", {})
        hooks_enabled_in_isa = any(
            hooks_config.get(name, {}).get("enabled", False) for name in HOOK_NAMES
        )
        if hooks_enabled_in_isa:
            hooks_header, hooks_impl = generate_hooks(self.isa_data, self.cpu_name)

        if hooks_header:
            print("  - Generating cpu_hooks.h/c...")
            (src_dir / f"{self.cpu_name}_hooks.h").write_text(hooks_header)
            (src_dir / f"{self.cpu_name}_hooks.c").write_text(hooks_impl)
        hooks_generated = hooks_header is not None

        # Generate main.c
        print("  - Generating main.c...")
        main_code = self._generate_main()
        (src_dir / "main.c").write_text(main_code)

        # Generate minimal C test harness scaffold
        print("  - Generating tests/test_cpu.c...")
        test_c_code = generate_test_c(self.isa_data, self.cpu_name)
        (tests_dir / "test_cpu.c").write_text(test_c_code)

        # Generate build system (always generated; may be extended to depend on
        # features/dispatch_mode in the future)
        print("  - Generating CMakeLists.txt...")
        cmake_code = generate_cmake(
            self.isa_data,
            self.cpu_name,
            include_hooks=hooks_generated,
            dispatch_mode=dispatch_mode,
        )
        (output_path / "CMakeLists.txt").write_text(cmake_code)

        print("  - Generating Makefile...")
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

        print(f"\nEmulator generated successfully!")
        print(f"  CPU: {self.cpu_name}")
        print(f"  Registers: {len(self.isa_data.get('registers', []))}")
        print(f"  Instructions: {len(self.isa_data.get('instructions', []))}")

        hooks = self.isa_data.get("hooks", {})
        if any(h.get("enabled") for h in hooks.values()):
            print(f"  Hooks: enabled")

    def _generate_main(self) -> str:
        """Generate main.c template."""

        memory_default_size = int(self.isa_data.get("memory", {}).get("default_size", 65536))

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
    printf("  --rom <file>    Load ROM file\\n");
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
    const char *rom_file = NULL;
    uint16_t load_addr = 0;
    const char *test_name = NULL;
    
    for (int i = 1; i < argc; i++) {{
        if (strcmp(argv[i], "--rom") == 0 && i + 1 < argc) {{
            rom_file = argv[++i];
        }} else if (strcmp(argv[i], "--addr") == 0 && i + 1 < argc) {{
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
    
    if (rom_file) {{
        if ({cpu_prefix}_load_rom(cpu, rom_file, load_addr) != 0) {{
            fprintf(stderr, "Failed to load ROM: %s\\n", rom_file);
            return 1;
        }}
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

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the ISA."""
        return self.loader.get_summary(self.isa_data)


def generate(
    processor_path: str,
    system_path: str,
    output_dir: str,
    dispatch_mode: str = "switch",
) -> None:
    """Convenience function to generate an emulator from processor+system YAML files."""
    generator = EmulatorGenerator(processor_path, system_path)
    generator.generate(output_dir, dispatch_mode=dispatch_mode)
