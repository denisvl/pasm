@echo off
setlocal EnableExtensions

rem One-shot helper: generate + build + run PASM Rust debugger for Apple II.
rem
rem Usage:
rem   scripts\run_apple2_debugger.bat [interactive^|default]
rem
rem Optional env overrides:
rem   START_PC=0xFA62
rem   MEMORY_SIZE=65536
rem   OUTPUT_DIR=generated/apple2_interactive
rem   EXTRA_CARGO_ARGS=--release
rem   EXTRA_CMAKE_ARGS=-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-windows
rem   VCPKG_ROOT=D:\Development\vcpkg
rem   VCPKG_TARGET_TRIPLET=x64-windows
rem   CMAKE_BUILD_TYPE=Release
rem   RUN_SPEED=realtime|max

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS="
if not defined EXTRA_CMAKE_ARGS set "EXTRA_CMAKE_ARGS="
if not defined VCPKG_TARGET_TRIPLET set "VCPKG_TARGET_TRIPLET=x64-windows"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/apple2/host_keyboard_apple2.yaml"
if not defined JOYSTICK_KEYBOARD_MAP set "JOYSTICK_KEYBOARD_MAP=examples/hosts/apple2/host_keyboard_apple2_joystick.yaml"
if not defined CONTROLLER_MAP set "CONTROLLER_MAP=examples/hosts/apple2/host_controller_apple2.yaml"
if not defined HOST_BACKEND set "HOST_BACKEND=glfw"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1

set "PROCESSOR=examples/processors/mos6502.yaml"
set "SYSTEM_DIR=examples/systems/apple2"
set "IC_KBD=examples/ics/apple2/apple2_keyboard_encoder_ay_5_3600.yaml"
set "IC_GAMEIO=examples/ics/apple2/apple2_gameio_ne558.yaml"
set "IC_VIDEO_SW=examples/ics/apple2/apple2_video_softswitches.yaml"
set "IC_SPK_SW=examples/ics/apple2/apple2_speaker_toggle.yaml"
set "IC_CHAR_ROM=examples/ics/apple2/apple2_char_generator_rom.yaml"
set "IC_SLOT_DEC=examples/ics/apple2/apple2_slot_decoder_ttl.yaml"
set "IC_MAIN_RAM=examples/ics/apple2/apple2_main_ram.yaml"
set "DEVICE_KB=examples/devices/apple2/apple2_keyboard.yaml"
set "DEVICE_GP=examples/devices/apple2/apple2_gameport.yaml"
set "DEVICE_VIDEO=examples/devices/apple2/apple2_video.yaml"
set "DEVICE_SPK=examples/devices/apple2/apple2_speaker.yaml"
set "HOST_INTERACTIVE=examples/hosts/apple2/apple2_host_hal_interactive.yaml"

if /I "%PROFILE%"=="default" (
  set "SYSTEM=examples/systems/apple2/apple2_default.yaml"
  set "DEFAULT_OUTPUT=generated/apple2"
) else if /I "%PROFILE%"=="interactive" (
  set "SYSTEM=examples/systems/apple2/apple2_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/apple2_interactive"
) else (
  >&2 echo Unsupported profile: %PROFILE%
  >&2 echo Use: default ^| interactive
  exit /b 2
)

if not defined OUTPUT_DIR set "OUTPUT_DIR=%DEFAULT_OUTPUT%"
set "BUILD_DIR=%OUTPUT_DIR%/build"

for %%I in ("%OUTPUT_DIR%") do (
  set "OUTPUT_DIR_ABS=%%~fI"
  set "OUTPUT_PARENT=%%~dpI"
)
if not exist "%OUTPUT_PARENT%" mkdir "%OUTPUT_PARENT%"
if errorlevel 1 exit /b %errorlevel%

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
  if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\include\SDL2\SDL.h" (
    set "INCLUDE=%VCPKG_INSTALLED_TRIPLET_DIR%\include;%INCLUDE%"
  )
  if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\lib\SDL2.lib" (
    set "LIB=%VCPKG_INSTALLED_TRIPLET_DIR%\lib;%LIB%"
  )
  if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\debug\lib\SDL2.lib" (
    set "LIB=%VCPKG_INSTALLED_TRIPLET_DIR%\debug\lib;%LIB%"
  )
  if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\bin\SDL2.dll" (
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
if /I "%PROFILE%"=="interactive" goto :gen_interactive
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --output "%OUTPUT_DIR%"
goto :gen_done

