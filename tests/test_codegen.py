import pathlib
import shutil

from src import generator as gen_mod


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _fresh_outdir(name: str) -> pathlib.Path:
    out = BASE_DIR / "generated" / name
    if out.exists():
        shutil.rmtree(out)
    return out


def test_generate_minimal8(tmp_path):
    isa_path = BASE_DIR / "examples" / "minimal8.yaml"
    outdir = _fresh_outdir("minimal8_test")

    gen_mod.generate(str(isa_path), str(outdir))

    src_dir = outdir / "src"
    assert (src_dir / "Minimal8.c").exists()
    assert (src_dir / "Minimal8.h").exists()
    assert (src_dir / "Minimal8_decoder.c").exists()
    assert (outdir / "CMakeLists.txt").exists()
    assert (outdir / "Makefile").exists()


def test_generate_simple8_full(tmp_path):
    isa_path = BASE_DIR / "examples" / "simple8.yaml"
    outdir = _fresh_outdir("simple8_test")

    gen_mod.generate(str(isa_path), str(outdir))

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

