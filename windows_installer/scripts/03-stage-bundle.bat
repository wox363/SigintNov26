@echo off
REM Stage all artefacts into a single folder for Inno Setup to package.
setlocal EnableDelayedExpansion
set SCRIPT_DIR=%~dp0
set ROOT_DIR=%SCRIPT_DIR%..\..
set INSTALLER_DIR=%SCRIPT_DIR%..
set STAGE=%INSTALLER_DIR%\staging\AMBER

echo.
echo --- [3/4] Staging bundle ---

if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%"
mkdir "%STAGE%\backend"
mkdir "%STAGE%\mongodb"
mkdir "%STAGE%\tesseract"
mkdir "%STAGE%\tesseract\tessdata"

REM --- Backend (frozen) ---
echo Copying frozen backend...
xcopy /e /q /y "%ROOT_DIR%\backend\dist\amber-backend\*" "%STAGE%\backend\" >nul

REM --- MongoDB ---
echo Extracting MongoDB...
for %%F in ("%INSTALLER_DIR%\bin\mongodb-windows-x86_64-*.zip") do (
    powershell -NoProfile -Command "Expand-Archive -LiteralPath '%%~fF' -DestinationPath '%STAGE%\mongodb\_tmp' -Force"
)
REM Flatten the single nested folder inside the zip
for /d %%D in ("%STAGE%\mongodb\_tmp\*") do (
    xcopy /e /q /y "%%D\bin\*" "%STAGE%\mongodb\bin\" >nul
)
rmdir /s /q "%STAGE%\mongodb\_tmp"

REM --- Tesseract — extract the installer with 7-Zip if available, else copy the installer EXE ---
echo Bundling Tesseract...
copy /y "%INSTALLER_DIR%\bin\eng.traineddata" "%STAGE%\tesseract\tessdata\" >nul
where 7z >nul 2>nul && (
    for %%F in ("%INSTALLER_DIR%\bin\tesseract-ocr-w64-setup-*.exe") do (
        7z x "%%~fF" -o"%STAGE%\tesseract\_tmp" -y >nul
        if exist "%STAGE%\tesseract\_tmp\tesseract.exe" (
            move /y "%STAGE%\tesseract\_tmp\tesseract.exe" "%STAGE%\tesseract\" >nul
            xcopy /e /q /y "%STAGE%\tesseract\_tmp\*.dll" "%STAGE%\tesseract\" >nul 2>nul
        )
        rmdir /s /q "%STAGE%\tesseract\_tmp"
    )
) || (
    echo [WARN] 7-Zip not installed — copying the Tesseract installer EXE itself.
    echo        The installer will run it silently during AMBER setup.
    copy /y "%INSTALLER_DIR%\bin\tesseract-ocr-w64-setup-*.exe" "%STAGE%\tesseract\tesseract-setup.exe" >nul
)

REM --- Runtime scripts ---
echo Copying runtime scripts...
copy /y "%SCRIPT_DIR%runtime\*.bat" "%STAGE%\" >nul
copy /y "%SCRIPT_DIR%runtime\README.txt" "%STAGE%\" >nul

echo Staging OK: %STAGE%
endlocal
