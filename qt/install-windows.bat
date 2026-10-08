@echo off
setlocal enabledelayedexpansion
REM Installiert Plutos - Das Haushaltsbuch (Qt-Variante) unter Windows als
REM per Doppelklick startbare Anwendung.
REM
REM Ausfuehren: Doppelklick auf install-windows.bat (oder im Terminal
REM             "install-windows.bat")
REM
REM Kopiert die Programmdateien nach %LOCALAPPDATA%\Plutos\app (getrennt
REM vom Datenordner %APPDATA%\Plutos, in dem die Datenbank liegt) und legt
REM eine Verknuepfung auf dem Desktop an.
REM
REM Hiess die App bei dir vorher "HaushaltsBuch": deine Daten werden beim
REM ersten Start automatisch vom alten in den neuen Datenordner umgezogen
REM (siehe db.py) - nichts geht verloren.

set "SCRIPT_DIR=%~dp0"
set "APP_DIR=%LOCALAPPDATA%\Plutos\app"
set "LEGACY_APP_DIR=%LOCALAPPDATA%\HaushaltsBuch\app"
set "LAUNCHER=%USERPROFILE%\Desktop\Plutos.bat"
set "LEGACY_LAUNCHER=%USERPROFILE%\Desktop\HaushaltsBuch.bat"

echo == Plutos installieren (Windows) ==
echo.

echo 1) Pruefe Python ...
set "PYTHON_CMD="
where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3"
    )
)

if "%PYTHON_CMD%"=="" (
    echo    Python wurde nicht gefunden.
    echo    Bitte installiere Python von https://www.python.org/downloads/
    echo    WICHTIG: Beim Installer das Haekchen "Add python.exe to PATH" setzen!
    pause
    exit /b 1
)
echo    Gefunden: %PYTHON_CMD%

echo 2) Installiere PySide6 ...
%PYTHON_CMD% -m pip install --user PySide6
if errorlevel 1 (
    echo    Installation fehlgeschlagen. Pruefe deine Internetverbindung
    echo    oder installiere manuell mit: %PYTHON_CMD% -m pip install PySide6
    pause
    exit /b 1
)
echo    OK.

echo 3) Kopiere Programmdateien nach %APP_DIR% ...
if not exist "%APP_DIR%" mkdir "%APP_DIR%"
for %%F in (main.py db.py charts.py dialogs.py) do (
    if not exist "%SCRIPT_DIR%%%F" (
        echo    FEHLER: %%F fehlt im selben Ordner wie dieses Skript.
        pause
        exit /b 1
    )
    copy /Y "%SCRIPT_DIR%%%F" "%APP_DIR%\%%F" >nul
)
REM Alten Programmordner unter dem frueheren Namen entfernen (enthaelt
REM keine Nutzerdaten, kann also gefahrlos geloescht werden).
if exist "%LEGACY_APP_DIR%" rmdir /S /Q "%LEGACY_APP_DIR%"

echo 4) Pruefe, ob pythonw verfuegbar ist (startet ohne Konsolenfenster) ...
set "RUN_CMD=%PYTHON_CMD%"
where pythonw >nul 2>nul
if not errorlevel 1 (
    set "RUN_CMD=pythonw"
)

echo 5) Erstelle Starter auf dem Desktop ...
(
    echo @echo off
    echo cd /d "%APP_DIR%"
    echo start "" %RUN_CMD% main.py
) > "%LAUNCHER%"
if exist "%LEGACY_LAUNCHER%" del /Q "%LEGACY_LAUNCHER%"

echo.
echo == Fertig ==
echo Auf dem Desktop liegt jetzt "Plutos.bat" - Doppelklick startet das
echo Programm.
echo.
echo Programmdateien liegen unter: %APP_DIR%
echo Nach einem Update (neue Dateien von mir): dieses Skript erneut
echo ausfuehren, ueberschreibt nur die Programmdateien, die Datenbank
echo bleibt unberuehrt.
echo.
pause
