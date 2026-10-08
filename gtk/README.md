# Plutos – Das Haushaltsbuch

Ein kleiner GTK-Finanzplaner für Linux Mint mit:

- **Buchungen** (Einnahmen/Ausgaben) mit drei Kalenderansichten – Monat,
  Woche und Jahr, umschaltbar oben links. Tage/Wochen/Monate mit Buchungen
  sind farblich bzw. fett hervorgehoben. Ein Klick zeigt die Buchungen des
  Tages, ein **Doppelklick auf einen Kalendertag** legt direkt eine neue
  Buchung MIT DIESEM DATUM an; bestehende Buchungen werden per Doppelklick
  in der Liste bearbeitet
- **Wiederkehrende Einträge** (wöchentlich/monatlich/jährlich), die für
  JEDEN Monat, den du dir ansiehst, automatisch nachgeneriert werden –
  unbegrenzt, bis du die Vorlage löschst oder ein Enddatum setzt
- **Budgets** pro Kategorie und Monat mit Fortschrittsbalken
- **Sparziele** mit Zielbetrag, Zieldatum und Einzahlungen – wahlweise nur
  informativ oder als echte Buchung im Haushaltsbuch verbucht
- **Finanzplanung**: echten Kontostand (Startguthaben + Buchungen seitdem)
  hinterlegen, Notgroschen-Ziel automatisch aus den laufenden
  wiederkehrenden Fixkosten berechnen (3–6 Monate, einstellbar) sowie eine
  einfache, transparente Empfehlung, wie Netto-Einkommen und Startkapital auf
  Notgroschen, ETF-Sparplan und Freizeitbudget aufgeteilt werden könnten
- **ETF-Sparplan-Rechner** mit Jahresprojektion, optional steigender
  Sparrate (mit Deckel), vereinfachter deutscher
  Kapitalertragsteuer-Berechnung (Teilfreistellung, Soli, Sparerpauschbetrag)
  wahlweise mit **jährlicher Vorabpauschale-Simulation**, sowie einem
  **Vergleichsdiagramm** aller gespeicherten Sparpläne
- **Auswertungen**: Kreisdiagramm der Ausgaben nach Kategorie sowie ein
  Trend-Balkendiagramm für Einnahmen/Ausgaben über mehrere Monate –
  Textfarben passen sich automatisch an helle/dunkle Themes an
- **Kategorien mit eigenem Icon**, frei verwaltbar (hinzufügen, umbenennen,
  Icon per Klick-Picker oder Texteingabe ändern, löschen)
- **Export**: CSV der Buchungen (für Excel/LibreOffice) und ein vollständiges
  JSON-Backup (für Sicherung/Umzug auf einen anderen Rechner)
- **Import**: CSV-Buchungen aus anderen Programmen (automatische Format-
  Erkennung) sowie JSON-Backup wieder einspielen

Alle Daten liegen lokal in `~/.local/share/plutos/finanzen.db` (SQLite).

Hieß die App bei dir vorher „HaushaltsBuch“: deine Daten werden beim ersten
Start automatisch vom alten in den neuen Datenordner umgezogen – nichts geht
verloren.

## Installation (Linux Mint)

Es wird **keine** externe Python-Bibliothek benötigt – nur die Systempakete für
GTK3 und die Cairo-Anbindung (für die Diagramme):

```bash
sudo apt update
sudo apt install python3-gi gir1.2-gtk-3.0 python3-gi-cairo
```

Programm starten:

```bash
python3 main.py
```

Beim allerersten Start wird automatisch die Datenbank samt Standardkategorien
(inkl. Icons) angelegt. Falls du eine ältere Version dieses Programms schon
benutzt hast, wird die bestehende Datenbank automatisch auf das neue Schema
migriert (Icon-Spalte, ETF-Zusatzfelder) – deine bisherigen Daten bleiben
erhalten.

## Als klickbare Anwendung installieren (kein Terminal mehr nötig)

Damit sich Plutos wie ein normales Programm per Klick aus dem Anwendungsmenü
starten lässt, liegt ein Installationsskript bei.

**Voraussetzung**: `main.py`, `db.py`, `icon.svg` und `install.sh` liegen alle
im selben Ordner (z. B. `~/Downloads/plutos/`).

