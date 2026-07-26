@echo off
setlocal
call "%~dp0run_sg1000ii_debugger.bat" interactive %*
exit /b %ERRORLEVEL%
