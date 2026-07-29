"""Main code generator orchestrator."""

import os
import copy
import json
import re
from pathlib import Path
from typing import Dict, Any, List
import sys

# Ensure parent directory is in path
pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from src.parser.yaml_loader import ProcessorSystemLoader
from src.codegen.cpu_header import generate_cpu_header
from src.codegen.cpu_impl import (
    generate_cpu_impl,
)
from src.codegen.split_units import (
    emit_split_unit,
    emit_ic_unit,
)
from src.codegen.cpu_decoder import generate_decoder
from src.codegen.cpu_debug_abi import generate_debug_abi
from src.codegen.automation_adapter import generate_automation_adapter
from src.codegen.cpu_hooks import HOOK_NAMES, generate_hooks
from src.codegen.build_system import generate_cmake, generate_makefile
from src.codegen.test_harness import generate_test_c
from src.codegen.split_layout import (
    SYSTEM_UNIT_SUFFIXES,
    ic_unit_basenames,
    system_ident,
    system_unit_basenames,
)
from src.codegen.build_system import _flatten_platform_values_for_host
from src.logging_utils import logger


REPO_ROOT = Path(__file__).resolve().parents[1]


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
        self.system_prefix = system_ident(
            self.isa_data.get("system", {}).get("metadata", {}).get("name", "system"),
            self.cpu_prefix,
        )

    def _resolve_subsystem_entries(self) -> List[Dict[str, Any]]:
        """Resolve any attached subsystem descriptors declared by the system."""
        integrations = (
            (self.isa_data.get("system", {}) or {}).get("integrations", {}) or {}
        )
        raw_entries = integrations.get("subsystems", [])
        if not raw_entries:
            return []
        if not isinstance(raw_entries, list):
            raise ValueError("system.integrations.subsystems must be an array")

        loader = ProcessorSystemLoader()
        resolved: List[Dict[str, Any]] = []
        for idx, raw in enumerate(raw_entries):
            if isinstance(raw, str):
                rel_path = raw
            elif isinstance(raw, dict):
                rel_path = str(raw.get("path", "")).strip()
            else:
                raise ValueError(
                    f"system.integrations.subsystems[{idx}] must be a string path or object"
                )
            if not rel_path:
                raise ValueError(
                    f"system.integrations.subsystems[{idx}] is missing a subsystem path"
                )
            subsystem_path = str((self.system_path.parent / rel_path).resolve())
            subsystem_data = loader.load_subsystem(subsystem_path)
            subsystem_meta = subsystem_data.get("metadata", {})
            subsystem_id = str(subsystem_meta.get("id", "")).strip()
            if not subsystem_id:
                raise ValueError(
                    f"subsystem descriptor '{subsystem_path}' is missing metadata.id"
                )
            resolved.append(
                {
                    "path": subsystem_path,
                    "id": subsystem_id,
                    "data": subsystem_data,
                }
            )
        return resolved

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
        subsystem_entries = self._resolve_subsystem_entries()
        subsystem_builds: List[Dict[str, Any]] = []
        if subsystem_entries:
            subsystem_root = output_path / "subsystems"
            subsystem_root.mkdir(parents=True, exist_ok=True)
            for entry in subsystem_entries:
                subsystem_outdir = subsystem_root / entry["id"]
                logger.info(f"  - Generating attached subsystem {entry['id']}...")
                generate_from_subsystem(
                    entry["path"],
                    str(subsystem_outdir),
                    dispatch_mode=dispatch_mode,
                )
                manifest_path = subsystem_outdir / "debugger_link.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                subsystem_builds.append(
                    {
                        "id": entry["id"],
                        "output_dir": subsystem_outdir,
                        "cmake_subdir": _posix_relpath(subsystem_outdir, output_path),
                        "cpu_prefix": str(manifest.get("cpu_prefix", "")).strip(),
                        "system_target": str(manifest.get("cmake_library_target", "")).strip(),
                        "cpu_core_target": str(
                            (manifest.get("split_targets", {}) or {}).get("cpu_core", "")
                        ).strip(),
                        "system_static": str(
                            (manifest.get("split_artifacts", {}) or {}).get("system_static", "")
                        ).strip(),
                        "cpu_core_static": str(
                            (manifest.get("split_artifacts", {}) or {}).get("cpu_core_static", "")
                        ).strip(),
                    }
                )
        isa_data_for_codegen = copy.deepcopy(self.isa_data)
        isa_data_for_codegen["_attached_subsystem_builds"] = [
            {
                "id": build["id"],
                "cpu_prefix": build["cpu_prefix"],
                "system_target": build["system_target"],
                "cpu_core_target": build["cpu_core_target"],
                "system_static": build["system_static"],
                "cpu_core_static": build["cpu_core_static"],
                "cmake_subdir": build["cmake_subdir"],
            }
            for build in subsystem_builds
        ]

        # Generate main CPU header
        logger.info("  - Generating cpu.h...")
        header_code = generate_cpu_header(isa_data_for_codegen, self.cpu_name)
        (src_dir / f"{self.cpu_name}.h").write_text(header_code)

        # Generate CPU implementation content (owned by split core TU).
        logger.info("  - Generating cpu_core.c...")
        impl_code = generate_cpu_impl(
            isa_data_for_codegen,
            self.cpu_name,
            dispatch_mode=dispatch_mode,
            include_loader_impls=False,
            include_interrupt_impls=False,
            exclude_split_sections=[
                "HOST_HAL_IMPL",
                "INPUT_RUNTIME",
                "CARTRIDGE_PICKER_RUNTIME",
                "COMPONENT_RUNTIME",
                "COMPONENT_LIFECYCLE",
                "COMPONENT_DISPATCH",
                "COMPONENT_ROUTING",
                "COMPONENT_CONNECTIONS",
            ],
        )
        (src_dir / f"{self.cpu_name}_core.c").write_text(impl_code)

        # Ensure stale legacy monolithic CPU TU is removed when regenerating.
        (src_dir / f"{self.cpu_name}.c").unlink(missing_ok=True)

        # Generate decoder
        logger.info("  - Generating cpu_decoder.h/c...")
        decoder_header, decoder_impl = generate_decoder(isa_data_for_codegen, self.cpu_name)
        (src_dir / f"{self.cpu_name}_decoder.h").write_text(decoder_header)
        (src_dir / f"{self.cpu_name}_decoder.c").write_text(decoder_impl)

        # Generate debug ABI bridge
        logger.info("  - Generating cpu_debug_abi.h/c...")
        debug_header, debug_impl = generate_debug_abi(isa_data_for_codegen, self.cpu_name)
        (src_dir / f"{self.cpu_name}_debug_abi.h").write_text(debug_header)
        (src_dir / f"{self.cpu_name}_debug_abi.c").write_text(debug_impl)

        # Generate automation ABI bridge and copy the canonical automation core.
        logger.info("  - Generating automation adapter...")
        automation_header, automation_impl = generate_automation_adapter(
            isa_data_for_codegen, self.cpu_name
        )
        (src_dir / "emu_automation.h").write_text(
            (REPO_ROOT / "automation" / "include" / "emu_automation.h").read_text(
                encoding="utf-8"
            )
        )
        (src_dir / "emu_automation_adapter.h").write_text(
            (REPO_ROOT / "automation" / "include" / "emu_automation_adapter.h").read_text(
                encoding="utf-8"
            )
        )
        (src_dir / "emu_automation.c").write_text(
            (REPO_ROOT / "automation" / "core" / "emu_automation.c").read_text(
                encoding="utf-8"
            )
        )
        (src_dir / f"{self.cpu_name}_automation_adapter.h").write_text(automation_header)
        (src_dir / f"{self.cpu_name}_automation_adapter.c").write_text(automation_impl)

        # Generate hooks if enabled in ISA
        hooks_header, hooks_impl = None, None
        hooks_config = self.isa_data.get("hooks", {})
        hooks_enabled_in_isa = any(
            hooks_config.get(name, {}).get("enabled", False) for name in HOOK_NAMES
        )
        if hooks_enabled_in_isa:
            hooks_header, hooks_impl = generate_hooks(isa_data_for_codegen, self.cpu_name)

        if hooks_header:
            logger.info("  - Generating cpu_hooks.h/c...")
            (src_dir / f"{self.cpu_name}_hooks.h").write_text(hooks_header)
            (src_dir / f"{self.cpu_name}_hooks.c").write_text(hooks_impl)
        hooks_generated = hooks_header is not None

        # Prune stale split system-side units from prior naming prefixes.
        ic_basenames = ic_unit_basenames(self.isa_data, self.system_prefix)
        current_split_units = {
            f"{name}.c" for name in (system_unit_basenames(self.system_prefix) + ic_basenames)
        }
        current_split_headers = {f"{name}.h" for name in system_unit_basenames(self.system_prefix)}
        for suffix in SYSTEM_UNIT_SUFFIXES:
            for stale_path in src_dir.glob(f"*_{suffix}.c"):
                stem = stale_path.stem
                prefix = stem[: -(len(suffix) + 1)] if stem.endswith(f"_{suffix}") else ""
                # Never prune CPU-owned generated units (e.g. {CPU}_debug_abi.c).
                if prefix == self.cpu_name:
                    continue
                if stale_path.name not in current_split_units:
                    stale_path.unlink(missing_ok=True)
            for stale_path in src_dir.glob(f"*_{suffix}.h"):
                stem = stale_path.stem
                prefix = stem[: -(len(suffix) + 1)] if stem.endswith(f"_{suffix}") else ""
                # Never prune CPU-owned generated units.
                if prefix == self.cpu_name:
                    continue
                if stale_path.name not in current_split_headers:
                    stale_path.unlink(missing_ok=True)

        # Prune stale per-IC units from previous split layouts (e.g. merged legacy IC ids).
        for stale_path in src_dir.glob(f"{self.system_prefix}_ic_*.c"):
            if stale_path.name not in current_split_units:
                stale_path.unlink(missing_ok=True)

        # Prune obsolete system-scoped debug ABI artifacts from pre-split layouts.
        # Debug ABI is CPU-owned now ({CPU}_debug_abi.c/.h), so keep only CPU-prefixed files.
        for stale_path in src_dir.glob("*_debug_abi.c"):
            stem = stale_path.stem
            prefix = stem[: -len("_debug_abi")] if stem.endswith("_debug_abi") else ""
            if prefix != self.cpu_name:
                stale_path.unlink(missing_ok=True)
        for stale_path in src_dir.glob("*_debug_abi.h"):
            stem = stale_path.stem
            prefix = stem[: -len("_debug_abi")] if stem.endswith("_debug_abi") else ""
            if prefix != self.cpu_name:
                stale_path.unlink(missing_ok=True)

        # Transitional split system-side units (to be populated incrementally).
        logger.info("  - Generating split system units...")
        for basename in system_unit_basenames(self.system_prefix):
            suffix = basename[len(self.system_prefix) + 1 :]
            unit_body = emit_split_unit(isa_data_for_codegen, self.cpu_name, suffix)
            (src_dir / f"{basename}.c").write_text(unit_body)
        for component in list(self.isa_data.get("ics", []) or []):
            if not isinstance(component, dict):
                continue
            comp_id = str((component.get("metadata") or {}).get("id", "")).strip()
            if not comp_id:
                continue
            comp_ident = (
                "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in comp_id).lower().strip("_")
                or "ic"
            )
            basename = f"{self.system_prefix}_ic_{comp_ident}"
            (src_dir / f"{basename}.c").write_text(
                emit_ic_unit(isa_data_for_codegen, self.cpu_name, component)
            )

        if subsystem_builds:
            self._patch_host_attached_subsystem_bridge(src_dir, subsystem_builds)

        # Generate main.c
        logger.info("  - Generating main.c...")
        main_code = self._generate_main()
        (src_dir / "main.c").write_text(main_code)

        # Generate minimal C test harness scaffold
        logger.info("  - Generating tests/test_cpu.c...")
        test_c_code = generate_test_c(isa_data_for_codegen, self.cpu_name)
        (tests_dir / "test_cpu.c").write_text(test_c_code)

        # Generate build system (always generated; may be extended to depend on
        # features/dispatch_mode in the future)
        logger.info("  - Generating CMakeLists.txt...")
        cmake_code = generate_cmake(
            self.isa_data,
            self.cpu_name,
            include_hooks=hooks_generated,
            dispatch_mode=dispatch_mode,
            subsystem_builds=subsystem_builds,
        )
        (output_path / "CMakeLists.txt").write_text(cmake_code)

        logger.info("  - Generating Makefile...")
        makefile_code = generate_makefile(
            self.isa_data,
            self.cpu_name,
            include_hooks=hooks_generated,
            dispatch_mode=dispatch_mode,
            subsystem_builds=subsystem_builds,
        )
        (output_path / "Makefile").write_text(makefile_code)

        logger.info("  - Generating open_vs_debug.bat...")
        (output_path / "open_vs_debug.bat").write_text(self._generate_vs_debug_script())

        # Generate include/cpu_defs.h
        defs_code = self._generate_defs_header()
        (include_dir / "cpu_defs.h").write_text(defs_code)

        # Generate debugger linkage manifest used by external debugger frontends.
        logger.info("  - Generating debugger_link.json...")
        debugger_manifest = self._generate_debugger_link_manifest()
        if subsystem_builds:
            debugger_manifest["subsystems"] = [
                {
                    "id": build["id"],
                    "output_dir": _posix_relpath(Path(build["output_dir"]), output_path),
                    "cmake_subdir": build["cmake_subdir"],
                    "system_target": build["system_target"],
                    "cpu_core_target": build["cpu_core_target"],
                    "system_static": build["system_static"],
                    "cpu_core_static": build["cpu_core_static"],
                }
                for build in subsystem_builds
            ]
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

    def _patch_host_attached_subsystem_bridge(
        self,
        src_dir: Path,
        subsystem_builds: List[Dict[str, Any]],
    ) -> None:
        target = None
        for build in subsystem_builds:
            if str(build.get("id", "")).strip() == "c64_1541_subsystem":
                target = build
                break
        if target is None or self.system_prefix != "c64":
            return
        device_glue_path = src_dir / f"{self.system_prefix}_device_glue.c"
        if not device_glue_path.exists():
            return
        text = device_glue_path.read_text(encoding="utf-8")
        device_glue_path.write_text(text, encoding="utf-8")

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
        keyboard_map_supported = interactive_host_backend
        keyboard_map_required = keyboard_map_supported and has_keyboard_callbacks
        default_cart_rom = (
            str(self.isa_data.get("cartridge_rom", {}).get("path", ""))
            .replace("\\", "\\\\")
            .replace('"', '\\"')
        )
        has_cartridge = bool(self.isa_data.get("cartridge"))
        has_floppy = bool(self.isa_data.get("floppy"))
        floppy_decl = '    const char *floppy_file = NULL;' if has_floppy else ""
        cart_usage_line = (
            '    printf("  --cart-rom <file>  Load cartridge ROM file (overrides generated default)\\n");'
            if has_cartridge
            else ""
        )
        floppy_usage_line = (
            '    printf("  --floppy <file> Load floppy disk image\\n");' if has_floppy else ""
        )
        cart_cli_parse = (
            '        } else if (strcmp(argv[i], "--cart-rom") == 0 && i + 1 < argc) {\n'
            "            cart_rom_file = argv[++i];\n"
            if has_cartridge
            else ""
        )
        floppy_cli_parse = (
            '        } else if (strcmp(argv[i], "--floppy") == 0 && i + 1 < argc) {\n'
            "            floppy_file = argv[++i];\n"
            if has_floppy
            else ""
        )
        cart_default_decl = (
            f'    const char *cart_rom_file = "{default_cart_rom}";' if has_cartridge else ""
        )
        cart_load_block = (
            "    if (cart_rom_file && cart_rom_file[0]) {{{{\n"
            "        if (" + self.cpu_prefix + "_load_cartridge_rom(cpu, cart_rom_file) != 0) {{{{\n"
            '            fprintf(stderr, "Failed to load cartridge ROM: %s\\n", cart_rom_file);\n'
            "            return 1;\n"
            "        }}}}\n"
            "        " + self.cpu_prefix + "_reset(cpu);\n"
            '        printf("Loaded cartridge ROM: %s\\n", cart_rom_file);\n'
            "    }}}}\n"
            if has_cartridge
            else ""
        )
        keyboard_usage_line = (
            '    printf("  --keyboard-map <file>  Load runtime keyboard map YAML\\n");'
            if keyboard_map_supported
            else ""
        )
        keyboard_cli_parse = (
            '        } else if (strcmp(argv[i], "--keyboard-map") == 0 && i + 1 < argc) {\n'
            "            keyboard_map_file = argv[++i];\n"
            if keyboard_map_supported
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
            "    if (keyboard_map_file && keyboard_map_file[0]) {{{{\n"
            "        if (" + self.cpu_prefix + "_load_keyboard_map(cpu, keyboard_map_file) != 0) {{{{\n"
            '            fprintf(stderr, "Failed to load keyboard map: %s\\n", keyboard_map_file);\n'
            "            return 1;\n"
            "        }}}}\n"
            '        printf("Loaded keyboard map: %s\\n", keyboard_map_file);\n'
            "    }}}}\n"
            if keyboard_map_required
            else ""
        )
        floppy_load_block = (
            "    if (floppy_file == NULL || floppy_file[0] == '\\0') {\n"
            '        floppy_file = getenv("PASM_EMU_FLOPPY_AUTO_PATH");\n'
            "    }\n"
            "    if (floppy_file != NULL && floppy_file[0] != '\\0') {\n"
            f"        if ({self.cpu_prefix}_load_floppy_media(cpu, floppy_file) != 0) {{\n"
            '            fprintf(stderr, "Failed to load floppy image: %s\\n", floppy_file);\n'
            "            return 1;\n"
            "        }\n"
            '        printf("Loaded floppy image: %s\\n", floppy_file);\n'
            "    }\n"
            if has_floppy
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
{floppy_usage_line}
    printf("  --addr <addr>   Load address (default: 0x0000)\\n");
    printf("  --run           Run emulator\\n");
    printf("  --cycles <n>    Run for n cycles\\n");
    printf("  --test <name>   Run test\\n");
    printf("  --help          Show this help\\n");
}}

