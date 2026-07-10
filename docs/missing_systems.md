# 8-Bit Emulator Portfolio: Final Completion Checklist

This document tracks the final remaining historical 8-bit systems required to achieve 100% completion of the 8-bit computing and gaming era.

---

## 🟢 Tier 1: The "Immediate Victories" (Reusable Code)
These machines can be completed almost instantly by recycling the CPU, video, and audio co-processors you have already written and verified for your current emulators.

- [ ] **ColecoVision**
  - *Status:* Missing
  - *Reuses:* Z80 CPU + TMS9918A VDP (MSX1) + SN76489 Audio (BBC Micro).
  - *Work Needed:* Simply map the unique ColecoVision I/O ports and hand-controller registers.
- [ ] **Dragon 32 / Dragon 64**
  - *Status:* Missing
  - *Reuses:* Motorola 6809 CPU + MC6847 VDG + MC6883 SAM (from your CoCo 1 core).
  - *Work Needed:* Swap the firmware ROMs and re-route the peripheral I/O assignments.
- [ ] **Oric-1 / Oric Atmos**
  - *Status:* Missing
  - *Reuses:* 6502 CPU Core (Apple II) + AY-3-8912 Audio Core (Amstrad CPC).
  - *Work Needed:* Code the custom Oric ULA video generator and its distinct line-attribute logic.

---

## 🇯🇵 Tier 2: The Japanese Powerhouses (Z80 Subsystem Overhauls)
These machines keep your verified Z80 engine but require coding complex, timing-heavy Japanese video layers and dedicated FM audio synthesis chips.

- [ ] **NEC PC-8801 Series**
  - *Status:* Missing
  - *Reuses:* Z80 CPU Core.
  - *Work Needed:* Build a massive 128 KB+ bank-switching memory management framework and emulate the Yamaha YM2203/YM2608 FM audio chips.
- [ ] **Sharp X1 Series**
  - *Status:* Missing
  - *Reuses:* Z80 CPU Core.
  - *Work Needed:* Build the custom display hardware that separates text memory from VRAM graphics via independent rendering planes.

---

## 🏛️ Tier 3: The Complete Architectural Rewrites (Brand-New CPUs)
These are entirely distinct historical platforms. They share zero core logic with your current codebase, requiring completely brand-new CPU instruction matrices and primitive video frameworks.

- [ ] **Texas Instruments TI-99/4A**
  - *Status:* Missing
  - *Reuses:* TMS9918A VDP (MSX1).
  - *Work Needed:* Code a brand-new **16-bit Texas Instruments TMS9900 CPU** core and handle its highly unusual "GROM" (Graphics ROM) addressing scheme.
- [ ] **Magnavox Odyssey²**
  - *Status:* Missing
  - *Work Needed:* Code an **Intel 8048 CPU** core from scratch and emulate its restrictive character-slot background/sprite rendering system.
- [ ] **Mattel Intellivision**
  - *Status:* Missing
  - *Work Needed:* Code the **General Instrument CP1600 CPU** core and the highly complex, timing-exact STIC video co-processor.


# Apple 8-Bit Emulator Upgrade Roadmap

This document outlines the logical progression steps to expand your existing **Apple II** emulator core across the rest of Apple's 8-bit hardware history. The roadmap is ranked from **least development work** to **most development work**.

---

## 🛠️ Tier 1: The "Quick Drop-In" (Minimal Work)
This machine uses your exact 6502 CPU core but has almost none of the complex video timing or disk drive logic of the Apple II. It is an easy weekend project.

- [ ] **Apple I**
  - **New Components:** A basic matrix text terminal display (it renders text line-by-line rather than using graphics modes).
  - **Memory/IO:** Reuses the 6502 CPU. You only need to emulate two PIA (Peripheral Interface Adapter) registers for keyboard input and text output, plus the tiny 256-byte Signetics PROM "Apple 1 Monitor" software.

---

## 🏎️ Tier 2: The "Evolutionary Steps" (Low Work)
These are variations of the standard Apple II architecture. Because you already have a working Apple II core, these models mostly require loading alternative ROMs or swapping existing features.

- [ ] **Apple II+**
  - **New Components:** Virtually identical to the original Apple II. 
  - **Adjustment:** Swap your current firmware file out for the **Applesoft BASIC** ROM image. It handles floating-point math instead of the old Integer BASIC.
- [ ] **Apple IIe**
  - **New Components:** Support for an 80-column text mode and lowercase characters. 
  - **Memory:** Implement the **80-Column / 64K Extended Memory Card** bank-switching logic. This maps an auxiliary bank of 64 KB RAM directly parallel to the main 64 KB RAM, controlled by I/O soft-switches (`$C000–$C00F`).

---

## 💾 Tier 3: The "All-In-One Redesigns" (Moderate Work)
These machines repackage the Apple IIe hardware into more integrated, compact portable frameworks. They introduce slightly modified CPUs and newer drive formats.

- [ ] **Apple IIc**
  - **New Components:** Upgrade your CPU core to support the **WDC 65C02** (which adds 27 new instructions to the standard 6502). Emulate the built-in ACIA 6551 serial chips for the integrated printer/modem ports.
  - **Disk I/O:** Map the Disk II controller logic directly to the built-in internal 5.25-inch drive.
