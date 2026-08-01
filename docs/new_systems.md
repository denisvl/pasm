# 8-Bit Emulator Portfolio: Master Implementation Roadmap

This document serves as your unified master completion checklist. Your existing portfolio of 12 implemented systems (Apple II, Amstrad CPC 464, Atari 800XL, BBC Micro, Commodore C64, MSX 1, TRS-80 Model 4, TRS-80 CoCo 1, ZX Spectrum 48k, NES, SG-1000, and SMS) has been analyzed alongside your expansion roadmaps. 

All remaining historical 8-bit hardware variants, evolutions, and standalone architectures have been aggregated and sorted strictly from **least development work to most development work**.

---

## 🟢 Tier 1: The "Instant Wins" (Zero to Minimal Effort)
*These systems require zero new core component logic. They are aesthetic variations, regional clones, or simple ROM-swaps of architectures you have already fully completed and verified.*

- [x] **Sega SG-1000 II** ✅ (2026-07-20)
  - *Strategy:* Uses your exact, verified SG-1000 core.
  - *Implementation:* Reuses the verified SG-1000 core ICs. System YAMLs point to the SG-1000 II BIOS/ROMs. Codegen, build, and test all pass.
- [x] **Sega Master System II** ✅ (2026-07-20)
  - *Strategy:* Uses your exact SMS core minus the physical Sega Card slot mapping.
  - *Implementation:* Created `examples/ics/sms2/sms2_asic.yaml` (315-5296 consolidated ASIC replacing discrete VDP/PSG/joy ICs) and `examples/ics/sms2/sms2_rf_modulator.yaml` (RF modulator). Updated `examples/systems/sms2/sms2_interactive.yaml` and `sms2_default.yaml` with 4 ICs (sms_bus0, sms_ram0, sms2_asic0, sms2_rf0). Added batch/shell scripts. Codegen, build (MSVC Release), and test all pass — `z80_test.exe` runs 1002 cycles, PC=0x0003.
- [x] **Sega Mark III** ✅ (2026-07-20)
  - *Strategy:* Uses your exact SMS discrete ICs; no BIOS (cartridge maps at $0000).
  - *Implementation:* Created `examples/systems/sm3/sm3_interactive.yaml` and `sm3_default.yaml` with 3-region memory map (CART_SLOT_48K at $0000, RAM_MAIN_8K at $C000, RAM_MIRROR_8K at $E000 — no overlap, no BIOS). Reuses all 6 SMS1 discrete ICs (sms_bus0, sms_ram0, sms_vdp0, sms_joy0, sms_psg0, sms_cxa0). Added batch/shell scripts (`run_sm3_debugger.bat/.sh`, `run_sm3_interactive.bat/.sh`). Codegen, build (MSVC Release), and test all pass — `z80_test.exe` runs 1002 cycles, PC=0x0003 (cartridge entry, no BIOS).
- [x] **Tandy Deluxe Color Computer (TDP-100)** ✅ (2026-07-21)
  - *Strategy:* 100% identical clone to your CoCo 1 core inside a different cosmetic shell.
  - *Implementation:* Created `examples/systems/tdp100/tdp100_default.yaml` and `tdp100_interactive.yaml` (metadata.name=MC6809TDP100DefaultSystem/MC6809TDP100InteractiveSystem, integrations.profile=tdp100_default/tdp100_interactive). Reuses ALL CoCo 1 ICs (SAM 6883, PIA0/PIA1 6821, VDG 6847, cart expansion, main RAM), devices (keyboard, gameport, video, speaker), hosts (stub/HAL interactive), keyboard/controller maps, and coco.rom. Added batch/shell scripts (`run_tdp100_debugger.bat/.sh`, `run_tdp100_default.bat`, `run_tdp100_interactive.bat/.sh`). Codegen, build (MSVC Release), and test all pass — `mc6809_test.exe` runs 1002 cycles, PC=0x014E.
