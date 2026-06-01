@echo off
setlocal EnableExtensions

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS=--release"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined START_PC set "START_PC=0x0000"
if not defined CARTRIDGE_MAP set "CARTRIDGE_MAP=examples/cartridges/sg1000/sg1000_mapper_none.yaml"
if not defined CARTRIDGE_ROM_GEN set "CARTRIDGE_ROM_GEN=../../roms/sg1000/Hang-On II (Japan).sg"
if not defined CONTROLLER_MAP set "CONTROLLER_MAP=examples/hosts/sg1000/host_controller_sg1000.yaml"
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/sg1000/host_console_sg1000.yaml"
if not defined CARTRIDGE_DIR set "CARTRIDGE_DIR=examples/roms/sg1000"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1

set "PROCESSOR=examples/processors/z80.yaml"
set "IC_BUS=examples/ics/sg1000/sg1000_cpu_bus.yaml"
set "IC_RAM=examples/ics/sg1000/sg1000_main_ram.yaml"
set "IC_VDP=examples/ics/sg1000/sg1000_vdp_tms9918a.yaml"
set "IC_JOY=examples/ics/sg1000/sg1000_joypad_io.yaml"
set "IC_PSG=examples/ics/sg1000/sg1000_psg_sn76489.yaml"
set "DEVICE_VIDEO=examples/devices/sms/sms_video.yaml"
set "DEVICE_SPK=examples/devices/sms/sms_speaker.yaml"
set "SYSTEM_DIR=examples/systems"

if /I "%PROFILE%"=="default" (
  set "SYSTEM=examples/systems/sg1000/sg1000_default.yaml"
  set "HOST=examples/hosts/sg1000/sg1000_host_stub.yaml"
  set "OUTPUT_DIR=generated/z80_sg1000"
) else (
  set "SYSTEM=examples/systems/sg1000/sg1000_interactive.yaml"
  set "HOST=examples/hosts/sg1000/sg1000_host_hal_interactive.yaml"
  set "OUTPUT_DIR=generated/z80_sg1000_sdl"
)

set "BUILD_DIR=%OUTPUT_DIR%/build"
for %%I in ("%OUTPUT_DIR%") do set "OUTPUT_DIR_ABS=%%~fI"
for %%I in ("%SYSTEM%") do set "SYSTEM_ABS=%%~fI"
for %%I in ("%SYSTEM_ABS%\..\%CARTRIDGE_ROM_GEN:/=\%") do set "ROM_RUNTIME=%%~fI"
if not exist "%ROM_RUNTIME%" for %%I in ("%REPO_ROOT%\%CARTRIDGE_ROM_GEN:/=\%") do set "ROM_RUNTIME=%%~fI"

echo [1/3] Generating emulator -^> %OUTPUT_DIR%
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_BUS%" ^
  --ic "%IC_RAM%" ^
  --ic "%IC_VDP%" ^
  --ic "%IC_JOY%" ^
  --ic "%IC_PSG%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST%" ^
  --cartridge-map "%CARTRIDGE_MAP%" ^
  --cartridge-rom "%CARTRIDGE_ROM_GEN%" ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%

echo [2/3] Building emulator -^> %BUILD_DIR%
cmake -S "%OUTPUT_DIR%" -B "%BUILD_DIR%" -DCMAKE_BUILD_TYPE="%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%
cmake --build "%BUILD_DIR%" --config "%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%

set "PASM_EMU_DIR=%OUTPUT_DIR_ABS%"
echo [3/3] Running Rust debugger ^(linked backend^)
cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --cart-rom "%ROM_RUNTIME%" ^
  --start-pc "%START_PC%" ^
  --controller-map "%CONTROLLER_MAP%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --cartridge-dir "%CARTRIDGE_DIR%" ^
  --run-speed "%RUN_SPEED%"
if errorlevel 1 exit /b %errorlevel%

exit /b 0
