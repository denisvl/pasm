@echo off
setlocal
call "%~dp0run_sg1000_debugger.bat" interactive %*
exit /b %ERRORLEVEL%
