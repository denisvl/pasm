
#include <stdio.h>
#include <stdint.h>
#include "Z80_decoder.h"

static int count_base(void){int ok=0;for(int op=0;op<256;op++){if(z80_decode((uint32_t)op,0,0).valid)ok++;}return ok;}
static int count_cb(void){int ok=0;for(int op=0;op<256;op++){uint32_t raw=0xCBu|((uint32_t)op<<8);if(z80_decode(raw,0,0).valid)ok++;}return ok;}
static int count_ed(void){int ok=0;for(int op=0;op<256;op++){uint32_t raw=0xEDu|((uint32_t)op<<8);if(z80_decode(raw,0,0).valid)ok++;}return ok;}
static int count_pref(uint8_t pref){int ok=0;for(int op=0;op<256;op++){if(z80_decode((uint32_t)op,pref,0).valid)ok++;}return ok;}
static int count_ddcb(uint8_t pref){int ok=0;for(int op=0;op<256;op++){uint32_t raw=0xCBu|((uint32_t)op<<16);if(z80_decode(raw,pref,0).valid)ok++;}return ok;}
int main(void){
  printf("base=%d
",count_base());
  printf("cb=%d
",count_cb());
  printf("ed=%d
",count_ed());
  printf("dd=%d
",count_pref(0xDD));
  printf("fd=%d
",count_pref(0xFD));
  printf("ddcb=%d
",count_ddcb(0xDD));
  printf("fdcb=%d
",count_ddcb(0xFD));
  return 0;
}
