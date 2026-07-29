from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from src import generator as gen_mod


BASE_DIR = Path(__file__).resolve().parents[1]
SYSTEMS_DIR = BASE_DIR / "examples" / "systems"
PROCESSORS_DIR = BASE_DIR / "examples" / "processors"
SCRIPTS_DIR = BASE_DIR / "scripts"

NON_STANDALONE_SYSTEMS = {
    "examples/systems/c1541/c1541_default.yaml": (
        "Drive-side 1541 scaffold depends on nested C64 subsystem bridge glue and is not a standalone compile target."
    ),
    "examples/systems/keymapper_tool/keymapper_tool_interactive.yaml": (
        "Keymapper host-HAL scaffold embeds raw SDL event/render code and is only exercised via its dedicated interactive generation script, not the generic stub-host compile sweep."
    ),
}


@dataclass(frozen=True)
class CompileCase:
    system_path: Path
    processor_path: Path
    ic_paths: tuple[Path, ...]
    device_paths: tuple[Path, ...]
    host_paths: tuple[Path, ...]
    host_backend_target: str | None
    cartridge_map_path: Path | None
    cartridge_rom_path: str | None

    @property
    def case_id(self) -> str:
        return self.system_path.relative_to(BASE_DIR).as_posix()


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _component_index(root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for path in sorted(root.rglob("*.yaml")):
        data = _load_yaml(path)
        comp_id = str((data.get("metadata") or {}).get("id", "")).strip()
        if not comp_id:
            continue
        index.setdefault(comp_id, []).append(path)
    return index


IC_INDEX = _component_index(BASE_DIR / "examples" / "ics")
DEVICE_INDEX = _component_index(BASE_DIR / "examples" / "devices")
HOST_INDEX = _component_index(BASE_DIR / "examples" / "hosts")


def _choose_host_path(paths: list[Path]) -> Path:
    preferred_tokens = ("stub", "headless", "bridge")
    for token in preferred_tokens:
        for path in paths:
            haystack = path.as_posix().lower()
            if token in haystack:
                return path
    return paths[0]


def _choose_component_path(paths: list[Path]) -> Path:
    non_common = [path for path in paths if "/common/" not in path.as_posix()]
    if non_common:
        return non_common[0]
    return paths[0]


def _host_id_aliases(component_id: str) -> list[str]:
    cid = str(component_id).strip()
    if not cid:
        return []
    aliases = [cid]
    if cid.endswith("_stub"):
        aliases.append(cid[: -len("_stub")])
    else:
        aliases.append(f"{cid}_stub")
    if cid.endswith("_sdl2"):
        aliases.append(cid[: -len("_sdl2")])
    else:
        aliases.append(f"{cid}_sdl2")
    return aliases


def _resolve_component_paths(ids: list[str], index: dict[str, list[Path]], kind: str) -> tuple[Path, ...]:
    resolved: list[Path] = []
    missing: list[str] = []
    for comp_id in ids:
        paths = index.get(comp_id, [])
        if not paths and kind == "host":
            for alias in _host_id_aliases(comp_id):
                paths = index.get(alias, [])
                if paths:
                    break
        if not paths:
            missing.append(comp_id)
            continue
        resolved.append(_choose_host_path(paths) if kind == "host" else _choose_component_path(paths))
    if missing:
        raise AssertionError(f"Missing {kind} definitions for ids: {', '.join(sorted(missing))}")
    return tuple(resolved)


def _parse_script_inventory() -> dict[str, dict[str, str]]:
    inventory: dict[str, dict[str, str]] = {}
    script_paths = sorted(SCRIPTS_DIR.glob("run_*_debugger.bat")) + sorted(
        path
        for path in SCRIPTS_DIR.glob("run_*_debugger.sh")
        if path.name != "run_generated_debugger.sh"
    )
    script_paths.append(SCRIPTS_DIR / "run_sms_bios_debugger.sh")
    script_paths.append(SCRIPTS_DIR / "run_keymapper_ui_host_hal_scaffold.sh")

    system_pattern = re.compile(r"examples/systems/[^\"'\r\n )]+\.yaml")
    processor_pattern = re.compile(
        r'(?:set "PROCESSOR=|PROCESSOR=")(examples/processors/[^"\r\n]+\.yaml)'
    )
    cartridge_map_pattern = re.compile(
        r'(?:set "CARTRIDGE_MAP=|CARTRIDGE_MAP="\$\{CARTRIDGE_MAP:-|CARTRIDGE_MAP=")(examples/cartridges/[^"\r\n}]+\.yaml)'
    )
    cartridge_rom_pattern = re.compile(
        r'(?:set "CARTRIDGE_ROM_GEN=|CARTRIDGE_ROM_GEN="\$\{CARTRIDGE_ROM_GEN:-|CARTRIDGE_ROM_GEN=")([^"\r\n}]+)'
    )

    for script_path in script_paths:
        if not script_path.exists():
            continue
        text = script_path.read_text(encoding="utf-8", errors="ignore")
        processor_match = processor_pattern.search(text)
        if not processor_match:
            continue
        processor = processor_match.group(1)
        cartridge_map_match = cartridge_map_pattern.search(text)
        cartridge_rom_match = cartridge_rom_pattern.search(text)
        payload = {
            "processor": processor,
            "cartridge_map": cartridge_map_match.group(1) if cartridge_map_match else "",
            "cartridge_rom": cartridge_rom_match.group(1) if cartridge_rom_match else "",
        }
        for system in system_pattern.findall(text):
            inventory[system] = payload
    return inventory


SCRIPT_INVENTORY = _parse_script_inventory()


FALLBACK_PROCESSORS = {
    "examples/systems/keymapper_tool/keymapper_tool_interactive.yaml": "examples/processors/mos6502.yaml",
    "examples/systems/minimal8/minimal8_default.yaml": "examples/processors/minimal8.yaml",
    "examples/systems/simple8/simple8_default.yaml": "examples/processors/simple8.yaml",
    "examples/systems/simple_cpu/simple_cpu_default.yaml": "examples/processors/simple_cpu.yaml",
}

FALLBACK_PROCESSORS_BY_DIR = {
    "apple2": "examples/processors/mos6502.yaml",
    "apple2plus": "examples/processors/mos6502.yaml",
    "atari2600": "examples/processors/mos6502.yaml",
    "atari65xe": "examples/processors/mos6502.yaml",
    "atari800xe": "examples/processors/mos6502.yaml",
    "atari800xl": "examples/processors/mos6502.yaml",
    "bbcmicro": "examples/processors/mos6502.yaml",
    "c1541": "examples/processors/mos6502.yaml",
    "c64": "examples/processors/mos6510.yaml",
    "c64c": "examples/processors/mos6510.yaml",
    "coco1": "examples/processors/mc6809.yaml",
    "coco2": "examples/processors/mc6809.yaml",
    "csx64": "examples/processors/mos6510.yaml",
    "famicom": "examples/processors/ricoh2a03.yaml",
    "mc6809": "examples/processors/mc6809.yaml",
    "mos6502": "examples/processors/mos6502.yaml",
    "mos6509": "examples/processors/mos6509.yaml",
    "mos6510": "examples/processors/mos6510.yaml",
    "msx1": "examples/processors/z80.yaml",
    "msx1_expanded": "examples/processors/z80.yaml",
    "nes": "examples/processors/ricoh2a03.yaml",
    "sg1000": "examples/processors/z80.yaml",
    "sg1000ii": "examples/processors/z80.yaml",
    "sm3": "examples/processors/z80.yaml",
    "sms": "examples/processors/z80.yaml",
    "sms2": "examples/processors/z80.yaml",
    "tdp100": "examples/processors/mc6809.yaml",
    "trs80_model4": "examples/processors/z80.yaml",
    "z80": "examples/processors/z80.yaml",
    "zx_spectrum48k": "examples/processors/z80.yaml",
}

FALLBACK_CARTRIDGE_BY_DIR = {
    "atari2600": (
        "examples/cartridges/atari2600/atari2600_mapper_none.yaml",
        "../../roms/atari2600/Pitfall! (1982) (Activision) [!].a26",
    ),
    "atari800xl": (
        "examples/cartridges/atari800xl/atari800xl_cart_8k_none.yaml",
        "../../roms/atari800xl/Star_Raiders_1979_Atari_US.rom",
    ),
    "c64": (
        "examples/cartridges/c64/c64_cart_auto.yaml",
        "../../roms/c64/basic.901226-01.bin",
    ),
    "c64c": (
        "examples/cartridges/c64/c64_cart_auto.yaml",
        "../../roms/c64/basic.901226-01.bin",
    ),
    "csx64": (
        "examples/cartridges/c64/c64_cart_auto.yaml",
        "../../roms/c64/basic.901226-01.bin",
    ),
    "coco1": (
        "examples/cartridges/coco1/coco_mapper_none.yaml",
        "../../roms/coco1/Downland V1.1 (1983) (26-3046) (Tandy) [a1].ccc",
    ),
    "coco2": (
        "examples/cartridges/coco1/coco_mapper_none.yaml",
        "../../roms/coco1/Downland V1.1 (1983) (26-3046) (Tandy) [a1].ccc",
    ),
    "famicom": (
        "examples/cartridges/famicom/famicom_mapper_auto.yaml",
        "../../roms/famicom/1942 (Japan, USA).nes",
    ),
    "msx1": (
        "examples/cartridges/msx1/msx_mapper_konami.yaml",
        "../../roms/msx1/Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom",
    ),
    "msx1_expanded": (
        "examples/cartridges/msx1_expanded/msx_mapper_konami_expanded.yaml",
        "../../roms/msx1/Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom",
    ),
    "nes": (
        "examples/cartridges/nes/nes_mapper_auto.yaml",
        "../../roms/nes/Super Mario Bros. + Duck Hunt (USA).nes",
    ),
    "sg1000": (
        "examples/cartridges/sg1000/sg1000_mapper_none.yaml",
        "../../roms/sg1000/Hang-On II (Japan).sg",
    ),
    "sg1000ii": (
        "examples/cartridges/sg1000/sg1000_mapper_none.yaml",
        "../../roms/sg1000/Hang-On II (Japan).sg",
    ),
    "sm3": (
        "examples/cartridges/sms/sms_mapper_sega.yaml",
        "../../roms/sms/Sonic The Hedgehog (USA, Europe).sms",
    ),
    "sms": (
        "examples/cartridges/sms/sms_mapper_sega.yaml",
        "../../roms/sms/Sonic The Hedgehog (USA, Europe).sms",
    ),
    "sms2": (
        "examples/cartridges/sms/sms_mapper_sega.yaml",
        "../../roms/sms/Sonic The Hedgehog (USA, Europe).sms",
    ),
    "tdp100": (
        "examples/cartridges/coco1/coco_mapper_none.yaml",
        "../../roms/coco1/Downland V1.1 (1983) (26-3046) (Tandy) [a1].ccc",
    ),
}


def _looks_resolved_path(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return "${" not in text and not text.endswith(":-")


def _processor_for_system(system_rel: str) -> Path:
    scripted = SCRIPT_INVENTORY.get(system_rel, {}).get("processor", "")
    processor_rel = scripted or FALLBACK_PROCESSORS.get(system_rel, "")
    if not processor_rel:
        system_dir = Path(system_rel).parent.name
        processor_rel = FALLBACK_PROCESSORS_BY_DIR.get(system_dir, "")
    if not processor_rel:
        raise AssertionError(f"No processor mapping found for {system_rel}")
    path = BASE_DIR / processor_rel
    if not path.exists():
        raise AssertionError(f"Processor path does not exist for {system_rel}: {processor_rel}")
    return path


def _cartridge_args_for_system(system_rel: str, system_data: dict) -> tuple[Path | None, str | None]:
    cartridge_id = str((system_data.get("components") or {}).get("cartridge", "")).strip()
    if not cartridge_id:
        return None, None
    scripted = SCRIPT_INVENTORY.get(system_rel, {})
    cartridge_map_rel = scripted.get("cartridge_map", "")
    cartridge_rom_rel = scripted.get("cartridge_rom", "")
    if not _looks_resolved_path(cartridge_map_rel) or not _looks_resolved_path(cartridge_rom_rel):
        fallback = FALLBACK_CARTRIDGE_BY_DIR.get(Path(system_rel).parent.name)
        if fallback:
            cartridge_map_rel, cartridge_rom_rel = fallback
    if not cartridge_map_rel or not cartridge_rom_rel:
        raise AssertionError(f"Missing cartridge defaults for {system_rel}")
    cartridge_map_path = BASE_DIR / cartridge_map_rel
    if not cartridge_map_path.exists():
        raise AssertionError(f"Cartridge map path does not exist for {system_rel}: {cartridge_map_rel}")
    return cartridge_map_path, cartridge_rom_rel


def _build_compile_cases() -> list[CompileCase]:
    cases: list[CompileCase] = []
    for system_path in sorted(SYSTEMS_DIR.rglob("*.yaml")):
        system_rel = system_path.relative_to(BASE_DIR).as_posix()
        if system_rel in NON_STANDALONE_SYSTEMS:
            continue
        system_data = _load_yaml(system_path)
        components = system_data.get("components") or {}
        ic_ids = [str(item).strip() for item in components.get("ics", [])]
        device_ids = [str(item).strip() for item in components.get("devices", [])]
        host_ids = [str(item).strip() for item in components.get("hosts", [])]
        ic_paths = _resolve_component_paths(ic_ids, IC_INDEX, "ic")
        device_paths = _resolve_component_paths(device_ids, DEVICE_INDEX, "device")
        host_paths = _resolve_component_paths(host_ids, HOST_INDEX, "host")
        cartridge_map_path, cartridge_rom_path = _cartridge_args_for_system(system_rel, system_data)
        cases.append(
            CompileCase(
                system_path=system_path,
                processor_path=_processor_for_system(system_rel),
                ic_paths=ic_paths,
                device_paths=device_paths,
                host_paths=host_paths,
                host_backend_target="stub" if host_paths else None,
                cartridge_map_path=cartridge_map_path,
                cartridge_rom_path=cartridge_rom_path,
            )
        )
    return cases


ALL_COMPILE_CASES = _build_compile_cases()


def test_all_example_systems_have_compile_cases():
    case_ids = {case.case_id for case in ALL_COMPILE_CASES}
    expected = {
        path.relative_to(BASE_DIR).as_posix()
        for path in SYSTEMS_DIR.rglob("*.yaml")
        if path.relative_to(BASE_DIR).as_posix() not in NON_STANDALONE_SYSTEMS
    }
    assert case_ids == expected


def test_non_standalone_systems_are_explicitly_documented():
    for system_rel, reason in NON_STANDALONE_SYSTEMS.items():
        assert (BASE_DIR / system_rel).exists(), f"Missing excluded system: {system_rel}"
        assert reason


@pytest.mark.skipif(
    os.environ.get("PASM_ENABLE_ALL_SYSTEMS_COMPILE") != "1",
    reason="Set PASM_ENABLE_ALL_SYSTEMS_COMPILE=1 to run full example-system compile coverage.",
)
@pytest.mark.skipif(not shutil.which("cmake"), reason="cmake not available on PATH")
@pytest.mark.parametrize("case", ALL_COMPILE_CASES, ids=lambda case: case.case_id)
def test_all_example_systems_generate_and_build(case: CompileCase, tmp_path: Path):
    outdir = tmp_path / case.system_path.stem
    gen_mod.generate(
        str(case.processor_path),
        str(case.system_path),
        str(outdir),
        ic_paths=[str(path) for path in case.ic_paths],
        device_paths=[str(path) for path in case.device_paths],
        host_paths=[str(path) for path in case.host_paths],
        cartridge_map_path=str(case.cartridge_map_path) if case.cartridge_map_path else None,
        cartridge_rom_path=case.cartridge_rom_path,
        host_backend_target=case.host_backend_target,
    )

    build_dir = outdir / "build"
    subprocess.run(
        ["cmake", "-S", str(outdir), "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Release"],
        cwd=BASE_DIR,
        check=True,
    )
    subprocess.run(
        ["cmake", "--build", str(build_dir), "--config", "Release"],
        cwd=BASE_DIR,
        check=True,
    )