- [ ] **Apple IIc Plus**
  - **New Components:** Take your IIc emulator code and add variable clock-rate logic to simulate the upgraded **4 MHz accelerator cache** chip.
  - **Disk I/O:** Update your disk controller code to support 3.5-inch Unidisk/Smartport protocols (`.2MG` or `.HDV` image formats) instead of just classic 5.25-inch `.DSK` files.

---

## 🏢 Tier 4: The "Total Business Pivot" (Maximum Work)
This was Apple's massive, standalone 8-bit business computer. While it still runs a 6502-family processor, its entire internal operating system, custom clock chips, and video display hardware are completely distinct from the Apple II line.

- [ ] **Apple III / Apple III Plus**
  - **New Components:** Emulate the custom **Synertek 6502A** running at a variable 2 MHz. Code an entirely new custom video generation engine that supports distinct 80-column text modes and high-resolution business graphics.
  - **Memory Map:** Build a highly complex **Memory Management Unit (MMU)** to handle banking across up to 256 KB of RAM using environmental registers.
  - **System Logic:** Emulate the integrated VIA 6522 chips, real-time clock, and specialized internal audio configurations necessary to properly boot **Apple SOS** (Sophisticated Operating System).

# Amstrad 8-Bit Emulator Upgrade Roadmap

This document outlines the logical progression steps to expand a fully functional **Amstrad CPC 464** emulator to support the rest of Amstrad's 8-bit hardware ecosystem. The roadmap is ranked from **least development work** to **most development work**.

---

## 🛠️ Tier 1: The "Easy Wins" (Minimal Work)
These machines share almost the exact same video, audio, and core hardware architecture as your CPC 464. You only need to add floppy disk controllers and basic memory banking.

- [ ] **CPC 664**
  - **New Components:** Emulate the standard **NEC µPD765 Floppy Disk Controller (FDC)** to parse `.DSK` files.
  - **Memory:** Keeps the exact same 64 KB RAM layout as your 464.
- [ ] **CPC 6128**
  - **New Components:** Uses the exact same FDC code as the 664.
  - **Memory:** Add an extra 64 KB of RAM. Implement basic 8-bit **RAM bank-switching** routines using the gate array config (`0x7F00`) to let the Z80 swap between the two 64 KB blocks.

---

## 🚀 Tier 2: The "ASIC Upgrade" (Moderate Work)
These are the Plus range systems. Your Z80 core and memory logic remain highly intact, but you must implement a cartridge parser, the 17-byte ASIC unlocking sequence, and custom graphics/audio features.

- [ ] **Amstrad GX4000**
  - **New Components:** A cartridge reader to handle `.CPR` files. Emulate the unlocked ASIC features (16 hardware sprites, 4096-color palette, and 3-channel DMA audio).
  - **Why it's first here:** It has **no keyboard, tape, or disk controller** to manage. It only runs cartridge games, making it the cleanest environment to test your new ASIC code.
- [ ] **Amstrad 464 plus**
  - **New Components:** Keep your original 464 tape and keyboard logic, but route the system architecture through your new ASIC and cartridge framework built for the GX4000.
- [ ] **Amstrad 6128 plus**
  - **New Components:** Combine your 6128 bank-switching/floppy controller code from Tier 1 with your new ASIC/cartridge code from Tier 2.

---

## 📄 Tier 3: The "Total Architecture Pivot" (Heavy Work)
The **PCW series** uses the same Z80 CPU, but everything else changes. They are monochrome office machines. You will have to swap out your CPC video/audio pipelines for entirely new custom hardware logic.

- [ ] **Amstrad PCW 8256**
  - **New Components:** A completely different monochrome video memory layout, different internal timers, and a custom map for its floppy drive. *(Note: It has no AY audio chip).*
- [ ] **Amstrad PCW 8512**
  - **New Components:** Take your 8256 core and add support for a second floppy disk drive head and expanded 512 KB bank-swapped RAM.
- [ ] **Amstrad PCW 9256**
  - **New Components:** Exactly like the 8256, but adjust the floppy code sector timings to match a 3.5-inch drive instead of a 3-inch drive.
- [ ] **Amstrad PCW 10**
  - **New Components:** Internally, this is just a re-cased PCW 9256. Zero extra emulator code is required once the 9256 works.
- [ ] **Amstrad PCW 9512**
  - **New Components:** Take the PCW 8512 core, but change how it emulates its custom parallel/printer port interface to handle the new daisy-wheel printer logic.
- [ ] **Amstrad PCW 9512+**
  - **New Components:** A minor tweak to the 9512 code to handle a 3.5-inch floppy disk controller map instead of a 3-inch one.

---

## 🔋 Tier 4: The "Handheld Redesign" (Maximum Work)
The **NC Notebooks** are an entirely different beast. While they still use a Z80-derived CPU, they use completely custom mobile power management, specialized real-time clocks, and liquid crystal displays.

- [ ] **Amstrad NC100**
  - **New Components:** Code a completely custom **LCD text-matrix screen controller**, battery power status logic, PCMCIA memory card slots, and an internal real-time clock chip.
- [ ] **Amstrad NC150**
  - **New Components:** No hardware changes. You just need to point your NC100 emulator framework to load the localized French/Italian firmware ROMs.
- [ ] **Amstrad NC200**
  - **New Components:** Take the massive custom NC100 framework, enlarge the LCD matrix resolution code for the bigger screen, and bolt on a 3.5-inch floppy disk controller.

