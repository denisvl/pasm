@echo off
setlocal EnableExtensions

rem One-shot helper: generate + build + run PASM interactive emulator for Apple I.
rem
rem Usage:
rem   scripts\run_apple1_interactive.bat [--clean]
rem
rem Optional env overrides:
rem   OUTPUT_DIR=generated/apple1_interactive
rem   EXTRA_CMAKE_ARGS=-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-windows
rem   VCPKG_ROOT=D:\Development\vcpkg
rem   VCPKG_TARGET_TRIPLET=x64-windows
rem   CMAKE_BUILD_TYPE=Release
rem   RUN_SPEED=realtime|max
rem   KEYBOARD_MAP=examples/hosts/apple1/host_keyboard_apple1.yaml
rem   JOYSTICK_KEYBOARD_MAP=examples/hosts/apple1/host_keyboard_apple1_joystick.yaml
rem   CONTROLLER_MAP=examples/hosts/apple1/host_controller_apple1.yaml
rem   HOST_BACKEND=glfw

set "CLEAN_BUILD=0"
if "%1"=="--clean" set "CLEAN_BUILD=1"

if not defined MEMORY_SIZE set "MEMORY_SIZE=65536"
if not defined EXTRA_CMAKE_ARGS set "EXTRA_CMAKE_ARGS="
if not defined VCPKG_TARGET_TRIPLET set "VCPKG_TARGET_TRIPLET=x64-windows"
if not defined CMAKE_BUILD_TYPE set "CMAKE_BUILD_TYPE=Release"
if not defined RUN_SPEED set "RUN_SPEED=realtime"
if not defined KEYBOARD_MAP set "KEYBOARD_MAP=examples/hosts/apple1/host_keyboard_apple1.yaml"
if not defined JOYSTICK_KEYBOARD_MAP set "JOYSTICK_KEYBOARD_MAP=examples/hosts/apple1/host_keyboard_apple1_joystick.yaml"
if not defined CONTROLLER_MAP set "CONTROLLER_MAP=examples/hosts/apple1/host_controller_apple1.yaml"
if not defined HOST_BACKEND set "HOST_BACKEND=glfw"

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%" >nul 2>&1

set "PROCESSOR=examples/processors/mos6502.yaml"
set "SYSTEM_DIR=examples/systems/apple1"
set "PASM_SYSTEM_DIR=%SYSTEM_DIR%"
set "IC_PIA=examples/ics/apple/apple1_pia_6820.yaml"
set "IC_CHAR_ROM=examples/ics/apple/apple1_char_rom.yaml"
set "IC_CASSETTE=examples/ics/apple/apple1_cassette_io.yaml"
set "DEVICE_KB=examples/devices/apple1/apple1_keyboard.yaml"
set "DEVICE_VIDEO=examples/devices/apple1/apple1_video.yaml"
set "DEVICE_CASSETTE=examples/devices/common/cassette_transport_nomotor.yaml"
set "HOST_INTERACTIVE=examples/hosts/apple1/apple1_host_hal_interactive.yaml"

set "SYSTEM=examples/systems/apple1/apple1_interactive.yaml"
set "DEFAULT_OUTPUT=generated/apple1_interactive"

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
uv run python -m src.main generate ^
  --processor "%PROCESSOR%" ^
  --system "%SYSTEM%" ^
  --ic "%IC_PIA%" ^
  --ic "%IC_CHAR_ROM%" ^
  --ic "%IC_CASSETTE%" ^
  --device "%DEVICE_KB%" ^
  --device "%DEVICE_VIDEO%" ^
  --device "%DEVICE_CASSETTE%" ^
  --host "%HOST_INTERACTIVE%" ^
  --host-backend "%HOST_BACKEND%" ^
  --output "%OUTPUT_DIR%"
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

echo [3/3] Running interactive emulator
echo     profile=interactive memory_size=%MEMORY_SIZE% run_speed=%RUN_SPEED% cmake_build_type=%CMAKE_BUILD_TYPE%

for %%I in ("%BUILD_DIR%") do set "BUILD_DIR_ABS=%%~fI"
set "CMAKE_CONFIG_BUILD_DIR=%BUILD_DIR%\%CMAKE_BUILD_TYPE%"
for %%I in ("%CMAKE_CONFIG_BUILD_DIR%") do set "CMAKE_CONFIG_BUILD_DIR_ABS=%%~fI"
set "PASM_EMU_DIR=%OUTPUT_DIR_ABS%"
set "PASM_EMU_BUILD_DIR=%BUILD_DIR_ABS%"
if exist "%CMAKE_CONFIG_BUILD_DIR%" set "PASM_EMU_BUILD_DIR=%CMAKE_CONFIG_BUILD_DIR_ABS%"

cd /d "%REPO_ROOT%"
if errorlevel 1 exit /b %errorlevel%

"%CMAKE_CONFIG_BUILD_DIR_ABS%\pasm_interactive.exe" --system "%PASM_EMU_DIR%/system.yaml"
if errorlevel 1 exit /b %errorlevel%

echo.
echo Interactive session ended.