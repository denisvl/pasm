@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined START_PC set "START_PC=0xA027"
if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS=--release"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined PASM_HOST_AUDIO set "PASM_HOST_AUDIO=1"
if not defined USE_CARTRIDGE set "USE_CARTRIDGE=0"
if not defined CARTRIDGE_MAP set "CARTRIDGE_MAP="
if not defined CARTRIDGE_ROM_GEN set "CARTRIDGE_ROM_GEN="
if not defined CARTRIDGE_ROM_RUN set "CARTRIDGE_ROM_RUN="
if not defined CARTRIDGE_DIR set "CARTRIDGE_DIR="
if not defined BOOT_CARTRIDGE set "BOOT_CARTRIDGE=0"
if not defined PASM_EMU_CART_PICKER_RAW_KEYS set "PASM_EMU_CART_PICKER_RAW_KEYS=1"
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/coco1/host_keyboard_coco.yaml"
if not defined CONTROLLER_MAP set "CONTROLLER_MAP=examples/hosts/coco1/host_controller_coco.yaml"
if not defined HOST_BACKEND set "HOST_BACKEND=glfw"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1

set "PROCESSOR=examples/processors/mc6809.yaml"
set "IC_SAM=examples/ics/coco1/coco1_sam_6883.yaml"
set "IC_PIA0=examples/ics/coco1/coco1_pia0_6821.yaml"
set "IC_PIA1=examples/ics/coco1/coco1_pia1_6821.yaml"
set "IC_VDG=examples/ics/coco1/coco1_vdg_6847.yaml"
set "IC_CART_EXP=examples/ics/coco1/coco1_cart_expansion.yaml"
set "IC_MAIN_RAM=examples/ics/coco1/coco1_main_ram.yaml"
set "DEVICE_KB=examples/devices/coco1/coco_keyboard.yaml"
set "DEVICE_GP=examples/devices/coco1/coco_gameport.yaml"
set "DEVICE_VIDEO=examples/devices/coco1/coco_video.yaml"
set "DEVICE_SPK=examples/devices/coco1/coco_speaker.yaml"
set "SYSTEM_DIR=examples/systems/coco1"

if /I "%PROFILE%"=="default" (
  set "SYSTEM=examples/systems/coco1/coco1_default.yaml"
  set "HOST=examples/hosts/coco1/coco_host_stub.yaml"
  set "DEFAULT_OUTPUT=generated/mc6809_coco1"
) else if /I "%PROFILE%"=="interactive" (
  set "SYSTEM=examples/systems/coco1/coco1_interactive.yaml"
  set "HOST=examples/hosts/coco1/coco_host_hal_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/mc6809_coco1_sdl"
) else (
  >&2 echo Unsupported profile: %PROFILE%
  >&2 echo Use: default ^| interactive
  exit /b 2
)

if not defined OUTPUT_DIR set "OUTPUT_DIR=%DEFAULT_OUTPUT%"
set "BUILD_DIR=%OUTPUT_DIR%/build"
for %%I in ("%OUTPUT_DIR%") do set "OUTPUT_DIR_ABS=%%~fI"
for %%I in ("%BUILD_DIR%") do set "BUILD_DIR_ABS=%%~fI"
set "CMAKE_CONFIG_BUILD_DIR=%BUILD_DIR%\%CMAKE_BUILD_TYPE%"
for %%I in ("%CMAKE_CONFIG_BUILD_DIR%") do set "CMAKE_CONFIG_BUILD_DIR_ABS=%%~fI"
for %%I in ("%SYSTEM%") do set "SYSTEM_DIR_ABS=%%~dpI"
if "%SYSTEM_DIR_ABS:~-1%"=="\" set "SYSTEM_DIR_ABS=%SYSTEM_DIR_ABS:~0,-1%"
if not defined CARTRIDGE_DIR set "CARTRIDGE_DIR=%REPO_ROOT%\examples\roms\coco1"

if "%USE_CARTRIDGE%"=="0" (
  if not "%CARTRIDGE_MAP%"=="" set "USE_CARTRIDGE=1"
  if not "%CARTRIDGE_ROM_GEN%"=="" set "USE_CARTRIDGE=1"
  if not "%CARTRIDGE_ROM_RUN%"=="" set "USE_CARTRIDGE=1"
  if not "%CARTRIDGE_DIR%"=="" set "USE_CARTRIDGE=1"
)

if "%USE_CARTRIDGE%"=="1" (
  if "%CARTRIDGE_MAP%"=="" set "CARTRIDGE_MAP=examples/cartridges/coco1/coco_mapper_none.yaml"
  if "%CARTRIDGE_ROM_GEN%"=="" if "%CARTRIDGE_ROM_RUN%"=="" set "CARTRIDGE_ROM_GEN=../../roms/coco1/Downland V1.1 (1983) (26-3046) (Tandy) [a1].ccc"
)

