@echo off
setlocal EnableExtensions

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined START_PC set "START_PC="
if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS=--release"
if not defined EXTRA_CMAKE_ARGS set "EXTRA_CMAKE_ARGS="
if not defined VCPKG_TARGET_TRIPLET set "VCPKG_TARGET_TRIPLET=x64-windows"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/bbcmicro/host_keyboard_bbc_micro.yaml"
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=.uv-cache"
if not defined RUST_BACKTRACE set "RUST_BACKTRACE=1"
if not defined PASM_HOST_AUDIO set "PASM_HOST_AUDIO=1"
set "PASM_TRACE=0"
set "PASM_TRACE_FILE="
set "PASM_BBC_IO_TRACE=0"
set "PASM_BBC_IO_TRACE_FILE="
set "PASM_BBC_KB_TRACE=0"
set "PASM_BBC_KB_TRACE_FILE="
if not defined HOST_BACKEND set "HOST_BACKEND=glfw"
if not defined HOST_FILE set "HOST_FILE="

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1
if not exist log mkdir log >nul 2>&1

set "PROCESSOR=examples/processors/mos6502.yaml"
set "SYSTEM_DIR=examples/systems/bbcmicro"
set "IC_CRTC=examples/ics/bbcmicro/bbc_micro_crtc_6845.yaml"
set "IC_VIDEO_ULA=examples/ics/bbcmicro/bbc_micro_video_ula.yaml"
set "IC_SYSTEM_VIA=examples/ics/bbcmicro/bbc_micro_system_via_6522.yaml"
set "IC_USER_VIA=examples/ics/bbcmicro/bbc_micro_user_via_6522.yaml"
set "IC_TELETEXT=examples/ics/bbcmicro/bbc_micro_teletext_saa5050.yaml"
set "IC_ADC=examples/ics/bbcmicro/bbc_micro_adc_upd7002.yaml"
set "IC_ACIA=examples/ics/bbcmicro/bbc_micro_acia_6850.yaml"
set "IC_MMU=examples/ics/bbcmicro/bbc_micro_mmu_paged_rom.yaml"
set "IC_PSG=examples/ics/bbcmicro/sn76489_psg0.yaml"
set "IC_MAIN_RAM=examples/ics/bbcmicro/bbc_micro_main_ram.yaml"
set "DEVICE_KB=examples/devices/bbcmicro/bbc_micro_keyboard.yaml"
set "DEVICE_VIDEO=examples/devices/bbcmicro/bbc_micro_video.yaml"
set "DEVICE_SPK=examples/devices/bbcmicro/bbc_micro_speaker.yaml"
set "HOST_INTERACTIVE=examples/hosts/bbcmicro/bbc_micro_host_hal_interactive.yaml"
set "HOST_STUB=examples/hosts/bbcmicro/bbc_micro_host_stub.yaml"

if /I "%PROFILE%"=="default" (
  set "SYSTEM=examples/systems/bbcmicro/bbc_micro_default.yaml"
  set "DEFAULT_OUTPUT=generated/bbcmicro"
  if not defined HOST_FILE set "HOST_FILE=%HOST_STUB%"
) else if /I "%PROFILE%"=="interactive" (
  set "SYSTEM=examples/systems/bbcmicro/bbc_micro_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/bbc_micro_interactive"
  if not defined HOST_FILE set "HOST_FILE=%HOST_INTERACTIVE%"
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

if not defined EXTRA_CMAKE_ARGS (
  if defined VCPKG_ROOT (
    set "VCPKG_CMAKE_FILE=%VCPKG_ROOT%\scripts\buildsystems\vcpkg.cmake"
    if exist "%VCPKG_CMAKE_FILE%" (
      set "VCPKG_CMAKE_FILE=%VCPKG_CMAKE_FILE:\=/%"
      set "EXTRA_CMAKE_ARGS=-DCMAKE_TOOLCHAIN_FILE=%VCPKG_CMAKE_FILE% -DVCPKG_TARGET_TRIPLET=%VCPKG_TARGET_TRIPLET%"
    )
  ) else (
    if exist "D:\Development\vcpkg\scripts\buildsystems\vcpkg.cmake" (
      set "EXTRA_CMAKE_ARGS=-DCMAKE_TOOLCHAIN_FILE=D:/Development/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=%VCPKG_TARGET_TRIPLET%"
    )
  )
)

set "VCPKG_INSTALLED_TRIPLET_DIR="
if defined VCPKG_ROOT (
  if exist "%VCPKG_ROOT%\installed\%VCPKG_TARGET_TRIPLET%" (
    set "VCPKG_INSTALLED_TRIPLET_DIR=%VCPKG_ROOT%\installed\%VCPKG_TARGET_TRIPLET%"
  )
) else (
  if exist "D:\Development\vcpkg\installed\%VCPKG_TARGET_TRIPLET%" (
    set "VCPKG_INSTALLED_TRIPLET_DIR=D:\Development\vcpkg\installed\%VCPKG_TARGET_TRIPLET%"
  )
)

if defined VCPKG_INSTALLED_TRIPLET_DIR (
  if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\include" (
    set "INCLUDE=%VCPKG_INSTALLED_TRIPLET_DIR%\include;%INCLUDE%"
  )
  if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\lib" (
    set "LIB=%VCPKG_INSTALLED_TRIPLET_DIR%\lib;%LIB%"
  )
  if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\debug\lib" (
    set "LIB=%VCPKG_INSTALLED_TRIPLET_DIR%\debug\lib;%LIB%"
  )
  if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\bin" (
    set "PATH=%VCPKG_INSTALLED_TRIPLET_DIR%\bin;%PATH%"
  )
)

