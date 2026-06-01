@echo off
setlocal EnableExtensions

call "%~dp0run_msx_debugger.bat" %*
exit /b %errorlevel%

