@echo off
setlocal
call "%~dp0run_sms_debugger.bat" interactive %*
exit /b %ERRORLEVEL%
