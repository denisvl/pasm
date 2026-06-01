@echo off
setlocal
call "%~dp0run_zx48_debugger.bat" interactive %*
exit /b %ERRORLEVEL%
