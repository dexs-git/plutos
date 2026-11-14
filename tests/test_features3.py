"""Tests: Kategorie-Regeln, Cashflow-Vorschau, Monte-Carlo-Streuung, Berichtsdaten."""
import datetime

import pytest

from test_db import store, _cat, _load  # noqa: F401


# -- Kategorie-Regeln -------------------------------------------------------------

def test_rules_suggest_longest_keyword_and_case_insensitive(store):
    food = _cat(store, "Lebensmittel")
    drug = _cat(store, "Drogerie")
    store.add_category_rule("rewe", food)
    store.add_category_rule("rewe drogerie", drug)
    assert store.suggest_category("Einkauf REWE Markt")["id"] == food
    assert store.suggest_category("REWE Drogerie Müller")["id"] == drug   # längster Begriff gewinnt
    assert store.suggest_category("Tankstelle") is None
    assert store.suggest_category("") is None and store.suggest_category(None) is None


def test_rules_validation_update_delete(store):
    food = _cat(store, "Lebensmittel")
    other = _cat(store, "Sonstiges")
    rid = store.add_category_rule(" Aldi ", food)
    with pytest.raises(ValueError):
        store.add_category_rule("ALDI", other)          # Duplikat, egal wie geschrieben
    with pytest.raises(ValueError):
        store.add_category_rule("  ", food)
    with pytest.raises(ValueError):
        store.add_category_rule("x", 99999)
    store.update_category_rule(rid, "aldi süd", other)
    assert store.suggest_category("Aldi Süd")["id"] == other
    rows = store.list_category_rules()
    assert [r["keyword"] for r in rows] == ["aldi süd"] and rows[0]["category_name"] == "Sonstiges"
    store.delete_category_rule(rid)
    assert store.list_category_rules() == []


def test_rules_in_backup_roundtrip(store, tmp_path):
    food = _cat(store, "Lebensmittel")
    store.add_category_rule("rewe", food)
    path = tmp_path / "b.json"
    store.export_backup_json(str(path))
    store.delete_category_rule(store.list_category_rules()[0]["id"])
    store.import_backup_json(str(path))
    assert [r["keyword"] for r in store.list_category_rules()] == ["rewe"]
    assert store.suggest_category("REWE")["name"] == "Lebensmittel"


# -- Cashflow ---------------------------------------------------------------------

def _forecast_setup(store):
    store.set_starting_balance(1000.0, "2026-01-01")
    rent = _cat(store, "Miete")
    pay = _cat(store, "Gehalt", "einnahme")
    food = _cat(store, "Essen")
    store.add_recurring_template(rent, -500.0, "Miete", "monatlich", "2026-11-01")
    store.add_recurring_template(pay, 2000.0, "Gehalt", "monatlich", "2026-11-28")
    for m in ("2026-08", "2026-09", "2026-10"):
        store.add_transaction(f"{m}-15", -300.0, food, "Alltag")
    return food


def test_cashflow_forecast_with_and_without_estimate(store):
    _forecast_setup(store)
    today = datetime.date(2026, 11, 10)
    start = store.get_balance_breakdown()["total"]
    # Ohne Schätzung: nur bekannte Buchungen
    fc = store.cashflow_forecast(3, today=today, include_estimate=False)
    assert fc["start_balance"] == pytest.approx(start)
    assert [m["month"] for m in fc["months"]] == ["2026-11", "2026-12", "2027-01", "2027-02"]
    nov = fc["months"][0]
    assert nov["recurring_in"] == 2000.0 and nov["recurring_out"] == 0.0   # Miete 1.11. liegt vor heute
    assert nov["balance"] == pytest.approx(start + 2000.0)
    dec = fc["months"][1]
    assert dec["net"] == 1500.0 and dec["balance"] == pytest.approx(start + 3500.0)
    # Mit Schätzung: Durchschnitt Alltag = 300 € Ausgaben pro Monat
    fc2 = store.cashflow_forecast(3, today=today, include_estimate=True)
    assert fc2["months_used"] == 3 and fc2["avg_out"] == 300.0 and fc2["avg_in"] == 0.0
    assert fc2["months"][1]["est_out"] == 300.0
    assert fc2["months"][1]["net"] == 1200.0
    assert fc2["lowest"]["balance"] == min(m["balance"] for m in fc2["months"])
    assert fc2["first_negative"] is None


