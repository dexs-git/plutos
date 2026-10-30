# Synchronisation & Inbox

Plutos kann seine Daten über einen gemeinsamen Ordner (z. B. mit Syncthing) auf mehrere Geräte bringen – unter Windows, Linux und macOS gleich – und Buchungen vom Handy einlesen.

Einstellungen: Tab **Export → Synchronisation & Inbox**.

## 1. Sync-Ordner (mehrere Computer)

1. Auf jedem Gerät denselben (per Syncthing geteilten) Ordner als **Sync-Ordner** wählen und einen **Gerätenamen** vergeben.
2. Beim Beenden schreibt Plutos einen Snapshot der Datenbank nach `<Sync-Ordner>/snapshots/plutos-<Gerät>-<id>.db`. Jedes Gerät schreibt nur seine **eigene** Datei – es gibt keine Sync-Konflikte.
3. Beim nächsten Start auf einem anderen Gerät wird ein neuerer Stand zum **Laden** angeboten (oder „Diese Version ignorieren“ / „Später“). Der eigene Stand wird vorher unter `sync-backups/` im Plutos-Datenordner gesichert. Theme und Sprache bleiben gerätelokal.

**Wichtig:** Es gewinnt immer ein *ganzer* Stand (kein Zusammenführen). Bitte nicht auf zwei Geräten gleichzeitig Änderungen machen, ohne dazwischen zu synchronisieren.

Syncthing: in `.stignore` des Ordners `*.plutos-tmp` eintragen (temporäre Schreibdateien).

## 2. Inbox (Buchungen vom Handy)

Plutos liest kleine Dateien aus dem **Inbox-Ordner** (Standard: `<Sync-Ordner>/inbox`, frei wählbar) beim Start (abschaltbar) oder per Knopf „Inbox jetzt einlesen“. Verarbeitete Dateien landen in `verarbeitet/`, fehlerhafte in `fehler/` samt `<Datei>.fehler.txt`. Eine Datei wird ganz oder gar nicht importiert. Dateien jünger als 2 Sekunden werden übersprungen (noch im Übertragen).

### Textformat (`.txt`, `.csv`)

Eine Buchung pro Zeile: `Betrag;Kategorie;Beschreibung;Tags;Datum`

```
12,50;Essen;Bäcker;;
4,20;Essen;Kaffee;unterwegs,arbeit;28.10.2026
```

- Nur Betrag und Kategorie sind Pflicht. Datum leer = Datum der Datei.
- Das Vorzeichen ergibt sich aus der Kategorie (Ausgabe → negativ, Einnahme → positiv).
- Unbekannte Kategorien führen zu einem Fehler (die Datei wandert nach `fehler/`).

### JSON-Format (`.json`)

Ein Objekt oder eine Liste von Objekten. Schlüssel (deutsch oder englisch): `datum`/`date`, `betrag`/`amount`, `kategorie`/`category`, `beschreibung`/`description`/`text`, `tags`, `art`/`kind`, `id`.

```json
{"betrag": 12.5, "kategorie": "Essen", "beschreibung": "Bäcker", "id": "handy-0001"}
```

Mit `id` wird dieselbe Buchung nie doppelt importiert.

## Handy → PC

- **KDE Connect:** In den Einstellungen des Plugins „Dateien empfangen“ den Ordner „Empfangene Dateien speichern in“ auf den Inbox-Ordner stellen. Dann reicht es, auf dem Handy eine Textdatei an den PC zu senden.
- **Android:** Notiz-/Datei-App mit einer Textdatei pro Buchung oder Tasker/Automate, die eine Datei im Format oben erzeugt und per KDE Connect oder Syncthing in den Inbox-Ordner legt.
- **iOS mit Synctrain (Syncthing-Client mit Kurzbefehle-Anbindung):** siehe unten.
- **iOS allgemein:** Mit einem Kurzbefehl (Eingabe „Betrag“ und „Kategorie“ abfragen → Text `Betrag;Kategorie;…` → als Datei in einen Ordner sichern, der mit dem PC synchronisiert wird, z. B. per Syncthing-kompatibler App oder iCloud-/Cloud-Ordner, den du als Inbox wählst).

## iOS: Kurzbefehl + Synctrain

**Buchungs-Kurzbefehl:** Betrag (Text) abfragen → Kategorie aus Liste wählen → Beschreibung abfragen → Text `Betrag;Kategorie;Beschreibung;;` bauen → „Datei sichern“ in den Synctrain-Ordner (Dateiname z. B. `dd.MM.yyyy-HH.mm.ss.txt`, Endung `.txt` ist wichtig). Die Kategorienamen müssen exakt wie in Plutos geschrieben sein. Der Betrag darf mit oder ohne Komma stehen.

**Automation für das Heimnetz:** Kurzbefehle → Automation → WLAN → dein Heimnetz, „Beigetreten“ → „Sofort ausführen“. Aktionen: Synctrain „Ordner erneut scannen“ (Sync-Ordner) und „Eine Weile synchronisieren“ (maximal 15 Sekunden). Unterwegs bleibt die Datei im Ordner liegen und wird beim Betreten des Heimnetzes übertragen.

Eingelesene Dateien verschiebt Plutos nach `inbox/verarbeitet/`; dort kannst du sie bedenkenlos löschen.
