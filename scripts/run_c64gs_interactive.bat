@echo off
setlocal EnableExtensions

call "%~dp0run_c64gs_debugger.bat" interactive %*
exit /b %errorlevel%

