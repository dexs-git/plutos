"""
Datenbankschicht für Plutos – Das Haushaltsbuch (Qt/PySide6-Variante).

Alle Zugriffe auf SQLite laufen über die Klasse FinanceStore. Sie deckt
Buchungen (inkl. wiederkehrender Vorlagen), Budgets, Sparziele, ETF-Sparpläne
(inkl. Steuer-/Vorabpauschale-Berechnung), die Finanzplanungs-Faustregeln
(Notgroschen, Mehrfachziele-Empfehlung, Risikoprofil) sowie Auswertungen und
CSV-/JSON-Export/-Import ab. main.py enthält ausschließlich die Qt-Oberfläche
und ruft für jede Datenoperation eine Methode hier auf.

Daten liegen plattformabhängig unter (siehe _default_data_dir() unten):
    macOS:   ~/Library/Application Support/Plutos/finanzen.db
    Windows: %APPDATA%\\Plutos\\finanzen.db
    Linux:   ~/.local/share/plutos/finanzen.db

Die App hieß früher "HaushaltsBuch" und speicherte entsprechend benannte
Ordner. Damit niemand beim Update auf den Namen "Plutos" seine bisherigen
Buchungen verliert, wird ein noch vorhandener alter Ordner beim ersten
Start automatisch in den neuen Ordner umgezogen (siehe
_migrate_legacy_data_dir unten) – nur falls der neue Ordner noch nicht
existiert, also nur einmalig.
"""

import sqlite3
import json
import csv
import datetime
import math
import sys
from pathlib import Path


def _default_data_dir() -> Path:
    """Plattformtypischer Speicherort für Anwendungsdaten. macOS nutzt den
    dort üblichen Ort unter ~/Library/Application Support/, Windows
    %APPDATA%, Linux die XDG-Konvention (~/.local/share/...)."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Plutos"
    if sys.platform.startswith("win"):
        import os
        base = os.environ.get("APPDATA", str(Path.home()))
        return Path(base) / "Plutos"
    return Path.home() / ".local" / "share" / "plutos"


def _legacy_data_dir() -> Path:
    """Datenordner unter dem alten App-Namen "HaushaltsBuch", von dem bei
    Bedarf automatisch migriert wird."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "HaushaltsBuch"
    if sys.platform.startswith("win"):
        import os
        base = os.environ.get("APPDATA", str(Path.home()))
        return Path(base) / "HaushaltsBuch"
    return Path.home() / ".local" / "share" / "haushaltsbuch"


def _migrate_legacy_data_dir():
    """Verschiebt automatisch Daten aus dem alten "HaushaltsBuch"-Ordner
    (frühere Namensgebung der App) in den neuen "Plutos"-Ordner – aber nur,
    wenn der alte Ordner existiert und der neue noch nicht (sonst nichts
    tun, um nichts versehentlich zu überschreiben)."""
    legacy = _legacy_data_dir()
    if DATA_DIR.exists() or not legacy.exists():
        return
    DATA_DIR.parent.mkdir(parents=True, exist_ok=True)
    legacy.rename(DATA_DIR)


DATA_DIR = _default_data_dir()
DB_PATH = DATA_DIR / "finanzen.db"
_migrate_legacy_data_dir()

# Standard-Vorlaufzeit (in Monaten), bis zu der wiederkehrende Buchungen
# mindestens erzeugt werden, wenn kein weiterer Horizont angefordert wird.
RECURRING_LOOKAHEAD_MONTHS = 3

DEFAULT_ICON = "💶"


def add_months(date: datetime.date, months: int) -> datetime.date:
    """Addiert Monate zu einem Datum, ohne externe Bibliothek (dateutil)."""
    month_index = date.month - 1 + months
    year = date.year + month_index // 12
    month = month_index % 12 + 1
    # Tag begrenzen (z. B. 31. Januar + 1 Monat -> letzter Tag im Februar)
    day = min(date.day, _days_in_month(year, month))
    return datetime.date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    return (next_month - datetime.timedelta(days=1)).day


def _month_pattern(month):
    """SQL-LIKE-Pattern für alle Tage eines Monats (Format YYYY-MM -> 'YYYY-MM-%')."""
    return f"{month}-%"


class FinanceStore:
    def __init__(self, db_path: Path = DB_PATH):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()
        self._migrate_schema()
        self._ensure_default_categories()
        # Horizont, bis zu dem wiederkehrende Buchungen mindestens erzeugt wurden.
        self._generated_horizon = None

    # -- Schema ---------------------------------------------------------

    def _create_schema(self):
        c = self.conn
        c.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL CHECK(kind IN ('einnahme','ausgabe')),
            icon TEXT NOT NULL DEFAULT '💶'
        );

        CREATE TABLE IF NOT EXISTS recurring_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            amount REAL NOT NULL,
            description TEXT,
            frequency TEXT NOT NULL CHECK(frequency IN ('woechentlich','monatlich','jaehrlich')),
            start_date TEXT NOT NULL,
            end_date TEXT,                 -- NULL = läuft unbegrenzt weiter
            last_generated_date TEXT       -- letztes erzeugtes Buchungsdatum
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,            -- YYYY-MM-DD
            amount REAL NOT NULL,          -- positiv = Einnahme, negativ = Ausgabe
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            description TEXT,
            recurring_template_id INTEGER REFERENCES recurring_templates(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            month TEXT NOT NULL,           -- YYYY-MM
            limit_amount REAL NOT NULL,
            UNIQUE(category_id, month)
        );

        CREATE TABLE IF NOT EXISTS savings_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            target_date TEXT,
            current_amount REAL NOT NULL DEFAULT 0,
            priority INTEGER
        );

        CREATE TABLE IF NOT EXISTS savings_contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            amount REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS etf_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            monthly_amount REAL NOT NULL,
            annual_return_percent REAL NOT NULL,
            start_date TEXT NOT NULL,
            duration_years INTEGER NOT NULL,
            annual_increase_percent REAL NOT NULL DEFAULT 0,
            max_monthly_amount REAL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        c.commit()

    def _migrate_schema(self):
        """Ergänzt Spalten, falls die DB noch aus einer älteren Version stammt."""
        c = self.conn
        existing_cat_cols = {row["name"] for row in c.execute("PRAGMA table_info(categories)")}
        if "icon" not in existing_cat_cols:
            c.execute(f"ALTER TABLE categories ADD COLUMN icon TEXT NOT NULL DEFAULT '{DEFAULT_ICON}'")

        existing_etf_cols = {row["name"] for row in c.execute("PRAGMA table_info(etf_plans)")}
        if "annual_increase_percent" not in existing_etf_cols:
            c.execute("ALTER TABLE etf_plans ADD COLUMN annual_increase_percent REAL NOT NULL DEFAULT 0")
        if "max_monthly_amount" not in existing_etf_cols:
            c.execute("ALTER TABLE etf_plans ADD COLUMN max_monthly_amount REAL")

        existing_goal_cols = {row["name"] for row in c.execute("PRAGMA table_info(savings_goals)")}
        if "priority" not in existing_goal_cols:
            c.execute("ALTER TABLE savings_goals ADD COLUMN priority INTEGER")
            # Bestehende Ziele bekommen eine Startreihenfolge, die der bisherigen
            # automatischen Sortierung entspricht (Notgroschen zuerst, dann nach
            # Zieldatum) – ab jetzt frei per move_goal_priority() umsortierbar.
            rows = c.execute("SELECT id, name, target_date FROM savings_goals").fetchall()
            ordered = sorted(
                rows,
                key=lambda r: (0 if r["name"] == "Notgroschen" else 1,
                                r["target_date"] is None, r["target_date"] or ""),
            )
            for index, row in enumerate(ordered):
                c.execute("UPDATE savings_goals SET priority = ? WHERE id = ?", (index, row["id"]))
        c.commit()

    def _ensure_default_categories(self):
        defaults = [
            ("Gehalt", "einnahme", "💼"),
            ("Sonstige Einnahmen", "einnahme", "➕"),
            ("Miete", "ausgabe", "🏠"),
            ("Lebensmittel", "ausgabe", "🛒"),
            ("Versicherungen", "ausgabe", "🛡️"),
            ("Freizeit", "ausgabe", "🎉"),
            ("Transport", "ausgabe", "🚌"),
            ("Sonstige Ausgaben", "ausgabe", "📦"),
        ]
        cur = self.conn.execute("SELECT COUNT(*) FROM categories")
        if cur.fetchone()[0] == 0:
            self.conn.executemany(
                "INSERT INTO categories (name, kind, icon) VALUES (?, ?, ?)", defaults
            )
            self.conn.commit()

    # -- Kategorien -------------------------------------------------------

    def list_categories(self, kind=None):
        if kind:
            cur = self.conn.execute(
                "SELECT * FROM categories WHERE kind = ? ORDER BY name", (kind,)
            )
        else:
            cur = self.conn.execute("SELECT * FROM categories ORDER BY kind, name")
        return cur.fetchall()

    def add_category(self, name, kind, icon=None):
        icon = icon or DEFAULT_ICON
        cur = self.conn.execute(
            "INSERT INTO categories (name, kind, icon) VALUES (?, ?, ?)", (name, kind, icon)
        )
        self.conn.commit()
        return cur.lastrowid

    def get_or_create_category(self, name, kind, icon):
        """Liefert eine Kategorie mit diesem Namen, legt sie bei Bedarf an.
        Wird u. a. genutzt, um Sparziel-Einzahlungen als echte Buchung in einer
        eigenen 'Sparbeitrag'-Kategorie zu verbuchen."""
        cur = self.conn.execute("SELECT * FROM categories WHERE name = ?", (name,))
        row = cur.fetchone()
        if row:
            return row
        self.add_category(name, kind, icon)
        return self.conn.execute("SELECT * FROM categories WHERE name = ?", (name,)).fetchone()

    def update_category(self, category_id, name, icon):
        self.conn.execute(
            "UPDATE categories SET name = ?, icon = ? WHERE id = ?",
            (name, icon, category_id),
        )
        self.conn.commit()

    def delete_category(self, category_id):
        self.conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        self.conn.commit()

    # -- Buchungen ----------------------------------------------------------

    def add_transaction(self, date, amount, category_id, description,
                         recurring_template_id=None):
        cur = self.conn.execute(
            "INSERT INTO transactions (date, amount, category_id, description, "
            "recurring_template_id) VALUES (?, ?, ?, ?, ?)",
            (date, amount, category_id, description, recurring_template_id),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_transaction(self, transaction_id, date, amount, category_id, description):
        self.conn.execute(
            "UPDATE transactions SET date = ?, amount = ?, category_id = ?, description = ? "
            "WHERE id = ?",
            (date, amount, category_id, description, transaction_id),
        )
        self.conn.commit()

    def get_transaction(self, transaction_id):
        cur = self.conn.execute("""
            SELECT t.*, c.kind AS kind FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.id = ?
        """, (transaction_id,))
        return cur.fetchone()

    def delete_transaction(self, transaction_id):
        self.conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        self.conn.commit()

    def list_transactions(self, month=None):
        """month im Format YYYY-MM, oder None für alle Buchungen."""
        pattern = _month_pattern(month) if month else "%"
        cur = self.conn.execute("""
            SELECT t.id, t.date, t.amount, t.description, t.recurring_template_id,
                   c.id AS category_id, c.name AS category_name, c.kind, c.icon
            FROM transactions t JOIN categories c ON t.category_id = c.id
            WHERE t.date LIKE ?
            ORDER BY t.date DESC, t.id DESC
        """, (pattern,))
        return cur.fetchall()

    def list_transactions_for_day(self, date):
        cur = self.conn.execute("""
            SELECT t.id, t.date, t.amount, t.description, t.recurring_template_id,
                   c.id AS category_id, c.name AS category_name, c.kind, c.icon
            FROM transactions t JOIN categories c ON t.category_id = c.id
            WHERE t.date = ?
            ORDER BY t.id
        """, (date,))
        return cur.fetchall()

    def days_with_transactions(self, year, month):
        pattern = f"{year:04d}-{month:02d}-%"
        cur = self.conn.execute(
            "SELECT DISTINCT date FROM transactions WHERE date LIKE ?", (pattern,)
        )
        return {int(row["date"].split("-")[2]) for row in cur.fetchall()}

    # -- Wiederkehrende Vorlagen ---------------------------------------------

    def add_recurring_template(self, category_id, amount, description, frequency,
                                start_date, end_date=None):
        cur = self.conn.execute(
            "INSERT INTO recurring_templates (category_id, amount, description, "
            "frequency, start_date, end_date, last_generated_date) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL)",
            (category_id, amount, description, frequency, start_date, end_date),
        )
        self.conn.commit()
        template_id = cur.lastrowid
        self.generate_due_transactions(horizon=self._generated_horizon)
        return template_id

    def list_recurring_templates(self):
        cur = self.conn.execute("""
            SELECT r.*, c.name AS category_name, c.kind, c.icon
            FROM recurring_templates r JOIN categories c ON r.category_id = c.id
            ORDER BY r.start_date DESC
        """)
        return cur.fetchall()

    def get_recurring_template(self, template_id):
        cur = self.conn.execute("""
            SELECT r.*, c.name AS category_name, c.kind, c.icon
            FROM recurring_templates r JOIN categories c ON r.category_id = c.id
            WHERE r.id = ?
        """, (template_id,))
        return cur.fetchone()

    def update_recurring_template(self, template_id, category_id, amount, description,
                                   frequency, start_date, end_date=None, apply_to_past=False):
        """Ändert eine wiederkehrende Vorlage.

        apply_to_past=False (Standard): Nur künftige (heute oder später)
        Buchungen übernehmen die neuen Werte; bereits vergangene bleiben als
        historischer Stand unverändert. Praktisch z. B. bei einer
        Gehaltserhöhung: alte Monate zeigen weiterhin den alten Betrag, erst
        ab jetzt gilt der neue.

        apply_to_past=True: ALLE bisher aus dieser Vorlage erzeugten
        Buchungen (auch vergangene) werden gelöscht und mit den neuen Werten
        komplett neu erzeugt – überschreibt die Historie rückwirkend."""
        if apply_to_past:
            self.conn.execute(
                "DELETE FROM transactions WHERE recurring_template_id = ?",
                (template_id,),
            )
            last_generated = None
        else:
            today = datetime.date.today().isoformat()
            self.conn.execute(
                "DELETE FROM transactions WHERE recurring_template_id = ? AND date >= ?",
                (template_id, today),
            )
            # Letztes verbliebenes (vergangenes) Erzeugungsdatum ermitteln, damit die
            # Neugenerierung nahtlos dort fortsetzt statt Duplikate zu erzeugen oder
            # bereits verbuchte Monate erneut anzulegen.
            row = self.conn.execute(
                "SELECT MAX(date) AS last_date FROM transactions WHERE recurring_template_id = ?",
                (template_id,),
            ).fetchone()
            last_generated = row["last_date"]

        self.conn.execute("""
            UPDATE recurring_templates
            SET category_id = ?, amount = ?, description = ?, frequency = ?,
                start_date = ?, end_date = ?, last_generated_date = ?
            WHERE id = ?
        """, (category_id, amount, description, frequency, start_date, end_date,
              last_generated, template_id))
        self.conn.commit()
        self.generate_due_transactions(horizon=self._generated_horizon)

    def delete_recurring_template(self, template_id, delete_future_transactions=True,
                                   delete_past_transactions=False):
        """Löscht eine wiederkehrende Vorlage.

        delete_future_transactions=True (Standard): löscht die noch nicht
        vergangenen (heute oder später datierten) Buchungen dieser Vorlage.

        delete_past_transactions=False (Standard): bereits vergangene
        Buchungen bleiben erhalten (verlieren nur ihre Verknüpfung zur
        Vorlage, siehe ON DELETE SET NULL im Schema) – auf True setzen, um
        sie ausdrücklich mitzulöschen."""
        if delete_past_transactions:
            self.conn.execute(
                "DELETE FROM transactions WHERE recurring_template_id = ?",
                (template_id,),
            )
        elif delete_future_transactions:
            today = datetime.date.today().isoformat()
            self.conn.execute(
                "DELETE FROM transactions WHERE recurring_template_id = ? AND date >= ?",
                (template_id, today),
            )
        self.conn.execute("DELETE FROM recurring_templates WHERE id = ?", (template_id,))
        self.conn.commit()

    def ensure_horizon(self, target_date: datetime.date):
        """Stellt sicher, dass wiederkehrende Buchungen mindestens bis
        RECURRING_LOOKAHEAD_MONTHS Monate nach target_date erzeugt wurden.
        Damit werden monatliche/wöchentliche/jährliche Vorlagen für JEDEN
        Monat sichtbar, den man sich im Kalender ansieht – nicht nur für die
        nächsten paar Monate ab heute.

        Ruft generate_due_transactions() bewusst OHNE Kurzschluss-Cache auf:
        jede Vorlage merkt sich ihr eigenes last_generated_date, daher ist der
        Aufruf auch bei wiederholter Ausführung günstig (pro Vorlage werden
        nur wirklich fehlende Daten ergänzt). Ein globaler "haben wir schon
        genug generiert"-Cache wäre hier ein Bug: er würde neu angelegte
        Vorlagen nicht bis zum bereits erreichten Horizont nachführen."""
        horizon = add_months(target_date, RECURRING_LOOKAHEAD_MONTHS)
        if self._generated_horizon is None or horizon > self._generated_horizon:
            self._generated_horizon = horizon
        self.generate_due_transactions(horizon=horizon)

    def generate_due_transactions(self, horizon=None):
        """Erzeugt fehlende Buchungen für alle wiederkehrenden Vorlagen bis
        `horizon` (Standard: RECURRING_LOOKAHEAD_MONTHS Monate ab heute),
        bzw. bis end_date der jeweiligen Vorlage, falls das früher ist."""
        if horizon is None:
            horizon = add_months(datetime.date.today(), RECURRING_LOOKAHEAD_MONTHS)

        for tmpl in self.list_recurring_templates():
            start = datetime.date.fromisoformat(tmpl["start_date"])
            end = (datetime.date.fromisoformat(tmpl["end_date"])
                   if tmpl["end_date"] else None)
            last_generated = (datetime.date.fromisoformat(tmpl["last_generated_date"])
                               if tmpl["last_generated_date"] else None)

            current = last_generated + self._step(tmpl["frequency"], last_generated) \
                if last_generated else start

            limit = min(end, horizon) if end else horizon

            newest = last_generated
            while current <= limit:
                self.conn.execute(
                    "INSERT INTO transactions (date, amount, category_id, description, "
                    "recurring_template_id) VALUES (?, ?, ?, ?, ?)",
                    (current.isoformat(), tmpl["amount"], tmpl["category_id"],
                     tmpl["description"], tmpl["id"]),
                )
                newest = current
                current = current + self._step(tmpl["frequency"], current)

            if newest and newest != last_generated:
                self.conn.execute(
                    "UPDATE recurring_templates SET last_generated_date = ? WHERE id = ?",
                    (newest.isoformat(), tmpl["id"]),
                )
        self.conn.commit()

    @staticmethod
    def _step(frequency, from_date):
        if frequency == "woechentlich":
            return datetime.timedelta(days=7)
        if frequency == "jaehrlich":
            next_year = add_months(from_date, 12)
            return next_year - from_date
        # monatlich (Standardfall)
        next_month = add_months(from_date, 1)
        return next_month - from_date

    # -- Budgets --------------------------------------------------------------

    def set_budget(self, category_id, month, limit_amount):
        self.conn.execute("""
            INSERT INTO budgets (category_id, month, limit_amount)
            VALUES (?, ?, ?)
            ON CONFLICT(category_id, month) DO UPDATE SET limit_amount = excluded.limit_amount
        """, (category_id, month, limit_amount))
        self.conn.commit()

    def budget_overview(self, month):
        """Liefert je Ausgaben-Kategorie: Budgetlimit (falls gesetzt) und Ist-Ausgaben.
        Der Datumsfilter sitzt bewusst in der JOIN-Bedingung (nicht erst im
        SUM/CASE), damit SQLite pro Kategorie nur die Buchungen des
        gewünschten Monats heranzieht statt aller Buchungen aller Zeiten."""
        cur = self.conn.execute("""
            SELECT c.id AS category_id, c.name AS category_name, c.icon,
                   b.limit_amount,
                   COALESCE(SUM(-t.amount), 0) AS spent
            FROM categories c
            LEFT JOIN budgets b ON b.category_id = c.id AND b.month = ?
            LEFT JOIN transactions t ON t.category_id = c.id AND t.date LIKE ?
            WHERE c.kind = 'ausgabe'
            GROUP BY c.id
            ORDER BY c.name
        """, (month, _month_pattern(month)))
        return cur.fetchall()

    # -- Sparziele --------------------------------------------------------------

    def add_goal(self, name, target_amount, target_date):
        """Legt ein neues Sparziel an. Die Priorität wird automatisch ans Ende
        der bestehenden Reihenfolge angehängt (höchste Zahl = niedrigste
        Priorität); über move_goal_priority() lässt sie sich frei anpassen."""
        row = self.conn.execute("SELECT MAX(priority) AS max_priority FROM savings_goals").fetchone()
        next_priority = (row["max_priority"] + 1) if row["max_priority"] is not None else 0
        cur = self.conn.execute(
            "INSERT INTO savings_goals (name, target_amount, target_date, current_amount, priority) "
            "VALUES (?, ?, ?, 0, ?)",
            (name, target_amount, target_date, next_priority),
        )
        self.conn.commit()
        return cur.lastrowid

    def delete_goal(self, goal_id):
        self.conn.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))
        self.conn.commit()

    def list_goals(self):
        """Liefert alle Sparziele in ihrer (manuell einstellbaren) Prioritäts-
        reihenfolge – wird u. a. von der Mehrfachziele-Empfehlung in der
        Finanzplanung genutzt, um festzulegen, welches Ziel zuerst befüllt wird."""
        cur = self.conn.execute(
            "SELECT * FROM savings_goals ORDER BY priority IS NULL, priority"
        )
        return cur.fetchall()

    def move_goal_priority(self, goal_id, direction):
        """Verschiebt ein Sparziel in der Prioritätsreihenfolge um eine Position.
        direction: -1 = nach oben (höhere Priorität), +1 = nach unten.
        Vertauscht dazu einfach die priority-Werte mit dem Nachbarziel."""
        goals = self.list_goals()
        ids = [g["id"] for g in goals]
        if goal_id not in ids:
            return False
        index = ids.index(goal_id)
        neighbor_index = index + direction
        if neighbor_index < 0 or neighbor_index >= len(ids):
            return False

        this_priority = goals[index]["priority"]
        neighbor_id = ids[neighbor_index]
        neighbor_priority = goals[neighbor_index]["priority"]

        self.conn.execute("UPDATE savings_goals SET priority = ? WHERE id = ?",
                           (neighbor_priority, goal_id))
        self.conn.execute("UPDATE savings_goals SET priority = ? WHERE id = ?",
                           (this_priority, neighbor_id))
        self.conn.commit()
        return True

    def get_goal_by_name(self, name):
        cur = self.conn.execute("SELECT * FROM savings_goals WHERE name = ?", (name,))
        return cur.fetchone()

    def update_goal_target(self, goal_id, target_amount, target_date=None):
        """Aktualisiert Zielbetrag (und optional Zieldatum) eines bestehenden
        Sparziels, ohne den bereits angesparten Betrag zu verändern. Wird u. a.
        genutzt, um ein Notgroschen-Ziel neu zu berechnen, wenn sich die
        Fixkosten geändert haben."""
        if target_date is not None:
            self.conn.execute(
                "UPDATE savings_goals SET target_amount = ?, target_date = ? WHERE id = ?",
                (target_amount, target_date, goal_id),
            )
        else:
            self.conn.execute(
                "UPDATE savings_goals SET target_amount = ? WHERE id = ?",
                (target_amount, goal_id),
            )
        self.conn.commit()

    def estimate_monthly_fixed_costs(self):
        """Schätzt die monatlichen Fixkosten aus allen aktuell laufenden
        wiederkehrenden Ausgaben-Vorlagen (wöchentliche/jährliche Beträge
        werden auf einen Monatswert umgerechnet). Dient als Ausgangspunkt für
        die Notgroschen-Berechnung und die Anlage-Empfehlung – frei
        überschreibbar, falls z. B. nicht alle Fixkosten als wiederkehrende
        Buchung erfasst sind."""
        today = datetime.date.today().isoformat()
        cur = self.conn.execute("""
            SELECT r.amount, r.frequency FROM recurring_templates r
            JOIN categories c ON r.category_id = c.id
            WHERE c.kind = 'ausgabe' AND (r.end_date IS NULL OR r.end_date >= ?)
        """, (today,))
        total = 0.0
        for row in cur.fetchall():
            amount = abs(row["amount"])
            if row["frequency"] == "monatlich":
                total += amount
            elif row["frequency"] == "woechentlich":
                total += amount * 52 / 12
            elif row["frequency"] == "jaehrlich":
                total += amount / 12
        return round(total, 2)

    def add_contribution(self, goal_id, date, amount, create_transaction=False, goal_name=None):
        """Verbucht eine Einzahlung auf ein Sparziel. Wenn create_transaction=True,
        wird zusätzlich eine echte Ausgaben-Buchung in der (automatisch angelegten)
        Kategorie 'Sparbeitrag' erzeugt, damit die Einzahlung auch im Kalender,
        in den Budgets und Auswertungen als Geldabfluss sichtbar ist."""
        self.conn.execute(
            "INSERT INTO savings_contributions (goal_id, date, amount) VALUES (?, ?, ?)",
            (goal_id, date, amount),
        )
        self.conn.execute(
            "UPDATE savings_goals SET current_amount = current_amount + ? WHERE id = ?",
            (amount, goal_id),
        )
        self.conn.commit()

        if create_transaction:
            category = self.get_or_create_category("Sparbeitrag", "ausgabe", "💰")
            description = f"Einzahlung Sparziel: {goal_name}" if goal_name else "Einzahlung Sparziel"
            self.add_transaction(date, -amount, category["id"], description)

    @staticmethod
    def recommend_allocation_multi(net_income, monthly_fixed_costs, leisure_amount,
                                    starting_capital, goals):
        """Transparente Faustregel zur Aufteilung von monatlichem Sparbetrag
        und vorhandenem Startkapital auf eine PRIORITÄTSLISTE von Sparzielen
        (typischerweise: Notgroschen zuerst, dann weitere Ziele z. B. nach
        Zieldatum sortiert) und – was danach übrig bleibt – den ETF-Sparplan.
        `goals` ist eine Liste von dicts mit 'id', 'name', 'target_amount',
        'current_amount', in der gewünschten Prioritätsreihenfolge.

        Für jedes Ziel wird der Reihe nach zunächst verfügbares Startkapital,
        dann verfügbarer Monatsbetrag eingesetzt, bis die Lücke gedeckt ist,
        bevor das nächste Ziel an der Reihe ist. Was danach übrig bleibt,
        fließt in den ETF-Sparplan. Auch das ist eine transparente
        Faustregel-Modellrechnung, KEINE individuelle Finanzberatung."""
        monthly_available = max(0.0, net_income - monthly_fixed_costs - leisure_amount)
        remaining_capital = max(0.0, starting_capital)
        remaining_monthly = monthly_available

        breakdown = []
        for g in goals:
            gap = max(0.0, g["target_amount"] - g["current_amount"])
            capital_alloc = min(remaining_capital, gap)
            remaining_capital -= capital_alloc
            gap_after_capital = gap - capital_alloc

            monthly_alloc = min(remaining_monthly, gap_after_capital)
            remaining_monthly -= monthly_alloc

            months_to_fill = None
            if monthly_alloc > 0:
                months_to_fill = math.ceil(gap_after_capital / monthly_alloc)

            breakdown.append({
                "id": g.get("id"),
                "name": g["name"],
                "target_amount": round(g["target_amount"], 2),
                "current_amount": round(g["current_amount"], 2),
                "gap_before": round(gap, 2),
                "capital_allocated": round(capital_alloc, 2),
                "monthly_allocated": round(monthly_alloc, 2),
                "remaining_gap": round(gap_after_capital, 2),
                "months_to_fill": months_to_fill,
                "fully_funded": gap_after_capital <= 0,
            })

        return {
            "monthly_available": round(monthly_available, 2),
            "goals": breakdown,
            "monthly_to_etf": round(remaining_monthly, 2),
            "capital_to_etf": round(remaining_capital, 2),
        }

    # Faustregel-Tabelle für den Aktien-/ETF-Anteil des zum Investieren
    # vorgesehenen Betrags, abhängig von Anlagehorizont und Risikoprofil.
    # Grundgedanke: je kürzer der Horizont bzw. je konservativer das Profil,
    # desto mehr sollte als Sicherheitsreserve (Tagesgeld o. Ä.) statt in
    # (volatile) ETFs fließen. Stark vereinfacht, keine Anlageberatung.
    _EQUITY_SHARE_TABLE = [
        # (min_jahre, max_jahre_exklusiv, {profil: anteil_prozent})
        (0, 3, {"konservativ": 0, "ausgewogen": 0, "offensiv": 0}),
        (3, 6, {"konservativ": 30, "ausgewogen": 50, "offensiv": 70}),
        (6, 10, {"konservativ": 50, "ausgewogen": 70, "offensiv": 90}),
        (10, None, {"konservativ": 60, "ausgewogen": 80, "offensiv": 100}),
    ]

    @classmethod
    def suggest_equity_share(cls, horizon_years, risk_profile):
        """Liefert einen Vorschlag (0–100 %), welcher Anteil des zum
        Investieren vorgesehenen Betrags in den ETF-Sparplan fließen könnte;
        der Rest wäre als Sicherheitsreserve (Tagesgeld/Festgeld) gedacht.
        Faustregel nach Anlagehorizont (Jahre) und Risikoprofil
        ('konservativ' | 'ausgewogen' | 'offensiv'). Stark vereinfacht und
        NICHT als individuelle Anlageberatung zu verstehen – reale Empfehlungen
        hängen zusätzlich von Einkommenssicherheit, Verschuldung, Alter,
        weiteren Vermögenswerten usw. ab."""
        for lo, hi, profile_map in cls._EQUITY_SHARE_TABLE:
            if horizon_years >= lo and (hi is None or horizon_years < hi):
                return profile_map.get(risk_profile, 50)
        return 50

    # -- ETF-Sparpläne ----------------------------------------------------------

    def add_etf_plan(self, name, monthly_amount, annual_return_percent, start_date,
                      duration_years, annual_increase_percent=0, max_monthly_amount=None):
        cur = self.conn.execute(
            "INSERT INTO etf_plans (name, monthly_amount, annual_return_percent, "
            "start_date, duration_years, annual_increase_percent, max_monthly_amount) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, monthly_amount, annual_return_percent, start_date, duration_years,
             annual_increase_percent, max_monthly_amount),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_etf_plans(self):
        cur = self.conn.execute("SELECT * FROM etf_plans ORDER BY id DESC")
        return cur.fetchall()

    def delete_etf_plan(self, plan_id):
        self.conn.execute("DELETE FROM etf_plans WHERE id = ?", (plan_id,))
        self.conn.commit()

    @staticmethod
    def project_etf_plan(monthly_amount, annual_return_percent, duration_years,
                          annual_increase_percent=0, max_monthly_amount=None):
        """Berechnet die Wertentwicklung eines Sparplans Jahr für Jahr (vor Steuern).

        - monthly_rate: aus der jährlichen Rendite abgeleitete Monatsverzinsung.
        - annual_increase_percent: jährliche Erhöhung der Sparrate (z. B. durch
          Gehaltssteigerung), optional gedeckelt durch max_monthly_amount.

        Rückgabe: Liste von dicts mit year, invested, value, gain, monthly_rate_amount
        (Sparrate, die in diesem Jahr galt).
        """
        monthly_rate = (1 + annual_return_percent / 100) ** (1 / 12) - 1
        results = []
        value = 0.0
        invested = 0.0
        current_monthly = monthly_amount

        for year in range(1, duration_years + 1):
            for _ in range(12):
                value = value * (1 + monthly_rate) + current_monthly
                invested += current_monthly
            results.append({
                "year": year,
                "invested": round(invested, 2),
                "value": round(value, 2),
                "gain": round(value - invested, 2),
                "monthly_rate_amount": round(current_monthly, 2),
            })
            if annual_increase_percent:
                current_monthly = current_monthly * (1 + annual_increase_percent / 100)
                if max_monthly_amount:
                    current_monthly = min(current_monthly, max_monthly_amount)

        return results

    @staticmethod
    def project_etf_plan_with_vorabpauschale(monthly_amount, annual_return_percent,
                                              duration_years, annual_increase_percent=0,
                                              max_monthly_amount=None,
                                              basiszins_percent=2.55,
                                              teilfreistellung_percent=30.0,
                                              kapitalertragsteuer_percent=25.0,
                                              soli_percent=5.5,
                                              sparerpauschbetrag=1000.0):
        """Wie project_etf_plan, simuliert aber zusätzlich die jährliche
        Vorabpauschale nach dem Investmentsteuergesetz:

        - Basisertrag = Wert zu Jahresbeginn × Basiszins × 70 %
          (Basiszins wird jährlich vom Bundesministerium der Finanzen
          veröffentlicht und schwankt – hier frei einstellbar, Vorbelegung
          orientiert sich am Wert für 2024).
        - Vorabpauschale = min(Basisertrag, tatsächlicher Wertzuwachs des
          Jahres ohne neue Einzahlungen), mindestens 0 (bei Kursverlusten
          fällt keine Vorabpauschale an).
        - Die Vorabpauschale wird sofort (jährlich) unter Anrechnung von
          Teilfreistellung und einem JÄHRLICH neu verfügbaren
          Sparerpauschbetrag versteuert; die Steuer wird dem Depotwert
          entnommen (vereinfachend, statt separat gezahlt).
        - Der kumulierte, bereits versteuerte Wertzuwachs wird zurückgegeben,
          damit er bei der Steuer auf den Veräußerungsgewinn am Laufzeitende
          angerechnet werden kann (keine Doppelbesteuerung).

        Rückgabe: (results, cumulative_pretaxed_gain)
        """
        monthly_rate = (1 + annual_return_percent / 100) ** (1 / 12) - 1
        results = []
        value = 0.0
        invested = 0.0
        current_monthly = monthly_amount
        cumulative_pretaxed_gain = 0.0

        for year in range(1, duration_years + 1):
            value_start = value
            deposits_this_year = 0.0
            for _ in range(12):
                value = value * (1 + monthly_rate) + current_monthly
                invested += current_monthly
                deposits_this_year += current_monthly
            value_before_tax = value

            basisertrag = max(0.0, value_start) * (basiszins_percent / 100.0) * 0.7
            wertzuwachs = value_before_tax - value_start - deposits_this_year
            vorabpauschale = max(0.0, min(basisertrag, wertzuwachs)) if wertzuwachs > 0 else 0.0

            taxable_vorab = max(0.0, vorabpauschale * (1 - teilfreistellung_percent / 100.0)
                                 - sparerpauschbetrag)
            tax_this_year = taxable_vorab * (kapitalertragsteuer_percent / 100.0) \
                * (1 + soli_percent / 100.0)

            value = value_before_tax - tax_this_year
            cumulative_pretaxed_gain += vorabpauschale

            results.append({
                "year": year,
                "invested": round(invested, 2),
                "value": round(value, 2),
                "gain": round(value - invested, 2),
                "monthly_rate_amount": round(current_monthly, 2),
                "vorabpauschale": round(vorabpauschale, 2),
                "tax_paid": round(tax_this_year, 2),
            })

            if annual_increase_percent:
                current_monthly = current_monthly * (1 + annual_increase_percent / 100)
                if max_monthly_amount:
                    current_monthly = min(current_monthly, max_monthly_amount)

        return results, round(cumulative_pretaxed_gain, 2)

    @staticmethod
    def apply_final_tax_with_vorabpauschale_credit(final_value, total_invested,
                                                     cumulative_pretaxed_gain,
                                                     teilfreistellung_percent=30.0,
                                                     kapitalertragsteuer_percent=25.0,
                                                     soli_percent=5.5,
                                                     sparerpauschbetrag=1000.0):
        """Steuer auf den Veräußerungsgewinn am Laufzeitende, wenn bereits über
        Jahre hinweg Vorabpauschalen versteuert wurden (Anrechnung, damit derselbe
        Wertzuwachs nicht doppelt besteuert wird)."""
        gain = final_value - total_invested
        remaining_gain = max(0.0, gain - cumulative_pretaxed_gain)
        gain_after_teilfreistellung = remaining_gain * (1 - teilfreistellung_percent / 100.0)
        taxable = max(0.0, gain_after_teilfreistellung - sparerpauschbetrag)
        tax = taxable * (kapitalertragsteuer_percent / 100.0) * (1 + soli_percent / 100.0)
        return {
            "gain": round(gain, 2),
            "already_taxed_gain": round(cumulative_pretaxed_gain, 2),
            "final_tax": round(tax, 2),
            "value_after_tax": round(final_value - tax, 2),
        }

    @staticmethod
    def apply_german_capital_gains_tax(final_value, total_invested,
                                        teilfreistellung_percent=30.0,
                                        kapitalertragsteuer_percent=25.0,
                                        soli_percent=5.5,
                                        sparerpauschbetrag=1000.0):
        """Vereinfachte deutsche Abgeltungsteuer-Berechnung auf den Gesamtgewinn
        bei (angenommenem) Verkauf am Ende der Laufzeit.

        Vereinfachungen (bewusst, um die Rechnung nachvollziehbar zu halten):
        - Die Vorabpauschale (jährliche Teilbesteuerung von Fonds nach dem
          Investmentsteuergesetz) wird NICHT berücksichtigt; es wird von
          nachgelagerter Besteuerung des Gesamtgewinns bei Entnahme ausgegangen.
        - Der Sparerpauschbetrag wird einmalig am Ende angesetzt, nicht jährlich.
        - Kirchensteuer wird nicht berücksichtigt.
        - Die Teilfreistellung (Standard 30 % für Aktienfonds nach §20 InvStG)
          ist frei einstellbar (z. B. 0 % für Einzelaktien/Anleihen-ETFs,
          15 % für Mischfonds, 30 % für Aktienfonds mit ≥51 % Aktienquote,
          60 % für Immobilienfonds).

        Rückgabe: dict mit gain, taxable_gain, tax, value_after_tax.
        """
        gain = final_value - total_invested
        gain_after_teilfreistellung = gain * (1 - teilfreistellung_percent / 100)
        taxable_gain = max(0.0, gain_after_teilfreistellung - sparerpauschbetrag)
        tax = taxable_gain * (kapitalertragsteuer_percent / 100) * (1 + soli_percent / 100)
        tax = max(0.0, tax)
        return {
            "gain": round(gain, 2),
            "taxable_gain": round(taxable_gain, 2),
            "tax": round(tax, 2),
            "value_after_tax": round(final_value - tax, 2),
        }

    # -- Auswertungen (für Diagramme) --------------------------------------------

    def spending_by_category(self, month):
        """Ausgaben (positive Beträge) je Kategorie im gegebenen Monat, absteigend."""
        cur = self.conn.execute("""
            SELECT c.name AS category_name, c.icon, -SUM(t.amount) AS total
            FROM transactions t JOIN categories c ON t.category_id = c.id
            WHERE c.kind = 'ausgabe' AND t.date LIKE ? AND t.amount < 0
            GROUP BY c.id
            ORDER BY total DESC
        """, (_month_pattern(month),))
        return cur.fetchall()

    def income_by_category(self, month):
        """Einnahmen je Kategorie im gegebenen Monat, absteigend. Pendant zu
        spending_by_category(), u. a. für die linke Seite des
        Sankey-Geldfluss-Diagramms."""
        cur = self.conn.execute("""
            SELECT c.name AS category_name, c.icon, SUM(t.amount) AS total
            FROM transactions t JOIN categories c ON t.category_id = c.id
            WHERE c.kind = 'einnahme' AND t.date LIKE ? AND t.amount > 0
            GROUP BY c.id
            ORDER BY total DESC
        """, (_month_pattern(month),))
        return cur.fetchall()

    def monthly_trend(self, num_months=6, end_month=None):
        """Liefert für die letzten `num_months` Monate (bis einschließlich end_month,
        Format YYYY-MM, Standard: aktueller Monat) je Einnahmen- und Ausgabensumme."""
        if end_month:
            end_date = datetime.datetime.strptime(end_month, "%Y-%m").date().replace(day=1)
        else:
            end_date = datetime.date.today().replace(day=1)

        months = []
        cursor_date = add_months(end_date, -(num_months - 1))
        for _ in range(num_months):
            months.append(cursor_date.strftime("%Y-%m"))
            cursor_date = add_months(cursor_date, 1)

        results = []
        for month in months:
            cur = self.conn.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
                    COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) AS expense
                FROM transactions WHERE date LIKE ?
            """, (_month_pattern(month),))
            row = cur.fetchone()
            results.append({"month": month, "income": row["income"], "expense": row["expense"]})
        return results

    def yearly_overview(self, year):
        """Einnahmen/Ausgaben je Monat eines Jahres (für die Jahresansicht im
        Buchungen-Tab). Liefert immer 12 Einträge, auch für Monate ohne Buchungen."""
        cur = self.conn.execute("""
            SELECT substr(date, 1, 7) AS month,
                   COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income,
                   COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) AS expense
            FROM transactions WHERE date LIKE ?
            GROUP BY month
        """, (f"{year:04d}-%",))
        by_month = {row["month"]: row for row in cur.fetchall()}

        results = []
        for m in range(1, 13):
            key = f"{year:04d}-{m:02d}"
            row = by_month.get(key)
            results.append({
                "month": m,
                "income": row["income"] if row else 0.0,
                "expense": row["expense"] if row else 0.0,
            })
        return results

    # -- Einstellungen / Kontostand ----------------------------------------------

    def get_setting(self, key, default=None):
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key, value):
        self.conn.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, str(value)))
        self.conn.commit()

    def set_starting_balance(self, amount, reference_date):
        """Legt ein Startguthaben zu einem Stichtag fest (z. B. den
        tatsächlichen Kontostand von heute). Der aktuelle Kontostand wird
        daraus als Startguthaben + Summe aller Buchungen ab diesem Stichtag
        berechnet – so muss nicht jede Buchung seit Kontoeröffnung erfasst
        werden, um einen realistischen Kontostand zu bekommen. Besonders
        hilfreich beim Einstieg in Notgroschen-Aufbau oder ETF-Sparen, wo
        der tatsächlich vorhandene Betrag zählt."""
        self.set_setting("starting_balance_amount", amount)
        self.set_setting("starting_balance_date", reference_date)

    def get_starting_balance(self):
        """Liefert (amount, date) des hinterlegten Startguthabens, oder
        (None, None), falls noch keines gesetzt wurde."""
        amount = self.get_setting("starting_balance_amount")
        date = self.get_setting("starting_balance_date")
        if amount is None or date is None:
            return None, None
        return float(amount), date

    def get_current_account_balance(self, as_of_date=None):
        """Berechnet den aktuellen Kontostand: Startguthaben + Summe aller
        Buchungen vom Stichtag (inklusive) bis einschließlich as_of_date
        (Standard: heute). None, falls noch kein Startguthaben hinterlegt
        wurde (Feature also noch nicht genutzt wird)."""
        amount, reference_date = self.get_starting_balance()
        if amount is None:
            return None
        if as_of_date is None:
            as_of_date = datetime.date.today().isoformat()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM transactions "
            "WHERE date >= ? AND date <= ?",
            (reference_date, as_of_date),
        ).fetchone()
        return round(amount + row["total"], 2)

    # -- Export / Import ----------------------------------------------------------

    def export_transactions_csv(self, path):
        rows = self.list_transactions()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Datum", "Kategorie", "Art", "Betrag", "Beschreibung"])
            for r in rows:
                writer.writerow([
                    r["date"], r["category_name"], r["kind"],
                    f"{r['amount']:.2f}".replace(".", ","), r["description"] or "",
                ])

    # Spaltennamen-Synonyme (klein geschrieben, ohne Leerzeichen) für den CSV-Import,
    # damit auch Exporte aus anderen Haushaltsbuch-/Banking-Programmen erkannt werden.
    _CSV_COLUMN_ALIASES = {
        "date": {"datum", "date", "buchungsdatum", "wertstellung"},
        "amount": {"betrag", "amount", "wert", "umsatz", "value"},
        "category": {"kategorie", "category", "kategorie/typ"},
        "kind": {"art", "kind", "type", "typ"},
        "description": {"beschreibung", "description", "verwendungszweck", "notiz",
                         "note", "buchungstext", "text"},
    }

    @staticmethod
    def _match_columns(fieldnames):
        """Ordnet die tatsächlichen CSV-Spaltennamen den erwarteten Feldern zu
        (case-insensitive, tolerant gegenüber Leerzeichen)."""
        normalized = {(fn or "").strip().lower(): fn for fn in fieldnames}
        mapping = {}
        for field, aliases in FinanceStore._CSV_COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in normalized:
                    mapping[field] = normalized[alias]
                    break
        return mapping

    @staticmethod
    def _parse_csv_date(text):
        text = (text or "").strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_csv_amount(text):
        text = (text or "").strip()
        if not text:
            return None
        # Währungssymbole/Leerzeichen entfernen
        for symbol in ("€", "EUR", "$", "USD", " "):
            text = text.replace(symbol, "")
        text = text.strip()
        negative = text.startswith("-") or text.startswith("(")
        text = text.strip("-()")
        if "," in text and "." in text:
            # Deutsches Format: Punkt = Tausendertrennzeichen, Komma = Dezimal
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                # Englisches Format: Komma = Tausendertrennzeichen
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")
        try:
            value = float(text)
        except ValueError:
            return None
        return -value if negative else value

    def import_transactions_csv(self, path):
        """Importiert Buchungen aus einer CSV-Datei. Erkennt automatisch das
        Trennzeichen (';' oder ',') sowie deutsche/englische Zahlen- und
        Datumsformate. Unbekannte Kategorien werden automatisch angelegt
        (Art wird aus der Art-Spalte übernommen, falls vorhanden, sonst aus
        dem Vorzeichen des Betrags abgeleitet).

        Rückgabe: dict mit imported (Anzahl), skipped (Anzahl übersprungener
        Zeilen) und errors (Liste von Fehlertexten mit Zeilennummer)."""
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
            except csv.Error:
                dialect = csv.excel
                dialect.delimiter = ";" if sample.count(";") >= sample.count(",") else ","

            reader = csv.DictReader(f, dialect=dialect)
            if not reader.fieldnames:
                return {"imported": 0, "skipped": 0, "errors": ["Datei enthält keine Kopfzeile."]}

            columns = self._match_columns(reader.fieldnames)
            if "date" not in columns or "amount" not in columns:
                return {"imported": 0, "skipped": 0,
                        "errors": ["Konnte Datums- oder Betrags-Spalte nicht erkennen. "
                                   "Erwartet werden Spalten wie 'Datum' und 'Betrag'."]}

            imported = 0
            skipped = 0
            errors = []

            for line_number, row in enumerate(reader, start=2):
                date_obj = self._parse_csv_date(row.get(columns["date"], ""))
                amount = self._parse_csv_amount(row.get(columns["amount"], ""))
                if date_obj is None or amount is None:
                    skipped += 1
                    errors.append(f"Zeile {line_number}: Datum oder Betrag nicht lesbar, übersprungen.")
                    continue

                kind_text = (row.get(columns.get("kind"), "") or "").strip().lower() if "kind" in columns else ""
                if kind_text in ("einnahme", "income", "credit", "gutschrift"):
                    kind = "einnahme"
                elif kind_text in ("ausgabe", "expense", "debit", "lastschrift"):
                    kind = "ausgabe"
                else:
                    kind = "einnahme" if amount >= 0 else "ausgabe"

                category_name = (row.get(columns.get("category"), "") or "").strip() \
                    if "category" in columns else ""
                if not category_name:
                    category_name = "Sonstige Einnahmen" if kind == "einnahme" else "Sonstige Ausgaben"
                category = self.get_or_create_category(category_name, kind, DEFAULT_ICON)

                description = (row.get(columns.get("description"), "") or "").strip() \
                    if "description" in columns else ""

                self.add_transaction(date_obj.isoformat(), amount, category["id"], description)
                imported += 1

            return {"imported": imported, "skipped": skipped, "errors": errors}

    def export_backup_json(self, path):
        data = {
            "categories": [dict(r) for r in self.conn.execute("SELECT * FROM categories")],
            "recurring_templates": [dict(r) for r in self.conn.execute("SELECT * FROM recurring_templates")],
            "transactions": [dict(r) for r in self.conn.execute("SELECT * FROM transactions")],
            "budgets": [dict(r) for r in self.conn.execute("SELECT * FROM budgets")],
            "savings_goals": [dict(r) for r in self.conn.execute("SELECT * FROM savings_goals")],
            "savings_contributions": [dict(r) for r in self.conn.execute("SELECT * FROM savings_contributions")],
            "etf_plans": [dict(r) for r in self.conn.execute("SELECT * FROM etf_plans")],
            "exported_at": datetime.datetime.now().isoformat(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def import_backup_json(self, path):
        """Ersetzt den kompletten Datenbestand durch den Inhalt der Backup-Datei."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        c = self.conn
        c.execute("PRAGMA foreign_keys = OFF")
        tables = ["savings_contributions", "savings_goals", "budgets", "transactions",
                  "recurring_templates", "etf_plans", "categories"]
        for table in tables:
            c.execute(f"DELETE FROM {table}")

        def insert_all(table, rows):
            if not rows:
                return
            columns = list(rows[0].keys())
            placeholders = ", ".join("?" * len(columns))
            column_list = ", ".join(columns)
            c.executemany(
                f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})",
                [tuple(row[col] for col in columns) for row in rows],
            )

        insert_all("categories", data.get("categories", []))
        insert_all("recurring_templates", data.get("recurring_templates", []))
        insert_all("transactions", data.get("transactions", []))
        insert_all("budgets", data.get("budgets", []))
        insert_all("savings_goals", data.get("savings_goals", []))
        insert_all("savings_contributions", data.get("savings_contributions", []))
        insert_all("etf_plans", data.get("etf_plans", []))

        c.execute("PRAGMA foreign_keys = ON")
        c.commit()
        self._generated_horizon = None