```bash
cd ~/Downloads/plutos   # Pfad ggf. anpassen
bash install.sh
```

Das Skript

1. prüft, ob die GTK3-Python-Bindings installiert sind,
2. kopiert `main.py`, `db.py` und `icon.svg` nach `~/.local/share/plutos-app/`
   (bewusst getrennt vom Datenordner `~/.local/share/plutos/`, in dem die
   Datenbank liegt),
3. legt unter `~/.local/share/applications/plutos.desktop` einen Menüeintrag
   an.

Danach taucht **Plutos** im Cinnamon-Anwendungsmenü auf (Kategorie „Büro“,
auch über die Menüsuche findbar) und lässt sich von dort per Klick starten –
auch an die Taskleiste anheftbar (Rechtsklick auf den Eintrag im Menü →
„An Favoriten anheften“ o. Ä.).

Falls der Eintrag nicht sofort erscheint: Menü einmal schließen und neu
öffnen, notfalls ab- und wieder anmelden (Cinnamon aktualisiert seinen
Menü-Cache nicht immer sofort).

**Alternative – Verknüpfung direkt auf dem Desktop**: die Datei
`~/.local/share/applications/plutos.desktop` (nach `install.sh`) einfach auf
den Desktop kopieren. Nemo zeigt beim ersten Doppelklick vermutlich eine
Sicherheitswarnung („nicht vertrauenswürdiger Starter“) – über Rechtsklick →
Eigenschaften → Berechtigungen → „Datei als Programm ausführen erlauben“
(oder im Kontextmenü direkt „Starten erlauben“) einmalig bestätigen, danach
funktioniert der Doppelklick normal.

**Nach einem Update** (neue Dateien von mir erhalten): einfach `install.sh`
erneut ausführen – überschreibt nur die Programmdateien, die Datenbank
bleibt unberührt.

**Deinstallieren**: `bash uninstall.sh` ausführen – entfernt Programmdateien
und Menüeintrag; fragt separat nach, ob auch die Datenbank
(`~/.local/share/plutos/`) gelöscht werden soll.

**Hieß die App bei dir vorher „HaushaltsBuch“?** Deine Daten ziehen beim
ersten Start automatisch vom alten Ordner (`~/.local/share/haushaltsbuch/`)
in den neuen (`~/.local/share/plutos/`) um – du musst nichts selbst tun.

## Bedienung

### Buchungen
- Oben links zwischen **Monats-, Wochen- und Jahresansicht** umschalten:
  - *Monat*: klassischer Kalender, Tage mit Buchungen sind **fett** markiert.
    Klick zeigt die Buchungen des Tages rechts an, **Doppelklick** öffnet
    direkt „Buchung hinzufügen“ mit dem angeklickten Datum vorausgefüllt.
  - *Woche*: sieben Tageskarten mit Tagessaldo (grün/rot), Navigation über
    ◀ ▶ und „Diese Woche“. Der Bezugsmonat für Monatsübersicht und Budgets
    folgt automatisch der angezeigten Woche (auch ohne Klick auf einen Tag);
    ein Klick auf einen Tag zeigt zusätzlich dessen Buchungen rechts an.
  - *Jahr*: 12 Monatskacheln mit Monatssaldo. Klick auf einen Monat wechselt
    direkt in die Monatsansicht für diesen Monat.
  - Beim Blättern werden wiederkehrende Buchungen automatisch für den neu
    angezeigten Monat nachgeneriert – du musst also nichts manuell anstoßen.
- **Buchung hinzufügen**: öffnet einen Dialog, der zunächst mit dem heutigen
  Datum vorausgefüllt ist (Art, Kategorie, Betrag, Datum, Beschreibung lassen
  sich frei anpassen). Häkchen bei „Wiederkehrende Buchung“ setzen, um daraus
  eine Vorlage zu machen (wöchentlich/monatlich/jährlich).
- **Bearbeiten**: entweder über den Button oder per **Doppelklick** auf eine
  Buchung in der Liste rechts. Bei aus einer Vorlage erzeugten Buchungen wird
  nur die einzelne, angeklickte Buchung geändert – die Vorlage selbst bleibt
  unangetastet.
