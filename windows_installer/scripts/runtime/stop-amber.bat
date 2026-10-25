@echo off
REM Stop AMBER backend and MongoDB.
taskkill /FI "WINDOWTITLE eq AMBER-Backend" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq AMBER-Mongo"   /T /F >nul 2>nul
taskkill /IM amber-backend.exe /F >nul 2>nul
taskkill /IM mongod.exe /F >nul 2>nul
echo AMBER stopped.
timeout /t 2 /nobreak >nul
