import hashlib
import os
import pathlib
import shutil
import subprocess
import urllib.request

import pytest

from src import generator as gen_mod
from tests.support import BASE_DIR, example_pair

RUN_ENV = "PASM_RUN_KLAUS65"
MAX_STEPS_ENV = "PASM_KLAUS65_MAX_STEPS"
OFFICIAL_PATH_ENV = "PASM_KLAUS65_OFFICIAL_PATH"
EXTENDED_PATH_ENV = "PASM_KLAUS65_EXTENDED_PATH"

CPU_MATRIX = ["mos6502", "mos6510", "mos6509"]
CPU_UPPER = {
    "mos6502": "MOS6502",
    "mos6510": "MOS6510",
    "mos6509": "MOS6509",
}

KLAUS_SUITES = {
    "official": {
        "filename": "6502_functional_test.bin",
        "sha256": "fa12bfc761e6f9057e4cc01a665a7b800ff01ae91f598af1e39a1201d01953fd",
        "urls": [
            "https://raw.githubusercontent.com/Klaus2m5/6502_65C02_functional_tests/master/bin_files/6502_functional_test.bin",
            "https://github.com/Klaus2m5/6502_65C02_functional_tests/raw/master/bin_files/6502_functional_test.bin",
        ],
        "start_pc": 0x0400,
        "pass_pc": 0x3469,
        "path_env": OFFICIAL_PATH_ENV,
        "expects_pass": True,
    },
    "extended": {
        "filename": "65C02_extended_opcodes_test.bin",
        "sha256": "10a2a07fa240666fa610c46accebe8d42b1000feef3aae619da15a8d152869b2",
        "urls": [
            "https://raw.githubusercontent.com/Klaus2m5/6502_65C02_functional_tests/master/bin_files/65C02_extended_opcodes_test.bin",
            "https://github.com/Klaus2m5/6502_65C02_functional_tests/raw/master/bin_files/65C02_extended_opcodes_test.bin",
        ],
        "start_pc": 0x0400,
        "pass_pc": 0x24F1,
        "path_env": EXTENDED_PATH_ENV,
        "expects_pass": False,
        "expected_loop_pc": 0x0423,
    },
}


def _want_run_klaus65() -> bool:
    return os.environ.get(RUN_ENV, "").lower() in {"1", "true", "yes", "on"}


def _klaus65_max_steps() -> int:
    raw = os.environ.get(MAX_STEPS_ENV, "").strip()
    if not raw:
        return 600_000_000
    try:
        value = int(raw, 10)
    except ValueError as exc:
        raise RuntimeError(f"invalid {MAX_STEPS_ENV}={raw!r}") from exc
    if value <= 0:
        raise RuntimeError(f"{MAX_STEPS_ENV} must be > 0, got {value}")
    return value


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: pathlib.Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _validate_suite_rom(path: pathlib.Path, expected_sha: str, source_name: str) -> pathlib.Path:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"{source_name}: missing ROM file at {path}")
    got = _sha256_file(path)
    if got != expected_sha:
        raise RuntimeError(
            f"{source_name}: sha256 mismatch for {path} (expected {expected_sha}, got {got})"
        )
    return path


def _download_suite_bytes(urls: list[str], expected_sha: str, suite_name: str) -> bytes:
    errors: list[str] = []
    request_headers = {"User-Agent": "pasm-klaus65-test/1.0"}
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                payload = response.read()
            if not payload:
                errors.append(f"{url}: empty payload")
                continue
            got = _sha256_bytes(payload)
            if got != expected_sha:
                errors.append(f"{url}: sha256 mismatch (expected {expected_sha}, got {got})")
                continue
            return payload
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError(f"unable to download {suite_name} ROM; " + " | ".join(errors))


def _ensure_klaus_rom(suite_name: str) -> pathlib.Path:
    suite = KLAUS_SUITES[suite_name]
    env_name = suite["path_env"]
    env_path = os.environ.get(env_name, "").strip()
    if env_path:
        candidate = pathlib.Path(env_path).expanduser().resolve()
        return _validate_suite_rom(candidate, suite["sha256"], env_name)

    cache_dir = BASE_DIR / "tests" / "data" / "6502"
    cache_dir.mkdir(parents=True, exist_ok=True)
    rom_path = cache_dir / suite["filename"]

    if rom_path.exists():
        try:
            return _validate_suite_rom(rom_path, suite["sha256"], f"cache:{suite_name}")
        except RuntimeError:
            rom_path.unlink()

    payload = _download_suite_bytes(suite["urls"], suite["sha256"], suite_name)
    tmp_path = rom_path.with_suffix(".tmp")
    tmp_path.write_bytes(payload)
    tmp_path.replace(rom_path)
    return rom_path


