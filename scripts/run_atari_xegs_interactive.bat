@echo off
setlocal EnableExtensions

call "%~dp0run_atari_xegs_debugger.bat" interactive %*
exit /b %errorlevel%
