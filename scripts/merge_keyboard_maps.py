#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def _read_lines(p: Path) -> list[str]:
    return p.read_text("utf-8").splitlines(True)


def _extract_bindings_block(lines: list[str]) -> list[str]:
    # Very small, repo-specific extractor:
    # expects:
    # keyboard:
    #   ...
    #   bindings:
    #   - ...
    start = None
    for i, raw in enumerate(lines):
        s = raw.strip()
        if s == "bindings:" or s.startswith("bindings:"):
            start = i + 1
            break
    if start is None:
        return []

    # Copy list items and their indented sublines to EOF.
    out: list[str] = []
    for raw in lines[start:]:
        if raw.strip() == "" and not out:
            continue
        out.append(raw)
    # Normalize: ensure each line is indented exactly 2 spaces for list items.
    # This works because host_keyboard YAML uses 2-space indent for list items.
    norm: list[str] = []
    for raw in out:
        if raw.strip() == "":
            norm.append(raw)
            continue
        # Strip any leading indentation then add two spaces.
        norm.append("  " + raw.lstrip())
    return norm


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: merge_keyboard_maps.py BASE.yaml EXTRA.yaml", file=sys.stderr)
        return 2
    base = Path(argv[1])
    extra = Path(argv[2])
    base_lines = _read_lines(base)
    extra_lines = _read_lines(extra)

    extra_bindings = _extract_bindings_block(extra_lines)
    if not extra_bindings:
        sys.stdout.write("".join(base_lines))
        return 0

    # Just append bindings; loader will validate duplicates and complain early.
    out = list(base_lines)
    if out and not out[-1].endswith("\n"):
        out[-1] += "\n"
    if out and out[-1].strip() != "":
        out.append("\n")
    out.append("# ---- merged bindings from: " + str(extra) + "\n")
    out.extend(extra_bindings)
    sys.stdout.write("".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

