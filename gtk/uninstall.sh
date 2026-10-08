#!/bin/bash
# Deinstalliert Plutos – Das Haushaltsbuch wieder (Umkehrung von
# install.sh): entfernt die Programmdateien und den Menüeintrag. Die
# Datenbank mit deinen Buchungen wird NICHT ohne Rückfrage gelöscht.
#
# Ausführen mit:
#   bash uninstall.sh

APP_DIR="$HOME/.local/share/plutos-app"
LEGACY_APP_DIR="$HOME/.local/share/haushaltsbuch-app"
DESKTOP_FILE="$HOME/.local/share/applications/plutos.desktop"
LEGACY_DESKTOP_FILE="$HOME/.local/share/applications/haushaltsbuch.desktop"
DATA_DIR="$HOME/.local/share/plutos"
LEGACY_DATA_DIR="$HOME/.local/share/haushaltsbuch"

echo "== Plutos deinstallieren =="
echo ""

removed_something=false

if [ -d "$APP_DIR" ]; then
    rm -rf "$APP_DIR"
    echo "Programmdateien entfernt: $APP_DIR"
    removed_something=true
else
    echo "Programmdateien nicht gefunden (vermutlich bereits entfernt): $APP_DIR"
fi

# Programmordner unter dem alten Namen "HaushaltsBuch" (falls noch vom
# Umstieg auf "Plutos" übrig) enthält keine Nutzerdaten, kann also
# gefahrlos ohne Rückfrage mit entfernt werden.
if [ -d "$LEGACY_APP_DIR" ]; then
    rm -rf "$LEGACY_APP_DIR"
    echo "Alten Programmordner (Name 'HaushaltsBuch') entfernt: $LEGACY_APP_DIR"
    removed_something=true
fi

if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    echo "Menüeintrag entfernt: $DESKTOP_FILE"
    removed_something=true
else
    echo "Menüeintrag nicht gefunden (vermutlich bereits entfernt): $DESKTOP_FILE"
fi

if [ -f "$LEGACY_DESKTOP_FILE" ]; then
    rm -f "$LEGACY_DESKTOP_FILE"
    echo "Alten Menüeintrag (Name 'HaushaltsBuch') entfernt: $LEGACY_DESKTOP_FILE"
    removed_something=true
fi

# Falls die .desktop-Datei zusätzlich auf den Desktop kopiert wurde
# (siehe README, Abschnitt "Alternative – Verknüpfung direkt auf dem
# Desktop"), auch diese Kopie entfernen. Deutsche und englische
# Ordnerbezeichnung sowie beide App-Namen werden berücksichtigt.
for desktop_dir in "$HOME/Desktop" "$HOME/Schreibtisch"; do
    for dateiname in "plutos.desktop" "haushaltsbuch.desktop"; do
        shortcut="$desktop_dir/$dateiname"
        if [ -f "$shortcut" ]; then
            rm -f "$shortcut"
            echo "Desktop-Verknüpfung entfernt: $shortcut"
            removed_something=true
        fi
    done
done

echo ""

if [ -d "$DATA_DIR" ]; then
    echo "Deine Datenbank mit allen Buchungen, Budgets, Sparzielen, ETF-Plänen"
    echo "usw. liegt noch unter: $DATA_DIR"
    echo ""
    read -r -p "Auch die Datenbank UNWIDERRUFLICH löschen? [j/N] " antwort
    case "$antwort" in
        [jJ]|[jJ][aA])
            rm -rf "$DATA_DIR"
            echo "Datenbank gelöscht: $DATA_DIR"
            ;;
        *)
            echo "Datenbank NICHT gelöscht. Bei einer erneuten Installation"
            echo "(install.sh) werden deine bisherigen Daten automatisch"
            echo "wieder verwendet."
            ;;
    esac
elif [ -d "$LEGACY_DATA_DIR" ]; then
    echo "Deine Datenbank liegt noch unter dem alten Namen: $LEGACY_DATA_DIR"
    echo "(Migration auf den neuen Ordner findet erst beim nächsten Start"
    echo "von Plutos statt.)"
    echo ""
    read -r -p "Auch diese Datenbank UNWIDERRUFLICH löschen? [j/N] " antwort
    case "$antwort" in
        [jJ]|[jJ][aA])
            rm -rf "$LEGACY_DATA_DIR"
            echo "Datenbank gelöscht: $LEGACY_DATA_DIR"
            ;;
        *)
            echo "Datenbank NICHT gelöscht."
            ;;
    esac
else
    echo "Keine Datenbank gefunden (nichts zu löschen)."
fi

echo ""
if [ "$removed_something" = true ]; then
    echo "Plutos wurde deinstalliert."
else
    echo "Es wurde nichts gefunden, das entfernt werden musste – Plutos"
    echo "scheint nicht (mehr) über install.sh installiert zu sein."
fi
