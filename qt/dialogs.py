"""
Dialoge für die Qt-Variante von HaushaltsBuch.

Nutzt QDateEdit (mit Kalender-Popup) statt manuell geparster Text-Datumsfelder
wie in der GTK-Version - robuster und komfortabler, kein eigener
Datums-Parser mehr nötig.
"""

import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QDoubleSpinBox, QDateEdit, QCheckBox, QPushButton,
    QDialogButtonBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QToolButton, QToolTip, QMessageBox, QWidget,
)
from PySide6.QtCore import Qt, QDate

from db import FinanceStore
from charts import fmt_amount

ICON_PICKER_CHOICES = [
    "💶", "💼", "🏠", "🛒", "🍔", "☕", "🚌", "🚗", "⛽", "✈️",
    "🎉", "🎬", "🎮", "📱", "💻", "👕", "💊", "🏥", "🛡️", "📚",
    "🎓", "🐶", "🐱", "🎸", "⚽", "🏋️", "🎁", "💰", "📦", "➕",
]


def make_help_button(text):
    """Kleiner '?'-Button: zeigt beim Klick (und beim Hovern) eine kurze
    Erklärung. Pendant zu _help_button() in der GTK-Version."""
    button = QToolButton()
    button.setText("?")
    button.setToolTip(text)
    button.setFixedSize(22, 22)
    button.setAutoRaise(True)
    button.clicked.connect(
        lambda: QToolTip.showText(button.mapToGlobal(button.rect().bottomLeft()), text, button)
    )
    return button


def _qdate_to_iso(qdate: QDate) -> str:
    return qdate.toString("yyyy-MM-dd")


def _iso_to_qdate(iso_text: str) -> QDate:
    return QDate.fromString(iso_text, "yyyy-MM-dd")


class TransactionDialog(QDialog):
    """Dialog zum Hinzufügen ODER Bearbeiten einer Buchung. Wird `existing`
    übergeben, läuft der Dialog im Bearbeiten-Modus: Felder sind
    vorausgefüllt, die Option "wiederkehrend" ist ausgeblendet (bearbeitet
    wird immer nur die einzelne Buchung, nicht die Vorlage)."""

    def __init__(self, parent, store: FinanceStore, default_date: datetime.date, existing=None):
        super().__init__(parent)
        self.store = store
        self.existing = existing
        self.setWindowTitle("Buchung bearbeiten" if existing else "Buchung hinzufügen")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        layout.addLayout(grid)

        grid.addWidget(QLabel("Art:"), 0, 0)
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Ausgabe", "ausgabe")
        self.kind_combo.addItem("Einnahme", "einnahme")
        default_kind = existing["kind"] if existing else "ausgabe"
        self.kind_combo.setCurrentIndex(0 if default_kind == "ausgabe" else 1)
        self.kind_combo.currentIndexChanged.connect(self._reload_categories)
        grid.addWidget(self.kind_combo, 0, 1)

        grid.addWidget(QLabel("Kategorie:"), 1, 0)
        self.category_combo = QComboBox()
        grid.addWidget(self.category_combo, 1, 1)
        self._reload_categories(preselect=existing["category_id"] if existing else None)

        grid.addWidget(QLabel("Betrag (€):"), 2, 0)
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0, 1_000_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setSuffix(" €")
        self.amount_spin.setValue(abs(existing["amount"]) if existing else 0)
        grid.addWidget(self.amount_spin, 2, 1)

        grid.addWidget(QLabel("Datum:"), 3, 0)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        initial_date = datetime.date.fromisoformat(existing["date"]) if existing else default_date
        self.date_edit.setDate(QDate(initial_date.year, initial_date.month, initial_date.day))
        grid.addWidget(self.date_edit, 3, 1)

        grid.addWidget(QLabel("Beschreibung:"), 4, 0)
        self.description_edit = QLineEdit(existing["description"] if existing else "")
        grid.addWidget(self.description_edit, 4, 1)

        if not existing:
            self.recurring_check = QCheckBox("Wiederkehrende Buchung")
            self.recurring_check.toggled.connect(self._on_recurring_toggled)
            grid.addWidget(self.recurring_check, 5, 0, 1, 2)

            self.frequency_combo = QComboBox()
            self.frequency_combo.addItem("Wöchentlich", "woechentlich")
            self.frequency_combo.addItem("Monatlich", "monatlich")
            self.frequency_combo.addItem("Jährlich", "jaehrlich")
            self.frequency_combo.setCurrentIndex(1)
            self.frequency_combo.setEnabled(False)
            grid.addWidget(self.frequency_combo, 6, 0, 1, 2)
        else:
            self.recurring_check = None
            if existing["recurring_template_id"] is not None:
                note = QLabel(
                    "Diese Buchung stammt aus einer wiederkehrenden Vorlage. "
                    "Änderungen betreffen nur diese einzelne Buchung."
                )
                note.setWordWrap(True)
                grid.addWidget(note, 5, 0, 1, 2)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reload_categories(self, *_args, preselect=None):
        kind = self.kind_combo.currentData()
        self.category_combo.clear()
        active_index = 0
        for i, cat in enumerate(self.store.list_categories(kind=kind)):
            self.category_combo.addItem(f"{cat['icon']} {cat['name']}", cat["id"])
            if preselect and cat["id"] == preselect:
                active_index = i
        self.category_combo.setCurrentIndex(active_index)

    def _on_recurring_toggled(self, active):
        self.frequency_combo.setEnabled(active)

    def save(self):
        kind = self.kind_combo.currentData()
        category_id = self.category_combo.currentData()
        raw_amount = self.amount_spin.value()
        amount = raw_amount if kind == "einnahme" else -raw_amount
        description = self.description_edit.text().strip()
        date_iso = _qdate_to_iso(self.date_edit.date())

        if self.existing:
            self.store.update_transaction(self.existing["id"], date_iso, amount,
                                           category_id, description)
        elif self.recurring_check is not None and self.recurring_check.isChecked():
            frequency = self.frequency_combo.currentData()
            self.store.add_recurring_template(category_id, amount, description,
                                               frequency, date_iso)
        else:
            self.store.add_transaction(date_iso, amount, category_id, description)


