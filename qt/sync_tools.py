"""Synchronisation über einen Ordner (z. B. mit Syncthing) und Inbox-Import.

Gemeinsames Modul von Qt- und GTK-Version (die Dateien sind identisch);
es braucht nur die Standardbibliothek.

Zwei Bausteine:

1. SNAPSHOTS – Plutos schreibt beim Beenden eine Kopie der Datenbank in
   <Sync-Ordner>/snapshots/. Jedes Gerät hat dort genau EINE eigene Datei
   (plutos-<Gerät>-<ID>.db), die nur dieses Gerät schreibt – dadurch entstehen
   mit Syncthing & Co. keine Konfliktkopien. Beim Start erkennt Plutos neuere
   Stände anderer Geräte und bietet an, sie zu laden. Die laufende Datenbank
   liegt immer lokal und wird nie direkt synchronisiert (SQLite-Dateien
   sollten nicht live über Sync-Dienste geteilt werden).
   Das ist KEIN Zusammenführen: Es gewinnt jeweils ein ganzer Stand. Vor dem
   Laden wird der lokale Stand gesichert.

2. INBOX – Einträge vom Handy (oder anderen Quellen) landen als kleine
   Textdateien in einem Ordner und werden von Plutos zu Buchungen gemacht.
   Unterstützt: .json (ein Objekt oder eine Liste), .txt/.csv (eine Buchung
   je Zeile: Betrag;Kategorie;Beschreibung;Tags;Datum – hinten darf alles
   fehlen). Verarbeitete Dateien wandern nach verarbeitet/, fehlerhafte nach
   fehler/ (mit einer .fehler.txt, die den Grund nennt).

Die geräteabhängige Einstellung (Sync-Ordner, Gerätename …) liegt bewusst in
einer eigenen Datei (sync.json im Datenordner) und NICHT in der Datenbank, damit
sie nicht von einem Snapshot eines anderen Geräts überschrieben wird."""
import datetime
import json
import os
import re
import shutil
import socket
import sqlite3
import time
import uuid
from pathlib import Path

# Einstellungen, die beim Laden eines fremden Snapshots lokal bleiben.
LOCAL_SETTING_KEYS = ("theme", "language")
SNAPSHOT_DIR = "snapshots"
INBOX_EXTENSIONS = (".json", ".txt", ".csv")
# Dateien jünger als so viele Sekunden werden übersprungen (evtl. noch im Transfer).
MIN_FILE_AGE_SECONDS = 2.0


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "geraet"


