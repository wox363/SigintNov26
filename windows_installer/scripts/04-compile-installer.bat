@echo off
REM Compile Inno Setup script into the final installer EXE.
setlocal
set SCRIPT_DIR=%~dp0
set INSTALLER_DIR=%SCRIPT_DIR%..

echo.
echo --- [4/4] Compiling Inno Setup installer ---

where iscc >nul 2>nul || (
    echo [SKIP] Inno Setup ^(iscc^) not in PATH.
    echo        Install from https://jrsoftware.org/isdl.php, then re-run this step:
    echo        iscc "%INSTALLER_DIR%\amber-installer.iss"
    exit /b 0
)

iscc "%INSTALLER_DIR%\amber-installer.iss" || exit /b 1

echo Installer OK: %INSTALLER_DIR%\dist\
endlocal
