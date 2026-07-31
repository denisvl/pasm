# Emulator Automation Example Flows

This file provides one short, stable automation scenario per currently
supported system family. The intent is to give Python, Rust, and MCP consumers
known-good targets that match the declared automation metadata and readiness
recipes.

Unless noted otherwise, these flows target the `*_default.yaml` system for the
family and assume the generated build already exists.

## Shared Patterns

### Python text flow

Use the existing [examples/automation/type_text_and_wait.py](../examples/automation/type_text_and_wait.py)
script for text-grid families:

```bash
uv run python examples/automation/type_text_and_wait.py \
  generated/<system_output_dir> \
  --create-symbol <create_symbol> \
  --input-text $'PRINT 1\r' \
  --wait-text "1"
```

### Python observation flow

Use [examples/automation/capture_text_and_screenshot.py](../examples/automation/capture_text_and_screenshot.py)
for passive capture:

```bash
uv run python examples/automation/capture_text_and_screenshot.py \
  generated/<system_output_dir>/build/<binary_or_exe> \
  --create-symbol <create_symbol> \
  --frames 30 \
  --screenshot framebuffer.png
```

### MCP open / observe pattern

For generated emulators, use:

1. `machine.open.generated`
2. `machine.capabilities`
3. `machine.reset`
4. `machine.resume`
5. `machine.run_frames` or a wait tool
6. `machine.screen.text_grid` or `machine.screen.framebuffer`

## Text-Grid Families

### Apple II / Apple II Plus

Goal: boot to monitor prompt and submit a BASIC-style line.

- Readiness target: `]`
- Python:

```bash
uv run python examples/automation/type_text_and_wait.py \
  generated/apple2_interactive \
  --create-symbol mos6502_automation_create \
  --input-text $'PRINT 1\r' \
  --wait-text "1"
```

### Atari 8-bit Family

Applies to Atari 65XE, 800XE, 800XL, and XEGS text-capable defaults.

Goal: boot to BASIC and confirm `READY`.

- Readiness target: `READY`
- Python:

```bash
uv run python examples/automation/capture_text_and_screenshot.py \
  generated/atari800xl_interactive/build/mos6502_test \
  --create-symbol mos6502_automation_create \
  --frames 180
```

### BBC Micro

Applies to Model B and Model A text-capable defaults.

Goal: boot to BASIC prompt and submit a single-line print statement.

- Readiness target: `BASIC`
- Python:

```bash
uv run python examples/automation/type_text_and_wait.py \
  generated/bbc_micro_interactive \
  --create-symbol mos6502_automation_create \
  --input-text $'PRINT 1\r' \
  --wait-text "1"
```

### Commodore 64 Family

Applies to C64, C64C, C64GS, and CSX64 variants.

Goal: wait for `READY.` and submit a BASIC command.

- Readiness target: `READY.`
- Python:

```bash
uv run python examples/automation/type_text_and_wait.py \
  generated/c64_interactive \
  --create-symbol mos6502_automation_create \
  --input-text $'PRINT 1\r' \
  --wait-text "1"
```

### CoCo / TDP-100

Applies to CoCo 1, CoCo 2, and TDP-100 defaults.

Goal: wait for `OK` and submit a BASIC command.

- Readiness target: `OK`
- Python:

```bash
uv run python examples/automation/type_text_and_wait.py \
  generated/coco1_interactive \
  --create-symbol mc6809_automation_create \
  --input-text $'PRINT 1\r' \
  --wait-text "1"
```

### Amstrad CPC

Goal: wait for BASIC `Ready` and submit a command.

- Readiness target: `Ready`
- Python:

```bash
uv run python examples/automation/type_text_and_wait.py \
  generated/cpc464_interactive \
  --create-symbol z80_automation_create \
  --input-text $'PRINT 1\r' \
  --wait-text "1"
```

### MSX / SG-1000 Text Mode

Applies to MSX1, MSX1 Expanded, SG-1000, and SG-1000 II defaults when the VDP
is in text mode.

Goal: wait for the boot banner and capture the text grid.

- Readiness targets:
  - MSX family: `BASIC`
  - SG-1000 family: `SEGA`
- Rust real-adapter example:

```bash
cargo run --manifest-path automation/rust/Cargo.toml \
  -p emu-automation --example real_adapter_text_wait -- \
  generated/msx1_interactive/build/z80_test \
  z80_automation_create \
  BASIC
```

### TRS-80 Model 4

Goal: wait for `READY` and confirm the boot text surface is stable.

- Readiness target: `READY`
- Python:

```bash
uv run python examples/automation/capture_text_and_screenshot.py \
  generated/trs80_model4_interactive/build/z80_test \
  --create-symbol z80_automation_create \
  --frames 300
```

## Framebuffer Families

### Atari 2600

Goal: boot to a live nonblank frame and capture a screenshot.

- Readiness target: nonblank framebuffer
- Python:

```bash
uv run python examples/automation/capture_text_and_screenshot.py \
  generated/atari2600_interactive/build/mos6502_test \
  --create-symbol mos6502_automation_create \
  --frames 8 \
  --screenshot atari2600.png
```

### NES / Famicom

Goal: boot cartridge content to a live nonblank frame.

- Readiness target: nonblank framebuffer
- Python:

```bash
uv run python examples/automation/capture_text_and_screenshot.py \
  generated/nes_interactive/build/mos6502_test \
  --create-symbol mos6502_automation_create \
  --frames 8 \
  --screenshot nes.png
```

### SMS / SMS2 / SM3

Goal: boot cartridge content to a live nonblank frame.

- Readiness target: nonblank framebuffer
- Python:

```bash
uv run python examples/automation/capture_text_and_screenshot.py \
  generated/sms_interactive/build/z80_test \
  --create-symbol z80_automation_create \
  --frames 8 \
  --screenshot sms.png
```

### ZX Spectrum

Applies to 48K and BetaDisk defaults.

Goal: boot to a live nonblank framebuffer and capture the visible cropped
frame.

- Readiness target: nonblank framebuffer
- Python:

```bash
uv run python examples/automation/capture_text_and_screenshot.py \
  generated/spectrum48k_interactive/build/z80_test \
  --create-symbol z80_automation_create \
  --frames 8 \
  --screenshot spectrum.png
```

## MCP Tool Sequences

### Text flow

Use this shape for BASIC/monitor families:

1. `machine.open.generated(output_dir=...)`
2. `machine.reset(kind="cold")`
3. `machine.resume()`
4. `machine.run_frames(frame_count=<warmup>)`
5. `machine.wait.for_text(text=<prompt>, timeout_frames=...)`
6. `machine.input.keyboard(mode="type_text", text="PRINT 1\r")`
7. `machine.wait.for_text(text="1", timeout_frames=...)`

### Framebuffer flow

Use this shape for console/framebuffer families:

1. `machine.open.generated(output_dir=...)`
2. `machine.reset(kind="cold")`
3. `machine.resume()`
4. `machine.run_frames(frame_count=8)`
5. `machine.screen.framebuffer(include_pixels=true)` or a higher-level client wait
6. Inspect `width`, `height`, `visible_area`, and `pixels`

## Notes

- These flows intentionally stay at the level of declared readiness metadata:
  warmup frames, text prompt detection, and nonblank framebuffer capture.
- They avoid system-specific debugger pokes and free-form condition logic.
- Systems with multiple media variants can use the same family flow shape while
  respecting each YAML's `media_defaults`.
