#!/bin/bash
# Installiert Plutos – Das Haushaltsbuch als startbare Anwendung im
# Cinnamon-Anwendungsmenü, sodass es sich per Klick statt über das Terminal
# starten lässt.
#
# Ausführen mit:
#   bash install.sh
#
# Legt die Programmdateien nach ~/.local/share/plutos-app ab (getrennt vom
# Datenordner ~/.local/share/plutos, in dem die Datenbank liegt) und
# erstellt einen Menüeintrag unter ~/.local/share/applications.
#
# Hieß die App bei dir vorher "HaushaltsBuch": deine Daten werden beim
# ersten Start automatisch vom alten in den neuen Datenordner umgezogen
# (siehe db.py, _migrate_legacy_data_dir) - nichts geht verloren. Ein
# eventuell noch vorhandener alter Programmordner
# ~/.local/share/haushaltsbuch-app enthält nur Programmdateien (keine
# Daten) und kann gefahrlos manuell gelöscht werden.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.local/share/plutos-app"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/plutos.desktop"

echo "== Plutos installieren =="

echo "1) Prüfe benötigte Systempakete ..."
if ! python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo "   Fehlend: GTK3-Python-Bindings. Installiere sie mit:"
    echo "     sudo apt install python3-gi gir1.2-gtk-3.0 python3-gi-cairo"
    echo "   und führe dieses Skript danach erneut aus."
    exit 1
fi
echo "   OK."

echo "2) Kopiere Programmdateien nach $APP_DIR ..."
mkdir -p "$APP_DIR"
cp "$SCRIPT_DIR/main.py" "$APP_DIR/main.py"
cp "$SCRIPT_DIR/db.py" "$APP_DIR/db.py"
if [ -f "$SCRIPT_DIR/icon.svg" ]; then
    cp "$SCRIPT_DIR/icon.svg" "$APP_DIR/icon.svg"
fi

echo "3) Erstelle Anwendungsmenü-Eintrag ..."
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Plutos
GenericName=Das Haushaltsbuch
Comment=Plutos – Das Haushaltsbuch: Budget- und Finanzplaner
Exec=python3 "$APP_DIR/main.py"
Icon=$APP_DIR/icon.svg
Terminal=false
Categories=Office;Finance;
StartupNotify=true
DESKTOP
chmod +x "$DESKTOP_FILE"

echo ""
echo "== Fertig =="
echo "Plutos sollte jetzt im Anwendungsmenü (z. B. unter „Büro“ oder über"
echo "die Suche) auftauchen. Falls nicht sofort sichtbar: Menü einmal"
echo "schließen und neu öffnen, notfalls ab- und wieder anmelden."
echo ""
echo "Zum Anheften an die Taskleiste/das Panel: Rechtsklick auf den Eintrag"
echo "im Menü -> „An Favoriten anheften“ o. Ä. (Bezeichnung je nach"
echo "Cinnamon-Version leicht unterschiedlich)."
echo ""
echo "Programmdateien liegen unter: $APP_DIR"
echo "Menüeintrag liegt unter:      $DESKTOP_FILE"
