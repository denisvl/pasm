from pathlib import Path


def test_atari800xl_split_ic_lists_include_main_ram_and_no_legacy_io():
    systems = [
        "examples/systems/atari800xl/atari800xl_default.yaml",
        "examples/systems/atari800xl/atari800xl_interactive.yaml",
        "examples/systems/atari800xl/atari800xl_cartridge_default.yaml",
        "examples/systems/atari800xl/atari800xl_cartridge_interactive.yaml",
    ]
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "- atari800xl_main_ram" in s
        assert "atari800xl_io" not in s


def test_atari800xl_debugger_script_loads_main_ram_and_avoids_inplace_system_mutation():
    script = Path("scripts/run_atari800xl_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_MAIN_RAM="examples/ics/atari800xl/atari800xl_main_ram.yaml"' in script
    assert '--ic "${IC_MAIN_RAM}"' in script
    assert "SYSTEM_ORIGINAL_CONTENT" not in script
    assert "RESTORE_SYSTEM" not in script
    assert 'SYSTEM_FOR_GEN="${TMP_SYSTEM}"' in script


def test_atari800xl_antic_uses_mmu_bridge_for_cart_irq_and_bus():
    antic = Path("examples/ics/atari800xl/atari800xl_antic.yaml").read_text(encoding="utf-8")
    assert "comp_atari_cart0" not in antic
    assert "cpu->irq_pending" not in antic
    assert "cpu->nmi_pending" not in antic
    assert "cpu->interrupt_pending" not in antic
    assert "cpu->memory[" not in antic
    assert "name: bus_read" in antic
    assert "name: bus_write" in antic
    assert "name: cart_present" in antic
    assert "name: cart_read" in antic
    assert "name: request_irq" in antic
    assert "name: request_nmi" in antic