def test_cashflow_estimate_does_not_double_count_known_one_offs(store):
    food = _forecast_setup(store)
    today = datetime.date(2026, 11, 10)
    store.add_transaction("2026-12-20", -120.0, food, "schon geplant")
    fc = store.cashflow_forecast(2, today=today)
    dec = fc["months"][1]
    assert dec["other_out"] == 120.0 and dec["est_out"] == 180.0     # 300 Durchschnitt - 120 bekannt


def test_cashflow_first_negative_and_none_without_start(store):
    food = _cat(store, "Essen")
    assert store.cashflow_forecast(3, today=datetime.date(2026, 11, 10)) is None
    store.set_starting_balance(100.0, "2026-01-01")
    rent = _cat(store, "Miete")
    store.add_recurring_template(rent, -80.0, "Miete", "monatlich", "2026-11-15")
    fc = store.cashflow_forecast(4, today=datetime.date(2026, 11, 10), include_estimate=False)
    assert fc["first_negative"] == "2026-12"
    assert fc["lowest"]["month"] == fc["months"][-1]["month"]


# -- Monte-Carlo --------------------------------------------------------------------

def test_monte_carlo_zero_volatility_equals_deterministic_line(store):
    F = type(store)
    det = F.project_etf_plan(200, 6.0, 10)
    mc = F.etf_monte_carlo(200, 6.0, 0.0, 10, runs=20)
    assert mc["p50"] == pytest.approx([r["value"] for r in det], abs=0.02)
    assert mc["p10"] == mc["p50"] == mc["p90"]
    assert mc["invested"][-1] == det[-1]["invested"]
    assert mc["loss_probability"] == 0.0


def test_monte_carlo_band_order_deterministic_and_loss_probability(store):
    F = type(store)
    a = F.etf_monte_carlo(200, 6.0, 15.0, 15, runs=300)
    b = F.etf_monte_carlo(200, 6.0, 15.0, 15, runs=300)
    assert a == b                                                  # feste Startzahl
    assert all(lo <= mid <= hi for lo, mid, hi in zip(a["p10"], a["p50"], a["p90"]))
    assert a["p10"][-1] < a["p50"][-1] < a["p90"][-1]
    f = a["final"]
    assert f["p10"]["real_value_after_tax"] < f["p10"]["value_after_tax"] <= f["p10"]["value"]
    assert 0.0 <= a["loss_probability"] < 0.5
    risky = F.etf_monte_carlo(200, 1.0, 30.0, 3, runs=300)         # kurz, riskant, wenig Rendite
    assert risky["loss_probability"] > a["loss_probability"]
    assert len(a["years"]) == 15 == len(a["invested"])


def test_monte_carlo_increase_and_cap(store):
    F = type(store)
    flat = F.etf_monte_carlo(100, 5.0, 0.0, 4, runs=10)
    grow = F.etf_monte_carlo(100, 5.0, 0.0, 4, annual_increase_percent=10, max_monthly_amount=110, runs=10)
    assert flat["invested"] == [1200.0, 2400.0, 3600.0, 4800.0]
    assert grow["invested"] == [1200.0, 2520.0, 3840.0, 5160.0]     # 100, 110, 110, 110 €/Monat


# -- Berichtsdaten ----------------------------------------------------------------

