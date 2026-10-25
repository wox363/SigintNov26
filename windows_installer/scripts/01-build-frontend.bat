@echo off
REM Build the React production bundle with localhost backend URL.
setlocal
set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..\..

echo.
echo --- [1/4] Building React frontend (localhost target) ---
cd /d "%ROOT_DIR%\frontend" || exit /b 1

REM Override the dev preview URL so the production bundle hits the local backend.
set "REACT_APP_BACKEND_URL=http://127.0.0.1:8001"
set "WDS_SOCKET_PORT=0"
set "ENABLE_HEALTH_CHECK=false"

call yarn install --frozen-lockfile || exit /b 1
call yarn build || exit /b 1

if not exist "build\index.html" (
    echo [ERROR] frontend build did not produce build\index.html
    exit /b 1
)
echo Frontend build OK: %ROOT_DIR%\frontend\build
endlocal
