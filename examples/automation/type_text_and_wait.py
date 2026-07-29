from __future__ import annotations

import argparse
from pathlib import Path

from src.pasm_automation import AutomationError, create
from src.pasm_automation.mcp_server import resolve_generated_machine_artifact


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open a built generated emulator, type text, and wait for a text response.",
    )
    parser.add_argument("output_dir", help="Generated PASM output directory, for example generated/apple2_interactive")
    parser.add_argument("--create-symbol", default="emu_automation_create")
    parser.add_argument("--binary-name", default=None)
    parser.add_argument("--build-dir", default=None)
    parser.add_argument("--input-text", required=True, help="Text to submit through the logical keyboard mapping.")
    parser.add_argument("--wait-text", required=True, help="Text to wait for in the text grid.")
    parser.add_argument("--text-region", default=None, help="Text region id to inspect.")
    parser.add_argument("--timeout-frames", type=int, default=180)
    parser.add_argument("--step-frames", type=int, default=1)
    parser.add_argument("--screenshot", type=Path, default=None)
    args = parser.parse_args()

    artifact = resolve_generated_machine_artifact(
        args.output_dir,
        binary_name=args.binary_name,
        build_dir=args.build_dir,
    )

    with create(str(artifact), args.create_symbol) as machine:
        machine.keyboard.type_text(args.input_text)
        snapshot = machine.wait.screen_contains(
            args.wait_text,
            region_id=args.text_region,
            timeout_frames=args.timeout_frames,
            step_frames=args.step_frames,
        )
        print(snapshot.plain)
        if args.screenshot is not None:
            machine.screen.framebuffer().save_png(args.screenshot)
            print(f"Wrote {args.screenshot}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AutomationError as exc:
        raise SystemExit(str(exc)) from exc
