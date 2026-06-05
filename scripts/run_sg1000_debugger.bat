@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "PROFILE=%~1"
if "%PROFILE%"=="" set "PROFILE=interactive"

set "ROOT_DIR=%~dp0.."
pushd "%ROOT_DIR%" >nul

set "OUT_DIR=generated\z80_sg1000_sdl"
set "BUILD_DIR=%OUT_DIR%\build"
set "BUILD_TYPE=Release"
if not defined HOST_BACKEND set "HOST_BACKEND=glfw"

set "PASM_HOST_AUDIO=%PASM_HOST_AUDIO%"
if "%PASM_HOST_AUDIO%"=="" set "PASM_HOST_AUDIO=1"

set "PASM_SG1000_JOY2_CONNECTED=%PASM_SG1000_JOY2_CONNECTED%"
if "%PASM_SG1000_JOY2_CONNECTED%"=="" set "PASM_SG1000_JOY2_CONNECTED=0"

set "SYSTEM_DIR=examples/systems"
set "CARTRIDGE_MAP=examples/cartridges/sg1000/sg1000_mapper_none.yaml"
set "CARTRIDGE_ROM_GEN=../../roms/sg1000/Hang-On II (Japan).sg"
set "CARTRIDGE_ROM_RUN=%PASM_SG1000_ROM%"
if "%CARTRIDGE_ROM_RUN%"=="" set "CARTRIDGE_ROM_RUN=%ROOT_DIR%\examples\roms\sg1000\Hang-On II (Japan).sg"
set "CARTRIDGE_DIR=%ROOT_DIR%\examples\roms\sg1000"

set "HOST_YAML=examples/hosts/sg1000/sg1000_host_hal_interactive.yaml"

if /I "%PROFILE%"=="default" (
  set "OUT_DIR=generated\z80_sg1000"
  set "HOST_YAML=examples/hosts/sg1000/sg1000_host_stub.yaml"
)
set "BUILD_DIR=%OUT_DIR%\build"

echo [1/3] Generating emulator -^> %OUT_DIR%
uv run python -m src.main generate ^
  --processor examples/processors/z80.yaml ^
  --system examples/systems/sg1000/sg1000_%PROFILE%.yaml ^
  --ic examples/ics/sg1000/sg1000_vdp_tms9918a.yaml ^
  --ic examples/ics/sg1000/sg1000_joypad_io.yaml ^
  --ic examples/ics/sg1000/sg1000_cpu_bus.yaml ^
  --ic examples/ics/sg1000/sg1000_main_ram.yaml ^
  --ic examples/ics/sg1000/sg1000_psg_sn76489.yaml ^
  --device examples/devices/sms/sms_video.yaml ^
  --device examples/devices/common/tv_crt_mono.yaml ^
  --host "%HOST_YAML%" ^
  --host-backend "%HOST_BACKEND%" ^
  --cartridge-map "%CARTRIDGE_MAP%" ^
  --cartridge-rom "%CARTRIDGE_ROM_GEN%" ^
  --output "%OUT_DIR%"
if errorlevel 1 goto :fail

echo [2/3] Building emulator with CMake -^> %BUILD_DIR%
cmake -S "%OUT_DIR%" -B "%BUILD_DIR%" -G "Visual Studio 17 2022" -A x64
if errorlevel 1 goto :fail
cmake --build "%BUILD_DIR%" --config "%BUILD_TYPE%"
if errorlevel 1 goto :fail

echo [3/3] Running Rust debugger (linked backend)
echo     profile=%PROFILE% memory_size=65536 start_pc=0x0000 sdl_audio=%PASM_HOST_AUDIO% run_speed=realtime cmake_build_type=%BUILD_TYPE%
echo     cartridge_map=%CARTRIDGE_MAP%
echo     cartridge_rom_gen=%CARTRIDGE_ROM_GEN%
echo     cartridge_rom_runtime=%CARTRIDGE_ROM_RUN%

for %%I in ("%OUT_DIR%") do set "OUT_DIR_ABS=%%~fI"
for %%I in ("%BUILD_DIR%") do set "BUILD_DIR_ABS=%%~fI"
set "CMAKE_CONFIG_BUILD_DIR=%BUILD_DIR%\%BUILD_TYPE%"
for %%I in ("%CMAKE_CONFIG_BUILD_DIR%") do set "CMAKE_CONFIG_BUILD_DIR_ABS=%%~fI"

set "PASM_EMU_DIR=%OUT_DIR_ABS%"
set "PASM_EMU_BUILD_DIR=%BUILD_DIR_ABS%"
if exist "%CMAKE_CONFIG_BUILD_DIR%" set "PASM_EMU_BUILD_DIR=%CMAKE_CONFIG_BUILD_DIR_ABS%"
set "PASM_EMU_MANIFEST=%OUT_DIR_ABS%\debugger_link.json"
set "PATH=%PASM_EMU_BUILD_DIR%;%PATH%"

if /I "%PROFILE%"=="interactive" goto :run_interactive
if exist "%CARTRIDGE_DIR%" (
  cargo run --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size 65536 ^
    --system-dir "%SYSTEM_DIR%" ^
    --start-pc 0x0000 ^
    --run-speed realtime ^
    --cartridge-map "%CARTRIDGE_MAP%" ^
    --cart-rom "%CARTRIDGE_ROM_RUN%" ^
    --cartridge-dir "%CARTRIDGE_DIR%"
) else (
  echo Warning: cartridge directory not found: %CARTRIDGE_DIR%
  cargo run --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size 65536 ^
    --system-dir "%SYSTEM_DIR%" ^
    --start-pc 0x0000 ^
    --run-speed realtime ^
    --cartridge-map "%CARTRIDGE_MAP%" ^
    --cart-rom "%CARTRIDGE_ROM_RUN%"
)
goto :run_done

:run_interactive
if exist "%CARTRIDGE_DIR%" (
  cargo run --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size 65536 ^
    --system-dir "%SYSTEM_DIR%" ^
    --start-pc 0x0000 ^
    --run-speed realtime ^
    --cartridge-map "%CARTRIDGE_MAP%" ^
    --cart-rom "%CARTRIDGE_ROM_RUN%" ^
    --controller-map "examples/hosts/sg1000/host_controller_sg1000.yaml" ^
    --keyboard-map "examples/hosts/sg1000/host_console_sg1000.yaml" ^
    --cartridge-dir "%CARTRIDGE_DIR%"
) else (
  echo Warning: cartridge directory not found: %CARTRIDGE_DIR%
  cargo run --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size 65536 ^
    --system-dir "%SYSTEM_DIR%" ^
    --start-pc 0x0000 ^
    --run-speed realtime ^
    --cartridge-map "%CARTRIDGE_MAP%" ^
    --cart-rom "%CARTRIDGE_ROM_RUN%" ^
    --controller-map "examples/hosts/sg1000/host_controller_sg1000.yaml" ^
    --keyboard-map "examples/hosts/sg1000/host_console_sg1000.yaml"
)

:run_done
if errorlevel 1 goto :fail

popd >nul
exit /b 0

:fail
set "ERR=%ERRORLEVEL%"
popd >nul
exit /b %ERR%
