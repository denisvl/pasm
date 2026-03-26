@echo off
setlocal EnableExtensions

rem One-shot helper: generate + build + run PASM Rust debugger for MSX.
rem
rem Usage:
rem   scripts\run_msx_debugger.bat [interactive^|default]
rem
rem Optional env overrides:
rem   START_PC=0x0000
rem   MEMORY_SIZE=65536
rem   OUTPUT_DIR=generated/z80_msx1_sdl
rem   EXTRA_CARGO_ARGS=--release
rem   USE_CARTRIDGE=1|0
rem   CARTRIDGE_MAP=examples/cartridges/msx1/msx_mapper_konami.yaml
rem   CARTRIDGE_ROM_GEN=../roms/Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom
rem   CARTRIDGE_ROM_RUNTIME=C:\full\path\to\rom.rom
rem   EXTRA_CMAKE_ARGS=-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-windows
rem   VCPKG_ROOT=D:\Development\vcpkg
rem   VCPKG_TARGET_TRIPLET=x64-windows
rem   PASM_SDL_DEBUG=1
rem   PASM_SDL_LOGFILE=%TEMP%\msx_sdl.log
rem   PASM_SDL_AUDIO=1|0
rem   PASM_MSX_JOY_BUTTONS=1|2   (1=KP0/KP_ENTER, 2=KP1/KP2)
rem   CMAKE_BUILD_TYPE=Release
rem   RUN_SPEED=realtime|max

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined START_PC set "START_PC=0x0000"
if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS="
if not defined EXTRA_CMAKE_ARGS set "EXTRA_CMAKE_ARGS="
if not defined VCPKG_TARGET_TRIPLET set "VCPKG_TARGET_TRIPLET=x64-windows"
if not defined PASM_SDL_DEBUG set "PASM_SDL_DEBUG=0"
if not defined PASM_SDL_LOGFILE set "PASM_SDL_LOGFILE=%TEMP%\msx_sdl.log"
if not defined PASM_SDL_AUDIO set "PASM_SDL_AUDIO=1"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined USE_CARTRIDGE set "USE_CARTRIDGE=1"
if not defined CARTRIDGE_MAP set "CARTRIDGE_MAP=examples/cartridges/msx1/msx_mapper_konami.yaml"
if not defined CARTRIDGE_ROM_GEN set "CARTRIDGE_ROM_GEN=../roms/Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not defined CARTRIDGE_ROM_RUNTIME set "CARTRIDGE_ROM_RUNTIME=%REPO_ROOT%\examples\roms\Penguin Adventure - Yumetairiku Adventure (1986) Konami [Konami Antiques MSX Collection 3 - RC-743] [2539].rom"

set "PROCESSOR=examples/processors/z80.yaml"
set "IC_VDP=examples/ics/msx1/msx1_vdp_tms9918a.yaml"
set "IC_PPI=examples/ics/msx1/msx1_ppi_8255.yaml"
set "IC_PSG=examples/ics/msx1/msx1_psg_ay8910.yaml"
set "DEVICE_KB=examples/devices/msx1/msx_keyboard.yaml"
set "DEVICE_VIDEO=examples/devices/msx1/msx_video.yaml"
set "DEVICE_SPK=examples/devices/msx1/msx_speaker.yaml"
set "SYSTEM_DIR=examples/systems"

if /I "%PROFILE%"=="default" (
  if "%USE_CARTRIDGE%"=="0" (
    set "SYSTEM=examples/systems/msx1/z80_msx1_default.yaml"
  ) else (
    set "SYSTEM=examples/systems/msx1/z80_msx1_cartridge_default.yaml"
  )
  set "HOST=examples/hosts/msx1/msx_host_stub.yaml"
  set "DEFAULT_OUTPUT=generated/z80_msx1"
) else if /I "%PROFILE%"=="interactive" (
  if "%USE_CARTRIDGE%"=="0" (
    set "SYSTEM=examples/systems/msx1/z80_msx1_interactive.yaml"
  ) else (
    set "SYSTEM=examples/systems/msx1/z80_msx1_cartridge_interactive.yaml"
  )
  set "HOST=examples/hosts/msx1/msx_host_sdl2_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/z80_msx1_sdl"
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
if "%USE_CARTRIDGE%"=="0" (
  uv run python -m src.main generate ^
    --processor "%PROCESSOR%" ^
    --system "%SYSTEM%" ^
    --ic "%IC_VDP%" ^
    --ic "%IC_PPI%" ^
    --ic "%IC_PSG%" ^
    --device "%DEVICE_KB%" ^
    --device "%DEVICE_VIDEO%" ^
    --device "%DEVICE_SPK%" ^
    --host "%HOST%" ^
    --output "%OUTPUT_DIR%"
) else (
  uv run python -m src.main generate ^
    --processor "%PROCESSOR%" ^
    --system "%SYSTEM%" ^
    --ic "%IC_VDP%" ^
    --ic "%IC_PPI%" ^
    --ic "%IC_PSG%" ^
    --device "%DEVICE_KB%" ^
    --device "%DEVICE_VIDEO%" ^
    --device "%DEVICE_SPK%" ^
    --host "%HOST%" ^
    --cartridge-map "%CARTRIDGE_MAP%" ^
    --cartridge-rom "%CARTRIDGE_ROM_GEN%" ^
    --output "%OUTPUT_DIR%"
)
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
if not "%USE_CARTRIDGE%"=="0" (
  echo     cartridge_map=%CARTRIDGE_MAP%
  echo     cartridge_rom_gen=%CARTRIDGE_ROM_GEN%
  echo     cartridge_rom_runtime=%CARTRIDGE_ROM_RUNTIME%
)
if /I "%PROFILE%"=="interactive" (
  if not "%PASM_SDL_DEBUG%"=="0" echo     SDL debug log -^> %PASM_SDL_LOGFILE%
)

for %%I in ("%BUILD_DIR%") do set "BUILD_DIR_ABS=%%~fI"
set "CMAKE_CONFIG_BUILD_DIR=%BUILD_DIR%\%CMAKE_BUILD_TYPE%"
for %%I in ("%CMAKE_CONFIG_BUILD_DIR%") do set "CMAKE_CONFIG_BUILD_DIR_ABS=%%~fI"
set "PASM_EMU_DIR=%OUTPUT_DIR_ABS%"
set "PASM_EMU_BUILD_DIR=%BUILD_DIR_ABS%"
if exist "%CMAKE_CONFIG_BUILD_DIR%" set "PASM_EMU_BUILD_DIR=%CMAKE_CONFIG_BUILD_DIR_ABS%"
set "PASM_EMU_MANIFEST=%OUTPUT_DIR_ABS%\debugger_link.json"
set "PASM_SDL_DEBUG=%PASM_SDL_DEBUG%"
set "PASM_SDL_LOGFILE=%PASM_SDL_LOGFILE%"
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

if "%USE_CARTRIDGE%"=="0" (
  "%CARGO_BIN%" run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size "%MEMORY_SIZE%" ^
    --system-dir "%SYSTEM_DIR%" ^
    --start-pc "%START_PC%" ^
    --run-speed "%RUN_SPEED%"
) else (
  "%CARGO_BIN%" run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
    --backend linked ^
    --memory-size "%MEMORY_SIZE%" ^
    --system-dir "%SYSTEM_DIR%" ^
    --cart-rom "%CARTRIDGE_ROM_RUNTIME%" ^
    --start-pc "%START_PC%" ^
    --run-speed "%RUN_SPEED%"
)
if errorlevel 1 exit /b %errorlevel%

exit /b 0
