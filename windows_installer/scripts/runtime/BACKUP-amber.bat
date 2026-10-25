@echo off
REM ============================================================================
REM AMBER — Backup the entire database to a folder (typically a USB drive).
REM Usage:   BACKUP-amber.bat  D:\AMBER-Backups
REM ============================================================================
setlocal
set INSTALL_DIR=%~dp0
set TARGET=%~1
if "%TARGET%"=="" (
    echo Usage: BACKUP-amber.bat ^<destination_folder^>
    echo Example: BACKUP-amber.bat D:\AMBER-Backups
    exit /b 1
)

set STAMP=%date:~10,4%%date:~4,2%%date:~7,2%-%time:~0,2%%time:~3,2%
set STAMP=%STAMP: =0%
set DEST=%TARGET%\amber-backup-%STAMP%

echo Backing up AMBER database to %DEST% ...
mkdir "%DEST%" 2>nul

"%INSTALL_DIR%mongodb\bin\mongodump.exe" --host 127.0.0.1:27017 --db amber_offline --out "%DEST%\mongo" || exit /b 1

REM Also backup uploaded files and WhatsApp data
set DATA_DIR=C:\AMBER-Data
if exist "%DATA_DIR%\mongo" (
    REM Mongo dump is enough — skip raw db files
)
if exist "%INSTALL_DIR%backend\whatsapp_data" (
    echo Copying WhatsApp local data ...
    xcopy /e /q /y "%INSTALL_DIR%backend\whatsapp_data" "%DEST%\whatsapp_data\" >nul
)

echo Backup complete: %DEST%
endlocal