class RecurringTemplateEditDialog(QDialog):
    """Bearbeitet eine wiederkehrende Vorlage. Änderungen wirken sich nur auf
    zukünftige Buchungen aus; vergangene bleiben als historischer Stand
    unverändert (siehe update_recurring_template in db.py)."""

    def __init__(self, parent, store: FinanceStore, template):
        super().__init__(parent)
        self.store = store
        self.template = template
        self.setWindowTitle("Wiederkehrende Vorlage bearbeiten")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        layout.addLayout(grid)

        grid.addWidget(QLabel("Art:"), 0, 0)
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Ausgabe", "ausgabe")
        self.kind_combo.addItem("Einnahme", "einnahme")
        self.kind_combo.setCurrentIndex(0 if template["kind"] == "ausgabe" else 1)
        self.kind_combo.currentIndexChanged.connect(
            lambda: self._reload_categories(preselect=template["category_id"]))
        grid.addWidget(self.kind_combo, 0, 1)

        grid.addWidget(QLabel("Kategorie:"), 1, 0)
        self.category_combo = QComboBox()
        grid.addWidget(self.category_combo, 1, 1)
        self._reload_categories(preselect=template["category_id"])

        grid.addWidget(QLabel("Betrag (€):"), 2, 0)
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0, 1_000_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setValue(abs(template["amount"]))
        grid.addWidget(self.amount_spin, 2, 1)

        grid.addWidget(QLabel("Beschreibung:"), 3, 0)
        self.description_edit = QLineEdit(template["description"] or "")
        grid.addWidget(self.description_edit, 3, 1)

        grid.addWidget(QLabel("Häufigkeit:"), 4, 0)
        self.frequency_combo = QComboBox()
        self.frequency_combo.addItem("Wöchentlich", "woechentlich")
        self.frequency_combo.addItem("Monatlich", "monatlich")
        self.frequency_combo.addItem("Jährlich", "jaehrlich")
        freq_index = {"woechentlich": 0, "monatlich": 1, "jaehrlich": 2}[template["frequency"]]
        self.frequency_combo.setCurrentIndex(freq_index)
        grid.addWidget(self.frequency_combo, 4, 1)

        grid.addWidget(QLabel("Startdatum:"), 5, 0)
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("dd.MM.yyyy")
        self.start_date_edit.setDate(_iso_to_qdate(template["start_date"]))
        grid.addWidget(self.start_date_edit, 5, 1)

        self.no_end_check = QCheckBox("Läuft unbegrenzt weiter")
        self.no_end_check.setChecked(template["end_date"] is None)
        self.no_end_check.toggled.connect(lambda checked: self.end_date_edit.setEnabled(not checked))
        grid.addWidget(self.no_end_check, 6, 0, 1, 2)

        grid.addWidget(QLabel("Enddatum:"), 7, 0)
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("dd.MM.yyyy")
        if template["end_date"]:
            self.end_date_edit.setDate(_iso_to_qdate(template["end_date"]))
        else:
            self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.setEnabled(template["end_date"] is not None)
        grid.addWidget(self.end_date_edit, 7, 1)

        note = QLabel(
            "Änderungen wirken standardmäßig nur auf zukünftige Buchungen (ab "
            "heute) – bereits vergangene bleiben als historischer Stand "
            "unverändert (z. B. sinnvoll bei einer Gehaltserhöhung: alte "
            "Monate zeigen weiterhin den alten Betrag)."
        )
        note.setWordWrap(True)
        grid.addWidget(note, 8, 0, 1, 2)

        self.apply_to_past_check = QCheckBox(
            "Änderungen auch auf bereits vergangene Buchungen anwenden "
            "(überschreibt deren bisherige Werte rückwirkend)"
        )
        grid.addWidget(self.apply_to_past_check, 9, 0, 1, 2)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reload_categories(self, preselect=None):
        kind = self.kind_combo.currentData()
        self.category_combo.clear()
        active_index = 0
        for i, cat in enumerate(self.store.list_categories(kind=kind)):
            self.category_combo.addItem(f"{cat['icon']} {cat['name']}", cat["id"])
            if preselect and cat["id"] == preselect:
                active_index = i
        self.category_combo.setCurrentIndex(active_index)

    def save(self):
        kind = self.kind_combo.currentData()
        category_id = self.category_combo.currentData()
        raw_amount = self.amount_spin.value()
        amount = raw_amount if kind == "einnahme" else -raw_amount
        description = self.description_edit.text().strip()
        frequency = self.frequency_combo.currentData()
        start_date = _qdate_to_iso(self.start_date_edit.date())
        end_date = None if self.no_end_check.isChecked() else _qdate_to_iso(self.end_date_edit.date())

        self.store.update_recurring_template(
            self.template["id"], category_id, amount, description, frequency,
            start_date, end_date,
            apply_to_past=self.apply_to_past_check.isChecked(),
        )