- [x] **TRS-80 Color Computer 2 (CoCo 2)** ✅ (2026-07-21)
  - *Strategy:* Uses your CoCo 1 core; swap the VDG to the MC6847T1 variant to fix minor artifacting and shift the default background to blue.
  - *Implementation:* Created `examples/ics/coco2/coco2_vdg_6847t1.yaml` (MC6847T1 VDG variant — `motorola_mc6847t1_vdg_boundary` model). Created `examples/systems/coco2/coco2_default.yaml` and `coco2_interactive.yaml` (metadata.name=MC6809CoCo2DefaultSystem/MC6809CoCo2InteractiveSystem, integrations.profile=coco2_default/coco2_interactive). Reuses all CoCo 1 ICs (SAM 6883, PIA0/PIA1 6821, cart expansion, main RAM) except the VDG which is the new coco2_vdg_6847t1. ROM changed to `examples/roms/coco2/extbas11.rom` (Extended BASIC 1.1). Added batch/shell scripts (`run_coco2_debugger.bat/.sh`, `run_coco2_default.bat`, `run_coco2_interactive.bat/.sh`). Codegen, build (MSVC Release), and test all pass for both profiles — `mc6809_test.exe` runs 1002 cycles, PC=0x014E.
- [x] **Atari 65XE** ✅ (2026-07-21)
  - *Strategy:* Uses your 800XL core; simply swap out the firmware for the XE OS ROM.
  - *Implementation:* Created `examples/systems/atari65xe/atari65xe_default.yaml` and `atari65xe_interactive.yaml` (metadata.name=Atari65XEDefaultSystem/Atari65XEInteractiveSystem, integrations.profile=atari65xe_default/atari65xe_interactive). Reuses all 800XL ICs (ANTIC, GTIA, POKEY, PIA 6520, MMU, main RAM), devices (keyboard, controller, video, speaker, cassette adapter, cassette transport, TV), and host stub. OS ROMs (ATARIXL_C000/D800/SELFTEST) reused from `examples/roms/atari800xl/`; BASIC ROM is `examples/roms/atari65xe/AtariBasic.rom` (byte-identical to 800XL BASIC_C.ROM, renamed to avoid space-in-filename). Added batch/shell scripts (`run_atari65xe_debugger.bat/.sh`, `run_atari65xe_default.bat`, `run_atari65xe_interactive.bat/.sh`). Codegen, build (MSVC Release), and test all pass for both profiles — `mos6502_test.exe` runs 105 cycles (basic), boot test reaches PC=0xC2AA with ROMs loaded from `examples/systems/atari65xe`.
- [x] **Atari 800XE** ✅ (2026-07-21)
  - *Strategy:* Uses your 800XL core; it utilizes an identical 65XE motherboard re-housed for Eastern Europe.
  - *Implementation:* Created `examples/systems/atari800xe/atari800xe_default.yaml` and `atari800xe_interactive.yaml` (metadata.name=Atari800XEDefaultSystem/Atari800XEInteractiveSystem, integrations.profile=atari800xe_default/atari800xe_interactive). Reuses all 800XL ICs (ANTIC, GTIA, POKEY, PIA 6520, MMU, main RAM), devices (keyboard, controller, video, speaker, cassette adapter, cassette transport, TV), and host stub. OS ROMs (ATARIXL_C000/D800/SELFTEST) copied to `examples/roms/atari800xe/` from `examples/roms/atari800xl/`; BASIC ROM copied from `examples/roms/atari65xe/AtariBasic.rom` (byte-identical to 800XL BASIC). Added batch/shell scripts (`run_atari800xe_debugger.bat/.sh`, `run_atari800xe_default.bat`, `run_atari800xe_interactive.bat/.sh`). Codegen, build (MSVC Release), and test all pass for both profiles — `mos6502_test.exe` runs 101 cycles (basic), boot test reaches PC=0xC2AA with ROMs loaded from `examples/systems/atari800xe`.
