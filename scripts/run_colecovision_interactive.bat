@echo off
setlocal
call "%~dp0run_colecovision_debugger.bat" interactive %*
exit /b %ERRORLEVEL%