:gen_interactive
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_KBD%" ^
  --ic "%IC_GAMEIO%" ^
  --ic "%IC_VIDEO_SW%" ^
  --ic "%IC_SPK_SW%" ^
  --ic "%IC_CHAR_ROM%" ^
  --ic "%IC_SLOT_DEC%" ^
  --ic "%IC_MAIN_RAM%" ^
  --device "%DEVICE_KB%" ^
  --device "%DEVICE_GP%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST_INTERACTIVE%" ^
  --host-backend "%HOST_BACKEND%" ^
  --output "%OUTPUT_DIR%"

:gen_done
if errorlevel 1 exit /b %errorlevel%

echo [2/3] Building emulator with CMake -^> %BUILD_DIR%
cmake -S "%OUTPUT_DIR%" -B "%BUILD_DIR%" -DCMAKE_BUILD_TYPE="%CMAKE_BUILD_TYPE%" %EXTRA_CMAKE_ARGS%
if errorlevel 1 (
  echo CMake configure failed; clearing "%BUILD_DIR%" and retrying once...
  if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
  cmake -S "%OUTPUT_DIR%" -B "%BUILD_DIR%" -DCMAKE_BUILD_TYPE="%CMAKE_BUILD_TYPE%" %EXTRA_CMAKE_ARGS%
  if errorlevel 1 exit /b %errorlevel%
)
cmake --build "%BUILD_DIR%" --config "%CMAKE_BUILD_TYPE%"
if errorlevel 1 exit /b %errorlevel%

echo [3/3] Running Rust debugger ^(linked backend^)
echo     profile=%PROFILE% memory_size=%MEMORY_SIZE% start_pc=%START_PC% run_speed=%RUN_SPEED% cmake_build_type=%CMAKE_BUILD_TYPE%

for %%I in ("%BUILD_DIR%") do set "BUILD_DIR_ABS=%%~fI"
set "CMAKE_CONFIG_BUILD_DIR=%BUILD_DIR%\%CMAKE_BUILD_TYPE%"
for %%I in ("%CMAKE_CONFIG_BUILD_DIR%") do set "CMAKE_CONFIG_BUILD_DIR_ABS=%%~fI"
set "PASM_EMU_DIR=%OUTPUT_DIR_ABS%"
set "PASM_EMU_BUILD_DIR=%BUILD_DIR_ABS%"
if exist "%CMAKE_CONFIG_BUILD_DIR%" set "PASM_EMU_BUILD_DIR=%CMAKE_CONFIG_BUILD_DIR_ABS%"
set "PASM_EMU_MANIFEST=%OUTPUT_DIR_ABS%\debugger_link.json"

set "CARGO_BIN=cargo"
where cargo >nul 2>&1
if errorlevel 1 (
  if exist "%USERPROFILE%\.cargo\bin\cargo.exe" (
    set "CARGO_BIN=%USERPROFILE%\.cargo\bin\cargo.exe"
  ) else (
    >&2 echo cargo executable not found.
    >&2 echo Install Rust with rustup, or add "%USERPROFILE%\.cargo\bin" to PATH.
    exit /b 3
  )
)

if defined START_PC goto :run_with_start_pc
"%CARGO_BIN%" run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --controller-map "%CONTROLLER_MAP%" ^
  --run-speed "%RUN_SPEED%"
goto :run_done

:run_with_start_pc
"%CARGO_BIN%" run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --controller-map "%CONTROLLER_MAP%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%"
:run_done
if errorlevel 1 exit /b %errorlevel%

exit /b 0