- [x] **Commodore 64C** ✅ (2026-07-22)
  - *Strategy:* Uses your C64 core; load the slightly revised Kernal/BASIC ROMs (adjust audio filter curves for the SID 8580).
  - *Implementation:* Created `examples/ics/c64/c64_sid_8580.yaml` (SID 8580 with revised filter curves), `examples/ics/c64/c64_vic_ii_8565.yaml` (VIC-II 8565), and `examples/ics/c64/c64_pla_8580.yaml` (85xx PLA variant). Created 4 system YAMLs in `examples/systems/c64c/` (cartridge_interactive, cartridge_default, interactive, default) with merged 16 KB ROM pattern: single `64c.251913-01.bin` loaded in two 8 KB chunks — BASIC at $A000 (file_offset=0, load_size=8192) and KERNAL at $E000 (file_offset=8192, load_size=8192). Enhanced ROM loader pipeline: added `file_offset`/`load_size` fields to `schemas/system_schema.json`, updated `src/parser/yaml_loader.py` validation, and fixed `src/codegen/cpu_impl.py` `_generate_system_rom_loader()` to support partial file loads via fseek/fread with load_size bounds checks. Added batch/shell scripts (`run_c64c_debugger.bat/.sh`, `run_c64c_interactive.bat/.sh`, `run_c64c_default.bat/.sh`). Codegen, build (MSVC Release), and test all pass — `mos6510_test.exe` runs 1004 cycles, PC=0xFD5C (KERNAL boot sequence from merged ROM).
- [x] **Commodore SX-64** ✅ (2026-07-22)
  - *Strategy:* Uses your C64 core; adjust the default Kernal startup colors for the built-in CRT screen and set the default device ID for the integrated disk drive.
  - *Implementation:* Created 4 system YAMLs in `examples/systems/csx64/` (csx64_default, csx64_interactive, csx64_cartridge_default, csx64_cartridge_interactive) with metadata.name=CSX64DefaultSystem/CSX64InteractiveSystem, integrations.profile=csx64_*. Reuses all C64 ICs (PLA 906114, VIC-II 6569, SID 6581, CIA1/CIA2 6526, color RAM 2114, main RAM). ROM paths point to `../../roms/csx64/` (basic.901226-01.bin, characters.901225-01.bin, kernal.901227-03.bin). **No datasette/cassette** — SX-64 has no Datassette port (removed datasette device from interactive generate and no cassette config block). Added batch/shell scripts (`run_csx64_debugger.bat/.sh`, `run_csx64_interactive.bat/.sh`). Codegen verified for all profiles — default generates with 0 ICs/devices/cartridges, interactive generates with 7 ICs, 4 devices, 1 host, 1 cartridge. Build and TUI launch verified.
- [x] **Apple II+** ✅ (2026-07-22)
  - *Strategy:* Uses your Apple II core; swap out the Integer BASIC firmware file for the floating-point Applesoft BASIC ROM image.
  - *Implementation:* Created `examples/systems/apple2plus/apple2plus_default.yaml` and `apple2plus_interactive.yaml` (metadata.name=Apple2PlusDefaultSystem/Apple2PlusInteractiveSystem, integrations.profile=apple2plus_default/apple2plus_interactive). Reuses all Apple II ICs (keyboard encoder, game I/O, video softswitches, speaker toggle, cassette I/O, char ROM, slot decoder, main RAM), devices (keyboard, gameport, video, speaker, cassette adapter, cassette transport, monitor), and host. ROM path points to `../../roms/apple2plus/apple2-asoft-auto.rom` (Applesoft BASIC + Autostart Monitor, 12 KB at $D000). Added batch/shell scripts (`run_apple2plus_debugger.bat/.sh`, `run_apple2plus_default.bat/.sh`, `run_apple2plus_interactive.bat/.sh`). Created `examples/cassettes/apple2plus/` directory. **Codegen fix:** Fixed systemic bug in `src/codegen/split_units.py` `generate_picker_glue()` — keyboard runtime functions (`cpu_component_keyboard_host_shift_down`, `cpu_runtime_keyboard_binding_pressed`, `cpu_component_keyboard_emulator_action_pressed`) were unconditionally emitted even for systems with empty components, causing undefined-symbol compile errors. Now conditionally emitted only when `INPUT_RUNTIME` support is present. This also fixes the c64 default profile build. Codegen, build (MSVC Release), and test all pass for both profiles — `mos6502_test.exe` builds and links successfully.
