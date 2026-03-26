@echo off
setlocal EnableExtensions

call "%~dp0run_atari800xl_debugger.bat" interactive %*
exit /b %errorlevel%