# Atari 8-Bit Emulator Upgrade Roadmap

This document outlines the logical progression steps to expand your existing **Atari 800XL** and **Atari 2600** emulator cores to cover the rest of Atari's 8-bit computer and console history. The roadmap is ranked from **least development work** to **most development work**.

---

## 🛠️ Tier 1: The "XL/XE Direct Relatives" (Minimal Work)
These machines share the exact same chipset (ANTIC, GTIA, POKEY) as your 800XL. They only require minor modifications to RAM sizes, OS ROMs, or basic bank-switching registers.

- [ ] **Atari 65XE**
  - **New Components:** None. Internally, this is just a cost-reduced repackaging of your 800XL.
  - **Adjustment:** Swap the OS ROM for the XE revision. It has the exact same 64 KB RAM layout.
- [ ] **Atari 800XE**
  - **New Components:** None. Released in Eastern Europe, it is literally a 65XE motherboard inside a 130XE case. Reuses your 65XE/800XL code completely.
- [ ] **Atari XE Game System (XEGS)**
  - **New Components:** A detachable keyboard toggle. The XEGS is just a 65XE computer turned into a game console.
  - **Adjustment:** Add logic to handle a 32 KB ROM cartridge slot (built-in *Missile Command* game) and allow the emulator to boot without a keyboard attached.
- [ ] **Atari 130XE**
  - **New Components:** Expanded **RAM Bank-Switching**. 
  - **Memory:** Implement the extended 128 KB memory mapping via the **PORTB** (`$D301`) register. This allows the CPU and the ANTIC chip to access the extra 64 KB of bank-swapped RAM independently.

---

## 🏛️ Tier 2: The "Ancestors" (Low Work)
These are the original 1979 computers that started the Atari 8-bit line. They use the same core chips, but you will need to emulate minor video/hardware variations and older operating systems.

- [ ] **Atari 400**
  - **New Components:** Emulate a membrane keyboard interface.
  - **Memory/Video:** Restrict the RAM to a base of 8 KB or 16 KB. Adjust the CTIA/GTIA logic; early 400 models used a **CTIA** chip instead of a GTIA, which lacks certain color modes (modes 9, 10, and 11).
- [ ] **Atari 800**
  - **New Components:** Support for multiple RAM/ROM expansion slot configurations.
  - **Memory:** Scale RAM up to 48 KB. Load the older 10 KB "OS Rev A" or "OS Rev B" ROMs instead of the XL/XE ROMs. It lacks the built-in Atari BASIC ROM of the 800XL.
- [ ] **Atari 1200XL**
  - **New Components:** Function keys and keyboard LEDs.
  - **Memory/IO:** This was Atari's first XL machine. Map the unique keyboard lines and implement its specific, short-lived OS ROM. 

---

## 📺 Tier 3: The "Consolized Chipsets" (Moderate Work)
These consoles repurposed Atari's existing computer chips into dedicated gaming systems, but require adjusting memory layouts or mixing your 2600 and 800XL logic.

- [ ] **Atari 5200 SuperSystem**
  - **New Components:** Analog joystick register mapping.
  - **Architecture:** This console is essentially a modified Atari 400 computer. It uses ANTIC, GTIA, and POKEY, but **lacks a PIA chip**. 
  - **Memory:** You must map a unique 16 KB memory layout and write an analog wrapper for inputs, as the 5200 used non-centering analog controllers instead of digital joysticks.
- [ ] **Atari 7800 ProSystem**
  - **New Components:** Code the **MARIA graphics processor** from scratch. 
  - **Why it's in this tier:** The 7800 contains a custom TIA-like chip for backward compatibility with your Atari 2600 emulator. However, its native 7800 mode uses a custom 6502C CPU (running at 1.79 MHz / 1.19 MHz) and a brand-new, highly complex, sprite-list-based graphics chip called MARIA.

---

## 📟 Tier 4: The "Handheld Outlier" (Maximum Work)
This is Atari's color handheld console. It has absolutely no shared DNA with the 2600 or the 800XL computer line.

- [ ] **Atari Lynx**
  - **New Components:** Build an entirely unique mobile architecture.
  - **CPU:** Uses a **WDC 65C02** processor running at 4 MHz.
  - **Custom Hardware:** You must emulate **SUZY** (a custom 16-bit blitter chip that handles hardware math, sprite scaling, distortion, and mirror effects) and **MIKEY** (an 8-bit chip controlling the LCD screen timings, 4-channel stereo sound, and power management).

# Acorn / BBC 8-Bit Emulator Upgrade Roadmap

This document outlines the logical progression steps to expand your existing **BBC Micro (Model B)** emulator core across the rest of Acorn's 8-bit computer history. The roadmap is ranked from **least development work** to **most development work**.

---

## 🛠️ Tier 1: The "Simple Variants" (Minimal Work)
These machines are virtually identical to your current BBC Model B. They use the same custom chips and memory layouts, only changing RAM capacities or operating system ROM branches.

- [ ] **BBC Micro Model A**
  - **New Components:** None. The Model A was just a cheaper, stripped-down Model B.
  - **Adjustment:** Downgrade the available RAM buffer from 32 KB to 16 KB. Disable the logic for the user VIA, user port, disc interface, and Centronics printer port.
