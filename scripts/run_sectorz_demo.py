#!/usr/bin/env python3
"""Compile and run the SectorZ hello-world demo against generated Z80 hooks."""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys

from src import generator as gen_mod


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLE_C = REPO_ROOT / "examples" / "sectorz_hello.c"
PROCESSOR_YAML = REPO_ROOT / "examples" / "processors" / "z80.yaml"
SYSTEM_YAML = REPO_ROOT / "examples" / "systems" / "z80_sectorz_hooks.yaml"
HARNESS_C = REPO_ROOT / "examples" / "sectorz_out_harness.c"


def _run(cmd: list[str], *, cwd: pathlib.Path | None = None, env: dict[str, str] | None = None) -> None:
    print("$", " ".join(str(p) for p in cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(cwd) if cwd else None, env=env)


def _pick_compiler() -> str:
    cc_env = os.environ.get("CC")
    if cc_env:
        if shutil.which(cc_env):
            return cc_env
        raise RuntimeError(f"CC is set but not found on PATH: {cc_env}")

    for candidate in ("cc", "gcc", "clang"):
        if shutil.which(candidate):
            return candidate
    raise RuntimeError("No C compiler found (tried CC, cc, gcc, clang).")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--z88dk-root",
        default=os.environ.get("PASM_SECTORZ_ROOT") or os.environ.get("Z88DK") or "/tmp/z88dk-src",
        help="Path to z88dk root directory (must contain bin/zcc and lib/config).",
    )
    parser.add_argument(
        "--workdir",
        default="/tmp/pasm-sectorz-demo",
        help="Working directory for generated emulator and outputs.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=200000,
        help="Maximum emulator steps for harness execution.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if (
        not SAMPLE_C.exists()
        or not PROCESSOR_YAML.exists()
        or not SYSTEM_YAML.exists()
        or not HARNESS_C.exists()
    ):
        raise RuntimeError("Missing required example files in ./examples")

    z88dk_root = pathlib.Path(args.z88dk_root).resolve()
    zcc = z88dk_root / "bin" / "zcc"
    zcccfg = z88dk_root / "lib" / "config"
    if not zcc.exists():
        raise RuntimeError(f"Missing SectorZ compiler: {zcc}")
    if not zcccfg.exists():
        raise RuntimeError(f"Missing z88dk config directory: {zcccfg}")

    workdir = pathlib.Path(args.workdir).resolve()
    rom_base = workdir / "sectorz_hello"
    rom_file = workdir / "sectorz_hello.rom"
    generated_dir = workdir / "generated"
    harness_bin = workdir / ("sectorz_out_harness.exe" if os.name == "nt" else "sectorz_out_harness")

    workdir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PATH"] = f"{z88dk_root / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env["ZCCCFG"] = str(zcccfg)

    _run(
        [
            "zcc",
            "+z80",
            "-compiler=sccz80",
            "-clib=classic",
            str(SAMPLE_C),
            "-o",
            str(rom_base),
            "-create-app",
        ],
        cwd=workdir,
        env=env,
    )
    if not rom_file.exists():
        raise RuntimeError(f"Expected ROM missing after build: {rom_file}")

    gen_mod.generate(str(PROCESSOR_YAML), str(SYSTEM_YAML), str(generated_dir))

    compiler = _pick_compiler()
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
            str(HARNESS_C),
            "-o",
            str(harness_bin),
        ]
    )

    _run([str(harness_bin), str(rom_file), str(args.max_steps)])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}", file=sys.stderr)
        raise
    except Exception as exc:  # pragma: no cover - top-level UX path
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
