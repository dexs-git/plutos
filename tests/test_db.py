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
    assert L(99.99, 100) == "warn" and L(100, 100) == "full"
    assert L(100.004, 100) == "full" and L(100.01, 100) == "over"
    store.set_budget(food, "2026-05", 100.0)
    assert store.budget_status(food, "2026-05")["level"] == "ok"
    store.add_transaction("2026-05-10", -85.0, food, "x")
    st = store.budget_status(food, "2026-05")
    assert st["level"] == "warn" and st["spent"] == 85.0
    assert store.budget_status(food, "2026-04") is None   # vor dem ersten Budget
    assert store.budget_status(food, "2026-06")["limit"] == 100.0   # wird übernommen


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


def test_budget_inherited_until_changed_or_ended(store):
    rent = _cat(store, "Testmiete")
    store.set_budget(rent, "2026-03", 800.0)
    ov = {r["category_id"]: r for r in store.budget_overview("2026-05")}
    assert ov[rent]["limit_amount"] == 800.0 and ov[rent]["inherited_from"] == "2026-03"
    # Vor dem ersten Eintrag gilt noch nichts
    assert {r["category_id"]: r for r in store.budget_overview("2026-02")}[rent]["limit_amount"] is None
    # Änderung gilt ab diesem Monat weiter, frühere Monate bleiben unverändert
    store.set_budget(rent, "2026-06", 850.0)
    get = lambda m: {r["category_id"]: r for r in store.budget_overview(m)}[rent]
    assert get("2026-05")["limit_amount"] == 800.0
    assert get("2026-06")["limit_amount"] == 850.0 and get("2026-06")["inherited_from"] is None
    assert get("2026-09")["limit_amount"] == 850.0 and get("2026-09")["inherited_from"] == "2026-06"
    # Beenden wirkt nur nach vorn
    store.end_budget(rent, "2026-08")
    assert get("2026-07")["limit_amount"] == 850.0
    assert get("2026-08")["limit_amount"] is None and get("2026-10")["limit_amount"] is None
    assert store.budget_status(rent, "2026-10") is None
    # Danach lässt sich wieder ein Budget setzen
    store.set_budget(rent, "2026-11", 900.0)
    assert get("2026-12")["limit_amount"] == 900.0


def test_budget_year_summary(store):
    food = _cat(store, "Testessen")
    store.set_budget(food, "2026-01", 100.0)
    store.add_transaction("2026-01-10", -80.0, food, "")     # 20 drunter
    store.add_transaction("2026-02-10", -130.0, food, "")    # 30 drüber
    store.add_transaction("2026-03-10", -100.0, food, "")    # genau Budget = nicht drüber
    store.add_transaction("2026-04-10", -500.0, food, "")    # laufender Monat zählt nicht mit
    s = store.budget_year_summary(2026, today=datetime.date(2026, 4, 15))
    row = next(r for r in s["rows"] if r["category_id"] == food)
    assert s["complete_months"] == 3
    assert row["months_over"] == 1 and row["months_under"] == 2
    assert row["over_sum"] == 30.0 and row["under_sum"] == 20.0 and row["net"] == 10.0
    assert row["cells"][3]["complete"] is False and row["cells"][4] is None
    assert s["totals"]["net"] == 10.0


