@echo off
setlocal EnableExtensions

rem One-shot helper: generate + build + run PASM Rust debugger for NES.
rem
rem Usage:
rem   scripts\run_nes_debugger.bat [interactive]
rem
rem Optional env overrides:
rem   START_PC=0xC000
rem   MEMORY_SIZE=65536
rem   OUTPUT_DIR=generated/mos6502_nes_interactive
rem   EXTRA_CARGO_ARGS=--release
rem   CMAKE_BUILD_TYPE=Release
rem   RUN_SPEED=realtime|max
rem   CARTRIDGE_ROM_GEN=../../roms/nes/Super Mario Bros. + Duck Hunt (USA).nes
rem   CARTRIDGE_ROM_RUNTIME=C:\path\to\rom.nes

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS=--release"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined PASM_HOST_AUDIO set "PASM_HOST_AUDIO=1"
if not defined PASM_HOST_DEBUG set "PASM_HOST_DEBUG=0"
if not defined PASM_NES_JOY2_CONNECTED set "PASM_NES_JOY2_CONNECTED=0"
if not defined CARTRIDGE_MAP set "CARTRIDGE_MAP=examples/cartridges/nes/nes_mapper_auto.yaml"
if not defined CARTRIDGE_ROM_GEN set "CARTRIDGE_ROM_GEN=../../roms/nes/Super Mario Bros. + Duck Hunt (USA).nes"
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/nes/host_console_nes.yaml"
if not defined CONTROLLER_MAP set "CONTROLLER_MAP=examples/hosts/nes/host_controller_nes.yaml"
if not defined CARTRIDGE_DIR set "CARTRIDGE_DIR=examples/roms/nes"
if not defined HOST_BACKEND set "HOST_BACKEND=glfw"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1

set "PROCESSOR=examples/processors/ricoh2a03.yaml"
set "SYSTEM=examples/systems/nes/nes_interactive.yaml"
set "SYSTEM_DIR=examples/systems/nes"
set "HOST=examples/hosts/nes/nes_host_hal_interactive.yaml"
set "IC_BUS=examples/ics/nes/nes_cpu_bus.yaml"
set "IC_CTRL=examples/ics/nes/nes_controller_ports.yaml"
set "IC_APU=examples/ics/nes/nes_apu.yaml"
set "IC_PPU_REGS=examples/ics/nes/nes_ppu_regs.yaml"
set "IC_CPU_RAM=examples/ics/nes/nes_cpu_ram.yaml"
set "IC_IO_PORTS=examples/ics/nes/nes_io_ports.yaml"
set "IC_CART_BRIDGE=examples/ics/nes/nes_cart_bridge.yaml"
set "DEVICE_CTRL=examples/devices/nes/nes_controller.yaml"
set "DEVICE_VIDEO=examples/devices/nes/nes_video.yaml"
set "DEVICE_SPK=examples/devices/nes/nes_speaker.yaml"

if /I not "%PROFILE%"=="interactive" (
  >&2 echo Unsupported profile: %PROFILE%
  >&2 echo Use: interactive
  exit /b 2
)

if not defined OUTPUT_DIR set "OUTPUT_DIR=generated/mos6502_nes_interactive"
set "BUILD_DIR=%OUTPUT_DIR%/build"
for %%I in ("%BUILD_DIR%") do set "BUILD_DIR_ABS=%%~fI"
set "CMAKE_CONFIG_BUILD_DIR=%BUILD_DIR%\%CMAKE_BUILD_TYPE%"
for %%I in ("%CMAKE_CONFIG_BUILD_DIR%") do set "CMAKE_CONFIG_BUILD_DIR_ABS=%%~fI"
for %%I in ("%OUTPUT_DIR%") do (
  set "OUTPUT_DIR_ABS=%%~fI"
  set "OUTPUT_PARENT=%%~dpI"
)
if not exist "%OUTPUT_PARENT%" mkdir "%OUTPUT_PARENT%"
if errorlevel 1 exit /b %errorlevel%

set "ROM_RUNTIME=%CARTRIDGE_ROM_RUNTIME%"
if not defined ROM_RUNTIME for %%I in ("%SYSTEM%\..\%CARTRIDGE_ROM_GEN:/=\%") do set "ROM_RUNTIME=%%~fI"
if not exist "%ROM_RUNTIME%" for %%I in ("%REPO_ROOT%\%CARTRIDGE_ROM_GEN:/=\%") do set "ROM_RUNTIME=%%~fI"
if not exist "%ROM_RUNTIME%" (
  >&2 echo Cartridge ROM not found: "%ROM_RUNTIME%"
  exit /b 4
)

echo [1/3] Generating emulator -^> %OUTPUT_DIR%
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_BUS%" ^
  --ic "%IC_CTRL%" ^
  --ic "%IC_APU%" ^
  --ic "%IC_PPU_REGS%" ^
  --ic "%IC_CPU_RAM%" ^
  --ic "%IC_IO_PORTS%" ^
  --ic "%IC_CART_BRIDGE%" ^
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
set "PASM_EMU_BUILD_DIR=%BUILD_DIR_ABS%"
if exist "%CMAKE_CONFIG_BUILD_DIR%" set "PASM_EMU_BUILD_DIR=%CMAKE_CONFIG_BUILD_DIR_ABS%"
set "PASM_EMU_MANIFEST=%OUTPUT_DIR_ABS%\debugger_link.json"
set "PATH=%PASM_EMU_BUILD_DIR%;%PATH%"
set "PASM_HOST_AUDIO=%PASM_HOST_AUDIO%"
set "PASM_HOST_DEBUG=%PASM_HOST_DEBUG%"
set "PASM_NES_JOY2_CONNECTED=%PASM_NES_JOY2_CONNECTED%"
set "PASM_NES_MMC3_TRACE=0"
set "PASM_NES_IRQ_TRACE=0"
set "PASM_NES_PAD_TRACE=0"
set "PASM_NES_PPUSTATUS_TRACE=0"
set "PASM_NES_PAD_ZP_TRACE=0"
set "PASM_NES_ZP_TRACE=0"
set "PASM_NES_4016_TRACE=0"
set "PASM_CYC_DEBUG=0"
set "PASM_TRACE=0"
set "PASM_IRQ_TRACE=0"

set "CARGO_BIN=cargo"
where cargo >nul 2>&1
if errorlevel 1 (
  if exist "%USERPROFILE%\.cargo\bin\cargo.exe" (
    set "CARGO_BIN=%USERPROFILE%\.cargo\bin\cargo.exe"
  ) else (
    >&2 echo cargo executable not found.
    exit /b 3
  )
)

echo [3/3] Running Rust debugger ^(linked backend^)
if defined START_PC goto :run_with_start_pc
"%CARGO_BIN%" run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --cart-rom "%ROM_RUNTIME%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --controller-map "%CONTROLLER_MAP%" ^
  --cartridge-dir "%CARTRIDGE_DIR%" ^
  --run-speed "%RUN_SPEED%"
goto :run_done

:run_with_start_pc
"%CARGO_BIN%" run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --cart-rom "%ROM_RUNTIME%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --controller-map "%CONTROLLER_MAP%" ^
  --cartridge-dir "%CARTRIDGE_DIR%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%"
:run_done
if errorlevel 1 exit /b %errorlevel%

exit /b 0
