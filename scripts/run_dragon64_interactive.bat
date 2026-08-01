@echo off
setlocal EnableExtensions
call "%~dp0run_dragon64_debugger.bat" interactive %*
exit /b %errorlevel%