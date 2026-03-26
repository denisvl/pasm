@echo off
setlocal EnableExtensions

call "%~dp0run_coco_debugger.bat" interactive %*
exit /b %errorlevel%