class RecurringTemplatesDialog(QDialog):
    def __init__(self, parent, store: FinanceStore):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Wiederkehrende Vorlagen")
        self.resize(650, 380)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Läuft eine Vorlage weiter, werden ihre Buchungen automatisch für "
            "jeden Monat erzeugt, den du dir im Kalender ansiehst – unbegrenzt, "
            "bis du sie hier löschst. Tipp: Doppelklick auf eine Vorlage öffnet "
            "sie zum Bearbeiten."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Kategorie", "Betrag", "Häufigkeit", "Start", "Ende"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_edit)
        layout.addWidget(self.table)

        btn_box = QHBoxLayout()
        layout.addLayout(btn_box)

        edit_btn = QPushButton("Bearbeiten")
        edit_btn.clicked.connect(self._on_edit)
        btn_box.addWidget(edit_btn)

        del_btn = QPushButton("Löschen (inkl. künftiger Buchungen)")
        del_btn.clicked.connect(self._on_delete)
        btn_box.addWidget(del_btn)
        btn_box.addStretch()

        close_btn = QPushButton("Schließen")
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(close_btn)

        self._refresh()

    def _refresh(self):
        freq_names = {"woechentlich": "Wöchentlich", "monatlich": "Monatlich",
                      "jaehrlich": "Jährlich"}
        templates = self.store.list_recurring_templates()
        self.table.setRowCount(len(templates))
        for row, t in enumerate(templates):
            values = [
                f"{t['icon']} {t['category_name']}", fmt_amount(t["amount"]),
                freq_names.get(t["frequency"], t["frequency"]),
                t["start_date"], t["end_date"] or "läuft weiter",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, t["id"])
                self.table.setItem(row, col, item)

    def _selected_template_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.UserRole)

    def _on_edit(self, *_args):
        template_id = self._selected_template_id()
        if template_id is None:
            return
        template = self.store.get_recurring_template(template_id)
        dialog = RecurringTemplateEditDialog(self, self.store, template)
        if dialog.exec() == QDialog.Accepted:
            dialog.save()
            self._refresh()

    def _on_delete(self):
        template_id = self._selected_template_id()
        if template_id is None:
            return

        box = QMessageBox(
            QMessageBox.Warning, "Wiederkehrende Vorlage löschen?",
            "Zukünftige (heute oder später datierte) Buchungen dieser Vorlage "
            "werden dabei immer entfernt.",
            QMessageBox.Ok | QMessageBox.Cancel, parent=self,
        )
        past_check = QCheckBox("Auch bereits vergangene Buchungen dieser Vorlage löschen")
        box.setCheckBox(past_check)
        response = box.exec()

        if response == QMessageBox.Ok:
            self.store.delete_recurring_template(
                template_id, delete_past_transactions=past_check.isChecked())
            self._refresh()


