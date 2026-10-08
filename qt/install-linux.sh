#!/bin/bash
# Installiert Plutos – Das Haushaltsbuch (Qt-Variante) unter Linux als
# startbare Anwendung im Anwendungsmenü, sodass es sich per Klick statt
# über das Terminal starten lässt. Für die native GTK-Variante (separates
# Paket) gibt es ein eigenes install.sh – dieses Skript ist speziell für
# die Qt/PySide6-Variante.
#
# Ausführen mit:
#   bash install-linux.sh
#
# Legt die Programmdateien nach ~/.local/share/plutos-qt-app ab (getrennt
# vom Datenordner ~/.local/share/plutos, in dem die Datenbank liegt –
# derselbe Datenordner wie bei der GTK-Variante, falls beide auf demselben
# Rechner installiert sind, sodass beide dieselben Buchungen sehen) und
# erstellt einen Menüeintrag unter ~/.local/share/applications.
#
# Hieß die App bei dir vorher "HaushaltsBuch": deine Daten werden beim
# ersten Start automatisch vom alten in den neuen Datenordner umgezogen
# (siehe db.py, _migrate_legacy_data_dir) - nichts geht verloren.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/plutos-qt-app"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/plutos-qt.desktop"

echo "== Plutos (Qt-Variante) installieren =="

PYTHON_BIN="python3"

echo "1) Prüfe/installiere PySide6 ..."
if python3 -c "import PySide6" 2>/dev/null; then
    echo "   Bereits systemweit verfügbar."
else
    echo "   Nicht gefunden. Versuche 'pip install --user' ..."
    if python3 -m pip install --user PySide6 2>/tmp/plutos_pip_error.log; then
        echo "   OK (per pip --user installiert)."
    else
        if grep -q "externally-managed-environment" /tmp/plutos_pip_error.log 2>/dev/null; then
            echo "   Direkte Installation vom System blockiert (PEP 668,"
            echo "   'externally-managed-environment' – üblich bei neueren"
            echo "   Debian/Ubuntu/Mint-Versionen)."
        else
            echo "   Direkte Installation fehlgeschlagen."
        fi
        VENV_DIR="$HOME/.local/share/plutos-qt-venv"
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
echo ""
echo "   Hinweis: Falls das Programm später mit einer Fehlermeldung wie"
echo "   'Could not load the Qt platform plugin \"xcb\"' nicht startet, fehlt"
echo "   eine Systembibliothek (nicht über pip installierbar). Beheben mit:"
echo "     sudo apt install libxcb-cursor0"

echo "2) Kopiere Programmdateien nach $APP_DIR ..."
mkdir -p "$APP_DIR"
for datei in main.py db.py charts.py dialogs.py; do
    if [ ! -f "$SCRIPT_DIR/$datei" ]; then
        echo "   FEHLER: $datei fehlt im selben Ordner wie dieses Skript."
        exit 1
    fi
    cp "$SCRIPT_DIR/$datei" "$APP_DIR/$datei"
done
if [ -f "$SCRIPT_DIR/icon.svg" ]; then
    cp "$SCRIPT_DIR/icon.svg" "$APP_DIR/icon.svg"
fi

echo "3) Erstelle Anwendungsmenü-Eintrag ..."
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Plutos (Qt)
GenericName=Das Haushaltsbuch
Comment=Plutos – Das Haushaltsbuch: Budget- und Finanzplaner (Qt-Oberfläche)
Exec=$PYTHON_BIN "$APP_DIR/main.py"
Icon=$APP_DIR/icon.svg
Terminal=false
Categories=Office;Finance;
StartupNotify=true
DESKTOP
chmod +x "$DESKTOP_FILE"

echo ""
echo "== Fertig =="
echo "Plutos (Qt) sollte jetzt im Anwendungsmenü auftauchen (Name bewusst"
echo "mit '(Qt)' versehen, falls die GTK-Variante ebenfalls installiert"
echo "ist). Falls nicht sofort sichtbar: Menü einmal schließen und neu"
echo "öffnen, notfalls ab- und wieder anmelden."
echo ""
echo "Programmdateien liegen unter: $APP_DIR"
echo "Menüeintrag liegt unter:      $DESKTOP_FILE"
echo ""
echo "Hinweis: Diese Variante nutzt denselben Datenordner wie die GTK-"
echo "Variante (~/.local/share/plutos/) – falls beide auf diesem Rechner"
echo "installiert sind, greifen sie auf dieselbe Datenbank zu."
