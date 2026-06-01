@echo off
setlocal EnableExtensions

call "%~dp0run_amstrad_cpc464_debugger.bat" interactive %*
exit /b %errorlevel%