- **Wiederkehrende Vorlagen verwalten**: zeigt alle laufenden Vorlagen. Per
  **Doppelklick** (oder Button „Bearbeiten“) lässt sich eine Vorlage direkt
  ändern (Kategorie, Betrag, Beschreibung, Häufigkeit, Start-/Enddatum).
  Standardmäßig wirken sich Änderungen nur auf zukünftige Buchungen aus,
  bereits vergangene bleiben als historischer Stand unverändert (praktisch
  z. B. bei einer Gehaltserhöhung: alte Monate zeigen weiterhin den alten
  Betrag) – über die Checkbox „Änderungen auch auf bereits vergangene
  Buchungen anwenden“ lässt sich das bei Bedarf überschreiben (rückwirkend).
  Über „Löschen“ verschwindet eine Vorlage inkl. aller noch nicht
  vergangenen Buchungen; auch hier lässt sich per Checkbox optional
  festlegen, dass auch bereits vergangene Buchungen mitgelöscht werden
  sollen. Eine Vorlage läuft unbegrenzt weiter, bis du sie löschst.
- **Kategorien verwalten**: Kategorien anlegen, umbenennen, das Icon per
  Klick-Picker (oder frei eingetippt, z. B. über die Emoji-Tastatur mit
  Strg+.) ändern oder löschen (Achtung: Löschen einer Kategorie löscht auch
  alle ihre Buchungen und Vorlagen).

### Budgets
- Gilt jeweils für den im Kalender (Buchungen-Tab) sichtbaren Monat.
- **Budget setzen/ändern**: Kategorie + Betrag wählen. Der Fortschrittsbalken
  zeigt, wie viel vom Budget bereits ausgegeben wurde.

### Sparziele
- **Ziel hinzufügen**: Name, Zielbetrag, optionales Zieldatum. Neue Ziele
  werden ans Ende der Prioritätsliste angehängt.
- **Priorität**: Die Reihenfolge in der Liste (Spalte „Priorität / Ziel“,
  durchnummeriert) legt fest, in welcher Reihenfolge die
  Finanzplanung-Empfehlung Geld auf die Ziele verteilt – oben wird zuerst
  befüllt. Mit **„▲ Nach oben“ / „▼ Nach unten“** frei umsortierbar
  (ausgewähltes Ziel verschieben).
- **Einzahlen**: erhöht den angesparten Betrag des ausgewählten Ziels. Per
  Häkchen („Als Buchung im Haushaltsbuch verbuchen“, standardmäßig an) wird
  die Einzahlung zusätzlich als echte Ausgabe in der automatisch angelegten
  Kategorie „Sparbeitrag“ verbucht – taucht dann im Kalender, in Budgets und
  Auswertungen auf, so wie das Geld tatsächlich vom Konto abgeht. Für rein
  informatives Vormerken (z. B. bei einem externen Depot) Häkchen entfernen.

### Finanzplanung
Viele Eingabefelder haben einen kleinen **„?“-Button** daneben, der beim
Klick kurz erklärt, was die Einstellung bedeutet (z. B. Teilfreistellung,
Sparerpauschbetrag, Risikoprofil).

- **Kontostand**: Stichtag und dein tatsächliches Kontoguthaben an diesem
  Tag eintragen und speichern. Der aktuelle Kontostand wird daraus
  automatisch als Startguthaben + alle seitdem in Plutos erfassten
  Buchungen berechnet und live aktualisiert, sobald sich Buchungen ändern –
  du musst also nicht jede einzelne Buchung seit Kontoeröffnung
  nacherfassen, um einen realistischen Wert zu bekommen. Besonders
  praktisch, wenn du gerade erst anfängst, für etwas zu sparen, einen
  Notgroschen aufzubauen oder in ETFs zu investieren: Über „Aktuellen
  Kontostand als Startkapital in der Empfehlung übernehmen“ landet der Wert
  direkt im Startkapital-Feld der Anlage-Empfehlung weiter unten.
- **Notgroschen einrichten**: Die monatlichen Fixkosten werden automatisch
  aus den laufenden wiederkehrenden Ausgaben-Vorlagen geschätzt (Button
  „Aus wiederkehrenden Ausgaben schätzen“ berechnet neu, falls sich die
  Vorlagen geändert haben) und lassen sich frei überschreiben. Zielmonate
  (üblich 3–6) wählen, dann „Notgroschen-Ziel anlegen/aktualisieren“ –
  erzeugt oder aktualisiert automatisch ein Sparziel „Notgroschen“ im
  Sparziele-Tab (der bereits angesparte Betrag bleibt dabei erhalten).
