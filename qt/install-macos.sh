#!/bin/bash
# Installiert Plutos – Das Haushaltsbuch (Qt-Variante) auf macOS als per
# Doppelklick startbare Anwendung, sodass kein Terminal mehr nötig ist.
#
# Ausführen mit:
#   bash install-macos.sh
#
# Kopiert die Programmdateien nach ~/Applications/Plutos (getrennt vom
# Datenordner ~/Library/Application Support/Plutos, in dem die Datenbank
# liegt) und legt einen Doppelklick-Starter auf dem Schreibtisch an.
#
# Hieß die App bei dir vorher "HaushaltsBuch": deine Daten werden beim
# ersten Start automatisch vom alten in den neuen Datenordner umgezogen
# (siehe db.py, _migrate_legacy_data_dir) - nichts geht verloren.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/Applications/Plutos"
LEGACY_APP_DIR="$HOME/Applications/HaushaltsBuch"
LAUNCHER="$HOME/Desktop/Plutos.command"
LEGACY_LAUNCHER="$HOME/Desktop/HaushaltsBuch.command"

echo "== Plutos installieren (macOS) =="

echo "1) Prüfe Python 3 ..."
if ! command -v python3 &> /dev/null; then
    echo "   Python 3 wurde nicht gefunden."
    echo "   Installiere es von https://www.python.org/downloads/"
    echo "   oder per Homebrew: brew install python"
    exit 1
fi
echo "   OK ($(python3 --version))"

PYTHON_BIN="python3"

echo "2) Prüfe/installiere PySide6 ..."
if python3 -c "import PySide6" 2>/dev/null; then
    echo "   Bereits verfügbar."
else
    echo "   Nicht gefunden. Versuche 'pip install --user' ..."
    if python3 -m pip install --user PySide6 2>/tmp/plutos_pip_error.log; then
        echo "   OK (per pip --user installiert)."
    else
        if grep -q "externally-managed-environment" /tmp/plutos_pip_error.log 2>/dev/null; then
            echo "   Direkte Installation blockiert (PEP 668,"
            echo "   'externally-managed-environment' – kommt z. B. bei"
            echo "   Homebrew-Python vor)."
        else
            echo "   Direkte Installation fehlgeschlagen."
        fi
        VENV_DIR="$HOME/Applications/.plutos-venv"
        echo "   Richte stattdessen eine eigene virtuelle Umgebung ein: $VENV_DIR"
        python3 -m venv "$VENV_DIR"
        "$VENV_DIR/bin/pip" install --upgrade pip -q
        if ! "$VENV_DIR/bin/pip" install PySide6; then
            echo "   FEHLER: Installation in der virtuellen Umgebung fehlgeschlagen."
            echo "   Prüfe deine Internetverbindung und führe das Skript erneut aus."
            exit 1
        fi
        PYTHON_BIN="$VENV_DIR/bin/python3"
        echo "   OK (in eigener virtueller Umgebung installiert)."
    fi
fi
rm -f /tmp/plutos_pip_error.log

echo "3) Kopiere Programmdateien nach $APP_DIR ..."
mkdir -p "$APP_DIR"
for datei in main.py db.py charts.py dialogs.py; do
    if [ ! -f "$SCRIPT_DIR/$datei" ]; then
        echo "   FEHLER: $datei fehlt im selben Ordner wie dieses Skript."
        exit 1
    fi
    cp "$SCRIPT_DIR/$datei" "$APP_DIR/$datei"
done
# Alten Programmordner unter dem früheren Namen entfernen (enthält keine
# Nutzerdaten, kann also gefahrlos ersetzt werden).
if [ -d "$LEGACY_APP_DIR" ]; then
    rm -rf "$LEGACY_APP_DIR"
fi

echo "4) Erstelle Doppelklick-Starter auf dem Schreibtisch ..."
mkdir -p "$(dirname "$LAUNCHER")"
cat > "$LAUNCHER" << LAUNCHEREOF
#!/bin/bash
cd "$APP_DIR"
"$PYTHON_BIN" main.py
LAUNCHEREOF
chmod +x "$LAUNCHER"
if [ -f "$LEGACY_LAUNCHER" ]; then
    rm -f "$LEGACY_LAUNCHER"
fi

echo ""
echo "== Fertig =="
echo "Auf dem Schreibtisch liegt jetzt 'Plutos.command' – Doppelklick"
echo "startet das Programm."
echo ""
echo "Hinweis: Beim allerersten Start zeigt macOS eventuell eine"
echo "Sicherheitswarnung (nicht signiertes Skript). Dann: Rechtsklick auf"
echo "Plutos.command -> 'Öffnen' -> im Dialog nochmal 'Öffnen' bestätigen."
echo "Das ist nur einmalig nötig, danach funktioniert der normale"
echo "Doppelklick."
echo ""
echo "Programmdateien liegen unter: $APP_DIR"
echo "Nach einem Update (neue Dateien von mir): dieses Skript erneut"
echo "ausführen, überschreibt nur die Programmdateien, die Datenbank bleibt"
echo "unberührt."
