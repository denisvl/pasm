import os
import pathlib
import re
import shutil
import subprocess

import pytest

from src import generator as gen_mod


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
SECTORZ_TAG = "v2.4"
SECTORZ_CACHE_ROOT = pathlib.Path("/tmp/pasm-sectorz-z88dk")
SECTORZ_SRC_DIR = SECTORZ_CACHE_ROOT / "src"
SECTORZ_STAMP = SECTORZ_CACHE_ROOT / "built-z80.stamp"
SECTORZ_SAMPLE_C = BASE_DIR / "examples" / "sectorz_hello.c"
SECTORZ_HOOK_ISA = BASE_DIR / "examples" / "z80_sectorz_hooks.yaml"
SECTORZ_HARNESS_C = BASE_DIR / "examples" / "sectorz_out_harness.c"


def _run(cmd: list[str], *, cwd: pathlib.Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.check_call(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def _ensure_sectorz_toolchain() -> pathlib.Path:
    toolchain_root = os.environ.get("PASM_SECTORZ_ROOT")
    if toolchain_root:
        root = pathlib.Path(toolchain_root)
        if (root / "bin" / "zcc").exists():
            return root
        pytest.skip(f"PASM_SECTORZ_ROOT is set but zcc is missing: {root / 'bin' / 'zcc'}")

    if os.environ.get("PASM_ENABLE_SECTORZ_TEST", "").lower() not in {"1", "true", "yes", "on"}:
        pytest.skip(
            "Set PASM_ENABLE_SECTORZ_TEST=1 to download/build SectorZ (z88dk) and run this integration test."
        )

    if SECTORZ_STAMP.exists() and (SECTORZ_SRC_DIR / "bin" / "zcc").exists():
        return SECTORZ_SRC_DIR

    if SECTORZ_SRC_DIR.exists():
        shutil.rmtree(SECTORZ_SRC_DIR)
    SECTORZ_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    _run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            SECTORZ_TAG,
            "https://github.com/z88dk/z88dk.git",
            str(SECTORZ_SRC_DIR),
        ]
    )
    _run(["git", "submodule", "update", "--init", "--recursive"], cwd=SECTORZ_SRC_DIR)

    build_env = os.environ.copy()
    build_env["CCACHE_DIR"] = "/tmp/ccache"
    build_env["CCACHE_TEMPDIR"] = "/tmp/ccache-tmp"
    pathlib.Path(build_env["CCACHE_DIR"]).mkdir(parents=True, exist_ok=True)
    pathlib.Path(build_env["CCACHE_TEMPDIR"]).mkdir(parents=True, exist_ok=True)

    # Build the z80 target libraries and toolchain once; cached under /tmp.
    _run(["./build.sh", "-p", "z80"], cwd=SECTORZ_SRC_DIR, env=build_env)
    SECTORZ_STAMP.write_text("ok\n", encoding="utf-8")
    return SECTORZ_SRC_DIR


def _compile_sectorz_program(toolchain_root: pathlib.Path, workdir: pathlib.Path) -> pathlib.Path:
    assert SECTORZ_SAMPLE_C.exists(), f"Missing sample source: {SECTORZ_SAMPLE_C}"

    env = os.environ.copy()
    env["PATH"] = f"{toolchain_root / 'bin'}:{env.get('PATH', '')}"
    env["ZCCCFG"] = str(toolchain_root / "lib" / "config")

    _run(
        [
            "zcc",
            "+z80",
            "-compiler=sccz80",
            "-clib=classic",
            str(SECTORZ_SAMPLE_C),
            "-o",
            str(workdir / "sectorz_print_sample"),
            "-create-app",
        ],
        cwd=workdir,
        env=env,
    )

    rom = workdir / "sectorz_print_sample.rom"
    assert rom.exists(), f"Expected compiled ROM missing: {rom}"
    return rom


def _generate_hooked_z80(outdir: pathlib.Path) -> pathlib.Path:
    outdir.mkdir(parents=True, exist_ok=True)
    assert SECTORZ_HOOK_ISA.exists(), f"Missing hook ISA: {SECTORZ_HOOK_ISA}"
    gen_mod.generate(str(SECTORZ_HOOK_ISA), str(outdir))
    return outdir


def _build_harness(generated_dir: pathlib.Path) -> pathlib.Path:
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        pytest.skip("No C compiler available on PATH")

    assert SECTORZ_HARNESS_C.exists(), f"Missing harness source: {SECTORZ_HARNESS_C}"

    binary_name = "sectorz_harness.exe" if os.name == "nt" else "sectorz_harness"
    binary = generated_dir / binary_name
    _run(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-I",
            str(generated_dir / "src"),
            str(generated_dir / "src" / "Z80.c"),
            str(generated_dir / "src" / "Z80_decoder.c"),
            str(generated_dir / "src" / "Z80_hooks.c"),
            str(SECTORZ_HARNESS_C),
            "-o",
            str(binary),
        ]
    )
    assert binary.exists(), f"Expected harness binary: {binary}"
    return binary


@pytest.mark.skipif(
    not (shutil.which("git") and (shutil.which("cc") or shutil.which("gcc"))),
    reason="git and C compiler are required for SectorZ integration test",
)
def test_sectorz_print_from_main_emits_hello_world_and_nul_with_expected_cycles(tmp_path):
    toolchain = _ensure_sectorz_toolchain()

    sectorz_work = tmp_path / "sectorz_src"
    sectorz_work.mkdir(parents=True, exist_ok=True)
    rom = _compile_sectorz_program(toolchain, sectorz_work)

    generated = _generate_hooked_z80(tmp_path / "generated")
    harness = _build_harness(generated)

    proc = subprocess.run([str(harness), str(rom)], check=True, capture_output=True)
    stdout = proc.stdout
    text = stdout.decode("latin1")

    assert b"hello world\x00" in stdout
    assert "COUNT=12" in text
    assert "HEX=68 65 6C 6C 6F 20 77 6F 72 6C 64 00" in text

    match = re.search(r"CYCLES=(\d+)", text)
    assert match, f"Missing CYCLES in output:\\n{text}"
    assert int(match.group(1)) == 5979
