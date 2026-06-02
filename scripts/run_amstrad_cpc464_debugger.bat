@echo off
setlocal EnableExtensions

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined START_PC set "START_PC=0x0000"
if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS=--release"
if not defined PASM_HOST_AUDIO set "PASM_HOST_AUDIO=1"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/cpc464/host_keyboard_cpc.yaml"
if not defined CONTROLLER_MAP set "CONTROLLER_MAP=examples/hosts/cpc464/host_controller_cpc464.yaml"
if not defined PASM_CPC_KB_TRACE set "PASM_CPC_KB_TRACE=1"
if not defined PASM_CPC_HOST_KB_TRACE set "PASM_CPC_HOST_KB_TRACE=1"
if not defined PASM_CPC_IRQ_TRACE set "PASM_CPC_IRQ_TRACE=1"
if not defined CLEAN_GENERATED set "CLEAN_GENERATED=1"
if not defined HOST_BACKEND set "HOST_BACKEND=sdl2"
if not defined AUTO_RUN set "AUTO_RUN=0"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1

set "PROCESSOR=examples/processors/z80.yaml"
set "IC_GATE_ARRAY=examples/ics/cpc464/cpc_gate_array_40010.yaml"
set "IC_CRTC=examples/ics/cpc464/cpc_crtc_6845.yaml"
set "IC_PPI=examples/ics/cpc464/cpc_ppi_8255.yaml"
set "IC_PSG=examples/ics/cpc464/cpc_ay_3_8912.yaml"
set "IC_RAM=examples/ics/cpc464/cpc464_ram_64k.yaml"
set "DEVICE_KB=examples/devices/cpc464/cpc_keyboard.yaml"
set "DEVICE_GP=examples/devices/cpc464/cpc_gameport.yaml"
set "DEVICE_VIDEO=examples/devices/cpc464/cpc_video.yaml"
set "DEVICE_SPK=examples/devices/cpc464/cpc_speaker.yaml"
set "SYSTEM_DIR=examples/systems/cpc464"

if /I "%PROFILE%"=="default" (
  set "SYSTEM=examples/systems/cpc464/cpc464_default.yaml"
  set "HOST=examples/hosts/cpc464/cpc_host_stub.yaml"
  set "DEFAULT_OUTPUT=generated/z80_amstrad_cpc464"
) else if /I "%PROFILE%"=="interactive" (
  set "SYSTEM=examples/systems/cpc464/cpc464_interactive.yaml"
  set "HOST=examples/hosts/cpc464/cpc_host_hal_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/z80_amstrad_cpc464_sdl"
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

if "%CLEAN_GENERATED%"=="1" (
  if exist "%OUTPUT_DIR%" rmdir /s /q "%OUTPUT_DIR%"
)

echo [1/3] Generating emulator -^> %OUTPUT_DIR%
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_GATE_ARRAY%" ^
  --ic "%IC_CRTC%" ^
  --ic "%IC_PPI%" ^
  --ic "%IC_PSG%" ^
  --ic "%IC_RAM%" ^
  --device "%DEVICE_KB%" ^
  --device "%DEVICE_GP%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST%" ^
  --host-backend "%HOST_BACKEND%" ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%

echo [2/3] Building emulator with CMake -^> %BUILD_DIR%
cmake -S "%OUTPUT_DIR%" -B "%BUILD_DIR%" -DCMAKE_BUILD_TYPE="%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%
cmake --build "%BUILD_DIR%" --config "%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%

echo [3/3] Running Rust debugger ^(linked backend^)
echo     profile=%PROFILE% memory_size=%MEMORY_SIZE% start_pc=%START_PC% run_speed=%RUN_SPEED% cmake_build_type=%CMAKE_BUILD_TYPE%
echo     expected_roms: examples/roms/cpc464/OS_464.ROM and examples/roms/cpc464/BASIC_1.0.ROM
if not exist log mkdir log >nul 2>&1
if exist log\cpc_host_kb_trace.log del /q log\cpc_host_kb_trace.log >nul 2>&1
if exist log\cpc_kb_trace.log del /q log\cpc_kb_trace.log >nul 2>&1
if exist log\cpc_ppi_trace.log del /q log\cpc_ppi_trace.log >nul 2>&1
if exist log\cpc_ay_trace.log del /q log\cpc_ay_trace.log >nul 2>&1
if exist log\cpc_irq_trace.log del /q log\cpc_irq_trace.log >nul 2>&1

set "PASM_EMU_DIR=%OUTPUT_DIR_ABS%"
set "PASM_EMU_BUILD_DIR=%BUILD_DIR_ABS%"
if exist "%CMAKE_CONFIG_BUILD_DIR%" set "PASM_EMU_BUILD_DIR=%CMAKE_CONFIG_BUILD_DIR_ABS%"
set "PASM_EMU_MANIFEST=%OUTPUT_DIR_ABS%\debugger_link.json"
set "PASM_HOST_AUDIO=%PASM_HOST_AUDIO%"
set "PASM_CPC_KB_TRACE=%PASM_CPC_KB_TRACE%"
set "PASM_CPC_HOST_KB_TRACE=%PASM_CPC_HOST_KB_TRACE%"
set "PASM_CPC_IRQ_TRACE=%PASM_CPC_IRQ_TRACE%"
set "AUTO_RUN_ARG="
if "%AUTO_RUN%"=="1" set "AUTO_RUN_ARG=--auto-run"

if /I "%PROFILE%"=="interactive" goto :run_interactive
cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --start-pc "%START_PC%" ^
  %AUTO_RUN_ARG% ^
  --run-speed "%RUN_SPEED%"
goto :run_done

:run_interactive
cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --start-pc "%START_PC%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --controller-map "%CONTROLLER_MAP%" ^
  %AUTO_RUN_ARG% ^
  --run-speed "%RUN_SPEED%"

:run_done
if errorlevel 1 exit /b %errorlevel%
exit /b 0
