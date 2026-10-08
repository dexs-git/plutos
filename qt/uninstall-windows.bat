@echo off
setlocal enabledelayedexpansion
REM Deinstalliert Plutos - Das Haushaltsbuch (Qt-Variante) unter Windows
REM wieder (Umkehrung von install-windows.bat). Die Datenbank mit deinen
REM Buchungen wird NICHT ohne Rueckfrage geloescht.
REM
REM Ausfuehren: Doppelklick auf uninstall-windows.bat

set "APP_DIR=%LOCALAPPDATA%\Plutos\app"
set "LEGACY_APP_DIR=%LOCALAPPDATA%\HaushaltsBuch\app"
set "DATA_DIR=%APPDATA%\Plutos"
set "LEGACY_DATA_DIR=%APPDATA%\HaushaltsBuch"
set "LAUNCHER=%USERPROFILE%\Desktop\Plutos.bat"
set "LEGACY_LAUNCHER=%USERPROFILE%\Desktop\HaushaltsBuch.bat"

echo == Plutos deinstallieren (Windows) ==
echo.

set "removed_something=0"

if exist "%APP_DIR%" (
    rmdir /S /Q "%APP_DIR%"
    echo Entfernt: %APP_DIR%
    set "removed_something=1"
)
if exist "%LEGACY_APP_DIR%" (
    rmdir /S /Q "%LEGACY_APP_DIR%"
    echo Entfernt: %LEGACY_APP_DIR%
    set "removed_something=1"
)
if exist "%LAUNCHER%" (
    del /Q "%LAUNCHER%"
    echo Desktop-Verknuepfung entfernt: %LAUNCHER%
    set "removed_something=1"
)
if exist "%LEGACY_LAUNCHER%" (
    del /Q "%LEGACY_LAUNCHER%"
    echo Desktop-Verknuepfung entfernt: %LEGACY_LAUNCHER%
    set "removed_something=1"
)

if "%removed_something%"=="0" (
    echo Programmdateien/Verknuepfung nicht gefunden ^(vermutlich bereits entfernt^).
)

echo.

set "vorhandener_datenordner="
if exist "%DATA_DIR%" set "vorhandener_datenordner=%DATA_DIR%"
if "%vorhandener_datenordner%"=="" (
    if exist "%LEGACY_DATA_DIR%" set "vorhandener_datenordner=%LEGACY_DATA_DIR%"
)

if not "%vorhandener_datenordner%"=="" (
    echo Deine Datenbank mit allen Buchungen, Budgets, Sparzielen, ETF-Plaenen
    echo usw. liegt noch unter: !vorhandener_datenordner!
    echo.
    set /p antwort="Auch die Datenbank UNWIDERRUFLICH loeschen? [j/N] "
    set "erste_stelle=!antwort:~0,1!"
    if /I "!erste_stelle!"=="j" (
        rmdir /S /Q "!vorhandener_datenordner!"
        echo Datenbank geloescht: !vorhandener_datenordner!
    ) else (
        echo Datenbank NICHT geloescht. Bei einer erneuten Installation
        echo ^(install-windows.bat^) werden deine bisherigen Daten automatisch
        echo wieder verwendet.
    )
) else (
    echo Keine Datenbank gefunden ^(nichts zu loeschen^).
)

echo.
if "%removed_something%"=="1" (
    echo Plutos wurde deinstalliert.
) else (
    echo Es wurde nichts gefunden, das entfernt werden musste.
)
echo.
pause
