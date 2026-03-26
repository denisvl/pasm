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


def _make_workdir(prefix: str) -> pathlib.Path:
    root = BASE_DIR / ".tmp_test_work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


def _compile_runtime_penalty_harness(outdir: pathlib.Path, cpu_name: str) -> pathlib.Path:
    cpu_upper = cpu_name.upper()
    cpu_prefix = cpu_name.lower()

    harness_c = outdir / "runtime_penalty_harness.c"
    harness_c.write_text(
        textwrap.dedent(
            f"""
            #include <stdint.h>
            #include <stdio.h>
            #include <string.h>
            #include "{cpu_upper}.h"

            typedef struct {{
                const char *name;
                uint16_t pc;
                uint8_t op;
                uint8_t b1;
                uint8_t b2;
                uint8_t x;
                uint8_t y;
                uint8_t flags;
                uint8_t use_ptr;
                uint8_t zp;
                uint8_t ptr_lo;
                uint8_t ptr_hi;
                uint8_t use_mem;
                uint16_t mem_addr;
                uint8_t expected_cycles;
                uint16_t expected_pc;
            }} CycleCase;

            static int run_case(const CycleCase *tc) {{
                CPUState *cpu = {cpu_prefix}_create(65536u);
                if (cpu == NULL) {{
                    fprintf(stderr, "create failed for %s\\n", tc->name);
                    return 1;
                }}

                memset(cpu->memory, 0, cpu->memory_size);
                cpu->pc = tc->pc;
                cpu->registers[REG_X] = tc->x;
                cpu->registers[REG_Y] = tc->y;
                cpu->flags.raw = tc->flags;
                cpu->running = true;
                cpu->halted = false;
                cpu->pc_modified = false;
                cpu->interrupt_pending = false;
                cpu->interrupts_enabled = false;
                cpu->total_cycles = 0u;
                cpu->reset_delay_pending = false;

                cpu->memory[tc->pc] = tc->op;
                cpu->memory[(uint16_t)(tc->pc + 1u)] = tc->b1;
                cpu->memory[(uint16_t)(tc->pc + 2u)] = tc->b2;

                if (tc->use_ptr != 0u) {{
                    cpu->memory[tc->zp] = tc->ptr_lo;
                    cpu->memory[(uint8_t)(tc->zp + 1u)] = tc->ptr_hi;
                }}
                if (tc->use_mem != 0u) {{
                    cpu->memory[tc->mem_addr] = 0x42u;
                }}

                if ({cpu_prefix}_step(cpu) != 0) {{
                    fprintf(stderr, "step failed for %s\\n", tc->name);
                    {cpu_prefix}_destroy(cpu);
                    return 1;
                }}

                {{
                    uint8_t got_cycles = (uint8_t)cpu->total_cycles;
                    uint16_t got_pc = cpu->pc;
                    if (got_cycles != tc->expected_cycles || got_pc != tc->expected_pc) {{
                        fprintf(
                            stderr,
                            "FAIL %s: cycles=%u expected=%u pc=%04X expected=%04X\\n",
                            tc->name,
                            (unsigned int)got_cycles,
                            (unsigned int)tc->expected_cycles,
                            (unsigned int)got_pc,
                            (unsigned int)tc->expected_pc
                        );
                        {cpu_prefix}_destroy(cpu);
                        return 1;
                    }}
                }}

                {cpu_prefix}_destroy(cpu);
                return 0;
            }}

            int main(void) {{
                const CycleCase cases[] = {{
                    /* BNE: not taken = 2 cycles */
                    {{ "bne_not_taken", 0x0200u, 0xD0u, 0x02u, 0x00u, 0u, 0u, 0x02u, 0u, 0u, 0u, 0u, 0u, 0u, 2u, 0x0202u }},
                    /* BNE: taken same page = 3 cycles */
                    {{ "bne_taken_same", 0x0200u, 0xD0u, 0x02u, 0x00u, 0u, 0u, 0x00u, 0u, 0u, 0u, 0u, 0u, 0u, 3u, 0x0204u }},
                    /* BNE: taken with +0 displacement is still taken (3 cycles). */
                    {{ "bne_taken_zero_offset", 0x0200u, 0xD0u, 0x00u, 0x00u, 0u, 0u, 0x00u, 0u, 0u, 0u, 0u, 0u, 0u, 3u, 0x0202u }},
                    /* BNE: taken page cross = 4 cycles */
                    {{ "bne_taken_cross", 0x20FDu, 0xD0u, 0x02u, 0x00u, 0u, 0u, 0x00u, 0u, 0u, 0u, 0u, 0u, 0u, 4u, 0x2101u }},

                    /* LDA abs,X: no page cross = 4 */
                    {{ "lda_absx_no_cross", 0x0300u, 0xBDu, 0x00u, 0x20u, 0x0Fu, 0u, 0x00u, 0u, 0u, 0u, 0u, 1u, 0x200Fu, 4u, 0x0303u }},
                    /* LDA abs,X: page cross = 5 */
                    {{ "lda_absx_cross", 0x0310u, 0xBDu, 0xFFu, 0x20u, 0x01u, 0u, 0x00u, 0u, 0u, 0u, 0u, 1u, 0x2100u, 5u, 0x0313u }},

                    /* LDA abs,Y: page cross = 5 */
                    {{ "lda_absy_cross", 0x0320u, 0xB9u, 0xFFu, 0x20u, 0u, 0x01u, 0x00u, 0u, 0u, 0u, 0u, 1u, 0x2100u, 5u, 0x0323u }},

                    /* LDA (zp),Y: no page cross = 5 */
                    {{ "lda_indy_no_cross", 0x0330u, 0xB1u, 0x10u, 0x00u, 0u, 0x01u, 0x00u, 1u, 0x10u, 0x00u, 0x20u, 1u, 0x2001u, 5u, 0x0332u }},
                    /* LDA (zp),Y: page cross = 6 */
                    {{ "lda_indy_cross", 0x0340u, 0xB1u, 0x10u, 0x00u, 0u, 0x01u, 0x00u, 1u, 0x10u, 0xFFu, 0x20u, 1u, 0x2100u, 6u, 0x0342u }},

                    /* Undocumented NOP abs,X has page-cross penalty too (4*) */
                    {{ "nop_absx_cross", 0x0350u, 0x1Cu, 0xFFu, 0x20u, 0x01u, 0u, 0x00u, 0u, 0u, 0u, 0u, 1u, 0x2100u, 5u, 0x0353u }},
                }};

                size_t count = sizeof(cases) / sizeof(cases[0]);
                for (size_t i = 0; i < count; i++) {{
                    if (run_case(&cases[i]) != 0) return 1;
                }}

                printf("ok cases=%u\\n", (unsigned int)count);
                return 0;
            }}
            """
        ),
        encoding="utf-8",
    )

    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        pytest.skip("No C compiler available on PATH")

    binary_name = f"{cpu_name}_runtime_penalty_harness.exe" if os.name == "nt" else f"{cpu_name}_runtime_penalty_harness"
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
    return binary


@pytest.mark.skipif(
    (shutil.which("cc") is None and shutil.which("gcc") is None and shutil.which("clang") is None),
    reason="C compiler not available on PATH",
)
@pytest.mark.parametrize("cpu_name", ["mos6502", "mos6510", "mos6509"])
def test_mos65xx_runtime_cycle_penalties(cpu_name: str):
    outdir = _make_workdir(f"{cpu_name}_runtime_cycle_penalty_") / "generated"
    processor_path, system_path = example_pair(cpu_name)
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    binary = _compile_runtime_penalty_harness(outdir, cpu_name)
    proc = subprocess.run([str(binary)], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"{cpu_name} runtime penalty harness failed with code {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )
