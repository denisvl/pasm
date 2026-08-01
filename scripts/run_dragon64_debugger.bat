@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined START_PC set "START_PC=0xB3B4"
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
set "DEVICE_CASS=examples/devices/common/cassette_transport.yaml"
set "SYSTEM_DIR=examples/systems/dragon64"

if /I "%PROFILE%"=="default" (
  set "SYSTEM=examples/systems/dragon64/dragon64_default.yaml"
  set "HOST=examples/hosts/coco1/coco_host_stub.yaml"
  set "DEFAULT_OUTPUT=generated/mc6809_dragon64"
) else if /I "%PROFILE%"=="interactive" (
  set "SYSTEM=examples/systems/dragon64/dragon64_interactive.yaml"
  set "HOST=examples/hosts/coco1/coco_host_hal_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/mc6809_dragon64_sdl"
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
if not defined CARTRIDGE_DIR set "CARTRIDGE_DIR=%REPO_ROOT%\examples\roms\dragon64"

if "%USE_CARTRIDGE%"=="0" (
  if not "%CARTRIDGE_MAP%"=="" set "USE_CARTRIDGE=1"
  if not "%CARTRIDGE_ROM_GEN%"=="" set "USE_CARTRIDGE=1"
  if not "%CARTRIDGE_ROM_RUN%"=="" set "USE_CARTRIDGE=1"
  if not "%CARTRIDGE_DIR%"=="" set "USE_CARTRIDGE=1"
)

if "%USE_CARTRIDGE%"=="1" (
  if "%CARTRIDGE_MAP%"=="" set "CARTRIDGE_MAP=examples/cartridges/coco1/coco_mapper_none.yaml"
  if "%CARTRIDGE_ROM_GEN%"=="" if "%CARTRIDGE_ROM_RUN%"=="" set "CARTRIDGE_ROM_GEN=../../roms/dragon64/ddos10.rom"
)

set "CARTRIDGE_ROM_RUNTIME=%CARTRIDGE_ROM_RUN%"
if "%USE_CARTRIDGE%"=="1" (
  if "!CARTRIDGE_ROM_RUNTIME!"=="" set "CARTRIDGE_ROM_RUNTIME=%SYSTEM_DIR_ABS%\%CARTRIDGE_ROM_GEN%"
  if "!CARTRIDGE_ROM_RUNTIME!"=="" set "CARTRIDGE_ROM_RUNTIME=%REPO_ROOT%\examples\roms\dragon64\ddos10.rom"
  if not exist "!CARTRIDGE_ROM_RUNTIME!" for %%I in ("%REPO_ROOT%\%CARTRIDGE_ROM_GEN%") do set "CARTRIDGE_ROM_RUNTIME=%%~fI"
  if "!CARTRIDGE_ROM_RUNTIME!"=="" for %%I in ("%REPO_ROOT%\examples\roms\dragon64\ddos10.rom") do set "CARTRIDGE_ROM_RUNTIME=%%~fI"
  if not exist "!CARTRIDGE_ROM_RUNTIME!" (
    >&2 echo Resolved cartridge runtime path: "!CARTRIDGE_ROM_RUNTIME!"
    >&2 echo Cartridge ROM not found: !CARTRIDGE_ROM_RUNTIME!
    exit /b 4
  )
)

echo [1/3] Generating Dragon 64 emulator -^> %OUTPUT_DIR%
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
  --device "%DEVICE_CASS%" ^
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
  --device "%DEVICE_CASS%" ^
  --host "%HOST%" ^
  --host-backend "%HOST_BACKEND%" ^
  --cartridge-map "%CARTRIDGE_MAP%" ^
  --cartridge-rom "%CART_GEN_ROM%" ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%

:gen_done
echo [2/3] Building Dragon 64 emulator with CMake -^> %BUILD_DIR%
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%" >nul 2>&1
cmake -S "%OUTPUT_DIR_ABS%" -B "%BUILD_DIR_ABS%" -DCMAKE_BUILD_TYPE=%CMAKE_BUILD_TYPE%
if errorlevel 1 exit /b %errorlevel%
cmake --build "%BUILD_DIR_ABS%" --config %CMAKE_BUILD_TYPE%
if errorlevel 1 exit /b %errorlevel%

echo [3/3] Running Rust debugger (linked backend)
set "CARGO_CMD=cargo run %EXTRA_CARGO_ARGS% -- --manifest "%OUTPUT_DIR_ABS%/debugger_link.json" --speed %RUN_SPEED% --audio %PASM_HOST_AUDIO%"
if "%KEYBOARD_MAP%" neq "" set "CARGO_CMD=%CARGO_CMD% --keyboard-map "%KEYBOARD_MAP%""
if "%CONTROLLER_MAP%" neq "" set "CARGO_CMD=%CARGO_CMD% --controller-map "%CONTROLLER_MAP%""
if "%USE_CARTRIDGE%"=="1" (
  if "%BOOT_CARTRIDGE%"=="1" set "CARGO_CMD=%CARGO_CMD% --boot-cartridge"
  if "%CARTRIDGE_ROM_RUNTIME%" neq "" set "CARGO_CMD=%CARGO_CMD% --cartridge-rom "%CARTRIDGE_ROM_RUNTIME%""
  if "%CARTRIDGE_DIR%" neq "" set "CARGO_CMD=%CARGO_CMD% --cartridge-dir "%CARTRIDGE_DIR%""
  if "%PASM_EMU_CART_PICKER_RAW_KEYS%"=="1" set "CARGO_CMD=%CARGO_CMD% --cart-picker-raw-keys"
)
set "CARGO_CMD=%CARGO_CMD% --auto-run"
cd tools\debugger_tui
echo %CARGO_CMD%
%CARGO_CMD%
set "EXIT_CODE=%errorlevel%"
cd /d "%REPO_ROOT%"
exit /b %EXIT_CODE%