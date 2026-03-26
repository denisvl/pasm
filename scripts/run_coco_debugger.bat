@echo off
setlocal EnableExtensions

rem One-shot helper: generate + build + run PASM Rust debugger for TRS-80 Color Computer 1.
rem
rem Usage:
rem   scripts\run_coco_debugger.bat [interactive^|default]
rem
rem Optional env overrides:
rem   START_PC=0xA027
rem   MEMORY_SIZE=65536
rem   OUTPUT_DIR=generated/mc6809_coco1_sdl
rem   EXTRA_CARGO_ARGS=--release
rem   EXTRA_CMAKE_ARGS=-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-windows
rem   VCPKG_ROOT=D:\Development\vcpkg
rem   VCPKG_TARGET_TRIPLET=x64-windows
rem   PASM_SDL_AUDIO=1
rem   CMAKE_BUILD_TYPE=Release
rem   RUN_SPEED=realtime|max
rem   CARTRIDGE_MAP=examples/cartridges/coco1/coco_mapper_none.yaml
rem   CARTRIDGE_ROM_GEN=../roms/Downland V1.1 (1983) (26-3046) (Tandy) [a1].ccc
rem   CARTRIDGE_ROM_RUN=C:\path\to\cart.ccc  (optional override for debugger runtime path)

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined START_PC set "START_PC=0xA027"
if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS=--release"
if not defined EXTRA_CMAKE_ARGS set "EXTRA_CMAKE_ARGS="
if not defined VCPKG_TARGET_TRIPLET set "VCPKG_TARGET_TRIPLET=x64-windows"
if not defined PASM_SDL_AUDIO set "PASM_SDL_AUDIO=1"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
rem PowerShell users often escape [ ] with backticks in env vars; strip them if present.
if defined CARTRIDGE_ROM_GEN set "CARTRIDGE_ROM_GEN=%CARTRIDGE_ROM_GEN:`=%"
if defined CARTRIDGE_ROM_RUN set "CARTRIDGE_ROM_RUN=%CARTRIDGE_ROM_RUN:`=%"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1

set "PROCESSOR=examples/processors/mc6809.yaml"
set "IC_MAIN=examples/ics/coco1/coco1_peripherals.yaml"
set "DEVICE_KB=examples/devices/coco1/coco_keyboard.yaml"
set "DEVICE_VIDEO=examples/devices/coco1/coco_video.yaml"
set "DEVICE_SPK=examples/devices/coco1/coco_speaker.yaml"
set "SYSTEM_DIR=examples/systems"

if /I "%PROFILE%"=="default" (
  set "SYSTEM=examples/systems/mc6809/mc6809_coco1_default.yaml"
  set "HOST=examples/hosts/coco1/coco_host_stub.yaml"
  set "DEFAULT_OUTPUT=generated/mc6809_coco1"
) else if /I "%PROFILE%"=="interactive" (
  set "SYSTEM=examples/systems/mc6809/mc6809_coco1_interactive.yaml"
  set "HOST=examples/hosts/coco1/coco_host_sdl2_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/mc6809_coco1_sdl"
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

set "USE_CARTRIDGE=0"
if defined CARTRIDGE_ROM_GEN if not defined CARTRIDGE_MAP set "CARTRIDGE_MAP=examples/cartridges/coco1/coco_mapper_none.yaml"
if defined CARTRIDGE_MAP (
  if not defined CARTRIDGE_ROM_GEN (
    >&2 echo CARTRIDGE_MAP was set but CARTRIDGE_ROM_GEN is missing.
    >&2 echo Set both CARTRIDGE_MAP and CARTRIDGE_ROM_GEN, or set neither.
    exit /b 4
  )
  set "USE_CARTRIDGE=1"
)

for %%I in ("%SYSTEM%") do set "SYSTEM_DIR_ABS=%%~dpI"
if "%SYSTEM_DIR_ABS:~-1%"=="\" set "SYSTEM_DIR_ABS=%SYSTEM_DIR_ABS:~0,-1%"
if not "%USE_CARTRIDGE%"=="1" goto :after_cart_setup
set "CARTRIDGE_ROM_GEN_FOR_GENERATE=%CARTRIDGE_ROM_GEN%"
set "CARTRIDGE_ROM_RUNTIME="
if defined CARTRIDGE_ROM_RUN set "CARTRIDGE_ROM_RUNTIME=%CARTRIDGE_ROM_RUN%"
if not defined CARTRIDGE_ROM_RUN for %%I in ("%SYSTEM_DIR_ABS%\%CARTRIDGE_ROM_GEN:/=\%") do set "CARTRIDGE_ROM_RUNTIME=%%~fI"
if not defined CARTRIDGE_ROM_RUN if not exist "%CARTRIDGE_ROM_RUNTIME%" for %%I in ("%REPO_ROOT%\%CARTRIDGE_ROM_GEN:/=\%") do set "CARTRIDGE_ROM_RUNTIME=%%~fI"
if not defined CARTRIDGE_ROM_RUN if not exist "%CARTRIDGE_ROM_RUNTIME%" for %%I in ("%SCRIPT_DIR%\%CARTRIDGE_ROM_GEN:/=\%") do set "CARTRIDGE_ROM_RUNTIME=%%~fI"
if not defined CARTRIDGE_ROM_RUN if exist "%CARTRIDGE_ROM_RUNTIME%" set "CARTRIDGE_ROM_GEN_FOR_GENERATE=%CARTRIDGE_ROM_RUNTIME%"
if not defined CARTRIDGE_ROM_RUNTIME (
  >&2 echo Cartridge ROM path resolution failed for CARTRIDGE_ROM_GEN="%CARTRIDGE_ROM_GEN%"
  exit /b 4
)
if not exist "%CARTRIDGE_ROM_RUNTIME%" (
  >&2 echo Cartridge ROM not found: "%CARTRIDGE_ROM_RUNTIME%"
  >&2 echo Hint: Use system-relative "..\roms\..." or repo-absolute path.
  exit /b 4
)
:after_cart_setup

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
  if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\bin" (
    set "PATH=%VCPKG_INSTALLED_TRIPLET_DIR%\bin;%PATH%"
  )
)

