@echo off
setlocal EnableExtensions

call "%~dp0run_c64_debugger.bat" interactive %*
exit /b %errorlevel%
