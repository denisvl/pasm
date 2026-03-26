import os
import pathlib
import shutil
import subprocess
import hashlib
import urllib.request

import pytest

from src import generator as gen_mod
from tests.support import BASE_DIR, example_pair

RUN_ENV = "PASM_RUN_ZEXALL"
ZEXALL_PATH_ENV = "PASM_ZEXALL_PATH"
ZEXALL_MAX_STEPS_ENV = "PASM_ZEXALL_MAX_STEPS"
ZEXALL_SHA256 = "af7e5d86146d390a68440fb85668648f14a648602da29a1816d2ef11459411ae"
ZEXALL_URLS = [
    "https://raw.githubusercontent.com/superzazu/z80/master/roms/zexall.cim",
    "https://github.com/superzazu/z80/raw/master/roms/zexall.cim",
]


def _want_run_zexall() -> bool:
    return os.environ.get(RUN_ENV, "").lower() in {"1", "true", "yes", "on"}


def _zexall_max_steps() -> int:
    raw = os.environ.get(ZEXALL_MAX_STEPS_ENV, "").strip()
    if not raw:
        return 400_000_000
    try:
        value = int(raw, 10)
    except ValueError as exc:
        raise RuntimeError(f"invalid {ZEXALL_MAX_STEPS_ENV}={raw!r}") from exc
    if value <= 0:
        raise RuntimeError(f"{ZEXALL_MAX_STEPS_ENV} must be > 0, got {value}")
    return value


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: pathlib.Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _is_valid_zexall(path: pathlib.Path) -> bool:
    return path.exists() and path.stat().st_size > 0 and _sha256_file(path) == ZEXALL_SHA256


def _download_zexall_bytes() -> bytes:
    errors: list[str] = []
    request_headers = {"User-Agent": "pasm-zexall-test/1.0"}
    for url in ZEXALL_URLS:
        try:
            req = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                payload = response.read()
            if not payload:
                errors.append(f"{url}: empty payload")
                continue
            got = _sha256_bytes(payload)
            if got != ZEXALL_SHA256:
                errors.append(f"{url}: sha256 mismatch (got {got})")
                continue
            return payload
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("unable to download zexall.cim; " + " | ".join(errors))


def _ensure_zexall_binary() -> pathlib.Path:
    env_path = os.environ.get(ZEXALL_PATH_ENV, "").strip()
    if env_path:
        candidate = pathlib.Path(env_path).expanduser().resolve()
        if not _is_valid_zexall(candidate):
            raise RuntimeError(
                f"{ZEXALL_PATH_ENV} points to invalid zexall.cim (expected sha256={ZEXALL_SHA256}): {candidate}"
            )
        return candidate

    cache_dir = BASE_DIR / "tests" / "data" / "z80"
    cache_dir.mkdir(parents=True, exist_ok=True)
    zexall_path = cache_dir / "zexall.cim"
    if _is_valid_zexall(zexall_path):
        return zexall_path
    if zexall_path.exists():
        zexall_path.unlink()

    payload = _download_zexall_bytes()
    tmp_path = zexall_path.with_suffix(".tmp")
    tmp_path.write_bytes(payload)
    tmp_path.replace(zexall_path)
    return zexall_path