def test_tags_normalize_search_and_summary(store, tmp_path):
    fun = _cat(store, "Testspaß")
    assert store.normalize_tags(" #Urlaub, 2026 ;urlaub,, ") == "Urlaub,2026"
    t1 = store.add_transaction("2026-03-01", -50.0, fun, "Hotel", tags="Urlaub, #2026")
    store.add_transaction("2026-03-02", -20.0, fun, "Eis", tags="urlaub")
    store.add_transaction("2026-03-03", -10.0, fun, "Kino")
    rows, _ = store.search_transactions(tag="#URLAUB")
    assert {r["description"] for r in rows} == {"Hotel", "Eis"}
    rows, _ = store.search_transactions(text="#2026")
    assert [r["description"] for r in rows] == ["Hotel"]
    summary = {e["tag"].lower(): e for e in store.tag_summary(2026)}
    assert summary["urlaub"]["count"] == 2 and summary["urlaub"]["expense"] == 70.0
    assert summary["2026"]["count"] == 1
    assert [t.lower() for t in store.list_tags()] == ["2026", "urlaub"]
    # Bearbeiten: None lässt Tags stehen, "" entfernt sie
    store.update_transaction(t1, "2026-03-01", -50.0, fun, "Hotel")
    assert store.get_transaction(t1)["tags"] == "Urlaub,2026"
    store.update_transaction(t1, "2026-03-01", -50.0, fun, "Hotel", tags="")
    assert store.get_transaction(t1)["tags"] == ""
    # CSV-Rundlauf
    store.update_transaction(t1, "2026-03-01", -50.0, fun, "Hotel", tags="Urlaub")
    path = tmp_path / "x.csv"
    store.export_transactions_csv(path)
    assert path.read_text(encoding="utf-8").splitlines()[0].endswith("Tags")
    for r in store.list_transactions():
        store.delete_transaction(r["id"])
    store.import_transactions_csv(path)
    rows, _ = store.search_transactions(tag="urlaub")
    assert len(rows) == 2


def test_tags_column_migrates_old_database(tmp_path):
    for variant in ("gtk", "qt"):
        path = tmp_path / f"{variant}.db"
        s = _load(variant).FinanceStore(path)
        s.conn.execute("ALTER TABLE transactions DROP COLUMN tags")
        s.conn.commit()
        s.conn.close()
        s2 = _load(variant).FinanceStore(path)
        cols = {r["name"] for r in s2.conn.execute("PRAGMA table_info(transactions)")}
        assert "tags" in cols
        s2.conn.close()


def test_recurring_and_quick_template_tags(store):
    start = datetime.date.today().isoformat()
    food = _cat(store, "Testessen")
    tid = store.add_recurring_template(food, -20.0, "Abo", "monatlich", start,
                                       tags="Streaming, abo")
    assert store.get_recurring_template(tid)["tags"] == "Streaming,abo"
    gen = [r for r in store.list_transactions() if r["recurring_template_id"] == tid]
    assert gen and all(r["tags"] == "Streaming,abo" for r in gen)
    # Ändern ohne tags-Argument behält die Tags, mit Argument ersetzt sie
    store.update_recurring_template(tid, food, -25.0, "Abo", "monatlich", start)
    assert store.get_recurring_template(tid)["tags"] == "Streaming,abo"
    store.update_recurring_template(tid, food, -25.0, "Abo", "monatlich", start,
                                    apply_to_past=True, tags="Fix")
    gen = [r for r in store.list_transactions() if r["recurring_template_id"] == tid]
    assert gen and all(r["tags"] == "Fix" for r in gen)
    q = store.add_quick_template("Kaffee", food, -3.5, "Kaffee", tags="Auszeit")
    assert store.list_quick_templates()[0]["tags"] == "Auszeit"
    tx = store.book_quick_template(q, "2026-08-02")
    assert store.get_transaction(tx)["tags"] == "Auszeit"


def test_template_tags_columns_migrate(tmp_path):
    for variant in ("gtk", "qt"):
        path = tmp_path / f"{variant}2.db"
        s = _load(variant).FinanceStore(path)
        for tbl in ("recurring_templates", "quick_templates"):
            s.conn.execute(f"ALTER TABLE {tbl} DROP COLUMN tags")
        s.conn.commit()
        s.conn.close()
        s2 = _load(variant).FinanceStore(path)
        for tbl in ("recurring_templates", "quick_templates"):
            cols = {r["name"] for r in s2.conn.execute(f"PRAGMA table_info({tbl})")}
            assert "tags" in cols
        s2.conn.close()


