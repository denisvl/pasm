# 8-Bit Emulator Portfolio: Master Implementation Roadmap

This document serves as your unified master completion checklist. Your existing portfolio of 12 implemented systems (Apple II, Amstrad CPC 464, Atari 800XL, BBC Micro, Commodore C64, MSX 1, TRS-80 Model 4, TRS-80 CoCo 1, ZX Spectrum 48k, NES, SG-1000, and SMS) has been analyzed alongside your expansion roadmaps. 

All remaining historical 8-bit hardware variants, evolutions, and standalone architectures have been aggregated and sorted strictly from **least development work to most development work**.

---

## 🟢 Tier 1: The "Instant Wins" (Zero to Minimal Effort)
*These systems require zero new core component logic. They are aesthetic variations, regional clones, or simple ROM-swaps of architectures you have already fully completed and verified.*

- [ ] **Sega SG-1000 II**
  - *Strategy:* Uses your exact, verified SG-1000 core.
- [ ] **Sega Master System II**
  - *Strategy:* Uses your exact SMS core minus the physical Sega Card slot mapping.
- [ ] **Sega Mark III**
  - *Strategy:* Uses your exact SMS core; point it to load the Japanese BIOS and game ROMs.
- [ ] **Tandy Deluxe Color Computer (TDP-100)**
  - *Strategy:* 100% identical clone to your CoCo 1 core inside a different cosmetic shell.
- [ ] **TRS-80 Color Computer 2 (CoCo 2)**
  - *Strategy:* Uses your CoCo 1 core; swap the VDG to the MC6847T1 variant to fix minor artifacting and shift the default background to blue.
- [ ] **Atari 65XE**
  - *Strategy:* Uses your 800XL core; simply swap out the firmware for the XE OS ROM.
- [ ] **Atari 800XE**
  - *Strategy:* Uses your 800XL core; it utilizes an identical 65XE motherboard re-housed for Eastern Europe.
- [ ] **Commodore 64C**
  - *Strategy:* Uses your C64 core; load the slightly revised Kernal/BASIC ROMs (optional: adjust audio filter curves for the SID 8580).
- [ ] **Commodore SX-64**
  - *Strategy:* Uses your C64 core; adjust the default Kernal startup colors for the built-in CRT screen and set the default device ID for the integrated disk drive.
- [ ] **Apple II+**
  - *Strategy:* Uses your Apple II core; swap out the Integer BASIC firmware file for the floating-point Applesoft BASIC ROM image.
- [ ] **BBC Micro Model A**
  - *Strategy:* Uses your BBC Model B core; downgrade the available RAM buffer to 16 KB and disable the unpopulated user port/drive I/O lines.
- [ ] **Famicom (Family Computer)**
  - *Strategy:* Uses your NES core; map the hardwired controllers and the Player 2 microphone register (`$4016/$4017`).
- [ ] **Expanded MSX1**
  - *Strategy:* Uses your MSX1 core; scale the primary RAM buffer up to 64 KB or 128 KB using your verified Slot Selection Register (`PPI Port A`).

---

## 🟡 Tier 2: The "Drop-In Modifications" (Very Low Work)
*These require minor architectural configurations, simple input/output overrides, or basic chip recycling using engines you already have running.*

- [ ] **Commodore 64 Games System (64GS)**
  - *Strategy:* Take your C64 core, strip away the keyboard input matrices, and modify the boot vector to skip the BASIC prompt and loop directly into the cartridge slot.
- [ ] **Atari XE Game System (XEGS)**
  - *Strategy:* Take your 65XE core, add logic to handle its built-in 32 KB *Missile Command* game cartridge slot, and allow a keyboard-less boot flag.
- [ ] **Apple I**
  - *Strategy:* Reuses your 6502 CPU core. Implement a basic, lightweight matrix terminal window to render text line-by-line, map two 6821 PIA registers for I/O, and load the 256-byte Signetics PROM monitor.
- [ ] **ColecoVision**
  - *Strategy:* Reuses your **Z80 CPU** (MSX/Amstrad), **TMS9918A VDP** (MSX1), and **SN76489 Audio** (BBC Micro). Work is strictly limited to mapping the unique ColecoVision I/O ports and hand-controller registers.
- [ ] **Dragon 32 / Dragon 64**
  - *Strategy:* Reuses your **6809 CPU**, **MC6847 VDG**, and **MC6883 SAM** core configurations directly from your CoCo 1. Simply re-route the peripheral I/O assignments and load the alternative firmware.

---

## 🟠 Tier 3: The "Memory Bank & Floppy Upgrades" (Low Work)
*These introduce standard floppy disk controllers or expanded bank-switching logic to platforms you already emulate.*

- [ ] **Atari 130XE**
  - *Strategy:* Take your 800XL core and implement extended 128 KB memory mapping via the **PORTB** (`$D301`) register, allowing independent CPU and ANTIC banking.
