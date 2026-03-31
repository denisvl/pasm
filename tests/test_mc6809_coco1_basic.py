import pathlib
import uuid

import yaml

from src import generator as gen_mod
from src.parser import yaml_loader


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _make_workdir(prefix: str) -> pathlib.Path:
    root = BASE_DIR / "generated" / "_pytest_work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


def test_mc6809_yaml_validates():
    data = yaml_loader.load_processor_system(
        str(BASE_DIR / "examples" / "processors" / "mc6809.yaml"),
        str(BASE_DIR / "examples" / "systems" / "mc6809" / "mc6809_default.yaml"),
    )
    assert data["metadata"]["name"] == "MC6809"
    assert data["interrupts"]["model"] == "mc6809"
    names = {inst["name"] for inst in data["instructions"]}
    assert "EXEC" not in names
    assert {"NOP", "LDA_IMM", "LDB_IMM", "BRA_REL", "JSR_EXT", "RTS"} <= names


def test_coco1_interactive_stack_validates():
    data = yaml_loader.load_processor_system(
        str(BASE_DIR / "examples" / "processors" / "mc6809.yaml"),
        str(BASE_DIR / "examples" / "systems" / "coco1" / "coco1_interactive.yaml"),
        ic_paths=[str(BASE_DIR / "examples" / "ics" / "coco1" / "coco1_peripherals.yaml")],
        device_paths=[
            str(BASE_DIR / "examples" / "devices" / "coco1" / "coco_keyboard.yaml"),
            str(BASE_DIR / "examples" / "devices" / "coco1" / "coco_video.yaml"),
            str(BASE_DIR / "examples" / "devices" / "coco1" / "coco_speaker.yaml"),
        ],
        host_paths=[str(BASE_DIR / "examples" / "hosts" / "coco1" / "coco_host_hal_interactive.yaml")],
        cartridge_path=str(
            BASE_DIR / "examples" / "cartridges" / "coco1" / "coco_mapper_none.yaml"
        ),
        cartridge_rom_path=str(BASE_DIR / "examples" / "roms" / "coco1" / "coco.rom"),
    )
    assert data["system"]["metadata"]["name"] == "MC6809CoCo1InteractiveSystem"
    assert data["cartridge"]["metadata"]["id"] == "coco_cart0"
    assert data["cartridge_rom"]["path"].endswith("examples\\roms\\coco1\\coco.rom") or data[
        "cartridge_rom"
    ]["path"].endswith("examples/roms/coco1/coco.rom")
    assert data["ics"][0]["metadata"]["model"] == "motorola_mc6883_sam_with_dual_pia"
    state_names = {s["name"] for s in data["ics"][0].get("state", [])}
    assert {"sam_ctrl", "sam_vdg_mode", "sam_display_base", "sam_all_ram"} <= state_names
    assert {
        "pia0_ora", "pia0_orb", "pia0_ddra", "pia0_ddrb", "pia0_cra", "pia0_crb",
        "pia1_ora", "pia1_orb", "pia1_ddra", "pia1_ddrb", "pia1_cra", "pia1_crb",
    } <= state_names
    video = next(d for d in data["devices"] if d["metadata"]["id"] == "video_coco")
    assert video["metadata"]["model"] == "motorola_mc6847_vdg"
    speaker = next(d for d in data["devices"] if d["metadata"]["id"] == "speaker_coco")
    assert speaker["metadata"]["model"] == "coco1_dac6_pcm_bridge"


