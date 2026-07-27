#include <stdio.h>
#include <stdint.h>
#include "MC6809.h"

int main(void) {
    CPUState *cpu = mc6809_create(65536);
    if (!cpu) return 1;
    if (mc6809_load_system_roms(cpu, "examples/systems/coco1") != 0) return 2;
    if (mc6809_load_keyboard_map(cpu, "examples/hosts/coco1/host_keyboard_coco.yaml") != 0) return 3;
    if (mc6809_load_cartridge_rom(cpu, "examples/roms/coco1/disk11.rom") != 0) return 4;
    if (mc6809_load_floppy_media(cpu, "examples/floppies/coco1/BANDIT.DSK") != 0) return 5;
    mc6809_reset(cpu);
    mc6809_run_until(cpu, 5000000u);
    printf("PC=%04X SP=%04X A=%02X B=%02X X=%04X Y=%04X U=%04X\n",
           cpu->pc, cpu->sp, cpu->registers[0], cpu->registers[1], cpu->x, cpu->y, cpu->u);
    for (uint16_t addr = 0x007C; addr < 0x00A8; addr += 2u) {
        printf("RAM %04X: %02X %02X\n", addr, mc6809_read_byte(cpu, addr), mc6809_read_byte(cpu, (uint16_t)(addr + 1u)));
    }
    for (uint16_t addr = cpu->sp; addr < (uint16_t)(cpu->sp + 16u); addr += 2u) {
        printf("STK %04X: %02X %02X\n", addr, mc6809_read_byte(cpu, addr), mc6809_read_byte(cpu, (uint16_t)(addr + 1u)));
    }
    for (uint16_t addr = (uint16_t)(cpu->pc - 24u); addr < (uint16_t)(cpu->pc + 48u); ) {
        uint32_t raw = 0u;
        for (uint16_t i = 0; i < 4u; ++i) {
            raw |= ((uint32_t)mc6809_read_byte(cpu, (uint16_t)(addr + i))) << (8u * i);
        }
        uint8_t b0 = (uint8_t)(raw & 0xFFu);
        uint8_t prefix = 0u;
        uint32_t decode_raw = raw;
        if (b0 == 0x10u || b0 == 0x11u) {
            prefix = b0;
            decode_raw = raw >> 8;
        }
        const char *text = mc6809_disassemble_instruction(addr, raw);
        DecodedInstruction inst = mc6809_decode(decode_raw, prefix, addr);
        uint8_t len = inst.valid && inst.length != 0u ? inst.length : 1u;
        printf("%s%04X: ", addr == cpu->pc ? ">>" : "  ", addr);
        for (uint8_t i = 0; i < len; ++i) {
            printf("%02X ", mc6809_read_byte(cpu, (uint16_t)(addr + i)));
        }
        for (uint8_t i = len; i < 5u; ++i) printf("   ");
        printf("%s\n", text);
        addr = (uint16_t)(addr + len);
    }
    mc6809_destroy(cpu);
    return 0;
}