class BudgetDialog(QDialog):
    def __init__(self, parent, store: FinanceStore, month, preselect_category_id=None):
        super().__init__(parent)
        self.store = store
        self.month = month
        self.setWindowTitle("Budget setzen")

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        layout.addLayout(grid)

        grid.addWidget(QLabel("Kategorie:"), 0, 0)
        self.category_combo = QComboBox()
        active_index = 0
        for i, cat in enumerate(store.list_categories(kind="ausgabe")):
            self.category_combo.addItem(f"{cat['icon']} {cat['name']}", cat["id"])
            if preselect_category_id and cat["id"] == preselect_category_id:
                active_index = i
        self.category_combo.setCurrentIndex(active_index)
        grid.addWidget(self.category_combo, 0, 1)

        month_name = month.strftime("%B %Y")
        grid.addWidget(QLabel(f"Monatsbudget für {month_name} (€):"), 1, 0)
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0, 1_000_000)
        self.amount_spin.setDecimals(2)
        grid.addWidget(self.amount_spin, 1, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        category_id = self.category_combo.currentData()
        amount = self.amount_spin.value()
        self.store.set_budget(category_id, self.month.strftime("%Y-%m"), amount)


class GoalDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Sparziel hinzufügen")

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        layout.addLayout(grid)

        grid.addWidget(QLabel("Name:"), 0, 0)
        self.name_edit = QLineEdit()
        grid.addWidget(self.name_edit, 0, 1)

        grid.addWidget(QLabel("Zielbetrag (€):"), 1, 0)
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(1, 10_000_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setValue(1000)
        grid.addWidget(self.amount_spin, 1, 1)

        self.no_date_check = QCheckBox("Kein Zieldatum")
        self.no_date_check.setChecked(True)
        self.no_date_check.toggled.connect(lambda checked: self.date_edit.setEnabled(not checked))
        grid.addWidget(self.no_date_check, 2, 0, 1, 2)

        grid.addWidget(QLabel("Zieldatum:"), 3, 0)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setDate(QDate.currentDate().addYears(1))
        self.date_edit.setEnabled(False)
        grid.addWidget(self.date_edit, 3, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        name = self.name_edit.text().strip()
        if not name:
            return None
        target_date = None if self.no_date_check.isChecked() else _qdate_to_iso(self.date_edit.date())
        return {"name": name, "target_amount": self.amount_spin.value(), "target_date": target_date}


class ContributionDialog(QDialog):
    def __init__(self, parent, goal_name):
        super().__init__(parent)
        self.setWindowTitle(f"Einzahlen: {goal_name}")

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Einzuzahlender Betrag (€):"))
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 1_000_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setValue(50)
        layout.addWidget(self.amount_spin)

        self.book_check = QCheckBox("Als Buchung im Haushaltsbuch verbuchen (Kategorie „Sparbeitrag“)")
        self.book_check.setChecked(True)
        layout.addWidget(self.book_check)

        hint = QLabel(
            "Damit taucht die Einzahlung als Ausgabe im Kalender, in Budgets "
            "und Auswertungen auf – so wie das Geld tatsächlich vom Konto "
            "abgeht. Zum rein informativen Vormerken (z. B. externes Depot) "
            "kannst du das Häkchen entfernen."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_amount(self):
        return self.amount_spin.value()

    def get_book_as_transaction(self):
        return self.book_check.isChecked()


class CategoryEditDialog(QDialog):
    def __init__(self, parent, name="", icon="", edit_mode=False):
        super().__init__(parent)
        self.setWindowTitle("Kategorie bearbeiten" if edit_mode else "Kategorie hinzufügen")
        self.edit_mode = edit_mode
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        layout.addLayout(grid)

        grid.addWidget(QLabel("Icon:"), 0, 0)
        self.icon_edit = QLineEdit(icon or "💶")
        self.icon_edit.setMaxLength(4)
        self.icon_edit.setFixedWidth(50)
        grid.addWidget(self.icon_edit, 0, 1)

        grid.addWidget(QLabel("Icon auswählen:"), 1, 0)
        picker = QWidget()
        picker_layout = QGridLayout(picker)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        for i, emoji in enumerate(ICON_PICKER_CHOICES):
            btn = QToolButton()
            btn.setText(emoji)
            btn.setAutoRaise(True)
            btn.clicked.connect(lambda checked=False, e=emoji: self.icon_edit.setText(e))
            picker_layout.addWidget(btn, i // 8, i % 8)
        grid.addWidget(picker, 1, 1)

        grid.addWidget(QLabel("Name:"), 2, 0)
        self.name_edit = QLineEdit(name)
        grid.addWidget(self.name_edit, 2, 1)

        if not edit_mode:
            grid.addWidget(QLabel("Art:"), 3, 0)
            self.kind_combo = QComboBox()
            self.kind_combo.addItem("Ausgabe", "ausgabe")
            self.kind_combo.addItem("Einnahme", "einnahme")
            grid.addWidget(self.kind_combo, 3, 1)
        else:
            self.kind_combo = None

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        name = self.name_edit.text().strip()
        icon = self.icon_edit.text().strip() or "💶"
        if not name:
            return None
        data = {"name": name, "icon": icon}
        if self.kind_combo is not None:
            data["kind"] = self.kind_combo.currentData()
        return data


class CategoryManagerDialog(QDialog):
    def __init__(self, parent, store: FinanceStore):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Kategorien verwalten")
        self.resize(480, 400)

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Icon", "Name", "Art"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)

        btn_box = QHBoxLayout()
        layout.addLayout(btn_box)

        add_btn = QPushButton("Hinzufügen")
        add_btn.clicked.connect(self._on_add)
        btn_box.addWidget(add_btn)

        edit_btn = QPushButton("Bearbeiten")
        edit_btn.clicked.connect(self._on_edit)
        btn_box.addWidget(edit_btn)

        del_btn = QPushButton("Löschen")
        del_btn.clicked.connect(self._on_delete)
        btn_box.addWidget(del_btn)
        btn_box.addStretch()

        close_btn = QPushButton("Schließen")
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(close_btn)

        self._refresh()

    def _refresh(self):
        categories = self.store.list_categories()
        self.table.setRowCount(len(categories))
        for row, c in enumerate(categories):
            icon_item = QTableWidgetItem(c["icon"])
            icon_item.setData(Qt.UserRole, c["id"])
            self.table.setItem(row, 0, icon_item)
            self.table.setItem(row, 1, QTableWidgetItem(c["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(
                "Einnahme" if c["kind"] == "einnahme" else "Ausgabe"))

    def _selected_category(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return {
            "id": self.table.item(row, 0).data(Qt.UserRole),
            "icon": self.table.item(row, 0).text(),
            "name": self.table.item(row, 1).text(),
        }

    def _on_add(self):
        dialog = CategoryEditDialog(self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if data:
                self.store.add_category(data["name"], data["kind"], data["icon"])
                self._refresh()

    def _on_edit(self):
        selected = self._selected_category()
        if not selected:
            return
        dialog = CategoryEditDialog(self, name=selected["name"], icon=selected["icon"],
                                     edit_mode=True)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if data:
                self.store.update_category(selected["id"], data["name"], data["icon"])
                self._refresh()

    def _on_delete(self):
        selected = self._selected_category()
        if not selected:
            return
        response = QMessageBox.warning(
            self, "Kategorie löschen",
            f'Kategorie "{selected["name"]}" wirklich löschen?\n\n'
            "Achtung: Dabei werden auch ALLE Buchungen und wiederkehrenden "
            "Vorlagen dieser Kategorie unwiderruflich gelöscht.",
            QMessageBox.Ok | QMessageBox.Cancel,
        )
        if response == QMessageBox.Ok:
            self.store.delete_category(selected["id"])
            self._refresh()