- [ ] **BBC Micro Model B+ (B+64 / B+128)**
  - **New Components:** Expanded RAM Bank-Switching.
  - **Adjustment:** The B+ keeps the exact same chipset but introduces shadow RAM to stop graphics modes from stealing user memory. Implement memory banking routines to handle an extra 32 KB (for the B+64) or 96 KB (for the B+128) of RAM via custom page registers.

---

## 🚀 Tier 2: The "Evolved Successors" (Low Work)
These represent the next generation of the official BBC Micro project. They use a slightly upgraded CPU and larger memory pools, but the fundamental way they handle video, audio, and I/O interrupts remains heavily backward-compatible.

- [ ] **BBC Master 128**
  - **New Components:** Upgrade the CPU core to a **WDC 65C02** (which adds new instructions). Map the two newly integrated physical cartridge slots.
  - **Memory:** Implement a much more aggressive memory management layout to swap between 128 KB of RAM and 128 KB of ROM.
- [ ] **BBC Master Compact**
  - **New Components:** Alternate floppy disk drive mapping.
  - **Adjustment:** Architecturally identical to the Master 128, but the internal Western Digital floppy controller chip is swapped for a newer model to support 3.5-inch disks instead of 5.25-inch disks.

---

## 📉 Tier 3: The "Cost-Reduced Cousin" (Moderate Work)
Acorn designed this machine to be a cheap, stripped-back version of the BBC Micro to compete in the home market against the ZX Spectrum. It shares the same 6502 CPU and running software, but the underlying motherboard was completely rewritten.

- [ ] **Acorn Electron**
  - **New Components:** The **Electron ULA (Uncommitted Logic Array)**. 
  - **The Shift:** Acorn removed almost all of the discrete support chips from the BBC Micro (like the MC6845 video controller and 6522 VIAs) and condensed them into one massive, custom ULA chip.
  - **Audio/Video Changes:** The ULA completely shifts memory access speeds (making RAM access slower than the BBC Micro). You must rewrite the sound routines because it downgrades the SN76489 chip to a simple, single-channel internal speaker.

---

## 📜 Tier 4: The "Vintage Ancestor" (Heavy Work)
This is the machine Acorn built *before* they won the BBC contract. While it is a 6502 system, it lacks almost all of the architectural luxuries you built for the BBC Micro.

- [ ] **Acorn Atom**
  - **New Components:** Code the **Motorola MC6847 Video Display Generator (VDG)** chip from scratch.
  - **The Shift:** The Atom (1980) uses a completely different video layout with its own unique graphics modes. It features a rudimentary 1-bit speaker hookup for audio and a vastly different memory map that handles a tiny 2 KB of RAM base (expandable to 12 KB).

# Commodore 8-Bit Emulator Upgrade Roadmap

This document outlines the logical progression steps to expand your existing **Commodore 64 (C64)** emulator core across the rest of Commodore's 8-bit hardware history. The roadmap is ranked from **least development work** to **most development work**.

---

## 🛠️ Tier 1: The "Direct Siblings" (Minimal Work)
These machines use the exact same 6510 CPU, VIC-II, and SID chips as your C64. They are virtually identical under the hood, requiring only simple case-logic or aesthetic tweaks.

- [ ] **Commodore 64C**
  - **New Components:** None. This was a late-80s redesign that shrunk the motherboard and introduced the newer **SID 8580** chip (which changed the volume filter curves and fixed a waveform bug). 
  - **Adjustment:** Use your existing C64 code, but load the slightly revised 64C Kernal/BASIC ROMs.
- [ ] **Commodore SX-64**
  - **New Components:** None. This was the briefcase-sized portable version of the C64.
  - **Adjustment:** The motherboard is identical to a standard C64. You only need to change the default startup text color scheme in the Kernal ROM to match the built-in 5-inch color CRT monitor and adjust the default device code for the integrated 1541 disk drive.
- [ ] **Commodore 64 Games System (64GS)**
  - **New Components:** A joystick-only boot loop. This was a keyboardless console version of the C64.
  - **Adjustment:** Strip out keyboard input logic. Modify the ROM loading sequence to boot directly into a cartridge slot layout, bypassing the classic `READY.` BASIC prompt.

---

## 🚀 Tier 2: The "Overclocked Evolution" (Low Work)
This machine was Commodore's ultimate 8-bit computer. While it seems massive, it contains a complete, native C64 motherboard inside it for backward compatibility, meaning you already have half the emulator finished.

- [ ] **Commodore 128 (C128 / C128D)**
  - **New Components:** Code the **MOS 8502 CPU** (an overclocked 6510 that can run at 2 MHz) and the **VDC 8563 chip** (an 80-column RGB text/graphics chip used alongside the standard VIC-II).
  - **The Switch:** Implement a 3-way mode switch. The C128 can boot into "C64 Mode" (uses your current code), "Native C128 Mode" (uses the 8502 at 2 MHz and the VDC chip), or "CP/M Mode" (which actually uses a built-in secondary Z80 CPU—a chip you already built for your Amstrad emulator!).

---

## 📺 Tier 3: The "Cost-Reduced Cousins" (Moderate Work)
Commodore attempted to replace the C64 with a series of cheaper productivity computers. They share the same architectural concepts but swapped out the graphics and sound chips for a single unified chip.

- [ ] **Commodore Plus/4**
  - **New Components:** Code the **TED (MOS 7360/8360)** chip from scratch and use a **MOS 7501/8501 CPU**.
  - **The Shift:** The Plus/4 removes the VIC-II and the SID chip entirely. Instead, the TED chip handles video, graphics, and basic 2-channel sound. It completely lacks hardware sprites but introduces a massive 121-color palette.