def test_month_summary_and_pending(store):
    food, job = _cat(store, "Testessen"), _cat(store, "Testgehalt", "einnahme")
    store.set_budget(food, "2026-08", 100.0)
    store.add_transaction("2026-07-02", -100.0, food, "")
    store.add_transaction("2026-08-01", 1000.0, job, "")
    store.add_transaction("2026-08-05", -150.0, food, "")
    s = store.month_summary("2026-08")
    assert s["income"] == 1000.0 and s["expense"] == 150.0 and s["saved"] == 850.0
    assert abs(s["saving_rate"] - 0.85) < 1e-9
    assert abs(s["expense_change"] - 0.5) < 1e-9
    assert s["top_category"]["name"] == "Testessen" and s["top_category"]["share"] == 1.0
    assert s["budget_count"] == 1 and s["budgets_ok"] == 0
    assert s["budgets_over"][0]["over_by"] == 50.0
    today = datetime.date(2026, 9, 3)
    assert store.pending_month_summary(today)["month"] == "2026-08"
    store.dismiss_month_summary("2026-08")
    assert store.pending_month_summary(today) is None
    assert store.pending_month_summary(datetime.date(2027, 1, 3)) is None  # Dezember leer


def test_reminders(store):
    food, rent = _cat(store, "Testessen"), _cat(store, "Testmiete")
    today = datetime.date(2026, 10, 20)
    store.set_budget(food, "2026-10", 100.0)
    store.set_budget(rent, "2026-10", 800.0)
    store.add_transaction("2026-10-05", -85.0, food, "")     # 85 % -> warn
    store.add_transaction("2026-10-06", -900.0, rent, "")    # drüber
    g_soon = store.add_goal("Rad", 500.0, "2026-11-15")
    g_far = store.add_goal("Auto", 5000.0, "2027-12-01")
    g_late = store.add_goal("Alt", 300.0, "2026-10-01")
    store.add_recurring_template(rent, -50.0, "Streaming", "monatlich", "2026-10-23")
    items = store.reminders(today)
    kinds = [i["kind"] for i in items]
    assert kinds == ["budget", "budget", "goal", "goal", "recurring"]
    assert items[0]["level"] == "over" and items[1]["level"] == "warn"
    goals = {i["name"]: i for i in items if i["kind"] == "goal"}
    assert set(goals) == {"Rad", "Alt"} and goals["Alt"]["overdue"] and not goals["Rad"]["overdue"]
    assert items[-1]["text"] == "Streaming" and items[-1]["date"] == "2026-10-23"
    # erreichtes Ziel und fernes Zieldatum erzeugen keinen Hinweis
    store.update_goal_target(g_soon, 500.0)
    store.conn.execute("UPDATE savings_goals SET current_amount = 500 WHERE id = ?", (g_soon,))
    store.conn.commit()
    assert "Rad" not in {i["name"] for i in store.reminders(today) if i["kind"] == "goal"}


def test_recommendation_flags_open_goals(store):
    R = store.recommend_allocation_multi
    goal = {"id": 1, "name": "Notgroschen", "target_amount": 7800.0, "current_amount": 500.0}
    rec = R(2500.0, 1300.0, 237.8, 2189.53, [goal])
    assert not rec["all_goals_funded"] and rec["monthly_to_etf"] == 0 and rec["capital_to_etf"] == 0
    assert rec["monthly_available"] == 962.2
    assert rec["months_until_funded"] == 6    # (7300 - 2189,53) / 962,2
    done = dict(goal, current_amount=7800.0)
    rec2 = R(2500.0, 1300.0, 237.8, 0.0, [done])
    assert rec2["all_goals_funded"] and rec2["months_until_funded"] is None
    assert rec2["monthly_to_etf"] == 962.2


def test_budget_reminders_can_be_muted(store):
    rent, fun = _cat(store, "Testmiete"), _cat(store, "Testfreizeit")
    month = datetime.date.today().strftime("%Y-%m")
    day = datetime.date.today().isoformat()
    for cid in (rent, fun):
        store.set_budget(cid, month, 100.0)
        store.add_transaction(day, -100.0, cid, "x")
    names = {r["name"] for r in store.reminders() if r["kind"] == "budget"}
    assert {"Testmiete", "Testfreizeit"} <= names
    store.set_budget_reminder(rent, False)
    assert store.muted_budget_reminders() == {rent}
    names = {r["name"] for r in store.reminders() if r["kind"] == "budget"}
    assert "Testmiete" not in names and "Testfreizeit" in names
    store.set_budget_reminder(rent, True)
    assert store.muted_budget_reminders() == set()
