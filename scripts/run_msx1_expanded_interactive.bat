@echo off
setlocal EnableExtensions

call "%~dp0run_msx1_expanded_debugger.bat" interactive %*
exit /b %errorlevel%