- [x] **BBC Micro Model A** ✅ (2026-07-25)
  - *Strategy:* Uses your BBC Model B core; downgrade the available RAM buffer to 16 KB and disable the unpopulated user port/drive I/O lines.
  - *Implementation:* Created `examples/systems/bbcmicro/bbc_micro_model_a_default.yaml` and `bbc_micro_model_a_interactive.yaml` (metadata.name=BBCMicroModelADefaultSystem/BBCMicroModelAInteractiveSystem, integrations.profile=bbc_micro_model_a_default/bbc_micro_model_a_interactive). Reuses all BBC Model B ICs (CRTC 6845, Video ULA, System VIA 6522, User VIA 6522, Teletext SAA5050, ACIA 6850, MMU paged ROM, SN76489 PSG) and devices (keyboard, video, speaker, cassette adapter, cassette transport, TV), with a dedicated 16 KB main RAM IC `examples/ics/bbcmicro/bbc_micro_model_a_main_ram.yaml` (calloc(16384u), reset memset 16384u). Dedicated hosts `examples/hosts/bbcmicro/bbc_micro_model_a_host_hal_interactive.yaml` and `bbc_micro_model_a_host_stub.yaml`. Added batch/shell scripts (`run_bbc_micro_model_a_debugger.bat/.sh`, `run_bbc_micro_model_a_interactive.bat/.sh`).
  - *Model A RAM detection fix:* System memory regions now support `type: unpopulated` with a configurable `read_value`. The Model A system YAMLs declare `$4000-$7FFF` as unpopulated, so generated reads return `0xFF` and writes are ignored while `memory_size` remains 64 KB for ROM loading. This matches the MOS 16 KB RAM-detection path without hard-coding BBC-specific behavior in codegen.
- [x] **Famicom (Family Computer)** ✅ (2026-07-25)
  - *Strategy:* Uses your NES core; map the hardwired controllers and the Player 2 microphone register (`$4016/$4017`).
  - *Implementation:* Created dedicated Famicom system separate from NES. Reuses NES core ICs (ricoh2a03, nes_cpu_ram, nes_cart_bridge, nes_video, nes_speaker). New ICs: `famicom_cpu_bus`, `famicom_controller_ports` (with `mic_state` and `set_mic` callback), `famicom_io_ports`, `famicom_apu`, `famicom_ppu_regs`. New device: `famicom_controller` (hardwired, no expansion port). System YAMLs in `examples/systems/famicom/` (default + interactive). Host HALs in `examples/hosts/famicom/` (stub + interactive with GLFW). Keyboard/controller maps in `examples/hosts/famicom/`. Default ROM: `1942 (Japan, USA).nes`. Added batch/shell scripts (`run_famicom_debugger.bat/.sh`, `run_famicom_interactive.bat/.sh`, `run_famicom_default.bat/.sh`). Env var `PASM_NES_JOY2_CONNECTED=1` for hardwired P2 controller. **Key hardware differences from NES:** 60-pin cartridge (no lockout chip), expansion audio pins on cartridge bus, hardwired controllers (no connector), P2 controller has microphone (read via `$4017` bit 2, write via `set_mic` dispatch), RF-only NTSC-J output, DC power (no AC adapter). **Bug fix:** Fixed inverted dispatch arguments in host YAML `step_post` — `set_mic` was passing `1` as args pointer and `&mic` as count, causing STATUS_ACCESS_VIOLATION (0xC0000005) at runtime. Corrected to use `uint64_t mic_args[1]` array with proper argument order. Codegen, build (MSVC Release, no warnings), and runtime all pass — debugger TUI launches and runs without crashing.