def test_coco1_keyboard_wiring_and_bindings():
    data = yaml_loader.load_processor_system(
        str(BASE_DIR / "examples" / "processors" / "mc6809.yaml"),
        str(BASE_DIR / "examples" / "systems" / "coco1" / "coco1_interactive.yaml"),
        ic_paths=[str(BASE_DIR / "examples" / "ics" / "coco1" / "coco1_peripherals.yaml")],
        device_paths=[
            str(BASE_DIR / "examples" / "devices" / "coco1" / "coco_keyboard.yaml"),
            str(BASE_DIR / "examples" / "devices" / "coco1" / "coco_video.yaml"),
            str(BASE_DIR / "examples" / "devices" / "coco1" / "coco_speaker.yaml"),
        ],
        host_paths=[str(BASE_DIR / "examples" / "hosts" / "coco1" / "coco_host_hal_interactive.yaml")],
        cartridge_path=str(
            BASE_DIR / "examples" / "cartridges" / "coco1" / "coco_mapper_none.yaml"
        ),
        cartridge_rom_path=str(BASE_DIR / "examples" / "roms" / "coco1" / "coco.rom"),
    )

    host = next(comp for comp in data["hosts"] if comp["metadata"]["id"] == "host_coco")
    keyboard = next(comp for comp in data["devices"] if comp["metadata"]["id"] == "keyboard_coco")
    callbacks = {cb["name"] for cb in keyboard["interfaces"]["callbacks"]}
    assert {"read_row", "host_matrix"} <= callbacks
    assert "input" not in host
    host_callbacks = {cb["name"] for cb in host["interfaces"]["callbacks"]}
    assert {"keyboard_matrix", "joystick_axis", "joystick_button"} <= host_callbacks

    keymap_data = yaml.safe_load(
        (BASE_DIR / "examples" / "hosts" / "coco1" / "host_keyboard_coco.yaml").read_text(encoding="utf-8")
    )
    assert keymap_data["keyboard"]["kind"] == "matrix"
    assert keymap_data["keyboard"]["focus_required"] is True

    conn_pairs = {
        (
            conn["from"]["component"],
            conn["from"]["kind"],
            conn["from"]["name"],
            conn["to"]["component"],
            conn["to"]["kind"],
            conn["to"]["name"],
        )
        for conn in data["connections"]
    }
    assert (
        "coco1_io",
        "callback",
        "keyboard_read_row",
        "keyboard_coco",
        "callback",
        "read_row",
    ) in conn_pairs
    assert (
        "keyboard_coco",
        "callback",
        "host_matrix",
        "host_coco",
        "callback",
        "keyboard_matrix",
    ) in conn_pairs
    assert (
        "coco1_io",
        "callback",
        "joystick_read_axis",
        "host_coco",
        "callback",
        "joystick_axis",
    ) in conn_pairs
    assert (
        "coco1_io",
        "callback",
        "joystick_read_button",
        "host_coco",
        "callback",
        "joystick_button",
    ) in conn_pairs

    bindings = keymap_data["keyboard"]["bindings"]
    binding_map = {b["host_key"]: {(p["row"], p["bit"]) for p in b["presses"]} for b in bindings}
    assert (0, 1) in binding_map["A"]
    assert (6, 2) in binding_map["ESCAPE"]
    assert (3, 5) in binding_map["BACKSPACE"]
    assert (3, 5) in binding_map["DELETE"]
    assert (3, 3) in binding_map["UP"]
    assert (3, 4) in binding_map["DOWN"]
    assert (3, 6) in binding_map["RIGHT"]
    assert (3, 7) in binding_map["SPACE"]
    assert (6, 0) in binding_map["RETURN"]
    assert (6, 0) in binding_map["KP_ENTER"]
    assert (5, 5) in binding_map["MINUS"]
    assert {(5, 5), (6, 7)} <= binding_map["EQUALS"]
    assert (4, 7) in binding_map["APOSTROPHE"]
    assert (5, 7) in binding_map["SLASH"]
    assert (6, 7) in binding_map["LSHIFT"]
    assert "KP_MULTIPLY" not in binding_map


def test_generate_mc6809_coco1():
    outdir = _make_workdir("mc6809_coco1_")
    gen_mod.generate(
        str(BASE_DIR / "examples" / "processors" / "mc6809.yaml"),
        str(BASE_DIR / "examples" / "systems" / "coco1" / "coco1_default.yaml"),
        str(outdir),
        ic_paths=[str(BASE_DIR / "examples" / "ics" / "coco1" / "coco1_peripherals.yaml")],
        device_paths=[
            str(BASE_DIR / "examples" / "devices" / "coco1" / "coco_keyboard.yaml"),
            str(BASE_DIR / "examples" / "devices" / "coco1" / "coco_video.yaml"),
            str(BASE_DIR / "examples" / "devices" / "coco1" / "coco_speaker.yaml"),
        ],
        host_paths=[str(BASE_DIR / "examples" / "hosts" / "coco1" / "coco_host_stub.yaml")],
        cartridge_map_path=str(
            BASE_DIR / "examples" / "cartridges" / "coco1" / "coco_mapper_none.yaml"
        ),
        cartridge_rom_path=str(BASE_DIR / "examples" / "roms" / "coco1" / "coco.rom"),
    )

    src_dir = outdir / "src"
    assert (src_dir / "MC6809.c").exists()
    assert (src_dir / "MC6809.h").exists()
    assert (src_dir / "MC6809_decoder.c").exists()
    impl = (src_dir / "MC6809.c").read_text(encoding="utf-8")
    assert "0xFFC0u" in impl
    assert "0xFF00u" in impl and "0xFF03u" in impl
    assert "0xFF20u" in impl and "0xFF23u" in impl
    assert "pia0_cra" in impl and "pia1_cra" in impl
    assert "pia0_ddra" in impl and "pia1_ddra" in impl
    assert "selected_cols" in impl
    assert "pressed_cols" in impl
    assert "sam_display_base" in impl
    assert "sam_all_ram" in impl
    assert "dac8" in impl
    assert "sbs_enabled" in impl
    assert "switch (mode)" in impl
    assert "row_bytes = 16u" in impl and "row_bytes = 32u" in impl
    assert "sam_gm0" in impl
    assert "(raw & 0x80u)" in impl
    assert "(raw & 0x40u)" in impl
