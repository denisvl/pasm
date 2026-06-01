@echo off
setlocal EnableExtensions

rem One-shot helper: generate + build + run PASM Rust debugger for Atari 800XL.
rem
rem Usage:
rem   scripts\run_atari800xl_debugger.bat [interactive^|default]
rem
rem Optional env overrides:
rem   START_PC=0xE477    (optional; if unset, uses reset vector)
rem   MEMORY_SIZE=65536
rem   OUTPUT_DIR=generated/atari800xl_interactive
rem   EXTRA_CARGO_ARGS=--release
rem   EXTRA_CMAKE_ARGS=-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-windows
rem   VCPKG_ROOT=D:\Development\vcpkg
rem   VCPKG_TARGET_TRIPLET=x64-windows
rem   CMAKE_BUILD_TYPE=Release
rem   RUN_SPEED=realtime|max
rem   PASM_SDL_AUDIO=1

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS=--release"
if not defined EXTRA_CMAKE_ARGS set "EXTRA_CMAKE_ARGS="
if not defined VCPKG_TARGET_TRIPLET set "VCPKG_TARGET_TRIPLET=x64-windows"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined PASM_HOST_AUDIO set "PASM_HOST_AUDIO=1"
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/atari800xl/host_keyboard_atari800xl.yaml"
if not defined USE_CARTRIDGE set "USE_CARTRIDGE=1"
if not defined BOOT_CARTRIDGE set "BOOT_CARTRIDGE=0"
if not defined PASM_EMU_CART_PICKER_RAW_KEYS set "PASM_EMU_CART_PICKER_RAW_KEYS=1"
if not defined CARTRIDGE_MAP set "CARTRIDGE_MAP=examples/cartridges/atari800xl/atari800xl_cart_8k_none.yaml"
if not defined CARTRIDGE_ROM_GEN set "CARTRIDGE_ROM_GEN=../../roms/atari800xl/Star_Raiders_1979_Atari_US.rom"
if not defined CARTRIDGE_ROM_RUNTIME set "CARTRIDGE_ROM_RUNTIME="
if not defined OS_ROM set "OS_ROM=../../roms/atari800xl/ATARIXL.ROM"
if not defined BASIC_ROM set "BASIC_ROM=../../roms/atari800xl/BASIC_C.ROM"
if not defined SELFTEST_ROM set "SELFTEST_ROM=../../roms/atari800xl/ATARIXL_SELFTEST.ROM"
if not defined HOST_BACKEND set "HOST_BACKEND=sdl2"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1

set "PROCESSOR=examples/processors/mos6502.yaml"
set "IC_ANTIC=examples/ics/atari800xl/atari800xl_antic.yaml"
set "IC_GTIA=examples/ics/atari800xl/atari800xl_gtia.yaml"
set "IC_POKEY=examples/ics/atari800xl/atari800xl_pokey.yaml"
set "IC_PIA=examples/ics/atari800xl/atari800xl_pia_6520.yaml"
set "IC_MMU=examples/ics/atari800xl/atari800xl_mmu.yaml"
set "IC_MAIN_RAM=examples/ics/atari800xl/atari800xl_main_ram.yaml"
set "DEVICE_KB=examples/devices/atari800xl/atari800xl_keyboard.yaml"
set "DEVICE_CTRL=examples/devices/atari800xl/atari800xl_controller.yaml"
set "DEVICE_VIDEO=examples/devices/atari800xl/atari800xl_video.yaml"
set "DEVICE_SPK=examples/devices/atari800xl/atari800xl_speaker.yaml"
set "SYSTEM_DIR=examples/systems/atari800xl"

if /I "%PROFILE%"=="default" (
  if "%USE_CARTRIDGE%"=="0" (
    set "SYSTEM=examples/systems/atari800xl/atari800xl_default.yaml"
  ) else (
    set "SYSTEM=examples/systems/atari800xl/atari800xl_cartridge_default.yaml"
  )
  set "HOST=examples/hosts/atari800xl/atari800xl_host_stub.yaml"
  set "DEFAULT_OUTPUT=generated/atari800xl_default"
) else if /I "%PROFILE%"=="interactive" (
  if "%USE_CARTRIDGE%"=="0" (
    set "SYSTEM=examples/systems/atari800xl/atari800xl_interactive.yaml"
  ) else (
    set "SYSTEM=examples/systems/atari800xl/atari800xl_cartridge_interactive.yaml"
  )
  set "HOST=examples/hosts/atari800xl/atari800xl_host_hal_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/atari800xl_interactive"
) else (
  >&2 echo Unsupported profile: %PROFILE%
  >&2 echo Use: default ^| interactive
  exit /b 2
)

