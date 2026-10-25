#!/usr/bin/env python3
"""
Plutos – Das Haushaltsbuch (Qt/PySide6-Variante). Budget- und Finanzplaner.

Portierung der GTK3/Linux-Version auf eine plattformübergreifende Qt-Oberfläche
(läuft nativ unter macOS, Windows und Linux). db.py ist unverändert von der
GTK-Version übernommen (reines Python/SQLite-Backend ohne UI-Abhängigkeit) –
nur der Speicherort der Datenbank ist jetzt plattformabhängig (siehe db.py).

Funktionsumfang identisch zur GTK-Version:
    - Buchungen in Kalenderansicht (Monat/Woche/Jahr), wiederkehrende
      Einträge, Bearbeiten per Doppelklick
    - Budgets, Sparziele (mit manueller Prioritätsreihenfolge),
      Finanzplanung (Notgroschen, Mehrfachziele-Empfehlung, Risikoprofil)
    - ETF-Sparplan-Rechner inkl. Vorabpauschale-Simulation und
      Plan-Vergleichsdiagramm
    - Auswertungen (Kreisdiagramm, Trend, Sankey-Geldfluss) als
      Umschalt-Ansichten
    - Kategorien mit Icon, CSV-/JSON-Export/-Import

Start:
    python3 main.py
"""

import sys
import datetime
import html as _html
from pathlib import Path
import re

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QLabel, QPushButton, QComboBox, QDoubleSpinBox, QSpinBox,
    QCheckBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QCalendarWidget, QScrollArea, QStackedWidget, QFileDialog,
    QMessageBox, QGroupBox, QProgressBar, QSizePolicy, QDateEdit, QInputDialog,
    QListWidget, QListWidgetItem, QFrame,
)
from PySide6.QtCore import Qt, QDate, QSize, QLocale
from PySide6.QtGui import QIcon, QColor, QTextCharFormat, QPalette, QShortcut, QKeySequence, QFontMetrics

from db import FinanceStore, add_months
from i18n import tr, set_language, get_language, LANGUAGES, months, months_short, weekdays, weekdays_short
import theme
from theme import (
    make_card, make_icon, make_link_button, set_role, ProgressRow, PaceBar, MiniTrend, BarCell,
)
from charts import (
    PieChartWidget, TrendChartWidget, SankeyWidget, EtfComparisonWidget,
    CategoryCompareWidget, CategoryYearWidget, YearCompareWidget, format_delta,
    fmt_amount, color_for_index,
)
from dialogs import (
    TransactionDialog, RecurringTemplatesDialog, BudgetDialog, GoalDialog,
    ContributionDialog, CategoryManagerDialog, QuickTemplatesDialog, make_help_button,
)




def _localize_import_error(line):
    """Fehlertexte aus db.py sind deutsch; hier passend zur Sprache ausgeben."""
    m = re.match(r"^Zeile (\d+): Datum oder Betrag nicht lesbar, übersprungen\.$", line)
    if m:
        return tr("Zeile {0}: Datum oder Betrag nicht lesbar, übersprungen.").format(m.group(1))
    return line


def month_label(date_obj):
    return f"{months()[date_obj.month - 1]} {date_obj.year}"


def _qdate_to_date(qdate: QDate) -> datetime.date:
    return datetime.date(qdate.year(), qdate.month(), qdate.day())


