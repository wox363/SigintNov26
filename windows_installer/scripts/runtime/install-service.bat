@echo off
REM Register MongoDB + AMBER backend as Windows Services so they auto-start on boot.
REM Must be run as Administrator. Uses NSSM (the Non-Sucking Service Manager).
REM Ship a tiny nssm.exe in the installer (~300 KB) under tools\.
setlocal
set INSTALL_DIR=%~dp0
set DATA_DIR=C:\AMBER-Data
set NSSM=%INSTALL_DIR%tools\nssm.exe

if not exist "%NSSM%" (
    echo [ERROR] nssm.exe not found at %NSSM%
    echo         Drop the 64-bit build into windows_installer\scripts\runtime\tools\
    echo         before running install-service.bat.
    exit /b 1
)

net session >nul 2>nul || (
    echo [ERROR] Must run as Administrator.
    exit /b 1
)

echo Installing AMBER-Mongo service ...
"%NSSM%" install AMBER-Mongo "%INSTALL_DIR%mongodb\bin\mongod.exe" ^
    --dbpath "%DATA_DIR%\mongo" --bind_ip 127.0.0.1 --port 27017 ^
    --logpath "%DATA_DIR%\logs\mongod.log" --quiet
"%NSSM%" set AMBER-Mongo Start SERVICE_AUTO_START
"%NSSM%" set AMBER-Mongo Description "AMBER local MongoDB (offline)"

echo Installing AMBER-Backend service ...
"%NSSM%" install AMBER-Backend "%INSTALL_DIR%backend\amber-backend.exe"
"%NSSM%" set AMBER-Backend AppEnvironmentExtra ^
    MONGO_URL=mongodb://127.0.0.1:27017 ^
    DB_NAME=amber_offline ^
    MAX_UPLOAD_MB=50 ^
    "TESSDATA_PREFIX=%INSTALL_DIR%tesseract\tessdata"
"%NSSM%" set AMBER-Backend AppDirectory "%INSTALL_DIR%backend"
"%NSSM%" set AMBER-Backend Start SERVICE_AUTO_START
"%NSSM%" set AMBER-Backend DependOnService AMBER-Mongo
"%NSSM%" set AMBER-Backend Description "AMBER FastAPI backend (offline)"

echo Starting services ...
net start AMBER-Mongo
net start AMBER-Backend

echo Done. AMBER will start automatically on every boot.
echo Open http://127.0.0.1:8001/ in your browser.
endlocal
