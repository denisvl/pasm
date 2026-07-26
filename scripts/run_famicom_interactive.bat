@echo off
setlocal EnableExtensions

rem Thin wrapper: run Famicom in interactive mode.
rem Usage: scripts\run_famicom_interactive.bat [extra args]

call "%~dp0run_famicom_debugger.bat" interactive %*
exit /b %errorlevel%