def _date_to_qdate(d: datetime.date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _themed_hint_html(html, palette):
    """Ersetzt die festen Hinweisfarben (für dunkle Themes gewählt) durch Farben
    aus der aktuellen Palette, damit Hinweise auch im hellen Modus lesbar
    sind: 'stark' = Textfarbe, 'gedämpft' = Textfarbe leicht zum Hintergrund
    gemischt."""
    text = palette.color(QPalette.WindowText)
    bg = palette.color(QPalette.Window)
    soft = QColor(int(text.red() * 0.72 + bg.red() * 0.28),
                  int(text.green() * 0.72 + bg.green() * 0.28),
                  int(text.blue() * 0.72 + bg.blue() * 0.28))
    for old in ("#d8dee9", "#c8ced6"):
        html = html.replace(old, text.name())
    return html.replace("#aeb6c0", soft.name())


# ---------------------------------------------------------------------------
# Hauptfenster
# ---------------------------------------------------------------------------

class PageTabs(QTabWidget):
    """Seitenstapel ohne eigene Tab-Leiste – umgeschaltet wird über die
    Seitenleiste (siehe MainWindow._build_sidebar)."""

    def __init__(self):
        super().__init__()
        self.setObjectName("pages")
        self.tabBar().hide()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1180, 760)

        self.store = FinanceStore()
        set_language(self.store.get_setting("language", "de"))
        theme.apply_theme(QApplication.instance(), self.store.get_setting("theme", "system"))
        self.setWindowTitle(tr('Plutos – Das Haushaltsbuch'))
        self.store.ensure_horizon(datetime.date.today())
        try:  # tägliches automatisches Datenbank-Backup; darf den Start nie verhindern
            self.store.create_db_backup()
        except Exception as exc:
            print(f"Automatisches Backup fehlgeschlagen: {exc}")

        self.selected_day = datetime.date.today()
        self.stats_month = datetime.date.today().replace(day=1)
        self.trend_months = 6
        self.current_etf_plan_id = None
        self._current_recommendation = None

        self.tabs = PageTabs()
        self.tab_index = {}
        pages = [
            ("overview", tr('Übersicht'), self._build_dashboard_tab),
            ("bookings", tr('Buchungen'), self._build_transactions_tab),
            ("budgets", tr('Budgets'), self._build_budgets_tab),
            ("goals", tr('Sparziele'), self._build_goals_tab),
            ("planning", tr('Finanzplanung'), self._build_planning_tab),
            ("etf", tr('ETF-Sparplan'), self._build_etf_tab),
            ("stats", tr('Auswertungen'), self._build_stats_tab),
            ("search", tr('Suche'), self._build_search_tab),
            ("export", tr('Export / Import'), self._build_export_tab),
        ]
        self._nav_entries = []
        for key, title, builder in pages:
            self.tab_index[key] = self.tabs.count()
            if key == "etf":
                self.etf_tab_index = self.tabs.count()
            self.tabs.addTab(builder(), title)
            self._nav_entries.append((key, title))

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 12, 14, 12)
        content_layout.addWidget(self.tabs)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)
        self.tabs.currentChanged.connect(self._on_page_changed)
        self._refresh_dashboard()

        # Zahlenfelder in Formularen linksbündig statt über die ganze Breite.
        for container in [self] + self.findChildren(QWidget):
            grid_layout = container.layout()
            if isinstance(grid_layout, QGridLayout):
                for i in range(grid_layout.count()):
                    item = grid_layout.itemAt(i)
                    if isinstance(item.widget(), (QSpinBox, QDoubleSpinBox, QDateEdit)):
                        item.setAlignment(Qt.AlignLeft)

        for table in self.findChildren(QTableWidget):
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(38)
            table.setShowGrid(False)
            table.setFocusPolicy(Qt.NoFocus)
        self.goal_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.goal_table.setColumnWidth(4, 190)

        # Wichtigste Aktionen farblich hervorheben (Primär-Buttons).
        primary_labels = {tr(x) for x in (
            'Speichern', 'Hinzufügen', 'Buchung hinzufügen', 'Empfehlung berechnen',
            'Berechnen & Speichern', 'Ziel hinzufügen', 'Einzahlen', 'Suchen')}
        for btn in self.findChildren(QPushButton):
            if btn.text().replace("&&", "&") in primary_labels:
                btn.setProperty("primary", True)
        for btn in self.findChildren(QPushButton):
            if btn.text() in ("◀", "▶"):
                btn.setProperty("nav", True)

        # Feste (dunkel gewählte) Hinweisfarben an das aktuelle Theme anpassen.
        for label in self.findChildren(QLabel):
            html = label.text()
            if "#aeb6c0" in html or "#c8ced6" in html or "#d8dee9" in html:
                label.setText(_themed_hint_html(html, label.palette()))

    # =====================================================================
    # Seitenleiste
    # =====================================================================

    def _build_sidebar(self):
        t = theme.current()
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(224)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(14, 20, 14, 14)
        layout.setSpacing(2)
        brand = QLabel("Plutos")
        brand.setObjectName("brand")
        sub = QLabel(tr('Das Haushaltsbuch'))
        sub.setObjectName("brandSub")
        layout.addWidget(brand)
        layout.addWidget(sub)
        layout.addSpacing(16)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setIconSize(QSize(20, 20))
        self.nav.setFocusPolicy(Qt.NoFocus)
        self._nav_icon_names = [key for key, _ in self._nav_entries]
        for key, title in self._nav_entries:
            item = QListWidgetItem(make_icon(key, t["muted"]), "  " + title)
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_nav_row)
        self._update_nav_icons()
        layout.addWidget(self.nav, 1)
        return bar

    def _update_nav_icons(self):
        t = theme.current()
        for i, key in enumerate(self._nav_icon_names):
            color = t["accent"] if i == self.nav.currentRow() else t["muted"]
            self.nav.item(i).setIcon(make_icon(key, color))

    def _on_nav_row(self, row):
        if row >= 0:
            self.tabs.setCurrentIndex(row)
        self._update_nav_icons()

    def _on_page_changed(self, index):
        if self.nav.currentRow() != index:
            self.nav.setCurrentRow(index)
        if index == self.tab_index["overview"]:
            self._refresh_dashboard()

    def _go_to(self, key):
        self.tabs.setCurrentIndex(self.tab_index[key])

    # =====================================================================
    # Tab 0: Übersicht
    # =====================================================================

    def _build_dashboard_tab(self):
        self.dashboard_scroll = QScrollArea()
        self.dashboard_scroll.setWidgetResizable(True)
        return self.dashboard_scroll

    def _kpi_card(self, title, value, sub, value_color=None):
        card, lay = make_card()
        t_label = QLabel(title)
        t_label.setObjectName("cardTitle")
        v_label = QLabel(value)
        v_label.setObjectName("kpiValue")
        if value_color:
            v_label.setStyleSheet(f"color: {value_color};")
        s_label = QLabel(sub)
        s_label.setObjectName("kpiSub")
        s_label.setWordWrap(True)
        lay.addWidget(t_label)
        lay.addWidget(v_label)
        lay.addWidget(s_label)
        lay.addStretch()
        return card, lay

    def _card_header(self, lay, title, link_text=None, link_key=None):
        row = QHBoxLayout()
        t_label = QLabel(title)
        t_label.setObjectName("cardTitle")
        row.addWidget(t_label, 1)
        if link_text:
            row.addWidget(make_link_button(link_text, lambda: self._go_to(link_key)))
        lay.addLayout(row)

    def _month_summary_card(self, sm):
        """Kleine Rückschau auf den Vormonat – bleibt, bis man sie ausblendet."""
        t = theme.current()
        card, lay = make_card()
        year, mon = int(sm["month"][:4]), int(sm["month"][5:7])
        row = QHBoxLayout()
        title = QLabel(tr('Monatsabschluss {0}').format(f"{months()[mon - 1]} {year}"))
        title.setObjectName("cardTitle")
        row.addWidget(title, 1)
        row.addWidget(make_link_button(tr('Auswertungen'), lambda: self._go_to("stats")))
        row.addWidget(make_link_button(tr('Ausblenden'), lambda: self._dismiss_month_summary(sm["month"])))
        lay.addLayout(row)

        saved = sm["saved"]
        head = QLabel(tr('Gespart {0}').format(fmt_amount(saved)))
        head.setStyleSheet(f"font-size: 20px; font-weight: 600; color: {t['positive'] if saved >= 0 else t['negative']};")
        lay.addWidget(head)
        lines = [tr('Einnahmen {0} · Ausgaben {1}').format(fmt_amount(sm["income"]), fmt_amount(sm["expense"]))]
        if sm["saving_rate"] is not None:
            lines[0] += " · " + tr('Sparquote {0:.0f} %').format(sm["saving_rate"] * 100)
        if sm["expense_change"] is not None:
            ch = sm["expense_change"] * 100
            lines.append(tr('Ausgaben {0}{1:.0f} % gegenüber dem Vormonat').format("+" if ch > 0 else "−", abs(ch)))
        top = sm["top_category"]
        if top:
            lines.append(tr('Größte Ausgabe: {0} {1} ({2}, {3:.0f} %)').format(
                top["icon"], top["name"], fmt_amount(top["amount"]), top["share"] * 100))
        if sm["budget_count"]:
            text = tr('Budgets: {0} von {1} eingehalten').format(sm["budgets_ok"], sm["budget_count"])
            if sm["budgets_over"]:
                text += " – " + tr('drüber: {0}').format(", ".join(
                    f"{b['icon']} {b['name']} (+{fmt_amount(b['over_by'])})" for b in sm["budgets_over"][:3]))
            lines.append(text)
        for text in lines:
            label = QLabel(text)
            label.setObjectName("kpiSub")
            label.setWordWrap(True)
            lay.addWidget(label)
        return card

    def _dismiss_month_summary(self, month):
        self.store.dismiss_month_summary(month)
        self._refresh_dashboard()


    def _reminder_lines(self, items, limit=6):
        """(Symbol, Text, Farb-Rolle) je Erinnerung, höchstens `limit` Zeilen."""
        lines = []
        for it in items:
            if it["kind"] == "budget":
                spent, lim = fmt_amount(it["spent"]), fmt_amount(it["limit"])
                if it["level"] == "over":
                    lines.append(("⛔", tr('{0} {1}: Budget überschritten ({2} von {3})').format(
                        it["icon"], it["name"], spent, lim), "negative"))
                elif it["level"] == "full":
                    lines.append(("⚠️", tr('{0} {1}: Budget ausgeschöpft ({2} von {3})').format(
                        it["icon"], it["name"], spent, lim), "warn"))
                else:
                    lines.append(("⚠️", tr('{0} {1}: {2:.0f} % des Budgets verbraucht ({3} von {4})').format(
                        it["icon"], it["name"], it["percent"], spent, lim), "warn"))
            elif it["kind"] == "goal":
                due = datetime.date.fromisoformat(it["date"]).strftime("%d.%m.%Y")
                key = (tr('Sparziel „{0}“: Zieldatum {1} ist überschritten, es fehlen noch {2}')
                       if it["overdue"] else tr('Sparziel „{0}“: Zieldatum {1}, es fehlen noch {2}'))
                lines.append(("🎯", key.format(it["name"], due, fmt_amount(it["missing"])),
                              "negative" if it["overdue"] else "warn"))
            else:
                day = datetime.date.fromisoformat(it["date"])
                lines.append(("🔁", tr('Fällig am {0}: {1} {2} ({3})').format(
                    day.strftime("%d.%m."), it["icon"], it["text"], fmt_amount(it["amount"])), None))
        extra = len(lines) - limit
        lines = lines[:limit]
        if extra > 0:
            lines.append(("", tr('… und {0} weitere').format(extra), None))
        return lines

    def _reminders_card(self, items):
        t = theme.current()
        card, lay = make_card()
        title = QLabel(tr('Erinnerungen'))
        title.setObjectName("cardTitle")
        lay.addWidget(title)
        colors = {"negative": t["negative"], "warn": t["warn"], None: None}
        for icon, text, role in self._reminder_lines(items):
            row = QHBoxLayout()
            sym = QLabel(icon)
            sym.setFixedWidth(26)
            label = QLabel(text)
            label.setWordWrap(True)
            if colors[role]:
                label.setStyleSheet(f"color: {colors[role]};")
            row.addWidget(sym)
            row.addWidget(label, 1)
            lay.addLayout(row)
        return card

    def _refresh_dashboard(self):
        if not hasattr(self, "dashboard_scroll"):
            return
        t = theme.current()
        d = self.store.dashboard_data()
        today = datetime.date.today()

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(4, 4, 8, 8)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        for col in range(6):
            grid.setColumnStretch(col, 1)

        header = QHBoxLayout()
        title = QLabel(tr('Übersicht'))
        title.setObjectName("pageTitle")
        header.addWidget(title)
        month_label = QLabel(f"{months()[today.month - 1]} {today.year}")
        month_label.setObjectName("muted")
        header.addWidget(month_label, 0, Qt.AlignBottom)
        header.addStretch()
        grid.addLayout(header, 0, 0, 1, 6)

        # --- Erinnerungen -------------------------------------------------------
        reminders = self.store.reminders()
        if reminders:
            grid.addWidget(self._reminders_card(reminders), 1, 0, 1, 6)

        # --- Monatsabschluss (Vormonat, bis er ausgeblendet wird) -----------
        summary = self.store.pending_month_summary()
        if summary:
            grid.addWidget(self._month_summary_card(summary), 2, 0, 1, 6)

        # --- Kennzahlen ---------------------------------------------------
        bd = d["balance"]
        if bd is None:
            card1, _ = self._kpi_card(tr('Kontostand'), "–",
                                      tr('Kontostand in der Finanzplanung hinterlegen'))
        elif d["pocket_enabled"]:
            card1, _ = self._kpi_card(
                tr('Gesamtvermögen'), fmt_amount(bd["total"]),
                tr('Girokonto {0} · Notgroschen {1}').format(fmt_amount(bd["giro"]), fmt_amount(bd["pocket"])))
        else:
            card1, _ = self._kpi_card(tr('Kontostand'), fmt_amount(bd["giro"]), tr('Berechnet bis heute'))
        grid.addWidget(card1, 3, 0, 1, 2)

        saldo = d["income_sofar"] - d["expense_sofar"]
        sub = tr('Einnahmen {0} · Ausgaben {1}').format(fmt_amount(d["income_sofar"]), fmt_amount(d["expense_sofar"]))
        if d["expense_planned"] - d["expense_sofar"] > 0.005:
            sub += "\n" + tr('Bis Monatsende geplant: {0} Ausgaben').format(
                fmt_amount(d["expense_planned"] - d["expense_sofar"]))
        card2, _ = self._kpi_card(tr('Saldo im {0}').format(months()[today.month - 1]),
                                  fmt_amount(saldo), sub,
                                  t["positive"] if saldo >= 0 else t["negative"])
        grid.addWidget(card2, 3, 2, 1, 2)

        emergency = next((g for g in d["goals"] if g["name"] == "Notgroschen"), None)
        if emergency and emergency["target"] > 0:
            pct = emergency["current"] / emergency["target"] * 100
            card3, lay3 = self._kpi_card(
                tr('Notgroschen'), fmt_amount(emergency["current"]),
                tr('von {0} · {1} %').format(fmt_amount(emergency["target"]), f"{pct:.0f}"))
            bar = ProgressRow("", "", emergency["current"] / emergency["target"], t["accent"])
            lay3.insertWidget(lay3.count() - 1, bar)
        else:
            card3, lay3 = self._kpi_card(tr('Notgroschen'), "–", tr('Noch nicht eingerichtet'))
            lay3.insertWidget(lay3.count() - 1,
                              make_link_button(tr('In der Finanzplanung einrichten'),
                                               lambda: self._go_to("planning")))
        grid.addWidget(card3, 3, 4, 1, 2)

        # --- Ausgabentempo -----------------------------------------------
        pace, pl = make_card()
        self._card_header(pl, tr('Ausgabentempo'))
        elapsed = d["day"] / d["days_in_month"]
        if d["baseline"]:
            ratio = d["expense_sofar"] / d["baseline"]
            basis = tr('deines Budgets') if d["baseline_kind"] == "budget" else tr('eines üblichen Monats')
            if ratio <= elapsed + 0.05:
                verdict, vcolor = tr('im Rahmen'), t["positive"]
            elif ratio <= 1.0:
                verdict, vcolor = tr('schneller als der Monat'), t["warn"]
            else:
                verdict, vcolor = tr('über dem Rahmen'), t["negative"]
            head = QHBoxLayout()
            amount = QLabel(tr('{0} von {1}').format(fmt_amount(d["expense_sofar"]), fmt_amount(d["baseline"])))
            amount.setStyleSheet("font-size: 18px; font-weight: 600;")
            head.addWidget(amount)
            chip = QLabel(verdict)
            chip.setStyleSheet(f"color: {vcolor}; font-weight: 600;")
            head.addWidget(chip)
            head.addStretch()
            pl.addLayout(head)
            bar = PaceBar()
            bar.set_values(ratio, elapsed)
            pl.addWidget(bar)
            note = QLabel(tr('Tag {0} von {1}: {2} % des Monats sind vorbei, {3} % {4} ausgegeben.').format(
                d["day"], d["days_in_month"], f"{elapsed * 100:.0f}", f"{ratio * 100:.0f}", basis))
            note.setObjectName("kpiSub")
            note.setWordWrap(True)
            pl.addWidget(note)
        else:
            hint = QLabel(tr('Sobald Budgets gesetzt sind oder Buchungen aus Vormonaten vorliegen, zeigt Plutos hier, ob du im Rahmen bleibst.'))
            hint.setObjectName("kpiSub")
            hint.setWordWrap(True)
            pl.addWidget(hint)
        grid.addWidget(pace, 4, 0, 1, 6)

        # --- Budgets ------------------------------------------------------
        bcard, bl = make_card()
        self._card_header(bl, tr('Budgets im Monat'), tr('Alle ansehen'), "budgets")
        if d["top_budgets"]:
            for b in d["top_budgets"]:
                color = {"over": t["negative"], "warn": t["warn"], "full": t["warn"]}.get(b["level"], t["accent"])
                bl.addWidget(ProgressRow(f"{b['icon']}  {b['name']}",
                                         f"{fmt_amount(b['spent'])} / {fmt_amount(b['limit'])}",
                                         b["spent"] / b["limit"], color))
        else:
            empty = QLabel(tr('Noch keine Budgets für diesen Monat.'))
            empty.setObjectName("kpiSub")
            bl.addWidget(empty)
            bl.addWidget(make_link_button(tr('Budget setzen'), lambda: self._go_to("budgets")))
        bl.addStretch()
        grid.addWidget(bcard, 5, 0, 1, 3)

        # --- Sparziele ----------------------------------------------------
        gcard, gl = make_card()
        self._card_header(gl, tr('Sparziele'), tr('Alle ansehen'), "goals")
        goals = [g for g in d["goals"] if g["target"] > 0][:5]
        if goals:
            for g in goals:
                gl.addWidget(ProgressRow(g["name"],
                                         f"{fmt_amount(g['current'])} / {fmt_amount(g['target'])}",
                                         g["current"] / g["target"], t["accent"]))
        else:
            empty = QLabel(tr('Noch keine Sparziele angelegt.'))
            empty.setObjectName("kpiSub")
            gl.addWidget(empty)
            gl.addWidget(make_link_button(tr('Sparziel anlegen'), lambda: self._go_to("goals")))
        gl.addStretch()
        grid.addWidget(gcard, 5, 3, 1, 3)

        # --- Verlauf ------------------------------------------------------
        tcard, tl = make_card()
        self._card_header(tl, tr('Letzte 6 Monate'), tr('Auswertungen'), "stats")
        legend = QLabel(f'<span style="color:{t["positive"]}">■</span> {tr("Einnahmen")}&nbsp;&nbsp;'
                        f'<span style="color:{t["accent"]}">■</span> {tr("Ausgaben")}')
        legend.setObjectName("muted")
        tl.addWidget(legend)
        trend = MiniTrend()
        trend.set_rows([(months_short()[int(r["month"][5:]) - 1], r["income"], r["expense"],
                         r["month"] == d["month"]) for r in d["trend"]])
        tl.addWidget(trend, 1)
        grid.addWidget(tcard, 6, 0, 1, 3)

        # --- Letzte Buchungen ---------------------------------------------
        rcard, rl = make_card()
        self._card_header(rl, tr('Letzte Buchungen'), tr('Alle ansehen'), "bookings")
        if d["recent"]:
            for r in d["recent"]:
                row = QHBoxLayout()
                day = datetime.date.fromisoformat(r["date"])
                date_label = QLabel(f"{day.day:02d}.{day.month:02d}.")
                date_label.setObjectName("muted")
                date_label.setFixedWidth(46)
                text = (r["description"] or r["category_name"]).strip()
                name = QLabel(f"{r['icon']}  {text}")
                name.setMinimumWidth(10)
                amount = QLabel(fmt_amount(r["amount"]))
                if r["amount"] > 0:
                    amount.setStyleSheet(f"color: {t['positive']};")
                amount.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                row.addWidget(date_label)
                row.addWidget(name, 1)
                row.addWidget(amount)
                rl.addLayout(row)
        else:
            empty = QLabel(tr('Noch keine Buchungen.'))
            empty.setObjectName("kpiSub")
            rl.addWidget(empty)
            rl.addWidget(make_link_button(tr('Buchung hinzufügen'), lambda: self._go_to("bookings")))
        rl.addStretch()
        grid.addWidget(rcard, 6, 3, 1, 3)

        grid.setRowStretch(7, 1)
        self.dashboard_scroll.setWidget(content)

    # =====================================================================
    # Tab 1: Buchungen (Kalenderansicht: Monat/Woche/Jahr)
    # =====================================================================

    def _build_transactions_tab(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)

        # -- Linke Seite: Ansicht wählen + Kalender/Woche/Jahr --
        left_widget, left_layout = make_card()
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)
        left_widget.setMaximumWidth(620)
        root_layout.addWidget(left_widget)

        self.view_switch_combo = QComboBox()
        self.view_switch_combo.addItem(tr('Monatsansicht'), "monat")
        self.view_switch_combo.addItem(tr('Wochenansicht'), "woche")
        self.view_switch_combo.addItem(tr('Jahresansicht'), "jahr")
        self.view_switch_combo.currentIndexChanged.connect(self._on_view_switch_changed)
        left_layout.addWidget(self.view_switch_combo)

        self.view_stack = QStackedWidget()
        left_layout.addWidget(self.view_stack)

        self.view_stack.addWidget(self._build_month_page())
        self.view_stack.addWidget(self._build_week_page())
        self.view_stack.addWidget(self._build_year_page())

        manage_cat_btn = QPushButton(tr('Kategorien verwalten'))
        manage_cat_btn.clicked.connect(self._on_manage_categories)
        left_layout.addWidget(manage_cat_btn)
        left_layout.addStretch()

        # -- Rechte Seite: Tagesliste --
        right_widget, right_layout = make_card()
        right_layout.setContentsMargins(16, 14, 16, 14)
        right_layout.setSpacing(8)
        root_layout.addWidget(right_widget, 1)

        self.day_title_label = QLabel()
        self.day_title_label.setStyleSheet("font-size: 17px; font-weight: 600;")
        right_layout.addWidget(self.day_title_label)

        self.day_table = QTableWidget(0, 5)
        self.day_table.setHorizontalHeaderLabels(
            [tr('Kategorie'), tr('Art'), tr('Betrag'), tr('Beschreibung'), tr('Wiederk.')])
        self.day_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.day_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.day_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.day_table.itemDoubleClicked.connect(self._on_edit_transaction_item)
        right_layout.addWidget(self.day_table)

        hint = QLabel(tr('Tipp: Doppelklick auf eine Buchung öffnet sie zum Bearbeiten.'))
        hint.setObjectName("muted")
        right_layout.addWidget(hint)

        btn_box = QHBoxLayout()
        right_layout.addLayout(btn_box)

        add_btn = QPushButton(tr('Buchung hinzufügen'))
        add_btn.clicked.connect(self._on_add_transaction)
        btn_box.addWidget(add_btn)

        edit_btn = QPushButton(tr('Bearbeiten'))
        edit_btn.clicked.connect(self._on_edit_selected_transaction)
        btn_box.addWidget(edit_btn)

        del_btn = QPushButton(tr('Löschen'))
        del_btn.clicked.connect(self._on_delete_transaction)
        btn_box.addWidget(del_btn)

        rec_btn = QPushButton(tr('Wiederkehrende Vorlagen verwalten'))
        rec_btn.clicked.connect(self._on_manage_recurring)
        btn_box.addWidget(rec_btn)
        btn_box.addStretch()

        btn_box2 = QHBoxLayout()
        right_layout.addLayout(btn_box2)
        self.undo_btn = QPushButton(tr('Rückgängig'))
        self.undo_btn.setToolTip(tr('Zuletzt gelöschte Buchung wiederherstellen (Strg+Z)'))
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self._on_undo_delete)
        btn_box2.addWidget(self.undo_btn)
        save_tpl_btn = QPushButton(tr('Als Vorlage speichern'))
        save_tpl_btn.setToolTip(tr('Die markierte Buchung als Schnellbuchungs-Vorlage merken'))
        save_tpl_btn.clicked.connect(self._on_save_quick_template)
        btn_box2.addWidget(save_tpl_btn)
        use_tpl_btn = QPushButton(tr('Aus Vorlage buchen…'))
        use_tpl_btn.clicked.connect(self._on_book_from_template)
        btn_box2.addWidget(use_tpl_btn)
        btn_box2.addStretch()
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._on_undo_delete)

        self._refresh_calendar_marks()
        self._refresh_day_list()
        self._refresh_month_balance()
        self._refresh_week_view()
        self._refresh_year_view()
        return root

    def _build_month_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.calendar = QCalendarWidget()
        self.calendar.setLocale(QLocale("en" if get_language() == "en" else "de"))
        self.calendar.setGridVisible(False)
        self.calendar.setMinimumHeight(300)
        self.calendar.setNavigationBarVisible(False)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(theme.current()["muted"]))
        self.calendar.setWeekdayTextFormat(Qt.Saturday, fmt)
        self.calendar.setWeekdayTextFormat(Qt.Sunday, fmt)
        self.calendar.selectionChanged.connect(self._on_day_selected)
        self.calendar.activated.connect(self._on_day_double_clicked)
        self.calendar.currentPageChanged.connect(self._on_calendar_page_changed)
        nav_row = QHBoxLayout()
        prev_month_btn = QPushButton("◀")
        prev_month_btn.clicked.connect(self.calendar.showPreviousMonth)
        self.calendar_title = QLabel()
        self.calendar_title.setAlignment(Qt.AlignCenter)
        self.calendar_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        next_month_btn = QPushButton("▶")
        next_month_btn.clicked.connect(self.calendar.showNextMonth)
        today_month_btn = QPushButton(tr('Heute'))
        today_month_btn.clicked.connect(lambda: (self.calendar.setSelectedDate(QDate.currentDate()),
                                                 self.calendar.setCurrentPage(QDate.currentDate().year(),
                                                                              QDate.currentDate().month())))
        nav_row.addWidget(prev_month_btn)
        nav_row.addWidget(self.calendar_title, 1)
        nav_row.addWidget(next_month_btn)
        nav_row.addWidget(today_month_btn)
        layout.addLayout(nav_row)
        self.calendar.currentPageChanged.connect(self._update_calendar_title)
        self._update_calendar_title(self.calendar.yearShown(), self.calendar.monthShown())
        layout.addWidget(self.calendar)

        self.month_balance_label = QLabel()
        self.month_balance_label.setWordWrap(True)
        layout.addWidget(self.month_balance_label)

        legend = QLabel(
    tr('\n    <b><font color="#d8dee9">Hinweise</font></b><br>\n    <b><font color="#c8ced6">Fett</font></b>\n    <font color="#aeb6c0"> – Buchungen an diesem Tag</font><br>\n    <b><font color="#c8ced6">Einfachklick</font></b>\n    <font color="#aeb6c0"> – Buchungen des Tages anzeigen</font><br>\n    <b><font color="#c8ced6">Doppelklick / Enter</font></b>\n    <font color="#aeb6c0"> – neue Buchung für dieses Datum anlegen</font>\n    ')
)

        legend.setWordWrap(True)
        layout.addWidget(legend)
        layout.addStretch()
        return page

    def _update_calendar_title(self, year, month):
        self.calendar_title.setText(f"{months()[month - 1]} {year}")

    def _build_week_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        nav = QHBoxLayout()
        layout.addLayout(nav)
        prev_btn = QPushButton("◀")
        prev_btn.clicked.connect(lambda: self._shift_week(-1))
        nav.addWidget(prev_btn)
        self.week_range_label = QLabel()
        nav.addWidget(self.week_range_label)
        next_btn = QPushButton("▶")
        next_btn.clicked.connect(lambda: self._shift_week(1))
        nav.addWidget(next_btn)
        today_btn = QPushButton(tr('Diese Woche'))
        today_btn.clicked.connect(self._goto_current_week)
        nav.addWidget(today_btn)
        nav.addStretch()

        week_box = QHBoxLayout()
        week_box.setSpacing(4)
        layout.addLayout(week_box)
        self.week_day_buttons = []
        for i in range(7):
            btn = QPushButton()
            btn.setFixedHeight(66)
            btn.setMinimumWidth(82)
            btn.setStyleSheet("padding: 6px 2px; min-height: 52px;")
            # Ignored + gleicher Stretch: alle Tage gleich breit, unabhängig vom Inhalt
            btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            btn.clicked.connect(lambda checked=False, offset=i: self._on_week_day_clicked(offset))
            # Beschriftung als Rich-Text-Label, damit der Betrag farbig sein kann
            tile = QVBoxLayout(btn)
            tile.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            lbl.setStyleSheet("background: transparent;")
            tile.addWidget(lbl)
            btn._tile_label = lbl
            week_box.addWidget(btn, 1)
            self.week_day_buttons.append(btn)

        hint = QLabel(
    tr('\n    <font color="#aeb6c0">\n        <b><font color="#c8ced6">Klick auf einen Tag</font></b>\n        – Buchungen des Tages rechts anzeigen.<br>\n        Monatsübersicht und Budgets folgen automatisch der angezeigten Woche.\n    </font>\n    ')
)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()

        self.week_start = self._monday_of(datetime.date.today())
        return page

    def _build_year_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        nav = QHBoxLayout()
        layout.addLayout(nav)
        prev_btn = QPushButton("◀")
        prev_btn.clicked.connect(lambda: self._shift_year(-1))
        nav.addWidget(prev_btn)
        self.year_label = QLabel()
        nav.addWidget(self.year_label)
        next_btn = QPushButton("▶")
        next_btn.clicked.connect(lambda: self._shift_year(1))
        nav.addWidget(next_btn)
        nav.addStretch()

        year_grid = QGridLayout()
        for _c in range(3):
            year_grid.setColumnStretch(_c, 1)
        layout.addLayout(year_grid)
        self.year_month_buttons = []
        for m in range(12):
            btn = QPushButton()
            btn.setMinimumHeight(50)
            btn.setMinimumWidth(110)
            btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            btn.clicked.connect(lambda checked=False, month=m + 1: self._on_year_month_clicked(month))
            year_grid.addWidget(btn, m // 3, m % 3)
            self.year_month_buttons.append(btn)

        hint = QLabel(
    tr('\n    <b><font color="#c8ced6">Klick auf einen Monat</font></b>\n    <font color="#aeb6c0"> – wechselt in die Monatsansicht.</font>\n    ')
)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()

        self.year_reference = datetime.date.today().year
        return page

    @staticmethod
    def _monday_of(d):
        return d - datetime.timedelta(days=d.weekday())

    def _selected_calendar_month(self):
        return datetime.date(self.calendar.yearShown(), self.calendar.monthShown(), 1)

    def _on_view_switch_changed(self, index):
        self.view_stack.setCurrentIndex(index)
        mode = self.view_switch_combo.currentData()
        if mode == "woche":
            self._refresh_week_view()
        elif mode == "jahr":
            self._refresh_year_view()

    def _on_day_selected(self):
        self.selected_day = _qdate_to_date(self.calendar.selectedDate())
        self._refresh_day_list()

    def _on_day_double_clicked(self, qdate):
        self.selected_day = _qdate_to_date(qdate)
        dialog = TransactionDialog(self, self.store, self.selected_day)
        if dialog.exec() == TransactionDialog.Accepted:
            dialog.save()
            self._after_transactions_changed()

    def _on_calendar_page_changed(self, year, month):
        month_start = datetime.date(year, month, 1)
        self.store.ensure_horizon(month_start)
        self._refresh_calendar_marks()
        self._refresh_month_balance()
        self._refresh_budgets_tab()

    def _refresh_calendar_marks(self):
        year = self.calendar.yearShown()
        month = self.calendar.monthShown()
        days_in_month = QDate(year, month, 1).daysInMonth()
        marked_days = self.store.days_with_transactions(year, month)

        bold_format = QTextCharFormat()
        font = bold_format.font()
        font.setBold(True)
        bold_format.setFont(font)
        empty_format = QTextCharFormat()

        for day in range(1, days_in_month + 1):
            qd = QDate(year, month, day)
            self.calendar.setDateTextFormat(qd, bold_format if day in marked_days else empty_format)

    def _refresh_month_balance(self):
        month_start = self._selected_calendar_month()
        month_str = month_start.strftime("%Y-%m")
        rows = self.store.list_transactions(month=month_str)
        income = sum(r["amount"] for r in rows if r["amount"] > 0)
        expense = sum(-r["amount"] for r in rows if r["amount"] < 0)
        saldo = income - expense
        sign = "+" if saldo >= 0 else ""
        self.month_balance_label.setText(
            tr('{0}\nEinnahmen: {1}\nAusgaben: {2}\nSaldo: {3}{4}').format(month_label(month_start), fmt_amount(income), fmt_amount(expense), sign, fmt_amount(saldo))
        )

    def _refresh_day_list(self):
        weekday_names = weekdays()
        d = self.selected_day
        self.day_title_label.setText(f"{weekday_names[d.weekday()]}, {d.strftime('%d.%m.%Y')}")

        rows = self.store.list_transactions_for_day(d.isoformat())
        self.day_table.setRowCount(len(rows))
        for row_idx, r in enumerate(rows):
            cat_item = QTableWidgetItem(f"{r['icon']} {r['category_name']}")
            cat_item.setData(Qt.UserRole, r["id"])
            self.day_table.setItem(row_idx, 0, cat_item)
            self.day_table.setItem(row_idx, 1, QTableWidgetItem(
                tr('Einnahme') if r["kind"] == "einnahme" else tr('Ausgabe')))
            amount_item = QTableWidgetItem(fmt_amount(r["amount"]))
            amount_item.setForeground(QColor(30, 140, 61) if r["amount"] >= 0 else QColor(191, 56, 38))
            self.day_table.setItem(row_idx, 2, amount_item)
            self.day_table.setItem(row_idx, 3, QTableWidgetItem(self._description_with_tags(r)))
            self.day_table.setItem(row_idx, 4, QTableWidgetItem(
                "✓" if r["recurring_template_id"] is not None else ""))

    def _description_with_tags(self, r):
        """Beschreibung, gefolgt von den Tags der Buchung als „#Tag“."""
        tags = " ".join(f"#{t}" for t in self.store.split_tags(r["tags"]))
        text = r["description"] or ""
        return f"{text}  {tags}".strip() if tags else text

    def _selected_transaction_id(self):
        row = self.day_table.currentRow()
        if row < 0:
            return None
        item = self.day_table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _on_add_transaction(self):
        dialog = TransactionDialog(self, self.store, datetime.date.today())
        if dialog.exec() == TransactionDialog.Accepted:
            dialog.save()
            self._after_transactions_changed()
            self._warn_if_budget_crossed(dialog.last_saved, is_new=True)

    def _on_edit_selected_transaction(self):
        tx_id = self._selected_transaction_id()
        if tx_id is not None:
            self._open_edit_dialog(tx_id)

    def _on_edit_transaction_item(self, item):
        tx_id = self.day_table.item(item.row(), 0).data(Qt.UserRole)
        if tx_id is not None:
            self._open_edit_dialog(tx_id)

    def _open_edit_dialog(self, tx_id):
        existing = self.store.get_transaction(tx_id)
        dialog = TransactionDialog(self, self.store, self.selected_day, existing=existing)
        if dialog.exec() == TransactionDialog.Accepted:
            dialog.save()
            self._after_transactions_changed()
            self._warn_if_budget_crossed(dialog.last_saved, is_new=False)

    def _on_delete_transaction(self):
        tx_id = self._selected_transaction_id()
        if tx_id is not None:
            self.store.delete_transaction(tx_id)
            self.undo_btn.setEnabled(True)
            self._after_transactions_changed()

    def _on_undo_delete(self):
        if not self.store.can_undo_delete():
            return
        restored = self.store.undo_delete_transaction()
        self.undo_btn.setEnabled(False)
        if restored:
            self.store.ensure_horizon(datetime.date.fromisoformat(restored["date"]))
            self._after_transactions_changed()
            self._refresh_stats()

    def _on_save_quick_template(self):
        tx_id = self._selected_transaction_id()
        if tx_id is None:
            QMessageBox.information(self, tr('Als Vorlage speichern'),
                                    tr('Bitte zuerst in der Liste eine Buchung markieren.'))
            return
        tx = self.store.get_transaction(tx_id)
        default_name = tx["description"] or tr("Vorlage")
        name, ok = QInputDialog.getText(self, tr('Als Vorlage speichern'),
                                        tr('Name der Vorlage:'), text=default_name)
        if ok and name.strip():
            self.store.add_quick_template(name, tx["category_id"], tx["amount"],
                                          tx["description"], tags=tx["tags"])

    def _on_book_from_template(self):
        dialog = QuickTemplatesDialog(self, self.store, self.selected_day)
        dialog.exec()
        if dialog.booked:
            self._after_transactions_changed()
            self._refresh_stats()
            for saved in dialog.booked:
                self._warn_if_budget_crossed(saved, is_new=True)

    def _warn_if_budget_crossed(self, saved, is_new):
        """Zeigt einen Hinweis, wenn eine Ausgabe das Monatsbudget ihrer
        Kategorie über 80 % bzw. 100 % hebt (nur beim Überschreiten einer
        Schwelle, nicht bei jeder weiteren Buchung)."""
        if not saved or saved["amount"] >= 0:
            return
        month = saved["date"][:7]
        status = self.store.budget_status(saved["category_id"], month)
        if not status:
            return
        before = self.store.budget_level(status["spent"] - (-saved["amount"] if is_new else 0),
                                         status["limit"])
        after = status["level"]
        if after == before or after not in ("warn", "full", "over"):
            return
        category = next((c for c in self.store.list_categories()
                         if c["id"] == saved["category_id"]), None)
        name = category["name"] if category else tr('Kategorie')
        percent = status["spent"] / status["limit"] * 100
        text = (tr('Budget „{0}“ ({1}/{2}): {3} von {4} ({5:.0f} %).').format(name, month[5:], month[:4], fmt_amount(status['spent']), fmt_amount(status['limit']), percent))
        if after == "over":
            QMessageBox.warning(self, tr('Budget überschritten'),
                                text + tr('\nDas Budget ist um {0} überschritten.').format(fmt_amount(status['spent'] - status['limit'])))
        elif after == "full":
            QMessageBox.information(self, tr('Budget ausgeschöpft'),
                                    text + tr('\nDas Budget ist damit vollständig ausgeschöpft.'))
        else:
            QMessageBox.information(self, tr('Budget fast aufgebraucht'),
                                    text + tr("\nDie 80-%-Marke ist erreicht."))

    def _on_manage_recurring(self):
        dialog = RecurringTemplatesDialog(self, self.store)
        dialog.exec()
        self.store.ensure_horizon(self._selected_calendar_month())
        self._after_transactions_changed()

    def _on_manage_categories(self):
        dialog = CategoryManagerDialog(self, self.store)
        dialog.exec()
        self._refresh_day_list()
        self._reload_search_categories()
        self._run_search()

    def _after_transactions_changed(self):
        self._refresh_calendar_marks()
        self._refresh_day_list()
        self._refresh_month_balance()
        self._refresh_budgets_tab()
        self._refresh_week_view()
        self._refresh_year_view()
        self._refresh_current_balance_display()
        self._run_search()

    # -- Wochenansicht --------------------------------------------------

    def _sync_calendar_to_week(self):
        month_date = self.week_start
        self.calendar.setCurrentPage(month_date.year, month_date.month)

    def _shift_week(self, delta):
        self.week_start = self.week_start + datetime.timedelta(weeks=delta)
        self._refresh_week_view()
        self._sync_calendar_to_week()

    def _goto_current_week(self):
        self.week_start = self._monday_of(datetime.date.today())
        self._refresh_week_view()
        self._sync_calendar_to_week()

    def _on_week_day_clicked(self, offset):
        d = self.week_start + datetime.timedelta(days=offset)
        self.calendar.setSelectedDate(_date_to_qdate(d))
        self.selected_day = d
        self._refresh_day_list()

    def _refresh_week_view(self):
        if not hasattr(self, "week_range_label"):
            return
        weekday_names = weekdays_short()
        start = self.week_start
        end = start + datetime.timedelta(days=6)
        self.week_range_label.setText(f"{start.strftime('%d.%m.')} – {end.strftime('%d.%m.%Y')}")
        self.store.ensure_horizon(start.replace(day=1))

        t = theme.current()
        tiles = []
        for i, btn in enumerate(self.week_day_buttons):
            d = start + datetime.timedelta(days=i)
            rows = self.store.list_transactions_for_day(d.isoformat())
            income = sum(r["amount"] for r in rows if r["amount"] > 0)
            expense = sum(-r["amount"] for r in rows if r["amount"] < 0)
            saldo = income - expense
            marker = " •" if d == datetime.date.today() else ""
            if rows:
                saldo_text = fmt_amount(saldo)
                color = t["positive"] if saldo >= 0 else t["negative"]
            else:
                saldo_text, color = "–", t["muted"]
            tiles.append((btn, f"{weekday_names[i]}{marker}", f"{d.day}.{d.month}.", saldo_text, color))

        # Schrift für alle Kacheln einheitlich so verkleinern, dass auch der
        # längste Betrag (z. B. „-1.000,00 €“) vollständig in die Kachel passt.
        base = tiles[0][0]._tile_label.font()
        base.setPointSizeF(max(base.pointSizeF(), 1.0))
        available = tiles[0][0].minimumWidth() - 8
        size = base.pointSizeF()
        while size > 7.0:
            base.setPointSizeF(size)
            fm = QFontMetrics(base)
            if all(fm.horizontalAdvance(tl[3]) <= available for tl in tiles):
                break
            size -= 0.5
        for btn, day, date_text, saldo_text, color in tiles:
            lbl = btn._tile_label
            f = lbl.font()
            f.setPointSizeF(size)
            lbl.setFont(f)
            lbl.setText(f"<b>{day}</b><br>{date_text}<br><span style=\"color:{color};\">{saldo_text}</span>")

    # -- Jahresansicht --------------------------------------------------

    def _shift_year(self, delta):
        self.year_reference += delta
        self._refresh_year_view()

    def _refresh_year_view(self):
        if not hasattr(self, "year_label"):
            return
        self.year_label.setText(str(self.year_reference))
        overview = self.store.yearly_overview(self.year_reference)
        for i, btn in enumerate(self.year_month_buttons):
            data = overview[i]
            saldo = data["income"] - data["expense"]
            has_data = bool(data["income"] or data["expense"])
            text = fmt_amount(saldo) if has_data else "–"
            name = months()[i][:3]
            btn.setText(f"{name}\n{text}")

    def _on_year_month_clicked(self, month):
        self.calendar.setCurrentPage(self.year_reference, month)
        self.store.ensure_horizon(datetime.date(self.year_reference, month, 1))
        self._refresh_calendar_marks()
        self._refresh_month_balance()
        self.view_switch_combo.setCurrentIndex(0)
        self.view_stack.setCurrentIndex(0)

    # =====================================================================
    # Tab 2: Budgets
    # =====================================================================

    def _build_budgets_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel(tr('Budgets gelten für den im Buchungen-Tab im Kalender sichtbaren Monat. Ein Budget läuft ab dem Monat, für den du es setzt, automatisch weiter (↺ = übernommen), bis du es änderst oder beendest.'))
        info.setWordWrap(True)
        layout.addWidget(info)

        self.budget_table = QTableWidget(0, 5)
        self.budget_table.setHorizontalHeaderLabels(
            [tr('Kategorie'), tr('Budget'), tr('Ausgegeben'), tr('Verbleibend'), tr('Fortschritt')])
        self.budget_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for _col in (1, 2, 3):
            self.budget_table.horizontalHeader().setSectionResizeMode(_col, QHeaderView.ResizeToContents)
        self.budget_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.budget_table.setColumnWidth(4, 190)
        self.budget_table.verticalHeader().setVisible(False)
        self.budget_table.verticalHeader().setDefaultSectionSize(40)
        self.budget_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.budget_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.budget_table)

        btn_box = QHBoxLayout()
        layout.addLayout(btn_box)
        set_btn = QPushButton(tr('Budget setzen/ändern'))
        set_btn.clicked.connect(self._on_set_budget)
        btn_box.addWidget(set_btn)
        end_btn = QPushButton(tr('Budget beenden'))
        end_btn.setToolTip(tr('Beendet das Budget der markierten Kategorie ab dem angezeigten Monat; frühere Monate bleiben unverändert.'))
        end_btn.clicked.connect(self._on_end_budget)
        btn_box.addWidget(end_btn)
        refresh_btn = QPushButton(tr('Aktualisieren'))
        refresh_btn.clicked.connect(self._refresh_budgets_tab)
        btn_box.addWidget(refresh_btn)
        btn_box.addStretch()

        self._refresh_budgets_tab()
        return widget

    def _refresh_budgets_tab(self):
        month_str = self._selected_calendar_month().strftime("%Y-%m")
        rows = self.store.budget_overview(month_str)
        self.budget_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            cat_item = QTableWidgetItem(f"{r['icon']} {r['category_name']}")
            cat_item.setData(Qt.UserRole, r["category_id"])
            self.budget_table.setItem(i, 0, cat_item)

            limit_amount = r["limit_amount"]
            spent = r["spent"]
            tk = theme.current()
            percent, bar_color = 0, tk["accent"]
            if limit_amount is None:
                self.budget_table.setItem(i, 1, QTableWidgetItem(tr('— kein Budget —')))
                self.budget_table.setItem(i, 2, QTableWidgetItem(fmt_amount(spent)))
                self.budget_table.setItem(i, 3, QTableWidgetItem("–"))
            else:
                remaining = limit_amount - spent
                percent = int(min(100, max(0, (spent / limit_amount) * 100))) if limit_amount else 0
                limit_item = QTableWidgetItem(
                    fmt_amount(limit_amount) + ("  ↺" if r["inherited_from"] else ""))
                if r["inherited_from"]:
                    y, m = r["inherited_from"].split("-")
                    limit_item.setToolTip(tr('Übernommen aus {0}').format(f"{months()[int(m) - 1]} {y}"))
                self.budget_table.setItem(i, 1, limit_item)
                self.budget_table.setItem(i, 2, QTableWidgetItem(fmt_amount(spent)))
                self.budget_table.setItem(i, 3, QTableWidgetItem(fmt_amount(remaining)))
                level = self.store.budget_level(spent, limit_amount)
                if level in ("warn", "full"):
                    bar_color = tk["warn"]
                    self.budget_table.item(i, 2).setForeground(QColor(tk["warn"]))
                elif level == "over":
                    bar_color = tk["negative"]
                    self.budget_table.item(i, 3).setForeground(QColor(tk["negative"]))
                    self.budget_table.item(i, 2).setForeground(QColor(tk["negative"]))
            progress = BarCell(percent, bar_color)
            self.budget_table.setCellWidget(i, 4, progress)

    def _on_set_budget(self):
        row = self.budget_table.currentRow()
        preselect = self.budget_table.item(row, 0).data(Qt.UserRole) if row >= 0 else None
        dialog = BudgetDialog(self, self.store, self._selected_calendar_month(), preselect)
        if dialog.exec() == BudgetDialog.Accepted:
            dialog.save()
            self._refresh_budgets_tab()

    def _on_end_budget(self):
        row = self.budget_table.currentRow()
        if row < 0:
            QMessageBox.information(self, tr('Budget beenden'), tr('Bitte zuerst eine Kategorie markieren.'))
            return
        category_id = self.budget_table.item(row, 0).data(Qt.UserRole)
        month = self._selected_calendar_month()
        if self.store.budget_status(category_id, month.strftime("%Y-%m")) is None:
            QMessageBox.information(self, tr('Budget beenden'), tr('Für diese Kategorie gilt in diesem Monat kein Budget.'))
            return
        self.store.end_budget(category_id, month.strftime("%Y-%m"))
        self._refresh_budgets_tab()

    # =====================================================================
    # Tab 3: Sparziele
    # =====================================================================

    def _build_goals_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel(
    tr('\n    <font color="#aeb6c0">\n        Die Reihenfolge legt fest, in welcher Priorität die\n        Finanzplanungsempfehlung das\n        <b><font color="#c8ced6">Startkapital / den Sparbetrag</font></b>\n        auf die Ziele verteilt.\n        <b><font color="#c8ced6">Oben</font></b> = zuerst befüllt.<br>\n        Mit <b><font color="#c8ced6">„Nach oben“</font></b> /\n        <b><font color="#c8ced6">„Nach unten“</font></b>\n        frei sortierbar.\n    </font>\n    ')
)
        info.setWordWrap(True)
        layout.addWidget(info)

        self.goal_table = QTableWidget(0, 5)
        self.goal_table.setHorizontalHeaderLabels(
            [tr('Priorität / Ziel'), tr('Zielbetrag'), tr('Angespart'), tr('Zieldatum'), tr('Fortschritt')])
        self.goal_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.goal_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.goal_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.goal_table)

        btn_box = QHBoxLayout()
        layout.addLayout(btn_box)
        add_btn = QPushButton(tr('Ziel hinzufügen'))
        add_btn.clicked.connect(self._on_add_goal)
        btn_box.addWidget(add_btn)
        contrib_btn = QPushButton(tr('Einzahlen'))
        contrib_btn.clicked.connect(self._on_add_contribution)
        btn_box.addWidget(contrib_btn)
        del_btn = QPushButton(tr('Ziel löschen'))
        del_btn.clicked.connect(self._on_delete_goal)
        btn_box.addWidget(del_btn)
        up_btn = QPushButton(tr('▲ Nach oben'))
        up_btn.clicked.connect(lambda: self._on_move_goal_priority(-1))
        btn_box.addWidget(up_btn)
        down_btn = QPushButton(tr('▼ Nach unten'))
        down_btn.clicked.connect(lambda: self._on_move_goal_priority(1))
        btn_box.addWidget(down_btn)
        btn_box.addStretch()

        self._refresh_goals_tab()
        return widget

    def _refresh_goals_tab(self):
        goals = self.store.list_goals()
        self.goal_table.setRowCount(len(goals))
        for i, g in enumerate(goals):
            item = QTableWidgetItem(f"{i + 1}. {g['name']}")
            item.setData(Qt.UserRole, g["id"])
            self.goal_table.setItem(i, 0, item)
            self.goal_table.setItem(i, 1, QTableWidgetItem(fmt_amount(g["target_amount"])))
            self.goal_table.setItem(i, 2, QTableWidgetItem(fmt_amount(g["current_amount"])))
            self.goal_table.setItem(i, 3, QTableWidgetItem(g["target_date"] or "–"))
            fraction = int(min(100, (g["current_amount"] / g["target_amount"]) * 100)) \
                if g["target_amount"] else 0
            progress = BarCell(fraction, theme.current()["accent"])
            self.goal_table.setCellWidget(i, 4, progress)

    def _selected_goal(self):
        row = self.goal_table.currentRow()
        if row < 0:
            return None
        item = self.goal_table.item(row, 0)
        return {"id": item.data(Qt.UserRole), "name": item.text().split(". ", 1)[-1]}

    def _on_move_goal_priority(self, direction):
        selected = self._selected_goal()
        if not selected:
            return
        if self.store.move_goal_priority(selected["id"], direction):
            self._refresh_goals_tab()
            for row in range(self.goal_table.rowCount()):
                if self.goal_table.item(row, 0).data(Qt.UserRole) == selected["id"]:
                    self.goal_table.selectRow(row)
                    break

    def _on_add_goal(self):
        dialog = GoalDialog(self)
        if dialog.exec() == GoalDialog.Accepted:
            data = dialog.get_data()
            if data:
                self.store.add_goal(**data)
                self._refresh_goals_tab()

    def _on_add_contribution(self):
        selected = self._selected_goal()
        if not selected:
            return
        dialog = ContributionDialog(self, selected["name"])
        if dialog.exec() == ContributionDialog.Accepted:
            amount = dialog.get_amount()
            book_as_transaction = dialog.get_book_as_transaction()
            if amount:
                self.store.add_contribution(
                    selected["id"], datetime.date.today().isoformat(), amount,
                    create_transaction=book_as_transaction, goal_name=selected["name"],
                )
                self._refresh_goals_tab()
                if book_as_transaction:
                    self._after_transactions_changed()
                    self._refresh_stats()

    def _on_delete_goal(self):
        selected = self._selected_goal()
        if selected:
            self.store.delete_goal(selected["id"])
            self._refresh_goals_tab()

    # =====================================================================
    # Tab 4: Finanzplanung (Notgroschen + Anlage-Empfehlung)
    # =====================================================================

    def _build_planning_tab(self):
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        outer.setWidget(container)

        # -- Abschnitt: Kontostand --
        balance_group = QGroupBox(tr('Kontostand'))
        layout.addWidget(balance_group)
        balance_grid = QGridLayout(balance_group)

        balance_grid.addWidget(QLabel(tr('Stichtag:')), 0, 0)
        existing_amount, existing_date = self.store.get_starting_balance()
        self.balance_date_edit = QDateEdit()
        self.balance_date_edit.setCalendarPopup(True)
        self.balance_date_edit.setDisplayFormat("dd.MM.yyyy")
        if existing_date:
            self.balance_date_edit.setDate(QDate.fromString(existing_date, "yyyy-MM-dd"))
        else:
            self.balance_date_edit.setDate(QDate.currentDate())
        balance_grid.addWidget(self.balance_date_edit, 0, 1)

        balance_grid.addWidget(QLabel(tr('Kontostand an diesem Tag (€):')), 1, 0)
        self.balance_amount_spin = QDoubleSpinBox()
        self.balance_amount_spin.setRange(-1_000_000, 10_000_000)
        self.balance_amount_spin.setDecimals(2)
        self.balance_amount_spin.setValue(existing_amount or 0)
        balance_grid.addWidget(self.balance_amount_spin, 1, 1)
        balance_grid.addWidget(make_help_button(
            tr('Dein tatsächliches Kontoguthaben an einem bestimmten Tag (z. B. heute) – nicht nur die in Plutos erfassten Buchungen. Der aktuelle Kontostand wird daraus als Startguthaben + alle Buchungen ab diesem Stichtag berechnet, du musst also nicht jede einzelne Buchung seit Kontoeröffnung nacherfassen.')
        ), 1, 2)

        save_balance_btn = QPushButton(tr('Speichern'))
        save_balance_btn.clicked.connect(self._on_save_starting_balance)
        balance_grid.addWidget(save_balance_btn, 2, 0, 1, 3)

        self.current_balance_label = QLabel()
        self.current_balance_label.setWordWrap(True)
        balance_grid.addWidget(self.current_balance_label, 3, 0, 1, 3)

        self.pocket_check = QCheckBox(tr('Notgroschen als eigenes Unterkonto führen (z. B. Tagesgeld)'))
        self.pocket_check.setChecked(self.store.notgroschen_pocket_enabled())
        self.pocket_check.toggled.connect(self._on_toggle_pocket)
        balance_grid.addWidget(self.pocket_check, 5, 0, 1, 3)

        apply_balance_btn = QPushButton(
            tr('Aktuellen Kontostand als Startkapital in der Empfehlung übernehmen'))
        apply_balance_btn.clicked.connect(self._on_apply_balance_to_recommendation)
        balance_grid.addWidget(apply_balance_btn, 4, 0, 1, 3)

        balance_hint = QLabel(
            tr('Praktisch, wenn du gerade erst anfängst, für etwas zu sparen, einen Notgroschen aufzubauen oder in ETFs zu investieren: so zählt dein tatsächlich vorhandenes Geld, nicht nur das, was du seit Nutzung von Plutos gebucht hast.')
        )
        balance_hint.setWordWrap(True)
        balance_grid.addWidget(balance_hint, 6, 0, 1, 3)

        # -- Abschnitt A: Notgroschen --
        ng_group = QGroupBox(tr('Notgroschen einrichten (3–6 Monate Fixkosten)'))
        layout.addWidget(ng_group)
        ng_grid = QGridLayout(ng_group)

        ng_grid.addWidget(QLabel(tr('Monatliche Fixkosten (€):')), 0, 0)
        self.planning_fixed_costs_spin = QDoubleSpinBox()
        self.planning_fixed_costs_spin.setRange(0, 100_000)
        self.planning_fixed_costs_spin.setDecimals(2)
        self.planning_fixed_costs_spin.setValue(self.store.estimate_monthly_fixed_costs())
        self.planning_fixed_costs_spin.valueChanged.connect(self._update_notgroschen_preview)
        ng_grid.addWidget(self.planning_fixed_costs_spin, 0, 1)
        recalc_btn = QPushButton(tr('Aus wiederkehrenden Ausgaben schätzen'))
        recalc_btn.clicked.connect(self._on_recalc_fixed_costs)
        ng_grid.addWidget(recalc_btn, 0, 2)

        ng_grid.addWidget(QLabel(tr('Ziel: Monate an Fixkosten:')), 1, 0)
        self.planning_months_spin = QSpinBox()
        self.planning_months_spin.setRange(1, 12)
        self.planning_months_spin.setValue(4)
        self.planning_months_spin.valueChanged.connect(self._update_notgroschen_preview)
        ng_grid.addWidget(self.planning_months_spin, 1, 1)
        ng_grid.addWidget(make_help_button(
            tr('Wie viele Monate an Fixkosten der Notgroschen abdecken soll – eine Reserve für unerwartete Ausgaben oder Einkommensausfälle (z. B. Jobverlust, Reparaturen). 3 Monate gelten als absolutes Minimum, 6 Monate als komfortabel; bei unsicherem Einkommen (Selbstständigkeit) eher mehr.')
        ), 1, 2)

        fixed_hint = QLabel(
            tr('Vorbelegt aus deinen laufenden wiederkehrenden Ausgaben-Vorlagen (Miete, Versicherungen, …). Frei anpassbar, falls nicht alle Fixkosten als wiederkehrende Buchung erfasst sind.')
        )
        fixed_hint.setWordWrap(True)
        ng_grid.addWidget(fixed_hint, 2, 0, 1, 3)

        self.notgroschen_preview_label = QLabel()
        self.notgroschen_preview_label.setWordWrap(True)
        ng_grid.addWidget(self.notgroschen_preview_label, 3, 0, 1, 3)

        ng_create_btn = QPushButton(tr('Notgroschen-Ziel anlegen/aktualisieren'))
        ng_create_btn.clicked.connect(self._on_create_or_update_notgroschen)
        ng_grid.addWidget(ng_create_btn, 4, 0, 1, 3)

        # -- Abschnitt B: Anlage-Empfehlung --
        rec_group = QGroupBox(tr('Anlage-Empfehlung (einfache Faustregel)'))
        layout.addWidget(rec_group)
        rec_grid = QGridLayout(rec_group)

        rec_grid.addWidget(QLabel(tr('Netto-Einkommen (monatlich, €):')), 0, 0)
        self.planning_income_spin = QDoubleSpinBox()
        self.planning_income_spin.setRange(0, 1_000_000)
        self.planning_income_spin.setDecimals(2)
        self.planning_income_spin.setValue(2500)
        rec_grid.addWidget(self.planning_income_spin, 0, 1)

        rec_grid.addWidget(QLabel(tr('Startkapital (€):')), 1, 0)
        self.planning_capital_spin = QDoubleSpinBox()
        self.planning_capital_spin.setRange(0, 10_000_000)
        self.planning_capital_spin.setDecimals(2)
        rec_grid.addWidget(self.planning_capital_spin, 1, 1)

        rec_grid.addWidget(QLabel(tr('Freizeit-/Pufferbudget (% vom Netto):')), 2, 0)
        self.planning_leisure_percent_spin = QDoubleSpinBox()
        self.planning_leisure_percent_spin.setRange(0, 50)
        self.planning_leisure_percent_spin.setValue(10)
        rec_grid.addWidget(self.planning_leisure_percent_spin, 2, 1)
        rec_grid.addWidget(make_help_button(
            tr('Anteil des Netto-Einkommens, der für Freizeit, Hobbys oder als spontaner finanzieller Puffer reserviert bleibt, statt komplett auf Notgroschen/Sparziele/ETF verteilt zu werden. Rein informativ – wird nirgends automatisch als Buchung angelegt.')
        ), 2, 2)

        self.planning_include_goals_check = QCheckBox(
            tr('Weitere Sparziele einbeziehen (Priorität siehe Sparziele-Tab)'))
        self.planning_include_goals_check.setChecked(True)
        rec_grid.addWidget(self.planning_include_goals_check, 3, 0, 1, 3)

        self.planning_risk_check = QCheckBox(
            tr('Risikoprofil/Anlagehorizont für den ETF-Anteil berücksichtigen (optional)'))
        self.planning_risk_check.toggled.connect(self._on_risk_toggle_changed)
        rec_grid.addWidget(self.planning_risk_check, 4, 0, 1, 3)

        rec_grid.addWidget(QLabel(tr('Anlagehorizont (Jahre):')), 5, 0)
        self.planning_horizon_spin = QSpinBox()
        self.planning_horizon_spin.setRange(0, 60)
        self.planning_horizon_spin.setValue(10)
        self.planning_horizon_spin.setEnabled(False)
        rec_grid.addWidget(self.planning_horizon_spin, 5, 1)
        rec_grid.addWidget(make_help_button(
            tr('Wie viele Jahre das Geld voraussichtlich investiert bleibt, bevor es gebraucht wird. Kurzer Horizont = höheres Risiko, dass ein Kurseinbruch sich nicht mehr erholt, bevor das Geld gebraucht wird – daher bei kurzem Horizont ein kleinerer ETF-Anteil.')
        ), 5, 2)

        rec_grid.addWidget(QLabel(tr('Risikoprofil:')), 6, 0)
        self.planning_risk_combo = QComboBox()
        self.planning_risk_combo.addItem(tr('Konservativ'), "konservativ")
        self.planning_risk_combo.addItem(tr('Ausgewogen'), "ausgewogen")
        self.planning_risk_combo.addItem(tr('Offensiv'), "offensiv")
        self.planning_risk_combo.setCurrentIndex(1)
        self.planning_risk_combo.setEnabled(False)
        rec_grid.addWidget(self.planning_risk_combo, 6, 1)
        rec_grid.addWidget(make_help_button(
            tr('Wie viel Wertschwankung (und damit Verlustrisiko) du bereit bist einzugehen, um langfristig höhere Renditechancen zu haben. Konservativ = mehr Sicherheitsreserve, weniger ETF-Anteil; offensiv = mehr ETF-Anteil, mehr Schwankung.')
        ), 6, 2)

        calc_rec_btn = QPushButton(tr('Empfehlung berechnen'))
        calc_rec_btn.clicked.connect(self._on_calculate_recommendation)
        rec_grid.addWidget(calc_rec_btn, 7, 0, 1, 3)

        self.recommendation_label = QLabel()
        self.recommendation_label.setWordWrap(True)
        rec_grid.addWidget(self.recommendation_label, 8, 0, 1, 3)

        action_box = QHBoxLayout()
        rec_grid.addLayout(action_box, 9, 0, 1, 3)
        apply_etf_btn = QPushButton(tr('Monatliche ETF-Rate übernehmen'))
        apply_etf_btn.clicked.connect(self._on_apply_recommendation_to_etf)
        action_box.addWidget(apply_etf_btn)
        apply_capital_btn = QPushButton(tr('Startkapital-Anteile als Fortschritt vormerken'))
        apply_capital_btn.clicked.connect(self._on_apply_capital_to_goals)
        action_box.addWidget(apply_capital_btn)
        action_box.addStretch()

        self.apply_capital_as_transaction_check = QCheckBox(
            tr('Dabei auch als Buchung verbuchen (Kontostand sinkt entsprechend)'))
        self.apply_capital_as_transaction_check.setChecked(True)
        rec_grid.addWidget(self.apply_capital_as_transaction_check, 10, 0, 1, 3)

        capital_hint = QLabel(
            tr('Wichtig: Ohne diese Buchung bleibt dein Kontostand oben unverändert, obwohl die Sparziele-Fortschritte steigen – dasselbe Geld würde dir beim nächsten Mal fälschlich erneut als Startkapital angeboten. Häkchen nur entfernen, wenn das eingegebene Startkapital NICHT aus deinem hinterlegten Kontostand stammt (z. B. separates Erbe/Depot, das dort nicht mitgezählt wird).')
        )
        capital_hint.setWordWrap(True)
        rec_grid.addWidget(capital_hint, 11, 0, 1, 3)

        disclaimer = QLabel(
            tr('Diese Aufteilung folgt der gängigen Faustregel „Notgroschen (und ggf. weitere Ziele) vor Investieren“ sowie einer einfachen Horizont-/Risiko-Faustregel für den ETF-Anteil. Beides sind transparente Modellrechnungen – KEINE individuelle Finanzberatung. Sie berücksichtigen weder Schulden noch Steuern noch deine tatsächliche persönliche Risikotragfähigkeit. Alle Werte lassen sich frei anpassen; für eine verbindliche Einschätzung wende dich an eine unabhängige Finanzberatung.')
        )
        disclaimer.setWordWrap(True)
        small_font = disclaimer.font()
        small_font.setPointSize(max(8, small_font.pointSize() - 1))
        disclaimer.setFont(small_font)
        rec_grid.addWidget(disclaimer, 12, 0, 1, 3)

        layout.addStretch()
        self._update_notgroschen_preview()
        self._refresh_current_balance_display()
        return outer

    def _on_save_starting_balance(self):
        date_iso = self.balance_date_edit.date().toString("yyyy-MM-dd")
        self.store.set_starting_balance(self.balance_amount_spin.value(), date_iso)
        self._refresh_current_balance_display()

    def _refresh_current_balance_display(self):
        if not hasattr(self, "current_balance_label"):
            return
        balance = self.store.get_current_account_balance()
        if balance is None:
            self.current_balance_label.setText(
                tr('Noch kein Kontostand hinterlegt – oben Stichtag und Betrag eintragen und speichern.')
            )
        else:
            text = tr('Aktueller Kontostand (berechnet): {0}').format(fmt_amount(balance))
            bd = self.store.get_balance_breakdown()
            if bd and self.store.notgroschen_pocket_enabled():
                text = (tr('Girokonto: {0}\nNotgroschen-Unterkonto: {1}\nGesamt: {2}').format(fmt_amount(bd['giro']), fmt_amount(bd['pocket']), fmt_amount(bd['total'])))
            self.current_balance_label.setText(text)

    def _on_toggle_pocket(self, checked):
        self.store.set_notgroschen_pocket(checked)
        self._refresh_current_balance_display()

    def _on_apply_balance_to_recommendation(self):
        balance = self.store.get_current_account_balance()
        if balance is not None:
            self.planning_capital_spin.setValue(max(0.0, balance))

    def _on_recalc_fixed_costs(self):
        self.planning_fixed_costs_spin.setValue(self.store.estimate_monthly_fixed_costs())

    def _update_notgroschen_preview(self):
        if not hasattr(self, "notgroschen_preview_label"):
            return
        fixed = self.planning_fixed_costs_spin.value()
        months = self.planning_months_spin.value()
        target = fixed * months
        existing = self.store.get_goal_by_name("Notgroschen")
        if existing:
            status = (tr('Bestehendes Sparziel „Notgroschen“: {0} von aktuell {1} angespart.').format(fmt_amount(existing['current_amount']), fmt_amount(existing['target_amount'])))
        else:
            status = tr('Noch kein Sparziel „Notgroschen“ angelegt.')
        self.notgroschen_preview_label.setText(
            tr('Zielbetrag bei {0} Monaten Fixkosten: {1}\n{2}').format(months, fmt_amount(target), status)
        )

    def _on_create_or_update_notgroschen(self):
        fixed = self.planning_fixed_costs_spin.value()
        months = self.planning_months_spin.value()
        target = fixed * months
        existing = self.store.get_goal_by_name("Notgroschen")
        if existing:
            self.store.update_goal_target(existing["id"], target)
        else:
            self.store.add_goal("Notgroschen", target, None)
        self._update_notgroschen_preview()
        self._refresh_goals_tab()

    def _on_risk_toggle_changed(self, active):
        self.planning_horizon_spin.setEnabled(active)
        self.planning_risk_combo.setEnabled(active)

    def _on_calculate_recommendation(self):
        net_income = self.planning_income_spin.value()
        capital = self.planning_capital_spin.value()
        leisure = net_income * (self.planning_leisure_percent_spin.value() / 100)
        fixed = self.planning_fixed_costs_spin.value()
        months = self.planning_months_spin.value()
        ng_target = fixed * months

        if self.planning_include_goals_check.isChecked():
            all_goals = self.store.list_goals()
            goals_input = []
            has_notgroschen = any(g["name"] == "Notgroschen" for g in all_goals)
            if not has_notgroschen:
                goals_input.append({"id": None, "name": "Notgroschen",
                                     "target_amount": ng_target, "current_amount": 0.0})
            for g in all_goals:
                target = ng_target if g["name"] == "Notgroschen" else g["target_amount"]
                goals_input.append({
                    "id": g["id"], "name": g["name"],
                    "target_amount": target, "current_amount": g["current_amount"],
                })
        else:
            ng_existing = self.store.get_goal_by_name("Notgroschen")
            ng_current = ng_existing["current_amount"] if ng_existing else 0.0
            goals_input = [{
                "id": ng_existing["id"] if ng_existing else None,
                "name": "Notgroschen", "target_amount": ng_target, "current_amount": ng_current,
            }]

        rec = FinanceStore.recommend_allocation_multi(
            net_income=net_income, monthly_fixed_costs=fixed, leisure_amount=leisure,
            starting_capital=capital, goals=goals_input,
        )

        if self.planning_risk_check.isChecked():
            horizon = self.planning_horizon_spin.value()
            profile = self.planning_risk_combo.currentData()
            share = FinanceStore.suggest_equity_share(horizon, profile)
            rec["risk_applied"] = True
            rec["equity_share_percent"] = share
            rec["monthly_to_equity"] = round(rec["monthly_to_etf"] * share / 100, 2)
            rec["monthly_to_safety"] = round(rec["monthly_to_etf"] - rec["monthly_to_equity"], 2)
            rec["capital_to_equity"] = round(rec["capital_to_etf"] * share / 100, 2)
            rec["capital_to_safety"] = round(rec["capital_to_etf"] - rec["capital_to_equity"], 2)
        else:
            rec["risk_applied"] = False

        self._current_recommendation = rec

        lines = [
            tr('Monatlich verfügbar (Netto abzüglich Fixkosten von {0} und Freizeitbudget von {1}): {2}').format(fmt_amount(fixed), fmt_amount(leisure), fmt_amount(rec['monthly_available'])),
            tr('Startkapital: {0}').format(fmt_amount(capital)),
            "",
        ]
        for g in rec["goals"]:
            if g["fully_funded"]:
                status = tr("bereits voll gedeckt") if g["gap_before"] <= 0 else tr('wird damit voll gedeckt')
            else:
                eta = (tr(', ca. {0} Monate bei diesem Tempo').format(g['months_to_fill'])
                       if g["months_to_fill"] else tr(', reicht mit aktuellem Tempo noch nicht'))
                status = tr('Lücke bleibt: {0}{1}').format(fmt_amount(g['remaining_gap']), eta)
            lines.append(
                tr('• {0} (Ziel: {1}, bereits {2} vorhanden): {3} aus Startkapital, {4}/Monat – {5}').format(g['name'], fmt_amount(g['target_amount']), fmt_amount(g['current_amount']), fmt_amount(g['capital_allocated']), fmt_amount(g['monthly_allocated']), status)
            )

        lines.append("")
        if not rec["all_goals_funded"]:
            # Noch nicht alles angespart: Hinweis, was danach investierbar wäre.
            eta = (tr(' (ca. {0} Monate bei diesem Tempo)').format(rec['months_until_funded'])
                   if rec["months_until_funded"] else "")
            lines.append("\x00" + tr('Rest zum Investieren: aktuell {0}, weil noch nicht alle Sparziele (z. B. der Notgroschen) angespart sind.').format(fmt_amount(0)))
            if rec["monthly_available"] > 0:
                lines.append("\x00" + tr('Sobald sie gedeckt sind{0}, könntest du die folgenden Beträge investieren:').format(eta))
                if rec["risk_applied"]:
                    future_equity = round(rec["monthly_available"] * rec["equity_share_percent"] / 100, 2)
                    future_safety = round(rec["monthly_available"] - future_equity, 2)
                    lines.append(tr('  → ETF-Sparplan: {0}/Monat (empfohlener ETF-Anteil {1}% bei {2} Jahren Horizont, Profil „{3}“)').format(fmt_amount(future_equity), rec['equity_share_percent'], int(self.planning_horizon_spin.value()), self.planning_risk_combo.currentText()))
                    lines.append(tr('  → Sicherheitsreserve (z. B. Tagesgeld): {0}/Monat').format(fmt_amount(future_safety)))
                else:
                    lines.append(tr('  → z. B. ETF-Sparplan: {0}/Monat').format(fmt_amount(rec['monthly_available'])))
        elif rec["risk_applied"]:
            lines.append(
                tr('Rest zum Investieren – bei {0} Jahren Horizont, Profil „{1}“: empfohlener ETF-Anteil {2}%, Rest als Sicherheitsreserve:').format(int(self.planning_horizon_spin.value()), self.planning_risk_combo.currentText(), rec['equity_share_percent'])
            )
            lines.append(
                tr('  → ETF-Sparplan: {0}/Monat, {1} Startkapital').format(fmt_amount(rec['monthly_to_equity']), fmt_amount(rec['capital_to_equity']))
            )
            lines.append(
                tr('  → Sicherheitsreserve (z. B. Tagesgeld): {0}/Monat, {1} Startkapital').format(fmt_amount(rec['monthly_to_safety']), fmt_amount(rec['capital_to_safety']))
            )
        if rec["all_goals_funded"] and not rec["risk_applied"]:
            lines.append(
                tr('Rest zum Investieren (z. B. ETF-Sparplan): {0}/Monat, {1} Startkapital').format(fmt_amount(rec['monthly_to_etf']), fmt_amount(rec['capital_to_etf']))
            )

        warn = theme.current()["warn"]
        html_lines = []
        for ln in lines:
            if ln.startswith("\x00"):
                html_lines.append(f'<b style="color:{warn};">{_html.escape(ln[1:])}</b>')
            else:
                html_lines.append(_html.escape(ln).replace("  ", "&nbsp;&nbsp;"))
        self.recommendation_label.setTextFormat(Qt.RichText)
        self.recommendation_label.setText("<br>".join(html_lines))

    def _on_apply_recommendation_to_etf(self):
        if not self._current_recommendation:
            return
        rec = self._current_recommendation
        amount = rec["monthly_to_equity"] if rec.get("risk_applied") else rec["monthly_to_etf"]
        if amount <= 0:
            return
        self.etf_amount_spin.setValue(amount)
        self.tabs.setCurrentIndex(self.etf_tab_index)

    def _on_apply_capital_to_goals(self):
        if not self._current_recommendation:
            return
        book_as_transaction = self.apply_capital_as_transaction_check.isChecked()
        applied_any = False
        for g in self._current_recommendation["goals"]:
            amount = g["capital_allocated"]
            if amount <= 0:
                continue
            goal_id = g["id"]
            if goal_id is None:
                self._on_create_or_update_notgroschen()
                created = self.store.get_goal_by_name("Notgroschen")
                goal_id = created["id"] if created else None
                if goal_id is None:
                    continue
            self.store.add_contribution(
                goal_id, datetime.date.today().isoformat(), amount,
                create_transaction=book_as_transaction, goal_name=g["name"],
            )
            applied_any = True
        if applied_any:
            self._update_notgroschen_preview()
            self._refresh_goals_tab()
            if book_as_transaction:
                self._after_transactions_changed()
            else:
                self._refresh_current_balance_display()

    # =====================================================================
    # Tab 5: ETF-Sparplan
    # =====================================================================

    def _build_etf_tab(self):
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        outer.setWidget(container)

        form_group = QGroupBox(tr('Sparplan'))
        layout.addWidget(form_group)
        form = QGridLayout(form_group)

        form.addWidget(QLabel(tr('Name:')), 0, 0)
        self.etf_name_edit = QLineEdit("Mein ETF-Sparplan")
        form.addWidget(self.etf_name_edit, 0, 1)

        form.addWidget(QLabel(tr('Monatliche Rate (€):')), 1, 0)
        self.etf_amount_spin = QDoubleSpinBox()
        self.etf_amount_spin.setRange(1, 100_000)
        self.etf_amount_spin.setDecimals(2)
        self.etf_amount_spin.setValue(100)
        form.addWidget(self.etf_amount_spin, 1, 1)

        form.addWidget(QLabel(tr('Erwartete jährl. Rendite (%):')), 2, 0)
        self.etf_return_spin = QDoubleSpinBox()
        self.etf_return_spin.setRange(-20, 30)
        self.etf_return_spin.setValue(6.0)
        form.addWidget(self.etf_return_spin, 2, 1)

        form.addWidget(QLabel(tr('Laufzeit (Jahre):')), 3, 0)
        self.etf_years_spin = QSpinBox()
        self.etf_years_spin.setRange(1, 60)
        self.etf_years_spin.setValue(10)
        form.addWidget(self.etf_years_spin, 3, 1)

        form.addWidget(QLabel(tr('Jährliche Erhöhung der Sparrate (%):')), 4, 0)
        self.etf_increase_spin = QDoubleSpinBox()
        self.etf_increase_spin.setRange(0, 50)
        form.addWidget(self.etf_increase_spin, 4, 1)
        form.addWidget(make_help_button(
            tr('Erhöht die monatliche Sparrate jedes Jahr um diesen Prozentsatz, z. B. um eine erwartete Gehaltssteigerung nachzubilden. 0 % = die Sparrate bleibt über die gesamte Laufzeit konstant.')
        ), 4, 2)

        form.addWidget(QLabel(tr('Maximale Sparrate (€, 0 = kein Deckel):')), 5, 0)
        self.etf_cap_spin = QDoubleSpinBox()
        self.etf_cap_spin.setRange(0, 100_000)
        form.addWidget(self.etf_cap_spin, 5, 1)
        form.addWidget(make_help_button(
            tr('Obergrenze für die Sparrate, falls sie sich durch die jährliche Erhöhung sonst unbegrenzt weiter steigern würde. 0 bedeutet: kein Deckel, die Rate wächst ungebremst weiter.')
        ), 5, 2)

        # -- Steuer-Einstellungen --
        tax_group = QGroupBox(tr('Deutsche Kapitalertragsteuer (vereinfacht, anpassbar)'))
        layout.addWidget(tax_group)
        tax_grid = QGridLayout(tax_group)

        self.etf_vorab_check = QCheckBox(
            tr('Jährliche Vorabpauschale simulieren (statt Einmalbesteuerung am Laufzeitende)'))
        self.etf_vorab_check.toggled.connect(self._on_vorab_toggled)
        tax_grid.addWidget(self.etf_vorab_check, 0, 0, 1, 3)

        tax_grid.addWidget(QLabel(tr('Basiszins (%, jährlich vom BMF festgelegt):')), 1, 0)
        self.etf_basiszins_spin = QDoubleSpinBox()
        self.etf_basiszins_spin.setRange(0, 15)
        self.etf_basiszins_spin.setValue(2.55)
        self.etf_basiszins_spin.setEnabled(False)
        tax_grid.addWidget(self.etf_basiszins_spin, 1, 1)
        tax_grid.addWidget(make_help_button(
            tr('Zinssatz, den das Bundesfinanzministerium jährlich für die Vorabpauschale-Berechnung festlegt (orientiert sich an langfristigen Bundesanleihen). Ändert sich jährlich – der voreingestellte Wert ist nur ein Richtwert.')
        ), 1, 2)

        tax_grid.addWidget(QLabel(tr('Teilfreistellung (%):')), 2, 0)
        self.etf_teilfreistellung_spin = QDoubleSpinBox()
        self.etf_teilfreistellung_spin.setRange(0, 60)
        self.etf_teilfreistellung_spin.setValue(30)
        tax_grid.addWidget(self.etf_teilfreistellung_spin, 2, 1)
        tax_grid.addWidget(make_help_button(
            tr('Anteil des Fondsgewinns, der steuerfrei bleibt (§20 InvStG). 30 % ist der übliche Satz für Aktienfonds-ETFs mit mindestens 51 % Aktienquote. Bei Anleihen-ETFs 0 %, bei Mischfonds meist 15 %, bei Immobilienfonds 60–80 %.')
        ), 2, 2)

        tax_grid.addWidget(QLabel(tr('Kapitalertragsteuer (%):')), 3, 0)
        self.etf_kest_spin = QDoubleSpinBox()
        self.etf_kest_spin.setRange(0, 50)
        self.etf_kest_spin.setValue(25)
        tax_grid.addWidget(self.etf_kest_spin, 3, 1)
        tax_grid.addWidget(make_help_button(
            tr('Die pauschale Abgeltungsteuer auf Kapitalerträge in Deutschland, gesetzlich 25 %.')
        ), 3, 2)

        tax_grid.addWidget(QLabel(tr('Solidaritätszuschlag (%):')), 4, 0)
        self.etf_soli_spin = QDoubleSpinBox()
        self.etf_soli_spin.setRange(0, 20)
        self.etf_soli_spin.setValue(5.5)
        tax_grid.addWidget(self.etf_soli_spin, 4, 1)
        tax_grid.addWidget(make_help_button(
            tr('Zuschlag von 5,5 % auf die Kapitalertragsteuer (nicht auf den Gewinn selbst) – gesetzlich vorgegeben.')
        ), 4, 2)

        tax_grid.addWidget(QLabel(tr('Sparerpauschbetrag (€/Jahr):')), 5, 0)
        self.etf_pauschbetrag_spin = QDoubleSpinBox()
        self.etf_pauschbetrag_spin.setRange(0, 5000)
        self.etf_pauschbetrag_spin.setDecimals(0)
        self.etf_pauschbetrag_spin.setValue(1000)
        tax_grid.addWidget(self.etf_pauschbetrag_spin, 5, 1)
        tax_grid.addWidget(make_help_button(
            tr('Steuerfreibetrag auf Kapitalerträge: 1.000 € pro Jahr bei Einzelveranlagung, 2.000 € bei Zusammenveranlagung (Ehepaare, Stand 2023).')
        ), 5, 2)

        self.etf_tax_hint = QLabel()
        self.etf_tax_hint.setWordWrap(True)
        self._update_tax_hint()
        tax_grid.addWidget(self.etf_tax_hint, 6, 0, 1, 3)

        calc_btn = QPushButton(tr('Berechnen & Speichern').replace("&", "&&"))
        calc_btn.clicked.connect(self._on_calculate_etf)
        layout.addWidget(calc_btn)

        self.etf_summary_label = QLabel()
        self.etf_summary_label.setWordWrap(True)
        layout.addWidget(self.etf_summary_label)

        scen_box = QHBoxLayout()
        layout.addLayout(scen_box)
        scen_box.addWidget(QLabel(tr('<b>Szenarien</b> – Rendite ±')))
        self.etf_spread_spin = QDoubleSpinBox()
        self.etf_spread_spin.setRange(0, 20)
        self.etf_spread_spin.setDecimals(1)
        self.etf_spread_spin.setValue(2.0)
        self.etf_spread_spin.setSuffix(tr(' Prozentpunkte'))
        self.etf_spread_spin.valueChanged.connect(self._refresh_etf_scenarios)
        scen_box.addWidget(self.etf_spread_spin)
        scen_box.addWidget(QLabel(tr('Inflation:')))
        self.etf_inflation_spin = QDoubleSpinBox()
        self.etf_inflation_spin.setRange(0, 15)
        self.etf_inflation_spin.setDecimals(1)
        self.etf_inflation_spin.setValue(2.0)
        self.etf_inflation_spin.setSuffix(tr(' % p.a.'))
        self.etf_inflation_spin.valueChanged.connect(self._refresh_etf_scenarios)
        scen_box.addWidget(self.etf_inflation_spin)
        scen_box.addWidget(make_help_button(
            tr('Zeigt, wie stark das Ergebnis streuen kann, wenn die Rendite besser oder schlechter ausfällt als angenommen. „Kaufkraftbereinigt“ zieht die Inflation ab und gibt den Endwert nach Steuern in heutiger Kaufkraft an. Das sind Rechenbeispiele, keine Prognose und keine Anlageempfehlung.')))
        scen_box.addStretch()

        self.etf_scenario_table = QTableWidget(3, 5)
        self.etf_scenario_table.setHorizontalHeaderLabels(
            [tr('Szenario'), tr('Rendite p.a.'), tr('Endwert vor Steuern'), tr('Endwert nach Steuern'),
             tr('nach Steuern, heutige Kaufkraft')])
        self.etf_scenario_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.etf_scenario_table.verticalHeader().setVisible(False)
        self.etf_scenario_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.etf_scenario_table.setMaximumHeight(120)
        layout.addWidget(self.etf_scenario_table)

        self.etf_result_table = QTableWidget(0, 5)
        self.etf_result_table.setHorizontalHeaderLabels(
            [tr('Jahr'), tr('Sparrate'), tr('Eingezahlt'), tr('Wert'), tr('Gewinn')])
        self.etf_result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.etf_result_table.setMaximumHeight(220)
        layout.addWidget(self.etf_result_table)

        plan_manage_box = QHBoxLayout()
        layout.addLayout(plan_manage_box)
        plan_manage_box.addWidget(QLabel(tr('Gespeicherter Plan:')))
        self.etf_saved_plans_combo = QComboBox()
        plan_manage_box.addWidget(self.etf_saved_plans_combo, 1)
        del_btn = QPushButton(tr('Löschen'))
        del_btn.clicked.connect(self._on_delete_etf_plan)
        plan_manage_box.addWidget(del_btn)

        layout.addWidget(QLabel(tr('Vergleich gespeicherter Sparpläne (Wertentwicklung, vor Steuern):')))
        self.etf_compare_widget = EtfComparisonWidget()
        layout.addWidget(self.etf_compare_widget)

        self._refresh_etf_plan_selector()
        self._refresh_etf_comparison()
        for spin in (self.etf_amount_spin, self.etf_return_spin, self.etf_years_spin,
                     self.etf_increase_spin, self.etf_cap_spin, self.etf_basiszins_spin,
                     self.etf_teilfreistellung_spin, self.etf_kest_spin, self.etf_soli_spin,
                     self.etf_pauschbetrag_spin):
            spin.valueChanged.connect(self._refresh_etf_scenarios)
        self._refresh_etf_scenarios()
        return outer

    def _refresh_etf_scenarios(self, *_args):
        if not hasattr(self, "etf_scenario_table"):
            return
        cap = self.etf_cap_spin.value()
        scenarios = FinanceStore.etf_scenarios(
            self.etf_amount_spin.value(), self.etf_return_spin.value(),
            self.etf_years_spin.value(),
            annual_increase_percent=self.etf_increase_spin.value(),
            max_monthly_amount=cap if cap > 0 else None,
            spread_percent=self.etf_spread_spin.value(),
            inflation_percent=self.etf_inflation_spin.value(),
            use_vorabpauschale=self.etf_vorab_check.isChecked(),
            basiszins_percent=self.etf_basiszins_spin.value(),
            teilfreistellung_percent=self.etf_teilfreistellung_spin.value(),
            kapitalertragsteuer_percent=self.etf_kest_spin.value(),
            soli_percent=self.etf_soli_spin.value(),
            sparerpauschbetrag=self.etf_pauschbetrag_spin.value(),
        )
        for row, sc in enumerate(scenarios):
            values = [sc["label"], f"{sc['annual_return']:.2f} %", fmt_amount(sc["value"]),
                      fmt_amount(sc["value_after_tax"]), fmt_amount(sc["real_value_after_tax"])]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.etf_scenario_table.setItem(row, col, item)

    def _on_vorab_toggled(self, active):
        self.etf_basiszins_spin.setEnabled(active)
        self._update_tax_hint()
        self._refresh_etf_scenarios()

    def _update_tax_hint(self):
        if self.etf_vorab_check.isChecked():
            text = (tr('Hinweis: Simuliert die jährliche Vorabpauschale (Basisertrag = Wert zu Jahresbeginn × Basiszins × 70 %, gedeckelt auf den tatsächlichen Wertzuwachs). Der Sparerpauschbetrag steht dabei JÄHRLICH neu zur Verfügung. Bereits versteuerte Beträge werden bei der Steuer am Laufzeitende angerechnet (keine Doppelbesteuerung). Kirchensteuer bleibt unberücksichtigt.'))
        else:
            text = (tr('Hinweis: Vereinfachte Rechnung ohne jährliche Vorabpauschale – Steuer wird pauschal auf den Gesamtgewinn am Laufzeitende angesetzt, mit dem Sparerpauschbetrag nur EINMALIG am Ende. Kirchensteuer bleibt unberücksichtigt.'))
        self.etf_tax_hint.setText(text)

    def _on_calculate_etf(self):
        name = self.etf_name_edit.text().strip() or "ETF-Sparplan"
        monthly_amount = self.etf_amount_spin.value()
        annual_return = self.etf_return_spin.value()
        years = self.etf_years_spin.value()
        increase = self.etf_increase_spin.value()
        cap = self.etf_cap_spin.value()
        cap = cap if cap > 0 else None

        teilfreistellung = self.etf_teilfreistellung_spin.value()
        kest = self.etf_kest_spin.value()
        soli = self.etf_soli_spin.value()
        pauschbetrag = self.etf_pauschbetrag_spin.value()

        if self.etf_vorab_check.isChecked():
            results, cumulative_pretaxed_gain = FinanceStore.project_etf_plan_with_vorabpauschale(
                monthly_amount, annual_return, years,
                annual_increase_percent=increase, max_monthly_amount=cap,
                basiszins_percent=self.etf_basiszins_spin.value(),
                teilfreistellung_percent=teilfreistellung,
                kapitalertragsteuer_percent=kest, soli_percent=soli,
                sparerpauschbetrag=pauschbetrag,
            )
            final = results[-1]
            tax = FinanceStore.apply_final_tax_with_vorabpauschale_credit(
                final["value"], final["invested"], cumulative_pretaxed_gain,
                teilfreistellung_percent=teilfreistellung,
                kapitalertragsteuer_percent=kest, soli_percent=soli,
                sparerpauschbetrag=pauschbetrag,
            )
            total_vorab_tax_paid = sum(r["tax_paid"] for r in results)
            vorab_note = (
                tr(' Während der Laufzeit wurden bereits {0} Steuern auf Vorabpauschalen gezahlt (im Endwert schon berücksichtigt); davon {1} Gewinn wurden bei der Steuer am Ende angerechnet.').format(fmt_amount(total_vorab_tax_paid), fmt_amount(cumulative_pretaxed_gain))
            )
        else:
            results = FinanceStore.project_etf_plan(
                monthly_amount, annual_return, years,
                annual_increase_percent=increase, max_monthly_amount=cap,
            )
            final = results[-1]
            tax = FinanceStore.apply_german_capital_gains_tax(
                final["value"], final["invested"],
                teilfreistellung_percent=teilfreistellung,
                kapitalertragsteuer_percent=kest, soli_percent=soli,
                sparerpauschbetrag=pauschbetrag,
            )
            vorab_note = ""

        self.etf_result_table.setRowCount(len(results))
        for row, r in enumerate(results):
            values = [str(r["year"]), fmt_amount(r["monthly_rate_amount"]),
                      fmt_amount(r["invested"]), fmt_amount(r["value"]), fmt_amount(r["gain"])]
            for col, value in enumerate(values):
                self.etf_result_table.setItem(row, col, QTableWidgetItem(value))

        value_after_tax = tax.get("value_after_tax")
        final_tax_amount = tax.get("final_tax", tax.get("tax"))
        self.etf_summary_label.setText(
            tr('Nach {0} Jahren bei {1:.2f}% p.a.: eingezahlt {2}, Endwert vor Abschluss-Steuer {3}, Gewinn {4}.\nSteuer bei (angenommenem) Verkauf: {5} → Endwert nach Steuern ca. {6}.{7}').format(years, annual_return, fmt_amount(final['invested']), fmt_amount(final['value']), fmt_amount(tax['gain']), fmt_amount(final_tax_amount), fmt_amount(value_after_tax), vorab_note)
        )

        self._refresh_etf_scenarios()

        self.current_etf_plan_id = self.store.add_etf_plan(
            name, monthly_amount, annual_return, datetime.date.today().isoformat(),
            years, annual_increase_percent=increase, max_monthly_amount=cap,
        )
        self._refresh_etf_plan_selector()
        self._refresh_etf_comparison()

    def _refresh_etf_plan_selector(self):
        self.etf_saved_plans_combo.clear()
        plans = self.store.list_etf_plans()
        for plan in plans:
            label = tr('{0} ({1} Jahre, {2})').format(plan['name'], plan['duration_years'], plan['start_date'])
            self.etf_saved_plans_combo.addItem(label, plan["id"])
        if plans:
            target_id = self.current_etf_plan_id or plans[-1]["id"]
            index = self.etf_saved_plans_combo.findData(target_id)
            self.etf_saved_plans_combo.setCurrentIndex(max(0, index))

    def _on_delete_etf_plan(self):
        plan_id = self.etf_saved_plans_combo.currentData()
        if plan_id is None:
            return
        self.store.delete_etf_plan(plan_id)
        if self.current_etf_plan_id == plan_id:
            self.current_etf_plan_id = None
            self.etf_result_table.setRowCount(0)
            self.etf_summary_label.setText("")
        self._refresh_etf_plan_selector()
        self._refresh_etf_comparison()

    def _refresh_etf_comparison(self):
        plans_data = []
        for i, plan in enumerate(self.store.list_etf_plans()):
            results = FinanceStore.project_etf_plan(
                plan["monthly_amount"], plan["annual_return_percent"], plan["duration_years"],
                annual_increase_percent=plan["annual_increase_percent"] or 0,
                max_monthly_amount=plan["max_monthly_amount"],
            )
            plans_data.append({
                "name": plan["name"],
                "color": color_for_index(i),
                "points": [(r["year"], r["value"]) for r in results],
            })
        if hasattr(self, "etf_compare_widget"):
            self.etf_compare_widget.set_data(plans_data)

    # =====================================================================
    # Tab 6: Auswertungen (Kreisdiagramm, Trend, Sankey)
    # =====================================================================

    def _build_stats_tab(self):
        root = QWidget()
        layout = QVBoxLayout(root)

        switcher_box = QHBoxLayout()
        layout.addLayout(switcher_box)
        switcher_box.addWidget(QLabel(tr('Ansicht:')))
        self.stats_view_combo = QComboBox()
        self.stats_view_combo.addItem(tr('Ausgaben nach Kategorie (Kreisdiagramm)'), "kategorien")
        self.stats_view_combo.addItem(tr('Einnahmen/Ausgaben-Trend'), "trend")
        self.stats_view_combo.addItem(tr('Geldfluss (Sankey-Diagramm)'), "fluss")
        self.stats_view_combo.addItem(tr('Kategorien vergleichen'), "vergleich")
        self.stats_view_combo.addItem(tr('Jahresübersicht (mit Vorjahr)'), "jahresvergleich")
        self.stats_view_combo.addItem(tr('Budgets im Jahr'), "budgetjahr")
        self.stats_view_combo.addItem(tr('Tags'), "tags")
        self.stats_view_combo.currentIndexChanged.connect(self._on_stats_view_changed)
        switcher_box.addWidget(self.stats_view_combo)
        switcher_box.addStretch()

        self.stats_stack = QStackedWidget()
        layout.addWidget(self.stats_stack)

        self.stats_stack.addWidget(self._build_pie_section())
        self.stats_stack.addWidget(self._build_trend_section())
        self.stats_stack.addWidget(self._build_sankey_section())
        self.stats_stack.addWidget(self._build_compare_section())
        self.stats_stack.addWidget(self._build_year_compare_section())
        self.stats_stack.addWidget(self._build_budget_year_section())
        self.stats_stack.addWidget(self._build_tags_section())

        self._refresh_stats()
        return root

    def _on_stats_view_changed(self, index):
        self.stats_stack.setCurrentIndex(index)

    def _build_pie_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)

        nav = QHBoxLayout()
        layout.addLayout(nav)
        nav.addWidget(QLabel(tr('Ausgaben nach Kategorie –')))
        prev_btn = QPushButton("◀")
        prev_btn.clicked.connect(lambda: self._shift_stats_month(-1))
        nav.addWidget(prev_btn)
        self.stats_month_label = QLabel()
        nav.addWidget(self.stats_month_label)
        next_btn = QPushButton("▶")
        next_btn.clicked.connect(lambda: self._shift_stats_month(1))
        nav.addWidget(next_btn)
        nav.addStretch()

        self.pie_widget = PieChartWidget()
        layout.addWidget(self.pie_widget)
        return section

    def _build_trend_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)

        nav = QHBoxLayout()
        layout.addLayout(nav)
        nav.addWidget(QLabel(tr('Trend – letzte')))
        self.trend_months_spin = QSpinBox()
        self.trend_months_spin.setRange(2, 24)
        self.trend_months_spin.setValue(6)
        self.trend_months_spin.valueChanged.connect(self._on_trend_months_changed)
        nav.addWidget(self.trend_months_spin)
        nav.addWidget(QLabel(tr('Monate (bezogen auf den gewählten Monat)')))
        nav.addStretch()
        legend = QLabel(tr('🟩 Einnahmen   🟥 Ausgaben'))
        nav.addWidget(legend)

        self.trend_widget = TrendChartWidget()
        layout.addWidget(self.trend_widget)
        return section

    def _build_sankey_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)

        nav = QHBoxLayout()
        layout.addLayout(nav)
        nav.addWidget(QLabel(tr('Geldfluss –')))
        prev_btn = QPushButton("◀")
        prev_btn.clicked.connect(lambda: self._shift_stats_month(-1))
        nav.addWidget(prev_btn)
        self.sankey_month_label = QLabel()
        nav.addWidget(self.sankey_month_label)
        next_btn = QPushButton("▶")
        next_btn.clicked.connect(lambda: self._shift_stats_month(1))
        nav.addWidget(next_btn)
        nav.addStretch()

        hint = QLabel(
    tr('\n    <font color="#aeb6c0">\n        <b><font color="#c8ced6">Links - </font></b>\n        Einnahmen nach Kategorie&nbsp;&nbsp;·&nbsp;&nbsp;\n        <b><font color="#c8ced6">Rechts - </font></b>\n        Ausgaben nach Kategorie\n        (<font color="#4caf50"><b>Überschuss</b></font> /\n        <font color="#e05245"><b>Fehlbetrag</b></font>).<br>\n        Die Bänder zeigen die anteilige Verteilung des Geldflusses\n        und keine direkte Zuordnung einzelner Buchungen.\n    </font>\n    ')
)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.sankey_widget = SankeyWidget()
        layout.addWidget(self.sankey_widget)
        return section

    def _build_compare_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)

        nav = QHBoxLayout()
        layout.addLayout(nav)
        self.compare_mode_combo = QComboBox()
        self.compare_mode_combo.addItem(tr('Monat gegen Vormonat'), "monat")
        self.compare_mode_combo.addItem(tr('Jahresverlauf'), "jahr")
        self.compare_mode_combo.currentIndexChanged.connect(self._on_compare_mode_changed)
        nav.addWidget(self.compare_mode_combo)
        prev_btn = QPushButton("◀")
        prev_btn.clicked.connect(lambda: self._shift_compare(-1))
        nav.addWidget(prev_btn)
        self.compare_label = QLabel()
        nav.addWidget(self.compare_label)
        next_btn = QPushButton("▶")
        next_btn.clicked.connect(lambda: self._shift_compare(1))
        nav.addWidget(next_btn)
        nav.addSpacing(16)
        self.compare_category_label = QLabel(tr('Kategorie:'))
        nav.addWidget(self.compare_category_label)
        self.compare_category_combo = QComboBox()
        self.compare_category_combo.setMinimumWidth(180)
        self.compare_category_combo.currentIndexChanged.connect(self._on_compare_category_changed)
        nav.addWidget(self.compare_category_combo)
        nav.addStretch()

        self.compare_stack = QStackedWidget()
        self.compare_month_widget = CategoryCompareWidget()
        self.compare_year_widget = CategoryYearWidget()
        self.compare_stack.addWidget(self.compare_month_widget)
        self.compare_stack.addWidget(self.compare_year_widget)
        layout.addWidget(self.compare_stack)

        self.compare_summary = QLabel()
        self.compare_summary.setWordWrap(True)
        layout.addWidget(self.compare_summary)
        return section

    def _on_compare_mode_changed(self, index):
        self.compare_stack.setCurrentIndex(index)
        self._refresh_stats()

    def _on_compare_category_changed(self, index):
        if not getattr(self, "_updating_compare_combo", False):
            self._refresh_stats()

    def _shift_compare(self, delta):
        step = 12 if self.compare_mode_combo.currentData() == "jahr" else 1
        self.stats_month = add_months(self.stats_month, delta * step)
        self._refresh_stats()

    def _refresh_compare(self, month_str):
        year_mode = self.compare_mode_combo.currentData() == "jahr"
        self.compare_category_label.setVisible(year_mode)
        self.compare_category_combo.setVisible(year_mode)

        if not year_mode:
            prev_month = add_months(self.stats_month, -1)
            prev_str = prev_month.strftime("%Y-%m")
            self.compare_label.setText(
                tr('{0} gegen {1}').format(month_label(self.stats_month), month_label(prev_month)))
            rows = self.store.category_comparison(month_str, prev_str)
            self.compare_month_widget.set_data(
                rows, month_label(self.stats_month), month_label(prev_month))
            total_cur = sum(r["current"] for r in rows)
            total_prev = sum(r["previous"] for r in rows)
            diff = total_cur - total_prev
            if rows:
                pct = f" ({diff / total_prev * 100:+.0f} %)".replace(".", ",") if total_prev > 0 else ""
                self.compare_summary.setText(
                    tr('Gesamtausgaben: {0} gegenüber {1} im Vormonat – Veränderung {2}{3}. Rot = mehr ausgegeben, grün = weniger.').format(fmt_amount(total_cur), fmt_amount(total_prev), fmt_amount(diff), pct))
            else:
                self.compare_summary.setText("")
            return

        year = self.stats_month.year
        self.compare_label.setText(tr('Jahr {0}').format(year))
        previous_choice = self.compare_category_combo.currentData()
        self._updating_compare_combo = True
        self.compare_category_combo.clear()
        self.compare_category_combo.addItem(tr('Alle Ausgaben'), None)
        for r in self.store.expense_categories_in_year(year):
            self.compare_category_combo.addItem(f"{r['icon']} {r['category_name']}",
                                                r["category_name"])
        idx = self.compare_category_combo.findData(previous_choice)
        self.compare_category_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._updating_compare_combo = False

        category = self.compare_category_combo.currentData()
        values = self.store.category_year_series(year, category)
        # Durchschnitt nur über die bereits begonnenen Monate (laufendes Jahr);
        # spätere Monate enthalten nur geplante/wiederkehrende Buchungen und
        # werden im Diagramm blasser gezeichnet.
        today = datetime.date.today()
        if year < today.year:
            months_counted = 12
        elif year == today.year:
            months_counted = today.month
        else:
            months_counted = 0
        elapsed_total = sum(values[:months_counted])
        average = elapsed_total / months_counted if months_counted and elapsed_total > 0 else 0.0
        total = sum(values)
        self.compare_year_widget.set_data(values, average, future_from=months_counted)
        if total > 0:
            peak = max(range(12), key=lambda i: values[i])
            names = months()
            self.compare_summary.setText(
                tr('Summe {0} (inkl. geplanter Buchungen): {1} · Ø pro Monat bisher: {2} · teuerster Monat: {3} ({4}). Rote Balken liegen über 120 % des Durchschnitts.').format(year, fmt_amount(total), fmt_amount(average), names[peak], fmt_amount(values[peak])))
        else:
            self.compare_summary.setText("")

    def _build_year_compare_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)

        nav = QHBoxLayout()
        layout.addLayout(nav)
        self.yearcmp_mode_combo = QComboBox()
        self.yearcmp_mode_combo.addItem(tr('Monate'), "monate")
        self.yearcmp_mode_combo.addItem(tr('Nach Kategorie'), "kategorien")
        self.yearcmp_mode_combo.currentIndexChanged.connect(self._on_yearcmp_mode_changed)
        nav.addWidget(self.yearcmp_mode_combo)
        self.yearcmp_metric_combo = QComboBox()
        self.yearcmp_metric_combo.addItem(tr('Ausgaben'), "expense")
        self.yearcmp_metric_combo.addItem(tr('Einnahmen'), "income")
        self.yearcmp_metric_combo.currentIndexChanged.connect(lambda _i: self._refresh_stats())
        nav.addWidget(self.yearcmp_metric_combo)
        prev_btn = QPushButton("◀")
        prev_btn.clicked.connect(lambda: self._shift_yearcmp(-1))
        nav.addWidget(prev_btn)
        self.yearcmp_label = QLabel()
        nav.addWidget(self.yearcmp_label)
        next_btn = QPushButton("▶")
        next_btn.clicked.connect(lambda: self._shift_yearcmp(1))
        nav.addWidget(next_btn)
        nav.addStretch()

        self.yearcmp_stack = QStackedWidget()
        self.yearcmp_months_widget = YearCompareWidget()
        self.yearcmp_cat_widget = CategoryCompareWidget()
        self.yearcmp_stack.addWidget(self.yearcmp_months_widget)
        self.yearcmp_stack.addWidget(self.yearcmp_cat_widget)
        layout.addWidget(self.yearcmp_stack)

        self.yearcmp_summary = QLabel()
        self.yearcmp_summary.setWordWrap(True)
        layout.addWidget(self.yearcmp_summary)
        return section

    def _year_nav(self, layout, label_attr):
        nav = QHBoxLayout()
        layout.addLayout(nav)
        prev_btn = QPushButton("◀")
        prev_btn.clicked.connect(lambda: self._shift_yearcmp(-1))
        nav.addWidget(prev_btn)
        label = QLabel()
        setattr(self, label_attr, label)
        nav.addWidget(label)
        next_btn = QPushButton("▶")
        next_btn.clicked.connect(lambda: self._shift_yearcmp(1))
        nav.addWidget(next_btn)
        nav.addStretch()
        return nav

    def _build_budget_year_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)
        self._year_nav(layout, "budgetyear_label")
        headers = ([tr('Kategorie')] + list(months_short())
                   + [tr('× drüber'), tr('× drunter'), tr('Summe drüber'), tr('Summe drunter'), tr('Saldo')])
        self.budgetyear_table = QTableWidget(0, len(headers))
        self.budgetyear_table.setHorizontalHeaderLabels(headers)
        header = self.budgetyear_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(headers)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.budgetyear_table.verticalHeader().setVisible(False)
        self.budgetyear_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.budgetyear_table.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.budgetyear_table)
        self.budgetyear_summary = QLabel()
        self.budgetyear_summary.setWordWrap(True)
        layout.addWidget(self.budgetyear_summary)
        return section

    def _refresh_budget_year(self):
        year = self.stats_month.year
        self.budgetyear_label.setText(str(year))
        data = self.store.budget_year_summary(year)
        tk = theme.current()
        table = self.budgetyear_table
        rows = data["rows"]
        table.setRowCount(len(rows) + (1 if rows else 0))

        def put(r, c, text, color=None, bold=False, align=Qt.AlignCenter, tooltip=None, italic=False, tint=None):
            item = QTableWidgetItem(text)
            item.setTextAlignment(align | Qt.AlignVCenter)
            if color:
                item.setForeground(QColor(color))
            if tint:
                bg = QColor(tint)
                bg.setAlpha(45)
                item.setBackground(bg)
            if bold or italic:
                f = item.font()
                f.setBold(bold)
                f.setItalic(italic)
                item.setFont(f)
            if tooltip:
                item.setToolTip(tooltip)
            table.setItem(r, c, item)

        def signed(value):
            return f"{'+' if value > 0.005 else ('−' if value < -0.005 else '±')}{abs(value):,.0f}".replace(",", ".")

        for i, row in enumerate(rows):
            put(i, 0, f"{row['icon']} {row['category_name']}", align=Qt.AlignLeft)
            for m, cell in enumerate(row["cells"]):
                if cell is None:
                    put(i, 1 + m, "")
                    continue
                over = cell["diff"] > 0.005
                tip = tr('Budget {0}, ausgegeben {1}').format(fmt_amount(cell["limit"]), fmt_amount(cell["spent"]))
                if not cell["complete"]:
                    tip += " – " + tr('Monat läuft noch, zählt noch nicht mit')
                put(i, 1 + m, signed(cell["diff"]),
                    color=tk["negative"] if over else tk["positive"],
                    tint=(tk["negative"] if over else tk["positive"]) if cell["complete"] else None,
                    tooltip=tip, italic=not cell["complete"])
            put(i, 13, str(row["months_over"]), color=tk["negative"] if row["months_over"] else None)
            put(i, 14, str(row["months_under"]))
            put(i, 15, fmt_amount(row["over_sum"]) if row["over_sum"] else "–", align=Qt.AlignRight)
            put(i, 16, fmt_amount(row["under_sum"]) if row["under_sum"] else "–", align=Qt.AlignRight)
            put(i, 17, ("+" if row["net"] > 0.005 else "") + fmt_amount(row["net"]), align=Qt.AlignRight,
                color=tk["negative"] if row["net"] > 0.005 else tk["positive"], bold=True)
        if rows:
            t = data["totals"]
            last = len(rows)
            put(last, 0, tr('Gesamt'), bold=True, align=Qt.AlignLeft)
            for c in range(1, 13):
                put(last, c, "")
            put(last, 13, str(t["months_over"]), bold=True)
            put(last, 14, str(t["months_under"]), bold=True)
            put(last, 15, fmt_amount(t["over_sum"]), bold=True, align=Qt.AlignRight)
            put(last, 16, fmt_amount(t["under_sum"]), bold=True, align=Qt.AlignRight)
            put(last, 17, ("+" if t["net"] > 0.005 else "") + fmt_amount(t["net"]), bold=True, align=Qt.AlignRight,
                color=tk["negative"] if t["net"] > 0.005 else tk["positive"])
            self.budgetyear_summary.setText(
                tr('Pro Monat ist angegeben, wie viel Euro du über (+) oder unter (−) dem Budget lagst. Gezählt werden nur abgeschlossene Monate mit geltendem Budget; der laufende Monat ist kursiv und zählt noch nicht mit. „Saldo“ positiv = insgesamt mehr ausgegeben als budgetiert.'))
        else:
            self.budgetyear_summary.setText(tr('Für dieses Jahr gibt es noch keine Budgets. Lege sie im Tab „Budgets“ an.'))

    def _build_tags_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)
        nav = self._year_nav(layout, "tags_label")
        self.tags_all_check = QCheckBox(tr('Alle Jahre'))
        self.tags_all_check.toggled.connect(lambda _c: self._refresh_stats())
        nav.insertWidget(nav.count() - 1, self.tags_all_check)
        headers = [tr('Tag'), tr('Buchungen'), tr('Ausgaben'), tr('Einnahmen'), tr('Saldo')]
        self.tags_table = QTableWidget(0, len(headers))
        self.tags_table.setHorizontalHeaderLabels(headers)
        self.tags_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 5):
            self.tags_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tags_table.verticalHeader().setVisible(False)
        self.tags_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tags_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.tags_table)
        self.tags_hint = QLabel()
        self.tags_hint.setWordWrap(True)
        layout.addWidget(self.tags_hint)
        return section

    def _refresh_tags(self):
        all_years = self.tags_all_check.isChecked()
        year = None if all_years else self.stats_month.year
        self.tags_label.setText(tr('alle Jahre') if all_years else str(year))
        rows = self.store.tag_summary(year)
        tk = theme.current()
        self.tags_table.setRowCount(len(rows))
        for i, e in enumerate(rows):
            saldo = e["income"] - e["expense"]
            cells = [f"#{e['tag']}", str(e["count"]), fmt_amount(e["expense"]),
                     fmt_amount(e["income"]), fmt_amount(saldo)]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 4:
                    item.setForeground(QColor(tk["positive"] if saldo >= 0 else tk["negative"]))
                self.tags_table.setItem(i, c, item)
        self.tags_hint.setText("" if rows else tr('Noch keine Buchungen mit Tags. Beim Anlegen oder Bearbeiten einer Buchung kannst du Tags wie „Urlaub“ eintragen; unabhängig von den Kategorien siehst du hier, was sie insgesamt gekostet haben.'))

    def _on_yearcmp_mode_changed(self, index):
        self.yearcmp_stack.setCurrentIndex(index)
        self._refresh_stats()

    def _shift_yearcmp(self, delta):
        self.stats_month = add_months(self.stats_month, 12 * delta)
        self._refresh_stats()

    @staticmethod
    def _year_delta_text(current, previous):
        diff = current - previous
        if previous <= 0:
            return "" if current <= 0 else tr(" (Vorjahr: –)")
        sign = "+" if diff > 0 else ("−" if diff < 0 else "±")
        return (tr(' (Vorjahr {0}, {1}{2} / {3}{4:.0f} %)').format(fmt_amount(previous), sign, fmt_amount(abs(diff)), sign, abs(diff / previous * 100)))

    def _refresh_year_compare(self):
        year = self.stats_month.year
        self.yearcmp_label.setText(tr('{0} gegen {1}').format(year, year - 1))
        by_month = self.yearcmp_mode_combo.currentData() == "monate"
        self.yearcmp_metric_combo.setVisible(by_month)

        data = self.store.year_comparison(year)
        today = datetime.date.today()
        months_started = 12 if year < today.year else (today.month if year == today.year else 0)
        metric = self.yearcmp_metric_combo.currentData()
        self.yearcmp_months_widget.set_data(data["months"], metric, str(year), str(year - 1),
                                            future_from=months_started)
        rows = self.store.category_comparison(str(year), str(year - 1))
        self.yearcmp_cat_widget.set_data(rows, str(year), str(year - 1))

        t = data["totals"]
        rate = t["saved"] / t["income"] * 100 if t["income"] > 0 else None
        prev_rate = t["prev_saved"] / t["prev_income"] * 100 if t["prev_income"] > 0 else None
        parts = [
            tr('Einnahmen {0}{1}').format(fmt_amount(t['income']), self._year_delta_text(t['income'], t['prev_income'])),
            tr('Ausgaben {0}{1}').format(fmt_amount(t['expense']), self._year_delta_text(t['expense'], t['prev_expense'])),
            tr('Gespart {0} (Vorjahr {1})').format(fmt_amount(t['saved']), fmt_amount(t['prev_saved'])),
        ]
        if rate is not None:
            rate_text = tr('Sparquote {0:.0f} %').format(rate)
            if prev_rate is not None:
                rate_text += tr(' (Vorjahr {0:.0f} %)').format(prev_rate)
            parts.append(rate_text)
        note = ""
        if year >= today.year:
            note = tr(' Hinweis: Bei laufenden Jahren sind geplante, noch nicht erreichte Monate blass dargestellt und in den Summen enthalten.')
        self.yearcmp_summary.setText(" · ".join(parts) + "." + note)

    def _shift_stats_month(self, delta):
        self.stats_month = add_months(self.stats_month, delta)
        self._refresh_stats()

    def _on_trend_months_changed(self, value):
        self.trend_months = value
        self._refresh_stats()

    def _refresh_stats(self):
        self.stats_month_label.setText(month_label(self.stats_month))
        self.sankey_month_label.setText(month_label(self.stats_month))
        month_str = self.stats_month.strftime("%Y-%m")

        expense_rows = self.store.spending_by_category(month_str)
        pie_data = [(r["category_name"], r["icon"], r["total"], color_for_index(i))
                    for i, r in enumerate(expense_rows)]
        self.pie_widget.set_data(pie_data)

        trend_data = self.store.monthly_trend(self.trend_months, end_month=month_str)
        self.trend_widget.set_data(trend_data)

        income_rows = self.store.income_by_category(month_str)
        left_nodes = [(r["category_name"], r["icon"], r["total"], color_for_index(i))
                      for i, r in enumerate(income_rows)]
        right_nodes = [(r["category_name"], r["icon"], r["total"], color_for_index(i))
                       for i, r in enumerate(expense_rows)]
        total_income = sum(n[2] for n in left_nodes)
        total_expense = sum(n[2] for n in right_nodes)

        if total_income > total_expense + 0.005:
            right_nodes.append((tr('Übrig/Gespart'), "💰", total_income - total_expense,
                                 QColor(30, 140, 61)))
        elif total_expense > total_income + 0.005:
            left_nodes.append((tr("Fehlbetrag"), "⚠️", total_expense - total_income,
                                QColor(191, 56, 38)))

        self.sankey_widget.set_data(left_nodes, right_nodes, max(total_income, total_expense))
        self._refresh_compare(month_str)
        self._refresh_year_compare()
        self._refresh_budget_year()
        self._refresh_tags()

    # =====================================================================
    # Tab: Suche (alle Buchungen filtern)
    # =====================================================================

    def _build_search_tab(self):
        root = QWidget()
        layout = QVBoxLayout(root)

        row1 = QHBoxLayout()
        layout.addLayout(row1)
        self.search_text = QLineEdit()
        self.search_text.setPlaceholderText(tr('Suchen in Beschreibung und Kategorie …'))
        self.search_text.setClearButtonEnabled(True)
        self.search_text.textChanged.connect(self._run_search)
        row1.addWidget(self.search_text, 1)

        self.search_kind = QComboBox()
        self.search_kind.addItem(tr('Alle Arten'), None)
        self.search_kind.addItem(tr('Ausgaben'), "ausgabe")
        self.search_kind.addItem(tr('Einnahmen'), "einnahme")
        self.search_kind.currentIndexChanged.connect(self._run_search)
        row1.addWidget(self.search_kind)

        self.search_category = QComboBox()
        self.search_category.setMinimumWidth(170)
        self.search_category.currentIndexChanged.connect(self._run_search)
        row1.addWidget(self.search_category)

        row2 = QHBoxLayout()
        layout.addLayout(row2)
        row2.addWidget(QLabel(tr('Zeitraum:')))
        self.search_period = QComboBox()
        for label, key in ((tr("Alle"), "alle"), (tr('Dieser Monat'), "monat"),
                           (tr('Letzte 3 Monate'), "3monate"), (tr('Dieses Jahr'), "jahr"),
                           (tr('Letztes Jahr'), "vorjahr"), (tr("Eigener Zeitraum"), "eigen")):
            self.search_period.addItem(label, key)
        self.search_period.currentIndexChanged.connect(self._on_search_period_changed)
        row2.addWidget(self.search_period)
        self.search_from = QDateEdit()
        self.search_to = QDateEdit()
        for edit in (self.search_from, self.search_to):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd.MM.yyyy")
            edit.setDate(_date_to_qdate(datetime.date.today()))
            edit.setEnabled(False)
            edit.dateChanged.connect(self._run_search)
        row2.addWidget(self.search_from)
        row2.addWidget(QLabel(tr('bis')))
        row2.addWidget(self.search_to)

        row2.addSpacing(16)
        row2.addWidget(QLabel(tr('Betrag von')))
        self.search_min = QDoubleSpinBox()
        self.search_max = QDoubleSpinBox()
        for spin in (self.search_min, self.search_max):
            spin.setRange(0, 1_000_000)
            spin.setDecimals(2)
            spin.setSuffix(" €")
            spin.setSpecialValueText(tr('egal'))
            spin.valueChanged.connect(self._run_search)
        row2.addWidget(self.search_min)
        row2.addWidget(QLabel(tr('bis')))
        row2.addWidget(self.search_max)

        self.search_future = QCheckBox(tr('auch geplante (zukünftige) Buchungen'))
        self.search_future.toggled.connect(self._run_search)
        row2.addWidget(self.search_future)
        row2.addStretch()

        self.search_table = QTableWidget(0, 5)
        self.search_table.setHorizontalHeaderLabels(
            [tr('Datum'), tr('Kategorie'), tr('Art'), tr('Betrag'), tr('Beschreibung')])
        self.search_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.search_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.search_table.verticalHeader().setVisible(False)
        header = self.search_table.horizontalHeader()
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.search_table.itemDoubleClicked.connect(self._on_search_row_activated)
        layout.addWidget(self.search_table, 1)

        self.search_summary = QLabel()
        layout.addWidget(self.search_summary)
        hint = QLabel(tr('Doppelklick auf eine Zeile öffnet die Buchung zum Bearbeiten.'))
        layout.addWidget(hint)

        self._reload_search_categories()
        self._run_search()
        return root

    def _reload_search_categories(self):
        current = self.search_category.currentData()
        self.search_category.blockSignals(True)
        self.search_category.clear()
        self.search_category.addItem(tr('Alle Kategorien'), None)
        for c in self.store.list_categories():
            self.search_category.addItem(f"{c['icon']} {c['name']}", c["id"])
        idx = self.search_category.findData(current)
        self.search_category.setCurrentIndex(idx if idx >= 0 else 0)
        self.search_category.blockSignals(False)

    def _on_search_period_changed(self, *_args):
        key = self.search_period.currentData()
        today = datetime.date.today()
        ranges = {
            "monat": (today.replace(day=1), today),
            "3monate": (add_months(today.replace(day=1), -2), today),
            "jahr": (today.replace(month=1, day=1), today),
            "vorjahr": (datetime.date(today.year - 1, 1, 1),
                        datetime.date(today.year - 1, 12, 31)),
        }
        custom = key == "eigen"
        self.search_from.setEnabled(custom)
        self.search_to.setEnabled(custom)
        if key in ranges:
            for edit, value in zip((self.search_from, self.search_to), ranges[key]):
                edit.blockSignals(True)
                edit.setDate(_date_to_qdate(value))
                edit.blockSignals(False)
        self._run_search()

    def _search_date_range(self):
        key = self.search_period.currentData()
        if key == "alle":
            return None, None
        return (self.search_from.date().toString("yyyy-MM-dd"),
                self.search_to.date().toString("yyyy-MM-dd"))

    def _run_search(self, *_args):
        if not hasattr(self, "search_table"):
            return
        date_from, date_to = self._search_date_range()
        rows, truncated = self.store.search_transactions(
            text=self.search_text.text() or None,
            category_id=self.search_category.currentData(),
            kind=self.search_kind.currentData(),
            date_from=date_from, date_to=date_to,
            min_amount=self.search_min.value() or None,
            max_amount=self.search_max.value() or None,
            include_future=self.search_future.isChecked(),
        )
        self.search_table.setRowCount(len(rows))
        income = expense = 0.0
        for i, r in enumerate(rows):
            d = datetime.date.fromisoformat(r["date"])
            cells = [d.strftime("%d.%m.%Y"), f"{r['icon']} {r['category_name']}",
                     tr('Einnahme') if r["kind"] == "einnahme" else tr('Ausgabe'),
                     fmt_amount(r["amount"]), self._description_with_tags(r)]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.UserRole, r["id"])
                if col == 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    item.setForeground(QColor(76, 175, 80) if r["amount"] >= 0
                                       else QColor(224, 82, 69))
                self.search_table.setItem(i, col, item)
            if r["amount"] >= 0:
                income += r["amount"]
            else:
                expense += -r["amount"]
        self.search_table.resizeColumnsToContents()
        self.search_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        text = (tr('{0} Treffer · Einnahmen {1} · Ausgaben {2} · Saldo {3}').format(len(rows), fmt_amount(income), fmt_amount(expense), fmt_amount(income - expense)))
        if truncated:
            text += tr(' · nur die neuesten 2000 Treffer werden angezeigt – Filter enger setzen')
        self.search_summary.setText(text)

    def _on_search_row_activated(self, item):
        tx_id = self.search_table.item(item.row(), 0).data(Qt.UserRole)
        existing = self.store.get_transaction(tx_id)
        if existing is None:
            return
        day = datetime.date.fromisoformat(existing["date"])
        dialog = TransactionDialog(self, self.store, day, existing=existing)
        if dialog.exec() == TransactionDialog.Accepted:
            dialog.save()
            self._after_transactions_changed()
            self._refresh_stats()
            self._run_search()

    # =====================================================================
    # Tab 7: Export / Import
    # =====================================================================

    def _build_export_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        widget = QWidget()
        scroll.setWidget(widget)
        outer = QVBoxLayout(widget)
        outer.setSpacing(14)

        def section(title):
            card, lay = make_card()
            lay.setSpacing(8)
            head = QLabel(title)
            head.setObjectName("cardTitle")
            lay.addWidget(head)
            outer.addWidget(card)
            return lay

        def text(lay, content):
            label = QLabel(content)
            label.setWordWrap(True)
            lay.addWidget(label)

        def button(lay, label, slot):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            lay.addWidget(btn, 0, Qt.AlignLeft)
            return btn

        lay = section(tr('Tabelle (CSV)'))
        text(lay, tr('CSV-Export aller Buchungen – zum Öffnen/Weiterverarbeiten in Excel oder Numbers/LibreOffice Calc.'))
        button(lay, tr('Buchungen als CSV exportieren…'), self._on_export_csv)
        text(lay, tr('CSV-Import: Buchungen aus einer anderen Haushaltsbuch- oder Banking-Software übernehmen. Trennzeichen sowie deutsche/englische Zahlen- und Datumsformate werden automatisch erkannt.'))
        button(lay, tr('Buchungen aus CSV importieren…'), self._on_import_csv)

        lay = section(tr('Sicherung'))
        text(lay, tr('Vollständiges Backup (JSON) – enthält alle Buchungen, Vorlagen, Budgets, Sparziele, ETF-Pläne und Kategorien.'))
        row = QHBoxLayout()
        for label, slot in ((tr('Backup als JSON exportieren…'), self._on_export_json),
                            (tr('Backup aus JSON importieren…'), self._on_import_json)):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch()
        lay.addLayout(row)
        text(lay, tr('Automatische Sicherung: Beim ersten Start eines Tages legt Plutos eine Kopie der Datenbank in {0} an (die letzten {1} bleiben erhalten).').format(self.store.backup_dir, self.store.BACKUP_KEEP))
        button(lay, tr('Datenbank jetzt sichern'), self._on_backup_now)

        lay = section(tr('Darstellung'))
        lang_row = QHBoxLayout()
        lang_label = QLabel("Sprache / Language:")
        lang_label.setMinimumWidth(150)
        lang_row.addWidget(lang_label)
        self.language_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(
            max(0, self.language_combo.findData(get_language())))
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_row.addWidget(self.language_combo)
        lang_row.addStretch()
        lay.addLayout(lang_row)

        theme_row = QHBoxLayout()
        theme_label = QLabel(tr('Darstellung:'))
        theme_label.setMinimumWidth(150)
        theme_row.addWidget(theme_label)
        self.theme_combo = QComboBox()
        for key, label in (("system", tr('Wie das System')), ("light", tr('Hell')), ("dark", tr('Dunkel'))):
            self.theme_combo.addItem(label, key)
        self.theme_combo.setCurrentIndex(
            max(0, self.theme_combo.findData(self.store.get_setting("theme", "system"))))
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        lay.addLayout(theme_row)

        self.export_status_label = QLabel()
        self.export_status_label.setWordWrap(True)
        outer.addWidget(self.export_status_label)
        outer.addStretch()
        return scroll

    def _on_theme_changed(self, index):
        self.store.set_setting("theme", self.theme_combo.itemData(index))
        self.export_status_label.setText(
            tr('Die Darstellung wird nach einem Neustart vollständig übernommen.'))

    def _on_language_changed(self, index):
        self.store.set_setting("language", self.language_combo.itemData(index))
        self.export_status_label.setText(
            "Neustart erforderlich, damit die Sprache wirksam wird. / "
            "Please restart Plutos to apply the language.")

    def _on_export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Buchungen als CSV exportieren'),
                                               "haushaltsbuch_export.csv", "CSV-Dateien (*.csv)")
        if path:
            self.store.export_transactions_csv(path)
            self.export_status_label.setText(tr('CSV exportiert nach: {0}').format(path))

    def _on_import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Buchungen aus CSV importieren'),
                                               "", "CSV-Dateien (*.csv)")
        if not path:
            return
        try:
            result = self.store.import_transactions_csv(path)
        except Exception as exc:
            QMessageBox.critical(self, tr('Fehler'), tr('CSV konnte nicht gelesen werden:\n{0}').format(exc))
            return

        summary = tr('{0} Buchung(en) importiert').format(result['imported'])
        if result.get("duplicates"):
            summary += tr(', {0} bereits vorhanden (nicht doppelt angelegt)').format(result['duplicates'])
        if result["skipped"]:
            summary += tr(', {0} übersprungen').format(result['skipped'])
        self.export_status_label.setText(tr('CSV importiert von: {0} – {1}.').format(path, summary))

        detail_lines = "\n".join(_localize_import_error(e) for e in result["errors"][:15])
        if len(result["errors"]) > 15:
            detail_lines += tr('\n… und {0} weitere.').format(len(result['errors']) - 15)
        icon = QMessageBox.Information if not result["errors"] else QMessageBox.Warning
        box = QMessageBox(icon, tr("CSV-Import"), summary + (":" if detail_lines else "."), parent=self)
        if detail_lines:
            box.setDetailedText(detail_lines)
        box.exec()

        self.store.ensure_horizon(self._selected_calendar_month())
        self._after_transactions_changed()
        self._refresh_stats()

    def _on_backup_now(self):
        path = self.store.create_db_backup(force=True)
        self.export_status_label.setText(tr('Datenbank gesichert: {0}').format(path))

    def _on_export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Backup als JSON exportieren'),
                                               "haushaltsbuch_backup.json", "JSON-Dateien (*.json)")
        if path:
            self.store.export_backup_json(path)
            self.export_status_label.setText(tr('Backup exportiert nach: {0}').format(path))

    def _on_import_json(self):
        response = QMessageBox.warning(
            self, tr('Backup importieren'), tr('Import ersetzt alle aktuellen Daten. Fortfahren?'),
            QMessageBox.Ok | QMessageBox.Cancel,
        )
        if response != QMessageBox.Ok:
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('Backup importieren'),
                                               "", "JSON-Dateien (*.json)")
        if not path:
            return
        self.store.import_backup_json(path)
        self.store.ensure_horizon(self._selected_calendar_month())
        self.export_status_label.setText(tr('Backup importiert von: {0}').format(path))
        self._after_transactions_changed()
        self._refresh_goals_tab()
        self._refresh_stats()
        self._refresh_etf_plan_selector()
        self._refresh_etf_comparison()


def _resource_path(name):
    """Pfad zu einer mitgelieferten Datei – im Quellcode neben main.py, in
    einer PyInstaller-App im entpackten Datenordner."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / name if base else Path(__file__).resolve().parent / name


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Plutos")
    app.setOrganizationName("Plutos")
    icon_path = _resource_path("icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