- [ ] **Commodore 16 / 116**
  - **New Components:** None if the Plus/4 is built. 
  - **Adjustment:** The C16 and C116 use the exact same TED chip and 7501 CPU as the Plus/4. You only need to drop the RAM buffer down from 64 KB to a tiny 16 KB and remove the Plus/4's built-in office software ROMs.

---

## 📜 Tier 4: The "Ancestors" (Heavy Work)
These are the machines that put Commodore on the map before the C64 was born. While they use the 6502 family, they use vastly different video layouts and input/output controllers.

- [ ] **VIC-20**
  - **New Components:** Code the **VIC (MOS 6560/6561)** graphics/audio chip from scratch.
  - **The Shift:** The VIC-20 (1980) uses a standard 6502 CPU and has a tiny 5 KB of base RAM. Its video layout is completely different from the VIC-II, rendering a unique 22-column by 23-line text screen and basic 4-channel sound.
- [ ] **Commodore PET Series (2001 / 4000 / 8000)**
  - **New Components:** Code a monochrome text-only display matrix and replace the C64's CIA chips with older **PIA 6520** and **VIA 6522** I/O adapters.
  - **The Shift:** The PET (1977) was Commodore's first computer. It has no bitmap graphics modes, no hardware sprites, and no custom sound chip (audio is just a simple 1-bit piezo speaker beep). It relies entirely on a custom character set known as "PETSCII" to draw menus and games.

# MSX Ecosystem Emulator Upgrade Roadmap

This document outlines the logical progression steps to expand your existing **MSX1** emulator core across the advanced generations of the official MSX standard. The roadmap is ranked from **least development work** to **most development work**.

---

## 🛠️ Tier 1: The "Memory Expansion" (Minimal Work)
These are variations of the base MSX1 specification. Because MSX utilizes a highly flexible slot system, scaling up to the maximum MSX1 memory limits requires no changes to your video or audio pipelines.

- [ ] **Expanded MSX1 (64 KB / 128 KB RAM)**
  - **New Components:** None. Many early MSX1 machines shipped with only 16 KB or 32 KB of RAM.
  - **Adjustment:** Expand your primary RAM buffer to the full 64 KB or 128 KB. Ensure your **Slot Selection Register** (`PPI Port A` at `$A8`) and memory mapper logic correctly route the Z80's page reads into these expanded memory segments.

---

## 🚀 Tier 2: The "Natural Progression" (Low Work)
This is the official second generation of the standard. It keeps your Z80 CPU completely intact but introduces a vastly superior, backward-compatible graphics chip.

- [ ] **MSX2**
  - **New Components:** Upgrade the video core to the **Yamaha V9938 VDP**.
  - **The Shift:** The V9938 is completely backward-compatible with your TMS9918A code, so old MSX1 games will run instantly. 
  - **New Features to Add:** Implement the new advanced video modes (up to 256 simultaneous colors from a palette of 512), hardware vertical/horizontal scrolling, a custom Real-Time Clock (RTC) chip, and support for memory mappers greater than 128 KB.

---

## 📺 Tier 3: The "Multimedia Enhancements" (Moderate Work)
These later evolutions of the standard introduced much sharper video scrolling, digitized sound, and a brand-new, legendary FM synthesis audio chip.

- [ ] **MSX2+**
  - **New Components:** Upgrade the video core to the **Yamaha V9958 VDP** and add the **OPLL (YM2413) sound chip**.
  - **The Shift:** The V9958 VDP introduces hardware horizontal scrolling registers and high-color "YJK" graphic modes (up to 19,268 colors on screen). 
  - **Audio:** Code the YM2413 FM sound chip to support the **MSX-Music** standard, which unlocks beautiful 9-channel synthesized soundtracks.

---

## 🏎️ Tier 4: The "Final Generation" (Maximum Work)
This represents the ultimate, final evolution of the 8-bit MSX standard, moving into hybrid 8/16-bit processing territory.

- [ ] **MSX TurboR (ST / GT)**
  - **New Components:** Code the **ASCII R800 RISC CPU** and a custom **PCM audio circuit**.
  - **The Shift:** Released only by Panasonic, this machine retains a Z80 inside for backward compatibility but shifts to a blistering fast 16-bit internal R800 processor running at 7.16 MHz for native software. You must also emulate a 1-bit PCM audio channel for digital sample playback.

# Tandy / RadioShack 8-Bit Emulator Upgrade Roadmap

This document outlines the logical progression steps to expand your existing **TRS-80 Model 4** (Z80-based) and **Color Computer 1** (6809-based) emulator cores across the rest of Tandy's official 8-bit computer history. The roadmap is ranked from **least development work** to **most development work**.

---

## 🛠️ Tier 1: The "CoCo Siblings" (Minimal Work)
These machines are evolution steps of your CoCo 1 core. They use the exact same 6809 CPU, SAM, and VDG chips, with only minor RAM or motherboard layout adjustments.

- [ ] **TRS-80 Color Computer 2 (CoCo 2)**
  - **New Components:** None. Internally, this is just a smaller, cost-reduced CoCo 1.
  - **Adjustment:** Swap out the case-handling and load the updated CoCo 2 ROM. It uses the newer **MC6847T1** VDG, which fixes lowercase text artifact bugs and changes the default background color to blue.
