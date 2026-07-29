from __future__ import annotations

import argparse
from pathlib import Path

from src.pasm_automation import AutomationError, create


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture text and a framebuffer PNG through the automation ABI.",
    )
    parser.add_argument("library", help="Path to a shared library exposing the automation ABI.")
    parser.add_argument(
        "--create-symbol",
        default="emu_automation_create",
        help="C symbol used to create an automation machine.",
    )
    parser.add_argument(
        "--text-region",
        default=None,
        help="Text region id to capture. Defaults to the adapter's primary text region.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=0,
        help="Frames to run before capturing.",
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=None,
        help="Optional PNG output path for the framebuffer.",
    )
    args = parser.parse_args()

    with create(args.library, args.create_symbol) as machine:
        if args.frames:
            machine.run.frames(args.frames)

        views = machine.screen.text_views()
        region_id = args.text_region
        if region_id is None and views:
            region_id = views[0].region_id

        if region_id is not None:
            print(machine.screen.text(region_id).plain)
        else:
            print("No text regions are exposed by this automation adapter.")

        if args.screenshot is not None:
            machine.screen.framebuffer().save_png(args.screenshot)
            print(f"Wrote {args.screenshot}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AutomationError as exc:
        raise SystemExit(str(exc)) from exc
