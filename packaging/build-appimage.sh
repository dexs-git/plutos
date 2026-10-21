#!/usr/bin/env bash
# Baut ein AppImage der Qt-Version (Linux, x86_64).
# Voraussetzung: das PyInstaller-Ergebnis liegt in dist/Plutos/
#   pyinstaller packaging/plutos.spec --noconfirm
# Aufruf (aus dem Repo-Wurzelverzeichnis):  packaging/build-appimage.sh [Version]
set -euo pipefail

VERSION="${1:-dev}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APPDIR="$ROOT/build/Plutos.AppDir"
OUT="$ROOT/dist/Plutos-${VERSION}-x86_64.AppImage"

[ -x "$ROOT/dist/Plutos/Plutos" ] || { echo "dist/Plutos/Plutos fehlt – zuerst pyinstaller ausführen."; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -a "$ROOT/dist/Plutos/." "$APPDIR/usr/bin/"
cp "$ROOT/packaging/icons/plutos.png" "$APPDIR/plutos.png"
cp "$ROOT/packaging/icons/plutos.png" "$APPDIR/.DirIcon"

cat > "$APPDIR/plutos.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Plutos
GenericName=Haushaltsbuch
Comment=Haushaltsbuch mit Sparzielen, Auswertungen und ETF-Sparplan
Exec=Plutos
Icon=plutos
Categories=Office;Finance;
Terminal=false
DESKTOP

cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/Plutos" "$@"
RUN
chmod +x "$APPDIR/AppRun"

TOOL="$ROOT/build/appimagetool"
if [ ! -x "$TOOL" ]; then
    curl -L -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
fi

mkdir -p "$ROOT/dist"
# --appimage-extract-and-run: funktioniert auch ohne FUSE (z. B. in CI-Containern)
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
echo "Fertig: $OUT"
