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
    assert 'CONTROLLER_MAP="${CONTROLLER_MAP:-examples/hosts/atari800xl/host_controller_atari800xl.yaml}"' in script
    assert '"${CONTROLLER_ARGS[@]}"' in script
    assert "SYSTEM_ORIGINAL_CONTENT" not in script
    assert "RESTORE_SYSTEM" not in script
    assert 'SYSTEM_FOR_GEN="${TMP_SYSTEM}"' in script


def test_atari800xl_antic_uses_mmu_bridge_for_cart_irq_and_bus():
    antic = Path("examples/ics/atari800xl/atari800xl_antic.yaml").read_text(encoding="utf-8")
    assert "comp_atari_cart0" not in antic or "cpu->comp_atari_cart0.rom_data != NULL" in antic
    assert "cpu->irq_pending" not in antic
    assert "cpu->nmi_pending" not in antic
    assert "cpu->interrupt_pending" not in antic
    assert "cpu->memory[" not in antic
    assert "name: bus_read" in antic
    assert "name: bus_write" in antic
    assert "name: cart_present" in antic
    assert "name: cart_read" in antic
    assert "name: cart_maps_low_window" in antic
    assert "name: request_irq" in antic
    assert "name: request_nmi" in antic


def test_atari800xl_cart_bridge_covers_8k_upper_window():
    mmu = Path("examples/ics/atari800xl/atari800xl_mmu.yaml").read_text(encoding="utf-8")
    antic = Path("examples/ics/atari800xl/atari800xl_antic.yaml").read_text(encoding="utf-8")
    assert "if (addr >= 0xA000u && addr < 0xC000u && eff_size > 0u)" in mmu
    assert "uint32_t bank_base = (eff_size > 0x2000u) ? (eff_size - 0x2000u) : 0u;" in mmu
    assert "if (cart_present != 0u) {" in antic
    assert "uint64_t cart_args[1] = { (uint64_t)addr };" in antic
    assert 'cpu_component_call(cpu, "atari800xl_antic", "cart_read", cart_args, 1)' in antic
    assert "return (uint64_t)(eff_size > 0x2000u ? 1u : 0u);" in mmu
    assert 'cpu_component_call(cpu, "atari800xl_antic", "cart_maps_low_window", NULL, 0)' in antic


def test_atari800xl_cart_detect_uses_trig3_high_when_present():
    antic = Path("examples/ics/atari800xl/atari800xl_antic.yaml").read_text(encoding="utf-8")
    assert "GTIA TRIG3 doubles as XL/XE cartridge detect." in antic
    assert "Match Atari800: a mapped cartridge drives TRIG3 high so the OS enters the cartridge boot path." in antic
    assert "trig = 1u;" in antic


def test_atari800xl_queues_display_list_interrupts() -> None:
    antic = Path("examples/ics/atari800xl/atari800xl_antic.yaml").read_text(encoding="utf-8")
    host = Path("examples/hosts/atari800xl/atari800xl_host_hal_interactive.yaml").read_text(encoding="utf-8")
    assert "render_colpf0_by_line" in antic
    assert "render_colpf0_next_by_line" in antic
    assert "render_colpf1_next_by_line" in antic
    assert "render_colpf2_next_by_line" in antic
    assert "render_colpf3_next_by_line" in antic
    assert "render_colbk_next_by_line" in antic
    assert "render_prior_by_line" in antic
    assert "render_prior_next_by_line" in antic
    assert "render_chactl_next_by_line" in antic
    assert "render_pmbase_by_line" in antic
    assert "render_pmbase_next_by_line" in antic
    assert "render_chbase_next_by_line" in antic
    assert "render_gtia_regs_by_line" in antic
    assert "render_gtia_regs_next_by_line" in antic
    assert "render_next_valid" in antic
    assert "target[i] = tracked_value;" in antic
    assert "else if (addr == 0xD01Bu) tracked = comp->render_prior_by_line;" in antic
    assert "else if (addr == 0xD01Bu) tracked_next = comp->render_prior_next_by_line;" in antic
    assert "else if (addr == 0xD407u) tracked = comp->render_pmbase_by_line;" in antic
    assert "else if (addr == 0xD407u) tracked_next = comp->render_pmbase_next_by_line;" in antic
    assert "0xD407u, (uint64_t)comp->antic_pmbase" in antic
    assert "0xD409u, (uint64_t)comp->antic_chbase" in antic
    assert "if (addr == 0xD407u) return comp->antic_pmbase;" in antic
    assert "if (addr == 0xD409u) return comp->antic_chbase;" in antic
    assert "static const uint32_t atari_ntsc_palette[256]" in antic
    assert "col_argb[ci] = atari_ntsc_palette[col_raw[ci]];" in antic
    assert "line_bg_raw = comp->render_colbk_by_line[line];" in antic
    assert "line_chbase = comp->render_chbase_by_line[line];" in antic
    assert "line_chbase_from_shadow" in antic
    assert "? ((uint16_t)line_chbase << 8u)" in antic
    assert ": ((uint16_t)(line_chbase & 0xFEu) << 8u)" in antic
    assert "uint16_t chbase20 = (uint16_t)((uint16_t)(line_chbase & 0xFEu) << 8u);" in antic
    assert "comp->render_next_valid == 0u" in antic
    assert "memcpy(comp->render_chbase_by_line, comp->render_chbase_next_by_line, 262u);" in antic
    assert "line_chactl = comp->render_chactl_by_line[line];" in antic
    assert "if (mode == 0x05u || mode == 0x07u)" in antic
    assert "glyph_row = (uint8_t)((py >> 1u) & 0x07u);" in antic
    assert "if (mode_67 != 0u) {" in antic
    assert "uint32_t pair_colors[4]" in antic
    assert "uint8_t hi2_raw = (uint8_t)((line_colpf2 & 0xF0u) | (line_colpf1 & 0x0Fu));" in antic
    assert "uint32_t mode_render_w = 320u;" in antic
    assert "uint32_t target_w = 320u;" in antic
    assert "uint8_t gtia_mode_line = (uint8_t)(line_prior >> 6u);" in antic
    assert "if ((mode == 0x0Du || mode == 0x0Eu) && gtia_mode_line != 0u) {" in antic
    assert "Minimal PMG overlay: enough to render status-panel/player text that" in antic
    assert "static const uint16_t gtia_track_addrs[19]" in antic
    assert "comp->render_gtia_regs_by_line + reg_i * 262u" in antic
    assert "uint8_t *gtia_line = comp->render_gtia_regs_by_line + hw_line;" in antic
    assert "uint8_t line_pmbase = comp->render_pmbase_by_line[hw_line];" in antic
    assert "uint8_t player_dma = (uint8_t)((dmactl & 0x08u) != 0u && (gractl & 0x02u) != 0u);" in antic
    assert "uint8_t missile_dma = (uint8_t)((dmactl & 0x04u) != 0u && (gractl & 0x01u) != 0u);" in antic
    assert "uint64_t frame_args[4] = {" in antic
    assert "Present a stable live KBCODE while the key is held" in antic
    assert "comp->keyboard_atascii != live_code" in antic
    assert "Use live hardware color registers first. OS shadows are only a fallback." in antic
    assert "SDLST is a fallback while hardware DLIST still points into bootstrap/page-zero RAM." in antic
    assert "if ((uint64_t)dl_ptr < cpu->memory_size && dl_ptr >= 0x0200u)" in antic
    assert "PASM_ATARI800XL_KEY_TRACE" in host
    assert "atari800xl_live_key" in host
    assert 'return (uint64_t)out;' in host
