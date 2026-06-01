@echo off
setlocal EnableExtensions

if not defined HOST_FILE set "HOST_FILE=examples/hosts/bbcmicro/bbc_micro_host_hal_interactive.yaml"
call "%~dp0run_bbc_micro_debugger.bat" interactive %*
exit /b %errorlevel%