- **Anlage-Empfehlung**: Netto-Einkommen, Startkapital und gewünschtes
  Freizeit-/Pufferbudget (als % vom Netto) eingeben, dann „Empfehlung
  berechnen“. Nach der Faustregel „Notgroschen vor Investieren“ wird
  Startkapital und monatlich verfügbarer Betrag der Reihe nach auf die Ziele
  verteilt – falls das Häkchen „Weitere Sparziele einbeziehen“ gesetzt ist,
  in der **im Sparziele-Tab manuell festgelegten Prioritätsreihenfolge**
  (der Notgroschen-Zielbetrag wird dabei immer live aus den Feldern oben
  berechnet, unabhängig vom gespeicherten Zielbetrag) –, bis jede Lücke
  gedeckt ist. Was danach übrig bleibt, ist für den ETF-Sparplan vorgesehen.
  - **Optional – Risikoprofil/Anlagehorizont**: Häkchen „Risikoprofil/
    Anlagehorizont berücksichtigen“ aktiviert eine zusätzliche, einfache
    Faustregel für den ETF-Rest: abhängig von Anlagehorizont (Jahre) und
    Risikoprofil (konservativ/ausgewogen/offensiv) wird der Investitionsbetrag
    in einen ETF-Anteil und eine Sicherheitsreserve (z. B. Tagesgeld)
    aufgeteilt – unter 3 Jahren Horizont komplett als Sicherheitsreserve, da
    Aktien-ETFs kurzfristig als zu volatil gelten.
  - Über die Buttons darunter lässt sich die berechnete monatliche
    ETF-Rate direkt ins ETF-Sparplan-Tab übernehmen, bzw. die
    Startkapital-Anteile für alle betroffenen Ziele als Fortschritt
    vormerken. Die Checkbox „dabei auch als Buchung verbuchen“ (standardmäßig
    an) sorgt dafür, dass der Kontostand oben entsprechend sinkt, wenn das
    Startkapital aus deinem hinterlegten Kontostand stammt – sonst würde
    dasselbe Geld beim nächsten Mal fälschlich erneut als verfügbares
    Startkapital angeboten. Nur ausschalten, wenn das eingegebene
    Startkapital nachweislich NICHT aus dem Kontostand stammt (z. B. ein
    separates Erbe/Depot, das dort nicht mitgezählt wird) – dann bleibt es
    rein informativ, ohne neue Buchung.
  - Die Empfehlung zeigt je Ziel auch den bereits vorhandenen Betrag an
    („Ziel: X, bereits Y vorhanden“), damit sichtbar bleibt, dass ein
    bestehender Sparziel-Fortschritt in die Lückenberechnung einfließt.
  - **Wichtig**: Das ist eine transparente Modellrechnung nach verbreiteten
    Faustregeln, **keine individuelle Finanzberatung**. Schulden, Steuern und
    deine tatsächliche persönliche Risikotragfähigkeit werden nicht
    berücksichtigt. Alle Werte sind frei anpassbar; für eine verbindliche
    Einschätzung bitte unabhängige Finanzberatung hinzuziehen.

### ETF-Sparplan
Auch hier erklären kleine **„?“-Buttons** neben den weniger offensichtlichen
Feldern (Erhöhung/Deckel der Sparrate, Basiszins, Teilfreistellung,
Kapitalertragsteuer, Soli, Sparerpauschbetrag) kurz, was gemeint ist.

- Monatliche Rate, erwartete jährliche Rendite (%), Laufzeit sowie optional
  eine **jährliche Erhöhung der Sparrate** (z. B. durch Gehaltssteigerungen)
  mit einem **Deckel** (maximale Sparrate, 0 = kein Deckel) eingeben, dann
  **Berechnen & Speichern**. Die Tabelle zeigt für jedes Jahr die geltende
  Sparrate, die Summe der Einzahlungen, den erwarteten Wert und den Gewinn.
