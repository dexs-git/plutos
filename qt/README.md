# Plutos – Das Haushaltsbuch (Qt-Variante)

Portierung der ursprünglichen GTK3/Linux-Mint-Version auf Qt (PySide6) –
läuft nativ unter macOS, Windows und Linux. Gleicher Funktionsumfang wie die
GTK-Version: Buchungen mit Kalenderansicht (Monat/Woche/Jahr), Budgets,
Sparziele mit manueller Priorität, Finanzplanung (Kontostand, Notgroschen,
Anlage-Empfehlung, Risikoprofil), ETF-Sparplan-Rechner (inkl. Vorabpauschale und
Plan-Vergleich), Auswertungen (Kreisdiagramm/Trend/Sankey), Kategorien mit
Icons, CSV-/JSON-Export/-Import.

Alle vier Programmdateien werden gebraucht und müssen im selben Ordner
liegen: `main.py`, `db.py`, `charts.py`, `dialogs.py`.

## Installation

Für jede Plattform liegt ein fertiges Installer-Skript bei (im selben
Ordner wie `main.py` ausführen). Jedes Skript prüft/installiert PySide6,
kopiert die vier Programmdateien an einen festen, plattformtypischen Ort
(getrennt vom Datenordner mit der Datenbank) und legt einen
Doppelklick-Starter an. Nach einem Update (neue Dateien von mir) reicht ein
erneuter Lauf desselben Skripts – überschreibt nur die Programmdateien, die
Datenbank bleibt unberührt.

### macOS

```bash
bash install-macos.sh      # Installieren
bash uninstall-macos.sh    # Deinstallieren
```

Landet unter `~/Applications/Plutos`, Starter als `Plutos.command` auf dem
Schreibtisch.

### Windows

Doppelklick auf `install-windows.bat` (bzw. `uninstall-windows.bat` zum
Deinstallieren).

Landet unter `%LOCALAPPDATA%\Plutos\app`, Starter als `Plutos.bat` auf dem
Desktop.

### Linux

```bash
bash install-linux.sh      # Installieren
bash uninstall-linux.sh    # Deinstallieren
```

Landet unter `~/.local/share/plutos-qt-app`, Eintrag „Plutos (Qt)“ im
Anwendungsmenü. Für die native GTK-Variante (separates Paket) gibt es ein
eigenes `install.sh` – dieses hier ist speziell für die Qt-Variante, falls
du sie zusätzlich oder stattdessen auf Linux nutzen willst.

### Manuell starten (ohne Installer-Skript)

```bash
cd /Pfad/zu/den/vier/Dateien
python3 main.py
```

Praktisch zum Ausprobieren oder Entwickeln; die Installer-Skripte sind für
den dauerhaften Klick-Start gedacht.

## Wo landen die Daten?

`db.py` erkennt automatisch, ob es unter macOS, Windows oder Linux läuft,
und wählt den passenden Ordner – dieselben vier Dateien funktionieren also
unverändert auf allen drei Plattformen:

