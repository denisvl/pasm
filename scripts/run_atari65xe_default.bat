@echo off
setlocal EnableExtensions

call "%~dp0run_atari65xe_debugger.bat" default %*
exit /b %errorlevel%