- [ ] **Tandy Deluxe Color Computer (TDP-100)**
  - **New Components:** None. This was a 100% identical clone of the CoCo 1 rebranded and sold under Tandy's alternative electronics store banner.

---

## 🚀 Tier 2: The "Model 4 Relatives" (Low Work)
These are the direct ancestors to your Model 4. Because the Model 4 contains a hardware "Model III compatibility mode" natively built inside it, you already have the vast majority of this code written.

- [ ] **TRS-80 Model III**
  - **New Components:** None. The Model 4 naturally falls back to Model III architecture when a Model III ROM is active.
  - **Adjustment:** Force the Z80 clock speed down to a strict 2.03 MHz, disable the 80-column video generation circuit, and restrict the hardware to a fixed 64 KB memory space without the Model 4's custom page-mapping registers.
- [ ] **TRS-80 Model I**
  - **New Components:** A simplified cassette and keyboard memory mapping.
  - **Adjustment:** This is the grandfather of the line (1977). Run the Z80 at 1.77 MHz, strip away the Model III/4 graphics cards, and map the memory structure to support Level I (4 KB) or Level II (16 KB) BASIC ROMs. You will need to account for its raw unbuffered expansion bus behavior if emulating external hardware.

---

## 📺 Tier 3: The "Ultimate 6809 Upgrade" (Moderate Work)
This is the final, heavy-duty evolution of the Color Computer family. It updates the CPU and swaps out the old video controllers for a highly customizable custom chip.

- [ ] **Tandy Color Computer 3 (CoCo 3)**
  - **New Components:** Code the **GIME (Graphics Interrupt Memory Enhancer)** custom ASIC chip and support the **Hitachi 6309 CPU**.
  - **The Shift:** The CoCo 3 keeps backward compatibility but removes the old SAM and VDG chips in favor of the GIME chip. 
  - **New Features to Add:** Implement a complex Memory Management Unit (MMU) to bank-swap up to 512 KB or 2 MB of RAM, code the new high-resolution text and 64-color graphic modes, and update your CPU instruction matrix to support the 6309's native extra registers and instructions if running in native mode.

---

## 📜 Tier 4: The "Business & Portability Outliers" (Heavy Work)
These machines share almost no common DNA with either of your current architectures. They represent Tandy's distinct excursions into alternative 8-bit formats.

- [ ] **Tandy 200**
  - **New Components:** Code an **Intel 80C85 CPU** core and a custom liquid crystal text display.
  - **The Shift:** This was an advanced flip-screen portable note-taking computer. It uses a different CPU family and relies on a monochrome matrix display rather than cathode-ray tube (CRT) timing signals.
- [ ] **Tandy / TRS-80 Model 100**
  - **New Components:** Scale down the Tandy 200 architecture.
  - **Adjustment:** This iconic "slab" portable uses the same 80C85 CPU core but requires a smaller liquid crystal layout and maps its internal applications (like Microsoft BASIC and TEXT) directly to memory-addressable ROM banks.
- [ ] **TRS-80 MC-10 (Micro Color Computer)**
  - **New Components:** Code a **Motorola 6803 CPU** core.
  - **The Shift:** Tandy's tiny budget computer. It shares a name with the CoCo line but uses a completely different CPU that integrates its own basic serial communications register pipelines and features a tiny 4 KB RAM limit.

# Tandy / RadioShack 8-Bit Emulator Upgrade Roadmap

This document outlines the logical progression steps to expand your existing **TRS-80 Model 4** (Z80-based) and **Color Computer 1** (6809-based) emulator cores across the rest of Tandy's official 8-bit computer history. The roadmap is ranked from **least development work** to **most development work**.

---

## 🛠️ Tier 1: The "CoCo Siblings" (Minimal Work)
These machines are evolution steps of your CoCo 1 core. They use the exact same 6809 CPU, SAM, and VDG chips, with only minor RAM or motherboard layout adjustments.

- [ ] **TRS-80 Color Computer 2 (CoCo 2)**
  - **New Components:** None. Internally, this is just a smaller, cost-reduced CoCo 1.
  - **Adjustment:** Swap out the case-handling and load the updated CoCo 2 ROM. It uses the newer **MC6847T1** VDG, which fixes lowercase text artifact bugs and changes the default background color to blue.
- [ ] **Tandy Deluxe Color Computer (TDP-100)**
  - **New Components:** None. This was a 100% identical clone of the CoCo 1 rebranded and sold under Tandy's alternative electronics store banner.

---

## 🚀 Tier 2: The "Model 4 Relatives" (Low Work)
These are the direct ancestors to your Model 4. Because the Model 4 contains a hardware "Model III compatibility mode" natively built inside it, you already have the vast majority of this code written.

- [ ] **TRS-80 Model III**
  - **New Components:** None. The Model 4 naturally falls back to Model III architecture when a Model III ROM is active.
  - **Adjustment:** Force the Z80 clock speed down to a strict 2.03 MHz, disable the 80-column video generation circuit, and restrict the hardware to a fixed 64 KB memory space without the Model 4's custom page-mapping registers.
- [ ] **TRS-80 Model I**
  - **New Components:** A simplified cassette and keyboard memory mapping.
  - **Adjustment:** This is the grandfather of the line (1977). Run the Z80 at 1.77 MHz, strip away the Model III/4 graphics cards, and map the memory structure to support Level I (4 KB) or Level II (16 KB) BASIC ROMs. You will need to account for its raw unbuffered expansion bus behavior if emulating external hardware.

