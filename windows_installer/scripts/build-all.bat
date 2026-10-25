@echo off
REM ============================================================================
REM AMBER Windows installer — master build script
REM ============================================================================
REM Run this from a Windows cmd.exe in windows_installer\scripts\
REM Produces: windows_installer\dist\AMBER_Setup_vX.Y.Z.exe
REM ============================================================================
setlocal EnableDelayedExpansion
set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..\..
set INSTALLER_DIR=%SCRIPT_DIR%..

echo.
echo ============================================================
echo   AMBER Windows Build Pipeline
echo ============================================================
echo.

REM --- Sanity check: required tools ---
where python >nul 2>nul || (echo [ERROR] python not in PATH & exit /b 1)
where yarn   >nul 2>nul || (echo [ERROR] yarn not in PATH   & exit /b 1)
where iscc   >nul 2>nul || (echo [WARN] Inno Setup ^(iscc^) not in PATH — installer step will be skipped)

REM --- Sanity check: bundled blobs ---
if not exist "%INSTALLER_DIR%\bin\mongodb-windows-x86_64-*.zip" (
    echo [ERROR] MongoDB ZIP not found in windows_installer\bin\
    echo         Download from mongodb.com and place it there.
    exit /b 1
)
if not exist "%INSTALLER_DIR%\bin\tesseract-ocr-w64-setup-*.exe" (
    echo [ERROR] Tesseract installer EXE not found in windows_installer\bin\
    exit /b 1
)
if not exist "%INSTALLER_DIR%\bin\eng.traineddata" (
    echo [ERROR] eng.traineddata not found in windows_installer\bin\
    exit /b 1
)

call "%SCRIPT_DIR%01-build-frontend.bat" || exit /b 1
call "%SCRIPT_DIR%02-freeze-backend.bat" || exit /b 1
call "%SCRIPT_DIR%03-stage-bundle.bat"   || exit /b 1
call "%SCRIPT_DIR%04-compile-installer.bat"

echo.
echo ============================================================
echo   BUILD COMPLETE
echo   Output: %INSTALLER_DIR%\dist\
echo ============================================================
endlocal
