@echo off
setlocal EnableExtensions

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined START_PC set "START_PC=0xFCE2"
if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS="
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/c64/host_keyboard_c64.yaml"
if not defined CONTROLLER_MAP set "CONTROLLER_MAP=examples/hosts/c64/host_controller_c64.yaml"
if not defined CARTRIDGE_MAP set "CARTRIDGE_MAP=examples/cartridges/c64/c64_cart_auto.yaml"
if not defined CARTRIDGE_ROM_GEN set "CARTRIDGE_ROM_GEN=../../roms/c64/basic.901226-01.bin"
if not defined CARTRIDGE_ROM_RUNTIME set "CARTRIDGE_ROM_RUNTIME="
if not defined CARTRIDGE_DIR set "CARTRIDGE_DIR="
if not defined BOOT_CARTRIDGE set "BOOT_CARTRIDGE=0"
if not defined PASM_EMU_CART_PICKER_RAW_KEYS set "PASM_EMU_CART_PICKER_RAW_KEYS=1"
if not defined HOST_BACKEND set "HOST_BACKEND=sdl2"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1
if not defined CARTRIDGE_DIR set "CARTRIDGE_DIR=%REPO_ROOT%\examples\roms\c64"

set "PROCESSOR=examples/processors/mos6510.yaml"
set "IC_PLA=examples/ics/c64/c64_pla_906114.yaml"
set "IC_VIC=examples/ics/c64/c64_vic_ii_6569.yaml"
set "IC_SID=examples/ics/c64/c64_sid_6581.yaml"
set "IC_CIA1=examples/ics/c64/c64_cia1_6526.yaml"
set "IC_CIA2=examples/ics/c64/c64_cia2_6526.yaml"
set "IC_COLOR_RAM=examples/ics/c64/c64_color_ram_2114.yaml"
set "IC_MAIN_RAM=examples/ics/c64/c64_main_ram.yaml"
set "DEVICE_KB=examples/devices/c64/c64_keyboard.yaml"
set "DEVICE_JOY=examples/devices/c64/c64_joystick.yaml"
set "DEVICE_VIDEO=examples/devices/c64/c64_video.yaml"
set "DEVICE_SPK=examples/devices/c64/c64_speaker.yaml"
set "HOST_INTERACTIVE=examples/hosts/c64/c64_host_hal_interactive.yaml"

if /I "%PROFILE%"=="default" (
  set "SYSTEM=examples/systems/c64/c64_cartridge_default.yaml"
  set "DEFAULT_OUTPUT=generated/c64"
) else if /I "%PROFILE%"=="interactive" (
  set "SYSTEM=examples/systems/c64/c64_cartridge_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/c64_interactive"
) else (
  >&2 echo Unsupported profile: %PROFILE%
  >&2 echo Use: default ^| interactive
  exit /b 2
)

for %%I in ("%SYSTEM%") do set "SYSTEM_DIR=%%~dpI"
if "%SYSTEM_DIR:~-1%"=="\" set "SYSTEM_DIR=%SYSTEM_DIR:~0,-1%"
set "ROM_RUNTIME=%CARTRIDGE_ROM_RUNTIME%"
if not defined ROM_RUNTIME set "ROM_RUNTIME=%SYSTEM_DIR%\%CARTRIDGE_ROM_GEN%"

if not defined OUTPUT_DIR set "OUTPUT_DIR=%DEFAULT_OUTPUT%"
set "BUILD_DIR=%OUTPUT_DIR%/build"
for %%I in ("%OUTPUT_DIR%") do set "OUTPUT_DIR_ABS=%%~fI"

echo [1/3] Generating emulator -^> %OUTPUT_DIR%
if /I "%PROFILE%"=="interactive" goto :gen_interactive
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --cartridge-map "%CARTRIDGE_MAP%" ^
  --cartridge-rom "%CARTRIDGE_ROM_GEN%" ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%
goto :gen_done

:gen_interactive
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_PLA%" ^
  --ic "%IC_VIC%" ^
  --ic "%IC_SID%" ^
  --ic "%IC_CIA1%" ^
  --ic "%IC_CIA2%" ^
  --ic "%IC_COLOR_RAM%" ^
  --ic "%IC_MAIN_RAM%" ^
  --device "%DEVICE_KB%" ^
  --device "%DEVICE_JOY%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST_INTERACTIVE%" ^
  --host-backend "%HOST_BACKEND%" ^
  --cartridge-map "%CARTRIDGE_MAP%" ^
  --cartridge-rom "%CARTRIDGE_ROM_GEN%" ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%
:gen_done

echo [2/3] Building emulator with CMake -^> %BUILD_DIR%
cmake -S "%OUTPUT_DIR%" -B "%BUILD_DIR%" -DCMAKE_BUILD_TYPE="%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%
cmake --build "%BUILD_DIR%" --config "%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%

echo [3/3] Running Rust debugger ^(linked backend^)
echo     profile=%PROFILE% memory_size=%MEMORY_SIZE% start_pc=%START_PC% run_speed=%RUN_SPEED%
echo     cartridge_map=%CARTRIDGE_MAP%
echo     cartridge_rom_gen=%CARTRIDGE_ROM_GEN%
echo     cartridge_rom_runtime=%ROM_RUNTIME%
echo     cartridge_dir=%CARTRIDGE_DIR%
echo     boot_cartridge=%BOOT_CARTRIDGE%
echo     cart_picker_raw_keys=%PASM_EMU_CART_PICKER_RAW_KEYS%

set "PASM_EMU_DIR=%OUTPUT_DIR_ABS%"
set "PASM_EMU_CART_PICKER_RAW_KEYS=%PASM_EMU_CART_PICKER_RAW_KEYS%"

if /I "%PROFILE%"=="interactive" goto :run_interactive
if "%BOOT_CARTRIDGE%"=="0" goto :run_default_no_boot
cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%" ^
  --cartridge-dir "%CARTRIDGE_DIR%" ^
  --cart-rom "%ROM_RUNTIME%"
goto :run_done

:run_default_no_boot
cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%" ^
  --cartridge-dir "%CARTRIDGE_DIR%"
goto :run_done

:run_interactive
if "%BOOT_CARTRIDGE%"=="0" goto :run_interactive_no_boot
cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --controller-map "%CONTROLLER_MAP%" ^
  --cartridge-dir "%CARTRIDGE_DIR%" ^
  --cart-rom "%ROM_RUNTIME%"
goto :run_done

:run_interactive_no_boot
cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --controller-map "%CONTROLLER_MAP%" ^
  --cartridge-dir "%CARTRIDGE_DIR%"

:run_done
if errorlevel 1 exit /b %errorlevel%
exit /b 0