class SyncConfig:
    """Geräteabhängige Sync-Einstellungen (JSON-Datei außerhalb der Datenbank)."""

    def __init__(self, path):
        self.path = Path(path)
        data = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        self.sync_dir = data.get("sync_dir", "") or ""
        self.inbox_dir = data.get("inbox_dir", "") or ""
        self.device_id = data.get("device_id") or uuid.uuid4().hex
        self.device_name = data.get("device_name") or socket.gethostname() or "geraet"
        self.last_saved_at = data.get("last_saved_at", "") or ""
        self.loaded = dict(data.get("loaded", {}))     # Geräte-ID -> geladener Stand
        self.ignored = dict(data.get("ignored", {}))   # Geräte-ID -> ignorierter Stand
        self.auto_import_inbox = bool(data.get("auto_import_inbox", True))
        try:
            self.processed_keep_days = max(0, int(data.get("processed_keep_days", 14)))
        except (TypeError, ValueError):
            self.processed_keep_days = 14   # 0 = verarbeitete Dateien nie löschen
        if not data.get("device_id"):
            self.save()

    def save(self):
        data = {
            "sync_dir": self.sync_dir, "inbox_dir": self.inbox_dir,
            "device_id": self.device_id, "device_name": self.device_name,
            "last_saved_at": self.last_saved_at, "loaded": self.loaded,
            "ignored": self.ignored, "auto_import_inbox": self.auto_import_inbox,
            "processed_keep_days": self.processed_keep_days,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    @property
    def sync_enabled(self):
        return bool(self.sync_dir)

    def effective_inbox(self):
        """Inbox-Ordner: explizit gesetzt, sonst <Sync-Ordner>/inbox, sonst ''."""
        if self.inbox_dir:
            return self.inbox_dir
        if self.sync_dir:
            return str(Path(self.sync_dir) / "inbox")
        return ""


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

def snapshot_path(cfg):
    name = f"plutos-{_safe(cfg.device_name)}-{cfg.device_id[:8]}.db"
    return Path(cfg.sync_dir) / SNAPSHOT_DIR / name


def write_snapshot(cfg, store):
    """Schreibt (atomar) den aktuellen Stand als eigenen Snapshot dieses Geräts
    in den Sync-Ordner. Rückgabe: Pfad der Snapshot-Datei."""
    if not cfg.sync_enabled:
        raise ValueError("Kein Sync-Ordner eingestellt.")
    final = snapshot_path(cfg)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(final.name + ".plutos-tmp")
    if tmp.exists():
        tmp.unlink()
    store.conn.commit()
    saved_at = _now_utc()
    count = store.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    dst = sqlite3.connect(str(tmp))
    try:
        store.conn.backup(dst)
        dst.execute("CREATE TABLE IF NOT EXISTS sync_meta "
                    "(device_id TEXT, device_name TEXT, saved_at TEXT, tx_count INTEGER)")
        dst.execute("DELETE FROM sync_meta")
        dst.execute("INSERT INTO sync_meta VALUES (?, ?, ?, ?)",
                    (cfg.device_id, cfg.device_name, saved_at, count))
        dst.commit()
    finally:
        dst.close()
    os.replace(tmp, final)
    cfg.last_saved_at = saved_at
    cfg.save()
    return final


def _read_meta(path):
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = con.execute("SELECT device_id, device_name, saved_at, tx_count FROM sync_meta").fetchone()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    if not row:
        return None
    return {"path": Path(path), "device_id": row[0], "device_name": row[1],
            "saved_at": row[2], "tx_count": row[3]}


def list_remote_snapshots(cfg):
    """Snapshots ANDERER Geräte im Sync-Ordner, neueste zuerst."""
    if not cfg.sync_enabled:
        return []
    found = []
    for p in sorted((Path(cfg.sync_dir) / SNAPSHOT_DIR).glob("plutos-*.db")):
        meta = _read_meta(p)
        if meta and meta["device_id"] != cfg.device_id:
            found.append(meta)
    return sorted(found, key=lambda m: m["saved_at"], reverse=True)


def find_newer(cfg):
    """Snapshots anderer Geräte, die neuer sind als mein letzter eigener
    Stand bzw. als das, was ich von diesem Gerät zuletzt geladen habe, und die
    ich nicht ausdrücklich ignoriert habe."""
    newer = []
    for meta in list_remote_snapshots(cfg):
        dev = meta["device_id"]
        known = max(cfg.last_saved_at, cfg.loaded.get(dev, ""))
        if meta["saved_at"] > known and cfg.ignored.get(dev) != meta["saved_at"]:
            newer.append(meta)
    return newer


def ignore_snapshot(cfg, meta):
    cfg.ignored[meta["device_id"]] = meta["saved_at"]
    cfg.save()


def load_snapshot(cfg, store, meta, backup_dir):
    """Ersetzt den lokalen Stand durch den Snapshot. Vorher wird der lokale
    Stand nach backup_dir gesichert. Geräteabhängige Einstellungen
    (Design, Sprache) bleiben erhalten. Rückgabe: Pfad der Sicherung."""
    src_path = Path(meta["path"])
    check = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    try:
        ok = check.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        check.close()
    if ok != "ok":
        raise ValueError(f"Snapshot ist beschädigt ({ok}).")

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"vor-sync-{time.strftime('%Y%m%d-%H%M%S')}.db"
    bk = sqlite3.connect(str(backup))
    try:
        store.conn.backup(bk)
    finally:
        bk.close()

    keep = {}
    for key in LOCAL_SETTING_KEYS:
        row = store.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row:
            keep[key] = row[0]

    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    try:
        src.backup(store.conn)
    finally:
        src.close()
    store.conn.execute("DROP TABLE IF EXISTS sync_meta")
    for key, value in keep.items():
        store.set_setting(key, value)
    store._migrate_schema()
    store.conn.commit()

    cfg.loaded[meta["device_id"]] = meta["saved_at"]
    cfg.ignored.pop(meta["device_id"], None)
    cfg.save()
    return backup


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y")


def parse_amount(text):
    """'12,50', '-12.50', '1.234,56 €', '12,5€' → float. Wirft ValueError."""
    s = str(text).strip().replace("€", "").replace("EUR", "").replace(" ", "").replace(" ", "")
    if not s:
        raise ValueError("Betrag fehlt")
    neg = s.startswith("-") or s.startswith("−")
    s = s.lstrip("+-−")
    if "," in s and "." in s:
        # das letzte Trennzeichen ist das Dezimalzeichen
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    value = float(s)
    return -value if neg else value


def parse_date(text):
    s = str(text).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Datum nicht lesbar: {text}")


_KEYS = {
    "betrag": "amount", "amount": "amount",
    "kategorie": "category", "category": "category",
    "beschreibung": "description", "description": "description", "text": "description",
    "tags": "tags", "tag": "tags",
    "datum": "date", "date": "date",
    "id": "id", "art": "kind", "kind": "kind",
}


def _entry_from_dict(raw):
    entry = {}
    for k, v in raw.items():
        key = _KEYS.get(str(k).strip().lower())
        if key and v is not None:
            entry[key] = v
    return entry


def _entries_from_text(text):
    entries = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(";")]
        if parts[0].lower() in ("betrag", "amount"):
            continue   # Kopfzeile
        if len(parts) < 2:
            raise ValueError(f"Zeile braucht mindestens „Betrag;Kategorie“: {line!r}")
        entry = {"amount": parts[0], "category": parts[1]}
        if len(parts) > 2 and parts[2]:
            entry["description"] = parts[2]
        if len(parts) > 3 and parts[3]:
            entry["tags"] = parts[3]
        if len(parts) > 4 and parts[4]:
            entry["date"] = parts[4]
        entries.append(entry)
    return entries


