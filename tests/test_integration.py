import pathlib
import shutil
import subprocess

import pytest

from src import generator as gen_mod


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    shutil.which("cmake") is None,
    reason="cmake not available on PATH",
)
def test_simple8_end_to_end(tmp_path):
    """Generate Simple8, build it with CMake, and run the basic test.

    This is a smoke test to ensure the generated code compiles and links.
    """

    isa_path = BASE_DIR / "examples" / "simple8.yaml"
    outdir = tmp_path / "simple8_e2e"
    if outdir.exists():
        shutil.rmtree(outdir)

    gen_mod.generate(str(isa_path), str(outdir))

    build_dir = outdir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    # Configure
    subprocess.check_call(
        ["cmake", "-S", str(outdir), "-B", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    # Build
    subprocess.check_call(
        ["cmake", "--build", str(build_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    # Run the ctest suite (which runs the basic test)
    subprocess.check_call(
        ["ctest", "--output-on-failure"],
        cwd=str(build_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

