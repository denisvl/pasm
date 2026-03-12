
#include <stdio.h>
#include <stdint.h>
#include "Z80_decoder.h"

static void dump_missing(uint8_t pref, const char *name) {
    printf("%s missing:", name);
    for (int op = 0; op < 256; op++) {
        uint32_t raw = (uint32_t)op;
        DecodedInstruction inst = z80_decode(raw, pref, 0);
        if (!inst.valid) printf(" %02X", op);
    }
    printf("\n");
}

int main(void) {
    dump_missing(0xDD, "dd");
    dump_missing(0xFD, "fd");
    return 0;
}
