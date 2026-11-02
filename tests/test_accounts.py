"""Tests: mehrere Konten, Umbuchungen, Jahresabschluss, ähnliche Buchungen."""
import json

import pytest

from test_db import store, _cat, _load  # noqa: F401  (Fixture 'store' für beide Varianten)


def test_default_account_and_unchanged_balance(store):
    assert [a["name"] for a in store.list_accounts()] == ["Girokonto"]
    food = _cat(store, "Essen")
    assert store.get_current_account_balance() is None
    store.set_starting_balance(1000.0, "2026-01-01")
    store.add_transaction("2026-01-05", -100.0, food, "x")
    assert store.get_current_account_balance(as_of_date="2026-12-31") == 900.0
    bd = store.get_balance_breakdown()
    assert bd["giro"] == 900.0 and bd["total"] == 900.0
    assert len(bd["accounts"]) == 1


def test_second_account_transfer_and_total(store):
    food = _cat(store, "Essen")
    giro = store.default_account_id()
    store.set_starting_balance(1000.0, "2026-01-01")
    tag = store.add_account("Tagesgeld", "💰", 500.0, "2026-01-01")
    cash = store.add_account("Bargeld", "👛", 0.0, "2026-01-01")
    store.add_transfer("2026-02-01", 200.0, giro, tag, "Sparen")
    store.add_transaction("2026-02-02", -20.0, food, "Markt", account_id=cash)
    store.add_transfer("2026-02-03", 50.0, giro, cash)
    asof = "2026-12-31"
    assert store.get_account_balance(giro, asof) == 750.0       # 1000 - 200 - 50
    assert store.get_account_balance(tag, asof) == 700.0        # 500 + 200
    assert store.get_account_balance(cash, asof) == 30.0        # 50 - 20
    # Umbuchungen sind keine Ausgaben: nur die 20 € Marktbuchung zählt
    expense = store.conn.execute(
        "SELECT COALESCE(SUM(-amount),0) FROM transactions WHERE amount < 0").fetchone()[0]
    assert expense == 20.0
    bd = store.get_balance_breakdown()
    assert [a["name"] for a in bd["accounts"]] == ["Girokonto", "Bargeld", "Tagesgeld"]


def test_default_account_booking_stored_as_null_and_update(store):
    food = _cat(store, "Essen")
    giro = store.default_account_id()
    tag = store.add_account("Tagesgeld")
    t1 = store.add_transaction("2026-03-01", -5.0, food, "a", account_id=giro)
    assert store.get_transaction(t1)["account_id"] is None
    store.update_transaction(t1, "2026-03-01", -5.0, food, "a", account_id=tag)
    assert store.get_transaction(t1)["account_id"] == tag
    store.update_transaction(t1, "2026-03-01", -6.0, food, "a")      # Konto bleibt
    assert store.get_transaction(t1)["account_id"] == tag
    store.update_transaction(t1, "2026-03-01", -6.0, food, "a", account_id=None)
    assert store.get_transaction(t1)["account_id"] is None


def test_account_rules(store):
    giro = store.default_account_id()
    tag = store.add_account("Tagesgeld")
    with pytest.raises(ValueError):
        store.add_account("tagesgeld")             # Name doppelt
    with pytest.raises(ValueError):
        store.add_account("  ")
    with pytest.raises(ValueError):
        store.delete_account(giro)
    with pytest.raises(ValueError):
        store.add_transfer("2026-01-01", 0, giro, tag)
    with pytest.raises(ValueError):
        store.add_transfer("2026-01-01", 5, giro, giro)
    tid = store.add_transfer("2026-01-01", 5, giro, tag)
    with pytest.raises(ValueError):
        store.delete_account(tag)                  # hat Umbuchung
    store.delete_transfer(tid)
    store.delete_account(tag)
    assert len(store.list_accounts()) == 1
    assert store.resolve_account_id("GIROKONTO") == giro
    assert store.resolve_account_id("gibtsnicht") is None


def test_backup_roundtrip_keeps_accounts(store, tmp_path):
    giro = store.default_account_id()
    tag = store.add_account("Tagesgeld", "💰", 10.0, "2026-01-01")
    store.add_transfer("2026-01-05", 3.0, giro, tag, "x")
    food = _cat(store, "Essen")
    store.add_transaction("2026-01-06", -1.0, food, "y", account_id=tag)
    path = tmp_path / "b.json"
    store.export_backup_json(path)
    data = json.loads(path.read_text())
    assert {a["name"] for a in data["accounts"]} == {"Girokonto", "Tagesgeld"}
    store.delete_transfer(store.list_transfers()[0]["id"])
    store.conn.execute("UPDATE transactions SET account_id = NULL")
    store.import_backup_json(path)
    assert len(store.list_transfers()) == 1
    assert store.conn.execute("SELECT COUNT(*) FROM transactions WHERE account_id IS NOT NULL").fetchone()[0] == 1
    # Ältere Backups ohne Konten lassen die vorhandenen Konten unangetastet
    del data["accounts"], data["transfers"]
    old = tmp_path / "old.json"
    old.write_text(json.dumps(data))
    store.import_backup_json(old)
    assert store.default_account_id() is not None
    assert len(store.list_accounts()) >= 1


def test_year_summary(store):
    food, rent, job = _cat(store, "Essen"), _cat(store, "Miete"), _cat(store, "Lohn", "einnahme")
    store.add_transaction("2025-01-10", -100.0, food, "a")
    store.add_transaction("2025-01-01", 1000.0, job, "gehalt")
    store.add_transaction("2026-01-10", -200.0, food, "b")
    store.add_transaction("2026-02-10", -600.0, rent, "m")
    store.add_transaction("2026-01-01", 2000.0, job, "gehalt")
    store.add_transaction("2026-02-01", 2000.0, job, "gehalt")
    s = store.year_summary(2026)
    assert s["income"] == 4000.0 and s["expense"] == 800.0 and s["saved"] == 3200.0
    assert s["saving_rate"] == pytest.approx(0.8)
    assert s["prev_expense"] == 100.0 and s["expense_change"] == pytest.approx(7.0)
    assert s["top_categories"][0]["name"] == "Miete"
    assert s["most_expensive_month"]["month"] == 2
    assert s["avg_monthly_expense"] == pytest.approx(400.0)
    assert store.year_summary(2024)["count"] == 0
    assert 2026 in store.list_years_with_transactions()


def test_pending_year_summary(store):
    import datetime
    food = _cat(store, "Essen")
    store.add_transaction("2025-06-01", -10.0, food, "a")
    assert store.pending_year_summary(datetime.date(2026, 1, 5))["year"] == 2025
    assert store.pending_year_summary(datetime.date(2026, 6, 1)) is None   # zu spät im Jahr
    store.dismiss_year_summary(2025)
    assert store.pending_year_summary(datetime.date(2026, 1, 5)) is None


def test_similar_transactions(store):
    food, fun = _cat(store, "Essen"), _cat(store, "Freizeit")
    a = store.add_transaction("2026-05-01", -12.5, food, "a")
    b = store.add_transaction("2026-05-01", -12.5, fun, "b")
    store.add_transaction("2026-05-02", -12.5, food, "anderer Tag")
    store.add_transaction("2026-05-01", -13.0, food, "anderer Betrag")
    assert [r["id"] for r in store.similar_transactions("2026-05-01", -12.5, exclude_id=a)] == [b]
    assert len(store.similar_transactions("2026-05-01", -12.5)) == 2
