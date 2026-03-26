# PASM Debugger TUI

Rust TUI debugger front-end for generated PASM emulators.

## Backends

- `mock`: no emulator linkage, UI-only development path.
- `linked`: links against a generated emulator library (`<cpu>_emu`) and uses the generated generic debug bridge API (`pasm_dbg_*`).

## Build and Run (Mock)

```bash
cargo run --manifest-path tools/debugger_tui/Cargo.toml -- --backend mock
```

## Build and Run (Linked)

1. Generate and build your emulator from `processor.yaml` + `system.yaml`:

```bash
uv run python -m src.main generate \
  --processor examples/processors/minimal8.yaml \
  --system examples/systems/minimal8/minimal8_default.yaml \
  --output /tmp/pasm_minimal8_dbg

cmake -S /tmp/pasm_minimal8_dbg -B /tmp/pasm_minimal8_dbg/build
cmake --build /tmp/pasm_minimal8_dbg/build
```

2. Link debugger TUI against generated emulator lib and run linked backend:

```bash
PASM_EMU_DIR=/tmp/pasm_minimal8_dbg \
cargo run --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked --memory-size 65536 --system-dir /tmp/pasm_minimal8_dbg
```

`PASM_EMU_DIR` must point to a generated emulator output directory that contains `debugger_link.json` and a built `*_emu` library (typically in `<out>/build` after CMake build).

Optional:
- `--start-pc <addr>` sets initial program counter for debugging (supports decimal or hex like `0xC000`).

## Keys

- `q` or `Ctrl+C`: quit
- `space`: run/pause
- `F10`: step over
- `F11`: step into
- `F12`: step out
- `s`: step into (fallback when function keys are unavailable)
- `n`: step over (fallback)
- `o`: step out (fallback)
- `Tab` / `Shift+Tab`: cycle focused pane
- `Up/Down` on disassembly pane: move disassembly selection cursor
- `b`: toggle breakpoint at selected disassembly row