static size_t pasm_c64_decode_autotype(const char *text, uint8_t *out, size_t cap) {{
    size_t len = 0u;
    if (text == NULL || out == NULL || cap == 0u) return 0u;
    while (*text != '\\0' && len < cap) {{
        unsigned char ch = (unsigned char)*text++;
        if (ch == '\\\\' && *text != '\\0') {{
            unsigned char esc = (unsigned char)*text++;
            if (esc == 'r') ch = 0x0Du;
            else if (esc == 'n') ch = 0x0Du;
            else if (esc == 't') ch = 0x09u;
            else ch = esc;
        }} else if (ch == '\\n' || ch == '\\r') {{
            ch = 0x0Du;
        }}
        out[len++] = (uint8_t)ch;
    }}
    if (len < cap && (len == 0u || out[len - 1u] != 0x0Du)) {{
        out[len++] = 0x0Du;
    }}
    return len;
}}

static void pasm_c64_inject_keybuf(CPUState *cpu, const char *text) {{
    uint8_t buf[256];
    size_t len = pasm_c64_decode_autotype(text, buf, sizeof(buf));
    if (cpu == NULL || len == 0u) return;
    for (size_t i = 0u; i < len; ++i) {{
        {cpu_prefix}_write_byte(cpu, (uint16_t)(0x0277u + i), buf[i]);
    }}
    {cpu_prefix}_write_byte(cpu, 0x00C6u, (uint8_t)len);
    printf("Injected C64 keyboard buffer: %zu byte(s)\\n", len);
}}

