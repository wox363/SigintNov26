@echo off
REM ============================================================================
REM AMBER — Restore the database from a previously-created backup folder.
REM Usage:   RESTORE-amber.bat  D:\AMBER-Backups\amber-backup-20260215-1430
REM ============================================================================
setlocal
set INSTALL_DIR=%~dp0
set SRC=%~1
if "%SRC%"=="" (
    echo Usage: RESTORE-amber.bat ^<backup_folder^>
    exit /b 1
)
if not exist "%SRC%\mongo\amber_offline" (
    echo [ERROR] %SRC% does not look like an AMBER backup (no mongo\amber_offline subfolder).
    exit /b 1
)

echo WARNING: This will OVERWRITE the current AMBER database.
set /p CONFIRM="Type YES to continue: "
if /i not "%CONFIRM%"=="YES" (
    echo Aborted.
    exit /b 0
)

echo Restoring database from %SRC% ...
"%INSTALL_DIR%mongodb\bin\mongorestore.exe" --host 127.0.0.1:27017 --drop "%SRC%\mongo" || exit /b 1

if exist "%SRC%\whatsapp_data" (
    echo Restoring WhatsApp local data ...
    xcopy /e /q /y "%SRC%\whatsapp_data" "%INSTALL_DIR%backend\whatsapp_data\" >nul
)

echo Restore complete.
endlocal
