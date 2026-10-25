@echo off
setlocal
set INSTALL_DIR=%~dp0
set NSSM=%INSTALL_DIR%tools\nssm.exe

net session >nul 2>nul || (echo [ERROR] Run as Administrator. & exit /b 1)

net stop AMBER-Backend >nul 2>nul
net stop AMBER-Mongo   >nul 2>nul
"%NSSM%" remove AMBER-Backend confirm >nul 2>nul
"%NSSM%" remove AMBER-Mongo   confirm >nul 2>nul

echo AMBER services removed.
endlocal