---

## 📺 Tier 3: The "Ultimate 6809 Upgrade" (Moderate Work)
This is the final, heavy-duty evolution of the Color Computer family. It updates the CPU and swaps out the old video controllers for a highly customizable custom chip.

- [ ] **Tandy Color Computer 3 (CoCo 3)**
  - **New Components:** Code the **GIME (Graphics Interrupt Memory Enhancer)** custom ASIC chip and support the **Hitachi 6309 CPU**.
  - **The Shift:** The CoCo 3 keeps backward compatibility but removes the old SAM and VDG chips in favor of the GIME chip. 
  - **New Features to Add:** Implement a complex Memory Management Unit (MMU) to bank-swap up to 512 KB or 2 MB of RAM, code the new high-resolution text and 64-color graphic modes, and update your CPU instruction matrix to support the 6309's native extra registers and instructions if running in native mode.

---

## 📜 Tier 4: The "Business & Portability Outliers" (Heavy Work)
These machines share almost no common DNA with either of your current architectures. They represent Tandy's distinct excursions into alternative 8-bit formats.

- [ ] **Tandy 200**
  - **New Components:** Code an **Intel 80C85 CPU** core and a custom liquid crystal text display.
  - **The Shift:** This was an advanced flip-screen portable note-taking computer. It uses a different CPU family and relies on a monochrome matrix display rather than cathode-ray tube (CRT) timing signals.
- [ ] **Tandy / TRS-80 Model 100**
  - **New Components:** Scale down the Tandy 200 architecture.
  - **Adjustment:** This iconic "slab" portable uses the same 80C85 CPU core but requires a smaller liquid crystal layout and maps its internal applications (like Microsoft BASIC and TEXT) directly to memory-addressable ROM banks.
- [ ] **TRS-80 MC-10 (Micro Color Computer)**
  - **New Components:** Code a **Motorola 6803 CPU** core.
  - **The Shift:** Tandy's tiny budget computer. It shares a name with the CoCo line but uses a completely different CPU that integrates its own basic serial communications register pipelines and features a tiny 4 KB RAM limit.

# Nintendo 8-Bit Emulator Upgrade Roadmap

This document outlines the logical progression steps to expand your existing **Nintendo Entertainment System (NES)** emulator core across the rest of Nintendo's official 8-bit hardware history. The roadmap is ranked from **least development work** to **most development work**.

---

## 🛠️ Tier 1: The "Direct Regional Relatives" (Minimal Work)
These machines are internally almost identical to your current NES emulator. They use the same CPU and PPU frameworks, only requiring minor timing adjustments or audio mapping tweaks.

- [ ] **Famicom (Family Computer)**
  - **New Components:** None. This is the original Japanese version of the NES.
  - **Adjustment:** Swap the CPU clock rate slightly to match the NTSC standard if your current emulator is tuned for PAL (or vice-versa). Map the hardwired Player 1 and Player 2 controllers, including the Player 2 microphone register ($4016/$4017).
- [ ] **Famicom Disk System (FDS)**
  - **New Components:** Code the **RP2C33 ASIC chip** to parse `.FDS` disk images.
  - **The Shift:** This was a floppy-disk expansion unit that sat underneath the Famicom.
  - **Adjustment:** The RP2C33 chip handles BIOS loading, custom hardware disk-drive stepping, and adds an extra internal **wavetable synthesis audio channel** to the NES APU. 

---

## 🚀 Tier 2: The "Handheld Siblings" (Low Work)
Nintendo's early handheld empire was built directly on the lessons learned from the NES. While the screens and audio structures shifted, the way the hardware "thinks" is incredibly similar to your current code.

- [ ] **Game Boy (Classic / Pocket)**
  - **New Components:** Implement the **Sharp SM83 CPU** core and map a monochrome tile LCD screen.
  - **Why it's low work:** The SM83 processor is a hybrid that merges the instructions of the Intel 8080/Z80 with the address layout of the 6502—two architectures you already fully coded for your Amstrad, MSX, and Apple emulators! 
  - **Graphics/Audio:** The Game Boy's 2D tile-based rendering pipeline operates on the exact same background/sprite attribute logic as your NES PPU, just stripped down to a 4-shade monochrome palette. The audio unit is almost identical to the NES APU square and noise channels.
- [ ] **Game Boy Color (GBC)**
  - **New Components:** Upgrade the CPU clock and add a color palette matrix.
  - **Adjustment:** Take your Game Boy core, double the SM83 clock speed to 8.4 MHz, implement VRAM bank-switching (swapping between two 8 KB video banks), and add the color palette registers to support up to 56 simultaneous colors on screen.

---

## 📺 Tier 3: The "Arcade Cousins" (Moderate Work)
During the 8-bit era, Nintendo built arcade cabinets using heavily modified versions of the NES motherboard to allow for easy game porting.

- [ ] **Nintendo VS. System**
  - **New Components:** Alternate PPU Palette Mapping and Coin/Dip-switch registers.
  - **The Shift:** This was an arcade unit running NES games. 
  - **The Challenge:** To prevent people from putting cheap home cartridges into expensive arcade cabinets, Nintendo swapped the internal PPU chips. These arcade PPUs have completely scrambled color palette tables. You must map these unique palettes per game and add I/O registers for coin insertion and internal operator dip-switches.