def parse_inbox_file(path):
    """Liest eine Inbox-Datei und liefert eine Liste von Roh-Einträgen (dicts)."""
    text = Path(path).read_text(encoding="utf-8-sig")
    if Path(path).suffix.lower() == ".json":
        data = json.loads(text)
        items = data if isinstance(data, list) else [data]
        return [_entry_from_dict(i) for i in items if isinstance(i, dict)]
    return _entries_from_text(text)


def _resolve_entry(store, entry, default_date):
    """Prüft einen Roh-Eintrag und macht daraus Buchungsdaten; wirft ValueError."""
    if "amount" not in entry:
        raise ValueError("Betrag fehlt")
    amount = parse_amount(entry["amount"])
    name = str(entry.get("category", "")).strip()
    if not name:
        raise ValueError("Kategorie fehlt")
    cats = store.conn.execute("SELECT id, name, kind FROM categories").fetchall()
    match = next((c for c in cats if c["name"].strip().lower() == name.lower()), None)
    kind_hint = str(entry.get("kind", "")).strip().lower()
    if match is None:
        if kind_hint in ("ausgabe", "einnahme"):
            category_id = store.get_or_create_category(name, kind_hint, "•")["id"]
            kind = kind_hint
        else:
            raise ValueError(f"Kategorie „{name}“ unbekannt")
    else:
        category_id, kind = match["id"], match["kind"]
    amount = abs(amount) if kind == "einnahme" else -abs(amount)
    date = parse_date(entry["date"]) if entry.get("date") else default_date
    return {
        "date": date.isoformat(), "amount": round(amount, 2), "category_id": category_id,
        "description": str(entry.get("description", "")).strip(),
        "tags": entry.get("tags", ""), "id": str(entry["id"]).strip() if entry.get("id") else None,
    }


def _unique_target(folder, name):
    target = folder / name
    n = 1
    while target.exists():
        target = folder / f"{Path(name).stem}-{n}{Path(name).suffix}"
        n += 1
    return target


