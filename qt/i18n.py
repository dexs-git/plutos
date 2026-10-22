"""Mehrsprachigkeit (Deutsch / Englisch) für Plutos.

Alle Oberflächentexte im Code stehen auf Deutsch und werden über tr()
geleitet. Ist die Sprache „en“ gewählt, wird der Text aus EN nachgeschlagen;
fehlt eine Übersetzung, bleibt der deutsche Text stehen (nie ein Fehler).
Die Sprache wird in der Datenbank (Einstellung „language“) gespeichert und
beim Start einmalig gesetzt; ein Wechsel wirkt nach dem Neustart.
Auch per Umgebungsvariable PLUTOS_LANG=en|de überschreibbar.
"""
import os

LANGUAGES = {"de": "Deutsch", "en": "English"}
_current = "de"


def set_language(code):
    global _current
    code = (os.environ.get("PLUTOS_LANG") or code or "de").lower()[:2]
    _current = code if code in LANGUAGES else "de"
    return _current


def get_language():
    return _current


_MONTHS = {
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
}
_MONTHS_SHORT = {
    "de": ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}


_WEEKDAYS = {
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}
_WEEKDAYS_SHORT = {
    "de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}


def weekdays():
    return _WEEKDAYS[_current]


def weekdays_short():
    return _WEEKDAYS_SHORT[_current]


def months():
    return _MONTHS[_current]


def months_short():
    return _MONTHS_SHORT[_current]


def tr(text):
    if _current == "de":
        return text
    return EN.get(text, text)


EN = {
    '\n    <b><font color="#c8ced6">Klick auf einen Monat</font></b>\n    <font color="#aeb6c0"> – wechselt in die Monatsansicht.</font>\n    ':
        '\n    <b><font color="#c8ced6">Click a month</font></b>\n    <font color="#aeb6c0"> – switches to the month view.</font>\n    ',
    '\n    <b><font color="#d8dee9">Hinweise</font></b><br>\n    <b><font color="#c8ced6">Fett</font></b>\n    <font color="#aeb6c0"> – Buchungen an diesem Tag</font><br>\n    <b><font color="#c8ced6">Einfachklick</font></b>\n    <font color="#aeb6c0"> – Buchungen des Tages anzeigen</font><br>\n    <b><font color="#c8ced6">Doppelklick / Enter</font></b>\n    <font color="#aeb6c0"> – neue Buchung für dieses Datum anlegen</font>\n    ':
        '\n    <b><font color="#d8dee9">Hints</font></b><br>\n    <b><font color="#c8ced6">Bold</font></b>\n    <font color="#aeb6c0"> – bookings on this day</font><br>\n    <b><font color="#c8ced6">Single click</font></b>\n    <font color="#aeb6c0"> – show the day\'s bookings</font><br>\n    <b><font color="#c8ced6">Double click / Enter</font></b>\n    <font color="#aeb6c0"> – create a new booking for this date</font>\n    ',
    '\n    <font color="#aeb6c0">\n        <b><font color="#c8ced6">Klick auf einen Tag</font></b>\n        – Buchungen des Tages rechts anzeigen.<br>\n        Monatsübersicht und Budgets folgen automatisch der angezeigten Woche.\n    </font>\n    ':
        '\n    <font color="#aeb6c0">\n        <b><font color="#c8ced6">Click a day</font></b>\n        – shows the day\'s bookings on the right.<br>\n        Monthly overview and budgets automatically follow the displayed week.\n    </font>\n    ',
    '\n    <font color="#aeb6c0">\n        <b><font color="#c8ced6">Links - </font></b>\n        Einnahmen nach Kategorie&nbsp;&nbsp;·&nbsp;&nbsp;\n        <b><font color="#c8ced6">Rechts - </font></b>\n        Ausgaben nach Kategorie\n        (<font color="#4caf50"><b>Überschuss</b></font> /\n        <font color="#e05245"><b>Fehlbetrag</b></font>).<br>\n        Die Bänder zeigen die anteilige Verteilung des Geldflusses\n        und keine direkte Zuordnung einzelner Buchungen.\n    </font>\n    ':
        '\n    <font color="#aeb6c0">\n        <b><font color="#c8ced6">Left - </font></b>\n        Income by category&nbsp;&nbsp;·&nbsp;&nbsp;\n        <b><font color="#c8ced6">Right - </font></b>\n        Expenses by category\n        (<font color="#4caf50"><b>Surplus</b></font> /\n        <font color="#e05245"><b>Shortfall</b></font>).<br>\n        The bands show the proportional distribution of the money flow,\n        not a direct assignment of individual bookings.\n    </font>\n    ',
    '\n    <font color="#aeb6c0">\n        Die Reihenfolge legt fest, in welcher Priorität die\n        Finanzplanungsempfehlung das\n        <b><font color="#c8ced6">Startkapital / den Sparbetrag</font></b>\n        auf die Ziele verteilt.\n        <b><font color="#c8ced6">Oben</font></b> = zuerst befüllt.<br>\n        Mit <b><font color="#c8ced6">„Nach oben“</font></b> /\n        <b><font color="#c8ced6">„Nach unten“</font></b>\n        frei sortierbar.\n    </font>\n    ':
        '\n    <font color="#aeb6c0">\n        The order determines the priority in which the financial planning\n        recommendation distributes the\n        <b><font color="#c8ced6">starting capital / savings amount</font></b>\n        across the goals.\n        <b><font color="#c8ced6">Top</font></b> = filled first.<br>\n        Reorder freely with <b><font color="#c8ced6">“Move up”</font></b> /\n        <b><font color="#c8ced6">“Move down”</font></b>.\n    </font>\n    ',
    '   Betrag von':
        '   Amount from',
    ' % p.a.':
        ' % p.a.',
    ' Prozentpunkte':
        ' percentage points',
    '% p.a.':
        '% p.a.',
    '<b>Fett</b> = Buchung(en)\n<b>Klick</b> = Tagesbuchungen anzeigen\n<b>Doppelklick / Enter</b> = Neue Buchung':
        "<b>Bold</b> = booking(s)\n<b>Click</b> = show the day's bookings\n<b>Double click / Enter</b> = new booking",
    '<b>Klick auf einen Monat</b> = wechselt in die Monatsansicht.':
        '<b>Click a month</b> = switches to the month view.',
    '<b>Klick auf einen Tag</b> = Buchungen des Tages rechts anzeigen.\nMonatsübersicht und Budgets folgen automatisch der angezeigten Woche.':
        "<b>Click a day</b> = show the day's bookings on the right.\nMonthly overview and budgets automatically follow the displayed week.",
    '<b>Links</b> = Einnahmen nach Kategorie. <b>Rechts</b> = Ausgaben nach Kategorie sowie <span foreground="#4caf50"><b>Überschuss</b></span> / <span foreground="#e05245"><b>Fehlbetrag</b></span>, falls Einnahmen und Ausgaben nicht übereinstimmen.\nDie Bänder zeigen keine direkte 1:1-Zuordnung einzelner Euro, sondern die anteilige Verteilung über das monatliche Gesamtbudget.':
        '<b>Left</b> = income by category. <b>Right</b> = expenses by category plus <span foreground="#4caf50"><b>surplus</b></span> / <span foreground="#e05245"><b>shortfall</b></span> if income and expenses do not match.\nThe bands do not show a direct 1:1 assignment of individual euros but the proportional distribution across the total monthly budget.',
    '<b>Monat</b>':
        '<b>Month</b>',
    '<b>Szenarien</b> – Rendite ±':
        '<b>Scenarios</b> – return ±',
    '<b>{0}, {1}</b>':
        '<b>{0}, {1}</b>',
    '<b>{0}</b>':
        '<b>{0}</b>',
    '<b>{0}</b>\n<span foreground="{1}">{2}</span>':
        '<b>{0}</b>\n<span foreground="{1}">{2}</span>',
    '<b>{0}</b>\nEinnahmen: {1}\nAusgaben: {2}\nSaldo: {3}{4}':
        '<b>{0}</b>\nIncome: {1}\nExpenses: {2}\nBalance: {3}{4}',
    '<b>{0}{1}</b>\n{2}.{3}.\n<span foreground="{4}">{5}</span>':
        '<b>{0}{1}</b>\n{2}.{3}.\n<span foreground="{4}">{5}</span>',
    '<i>Noch kein Kontostand hinterlegt – oben Stichtag und Betrag eintragen und speichern.</i>':
        '<i>No account balance set yet – enter a reference date and amount above and save.</i>',
    '<small>Diese Aufteilung folgt der gängigen Faustregel „Notgroschen (und ggf. weitere Ziele) vor Investieren“ sowie einer einfachen Horizont-/Risiko-Faustregel für den ETF-Anteil. Beides sind transparente Modellrechnungen – KEINE individuelle Finanzberatung. Sie berücksichtigen weder Schulden noch Steuern noch deine tatsächliche persönliche Risikotragfähigkeit. Alle Werte lassen sich frei anpassen; für eine verbindliche Einschätzung wende dich an eine unabhängige Finanzberatung.</small>':
        '<small>This allocation follows the common rule of thumb “emergency fund (and any other goals) before investing” plus a simple horizon/risk rule of thumb for the ETF share. Both are transparent model calculations – NOT individual financial advice. They take neither debts nor taxes nor your actual personal risk tolerance into account. All values can be adjusted freely; for a binding assessment, consult an independent financial adviser.</small>',
    '<span foreground="#1e8c3d">■</span>':
        '<span foreground="#1e8c3d">■</span>',
    '<span foreground="#777777"><b>KW</b></span>':
        '<span foreground="#777777"><b>CW</b></span>',
    '<span foreground="#777777">{0:02d}</span>':
        '<span foreground="#777777">{0:02d}</span>',
    '<span foreground="#bf3826">■</span>':
        '<span foreground="#bf3826">■</span>',
    'Achtung: Dabei werden auch ALLE Buchungen und wiederkehrenden Vorlagen dieser Kategorie unwiderruflich gelöscht.':
        'Warning: this also permanently deletes ALL bookings and recurring templates of this category.',
    'Aktualisieren':
        'Refresh',
    'Aktuellen Kontostand als Startkapital in der Empfehlung übernehmen':
        'Use current balance as starting capital in the recommendation',
    'Aktueller Kontostand (berechnet): <b>{0}</b>':
        'Current balance (calculated): <b>{0}</b>',
    'Alle Arten':
        'All types',
    'Alle Ausgaben':
        'All expenses',
    'Alle Kategorien':
        'All categories',
    'Als Buchung im Haushaltsbuch verbuchen (Kategorie „Sparbeitrag“)':
        'Record as a booking in the household book (category “Savings contribution”)',
    'Als Vorlage speichern':
        'Save as template',
    'Angespart':
        'Saved',
    'Anlage-Empfehlung (einfache Faustregel)':
        'Investment recommendation (simple rule of thumb)',
    'Anlagehorizont (Jahre):':
        'Investment horizon (years):',
    'Ansicht:':
        'View:',
    'Anteil des Fondsgewinns, der steuerfrei bleibt (§20 InvStG), um die Vorbelastung durch Unternehmenssteuern auszugleichen. 30 % ist der übliche Satz für Aktienfonds-ETFs mit mindestens 51 % Aktienquote. Bei Anleihen-ETFs 0 %, bei Mischfonds meist 15 %, bei Immobilienfonds 60–80 %.':
        'Share of the fund gain that stays tax-free (§20 InvStG) to offset the prior burden of corporate taxes. 30 % is the usual rate for equity ETFs with at least 51 % equity share. 0 % for bond ETFs, usually 15 % for mixed funds, 60–80 % for real-estate funds.',
    'Anteil des Fondsgewinns, der steuerfrei bleibt (§20 InvStG). 30 % ist der übliche Satz für Aktienfonds-ETFs mit mindestens 51 % Aktienquote. Bei Anleihen-ETFs 0 %, bei Mischfonds meist 15 %, bei Immobilienfonds 60–80 %.':
        'Share of the fund gain that stays tax-free (§20 InvStG). 30 % is the usual rate for equity ETFs with at least 51 % equity share. 0 % for bond ETFs, usually 15 % for mixed funds, 60–80 % for real-estate funds.',
    'Anteil des Netto-Einkommens, der für Freizeit, Hobbys oder als spontaner finanzieller Puffer reserviert bleibt, statt komplett auf Notgroschen/Sparziele/ETF verteilt zu werden. Rein informativ – wird nirgends automatisch als Buchung angelegt.':
        'Share of net income kept aside for leisure, hobbies or as a spontaneous financial buffer instead of being fully allocated to emergency fund/savings goals/ETF. Informational only – never booked automatically.',
    'Art':
        'Type',
    'Art:':
        'Type:',
    'Auch bereits vergangene Buchungen dieser Vorlage löschen':
        'Also delete past bookings of this template',
    'Aus Vorlage buchen':
        'Book from template',
    'Aus Vorlage buchen…':
        'Book from template…',
    'Aus wiederkehrenden Ausgaben schätzen':
        'Estimate from recurring expenses',
    'Ausgabe':
        'Expense',
    'Ausgaben':
        'Expenses',
    'Ausgaben nach Kategorie (Kreisdiagramm)':
        'Expenses by category (pie chart)',
    'Ausgaben nach Kategorie –':
        'Expenses by category –',
    'Ausgegeben':
        'Spent',
    'Ausgewogen':
        'Balanced',
    'Auswertungen':
        'Reports',
    'Automatische Sicherung: Beim ersten Start eines Tages legt Plutos eine Kopie der Datenbank in {0} an (die letzten {1} bleiben erhalten).':
        'Automatic backup: on the first start of each day Plutos saves a copy of the database in {0} (the last {1} are kept).',
    'Backup als JSON exportieren':
        'Export backup as JSON',
    'Backup als JSON exportieren…':
        'Export backup as JSON…',
    'Backup aus JSON importieren…':
        'Import backup from JSON…',
    'Backup exportiert nach: {0}':
        'Backup exported to: {0}',
    'Backup importieren':
        'Import backup',
    'Backup importiert von: {0}':
        'Backup imported from: {0}',
    'Basiszins (%, jährlich vom BMF festgelegt):':
        'Base rate (%, set annually by the German Federal Ministry of Finance):',
    'Bearbeiten':
        'Edit',
    'Berechnen & Speichern':
        'Calculate & save',
    'Beschreibung':
        'Description',
    'Beschreibung:':
        'Description:',
    'Betrag':
        'Amount',
    'Betrag (€):':
        'Amount (€):',
    'Betrag von':
        'Amount from',
    'Bitte zuerst in der Liste eine Buchung markieren.':
        'Please select a booking in the list first.',
    'Buchung hinzufügen':
        'Add booking',
    'Buchungen':
        'Bookings',
    'Buchungen als CSV exportieren':
        'Export bookings as CSV',
    'Buchungen als CSV exportieren…':
        'Export bookings as CSV…',
    'Buchungen aus CSV importieren':
        'Import bookings from CSV',
    'Buchungen aus CSV importieren…':
        'Import bookings from CSV…',
    'Buchungsdatum: {0}':
        'Booking date: {0}',
    'Budget':
        'Budget',
    'Budget fast aufgebraucht':
        'Budget almost used up',
    'Budget setzen':
        'Set budget',
    'Budget setzen/ändern':
        'Set/change budget',
    'Budget überschritten':
        'Budget exceeded',
    'Budgets':
        'Budgets',
    'Budgets gelten für den im Buchungen-Tab im Kalender sichtbaren Monat.':
        'Budgets apply to the month visible in the calendar on the Bookings tab.',
    'CSV exportiert nach: {0}':
        'CSV exported to: {0}',
    'CSV importiert von: {0} – {1}.':
        'CSV imported from: {0} – {1}.',
    'CSV konnte nicht gelesen werden:\n{0}':
        'CSV could not be read:\n{0}',
    'CSV-Export aller Buchungen – zum Öffnen/Weiterverarbeiten in Excel oder LibreOffice Calc.':
        'CSV export of all bookings – to open/process in Excel or LibreOffice Calc.',
    'CSV-Export aller Buchungen – zum Öffnen/Weiterverarbeiten in Excel oder Numbers/LibreOffice Calc.':
        'CSV export of all bookings – to open/process in Excel or Numbers/LibreOffice Calc.',
    "CSV-Import: Buchungen aus einer anderen Haushaltsbuch- oder Banking-Software übernehmen. Trennzeichen (';' oder ',') sowie deutsche/englische Zahlen- und Datumsformate werden automatisch erkannt. Erwartet werden Spalten für Datum und Betrag (z. B. 'Datum'/'Date', 'Betrag'/'Amount'); Kategorie, Art und Beschreibung sind optional – unbekannte Kategorien werden automatisch angelegt.":
        "CSV import: take over bookings from another household-budget or banking software. Separators (';' or ',') as well as German/English number and date formats are detected automatically. Columns for date and amount are expected (e.g. 'Datum'/'Date', 'Betrag'/'Amount'); category, type and description are optional – unknown categories are created automatically.",
    'CSV-Import: Buchungen aus einer anderen Haushaltsbuch- oder Banking-Software übernehmen. Trennzeichen sowie deutsche/englische Zahlen- und Datumsformate werden automatisch erkannt.':
        'CSV import: take over bookings from another household-budget or banking software. Separators as well as German/English number and date formats are detected automatically.',
    'Dabei auch als Buchung verbuchen (Kontostand sinkt entsprechend)':
        'Also record as a booking (the balance decreases accordingly)',
    'Damit taucht die Einzahlung als Ausgabe im Kalender, in Budgets und Auswertungen auf – so wie das Geld tatsächlich vom Konto abgeht. Zum rein informativen Vormerken (z. B. externes Depot) kannst du das Häkchen entfernen.':
        'This way the deposit appears as an expense in the calendar, budgets and reports – just as the money actually leaves the account. For purely informational tracking (e.g. an external brokerage account) you can uncheck this.',
    'Datenbank gesichert: {0}':
        'Database backed up: {0}',
    'Datenbank jetzt sichern':
        'Back up database now',
    'Datum':
        'Date',
    'Datum (TT.MM.JJJJ):':
        'Date (DD.MM.YYYY):',
    'Datum:':
        'Date:',
    'Dein tatsächliches Kontoguthaben an einem bestimmten Tag (z. B. heute) – nicht nur die in Plutos erfassten Buchungen. Der aktuelle Kontostand wird daraus als Startguthaben + alle Buchungen ab diesem Stichtag berechnet, du musst also nicht jede einzelne Buchung seit Kontoeröffnung nacherfassen.':
        'Your actual account balance on a given day (e.g. today) – not just the bookings recorded in Plutos. The current balance is calculated from it as starting balance + all bookings since that date, so you do not have to enter every single booking since opening the account.',
    'Deutsche Kapitalertragsteuer (vereinfacht, anpassbar)':
        'German capital gains tax (simplified, adjustable)',
    'Die Reihenfolge hier legt fest, in welcher Priorität die Finanzplanung-Empfehlung Startkapital/Sparbetrag auf die Ziele verteilt (oben = zuerst befüllt). Mit „Nach oben“/„Nach unten“ frei sortierbar.':
        'The order here determines the priority in which the financial-planning recommendation distributes starting capital/savings amount across the goals (top = filled first). Reorder freely with “Move up”/“Move down”.',
    'Die markierte Buchung als Schnellbuchungs-Vorlage merken':
        'Remember the selected booking as a quick-booking template',
    'Die pauschale Abgeltungsteuer auf Kapitalerträge in Deutschland, gesetzlich 25 %.':
        'The flat-rate withholding tax on capital gains in Germany, 25 % by law.',
    'Die pauschale Abgeltungsteuer auf Kapitalerträge in Deutschland, gesetzlich 25 %. In der Regel nicht anzupassen, außer für Was-wäre-wenn-Szenarien.':
        'The flat-rate withholding tax on capital gains in Germany, 25 % by law. Normally not to be changed, except for what-if scenarios.',
    'Diese Aufteilung folgt der gängigen Faustregel „Notgroschen (und ggf. weitere Ziele) vor Investieren“ sowie einer einfachen Horizont-/Risiko-Faustregel für den ETF-Anteil. Beides sind transparente Modellrechnungen – KEINE individuelle Finanzberatung. Sie berücksichtigen weder Schulden noch Steuern noch deine tatsächliche persönliche Risikotragfähigkeit. Alle Werte lassen sich frei anpassen; für eine verbindliche Einschätzung wende dich an eine unabhängige Finanzberatung.':
        'This allocation follows the common rule of thumb “emergency fund (and any other goals) before investing” plus a simple horizon/risk rule of thumb for the ETF share. Both are transparent model calculations – NOT individual financial advice. They take neither debts nor taxes nor your actual personal risk tolerance into account. All values can be adjusted freely; for a binding assessment, consult an independent financial adviser.',
    'Diese Buchung stammt aus einer wiederkehrenden Vorlage. Änderungen betreffen nur diese einzelne Buchung.':
        'This booking comes from a recurring template. Changes only affect this single booking.',
    'Diese Woche':
        'This week',
    'Doppelklick auf eine Zeile öffnet die Buchung zum Bearbeiten.':
        'Double-click a row to open the booking for editing.',
    'ETF-Sparplan':
        'ETF savings plan',
    'Eigenes Emoji eintippen geht auch – z. B. über die Emoji-Tastatur mit Strg+.':
        'You can also type your own emoji – e.g. via the emoji keyboard with Ctrl+.',
    'Eingezahlt':
        'Paid in',
    'Einnahme':
        'Income',
    'Einnahmen':
        'Income',
    'Einnahmen/Ausgaben-Trend':
        'Income/expense trend',
    'Einzahlen':
        'Pay in',
    'Einzahlen: {0}':
        'Pay in: {0}',
    'Einzuzahlender Betrag (€):':
        'Amount to pay in (€):',
    'Empfehlung berechnen':
        'Calculate recommendation',
    'Enddatum (TT.MM.JJJJ, optional):':
        'End date (DD.MM.YYYY, optional):',
    'Enddatum:':
        'End date:',
    'Ende':
        'End',
    'Endwert nach Steuern':
        'Final value after tax',
    'Endwert vor Steuern':
        'Final value before tax',
    'Erhöht die monatliche Sparrate jedes Jahr um diesen Prozentsatz, z. B. um eine erwartete Gehaltssteigerung nachzubilden. 0 % = die Sparrate bleibt über die gesamte Laufzeit konstant.':
        'Increases the monthly savings rate by this percentage every year, e.g. to model an expected salary increase. 0 % = the savings rate stays constant over the whole term.',
    'Erwartete jährl. Rendite (%):':
        'Expected annual return (%):',
    'Export / Import':
        'Export / Import',
    'Fehler':
        'Error',
    'Finanzplanung':
        'Financial planning',
    'Fortschritt':
        'Progress',
    'Freizeit-/Pufferbudget (% vom Netto):':
        'Leisure/buffer budget (% of net):',
    'Geldfluss (Sankey-Diagramm)':
        'Money flow (Sankey diagram)',
    'Geldfluss –':
        'Money flow –',
    'Gesamt':
        'Total',
    'Gesamtausgaben: {0} gegenüber {1} im Vormonat – Veränderung {2}{3}. Rot = mehr ausgegeben, grün = weniger.':
        'Total expenses: {0} versus {1} in the previous month – change {2}{3}. Red = spent more, green = spent less.',
    'Gespeicherter Plan:':
        'Saved plan:',
    'Gewinn':
        'Gain',
    'Girokonto: <b>{0}</b>\nNotgroschen-Unterkonto: <b>{1}</b>\nGesamt: <b>{2}</b>':
        'Checking account: <b>{0}</b>\nEmergency-fund sub-account: <b>{1}</b>\nTotal: <b>{2}</b>',
    'Grobe Faustregel: je kürzer der Horizont bzw. je konservativer das Profil, desto mehr vom Investitionsbetrag als Sicherheitsreserve (Tagesgeld) statt in den ETF-Sparplan. Unter 3 Jahren Horizont wird ganz von Aktien-ETFs abgeraten, da kurzfristige Kursschwankungen zu riskant wären.':
        'Rough rule of thumb: the shorter the horizon or the more conservative the profile, the more of the investment amount goes into a safety reserve (call money) instead of the ETF savings plan. Below a 3-year horizon equity ETFs are advised against entirely, as short-term price swings would be too risky.',
    'Heute':
        'Today',
    'Hinzufügen':
        'Add',
    'Häufigkeit':
        'Frequency',
    'Häufigkeit:':
        'Frequency:',
    'Icon':
        'Icon',
    'Icon auswählen:':
        'Choose icon:',
    'Icon:':
        'Icon:',
    'Import ersetzt alle aktuellen Daten. Fortfahren?':
        'Import replaces all current data. Continue?',
    'Inflation:':
        'Inflation:',
    'Jahr':
        'Year',
    'Jahr {0}':
        'Year {0}',
    'Jahresansicht':
        'Year view',
    'Jahresverlauf':
        'Year trend',
    'Jahresübersicht (mit Vorjahr)':
        'Year overview (with previous year)',
    'Jetzt buchen':
        'Book now',
    'J{0}':
        'Y{0}',
    'Jährlich':
        'Yearly',
    'Jährliche Erhöhung der Sparrate (%):':
        'Annual increase of the savings rate (%):',
    'Jährliche Vorabpauschale simulieren (statt Einmalbesteuerung am Laufzeitende)':
        'Simulate annual advance lump sum (instead of one-time taxation at the end of the term)',
    'KW':
        'CW',
    'Kapitalertragsteuer (%):':
        'Capital gains tax (%):',
    'Kategorie':
        'Category',
    'Kategorie "{0}" wirklich löschen?':
        'Really delete category "{0}"?',
    'Kategorie "{0}" wirklich löschen?\n\nAchtung: Dabei werden auch ALLE Buchungen und wiederkehrenden Vorlagen dieser Kategorie unwiderruflich gelöscht.':
        'Really delete category "{0}"?\n\nWarning: this also permanently deletes ALL bookings and recurring templates of this category.',
    'Kategorie löschen':
        'Delete category',
    'Kategorie:':
        'Category:',
    'Kategorien vergleichen':
        'Compare categories',
    'Kategorien verwalten':
        'Manage categories',
    'Kein Zieldatum':
        'No target date',
    'Keine Ausgaben in diesem Jahr.':
        'No expenses in this year.',
    'Keine Ausgaben in diesem Monat.':
        'No expenses in this month.',
    'Keine Ausgaben in diesen beiden Monaten.':
        'No expenses in these two months.',
    'Keine Ausgaben in diesen beiden Zeiträumen.':
        'No expenses in these two periods.',
    'Keine Buchungen in diesem Monat.':
        'No bookings in this month.',
    'Keine Buchungen in diesen beiden Jahren.':
        'No bookings in these two years.',
    'Keine Daten.':
        'No data.',
    'Konservativ':
        'Conservative',
    'Kontostand':
        'Balance',
    'Kontostand an diesem Tag (€):':
        'Balance on this day (€):',
    'Laufzeit (Jahre):':
        'Term (years):',
    'Läuft eine Vorlage weiter, werden ihre Buchungen automatisch für jeden Monat erzeugt, den du dir im Kalender ansiehst – unbegrenzt, bis du sie hier löschst. Tipp: Doppelklick auf eine Vorlage öffnet sie zum Bearbeiten.':
        'While a template keeps running, its bookings are generated automatically for every month you view in the calendar – indefinitely, until you delete it here. Tip: double-click a template to edit it.',
    'Läuft unbegrenzt weiter':
        'Runs indefinitely',
    'Löschen':
        'Delete',
    'Löschen (inkl. künftiger Buchungen)':
        'Delete (incl. future bookings)',
    'Maximale Sparrate (€, 0 = kein Deckel):':
        'Maximum savings rate (€, 0 = no cap):',
    'Monat gegen Vormonat':
        'Month vs. previous month',
    'Monate':
        'Months',
    'Monate (bezogen auf den gewählten Monat)':
        'Months (relative to the selected month)',
    'Monatlich':
        'Monthly',
    'Monatliche ETF-Rate übernehmen':
        'Use monthly ETF amount',
    'Monatliche Fixkosten (€):':
        'Monthly fixed costs (€):',
    'Monatliche Rate (€):':
        'Monthly amount (€):',
    'Monatsansicht':
        'Month view',
    'Monatsbudget für {0} (€):':
        'Monthly budget for {0} (€):',
    'Nach <b>{0} Jahren</b> bei <b>{1:.2f}% p.a.</b>: eingezahlt <b>{2}</b>, Endwert vor Abschluss-Steuer <b>{3}</b>, Gewinn <b>{4}</b>.\nSteuer bei (angenommenem) Verkauf: <b>{5}</b> → Endwert nach Steuern ca. <b>{6}</b>.{7}':
        'After <b>{0} years</b> at <b>{1:.2f}% p.a.</b>: paid in <b>{2}</b>, final value before closing tax <b>{3}</b>, gain <b>{4}</b>.\nTax on (assumed) sale: <b>{5}</b> → final value after tax approx. <b>{6}</b>.{7}',
    'Nach Kategorie':
        'By category',
    'Nach {0} Jahren bei {1:.2f}% p.a.: eingezahlt {2}, Endwert vor Abschluss-Steuer {3}, Gewinn {4}.\nSteuer bei (angenommenem) Verkauf: {5} → Endwert nach Steuern ca. {6}.{7}':
        'After {0} years at {1:.2f}% p.a.: paid in {2}, final value before closing tax {3}, gain {4}.\nTax on (assumed) sale: {5} → final value after tax approx. {6}.{7}',
    'Name':
        'Name',
    'Name der Vorlage:':
        'Template name:',
    'Name:':
        'Name:',
    'Netto-Einkommen (monatlich, €):':
        'Net income (monthly, €):',
    'Noch kein Kontostand hinterlegt – oben Stichtag und Betrag eintragen und speichern.':
        'No account balance set yet – enter a reference date and amount above and save.',
    'Noch keine gespeicherten Sparpläne zum Vergleichen.':
        'No saved savings plans to compare yet.',
    'Notgroschen als eigenes Unterkonto führen (z. B. Tagesgeld)':
        'Keep the emergency fund as its own sub-account (e.g. call money)',
    'Notgroschen einrichten (3–6 Monate Fixkosten)':
        'Set up emergency fund (3–6 months of fixed costs)',
    'Notgroschen-Ziel anlegen/aktualisieren':
        'Create/update emergency-fund goal',
    'Obergrenze für die Sparrate, falls sie sich durch die jährliche Erhöhung sonst unbegrenzt weiter steigern würde. 0 bedeutet: kein Deckel, die Rate wächst ungebremst weiter.':
        'Upper limit for the savings rate in case the annual increase would otherwise keep raising it indefinitely. 0 means: no cap, the rate keeps growing unchecked.',
    'Offensiv':
        'Aggressive',
    'Plutos – Das Haushaltsbuch':
        'Plutos – The Household Book',
    'Praktisch, wenn du gerade erst anfängst, für etwas zu sparen, einen Notgroschen aufzubauen oder in ETFs zu investieren: so zählt dein tatsächlich vorhandenes Geld, nicht nur das, was du seit Nutzung von Plutos gebucht hast.':
        'Handy when you are just starting to save for something, build an emergency fund or invest in ETFs: this way your actual money counts, not just what you have booked since you started using Plutos.',
    'Priorität / Ziel':
        'Priority / goal',
    'Prozentpunkte   Inflation:':
        'percentage points   Inflation:',
    'Rendite p.a.':
        'Return p.a.',
    'Risikoprofil/Anlagehorizont für den ETF-Anteil berücksichtigen (optional)':
        'Take risk profile/investment horizon into account for the ETF share (optional)',
    'Risikoprofil:':
        'Risk profile:',
    'Rückgängig':
        'Undo',
    'Schließen':
        'Close',
    'Solidaritätszuschlag (%):':
        'Solidarity surcharge (%):',
    'Sparerpauschbetrag (€/Jahr):':
        "Saver's allowance (€/year):",
    'Sparplan':
        'Savings plan',
    'Sparrate':
        'Savings rate',
    'Sparziel hinzufügen':
        'Add savings goal',
    'Sparziele':
        'Savings goals',
    'Speichern':
        'Save',
    'Start':
        'Start',
    'Startdatum (TT.MM.JJJJ):':
        'Start date (DD.MM.YYYY):',
    'Startdatum:':
        'Start date:',
    'Startkapital (€):':
        'Starting capital (€):',
    'Startkapital-Anteile als Fortschritt vormerken':
        'Note starting-capital shares as progress',
    'Steuerfreibetrag auf Kapitalerträge: 1.000 € pro Jahr bei Einzelveranlagung, 2.000 € bei Zusammenveranlagung (Ehepaare, Stand 2023).':
        'Tax-free allowance on capital gains: €1,000 per year for single filers, €2,000 for joint filers (married couples, as of 2023).',
    'Steuerfreibetrag auf Kapitalerträge: 1.000 € pro Jahr bei Einzelveranlagung, 2.000 € bei Zusammenveranlagung (Ehepaare, Stand 2023). Wird hier nur einmalig (ohne Vorabpauschale) bzw. jährlich (mit Vorabpauschale) angesetzt – in der Realität ist er über einen Freistellungsauftrag auf mehrere Banken/Depots aufteilbar.':
        'Tax-free allowance on capital gains: €1,000 per year for single filers, €2,000 for joint filers (married couples, as of 2023). Applied here only once (without advance lump sum) or annually (with advance lump sum) – in reality it can be split across several banks/brokerage accounts via an exemption order.',
    'Stichtag (TT.MM.JJJJ):':
        'Reference date (DD.MM.YYYY):',
    'Stichtag:':
        'Reference date:',
    'Suche':
        'Search',
    'Suchen in Beschreibung und Kategorie …':
        'Search in description and category …',
    'Summe {0} (inkl. geplanter Buchungen): {1} · Ø pro Monat bisher: {2} · teuerster Monat: {3} ({4}). Rote Balken liegen über 120 % des Durchschnitts.':
        'Total {0} (incl. planned bookings): {1} · Avg. per month so far: {2} · most expensive month: {3} ({4}). Red bars are above 120 % of the average.',
    'Szenario':
        'Scenario',
    'TT.MM.JJJJ':
        'DD.MM.YYYY',
    'Teilfreistellung (%):':
        'Partial exemption (%):',
    'Tipp: Doppelklick auf eine Buchung öffnet sie zum Bearbeiten.':
        'Tip: double-click a booking to open it for editing.',
    'Trend – letzte':
        'Trend – last',
    'Verbleibend':
        'Remaining',
    'Vergleich gespeicherter Sparpläne (Wertentwicklung, vor Steuern):':
        'Comparison of saved savings plans (value development, before tax):',
    'Vollständiges Backup (JSON) – enthält alle Buchungen, Vorlagen, Budgets, Sparziele, ETF-Pläne und Kategorien (inkl. Icons). Zum Sichern oder Übertragen auf einen anderen Rechner mit diesem Programm.':
        'Full backup (JSON) – contains all bookings, templates, budgets, savings goals, ETF plans and categories (incl. icons). For saving or transferring to another computer running this program.',
    'Vollständiges Backup (JSON) – enthält alle Buchungen, Vorlagen, Budgets, Sparziele, ETF-Pläne und Kategorien.':
        'Full backup (JSON) – contains all bookings, templates, budgets, savings goals, ETF plans and categories.',
    'Vorbelegt aus deinen laufenden wiederkehrenden Ausgaben-Vorlagen (Miete, Versicherungen, …). Frei anpassbar, falls nicht alle Fixkosten als wiederkehrende Buchung erfasst sind.':
        'Pre-filled from your running recurring-expense templates (rent, insurance, …). Freely adjustable if not all fixed costs are recorded as recurring bookings.',
    'Vorbelegt aus deinen laufenden wiederkehrenden Ausgaben-Vorlagen (Miete, Versicherungen, …). Frei anpassbar, falls nicht alle Fixkosten als wiederkehrende Buchung erfasst sind. Üblich sind 3–6 Monate: eher 3 bei sicherem Einkommen (z. B. Beamte), eher 6 bei unsicherem Einkommen (z. B. Selbstständigkeit).':
        'Pre-filled from your running recurring-expense templates (rent, insurance, …). Freely adjustable if not all fixed costs are recorded as recurring bookings. 3–6 months is typical: rather 3 with secure income (e.g. civil servants), rather 6 with uncertain income (e.g. self-employment).',
    'Vorlage löschen':
        'Delete template',
    'Weitere Sparziele einbeziehen (Priorität siehe Sparziele-Tab)':
        'Include further savings goals (priority: see Savings goals tab)',
    'Wert':
        'Value',
    'Wichtig: Ohne diese Buchung bleibt dein Kontostand oben unverändert, obwohl die Sparziele-Fortschritte steigen – dasselbe Geld würde dir beim nächsten Mal fälschlich erneut als Startkapital angeboten. Häkchen nur entfernen, wenn das eingegebene Startkapital NICHT aus deinem hinterlegten Kontostand stammt (z. B. separates Erbe/Depot, das dort nicht mitgezählt wird).':
        'Important: without this booking your balance above stays unchanged although the savings-goal progress increases – the same money would wrongly be offered again as starting capital next time. Only uncheck if the entered starting capital does NOT come from your stored balance (e.g. a separate inheritance/brokerage account that is not counted there).',
    'Wie viel Wertschwankung (und damit Verlustrisiko) du bereit bist einzugehen, um langfristig höhere Renditechancen zu haben. Konservativ = mehr Sicherheitsreserve, weniger ETF-Anteil; offensiv = mehr ETF-Anteil, mehr Schwankung.':
        'How much price fluctuation (and thus risk of loss) you are willing to accept for better long-term return prospects. Conservative = more safety reserve, smaller ETF share; aggressive = larger ETF share, more fluctuation.',
    'Wie viele Jahre das Geld voraussichtlich investiert bleibt, bevor es gebraucht wird. Kurzer Horizont = höheres Risiko, dass ein Kurseinbruch sich nicht mehr erholt, bevor das Geld gebraucht wird – daher bei kurzem Horizont ein kleinerer ETF-Anteil.':
        'How many years the money is expected to stay invested before it is needed. A short horizon = higher risk that a price slump will not recover before the money is needed – hence a smaller ETF share for a short horizon.',
    'Wie viele Monate an Fixkosten der Notgroschen abdecken soll – eine Reserve für unerwartete Ausgaben oder Einkommensausfälle (z. B. Jobverlust, Reparaturen). 3 Monate gelten als absolutes Minimum, 6 Monate als komfortabel; bei unsicherem Einkommen (Selbstständigkeit) eher mehr.':
        'How many months of fixed costs the emergency fund should cover – a reserve for unexpected expenses or loss of income (e.g. job loss, repairs). 3 months is considered the absolute minimum, 6 months comfortable; with uncertain income (self-employment) rather more.',
    'Wiederk.':
        'Recurr.',
    'Wiederkehrende Buchung':
        'Recurring booking',
    'Wiederkehrende Vorlage bearbeiten':
        'Edit recurring template',
    'Wiederkehrende Vorlage löschen?':
        'Delete recurring template?',
    'Wiederkehrende Vorlagen':
        'Recurring templates',
    'Wiederkehrende Vorlagen verwalten':
        'Manage recurring templates',
    'Wochenansicht':
        'Week view',
    'Wöchentlich':
        'Weekly',
    'Zeigt, wie stark das Ergebnis streuen kann, wenn die Rendite besser oder schlechter ausfällt als angenommen. „Kaufkraftbereinigt“ zieht die Inflation ab und gibt den Endwert nach Steuern in heutiger Kaufkraft an. Das sind Rechenbeispiele, keine Prognose und keine Anlageempfehlung.':
        "Shows how widely the result can scatter if the return turns out better or worse than assumed. “Real terms” deducts inflation and states the final value after tax in today's purchasing power. These are calculation examples, not a forecast and not investment advice.",
    'Zeitraum:':
        'Period:',
    'Ziel hinzufügen':
        'Add goal',
    'Ziel löschen':
        'Delete goal',
    'Ziel: Monate an Fixkosten:':
        'Goal: months of fixed costs:',
    'Zielbetrag':
        'Target amount',
    'Zielbetrag (€):':
        'Target amount (€):',
    'Zielbetrag bei {0} Monaten Fixkosten: <b>{1}</b>\n{2}':
        'Target amount for {0} months of fixed costs: <b>{1}</b>\n{2}',
    'Zielbetrag bei {0} Monaten Fixkosten: {1}\n{2}':
        'Target amount for {0} months of fixed costs: {1}\n{2}',
    'Zieldatum':
        'Target date',
    'Zieldatum (TT.MM.JJJJ, optional):':
        'Target date (DD.MM.YYYY, optional):',
    'Zieldatum:':
        'Target date:',
    'Zinssatz, den das Bundesfinanzministerium jährlich für die Vorabpauschale-Berechnung festlegt (orientiert sich an langfristigen Bundesanleihen). Ändert sich jährlich – der voreingestellte Wert ist nur ein Richtwert, aktuellen Wert bei Bedarf nachschlagen.':
        'Interest rate that the German Federal Ministry of Finance sets annually for the advance-lump-sum calculation (based on long-term federal bonds). Changes every year – the preset value is only a guide, look up the current value if needed.',
    'Zinssatz, den das Bundesfinanzministerium jährlich für die Vorabpauschale-Berechnung festlegt (orientiert sich an langfristigen Bundesanleihen). Ändert sich jährlich – der voreingestellte Wert ist nur ein Richtwert.':
        'Interest rate that the German Federal Ministry of Finance sets annually for the advance-lump-sum calculation (based on long-term federal bonds). Changes every year – the preset value is only a guide.',
    'Zukünftige (heute oder später datierte) Buchungen dieser Vorlage werden dabei immer entfernt.':
        'Future bookings of this template (today or later) are always removed.',
    'Zuletzt gelöschte Buchung wiederherstellen (Strg+Z)':
        'Restore the last deleted booking (Ctrl+Z)',
    'Zuschlag von 5,5 % auf die Kapitalertragsteuer (nicht auf den Gewinn selbst) – gesetzlich vorgegeben, in der Regel nicht anzupassen.':
        'Surcharge of 5.5 % on the capital gains tax (not on the gain itself) – set by law, normally not to be changed.',
    'Zuschlag von 5,5 % auf die Kapitalertragsteuer (nicht auf den Gewinn selbst) – gesetzlich vorgegeben.':
        'Surcharge of 5.5 % on the capital gains tax (not on the gain itself) – set by law.',
    'aktuell ausgewählt':
        'currently selected',
    'auch geplante (zukünftige) Buchungen':
        'also planned (future) bookings',
    'bis':
        'to',
    'egal':
        'any',
    'leer = läuft unbegrenzt weiter':
        'empty = runs indefinitely',
    'nach Steuern, heutige Kaufkraft':
        "after tax, today's purchasing power",
    'z. B. 31.12.2027':
        'e.g. 31.12.2027',
    '{0}\nEinnahmen: {1}\nAusgaben: {2}\nSaldo: {3}{4}':
        '{0}\nIncome: {1}\nExpenses: {2}\nBalance: {3}{4}',
    '{0} gegen {1}':
        '{0} vs. {1}',
    'Änderungen auch auf bereits vergangene Buchungen anwenden (überschreibt deren bisherige Werte rückwirkend)':
        'Also apply changes to past bookings (retroactively overwrites their previous values)',
    'Änderungen wirken standardmäßig nur auf zukünftige Buchungen (ab heute) – bereits vergangene bleiben als historischer Stand unverändert (z. B. sinnvoll bei einer Gehaltserhöhung: alte Monate zeigen weiterhin den alten Betrag).':
        'By default changes only affect future bookings (from today) – past ones remain unchanged as a historical record (useful e.g. for a raise: old months still show the old amount).',
    'Ø {0}':
        'Ø {0}',
    '„{0}“ gebucht ({1}).':
        '“{0}” booked ({1}).',
    '€ (0 = egal)':
        '€ (0 = any)',
    '▲ Nach oben':
        '▲ Move up',
    '▼ Nach unten':
        '▼ Move down',
    '🟩 Einnahmen   🟥 Ausgaben':
        '🟩 Income   🟥 Expenses',
    '\nDas Budget ist um {0} überschritten.':
        '\nThe budget is exceeded by {0}.',
    '\n… und {0} weitere.':
        '\n… and {0} more.',
    '  → ETF-Sparplan: <b>{0}</b>/Monat, <b>{1}</b> Startkapital':
        '  → ETF savings plan: <b>{0}</b>/month, <b>{1}</b> starting capital',
    '  → ETF-Sparplan: {0}/Monat, {1} Startkapital':
        '  → ETF savings plan: {0}/month, {1} starting capital',
    '  → Sicherheitsreserve (z. B. Tagesgeld): <b>{0}</b>/Monat, <b>{1}</b> Startkapital':
        '  → Safety reserve (e.g. call money): <b>{0}</b>/month, <b>{1}</b> starting capital',
    '  → Sicherheitsreserve (z. B. Tagesgeld): {0}/Monat, {1} Startkapital':
        '  → Safety reserve (e.g. call money): {0}/month, {1} starting capital',
    ' Hinweis: Bei laufenden Jahren sind geplante, noch nicht erreichte Monate blass dargestellt und in den Summen enthalten.':
        ' Note: for the current year, planned months not yet reached are shown faded and included in the totals.',
    ' Während der Laufzeit wurden bereits <b>{0}</b> Steuern auf Vorabpauschalen gezahlt (im Endwert schon berücksichtigt); davon <b>{1}</b> Gewinn wurden bei der Steuer am Ende angerechnet.':
        ' During the term, <b>{0}</b> of tax on advance lump sums has already been paid (already included in the final value); of that, <b>{1}</b> of gain was credited against the tax at the end.',
    ' Während der Laufzeit wurden bereits {0} Steuern auf Vorabpauschalen gezahlt (im Endwert schon berücksichtigt); davon {1} Gewinn wurden bei der Steuer am Ende angerechnet.':
        ' During the term, {0} of tax on advance lump sums has already been paid (already included in the final value); of that, {1} of gain was credited against the tax at the end.',
    ' · nur die neuesten 2000 Treffer werden angezeigt – Filter enger setzen':
        ' · only the newest 2000 hits are shown – narrow the filter',
    ', ca. {0} Monate bei diesem Tempo':
        ', approx. {0} months at this pace',
    ', reicht mit aktuellem Tempo noch nicht':
        ', not enough yet at the current pace',
    ', {0} bereits vorhanden (nicht doppelt angelegt)':
        ', {0} already existed (not created twice)',
    ', {0} übersprungen':
        ', {0} skipped',
    'Aktueller Kontostand (berechnet): {0}':
        'Current balance (calculated): {0}',
    'Ausgaben {0}{1}':
        'Expenses {0}{1}',
    'Bestehendes Sparziel „Notgroschen“: {0} von aktuell {1} angespart.':
        'Existing savings goal “Emergency fund”: {0} of currently {1} saved.',
    'Buchung bearbeiten':
        'Edit booking',
    'Budget „{0}“ ({1}/{2}): {3} von {4} ({5:.0f} %).':
        'Budget “{0}” ({1}/{2}): {3} of {4} ({5:.0f} %).',
    'Dieser Monat':
        'This month',
    'Dieses Jahr':
        'This year',
    'Einnahmen {0}{1}':
        'Income {0}{1}',
    'Girokonto: {0}\nNotgroschen-Unterkonto: {1}\nGesamt: {2}':
        'Checking account: {0}\nEmergency-fund sub-account: {1}\nTotal: {2}',
    'Hinweis: Simuliert die jährliche Vorabpauschale (Basisertrag = Wert zu Jahresbeginn × Basiszins × 70 %, gedeckelt auf den tatsächlichen Wertzuwachs). Der Sparerpauschbetrag steht dabei JÄHRLICH neu zur Verfügung. Bereits versteuerte Beträge werden bei der Steuer am Laufzeitende angerechnet (keine Doppelbesteuerung). Kirchensteuer bleibt unberücksichtigt.':
        "Note: simulates the annual advance lump sum (base income = value at start of year × base rate × 70 %, capped at the actual gain in value). The saver's allowance is available anew EVERY year. Amounts already taxed are credited against the tax at the end of the term (no double taxation). Church tax is not taken into account.",
    'Hinweis: Vereinfachte Rechnung ohne jährliche Vorabpauschale – Steuer wird pauschal auf den Gesamtgewinn am Laufzeitende angesetzt, mit dem Sparerpauschbetrag nur EINMALIG am Ende. Kirchensteuer bleibt unberücksichtigt.':
        "Note: simplified calculation without annual advance lump sum – tax is applied as a flat rate on the total gain at the end of the term, with the saver's allowance only ONCE at the end. Church tax is not taken into account.",
    'Hinweis: Vereinfachte Rechnung ohne jährliche Vorabpauschale – Steuer wird pauschal auf den Gesamtgewinn am Laufzeitende angesetzt, mit dem Sparerpauschbetrag nur EINMALIG am Ende. Kirchensteuer bleibt unberücksichtigt. Standardwerte: 30 % Teilfreistellung für Aktienfonds-ETFs, 25 % Kapitalertragsteuer, 5,5 % Soli, 1.000 € Sparerpauschbetrag (Einzelveranlagung).':
        "Note: simplified calculation without annual advance lump sum – tax is applied as a flat rate on the total gain at the end of the term, with the saver's allowance only ONCE at the end. Church tax is not taken into account. Defaults: 30 % partial exemption for equity ETFs, 25 % capital gains tax, 5.5 % solidarity surcharge, €1,000 saver's allowance (single filer).",
    'Kategorie bearbeiten':
        'Edit category',
    'Kategorie hinzufügen':
        'Add category',
    'Keine Buchungen an diesem Tag.':
        'No bookings on this day.',
    'Letzte 3 Monate':
        'Last 3 months',
    'Letztes Jahr':
        'Last year',
    'Lücke bleibt: {0}{1}':
        'Gap remains: {0}{1}',
    'Monatlich verfügbar (Netto abzüglich Fixkosten von {0} und Freizeitbudget von {1}): <b>{2}</b>':
        'Monthly available (net minus fixed costs of {0} and leisure budget of {1}): <b>{2}</b>',
    'Monatlich verfügbar (Netto abzüglich Fixkosten von {0} und Freizeitbudget von {1}): {2}':
        'Monthly available (net minus fixed costs of {0} and leisure budget of {1}): {2}',
    'Noch kein Sparziel „Notgroschen“ angelegt.':
        'No savings goal “Emergency fund” created yet.',
    'Noch keine Vorlagen. Wähle in der Buchungsliste eine Buchung und klicke auf „Als Vorlage speichern“.':
        'No templates yet. Select a booking in the list and click “Save as template”.',
    'Rest zum Investieren (z. B. ETF-Sparplan): <b>{0}</b>/Monat, <b>{1}</b> Startkapital':
        'Remainder to invest (e.g. ETF savings plan): <b>{0}</b>/month, <b>{1}</b> starting capital',
    'Rest zum Investieren (z. B. ETF-Sparplan): {0}/Monat, {1} Startkapital':
        'Remainder to invest (e.g. ETF savings plan): {0}/month, {1} starting capital',
    'Rest zum Investieren – bei {0} Jahren Horizont, Profil „{1}“: empfohlener ETF-Anteil <b>{2}%</b>, Rest als Sicherheitsreserve:':
        'Remainder to invest – with a {0}-year horizon, profile “{1}”: recommended ETF share <b>{2}%</b>, remainder as safety reserve:',
    'Rest zum Investieren – bei {0} Jahren Horizont, Profil „{1}“: empfohlener ETF-Anteil {2}%, Rest als Sicherheitsreserve:':
        'Remainder to invest – with a {0}-year horizon, profile “{1}”: recommended ETF share {2}%, remainder as safety reserve:',
    'läuft weiter':
        'runs on',
    'wird damit voll gedeckt':
        'will be fully covered',
    '{0}\nEinnahmen: {1}\nAusgaben: {2}\nSaldo: {3}':
        '{0}\nIncome: {1}\nExpenses: {2}\nBalance: {3}',
    '{0} ({1} Jahre, {2})':
        '{0} ({1} years, {2})',
    '{0} Buchung(en) importiert':
        '{0} booking(s) imported',
    '{0} Treffer · Einnahmen {1} · Ausgaben {2} · Saldo {3}':
        '{0} hits · Income {1} · Expenses {2} · Balance {3}',
    'Übrig/Gespart':
        'Left over/Saved',
    '— kein Budget —':
        '— no budget —',
    '• <b>{0}</b> (Ziel: {1}, bereits {2} vorhanden): {3} aus Startkapital, {4}/Monat – {5}':
        '• <b>{0}</b> (goal: {1}, {2} already available): {3} from starting capital, {4}/month – {5}',
    '• {0} (Ziel: {1}, bereits {2} vorhanden): {3} aus Startkapital, {4}/Monat – {5}':
        '• {0} (goal: {1}, {2} already available): {3} from starting capital, {4}/month – {5}',
    'Alle':
        'All',
    'Eigener Zeitraum':
        'Custom period',
    'Zeile {0}: Datum oder Betrag nicht lesbar, übersprungen.':
        'Row {0}: date or amount unreadable, skipped.',
    '\nDie 80-%-Marke ist erreicht.':
        '\nThe 80 % mark has been reached.',
    ' (Vorjahr {0:.0f} %)':
        ' (previous year {0:.0f} %)',
    ' (Vorjahr {0}, {1}{2} / {3}{4:.0f} %)':
        ' (previous year {0}, {1}{2} / {3}{4:.0f} %)',
    ' (Vorjahr: –)':
        ' (previous year: –)',
    '+{0} (neu)':
        '+{0} (new)',
    'CSV-Import':
        'CSV import',
    'Fehlbetrag':
        'Shortfall',
    'Gespart {0} (Vorjahr {1})':
        'Saved {0} (previous year {1})',
    'Sparquote {0:.0f} %':
        'Savings rate {0:.0f} %',
    'Startkapital: <b>{0}</b>':
        'Starting capital: <b>{0}</b>',
    'Startkapital: {0}':
        'Starting capital: {0}',
    'Vorlage':
        'Template',
    'bereits voll gedeckt':
        'already fully covered',
    'Alle ansehen':
        'View all',
    'Ausgabentempo':
        'Spending pace',
    'Berechnet bis heute':
        'Calculated up to today',
    'Bis Monatsende geplant: {0} Ausgaben':
        'Planned until month end: {0} in expenses',
    'Budgets im Monat':
        'Budgets this month',
    'Darstellung:':
        'Appearance:',
    'Das Haushaltsbuch':
        'The household book',
    'Die Darstellung wird nach einem Neustart vollständig übernommen.':
        'The appearance is fully applied after a restart.',
    'Dunkel':
        'Dark',
    'Einnahmen {0} · Ausgaben {1}':
        'Income {0} · Expenses {1}',
    'Gesamtvermögen':
        'Total assets',
    'Girokonto {0} · Notgroschen {1}':
        'Checking account {0} · Emergency fund {1}',
    'Hell':
        'Light',
    'In der Finanzplanung einrichten':
        'Set up in Financial planning',
    'Kontostand in der Finanzplanung hinterlegen':
        'Enter your balance under Financial planning',
    'Letzte 6 Monate':
        'Last 6 months',
    'Letzte Buchungen':
        'Recent bookings',
    'Noch keine Buchungen.':
        'No bookings yet.',
    'Noch keine Budgets für diesen Monat.':
        'No budgets for this month yet.',
    'Noch keine Sparziele angelegt.':
        'No savings goals yet.',
    'Noch nicht eingerichtet':
        'Not set up yet',
    'Notgroschen':
        'Emergency fund',
    'Saldo im {0}':
        'Balance in {0}',
    'Sobald Budgets gesetzt sind oder Buchungen aus Vormonaten vorliegen, zeigt Plutos hier, ob du im Rahmen bleibst.':
        'Once budgets are set or earlier months have bookings, Plutos shows here whether you are on track.',
    'Sparziel anlegen':
        'Create savings goal',
    'Tag {0} von {1}: {2} % des Monats sind vorbei, {3} % {4} ausgegeben.':
        'Day {0} of {1}: {2} % of the month is over, {3} % {4} spent.',
    'Wie das System':
        'Same as system',
    'deines Budgets':
        'of your budget',
    'eines üblichen Monats':
        'of a typical month',
    'heute':
        'today',
    'im Rahmen':
        'on track',
    'schneller als der Monat':
        'faster than the month',
    'von {0} · {1} %':
        'of {0} · {1} %',
    '{0} von {1}':
        '{0} of {1}',
    'Übersicht':
        'Overview',
    'über dem Rahmen':
        'over the limit',
    'Tabelle (CSV)':
        'Spreadsheet (CSV)',
    'Sicherung':
        'Backup',
    'Darstellung':
        'Appearance',
    'Budgets gelten für den im Buchungen-Tab im Kalender sichtbaren Monat. Ein Budget läuft ab dem Monat, für den du es setzt, automatisch weiter (↺ = übernommen), bis du es änderst oder beendest.':
        'Budgets apply to the month shown in the calendar on the Bookings tab. A budget runs on automatically from the month you set it (↺ = carried over) until you change or end it.',
    'Budget beenden':
        'End budget',
    'Beendet das Budget der markierten Kategorie ab dem angezeigten Monat; frühere Monate bleiben unverändert.':
        'Ends the budget of the selected category from the month shown; earlier months stay unchanged.',
    'Budgets im Jahr':
        'Budgets over the year',
    'Tags':
        'Tags',
    'Alle Jahre':
        'All years',
    'Tag':
        'Tag',
    'Saldo':
        'Balance',
    'Ausblenden':
        'Dismiss',
    'Bitte zuerst eine Kategorie markieren.':
        'Please select a category first.',
    'Für diese Kategorie gilt in diesem Monat kein Budget.':
        'This category has no budget in this month.',
    '× drüber':
        '× over',
    '× drunter':
        '× under',
    'Summe drüber':
        'Total over',
    'Summe drunter':
        'Total under',
    'Pro Monat ist angegeben, wie viel Euro du über (+) oder unter (−) dem Budget lagst. Gezählt werden nur abgeschlossene Monate mit geltendem Budget; der laufende Monat ist kursiv und zählt noch nicht mit. „Saldo“ positiv = insgesamt mehr ausgegeben als budgetiert.':
        'Each month shows how many euros you were over (+) or under (−) the budget. Only completed months with an active budget are counted; the current month is in italics and does not count yet. A positive “Balance” means you spent more than budgeted overall.',
    'Für dieses Jahr gibt es noch keine Budgets. Lege sie im Tab „Budgets“ an.':
        'There are no budgets for this year yet. Create them on the “Budgets” tab.',
    'alle Jahre':
        'all years',
    'Noch keine Buchungen mit Tags. Beim Anlegen oder Bearbeiten einer Buchung kannst du Tags wie „Urlaub“ eintragen; unabhängig von den Kategorien siehst du hier, was sie insgesamt gekostet haben.':
        'No bookings with tags yet. When adding or editing a booking you can enter tags such as “Holiday”; independent of categories, this shows what they cost in total.',
    'Monatsabschluss {0}':
        'Month in review: {0}',
    'Gespart {0}':
        'Saved {0}',
    'Budgets: {0} von {1} eingehalten':
        'Budgets: {0} of {1} kept',
    'Ausgaben {0}{1:.0f} % gegenüber dem Vormonat':
        'Expenses {0}{1:.0f} % compared with the previous month',
    'Größte Ausgabe: {0} {1} ({2}, {3:.0f} %)':
        'Biggest expense: {0} {1} ({2}, {3:.0f} %)',
    'Budget {0}, ausgegeben {1}':
        'Budget {0}, spent {1}',
    'Monat läuft noch, zählt noch nicht mit':
        'month still running, not counted yet',
    'drüber: {0}':
        'over: {0}',
    'Übernommen aus {0}':
        'Carried over from {0}',
    'z. B. Urlaub, Geschenk (mit Komma trennen)':
        'e.g. Holiday, Gift (separate with commas)',
    'Das Budget gilt ab diesem Monat und läuft danach automatisch weiter, bis du es änderst oder beendest. Frühere Monate bleiben unverändert.':
        'The budget applies from this month and then continues automatically until you change or end it. Earlier months stay unchanged.',
    'Tags:':
        'Tags:',
    'Monatsbudget ab {0} (€):':
        'Monthly budget from {0} (€):',
}
