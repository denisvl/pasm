#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../generated/_apple1_check/src/MOS6502_debug_abi.h"

static void dump_text(CPUState *cpu, uint16_t base, size_t count) {
    uint8_t buf[128];
    if (count > sizeof(buf)) count = sizeof(buf);
    memset(buf, 0, sizeof(buf));
    if (pasm_dbg_read_memory(cpu, base, buf, count) != 0) {
        printf("read_memory failed at %04X\n", base);
        return;
    }
    printf("text[%04X]:", base);
    for (size_t i = 0; i < count; ++i) {
        printf(" %02X", buf[i]);
    }
    printf("  |");
    for (size_t i = 0; i < count; ++i) {
        uint8_t ch = buf[i];
        putchar((ch >= 0x20 && ch <= 0x7e) ? (int)ch : '.');
    }
    printf("|\n");
}

int main(void) {
    CPUState *cpu = pasm_dbg_create(65536);
    if (cpu == NULL) {
        fprintf(stderr, "create failed\n");
        return 1;
    }
    if (pasm_dbg_load_system_roms(cpu, "examples/systems/apple1") != 0) {
        fprintf(stderr, "load_system_roms failed\n");
        pasm_dbg_destroy(cpu);
        return 2;
    }
    pasm_dbg_reset(cpu);

    for (int i = 0; i < 64; ++i) {
        PASMDebugSnapshotCore core;
        memset(&core, 0, sizeof(core));
        if (pasm_dbg_snapshot_fill(
                cpu,
                &core,
                NULL, 0,
                NULL, 0,
                NULL, 0,
                NULL, 0,
                NULL, 0,
                NULL, 0,
                NULL, 0,
                NULL, 0,
                NULL, 0,
                NULL, 0,
                NULL, 0) != 0) {
            fprintf(stderr, "snapshot failed\n");
            pasm_dbg_destroy(cpu);
            return 3;
        }
        printf("%02d PC=%04" PRIX64 " cycles=%" PRIu64 " dsp=%02X cur=(%u,%u) frame=%u\n",
               i,
               core.pc,
               core.total_cycles,
               cpu->comp_apple1_pia_6820.prb & 0x7f,
               (unsigned)cpu->comp_apple1_video.cursor_x,
               (unsigned)cpu->comp_apple1_video.cursor_y,
               (unsigned)cpu->comp_apple1_video.frame_count);
        if (pasm_dbg_step_into(cpu) != 0) {
            fprintf(stderr, "step failed\n");
            pasm_dbg_destroy(cpu);
            return 4;
        }
    }

    dump_text(cpu, 0xD000, 64);

    {
        PASMDebugFramebuffer fb;
        memset(&fb, 0, sizeof(fb));
        if (pasm_dbg_capture_framebuffer(cpu, &fb) == 0 && fb.pixels != NULL && fb.pixel_size >= 16) {
            const uint32_t *px = (const uint32_t *)fb.pixels;
            printf("fb %ux%u frame=%" PRIu64 " pixels=%08X %08X %08X %08X\n",
                   fb.width, fb.height, fb.frame_number, px[0], px[1], px[2], px[3]);
            pasm_dbg_release_framebuffer(cpu, &fb);
        } else {
            printf("framebuffer capture unavailable\n");
        }
    }

    pasm_dbg_destroy(cpu);
    return 0;
}
