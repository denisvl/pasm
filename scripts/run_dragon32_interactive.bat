@echo off
setlocal EnableExtensions
call "%~dp0run_dragon32_debugger.bat" interactive %*
exit /b %errorlevel%