- [ ] **Expanded MSX1**
  - *Strategy:* Uses your MSX1 core; scale the primary RAM buffer up to 64 KB or 128 KB using your verified Slot Selection Register (`PPI Port A`).

---

## 🟡 Tier 2: The "Drop-In Modifications" (Very Low Work)
*These require minor architectural configurations, simple input/output overrides, or basic chip recycling using engines you already have running.*

- [x] **Commodore 64 Games System (64GS)** ✅ (2026-07-27)
  - *Strategy:* Take your C64 core, strip away the keyboard input matrices, and modify the boot vector to skip the BASIC prompt and loop directly into the cartridge slot.
  - *Implementation:* Created 4 system YAMLs in `examples/systems/c64gs/` (c64gs_default, c64gs_interactive, c64gs_cartridge_default, c64gs_cartridge_interactive) with metadata.name=MOS6510C64GSDefaultSystem/MOS6510C64GSInteractiveSystem/MOS6510C64GSCartridgeDefaultSystem/MOS6510C64GSCartridgeInteractiveSystem. Reuses all C64C ICs (VIC-II 8565, SID 8580, CIA1/CIA2 6526, color RAM 2114, PLA 8580, main RAM). ROM paths: `../../roms/64gs/64gs.390852-01.bin` (merged 16 KB ROM — BASIC at $A000 file_offset=0 load_size=8192, KERNAL at $E000 file_offset=8192 load_size=8192) and `../../roms/64gs/characters_64gs.bin` (C64GS-specific char ROM). Added batch/shell scripts (`run_c64gs_debugger.bat/.sh`, `run_c64gs_interactive.bat/.sh`, `run_c64gs_default.bat/.sh`, `run_c64gs_cartridge_default.bat/.sh`, `run_c64gs_cartridge_interactive.bat/.sh`).
  - **Character ROM fix:** The C64GS KERNAL (390852-01) writes PETSCII codes directly to screen RAM for boot text (e.g. 0x43 for 'C') instead of converting to C64 screen codes (0x03). The standard C64 char ROM (characters.901225-01.bin) maps screen code 0x43 to a graphics character, producing garbled text like "-OMMODORE -64 |AMES ♥YSTEM". Created `examples/roms/64gs/characters_64gs.bin` — a 4096-byte char ROM derived from the standard C64 char ROM with glyphs for screen codes 0x00-0x1F duplicated to positions 0x40-0x5F, so PETSCII letter codes (0x41-0x5A = A-Z) map to the same glyphs as their screen-code equivalents (0x01-0x1A). This matches the C64GS hardware behavior where the KERNAL's direct PETSCII writes render as correct uppercase text.
  - **Script fixes:** Fixed `run_c64gs_debugger.bat` — corrected device path (c64_joystick.yaml not c64_controller.yaml), added missing TV device (tv_crt_mono.yaml), fixed host file references (c64_host_hal_interactive.yaml for both profiles), and added `--auto-run` flag to all cargo run invocations so the Rust debugger TUI starts the emulator automatically without waiting for user input. Created missing `run_c64gs_debugger.sh` with equivalent fixes for Linux. Applied same fixes to `run_c64gs_cartridge_interactive.sh`. Codegen, build (MSVC Release), and runtime all pass — default runs `mos6510_test.exe` with `--cycles`, interactive launches the GLFW window via the Rust debugger TUI.
- [ ] **Atari XE Game System (XEGS)**
  - *Strategy:* Take your 65XE core, add logic to handle its built-in 32 KB *Missile Command* game cartridge slot, and allow a keyboard-less boot flag.
- [ ] **Apple I**
  - *Strategy:* Reuses your 6502 CPU core. Implement a basic, lightweight matrix terminal window to render text line-by-line, map two 6821 PIA registers for I/O, and load the 256-byte Signetics PROM monitor.
