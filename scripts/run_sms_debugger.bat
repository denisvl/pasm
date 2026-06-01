@echo off
setlocal EnableExtensions

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"
set "START_PC=%START_PC%"
if not defined START_PC set "START_PC=0x0000"
set "MEMORY_SIZE=%MEMORY_SIZE%"
if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
set "EXTRA_CARGO_ARGS=%EXTRA_CARGO_ARGS%"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS=--release"
set "PASM_HOST_AUDIO=%PASM_HOST_AUDIO%"
if not defined PASM_HOST_AUDIO set "PASM_HOST_AUDIO=1"
set "PASM_SMS_JOY2_CONNECTED=%PASM_SMS_JOY2_CONNECTED%"
if not defined PASM_SMS_JOY2_CONNECTED set "PASM_SMS_JOY2_CONNECTED=0"
set "PASM_SMS_CROP_LEFT8=%PASM_SMS_CROP_LEFT8%"
if not defined PASM_SMS_CROP_LEFT8 set "PASM_SMS_CROP_LEFT8=1"
set "CMAKE_BUILD_TYPE=%CMAKE_BUILD_TYPE%"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
set "RUN_SPEED=%RUN_SPEED%"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
set "CARTRIDGE_MAP=%CARTRIDGE_MAP%"
if not defined CARTRIDGE_MAP set "CARTRIDGE_MAP=examples/cartridges/sms/sms_mapper_sega.yaml"
set "CARTRIDGE_ROM_GEN=%CARTRIDGE_ROM_GEN%"
if not defined CARTRIDGE_ROM_GEN set "CARTRIDGE_ROM_GEN=../../roms/sms/Sonic The Hedgehog (USA, Europe).sms"
set "CONTROLLER_MAP=%CONTROLLER_MAP%"
if not defined CONTROLLER_MAP set "CONTROLLER_MAP=examples/hosts/sms/host_controller_sms.yaml"
set "KEYBOARD_MAP=%KEYBOARD_MAP%"
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/sms/host_console_sms.yaml"
set "CARTRIDGE_DIR=%CARTRIDGE_DIR%"
if not defined CARTRIDGE_DIR set "CARTRIDGE_DIR=examples/roms/sms"
set "HOST_BACKEND=%HOST_BACKEND%"
if not defined HOST_BACKEND set "HOST_BACKEND=sdl2"

for %%I in ("%~dp0..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%" || exit /b 1

set "PROCESSOR=examples/processors/z80.yaml"
set "IC_BUS=examples/ics/sms/sms_cpu_bus.yaml"
set "IC_RAM=examples/ics/sms/sms_main_ram.yaml"
set "IC_VDP=examples/ics/sms/sms_vdp_sega315_5124.yaml"
set "IC_JOY=examples/ics/sms/sms_joypad_io.yaml"
set "IC_PSG=examples/ics/sms/sms_psg_sn76489.yaml"
set "DEVICE_CTRL=examples/devices/sms/sms_controller.yaml"
set "DEVICE_VIDEO=examples/devices/sms/sms_video.yaml"
set "DEVICE_SPK=examples/devices/sms/sms_speaker.yaml"

if /I "%PROFILE%"=="default" (
  set "SYSTEM=examples/systems/sms/sms_default.yaml"
  set "HOST=examples/hosts/sms/sms_host_stub.yaml"
  set "DEFAULT_OUTPUT=generated/z80_sms"
) else if /I "%PROFILE%"=="interactive" (
  set "SYSTEM=examples/systems/sms/sms_interactive.yaml"
  set "HOST=examples/hosts/sms/sms_host_hal_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/z80_sms_sdl"
) else (
  echo Unsupported profile: %PROFILE%
  echo Use: default ^| interactive
  exit /b 2
)

if not defined OUTPUT_DIR set "OUTPUT_DIR=%DEFAULT_OUTPUT%"
set "BUILD_DIR=%OUTPUT_DIR%\build"
for %%I in ("%OUTPUT_DIR%") do set "OUTPUT_DIR_ABS=%%~fI"
for %%I in ("%SYSTEM%") do set "SYSTEM_DIR_ABS=%%~dpI"
if "%SYSTEM_DIR_ABS:~-1%"=="\" set "SYSTEM_DIR_ABS=%SYSTEM_DIR_ABS:~0,-1%"

if defined CARTRIDGE_ROM_RUN (
  set "CARTRIDGE_ROM_RUNTIME=%CARTRIDGE_ROM_RUN%"
) else (
  for %%I in ("%SYSTEM_DIR_ABS%\%CARTRIDGE_ROM_GEN:/=\%") do set "CARTRIDGE_ROM_RUNTIME=%%~fI"
)

echo [1/3] Generating emulator -^> %OUTPUT_DIR%
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_BUS%" ^
  --ic "%IC_RAM%" ^
  --ic "%IC_VDP%" ^
  --ic "%IC_JOY%" ^
  --ic "%IC_PSG%" ^
  --device "%DEVICE_CTRL%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST%" ^
  --host-backend "%HOST_BACKEND%" ^
  --cartridge-map "%CARTRIDGE_MAP%" ^
  --cartridge-rom "%CARTRIDGE_ROM_GEN%" ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%

echo [2/3] Building emulator with CMake -^> %BUILD_DIR%
cmake -S "%OUTPUT_DIR%" -B "%BUILD_DIR%" -DCMAKE_BUILD_TYPE="%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%
cmake --build "%BUILD_DIR%" --config "%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%

set "PASM_EMU_DIR=%OUTPUT_DIR_ABS%"
set "PASM_HOST_AUDIO=%PASM_HOST_AUDIO%"
set "PASM_SMS_JOY2_CONNECTED=%PASM_SMS_JOY2_CONNECTED%"
set "PASM_EMU_EXTRA_LIBS=SDL2"

echo [3/3] Running Rust debugger (linked backend)
if /I "%PROFILE%"=="interactive" (
  cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size "%MEMORY_SIZE%" ^
    --system-dir "%SYSTEM_DIR_ABS%" ^
    --cart-rom "%CARTRIDGE_ROM_RUNTIME%" ^
    --start-pc "%START_PC%" ^
    --keyboard-map "%KEYBOARD_MAP%" ^
    --controller-map "%CONTROLLER_MAP%" ^
    --cartridge-dir "%CARTRIDGE_DIR%" ^
    --run-speed "%RUN_SPEED%"
) else (
  cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size "%MEMORY_SIZE%" ^
    --system-dir "%SYSTEM_DIR_ABS%" ^
    --cart-rom "%CARTRIDGE_ROM_RUNTIME%" ^
    --start-pc "%START_PC%" ^
    --run-speed "%RUN_SPEED%"
)
if errorlevel 1 exit /b %errorlevel%
exit /b 0
