@echo off
setlocal EnableExtensions

call "%~dp0run_csx64_debugger.bat" interactive %*
exit /b %errorlevel%