def cleanup_processed(inbox_dir, keep_days, now=None):
    """Löscht Dateien im Unterordner verarbeitet/, die älter als keep_days Tage
    sind (Alter = Änderungsdatum der Datei). keep_days 0 = nie löschen. Fasst
    nur verarbeitet/ an, nie die Inbox selbst oder fehler/. Gibt die Anzahl
    gelöschter Dateien zurück."""
    if not inbox_dir or keep_days <= 0:
        return 0
    folder = Path(inbox_dir) / "verarbeitet"
    if not folder.is_dir():
        return 0
    now = now if now is not None else time.time()
    limit = now - keep_days * 86400
    removed = 0
    for path in folder.iterdir():
        try:
            if path.is_file() and not path.is_symlink() and path.stat().st_mtime < limit:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def import_inbox(store, inbox_dir, now=None):
    """Importiert alle Dateien aus dem Inbox-Ordner.

    Rückgabe: {"imported": Anzahl Buchungen, "files": Anzahl Dateien,
               "errors": [(Dateiname, Grund), …]}.
    Eine Datei wird nur ganz oder gar nicht importiert. Entdeckt eine Datei
    einen Fehler, wandert sie samt Fehlertext nach fehler/."""
    result = {"imported": 0, "files": 0, "errors": []}
    inbox = Path(inbox_dir) if inbox_dir else None
    if not inbox or not inbox.is_dir():
        return result
    now = now if now is not None else time.time()
    store.conn.execute("CREATE TABLE IF NOT EXISTS inbox_imports (id TEXT PRIMARY KEY)")

    for path in sorted(inbox.iterdir()):
        if (not path.is_file() or path.name.startswith(".")
                or path.suffix.lower() not in INBOX_EXTENSIONS):
            continue
        if now - path.stat().st_mtime < MIN_FILE_AGE_SECONDS:
            continue   # evtl. noch im Transfer
        file_date = datetime.date.fromtimestamp(path.stat().st_mtime)
        try:
            raw_entries = parse_inbox_file(path)
            if not raw_entries:
                raise ValueError("Keine Buchung in der Datei gefunden")
            resolved = [_resolve_entry(store, e, file_date) for e in raw_entries]
        except (ValueError, OSError, UnicodeDecodeError) as exc:
            reason = str(exc) or exc.__class__.__name__
            result["errors"].append((path.name, reason))
            err_dir = inbox / "fehler"
            err_dir.mkdir(exist_ok=True)
            target = _unique_target(err_dir, path.name)
            shutil.move(str(path), target)
            target.with_name(target.name + ".fehler.txt").write_text(reason + "\n", encoding="utf-8")
            continue

        for r in resolved:
            if r["id"]:
                if store.conn.execute("SELECT 1 FROM inbox_imports WHERE id = ?", (r["id"],)).fetchone():
                    continue    # schon importiert (z. B. doppelt übertragen)
                store.conn.execute("INSERT INTO inbox_imports (id) VALUES (?)", (r["id"],))
            store.add_transaction(r["date"], r["amount"], r["category_id"], r["description"],
                                  tags=r["tags"])
            result["imported"] += 1
        store.conn.commit()
        done_dir = inbox / "verarbeitet"
        done_dir.mkdir(exist_ok=True)
        shutil.move(str(path), _unique_target(done_dir, path.name))
        result["files"] += 1
    return result


def format_saved_at(saved_at):
    """ISO-Zeitstempel (UTC) → lokale Anzeige „TT.MM.JJJJ HH:MM“."""
    try:
        dt = datetime.datetime.strptime(saved_at, "%Y-%m-%dT%H:%M:%S.%fZ")
        dt = dt.replace(tzinfo=datetime.timezone.utc).astimezone()
        return dt.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return saved_at


def describe_inbox_result(result, tr):
    """Meldungstext (Liste von Zeilen) zu einem import_inbox-Ergebnis."""
    lines = []
    if result["imported"]:
        lines.append(tr('{0} Buchung(en) aus {1} Datei(en) importiert.').format(
            result["imported"], result["files"]))
    if result["errors"]:
        detail = "; ".join(f"{name}: {reason}" for name, reason in result["errors"][:5])
        lines.append(tr('Fehlerhafte Dateien ({0}): {1} – sie liegen im Unterordner „fehler“.').format(
            len(result["errors"]), detail))
    return lines
