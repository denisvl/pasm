@echo off
setlocal EnableExtensions

set "PROFILE=%~1"
if not defined PROFILE set "PROFILE=interactive"

if not defined START_PC set "START_PC=0xC02C"
if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CARGO_ARGS set "EXTRA_CARGO_ARGS=--release"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/atari800xl/host_keyboard_atari800xl.yaml"
if not defined OS_ROM_LOW set "OS_ROM_LOW=../../roms/atari_xegs/c101687.rom"
if not defined OS_ROM_HIGH set "OS_ROM_HIGH=../../roms/atari_xegs/c101687.rom"
if not defined SELFTEST_ROM set "SELFTEST_ROM=../../roms/atari_xegs/c101687.rom"
if not defined BASIC_ROM set "BASIC_ROM=../../roms/atari_xegs/c101687.rom"
if not defined HOST_BACKEND set "HOST_BACKEND=glfw"
if not defined VCPKG_TARGET_TRIPLET set "VCPKG_TARGET_TRIPLET=x64-windows"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1

rem Resolve vcpkg installation directory for DLL dependencies (glfw3.dll, SDL2.dll)
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

rem Configure CMake to use vcpkg toolchain if not already set
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

rem Add vcpkg bin to PATH so DLL dependencies are found at runtime
if defined VCPKG_INSTALLED_TRIPLET_DIR (
  if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\bin" (
    set "PATH=%VCPKG_INSTALLED_TRIPLET_DIR%\bin;%PATH%"
  )
)

set "PROCESSOR=examples/processors/mos6502.yaml"
set "IC_ANTIC=examples/ics/atari800xl/atari800xl_antic.yaml"
set "IC_GTIA=examples/ics/atari800xl/atari800xl_gtia.yaml"
set "IC_POKEY=examples/ics/atari800xl/atari800xl_pokey.yaml"
set "IC_PIA=examples/ics/atari800xl/atari800xl_pia_6520.yaml"
set "IC_MMU=examples/ics/atari800xl/atari800xl_mmu.yaml"
set "IC_MAIN_RAM=examples/ics/atari800xl/atari800xl_main_ram.yaml"
set "DEVICE_CTRL=examples/devices/atari800xl/atari800xl_controller.yaml"
set "DEVICE_VIDEO=examples/devices/atari800xl/atari800xl_video.yaml"
set "DEVICE_SPEAKER=examples/devices/atari800xl/atari800xl_speaker.yaml"
set "DEVICE_TV=examples/devices/common/tv_crt_mono.yaml"
set "DEVICE_KEYBOARD=examples/devices/atari800xl/atari800xl_keyboard.yaml"

if /I "%PROFILE%"=="default" (
  set "SYSTEM=examples/systems/atari_xegs/atari_xegs_default.yaml"
  set "HOST=examples/hosts/atari800xl/atari800xl_host_stub.yaml"
  set "DEFAULT_OUTPUT=generated/atari_xegs_default"
  set "DEVICE_FLAGS=--device "%DEVICE_CTRL%" --device "%DEVICE_VIDEO%" --device "%DEVICE_SPEAKER%" --device "%DEVICE_TV%""
) else if /I "%PROFILE%"=="interactive" (
  set "SYSTEM=examples/systems/atari_xegs/atari_xegs_interactive.yaml"
  set "HOST=examples/hosts/atari800xl/atari800xl_host_hal_interactive.yaml"
  set "DEFAULT_OUTPUT=generated/atari_xegs_interactive"
  set "DEVICE_FLAGS=--device "%DEVICE_KEYBOARD%" --device "%DEVICE_CTRL%" --device "%DEVICE_VIDEO%" --device "%DEVICE_SPEAKER%" --device "%DEVICE_TV%""
) else (
  >&2 echo Unsupported profile: %PROFILE%
  >&2 echo Use: default ^| interactive
  exit /b 2
)

for %%I in ("%SYSTEM%") do set "SYSTEM_DIR=%%~dpI"
if "%SYSTEM_DIR:~-1%"=="\" set "SYSTEM_DIR=%SYSTEM_DIR:~0,-1%"

if not defined OUTPUT_DIR set "OUTPUT_DIR=%DEFAULT_OUTPUT%"
set "BUILD_DIR=%OUTPUT_DIR%/build"
for %%I in ("%OUTPUT_DIR%") do set "OUTPUT_DIR_ABS=%%~fI"
for %%I in ("%BUILD_DIR%") do set "BUILD_DIR_ABS=%%~fI"
set "CMAKE_CONFIG_BUILD_DIR=%BUILD_DIR%\%CMAKE_BUILD_TYPE%"
for %%I in ("%CMAKE_CONFIG_BUILD_DIR%") do set "CMAKE_CONFIG_BUILD_DIR_ABS=%%~fI"