- [ ] **Atari 800**
  - *Strategy:* Adjust your Atari computer core to expand RAM limits to 48 KB, handle multiple ROM expansion slot configurations, and load the older 10 KB OS Rev A/B files.
- [ ] **Apple IIe**
  - *Strategy:* Take your Apple II core, add support for 80-column text modes/lowercase rendering, and implement the parallel 64 KB auxiliary bank-switching soft-switches (`$C000–$C00F`).
- [ ] **BBC Micro Model B+ (B+64 / B+128)**
  - *Strategy:* Take your BBC core and implement memory banking routines to handle shadow RAM and extra page expansion slots to prevent high-res graphics modes from choking user memory.
- [ ] **Amstrad CPC 664**
  - *Strategy:* Take your CPC 464 core and emulate the standard **NEC µPD765 Floppy Disk Controller (FDC)** to parse `.DSK` file frameworks.
- [ ] **Amstrad CPC 6128**
  - *Strategy:* Combine your new CPC 664 floppy drive logic with an extra 64 KB of RAM, using the gate array configuration register (`0x7F00`) to handle 8-bit bank-switching.

---

## 🔵 Tier 4: The "Evolutionary Step-Ups" (Moderate Work)
*These demand upgrades to updated CPU variants (like moving from the 6502 to the 65C02 or the hybrid SM83) or transitioning to highly backwards-compatible secondary video processors.*

- [ ] **Sega Game Gear**
  - *Strategy:* Uses your SMS core. Crop the active video rendering viewport down to a centered $160 \times 144$ matrix, expand the color palette registers to a 4,096-color lookup table, and implement left/right stereo audio panning bits.
