from pathlib import Path


def test_cpc464_gate_array_uses_isolated_ram_and_no_ppi_state_peek():
    p = Path("examples/ics/cpc464/cpc_gate_array_40010.yaml")
    s = p.read_text(encoding="utf-8")

    assert "cpu->comp_cpc464_ram.bytes" in s
    assert "if (ram == NULL) ram = cpu->memory;" not in s
    assert "cpu->comp_cpc_ppi." not in s


def test_cpc464_system_routes_psg_tick_audio():
    for rel in (
        "examples/systems/cpc464/cpc464_default.yaml",
        "examples/systems/cpc464/cpc464_interactive.yaml",
    ):
        s = Path(rel).read_text(encoding="utf-8")
        assert "name: psg_tick_audio" in s
        assert "name: tick_audio" in s
        assert "name: psg_pull_level" not in s
        assert "name: pull_level" not in s
