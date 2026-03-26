# ASSEMBLY DEBUGGER TUI SPEC

## Purpose
Rust terminal UI for stepping and inspecting PASM-generated emulators through a stable C debug ABI.

This is the canonical debugger spec for current behavior.

## Backend Modes
- `mock`: UI and interaction development without emulator linkage.
- `linked`: links against generated emulator library from `PASM_EMU_DIR` and uses generated debug ABI (`pasm_dbg_*`).

## Runtime Requirements (Linked Backend)
- Generated emulator output dir with `debugger_link.json` and built `*_emu` library.
- `PASM_EMU_DIR=<generated_out_dir>`.
- `--system-dir <dir>` so runtime ROM manifests can be loaded.
- Optional `--cart-rom <file>` for cartridge-enabled systems.
- Optional `--start-pc <addr>` (hex like `0xC000` or decimal).
- Optional `--run-speed realtime|max` (alias: `--speed`).

## Launch
Mock backend:

```bash
cargo run --manifest-path tools/debugger_tui/Cargo.toml -- --backend mock
```

Linked backend:

```bash
PASM_EMU_DIR=generated/<target> \
cargo run --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked --memory-size 65536 --system-dir examples/systems
```

Linked backend with cartridge override:

```bash
PASM_EMU_DIR=generated/<target> \
cargo run --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- \
  --backend linked --memory-size 65536 --system-dir examples/systems \
  --cart-rom "examples/roms/My Cart.sms"
```

## UI Model
Primary panes:
- Status
- Disassembly
- Registers
- Flags
- Breakpoints
- Stack
- Threads
- Memory
- Shortcuts

Behavior:
- Focus changes by pane (`Tab` / `Shift+Tab`).
- Disassembly supports selection, jump-to-address, and run-to-cursor.
- Memory supports cursor navigation and jump-to-address.
- Diff markers are applied between snapshots for changed values.

## Keybindings
Current keymap:
- `F7`: Step Into
- `F8`: Step Over
- `F6`: Step Out
- `F9`: Run/Pause
- `F5`: Reset
- `F4`: Run To Cursor
- `g`: Jump dialog (disassembly or memory pane)
- `PgUp` / `PgDn`: page navigation (disassembly/memory)
- `Up` / `Down`: row navigation
- `Tab` / `Shift+Tab`: next/previous pane
- `b`: toggle breakpoint at selected disassembly row
- `i`: toggle disassembly instruction metadata visibility
- `o`: toggle overlay
- `q` or `Ctrl+C`: quit

## Run Control Semantics
- Step commands execute through backend (`step_into`, `step_over`, `step_out`).
- `Run To Cursor` sets a temporary breakpoint when needed, starts run mode, and cleans the temporary breakpoint on stop.
- Disassembly jump while running auto-pauses first, then selects nearest instruction row to requested address.
- Memory jump aligns to memory row boundaries.

## Linked Integration Contract
The linked backend relies on generated debug ABI symbols, including:
- state/control: `pasm_dbg_snapshot_counts`, `pasm_dbg_snapshot_fill`, `pasm_dbg_run`, `pasm_dbg_pause`, `pasm_dbg_reset`
- stepping: `pasm_dbg_step_into`, `pasm_dbg_step_over`, `pasm_dbg_step_out`
- navigation/data: `pasm_dbg_toggle_breakpoint`, `pasm_dbg_read_memory`, `pasm_dbg_set_pc`
- ROM loading: `pasm_dbg_load_system_roms`, `pasm_dbg_load_cartridge_rom`

This keeps the TUI generic; processor/system-specific behavior comes from generated emulator data.

## Current Constraints
- Linked mode requires building generated emulator artifacts before running the TUI.
- `disassembly_window` requests are backend-driven and may require paused mode.
- Feature set is designed for keyboard-only operation in terminal environments.
