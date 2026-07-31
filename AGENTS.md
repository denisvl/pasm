# AGENTS.md

This repository contains PASM emulator generators, generated emulator builds,
and an MCP server for structured emulator automation.

These instructions are for coding agents working in this repo, especially
Codex under VS Code.

## Repo Skills

When adding or extending a machine under `examples/systems/`, use the local
Codex skill `create-system` in `.codex/skills/create-system/`.

## Preferred Emulator Interaction Path

When you need to inspect, control, test, or script a generated emulator, prefer
the PASM automation MCP server over:

- ad hoc terminal key injection
- brittle sleep loops
- OCR or screenshot-first inspection
- debugger TUI scraping

Use direct shell interaction only when the MCP server cannot cover the needed
operation.

## MCP Server

The repo provides a stdio MCP server entry point:

```bash
UV_CACHE_DIR=.uv-cache uv run pasm-automation-mcp
```

Project script name:

```bash
pasm-automation-mcp
```

If your MCP host requires argv form, use:

- command: `uv`
- args: `["run", "pasm-automation-mcp"]`
- env: `{"UV_CACHE_DIR": ".uv-cache"}`

## When To Use It

Use the PASM automation MCP tools when you need to:

- open a built generated emulator
- query emulator capabilities
- capture text-grid or framebuffer state
- inject keyboard or controller input
- wait for deterministic emulator conditions
- inspect memory, registers, PC, or current instruction
- record and replay structured sessions
- set breakpoints through the automation surface

## Recommended Tool Flow

For most emulator tasks, follow this order:

1. Open a machine session
2. Describe the machine
3. Query capabilities
4. Prefer structured screen/text observation
5. Inject input with structured tool calls
6. Use `machine.wait.*` instead of sleeps
7. Use inspection/debug tools only when capabilities support them

Typical sequence:

1. `machine.open.generated`
2. `machine.describe`
3. `machine.capabilities`
4. `machine.screen.text_views` or `machine.screen.text_grid`
5. `machine.input.keyboard` or `machine.input.controller`
6. `machine.wait.*`
7. `machine.inspect.*` / `machine.debug.*`

## Opening Machines

Preferred:

- `machine.open.generated`

Use it with a built generated output directory, for example:

- `generated/apple2_interactive`
- `generated/atari800xl_interactive`
- `generated/bbc_micro_model_a_interactive`

This tool resolves the built emulator artifact from the repo’s normal generated
layout and handles Windows-style `.exe` resolution as well.

Lower-level fallback:

- `machine.open`

Use `machine.open` only when you already know the exact built artifact path and
need to bypass the generated-output resolver.

## Observation Rules

Prefer:

- `machine.screen.text_grid`
- `machine.screen.text_views`

over:

- screenshots
- OCR
- terminal scraping

If text-grid support is unavailable, then use:

- `machine.screen.framebuffer`

and only fall back to image-based reasoning if the structured automation
surface does not expose the needed state.

## Timing Rules

Do not use arbitrary sleep loops when the automation MCP surface can wait for a
real emulator condition.

Prefer:

- `machine.wait.for_text`
- `machine.wait.for_text_disappearance`
- `machine.wait.for_event`
- `machine.wait.for_memory_value`
- `machine.wait.for_program_counter`
- `machine.wait.for_breakpoint`
- `machine.wait.for_watchpoint`

## Input Rules

Prefer structured input tools:

- `machine.input.keyboard`
- `machine.input.controller`

For text entry, prefer:

- keyboard mode `type_text`

Do not invent free-form key expression languages.

## Inspection / Debug Rules

Before using inspection or debug operations, call:

- `machine.capabilities`

Then use only the supported subset of:

- `machine.inspect.memory.read`
- `machine.inspect.memory.write`
- `machine.inspect.program_counter`
- `machine.inspect.frame_metadata`
- `machine.inspect.current_instruction`
- `machine.inspect.registers.read`
- `machine.inspect.registers.write`
- `machine.debug.breakpoint.set`

## Recording / Replay

For deterministic reproduction, prefer:

- `machine.record.sequence`
- `machine.replay.recording`

Use these instead of manually reconstructing long input scripts when you need a
repeatable emulator interaction.

## Example Flow

Example high-level flow for a built Apple II output:

1. Open:
   - `machine.open.generated(output_dir="generated/apple2_interactive")`
2. Inspect:
   - `machine.describe(session_id=...)`
   - `machine.capabilities(session_id=...)`
3. Read screen:
   - `machine.screen.text_views(session_id=...)`
   - `machine.screen.text_grid(session_id=..., region_id="primary_text")`
4. Type:
   - `machine.input.keyboard(session_id=..., mode="type_text", text="LOAD")`
5. Wait:
   - `machine.wait.for_text(session_id=..., text="READY", timeout_frames=120)`

## Validation Notes

The MCP server in this repo is implemented in:

- [src/pasm_automation/mcp_server.py](/home/dvlop/projects/pasm/src/pasm_automation/mcp_server.py)

Current focused coverage is in:

- [tests/test_mcp_server.py](/home/dvlop/projects/pasm/tests/test_mcp_server.py)

If you change the MCP tool surface, update the tests and keep tool names stable
unless there is a deliberate compatibility break.