| Plattform | Datenordner |
|---|---|
| macOS | `~/Library/Application Support/Plutos/` |
| Windows | `%APPDATA%\Plutos\` |
| Linux | `~/.local/share/plutos/` |

**Hieß die App bei dir vorher „HaushaltsBuch“?** Deine Daten ziehen beim
ersten Start automatisch vom alten in den neuen, oben genannten Datenordner
um – du musst nichts selbst tun (Details siehe `db.py`,
`_migrate_legacy_data_dir`).

**Linux-Besonderheit**: Läuft auf demselben Rechner zusätzlich die
GTK-Variante von Plutos, teilen sich beide denselben Datenordner
(`~/.local/share/plutos/`) – unabhängig davon, welche Oberfläche du gerade
startest, siehst du immer dieselben Buchungen.

## Problembehandlung

Allgemein gilt für alle drei Plattformen: **fehlende Programmdatei** (z. B.
`ModuleNotFoundError: No module named 'charts'` o. Ä.) bedeutet, dass nicht
alle vier Dateien (`main.py`, `db.py`, `charts.py`, `dialogs.py`) im
selben Ordner liegen – alle vier zusammen an einen Ort legen und erneut
versuchen.

### macOS

- **`ModuleNotFoundError: No module named 'PySide6'`**: Die Qt-Bibliothek
  fehlt. `install-macos.sh` installiert sie automatisch (inkl. Fallback auf
  eine eigene virtuelle Umgebung, siehe unten); bei manuellem Start ohne
  Installer-Skript hilft `python3 -m pip install --user PySide6`.
- **App startet nach Installation über das Menü/Doppelklick gar nicht,
  ohne Fehlermeldung**: Meist installiert sich PySide6 wegen
  „externally-managed-environment“ (siehe unten) automatisch in eine eigene
  virtuelle Umgebung – `install-macos.sh` erneut ausführen, es aktualisiert
  den Starter dann korrekt auf den richtigen Python-Interpreter.
- **Sicherheitswarnung beim ersten Doppelklick auf `Plutos.command`**:
  normal bei unsignierten Skripten. Rechtsklick → „Öffnen“ → im Dialog
  nochmal „Öffnen“ bestätigen. Nur einmalig nötig.

### Windows

- **`ModuleNotFoundError: No module named 'PySide6'`**: `install-windows.bat`
  installiert die Bibliothek automatisch; bei manuellem Start hilft
  `python -m pip install --user PySide6`.
- **Python wurde beim Ausführen des Skripts nicht gefunden**: Python von
  https://www.python.org/downloads/ installieren – beim Installer unbedingt
  das Häkchen „Add python.exe to PATH“ setzen, sonst findet das
  Installer-Skript Python nicht.
- **Ein Konsolenfenster bleibt im Hintergrund offen**: Das Installer-Skript
  nutzt automatisch `pythonw` statt `python`, falls vorhanden (startet ohne
  sichtbare Konsole) – ist `pythonw` bei dir nicht installiert, bleibt das
  Fenster als Fallback offen, funktional aber unproblematisch.

### Linux

- **`ModuleNotFoundError: No module named 'PySide6'`** bzw. Installation
  schlägt mit `error: externally-managed-environment` fehl: Das ist der
  PEP-668-Schutz neuerer Debian/Ubuntu/Mint-Versionen gegen system-globale
  `pip`-Installationen. `install-linux.sh` fängt das automatisch ab und
  legt bei Bedarf eine eigene virtuelle Umgebung unter
  `~/.local/share/plutos-qt-venv` an – der Menüeintrag wird dann
  automatisch auf deren Python-Interpreter eingerichtet. Bei manuellem
  Start ohne Installer-Skript: entweder
  `python3 -m pip install --user PySide6 --break-system-packages` (nicht
  empfohlen, siehe Warnhinweis von `pip`) oder von Hand eine virtuelle
  Umgebung anlegen:
  ```bash
  python3 -m venv ~/.venvs/plutos
  source ~/.venvs/plutos/bin/activate
  pip install PySide6
  python3 main.py
  ```
- **App startet über das Anwendungsmenü gar nicht, ohne sichtbare
  Fehlermeldung**: Menü-Starts laufen ohne Terminal im Hintergrund – ein
  Python-Fehler (z. B. fehlendes PySide6 im „falschen“ Interpreter) bleibt
  dadurch unsichtbar. Zur Diagnose direkt im Terminal starten:
  `python3 ~/.local/share/plutos-qt-app/main.py` (zeigt die tatsächliche
  Fehlermeldung).
- **`Could not load the Qt platform plugin "xcb"`**: Es fehlt eine
  Systembibliothek (nicht über `pip` installierbar):
  ```bash
  sudo apt install libxcb-cursor0
  ```

## Bekannte Unterschiede zur GTK-Version

- **Datumsfelder**: nutzen jetzt `QDateEdit` mit Kalender-Popup statt
  Text-Eingabe (TT.MM.JJJJ) – robuster, kein eigener Datums-Parser mehr nötig.
- **Datei-Dialoge**: Qt verwendet unter macOS/Windows automatisch den
  jeweils nativen Dialog (kein Nachbau wie bei GTK).
- **Wochen-/Jahresansicht-Kacheln**: aus Zeitgründen bewusst mit einfachem
  Text statt farbiger Hervorhebung des Saldos umgesetzt (Grün/Rot-Färbung
  wie in der GTK-Version wäre mit eigens gezeichneten Widgets machbar, war
  für diese erste Portierung aber nicht der Kern der Anfrage).
- **„?“-Hilfe-Buttons**: zeigen die Erklärung als Tooltip (Hover **und**
  Klick), statt eines Popovers wie in der GTK-Version – funktional gleich.
- **Menüleiste**: bislang keine native macOS-Menüleiste oben am
  Bildschirmrand (Cmd+Q zum Beenden, Anwendungsname im Menü) – aktuell nur
  über das Fenster selbst bedienbar. Wäre ein sinnvoller nächster Schritt.

## Testhinweis

Ich habe diese Version **nicht auf echtem macOS oder Windows** getestet
(keine entsprechende Hardware vorhanden), sondern die komplette
Programmlogik plattformübergreifend unter Linux mit Qt im Offscreen-Modus
sowie – für die Installer-Skripte – mit echtem X11-Display (Xvfb)
durchgetestet: Fensteraufbau, alle sieben Tabs, alle Dialoge, alle vier
Diagramme (inkl. tatsächlichem Zeichnen), den zuvor gemeldeten
ETF-Plan-Löschen-Bug, die Sparziel-Priorisierung, den CSV-Import, die
automatische Datenordner-Migration (für alle drei Plattform-Pfade simuliert)
sowie den venv-Fallback bei blockierter PySide6-Installation. Windows-Skripte
konnte ich mangels `cmd.exe`/Wine in meiner Umgebung nur durch sorgfältiges
manuelles Durchlesen prüfen, nicht ausführen.

Da Qt für sich in Anspruch nimmt, sich auf jeder Plattform gleich zu
verhalten, gibt das gute Zuversicht – *visuelle* Details (wie nativ es sich
anfühlt, Schriftgrößen, Fensterrahmen) kann ich damit aber nicht
verifizieren. Bitte gib Rückmeldung, falls dir dort etwas komisch vorkommt.
