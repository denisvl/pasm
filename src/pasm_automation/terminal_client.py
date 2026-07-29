from __future__ import annotations

import argparse
import json
from typing import Sequence

from . import AutomationError, EventType, create
from .protocol import event_to_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pasm-automation",
        description="Terminal client for the emulator automation ABI.",
    )
    parser.add_argument("library", help="Path to a shared library exposing the automation ABI.")
    parser.add_argument(
        "--create-symbol",
        default="emu_automation_create",
        help="C symbol used to create an automation machine.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON instead of plain text where supported.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("machine-info", help="Describe the connected machine.")
    subparsers.add_parser("machine-capabilities", help="Show machine capability bits.")

    text_parser = subparsers.add_parser("screen-text", help="Capture a text region.")
    text_parser.add_argument("--region-id", default=None, help="Optional text region id.")

    screen_parser = subparsers.add_parser(
        "screen",
        help="Render the best available terminal-friendly screen view.",
    )
    screen_parser.add_argument("--region-id", default=None, help="Optional text region id.")

    framebuffer_parser = subparsers.add_parser(
        "screen-framebuffer",
        help="Show framebuffer metadata and optionally save a PNG snapshot.",
    )
    framebuffer_parser.add_argument(
        "--save-png",
        default=None,
        help="Optional PNG output path.",
    )

    pause_parser = subparsers.add_parser("pause", help="Pause execution.")
    pause_parser.set_defaults(_command="pause")
    resume_parser = subparsers.add_parser("resume", help="Resume execution.")
    resume_parser.set_defaults(_command="resume")

    reset_parser = subparsers.add_parser("reset", help="Reset execution.")
    reset_parser.add_argument(
        "--kind",
        choices=["cold", "warm"],
        default="cold",
        help="Reset kind.",
    )

    subparsers.add_parser("step-frame", help="Advance one frame.")

    run_parser = subparsers.add_parser("run-frames", help="Advance by a frame count.")
    run_parser.add_argument("frame_count", type=int, help="Number of frames to run.")

    wait_text_parser = subparsers.add_parser("wait-text", help="Wait for text to appear.")
    wait_text_parser.add_argument("text", help="Text to wait for.")
    wait_text_parser.add_argument("--region-id", default=None, help="Optional text region id.")
    wait_text_parser.add_argument("--timeout-frames", type=int, default=300)
    wait_text_parser.add_argument("--step-frames", type=int, default=1)

    event_parser = subparsers.add_parser("poll-event", help="Poll a single event.")
    event_parser.add_argument("--after-sequence", type=int, default=0)
    event_parser.add_argument(
        "--event-type",
        choices=[
            "frame_completed",
            "machine_reset",
            "execution_state_changed",
            "input_submitted",
            "screen_changed",
            "text_changed",
            "media_activity",
            "debug_message",
            "error",
        ],
        default=None,
        help="Optional event type filter applied client-side.",
    )

    watch_parser = subparsers.add_parser(
        "events-watch",
        help="Drain and print matching events, advancing frames when needed.",
    )
    watch_parser.add_argument("--after-sequence", type=int, default=0)
    watch_parser.add_argument(
        "--event-type",
        choices=[
            "frame_completed",
            "machine_reset",
            "execution_state_changed",
            "input_submitted",
            "screen_changed",
            "text_changed",
            "media_activity",
            "debug_message",
            "error",
        ],
        default=None,
    )
    watch_parser.add_argument("--limit", type=int, default=1)
    watch_parser.add_argument("--timeout-frames", type=int, default=0)
    watch_parser.add_argument("--step-frames", type=int, default=1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    with create(args.library, args.create_symbol) as machine:
        if args.command == "machine-info":
            descriptor = machine.describe()
            return _print_payload(
                args.json,
                {
                    "machine_id": descriptor.machine_id,
                    "system_id": descriptor.system_id,
                    "model_id": descriptor.model_id,
                    "region": descriptor.region,
                    "video_standard": descriptor.video_standard,
                    "adapter_version": descriptor.adapter_version,
                    "configured_memory_bytes": descriptor.configured_memory_bytes,
                    "feature_bits": descriptor.capabilities.feature_bits,
                },
                _format_machine_info(descriptor),
            )

        if args.command == "machine-capabilities":
            capabilities = machine.capabilities()
            return _print_payload(
                args.json,
                {"feature_bits": capabilities.feature_bits},
                str(capabilities.feature_bits),
            )

        if args.command == "screen-text":
            snapshot = machine.capture_text_grid(args.region_id)
            return _print_payload(
                args.json,
                {
                    "region_id": snapshot.region_id,
                    "columns": snapshot.columns,
                    "rows": snapshot.rows,
                    "row_stride": snapshot.row_stride,
                    "plain": snapshot.plain,
                    "frame_number": snapshot.frame_number,
                },
                _render_text_snapshot(snapshot),
            )

        if args.command == "screen":
            views = machine.text_views()
            if views:
                snapshot = machine.capture_text_grid(args.region_id or views[0].region_id)
                return _print_payload(
                    args.json,
                    {
                        "kind": "text_grid",
                        "region_id": snapshot.region_id,
                        "plain": snapshot.plain,
                        "frame_number": snapshot.frame_number,
                    },
                    _render_text_snapshot(snapshot),
                )
            framebuffer = machine.capture_framebuffer()
            summary = _framebuffer_summary(framebuffer)
            return _print_payload(
                args.json,
                {
                    "kind": "framebuffer",
                    "frame_number": framebuffer.frame.frame_number,
                    "width": framebuffer.width,
                    "height": framebuffer.height,
                    "pixel_format": framebuffer.pixel_format,
                },
                summary + _framebuffer_render_suffix(framebuffer),
            )

        if args.command == "screen-framebuffer":
            framebuffer = machine.capture_framebuffer()
            if args.save_png is not None:
                framebuffer.save_png(args.save_png)
            return _print_payload(
                args.json,
                {
                    "frame_number": framebuffer.frame.frame_number,
                    "width": framebuffer.width,
                    "height": framebuffer.height,
                    "stride_bytes": framebuffer.stride_bytes,
                    "pixel_format": framebuffer.pixel_format,
                    "saved_png": args.save_png,
                },
                _framebuffer_summary(framebuffer)
                + _framebuffer_render_suffix(framebuffer)
                + (f"\nsaved_png: {args.save_png}" if args.save_png is not None else ""),
            )

        if args.command == "pause":
            machine.pause()
            print("ok")
            return 0

        if args.command == "resume":
            machine.resume()
            print("ok")
            return 0

        if args.command == "reset":
            machine.reset(args.kind)
            print("ok")
            return 0

        if args.command == "step-frame":
            machine.step_frame()
            print("ok")
            return 0

        if args.command == "run-frames":
            machine.run_frames(args.frame_count)
            print("ok")
            return 0

        if args.command == "wait-text":
            snapshot = machine.wait_for_text(
                args.text,
                region_id=args.region_id,
                timeout_frames=args.timeout_frames,
                step_frames=args.step_frames,
            )
            return _print_payload(
                args.json,
                {
                    "region_id": snapshot.region_id,
                    "plain": snapshot.plain,
                    "frame_number": snapshot.frame_number,
                },
                snapshot.plain,
            )

        if args.command == "poll-event":
            event = _poll_matching_event(machine, args.after_sequence, args.event_type)
            if args.json:
                print(json.dumps({"event": None if event is None else event_to_payload(event)}, sort_keys=True))
            elif event is None:
                print("none")
            else:
                print(_format_event(event))
            return 0

        if args.command == "events-watch":
            events = _watch_events(
                machine,
                after_sequence=args.after_sequence,
                event_type_name=args.event_type,
                limit=args.limit,
                timeout_frames=args.timeout_frames,
                step_frames=args.step_frames,
            )
            if args.json:
                print(json.dumps({"events": [event_to_payload(event) for event in events]}, sort_keys=True))
            else:
                for event in events:
                    print(_format_event(event))
            return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def _poll_matching_event(machine, after_sequence: int, event_type_name: str | None):
    event = machine.poll_event(after_sequence)
    if event is None or event_type_name is None:
        return event
    while event is not None and event.type.name.lower() != event_type_name:
        after_sequence = event.sequence_number
        event = machine.poll_event(after_sequence)
    return event


def _watch_events(
    machine,
    *,
    after_sequence: int,
    event_type_name: str | None,
    limit: int,
    timeout_frames: int,
    step_frames: int,
):
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if timeout_frames < 0:
        raise ValueError("timeout_frames must be non-negative")
    if step_frames <= 0:
        raise ValueError("step_frames must be positive")

    events = []
    frames_elapsed = 0
    sequence = after_sequence
    while limit == 0 or len(events) < limit:
        event = _poll_matching_event(machine, sequence, event_type_name)
        if event is not None:
            events.append(event)
            sequence = event.sequence_number
            continue
        if frames_elapsed >= timeout_frames:
            break
        frames_to_run = min(step_frames, timeout_frames - frames_elapsed) if timeout_frames else step_frames
        machine.run_frames(frames_to_run)
        frames_elapsed += frames_to_run
    return events


def _format_machine_info(descriptor) -> str:
    return "\n".join(
        [
            f"machine_id: {descriptor.machine_id}",
            f"system_id: {descriptor.system_id}",
            f"model_id: {descriptor.model_id}",
            f"region: {descriptor.region}",
            f"video_standard: {descriptor.video_standard}",
            f"adapter_version: {descriptor.adapter_version}",
            f"configured_memory_bytes: {descriptor.configured_memory_bytes}",
            f"feature_bits: {descriptor.capabilities.feature_bits}",
        ]
    )


def _format_event(event) -> str:
    parts = [
        f"sequence={event.sequence_number}",
        f"type={EventType(event.event_type).name.lower()}",
        f"frame={event.frame.frame_number}",
    ]
    if event.region_id:
        parts.append(f"region={event.region_id}")
    if event.control_id:
        parts.append(f"control={event.control_id}")
    if event.message:
        parts.append(f"message={event.message}")
    return " ".join(parts)


def _render_text_snapshot(snapshot) -> str:
    return "\n".join(
        [
            f"region_id: {snapshot.region_id}",
            f"frame_number: {snapshot.frame_number}",
            "---",
            snapshot.plain,
        ]
    )


def _framebuffer_summary(framebuffer) -> str:
    return "\n".join(
        [
            f"frame_number: {framebuffer.frame.frame_number}",
            f"width: {framebuffer.width}",
            f"height: {framebuffer.height}",
            f"stride_bytes: {framebuffer.stride_bytes}",
            f"pixel_format: {framebuffer.pixel_format}",
        ]
    )


def _framebuffer_render_suffix(framebuffer) -> str:
    preview = _render_framebuffer_preview(framebuffer)
    if not preview:
        return ""
    return "\npreview:\n" + preview


def _render_framebuffer_preview(framebuffer) -> str:
    if int(framebuffer.pixel_format) != 1:
        return ""
    if framebuffer.width <= 0 or framebuffer.height <= 0:
        return ""
    bytes_per_pixel = 4
    if framebuffer.stride_bytes < framebuffer.width * bytes_per_pixel:
        return ""
    rows = []
    for y in range(framebuffer.height):
        row = []
        row_start = y * framebuffer.stride_bytes
        for x in range(framebuffer.width):
            offset = row_start + x * bytes_per_pixel
            pixel = framebuffer.pixels[offset : offset + bytes_per_pixel]
            if len(pixel) < bytes_per_pixel:
                return ""
            row.append(f"{pixel[0]:02x}{pixel[1]:02x}{pixel[2]:02x}")
        rows.append(" ".join(row))
    return "\n".join(rows)


def _print_payload(as_json: bool, payload: dict, plain_text: str) -> int:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(plain_text)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AutomationError as exc:
        raise SystemExit(str(exc)) from exc
