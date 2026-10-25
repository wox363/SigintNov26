@echo off
REM ============================================================================
REM AMBER — start MongoDB and the backend, then open the browser.
REM Double-click this. Closes everything when you close the console window.
REM ============================================================================
setlocal
set INSTALL_DIR=%~dp0
set DATA_DIR=%AMBER_DATA_DIR%
if "%DATA_DIR%"=="" set DATA_DIR=C:\AMBER-Data

if not exist "%DATA_DIR%\mongo"  mkdir "%DATA_DIR%\mongo"
if not exist "%DATA_DIR%\logs"   mkdir "%DATA_DIR%\logs"

echo ============================================================
echo   AMBER  -  Offline SIGINT Forensic Platform
echo ============================================================
echo Data directory: %DATA_DIR%
echo.

REM Make the bundled Tesseract findable by pytesseract
set "PATH=%INSTALL_DIR%tesseract;%PATH%"
set "TESSDATA_PREFIX=%INSTALL_DIR%tesseract\tessdata"

REM --- Start MongoDB ---
echo [1/3] Starting MongoDB on 127.0.0.1:27017 ...
start "AMBER-Mongo" /MIN "%INSTALL_DIR%mongodb\bin\mongod.exe" ^
    --dbpath "%DATA_DIR%\mongo" ^
    --bind_ip 127.0.0.1 ^
    --port 27017 ^
    --logpath "%DATA_DIR%\logs\mongod.log" ^
    --quiet

REM Wait up to 15s for Mongo to accept connections
set /a tries=0
:wait_mongo
timeout /t 1 /nobreak >nul
"%INSTALL_DIR%mongodb\bin\mongod.exe" --version >nul 2>nul
powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',27017); exit 0 } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 goto mongo_up
set /a tries+=1
if %tries% lss 15 goto wait_mongo
echo [WARN] MongoDB did not respond on 27017 after 15s — check %DATA_DIR%\logs\mongod.log
:mongo_up

REM --- Start backend ---
echo [2/3] Starting AMBER backend on 127.0.0.1:8001 ...
set "MONGO_URL=mongodb://127.0.0.1:27017"
set "DB_NAME=amber_offline"
set "CORS_ORIGINS=http://127.0.0.1:8001,http://localhost:8001"
set "MAX_UPLOAD_MB=50"
start "AMBER-Backend" /MIN "%INSTALL_DIR%backend\amber-backend.exe"

REM Wait up to 20s for backend
set /a tries=0
:wait_backend
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8001/api/health' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 goto backend_up
set /a tries+=1
if %tries% lss 20 goto wait_backend
echo [WARN] Backend did not respond on 8001 after 20s.
:backend_up

REM --- Open browser ---
echo [3/3] Opening AMBER in your browser ...
start "" "http://127.0.0.1:8001/"

echo.
echo AMBER is running. Close this window to stop everything.
echo.
pause
endlocal

REM On exit, kill the background services
taskkill /FI "WINDOWTITLE eq AMBER-Backend" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq AMBER-Mongo"   /T /F >nul 2>nul