- **Steuer-Einstellungen**: vereinfachte deutsche Kapitalertragsteuer
  (Abgeltungsteuer). Standardwerte: 30 % Teilfreistellung (üblich für
  Aktienfonds-ETFs mit ≥51 % Aktienquote – bei Anleihen-ETFs z. B. auf 0 %
  setzen, bei Mischfonds auf 15 %), 25 % Kapitalertragsteuer, 5,5 %
  Solidaritätszuschlag, 1.000 € Sparerpauschbetrag (Einzelveranlagung,
  Stand 2023 – bei Zusammenveranlagung ggf. auf 2.000 € anpassen).
  - **Häkchen „Jährliche Vorabpauschale simulieren“**: berechnet statt einer
    Einmalbesteuerung am Laufzeitende die jährliche Vorabpauschale nach
    Investmentsteuergesetz (Basisertrag = Wert zu Jahresbeginn × Basiszins ×
    70 %, gedeckelt auf den tatsächlichen Wertzuwachs; der Sparerpauschbetrag
    steht dabei JÄHRLICH neu zur Verfügung). Der **Basiszins** wird jährlich
    vom Bundesministerium der Finanzen veröffentlicht und ändert sich –
    Vorbelegung 2,55 % (Richtwert 2024), frei anpassbar. Bereits versteuerte
    Beträge werden bei der Steuer am Laufzeitende angerechnet, um eine
    Doppelbesteuerung zu vermeiden.
  - Vereinfachungen (in beiden Modi): keine Kirchensteuer. Ohne
    Vorabpauschale wird zusätzlich vereinfachend nachgelagerte Besteuerung
    des Gesamtgewinns angenommen und der Sparerpauschbetrag nur einmalig am
    Ende angesetzt statt jährlich. Das Ergebnis dient zur groben
    Orientierung, nicht als Steuerberatung.
- Die Rendite-Berechnung selbst ist ohnehin eine Modellrechnung mit
  konstanter Rendite – reale Wertentwicklungen schwanken natürlich.
- **Vergleichsdiagramm**: unterhalb der Tabelle zeigt ein Liniendiagramm die
  Wertentwicklung ALLER gespeicherten Sparpläne übereinandergelegt (jeweils
  vor Steuern, mit den beim Speichern gültigen Grundparametern), mit
  Legende und Endwert je Plan. Wird automatisch aktualisiert, wenn ein Plan
  berechnet oder gelöscht wird.
- **Gespeicherten Plan verwalten**: Auswahlliste über der Vergleichsgrafik
  zeigt ALLE gespeicherten Pläne (nicht nur den zuletzt berechneten) – Plan
  auswählen und „Löschen“ entfernt gezielt genau diesen, unabhängig davon,
  in welcher Reihenfolge die Pläne angelegt wurden.

### Auswertungen
- Oben über „Ansicht:“ zwischen drei Diagrammtypen umschalten (nur einer ist
  jeweils sichtbar, nicht mehr alle untereinander):
  - **Kreisdiagramm**: Ausgaben nach Kategorie für einen wählbaren Monat
    (mit ◀ ▶ navigierbar), inkl. Icon, Betrag und Prozentanteil in der Legende.
  - **Trend**: gestapeltes Balkendiagramm für Einnahmen (grün) und Ausgaben
    (rot) über die letzten N Monate (Anzahl einstellbar), bezogen auf den
    gewählten Monat.
  - **Geldfluss (Sankey-Diagramm)**: zeigt für den gewählten Monat, wie sich
    Einnahmen (linke Bänder, nach Kategorie) über ein „Gesamt“-Band auf
    Ausgabenkategorien (rechte Bänder) verteilen. Übersteigen die Einnahmen
    die Ausgaben, erscheint rechts zusätzlich ein grünes Band „Übrig/Gespart“;
    übersteigen die Ausgaben die Einnahmen, erscheint links ein rotes Band
    „Fehlbetrag“, damit beide Seiten immer im Gleichgewicht sind. Die Bänder
    stellen die anteilige Verteilung über das Monatsbudget dar, keine echte
    1:1-Zuordnung einzelner Buchungen.

### Export / Import
- **CSV exportieren**: alle Buchungen als `.csv` (Semikolon-getrennt, deutsches
  Zahlenformat mit Komma) – lässt sich direkt in Excel/LibreOffice öffnen.
- **CSV importieren**: Buchungen aus einer anderen Haushaltsbuch- oder
  Banking-Software übernehmen. Trennzeichen (`;`, `,` oder Tab) sowie
  deutsche/englische Zahlen- (`1.234,56` oder `1,234.56`) und Datumsformate
  (`TT.MM.JJJJ`, `JJJJ-MM-TT`, `TT/MM/JJJJ`) werden automatisch erkannt.
  Erwartet werden Spalten für Datum und Betrag (z. B. „Datum“/„Date“,
  „Betrag“/„Amount“) – Kategorie, Art und Beschreibung sind optional.
  Unbekannte Kategorien werden automatisch angelegt (Art aus einer
  Art-Spalte oder aus dem Vorzeichen des Betrags abgeleitet). Nicht lesbare
  Zeilen werden übersprungen und nach dem Import mit Zeilennummer aufgelistet.
- **Backup als JSON exportieren**: sichert den kompletten Datenbestand
  (Buchungen, Vorlagen, Budgets, Sparziele, ETF-Pläne).
- **Backup importieren**: liest eine zuvor exportierte JSON-Datei ein und
  **ersetzt dabei alle aktuellen Daten** – vorher wird eine Sicherheitsabfrage
  angezeigt.

## Anpassungen

- **Vorlauf für wiederkehrende Buchungen**: `RECURRING_LOOKAHEAD_MONTHS` in
  `db.py` (Standard: 3 Monate über den jeweils angezeigten Kalendermonat
  hinaus – wird beim Blättern automatisch nachgezogen).
- **Standardkategorien inkl. Icons**: `_ensure_default_categories()` in
  `db.py` – werden nur beim allerersten Start angelegt, danach frei über
  „Kategorien verwalten“ in der Oberfläche erweiterbar.
- **Icon-Auswahl im Picker**: `ICON_PICKER_CHOICES` in `main.py`.
- **Standard-Steuersätze/Basiszins für den ETF-Rechner**: Startwerte der
  SpinButtons in `_build_etf_tab()` in `main.py` (Teilfreistellung,
  Kapitalertragsteuer, Soli, Sparerpauschbetrag, Basiszins).
- **Farbpalette der Diagramme**: `CATEGORY_COLORS` in `main.py`.
- **Währungssymbol**: `CURRENCY` in `main.py`.
- **CSV-Import-Spaltennamen**: `_CSV_COLUMN_ALIASES` in `db.py`, falls weitere
  Spaltenbezeichnungen (z. B. aus einer bestimmten Bank-Software) erkannt
  werden sollen.
- **Standard-Notgroschen-Monate und Freizeit-Prozentsatz**: Startwerte der
  SpinButtons in `_build_planning_tab()` in `main.py`.

## Hinweise zu einigen Design-Entscheidungen

- **Diagrammtext**: Legenden- und Achsenbeschriftungen in den
  selbstgezeichneten Diagrammen (Kreisdiagramm, Trend, ETF-Vergleich) lesen
  die tatsächliche Vordergrundfarbe des aktuell aktiven GTK-Themes aus
  (`_widget_fg_color()` in `main.py`), damit der Text sowohl bei hellen als
  auch bei dunklen Themes lesbar bleibt, statt eine feste Farbe zu verwenden.
- **Wochenansicht und Budgets/Monatsübersicht**: Bei einer Woche, die zwei
  Monate überspannt, zählt für die automatische Synchronisierung von
  Monatsübersicht und Budgets der Monat des Wochenbeginns (Montag).
- **Notgroschen-Fortschritt durch Startkapital**: Wird der Startkapital-Anteil
  über die Finanzplanung als Notgroschen-Fortschritt vorgemerkt, erzeugt das
  bewusst KEINE Buchung im Kalender – es handelt sich um bereits vorhandenes
  Kapital, das nur zweckgebunden (nicht neu verdient oder ausgegeben) wird.
  Bei laufenden Einzahlungen über den Sparziele-Tab ist die Buchungs-Kopplung
  dagegen sinnvoll und standardmäßig aktiv, da dort tatsächlich Geld vom
  laufenden Konto absepariert wird.

## Code-Qualität

