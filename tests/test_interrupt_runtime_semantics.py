import os
import pathlib
import shutil
import subprocess

import pytest

from src import generator as gen_mod
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _parse_kv(stdout: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


@pytest.fixture(scope="module")
def z80_interrupt_harness(tmp_path_factory):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("No C compiler available on PATH")

    outdir = tmp_path_factory.mktemp("z80_interrupt_runtime") / "generated"
    processor_path, system_path = example_pair("z80")
    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    harness_c = outdir / "interrupt_harness.c"
    harness_c.write_text(
        """#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "Z80.h"

static int run_case(const char *mode) {
    CPUState *cpu = z80_create(65536);
    if (!cpu) return 2;

    cpu->pc = 0x1234;
    cpu->sp = 0x2000;

    if (strcmp(mode, "im1") == 0) {
        z80_set_interrupt_mode(cpu, 1);
        z80_set_irq(cpu, true);
        z80_interrupt(cpu, 0xAA);
    } else if (strcmp(mode, "im0_rst") == 0) {
        z80_set_interrupt_mode(cpu, 0);
        z80_set_irq(cpu, true);
        z80_interrupt(cpu, 0xEF);
    } else if (strcmp(mode, "im0_fallback") == 0) {
        z80_set_interrupt_mode(cpu, 0);
        z80_set_irq(cpu, true);
        z80_interrupt(cpu, 0x12);
    } else if (strcmp(mode, "im2") == 0) {
        cpu->pc = 0x2222;
        cpu->sp = 0x3000;
        cpu->registers[REG_I] = 0x40;
        z80_write_byte(cpu, 0x4010, 0x78);
        z80_write_byte(cpu, 0x4011, 0x56);
        z80_set_interrupt_mode(cpu, 2);
        z80_set_irq(cpu, true);
        z80_interrupt(cpu, 0x10);
    } else if (strcmp(mode, "retn") == 0) {
        cpu->pc = 0x0100;
        cpu->sp = 0x2200;
        z80_write_byte(cpu, 0x0100, 0xED);
        z80_write_byte(cpu, 0x0101, 0x45);
        z80_write_byte(cpu, 0x2200, 0x34);
        z80_write_byte(cpu, 0x2201, 0x12);
        z80_set_irq(cpu, false);
    } else if (strcmp(mode, "reti") == 0) {
        cpu->pc = 0x0110;
        cpu->sp = 0x2210;
        z80_write_byte(cpu, 0x0110, 0xED);
        z80_write_byte(cpu, 0x0111, 0x4D);
        z80_write_byte(cpu, 0x2210, 0x78);
        z80_write_byte(cpu, 0x2211, 0x56);
        z80_set_irq(cpu, false);
    } else if (strcmp(mode, "di") == 0) {
        cpu->pc = 0x0120;
        z80_write_byte(cpu, 0x0120, 0xF3);
        z80_set_irq(cpu, true);
    } else if (strcmp(mode, "ei") == 0) {
        cpu->pc = 0x0130;
        z80_write_byte(cpu, 0x0130, 0xFB);
        z80_set_irq(cpu, false);
    } else if (strcmp(mode, "im0_insn") == 0) {
        cpu->pc = 0x0140;
        z80_write_byte(cpu, 0x0140, 0xED);
        z80_write_byte(cpu, 0x0141, 0x46);
        z80_set_interrupt_mode(cpu, 1);
    } else if (strcmp(mode, "im1_insn") == 0) {
        cpu->pc = 0x0150;
        z80_write_byte(cpu, 0x0150, 0xED);
        z80_write_byte(cpu, 0x0151, 0x56);
        z80_set_interrupt_mode(cpu, 0);
    } else if (strcmp(mode, "im2_insn") == 0) {
        cpu->pc = 0x0160;
        z80_write_byte(cpu, 0x0160, 0xED);
        z80_write_byte(cpu, 0x0161, 0x5E);
        z80_set_interrupt_mode(cpu, 1);
    } else if (strcmp(mode, "halt_no_irq") == 0) {
        cpu->pc = 0x0170;
        z80_write_byte(cpu, 0x0170, 0x76);
    } else if (strcmp(mode, "halt_irq_resume") == 0) {
        cpu->pc = 0x0180;
        cpu->sp = 0x2400;
        cpu->halted = true;
        z80_set_interrupt_mode(cpu, 1);
        z80_set_irq(cpu, true);
        z80_interrupt(cpu, 0xAA);
    } else {
        z80_destroy(cpu);
        return 3;
    }

    int rc = z80_step(cpu);
    printf("rc=%d\\n", rc);
    printf("pc=%04X\\n", cpu->pc);
    printf("sp=%04X\\n", cpu->sp);
    printf("cycles=%llu\\n", (unsigned long long)cpu->total_cycles);
    printf("pending=%d\\n", cpu->interrupt_pending ? 1 : 0);
    printf("irq=%d\\n", cpu->interrupts_enabled ? 1 : 0);
    printf("halted=%d\\n", cpu->halted ? 1 : 0);
    printf("mode=%u\\n", (unsigned int)cpu->interrupt_mode);
    printf("stack_lo=%02X\\n", z80_read_byte(cpu, cpu->sp));
    printf("stack_hi=%02X\\n", z80_read_byte(cpu, (uint16_t)(cpu->sp + 1)));

    z80_destroy(cpu);
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2) return 1;
    return run_case(argv[1]);
}
""",
        encoding="utf-8",
    )

    binary_name = "interrupt_harness.exe" if os.name == "nt" else "interrupt_harness"
    binary = outdir / binary_name

    subprocess.check_call(
        [
            compiler,
            "-std=c11",
            "-O2",
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
    assert binary.exists(), f"Expected interrupt harness binary: {binary}"
    return binary


def _run_interrupt_case(binary: pathlib.Path, mode: str) -> dict[str, str]:
    proc = subprocess.run(
        [str(binary), mode],
        check=True,
        capture_output=True,
        text=True,
    )
    return _parse_kv(proc.stdout)


def test_im1_interrupt_runtime_semantics(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "im1")
    assert out["rc"] == "0"
    assert out["pc"] == "0038"
    assert out["sp"] == "1FFE"
    assert out["cycles"] == "13"
    assert out["pending"] == "0"
    assert out["irq"] == "0"
    assert out["stack_lo"] == "34"
    assert out["stack_hi"] == "12"


def test_im0_rst_vector_runtime_semantics(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "im0_rst")
    assert out["rc"] == "0"
    assert out["pc"] == "0028"
    assert out["sp"] == "1FFE"
    assert out["cycles"] == "13"
    assert out["stack_lo"] == "34"
    assert out["stack_hi"] == "12"


def test_im0_fallback_vector_runtime_semantics(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "im0_fallback")
    assert out["rc"] == "0"
    assert out["pc"] == "0038"
    assert out["sp"] == "1FFE"
    assert out["cycles"] == "13"
    assert out["stack_lo"] == "34"
    assert out["stack_hi"] == "12"


def test_im2_vector_table_runtime_semantics(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "im2")
    assert out["rc"] == "0"
    assert out["pc"] == "5678"
    assert out["sp"] == "2FFE"
    assert out["cycles"] == "19"
    assert out["pending"] == "0"
    assert out["irq"] == "0"
    assert out["stack_lo"] == "22"
    assert out["stack_hi"] == "22"


def test_retn_pops_pc_and_reenables_irq(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "retn")
    assert out["rc"] == "0"
    assert out["pc"] == "1234"
    assert out["sp"] == "2202"
    assert out["cycles"] == "14"
    assert out["irq"] == "1"
    assert out["pending"] == "0"


def test_reti_pops_pc_and_reenables_irq(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "reti")
    assert out["rc"] == "0"
    assert out["pc"] == "5678"
    assert out["sp"] == "2212"
    assert out["cycles"] == "14"
    assert out["irq"] == "1"
    assert out["pending"] == "0"


def test_di_disables_irq(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "di")
    assert out["rc"] == "0"
    assert out["pc"] == "0121"
    assert out["cycles"] == "4"
    assert out["irq"] == "0"


def test_ei_enables_irq(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "ei")
    assert out["rc"] == "0"
    assert out["pc"] == "0131"
    assert out["cycles"] == "4"
    assert out["irq"] == "1"


def test_im0_instruction_sets_mode_zero(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "im0_insn")
    assert out["rc"] == "0"
    assert out["pc"] == "0142"
    assert out["cycles"] == "8"
    assert out["mode"] == "0"


def test_im1_instruction_sets_mode_one(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "im1_insn")
    assert out["rc"] == "0"
    assert out["pc"] == "0152"
    assert out["cycles"] == "8"
    assert out["mode"] == "1"


def test_im2_instruction_sets_mode_two(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "im2_insn")
    assert out["rc"] == "0"
    assert out["pc"] == "0162"
    assert out["cycles"] == "8"
    assert out["mode"] == "2"


def test_halt_without_irq_sets_halted_state(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "halt_no_irq")
    assert out["rc"] == "0"
    assert out["pc"] == "0171"
    assert out["cycles"] == "4"
    assert out["halted"] == "1"
    assert out["irq"] == "0"


def test_pending_irq_resumes_from_halt_and_vectors(z80_interrupt_harness):
    out = _run_interrupt_case(z80_interrupt_harness, "halt_irq_resume")
    assert out["rc"] == "0"
    assert out["pc"] == "0038"
    assert out["sp"] == "23FE"
    assert out["cycles"] == "13"
    assert out["halted"] == "0"
    assert out["pending"] == "0"
    assert out["irq"] == "0"
    assert out["stack_lo"] == "80"
    assert out["stack_hi"] == "01"