- [ ] **PlayChoice-10**
  - **New Components:** A dual-CPU system link.
  - **The Shift:** A famous arcade cabinet that let users pay coins for timed play of standard NES games. 
  - **The Challenge:** The machine contains a standard NES motherboard, but it is controlled by a secondary **Zilog Z80 CPU** (a chip you already know well!). The Z80 handles the coin slots, the main on-screen game selection menus, and counts down the play timer before cutting off the NES video signal.

---

## 🕹️ Tier 4: The "Standalone LCD Outliers" (Heavy Work)
These represent Nintendo's early step into portable gaming before the Game Boy was conceived. They share absolutely zero code or architectural patterns with the NES.

- [ ] **Game & Watch Series**
  - **New Components:** Code a custom **Sharp SM5xx 4-bit microcontroller** core.
  - **The Shift:** Nintendo's iconic 1980s handheld LCD games.
  - **The Challenge:** These do not use a standard CPU or matrix pixel rendering. The SM5xx microcontroller directly triggers pre-printed static segments on a liquid crystal display based on a hardcoded internal ROM. You will have to map individual memory bits directly to a custom SVG graphic overlay to simulate the characters turning on and off.

# Sega 8-Bit Emulator Upgrade Roadmap

This document outlines the logical progression steps to expand your existing **Sega SG-1000** and **Sega Master System (SMS)** emulator cores across the rest of Sega's official 8-bit history. The roadmap is ranked from **least development work** to **most development work**.

---

## 🛠️ Tier 1: The "Instant Console Wins" (Minimal Work)
These machines are minor internal revisions or aesthetic repackagings of the hardware you have already emulated. They require almost zero new architectural code.

- [ ] **Sega Mark III**
  - **New Components:** None. This was the original Japanese release of what would become the Master System.
  - **Adjustment:** It is functionally identical to your SMS core. You only need to load the Japanese Mark III BIOS and game images, which utilize standard SMS memory configurations.
- [ ] **Sega SG-1000 II**
  - **New Components:** None. This was a 1984 cosmetic redesign of the SG-1000 that introduced detachable joysticks.
  - **Adjustment:** Reuses your exact SG-1000 emulator codebase without a single change.
- [ ] **Sega Master System II**
  - **New Components:** None. A cost-reduced model released in 1990.
  - **Adjustment:** Reuses your SMS code exactly as-is. It simply removes the physical Sega Card slot and the power LED from the hardware layer.

---

## 🚀 Tier 2: The "Handheld Transition" (Low Work)
Sega designed their first handheld to be a portable version of the Master System. Because you already have a working SMS emulator, this upgrade is incredibly straightforward.

- [ ] **Sega Game Gear**
  - **New Components:** An expanded palette lookup table and stereo audio mixing logic.
  - **Why it's low work:** The Game Gear uses the exact same Z80 CPU, the exact same SN76489 PSG, and the exact same Custom VDP architecture as your Master System core.
  - **Adjustments to make:** 
    1. **Video:** Instead of rendering the full SMS resolution, crop the active rendering viewport down to a centered $160 \times 144$ screen layout to simulate the LCD window. Expand the palette registers from 64 colors up to a **4,096-color selection** matrix.
    2. **Audio:** Add simple directional panning register bits to map the standard PSG audio channels into left/right stereo outputs for the headphone jack.

---

## ⌨️ Tier 3: The "Computer Branch" (Moderate Work)
Simultaneously with the SG-1000, Sega released a full home computer version of the machine to compete in the Japanese PC market. 

- [ ] **Sega SC-3000 / SC-3000H**
  - **New Components:** Code a full 64-key matrix keyboard controller.
  - **The Shift:** This is an SG-1000 inside a computer shell. It uses your exact Z80, TMS9918A VDP, and SN76489 audio pipelines.
  - **Adjustments to make:** Map the specific **Intel 8255 PPI (Programmable Peripheral Interface)** I/O ports to listen for raw keyboard matrices instead of standard controller D-pads, and add support for loading and saving raw cassette audio structures (`.CAS` files) used by Sega BASIC.

---

## 💾 Tier 4: The "Floppy Disk Evolution" (Heavy Work)
This rare, Japan-only expansion turned the SC-3000 computer into a heavy-duty processing unit, forcing the 8-bit architecture to interface with business-class hardware.

- [ ] **Sega SF-7000**
  - **New Components:** Code an alternative I/O bus and memory bank-switching wrapper.
  - **The Shift:** An expansion unit that plugged into the SC-3000, introducing an extra 64 KB of RAM (bringing the total to 80 KB) and a built-in 3-inch floppy disk drive.
  - **The Challenge:** You must write memory banking code to swap between the firmware ROMs and the new RAM blocks. You will also need to map a custom layout for the integrated **µPD765 Floppy Disk Controller**—the exact same drive controller chip you already mastered if you expanded your Amstrad or Spectrum emulators!

---

## 📚 The Outlier Note: The Sega Pico
Sega released the **Sega Pico** (Kids Computer Pico) in 1993 as an 8-bit educational toy system. However, for emulator development, it does not belong in this roadmap. Despite being an educational toy, it was built around a stripped-down **16-bit Sega Genesis** architecture, using a Motorola 68000 CPU and a Genesis-class VDP. 

