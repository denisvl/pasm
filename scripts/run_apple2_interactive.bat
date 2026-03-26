@echo off
setlocal EnableExtensions

call "%~dp0run_apple2_debugger.bat" interactive %*
exit /b %errorlevel%
