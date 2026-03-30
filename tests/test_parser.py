import pathlib
import subprocess
import sys

import pytest
import yaml
from src.parser import yaml_loader
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def test_minimal8_loads_and_validates():
    processor_path, system_path = example_pair("minimal8")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))
    assert data["metadata"]["name"] == "Minimal8"
    assert data["memory"]["address_bits"] == 16
    assert len(data["instructions"]) > 0


def test_simple8_loads_and_validates():
    processor_path, system_path = example_pair("simple8")
    data = yaml_loader.load_processor_system(str(processor_path), str(system_path))
    assert data["metadata"]["name"] == "Simple8"
    assert len(data["registers"]) >= 8
    assert any(inst["name"] == "HALT" for inst in data["instructions"])


def test_processor_requires_metadata_codegen():
    processor_path, _ = example_pair("minimal8")
    processor_data = yaml.safe_load(processor_path.read_text(encoding="utf-8"))
    processor_data["metadata"].pop("codegen", None)
    loader = yaml_loader.ProcessorSystemLoader()
    with pytest.raises(Exception, match="metadata.*codegen|Processor validation failed"):
        loader.validate_processor(processor_data)


def test_processor_rejects_invalid_codegen_numeric_style():
    processor_path, _ = example_pair("minimal8")
    processor_data = yaml.safe_load(processor_path.read_text(encoding="utf-8"))
    processor_data["metadata"]["codegen"]["numeric_style"] = "bad_style"
    loader = yaml_loader.ProcessorSystemLoader()
    with pytest.raises(Exception, match="numeric_style|Processor validation failed"):
        loader.validate_processor(processor_data)


def test_processor_rejects_formatter_not_enabled_by_codegen():
    processor_path, _ = example_pair("minimal8")
    processor_data = yaml.safe_load(processor_path.read_text(encoding="utf-8"))
    processor_data["metadata"]["codegen"]["display_kinds_enabled"] = []
    processor_data["instructions"][0]["display_template"] = "NOP {imm:mc6809_idx}"
    processor_data["instructions"][0]["encoding"]["fields"] = [
        {"name": "imm", "position": [15, 8], "type": "immediate"}
    ]
    loader = yaml_loader.ProcessorSystemLoader()
    with pytest.raises(Exception, match="not enabled|display_kinds_enabled"):
        loader.validate_processor(processor_data)


def test_system_reset_delay_seconds_is_loaded():
    processor_path, system_path = example_pair("z80", "trs80_model4_interactive.yaml")
    data = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        ic_paths=[
            str(
                BASE_DIR
                / "examples"
                / "ics"
                / "trs80_model4"
                / "trs80_model4_peripherals.yaml"
            )
        ],
        device_paths=[
            str(BASE_DIR / "examples" / "devices" / "trs80_model4" / "trs80_keyboard.yaml"),
            str(BASE_DIR / "examples" / "devices" / "trs80_model4" / "trs80_video.yaml"),
            str(BASE_DIR / "examples" / "devices" / "trs80_model4" / "trs80_speaker.yaml"),
        ],
        host_paths=[
            str(
                BASE_DIR
                / "examples"
                / "hosts"
                / "trs80_model4"
                / "trs80_host_hal_interactive.yaml"
            )
        ],
    )
    assert data["system"]["reset_delay_seconds"] == 5


def test_single_file_loader_is_removed():
    with pytest.raises(RuntimeError, match="no longer supported"):
        yaml_loader.load_isa("examples/simple8.yaml")


