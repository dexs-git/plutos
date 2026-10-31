"""Tests für sync_tools.py (Snapshots über einen Sync-Ordner, Inbox-Import)."""
import importlib.util
import json
import os
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(variant, name):
    spec = importlib.util.spec_from_file_location(f"{name}_{variant}", ROOT / variant / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["gtk", "qt"])
def env(request, tmp_path):
    db = _load(request.param, "db")
    st = _load(request.param, "sync_tools")
    return db, st, tmp_path


def _store(db, path):
    return db.FinanceStore(path)


def test_sync_tools_files_identical():
    assert (ROOT / "gtk" / "sync_tools.py").read_text() == (ROOT / "qt" / "sync_tools.py").read_text()


def test_parse_amount_and_date(env):
    _, st, _ = env
    assert st.parse_amount("12,50") == 12.5
    assert st.parse_amount("-12.50") == -12.5
    assert st.parse_amount("1.234,56 €") == 1234.56
    assert st.parse_amount("1,234.56") == 1234.56
    assert st.parse_amount("1.234") == 1234.0 or st.parse_amount("1.234") == 1.234
    with pytest.raises(ValueError):
        st.parse_amount("abc")
    assert str(st.parse_date("28.10.2026")) == "2026-10-28"
    assert str(st.parse_date("2026-10-28")) == "2026-10-28"


def _old(path):
    t = time.time() - 60
    os.utime(path, (t, t))


def test_inbox_import_text_json_and_errors(env):
    db, st, tmp = env
    s = _store(db, tmp / "a.db")
    s.get_or_create_category("Lebensmittel", "ausgabe", "x")
    s.get_or_create_category("Gehalt", "einnahme", "x")
    inbox = tmp / "inbox"
    inbox.mkdir()
    (inbox / "a.txt").write_text("12,50;lebensmittel;Rewe;Wocheneinkauf, Bio;28.10.2026\n"
                                 "2500;Gehalt\n", encoding="utf-8")
    (inbox / "b.json").write_text(json.dumps(
        {"datum": "2026-10-27", "betrag": -3.2, "kategorie": "Lebensmittel", "id": "x1"}), encoding="utf-8")
    (inbox / "c.txt").write_text("5;Unbekannt\n", encoding="utf-8")
    (inbox / "d.json").write_text(json.dumps(
        {"betrag": 7, "kategorie": "Neu", "art": "ausgabe"}), encoding="utf-8")
    (inbox / "ignored.png").write_text("x")
    for p in inbox.iterdir():
        _old(p)
    (inbox / "frisch.txt").write_text("1;Lebensmittel\n")   # zu neu -> übersprungen

    res = st.import_inbox(s, inbox)
    assert res["imported"] == 4 and res["files"] == 3
    assert [e[0] for e in res["errors"]] == ["c.txt"]
    assert "unbekannt" in res["errors"][0][1]
    assert (inbox / "fehler" / "c.txt.fehler.txt").exists()
    assert (inbox / "verarbeitet" / "a.txt").exists() and (inbox / "frisch.txt").exists()

    rows = {(r["date"], r["description"]): r for r in s.list_transactions()}
    rewe = rows[("2026-10-28", "Rewe")]
    assert rewe["amount"] == -12.5 and rewe["tags"] == "Wocheneinkauf,Bio"
    assert any(r["amount"] == 2500.0 for r in s.list_transactions())   # Einnahme positiv
    assert any(r["amount"] == -7.0 and r["category_name"] == "Neu" for r in s.list_transactions())

    # dieselbe Datei mit gleicher id noch einmal -> keine Doppelbuchung
    (inbox / "b2.json").write_text(json.dumps(
        {"datum": "2026-10-27", "betrag": -3.2, "kategorie": "Lebensmittel", "id": "x1"}), encoding="utf-8")
    _old(inbox / "b2.json")
    before = len(s.list_transactions())
    st.import_inbox(s, inbox)
    assert len(s.list_transactions()) == before
    s.conn.close()


def test_snapshot_roundtrip_between_two_devices(env):
    db, st, tmp = env
    sync = tmp / "sync"
    a, b = _store(db, tmp / "a.db"), _store(db, tmp / "b.db")
    cfg_a = st.SyncConfig(tmp / "cfg_a.json"); cfg_a.sync_dir = str(sync); cfg_a.device_name = "Laptop"
    cfg_b = st.SyncConfig(tmp / "cfg_b.json"); cfg_b.sync_dir = str(sync); cfg_b.device_name = "Desktop"
    assert cfg_a.device_id != cfg_b.device_id

    cat = a.get_or_create_category("Testessen", "ausgabe", "x")["id"]
    a.add_transaction("2026-10-01", -9.99, cat, "Snapshot-Test")
    a.set_setting("theme", "dark")
    b.set_setting("theme", "light")
    assert st.find_newer(cfg_b) == []
    path = st.write_snapshot(cfg_a, a)
    assert path.exists() and not list(path.parent.glob("*.plutos-tmp"))

    assert st.find_newer(cfg_a) == []                  # eigener Snapshot zählt nicht
    newer = st.find_newer(cfg_b)
    assert len(newer) == 1 and newer[0]["device_name"] == "Laptop" and newer[0]["tx_count"] == 1

    backup = st.load_snapshot(cfg_b, b, newer[0], tmp / "backups")
    assert backup.exists()
    assert any(r["description"] == "Snapshot-Test" for r in b.list_transactions())
    assert b.get_setting("theme") == "light"            # geräteabhängig, bleibt lokal
    assert st.find_newer(cfg_b) == []                   # schon geladen

    # ignorieren
    a.add_transaction("2026-10-02", -1.0, cat, "später")
    st.write_snapshot(cfg_a, a)
    again = st.find_newer(cfg_b)
    assert len(again) == 1
    st.ignore_snapshot(cfg_b, again[0])
    assert st.find_newer(cfg_b) == []
    a.conn.close(); b.conn.close()


def test_cleanup_processed_only_old_files_in_verarbeitet(env):
    _db, sync_tools, tmp_path = env
    inbox = tmp_path / "inbox"
    done = inbox / "verarbeitet"
    err = inbox / "fehler"
    done.mkdir(parents=True)
    err.mkdir()
    old, new = done / "alt.txt", done / "neu.txt"
    keep_err, keep_inbox = err / "x.txt", inbox / "offen.txt"
    for p in (old, new, keep_err, keep_inbox):
        p.write_text("1;a")
    now = time.time()
    for p in (old, keep_err, keep_inbox):
        os.utime(p, (now - 40 * 86400, now - 40 * 86400))
    assert sync_tools.cleanup_processed(inbox, 0, now) == 0
    assert old.exists()
    assert sync_tools.cleanup_processed(inbox, 14, now) == 1
    assert not old.exists() and new.exists() and keep_err.exists() and keep_inbox.exists()
