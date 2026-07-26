@echo off
call "%~dp0run_c64c_debugger.bat" interactive %*
exit /b %errorlevel%
