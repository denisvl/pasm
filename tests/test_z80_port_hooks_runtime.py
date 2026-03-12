import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

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
def z80_port_hook_harness(tmp_path_factory):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if not compiler:
        pytest.skip("No C compiler available on PATH")

    workdir = tmp_path_factory.mktemp("z80_port_hook_runtime")
    processor_path, system_path = example_pair("z80")
    processor_data = yaml.safe_load(processor_path.read_text(encoding="utf-8"))
    system_data = yaml.safe_load(system_path.read_text(encoding="utf-8"))
    system_data["hooks"] = {
        "pre_fetch": {"enabled": False},
        "post_decode": {"enabled": False},
        "post_execute": {"enabled": False},
        "port_read_pre": {"enabled": True},
        "port_read_post": {"enabled": True},
        "port_write_pre": {"enabled": True},
        "port_write_post": {"enabled": True},
    }

    test_processor_path = workdir / "z80_processor.yaml"
    test_system_path = workdir / "z80_port_hooks_system.yaml"
    test_processor_path.write_text(
        yaml.safe_dump(processor_data, sort_keys=False), encoding="utf-8"
    )
    test_system_path.write_text(
        yaml.safe_dump(system_data, sort_keys=False), encoding="utf-8"
    )

    outdir = workdir / "generated"
    gen_mod.generate(str(test_processor_path), str(test_system_path), str(outdir))

    harness_c = outdir / "port_hook_harness.c"
    harness_c.write_text(
        """#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "Z80.h"
#include "Z80_hooks.h"

typedef struct {
    unsigned int rp_pre;
    unsigned int rp_post;
    unsigned int wp_pre;
    unsigned int wp_post;
    uint16_t read_port;
    uint16_t write_port;
    uint8_t read_value;
    uint8_t write_value;
} HookStats;

static void on_hook(CPUState *cpu, const CPUHookEvent *event, void *context) {
    HookStats *stats = (HookStats *)context;
    (void)cpu;
    switch (event->type) {
        case HOOK_PORT_READ_PRE:
            stats->rp_pre++;
            stats->read_port = event->port;
            break;
        case HOOK_PORT_READ_POST:
            stats->rp_post++;
            stats->read_port = event->port;
            stats->read_value = event->value;
            break;
        case HOOK_PORT_WRITE_PRE:
            stats->wp_pre++;
            stats->write_port = event->port;
            stats->write_value = event->value;
            break;
        case HOOK_PORT_WRITE_POST:
            stats->wp_post++;
            stats->write_port = event->port;
            stats->write_value = event->value;
            break;
        default:
            break;
    }
}

static void attach_hooks(CPUState *cpu, HookStats *stats) {
    z80_hook_set(cpu, HOOK_PORT_READ_PRE, on_hook, stats);
    z80_hook_set(cpu, HOOK_PORT_READ_POST, on_hook, stats);
    z80_hook_set(cpu, HOOK_PORT_WRITE_PRE, on_hook, stats);
    z80_hook_set(cpu, HOOK_PORT_WRITE_POST, on_hook, stats);
    z80_hook_enable(cpu, HOOK_PORT_READ_PRE, true);
    z80_hook_enable(cpu, HOOK_PORT_READ_POST, true);
    z80_hook_enable(cpu, HOOK_PORT_WRITE_PRE, true);
    z80_hook_enable(cpu, HOOK_PORT_WRITE_POST, true);
}

static int run_case(const char *mode) {
    CPUState *cpu = z80_create(65536);
    HookStats stats = {0};
    int steps = 0;
    if (!cpu) return 2;

    attach_hooks(cpu, &stats);
    cpu->pc = 0x0000;
    cpu->sp = 0xFFFE;

    if (strcmp(mode, "in_out") == 0) {
        z80_write_byte(cpu, 0x0000, 0x3E); /* LD A, n */
        z80_write_byte(cpu, 0x0001, 0x5A);
        z80_write_byte(cpu, 0x0002, 0xD3); /* OUT (n), A */
        z80_write_byte(cpu, 0x0003, 0x10);
        z80_write_byte(cpu, 0x0004, 0xDB); /* IN A, (n) */
        z80_write_byte(cpu, 0x0005, 0x10);
        z80_write_byte(cpu, 0x0006, 0x76); /* HALT */
    } else if (strcmp(mode, "ini") == 0) {
        z80_write_byte(cpu, 0x0000, 0x21); /* LD HL, 0x2000 */
        z80_write_byte(cpu, 0x0001, 0x00);
        z80_write_byte(cpu, 0x0002, 0x20);
        z80_write_byte(cpu, 0x0003, 0x01); /* LD BC, 0x0120 (B=1, C=0x20) */
        z80_write_byte(cpu, 0x0004, 0x20);
        z80_write_byte(cpu, 0x0005, 0x01);
        z80_write_byte(cpu, 0x0006, 0xED); /* INI */
        z80_write_byte(cpu, 0x0007, 0xA2);
        z80_write_byte(cpu, 0x0008, 0x76); /* HALT */
        cpu->port_memory[0x20] = 0xAA;
    } else if (strcmp(mode, "outi") == 0) {
        z80_write_byte(cpu, 0x0000, 0x21); /* LD HL, 0x2001 */
        z80_write_byte(cpu, 0x0001, 0x01);
        z80_write_byte(cpu, 0x0002, 0x20);
        z80_write_byte(cpu, 0x0003, 0x01); /* LD BC, 0x0121 (B=1, C=0x21) */
        z80_write_byte(cpu, 0x0004, 0x21);
        z80_write_byte(cpu, 0x0005, 0x01);
        z80_write_byte(cpu, 0x0006, 0x36); /* LD (HL), n */
        z80_write_byte(cpu, 0x0007, 0x66);
        z80_write_byte(cpu, 0x0008, 0xED); /* OUTI */
        z80_write_byte(cpu, 0x0009, 0xA3);
        z80_write_byte(cpu, 0x000A, 0x76); /* HALT */
    } else {
        z80_destroy(cpu);
        return 3;
    }

    while (cpu->running && !cpu->halted && steps < 64) {
        if (z80_step(cpu) != 0) break;
        steps++;
    }

    printf("rp_pre=%u\\n", stats.rp_pre);
    printf("rp_post=%u\\n", stats.rp_post);
    printf("wp_pre=%u\\n", stats.wp_pre);
    printf("wp_post=%u\\n", stats.wp_post);
    printf("read_port=%u\\n", (unsigned int)stats.read_port);
    printf("write_port=%u\\n", (unsigned int)stats.write_port);
    printf("read_value=%u\\n", (unsigned int)stats.read_value);
    printf("write_value=%u\\n", (unsigned int)stats.write_value);
    printf("A=%u\\n", (unsigned int)cpu->registers[REG_A]);
    printf("mem2000=%u\\n", (unsigned int)z80_read_byte(cpu, 0x2000));
    printf("port21=%u\\n", (unsigned int)cpu->port_memory[0x21]);

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

    binary_name = "port_hook_harness.exe" if os.name == "nt" else "port_hook_harness"
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
            str(outdir / "src" / "Z80_hooks.c"),
            str(harness_c),
            "-o",
            str(binary),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    assert binary.exists(), f"Expected port hook harness binary: {binary}"
    return binary


def _run_case(binary: pathlib.Path, mode: str) -> dict[str, str]:
    proc = subprocess.run(
        [str(binary), mode],
        check=True,
        capture_output=True,
        text=True,
    )
    return _parse_kv(proc.stdout)


def test_port_hooks_fire_for_in_and_out(z80_port_hook_harness):
    out = _run_case(z80_port_hook_harness, "in_out")
    assert out["wp_pre"] == "1"
    assert out["wp_post"] == "1"
    assert out["rp_pre"] == "1"
    assert out["rp_post"] == "1"
    assert out["write_port"] == "16"
    assert out["write_value"] == "90"
    assert out["read_port"] == "16"
    assert out["read_value"] == "90"
    assert out["A"] == "90"


def test_port_hooks_fire_for_ini_block_input(z80_port_hook_harness):
    out = _run_case(z80_port_hook_harness, "ini")
    assert out["rp_pre"] == "1"
    assert out["rp_post"] == "1"
    assert out["wp_pre"] == "0"
    assert out["wp_post"] == "0"
    assert out["read_port"] == "32"
    assert out["read_value"] == "170"
    assert out["mem2000"] == "170"


def test_port_hooks_fire_for_outi_block_output(z80_port_hook_harness):
    out = _run_case(z80_port_hook_harness, "outi")
    assert out["wp_pre"] == "1"
    assert out["wp_post"] == "1"
    assert out["rp_pre"] == "0"
    assert out["rp_post"] == "0"
    assert out["write_port"] == "33"
    assert out["write_value"] == "102"
    assert out["port21"] == "102"
