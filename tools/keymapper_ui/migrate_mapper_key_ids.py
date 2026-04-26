from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

MODIFIERS = {"SHIFT", "CTRL", "CONTROL", "ALT", "CAPS"}

ALIASES = {
    "APOSTROPHE": ["'"],
    "BACKSLASH": ["\\"],
    "COMMA": [","],
    "PERIOD": ["."],
    "SEMICOLON": [";"],
    "SLASH": ["/"],
    "MINUS": ["-"],
    "EQUALS": ["="],
    "LEFTBRACKET": ["["],
    "RIGHTBRACKET": ["]"],
    "GRAVE": ["`"],
    "ESCAPE": ["ESC"],
    "BACKSPACE": ["DEL", "CLR"],
    "RETURN": ["ENTER", "RET"],
    "KP_ENTER": ["ENTER", "RET"],
}


def load_yaml(path: Path) -> Dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return data


def build_candidates(mapper_data: Dict) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for key in mapper_data.get("keys", []):
        key_id = str(key.get("id", ""))
        if not key_id:
            continue

        tokens: Set[str] = set()
        for legend in key.get("legend", []) or []:
            if isinstance(legend, str) and legend.strip():
                tokens.add(legend.strip().upper())

        combos = key.get("legend_combos", {}) or {}
        if isinstance(combos, dict):
            for seq in combos.values():
                if not isinstance(seq, list):
                    continue
                for t in seq:
                    if isinstance(t, str) and t.strip() and t.strip().upper() not in MODIFIERS:
                        tokens.add(t.strip().upper())

        for token in tokens:
            out.setdefault(token, []).append(key_id)
    return out


def resolve_mapper_key_id(host_key: str, candidates: Dict[str, List[str]]) -> Optional[str]:
    probe = [host_key]
    probe.extend(ALIASES.get(host_key, []))

    for p in probe:
        ids = candidates.get(p.upper(), [])
        if ids:
            return ids[0]
    return None


def migrate(host_map_path: Path, mapper_path: Path, output_path: Optional[Path]) -> int:
    host_map = load_yaml(host_map_path)
    mapper = load_yaml(mapper_path)

    bindings = host_map.get("keyboard", {}).get("bindings", [])
    if not isinstance(bindings, list):
        raise ValueError("host map keyboard.bindings must be an array")

    candidates = build_candidates(mapper)
    unresolved: List[str] = []
    updated = 0

    for b in bindings:
        if not isinstance(b, dict):
            continue
        host_key = str(b.get("host_key", "")).strip().upper()
        host_scancode = str(b.get("host_scancode", "")).strip().upper()
        if host_scancode.startswith("SDL_SCANCODE_"):
            host_key = host_scancode[len("SDL_SCANCODE_") :]
        elif host_scancode:
            host_key = host_scancode
        if not host_key:
            continue
        if str(b.get("mapper_key_id", "")).strip():
            continue
        mid = resolve_mapper_key_id(host_key, candidates)
        if mid:
            b["mapper_key_id"] = mid
            updated += 1
        else:
            unresolved.append(host_key)

    out_path = output_path or host_map_path
    out_path.write_text(yaml.safe_dump(host_map, sort_keys=False), encoding="utf-8")

    print(f"Updated bindings with mapper_key_id: {updated}")
    if unresolved:
        print(f"Unresolved ({len(unresolved)}): {', '.join(sorted(set(unresolved)))}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Inject mapper_key_id into host keyboard map")
    ap.add_argument("--host-map", required=True)
    ap.add_argument("--mapper", required=True)
    ap.add_argument("--output")
    args = ap.parse_args()

    return migrate(
        host_map_path=Path(args.host_map),
        mapper_path=Path(args.mapper),
        output_path=Path(args.output) if args.output else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
