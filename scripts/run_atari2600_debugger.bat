@echo off
setlocal EnableExtensions

rem One-shot helper: generate + build + run PASM Rust debugger for Atari 2600.
rem
rem Usage:
rem   scripts\run_atari2600_debugger.bat [interactive^|default]

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined START_PC set "START_PC="
if not defined MEMORY_SIZE set "MEMORY_SIZE=8192"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS=--release"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined PASM_HOST_AUDIO set "PASM_HOST_AUDIO=1"
if not defined USE_CARTRIDGE set "USE_CARTRIDGE="
if not defined CARTRIDGE_MAP set "CARTRIDGE_MAP=examples/cartridges/atari2600/atari2600_mapper_none.yaml"
if not defined CARTRIDGE_ROM_GEN set "CARTRIDGE_ROM_GEN=../../roms/atari2600/Pitfall! (1982) (Activision) [!].a26"
if not defined CARTRIDGE_ROM_RUNTIME set "CARTRIDGE_ROM_RUNTIME="
if not defined CARTRIDGE_DIR set "CARTRIDGE_DIR="
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/atari2600/host_console_atari2600.yaml"
if not defined CONTROLLER_MAP set "CONTROLLER_MAP=examples/hosts/atari2600/host_controller_atari2600.yaml"
if not defined HOST_BACKEND set "HOST_BACKEND=sdl2"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1
if not defined CARTRIDGE_DIR set "CARTRIDGE_DIR=%REPO_ROOT%\examples\roms\atari2600"

set "PROCESSOR=examples/processors/mos6502.yaml"
set "IC_TIA=examples/ics/atari2600/atari2600_tia.yaml"
set "IC_RIOT=examples/ics/atari2600/atari2600_riot_6532.yaml"
set "IC_RAM=examples/ics/atari2600/atari2600_main_ram.yaml"
set "DEVICE_CTRL=examples/devices/atari2600/atari2600_controller.yaml"
set "DEVICE_VIDEO=examples/devices/atari2600/atari2600_video.yaml"
set "DEVICE_SPK=examples/devices/atari2600/atari2600_speaker.yaml"

if /I "%PROFILE%"=="default" (
  if not defined USE_CARTRIDGE set "USE_CARTRIDGE=0"
  set "SYSTEM=examples/systems/atari2600/atari2600_default.yaml"
  set "HOST=examples/hosts/atari2600/atari2600_host_stub.yaml"
  set "DEFAULT_OUTPUT=generated/atari2600_default"
) else if /I "%PROFILE%"=="interactive" (
  if not defined USE_CARTRIDGE set "USE_CARTRIDGE=1"
  set "SYSTEM=examples/systems/atari2600/atari2600_interactive.yaml"
  set "HOST=examples/hosts/atari2600/atari2600_host_hal_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/atari2600_interactive"
) else (
  >&2 echo Unsupported profile: %PROFILE%
  >&2 echo Use: default ^| interactive
  exit /b 2
)

if not defined OUTPUT_DIR set "OUTPUT_DIR=%DEFAULT_OUTPUT%"
set "BUILD_DIR=%OUTPUT_DIR%/build"
for %%I in ("%OUTPUT_DIR%") do set "OUTPUT_DIR_ABS=%%~fI"
for %%I in ("%SYSTEM%") do set "SYSTEM_DIR=%%~dpI"
if "%SYSTEM_DIR:~-1%"=="\" set "SYSTEM_DIR=%SYSTEM_DIR:~0,-1%"
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%" >nul 2>&1

set "ROM_RUNTIME=%CARTRIDGE_ROM_RUNTIME%"
if "%USE_CARTRIDGE%"=="0" goto :cart_done
if not defined ROM_RUNTIME set "ROM_RUNTIME=%SYSTEM_DIR%\%CARTRIDGE_ROM_GEN%"
:cart_done

echo [1/3] Generating emulator -^> %OUTPUT_DIR%
if "%USE_CARTRIDGE%"=="0" goto :gen_no_cart
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_RAM%" ^
  --ic "%IC_TIA%" ^
  --ic "%IC_RIOT%" ^
  --device "%DEVICE_CTRL%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST%" ^
  --host-backend "%HOST_BACKEND%" ^
  --cartridge-map "%CARTRIDGE_MAP%" ^
  --cartridge-rom "%CARTRIDGE_ROM_GEN%" ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%
goto :gen_done

:gen_no_cart
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_RAM%" ^
  --ic "%IC_TIA%" ^
  --ic "%IC_RIOT%" ^
  --device "%DEVICE_CTRL%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST%" ^
  --host-backend "%HOST_BACKEND%" ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%
:gen_done

echo [2/3] Building emulator with CMake -^> %BUILD_DIR%
cmake -S "%OUTPUT_DIR%" -B "%BUILD_DIR%" -DCMAKE_BUILD_TYPE="%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%
cmake --build "%BUILD_DIR%" --config "%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%

echo [3/3] Running Rust debugger ^(linked backend^)
echo     profile=%PROFILE% memory_size=%MEMORY_SIZE% start_pc=%START_PC% run_speed=%RUN_SPEED% cmake_build_type=%CMAKE_BUILD_TYPE% use_cartridge=%USE_CARTRIDGE%

set "PASM_EMU_DIR=%OUTPUT_DIR_ABS%"
set "PASM_EMU_BUILD_DIR=%BUILD_DIR%"
set "PASM_EMU_MANIFEST=%OUTPUT_DIR_ABS%\debugger_link.json"
set "PASM_HOST_AUDIO=%PASM_HOST_AUDIO%"

if "%USE_CARTRIDGE%"=="0" goto :run_no_cart
if defined START_PC (
  cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size "%MEMORY_SIZE%" ^
    --system-dir "%SYSTEM_DIR%" ^
    --keyboard-map "%KEYBOARD_MAP%" ^
    --controller-map "%CONTROLLER_MAP%" ^
    --cart-rom "%ROM_RUNTIME%" ^
    --cartridge-dir "%CARTRIDGE_DIR%" ^
    --start-pc "%START_PC%" ^
    --run-speed "%RUN_SPEED%"
) else (
  cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size "%MEMORY_SIZE%" ^
    --system-dir "%SYSTEM_DIR%" ^
    --keyboard-map "%KEYBOARD_MAP%" ^
    --controller-map "%CONTROLLER_MAP%" ^
    --cart-rom "%ROM_RUNTIME%" ^
    --cartridge-dir "%CARTRIDGE_DIR%" ^
    --run-speed "%RUN_SPEED%"
)
goto :run_done

:run_no_cart
if defined START_PC (
  cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size "%MEMORY_SIZE%" ^
    --system-dir "%SYSTEM_DIR%" ^
    --keyboard-map "%KEYBOARD_MAP%" ^
    --controller-map "%CONTROLLER_MAP%" ^
    --start-pc "%START_PC%" ^
    --run-speed "%RUN_SPEED%"
) else (
  cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size "%MEMORY_SIZE%" ^
    --system-dir "%SYSTEM_DIR%" ^
    --keyboard-map "%KEYBOARD_MAP%" ^
    --controller-map "%CONTROLLER_MAP%" ^
    --run-speed "%RUN_SPEED%"
)
:run_done
if errorlevel 1 exit /b %errorlevel%

exit /b 0
