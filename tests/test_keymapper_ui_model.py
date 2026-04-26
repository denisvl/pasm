from pathlib import Path

import yaml

from tools.keymapper_ui.migrate_mapper_key_ids import migrate
from tools.keymapper_ui.model import KeymapperModel


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_keymapper_model_assign_save_roundtrip(tmp_path):
    mapper = {
        "system_name": "test_system",
        "image": {
            "file": "kbd.png",
            "width_px": 100,
            "height_px": 50,
            "origin": "top-left",
            "bbox_format": {"x": "left", "y": "top", "width": "px", "height": "px"},
            "approximate": True,
            "notes": [],
        },
        "keys": [
            {
                "id": "k_a",
                "row": 1,
                "column": 1,
                "multi_legend": False,
                "legend": ["A"],
                "legend_combos": {"A": ["A"]},
                "bbox": {"x": 1, "y": 2, "width": 10, "height": 10},
            }
        ],
    }
    host_map = {
        "keyboard": {
            "kind": "matrix",
            "focus_required": True,
            "bindings": [{"host_key": "A", "presses": [{"row": 1, "bit": 0}], "mapper_key_id": "k_a"}],
        }
    }

    mapper_path = tmp_path / "mapper.yaml"
    host_map_path = tmp_path / "host_map.yaml"
    _write_yaml(mapper_path, mapper)
    _write_yaml(host_map_path, host_map)

    model = KeymapperModel.load(
        mapper_path=mapper_path,
        host_map_path=host_map_path,
        keymapper_schema_path=Path("schemas/keyboard-keymapper.schema.json"),
        runtime_map_schema_path=Path("schemas/runtime_keyboard_map_schema.json"),
    )
    assert model.validate_links() == []

    model.assign_host_to_mapper("B", "k_a")
    model.set_binding_matrix("B", 2, 3)
    model.save_mapping()

    reloaded = yaml.safe_load(host_map_path.read_text(encoding="utf-8"))
    b = [x for x in reloaded["keyboard"]["bindings"] if x.get("host_scancode") == "B"][0]
    assert b["mapper_key_id"] == "k_a"
    assert b["presses"][0] == {"row": 2, "bit": 3}


def test_keymapper_model_detects_missing_mapper_links(tmp_path):
    mapper = {
        "system_name": "test_system",
        "image": {
            "file": "kbd.png",
            "width_px": 100,
            "height_px": 50,
            "origin": "top-left",
            "bbox_format": {"x": "left", "y": "top", "width": "px", "height": "px"},
            "approximate": True,
            "notes": [],
        },
        "keys": [
            {
                "id": "k_a",
                "row": 1,
                "column": 1,
                "multi_legend": False,
                "legend": ["A"],
                "legend_combos": {"A": ["A"]},
                "bbox": {"x": 1, "y": 2, "width": 10, "height": 10},
            }
        ],
    }
    host_map = {
        "keyboard": {
            "kind": "matrix",
            "focus_required": True,
            "bindings": [{"host_key": "A"}],
        }
    }

    mapper_path = tmp_path / "mapper.yaml"
    host_map_path = tmp_path / "host_map.yaml"
    _write_yaml(mapper_path, mapper)
    _write_yaml(host_map_path, host_map)

    model = KeymapperModel.load(
        mapper_path=mapper_path,
        host_map_path=host_map_path,
        keymapper_schema_path=Path("schemas/keyboard-keymapper.schema.json"),
        runtime_map_schema_path=Path("schemas/runtime_keyboard_map_schema.json"),
    )
    errs = model.validate_links()
    assert errs
    assert "missing mapper_key_id" in errs[0]


def test_migration_injects_mapper_key_ids(tmp_path):
    mapper_path = Path("examples/hosts/cpc464/cpc_keyboard_mapper.yaml")
    host_map_path = tmp_path / "host_keyboard_cpc.yaml"
    host_map_path.write_text(
        Path("examples/hosts/cpc464/host_keyboard_cpc.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    rc = migrate(host_map_path, mapper_path, None)
    assert rc == 0
    migrated = yaml.safe_load(host_map_path.read_text(encoding="utf-8"))
    bindings = migrated["keyboard"]["bindings"]
    assert any(b.get("mapper_key_id") for b in bindings)


def test_add_host_alias_clones_payload_and_persists(tmp_path):
    mapper = {
        "system_name": "test_system",
        "image": {
            "file": "kbd.png",
            "width_px": 100,
            "height_px": 50,
            "origin": "top-left",
            "bbox_format": {"x": "left", "y": "top", "width": "px", "height": "px"},
            "approximate": True,
            "notes": [],
        },
        "keys": [
            {
                "id": "k_a",
                "row": 1,
                "column": 1,
                "multi_legend": False,
                "legend": ["A"],
                "legend_combos": {"A": ["A"]},
                "bbox": {"x": 1, "y": 2, "width": 10, "height": 10},
            }
        ],
    }
    host_map = {
        "keyboard": {
            "kind": "matrix",
            "focus_required": True,
            "bindings": [{"host_key": "A", "presses": [{"row": 1, "bit": 0}], "mapper_key_id": "k_a"}],
        }
    }
    mapper_path = tmp_path / "mapper.yaml"
    host_map_path = tmp_path / "host_map.yaml"
    _write_yaml(mapper_path, mapper)
    _write_yaml(host_map_path, host_map)
    model = KeymapperModel.load(
        mapper_path=mapper_path,
        host_map_path=host_map_path,
        keymapper_schema_path=Path("schemas/keyboard-keymapper.schema.json"),
        runtime_map_schema_path=Path("schemas/runtime_keyboard_map_schema.json"),
    )

    model.add_host_alias("k_a", "B", source_host_key="A")
    alias = model.binding_for_host_key("B")
    assert alias is not None
    assert alias["mapper_key_id"] == "k_a"
    assert alias["presses"][0] == {"row": 1, "bit": 0}


def test_keymapper_model_supports_multi_press_matrix_payload(tmp_path):
    mapper = {
        "system_name": "test_system",
        "image": {
            "file": "kbd.png",
            "width_px": 100,
            "height_px": 50,
            "origin": "top-left",
            "bbox_format": {"x": "left", "y": "top", "width": "px", "height": "px"},
            "approximate": True,
            "notes": [],
        },
        "keys": [
            {
                "id": "k_left",
                "row": 1,
                "column": 1,
                "multi_legend": False,
                "legend": ["LEFT"],
                "legend_combos": {"LEFT": ["LEFT"]},
                "bbox": {"x": 1, "y": 2, "width": 10, "height": 10},
            }
        ],
    }
    host_map = {
        "keyboard": {
            "kind": "matrix",
            "focus_required": True,
            "bindings": [{"host_key": "LEFT", "presses": [{"row": 1, "bit": 0}], "mapper_key_id": "k_left"}],
        }
    }

    mapper_path = tmp_path / "mapper.yaml"
    host_map_path = tmp_path / "host_map.yaml"
    _write_yaml(mapper_path, mapper)
    _write_yaml(host_map_path, host_map)

    model = KeymapperModel.load(
        mapper_path=mapper_path,
        host_map_path=host_map_path,
        keymapper_schema_path=Path("schemas/keyboard-keymapper.schema.json"),
        runtime_map_schema_path=Path("schemas/runtime_keyboard_map_schema.json"),
    )
    model.set_binding_presses("LEFT", [{"row": 2, "bit": 3}, {"row": 7, "bit": 1}])
    model.save_mapping()

    reloaded = yaml.safe_load(host_map_path.read_text(encoding="utf-8"))
    b = [x for x in reloaded["keyboard"]["bindings"] if x.get("host_scancode") == "LEFT"][0]
    assert b["presses"] == [{"row": 2, "bit": 3}, {"row": 7, "bit": 1}]


def test_remove_alias_keeps_other_aliases(tmp_path):
    mapper = {
        "system_name": "test_system",
        "image": {
            "file": "kbd.png",
            "width_px": 100,
            "height_px": 50,
            "origin": "top-left",
            "bbox_format": {"x": "left", "y": "top", "width": "px", "height": "px"},
            "approximate": True,
            "notes": [],
        },
        "keys": [
            {
                "id": "k_a",
                "row": 1,
                "column": 1,
                "multi_legend": False,
                "legend": ["A"],
                "legend_combos": {"A": ["A"]},
                "bbox": {"x": 1, "y": 2, "width": 10, "height": 10},
            }
        ],
    }
    host_map = {
        "keyboard": {
            "kind": "matrix",
            "focus_required": True,
            "bindings": [
                {"host_key": "A", "presses": [{"row": 1, "bit": 0}], "mapper_key_id": "k_a"},
                {"host_key": "B", "presses": [{"row": 1, "bit": 0}], "mapper_key_id": "k_a"},
            ],
        }
    }
    mapper_path = tmp_path / "mapper.yaml"
    host_map_path = tmp_path / "host_map.yaml"
    _write_yaml(mapper_path, mapper)
    _write_yaml(host_map_path, host_map)
    model = KeymapperModel.load(
        mapper_path=mapper_path,
        host_map_path=host_map_path,
        keymapper_schema_path=Path("schemas/keyboard-keymapper.schema.json"),
        runtime_map_schema_path=Path("schemas/runtime_keyboard_map_schema.json"),
    )

    assert model.remove_host_binding("A")
    assert model.binding_for_host_key("A") is None
    assert model.binding_for_host_key("B") is not None
    assert len(model.bindings_for_mapper_key("k_a")) == 1


def test_validate_links_rejects_duplicate_host_key_entries(tmp_path):
    mapper = {
        "system_name": "test_system",
        "image": {
            "file": "kbd.png",
            "width_px": 100,
            "height_px": 50,
            "origin": "top-left",
            "bbox_format": {"x": "left", "y": "top", "width": "px", "height": "px"},
            "approximate": True,
            "notes": [],
        },
        "keys": [
            {
                "id": "k_a",
                "row": 1,
                "column": 1,
                "multi_legend": False,
                "legend": ["A"],
                "legend_combos": {"A": ["A"]},
                "bbox": {"x": 1, "y": 2, "width": 10, "height": 10},
            }
        ],
    }
    host_map = {
        "keyboard": {
            "kind": "matrix",
            "focus_required": True,
            "bindings": [
                {"host_key": "A", "presses": [{"row": 1, "bit": 0}], "mapper_key_id": "k_a"},
                {"host_key": "A", "presses": [{"row": 1, "bit": 1}], "mapper_key_id": "k_a"},
            ],
        }
    }
    mapper_path = tmp_path / "mapper.yaml"
    host_map_path = tmp_path / "host_map.yaml"
    _write_yaml(mapper_path, mapper)
    _write_yaml(host_map_path, host_map)
    model = KeymapperModel.load(
        mapper_path=mapper_path,
        host_map_path=host_map_path,
        keymapper_schema_path=Path("schemas/keyboard-keymapper.schema.json"),
        runtime_map_schema_path=Path("schemas/runtime_keyboard_map_schema.json"),
    )
    errs = model.validate_links()
    assert any("duplicate host entry" in e for e in errs)


def test_validate_links_accepts_fixed_emulator_key_id(tmp_path):
    mapper = {
        "system_name": "test_system",
        "image": {
            "file": "kbd.png",
            "width_px": 100,
            "height_px": 50,
            "origin": "top-left",
            "bbox_format": {"x": "left", "y": "top", "width": "px", "height": "px"},
            "approximate": True,
            "notes": [],
        },
        "keys": [
            {
                "id": "k_a",
                "row": 1,
                "column": 1,
                "multi_legend": False,
                "legend": ["A"],
                "legend_combos": {"A": ["A"]},
                "bbox": {"x": 1, "y": 2, "width": 10, "height": 10},
            }
        ],
    }
    host_map = {
        "keyboard": {
            "kind": "matrix",
            "focus_required": True,
            "bindings": [{"host_key": "F12", "presses": [{"row": 1, "bit": 0}], "emulator_key_id": "EMU_RESET"}],
        }
    }
    mapper_path = tmp_path / "mapper.yaml"
    host_map_path = tmp_path / "host_map.yaml"
    _write_yaml(mapper_path, mapper)
    _write_yaml(host_map_path, host_map)
    model = KeymapperModel.load(
        mapper_path=mapper_path,
        host_map_path=host_map_path,
        keymapper_schema_path=Path("schemas/keyboard-keymapper.schema.json"),
        runtime_map_schema_path=Path("schemas/runtime_keyboard_map_schema.json"),
    )
    assert model.validate_links() == []


def test_validate_links_rejects_undefined_system_key_id(tmp_path):
    mapper = {
        "system_name": "test_system",
        "image": {
            "file": "kbd.png",
            "width_px": 100,
            "height_px": 50,
            "origin": "top-left",
            "bbox_format": {"x": "left", "y": "top", "width": "px", "height": "px"},
            "approximate": True,
            "notes": [],
        },
        "keys": [
            {
                "id": "k_a",
                "row": 1,
                "column": 1,
                "multi_legend": False,
                "legend": ["A"],
                "legend_combos": {"A": ["A"]},
                "bbox": {"x": 1, "y": 2, "width": 10, "height": 10},
            }
        ],
    }
    host_map = {
        "keyboard": {
            "kind": "matrix",
            "focus_required": True,
            "bindings": [{"host_key": "F1", "presses": [{"row": 1, "bit": 0}], "system_key_id": "SYS_FOO"}],
        }
    }
    mapper_path = tmp_path / "mapper.yaml"
    host_map_path = tmp_path / "host_map.yaml"
    _write_yaml(mapper_path, mapper)
    _write_yaml(host_map_path, host_map)
    model = KeymapperModel.load(
        mapper_path=mapper_path,
        host_map_path=host_map_path,
        keymapper_schema_path=Path("schemas/keyboard-keymapper.schema.json"),
        runtime_map_schema_path=Path("schemas/runtime_keyboard_map_schema.json"),
    )
    errs = model.validate_links()
    assert any("system_key_id 'SYS_FOO'" in e for e in errs)
    assert any("no system keys defined" in e for e in errs)


def test_validate_links_accepts_declared_system_key_id(tmp_path):
    mapper = {
        "system_name": "test_system",
        "image": {
            "file": "kbd.png",
            "width_px": 100,
            "height_px": 50,
            "origin": "top-left",
            "bbox_format": {"x": "left", "y": "top", "width": "px", "height": "px"},
            "approximate": True,
            "notes": [],
        },
        "keys": [
            {
                "id": "k_a",
                "row": 1,
                "column": 1,
                "multi_legend": False,
                "legend": ["A"],
                "legend_combos": {"A": ["A"]},
                "bbox": {"x": 1, "y": 2, "width": 10, "height": 10},
            }
        ],
    }
    host_map = {
        "keyboard": {
            "kind": "matrix",
            "focus_required": True,
            "system_keys": ["SYS_FOO", "SYS_BAR"],
            "bindings": [{"host_key": "F1", "presses": [{"row": 1, "bit": 0}], "system_key_id": "SYS_FOO"}],
        }
    }
    mapper_path = tmp_path / "mapper.yaml"
    host_map_path = tmp_path / "host_map.yaml"
    _write_yaml(mapper_path, mapper)
    _write_yaml(host_map_path, host_map)
    model = KeymapperModel.load(
        mapper_path=mapper_path,
        host_map_path=host_map_path,
        keymapper_schema_path=Path("schemas/keyboard-keymapper.schema.json"),
        runtime_map_schema_path=Path("schemas/runtime_keyboard_map_schema.json"),
    )
    assert model.validate_links() == []
