@echo off
setlocal EnableExtensions

call "%~dp0run_atari2600_debugger.bat" interactive %*
exit /b %errorlevel%