def test_system_requires_clock_hz(tmp_path):
    processor_path, _ = example_pair("minimal8")
    bad_system = tmp_path / "bad_system.yaml"
    bad_system.write_text(
        (
            "metadata:\n"
            "  name: MissingClock\n"
            "memory:\n"
            "  default_size: 65536\n"
            "components:\n"
            "  ics: []\n"
            "  devices: []\n"
            "  hosts: []\n"
            "connections: []\n"
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="clock_hz"):
        yaml_loader.load_processor_system(str(processor_path), str(bad_system))


def test_system_rejects_unknown_hook_names(tmp_path):
    processor_path, _ = example_pair("minimal8")
    bad_system = tmp_path / "bad_hook_system.yaml"
    bad_system.write_text(
        (
            "metadata:\n"
            "  name: BadHooks\n"
            "clock_hz: 1000000\n"
            "memory:\n"
            "  default_size: 65536\n"
            "components:\n"
            "  ics: []\n"
            "  devices: []\n"
            "  hosts: []\n"
            "connections: []\n"
            "hooks:\n"
            "  invalid_hook:\n"
            "    enabled: true\n"
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="invalid_hook|unsupported hook"):
        yaml_loader.load_processor_system(str(processor_path), str(bad_system))


def test_composition_rejects_memory_outside_address_space(tmp_path):
    processor_path, system_path = example_pair("minimal8")
    system_text = pathlib.Path(system_path).read_text(encoding="utf-8")
    oversized = system_text.replace("default_size: 65536", "default_size: 131072")
    bad_system = tmp_path / "oversized_system.yaml"
    bad_system.write_text(oversized, encoding="utf-8")
    with pytest.raises(Exception, match="exceeds processor address space"):
        yaml_loader.load_processor_system(str(processor_path), str(bad_system))


def test_cli_rejects_single_file_flag():
    proc = subprocess.run(
        [sys.executable, "-m", "src.main", "validate", "--isa", "examples/simple8.yaml"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "single-file ISA input was removed" in proc.stderr


def test_system_rejects_legacy_literal_host_component(tmp_path):
    processor_path, _ = example_pair("z80")
    bad_system = tmp_path / "bad_host_literal.yaml"
    bad_system.write_text(
        (
            "metadata:\n"
            "  name: BadHostLiteral\n"
            "clock_hz: 1000000\n"
            "memory:\n"
            "  default_size: 65536\n"
            "components:\n"
            "  ics: []\n"
            "  devices: []\n"
            "  hosts: [host0]\n"
            "connections:\n"
            "  - from:\n"
            "      component: host\n"
            "      kind: callback\n"
            "      name: bad\n"
            "    to:\n"
            "      component: host0\n"
            "      kind: callback\n"
            "      name: ok\n"
        ),
        encoding="utf-8",
    )
    host = tmp_path / "host.yaml"
    host.write_text(
            (
                "metadata:\n"
                "  id: host0\n"
                "  type: host\n"
                "  model: test\n"
                "backend:\n"
                "  target: sdl2\n"
                "state: []\n"
                "interfaces:\n"
                "  callbacks:\n"
                "    - name: ok\n"
            "      args: []\n"
            "      returns: u8\n"
            "  handlers: []\n"
            "  signals: []\n"
            "behavior:\n"
            "  snippets: {}\n"
            "  callback_handlers:\n"
            "    ok: |\n"
            "      return 0;\n"
            "  handler_bodies: {}\n"
            "coding:\n"
            "  headers: []\n"
            "  include_paths: []\n"
            "  linked_libraries: []\n"
            "  library_paths: []\n"
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="literal component 'host' is removed"):
        yaml_loader.load_processor_system(
            str(processor_path),
            str(bad_system),
            host_paths=[str(host)],
        )


def test_system_rom_images_validate_region_and_file(tmp_path):
    processor_path, _ = example_pair("minimal8")
    rom_path = tmp_path / "rom.bin"
    rom_path.write_bytes(b"\xAA\x55\xCC\x33")
    system = tmp_path / "rom_system.yaml"
    system.write_text(
        (
            "metadata:\n"
            "  name: RomSystem\n"
            "clock_hz: 1000000\n"
            "memory:\n"
            "  default_size: 65536\n"
            "  regions:\n"
            "    - name: ROM\n"
            "      start: 0x8000\n"
            "      size: 0x4000\n"
            "      read_only: true\n"
            "  rom_images:\n"
            "    - name: test_rom\n"
            f"      file: {rom_path.name}\n"
            "      target_region: ROM\n"
            "      offset: 2\n"
            "components:\n"
            "  ics: []\n"
            "  devices: []\n"
            "  hosts: []\n"
            "connections: []\n"
        ),
        encoding="utf-8",
    )
    data = yaml_loader.load_processor_system(str(processor_path), str(system))
    rom_images = data["memory"]["rom_images"]
    assert len(rom_images) == 1
    assert rom_images[0]["address"] == 0x8002
    assert rom_images[0]["size"] == 4


def _write_cartridge_yaml(path: pathlib.Path, cart_id: str = "sms_cart0") -> pathlib.Path:
    cart_path = path / "cart.yaml"
    cart_path.write_text(
        (
            "metadata:\n"
            f"  id: {cart_id}\n"
            "  type: cartridge_mapper\n"
            "  model: test_mapper\n"
            "state:\n"
            "  - name: rom_data\n"
            "    type: uint8_t *\n"
            "    initial: \"NULL\"\n"
            "  - name: rom_size\n"
            "    type: uint32_t\n"
            "    initial: \"0\"\n"
            "interfaces:\n"
            "  callbacks: []\n"
            "  handlers: []\n"
            "  signals: []\n"
            "maps:\n"
            "  memory:\n"
            "    ranges:\n"
            "      - start: 0\n"
            "        size: 49152\n"
            "        access: [read]\n"
            "behavior:\n"
            "  snippets:\n"
            "    mem_read_pre: |\n"
            "      if (addr < 0xC000u && comp->rom_data != NULL && comp->rom_size > 0u) {\n"
            "          uint32_t off = (uint32_t)addr;\n"
            "          if (off < comp->rom_size) return comp->rom_data[off];\n"
            "          return 0xFFu;\n"
            "      }\n"
            "  callback_handlers: {}\n"
            "  handler_bodies: {}\n"
            "coding:\n"
            "  headers: []\n"
            "  include_paths: []\n"
            "  linked_libraries: []\n"
            "  library_paths: []\n"
        ),
        encoding="utf-8",
    )
    return cart_path


def _write_cartridge_system_yaml(path: pathlib.Path, cart_id: str = "sms_cart0") -> pathlib.Path:
    system_path = path / "cart_system.yaml"
    system_path.write_text(
        (
            "metadata:\n"
            "  name: CartSystem\n"
            "clock_hz: 3579545\n"
            "memory:\n"
            "  default_size: 65536\n"
            "  regions:\n"
            "    - name: BIOS\n"
            "      start: 0x0000\n"
            "      size: 0x8000\n"
            "      read_only: true\n"
            "    - name: RAM\n"
            "      start: 0x8000\n"
            "      size: 0x8000\n"
            "      read_write: true\n"
            "components:\n"
            "  ics: []\n"
            "  devices: []\n"
            "  hosts: []\n"
            f"  cartridge: {cart_id}\n"
            "connections: []\n"
        ),
        encoding="utf-8",
    )
    return system_path


def test_cartridge_system_requires_map_and_rom(tmp_path):
    processor_path, _ = example_pair("z80")
    system_path = _write_cartridge_system_yaml(tmp_path, "sms_cart0")
    cart_path = _write_cartridge_yaml(tmp_path, "sms_cart0")
    cart_rom = tmp_path / "cart.rom"
    cart_rom.write_bytes(bytes([0x00, 0x01, 0x02, 0x03]))

    loaded = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        cartridge_path=str(cart_path),
        cartridge_rom_path=str(cart_rom),
    )
    assert loaded["cartridge"]["metadata"]["id"] == "sms_cart0"
    assert loaded["cartridge_rom"]["path"]


def test_cartridge_system_allows_no_cartridge_args(tmp_path):
    processor_path, _ = example_pair("z80")
    system_path = _write_cartridge_system_yaml(tmp_path, "sms_cart0")

    loaded = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
    )
    assert loaded["cartridge"] == {}
    assert loaded["cartridge_rom"]["path"] == ""


def test_cartridge_system_rejects_missing_rom_argument(tmp_path):
    processor_path, _ = example_pair("z80")
    system_path = _write_cartridge_system_yaml(tmp_path, "sms_cart0")
    cart_path = _write_cartridge_yaml(tmp_path, "sms_cart0")

    with pytest.raises(Exception, match="requires --cartridge-rom"):
        yaml_loader.load_processor_system(
            str(processor_path),
            str(system_path),
            cartridge_path=str(cart_path),
        )


def test_cartridge_system_rejects_rom_without_map(tmp_path):
    processor_path, _ = example_pair("z80")
    system_path = _write_cartridge_system_yaml(tmp_path, "sms_cart0")
    cart_rom = tmp_path / "cart.rom"
    cart_rom.write_bytes(b"\x00")

    with pytest.raises(Exception, match="requires --cartridge-map when --cartridge-rom is provided"):
        yaml_loader.load_processor_system(
            str(processor_path),
            str(system_path),
            cartridge_rom_path=str(cart_rom),
        )


def test_non_cartridge_system_rejects_cartridge_args(tmp_path):
    processor_path, system_path = example_pair("z80")
    cart_path = _write_cartridge_yaml(tmp_path, "sms_cart0")
    cart_rom = tmp_path / "cart.rom"
    cart_rom.write_bytes(b"\x00")

    with pytest.raises(Exception, match="no cartridge slot"):
        yaml_loader.load_processor_system(
            str(processor_path),
            str(system_path),
            cartridge_path=str(cart_path),
            cartridge_rom_path=str(cart_rom),
        )


def test_cartridge_component_id_must_match_system_slot(tmp_path):
    processor_path, _ = example_pair("z80")
    system_path = _write_cartridge_system_yaml(tmp_path, "sms_cart0")
    cart_path = _write_cartridge_yaml(tmp_path, "other_cart")
    cart_rom = tmp_path / "cart.rom"
    cart_rom.write_bytes(b"\x00")

    with pytest.raises(Exception, match="must match loaded --cartridge-map metadata.id"):
        yaml_loader.load_processor_system(
            str(processor_path),
            str(system_path),
            cartridge_path=str(cart_path),
            cartridge_rom_path=str(cart_rom),
        )


def _write_portmap_ic(
    path: pathlib.Path,
    comp_id: str,
    read_map: list[tuple[int, int]] | None = None,
    write_map: list[tuple[int, int]] | None = None,
) -> pathlib.Path:
    read_map = read_map or []
    write_map = write_map or []
    ic_path = path / f"{comp_id}.yaml"
    lines = [
        "metadata:",
        f"  id: {comp_id}",
        "  type: io_component",
        "  model: test",
        "state: []",
        "interfaces:",
        "  callbacks: []",
        "  handlers: []",
        "  signals: []",
        "maps:",
        "  ports:",
        "    read:",
    ]
    if read_map:
        for idx, (mask, value) in enumerate(read_map):
            lines.extend(
                [
                    f"      - name: r{idx}",
                    f"        mask: 0x{mask:04X}",
                    f"        value: 0x{value:04X}",
                ]
            )
    else:
        lines.append("      []")
    lines.append("    write:")
    if write_map:
        for idx, (mask, value) in enumerate(write_map):
            lines.extend(
                [
                    f"      - name: w{idx}",
                    f"        mask: 0x{mask:04X}",
                    f"        value: 0x{value:04X}",
                ]
            )
    else:
        lines.append("      []")
    lines.extend(
        [
            "behavior:",
            "  snippets: {}",
            "  callback_handlers: {}",
            "  handler_bodies: {}",
            "coding:",
            "  headers: []",
            "  include_paths: []",
            "  linked_libraries: []",
            "  library_paths: []",
        ]
    )
    ic_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ic_path


def _write_component_system_yaml(path: pathlib.Path, ic_ids: list[str]) -> pathlib.Path:
    system_path = path / "component_system.yaml"
    lines = [
        "metadata:",
        "  name: ComponentPortMapSystem",
        "clock_hz: 3579545",
        "memory:",
        "  default_size: 65536",
        "components:",
        "  ics:",
    ]
    for ic_id in ic_ids:
        lines.append(f"    - {ic_id}")
    lines.extend(
        [
            "  devices: []",
            "  hosts: []",
            "connections: []",
        ]
    )
    system_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return system_path


def test_port_overlap_allows_read_write_share_same_port(tmp_path):
    processor_path, _ = example_pair("z80")
    system_path = _write_component_system_yaml(tmp_path, ["reader", "writer"])
    reader = _write_portmap_ic(tmp_path, "reader", read_map=[(0x00C1, 0x0040)])
    writer = _write_portmap_ic(tmp_path, "writer", write_map=[(0x00C1, 0x0040)])

    loaded = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        ic_paths=[str(reader), str(writer)],
    )
    assert loaded["components"]["ics"] == ["reader", "writer"]
    assert [ic["metadata"]["id"] for ic in loaded["ics"]] == ["reader", "writer"]


def test_port_overlap_rejects_same_direction(tmp_path):
    processor_path, _ = example_pair("z80")
    system_path = _write_component_system_yaml(tmp_path, ["reader_a", "reader_b"])
    reader_a = _write_portmap_ic(tmp_path, "reader_a", read_map=[(0x00C1, 0x0040)])
    reader_b = _write_portmap_ic(tmp_path, "reader_b", read_map=[(0x00C1, 0x0040)])

    with pytest.raises(Exception, match="port mapping overlap \\(read\\)"):
        yaml_loader.load_processor_system(
            str(processor_path),
            str(system_path),
            ic_paths=[str(reader_a), str(reader_b)],
        )


def _write_processor_variant(tmp_path, transform):
    processor_path, system_path = example_pair("minimal8")
    processor_data = yaml.safe_load(pathlib.Path(processor_path).read_text(encoding="utf-8"))
    transform(processor_data)
    out_processor = tmp_path / "processor.yaml"
    out_processor.write_text(yaml.safe_dump(processor_data, sort_keys=False), encoding="utf-8")
    return out_processor, system_path


def test_processor_display_template_validation_accepts_known_fields(tmp_path):
    def _transform(data):
        data["instructions"][0]["display_template"] = "NOP {opcode:hex8}"

    processor_file, system_path = _write_processor_variant(tmp_path, _transform)
    loaded = yaml_loader.load_processor_system(str(processor_file), str(system_path))
    assert loaded["instructions"][0]["display_template"] == "NOP {opcode:hex8}"


def test_processor_display_template_accepts_mc6809_stack_mask_formatter(tmp_path):
    def _transform(data):
        data["metadata"]["codegen"]["display_kinds_enabled"] = ["mc6809_pshs_mask"]
        data["instructions"][0]["encoding"]["length"] = 2
        data["instructions"][0]["encoding"]["fields"] = [
            {"name": "mask", "position": [15, 8], "type": "immediate"}
        ]
        data["instructions"][0]["display_template"] = "PSHS {mask:mc6809_pshs_mask}"

    processor_file, system_path = _write_processor_variant(tmp_path, _transform)
    loaded = yaml_loader.load_processor_system(str(processor_file), str(system_path))
    assert (
        loaded["instructions"][0]["display_template"]
        == "PSHS {mask:mc6809_pshs_mask}"
    )


def test_processor_display_template_rejects_unknown_field(tmp_path):
    def _transform(data):
        data["instructions"][0]["display_template"] = "NOP {unknown_field}"

    processor_file, system_path = _write_processor_variant(tmp_path, _transform)
    with pytest.raises(Exception, match="unknown decoded field"):
        yaml_loader.load_processor_system(str(processor_file), str(system_path))


def test_processor_display_template_rejects_unknown_formatter(tmp_path):
    def _transform(data):
        data["instructions"][0]["display_template"] = "NOP {opcode:nope}"

    processor_file, system_path = _write_processor_variant(tmp_path, _transform)
    with pytest.raises(Exception, match="formatter 'nope' is not supported"):
        yaml_loader.load_processor_system(str(processor_file), str(system_path))


def test_processor_display_operands_table_requires_non_empty_table(tmp_path):
    def _transform(data):
        data["instructions"][0]["display_template"] = "NOP {opcode:table}"
        data["instructions"][0]["display_operands"] = {
            "opcode": {
                "kind": "table",
                "table": [],
            }
        }

    processor_file, system_path = _write_processor_variant(tmp_path, _transform)
    with pytest.raises(Exception, match="non-empty"):
        yaml_loader.load_processor_system(str(processor_file), str(system_path))


def _base_host_with_keyboard_input():
    return {
        "metadata": {"id": "host_hal", "type": "host_adapter", "model": "test"},
        "state": [],
        "interfaces": {"callbacks": [], "handlers": [], "signals": []},
        "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
        "coding": {
            "headers": [],
            "include_paths": [],
            "linked_libraries": [],
            "library_paths": [],
        },
        "input": {
            "keyboard": {
                "focus_required": True,
                "bindings": [
                    {
                        "host_key": "A",
                        "presses": [{"row": 1, "bit": 0}],
                    }
                ],
            }
        },
    }


def _write_host_yaml(
    path: pathlib.Path, host_id: str, backend_target: str | None = None
) -> pathlib.Path:
    host_path = path / f"{host_id}.yaml"
    host_data = {
        "metadata": {"id": host_id, "type": "host_adapter", "model": f"{host_id}_model"},
        "state": [],
        "interfaces": {"callbacks": [], "handlers": [], "signals": []},
        "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
        "coding": {
            "headers": [],
            "include_paths": [],
            "linked_libraries": [],
            "library_paths": [],
        },
    }
    if backend_target is not None:
        host_data["backend"] = {"target": backend_target}
    host_path.write_text(yaml.safe_dump(host_data, sort_keys=False), encoding="utf-8")
    return host_path


def _write_host_yaml_without_backend(path: pathlib.Path, host_id: str, model: str) -> pathlib.Path:
    host_path = path / f"{host_id}.yaml"
    host_data = {
        "metadata": {"id": host_id, "type": "host_adapter", "model": model},
        "state": [],
        "interfaces": {"callbacks": [], "handlers": [], "signals": []},
        "behavior": {"snippets": {}, "callback_handlers": {}, "handler_bodies": {}},
        "coding": {
            "headers": [],
            "include_paths": [],
            "linked_libraries": [],
            "library_paths": [],
        },
    }
    host_path.write_text(yaml.safe_dump(host_data, sort_keys=False), encoding="utf-8")
    return host_path


def _write_host_system_yaml(path: pathlib.Path, host_ids: list[str]) -> pathlib.Path:
    system_path = path / "host_system.yaml"
    lines = [
        "metadata:",
        "  name: HostSystem",
        "clock_hz: 1000000",
        "memory:",
        "  default_size: 65536",
        "components:",
        "  ics: []",
        "  devices: []",
        "  hosts:",
    ]
    for host_id in host_ids:
        lines.append(f"    - {host_id}")
    lines.append("connections: []")
    system_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return system_path


def test_host_keyboard_input_validation_accepts_valid_mapping():
    loader = yaml_loader.ProcessorSystemLoader()
    host_data = _base_host_with_keyboard_input()
    validated = loader.validate_host(host_data)
    assert validated["input"]["keyboard"]["bindings"][0]["host_key"] == "A"


def test_host_keyboard_input_validation_accepts_explicit_host_key_source():
    loader = yaml_loader.ProcessorSystemLoader()
    host_data = _base_host_with_keyboard_input()
    host_data["input"]["keyboard"]["source"] = "host_key"
    validated = loader.validate_host(host_data)
    assert validated["input"]["keyboard"]["source"] == "host_key"


def test_host_keyboard_input_validation_rejects_legacy_sdl_source():
    loader = yaml_loader.ProcessorSystemLoader()
    host_data = _base_host_with_keyboard_input()
    host_data["input"]["keyboard"]["source"] = "sdl_scancode"
    with pytest.raises(Exception, match="source.*not one of \\['host_key'\\]"):
        loader.validate_host(host_data)


def test_host_keyboard_input_validation_rejects_legacy_sdl_host_key_token():
    loader = yaml_loader.ProcessorSystemLoader()
    host_data = _base_host_with_keyboard_input()
    host_data["input"]["keyboard"]["bindings"][0]["host_key"] = "SDL_SCANCODE_A"
    with pytest.raises(Exception, match="must be canonical"):
        loader.validate_host(host_data)


def test_host_keyboard_input_validation_rejects_duplicate_host_key():
    loader = yaml_loader.ProcessorSystemLoader()
    host_data = _base_host_with_keyboard_input()
    host_data["input"]["keyboard"]["bindings"].append(
        {"host_key": "A", "presses": [{"row": 0, "bit": 0}]}
    )
    with pytest.raises(Exception, match="duplicate host_key"):
        loader.validate_host(host_data)


def test_host_keyboard_input_validation_rejects_invalid_canonical_host_key():
    loader = yaml_loader.ProcessorSystemLoader()
    host_data = _base_host_with_keyboard_input()
    host_data["input"]["keyboard"]["bindings"][0]["host_key"] = "A-key"
    with pytest.raises(Exception, match="host_key.*does not match '\\^\\[A-Z0-9_\\]\\+\\$'|must be canonical"):
        loader.validate_host(host_data)


def test_host_keyboard_input_validation_rejects_unknown_scancode():
    loader = yaml_loader.ProcessorSystemLoader()
    host_data = _base_host_with_keyboard_input()
    host_data["input"]["keyboard"]["bindings"][0]["host_key"] = "UNKNOWN_X"
    with pytest.raises(Exception, match="not supported"):
        loader.validate_host(host_data)


def test_host_keyboard_input_validation_rejects_out_of_range_press():
    loader = yaml_loader.ProcessorSystemLoader()
    host_data = _base_host_with_keyboard_input()
    host_data["input"]["keyboard"]["bindings"][0]["presses"] = [{"row": 32, "bit": 0}]
    with pytest.raises(Exception, match="maximum of 31|row out of range"):
        loader.validate_host(host_data)


def test_host_backend_allows_omitted_target():
    loader = yaml_loader.ProcessorSystemLoader()
    host_data = _base_host_with_keyboard_input()
    host_data.pop("backend", None)
    validated = loader.validate_host(host_data)
    assert "backend" not in validated


def test_host_backend_accepts_explicit_target():
    loader = yaml_loader.ProcessorSystemLoader()
    host_data = _base_host_with_keyboard_input()
    host_data["backend"] = {"target": "sdl2"}
    validated = loader.validate_host(host_data)
    assert validated["backend"]["target"] == "sdl2"


def test_host_backend_rejects_invalid_target_format():
    loader = yaml_loader.ProcessorSystemLoader()
    host_data = _base_host_with_keyboard_input()
    host_data["backend"] = {"target": "SDL-2"}
    with pytest.raises(Exception, match="backend -> target|\\^\\[a-z\\]\\[a-z0-9_\\]\\*\\$"):
        loader.validate_host(host_data)


def test_compose_requires_explicit_host_backend_selection(tmp_path):
    processor_path, _ = example_pair("z80")
    system_path = _write_host_system_yaml(tmp_path, ["host_sdl", "host_stub"])
    host_sdl = _write_host_yaml(tmp_path, "host_sdl", backend_target="sdl2")
    host_stub = _write_host_yaml(tmp_path, "host_stub", backend_target="stub")

    with pytest.raises(Exception, match="multiple host backend targets"):
        yaml_loader.load_processor_system(
            str(processor_path),
            str(system_path),
            host_paths=[str(host_sdl), str(host_stub)],
        )


def test_compose_accepts_single_host_backend_target(tmp_path):
    processor_path, _ = example_pair("z80")
    system_path = _write_host_system_yaml(tmp_path, ["host_a", "host_b"])
    host_a = _write_host_yaml(tmp_path, "host_a")
    host_b = _write_host_yaml(tmp_path, "host_b")

    loaded = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        host_paths=[str(host_a), str(host_b)],
        host_backend_target="sdl2",
    )
    assert len(loaded["hosts"]) == 2
    assert loaded["host_backend_target"] == "sdl2"


def test_compose_does_not_infer_backend_target_from_host_model_name(tmp_path):
    processor_path, _ = example_pair("z80")
    system_path = _write_host_system_yaml(tmp_path, ["host_model_sdl2"])
    host_model_sdl2 = _write_host_yaml_without_backend(tmp_path, "host_model_sdl2", "test_host_hal")

    loaded = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        host_paths=[str(host_model_sdl2)],
    )
    assert loaded["host_backend_target"] == ""

