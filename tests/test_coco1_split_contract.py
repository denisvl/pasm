from pathlib import Path


def test_coco1_systems_include_split_ics_and_main_ram():
    systems = (
        "examples/systems/coco1/coco1_default.yaml",
        "examples/systems/coco1/coco1_interactive.yaml",
    )
    for rel in systems:
        s = Path(rel).read_text(encoding="utf-8")
        assert "- coco1_sam_6883" in s
        assert "- coco1_pia0_6821" in s
        assert "- coco1_pia1_6821" in s
        assert "- coco1_vdg_6847" in s
        assert "- coco1_cart_expansion" in s
        assert "- coco1_main_ram" in s


def test_coco1_runners_load_main_ram_split():
    sh = Path("scripts/run_coco_debugger.sh").read_text(encoding="utf-8")
    assert 'IC_MAIN_RAM="examples/ics/coco1/coco1_main_ram.yaml"' in sh
    assert '--ic "${IC_MAIN_RAM}"' in sh

    bat = Path("scripts/run_coco_debugger.bat").read_text(encoding="utf-8")
    assert 'set "IC_MAIN_RAM=examples/ics/coco1/coco1_main_ram.yaml"' in bat
    assert '--ic "%IC_MAIN_RAM%" ^' in bat
