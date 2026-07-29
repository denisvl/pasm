from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"


SCRIPT_NAME_EXCLUDES = (
    "controller_mapper",
    "keymapper",
    "schema_editor",
)


def _is_system_launcher_script(path: Path) -> bool:
    name = path.name
    return not any(token in name for token in SCRIPT_NAME_EXCLUDES)


def _current_os_system_launcher_scripts() -> list[Path]:
    ext = ".bat" if os.name == "nt" else ".sh"
    scripts = []
    patterns = (f"run_*_debugger{ext}", f"run_*_interactive{ext}", f"run_*_no_tui{ext}")
    for pattern in patterns:
        for path in sorted(SCRIPTS_DIR.glob(pattern)):
            if path.name == f"run_generated_no_tui{ext}":
                continue
            if not _is_system_launcher_script(path):
                continue
            scripts.append(path)
    return scripts


CURRENT_OS_SYSTEM_LAUNCHER_SCRIPTS = _current_os_system_launcher_scripts()
LAUNCHER_ARGUMENTS = ("default", "interactive")


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _install_posix_tool_shims(bin_dir: Path) -> None:
    _write_executable(
        bin_dir / "cmake",
        """#!/usr/bin/env bash
set -euo pipefail
prev=""
build_dir=""
for arg in "$@"; do
  if [[ "$prev" == "-B" && -n "$arg" ]]; then
    mkdir -p "$arg" "$arg/Release"
    build_dir="$arg"
  fi
  prev="$arg"
done
if [[ "${1:-}" == "--build" && -n "${2:-}" ]]; then
  mkdir -p "$2" "$2/Release"
  for exe in z80_test mos6502_test mos6510_test; do
    cat >"$2/$exe" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$2/$exe"
    cp "$2/$exe" "$2/Release/$exe"
  done
fi
exit 0
""",
    )
    _write_executable(
        bin_dir / "cargo",
        """#!/usr/bin/env bash
exit 0
""",
    )


def _install_windows_tool_shims(bin_dir: Path) -> None:
    (bin_dir / "cmake.bat").write_text(
        """@echo off
setlocal EnableExtensions
:loop
if "%~1"=="" exit /b 0
if "%~1"=="-B" (
  shift
  if not "%~1"=="" (
    mkdir "%~1" >nul 2>nul
    mkdir "%~1\\Release" >nul 2>nul
  )
)
if "%~1"=="--build" (
  shift
  if not "%~1"=="" (
    mkdir "%~1" >nul 2>nul
    mkdir "%~1\\Release" >nul 2>nul
    for %%E in (z80_test mos6502_test mos6510_test) do (
      echo @echo off>"%~1\\%%E.bat"
      echo exit /b 0>>"%~1\\%%E.bat"
      echo @echo off>"%~1\\Release\\%%E.bat"
      echo exit /b 0>>"%~1\\Release\\%%E.bat"
    )
  )
)
shift
goto loop
""",
        encoding="utf-8",
    )
    (bin_dir / "cargo.bat").write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")


def _install_fake_generated_binary(tmp_path: Path) -> Path:
    if os.name == "nt":
        binary = tmp_path / "generated_test_binary.bat"
        binary.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
        return binary
    binary = tmp_path / "generated_test_binary"
    _write_executable(
        binary,
        """#!/usr/bin/env bash
exit 0
""",
    )
    return binary


@pytest.fixture()
def launcher_smoke_env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if os.name == "nt":
        _install_windows_tool_shims(bin_dir)
    else:
        _install_posix_tool_shims(bin_dir)

    dummy = tmp_path / "dummy.rom"
    dummy.write_bytes(bytes([0xEA]) * 32768)
    rom_dir = tmp_path / "roms"
    rom_dir.mkdir()
    fake_generated_binary = _install_fake_generated_binary(tmp_path)

    env = os.environ.copy()
    env.update(
        {
            "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
            "UV_CACHE_DIR": str(tmp_path / ".uv-cache"),
            "HOST_BACKEND": "stub",
            "PASM_HOST_AUDIO": "0",
            "PASM_SDL_AUDIO": "0",
            "USE_CARTRIDGE": "0",
            "USE_CARTRIDGE_SYSTEM": "0",
            "BOOT_CARTRIDGE": "0",
            "CARTRIDGE_ROM_RUN": str(dummy),
            "CARTRIDGE_ROM_RUNTIME": str(dummy),
            "CARTRIDGE_DIR": str(rom_dir),
            "FLOPPY": "",
            "DISK_ROM": "",
            "BIN": str(fake_generated_binary),
        }
    )
    return env


def test_current_os_system_launcher_scripts_discovered():
    assert CURRENT_OS_SYSTEM_LAUNCHER_SCRIPTS
    suffixes = {path.suffix for path in CURRENT_OS_SYSTEM_LAUNCHER_SCRIPTS}
    assert suffixes == ({".bat"} if os.name == "nt" else {".sh"})
    assert all(_is_system_launcher_script(path) for path in CURRENT_OS_SYSTEM_LAUNCHER_SCRIPTS)
    assert any("_debugger" in path.stem for path in CURRENT_OS_SYSTEM_LAUNCHER_SCRIPTS)
    assert any("_interactive" in path.stem for path in CURRENT_OS_SYSTEM_LAUNCHER_SCRIPTS)
    assert any("_no_tui" in path.stem for path in CURRENT_OS_SYSTEM_LAUNCHER_SCRIPTS)


@pytest.mark.parametrize(
    "script_path",
    CURRENT_OS_SYSTEM_LAUNCHER_SCRIPTS,
    ids=lambda path: path.name,
)
@pytest.mark.parametrize("launcher_arg", LAUNCHER_ARGUMENTS)
def test_current_os_system_launcher_script_executes(
    script_path: Path,
    launcher_arg: str,
    tmp_path: Path,
    launcher_smoke_env: dict[str, str],
):
    env = launcher_smoke_env.copy()
    env["OUTPUT_DIR"] = str(tmp_path / launcher_arg / script_path.stem)
    cmd = (
        ["cmd", "/c", str(script_path), launcher_arg]
        if os.name == "nt"
        else ["bash", str(script_path), launcher_arg]
    )
    proc = subprocess.run(
        cmd,
        cwd=BASE_DIR,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"{script_path.name} failed with exit code {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )
