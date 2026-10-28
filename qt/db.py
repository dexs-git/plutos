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
import collections
import csv
import re
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
    BACKUP_KEEP = 14  # so viele automatische Datenbank-Backups bleiben erhalten

    def __init__(self, db_path: Path = DB_PATH):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path)
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

        -- Vorlagen für häufige Einzelbuchungen ("Tanken 60 €" per Klick)
        CREATE TABLE IF NOT EXISTS quick_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            amount REAL NOT NULL,
            description TEXT
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

        existing_tx_cols = {row["name"] for row in c.execute("PRAGMA table_info(transactions)")}
        if "tags" not in existing_tx_cols:
            c.execute("ALTER TABLE transactions ADD COLUMN tags TEXT NOT NULL DEFAULT ''")

        for tbl in ("recurring_templates", "quick_templates"):
            cols = {row["name"] for row in c.execute(f"PRAGMA table_info({tbl})")}
            if "tags" not in cols:
                c.execute(f"ALTER TABLE {tbl} ADD COLUMN tags TEXT NOT NULL DEFAULT ''")

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

    @staticmethod
    def normalize_tags(text):
        """Macht aus Eingaben wie "Urlaub, #2026 ; urlaub" eine saubere,
        kommagetrennte Liste ("Urlaub,2026"): Raute und Leerraum entfernt,
        Duplikate (ohne Beachtung der Schreibweise) nur einmal."""
        if not text:
            return ""
        seen, result = set(), []
        for part in re.split(r"[,;]", text):
            tag = part.strip().lstrip("#").strip()
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                result.append(tag)
        return ",".join(result)

    @staticmethod
    def split_tags(tags):
        return [t for t in (tags or "").split(",") if t]

    def add_transaction(self, date, amount, category_id, description,
                         recurring_template_id=None, tags=""):
        cur = self.conn.execute(
            "INSERT INTO transactions (date, amount, category_id, description, "
            "recurring_template_id, tags) VALUES (?, ?, ?, ?, ?, ?)",
            (date, amount, category_id, description, recurring_template_id,
             self.normalize_tags(tags)),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_transaction(self, transaction_id, date, amount, category_id, description,
                            tags=None):
        """tags=None lässt die vorhandenen Tags unverändert."""
        if tags is None:
            self.conn.execute(
                "UPDATE transactions SET date = ?, amount = ?, category_id = ?, description = ? "
                "WHERE id = ?",
                (date, amount, category_id, description, transaction_id),
            )
        else:
            self.conn.execute(
                "UPDATE transactions SET date = ?, amount = ?, category_id = ?, description = ?, "
                "tags = ? WHERE id = ?",
                (date, amount, category_id, description, self.normalize_tags(tags), transaction_id),
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
        """Löscht eine Buchung. Die zuletzt gelöschte Buchung wird gemerkt und
        lässt sich mit undo_delete_transaction() wiederherstellen."""
        row = self.conn.execute("SELECT * FROM transactions WHERE id = ?",
                                (transaction_id,)).fetchone()
        self._last_deleted = dict(row) if row else None
        self.conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        self.conn.commit()

    def can_undo_delete(self):
        return getattr(self, "_last_deleted", None) is not None

    def undo_delete_transaction(self):
        """Stellt die zuletzt gelöschte Buchung wieder her (nur eine Ebene).
        Gibt die wiederhergestellte Buchung als dict zurück oder None."""
        data = getattr(self, "_last_deleted", None)
        if not data:
            return None
        data = dict(data)
        # Gehört die Buchung zu einer inzwischen gelöschten Vorlage, wird sie
        # zur normalen Einzelbuchung statt an einer toten Referenz zu hängen.
        template_id = data.get("recurring_template_id")
        if template_id is not None and self.conn.execute(
                "SELECT 1 FROM recurring_templates WHERE id = ?", (template_id,)).fetchone() is None:
            data["recurring_template_id"] = None
        if self.conn.execute("SELECT 1 FROM transactions WHERE id = ?",
                             (data["id"],)).fetchone():
            data.pop("id")  # ID wurde inzwischen neu vergeben
        columns = ", ".join(data)
        placeholders = ", ".join("?" * len(data))
        self.conn.execute(f"INSERT INTO transactions ({columns}) VALUES ({placeholders})",
                          list(data.values()))
        self.conn.commit()
        self._last_deleted = None
        return data

    # -- Schnellbuchungs-Vorlagen -------------------------------------------------

    def add_quick_template(self, name, category_id, amount, description="", tags=""):
        cur = self.conn.execute(
            "INSERT INTO quick_templates (name, category_id, amount, description, tags) "
            "VALUES (?, ?, ?, ?, ?)",
            (name.strip(), category_id, amount, description or "", self.normalize_tags(tags)))
        self.conn.commit()
        return cur.lastrowid

    def list_quick_templates(self):
        return self.conn.execute("""
            SELECT q.id, q.name, q.amount, q.description, q.tags,
                   c.id AS category_id, c.name AS category_name, c.kind, c.icon
            FROM quick_templates q JOIN categories c ON q.category_id = c.id
            ORDER BY q.name COLLATE NOCASE
        """).fetchall()

    def delete_quick_template(self, template_id):
        self.conn.execute("DELETE FROM quick_templates WHERE id = ?", (template_id,))
        self.conn.commit()

    def book_quick_template(self, template_id, date):
        """Legt aus einer Vorlage eine Buchung für `date` (ISO) an; Rückgabe: ID."""
        q = self.conn.execute("SELECT * FROM quick_templates WHERE id = ?",
                              (template_id,)).fetchone()
        if q is None:
            return None
        return self.add_transaction(date, q["amount"], q["category_id"], q["description"],
                                    tags=q["tags"])

    def list_transactions(self, month=None):
        """month im Format YYYY-MM, oder None für alle Buchungen."""
        pattern = _month_pattern(month) if month else "%"
        cur = self.conn.execute("""
            SELECT t.id, t.date, t.amount, t.description, t.recurring_template_id, t.tags,
                   c.id AS category_id, c.name AS category_name, c.kind, c.icon
            FROM transactions t JOIN categories c ON t.category_id = c.id
            WHERE t.date LIKE ?
            ORDER BY t.date DESC, t.id DESC
        """, (pattern,))
        return cur.fetchall()

    def search_transactions(self, text=None, category_id=None, kind=None,
                            date_from=None, date_to=None, min_amount=None,
                            max_amount=None, include_future=False, limit=2000, tag=None):
        """Durchsucht alle Buchungen. Alle Filter sind optional und werden
        mit UND verknüpft.

        text: Teilstring in Beschreibung, Kategoriename oder Tags (ohne
              Beachtung der Groß-/Kleinschreibung); ein führendes "#" wird
              ignoriert
        tag: genau dieses Tag (z. B. "Urlaub")
        kind: 'einnahme' oder 'ausgabe'
        date_from/date_to: ISO-Datum 'YYYY-MM-DD', jeweils einschließlich
        min_amount/max_amount: Grenzen für den Betrag OHNE Vorzeichen
        include_future: False blendet Buchungen nach heute aus (wiederkehrende
              Buchungen werden vorab für die Zukunft erzeugt)

        Gibt (rows, truncated) zurück; truncated ist True, wenn mehr als
        `limit` Treffer existieren."""
        where, params = [], []
        if text:
            pattern = f"%{text.strip().lstrip('#').lower()}%"
            where.append("(LOWER(COALESCE(t.description, '')) LIKE ? OR LOWER(c.name) LIKE ? "
                         "OR LOWER(COALESCE(t.tags, '')) LIKE ?)")
            params += [pattern, pattern, pattern]
        if tag:
            where.append("(',' || LOWER(COALESCE(t.tags, '')) || ',') LIKE ?")
            params.append(f"%,{tag.strip().lstrip('#').lower()},%")
        if category_id is not None:
            where.append("c.id = ?")
            params.append(category_id)
        if kind:
            where.append("c.kind = ?")
            params.append(kind)
        if date_from:
            where.append("t.date >= ?")
            params.append(date_from)
        if date_to:
            where.append("t.date <= ?")
            params.append(date_to)
        if not include_future:
            where.append("t.date <= ?")
            params.append(datetime.date.today().isoformat())
        if min_amount is not None:
            where.append("ABS(t.amount) >= ?")
            params.append(min_amount - 0.005)
        if max_amount is not None:
            where.append("ABS(t.amount) <= ?")
            params.append(max_amount + 0.005)
        sql = """
            SELECT t.id, t.date, t.amount, t.description, t.recurring_template_id, t.tags,
                   c.id AS category_id, c.name AS category_name, c.kind, c.icon
            FROM transactions t JOIN categories c ON t.category_id = c.id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY t.date DESC, t.id DESC LIMIT ?"
        rows = self.conn.execute(sql, params + [limit + 1]).fetchall()
        return rows[:limit], len(rows) > limit

    def list_transactions_for_day(self, date):
        cur = self.conn.execute("""
            SELECT t.id, t.date, t.amount, t.description, t.recurring_template_id, t.tags,
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
                                start_date, end_date=None, tags=""):
        cur = self.conn.execute(
            "INSERT INTO recurring_templates (category_id, amount, description, "
            "frequency, start_date, end_date, last_generated_date, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
            (category_id, amount, description, frequency, start_date, end_date,
             self.normalize_tags(tags)),
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
                                   frequency, start_date, end_date=None, apply_to_past=False,
                                   tags=None):
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

        if tags is None:
            row = self.conn.execute("SELECT tags FROM recurring_templates WHERE id = ?",
                                    (template_id,)).fetchone()
            tags = row["tags"] if row else ""
        self.conn.execute("""
            UPDATE recurring_templates
            SET category_id = ?, amount = ?, description = ?, frequency = ?,
                start_date = ?, end_date = ?, last_generated_date = ?, tags = ?
            WHERE id = ?
        """, (category_id, amount, description, frequency, start_date, end_date,
              last_generated, self.normalize_tags(tags), template_id))
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
                    "recurring_template_id, tags) VALUES (?, ?, ?, ?, ?, ?)",
                    (current.isoformat(), tmpl["amount"], tmpl["category_id"],
                     tmpl["description"], tmpl["id"], tmpl["tags"]),
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
        """Setzt das Budget einer Kategorie ab diesem Monat (YYYY-MM). Es gilt
        für alle folgenden Monate weiter, bis ein neuer Wert gesetzt oder das
        Budget beendet wird; frühere Monate bleiben unverändert. Ein Betrag
        von 0 (oder None) beendet das Budget ab diesem Monat."""
        limit_amount = float(limit_amount or 0)
        if limit_amount < 0:
            limit_amount = 0.0
        self.conn.execute("""
            INSERT INTO budgets (category_id, month, limit_amount)
            VALUES (?, ?, ?)
            ON CONFLICT(category_id, month) DO UPDATE SET limit_amount = excluded.limit_amount
        """, (category_id, month, limit_amount))
        self.conn.commit()

    def end_budget(self, category_id, month):
        """Beendet das Budget einer Kategorie ab diesem Monat (spätere Monate
        haben dann kein Budget, bis wieder eines gesetzt wird)."""
        self.set_budget(category_id, month, 0)

    def _effective_budgets(self, month):
        """{category_id: (limit, quelle_monat)} der zum Monat geltenden
        Budgets: je Kategorie der jüngste Eintrag bis einschließlich dieses
        Monats. Beendete Budgets (Betrag 0) fehlen im Ergebnis."""
        latest = {}
        for r in self.conn.execute(
                "SELECT category_id, month, limit_amount FROM budgets "
                "WHERE month <= ? ORDER BY month", (month,)):
            latest[r["category_id"]] = (r["limit_amount"], r["month"])
        return {cid: v for cid, v in latest.items() if v[0] and v[0] > 0}

    def budget_overview(self, month):
        """Liefert je Ausgaben-Kategorie: geltendes Budgetlimit (None, wenn
        keines), Ist-Ausgaben und `inherited_from` – der Monat, aus dem das
        Budget übernommen wurde (None, wenn es für genau diesen Monat gesetzt
        wurde oder kein Budget gilt)."""
        effective = self._effective_budgets(month)
        cur = self.conn.execute("""
            SELECT c.id AS category_id, c.name AS category_name, c.icon,
                   COALESCE(SUM(-t.amount), 0) AS spent
            FROM categories c
            LEFT JOIN transactions t ON t.category_id = c.id AND t.date LIKE ?
            WHERE c.kind = 'ausgabe'
            GROUP BY c.id
            ORDER BY c.name
        """, (_month_pattern(month),))
        rows = []
        for r in cur.fetchall():
            limit, source = effective.get(r["category_id"], (None, None))
            rows.append({
                "category_id": r["category_id"], "category_name": r["category_name"],
                "icon": r["icon"], "limit_amount": limit, "spent": r["spent"],
                "inherited_from": source if source and source != month else None,
            })
        return rows

    def budget_year_summary(self, year, today=None):
        """Wie oft und um wie viel lag man je Kategorie über/unter dem
        Monatsbudget? Gezählt werden nur abgeschlossene Monate des Jahres mit
        geltendem Budget; der laufende Monat steht in `cells`, zählt aber noch
        nicht mit.

        Rückgabe: {"year", "complete_months", "rows": [...], "totals": {...}};
        jede Zeile hat category_id/-name/icon, `cells` (12 Einträge: None oder
        {limit, spent, diff, complete}), months_over, months_under, over_sum
        (Summe der Überschreitungen), under_sum (Summe nicht ausgegebener
        Beträge) und net (Ausgaben minus Budget, positiv = insgesamt drüber)."""
        today = today or datetime.date.today()
        current = f"{today.year:04d}-{today.month:02d}"
        per_category = {}
        for m in range(1, 13):
            key = f"{year:04d}-{m:02d}"
            if key > current:
                break
            for r in self.budget_overview(key):
                if not r["limit_amount"]:
                    continue
                row = per_category.setdefault(r["category_id"], {
                    "category_id": r["category_id"], "category_name": r["category_name"],
                    "icon": r["icon"], "cells": [None] * 12,
                    "months_over": 0, "months_under": 0, "over_sum": 0.0,
                    "under_sum": 0.0, "net": 0.0})
                diff = r["spent"] - r["limit_amount"]
                complete = key < current
                row["cells"][m - 1] = {"limit": r["limit_amount"], "spent": r["spent"],
                                       "diff": diff, "complete": complete}
                if complete:
                    if diff > 0.005:
                        row["months_over"] += 1
                        row["over_sum"] += diff
                    else:
                        row["months_under"] += 1
                        row["under_sum"] += -diff
                    row["net"] += diff
        rows = sorted(per_category.values(), key=lambda r: r["category_name"].lower())
        totals = {"months_over": sum(r["months_over"] for r in rows),
                  "months_under": sum(r["months_under"] for r in rows),
                  "over_sum": sum(r["over_sum"] for r in rows),
                  "under_sum": sum(r["under_sum"] for r in rows),
                  "net": sum(r["net"] for r in rows)}
        return {"year": year, "rows": rows, "totals": totals,
                "complete_months": sum(1 for m in range(1, 13)
                                       if f"{year:04d}-{m:02d}" < current)}

    BUDGET_WARN_FRACTION = 0.8

    @staticmethod
    def budget_level(spent, limit_amount):
        """'ok', 'warn' (ab 80 % des Budgets), 'full' (genau ausgeschöpft,
        auf den Cent), 'over' (tatsächlich überschritten) oder 'none', wenn
        kein Budget gesetzt ist."""
        if not limit_amount or limit_amount <= 0:
            return "none"
        if spent - limit_amount > 0.005:
            return "over"
        if spent >= limit_amount - 0.005:
            return "full"
        if spent >= limit_amount * FinanceStore.BUDGET_WARN_FRACTION:
            return "warn"
        return "ok"

    def budget_status(self, category_id, month):
        """Budget-Stand einer Kategorie in einem Monat (YYYY-MM) oder None,
        wenn dafür kein Budget gesetzt ist."""
        for r in self.budget_overview(month):
            if r["category_id"] == category_id:
                if r["limit_amount"] is None:
                    return None
                return {"limit": r["limit_amount"], "spent": r["spent"],
                        "level": self.budget_level(r["spent"], r["limit_amount"])}
        return None

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

        # Solange noch Ziele offen sind, bleibt für den ETF-Sparplan nichts
        # übrig. Damit klar ist, was danach möglich wäre: nach wie vielen
        # Monaten alle Ziele gedeckt wären (Monatsbetrag fließt der Reihe nach
        # in die Ziele) – ab dann stünde der gesamte Monatsbetrag zur Verfügung.
        total_open_gap = sum(b["remaining_gap"] for b in breakdown)
        all_funded = total_open_gap <= 0.005
        months_until_funded = None
        if not all_funded and monthly_available > 0:
            months_until_funded = math.ceil(total_open_gap / monthly_available)

        return {
            "monthly_available": round(monthly_available, 2),
            "all_goals_funded": all_funded,
            "months_until_funded": months_until_funded,
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

    @staticmethod
    def etf_scenarios(monthly_amount, annual_return_percent, duration_years,
                      annual_increase_percent=0, max_monthly_amount=None,
                      spread_percent=2.0, inflation_percent=2.0,
                      use_vorabpauschale=False, basiszins_percent=2.55,
                      teilfreistellung_percent=30.0, kapitalertragsteuer_percent=25.0,
                      soli_percent=5.5, sparerpauschbetrag=1000.0):
        """Rechnet denselben Sparplan für drei Renditeannahmen durch:
        pessimistisch (Rendite - spread), erwartet und optimistisch
        (Rendite + spread). Das sind Gedankenspiele über die Streuung möglicher
        Ergebnisse, keine Prognose und keine Anlageempfehlung.

        Je Szenario: Endwert vor Steuern, Steuer bei Verkauf, Endwert nach
        Steuern und der Endwert nach Steuern in heutiger Kaufkraft (abgezinst
        mit der Inflationsrate über die Laufzeit)."""
        scenarios = (("Pessimistisch", annual_return_percent - spread_percent),
                     ("Erwartet", annual_return_percent),
                     ("Optimistisch", annual_return_percent + spread_percent))
        deflator = (1 + inflation_percent / 100.0) ** duration_years
        out = []
        for label, rate in scenarios:
            rate = max(rate, -99.0)
            if use_vorabpauschale:
                results, pretaxed = FinanceStore.project_etf_plan_with_vorabpauschale(
                    monthly_amount, rate, duration_years,
                    annual_increase_percent=annual_increase_percent,
                    max_monthly_amount=max_monthly_amount,
                    basiszins_percent=basiszins_percent,
                    teilfreistellung_percent=teilfreistellung_percent,
                    kapitalertragsteuer_percent=kapitalertragsteuer_percent,
                    soli_percent=soli_percent, sparerpauschbetrag=sparerpauschbetrag)
                final = results[-1]
                tax = FinanceStore.apply_final_tax_with_vorabpauschale_credit(
                    final["value"], final["invested"], pretaxed,
                    teilfreistellung_percent=teilfreistellung_percent,
                    kapitalertragsteuer_percent=kapitalertragsteuer_percent,
                    soli_percent=soli_percent, sparerpauschbetrag=sparerpauschbetrag)
            else:
                results = FinanceStore.project_etf_plan(
                    monthly_amount, rate, duration_years,
                    annual_increase_percent=annual_increase_percent,
                    max_monthly_amount=max_monthly_amount)
                final = results[-1]
                tax = FinanceStore.apply_german_capital_gains_tax(
                    final["value"], final["invested"],
                    teilfreistellung_percent=teilfreistellung_percent,
                    kapitalertragsteuer_percent=kapitalertragsteuer_percent,
                    soli_percent=soli_percent, sparerpauschbetrag=sparerpauschbetrag)
            after_tax = tax.get("value_after_tax")
            out.append({
                "label": label, "annual_return": round(rate, 2),
                "invested": final["invested"], "value": final["value"],
                "tax": tax.get("final_tax", tax.get("tax")),
                "value_after_tax": after_tax,
                "real_value_after_tax": round(after_tax / deflator, 2),
            })
        return out

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

    # -- Kategorien-Vergleich (Monat vs. Vormonat, Jahresverlauf) ---------------

    def category_comparison(self, month_current, month_previous):
        """Vergleicht die Ausgaben je Kategorie zweier Monate (Format YYYY-MM).

        Liefert eine Liste von dicts (name, icon, current, previous, diff, pct),
        absteigend nach dem größeren der beiden Beträge. `pct` ist die
        prozentuale Veränderung gegenüber dem Vergleichsmonat und None, wenn
        dort nichts ausgegeben wurde (Division durch 0 / "neu")."""
        cur_rows = {r["category_name"]: r for r in self.spending_by_category(month_current)}
        prev_rows = {r["category_name"]: r for r in self.spending_by_category(month_previous)}
        result = []
        for name in set(cur_rows) | set(prev_rows):
            icon = (cur_rows.get(name) or prev_rows[name])["icon"]
            current = cur_rows[name]["total"] if name in cur_rows else 0.0
            previous = prev_rows[name]["total"] if name in prev_rows else 0.0
            diff = current - previous
            pct = (diff / previous * 100.0) if previous > 0 else None
            result.append({
                "name": name, "icon": icon,
                "current": round(current, 2), "previous": round(previous, 2),
                "diff": round(diff, 2), "pct": pct,
            })
        result.sort(key=lambda r: (-max(r["current"], r["previous"]), r["name"]))
        return result

    def year_comparison(self, year):
        """Monatswerte (Einnahmen/Ausgaben) eines Jahres neben denen des
        Vorjahres sowie Jahressummen.

        Rückgabe: dict mit
          months  - 12 dicts (month 1-12, income, expense, prev_income, prev_expense)
          totals  - dict (income, expense, saved, prev_income, prev_expense, prev_saved)
        Kategorienvergleich Jahr gegen Vorjahr: category_comparison(str(year),
        str(year - 1)) – die LIKE-Muster akzeptieren auch reine Jahreszahlen."""
        cur = self.yearly_overview(year)
        prev = self.yearly_overview(year - 1)
        months = []
        for c, p in zip(cur, prev):
            months.append({
                "month": c["month"],
                "income": c["income"], "expense": c["expense"],
                "prev_income": p["income"], "prev_expense": p["expense"],
            })
        income = sum(m["income"] for m in months)
        expense = sum(m["expense"] for m in months)
        prev_income = sum(m["prev_income"] for m in months)
        prev_expense = sum(m["prev_expense"] for m in months)
        totals = {
            "income": round(income, 2), "expense": round(expense, 2),
            "saved": round(income - expense, 2),
            "prev_income": round(prev_income, 2), "prev_expense": round(prev_expense, 2),
            "prev_saved": round(prev_income - prev_expense, 2),
        }
        return {"months": months, "totals": totals}

    def expense_categories_in_year(self, year):
        """Ausgabenkategorien, in denen im Jahr mindestens eine Buchung liegt."""
        cur = self.conn.execute("""
            SELECT DISTINCT c.name AS category_name, c.icon
            FROM transactions t JOIN categories c ON t.category_id = c.id
            WHERE c.kind = 'ausgabe' AND t.amount < 0 AND t.date LIKE ?
            ORDER BY c.name COLLATE NOCASE
        """, (f"{year:04d}-%",))
        return cur.fetchall()

    def category_year_series(self, year, category_name=None):
        """Ausgaben je Monat (12 Werte, Jan-Dez) für eine Kategorie oder – bei
        category_name=None – für alle Ausgaben zusammen."""
        sql = """
            SELECT CAST(substr(t.date, 6, 2) AS INTEGER) AS m, -SUM(t.amount) AS total
            FROM transactions t JOIN categories c ON t.category_id = c.id
            WHERE c.kind = 'ausgabe' AND t.amount < 0 AND t.date LIKE ?
        """
        params = [f"{year:04d}-%"]
        if category_name is not None:
            sql += " AND c.name = ?"
            params.append(category_name)
        sql += " GROUP BY m"
        by_month = {row["m"]: row["total"] for row in self.conn.execute(sql, params)}
        return [round(by_month.get(m, 0.0), 2) for m in range(1, 13)]

    # -- Datenbank-Backups -------------------------------------------------------

    @property
    def backup_dir(self):
        return self.db_path.parent / "backups"

    def create_db_backup(self, force=False):
        """Sichert die komplette Datenbank als Kopie nach <Datenordner>/backups/.

        Ohne `force` wird höchstens ein Backup pro Tag angelegt (gedacht für
        den automatischen Aufruf beim Programmstart). Es werden nur die
        letzten BACKUP_KEEP Backups behalten. Gibt den Pfad der neuen Datei
        zurück oder None, wenn heute schon gesichert wurde."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.date.today().strftime("%Y%m%d")
        if not force and any(self.backup_dir.glob(f"finanzen-{today}-*.db")):
            return None
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.backup_dir / f"finanzen-{stamp}.db"
        dest = sqlite3.connect(str(target))
        try:
            self.conn.backup(dest)  # konsistent, auch bei offener Verbindung
        finally:
            dest.close()
        for old in sorted(self.backup_dir.glob("finanzen-*.db"))[:-self.BACKUP_KEEP]:
            old.unlink(missing_ok=True)
        return target

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

    # -- Notgroschen als Unterkonto -------------------------------------------

    def notgroschen_pocket_enabled(self):
        return self.get_setting("notgroschen_pocket", "0") == "1"

    def set_notgroschen_pocket(self, enabled):
        self.set_setting("notgroschen_pocket", "1" if enabled else "0")

    def get_balance_breakdown(self):
        """Teilt das Vermögen in Girokonto und (optionales) Notgroschen-
        Unterkonto. Das Unterkonto entspricht dem angesparten Betrag des
        Sparziels „Notgroschen“. Girokonto = berechneter Kontostand (gebuchte
        Sparbeiträge haben ihn bereits reduziert, es wird also nichts doppelt
        gezählt). None, falls noch kein Startguthaben hinterlegt ist."""
        giro = self.get_current_account_balance()
        if giro is None:
            return None
        pocket = 0.0
        if self.notgroschen_pocket_enabled():
            goal = self.get_goal_by_name("Notgroschen")
            if goal:
                pocket = round(float(goal["current_amount"]), 2)
        return {"giro": giro, "pocket": pocket, "total": round(giro + pocket, 2)}

    # -- Übersichtsseite ----------------------------------------------------------

    def dashboard_data(self, today=None):
        """Kennzahlen für die Übersichtsseite (Stand: today, Standard heute).

        Monatssummen gibt es "bisher" (bis einschließlich heute) und
        "geplant" (inkl. künftiger Buchungen, z. B. wiederkehrender
        Vorlagen). Als Vergleichsmaßstab für das Ausgabentempo dient die
        Summe der Monatsbudgets; gibt es keine, der Durchschnitt der bis zu
        drei Vormonate mit Ausgaben (sonst None)."""
        if today is None:
            today = datetime.date.today()
        month = today.strftime("%Y-%m")
        pattern = _month_pattern(month)
        first = today.replace(day=1)
        days_in_month = (add_months(first, 1) - first).days

        def sums(upto=None):
            sql = ("SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income, "
                   "COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) AS expense "
                   "FROM transactions WHERE date LIKE ?")
            params = [pattern]
            if upto:
                sql += " AND date <= ?"
                params.append(upto.isoformat())
            row = self.conn.execute(sql, params).fetchone()
            return float(row["income"]), float(row["expense"])

        income_sofar, expense_sofar = sums(today)
        income_planned, expense_planned = sums()

        budgets = [r for r in self.budget_overview(month) if r["limit_amount"]]
        budget_total = sum(r["limit_amount"] for r in budgets)
        baseline, baseline_kind = None, None
        if budget_total > 0:
            baseline, baseline_kind = budget_total, "budget"
        else:
            previous = []
            for back in (1, 2, 3):
                m = add_months(first, -back).strftime("%Y-%m")
                row = self.conn.execute(
                    "SELECT COALESCE(SUM(-amount), 0) AS e FROM transactions "
                    "WHERE date LIKE ? AND amount < 0", (_month_pattern(m),)).fetchone()
                if row["e"] > 0:
                    previous.append(float(row["e"]))
            if previous:
                baseline, baseline_kind = sum(previous) / len(previous), "average"

        top_budgets = sorted(
            ({"name": r["category_name"], "icon": r["icon"], "spent": float(r["spent"]),
              "limit": float(r["limit_amount"]),
              "level": self.budget_level(r["spent"], r["limit_amount"])} for r in budgets),
            key=lambda b: b["spent"] / b["limit"], reverse=True)[:5]

        goals = [{"id": g["id"], "name": g["name"], "target": float(g["target_amount"] or 0),
                  "current": float(g["current_amount"] or 0)} for g in self.list_goals()]

        recent = [dict(r) for r in self.conn.execute("""
            SELECT t.date, t.amount, t.description, c.name AS category_name, c.icon
            FROM transactions t JOIN categories c ON t.category_id = c.id
            WHERE t.date <= ? ORDER BY t.date DESC, t.id DESC LIMIT 6
        """, (today.isoformat(),)).fetchall()]

        return {
            "month": month, "day": today.day, "days_in_month": days_in_month,
            "income_sofar": income_sofar, "expense_sofar": expense_sofar,
            "income_planned": income_planned, "expense_planned": expense_planned,
            "baseline": baseline, "baseline_kind": baseline_kind,
            "balance": self.get_balance_breakdown(),
            "pocket_enabled": self.notgroschen_pocket_enabled(),
            "top_budgets": top_budgets, "goals": goals, "recent": recent,
            "trend": self.monthly_trend(6, month),
        }

    # -- Export / Import ----------------------------------------------------------

    # -- Tags -------------------------------------------------------------------

    def tag_summary(self, year=None):
        """Auswertung nach Tags: je Tag Anzahl der Buchungen sowie Summe der
        Ausgaben und Einnahmen (year=None: alle Jahre). Sortiert nach
        Ausgaben, absteigend. Geplante, noch zukünftige Buchungen zählen
        nicht mit."""
        pattern = f"{year:04d}-%" if year else "%"
        today = datetime.date.today().isoformat()
        stats = {}
        for r in self.conn.execute(
                "SELECT amount, tags FROM transactions "
                "WHERE tags != '' AND date LIKE ? AND date <= ?", (pattern, today)):
            for tag in self.split_tags(r["tags"]):
                entry = stats.setdefault(tag.lower(), {"tag": tag, "count": 0,
                                                       "expense": 0.0, "income": 0.0})
                entry["count"] += 1
                if r["amount"] < 0:
                    entry["expense"] += -r["amount"]
                else:
                    entry["income"] += r["amount"]
        return sorted(stats.values(), key=lambda e: (-e["expense"], e["tag"].lower()))

    def list_tags(self):
        """Alle verwendeten Tags (alphabetisch), z. B. für Vorschläge."""
        names = {}
        for r in self.conn.execute("SELECT DISTINCT tags FROM transactions WHERE tags != ''"):
            for tag in self.split_tags(r["tags"]):
                names.setdefault(tag.lower(), tag)
        return sorted(names.values(), key=str.lower)

    # -- Erinnerungen -------------------------------------------------------------

    def muted_budget_reminders(self):
        """IDs der Kategorien, deren Budget nicht in den Erinnerungen auftauchen soll."""
        raw = self.get_setting("reminder_muted_budgets", "") or ""
        return {int(x) for x in raw.split(",") if x.strip().isdigit()}

    def set_budget_reminder(self, category_id, enabled):
        """Schaltet die Erinnerung für das Budget einer Kategorie an oder aus
        (z. B. Miete: soll nicht jeden Monat als „ausgeschöpft“ gemeldet werden)."""
        muted = self.muted_budget_reminders()
        if enabled:
            muted.discard(int(category_id))
        else:
            muted.add(int(category_id))
        self.set_setting("reminder_muted_budgets", ",".join(str(i) for i in sorted(muted)))

    def reminders(self, today=None, days=7):
        """Hinweise für die Übersichtsseite, geordnet nach Dringlichkeit:
        - Budgets des laufenden Monats ab 80 % (kind "budget", level "warn"
          oder "over"),
        - Sparziele mit Zieldatum in den nächsten 60 Tagen (oder bereits
          überschritten), die noch nicht erreicht sind (kind "goal"),
        - wiederkehrende Buchungen, die in den nächsten `days` Tagen fällig
          werden (kind "recurring").
        Es wird nichts gespeichert: sobald die Ursache weg ist, verschwindet
        auch der Hinweis."""
        today = today or datetime.date.today()
        items = []

        budgets = []
        muted = self.muted_budget_reminders()
        for r in self.budget_overview(today.strftime("%Y-%m")):
            if not r["limit_amount"] or r["category_id"] in muted:
                continue
            level = self.budget_level(r["spent"], r["limit_amount"])
            if level in ("warn", "full", "over"):
                budgets.append({"kind": "budget", "level": level, "name": r["category_name"],
                                "category_id": r["category_id"],
                                "icon": r["icon"], "spent": r["spent"], "limit": r["limit_amount"],
                                "percent": r["spent"] / r["limit_amount"] * 100})
        budgets.sort(key=lambda b: (b["level"] != "over", -b["percent"]))
        items += budgets

        for g in self.list_goals():
            if not g["target_date"] or g["target_amount"] <= 0:
                continue
            missing = g["target_amount"] - (g["current_amount"] or 0)
            if missing <= 0.005:
                continue
            due = datetime.date.fromisoformat(g["target_date"])
            if (due - today).days <= 60:
                items.append({"kind": "goal", "name": g["name"], "date": g["target_date"],
                              "missing": missing, "overdue": due < today})

        self.ensure_horizon(today + datetime.timedelta(days=days))
        for r in self.conn.execute("""
                SELECT t.date, t.amount, t.description, c.name AS category_name, c.icon
                FROM transactions t JOIN categories c ON t.category_id = c.id
                WHERE t.recurring_template_id IS NOT NULL AND t.date > ? AND t.date <= ?
                ORDER BY t.date, t.id""",
                (today.isoformat(), (today + datetime.timedelta(days=days)).isoformat())):
            items.append({"kind": "recurring", "date": r["date"], "amount": r["amount"],
                          "text": (r["description"] or r["category_name"]).strip(),
                          "icon": r["icon"]})
        return items

    # -- Monatsabschluss ----------------------------------------------------------

    def month_summary(self, month):
        """Kennzahlen eines abgeschlossenen Monats (YYYY-MM): Einnahmen,
        Ausgaben, Gespartes, Sparquote, Vergleich zum Vormonat, größte
        Ausgabenkategorie sowie wie viele Budgets eingehalten wurden."""
        def sums(m):
            row = self.conn.execute(
                "SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS income, "
                "COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0) AS expense, "
                "COUNT(*) AS n FROM transactions WHERE date LIKE ?", (_month_pattern(m),)).fetchone()
            return row["income"], row["expense"], row["n"]

        income, expense, count = sums(month)
        year, mon = int(month[:4]), int(month[5:7])
        prev = add_months(datetime.date(year, mon, 1), -1).strftime("%Y-%m")
        prev_income, prev_expense, prev_count = sums(prev)
        top = self.spending_by_category(month)
        top_category = None
        if top:
            best = max(top, key=lambda r: r["total"])
            top_category = {"name": best["category_name"], "icon": best["icon"], "amount": best["total"],
                            "share": best["total"] / expense if expense else 0.0}
        budgets = [r for r in self.budget_overview(month) if r["limit_amount"]]
        over = sorted(({"name": r["category_name"], "icon": r["icon"],
                        "over_by": r["spent"] - r["limit_amount"]}
                       for r in budgets if r["spent"] - r["limit_amount"] > 0.005),
                      key=lambda r: -r["over_by"])
        return {
            "month": month, "count": count, "income": income, "expense": expense,
            "saved": income - expense,
            "saving_rate": (income - expense) / income if income > 0 else None,
            "prev_expense": prev_expense if prev_count else None,
            "expense_change": ((expense - prev_expense) / prev_expense
                               if prev_count and prev_expense > 0 else None),
            "top_category": top_category,
            "budget_count": len(budgets), "budgets_ok": len(budgets) - len(over),
            "budgets_over": over,
        }

    def pending_month_summary(self, today=None):
        """Monatsabschluss für den Vormonat, solange er Buchungen enthält und
        noch nicht ausgeblendet wurde; sonst None."""
        today = today or datetime.date.today()
        prev = add_months(today.replace(day=1), -1).strftime("%Y-%m")
        if self.get_setting("month_summary_seen") == prev:
            return None
        summary = self.month_summary(prev)
        return summary if summary["count"] else None

    def dismiss_month_summary(self, month):
        self.set_setting("month_summary_seen", month)

    def export_transactions_csv(self, path):
        rows = self.list_transactions()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Datum", "Kategorie", "Art", "Betrag", "Beschreibung", "Tags"])
            for r in rows:
                writer.writerow([
                    r["date"], r["category_name"], r["kind"],
                    f"{r['amount']:.2f}".replace(".", ","), r["description"] or "",
                    ", ".join(self.split_tags(r["tags"])),
                ])

    # Spaltennamen-Synonyme (klein geschrieben, ohne Leerzeichen) für den CSV-Import,
    # damit auch Exporte aus anderen Haushaltsbuch-/Banking-Programmen erkannt werden.
    _CSV_COLUMN_ALIASES = {
        "date": {"datum", "date", "buchungsdatum", "wertstellung", "buchungstag", "valuta"},
        "amount": {"betrag", "amount", "wert", "umsatz", "value", "betrag (eur)",
                    "betrag in eur", "umsatz in eur"},
        "category": {"kategorie", "category", "kategorie/typ"},
        "kind": {"art", "kind", "type", "typ"},
        "description": {"beschreibung", "description", "verwendungszweck", "notiz",
                         "note", "buchungstext", "text"},
        "tags": {"tags", "tag", "schlagwörter", "schlagworte", "labels"},
        "payee": {"empfänger", "zahlungsempfänger", "beguenstigter/zahlungspflichtiger",
                   "begünstigter/zahlungspflichtiger", "auftraggeber", "payee", "name"},
    }

    # Stichwort-Regeln für Zeilen ohne Kategorie-Spalte (Bank-Exporte): Treffer im
    # Empfänger/Verwendungszweck ordnen die Buchung einer Standardkategorie zu.
    # (Kategorie, Art, Symbol, Stichwörter in Kleinbuchstaben)
    _CSV_KEYWORD_RULES = [
        ("Gehalt", "einnahme", "💼", ("gehalt", "lohn", "bezüge", "salary")),
        ("Lebensmittel", "ausgabe", "🛒", ("rewe", "edeka", "aldi", "lidl", "penny", "netto",
                                           "kaufland", "dm drogerie", "rossmann", "bäckerei",
                                           "backerei", "supermarkt")),
        ("Transport", "ausgabe", "🚌", ("tankstelle", "aral", "shell", "esso", "bahn",
                                         "db vertrieb", "bvg", "mvg", "bus", "taxi", "uber",
                                         "deutschlandticket")),
        ("Versicherungen", "ausgabe", "🛡️", ("versicherung", "allianz", "huk", "haftpflicht",
                                              "krankenkasse")),
        ("Miete", "ausgabe", "🏠", ("miete", "hausverwaltung", "wohnungsbau")),
        ("Freizeit", "ausgabe", "🎉", ("netflix", "spotify", "kino", "cafe", "café",
                                        "restaurant", "steam", "disney", "fitness")),
    ]

    @classmethod
    def _guess_category(cls, text, kind):
        """Liefert (name, icon) einer Standardkategorie anhand von Stichwörtern
        oder None, wenn keine Regel passt (dann greift 'Sonstige …')."""
        lowered = (text or "").lower()
        for name, rule_kind, icon, keywords in cls._CSV_KEYWORD_RULES:
            if rule_kind == kind and any(k in lowered for k in keywords):
                return name, icon
        return None

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

        Zeilen ohne Kategorie werden per Stichwortregeln (z. B. "REWE" ->
        Lebensmittel) einer Standardkategorie zugeordnet. Bereits vorhandene
        Buchungen (gleiches Datum, gleicher Betrag, gleiche Beschreibung)
        werden nicht doppelt angelegt, sodass derselbe Kontoauszug gefahrlos
        mehrfach importiert werden kann.

        Rückgabe: dict mit imported (Anzahl), skipped (Anzahl nicht lesbarer
        Zeilen), duplicates (Anzahl erkannter Duplikate) und errors (Liste von
        Fehlertexten mit Zeilennummer)."""
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
            duplicates = 0
            errors = []

            # Vorhandene Buchungen vor dem Import zählen. Pro Treffer wird ein
            # Eintrag "verbraucht"; so bleiben zwei echte gleiche Zeilen in
            # einer Datei (zwei Kaffee am selben Tag) erhalten, ein zweiter
            # Import derselben Datei legt aber nichts doppelt an.
            existing = collections.Counter(
                (r["date"], round(r["amount"], 2), r["description"] or "")
                for r in self.conn.execute(
                    "SELECT date, amount, description FROM transactions"))

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

                # Vorzeichen passend zur Art vereinheitlichen (Ausgaben negativ).
                amount = -abs(amount) if kind == "ausgabe" else abs(amount)

                description = (row.get(columns.get("description"), "") or "").strip() \
                    if "description" in columns else ""
                payee = (row.get(columns.get("payee"), "") or "").strip() \
                    if "payee" in columns else ""
                if payee and payee.lower() not in description.lower():
                    description = f"{payee} – {description}" if description else payee

                key = (date_obj.isoformat(), round(amount, 2), description)
                if existing[key] > 0:
                    existing[key] -= 1
                    duplicates += 1
                    continue

                category_name = (row.get(columns.get("category"), "") or "").strip() \
                    if "category" in columns else ""
                icon = DEFAULT_ICON
                if not category_name:
                    guess = self._guess_category(description, kind)
                    if guess:
                        category_name, icon = guess
                    else:
                        category_name = ("Sonstige Einnahmen" if kind == "einnahme"
                                         else "Sonstige Ausgaben")
                category = self.get_or_create_category(category_name, kind, icon)

                tags = (row.get(columns.get("tags"), "") or "") if "tags" in columns else ""
                self.add_transaction(date_obj.isoformat(), amount, category["id"], description,
                                     tags=tags)
                imported += 1

            return {"imported": imported, "skipped": skipped,
                    "duplicates": duplicates, "errors": errors}

    def export_backup_json(self, path):
        data = {
            "categories": [dict(r) for r in self.conn.execute("SELECT * FROM categories")],
            "recurring_templates": [dict(r) for r in self.conn.execute("SELECT * FROM recurring_templates")],
            "transactions": [dict(r) for r in self.conn.execute("SELECT * FROM transactions")],
            "budgets": [dict(r) for r in self.conn.execute("SELECT * FROM budgets")],
            "savings_goals": [dict(r) for r in self.conn.execute("SELECT * FROM savings_goals")],
            "savings_contributions": [dict(r) for r in self.conn.execute("SELECT * FROM savings_contributions")],
            "etf_plans": [dict(r) for r in self.conn.execute("SELECT * FROM etf_plans")],
            "quick_templates": [dict(r) for r in self.conn.execute("SELECT * FROM quick_templates")],
            "settings": [dict(r) for r in self.conn.execute("SELECT * FROM settings")],
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
                  "recurring_templates", "etf_plans", "quick_templates", "categories"]
        # Einstellungen (z. B. Startguthaben) nur ersetzen, wenn das Backup sie
        # enthält; ältere Backups kennen sie nicht und sollen sie nicht löschen.
        if "settings" in data:
            tables.append("settings")
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
        insert_all("quick_templates", data.get("quick_templates", []))
        insert_all("settings", data.get("settings", []))

        c.execute("PRAGMA foreign_keys = ON")
        c.commit()
        self._generated_horizon = None
