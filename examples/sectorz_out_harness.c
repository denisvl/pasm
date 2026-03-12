#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "Z80.h"
#include "Z80_hooks.h"

enum {
    OUT_PORT = 0x10,
    MAX_CAPTURE = 1024
};

typedef struct {
    uint8_t bytes[MAX_CAPTURE];
    int count;
    bool done;
} OutputCapture;

static void on_hook(CPUState *cpu, const CPUHookEvent *event, void *context) {
    (void)cpu;
    OutputCapture *out = (OutputCapture *)context;

    if (event->type != HOOK_PORT_WRITE_POST || event->port != OUT_PORT || out->count >= MAX_CAPTURE) {
        return;
    }

    out->bytes[out->count++] = event->value;
    putc((char)event->value, stdout);
    fflush(stdout);
    if (event->value == 0) {
        out->done = true;
    }
}

int main(int argc, char **argv) {
    if (argc < 2 || argc > 3) {
        fprintf(stderr, "Usage: %s <rom_file> [max_steps]\n", argv[0]);
        return 2;
    }

    const char *rom = argv[1];
    long max_steps = 200000;
    if (argc == 3) {
        max_steps = strtol(argv[2], NULL, 0);
        if (max_steps <= 0) {
            fprintf(stderr, "Invalid max_steps: %s\n", argv[2]);
            return 2;
        }
    }

    CPUState *cpu = z80_create(65536);
    if (!cpu) {
        fprintf(stderr, "Failed to create CPU\n");
        return 3;
    }

    OutputCapture out = {0};
    z80_hook_set(cpu, HOOK_PORT_WRITE_POST, on_hook, &out);
    z80_hook_enable(cpu, HOOK_PORT_WRITE_POST, true);

    if (z80_load_rom(cpu, rom, 0) != 0) {
        fprintf(stderr, "Failed to load ROM: %s\n", rom);
        z80_destroy(cpu);
        return 4;
    }

    for (long i = 0; i < max_steps; i++) {
        if (z80_step(cpu) != 0) {
            break;
        }
        if (out.done) {
            break;
        }
    }

    printf("\nCOUNT=%d\n", out.count);
    printf("HEX=");
    for (int i = 0; i < out.count; i++) {
        printf("%02X", out.bytes[i]);
        if (i + 1 < out.count) {
            putc(' ', stdout);
        }
    }
    putc('\n', stdout);
    printf("CYCLES=%llu\n", (unsigned long long)cpu->total_cycles);

    z80_destroy(cpu);
    return 0;
}
