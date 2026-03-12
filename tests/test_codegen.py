from src import generator as gen_mod
from tests.support import example_pair


def test_generate_minimal8(tmp_path):
    processor_path, system_path = example_pair("minimal8")
    outdir = tmp_path / "minimal8_test"

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    src_dir = outdir / "src"
    assert (src_dir / "Minimal8.c").exists()
    assert (src_dir / "Minimal8.h").exists()
    assert (src_dir / "Minimal8_decoder.c").exists()
    assert (outdir / "CMakeLists.txt").exists()
    assert (outdir / "Makefile").exists()


def test_generate_simple8_full(tmp_path):
    processor_path, system_path = example_pair("simple8")
    outdir = tmp_path / "simple8_test"

    gen_mod.generate(str(processor_path), str(system_path), str(outdir))

    src_dir = outdir / "src"
    # Core files
    assert (src_dir / "Simple8.c").exists()
    assert (src_dir / "Simple8.h").exists()
    assert (src_dir / "Simple8_decoder.c").exists()
    # Hooks are disabled in simple8.yaml
    assert not (src_dir / "Simple8_hooks.c").exists()
    # Include dir and defs header
    include_dir = outdir / "include"
    assert (include_dir / "cpu_defs.h").exists()

