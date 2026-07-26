@echo off
setlocal EnableExtensions
call "%~dp0run_coco2_debugger.bat" default %*
exit /b %errorlevel%
