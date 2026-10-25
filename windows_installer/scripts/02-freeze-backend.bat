@echo off
REM Freeze the FastAPI backend into a Windows EXE using PyInstaller.
setlocal
set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..\..

echo.
echo --- [2/4] Freezing backend with PyInstaller ---
cd /d "%ROOT_DIR%\backend" || exit /b 1

REM Ensure PyInstaller is installed (build machine only — never on target)
python -m pip install --quiet pyinstaller==6.* || exit /b 1
python -m pip install --quiet -r requirements.txt || exit /b 1

REM Clean previous build artefacts
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist

python -m PyInstaller "%SCRIPT_DIR%amber-backend.spec" --noconfirm --clean || exit /b 1

if not exist "dist\amber-backend\amber-backend.exe" (
    echo [ERROR] PyInstaller did not produce amber-backend.exe
    exit /b 1
)
echo Backend freeze OK: %ROOT_DIR%\backend\dist\amber-backend\
endlocal