if not defined PASM_EMU_EXTRA_LIB_DIRS (
  if defined VCPKG_INSTALLED_TRIPLET_DIR (
    if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\lib" (
      set "PASM_EMU_EXTRA_LIB_DIRS=%VCPKG_INSTALLED_TRIPLET_DIR%\lib"
      if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\debug\lib" (
        set "PASM_EMU_EXTRA_LIB_DIRS=%PASM_EMU_EXTRA_LIB_DIRS%,%VCPKG_INSTALLED_TRIPLET_DIR%\debug\lib"
      )
    )
  )
)

echo [1/3] Generating emulator -^> %OUTPUT_DIR%
set "UV_CACHE_DIR=%UV_CACHE_DIR%"
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_CRTC%" ^
  --ic "%IC_VIDEO_ULA%" ^
  --ic "%IC_SYSTEM_VIA%" ^
  --ic "%IC_USER_VIA%" ^
  --ic "%IC_TELETEXT%" ^
  --ic "%IC_ADC%" ^
  --ic "%IC_ACIA%" ^
  --ic "%IC_MMU%" ^
  --ic "%IC_PSG%" ^
  --ic "%IC_MAIN_RAM%" ^
  --device "%DEVICE_KB%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST_FILE%" ^
  --host-backend "%HOST_BACKEND%" ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%

echo [2/3] Building emulator with CMake -^> %BUILD_DIR%
cmake -S "%OUTPUT_DIR%" -B "%BUILD_DIR%" -DCMAKE_BUILD_TYPE="%CMAKE_BUILD_TYPE%" %EXTRA_CMAKE_ARGS%
if errorlevel 1 exit /b %errorlevel%
cmake --build "%BUILD_DIR%" --config "%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%

echo [3/3] Running Rust debugger ^(linked backend^)
echo     profile=%PROFILE% memory_size=%MEMORY_SIZE% start_pc=%START_PC% run_speed=%RUN_SPEED%
echo     keyboard_map=%KEYBOARD_MAP%
echo     host_file=%HOST_FILE%

set "PASM_EMU_DIR=%OUTPUT_DIR_ABS%"
set "PASM_EMU_BUILD_DIR=%BUILD_DIR_ABS%"
if exist "%CMAKE_CONFIG_BUILD_DIR%" set "PASM_EMU_BUILD_DIR=%CMAKE_CONFIG_BUILD_DIR_ABS%"
set "PASM_EMU_MANIFEST=%OUTPUT_DIR_ABS%\debugger_link.json"
set "PASM_HOST_AUDIO=%PASM_HOST_AUDIO%"
set "PASM_TRACE=%PASM_TRACE%"
set "PASM_TRACE_FILE=%PASM_TRACE_FILE%"
set "PASM_BBC_IO_TRACE=%PASM_BBC_IO_TRACE%"
set "PASM_BBC_IO_TRACE_FILE=%PASM_BBC_IO_TRACE_FILE%"
set "PASM_BBC_KB_TRACE=%PASM_BBC_KB_TRACE%"
set "PASM_BBC_KB_TRACE_FILE=%PASM_BBC_KB_TRACE_FILE%"
set "RUST_BACKTRACE=%RUST_BACKTRACE%"

if defined START_PC (
  cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size "%MEMORY_SIZE%" ^
    --system-dir "%SYSTEM_DIR%" ^
    --run-speed "%RUN_SPEED%" ^
    --keyboard-map "%KEYBOARD_MAP%" ^
    --start-pc "%START_PC%"
) else (
  cargo run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size "%MEMORY_SIZE%" ^
    --system-dir "%SYSTEM_DIR%" ^
    --run-speed "%RUN_SPEED%" ^
    --keyboard-map "%KEYBOARD_MAP%"
)
if errorlevel 1 exit /b %errorlevel%

exit /b 0

