import json
import os
import pathlib
import shutil
import subprocess
import textwrap
import uuid

import pytest

from src import generator as gen_mod
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
REFERENCE_PATH = BASE_DIR / "tests" / "data" / "mc6809_cycle_reference.json"


def _make_workdir(prefix: str) -> pathlib.Path:
    root = BASE_DIR / "generated" / "_pytest_work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


def _scan_decode_cycles() -> dict[str, list[int]]:
    processor_path, system_path = example_pair("mc6809")
    outdir = _make_workdir("mc6809_cycle_scan_")
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    scan_c = outdir / "scan_cycles.c"
    scan_c.write_text(
        textwrap.dedent(
            """
            #include <stdio.h>
            #include <stdint.h>
            #include "MC6809_decoder.h"

            static void dump_space(const char *name, uint8_t prefix) {
                printf("%s=", name);
                for (int op = 0; op < 256; op++) {
                    uint32_t raw = (uint32_t)op;
                    DecodedInstruction inst = mc6809_decode(raw, prefix, 0);
                    printf("%u", (unsigned int)inst.cycles);
                    if (op != 255) putchar(',');
                }
                putchar('\\n');
            }

            int main(void) {
                dump_space("base", 0x00);
                dump_space("p10", 0x10);
                dump_space("p11", 0x11);
                return 0;
            }
            """
        ),
        encoding="utf-8",
    )

    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        pytest.skip("No C compiler available on PATH")

    binary_name = "scan_cycles.exe" if os.name == "nt" else "scan_cycles"
    binary = outdir / binary_name
    subprocess.check_call(
        [
            compiler,
            "-std=c11",
            "-O2",
            "-I",
            str(outdir / "src"),
            str(outdir / "src" / "MC6809_decoder.c"),
            str(scan_c),
            "-o",
            str(binary),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    proc = subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    scanned: dict[str, list[int]] = {}
    for line in proc.stdout.strip().splitlines():
        name, values = line.split("=", 1)
        scanned[name] = [int(x) for x in values.split(",")]
    return scanned


@pytest.mark.skipif(
    (shutil.which("cc") is None and shutil.which("gcc") is None and shutil.which("clang") is None),
    reason="C compiler not available on PATH",
)
def test_mc6809_decode_cycles_match_reference_table():
    scanned = _scan_decode_cycles()

    if os.environ.get("PASM_REGENERATE_MC6809_CYCLE_REFERENCE", "").lower() in {"1", "true", "yes", "on"}:
        REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        REFERENCE_PATH.write_text(json.dumps(scanned, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pytest.fail(f"Regenerated cycle reference at {REFERENCE_PATH}; re-run tests without regeneration enabled.")

    assert REFERENCE_PATH.exists(), (
        f"Missing cycle reference file: {REFERENCE_PATH}. "
        "Generate it with PASM_REGENERATE_MC6809_CYCLE_REFERENCE=1."
    )
    expected = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    assert scanned == expected