def _harness_source(cpu: str) -> str:
    cpu_upper = CPU_UPPER[cpu]
    return f"""#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "{cpu_upper}.h"

int main(int argc, char **argv) {{
    if (argc < 5) {{
        fprintf(stderr, "usage: %s <rom.bin> <start_pc_hex> <pass_pc_hex> <max_steps>\\n", argv[0]);
        return 2;
    }}

    const char *rom_path = argv[1];
    uint32_t start_pc = (uint32_t)strtoul(argv[2], NULL, 16);
    uint32_t pass_pc = (uint32_t)strtoul(argv[3], NULL, 16);
    uint64_t max_steps = strtoull(argv[4], NULL, 10);
    if (max_steps == 0ULL) max_steps = 1ULL;

    CPUState *cpu = {cpu}_create(65536);
    if (!cpu) return 3;

    if ({cpu}_load_rom(cpu, rom_path, 0x0000) != 0) {{
        {cpu}_destroy(cpu);
        return 4;
    }}

    cpu->pc = (uint16_t)start_pc;
    cpu->running = 1;

    uint16_t last_pc = cpu->pc;
    uint16_t loop_pc = 0;
    uint32_t same_pc_count = 0;
    uint64_t steps = 0ULL;
    int step_rc = 0;
    int status = 0;

    for (steps = 0ULL; steps < max_steps; ++steps) {{
        if ((uint16_t)pass_pc == cpu->pc) {{
            status = 0;
            break;
        }}

        step_rc = {cpu}_step(cpu);
        if (step_rc != 0) {{
            status = 5;
            break;
        }}
        if (!cpu->running) {{
            status = 6;
            break;
        }}

        if (cpu->pc == last_pc) {{
            same_pc_count += 1U;
        }} else {{
            same_pc_count = 0U;
            last_pc = cpu->pc;
        }}

        if (same_pc_count >= 2048U) {{
            loop_pc = cpu->pc;
            status = 7;
            break;
        }}
    }}

    if (steps >= max_steps) {{
        status = 8;
    }}

    printf(
        "status=%d steps=%" PRIu64 " pc=0x%04X sp=0x%02X p=0x%02X a=0x%02X x=0x%02X y=0x%02X loop_pc=0x%04X step_rc=%d\\n",
        status,
        steps,
        cpu->pc,
        cpu->sp,
        cpu->flags.raw,
        cpu->registers[REG_A],
        cpu->registers[REG_X],
        cpu->registers[REG_Y],
        loop_pc,
        step_rc
    );

    {cpu}_destroy(cpu);
    return status;
}}
"""


@pytest.fixture(scope="module")
def klaus65_runtime_assets(tmp_path_factory):
    if not _want_run_klaus65():
        pytest.skip(f"Set {RUN_ENV}=1 to run the long Klaus 65xx integration test")

    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("No C compiler available on PATH")
    if not shutil.which("cmake"):
        pytest.skip("cmake not available on PATH")

    try:
        suite_roms = {name: _ensure_klaus_rom(name) for name in KLAUS_SUITES}
    except Exception as exc:
        pytest.fail(f"Unable to fetch/verify Klaus ROMs automatically: {exc}")

    harnesses: dict[str, pathlib.Path] = {}
    for cpu in CPU_MATRIX:
        outdir = tmp_path_factory.mktemp(f"{cpu}_klaus65") / "generated"
        processor_path, system_path = example_pair(cpu)
        gen_mod.generate(str(processor_path), str(system_path), str(outdir))

        cpu_upper = CPU_UPPER[cpu]
        harness_c = outdir / "klaus65_harness.c"
        harness_c.write_text(_harness_source(cpu), encoding="utf-8")

        binary_name = f"{cpu}_klaus65_harness.exe" if os.name == "nt" else f"{cpu}_klaus65_harness"
        binary = outdir / binary_name
        subprocess.check_call(
            [
                compiler,
                "-std=c11",
                "-O2",
                "-D_POSIX_C_SOURCE=199309L",
                "-I",
                str(outdir / "src"),
                str(outdir / "src" / f"{cpu_upper}.c"),
                str(outdir / "src" / f"{cpu_upper}_decoder.c"),
                str(harness_c),
                "-o",
                str(binary),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        assert binary.exists(), f"Expected Klaus harness binary: {binary}"
        harnesses[cpu] = binary

    return harnesses, suite_roms


@pytest.mark.parametrize("suite_name", ["official", "extended"])
@pytest.mark.parametrize("cpu", CPU_MATRIX)
def test_mos65xx_runs_klaus_suite(klaus65_runtime_assets, cpu: str, suite_name: str):
    harnesses, suite_roms = klaus65_runtime_assets
    suite = KLAUS_SUITES[suite_name]
    max_steps = _klaus65_max_steps()

    proc = subprocess.run(
        [
            str(harnesses[cpu]),
            str(suite_roms[suite_name]),
            f"{suite['start_pc']:04x}",
            f"{suite['pass_pc']:04x}",
            str(max_steps),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if suite["expects_pass"]:
        if proc.returncode != 0:
            raise AssertionError(
                f"Klaus run failed for cpu={cpu} suite={suite_name} rc={proc.returncode} max_steps={max_steps}.\n"
                f"stdout: {proc.stdout.strip()}\n"
                f"stderr: {proc.stderr.strip()}"
            )
        return

    if proc.returncode == 0:
        raise AssertionError(
            f"Klaus suite unexpectedly passed for cpu={cpu} suite={suite_name}.\n"
            f"stdout: {proc.stdout.strip()}\n"
            f"stderr: {proc.stderr.strip()}"
        )

    expected_loop = f"loop_pc=0x{suite['expected_loop_pc']:04X}"
    if expected_loop not in proc.stdout:
        raise AssertionError(
            f"Klaus incompatible-suite trap mismatch for cpu={cpu} suite={suite_name}.\n"
            f"expected {expected_loop}\n"
            f"stdout: {proc.stdout.strip()}\n"
            f"stderr: {proc.stderr.strip()}"
        )


def test_klaus65_bad_hash_reports_expected_and_actual(tmp_path):
    bad_rom = tmp_path / "bad.bin"
    bad_rom.write_bytes(b"not-a-real-klaus-rom")

    with pytest.raises(RuntimeError) as excinfo:
        _validate_suite_rom(
            bad_rom,
            "0000000000000000000000000000000000000000000000000000000000000000",
            "unit-test",
        )

    msg = str(excinfo.value)
    assert "expected" in msg
    assert "got" in msg
