import os
import pathlib
import re
import shutil
import subprocess
import urllib.request
import uuid

import pytest

from src import generator as gen_mod
from tests.support import BASE_DIR


RUN_ENV = "PASM_RUN_NESTEST"
ROM_PATH_ENV = "PASM_NESTEST_ROM_PATH"
LOG_PATH_ENV = "PASM_NESTEST_LOG_PATH"
MAX_STEPS_ENV = "PASM_NESTEST_MAX_STEPS"

NESTEST_ROM_URLS = [
    "https://raw.githubusercontent.com/christopherpow/nes-test-roms/master/other/nestest.nes",
    "https://raw.githubusercontent.com/christopherpow/nes-test-roms/master/other/nestest/nestest.nes",
]
NESTEST_LOG_URLS = [
    "https://raw.githubusercontent.com/christopherpow/nes-test-roms/master/other/nestest.log",
    "https://raw.githubusercontent.com/christopherpow/nes-test-roms/master/other/nestest/nestest.log",
]


def _want_run() -> bool:
    return os.environ.get(RUN_ENV, "").lower() in {"1", "true", "yes", "on"}


def _max_steps(default_steps: int) -> int:
    raw = os.environ.get(MAX_STEPS_ENV, "").strip()
    if not raw:
        return default_steps
    value = int(raw, 10)
    if value <= 0:
        raise RuntimeError(f"{MAX_STEPS_ENV} must be > 0, got {value}")
    return value


def _download_first(urls: list[str], dst: pathlib.Path) -> pathlib.Path:
    errors: list[str] = []
    headers = {"User-Agent": "pasm-nestest/1.0"}
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                payload = response.read()
            if not payload:
                errors.append(f"{url}: empty payload")
                continue
            tmp = dst.with_suffix(".tmp")
            tmp.write_bytes(payload)
            tmp.replace(dst)
            return dst
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("unable to download file; " + " | ".join(errors))


def _resolve_or_download(path_env: str, urls: list[str], default_name: str) -> pathlib.Path:
    env_path = os.environ.get(path_env, "").strip()
    if env_path:
        p = pathlib.Path(env_path).expanduser().resolve()
        if not p.exists():
            raise RuntimeError(f"{path_env} does not exist: {p}")
        return p

    cache_dir = BASE_DIR / "tests" / "data" / "nes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    dst = cache_dir / default_name
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    return _download_first(urls, dst)


def _make_workdir(prefix: str) -> pathlib.Path:
    root = BASE_DIR / ".tmp_test_work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


def _ines_to_cpu_image(nes_rom: bytes) -> bytes:
    if len(nes_rom) < 16 or nes_rom[0:4] != b"NES\x1A":
        raise RuntimeError("invalid iNES header in nestest ROM")

    prg_banks = nes_rom[4]
    flag6 = nes_rom[6]
    has_trainer = (flag6 & 0x04) != 0
    offset = 16 + (512 if has_trainer else 0)
    prg_size = prg_banks * 16 * 1024
    prg = nes_rom[offset : offset + prg_size]
    if len(prg) != prg_size:
        raise RuntimeError("nestest ROM is truncated (PRG data missing)")

    image = bytearray([0x00] * 65536)
    if prg_banks == 1:
        image[0x8000:0xC000] = prg
        image[0xC000:0x10000] = prg
    else:
        image[0x8000:0x10000] = prg[: 32 * 1024]
    return bytes(image)


def _parse_golden_states(log_text: str) -> list[tuple[int, int, int, int, int, int]]:
    out: list[tuple[int, int, int, int, int, int]] = []
    pattern = re.compile(
        r"^([0-9A-F]{4}).*A:([0-9A-F]{2}) X:([0-9A-F]{2}) Y:([0-9A-F]{2}) P:([0-9A-F]{2}) SP:([0-9A-F]{2})"
    )
    for line in log_text.splitlines():
        m = pattern.match(line.strip())
        if not m:
            continue
        out.append(tuple(int(x, 16) for x in m.groups()))
    if not out:
        raise RuntimeError("failed to parse any states from nestest.log")
    return out