- [ ] **Game Boy (Classic / Pocket)**
  - *Strategy:* Build the **Sharp SM83 CPU** core (an architectural hybrid that merges Intel 8080/Z80 instructions with the 6502's address layout—all structures you already have written). Map a monochrome 2D tile-based rendering pipeline using the same background/sprite attribute logic as your NES PPU.
- [ ] **Game Boy Color (GBC)**
  - *Strategy:* Take your new Game Boy core, double the SM83 clock speed to 8.4 MHz, implement VRAM bank-switching, and add the color palette matrix to support up to 56 simultaneous on-screen colors.
- [ ] **Sega SC-3000 / SC-3000H**
  - *Strategy:* Extends your SG-1000 core. Code a full 64-key matrix keyboard controller mapped through **Intel 8255 PPI** I/O ports, and add a parser for raw cassette audio files (`.CAS`).
- [ ] **Apple IIc**
  - *Strategy:* Take your Apple IIe framework and upgrade the CPU core to support the **WDC 65C02** (which introduces 27 new instructions). Emulate the built-in 6551 ACIA serial communication chips.
- [ ] **Apple IIc Plus**
  - *Strategy:* Take your IIc core, add variable clock-rate logic to simulate the 4 MHz accelerator cache, and update your disk controller code to handle 3.5-inch Smartport storage protocols (`.2MG`/`.HDV`).
- [ ] **BBC Master 128**
  - *Strategy:* Upgrade your BBC Micro core to the **WDC 65C02** processor, map its dual physical cartridge slot layouts, and build an aggressive MMU layout to swap across 128 KB of RAM and 128 KB of ROM.
- [ ] **BBC Master Compact**
  - *Strategy:* Identical architecture to your Master 128 core, but update the internal Western Digital floppy controller logic parameters to support 3.5-inch disks instead of older 5.25-inch units.
- [ ] **MSX2**
  - *Strategy:* Take your MSX1 core and upgrade the video engine to the backward-compatible **Yamaha V9938 VDP**. Implement its advanced video modes (512-color palette), hardware vertical/horizontal scrolling, a custom RTC chip, and expanded memory mappers.
- [ ] **TRS-80 Model III**
  - *Strategy:* Take your Model 4 core and force the Z80 clock down to a strict 2.03 MHz, disable the 80-column video generation paths, and restrict the hardware to a fixed 64 KB memory block without page registers.
- [ ] **TRS-80 Model I**
  - *Strategy:* Scale down your Model III compatibility layer. Run the Z80 at 1.77 MHz, strip away advanced graphics cards, and map memory to handle Level I (4 KB) or Level II (16 KB) BASIC ROM lines.
- [ ] **Famicom Disk System (FDS)**
  - *Strategy:* Extends your NES core. Code the **RP2C33 ASIC** chip to handle BIOS loading, mechanical floppy-drive stepping parameters, and map its unique internal **wavetable synthesis audio channel** directly into your NES APU pipeline.

---

## 🟣 Tier 5: The "Architectural Extensions" (Medium-Heavy Work)
*These require building entirely custom video/audio ASIC layouts or writing complex dual-CPU/multi-chip coordination logic for platforms where you only own a portion of the core logic.*

- [ ] **Amstrad GX4000**
  - *Strategy:* Uses your CPC Z80 core. Code a cartridge reader to parse `.CPR` images and build the custom unlocked **ASIC features**: 16 hardware sprites, a 4096-color palette, and 3-channel DMA audio. No keyboard or drive logic is needed.
- [ ] **Amstrad 464 plus**
  - *Strategy:* Merge your original CPC 464 tape and keyboard input logic directly into the new GX4000 ASIC and cartridge framework.
- [ ] **Amstrad 6128 plus**
  - *Strategy:* Merge your CPC 6128 memory banking and floppy controller logic directly into the new GX4000 ASIC and cartridge framework.
- [ ] **Oric-1 / Oric Atmos**
  - *Strategy:* Reuses your **6502 CPU core** (Apple II) and **AY-3-8912 Audio core** (Amstrad CPC). You must code the custom Oric ULA video generator from scratch, including its unique line-attribute layout logic.
- [ ] **Atari 1200XL**
  - *Strategy:* Modify your Atari computer core to map its short-lived custom function keys, unique keyboard LED lines, and specific early OS ROM configurations.
- [ ] **Atari 400**
  - *Strategy:* Restrict your Atari core RAM to an 8/16 KB base and emulate early **CTIA video chip** variations, which lack the standard GTIA color modes 9, 10, and 11.
- [ ] **Atari 5200 SuperSystem**
  - *Strategy:* Modify your Atari computer core to run on a unique 16 KB memory block and strip out the PIA chip completely. Write an analog wrapper for inputs, as the 5200 used non-centering analog joystick registers instead of digital lines.
- [ ] **Nintendo VS. System**
  - *Strategy:* Extends your NES core. Build scrambled, game-specific PPU color lookup palette tables, and add I/O registers for coin insertion and internal operator dip-switches.
- [ ] **PlayChoice-10**
  - *Strategy:* Connect your standard NES core to a secondary **Zilog Z80 CPU** core. The Z80 acts as the master, handling coin counting, parsing the arcade game selection menus, and managing a countdown play timer that toggles the NES video signal line.
- [ ] **MSX2+**
  - *Strategy:* Upgrade your MSX2 video core to the **Yamaha V9958 VDP** (adds hardware horizontal scrolling and high-color YJK graphics modes) and code the **OPLL (YM2413) sound chip** to satisfy the 9-channel synthesized MSX-Music standard.
- [ ] **Commodore 128 (C128 / C128D)**
  - *Strategy:* Build a 3-way hardware mode switch. "C64 Mode" runs your current core. For native mode, code the **MOS 8502 CPU** (an overclocked 6510 running at 2 MHz) and the **VDC 8563** 80-column RGB text/graphics chip. For "CP/M Mode", link your existing Z80 core directly to the bus.

---

## 🔴 Tier 6: The "Heavy Architectural Shifts" (Heavy Work)
*These represent massive ecosystem branches or complex standalone business architectures where everything outside of the CPU core must be built completely from scratch.*

- [ ] **Sega SF-7000**
  - *Strategy:* Extends your SC-3000 computer framework. Write an alternative I/O bus expansion wrapper, handle memory banking for an additional 64 KB of RAM, and map a custom implementation for an integrated **µPD765 Floppy Disk Controller**.
- [ ] **NEC PC-8801 Series**
  - *Strategy:* Reuses your Z80 CPU core. Build a massive 128 KB+ bank-switching memory management framework from scratch and emulate the complex **Yamaha YM2203/YM2608** FM audio synthesis chips.
- [ ] **Sharp X1 Series**
  - *Strategy:* Reuses your Z80 CPU core. Build custom display hardware that separates text memory from VRAM graphics via completely independent, multi-plane rendering lines.
- [ ] **Acorn Electron**
  - *Strategy:* Reuses your 6502 CPU core. Code the massive, custom **Electron ULA** from scratch, which condenses all video timing, bottlenecks RAM access speeds, and downgrades audio down to a simple 1-channel internal speaker toggle.
- [ ] **Commodore Plus/4**
  - *Strategy:* Code the **TED (MOS 7360/8360)** chip from scratch and link it to a modified **MOS 7501/8501 CPU** core. The TED chip handles all video generation (a sprite-less 121-color palette) and basic 2-channel sound.
- [ ] **Commodore 16 / 116**
  - *Strategy:* Uses your new Plus/4 TED/CPU architecture; drop the primary RAM buffer down to a strict 16 KB map and remove the Plus/4 productivity software ROM vectors.
- [ ] **VIC-20**
  - *Strategy:* Reuses your 6502 CPU core. Code the original **VIC (MOS 6560/6561)** graphics and audio chip from scratch to handle a unique 5 KB base memory map, 22-column video frame lines, and 4-channel raw sound registers.
- [ ] **Tandy Color Computer 3 (CoCo 3)**
  - *Strategy:* Take your CoCo 1/2 core and upgrade your instruction matrix to support the native extra registers and instructions of the **Hitachi 6309 CPU**. Code the custom **GIME (Graphics Interrupt Memory Enhancer) ASIC** to handle 512 KB/2 MB MMU memory banking and high-res 64-color graphics.

---

## 💀 Tier 7: The "Ground-Up Complete Rewrites" (Maximum Work)
*These platforms share 0% core or peripheral logic with your current codebase. They require entirely new CPU instruction matrices, specialized LCD microcontrollers, or complex legacy business I/O hardware.*

- [ ] **Acorn Atom**
  - *Strategy:* Early 1980 system. Uses a 6502 CPU, but requires coding the **Motorola MC6847 Video Display Generator (VDG)** from scratch, handling a tiny 2 KB base RAM layout, and routing audio through a crude 1-bit speaker toggle.
- [ ] **Texas Instruments TI-99/4A**
  - *Strategy:* Reuses your MSX1 TMS9918A VDP, but requires coding a brand-new **16-bit Texas Instruments TMS9900 CPU** core from scratch and handling its highly unusual "GROM" (Graphics ROM) addressing scheme.
- [ ] **Magnavox Odyssey²**
  - *Strategy:* Requires coding an **Intel 8048 CPU** core from scratch and emulating its highly restrictive, custom character-slot background and sprite video rendering system.
- [ ] **Mattel Intellivision**
  - *Strategy:* Requires coding a brand-new **General Instrument CP1600 CPU** core from scratch alongside the highly complex, timing-exact **STIC** video co-processor layout.
- [ ] **Atari 7800 ProSystem**
  - *Strategy:* Emulate a custom 6502C CPU (running at variable 1.79 MHz / 1.19 MHz clocks). While it contains a TIA chip for backward compatibility with the 2600, its native mode requires coding a completely brand-new, highly complex, sprite-list-based graphics chip called **MARIA**.
- [ ] **Commodore PET Series (2001 / 4000 / 8000)**
  - *Strategy:* Uses a 6502 CPU, but requires writing a custom monochrome text display matrix, rendering native "PETSCII" character graphics, handling a 1-bit piezo speaker beep, and replacing modern CIA controller chips with legacy **PIA 6520** and **VIA 6522** I/O adapters.
- [ ] **Amstrad PCW Series (8256 / 8512 / 9256 / 10 / 9512 / 9512+)**
  - *Strategy:* Uses a Z80 CPU, but strips out all CPC audio and video pipelines. You must code an entirely distinct monochrome video memory layout, custom internal timers, unique sector floppy drive mappings, and custom parallel daisy-wheel printer register interfaces.
- [ ] **Amstrad NC Series Notebooks (NC100 / NC150 / NC200)**
  - *Strategy:* Portable mobile Z80 environments. Code a completely custom **LCD text-matrix screen controller**, battery power status logic registers, PCMCIA memory card slots, and an internal real-time clock chip.
- [ ] **Tandy 200 / TRS-80 Model 100**
  - *Strategy:* Flip-screen and slab portables. Code an entirely brand-new **Intel 80C85 CPU** core from scratch, couple it to a custom liquid crystal text matrix display layout, and map integrated text/BASIC applications directly to addressable memory ROM banks.
- [ ] **TRS-80 MC-10 (Micro Color Computer)**
  - *Strategy:* Tandy's budget outlier. You must code a completely separate **Motorola 6803 CPU** core from scratch, integrating its native, internal serial communications register pipelines.
- [ ] **MSX TurboR (ST / GT)**
  - *Strategy:* The ultimate MSX hybrid. Retains your Z80 for backward compatibility, but requires coding a brand-new, blistering fast **16-bit ASCII R800 RISC CPU** core running at 7.16 MHz for native software, paired with a custom 1-bit PCM audio circuit for digital sample playback.
- [ ] **Game & Watch Series**
  - *Strategy:* Requires coding a custom **Sharp SM5xx 4-bit microcontroller** core. It bypasses standard matrix pixel rendering completely; you must write an engine that maps individual memory bits directly to a static SVG graphic overlay to simulate fixed liquid crystal segments turning on and off.
- [ ] **Atari Lynx**
  - *Strategy:* Build a unique mobile architecture from scratch. Code a **WDC 65C02** at 4 MHz, then emulate two massive custom ASICs: **SUZY** (a 16-bit blitter chip handling hardware math, sprite scaling, distortion, and mirror effects) and **MIKEY** (controlling LCD screen timings, 4-channel stereo sound, and power management).