def test_month_report_data(store):
    food, rent = _cat(store, "Essen"), _cat(store, "Miete")
    pay = _cat(store, "Gehalt", "einnahme")
    store.set_starting_balance(1000.0, "2026-01-01")
    store.add_transaction("2026-10-01", 2000.0, pay, "Gehalt")
    store.add_transaction("2026-10-02", -600.0, rent, "Miete")
    store.add_transaction("2026-10-05", -80.0, food, "REWE")
    store.add_transaction("2026-11-02", -50.0, food, "später")
    store.set_budget(food, "2026-10", 100.0) if hasattr(store, "set_budget") else None
    data = store.month_report_data("2026-10")
    assert data["summary"]["income"] == 2000.0 and data["summary"]["expense"] == 680.0
    assert [r["category_name"] for r in data["spending"]] == ["Miete", "Essen"]
    assert data["income"][0]["category_name"] == "Gehalt"
    assert data["biggest"][0]["amount"] == -600.0 and len(data["biggest"]) == 2
    assert data["balance_end"] == pytest.approx(1000.0 + 2000.0 - 680.0)   # ohne die Novemberbuchung


# -- PDF-Bericht ------------------------------------------------------------------

def _load_report(variant):
    import importlib.util
    from test_db import ROOT
    spec = importlib.util.spec_from_file_location(f"rp_{variant}", ROOT / variant / "report_pdf.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
          "Oktober", "November", "Dezember"]


