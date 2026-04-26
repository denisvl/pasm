from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

try:
    import jsonschema
except Exception:  # pragma: no cover
    jsonschema = None


def _load_yaml(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


def _save_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _load_schema(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any], label: str) -> None:
    if jsonschema is None:
        return
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        msgs = []
        for err in errors[:20]:
            path = " -> ".join(str(x) for x in err.path) if err.path else "root"
            msgs.append(f"{path}: {err.message}")
        raise ValueError(f"{label} validation failed:\n" + "\n".join(msgs))


@dataclass
class LoadedDocs:
    mapper_path: Path
    host_map_path: Path
    device_path: Optional[Path]
    mapper: Dict[str, Any]
    host_map: Dict[str, Any]
    device: Optional[Dict[str, Any]]


class KeymapperModel:
    FIXED_EMULATOR_KEY_IDS = {
        "EMU_POWER_TOGGLE",
        "EMU_RESET",
        "EMU_PAUSE_TOGGLE",
        "EMU_SAVE_SNAPSHOT",
        "EMU_LOAD_SNAPSHOT",
        "EMU_MUTE_TOGGLE",
        "EMU_VOLUME_UP",
        "EMU_VOLUME_DOWN",
        "EMU_CART_PICKER",
    }
    HOST_ID_ALIASES = {
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
    _MODIFIER_TOKENS = {"SHIFT", "CTRL", "CONTROL", "ALT", "CAPS"}

    def __init__(self, docs: LoadedDocs):
        self.docs = docs
        self.mapper = docs.mapper
        self.host_map = docs.host_map
        self.device = docs.device
        self._normalize_bindings_to_scancodes()

    @staticmethod
    def load(
        mapper_path: Path,
        host_map_path: Path,
        keymapper_schema_path: Path,
        runtime_map_schema_path: Path,
        device_path: Optional[Path] = None,
    ) -> "KeymapperModel":
        mapper = _load_yaml(mapper_path)
        host_map = _load_yaml(host_map_path)
        device = _load_yaml(device_path) if device_path else None

        validate_json_schema(mapper, _load_schema(keymapper_schema_path), "Keymapper")
        validate_json_schema(host_map, _load_schema(runtime_map_schema_path), "Runtime keyboard map")

        docs = LoadedDocs(
            mapper_path=mapper_path,
            host_map_path=host_map_path,
            device_path=device_path,
            mapper=mapper,
            host_map=host_map,
            device=device,
        )
        return KeymapperModel(docs)

    def snapshot(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return copy.deepcopy(self.mapper), copy.deepcopy(self.host_map)

    def restore_snapshot(self, snap: Tuple[Dict[str, Any], Dict[str, Any]]) -> None:
        self.mapper, self.host_map = copy.deepcopy(snap[0]), copy.deepcopy(snap[1])

    def save_mapper(self, path: Optional[Path] = None) -> None:
        _save_yaml(path or self.docs.mapper_path, self.mapper)

    def save_mapping(self, path: Optional[Path] = None) -> None:
        self._normalize_bindings_to_scancodes()
        _save_yaml(path or self.docs.host_map_path, self.host_map)

    def mapper_keys(self) -> List[Dict[str, Any]]:
        return list(self.mapper.get("keys", []))

    def mapper_key_ids(self) -> set[str]:
        return {str(k.get("id", "")) for k in self.mapper_keys() if str(k.get("id", ""))}

    def host_bindings(self) -> List[Dict[str, Any]]:
        return list(self.host_map.get("keyboard", {}).get("bindings", []))

    def _bindings_mut(self) -> List[Dict[str, Any]]:
        return self.host_map.setdefault("keyboard", {}).setdefault("bindings", [])

    def normalize_host_binding_id(self, host_key: str) -> str:
        hk = str(host_key).strip().upper()
        if not hk:
            raise ValueError("host key/scancode cannot be empty")
        return hk

    def _binding_host_id_or_empty(self, binding: Dict[str, Any]) -> str:
        hs = str(binding.get("host_scancode", "")).strip().upper()
        if hs:
            return self.normalize_host_binding_id(hs)
        hk = str(binding.get("host_key", "")).strip().upper()
        if hk:
            return self.normalize_host_binding_id(hk)
        return ""

    def binding_host_id(self, binding: Dict[str, Any]) -> str:
        return self._binding_host_id_or_empty(binding)

    def binding_host_label(self, binding: Dict[str, Any]) -> str:
        hid = self._binding_host_id_or_empty(binding)
        return hid

    def _normalize_bindings_to_scancodes(self) -> None:
        for b in self._bindings_mut():
            hid = self._binding_host_id_or_empty(b)
            if not hid:
                continue
            b["host_scancode"] = hid
            b.pop("host_key", None)
            self._canonicalize_binding_order(b)

    @staticmethod
    def _canonicalize_binding_order(binding: Dict[str, Any]) -> None:
        preferred = [
            "host_scancode",
            "mapper_key_id",
            "emulator_key_id",
            "system_key_id",
            "presses",
            "ascii",
            "ascii_shift",
            "ascii_ctrl",
        ]
        ordered: Dict[str, Any] = {}
        for key in preferred:
            if key in binding:
                ordered[key] = binding[key]
        for key, value in list(binding.items()):
            if key not in ordered:
                ordered[key] = value
        binding.clear()
        binding.update(ordered)

    def ensure_host_binding(self, host_key: str) -> Dict[str, Any]:
        host_scancode = self.normalize_host_binding_id(host_key)
        bindings = self._bindings_mut()
        for b in bindings:
            if self._binding_host_id_or_empty(b) == host_scancode:
                return b
        b = {"host_scancode": host_scancode}
        bindings.append(b)
        return b

    def binding_for_host_key(self, host_key: str) -> Optional[Dict[str, Any]]:
        host_scancode = self.normalize_host_binding_id(host_key)
        for b in self.host_bindings():
            if self._binding_host_id_or_empty(b) == host_scancode:
                return b
        return None

    def bindings_for_mapper_key(self, mapper_key_id: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for b in self.host_bindings():
            if self.binding_mapper_key_id(b) == mapper_key_id:
                out.append(b)
        return out

    def binding_mapper_key_id(self, binding: Dict[str, Any]) -> str:
        explicit = str(binding.get("mapper_key_id", "")).strip()
        if explicit:
            return explicit
        inferred = self._infer_mapper_key_id_from_binding(binding)
        return inferred or ""

    def assign_host_to_mapper(self, host_key: str, mapper_key_id: str) -> None:
        binding = self.ensure_host_binding(host_key)
        binding["mapper_key_id"] = mapper_key_id

    def _copy_payload_fields(self, source: Dict[str, Any], dest: Dict[str, Any]) -> bool:
        copied = False
        if "presses" in source:
            presses = source.get("presses")
            if isinstance(presses, list):
                dest["presses"] = copy.deepcopy(presses)
                dest.pop("ascii", None)
                dest.pop("ascii_shift", None)
                dest.pop("ascii_ctrl", None)
                copied = True
        if any(k in source for k in ("ascii", "ascii_shift", "ascii_ctrl")):
            dest.pop("presses", None)
            for k in ("ascii", "ascii_shift", "ascii_ctrl"):
                if k in source:
                    dest[k] = int(source[k])
                else:
                    dest.pop(k, None)
            copied = True
        return copied

    def add_host_alias(
        self,
        mapper_key_id: str,
        host_key: str,
        source_host_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        host_key = self.normalize_host_binding_id(host_key)
        if not host_key:
            raise ValueError("host_key cannot be empty")
        if not mapper_key_id:
            raise ValueError("mapper_key_id cannot be empty")

        binding = self.ensure_host_binding(host_key)
        binding["mapper_key_id"] = mapper_key_id

        def _has_payload(binding: Dict[str, Any]) -> bool:
            return (
                ("presses" in binding and isinstance(binding.get("presses"), list) and bool(binding.get("presses")))
                or any(k in binding for k in ("ascii", "ascii_shift", "ascii_ctrl"))
            )

        source: Optional[Dict[str, Any]] = None
        if source_host_key:
            candidate = self.binding_for_host_key(source_host_key)
            if candidate is not None and _has_payload(candidate):
                source = candidate

        if source is None:
            same_key = self.bindings_for_mapper_key(mapper_key_id)
            fallback: Optional[Dict[str, Any]] = None
            for candidate in same_key:
                if self._binding_host_id_or_empty(candidate) != host_key:
                    if _has_payload(candidate):
                        source = candidate
                        break
                    if fallback is None:
                        fallback = candidate
            if source is None:
                source = fallback

        has_payload = _has_payload(binding)
        if not has_payload and source is not None:
            self._copy_payload_fields(source, binding)

        has_payload = _has_payload(binding)
        # Allow creating alias first, then setting matrix/ascii payload afterward.
        # Validation/save path still enforces consistency before persisting.
        return binding

    def remove_host_binding(self, host_key: str) -> bool:
        bindings = self._bindings_mut()
        hk = self.normalize_host_binding_id(host_key)
        for i, b in enumerate(bindings):
            if self._binding_host_id_or_empty(b) == hk:
                del bindings[i]
                return True
        return False

    def set_binding_matrix(self, host_key: str, row: int, bit: int) -> None:
        binding = self.ensure_host_binding(host_key)
        binding.pop("ascii", None)
        binding.pop("ascii_shift", None)
        binding.pop("ascii_ctrl", None)
        binding["presses"] = [{"row": int(row), "bit": int(bit)}]

    def set_binding_presses(self, host_key: str, presses: List[Dict[str, int]]) -> None:
        """Set matrix presses payload (supports multi-press bindings).

        `presses` is a list of {"row": int, "bit": int} dicts.
        """
        if not isinstance(presses, list) or not presses:
            raise ValueError("presses must be a non-empty list")
        for p in presses:
            if not isinstance(p, dict):
                raise ValueError("each press must be a dict")
            if "row" not in p or "bit" not in p:
                raise ValueError("each press must include row and bit")
        binding = self.ensure_host_binding(host_key)
        binding.pop("ascii", None)
        binding.pop("ascii_shift", None)
        binding.pop("ascii_ctrl", None)
        binding["presses"] = [{"row": int(p["row"]), "bit": int(p["bit"])} for p in presses]

    def set_binding_ascii(
        self,
        host_key: str,
        ascii_value: Optional[int],
        ascii_shift: Optional[int],
        ascii_ctrl: Optional[int],
    ) -> None:
        binding = self.ensure_host_binding(host_key)
        binding.pop("presses", None)
        for key, value in (
            ("ascii", ascii_value),
            ("ascii_shift", ascii_shift),
            ("ascii_ctrl", ascii_ctrl),
        ):
            if value is None:
                binding.pop(key, None)
            else:
                binding[key] = int(value)

    def set_mapper_bbox(self, mapper_key_id: str, x: int, y: int, width: int, height: int) -> None:
        for key in self.mapper_keys():
            if str(key.get("id", "")) == mapper_key_id:
                key["bbox"] = {
                    "x": int(x),
                    "y": int(y),
                    "width": int(width),
                    "height": int(height),
                }
                return
        raise KeyError(f"Unknown mapper key: {mapper_key_id}")

    def set_mapper_legend(self, mapper_key_id: str, legends: List[str]) -> None:
        for key in self.mapper_keys():
            if str(key.get("id", "")) == mapper_key_id:
                key["legend"] = legends
                key["multi_legend"] = len(legends) > 1
                return
        raise KeyError(f"Unknown mapper key: {mapper_key_id}")

    def key_overlay_color(self, mapper_key_id: str) -> Optional[Tuple[int, int, int]]:
        for key in self.mapper_keys():
            if str(key.get("id", "")) == mapper_key_id:
                color = key.get("overlay_color")
                if (
                    isinstance(color, list)
                    and len(color) == 3
                    and all(isinstance(v, int) for v in color)
                ):
                    return int(color[0]), int(color[1]), int(color[2])
                return None
        return None

    def set_mapper_overlay_color(self, mapper_key_id: str, r: int, g: int, b: int) -> None:
        for key in self.mapper_keys():
            if str(key.get("id", "")) == mapper_key_id:
                key["overlay_color"] = [int(r), int(g), int(b)]
                return
        raise KeyError(f"Unknown mapper key: {mapper_key_id}")

    def validate_links(self) -> List[str]:
        ids = self.mapper_key_ids()
        errors: List[str] = []
        seen_host_keys: set[str] = set()
        system_key_ids = self._defined_system_key_ids()
        for b in self.host_bindings():
            hk = self._binding_host_id_or_empty(b)
            if hk in seen_host_keys:
                errors.append(f"host_scancode {hk}: duplicate host entry")
            else:
                seen_host_keys.add(hk)
            if not hk:
                errors.append("binding missing host_scancode")
                continue
            mid = str(b.get("mapper_key_id", "")).strip()
            eid = str(b.get("emulator_key_id", "")).strip()
            sid = str(b.get("system_key_id", "")).strip()
            present = [name for name, val in (("mapper_key_id", mid), ("emulator_key_id", eid), ("system_key_id", sid)) if val]
            has_payload = (
                ("presses" in b and isinstance(b.get("presses"), list) and bool(b.get("presses")))
                or any(k in b for k in ("ascii", "ascii_shift", "ascii_ctrl"))
            )
            if not present:
                if not has_payload:
                    errors.append(
                        f"host_scancode {hk}: missing mapper_key_id "
                        f"(or emulator_key_id/system_key_id)"
                    )
                continue
            if len(present) > 1:
                errors.append(f"host_scancode {hk}: multiple target ids set ({', '.join(present)})")
                continue
            if mid and mid not in ids:
                errors.append(f"host_scancode {hk}: mapper_key_id '{mid}' not found in keymapper")
            if eid and eid not in self.FIXED_EMULATOR_KEY_IDS:
                allowed = ", ".join(sorted(self.FIXED_EMULATOR_KEY_IDS))
                errors.append(f"host_scancode {hk}: emulator_key_id '{eid}' is invalid (allowed: {allowed})")
            if sid:
                if not system_key_ids:
                    errors.append(
                        f"host_scancode {hk}: system_key_id '{sid}' is not allowed (no system keys defined)"
                    )
                elif sid not in system_key_ids:
                    allowed = ", ".join(sorted(system_key_ids))
                    errors.append(
                        f"host_scancode {hk}: system_key_id '{sid}' is invalid (allowed: {allowed})"
                    )
        return errors

    def _defined_system_key_ids(self) -> set[str]:
        out: set[str] = set()

        keyboard_cfg = self.host_map.get("keyboard", {})
        out.update(self._extract_string_ids(keyboard_cfg.get("system_keys")))

        if isinstance(self.device, dict):
            out.update(self._extract_string_ids(self.device.get("system_keys")))
            meta = self.device.get("metadata")
            if isinstance(meta, dict):
                out.update(self._extract_string_ids(meta.get("system_keys")))
        return out

    def defined_system_key_ids(self) -> set[str]:
        return set(self._defined_system_key_ids())

    def set_binding_target(self, host_key: str, target_kind: str, target_id: str) -> None:
        hk = self.normalize_host_binding_id(host_key)
        kind = str(target_kind).strip().lower()
        tid = str(target_id).strip()
        if not hk:
            raise ValueError("host_key cannot be empty")
        if not tid:
            raise ValueError("target_id cannot be empty")
        binding = self.ensure_host_binding(hk)
        binding.pop("mapper_key_id", None)
        binding.pop("emulator_key_id", None)
        binding.pop("system_key_id", None)
        if kind == "mapper":
            binding["mapper_key_id"] = tid
            return
        if kind == "emulator":
            if tid not in self.FIXED_EMULATOR_KEY_IDS:
                allowed = ", ".join(sorted(self.FIXED_EMULATOR_KEY_IDS))
                raise ValueError(f"invalid emulator_key_id '{tid}' (allowed: {allowed})")
            binding["emulator_key_id"] = tid
            return
        if kind == "system":
            # Auto-register unknown system keys so the user can map and then edit metadata in UI.
            if tid not in self._defined_system_key_ids():
                self.upsert_host_system_key(tid, False)
            binding["system_key_id"] = tid
            return
        raise ValueError("target_kind must be one of: mapper, emulator, system")

    def host_system_keys(self) -> List[Dict[str, Any]]:
        keyboard_cfg = self.host_map.setdefault("keyboard", {})
        return self._extract_system_key_entries(keyboard_cfg.get("system_keys"))

    def upsert_host_system_key(self, key_id: str, visual_feedback: bool) -> None:
        kid = str(key_id).strip()
        if not kid:
            raise ValueError("system key id cannot be empty")
        keyboard_cfg = self.host_map.setdefault("keyboard", {})
        entries = self._extract_system_key_entries(keyboard_cfg.get("system_keys"))
        for e in entries:
            if str(e.get("id", "")).strip() == kid:
                e["visual_feedback"] = bool(visual_feedback)
                keyboard_cfg["system_keys"] = entries
                return
        entries.append({"id": kid, "visual_feedback": bool(visual_feedback)})
        keyboard_cfg["system_keys"] = entries

    def remove_host_system_key(self, key_id: str) -> bool:
        kid = str(key_id).strip()
        if not kid:
            return False
        keyboard_cfg = self.host_map.setdefault("keyboard", {})
        entries = self._extract_system_key_entries(keyboard_cfg.get("system_keys"))
        kept = [e for e in entries if str(e.get("id", "")).strip() != kid]
        if len(kept) == len(entries):
            return False
        if kept:
            keyboard_cfg["system_keys"] = kept
        else:
            keyboard_cfg.pop("system_keys", None)
        return True

    def rename_host_system_key(self, old_key_id: str, new_key_id: str) -> None:
        old_id = str(old_key_id).strip()
        new_id = str(new_key_id).strip()
        if not old_id or not new_id:
            raise ValueError("system key id cannot be empty")
        if old_id == new_id:
            return

        keyboard_cfg = self.host_map.setdefault("keyboard", {})
        entries = self._extract_system_key_entries(keyboard_cfg.get("system_keys"))
        if not any(str(e.get("id", "")).strip() == old_id for e in entries):
            raise ValueError(f"system key '{old_id}' not found")
        if any(str(e.get("id", "")).strip() == new_id for e in entries):
            raise ValueError(f"system key '{new_id}' already exists")

        for e in entries:
            if str(e.get("id", "")).strip() == old_id:
                e["id"] = new_id
                break
        keyboard_cfg["system_keys"] = entries

        # Keep bindings targeting this system key in sync.
        for b in self._bindings_mut():
            if str(b.get("system_key_id", "")).strip() == old_id:
                b["system_key_id"] = new_id

        # Preserve bbox-edit convention for UI-created system keys.
        if new_id not in self.mapper_key_ids():
            for key in self.mapper_keys():
                if str(key.get("id", "")).strip() != old_id:
                    continue
                if str(key.get("section", "")).strip() == "system":
                    key["id"] = new_id
                break

    def system_key_visual_feedback(self, key_id: str) -> bool:
        kid = str(key_id).strip()
        if not kid:
            return False
        for entry in self.host_system_keys():
            if str(entry.get("id", "")).strip() == kid:
                return bool(entry.get("visual_feedback", False))
        for entry in self._extract_system_key_entries(
            (self.device or {}).get("system_keys") if isinstance(self.device, dict) else None
        ):
            if str(entry.get("id", "")).strip() == kid:
                return bool(entry.get("visual_feedback", False))
        if isinstance(self.device, dict):
            meta = self.device.get("metadata")
            for entry in self._extract_system_key_entries(meta.get("system_keys") if isinstance(meta, dict) else None):
                if str(entry.get("id", "")).strip() == kid:
                    return bool(entry.get("visual_feedback", False))
        return False

    @staticmethod
    def _extract_string_ids(value: Any) -> set[str]:
        out: set[str] = set()
        if not isinstance(value, list):
            return out
        for item in value:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    out.add(s)
                continue
            if isinstance(item, dict):
                for key in ("id", "key_id", "key", "name"):
                    v = item.get(key)
                    if isinstance(v, str) and v.strip():
                        out.add(v.strip())
                        break
        return out

    @staticmethod
    def _extract_system_key_entries(value: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not isinstance(value, list):
            return out
        for item in value:
            if isinstance(item, str):
                sid = item.strip()
                if sid:
                    out.append({"id": sid, "visual_feedback": False})
                continue
            if not isinstance(item, dict):
                continue
            sid = None
            for k in ("id", "key_id", "key", "name"):
                v = item.get(k)
                if isinstance(v, str) and v.strip():
                    sid = v.strip()
                    break
            if not sid:
                continue
            out.append(
                {
                    "id": sid,
                    "visual_feedback": bool(item.get("visual_feedback", False)),
                }
            )
        # Keep first occurrence order, drop duplicates by id.
        seen: set[str] = set()
        dedup: List[Dict[str, Any]] = []
        for e in out:
            sid = str(e.get("id", "")).strip()
            if not sid or sid in seen:
                continue
            seen.add(sid)
            dedup.append(e)
        return dedup

    def key_bbox(self, mapper_key_id: str) -> Optional[Dict[str, int]]:
        for key in self.mapper_keys():
            if str(key.get("id", "")) == mapper_key_id:
                bbox = key.get("bbox")
                if isinstance(bbox, dict):
                    return {
                        "x": int(bbox.get("x", 0)),
                        "y": int(bbox.get("y", 0)),
                        "width": int(bbox.get("width", 0)),
                        "height": int(bbox.get("height", 0)),
                    }
        return None

    def _mapper_legend_candidates(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for key in self.mapper_keys():
            key_id = str(key.get("id", "")).strip()
            if not key_id:
                continue
            tokens: set[str] = set()
            for legend in key.get("legend", []) or []:
                if isinstance(legend, str) and legend.strip():
                    tokens.add(legend.strip().upper())
            combos = key.get("legend_combos", {}) or {}
            if isinstance(combos, dict):
                for seq in combos.values():
                    if not isinstance(seq, list):
                        continue
                    for token in seq:
                        if not isinstance(token, str):
                            continue
                        t = token.strip().upper()
                        if t and t not in self._MODIFIER_TOKENS:
                            tokens.add(t)
            for token in tokens:
                out.setdefault(token, []).append(key_id)
        return out

    def _infer_mapper_key_id_from_binding(self, binding: Dict[str, Any]) -> Optional[str]:
        hid = self._binding_host_id_or_empty(binding)
        if not hid:
            return None
        candidates = self._mapper_legend_candidates()
        probe = [hid]
        probe.extend(self.HOST_ID_ALIASES.get(hid, []))
        for token in probe:
            ids = candidates.get(str(token).strip().upper(), [])
            if ids:
                return ids[0]
        return None

    def mapping_kind(self) -> str:
        return str(self.host_map.get("keyboard", {}).get("kind", "matrix"))
