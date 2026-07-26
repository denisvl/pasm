@echo off
setlocal EnableExtensions

call "%~dp0run_atari65xe_debugger.bat" interactive %*
exit /b %errorlevel%