echo [1/3] Generating emulator -^> %OUTPUT_DIR%
if "%USE_CARTRIDGE%"=="1" goto :gen_with_cart
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_MAIN%" ^
  --device "%DEVICE_KB%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST%" ^
  --output "%OUTPUT_DIR%"
goto :gen_done

:gen_with_cart
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_MAIN%" ^
  --device "%DEVICE_KB%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST%" ^
  --cartridge-map "%CARTRIDGE_MAP%" ^
  --cartridge-rom "%CARTRIDGE_ROM_GEN_FOR_GENERATE%" ^
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
echo     profile=%PROFILE% memory_size=%MEMORY_SIZE% start_pc=%START_PC% sdl_audio=%PASM_SDL_AUDIO% run_speed=%RUN_SPEED% cmake_build_type=%CMAKE_BUILD_TYPE%
if "%USE_CARTRIDGE%"=="1" echo     cartridge_map=%CARTRIDGE_MAP%
if "%USE_CARTRIDGE%"=="1" echo     cartridge_rom_gen=%CARTRIDGE_ROM_GEN%
if "%USE_CARTRIDGE%"=="1" echo     cartridge_rom_runtime=%CARTRIDGE_ROM_RUNTIME%
echo     pasm_emu_dir=%OUTPUT_DIR_ABS%

for %%I in ("%BUILD_DIR%") do set "BUILD_DIR_ABS=%%~fI"
set "CMAKE_CONFIG_BUILD_DIR=%BUILD_DIR%\%CMAKE_BUILD_TYPE%"
for %%I in ("%CMAKE_CONFIG_BUILD_DIR%") do set "CMAKE_CONFIG_BUILD_DIR_ABS=%%~fI"
set "PASM_EMU_DIR=%OUTPUT_DIR_ABS%"
set "PASM_EMU_BUILD_DIR=%BUILD_DIR_ABS%"
if exist "%CMAKE_CONFIG_BUILD_DIR%" set "PASM_EMU_BUILD_DIR=%CMAKE_CONFIG_BUILD_DIR_ABS%"
set "PASM_EMU_MANIFEST=%OUTPUT_DIR_ABS%\debugger_link.json"
echo     pasm_emu_build_dir=%PASM_EMU_BUILD_DIR%
set "PASM_SDL_AUDIO=%PASM_SDL_AUDIO%"

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

if "%USE_CARTRIDGE%"=="1" goto :run_with_cart
"%CARGO_BIN%" run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%"
goto :run_done

:run_with_cart
"%CARGO_BIN%" run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --cart-rom "%CARTRIDGE_ROM_RUNTIME%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%"
:run_done
if errorlevel 1 exit /b %errorlevel%

exit /b 0