set "CARTRIDGE_ROM_RUNTIME=%CARTRIDGE_ROM_RUN%"
if "%USE_CARTRIDGE%"=="1" (
  if "!CARTRIDGE_ROM_RUNTIME!"=="" set "CARTRIDGE_ROM_RUNTIME=%SYSTEM_DIR_ABS%\%CARTRIDGE_ROM_GEN%"
  if "!CARTRIDGE_ROM_RUNTIME!"=="" set "CARTRIDGE_ROM_RUNTIME=%REPO_ROOT%\examples\roms\coco1\Downland V1.1 (1983) (26-3046) (Tandy) [a1].ccc"
  if not exist "!CARTRIDGE_ROM_RUNTIME!" for %%I in ("%REPO_ROOT%\%CARTRIDGE_ROM_GEN%") do set "CARTRIDGE_ROM_RUNTIME=%%~fI"
  if "!CARTRIDGE_ROM_RUNTIME!"=="" for %%I in ("%REPO_ROOT%\examples\roms\coco1\Downland V1.1 (1983) (26-3046) (Tandy) [a1].ccc") do set "CARTRIDGE_ROM_RUNTIME=%%~fI"
  if not exist "!CARTRIDGE_ROM_RUNTIME!" (
    >&2 echo Resolved cartridge runtime path: "!CARTRIDGE_ROM_RUNTIME!"
    >&2 echo Cartridge ROM not found: !CARTRIDGE_ROM_RUNTIME!
    exit /b 4
  )
)

echo [1/3] Generating emulator -^> %OUTPUT_DIR%
if "%USE_CARTRIDGE%"=="1" goto :gen_cart
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_SAM%" ^
  --ic "%IC_PIA0%" ^
  --ic "%IC_PIA1%" ^
  --ic "%IC_VDG%" ^
  --ic "%IC_CART_EXP%" ^
  --ic "%IC_MAIN_RAM%" ^
  --device "%DEVICE_KB%" ^
  --device "%DEVICE_GP%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST%" ^
  --host-backend "%HOST_BACKEND%" ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%
goto :gen_done

:gen_cart
set "CART_GEN_ROM=%CARTRIDGE_ROM_GEN%"
if "%CART_GEN_ROM%"=="" set "CART_GEN_ROM=%CARTRIDGE_ROM_RUNTIME%"
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_SAM%" ^
  --ic "%IC_PIA0%" ^
  --ic "%IC_PIA1%" ^
  --ic "%IC_VDG%" ^
  --ic "%IC_CART_EXP%" ^
  --ic "%IC_MAIN_RAM%" ^
  --device "%DEVICE_KB%" ^
  --device "%DEVICE_GP%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST%" ^
  --host-backend "%HOST_BACKEND%" ^
  --cartridge-map "%CARTRIDGE_MAP%" ^
  --cartridge-rom "%CART_GEN_ROM%" ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%
:gen_done

echo [2/3] Building emulator with CMake -^> %BUILD_DIR%
cmake -S "%OUTPUT_DIR%" -B "%BUILD_DIR%" -DCMAKE_BUILD_TYPE="%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%
cmake --build "%BUILD_DIR%" --config "%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%

echo [3/3] Running Rust debugger ^(linked backend^)
set "PASM_EMU_DIR=%OUTPUT_DIR_ABS%"
set "PASM_EMU_BUILD_DIR=%BUILD_DIR_ABS%"
if exist "%CMAKE_CONFIG_BUILD_DIR%" set "PASM_EMU_BUILD_DIR=%CMAKE_CONFIG_BUILD_DIR_ABS%"
set "PASM_EMU_MANIFEST=%OUTPUT_DIR_ABS%\debugger_link.json"
set "PATH=%PASM_EMU_BUILD_DIR%;%PATH%"
set "PASM_HOST_AUDIO=%PASM_HOST_AUDIO%"
set "PASM_EMU_CART_PICKER_RAW_KEYS=%PASM_EMU_CART_PICKER_RAW_KEYS%"
set "PASM_SYSTEM_DIR=%SYSTEM_DIR%"

if /I "%PROFILE%"=="interactive" goto :run_interactive
goto :run_default

:run_default
if "%USE_CARTRIDGE%"=="1" if not "%BOOT_CARTRIDGE%"=="0" goto :run_default_boot_cart
cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --cartridge-dir "%CARTRIDGE_DIR%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%"
goto :run_done

:run_default_boot_cart
cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --cartridge-dir "%CARTRIDGE_DIR%" ^
  --cart-rom "%CARTRIDGE_ROM_RUNTIME%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%"
goto :run_done

:run_interactive
if "%USE_CARTRIDGE%"=="1" if not "%BOOT_CARTRIDGE%"=="0" goto :run_interactive_boot_cart
cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --controller-map "%CONTROLLER_MAP%" ^
  --cartridge-dir "%CARTRIDGE_DIR%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%"
goto :run_done

:run_interactive_boot_cart
cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --controller-map "%CONTROLLER_MAP%" ^
  --cartridge-dir "%CARTRIDGE_DIR%" ^
  --cart-rom "%CARTRIDGE_ROM_RUNTIME%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%"

:run_done
if errorlevel 1 exit /b %errorlevel%
exit /b 0