echo [1/3] Generating emulator -^> %OUTPUT_DIR%
set "TMP_SYSTEM=%SYSTEM_DIR%\.tmp_atari_xegs_system_%RANDOM%%RANDOM%.yaml"
uv run python -c "import yaml,sys; src,dst,osl,osh,st,bas=sys.argv[1:7]; data=yaml.safe_load(open(src,'r',encoding='utf-8')); imgs=((data.get('memory') or {}).get('rom_images') or []); [rom.__setitem__('file', bas if str(rom.get('name',''))=='atari_xegs_basic' else st if str(rom.get('name',''))=='atari_xegs_selftest' else osl if str(rom.get('name',''))=='atari_xegs_os_low' else osh if str(rom.get('name',''))=='atari_xegs_os_high' else rom.get('file')) for rom in imgs]; yaml.safe_dump(data,open(dst,'w',encoding='utf-8'),sort_keys=False)" "%SYSTEM%" "%TMP_SYSTEM%" "%OS_ROM_LOW%" "%OS_ROM_HIGH%" "%SELFTEST_ROM%" "%BASIC_ROM%"
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
  %DEVICE_FLAGS% ^
  --host "%HOST%" ^
  --host-backend "%HOST_BACKEND%" ^
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
set "PASM_TRACE=%PASM_TRACE%"
set "PASM_TRACE_FILE="
set "PASM_ATARI800XL_KEY_TRACE=%PASM_ATARI800XL_KEY_TRACE%"
set "PASM_ATARI800XL_KB_EVENTS=%PASM_ATARI800XL_KB_EVENTS%"
set "PASM_SYSTEM_DIR=%SYSTEM_DIR%"

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

"%CARGO_BIN%" build %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator
if errorlevel 1 exit /b %errorlevel%

rem Copy runtime DLL dependencies (glfw3.dll, SDL2.dll) next to the built exe
rem to avoid STATUS_DLL_NOT_FOUND (0xc0000135) at process launch.
set "TARGET_PROFILE_DIR=tools\debugger_tui\target\release"
echo %EXTRA_CARGO_ARGS% | findstr /i "debug" >nul 2>&1 && set "TARGET_PROFILE_DIR=tools\debugger_tui\target\debug"
if not exist "%TARGET_PROFILE_DIR%" mkdir "%TARGET_PROFILE_DIR%" >nul 2>&1

if defined VCPKG_INSTALLED_TRIPLET_DIR (
  for %%D in (glfw3.dll SDL2.dll) do (
    if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\bin\%%D" (
      copy /y "%VCPKG_INSTALLED_TRIPLET_DIR%\bin\%%D" "%TARGET_PROFILE_DIR%\%%D" >nul 2>&1
      echo Copied %%D to %TARGET_PROFILE_DIR%
    ) else if exist "%VCPKG_INSTALLED_TRIPLET_DIR%\debug\bin\%%D" (
      copy /y "%VCPKG_INSTALLED_TRIPLET_DIR%\debug\bin\%%D" "%TARGET_PROFILE_DIR%\%%D" >nul 2>&1
      echo Copied %%D ^(debug^) to %TARGET_PROFILE_DIR%
    ) else (
      >&2 echo Warning: %%D not found in vcpkg installed dir
    )
  )
) else (
  >&2 echo Warning: VCPKG_INSTALLED_TRIPLET_DIR not set - skipping DLL copy
  >&2 echo Set VCPKG_ROOT or ensure glfw3.dll/SDL2.dll are on PATH
)

if defined START_PC goto :run_with_start_pc
"%CARGO_BIN%" run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --run-speed "%RUN_SPEED%"
goto :run_done

:run_with_start_pc
"%CARGO_BIN%" run %EXTRA_CARGO_ARGS% --manifest-path tools/debugger_tui/Cargo.toml --features linked-emulator -- ^
  --backend linked ^
  --memory-size "%MEMORY_SIZE%" ^
  --system-dir "%SYSTEM_DIR%" ^
  --keyboard-map "%KEYBOARD_MAP%" ^
  --start-pc "%START_PC%" ^
  --run-speed "%RUN_SPEED%"
:run_done
if errorlevel 1 exit /b %errorlevel%

exit /b 0