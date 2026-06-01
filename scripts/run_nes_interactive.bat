@echo off
setlocal EnableExtensions

call "%~dp0run_nes_debugger.bat" interactive %*
exit /b %errorlevel%