static char pasm_c64_screen_char(uint8_t code) {{
    if (code >= 1u && code <= 26u) return (char)('A' + code - 1u);
    if (code >= 48u && code <= 57u) return (char)code;
    if (code == 32u || code == 160u) return ' ';
    if (code == 34u) return '"';
    if (code == 36u) return '$';
    if (code == 42u) return '*';
    if (code == 44u) return ',';
    if (code == 45u) return '-';
    if (code == 46u) return '.';
    if (code == 47u) return '/';
    if (code == 58u) return ':';
    if (code == 63u) return '?';
    return '.';
}}

static void pasm_c64_dump_screen(CPUState *cpu) {{
    const char *env = getenv("PASM_C64_SCREEN_DUMP");
    if (cpu == NULL || env == NULL || env[0] == '\\0' || env[0] == '0') return;
    printf("C64 status ST=$%02X\\n", (unsigned){cpu_prefix}_read_byte(cpu, 0x0090u));
    for (uint16_t row = 0u; row < 25u; ++row) {{
        char line[41];
        for (uint16_t col = 0u; col < 40u; ++col) {{
            line[col] = pasm_c64_screen_char({cpu_prefix}_read_byte(cpu, (uint16_t)(0x0400u + row * 40u + col)));
        }}
        line[40] = '\\0';
        printf("C64SCREEN:%02u:%s\\n", (unsigned)row, line);
    }}
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
{floppy_decl}
{cart_default_decl}
    const char *c64_autotype_text = getenv("PASM_C64_AUTOTYPE");
    const char *c64_autotype_cycle_env = getenv("PASM_C64_AUTOTYPE_CYCLE");
    uint64_t c64_autotype_cycle = 5000000u;
    uint16_t load_addr = 0;
    const char *test_name = NULL;

    if (c64_autotype_cycle_env != NULL && c64_autotype_cycle_env[0] != '\\0') {{
        c64_autotype_cycle = strtoull(c64_autotype_cycle_env, NULL, 0);
    }}
    
    for (int i = 1; i < argc; i++) {{
        if (strcmp(argv[i], "--system-dir") == 0 && i + 1 < argc) {{
            system_dir = argv[++i];
{keyboard_cli_parse}        }} else if (strcmp(argv[i], "--rom") == 0 && i + 1 < argc) {{
            rom_file = argv[++i];
{floppy_cli_parse}        }} else if (0) {{
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

{floppy_load_block}
    
    if (test_name) {{
        printf("Running test: %s\\n", test_name);
        if (strcmp(test_name, "basic") == 0) {{
            {cpu_prefix}_run_until(cpu, 100);
            printf("Executed %llu cycles\\n", cpu->total_cycles);
            {cpu_prefix}_dump_registers(cpu);
        }}
    }} else if (run_emulator || max_cycles > 0) {{
        if (max_cycles > 0) {{
            if (c64_autotype_text != NULL && c64_autotype_text[0] != '\\0' && c64_autotype_cycle < max_cycles) {{
                {cpu_prefix}_run_until(cpu, c64_autotype_cycle);
                pasm_c64_inject_keybuf(cpu, c64_autotype_text);
                {cpu_prefix}_run_until(cpu, max_cycles);
            }} else {{
                {cpu_prefix}_run_until(cpu, max_cycles);
            }}
            printf("Executed %llu cycles\\n", cpu->total_cycles);
        }} else {{
            if (c64_autotype_text != NULL && c64_autotype_text[0] != '\\0') {{
                {cpu_prefix}_run_until(cpu, c64_autotype_cycle);
                pasm_c64_inject_keybuf(cpu, c64_autotype_text);
            }}
            {cpu_prefix}_run(cpu);
        }}
    }} else {{
        print_usage(argv[0]);
    }}
    
    pasm_c64_dump_screen(cpu);
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
            floppy_usage_line=floppy_usage_line,
            cart_default_decl=cart_default_decl,
            keyboard_cli_parse=keyboard_cli_parse,
            floppy_cli_parse=floppy_cli_parse,
            cart_cli_parse=cart_cli_parse,
            floppy_decl=floppy_decl,
            floppy_load_block=floppy_load_block,
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

    def _generate_vs_debug_script(self) -> str:
        """Generate a Windows helper that creates and opens a Visual Studio solution."""

        return f"""@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\\" set "ROOT=%ROOT:~0,-1%"
set "BUILD_DIR=%ROOT%\\build_vs"
set "GENERATOR=Visual Studio 17 2022"
set "PLATFORM=x64"

set "EXTRA_CMAKE_ARGS="
if defined VCPKG_TARGET_TRIPLET (
  set "PASM_VCPKG_TRIPLET=%VCPKG_TARGET_TRIPLET%"
) else (
  set "PASM_VCPKG_TRIPLET=x64-windows"
)
set "EXTRA_CMAKE_ARGS=%EXTRA_CMAKE_ARGS% -DVCPKG_TARGET_TRIPLET=%PASM_VCPKG_TRIPLET% -DPASM_VCPKG_TRIPLET=%PASM_VCPKG_TRIPLET%"

if defined VCPKG_ROOT (
  if exist "%VCPKG_ROOT%\\scripts\\buildsystems\\vcpkg.cmake" (
    set "EXTRA_CMAKE_ARGS=%EXTRA_CMAKE_ARGS% -DCMAKE_TOOLCHAIN_FILE=%VCPKG_ROOT%\\scripts\\buildsystems\\vcpkg.cmake"
  )
) else if exist "D:\\Development\\vcpkg\\scripts\\buildsystems\\vcpkg.cmake" (
  set "VCPKG_ROOT=D:\\Development\\vcpkg"
  set "EXTRA_CMAKE_ARGS=%EXTRA_CMAKE_ARGS% -DCMAKE_TOOLCHAIN_FILE=D:\\Development\\vcpkg\\scripts\\buildsystems\\vcpkg.cmake"
) else if exist "C:\\vcpkg\\scripts\\buildsystems\\vcpkg.cmake" (
  set "VCPKG_ROOT=C:\\vcpkg"
  set "EXTRA_CMAKE_ARGS=%EXTRA_CMAKE_ARGS% -DCMAKE_TOOLCHAIN_FILE=C:\\vcpkg\\scripts\\buildsystems\\vcpkg.cmake"
)

echo Generating Visual Studio solution for {self.cpu_name}...
cmake -S "%ROOT%" -B "%BUILD_DIR%" -G "%GENERATOR%" -A "%PLATFORM%" %EXTRA_CMAKE_ARGS%
if errorlevel 1 exit /b %ERRORLEVEL%

set "SLN=%BUILD_DIR%\\{self.cpu_prefix}_emulator.sln"
if not exist "%SLN%" (
  echo Expected solution was not generated: "%SLN%"
  exit /b 1
)

start "" "%SLN%"
exit /b 0
"""

    def _generate_debugger_link_manifest(self) -> Dict[str, Any]:
        """Generate debugger linkage metadata for Rust/C host frontends."""

        metadata = self.isa_data.get("metadata", {})
        system_meta = self.isa_data.get("system", {}).get("metadata", {})
        memory = self.isa_data.get("memory", {})
        coding = self.isa_data.get("coding", {})
        linked_libraries = _flatten_platform_values_for_host(coding.get("linked_libraries", []))
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
        if host_backend_target == "glfw":
            glfw_lib = "glfw3dll" if os.name == "nt" else "glfw"
            if glfw_lib not in link_library_names:
                link_library_names.append(glfw_lib)
            if "SDL2" not in link_library_names:
                link_library_names.append("SDL2")
            opengl_lib = "opengl32" if os.name == "nt" else "GL"
            if opengl_lib not in link_library_names:
                link_library_names.append(opengl_lib)
            if os.name == "nt" and "winmm" not in link_library_names:
                link_library_names.append("winmm")
            if sys.platform.startswith("linux") and "asound" not in link_library_names:
                link_library_names.append("asound")

        is_windows = os.name == "nt"
        if is_windows:
            cpu_core_static = f"{self.cpu_prefix}_cpu_core.lib"
            system_static = f"{self.system_prefix}_system.lib"
        else:
            cpu_core_static = f"lib{self.cpu_prefix}_cpu_core.a"
            system_static = f"lib{self.system_prefix}_system.a"

        return {
            "schema_version": 1,
            "processor_name": metadata.get("name", self.cpu_name),
            "processor_version": metadata.get("version", ""),
            "system_name": system_meta.get("name", "system"),
            "cpu_name": self.cpu_name,
            "cpu_prefix": self.cpu_prefix,
            "system_prefix": self.system_prefix,
            "cmake_library_target": f"{self.system_prefix}_system",
            "library_basename": f"{self.system_prefix}_system",
            "split_targets": {
                "cpu_core": f"{self.cpu_prefix}_cpu_core",
                "system": f"{self.system_prefix}_system",
            },
            "split_units": {
                "cpu_core_sources": [
                    f"src/{self.cpu_name}_core.c",
                    f"src/{self.cpu_name}_decoder.c",
                    f"src/{self.cpu_name}_debug_abi.c",
                    "src/emu_automation.c",
                    f"src/{self.cpu_name}_automation_adapter.c",
                ],
                "system_sources": [
                    f"src/{name}.c"
                    for name in (
                        system_unit_basenames(self.system_prefix)
                        + ic_unit_basenames(self.isa_data, self.system_prefix)
                    )
                ],
            },
            "split_artifacts": {
                "cpu_core_static": cpu_core_static,
                "system_static": system_static,
            },
            "artifacts": {
                "static": system_static,
            },
            "headers": {
                "cpu": f"src/{self.cpu_name}.h",
                "debug_abi": f"src/{self.cpu_name}_debug_abi.h",
                "automation_abi": "src/emu_automation.h",
                "automation_adapter": f"src/{self.cpu_name}_automation_adapter.h",
            },
            "link": {
                "library_paths": _flatten_platform_values_for_host(coding.get("library_paths", [])),
                "library_names": link_library_names,
                "library_files": link_library_files,
            },
            "memory_default_size": int(memory.get("default_size", 65536)),
            "automation": {
                "system": self.isa_data.get("system", {}).get("automation", {}),
            },
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


def generate_from_subsystem(
    subsystem_path: str,
    output_dir: str,
    dispatch_mode: str = "switch",
) -> None:
    """Generate a standalone emulator from a subsystem descriptor."""
    loader = ProcessorSystemLoader()
    subsystem_data = loader.load_subsystem(subsystem_path)
    subsystem = subsystem_data.get("subsystem", {})
    processor_path = str(subsystem.get("processor", ""))
    system_path = str(subsystem.get("system", ""))
    system_data = loader.validate_system(loader._load_yaml(system_path, "system"))
    configured = system_data.get("components", {})
    configured_ic_ids = {str(item).strip() for item in configured.get("ics", [])}
    configured_device_ids = {str(item).strip() for item in configured.get("devices", [])}

    ic_paths: List[str] = []
    for path in subsystem.get("ics", []):
        path_str = str(path)
        ic_data = loader.validate_ic(loader._load_yaml(path_str, "ic"))
        ic_id = str(ic_data.get("metadata", {}).get("id", "")).strip()
        if ic_id in configured_ic_ids:
            ic_paths.append(path_str)

    device_paths: List[str] = []
    for group_name in ("media_backends", "bridge_devices", "core_devices"):
        for path in subsystem.get(group_name, []):
            path_str = str(path)
            device_data = loader.validate_device(loader._load_yaml(path_str, "device"))
            device_id = str(device_data.get("metadata", {}).get("id", "")).strip()
            if device_id in configured_device_ids:
                device_paths.append(path_str)
    generator = EmulatorGenerator(
        processor_path,
        system_path,
        ic_paths=ic_paths,
        device_paths=device_paths,
        host_paths=[],
        cartridge_map_path=None,
        cartridge_rom_path=None,
        host_backend_target=None,
    )
    generator.generate(output_dir, dispatch_mode=dispatch_mode)
    _namespace_generated_subsystem_output(
        generator,
        Path(output_dir),
        str(subsystem_data.get("metadata", {}).get("id", "")).strip(),
    )


def _posix_relpath(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path, base)).as_posix()


def _namespace_generated_subsystem_output(
    generator: EmulatorGenerator,
    output_dir: Path,
    subsystem_id: str,
) -> None:
    """Namespace subsystem-only exported symbols and build targets.

    Subsystems are compiled into host builds, so their public helper symbols and
    library target names must not collide with host-side or sibling subsystem
    outputs.
    """
    if not subsystem_id:
        return

    cpu_prefix = generator.cpu_prefix
    system_prefix = generator.system_prefix
    ns = _sanitize_ident(subsystem_id)
    namespaced_cpu_prefix = f"{ns}_{cpu_prefix}"
    namespaced_system_prefix = f"{ns}_{system_prefix}"

    replacements = [
        ("cpu_components_", f"{ns}_cpu_components_"),
        ("cpu_component_", f"{ns}_cpu_component_"),
        (f"{cpu_prefix}_", f"{namespaced_cpu_prefix}_"),
        ("pasm_dbg_", f"{ns}_pasm_dbg_"),
        ("g_runtime_keyboard_map", f"{ns}_g_runtime_keyboard_map"),
        ("g_component_connections_count", f"{ns}_g_component_connections_count"),
        ("g_component_connections", f"{ns}_g_component_connections"),
    ]

    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".c", ".h", ".txt", ".json", ".py", ""} and path.name not in {
            "CMakeLists.txt",
            "Makefile",
            "debugger_link.json",
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        orig = text
        for old, new in replacements:
            text = text.replace(old, new)
        text = text.replace(
            f"{system_prefix}_system", f"{namespaced_system_prefix}_system"
        )
        text = text.replace(
            f"lib{system_prefix}_system.a", f"lib{namespaced_system_prefix}_system.a"
        )
        if subsystem_id == "c64_1541_subsystem":
            text = text.replace("mos6510_read_byte", f"{namespaced_cpu_prefix}_read_byte")
            text = text.replace("mos6510_write_byte", f"{namespaced_cpu_prefix}_write_byte")
        if text != orig:
            path.write_text(text, encoding="utf-8")

    manifest_path = output_dir / "debugger_link.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["cpu_prefix"] = namespaced_cpu_prefix
        manifest["cmake_library_target"] = f"{namespaced_system_prefix}_system"
        manifest["library_basename"] = f"{namespaced_system_prefix}_system"
        manifest["split_targets"] = {
            "cpu_core": f"{namespaced_cpu_prefix}_cpu_core",
            "system": f"{namespaced_system_prefix}_system",
        }
        split_units = manifest.get("split_units", {}) or {}
        system_sources = list(split_units.get("system_sources", []) or [])
        normalized_system_sources = []
        for source in system_sources:
            source_text = str(source)
            source_text = source_text.replace(
                f"src/{namespaced_system_prefix}_system_bus.c",
                f"src/{system_prefix}_system_bus.c",
            )
            source_text = source_text.replace(
                f"src/{namespaced_system_prefix}_system_glue.c",
                f"src/{system_prefix}_system_glue.c",
            )
            normalized_system_sources.append(source_text)
        if split_units:
            split_units["system_sources"] = normalized_system_sources
            manifest["split_units"] = split_units
        manifest["split_artifacts"] = {
            "cpu_core_static": f"lib{namespaced_cpu_prefix}_cpu_core.a",
            "system_static": f"lib{namespaced_system_prefix}_system.a",
        }
        manifest["artifacts"] = {
            "static": f"lib{namespaced_system_prefix}_system.a",
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    cmake_path = output_dir / "CMakeLists.txt"
    if cmake_path.exists():
        cmake_text = cmake_path.read_text(encoding="utf-8")
        cmake_text = cmake_text.replace(
            f"src/{namespaced_system_prefix}_system_bus.c",
            f"src/{system_prefix}_system_bus.c",
        )
        cmake_text = cmake_text.replace(
            f"src/{namespaced_system_prefix}_system_glue.c",
            f"src/{system_prefix}_system_glue.c",
        )
        cmake_path.write_text(cmake_text, encoding="utf-8")


def _sanitize_ident(value: str) -> str:
    ident = re.sub(r"[^0-9A-Za-z_]", "_", value.strip()).lower().strip("_")
    if not ident:
        return "subsystem"
    if ident[0].isdigit():
        return f"subsystem_{ident}"
    return ident
