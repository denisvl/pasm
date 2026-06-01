@echo off
setlocal
call "%~dp0run_trs80_model4_debugger.bat" interactive %*
exit /b %ERRORLEVEL%
