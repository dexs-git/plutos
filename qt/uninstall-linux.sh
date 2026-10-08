#!/bin/bash
# Deinstalliert Plutos – Das Haushaltsbuch (Qt-Variante) unter Linux wieder
# (Umkehrung von install-linux.sh): entfernt die Programmdateien, eine
# eventuell angelegte virtuelle Umgebung und den Menüeintrag. Die
# Datenbank mit deinen Buchungen wird NICHT ohne Rückfrage gelöscht.
#
# Ausführen mit:
#   bash uninstall-linux.sh

APP_DIR="$HOME/.local/share/plutos-qt-app"
VENV_DIR="$HOME/.local/share/plutos-qt-venv"
LEGACY_APP_DIR="$HOME/.local/share/haushaltsbuch-qt-app"
LEGACY_VENV_DIR="$HOME/.local/share/haushaltsbuch-qt-venv"
DESKTOP_FILE="$HOME/.local/share/applications/plutos-qt.desktop"
LEGACY_DESKTOP_FILE="$HOME/.local/share/applications/haushaltsbuch-qt.desktop"
DATA_DIR="$HOME/.local/share/plutos"
LEGACY_DATA_DIR="$HOME/.local/share/haushaltsbuch"

echo "== Plutos (Qt-Variante) deinstallieren =="
echo ""

removed_something=false

for dir in "$APP_DIR" "$LEGACY_APP_DIR" "$VENV_DIR" "$LEGACY_VENV_DIR"; do
    if [ -d "$dir" ]; then
        rm -rf "$dir"
        echo "Entfernt: $dir"
        removed_something=true
    fi
done

for datei in "$DESKTOP_FILE" "$LEGACY_DESKTOP_FILE"; do
    if [ -f "$datei" ]; then
        rm -f "$datei"
        echo "Menüeintrag entfernt: $datei"
        removed_something=true
    fi
done

if [ "$removed_something" = false ]; then
    echo "Programmdateien/Menüeintrag nicht gefunden (vermutlich bereits entfernt)."
fi

echo ""

vorhandener_datenordner=""
if [ -d "$DATA_DIR" ]; then
    vorhandener_datenordner="$DATA_DIR"
elif [ -d "$LEGACY_DATA_DIR" ]; then
    vorhandener_datenordner="$LEGACY_DATA_DIR"
fi

if [ -n "$vorhandener_datenordner" ]; then
    echo "Deine Datenbank mit allen Buchungen, Budgets, Sparzielen, ETF-Plänen"
    echo "usw. liegt noch unter: $vorhandener_datenordner"
    echo ""
    echo "ACHTUNG: Falls auf diesem Rechner zusätzlich die GTK-Variante von"
    echo "Plutos installiert ist, nutzt sie DENSELBEN Datenordner – ein"
    echo "Löschen hier würde auch deren Daten entfernen."
    echo ""
    read -r -p "Datenbank UNWIDERRUFLICH löschen? [j/N] " antwort
    case "$antwort" in
        [jJ]|[jJ][aA])
            rm -rf "$vorhandener_datenordner"
            echo "Datenbank gelöscht: $vorhandener_datenordner"
            ;;
        *)
            echo "Datenbank NICHT gelöscht. Bei einer erneuten Installation"
            echo "(install-linux.sh) werden deine bisherigen Daten automatisch"
            echo "wieder verwendet."
            ;;
    esac
else
    echo "Keine Datenbank gefunden (nichts zu löschen)."
fi

echo ""
if [ "$removed_something" = true ]; then
    echo "Plutos (Qt-Variante) wurde deinstalliert."
else
    echo "Es wurde nichts gefunden, das entfernt werden musste."
fi