def _harness_source() -> str:
    return r"""#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "MOS6502.h"

int main(int argc, char **argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: %s <image.bin> <start_pc_hex> <steps>\n", argv[0]);
        return 2;
    }

    const char *image_path = argv[1];
    uint32_t start_pc = (uint32_t)strtoul(argv[2], NULL, 16);
    uint64_t max_steps = strtoull(argv[3], NULL, 10);
    if (max_steps == 0ULL) max_steps = 1ULL;

    CPUState *cpu = mos6502_create(65536);
    if (!cpu) return 3;
    if (mos6502_load_rom(cpu, image_path, 0x0000u) != 0) {
        mos6502_destroy(cpu);
        return 4;
    }

    cpu->pc = (uint16_t)start_pc;
    cpu->registers[REG_A] = 0x00u;
    cpu->registers[REG_X] = 0x00u;
    cpu->registers[REG_Y] = 0x00u;
    cpu->flags.raw = 0x24u;
    cpu->sp = 0xFDu;
    cpu->running = 1;
    cpu->halted = 0;

    for (uint64_t i = 0; i < max_steps; ++i) {
        printf(
            "%04X A:%02X X:%02X Y:%02X P:%02X SP:%02X\n",
            cpu->pc,
            cpu->registers[REG_A],
            cpu->registers[REG_X],
            cpu->registers[REG_Y],
            cpu->flags.raw,
            cpu->sp
        );
        int rc = mos6502_step(cpu);
        if (rc != 0 || !cpu->running) {
            break;
        }
    }

    mos6502_destroy(cpu);
    return 0;
}
"""


@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
def test_ricoh2a03_matches_nestest_golden_log():
    if not _want_run():
        pytest.skip(f"Set {RUN_ENV}=1 to run nestest CPU compatibility check")

    rom_path = _resolve_or_download(ROM_PATH_ENV, NESTEST_ROM_URLS, "nestest.nes")
    log_path = _resolve_or_download(LOG_PATH_ENV, NESTEST_LOG_URLS, "nestest.log")

    golden = _parse_golden_states(log_path.read_text(encoding="utf-8", errors="replace"))
    steps = _max_steps(len(golden))
    golden = golden[:steps]

    outdir = _make_workdir("ricoh2a03_nestest_") / "generated"
    processor_path = BASE_DIR / "examples" / "processors" / "ricoh2a03.yaml"
    system_path = BASE_DIR / "examples" / "systems" / "mos6502" / "mos6502_default.yaml"
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    harness_c = outdir / "nestest_harness.c"
    harness_c.write_text(_harness_source(), encoding="utf-8")
    harness_bin = outdir / ("nestest_harness.exe" if os.name == "nt" else "nestest_harness")
    cc = shutil.which("cc") or shutil.which("gcc")
    if not cc:
        pytest.skip("No C compiler available on PATH")
    subprocess.check_call(
        [
            cc,
            "-std=c11",
            "-O2",
            "-I",
            str(outdir / "src"),
            str(outdir / "src" / "MOS6502_core.c"),
            str(outdir / "src" / "MOS6502_decoder.c"),
            str(harness_c),
            "-o",
            str(harness_bin),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    image_path = outdir / "nestest_cpu_image.bin"
    image_path.write_bytes(_ines_to_cpu_image(rom_path.read_bytes()))

    proc = subprocess.run(
        [str(harness_bin), str(image_path), "C000", str(steps)],
        check=True,
        capture_output=True,
        text=True,
    )
    actual_lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    pattern = re.compile(
        r"^([0-9A-F]{4}) A:([0-9A-F]{2}) X:([0-9A-F]{2}) Y:([0-9A-F]{2}) P:([0-9A-F]{2}) SP:([0-9A-F]{2})$"
    )
    actual: list[tuple[int, int, int, int, int, int]] = []
    for line in actual_lines:
        m = pattern.match(line)
        if m:
            actual.append(tuple(int(x, 16) for x in m.groups()))

    assert len(actual) >= len(golden), (
        f"nestest run ended early: got {len(actual)} states, expected {len(golden)}\n"
        f"last output line: {actual_lines[-1] if actual_lines else '<none>'}"
    )
    for i, (a, e) in enumerate(zip(actual, golden)):
        if a != e:
            raise AssertionError(
                f"nestest mismatch at step {i}: actual={a} expected={e}\n"
                f"actual_line={actual_lines[i]}"
            )