@pytest.fixture(scope="module")
def z80_zexall_harness(tmp_path_factory):
    if not _want_run_zexall():
        pytest.skip(f"Set {RUN_ENV}=1 to run the long ZEXALL integration test")

    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("No C compiler available on PATH")
    if not shutil.which("cmake"):
        pytest.skip("cmake not available on PATH")

    try:
        zexall = _ensure_zexall_binary()
    except Exception as exc:
        pytest.fail(f"Unable to fetch verified zexall.cim automatically: {exc}")

    outdir = tmp_path_factory.mktemp("z80_zexall_runtime") / "generated"
    processor_path, system_path = example_pair("z80")
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    harness_c = outdir / "zexall_harness.c"
    harness_c.write_text(
        """#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "Z80.h"

static int bdos_call(CPUState *cpu, FILE *out) {
    uint8_t fn = cpu->registers[REG_C];
    if (fn == 2) {
        fputc((int)cpu->registers[REG_E], out);
    } else if (fn == 9) {
        uint16_t addr = (uint16_t)(((uint16_t)cpu->registers[REG_D] << 8) | cpu->registers[REG_E]);
        for (;;) {
            uint8_t ch = z80_read_byte(cpu, addr++);
            if (ch == '$') break;
            fputc((int)ch, out);
        }
    }

    /* Return from CALL 0005 (CP/M BDOS) by popping return address. */
    uint8_t lo = z80_read_byte(cpu, cpu->sp);
    cpu->sp = (uint16_t)(cpu->sp + 1);
    uint8_t hi = z80_read_byte(cpu, cpu->sp);
    cpu->sp = (uint16_t)(cpu->sp + 1);
    cpu->pc = (uint16_t)(((uint16_t)hi << 8) | lo);
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s <zexall.cim> <out.txt> [max_steps]\\n", argv[0]);
        return 2;
    }
    uint64_t max_steps = 40000000ULL;
    if (argc >= 4) {
        max_steps = strtoull(argv[3], NULL, 10);
        if (max_steps == 0ULL) max_steps = 1ULL;
    }

    CPUState *cpu = z80_create(65536);
    if (!cpu) return 3;
    if (z80_load_rom(cpu, argv[1], 0x0100) != 0) {
        z80_destroy(cpu);
        return 4;
    }

    /* CP/M ABI setup expected by zexall. */
    z80_write_byte(cpu, 0x0006, 0x00);
    z80_write_byte(cpu, 0x0007, 0xF0); /* initial SP=0xF000 from (0006) */
    cpu->pc = 0x0100;
    cpu->sp = 0xF000;
    cpu->running = 1;

    FILE *out = fopen(argv[2], "wb");
    if (!out) {
        z80_destroy(cpu);
        return 5;
    }

    int rc = 0;
    for (uint64_t step = 0; step < max_steps; ++step) {
        if (cpu->pc == 0x0000) {
            rc = 0; /* Warm boot after "Tests complete". */
            break;
        }
        if (cpu->pc == 0x0005) {
            if (bdos_call(cpu, out) != 0) {
                rc = 6;
                break;
            }
            continue;
        }
        int step_rc = z80_step(cpu);
        if (step_rc != 0) {
            rc = 7;
            break;
        }
        if (!cpu->running) {
            rc = 8;
            break;
        }
        if (step + 1 == max_steps) {
            rc = 9;
            break;
        }
    }

    fflush(out);
    fclose(out);
    z80_destroy(cpu);
    return rc;
}
""",
        encoding="utf-8",
    )

    binary_name = "zexall_harness.exe" if os.name == "nt" else "zexall_harness"
    binary = outdir / binary_name
    subprocess.check_call(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-D_POSIX_C_SOURCE=199309L",
            "-I",
            str(outdir / "src"),
            str(outdir / "src" / "Z80.c"),
            str(outdir / "src" / "Z80_decoder.c"),
            str(harness_c),
            "-o",
            str(binary),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    assert binary.exists(), f"Expected ZEXALL harness binary: {binary}"
    return binary, zexall


def test_z80_runs_zexall_clean(z80_zexall_harness, tmp_path):
    harness, zexall = z80_zexall_harness
    output = tmp_path / "zexall_output.txt"
    max_steps = _zexall_max_steps()

    proc = subprocess.run(
        [str(harness), str(zexall), str(output), str(max_steps)],
        check=False,
        capture_output=True,
        text=True,
    )
    text = output.read_text(encoding="latin-1", errors="replace")
    if proc.returncode != 0:
        raise AssertionError(
            f"zexall harness exited rc={proc.returncode} (max_steps={max_steps}).\n"
            f"--- zexall output (tail) ---\n{text[-2000:]}"
        )
    assert "Z80all instruction exerciser" in text
    assert "Tests complete" in text
    assert "ERROR" not in text
    assert "OK" in text