- [x] **ColecoVision** ✅ (2026-07-30)
  - *Strategy:* Reuses your **Z80 CPU** (MSX/Amstrad), **TMS9918A VDP** (MSX1), and **SN76489 Audio** (BBC Micro). Work is strictly limited to mapping the unique ColecoVision I/O ports and hand-controller registers.
  - *Implementation:* Created 5 dedicated IC YAMLs in `examples/ics/colecovision/` (cpu_bus, main_ram_1k, vdp_tms9928a, psg_sn76489, joypad_io). Created cartridge mapper `examples/cartridges/colecovision/colecovision_mapper_none.yaml` (direct ROM mirror at $8000-$FFFF, up to 32 KB). Created 4 host YAMLs in `examples/hosts/colecovision/` (host_stub, host_hal_interactive with GLFW, host_controller_colecovision with keyboard+gamepad+joystick bindings for P1/P2 joystick and 12-key keypad, host_console_colecovision). Created 2 system YAMLs in `examples/systems/colecovision/` (default + interactive). BIOS ROM: `examples/roms/colecovision/ColecoVision BIOS (1982).col` (8 KB at $0000). Memory map: BIOS ROM 8 KB at $0000-$1FFF, 1 KB RAM at $6000-$67FF, cartridge up to 32 KB at $8000-$FFFF. **Key port decoding:** Uses mask 0xE1 (not SG-1000's 0xC1) to distinguish VDP ($80/$81), PSG ($A0/$A1), and controller ports ($C0/$C1) — bit 5 added to disambiguate VDP from PSG. **Joypad:** Two 9-pin controller ports with joystick (up/down/left/right/fire A/fire B) + 12-key numeric keypad (3×4 matrix: 1-2-3 / 4-5-6 / 7-8-9 / *-0-#). Added batch/shell scripts (`run_colecovision_debugger.bat/.sh`, `run_colecovision_interactive.bat/.sh`). Codegen, build (MSVC Release), and runtime all pass — debugger TUI launches with GLFW window.
- [ ] **Dragon 32** ✅ (2026-08-04)
  - *Strategy:* Reuses your **6809 CPU**, **MC6847 VDG**, and **MC6883 SAM** core configurations directly from your CoCo 1. Simply re-route the peripheral I/O assignments and load the alternative firmware.
  - *Implementation:* Created 2 system YAMLs in `examples/systems/dragon32/` (default + interactive). Reuses ALL coco1 ICs directly: `coco1_sam_6883`, `coco1_pia0_6821`, `coco1_pia1_6821`, `coco1_vdg_6847` (standard MC6847, NOT the coco2 `coco2_vdg_6847t1` variant), `coco1_cart_expansion`, `coco1_main_ram`. Reuses coco1 devices (keyboard, gameport, video, speaker, cassette_transport, tv) and `host_coco` (stub + HAL interactive). 32 KB RAM (cassette-only, no floppy). 16 KB Microsoft Extended BASIC ROM (`examples/roms/dragon32/d32.rom`) split across three 8 KB regions using `file_offset`/`load_size`: bytes 0-8191 → `ROM_DRAGONROM_8000` ($8000), bytes 8192-16383 → `ROM_DRAGONROM_A000` ($A000), bytes 8192-16383 (mirror) → `ROM_DRAGONROM_E000` ($E000). DragonDOS cartridge ROM (`ddos11c.rom`, 8 KB) available via cartridge slot. Clock: 894886 Hz (0.89 MHz). Profiles: `dragon32_default` (output `generated/mc6809_dragon32`) and `dragon32_interactive` (output `generated/mc6809_dragon32_sdl`). Scripts: `run_dragon32_debugger.bat/.sh`, `run_dragon32_interactive.bat/.sh`. Codegen, build (MSVC Release), and runtime all pass — default runs `mc6809_test.exe`, interactive launches the GLFW window via the Rust debugger TUI.

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