if not defined OUTPUT_DIR set "OUTPUT_DIR=%DEFAULT_OUTPUT%"
set "BUILD_DIR=%OUTPUT_DIR%/build"
for %%I in ("%SYSTEM%") do (
  set "SYSTEM_FOR_GEN=%SYSTEM%"
  set "SYSTEM_DIR_ABS=%%~dpI"
)
if "%SYSTEM_DIR_ABS:~-1%"=="\" set "SYSTEM_DIR_ABS=%SYSTEM_DIR_ABS:~0,-1%"
if not defined CARTRIDGE_DIR set "CARTRIDGE_DIR=%REPO_ROOT%\examples\roms\atari800xl"

set "GEN_CARTRIDGE_ARGS="
set "RUN_CARTRIDGE_ARGS="
set "GEN_CARTRIDGE_ROM=%CARTRIDGE_ROM_GEN%"
set "ROM_RUNTIME=%CARTRIDGE_ROM_RUNTIME%"
if not defined ROM_RUNTIME set "ROM_RUNTIME="
if not "%USE_CARTRIDGE%"=="0" (
  set "RUN_CARTRIDGE_ARGS=--cartridge-dir ""%CARTRIDGE_DIR%"""
  if not "%BOOT_CARTRIDGE%"=="0" (
    if not defined CARTRIDGE_ROM_RUNTIME set "ROM_RUNTIME=%SYSTEM_DIR_ABS%\%CARTRIDGE_ROM_GEN%"
    set "RUN_CARTRIDGE_ARGS=%RUN_CARTRIDGE_ARGS% --cart-rom ""%ROM_RUNTIME%"""
  ) else (
    set "GEN_CARTRIDGE_ROM=%BASIC_ROM%"
  )
  set "GEN_CARTRIDGE_ARGS=--cartridge-map ""%CARTRIDGE_MAP%"" --cartridge-rom ""%GEN_CARTRIDGE_ROM%"""
)

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
set "TMP_SYSTEM=%SYSTEM_DIR_ABS%\.tmp_atari800xl_system_%RANDOM%%RANDOM%.yaml"
uv run python -c "import yaml,sys; src,dst,osr,bas,st=sys.argv[1:6]; data=yaml.safe_load(open(src,'r',encoding='utf-8')); imgs=((data.get('memory') or {}).get('rom_images') or []); [rom.__setitem__('file', bas if str(rom.get('name',''))=='atari800xl_basic' else st if str(rom.get('name',''))=='atari800xl_selftest' else osr if str(rom.get('name','')) in ('atari800xl_os','atari800xl_os_rom') else rom.get('file')) for rom in imgs]; yaml.safe_dump(data,open(dst,'w',encoding='utf-8'),sort_keys=False)" "%SYSTEM%" "%TMP_SYSTEM%" "%OS_ROM%" "%BASIC_ROM%" "%SELFTEST_ROM%"
if errorlevel 1 exit /b %errorlevel%

uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%TMP_SYSTEM%" ^
  --ic "%IC_ANTIC%" ^
  --ic "%IC_GTIA%" ^
  --ic "%IC_POKEY%" ^
  --ic "%IC_PIA%" ^
  --ic "%IC_MMU%" ^
  --ic "%IC_MAIN_RAM%" ^
  --device "%DEVICE_KB%" ^
  --device "%DEVICE_CTRL%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_SPK%" ^
  --host "%HOST%" ^
  --host-backend "%HOST_BACKEND%" ^
  %GEN_CARTRIDGE_ARGS% ^
  --output "%OUTPUT_DIR%"
if errorlevel 1 exit /b %errorlevel%
if exist "%TMP_SYSTEM%" del /q "%TMP_SYSTEM%" >nul 2>&1

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
set "PASM_HOST_AUDIO=%PASM_HOST_AUDIO%"
set "PASM_SYSTEM_DIR=%SYSTEM_DIR_ABS%"
set "PASM_EMU_CART_PICKER_RAW_KEYS=%PASM_EMU_CART_PICKER_RAW_KEYS%"

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
  %RUN_CARTRIDGE_ARGS% ^
  --run-speed "%RUN_SPEED%"
goto :run_done

:run_with_start_pc
"%CARGO_BIN%" run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  %RUN_CARTRIDGE_ARGS% ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%"
:run_done
if errorlevel 1 exit /b %errorlevel%

exit /b 0