Der Code wurde durchgesehen auf toten Code, Effizienz und Struktur:

- Zwei nicht mehr genutzte Methoden entfernt (`set_recurring_end_date`,
  die alte Einzelziel-Version von `recommend_allocation`), ein ungenutzter
  Import (`GLib`) entfernt (per `pyflakes` verifiziert).
- `budget_overview()` effizienter gemacht: Datumsfilter sitzt jetzt in der
  `JOIN`-Bedingung statt im `SUM/CASE`, wodurch pro Kategorie nur die
  Buchungen des gewünschten Monats statt aller Buchungen aller Zeiten
  herangezogen werden.
- Wiederholte Boilerplate gebündelt: eine `FormDialog`-Basisklasse für die
  fünf Abbrechen/OK-Eingabedialoge, `_nav_button()` für die vier ◀/▶-
  Navigations-Buttons, `_run_message_dialog()` für die vier Fehler-/Info-/
  Bestätigungsdialoge, `_month_pattern()` für das wiederholte SQL-LIKE-Muster.
- Abschnittskommentare (Tab-Nummerierung) korrigiert und beide
  Modul-Docstrings auf den tatsächlichen Funktionsumfang aktualisiert.
- Nach jeder Änderung mit der bestehenden Testsuite (Datenbank-Logik + GUI
  unter Xvfb) gegengeprüft – keine funktionalen Änderungen.

## Umgesetzte Erweiterungen

Alle bisher hier vorgeschlagenen Erweiterungen sind umgesetzt:

- ✅ Jährliche Vorabpauschale im ETF-Rechner (optional zuschaltbar, mit
  einstellbarem Basiszins)
- ✅ Vergleichsdiagramm mehrerer gespeicherter ETF-Sparpläne
- ✅ Kopplung von Sparzielen an echte Buchungen (optional per Häkchen)
- ✅ Icon-Klick-Picker in der Kategorienverwaltung
- ✅ Wochen- und Jahresansicht zusätzlich zur Monatsansicht im Kalender
- ✅ Wochenansicht synchronisiert Monatsübersicht/Budgets automatisch, auch
  ohne expliziten Tagesklick
- ✅ CSV-Import für Buchungen aus anderen Programmen
- ✅ Notgroschen-Sparziel automatisch aus Fixkosten berechnen
- ✅ Anlage-Empfehlung (Notgroschen/ETF-Sparplan/Freizeitbudget) auf Basis von
  Netto-Einkommen und Startkapital
- ✅ Empfehlungslogik auf beliebig viele Sparziele erweitert, mit **manuell
  im Sparziele-Tab einstellbarer Priorität** (▲/▼) statt ausschließlich
  automatischer Sortierung nach Zieldatum
- ✅ Optionales Risikoprofil/Anlagehorizont als zusätzlicher Faktor für den
  ETF-Anteil der Empfehlung
- ✅ Sankey-Diagramm (Geldfluss Einnahmen → Ausgaben/Überschuss) als weitere
  Auswertung
- ✅ Auswertungen-Tab auf Umschalt-Ansicht umgestellt (Kreisdiagramm/Trend/
  Sankey einzeln statt alle untereinander)
- ✅ Wiederkehrende Vorlagen per Doppelklick bearbeitbar (statt nur
  löschen + neu anlegen)
- ✅ Bug behoben: gespeicherte ETF-Pläne lassen sich jetzt einzeln über eine
  Auswahlliste löschen, unabhängig von der Erstellungsreihenfolge (vorher
  war nur der zuletzt berechnete Plan löschbar)
- ✅ Kleine „?“-Hilfe-Buttons neben erklärungsbedürftigen Feldern (ETF-
  Steuereinstellungen, Finanzplanung)

Ideen für weitere Ausbaustufen:

- Eigene Bilddateien statt Emoji als Kategorie-Icons
- Deutsch/Englisch umschaltbare Oberfläche (siehe gesonderte Rückmeldung im
  Chat – vollständige Übersetzung der gesamten Oberfläche ist ein separates,
  größeres Vorhaben)
- Mobile Begleit-App mit Sync übers Heim-WLAN (siehe gesonderte Rückmeldung
  im Chat – deutlich größeres, eigenständiges Projekt)
