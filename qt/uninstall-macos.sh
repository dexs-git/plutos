#!/bin/bash
# Deinstalliert Plutos – Das Haushaltsbuch (Qt-Variante) auf macOS wieder
# (Umkehrung von install-macos.sh). Die Datenbank mit deinen Buchungen
# wird NICHT ohne Rückfrage gelöscht.
#
# Ausführen mit:
#   bash uninstall-macos.sh

APP_DIR="$HOME/Applications/Plutos"
VENV_DIR="$HOME/Applications/.plutos-venv"
LEGACY_APP_DIR="$HOME/Applications/HaushaltsBuch"
LAUNCHER="$HOME/Desktop/Plutos.command"
LEGACY_LAUNCHER="$HOME/Desktop/HaushaltsBuch.command"
DATA_DIR="$HOME/Library/Application Support/Plutos"
LEGACY_DATA_DIR="$HOME/Library/Application Support/HaushaltsBuch"

echo "== Plutos deinstallieren (macOS) =="
echo ""

removed_something=false

for dir in "$APP_DIR" "$VENV_DIR" "$LEGACY_APP_DIR"; do
    if [ -d "$dir" ]; then
        rm -rf "$dir"
        echo "Entfernt: $dir"
        removed_something=true
    fi
done

for datei in "$LAUNCHER" "$LEGACY_LAUNCHER"; do
    if [ -f "$datei" ]; then
        rm -f "$datei"
        echo "Schreibtisch-Starter entfernt: $datei"
        removed_something=true
    fi
done

if [ "$removed_something" = false ]; then
    echo "Programmdateien/Starter nicht gefunden (vermutlich bereits entfernt)."
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
    read -r -p "Auch die Datenbank UNWIDERRUFLICH löschen? [j/N] " antwort
    case "$antwort" in
        [jJ]|[jJ][aA])
            rm -rf "$vorhandener_datenordner"
            echo "Datenbank gelöscht: $vorhandener_datenordner"
            ;;
        *)
            echo "Datenbank NICHT gelöscht. Bei einer erneuten Installation"
            echo "(install-macos.sh) werden deine bisherigen Daten automatisch"
            echo "wieder verwendet."
            ;;
    esac
else
    echo "Keine Datenbank gefunden unter: $DATA_DIR (nichts zu löschen)."
fi

echo ""
if [ "$removed_something" = true ]; then
    echo "Plutos wurde deinstalliert."
else
    echo "Es wurde nichts gefunden, das entfernt werden musste."
fi