def _fmt(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


@pytest.mark.parametrize("variant", ["gtk", "qt"])
def test_month_report_pdf_is_valid_and_paginates(store, tmp_path, variant):
    rp = _load_report(variant)
    pay = _cat(store, "Gehalt", "einnahme")
    store.set_starting_balance(500.0, "2026-01-01")
    store.add_transaction("2026-10-01", 2000.0, pay, "Gehalt")
    big = _cat(store, "Auto")
    store.add_transaction("2026-10-03", -999.0, big, "Reparatur (Auto) \\ 😀")  # Klammern, Backslash, Emoji
    for i in range(40):
        cid = _cat(store, f"Kategorie {i}")
        store.add_transaction("2026-10-02", -10.0 - i, cid, f"Eintrag {i}")
        store.set_budget(cid, "2026-10", 20.0) if hasattr(store, "set_budget") else None
    out = tmp_path / "bericht.pdf"
    rp.build_month_report(store.month_report_data("2026-10"), str(out), lambda x: x, _fmt, MONTHS,
                          today=datetime.date(2026, 11, 2))
    raw = out.read_bytes()
    assert raw.startswith(b"%PDF-1.4") and raw.rstrip().endswith(b"%%EOF")
    assert raw.count(b"/Type /Page ") >= 2                       # mehrere Seiten
    startxref = int(raw.rsplit(b"startxref", 1)[1].split()[0])
    assert raw[startxref:startxref + 4] == b"xref"               # Verweistabelle stimmt
    assert b"Oktober 2026" in raw and b"\\(Auto\\)" in raw     # Klammern maskiert


@pytest.mark.parametrize("variant", ["gtk", "qt"])
def test_pdf_text_helpers(variant):
    rp = _load_report(variant)
    assert rp.clean("Kaffee ☕ 3€") == "Kaffee  3€"
    assert rp.text_width("iii", 10) < rp.text_width("WWW", 10)
    short = rp.fit_text("Ein sehr langer Beschreibungstext der nicht passt", 10, 80)
    assert short.endswith("...") and rp.text_width(short, 10) <= 80
    assert rp.fit_text("kurz", 10, 80) == "kurz"


# -- Regeln im Inbox-Import -------------------------------------------------------

def _load_sync(variant):
    import importlib.util
    from test_db import ROOT
    spec = importlib.util.spec_from_file_location(f"st_{variant}", ROOT / variant / "sync_tools.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inbox_uses_rules_for_empty_category(store, tmp_path):
    import os
    import time
    st = _load_sync("gtk" if "gtk" in type(store).__module__ else "qt")
    food = _cat(store, "Lebensmittel")
    store.add_category_rule("rewe", food)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    old = time.time() - 60
    (inbox / "a.txt").write_text("12,50;;REWE Markt\n7;?;rewe Brötchen\n", encoding="utf-8")
    (inbox / "b.txt").write_text("5;;Unbekannter Laden\n", encoding="utf-8")
    (inbox / "c.json").write_text('[{"amount": "3,20", "description": "Rewe Pfand"}]', encoding="utf-8")
    for f in inbox.iterdir():
        os.utime(f, (old, old))
    res = st.import_inbox(store, str(inbox))
    assert res["imported"] == 3 and res["files"] == 2
    assert [e[0] for e in res["errors"]] == ["b.txt"]
    assert "keine Regel" in res["errors"][0][1] and "Unbekannter Laden" in res["errors"][0][1]
    rows = store.conn.execute("SELECT amount, category_id FROM transactions ORDER BY amount").fetchall()
    assert {r["category_id"] for r in rows} == {food} and sorted(r["amount"] for r in rows) == [-12.5, -7.0, -3.2]


def test_delete_category_removes_its_rules(store):
    food = _cat(store, "Lebensmittel")
    store.add_category_rule("rewe", food)
    store.delete_category(food)
    assert store.list_category_rules() == []
    assert store.conn.execute("SELECT COUNT(*) FROM category_rules").fetchone()[0] == 0


# -- Zahltag ------------------------------------------------------------------------

def _payday_setup(store):
    store.set_starting_balance(1000.0, "2026-01-01")
    rent = _cat(store, "Miete")
    pay = _cat(store, "Gehalt", "einnahme")
    food = _cat(store, "Essen")
    store.add_transaction("2026-10-22", -150.0, food, "Alltag")      # genau 30 Tage vor dem 20.11.
    store.add_transaction("2026-11-10", -150.0, food, "Alltag")
    store.add_transaction("2026-11-15", 2000.0, pay, "Gehalt")
    store.add_recurring_template(rent, -500.0, "Miete", "monatlich", "2026-12-01")
    store.add_transaction("2026-12-10", 50.0, pay, "Erstattung")       # künftige Einnahme zählt nicht
    store.set_payday(15)
    store.set_payday_buffer(100.0)


def test_payday_cycle_numbers(store):
    _payday_setup(store)
    pc = store.payday_cycle(today=datetime.date(2026, 11, 20))
    assert pc["prev_payday"] == datetime.date(2026, 11, 15) and pc["next_payday"] == datetime.date(2026, 12, 15)
    assert pc["days_left"] == 25 and pc["cycle_day"] == 6 and pc["cycle_days"] == 30
    assert pc["balance"] == 2700.0                      # 1000 - 300 + 2000
    assert pc["known_out"] == 500.0                     # Miete am 1.12.; Gehalt/Erstattung zählen nicht
    assert pc["avg_daily"] == 10.0 and pc["est_variable"] == 250.0   # 300 € in 30 Tagen
    assert pc["projected_leftover"] == 1950.0 and pc["suggestion"] == 1850.0
    assert pc["daily_allowance"] == 84.0 and pc["on_track"] is True
    assert pc["cycle_expense"] == 0.0                   # seit 15.11. nichts ausgegeben


def test_payday_before_and_on_payday_and_one_offs(store):
    _payday_setup(store)
    food = _cat(store, "Essen")
    store.add_transaction("2026-12-05", -100.0, food, "Geplant")       # bekannte einmalige Ausgabe
    pc = store.payday_cycle(today=datetime.date(2026, 11, 20))
    assert pc["known_out"] == 600.0 and pc["est_variable"] == 150.0    # 250 - 100 schon eingeplant
    # am Zahltag selbst beginnt der neue Zyklus
    on = store.payday_cycle(today=datetime.date(2026, 11, 15))
    assert on["prev_payday"] == datetime.date(2026, 11, 15) and on["days_left"] == 30
    # vor dem Zahltag des Monats gehört der Tag noch zum alten Zyklus
    early = store.payday_cycle(today=datetime.date(2026, 11, 3))
    assert early["next_payday"] == datetime.date(2026, 11, 15) and early["prev_payday"] == datetime.date(2026, 10, 15)


def test_payday_tight_and_disabled(store):
    _payday_setup(store)
    store.set_payday_buffer(5000.0)
    pc = store.payday_cycle(today=datetime.date(2026, 11, 20))
    assert pc["on_track"] is False and pc["suggestion"] == 0.0 and pc["daily_allowance"] == 0.0
    store.set_payday(0)
    assert store.payday_cycle(today=datetime.date(2026, 11, 20)) is None
    with pytest.raises(ValueError):
        store.set_payday(31)
    assert store.get_payday() == 0


def test_payday_needs_starting_balance(store):
    store.set_payday(15)
    assert store.payday_cycle(today=datetime.date(2026, 11, 20)) is None


# -- Zeitraum-Modus: Kalendermonat (Standard) oder Zahltag-Zyklus -----------------

def _period_setup(store):
    food = _cat(store, "Essen")
    pay = _cat(store, "Gehalt", "einnahme")
    store.add_transaction("2026-10-10", -40.0, food, "alt")        # Kalender Okt / Zyklus 09
    store.add_transaction("2026-10-16", -100.0, food, "A")          # Okt / Zyklus 10
    store.add_transaction("2026-10-15", 2000.0, pay, "Gehalt")
    store.add_transaction("2026-11-05", -60.0, food, "B")           # Nov / Zyklus 10
    store.add_transaction("2026-11-20", -30.0, food, "C")           # Nov / Zyklus 11
    store.set_payday(15)


def test_period_default_is_calendar(store):
    _period_setup(store)
    assert store.get_period_mode() == "calendar"
    assert store.period_bounds("2026-10") == ("2026-10-01", "2026-11-01")
    assert store.current_period(datetime.date(2026, 11, 20)) == "2026-11"
    assert {r["category_name"]: r["total"] for r in store.spending_by_category("2026-10")}["Essen"] == 140.0


def test_period_cycle_mode_sums_and_keys(store):
    _period_setup(store)
    store.set_period_mode("cycle")
    assert store.get_period_mode() == "cycle"
    assert store.period_bounds("2026-10") == ("2026-10-15", "2026-11-15")
    assert store.period_of(datetime.date(2026, 11, 14)) == "2026-10"
    assert store.period_of(datetime.date(2026, 11, 15)) == "2026-11"
    assert store.current_period(datetime.date(2026, 11, 20)) == "2026-11"
    assert store.current_period(datetime.date(2026, 11, 3)) == "2026-10"
    assert {r["category_name"]: r["total"] for r in store.spending_by_category("2026-10")}["Essen"] == 160.0
    assert store.income_by_category("2026-10")[0]["total"] == 2000.0
    trend = store.monthly_trend(2, "2026-11")
    assert [t["month"] for t in trend] == ["2026-10", "2026-11"]
    assert trend[0]["expense"] == 160.0 and trend[1]["expense"] == 30.0
    s = store.month_summary("2026-10")
    assert s["expense"] == 160.0 and s["income"] == 2000.0 and s["prev_expense"] == 40.0
    assert store.list_months_with_transactions(), "Zeiträume vorhanden"


def test_period_cycle_without_payday_falls_back(store):
    _period_setup(store)
    store.set_period_mode("cycle")
    store.set_payday(0)
    assert store.get_period_mode() == "calendar"
    assert store.period_bounds("2026-10") == ("2026-10-01", "2026-11-01")
    with pytest.raises(ValueError):
        store.set_period_mode("quatsch")


def test_period_dashboard_and_pending_summary_in_cycle(store):
    _period_setup(store)
    store.set_period_mode("cycle")
    d = store.dashboard_data(today=datetime.date(2026, 11, 20))
    assert d["month"] == "2026-11" and d["period_mode"] == "cycle"
    assert d["day"] == 6 and d["days_in_month"] == 30
    assert d["expense_sofar"] == 30.0
    assert d["period_start"] == datetime.date(2026, 11, 15) and d["period_end"] == datetime.date(2026, 12, 14)
    pend = store.pending_month_summary(today=datetime.date(2026, 11, 20))
    assert pend["month"] == "2026-10" and pend["expense"] == 160.0
    rep = store.month_report_data("2026-10")
    assert rep["period_start"] == "2026-10-15" and rep["period_end"] == "2026-11-14"
