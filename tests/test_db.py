"""Tests für die gemeinsame Datenlogik (db.py) beider Varianten.

Ausführen:  python -m pytest tests -q
Getestet werden gtk/db.py und qt/db.py mit identischen Szenarien. Es wird
nie die echte Datenbank des Nutzers verwendet (temporäre Datei je Test)."""
import datetime
import importlib.util
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(variant):
    spec = importlib.util.spec_from_file_location(f"db_{variant}", ROOT / variant / "db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["gtk", "qt"])
def store(request, tmp_path):
    module = _load(request.param)
    s = module.FinanceStore(tmp_path / "test.db")
    yield s
    s.conn.close()


def _cat(store, name, kind="ausgabe"):
    row = store.get_or_create_category(name, kind, "•")
    return row["id"] if hasattr(row, "keys") else row


def test_category_comparison_pct_and_new(store):
    food, fun = _cat(store, "Testessen"), _cat(store, "Testspaß")
    store.add_transaction("2026-03-05", -100.0, food, "a")
    store.add_transaction("2026-04-05", -150.0, food, "b")
    store.add_transaction("2026-04-06", -40.0, fun, "c")  # nur im aktuellen Monat
    rows = {r["name"]: r for r in store.category_comparison("2026-04", "2026-03")}
    assert rows["Testessen"]["diff"] == 50.0
    assert rows["Testessen"]["pct"] == pytest.approx(50.0)
    assert rows["Testspaß"]["previous"] == 0.0
    assert rows["Testspaß"]["pct"] is None  # "neu", keine Division durch 0


def test_category_year_series(store):
    food = _cat(store, "Testessen")
    store.add_transaction("2026-01-10", -20.0, food, "a")
    store.add_transaction("2026-01-20", -30.0, food, "b")
    store.add_transaction("2026-12-01", -5.0, food, "c")
    store.add_transaction("2025-12-01", -999.0, food, "anderes Jahr")
    series = store.category_year_series(2026, "Testessen")
    assert len(series) == 12
    assert series[0] == 50.0 and series[11] == 5.0 and sum(series) == 55.0
    assert sum(store.category_year_series(2026)) >= 55.0  # "alle Ausgaben"
    assert "Testessen" in [r["category_name"] for r in store.expense_categories_in_year(2026)]


def test_income_not_counted_as_expense(store):
    job = _cat(store, "Testgehalt", "einnahme")
    store.add_transaction("2026-05-01", 2000.0, job, "Gehalt")
    names = [r["name"] for r in store.category_comparison("2026-05", "2026-04")]
    assert "Testgehalt" not in names


def test_db_backup_daily_limit_and_pruning(store):
    first = store.create_db_backup()
    assert first is not None and first.exists()
    assert store.create_db_backup() is None            # heute schon gesichert
    assert store.create_db_backup(force=True).exists()  # manuell geht immer
    # Backup ist eine gültige, lesbare Datenbank mit den Kategorien
    con = sqlite3.connect(str(first))
    assert con.execute("SELECT COUNT(*) FROM categories").fetchone()[0] > 0
    con.close()
    # Alte Backups werden entfernt
    for i in range(30):
        (store.backup_dir / f"finanzen-2020010{i % 9 + 1}-0000{i:02d}.db").write_bytes(b"x")
    store.create_db_backup(force=True)
    assert len(list(store.backup_dir.glob("finanzen-*.db"))) <= store.BACKUP_KEEP


def _write_csv(path, rows, header="Buchungstag;Betrag;Zahlungsempfänger;Verwendungszweck"):
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def test_csv_import_keywords_duplicates_and_signs(store, tmp_path):
    f = tmp_path / "konto.csv"
    _write_csv(f, [
        "02.03.2026;-45,30;REWE Markt;Einkauf",
        "03.03.2026;-3,50;Café Blau;Kaffee",
        "03.03.2026;-3,50;Café Blau;Kaffee",   # echte zweite Zeile, kein Duplikat
        "01.03.2026;2.500,00;Firma GmbH;Gehalt März",
        "04.03.2026;-12,00;Unbekannt;Irgendwas",
    ])
    first = store.import_transactions_csv(str(f))
    assert first["imported"] == 5 and first["duplicates"] == 0
    cats = {r["description"]: r["category_name"] for r in store.conn.execute(
        "SELECT t.description, c.name AS category_name FROM transactions t "
        "JOIN categories c ON t.category_id = c.id")}
    assert cats["REWE Markt – Einkauf"] == "Lebensmittel"
    assert cats["Firma GmbH – Gehalt März"] == "Gehalt"
    assert cats["Unbekannt – Irgendwas"] == "Sonstige Ausgaben"
    amounts = [r[0] for r in store.conn.execute("SELECT amount FROM transactions WHERE description LIKE 'REWE%'")]
    assert amounts == [-45.30]
    # Derselbe Kontoauszug nochmal: nichts wird doppelt angelegt
    second = store.import_transactions_csv(str(f))
    assert second["imported"] == 0 and second["duplicates"] == 5
    assert store.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 5


def test_search_transactions_filters(store):
    food, fun = _cat(store, "Testessen"), _cat(store, "Testspaß")
    job = _cat(store, "Testgehalt", "einnahme")
    store.add_transaction("2026-01-05", -12.50, food, "Pizza Mario")
    store.add_transaction("2026-02-05", -80.00, food, "Wocheneinkauf")
    store.add_transaction("2026-02-07", -25.00, fun, "Kino")
    store.add_transaction("2026-02-01", 2000.00, job, "Gehalt")
    far = (datetime.date.today() + datetime.timedelta(days=400)).isoformat()
    store.add_transaction(far, -9.99, fun, "Zukunfts-Abo")

    def names(**kw):
        rows, _ = store.search_transactions(**kw)
        return {r["description"] for r in rows}

    assert names(text="PIZZA") == {"Pizza Mario"}                   # ohne Groß-/Kleinschreibung
    assert names(text="testessen") == {"Pizza Mario", "Wocheneinkauf"}  # Kategoriename zählt
    assert names(kind="einnahme") == {"Gehalt"}
    assert names(category_id=fun) == {"Kino"}                         # Zukunft standardmäßig aus
    assert names(category_id=fun, include_future=True) == {"Kino", "Zukunfts-Abo"}
    assert names(date_from="2026-02-01", date_to="2026-02-06") == {"Wocheneinkauf", "Gehalt"}
    assert names(min_amount=20, max_amount=100, kind="ausgabe") == {"Wocheneinkauf", "Kino"}
    assert names(min_amount=12.50, max_amount=12.50) == {"Pizza Mario"}  # Grenzen inklusive
    rows, truncated = store.search_transactions(limit=2)
    assert len(rows) == 2 and truncated
    assert rows[0]["date"] >= rows[1]["date"]                          # neueste zuerst


def test_undo_delete_transaction(store):
    food = _cat(store, "Testessen")
    tx = store.add_transaction("2026-03-05", -12.5, food, "Pizza")
    assert not store.can_undo_delete()
    store.delete_transaction(tx)
    assert store.get_transaction(tx) is None and store.can_undo_delete()
    restored = store.undo_delete_transaction()
    assert restored["description"] == "Pizza"
    back = store.get_transaction(tx)
    assert back["amount"] == -12.5 and back["date"] == "2026-03-05"
    assert not store.can_undo_delete() and store.undo_delete_transaction() is None


def test_quick_templates(store):
    fuel = _cat(store, "Testtanken")
    qid = store.add_quick_template("Tanken", fuel, -60.0, "Volltanken")
    templates = store.list_quick_templates()
    assert [t["name"] for t in templates] == ["Tanken"]
    tx = store.book_quick_template(qid, "2026-04-02")
    booked = store.get_transaction(tx)
    assert booked["amount"] == -60.0 and booked["description"] == "Volltanken"
    assert booked["date"] == "2026-04-02"
    store.delete_quick_template(qid)
    assert store.list_quick_templates() == []


def test_budget_levels(store):
    food = _cat(store, "Testessen")
    L = store.budget_level
    assert L(10, None) == "none" and L(10, 0) == "none"
    assert L(79.9, 100) == "ok" and L(80, 100) == "warn"
    assert L(99.99, 100) == "warn" and L(100, 100) == "over"
    store.set_budget(food, "2026-05", 100.0)
    assert store.budget_status(food, "2026-05")["level"] == "ok"
    store.add_transaction("2026-05-10", -85.0, food, "x")
    st = store.budget_status(food, "2026-05")
    assert st["level"] == "warn" and st["spent"] == 85.0
    assert store.budget_status(food, "2026-06") is None   # kein Budget gesetzt


def test_json_backup_roundtrip_keeps_settings_and_templates(store, tmp_path):
    food = _cat(store, "Testessen")
    store.set_starting_balance(1234.5, "2026-01-01")
    store.add_quick_template("Brot", food, -3.2, "")
    path = tmp_path / "b.json"
    store.export_backup_json(str(path))
    store.set_starting_balance(1.0, "2026-02-01")
    store.delete_quick_template(store.list_quick_templates()[0]["id"])
    store.import_backup_json(str(path))
    assert store.get_starting_balance() is not None
    assert [t["name"] for t in store.list_quick_templates()] == ["Brot"]
    assert store.get_current_account_balance(as_of_date=datetime.date(2026, 1, 1)) == 1234.5


def test_year_comparison_and_category_years(store):
    food, fun = _cat(store, "Testessen"), _cat(store, "Testspaß")
    job = _cat(store, "Testgehalt", "einnahme")
    store.add_transaction("2025-03-01", -100.0, food, "a")
    store.add_transaction("2025-03-02", 1000.0, job, "g")
    store.add_transaction("2026-03-01", -150.0, food, "b")
    store.add_transaction("2026-07-01", -30.0, fun, "c")
    store.add_transaction("2026-03-02", 1200.0, job, "g")
    result = store.year_comparison(2026)
    march = result["months"][2]
    assert march["expense"] == 150.0 and march["prev_expense"] == 100.0
    assert march["income"] == 1200.0 and march["prev_income"] == 1000.0
    t = result["totals"]
    assert t["expense"] == 180.0 and t["prev_expense"] == 100.0
    assert t["saved"] == 1020.0 and t["prev_saved"] == 900.0
    rows = {r["name"]: r for r in store.category_comparison("2026", "2025")}
    assert rows["Testessen"]["diff"] == 50.0 and rows["Testessen"]["pct"] == pytest.approx(50.0)
    assert rows["Testspaß"]["pct"] is None            # Vorjahr 0 -> "neu"


@pytest.mark.parametrize("vorab", [False, True])
def test_etf_scenarios(store, vorab):
    kw = dict(monthly_amount=200.0, annual_return_percent=6.0, duration_years=20,
              use_vorabpauschale=vorab)
    low, mid, high = store.etf_scenarios(spread_percent=2.0, inflation_percent=2.0, **kw)
    assert [s["label"] for s in (low, mid, high)] == ["Pessimistisch", "Erwartet", "Optimistisch"]
    assert (low["annual_return"], mid["annual_return"], high["annual_return"]) == (4.0, 6.0, 8.0)
    assert low["invested"] == mid["invested"] == high["invested"] == 48000.0
    assert low["value"] < mid["value"] < high["value"]
    assert low["value_after_tax"] < mid["value_after_tax"] < high["value_after_tax"]
    assert mid["value_after_tax"] <= mid["value"]                     # Steuer kürzt nur
    assert mid["real_value_after_tax"] < mid["value_after_tax"]      # Inflation zehrt
    flat = store.etf_scenarios(spread_percent=0.0, inflation_percent=0.0, **kw)
    assert flat[0]["value"] == flat[1]["value"] == flat[2]["value"]
    assert flat[1]["real_value_after_tax"] == flat[1]["value_after_tax"]


def test_notgroschen_pocket_breakdown(store):
    assert store.get_balance_breakdown() is None
    store.set_starting_balance(1000.0, "2020-01-01")
    gid = store.add_goal("Notgroschen", 3000.0, None)
    gid = gid if isinstance(gid, int) else store.get_goal_by_name("Notgroschen")["id"]
    store.add_contribution(gid, "2026-01-01", 500.0)
    # Unterkonto aus: nur Girokonto
    assert store.get_balance_breakdown()["pocket"] == 0.0
    store.set_notgroschen_pocket(True)
    bd = store.get_balance_breakdown()
    assert bd["giro"] == 1000.0 and bd["pocket"] == 500.0 and bd["total"] == 1500.0
    # gebuchter Sparbeitrag senkt das Girokonto, Gesamt bleibt konsistent
    store.add_contribution(gid, "2026-01-02", 200.0, create_transaction=True, goal_name="Notgroschen")
    bd = store.get_balance_breakdown()
    assert bd["giro"] == 800.0 and bd["pocket"] == 700.0 and bd["total"] == 1500.0


def test_dashboard_data(store):
    today = datetime.date(2026, 10, 21)
    food, job = _cat(store, "Testessen"), _cat(store, "Testjob", "einnahme")
    store.add_transaction("2026-07-05", -300.0, food, "a")
    store.add_transaction("2026-08-05", -200.0, food, "b")
    store.add_transaction("2026-10-02", 2000.0, job, "Gehalt")
    store.add_transaction("2026-10-10", -120.0, food, "c")
    store.add_transaction("2026-10-28", -80.0, food, "geplant")  # in der Zukunft
    d = store.dashboard_data(today)
    assert d["day"] == 21 and d["days_in_month"] == 31
    assert d["income_sofar"] == 2000.0 and d["expense_sofar"] == 120.0
    assert d["expense_planned"] == 200.0
    # ohne Budget: Durchschnitt der Vormonate mit Ausgaben (Juli 300, August 200, September keine)
    assert d["baseline_kind"] == "average" and d["baseline"] == 250.0
    store.set_budget(food, "2026-10", 400.0)
    d = store.dashboard_data(today)
    assert d["baseline_kind"] == "budget" and d["baseline"] == 400.0
    assert d["top_budgets"][0]["name"] == "Testessen" and d["top_budgets"][0]["spent"] == 200.0
    assert d["recent"][0]["description"] == "c" and len(d["recent"]) <= 6
    assert len(d["trend"]) == 6 and d["balance"] is None
