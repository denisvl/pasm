from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from src import generator as gen_mod
from tests.test_all_systems_compilation import ALL_COMPILE_CASES, BASE_DIR, CompileCase


COMMON_LINK_LIBS = ["-lz"] if sys.platform != "win32" else []


def _compile_case(system_rel: str) -> CompileCase:
    for case in ALL_COMPILE_CASES:
        if case.case_id == system_rel:
            return case
    raise AssertionError(f"Missing compile case for {system_rel}")


def _processor_name(case: CompileCase) -> str:
    data = yaml.safe_load(case.processor_path.read_text(encoding="utf-8")) or {}
    name = str((data.get("metadata") or {}).get("name", "")).strip()
    if not name:
        raise AssertionError(f"Processor metadata.name missing for {case.processor_path}")
    return name


def _system_yaml(case: CompileCase) -> dict:
    data = yaml.safe_load(case.system_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise AssertionError(f"Expected mapping at top level of {case.system_path}")
    return data


def _primary_text_view(case: CompileCase) -> dict:
    data = _system_yaml(case)
    views = (
        (data.get("automation") or {})
        .get("screen", {})
        .get("text_views", [])
    )
    for view in views:
        if view.get("id") == "primary_text":
            return view
    raise AssertionError(f"primary_text automation view missing in {case.system_path}")


def _framebuffer_view(case: CompileCase) -> dict:
    data = _system_yaml(case)
    screen = (data.get("automation") or {}).get("screen", {})
    framebuffer = screen.get("framebuffer")
    if isinstance(framebuffer, dict):
        return framebuffer
    views = screen.get("framebuffer_views", [])
    if views:
        return views[0]
    raise AssertionError(f"framebuffer automation view missing in {case.system_path}")


def _write_text_grid_smoke_harness(
    outdir: Path,
    processor_name: str,
    expected_columns: int,
    expected_rows: int,
) -> Path:
    cpu_prefix = processor_name.lower()
    header_name = f"{processor_name}_automation_adapter.h"
    harness = outdir / "automation_smoke.c"
    harness.write_text(
        textwrap.dedent(
            f"""
            #include "{header_name}"
            #include <stdint.h>
            #include <stdio.h>
            #include <string.h>

            int main(void) {{
                CPUState *cpu = pasm_dbg_create(65536u);
                emu_automation_machine_t *machine = NULL;
                emu_automation_text_view_descriptor_t descriptor;
                emu_automation_text_grid_snapshot_t text;
                emu_automation_capabilities_t caps;
                size_t text_view_count = 0u;
                int rc = 0;

                if (cpu == NULL) return 1;
                memset(&descriptor, 0, sizeof(descriptor));
                memset(&text, 0, sizeof(text));
                memset(&caps, 0, sizeof(caps));

                if ({cpu_prefix}_automation_attach_debug(cpu, &machine) != EMU_AUTOMATION_OK) {{
                    pasm_dbg_destroy(cpu);
                    return 2;
                }}
                if (emu_automation_machine_capabilities(machine, &caps) != EMU_AUTOMATION_OK) {{
                    rc = 3;
                    goto cleanup;
                }}
                if (emu_automation_screen_text_view_count(machine, &text_view_count) != EMU_AUTOMATION_OK) {{
                    rc = 4;
                    goto cleanup;
                }}
                if (text_view_count < 1u) {{
                    rc = 5;
                    goto cleanup;
                }}
                if (emu_automation_screen_text_view_descriptor(machine, 0u, &descriptor) != EMU_AUTOMATION_OK) {{
                    rc = 6;
                    goto cleanup;
                }}
                if (strcmp(descriptor.region_id, "primary_text") != 0) {{
                    rc = 7;
                    goto cleanup;
                }}
                if (descriptor.columns != {expected_columns}u || descriptor.rows != {expected_rows}u) {{
                    rc = 8;
                    goto cleanup;
                }}
                if (emu_automation_screen_text_grid(machine, "primary_text", &text) != EMU_AUTOMATION_OK) {{
                    rc = 9;
                    goto cleanup;
                }}
                if (text.columns != {expected_columns}u || text.rows != {expected_rows}u) {{
                    rc = 10;
                    goto cleanup;
                }}
                if (text.cell_count != ((size_t){expected_columns}u * (size_t){expected_rows}u)) {{
                    rc = 11;
                    goto cleanup;
                }}
                if (text.cells == NULL || text.plain_utf8 == NULL) {{
                    rc = 12;
                    goto cleanup;
                }}

            cleanup:
                if (text.cells != NULL || text.plain_utf8 != NULL) {{
                    emu_automation_text_grid_release(machine, &text);
                }}
                if (machine != NULL) {{
                    emu_automation_machine_destroy(machine);
                }}
                pasm_dbg_destroy(cpu);
                return rc;
            }}
            """
        ),
        encoding="utf-8",
    )
    return harness


def _write_framebuffer_smoke_harness(
    outdir: Path,
    processor_name: str,
    expected_width: int,
    expected_height: int,
    system_base_dir: str,
    cartridge_rom_path: str | None,
) -> Path:
    cpu_prefix = processor_name.lower()
    header_name = f"{processor_name}_automation_adapter.h"
    harness = outdir / "automation_framebuffer_smoke.c"
    harness.write_text(
        textwrap.dedent(
            f"""
            #include "{header_name}"
            #include <stdint.h>
            #include <string.h>

            int main(void) {{
                CPUState *cpu = pasm_dbg_create(65536u);
                emu_automation_machine_t *machine = NULL;
                emu_automation_framebuffer_snapshot_t framebuffer;
                int rc = 0;

                if (cpu == NULL) return 1;
                memset(&framebuffer, 0, sizeof(framebuffer));

                if (pasm_dbg_load_system_roms(cpu, "{system_base_dir}") != 0) {{
                    pasm_dbg_destroy(cpu);
                    return 13;
                }}
                {"if (pasm_dbg_load_cartridge_rom(cpu, \"" + cartridge_rom_path + "\") != 0) { pasm_dbg_destroy(cpu); return 14; }" if cartridge_rom_path else ""}

                if ({cpu_prefix}_automation_attach_debug(cpu, &machine) != EMU_AUTOMATION_OK) {{
                    pasm_dbg_destroy(cpu);
                    return 2;
                }}
                if (emu_automation_machine_reset(machine, EMU_AUTOMATION_RESET_COLD) != EMU_AUTOMATION_OK) {{
                    rc = 3;
                    goto cleanup;
                }}
                if (emu_automation_machine_resume(machine) != EMU_AUTOMATION_OK) {{
                    rc = 4;
                    goto cleanup;
                }}
                if (emu_automation_machine_run_frames(machine, 4u) != EMU_AUTOMATION_OK) {{
                    rc = 5;
                    goto cleanup;
                }}
                if (emu_automation_screen_framebuffer(machine, &framebuffer) != EMU_AUTOMATION_OK) {{
                    rc = 6;
                    goto cleanup;
                }}
                if (framebuffer.width != {expected_width}u || framebuffer.height != {expected_height}u) {{
                    rc = 7;
                    goto cleanup;
                }}
                if (framebuffer.visible_area.width != {expected_width}u ||
                    framebuffer.visible_area.height != {expected_height}u) {{
                    rc = 8;
                    goto cleanup;
                }}
                if (framebuffer.pixel_format != EMU_AUTOMATION_PIXEL_FORMAT_RGBA8888) {{
                    rc = 9;
                    goto cleanup;
                }}
                if (framebuffer.pixels == NULL) {{
                    rc = 10;
                    goto cleanup;
                }}
                if (framebuffer.stride_bytes < ({expected_width}u * 4u)) {{
                    rc = 11;
                    goto cleanup;
                }}
                if (framebuffer.pixel_size < (size_t)framebuffer.stride_bytes * (size_t)framebuffer.height) {{
                    rc = 12;
                    goto cleanup;
                }}

            cleanup:
                if (framebuffer.pixels != NULL) {{
                    emu_automation_framebuffer_release(machine, &framebuffer);
                }}
                if (machine != NULL) {{
                    emu_automation_machine_destroy(machine);
                }}
                pasm_dbg_destroy(cpu);
                return rc;
            }}
            """
        ),
        encoding="utf-8",
    )
    return harness


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
@pytest.mark.skipif(shutil.which("cc") is None, reason="cc is not available")
@pytest.mark.parametrize(
    "system_rel",
    [
        "examples/systems/apple2/apple2_default.yaml",
        "examples/systems/atari800xl/atari800xl_default.yaml",
        "examples/systems/bbcmicro/bbc_micro_default.yaml",
        "examples/systems/c64/c64_default.yaml",
        "examples/systems/coco1/coco1_default.yaml",
        "examples/systems/cpc464/cpc464_default.yaml",
        "examples/systems/msx1/msx1_default.yaml",
        "examples/systems/sg1000/sg1000_default.yaml",
        "examples/systems/tdp100/tdp100_default.yaml",
        "examples/systems/trs80_model4/trs80_model4_default.yaml",
    ],
)
def test_generated_real_system_exposes_text_grid_automation_smoke(
    tmp_path: Path,
    system_rel: str,
):
    case = _compile_case(system_rel)
    processor_name = _processor_name(case)
    text_view = _primary_text_view(case)
    expected_columns = int(text_view["columns"])
    expected_rows = int(text_view["rows"])
    outdir = tmp_path / case.system_path.stem

    gen_mod.generate(
        str(case.processor_path),
        str(case.system_path),
        str(outdir),
        ic_paths=[str(path) for path in case.ic_paths],
        device_paths=[str(path) for path in case.device_paths],
        host_paths=[str(path) for path in case.host_paths],
        cartridge_map_path=str(case.cartridge_map_path) if case.cartridge_map_path else None,
        cartridge_rom_path=case.cartridge_rom_path,
        host_backend_target=case.host_backend_target,
    )

    build_dir = outdir / "build"
    subprocess.run(
        ["cmake", "-S", str(outdir), "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release"],
        cwd=BASE_DIR,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    subprocess.run(
        ["cmake", "--build", str(build_dir), "--config", "Release"],
        cwd=BASE_DIR,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    harness = _write_text_grid_smoke_harness(outdir, processor_name, expected_columns, expected_rows)
    static_libs = sorted(
        build_dir.glob("*.a"),
        key=lambda path: ("cpu_core" not in path.name, path.name),
    )
    assert static_libs, f"no static libraries found in {build_dir}"

    binary = outdir / "automation_smoke"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-I",
            str(outdir / "src"),
            str(harness),
            *[str(path) for path in static_libs],
            *COMMON_LINK_LIBS,
            "-o",
            str(binary),
        ],
        cwd=BASE_DIR,
        check=True,
    )

    proc = subprocess.run([str(binary)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout or f"exit={proc.returncode}"


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
@pytest.mark.skipif(shutil.which("cc") is None, reason="cc is not available")
@pytest.mark.parametrize(
    "system_rel",
    [
        "examples/systems/atari2600/atari2600_default.yaml",
        "examples/systems/nes/nes_default.yaml",
        "examples/systems/sms/sms_default.yaml",
        "examples/systems/zx_spectrum48k/spectrum48k_default.yaml",
    ],
)
def test_generated_real_system_exposes_framebuffer_automation_smoke(
    tmp_path: Path,
    system_rel: str,
):
    case = _compile_case(system_rel)
    processor_name = _processor_name(case)
    framebuffer_view = _framebuffer_view(case)
    expected_width = int(framebuffer_view["width"])
    expected_height = int(framebuffer_view["height"])
    outdir = tmp_path / case.system_path.stem

    gen_mod.generate(
        str(case.processor_path),
        str(case.system_path),
        str(outdir),
        ic_paths=[str(path) for path in case.ic_paths],
        device_paths=[str(path) for path in case.device_paths],
        host_paths=[str(path) for path in case.host_paths],
        cartridge_map_path=str(case.cartridge_map_path) if case.cartridge_map_path else None,
        cartridge_rom_path=case.cartridge_rom_path,
        host_backend_target=case.host_backend_target,
    )

    build_dir = outdir / "build"
    subprocess.run(
        ["cmake", "-S", str(outdir), "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release"],
        cwd=BASE_DIR,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    subprocess.run(
        ["cmake", "--build", str(build_dir), "--config", "Release"],
        cwd=BASE_DIR,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    harness = _write_framebuffer_smoke_harness(
        outdir,
        processor_name,
        expected_width,
        expected_height,
        str(case.system_path.parent),
        (
            str((case.system_path.parent / case.cartridge_rom_path).resolve())
            if case.cartridge_rom_path
            else None
        ),
    )
    static_libs = sorted(
        build_dir.glob("*.a"),
        key=lambda path: ("cpu_core" not in path.name, path.name),
    )
    assert static_libs, f"no static libraries found in {build_dir}"

    binary = outdir / "automation_framebuffer_smoke"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-I",
            str(outdir / "src"),
            str(harness),
            *[str(path) for path in static_libs],
            *COMMON_LINK_LIBS,
            "-o",
            str(binary),
        ],
        cwd=BASE_DIR,
        check=True,
    )

    proc = subprocess.run([str(binary)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout or f"exit={proc.returncode}"
