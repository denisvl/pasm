#include <stdlib.h>

/*
 * SectorZ (z88dk sccz80) sample:
 * - print(char*) sends each byte to OUT port 0x10
 * - includes the terminating NUL byte
 */
void print(char *s) {
    while (1) {
        unsigned char c = (unsigned char)*s++;
        outp(0x10, c);
        if (c == 0) {
            return;
        }
    }
}

int main(void) {
    print("hello world");
#asm
    halt
#endasm
    return 0;
}
