import json
import os
import pathlib
import shutil
import subprocess
import textwrap

import pytest

from src import generator as gen_mod


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
REFERENCE_PATH = BASE_DIR / "tests" / "data" / "z80_cycle_reference.json"


def _scan_decode_cycles(tmp_path: pathlib.Path) -> dict[str, list[int]]:
    isa_path = BASE_DIR / "examples" / "z80.yaml"
    outdir = tmp_path / "z80_cycle_scan"
    gen_mod.generate(str(isa_path), str(outdir))

    scan_c = outdir / "scan_cycles.c"
    scan_c.write_text(
        textwrap.dedent(
            """
            #include <stdio.h>
            #include <stdint.h>
            #include "Z80_decoder.h"

            static void dump_space(const char *name, uint8_t prefix, int mode) {
                printf("%s=", name);
                for (int op = 0; op < 256; op++) {
                    uint32_t raw = 0;
                    switch (mode) {
                        case 0: raw = (uint32_t)op; break;                          /* base, dd, fd */
                        case 1: raw = 0xCBu | ((uint32_t)op << 8); break;            /* cb */
                        case 2: raw = 0xEDu | ((uint32_t)op << 8); break;            /* ed */
                        case 3: raw = 0xCBu | ((uint32_t)op << 16); break;           /* ddcb, fdcb */
                        default: raw = 0; break;
                    }
                    DecodedInstruction inst = z80_decode(raw, prefix, 0);
                    printf("%u", (unsigned int)inst.cycles);
                    if (op != 255) putchar(',');
                }
                putchar('\\n');
            }

            int main(void) {
                dump_space("base", 0x00, 0);
                dump_space("cb", 0x00, 1);
                dump_space("ed", 0x00, 2);
                dump_space("dd", 0xDD, 0);
                dump_space("fd", 0xFD, 0);
                dump_space("ddcb", 0xDD, 3);
                dump_space("fdcb", 0xFD, 3);
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
            str(outdir / "src" / "Z80_decoder.c"),
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
def test_z80_decode_cycles_match_reference_table(tmp_path):
    scanned = _scan_decode_cycles(tmp_path)

    if os.environ.get("PASM_REGENERATE_Z80_CYCLE_REFERENCE", "").lower() in {"1", "true", "yes", "on"}:
        REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        REFERENCE_PATH.write_text(json.dumps(scanned, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pytest.fail(f"Regenerated cycle reference at {REFERENCE_PATH}; re-run tests without regeneration enabled.")

    assert REFERENCE_PATH.exists(), (
        f"Missing cycle reference file: {REFERENCE_PATH}. "
        "Generate it with PASM_REGENERATE_Z80_CYCLE_REFERENCE=1."
    )
    expected = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    assert scanned == expected
