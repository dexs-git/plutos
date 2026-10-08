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

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QLabel, QPushButton, QComboBox, QDoubleSpinBox, QSpinBox,
    QCheckBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QCalendarWidget, QScrollArea, QStackedWidget, QFileDialog,
    QMessageBox, QGroupBox, QProgressBar, QSizePolicy, QDateEdit,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor, QTextCharFormat

from db import FinanceStore, add_months
from charts import (
    PieChartWidget, TrendChartWidget, SankeyWidget, EtfComparisonWidget,
    fmt_amount, color_for_index,
)
from dialogs import (
    TransactionDialog, RecurringTemplatesDialog, BudgetDialog, GoalDialog,
    ContributionDialog, CategoryManagerDialog, make_help_button,
)

GERMAN_MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                  "August", "September", "Oktober", "November", "Dezember"]


def month_label(date_obj):
    return f"{GERMAN_MONTHS[date_obj.month - 1]} {date_obj.year}"


def _qdate_to_date(qdate: QDate) -> datetime.date:
    return datetime.date(qdate.year(), qdate.month(), qdate.day())


def _date_to_qdate(d: datetime.date) -> QDate:
    return QDate(d.year, d.month, d.day)


# ---------------------------------------------------------------------------
# Hauptfenster
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plutos – Das Haushaltsbuch")
        self.resize(1080, 700)

        self.store = FinanceStore()
        self.store.ensure_horizon(datetime.date.today())

        self.selected_day = datetime.date.today()
        self.stats_month = datetime.date.today().replace(day=1)
        self.trend_months = 6
        self.current_etf_plan_id = None
        self._current_recommendation = None

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tabs.addTab(self._build_transactions_tab(), "Buchungen")
        self.tabs.addTab(self._build_budgets_tab(), "Budgets")
        self.tabs.addTab(self._build_goals_tab(), "Sparziele")
        self.tabs.addTab(self._build_planning_tab(), "Finanzplanung")
        self.etf_tab_index = self.tabs.count()
        self.tabs.addTab(self._build_etf_tab(), "ETF-Sparplan")
        self.tabs.addTab(self._build_stats_tab(), "Auswertungen")
        self.tabs.addTab(self._build_export_tab(), "Export / Import")

    # =====================================================================
    # Tab 1: Buchungen (Kalenderansicht: Monat/Woche/Jahr)
    # =====================================================================

    def _build_transactions_tab(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)

        # -- Linke Seite: Ansicht wählen + Kalender/Woche/Jahr --
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_widget.setMaximumWidth(480)
        root_layout.addWidget(left_widget)

        self.view_switch_combo = QComboBox()
        self.view_switch_combo.addItem("Monatsansicht", "monat")
        self.view_switch_combo.addItem("Wochenansicht", "woche")
        self.view_switch_combo.addItem("Jahresansicht", "jahr")
        self.view_switch_combo.currentIndexChanged.connect(self._on_view_switch_changed)
        left_layout.addWidget(self.view_switch_combo)

        self.view_stack = QStackedWidget()
        left_layout.addWidget(self.view_stack)

        self.view_stack.addWidget(self._build_month_page())
        self.view_stack.addWidget(self._build_week_page())
        self.view_stack.addWidget(self._build_year_page())

        manage_cat_btn = QPushButton("Kategorien verwalten")
        manage_cat_btn.clicked.connect(self._on_manage_categories)
        left_layout.addWidget(manage_cat_btn)
        left_layout.addStretch()

        # -- Rechte Seite: Tagesliste --
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        root_layout.addWidget(right_widget, 1)

        self.day_title_label = QLabel()
        font = self.day_title_label.font()
        font.setBold(True)
        self.day_title_label.setFont(font)
        right_layout.addWidget(self.day_title_label)

        self.day_table = QTableWidget(0, 5)
        self.day_table.setHorizontalHeaderLabels(
            ["Kategorie", "Art", "Betrag", "Beschreibung", "Wiederk."])
        self.day_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.day_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.day_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.day_table.itemDoubleClicked.connect(self._on_edit_transaction_item)
        right_layout.addWidget(self.day_table)

        hint = QLabel("Tipp: Doppelklick auf eine Buchung öffnet sie zum Bearbeiten.")
        right_layout.addWidget(hint)

        btn_box = QHBoxLayout()
        right_layout.addLayout(btn_box)

        add_btn = QPushButton("Buchung hinzufügen")
        add_btn.clicked.connect(self._on_add_transaction)
        btn_box.addWidget(add_btn)

        edit_btn = QPushButton("Bearbeiten")
        edit_btn.clicked.connect(self._on_edit_selected_transaction)
        btn_box.addWidget(edit_btn)

        del_btn = QPushButton("Löschen")
        del_btn.clicked.connect(self._on_delete_transaction)
        btn_box.addWidget(del_btn)

        rec_btn = QPushButton("Wiederkehrende Vorlagen verwalten")
        rec_btn.clicked.connect(self._on_manage_recurring)
        btn_box.addWidget(rec_btn)
        btn_box.addStretch()

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
        self.calendar.setGridVisible(True)
        self.calendar.selectionChanged.connect(self._on_day_selected)
        self.calendar.activated.connect(self._on_day_double_clicked)
        self.calendar.currentPageChanged.connect(self._on_calendar_page_changed)
        layout.addWidget(self.calendar)

        self.month_balance_label = QLabel()
        self.month_balance_label.setWordWrap(True)
        layout.addWidget(self.month_balance_label)

        legend = QLabel(
    """
    <b><font color="#d8dee9">Hinweise</font></b><br>
    <b><font color="#c8ced6">Fett</font></b>
    <font color="#aeb6c0"> – Buchungen an diesem Tag</font><br>
    <b><font color="#c8ced6">Einfachklick</font></b>
    <font color="#aeb6c0"> – Buchungen des Tages anzeigen</font><br>
    <b><font color="#c8ced6">Doppelklick / Enter</font></b>
    <font color="#aeb6c0"> – neue Buchung für dieses Datum anlegen</font>
    """
)

        legend.setWordWrap(True)
        layout.addWidget(legend)
        layout.addStretch()
        return page

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
        today_btn = QPushButton("Diese Woche")
        today_btn.clicked.connect(self._goto_current_week)
        nav.addWidget(today_btn)
        nav.addStretch()

        week_box = QHBoxLayout()
        layout.addLayout(week_box)
        self.week_day_buttons = []
        for i in range(7):
            btn = QPushButton()
            btn.setMinimumHeight(64)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda checked=False, offset=i: self._on_week_day_clicked(offset))
            week_box.addWidget(btn)
            self.week_day_buttons.append(btn)

        hint = QLabel(
    """
    <font color="#aeb6c0">
        <b><font color="#c8ced6">Klick auf einen Tag</font></b>
        – Buchungen des Tages rechts anzeigen.<br>
        Monatsübersicht und Budgets folgen automatisch der angezeigten Woche.
    </font>
    """
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
        layout.addLayout(year_grid)
        self.year_month_buttons = []
        for m in range(12):
            btn = QPushButton()
            btn.setMinimumHeight(50)
            btn.clicked.connect(lambda checked=False, month=m + 1: self._on_year_month_clicked(month))
            year_grid.addWidget(btn, m // 3, m % 3)
            self.year_month_buttons.append(btn)

        hint = QLabel(
    """
    <b><font color="#c8ced6">Klick auf einen Monat</font></b>
    <font color="#aeb6c0"> – wechselt in die Monatsansicht.</font>
    """
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
            f"{month_label(month_start)}\n"
            f"Einnahmen: {fmt_amount(income)}\n"
            f"Ausgaben: {fmt_amount(expense)}\n"
            f"Saldo: {sign}{fmt_amount(saldo)}"
        )

    def _refresh_day_list(self):
        weekday_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                          "Freitag", "Samstag", "Sonntag"]
        d = self.selected_day
        self.day_title_label.setText(f"{weekday_names[d.weekday()]}, {d.strftime('%d.%m.%Y')}")

        rows = self.store.list_transactions_for_day(d.isoformat())
        self.day_table.setRowCount(len(rows))
        for row_idx, r in enumerate(rows):
            cat_item = QTableWidgetItem(f"{r['icon']} {r['category_name']}")
            cat_item.setData(Qt.UserRole, r["id"])
            self.day_table.setItem(row_idx, 0, cat_item)
            self.day_table.setItem(row_idx, 1, QTableWidgetItem(
                "Einnahme" if r["kind"] == "einnahme" else "Ausgabe"))
            amount_item = QTableWidgetItem(fmt_amount(r["amount"]))
            amount_item.setForeground(QColor(30, 140, 61) if r["amount"] >= 0 else QColor(191, 56, 38))
            self.day_table.setItem(row_idx, 2, amount_item)
            self.day_table.setItem(row_idx, 3, QTableWidgetItem(r["description"] or ""))
            self.day_table.setItem(row_idx, 4, QTableWidgetItem(
                "✓" if r["recurring_template_id"] is not None else ""))

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

    def _on_delete_transaction(self):
        tx_id = self._selected_transaction_id()
        if tx_id is not None:
            self.store.delete_transaction(tx_id)
            self._after_transactions_changed()

    def _on_manage_recurring(self):
        dialog = RecurringTemplatesDialog(self, self.store)
        dialog.exec()
        self.store.ensure_horizon(self._selected_calendar_month())
        self._after_transactions_changed()

    def _on_manage_categories(self):
        dialog = CategoryManagerDialog(self, self.store)
        dialog.exec()
        self._refresh_day_list()

    def _after_transactions_changed(self):
        self._refresh_calendar_marks()
        self._refresh_day_list()
        self._refresh_month_balance()
        self._refresh_budgets_tab()
        self._refresh_week_view()
        self._refresh_year_view()
        self._refresh_current_balance_display()

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
        weekday_names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        start = self.week_start
        end = start + datetime.timedelta(days=6)
        self.week_range_label.setText(f"{start.strftime('%d.%m.')} – {end.strftime('%d.%m.%Y')}")
        self.store.ensure_horizon(start.replace(day=1))

        for i, btn in enumerate(self.week_day_buttons):
            d = start + datetime.timedelta(days=i)
            rows = self.store.list_transactions_for_day(d.isoformat())
            income = sum(r["amount"] for r in rows if r["amount"] > 0)
            expense = sum(-r["amount"] for r in rows if r["amount"] < 0)
            saldo = income - expense
            marker = " •" if d == datetime.date.today() else ""
            saldo_text = fmt_amount(saldo) if rows else "–"
            btn.setText(f"{weekday_names[i]}{marker}\n{d.day}.{d.month}.\n{saldo_text}")

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
            name = GERMAN_MONTHS[i][:3]
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

        info = QLabel("Budgets gelten für den im Buchungen-Tab im Kalender sichtbaren Monat.")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.budget_table = QTableWidget(0, 5)
        self.budget_table.setHorizontalHeaderLabels(
            ["Kategorie", "Budget", "Ausgegeben", "Verbleibend", "Fortschritt"])
        self.budget_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.budget_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.budget_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.budget_table)

        btn_box = QHBoxLayout()
        layout.addLayout(btn_box)
        set_btn = QPushButton("Budget setzen/ändern")
        set_btn.clicked.connect(self._on_set_budget)
        btn_box.addWidget(set_btn)
        refresh_btn = QPushButton("Aktualisieren")
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
            progress = QProgressBar()
            progress.setTextVisible(True)
            if limit_amount is None:
                self.budget_table.setItem(i, 1, QTableWidgetItem("— kein Budget —"))
                self.budget_table.setItem(i, 2, QTableWidgetItem(fmt_amount(spent)))
                self.budget_table.setItem(i, 3, QTableWidgetItem("–"))
                progress.setValue(0)
            else:
                remaining = limit_amount - spent
                fraction = int(min(100, max(0, (spent / limit_amount) * 100))) if limit_amount else 0
                self.budget_table.setItem(i, 1, QTableWidgetItem(fmt_amount(limit_amount)))
                self.budget_table.setItem(i, 2, QTableWidgetItem(fmt_amount(spent)))
                self.budget_table.setItem(i, 3, QTableWidgetItem(fmt_amount(remaining)))
                progress.setValue(fraction)
            self.budget_table.setCellWidget(i, 4, progress)

    def _on_set_budget(self):
        row = self.budget_table.currentRow()
        preselect = self.budget_table.item(row, 0).data(Qt.UserRole) if row >= 0 else None
        dialog = BudgetDialog(self, self.store, self._selected_calendar_month(), preselect)
        if dialog.exec() == BudgetDialog.Accepted:
            dialog.save()
            self._refresh_budgets_tab()

    # =====================================================================
    # Tab 3: Sparziele
    # =====================================================================

    def _build_goals_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel(
    """
    <font color="#aeb6c0">
        Die Reihenfolge legt fest, in welcher Priorität die
        Finanzplanungsempfehlung das
        <b><font color="#c8ced6">Startkapital / den Sparbetrag</font></b>
        auf die Ziele verteilt.
        <b><font color="#c8ced6">Oben</font></b> = zuerst befüllt.<br>
        Mit <b><font color="#c8ced6">„Nach oben“</font></b> /
        <b><font color="#c8ced6">„Nach unten“</font></b>
        frei sortierbar.
    </font>
    """
)
        info.setWordWrap(True)
        layout.addWidget(info)

        self.goal_table = QTableWidget(0, 5)
        self.goal_table.setHorizontalHeaderLabels(
            ["Priorität / Ziel", "Zielbetrag", "Angespart", "Zieldatum", "Fortschritt"])
        self.goal_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.goal_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.goal_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.goal_table)

        btn_box = QHBoxLayout()
        layout.addLayout(btn_box)
        add_btn = QPushButton("Ziel hinzufügen")
        add_btn.clicked.connect(self._on_add_goal)
        btn_box.addWidget(add_btn)
        contrib_btn = QPushButton("Einzahlen")
        contrib_btn.clicked.connect(self._on_add_contribution)
        btn_box.addWidget(contrib_btn)
        del_btn = QPushButton("Ziel löschen")
        del_btn.clicked.connect(self._on_delete_goal)
        btn_box.addWidget(del_btn)
        up_btn = QPushButton("▲ Nach oben")
        up_btn.clicked.connect(lambda: self._on_move_goal_priority(-1))
        btn_box.addWidget(up_btn)
        down_btn = QPushButton("▼ Nach unten")
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
            progress = QProgressBar()
            progress.setValue(fraction)
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
        balance_group = QGroupBox("Kontostand")
        layout.addWidget(balance_group)
        balance_grid = QGridLayout(balance_group)

        balance_grid.addWidget(QLabel("Stichtag:"), 0, 0)
        existing_amount, existing_date = self.store.get_starting_balance()
        self.balance_date_edit = QDateEdit()
        self.balance_date_edit.setCalendarPopup(True)
        self.balance_date_edit.setDisplayFormat("dd.MM.yyyy")
        if existing_date:
            self.balance_date_edit.setDate(QDate.fromString(existing_date, "yyyy-MM-dd"))
        else:
            self.balance_date_edit.setDate(QDate.currentDate())
        balance_grid.addWidget(self.balance_date_edit, 0, 1)

        balance_grid.addWidget(QLabel("Kontostand an diesem Tag (€):"), 1, 0)
        self.balance_amount_spin = QDoubleSpinBox()
        self.balance_amount_spin.setRange(-1_000_000, 10_000_000)
        self.balance_amount_spin.setDecimals(2)
        self.balance_amount_spin.setValue(existing_amount or 0)
        balance_grid.addWidget(self.balance_amount_spin, 1, 1)
        balance_grid.addWidget(make_help_button(
            "Dein tatsächliches Kontoguthaben an einem bestimmten Tag (z. B. "
            "heute) – nicht nur die in Plutos erfassten Buchungen. Der "
            "aktuelle Kontostand wird daraus als Startguthaben + alle "
            "Buchungen ab diesem Stichtag berechnet, du musst also nicht "
            "jede einzelne Buchung seit Kontoeröffnung nacherfassen."
        ), 1, 2)

        save_balance_btn = QPushButton("Speichern")
        save_balance_btn.clicked.connect(self._on_save_starting_balance)
        balance_grid.addWidget(save_balance_btn, 2, 0, 1, 3)

        self.current_balance_label = QLabel()
        self.current_balance_label.setWordWrap(True)
        balance_grid.addWidget(self.current_balance_label, 3, 0, 1, 3)

        apply_balance_btn = QPushButton(
            "Aktuellen Kontostand als Startkapital in der Empfehlung übernehmen")
        apply_balance_btn.clicked.connect(self._on_apply_balance_to_recommendation)
        balance_grid.addWidget(apply_balance_btn, 4, 0, 1, 3)

        balance_hint = QLabel(
            "Praktisch, wenn du gerade erst anfängst, für etwas zu sparen, "
            "einen Notgroschen aufzubauen oder in ETFs zu investieren: so "
            "zählt dein tatsächlich vorhandenes Geld, nicht nur das, was du "
            "seit Nutzung von Plutos gebucht hast."
        )
        balance_hint.setWordWrap(True)
        balance_grid.addWidget(balance_hint, 5, 0, 1, 3)

        # -- Abschnitt A: Notgroschen --
        ng_group = QGroupBox("Notgroschen einrichten (3–6 Monate Fixkosten)")
        layout.addWidget(ng_group)
        ng_grid = QGridLayout(ng_group)

        ng_grid.addWidget(QLabel("Monatliche Fixkosten (€):"), 0, 0)
        self.planning_fixed_costs_spin = QDoubleSpinBox()
        self.planning_fixed_costs_spin.setRange(0, 100_000)
        self.planning_fixed_costs_spin.setDecimals(2)
        self.planning_fixed_costs_spin.setValue(self.store.estimate_monthly_fixed_costs())
        self.planning_fixed_costs_spin.valueChanged.connect(self._update_notgroschen_preview)
        ng_grid.addWidget(self.planning_fixed_costs_spin, 0, 1)
        recalc_btn = QPushButton("Aus wiederkehrenden Ausgaben schätzen")
        recalc_btn.clicked.connect(self._on_recalc_fixed_costs)
        ng_grid.addWidget(recalc_btn, 0, 2)

        ng_grid.addWidget(QLabel("Ziel: Monate an Fixkosten:"), 1, 0)
        self.planning_months_spin = QSpinBox()
        self.planning_months_spin.setRange(1, 12)
        self.planning_months_spin.setValue(4)
        self.planning_months_spin.valueChanged.connect(self._update_notgroschen_preview)
        ng_grid.addWidget(self.planning_months_spin, 1, 1)
        ng_grid.addWidget(make_help_button(
            "Wie viele Monate an Fixkosten der Notgroschen abdecken soll – "
            "eine Reserve für unerwartete Ausgaben oder Einkommensausfälle "
            "(z. B. Jobverlust, Reparaturen). 3 Monate gelten als absolutes "
            "Minimum, 6 Monate als komfortabel; bei unsicherem Einkommen "
            "(Selbstständigkeit) eher mehr."
        ), 1, 2)

        fixed_hint = QLabel(
            "Vorbelegt aus deinen laufenden wiederkehrenden Ausgaben-Vorlagen "
            "(Miete, Versicherungen, …). Frei anpassbar, falls nicht alle "
            "Fixkosten als wiederkehrende Buchung erfasst sind."
        )
        fixed_hint.setWordWrap(True)
        ng_grid.addWidget(fixed_hint, 2, 0, 1, 3)

        self.notgroschen_preview_label = QLabel()
        self.notgroschen_preview_label.setWordWrap(True)
        ng_grid.addWidget(self.notgroschen_preview_label, 3, 0, 1, 3)

        ng_create_btn = QPushButton("Notgroschen-Ziel anlegen/aktualisieren")
        ng_create_btn.clicked.connect(self._on_create_or_update_notgroschen)
        ng_grid.addWidget(ng_create_btn, 4, 0, 1, 3)

        # -- Abschnitt B: Anlage-Empfehlung --
        rec_group = QGroupBox("Anlage-Empfehlung (einfache Faustregel)")
        layout.addWidget(rec_group)
        rec_grid = QGridLayout(rec_group)

        rec_grid.addWidget(QLabel("Netto-Einkommen (monatlich, €):"), 0, 0)
        self.planning_income_spin = QDoubleSpinBox()
        self.planning_income_spin.setRange(0, 1_000_000)
        self.planning_income_spin.setDecimals(2)
        self.planning_income_spin.setValue(2500)
        rec_grid.addWidget(self.planning_income_spin, 0, 1)

        rec_grid.addWidget(QLabel("Startkapital (€):"), 1, 0)
        self.planning_capital_spin = QDoubleSpinBox()
        self.planning_capital_spin.setRange(0, 10_000_000)
        self.planning_capital_spin.setDecimals(2)
        rec_grid.addWidget(self.planning_capital_spin, 1, 1)

        rec_grid.addWidget(QLabel("Freizeit-/Pufferbudget (% vom Netto):"), 2, 0)
        self.planning_leisure_percent_spin = QDoubleSpinBox()
        self.planning_leisure_percent_spin.setRange(0, 50)
        self.planning_leisure_percent_spin.setValue(10)
        rec_grid.addWidget(self.planning_leisure_percent_spin, 2, 1)
        rec_grid.addWidget(make_help_button(
            "Anteil des Netto-Einkommens, der für Freizeit, Hobbys oder als "
            "spontaner finanzieller Puffer reserviert bleibt, statt komplett "
            "auf Notgroschen/Sparziele/ETF verteilt zu werden. Rein "
            "informativ – wird nirgends automatisch als Buchung angelegt."
        ), 2, 2)

        self.planning_include_goals_check = QCheckBox(
            "Weitere Sparziele einbeziehen (Priorität siehe Sparziele-Tab)")
        self.planning_include_goals_check.setChecked(True)
        rec_grid.addWidget(self.planning_include_goals_check, 3, 0, 1, 3)

        self.planning_risk_check = QCheckBox(
            "Risikoprofil/Anlagehorizont für den ETF-Anteil berücksichtigen (optional)")
        self.planning_risk_check.toggled.connect(self._on_risk_toggle_changed)
        rec_grid.addWidget(self.planning_risk_check, 4, 0, 1, 3)

        rec_grid.addWidget(QLabel("Anlagehorizont (Jahre):"), 5, 0)
        self.planning_horizon_spin = QSpinBox()
        self.planning_horizon_spin.setRange(0, 60)
        self.planning_horizon_spin.setValue(10)
        self.planning_horizon_spin.setEnabled(False)
        rec_grid.addWidget(self.planning_horizon_spin, 5, 1)
        rec_grid.addWidget(make_help_button(
            "Wie viele Jahre das Geld voraussichtlich investiert bleibt, "
            "bevor es gebraucht wird. Kurzer Horizont = höheres Risiko, "
            "dass ein Kurseinbruch sich nicht mehr erholt, bevor das Geld "
            "gebraucht wird – daher bei kurzem Horizont ein kleinerer "
            "ETF-Anteil."
        ), 5, 2)

        rec_grid.addWidget(QLabel("Risikoprofil:"), 6, 0)
        self.planning_risk_combo = QComboBox()
        self.planning_risk_combo.addItem("Konservativ", "konservativ")
        self.planning_risk_combo.addItem("Ausgewogen", "ausgewogen")
        self.planning_risk_combo.addItem("Offensiv", "offensiv")
        self.planning_risk_combo.setCurrentIndex(1)
        self.planning_risk_combo.setEnabled(False)
        rec_grid.addWidget(self.planning_risk_combo, 6, 1)
        rec_grid.addWidget(make_help_button(
            "Wie viel Wertschwankung (und damit Verlustrisiko) du bereit "
            "bist einzugehen, um langfristig höhere Renditechancen zu "
            "haben. Konservativ = mehr Sicherheitsreserve, weniger "
            "ETF-Anteil; offensiv = mehr ETF-Anteil, mehr Schwankung."
        ), 6, 2)

        calc_rec_btn = QPushButton("Empfehlung berechnen")
        calc_rec_btn.clicked.connect(self._on_calculate_recommendation)
        rec_grid.addWidget(calc_rec_btn, 7, 0, 1, 3)

        self.recommendation_label = QLabel()
        self.recommendation_label.setWordWrap(True)
        rec_grid.addWidget(self.recommendation_label, 8, 0, 1, 3)

        action_box = QHBoxLayout()
        rec_grid.addLayout(action_box, 9, 0, 1, 3)
        apply_etf_btn = QPushButton("Monatliche ETF-Rate übernehmen")
        apply_etf_btn.clicked.connect(self._on_apply_recommendation_to_etf)
        action_box.addWidget(apply_etf_btn)
        apply_capital_btn = QPushButton("Startkapital-Anteile als Fortschritt vormerken")
        apply_capital_btn.clicked.connect(self._on_apply_capital_to_goals)
        action_box.addWidget(apply_capital_btn)
        action_box.addStretch()

        self.apply_capital_as_transaction_check = QCheckBox(
            "Dabei auch als Buchung verbuchen (Kontostand sinkt entsprechend)")
        self.apply_capital_as_transaction_check.setChecked(True)
        rec_grid.addWidget(self.apply_capital_as_transaction_check, 10, 0, 1, 3)

        capital_hint = QLabel(
            "Wichtig: Ohne diese Buchung bleibt dein Kontostand oben "
            "unverändert, obwohl die Sparziele-Fortschritte steigen – "
            "dasselbe Geld würde dir beim nächsten Mal fälschlich erneut "
            "als Startkapital angeboten. Häkchen nur entfernen, wenn das "
            "eingegebene Startkapital NICHT aus deinem hinterlegten "
            "Kontostand stammt (z. B. separates Erbe/Depot, das dort nicht "
            "mitgezählt wird)."
        )
        capital_hint.setWordWrap(True)
        rec_grid.addWidget(capital_hint, 11, 0, 1, 3)

        disclaimer = QLabel(
            "Diese Aufteilung folgt der gängigen Faustregel „Notgroschen "
            "(und ggf. weitere Ziele) vor Investieren“ sowie einer einfachen "
            "Horizont-/Risiko-Faustregel für den ETF-Anteil. Beides sind "
            "transparente Modellrechnungen – KEINE individuelle "
            "Finanzberatung. Sie berücksichtigen weder Schulden noch "
            "Steuern noch deine tatsächliche persönliche Risikotragfähigkeit. "
            "Alle Werte lassen sich frei anpassen; für eine verbindliche "
            "Einschätzung wende dich an eine unabhängige Finanzberatung."
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
                "Noch kein Kontostand hinterlegt – oben Stichtag und Betrag "
                "eintragen und speichern."
            )
        else:
            self.current_balance_label.setText(
                f"Aktueller Kontostand (berechnet): {fmt_amount(balance)}"
            )

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
            status = (f"Bestehendes Sparziel „Notgroschen“: {fmt_amount(existing['current_amount'])} "
                      f"von aktuell {fmt_amount(existing['target_amount'])} angespart.")
        else:
            status = "Noch kein Sparziel „Notgroschen“ angelegt."
        self.notgroschen_preview_label.setText(
            f"Zielbetrag bei {months} Monaten Fixkosten: {fmt_amount(target)}\n{status}"
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
            f"Monatlich verfügbar (Netto abzüglich Fixkosten von {fmt_amount(fixed)} und "
            f"Freizeitbudget von {fmt_amount(leisure)}): {fmt_amount(rec['monthly_available'])}",
            f"Startkapital: {fmt_amount(capital)}",
            "",
        ]
        for g in rec["goals"]:
            if g["fully_funded"]:
                status = "bereits voll gedeckt" if g["gap_before"] <= 0 else "wird damit voll gedeckt"
            else:
                eta = (f", ca. {g['months_to_fill']} Monate bei diesem Tempo"
                       if g["months_to_fill"] else ", reicht mit aktuellem Tempo noch nicht")
                status = f"Lücke bleibt: {fmt_amount(g['remaining_gap'])}{eta}"
            lines.append(
                f"• {g['name']} (Ziel: {fmt_amount(g['target_amount'])}, "
                f"bereits {fmt_amount(g['current_amount'])} vorhanden): "
                f"{fmt_amount(g['capital_allocated'])} aus Startkapital, "
                f"{fmt_amount(g['monthly_allocated'])}/Monat – {status}"
            )

        lines.append("")
        if rec["risk_applied"]:
            lines.append(
                f"Rest zum Investieren – bei {int(self.planning_horizon_spin.value())} Jahren "
                f"Horizont, Profil „{self.planning_risk_combo.currentText()}“: empfohlener "
                f"ETF-Anteil {rec['equity_share_percent']}%, Rest als Sicherheitsreserve:"
            )
            lines.append(
                f"  → ETF-Sparplan: {fmt_amount(rec['monthly_to_equity'])}/Monat, "
                f"{fmt_amount(rec['capital_to_equity'])} Startkapital"
            )
            lines.append(
                f"  → Sicherheitsreserve (z. B. Tagesgeld): "
                f"{fmt_amount(rec['monthly_to_safety'])}/Monat, "
                f"{fmt_amount(rec['capital_to_safety'])} Startkapital"
            )
        else:
            lines.append(
                f"Rest zum Investieren (z. B. ETF-Sparplan): "
                f"{fmt_amount(rec['monthly_to_etf'])}/Monat, "
                f"{fmt_amount(rec['capital_to_etf'])} Startkapital"
            )

        self.recommendation_label.setText("\n".join(lines))

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

        form_group = QGroupBox("Sparplan")
        layout.addWidget(form_group)
        form = QGridLayout(form_group)

        form.addWidget(QLabel("Name:"), 0, 0)
        self.etf_name_edit = QLineEdit("Mein ETF-Sparplan")
        form.addWidget(self.etf_name_edit, 0, 1)

        form.addWidget(QLabel("Monatliche Rate (€):"), 1, 0)
        self.etf_amount_spin = QDoubleSpinBox()
        self.etf_amount_spin.setRange(1, 100_000)
        self.etf_amount_spin.setDecimals(2)
        self.etf_amount_spin.setValue(100)
        form.addWidget(self.etf_amount_spin, 1, 1)

        form.addWidget(QLabel("Erwartete jährl. Rendite (%):"), 2, 0)
        self.etf_return_spin = QDoubleSpinBox()
        self.etf_return_spin.setRange(-20, 30)
        self.etf_return_spin.setValue(6.0)
        form.addWidget(self.etf_return_spin, 2, 1)

        form.addWidget(QLabel("Laufzeit (Jahre):"), 3, 0)
        self.etf_years_spin = QSpinBox()
        self.etf_years_spin.setRange(1, 60)
        self.etf_years_spin.setValue(10)
        form.addWidget(self.etf_years_spin, 3, 1)

        form.addWidget(QLabel("Jährliche Erhöhung der Sparrate (%):"), 4, 0)
        self.etf_increase_spin = QDoubleSpinBox()
        self.etf_increase_spin.setRange(0, 50)
        form.addWidget(self.etf_increase_spin, 4, 1)
        form.addWidget(make_help_button(
            "Erhöht die monatliche Sparrate jedes Jahr um diesen "
            "Prozentsatz, z. B. um eine erwartete Gehaltssteigerung "
            "nachzubilden. 0 % = die Sparrate bleibt über die gesamte "
            "Laufzeit konstant."
        ), 4, 2)

        form.addWidget(QLabel("Maximale Sparrate (€, 0 = kein Deckel):"), 5, 0)
        self.etf_cap_spin = QDoubleSpinBox()
        self.etf_cap_spin.setRange(0, 100_000)
        form.addWidget(self.etf_cap_spin, 5, 1)
        form.addWidget(make_help_button(
            "Obergrenze für die Sparrate, falls sie sich durch die "
            "jährliche Erhöhung sonst unbegrenzt weiter steigern würde. "
            "0 bedeutet: kein Deckel, die Rate wächst ungebremst weiter."
        ), 5, 2)

        # -- Steuer-Einstellungen --
        tax_group = QGroupBox("Deutsche Kapitalertragsteuer (vereinfacht, anpassbar)")
        layout.addWidget(tax_group)
        tax_grid = QGridLayout(tax_group)

        self.etf_vorab_check = QCheckBox(
            "Jährliche Vorabpauschale simulieren (statt Einmalbesteuerung am Laufzeitende)")
        self.etf_vorab_check.toggled.connect(self._on_vorab_toggled)
        tax_grid.addWidget(self.etf_vorab_check, 0, 0, 1, 3)

        tax_grid.addWidget(QLabel("Basiszins (%, jährlich vom BMF festgelegt):"), 1, 0)
        self.etf_basiszins_spin = QDoubleSpinBox()
        self.etf_basiszins_spin.setRange(0, 15)
        self.etf_basiszins_spin.setValue(2.55)
        self.etf_basiszins_spin.setEnabled(False)
        tax_grid.addWidget(self.etf_basiszins_spin, 1, 1)
        tax_grid.addWidget(make_help_button(
            "Zinssatz, den das Bundesfinanzministerium jährlich für die "
            "Vorabpauschale-Berechnung festlegt (orientiert sich an "
            "langfristigen Bundesanleihen). Ändert sich jährlich – der "
            "voreingestellte Wert ist nur ein Richtwert."
        ), 1, 2)

        tax_grid.addWidget(QLabel("Teilfreistellung (%):"), 2, 0)
        self.etf_teilfreistellung_spin = QDoubleSpinBox()
        self.etf_teilfreistellung_spin.setRange(0, 60)
        self.etf_teilfreistellung_spin.setValue(30)
        tax_grid.addWidget(self.etf_teilfreistellung_spin, 2, 1)
        tax_grid.addWidget(make_help_button(
            "Anteil des Fondsgewinns, der steuerfrei bleibt (§20 InvStG). "
            "30 % ist der übliche Satz für Aktienfonds-ETFs mit mindestens "
            "51 % Aktienquote. Bei Anleihen-ETFs 0 %, bei Mischfonds meist "
            "15 %, bei Immobilienfonds 60–80 %."
        ), 2, 2)

        tax_grid.addWidget(QLabel("Kapitalertragsteuer (%):"), 3, 0)
        self.etf_kest_spin = QDoubleSpinBox()
        self.etf_kest_spin.setRange(0, 50)
        self.etf_kest_spin.setValue(25)
        tax_grid.addWidget(self.etf_kest_spin, 3, 1)
        tax_grid.addWidget(make_help_button(
            "Die pauschale Abgeltungsteuer auf Kapitalerträge in "
            "Deutschland, gesetzlich 25 %."
        ), 3, 2)

        tax_grid.addWidget(QLabel("Solidaritätszuschlag (%):"), 4, 0)
        self.etf_soli_spin = QDoubleSpinBox()
        self.etf_soli_spin.setRange(0, 20)
        self.etf_soli_spin.setValue(5.5)
        tax_grid.addWidget(self.etf_soli_spin, 4, 1)
        tax_grid.addWidget(make_help_button(
            "Zuschlag von 5,5 % auf die Kapitalertragsteuer (nicht auf den "
            "Gewinn selbst) – gesetzlich vorgegeben."
        ), 4, 2)

        tax_grid.addWidget(QLabel("Sparerpauschbetrag (€/Jahr):"), 5, 0)
        self.etf_pauschbetrag_spin = QDoubleSpinBox()
        self.etf_pauschbetrag_spin.setRange(0, 5000)
        self.etf_pauschbetrag_spin.setDecimals(0)
        self.etf_pauschbetrag_spin.setValue(1000)
        tax_grid.addWidget(self.etf_pauschbetrag_spin, 5, 1)
        tax_grid.addWidget(make_help_button(
            "Steuerfreibetrag auf Kapitalerträge: 1.000 € pro Jahr bei "
            "Einzelveranlagung, 2.000 € bei Zusammenveranlagung (Ehepaare, "
            "Stand 2023)."
        ), 5, 2)

        self.etf_tax_hint = QLabel()
        self.etf_tax_hint.setWordWrap(True)
        self._update_tax_hint()
        tax_grid.addWidget(self.etf_tax_hint, 6, 0, 1, 3)

        calc_btn = QPushButton("Berechnen & Speichern")
        calc_btn.clicked.connect(self._on_calculate_etf)
        layout.addWidget(calc_btn)

        self.etf_summary_label = QLabel()
        self.etf_summary_label.setWordWrap(True)
        layout.addWidget(self.etf_summary_label)

        self.etf_result_table = QTableWidget(0, 5)
        self.etf_result_table.setHorizontalHeaderLabels(
            ["Jahr", "Sparrate", "Eingezahlt", "Wert", "Gewinn"])
        self.etf_result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.etf_result_table.setMaximumHeight(220)
        layout.addWidget(self.etf_result_table)

        plan_manage_box = QHBoxLayout()
        layout.addLayout(plan_manage_box)
        plan_manage_box.addWidget(QLabel("Gespeicherter Plan:"))
        self.etf_saved_plans_combo = QComboBox()
        plan_manage_box.addWidget(self.etf_saved_plans_combo, 1)
        del_btn = QPushButton("Löschen")
        del_btn.clicked.connect(self._on_delete_etf_plan)
        plan_manage_box.addWidget(del_btn)

        layout.addWidget(QLabel("Vergleich gespeicherter Sparpläne (Wertentwicklung, vor Steuern):"))
        self.etf_compare_widget = EtfComparisonWidget()
        layout.addWidget(self.etf_compare_widget)

        self._refresh_etf_plan_selector()
        self._refresh_etf_comparison()
        return outer

    def _on_vorab_toggled(self, active):
        self.etf_basiszins_spin.setEnabled(active)
        self._update_tax_hint()

    def _update_tax_hint(self):
        if self.etf_vorab_check.isChecked():
            text = ("Hinweis: Simuliert die jährliche Vorabpauschale (Basisertrag = "
                    "Wert zu Jahresbeginn × Basiszins × 70 %, gedeckelt auf den "
                    "tatsächlichen Wertzuwachs). Der Sparerpauschbetrag steht dabei "
                    "JÄHRLICH neu zur Verfügung. Bereits versteuerte Beträge werden "
                    "bei der Steuer am Laufzeitende angerechnet (keine "
                    "Doppelbesteuerung). Kirchensteuer bleibt unberücksichtigt.")
        else:
            text = ("Hinweis: Vereinfachte Rechnung ohne jährliche Vorabpauschale – "
                    "Steuer wird pauschal auf den Gesamtgewinn am Laufzeitende "
                    "angesetzt, mit dem Sparerpauschbetrag nur EINMALIG am Ende. "
                    "Kirchensteuer bleibt unberücksichtigt.")
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
                f" Während der Laufzeit wurden bereits {fmt_amount(total_vorab_tax_paid)} "
                f"Steuern auf Vorabpauschalen gezahlt (im Endwert schon berücksichtigt); "
                f"davon {fmt_amount(cumulative_pretaxed_gain)} Gewinn wurden bei der "
                f"Steuer am Ende angerechnet."
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
            f"Nach {years} Jahren bei {annual_return:.2f}% p.a.: "
            f"eingezahlt {fmt_amount(final['invested'])}, "
            f"Endwert vor Abschluss-Steuer {fmt_amount(final['value'])}, "
            f"Gewinn {fmt_amount(tax['gain'])}.\n"
            f"Steuer bei (angenommenem) Verkauf: {fmt_amount(final_tax_amount)} "
            f"→ Endwert nach Steuern ca. {fmt_amount(value_after_tax)}."
            f"{vorab_note}"
        )

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
            label = f"{plan['name']} ({plan['duration_years']} Jahre, {plan['start_date']})"
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
        switcher_box.addWidget(QLabel("Ansicht:"))
        self.stats_view_combo = QComboBox()
        self.stats_view_combo.addItem("Ausgaben nach Kategorie (Kreisdiagramm)", "kategorien")
        self.stats_view_combo.addItem("Einnahmen/Ausgaben-Trend", "trend")
        self.stats_view_combo.addItem("Geldfluss (Sankey-Diagramm)", "fluss")
        self.stats_view_combo.currentIndexChanged.connect(self._on_stats_view_changed)
        switcher_box.addWidget(self.stats_view_combo)
        switcher_box.addStretch()

        self.stats_stack = QStackedWidget()
        layout.addWidget(self.stats_stack)

        self.stats_stack.addWidget(self._build_pie_section())
        self.stats_stack.addWidget(self._build_trend_section())
        self.stats_stack.addWidget(self._build_sankey_section())

        self._refresh_stats()
        return root

    def _on_stats_view_changed(self, index):
        self.stats_stack.setCurrentIndex(index)

    def _build_pie_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)

        nav = QHBoxLayout()
        layout.addLayout(nav)
        nav.addWidget(QLabel("Ausgaben nach Kategorie –"))
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
        nav.addWidget(QLabel("Trend – letzte"))
        self.trend_months_spin = QSpinBox()
        self.trend_months_spin.setRange(2, 24)
        self.trend_months_spin.setValue(6)
        self.trend_months_spin.valueChanged.connect(self._on_trend_months_changed)
        nav.addWidget(self.trend_months_spin)
        nav.addWidget(QLabel("Monate (bezogen auf den gewählten Monat)"))
        nav.addStretch()
        legend = QLabel("🟩 Einnahmen   🟥 Ausgaben")
        nav.addWidget(legend)

        self.trend_widget = TrendChartWidget()
        layout.addWidget(self.trend_widget)
        return section

    def _build_sankey_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)

        nav = QHBoxLayout()
        layout.addLayout(nav)
        nav.addWidget(QLabel("Geldfluss –"))
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
    """
    <font color="#aeb6c0">
        <b><font color="#c8ced6">Links - </font></b>
        Einnahmen nach Kategorie&nbsp;&nbsp;·&nbsp;&nbsp;
        <b><font color="#c8ced6">Rechts - </font></b>
        Ausgaben nach Kategorie
        (<font color="#4caf50"><b>Überschuss</b></font> /
        <font color="#e05245"><b>Fehlbetrag</b></font>).<br>
        Die Bänder zeigen die anteilige Verteilung des Geldflusses
        und keine direkte Zuordnung einzelner Buchungen.
    </font>
    """
)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.sankey_widget = SankeyWidget()
        layout.addWidget(self.sankey_widget)
        return section

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
            right_nodes.append(("Übrig/Gespart", "💰", total_income - total_expense,
                                 QColor(30, 140, 61)))
        elif total_expense > total_income + 0.005:
            left_nodes.append(("Fehlbetrag", "⚠️", total_expense - total_income,
                                QColor(191, 56, 38)))

        self.sankey_widget.set_data(left_nodes, right_nodes, max(total_income, total_expense))

    # =====================================================================
    # Tab 7: Export / Import
    # =====================================================================

    def _build_export_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        csv_label = QLabel(
            "CSV-Export aller Buchungen – zum Öffnen/Weiterverarbeiten in "
            "Excel oder Numbers/LibreOffice Calc."
        )
        csv_label.setWordWrap(True)
        layout.addWidget(csv_label)
        csv_btn = QPushButton("Buchungen als CSV exportieren…")
        csv_btn.clicked.connect(self._on_export_csv)
        layout.addWidget(csv_btn)

        csv_import_label = QLabel(
            "CSV-Import: Buchungen aus einer anderen Haushaltsbuch- oder "
            "Banking-Software übernehmen. Trennzeichen sowie deutsche/"
            "englische Zahlen- und Datumsformate werden automatisch erkannt."
        )
        csv_import_label.setWordWrap(True)
        layout.addWidget(csv_import_label)
        csv_import_btn = QPushButton("Buchungen aus CSV importieren…")
        csv_import_btn.clicked.connect(self._on_import_csv)
        layout.addWidget(csv_import_btn)

        json_label = QLabel(
            "Vollständiges Backup (JSON) – enthält alle Buchungen, Vorlagen, "
            "Budgets, Sparziele, ETF-Pläne und Kategorien."
        )
        json_label.setWordWrap(True)
        layout.addWidget(json_label)
        export_json_btn = QPushButton("Backup als JSON exportieren…")
        export_json_btn.clicked.connect(self._on_export_json)
        layout.addWidget(export_json_btn)
        import_json_btn = QPushButton("Backup aus JSON importieren…")
        import_json_btn.clicked.connect(self._on_import_json)
        layout.addWidget(import_json_btn)

        self.export_status_label = QLabel()
        layout.addWidget(self.export_status_label)
        layout.addStretch()
        return widget

    def _on_export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Buchungen als CSV exportieren",
                                               "haushaltsbuch_export.csv", "CSV-Dateien (*.csv)")
        if path:
            self.store.export_transactions_csv(path)
            self.export_status_label.setText(f"CSV exportiert nach: {path}")

    def _on_import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Buchungen aus CSV importieren",
                                               "", "CSV-Dateien (*.csv)")
        if not path:
            return
        try:
            result = self.store.import_transactions_csv(path)
        except Exception as exc:
            QMessageBox.critical(self, "Fehler", f"CSV konnte nicht gelesen werden:\n{exc}")
            return

        summary = f"{result['imported']} Buchung(en) importiert"
        if result["skipped"]:
            summary += f", {result['skipped']} übersprungen"
        self.export_status_label.setText(f"CSV importiert von: {path} – {summary}.")

        detail_lines = "\n".join(result["errors"][:15])
        if len(result["errors"]) > 15:
            detail_lines += f"\n… und {len(result['errors']) - 15} weitere."
        icon = QMessageBox.Information if not result["errors"] else QMessageBox.Warning
        box = QMessageBox(icon, "CSV-Import", summary + (":" if detail_lines else "."), parent=self)
        if detail_lines:
            box.setDetailedText(detail_lines)
        box.exec()

        self.store.ensure_horizon(self._selected_calendar_month())
        self._after_transactions_changed()
        self._refresh_stats()

    def _on_export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Backup als JSON exportieren",
                                               "haushaltsbuch_backup.json", "JSON-Dateien (*.json)")
        if path:
            self.store.export_backup_json(path)
            self.export_status_label.setText(f"Backup exportiert nach: {path}")

    def _on_import_json(self):
        response = QMessageBox.warning(
            self, "Backup importieren", "Import ersetzt alle aktuellen Daten. Fortfahren?",
            QMessageBox.Ok | QMessageBox.Cancel,
        )
        if response != QMessageBox.Ok:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Backup importieren",
                                               "", "JSON-Dateien (*.json)")
        if not path:
            return
        self.store.import_backup_json(path)
        self.store.ensure_horizon(self._selected_calendar_month())
        self.export_status_label.setText(f"Backup importiert von: {path}")
        self._after_transactions_changed()
        self._refresh_goals_tab()
        self._refresh_stats()
        self._refresh_etf_plan_selector()
        self._refresh_etf_comparison()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Plutos")
    app.setOrganizationName("Plutos")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
