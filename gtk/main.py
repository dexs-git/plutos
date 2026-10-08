#!/usr/bin/env python3
"""
Plutos – Das Haushaltsbuch. Budget- und Finanzplaner für Linux Mint.

Funktionen:
    - Buchungen (Einnahmen/Ausgaben) in Kalenderansicht (Monat/Woche/Jahr
      umschaltbar), inkl. wiederkehrender Einträge (laufen unbegrenzt weiter,
      werden für jeden Monat erzeugt, den man sich ansieht) und Bearbeiten
      per Doppelklick
    - Budgets pro Kategorie und Monat mit Fortschrittsbalken
    - Sparziele mit Einzahlungen/Fortschritt, optional als echte Buchung
      verbucht
    - Finanzplanung: Notgroschen-Ziel aus laufenden Fixkosten ableiten sowie
      eine Faustregel-Empfehlung zur Aufteilung von Einkommen/Startkapital auf
      mehrere Sparziele, ETF-Sparplan und Freizeitbudget (optional mit
      Risikoprofil/Anlagehorizont)
    - ETF-Sparplan-Rechner mit Jahresprojektion, steigender Sparrate (mit
      Deckel), vereinfachter deutscher Abgeltungsteuer-Berechnung (wahlweise
      mit jährlicher Vorabpauschale-Simulation) und Vergleichsdiagramm
      mehrerer gespeicherter Pläne
    - Auswertungen: Ausgaben nach Kategorie (Kreisdiagramm), Einnahmen/
      Ausgaben-Trend über mehrere Monate sowie ein Sankey-Geldfluss-Diagramm
      – als umschaltbare Ansichten, nicht alle gleichzeitig sichtbar
    - Kategorien mit eigenem Icon (Klick-Picker oder freie Eingabe), frei
      verwaltbar
    - Export als CSV (Buchungen) und JSON (Vollbackup); Import von CSV
      (automatische Format-Erkennung) und JSON-Backup

Start:
    python3 main.py
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, Pango, PangoCairo
import cairo

import datetime
import math

from db import FinanceStore, add_months

CURRENCY = "€"

CATEGORY_COLORS = [
    (0.20, 0.47, 0.75), (0.85, 0.37, 0.13), (0.17, 0.63, 0.34),
    (0.58, 0.20, 0.75), (0.90, 0.62, 0.00), (0.13, 0.59, 0.66),
    (0.75, 0.18, 0.36), (0.40, 0.40, 0.40), (0.35, 0.70, 0.90),
    (0.95, 0.80, 0.20),
]


def fmt_amount(value):
    return f"{value:,.2f} {CURRENCY}".replace(",", "X").replace(".", ",").replace("X", ".")


def color_for_index(i):
    return CATEGORY_COLORS[i % len(CATEGORY_COLORS)]


GERMAN_MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                  "August", "September", "Oktober", "November", "Dezember"]

# Vorausgewählte Icons für den Klick-Picker in der Kategorienverwaltung.
ICON_PICKER_CHOICES = [
    "💶", "💼", "🏠", "🛒", "🍔", "☕", "🚌", "🚗", "⛽", "✈️",
    "🎉", "🎬", "🎮", "📱", "💻", "👕", "💊", "🏥", "🛡️", "📚",
    "🎓", "🐶", "🐱", "🎸", "⚽", "🏋️", "🎁", "💰", "📦", "➕",
]


def month_label(date_obj):
    return f"{GERMAN_MONTHS[date_obj.month - 1]} {date_obj.year}"


def _widget_fg_color(widget):
    """Liest die tatsächliche Vordergrundfarbe des aktuellen GTK-Themes aus,
    damit selbst gezeichneter (Cairo-)Text bei dunklen wie hellen Themes
    lesbar bleibt, statt eine feste Farbe zu verwenden."""
    ctx = widget.get_style_context()
    color = ctx.get_color(Gtk.StateFlags.NORMAL)
    return (color.red, color.green, color.blue)


def _help_button(explanation):
    """Erzeugt einen kleinen '?'-Button, der beim Klick ein Popover mit einer
    kurzen Erklärung zeigt. Für Fachbegriffe/Einstellungen gedacht, die nicht
    selbsterklärend sind (z. B. Teilfreistellung, Sparerpauschbetrag)."""
    button = Gtk.Button(label="?")
    button.set_relief(Gtk.ReliefStyle.NONE)
    button.set_size_request(26, 26)
    button.set_tooltip_text(explanation)

    popover = Gtk.Popover()
    popover.set_relative_to(button)
    label = Gtk.Label(label=explanation)
    label.set_line_wrap(True)
    label.set_max_width_chars(42)
    label.set_margin_top(8)
    label.set_margin_bottom(8)
    label.set_margin_start(8)
    label.set_margin_end(8)
    popover.add(label)
    label.show()

    button.connect("clicked", lambda w: popover.popup())
    return button


def _nav_button(label_text, callback):
    """Erzeugt einen kompakten ◀/▶-Navigationsbutton. Wird an vier Stellen
    für die Vor-/Zurück-Navigation (Woche, Jahr, Kreisdiagramm-Monat,
    Sankey-Monat) verwendet, um die sich sonst wiederholende
    Button-Erstellung + Signalverbindung zu bündeln."""
    button = Gtk.Button(label=label_text)
    button.connect("clicked", callback)
    return button


def _run_message_dialog(parent, message_type, buttons, text, secondary_text=None):
    """Erzeugt, zeigt (modal) und schließt einen Gtk.MessageDialog in einem
    Aufruf; gibt die Response zurück (z. B. Gtk.ResponseType.OK). Bündelt die
    sonst an vier Stellen wiederholte Erzeugen/run/destroy-Boilerplate für
    Fehler-, Info- und Bestätigungs-Meldungen."""
    dialog = Gtk.MessageDialog(
        transient_for=parent, flags=0, message_type=message_type,
        buttons=buttons, text=text, secondary_text=secondary_text,
    )
    response = dialog.run()
    dialog.destroy()
    return response


# ---------------------------------------------------------------------------
# Hauptfenster
# ---------------------------------------------------------------------------

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Plutos – Das Haushaltsbuch")
        self.set_default_size(1050, 680)
        self.set_border_width(10)
        self.store = FinanceStore()
        self.store.ensure_horizon(datetime.date.today())

        self.selected_day = datetime.date.today()
        self.stats_month = datetime.date.today().replace(day=1)
        self.trend_months = 6
        self.current_etf_plan_id = None

        notebook = Gtk.Notebook()
        self.add(notebook)
        self.notebook = notebook

        notebook.append_page(self._build_transactions_tab(), Gtk.Label(label="Buchungen"))
        notebook.append_page(self._build_budgets_tab(), Gtk.Label(label="Budgets"))
        notebook.append_page(self._build_goals_tab(), Gtk.Label(label="Sparziele"))
        notebook.append_page(self._build_planning_tab(), Gtk.Label(label="Finanzplanung"))
        self.etf_tab_page = self._build_etf_tab()
        notebook.append_page(self.etf_tab_page, Gtk.Label(label="ETF-Sparplan"))
        notebook.append_page(self._build_stats_tab(), Gtk.Label(label="Auswertungen"))
        notebook.append_page(self._build_export_tab(), Gtk.Label(label="Export / Import"))

        self.connect("destroy", Gtk.main_quit)
        
# =====================================================================
# Tab 1: Buchungen (Kalenderansicht)
# =====================================================================

    def _shift_calendar_month(self, delta):
        """Wechselt den Monat der Kalenderansicht."""

        self.month_display_date = add_months(
            self.month_display_date,
            delta
        )

        self.store.ensure_horizon(
            self.month_display_date
        )

        self._refresh_custom_calendar()
        self._refresh_month_balance()
        self._refresh_budgets_tab()


    def _refresh_custom_calendar(self):
        """Aktualisiert die Monatsansicht mit stabilen Kalenderfeldgrößen."""

        if not hasattr(self, "month_day_buttons"):
            return

        year = self.month_display_date.year
        month = self.month_display_date.month

        # ---------------------------------------------------------------
        # Monatsüberschrift
        # ---------------------------------------------------------------

        self.custom_calendar_month_label.set_markup(
            f"<b>{month_label(self.month_display_date)}</b>"
        )

        # ---------------------------------------------------------------
        # Erster Tag des Monats
        # ---------------------------------------------------------------

        first_day = datetime.date(
            year,
            month,
            1
        )

        start_offset = first_day.weekday()

        # ---------------------------------------------------------------
        # Anzahl Tage des Monats
        # ---------------------------------------------------------------

        if month == 12:
            next_month = datetime.date(
                year + 1,
                1,
                1
            )
        else:
            next_month = datetime.date(
                year,
                month + 1,
                1
            )

        days_in_month = (
            next_month - first_day
        ).days

        # ---------------------------------------------------------------
        # Vorheriger Monat
        # ---------------------------------------------------------------

        if month == 1:
            prev_year = year - 1
            prev_month = 12
        else:
            prev_year = year
            prev_month = month - 1

        prev_month_start = datetime.date(
            prev_year,
            prev_month,
            1
        )

        if prev_month == 12:
            after_prev = datetime.date(
                prev_year + 1,
                1,
                1
            )
        else:
            after_prev = datetime.date(
                prev_year,
                prev_month + 1,
                1
            )

        prev_days = (
            after_prev - prev_month_start
        ).days

        today = datetime.date.today()

        # ---------------------------------------------------------------
        # Kalenderwochen aktualisieren
        # ---------------------------------------------------------------

        for row in range(6):

            monday_index = (
                row * 7 - start_offset
            )

            monday_date = (
                first_day
                + datetime.timedelta(
                    days=monday_index
                )
            )

            kw = monday_date.isocalendar().week

            self.calendar_week_labels[row].set_markup(
                f'<span foreground="#777777">'
                f"{kw:02d}"
                f"</span>"
            )

        # ---------------------------------------------------------------
        # 42 Kalenderfelder
        # ---------------------------------------------------------------

        for index, (button, label) in enumerate(
            self.month_day_buttons
        ):

            day_number = (
                index - start_offset + 1
            )

            # -----------------------------------------------------------
            # Datum bestimmen
            # -----------------------------------------------------------

            if day_number < 1:

                d = datetime.date(
                    prev_year,
                    prev_month,
                    prev_days + day_number
                )

            elif day_number > days_in_month:

                d = datetime.date(
                    year,
                    month,
                    days_in_month
                ) + datetime.timedelta(
                    days=day_number - days_in_month
                )

            else:

                d = datetime.date(
                    year,
                    month,
                    day_number
                )

            button._calendar_date = d

            # -----------------------------------------------------------
            # Buchungen
            # -----------------------------------------------------------

            rows = self.store.list_transactions_for_day(
                d.isoformat()
            )

            income = sum(
                r["amount"]
                for r in rows
                if r["amount"] > 0
            )

            expense = sum(
                -r["amount"]
                for r in rows
                if r["amount"] < 0
            )

            saldo = income - expense

            has_transactions = bool(rows)

            # -----------------------------------------------------------
            # Saldo-Farbe
            # -----------------------------------------------------------

            if saldo > 0:
                saldo_color = "#1e8c3d"
            elif saldo < 0:
                saldo_color = "#bf3826"
            else:
                saldo_color = "#888888"

            # -----------------------------------------------------------
            # Grunddarstellung
            #
            # Immer exakt zwei Zeilen.
            # -----------------------------------------------------------

            if has_transactions:

                markup = (
                    f"<b>{d.day}</b>\n"
                    f'<span foreground="{saldo_color}">'
                    f"{fmt_amount(saldo)}"
                    f"</span>"
                )

            else:

                markup = (
                    f"{d.day}\n"
                    '<span foreground="#888888">–</span>'
                )

            # -----------------------------------------------------------
            # HEUTE
            # -----------------------------------------------------------

            if d == today and d != self.selected_day:

                if has_transactions:

                    markup = (
                        '<span foreground="#1976d2">'
                        f"<b>{d.day}</b>"
                        "</span>\n"
                        f'<span foreground="{saldo_color}">'
                        f"{fmt_amount(saldo)}"
                        "</span>"
                    )

                else:

                    markup = (
                        '<span foreground="#1976d2">'
                        f"<b>{d.day}</b>"
                        "</span>\n"
                        '<span foreground="#888888">–</span>'
                    )

            # -----------------------------------------------------------
            # AUSGEWÄHLTER TAG
            # -----------------------------------------------------------

            if d == self.selected_day:

                if has_transactions:

                    markup = (
                        '<span background="#1976d2" foreground="white">'
                        f"<b>{d.day}</b>"
                        "</span>\n"
                        f'<span foreground="{saldo_color}">'
                        f"{fmt_amount(saldo)}"
                        "</span>"
                    )

                else:

                    markup = (
                        '<span background="#1976d2" foreground="white">'
                        f"<b>{d.day}</b>"
                        "</span>\n"
                        '<span foreground="#888888">–</span>'
                    )

            label.set_markup(markup)

            # -----------------------------------------------------------
            # Opacity
            # -----------------------------------------------------------

            if (
                d.month != month
                or d.year != year
            ):
                opacity = 0.35
            else:
                opacity = 1.0

            if d.weekday() >= 5:
                opacity = min(
                    opacity,
                    0.85
                )

            label.set_opacity(opacity)

            # -----------------------------------------------------------
            # Tooltip
            # -----------------------------------------------------------

            if rows:

                tooltip = (
                    f"{d.strftime('%d.%m.%Y')}\n"
                    f"Einnahmen: {fmt_amount(income)}\n"
                    f"Ausgaben: {fmt_amount(expense)}\n"
                    f"Saldo: {fmt_amount(saldo)}"
                )

            else:

                tooltip = d.strftime(
                    "%d.%m.%Y"
                )

            button.set_tooltip_text(
                tooltip
            )

            # -----------------------------------------------------------
            # GTK-Auswahl deaktivieren
            # -----------------------------------------------------------

            button.unset_state_flags(
                Gtk.StateFlags.SELECTED
            )

            # -----------------------------------------------------------
            # FESTE GRÖSSE
            # -----------------------------------------------------------

            button.show_all()

    def _on_custom_calendar_day_clicked(
        self,
        button
    ):
        """Einfachklick auf einen Kalendertag."""

        d = getattr(
            button,
            "_calendar_date",
            None
        )

        if d is None:
            return

        # Angeclickten Tag auswählen
        self.selected_day = d

        # Falls Tag aus anderem Monat stammt,
        # direkt in diesen Monat wechseln.
        if (
            d.year != self.month_display_date.year
            or d.month != self.month_display_date.month
        ):

            self.month_display_date = d.replace(
                day=1
            )

            self.store.ensure_horizon(
                self.month_display_date
            )

        # Kalender aktualisieren
        self._refresh_custom_calendar()

        # Tagesliste aktualisieren
        self._refresh_day_list()

        # Monatssaldo aktualisieren
        self._refresh_month_balance()

        # Budgets aktualisieren
        self._refresh_budgets_tab()


    def _on_custom_calendar_key_press(
        self,
        button,
        event
    ):
        """Enter auf einem Kalendertag öffnet neue Buchung."""

        if event.keyval in (
            Gdk.KEY_Return,
            Gdk.KEY_KP_Enter
        ):

            d = getattr(
                button,
                "_calendar_date",
                None
            )

            if d is None:
                return False

            self.selected_day = d

            # Bei Enter auf einen anderen Monat
            # in diesen Monat wechseln.
            if (
                d.year != self.month_display_date.year
                or d.month != self.month_display_date.month
            ):

                self.month_display_date = d.replace(
                    day=1
                )

                self.store.ensure_horizon(
                    self.month_display_date
                )

            dialog = TransactionDialog(
                self,
                self.store,
                d
            )

            if dialog.run() == Gtk.ResponseType.OK:
                dialog.save()

            dialog.destroy()

            self._after_transactions_changed()

            return True

        return False


    def _on_custom_calendar_button_press(
        self,
        button,
        event
    ):
        """Doppelklick auf einen Kalendertag öffnet neue Buchung."""

        if event.type == Gdk.EventType._2BUTTON_PRESS:

            d = getattr(
                button,
                "_calendar_date",
                None
            )

            if d is None:
                return False

            self.selected_day = d

            # Bei Doppelklick auf einen anderen Monat
            # in diesen Monat wechseln.
            if (
                d.year != self.month_display_date.year
                or d.month != self.month_display_date.month
            ):

                self.month_display_date = d.replace(
                    day=1
                )

                self.store.ensure_horizon(
                    self.month_display_date
                )

            dialog = TransactionDialog(
                self,
                self.store,
                d
            )

            if dialog.run() == Gtk.ResponseType.OK:
                dialog.save()

            dialog.destroy()

            self._after_transactions_changed()

            return True

        return False


    def _build_transactions_tab(self):

        root = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10
        )

        root.set_border_width(8)

        # ================================================================
        # LINKE SEITE
        # ================================================================

        left_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=5
        )

        # Die Monatsansicht darf niemals kleiner werden, nur weil der
        # aktuell angezeigte Monat keine Buchungen enthält.
        # 414 px entsprechen 8 Kalender-Spalten à 50 px + 7 Abstände à 2 px.
        left_box.set_size_request(
            600,
            -1
        )

        root.pack_start(
            left_box,
            False,
            False,
            0
        )

        # ================================================================
        # ANSICHT AUSWÄHLEN
        # ================================================================

        self.view_switcher_combo = Gtk.ComboBoxText()

        self.view_switcher_combo.append(
            "monat",
            "Monatsansicht"
        )

        self.view_switcher_combo.append(
            "woche",
            "Wochenansicht"
        )

        self.view_switcher_combo.append(
            "jahr",
            "Jahresansicht"
        )

        self.view_switcher_combo.set_active_id(
            "monat"
        )

        self.view_switcher_combo.connect(
            "changed",
            self._on_view_switch_changed
        )

        left_box.pack_start(
            self.view_switcher_combo,
            False,
            False,
            0
        )

        # ================================================================
        # STACK
        # ================================================================

        self.view_stack = Gtk.Stack()

        self.view_stack.set_transition_type(
            Gtk.StackTransitionType.CROSSFADE
        )

        left_box.pack_start(
            self.view_stack,
            True,
            True,
            0
        )

        # ================================================================
        # MONATSANSICHT
        # ================================================================

        month_page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=5
        )

        # Feste Mindestfläche für die komplette Monatsansicht.
        # Dadurch kann GTK bei einem Monat ohne Buchungen weder Höhe noch
        # Breite aus den kleineren Label-Inhalten ableiten.
        month_page.set_size_request(
            600,
            327
        )

        # ================================================================
        # MONATSNAVIGATION
        # ================================================================

        month_nav = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=5
        )

        prev_month_btn = _nav_button(
            "◀",
            lambda w: self._shift_calendar_month(-1)
        )

        month_nav.pack_start(
            prev_month_btn,
            False,
            False,
            0
        )

        self.custom_calendar_month_label = Gtk.Label()

        self.custom_calendar_month_label.set_markup(
            "<b>Monat</b>"
        )

        month_nav.pack_start(
            self.custom_calendar_month_label,
            True,
            False,
            0
        )

        next_month_btn = _nav_button(
            "▶",
            lambda w: self._shift_calendar_month(1)
        )

        month_nav.pack_start(
            next_month_btn,
            False,
            False,
            0
        )

        today_month_btn = Gtk.Button(
            label="Heute"
        )

        today_month_btn.connect(
            "clicked",
            self._goto_current_month
        )

        month_nav.pack_start(
            today_month_btn,
            False,
            False,
            0
        )

        month_page.pack_start(
            month_nav,
            False,
            False,
            0
        )

                                              
        # ================================================================
        # KALENDER MIT KW-SPALTE
        # ================================================================

        # Ein einziges Grid für KW + Kalender.
        # Dadurch haben KW-Zahlen und Kalendertage garantiert
        # exakt dieselben Zeilenhöhen und können nicht verrutschen.
       
        # Kein Gtk.Grid für die eigentliche Monatsgeometrie:
        # Gtk.Grid kann die Zeilenhöhe aus dem Inhalt neu berechnen.
        # Bei einem Monat ohne Buchungen ist dieser Inhalt kleiner und die
        # Ansicht kann dadurch zusammengestaucht werden.
        # Gtk.Fixed hält dagegen die Position und Größe jeder Zelle unabhängig
        # vom Textinhalt konstant. Die normalen Gtk.Button/Gtk.Label bleiben
        # dabei vollständig erhalten – inklusive Schrift, Farben und Buchungen.
        calendar_grid = Gtk.Fixed()

        # Exakte, unveränderliche Kalenderfläche:
        # KW-Spalte 40 px + 7 × 50 px, jeweils 2 px Abstand.
        # Höhe: Kopfzeile + 6 Wochenzeilen = 7 × 45 px + 6 × 2 px.
        calendar_grid.set_size_request(
            600,
            327
        )

        calendar_grid.set_halign(
            Gtk.Align.START
        )

        calendar_grid.set_valign(
            Gtk.Align.START
        )



        # ================================================================
        # KW-SPALTE
        # ================================================================

        self.calendar_week_labels = []

        kw_header = Gtk.Label(
            label="KW"
        )

        kw_header.set_markup(
            '<span foreground="#777777"><b>KW</b></span>'
        )

        kw_header.set_xalign(0.5)
        kw_header.set_yalign(0.5)

        # KW-Spalte bekommt eine feste Breite.
        kw_header.set_size_request(
            40,
            45
        )

        calendar_grid.put(
            kw_header,
            0,
            0
        )


        # ================================================================
        # WOCHENTAGE
        # ================================================================

        weekday_names = [
            "Mo",
            "Di",
            "Mi",
            "Do",
            "Fr",
            "Sa",
            "So"
        ]

        for col, name in enumerate(
            weekday_names,
            start=1
        ):

            label = Gtk.Label()

            label.set_markup(
                f"<b>{name}</b>"
            )

            label.set_xalign(0.5)
            label.set_yalign(0.5)

            # Feste Breite verhindert, dass lange Inhalte
            # die Kalender-Spalten verschieben.
            label.set_size_request(
                78,
                45
            )

            calendar_grid.put(
                label,
                42 + (col - 1) * 80,
                0
            )


        # ================================================================
        # KW-ZEILEN
        # ================================================================

        for row in range(6):

            kw_label = Gtk.Label()

            kw_label.set_size_request(
                40,
                45
            )

            kw_label.set_xalign(0.5)
            kw_label.set_yalign(0.5)


            self.calendar_week_labels.append(
                kw_label
            )

            calendar_grid.put(
                kw_label,
                0,
                47 + row * 47
            )


        # ================================================================
        # 42 KALENDERFELDER
        # ================================================================

        self.month_day_buttons = []

        for row in range(6):

            for col in range(7):

                # --------------------------------------------------------
                # FESTE KALENDERZELLE
                # --------------------------------------------------------

                button = Gtk.Button()

                button.set_relief(
                    Gtk.ReliefStyle.NONE
                )

                # WICHTIG:
                # Die Kalenderzelle hat immer exakt diese Größe.
                button.set_size_request(
                    78,
                    45
                )

                button.set_hexpand(False)
                button.set_vexpand(False)

                button.set_halign(
                    Gtk.Align.CENTER
                )

                button.set_valign(
                    Gtk.Align.CENTER
                )

                # --------------------------------------------------------
                # LABEL
                # --------------------------------------------------------

                # --------------------------------------------------------
                # FESTE ZELLENHÖHE
                # --------------------------------------------------------
                # Die Kalenderzelle selbst bestimmt die Größe. Der Text
                # darf die GTK-Mindesthöhe der Grid-Zeile NICHT beeinflussen.
                # Deshalb bekommt das Label eine exakt begrenzte
                # Ein-Zeilen-Pango-Layoutfläche; der Text enthält weiterhin
                # den Zeilenumbruch zwischen Tag und Betrag.

                label = Gtk.Label()
                label.set_justify(Gtk.Justification.CENTER)
                label.set_xalign(0.5)
                label.set_yalign(0.5)
                label.set_halign(Gtk.Align.CENTER)
                label.set_valign(Gtk.Align.CENTER)
                label.set_hexpand(False)
                label.set_vexpand(False)

                # Exakte Zeichenfläche innerhalb der 50x45px-Zelle.
                # Keine zusätzliche Höhe aus langem Betrags-Text.
                label.set_size_request(76, 40)
                label.set_line_wrap(False)
                label.set_max_width_chars(8)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                label.set_single_line_mode(False)

                button.add(label)

                # --------------------------------------------------------
                # KLICK
                # --------------------------------------------------------

                button.connect(
                    "clicked",
                    self._on_custom_calendar_day_clicked
                )

                # --------------------------------------------------------
                # DOPPELKLICK
                # --------------------------------------------------------

                button.connect(
                    "button-press-event",
                    self._on_custom_calendar_button_press
                )

                # --------------------------------------------------------
                # ENTER
                # --------------------------------------------------------

                button.connect(
                    "key-press-event",
                    self._on_custom_calendar_key_press
                )

                # --------------------------------------------------------
                # INS GRID
                # --------------------------------------------------------

                calendar_grid.put(
                    button,
                    42 + col * 80,
                    47 + row * 47
                )

                self.month_day_buttons.append(
                    (
                        button,
                        label
                    )
                )



        # ================================================================
        # KALENDER-CONTAINER
        # ================================================================

        calendar_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=0
        )

        calendar_container.set_halign(
            Gtk.Align.START
        )

        calendar_container.set_valign(
            Gtk.Align.START
        )

        calendar_container.pack_start(
            calendar_grid,
            False,
            False,
            0
        )



        # ================================================================
        # KALENDER IN DIE MONATSANSICHT
        # ================================================================

        month_page.pack_start(
            calendar_container,
            False,
            False,
            0
        )

        # ================================================================
        # MONATSSALDO
        # ================================================================

        self.month_balance_label = Gtk.Label(
            xalign=0
        )

        self.month_balance_label.set_line_wrap(
            True
        )

        month_page.pack_start(
            self.month_balance_label,
            False,
            False,
            0
        )

        # ================================================================
        # HINWEIS
        # ================================================================

        legend = Gtk.Label(
            xalign=0
        )

        legend.set_markup(
            '<b>Fett</b> = Buchung(en)\n'
            '<b>Klick</b> = Tagesbuchungen anzeigen\n'
            '<b>Doppelklick / Enter</b> = Neue Buchung'
        )

        legend.set_line_wrap(
            True
        )

        legend.set_max_width_chars(
            42
        )

        month_page.pack_start(
            legend,
            False,
            False,
            0
        )

        self.view_stack.add_named(
            month_page,
            "monat"
        )

        # ================================================================
        # WOCHEN- UND JAHRESANSICHT
        # ================================================================

        self.view_stack.add_named(
            self._build_week_view(),
            "woche"
        )

        self.view_stack.add_named(
            self._build_year_view(),
            "jahr"
        )

        # ================================================================
        # KATEGORIEN
        # ================================================================

        manage_cat_btn = Gtk.Button(
            label="Kategorien verwalten"
        )

        manage_cat_btn.connect(
            "clicked",
            self._on_manage_categories
        )

        left_box.pack_start(
            manage_cat_btn,
            False,
            False,
            5
        )

        # ================================================================
        # RECHTE SEITE – TAGESLISTE
        # ================================================================

        right_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=5
        )

        root.pack_start(
            right_box,
            True,
            True,
            0
        )

        self.day_title_label = Gtk.Label(
            xalign=0
        )

        right_box.pack_start(
            self.day_title_label,
            False,
            False,
            0
        )

        scroller = Gtk.ScrolledWindow()

        right_box.pack_start(
            scroller,
            True,
            True,
            0
        )

        self.day_store = Gtk.ListStore(
            int,
            str,
            str,
            float,
            str,
            bool
        )

        self.day_view = Gtk.TreeView(
            model=self.day_store
        )

        self.day_view.connect(
            "row-activated",
            self._on_edit_transaction
        )

        scroller.add(
            self.day_view
        )

        # ================================================================
        # KATEGORIE
        # ================================================================

        cat_renderer = Gtk.CellRendererText()

        cat_col = Gtk.TreeViewColumn(
            "Kategorie",
            cat_renderer,
            text=1
        )

        self.day_view.append_column(
            cat_col
        )

        # ================================================================
        # ART
        # ================================================================

        art_renderer = Gtk.CellRendererText()

        art_col = Gtk.TreeViewColumn(
            "Art",
            art_renderer,
            text=2
        )

        self.day_view.append_column(
            art_col
        )

        # ================================================================
        # BETRAG
        # ================================================================

        amount_renderer = Gtk.CellRendererText()

        amount_renderer.set_property(
            "xalign",
            1.0
        )

        amount_col = Gtk.TreeViewColumn(
            "Betrag",
            amount_renderer
        )

        amount_col.set_cell_data_func(
            amount_renderer,
            self._render_amount_cell,
            3
        )

        self.day_view.append_column(
            amount_col
        )

        # ================================================================
        # BESCHREIBUNG
        # ================================================================

        desc_renderer = Gtk.CellRendererText()

        desc_renderer.set_property(
            "ellipsize",
            Pango.EllipsizeMode.END
        )

        desc_col = Gtk.TreeViewColumn(
            "Beschreibung",
            desc_renderer,
            text=4
        )

        desc_col.set_expand(
            True
        )

        self.day_view.append_column(
            desc_col
        )

        # ================================================================
        # WIEDERKEHREND
        # ================================================================

        rec_renderer = Gtk.CellRendererToggle()

        rec_renderer.set_property(
            "activatable",
            False
        )

        rec_col = Gtk.TreeViewColumn(
            "Wiederk.",
            rec_renderer,
            active=5
        )

        self.day_view.append_column(
            rec_col
        )

        # ================================================================
        # HINWEIS
        # ================================================================

        hint = Gtk.Label(
            label=(
                "Tipp: Doppelklick auf eine Buchung "
                "öffnet sie zum Bearbeiten."
            ),
            xalign=0
        )

        right_box.pack_start(
            hint,
            False,
            False,
            0
        )

        # ================================================================
        # BUTTONS
        # ================================================================

        btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=5
        )

        right_box.pack_start(
            btn_box,
            False,
            False,
            0
        )

        # ------------------------------------------------
        # Hinzufügen
        # ------------------------------------------------

        add_btn = Gtk.Button(
            label="Buchung hinzufügen"
        )

        add_btn.connect(
            "clicked",
            self._on_add_transaction
        )

        btn_box.pack_start(
            add_btn,
            False,
            False,
            0
        )

        # ------------------------------------------------
        # Bearbeiten
        # ------------------------------------------------

        edit_btn = Gtk.Button(
            label="Bearbeiten"
        )

        edit_btn.connect(
            "clicked",
            self._on_edit_selected
        )

        btn_box.pack_start(
            edit_btn,
            False,
            False,
            0
        )

        # ------------------------------------------------
        # Löschen
        # ------------------------------------------------

        del_btn = Gtk.Button(
            label="Löschen"
        )

        del_btn.connect(
            "clicked",
            self._on_delete_transaction
        )

        btn_box.pack_start(
            del_btn,
            False,
            False,
            0
        )

        # ------------------------------------------------
        # Wiederkehrende Vorlagen
        # ------------------------------------------------

        rec_btn = Gtk.Button(
            label="Wiederkehrende Vorlagen verwalten"
        )

        rec_btn.connect(
            "clicked",
            self._on_manage_recurring
        )

        btn_box.pack_start(
            rec_btn,
            False,
            False,
            0
        )

        # ================================================================
        # INITIALISIERUNG
        # ================================================================

        self.month_display_date = (
            datetime.date.today().replace(
                day=1
            )
        )

        self.selected_day = (
            datetime.date.today()
        )

        self._refresh_custom_calendar()
        self._refresh_day_list()
        self._refresh_month_balance()
        self._refresh_week_view()
        self._refresh_year_view()

        return root


    def _goto_current_month(
        self,
        widget=None
    ):
        today = datetime.date.today()

        self.month_display_date = today.replace(
            day=1
        )

        self.selected_day = today

        self._refresh_custom_calendar()
        self._refresh_day_list()
        self._refresh_month_balance()
        self._refresh_budgets_tab()


    def _on_view_switch_changed(
        self,
        combo
    ):
        self.view_stack.set_visible_child_name(
            combo.get_active_id()
        )

        if combo.get_active_id() == "woche":
            self._refresh_week_view()

        elif combo.get_active_id() == "jahr":
            self._refresh_year_view()


    # -- Wochenansicht -------------------------------------------------------

    def _build_week_view(self):

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6
        )

        nav = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6
        )

        box.pack_start(
            nav,
            False,
            False,
            0
        )

        prev_btn = _nav_button(
            "◀",
            lambda w: self._shift_week(-1)
        )

        nav.pack_start(
            prev_btn,
            False,
            False,
            0
        )

        self.week_range_label = Gtk.Label(
            label=""
        )

        nav.pack_start(
            self.week_range_label,
            False,
            False,
            0
        )

        next_btn = _nav_button(
            "▶",
            lambda w: self._shift_week(1)
        )

        nav.pack_start(
            next_btn,
            False,
            False,
            0
        )

        today_btn = Gtk.Button(
            label="Diese Woche"
        )

        today_btn.connect(
            "clicked",
            lambda w: self._goto_current_week()
        )

        nav.pack_start(
            today_btn,
            False,
            False,
            6
        )

        self.week_grid = Gtk.Grid(
            column_spacing=4,
            row_spacing=2
        )

        self.week_grid.set_column_homogeneous(
            True
        )

        box.pack_start(
            self.week_grid,
            False,
            False,
            0
        )

        self.week_day_buttons = []

        for i in range(7):

            btn = Gtk.Button()

            btn.set_size_request(
                -1,
                64
            )

            lbl = Gtk.Label()

            lbl.set_justify(
                Gtk.Justification.CENTER
            )

            btn.add(
                lbl
            )

            btn.connect(
                "clicked",
                self._on_week_day_clicked,
                i
            )

            self.week_grid.attach(
                btn,
                i,
                0,
                1,
                1
            )

            self.week_day_buttons.append(
                (
                    btn,
                    lbl
                )
            )

        hint = Gtk.Label(
            xalign=0
        )

        hint.set_markup(
            '<b>Klick auf einen Tag</b> = Buchungen des Tages rechts anzeigen.\n'
            'Monatsübersicht und Budgets folgen automatisch der angezeigten Woche.'
        )

        hint.set_line_wrap(
            True
        )

        hint.set_max_width_chars(
            28
        )

        box.pack_start(
            hint,
            False,
            False,
            0
        )

        self.week_start = self._monday_of(
            datetime.date.today()
        )

        return box


    @staticmethod
    def _monday_of(d):
        return d - datetime.timedelta(
            days=d.weekday()
        )


    def _sync_calendar_to_week(self):
        """Synchronisiert die Monatsansicht mit dem Monat
        der aktuell angezeigten Woche."""

        month_date = self.week_start.replace(
            day=1
        )

        self.month_display_date = month_date

        self.store.ensure_horizon(
            month_date
        )

        self._refresh_custom_calendar()
        self._refresh_month_balance()
        self._refresh_budgets_tab()


    def _shift_week(
        self,
        delta
    ):
        self.week_start = (
            self.week_start
            + datetime.timedelta(
                weeks=delta
            )
        )

        self._refresh_week_view()
        self._sync_calendar_to_week()


    def _goto_current_week(self):

        self.week_start = self._monday_of(
            datetime.date.today()
        )

        self._refresh_week_view()
        self._sync_calendar_to_week()


    def _on_week_day_clicked(
        self,
        button,
        offset
    ):

        d = (
            self.week_start
            + datetime.timedelta(
                days=offset
            )
        )

        self.selected_day = d

        self.month_display_date = d.replace(
            day=1
        )

        self.store.ensure_horizon(
            self.month_display_date
        )

        self._refresh_custom_calendar()
        self._refresh_month_balance()
        self._refresh_day_list()
        self._refresh_budgets_tab()


    def _refresh_week_view(self):

        if not hasattr(
            self,
            "week_range_label"
        ):
            return

        weekday_names = [
            "Mo",
            "Di",
            "Mi",
            "Do",
            "Fr",
            "Sa",
            "So"
        ]

        start = self.week_start

        end = (
            start
            + datetime.timedelta(
                days=6
            )
        )

        self.week_range_label.set_text(
            f"{start.strftime('%d.%m.')} – "
            f"{end.strftime('%d.%m.%Y')}"
        )

        self.store.ensure_horizon(
            start.replace(day=1)
        )

        for i, (btn, lbl) in enumerate(
            self.week_day_buttons
        ):

            d = (
                start
                + datetime.timedelta(
                    days=i
                )
            )

            rows = self.store.list_transactions_for_day(
                d.isoformat()
            )

            income = sum(
                r["amount"]
                for r in rows
                if r["amount"] > 0
            )

            expense = sum(
                -r["amount"]
                for r in rows
                if r["amount"] < 0
            )

            saldo = income - expense

            if rows:

                color = (
                    "#1e8c3d"
                    if saldo >= 0
                    else "#bf3826"
                )

                saldo_text = fmt_amount(
                    saldo
                )

            else:

                color = "#888888"
                saldo_text = "–"

            today_marker = (
                " •"
                if d == datetime.date.today()
                else ""
            )

            lbl.set_markup(
                f"<b>{weekday_names[i]}"
                f"{today_marker}</b>\n"
                f"{d.day}.{d.month}.\n"
                f'<span foreground="{color}">'
                f"{saldo_text}"
                f"</span>"
            )


    # -- Jahresansicht -------------------------------------------------------

    def _build_year_view(self):

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6
        )

        nav = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6
        )

        box.pack_start(
            nav,
            False,
            False,
            0
        )

        prev_btn = _nav_button(
            "◀",
            lambda w: self._shift_year(-1)
        )

        nav.pack_start(
            prev_btn,
            False,
            False,
            0
        )

        self.year_label = Gtk.Label(
            label=""
        )

        nav.pack_start(
            self.year_label,
            False,
            False,
            0
        )

        next_btn = _nav_button(
            "▶",
            lambda w: self._shift_year(1)
        )

        nav.pack_start(
            next_btn,
            False,
            False,
            0
        )

        self.year_grid = Gtk.Grid(
            column_spacing=4,
            row_spacing=4
        )

        self.year_grid.set_column_homogeneous(
            True
        )

        self.year_grid.set_row_homogeneous(
            True
        )

        box.pack_start(
            self.year_grid,
            False,
            False,
            0
        )

        self.year_month_buttons = []

        for m in range(12):

            btn = Gtk.Button()

            btn.set_size_request(
                -1,
                50
            )

            lbl = Gtk.Label()

            lbl.set_justify(
                Gtk.Justification.CENTER
            )

            btn.add(
                lbl
            )

            btn.connect(
                "clicked",
                self._on_year_month_clicked,
                m + 1
            )

            self.year_grid.attach(
                btn,
                m % 3,
                m // 3,
                1,
                1
            )

            self.year_month_buttons.append(
                (
                    btn,
                    lbl
                )
            )

        hint = Gtk.Label(
            xalign=0
        )

        hint.set_markup(
            '<b>Klick auf einen Monat</b> = wechselt in die Monatsansicht.'
        )

        hint.set_line_wrap(
            True
        )

        hint.set_max_width_chars(
            28
        )

        box.pack_start(
            hint,
            False,
            False,
            0
        )

        self.year_reference = (
            datetime.date.today().year
        )

        return box


    def _shift_year(
        self,
        delta
    ):
        self.year_reference += delta
        self._refresh_year_view()


    def _refresh_year_view(self):

        if not hasattr(
            self,
            "year_label"
        ):
            return

        self.year_label.set_text(
            str(self.year_reference)
        )

        overview = self.store.yearly_overview(
            self.year_reference
        )

        for i, (btn, lbl) in enumerate(
            self.year_month_buttons
        ):

            data = overview[i]

            saldo = (
                data["income"]
                - data["expense"]
            )

            has_data = bool(
                data["income"]
                or data["expense"]
            )

            if has_data:

                color = (
                    "#1e8c3d"
                    if saldo >= 0
                    else "#bf3826"
                )

            else:

                color = "#888888"

            text = (
                fmt_amount(saldo)
                if has_data
                else "–"
            )

            name = GERMAN_MONTHS[i][:3]

            lbl.set_markup(
                f"<b>{name}</b>\n"
                f'<span foreground="{color}">'
                f"{text}"
                f"</span>"
            )


    def _on_year_month_clicked(
        self,
        button,
        month
    ):

        self.month_display_date = datetime.date(
            self.year_reference,
            month,
            1
        )

        self.store.ensure_horizon(
            self.month_display_date
        )

        self._refresh_custom_calendar()
        self._refresh_month_balance()
        self._refresh_budgets_tab()

        self.view_switcher_combo.set_active_id(
            "monat"
        )

        self.view_stack.set_visible_child_name(
            "monat"
        )


    def _selected_calendar_month(self):
        return self.month_display_date


    def _refresh_month_balance(self):

        month_start = self.month_display_date

        month_str = month_start.strftime(
            "%Y-%m"
        )

        rows = self.store.list_transactions(
            month=month_str
        )

        income = sum(
            r["amount"]
            for r in rows
            if r["amount"] > 0
        )

        expense = sum(
            -r["amount"]
            for r in rows
            if r["amount"] < 0
        )

        saldo = income - expense

        sign = "+" if saldo >= 0 else ""

        self.month_balance_label.set_markup(
            f"<b>{month_label(month_start)}</b>\n"
            f"Einnahmen: {fmt_amount(income)}\n"
            f"Ausgaben: {fmt_amount(expense)}\n"
            f"Saldo: {sign}{fmt_amount(saldo)}"
        )


    def _refresh_day_list(self):

        weekday_names = [
            "Montag",
            "Dienstag",
            "Mittwoch",
            "Donnerstag",
            "Freitag",
            "Samstag",
            "Sonntag"
        ]

        d = self.selected_day

        self.day_title_label.set_markup(
            f"<b>{weekday_names[d.weekday()]}, "
            f"{d.strftime('%d.%m.%Y')}</b>"
        )

        self.day_store.clear()

        rows = self.store.list_transactions_for_day(
            d.isoformat()
        )

        if not rows:

            self.day_store.append(
                [
                    0,
                    "",
                    "",
                    0.0,
                    "Keine Buchungen an diesem Tag.",
                    False
                ]
            )

        else:

            for r in rows:

                self.day_store.append(
                    [
                        r["id"],
                        f"{r['icon']} {r['category_name']}",
                        (
                            "Einnahme"
                            if r["kind"] == "einnahme"
                            else "Ausgabe"
                        ),
                        r["amount"],
                        r["description"] or "",
                        r["recurring_template_id"] is not None,
                    ]
                )


    def _render_amount_cell(
        self,
        column,
        cell,
        model,
        tree_iter,
        col_index
    ):

        row_id = model.get_value(
            tree_iter,
            0
        )

        if row_id == 0:

            cell.set_property(
                "text",
                ""
            )

            return

        value = model.get_value(
            tree_iter,
            col_index
        )

        cell.set_property(
            "text",
            fmt_amount(value)
        )

        cell.set_property(
            "foreground",
            "#1e8e3e"
            if value >= 0
            else "#c0392b"
        )


    def _selected_transaction_id(self):

        selection = self.day_view.get_selection()

        model, tree_iter = (
            selection.get_selected()
        )

        if tree_iter is None:
            return None

        row_id = model.get_value(
            tree_iter,
            0
        )

        return (
            row_id
            if row_id != 0
            else None
        )


    def _on_add_transaction(
        self,
        widget
    ):

        dialog = TransactionDialog(
            self,
            self.store,
            self.selected_day
        )

        if dialog.run() == Gtk.ResponseType.OK:
            dialog.save()

        dialog.destroy()

        self._after_transactions_changed()


    def _on_edit_selected(
        self,
        widget
    ):

        tx_id = self._selected_transaction_id()

        if tx_id is not None:

            self._open_edit_dialog(
                tx_id
            )


    def _on_edit_transaction(
        self,
        tree_view,
        path,
        column
    ):

        model = tree_view.get_model()

        tree_iter = model.get_iter(
            path
        )

        row_id = model.get_value(
            tree_iter,
            0
        )

        if row_id != 0:

            self._open_edit_dialog(
                row_id
            )


    def _open_edit_dialog(
        self,
        tx_id
    ):

        existing = self.store.get_transaction(
            tx_id
        )

        dialog = TransactionDialog(
            self,
            self.store,
            self.selected_day,
            existing=existing
        )

        if dialog.run() == Gtk.ResponseType.OK:
            dialog.save()

        dialog.destroy()

        self._after_transactions_changed()


    def _on_delete_transaction(
        self,
        widget
    ):

        tx_id = self._selected_transaction_id()

        if tx_id is not None:

            self.store.delete_transaction(
                tx_id
            )

            self._after_transactions_changed()


    def _on_manage_recurring(
        self,
        widget
    ):

        dialog = RecurringTemplatesDialog(
            self,
            self.store
        )

        dialog.run()
        dialog.destroy()

        self.store.ensure_horizon(
            self.month_display_date
        )

        self._after_transactions_changed()


    def _on_manage_categories(
        self,
        widget
    ):

        dialog = CategoryManagerDialog(
            self,
            self.store
        )

        dialog.run()
        dialog.destroy()

        self._refresh_day_list()


    def _after_transactions_changed(self):

        self._refresh_custom_calendar()
        self._refresh_day_list()
        self._refresh_month_balance()
        self._refresh_budgets_tab()
        self._refresh_week_view()
        self._refresh_year_view()
        self._refresh_current_balance_display()

    # =====================================================================
    # Tab 2: Budgets
    # =====================================================================

    def _build_budgets_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(10)

        info = Gtk.Label(label="Budgets gelten für den im Buchungen-Tab im Kalender "
                                "sichtbaren Monat.", xalign=0)
        box.pack_start(info, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        box.pack_start(scroller, True, True, 0)

        # category_id, name(icon+name), limit_text, spent_text, remaining_text, fraction
        self.budget_store = Gtk.ListStore(int, str, str, str, str, int)
        self.budget_view = Gtk.TreeView(model=self.budget_store)
        scroller.add(self.budget_view)

        for title, col_id in [("Kategorie", 1), ("Budget", 2), ("Ausgegeben", 3),
                               ("Verbleibend", 4)]:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=col_id)
            self.budget_view.append_column(column)

        progress_renderer = Gtk.CellRendererProgress()
        progress_col = Gtk.TreeViewColumn("Fortschritt", progress_renderer, value=5)
        progress_col.set_expand(True)
        self.budget_view.append_column(progress_col)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_start(btn_box, False, False, 0)

        set_btn = Gtk.Button(label="Budget setzen/ändern")
        set_btn.connect("clicked", self._on_set_budget)
        btn_box.pack_start(set_btn, False, False, 0)

        refresh_btn = Gtk.Button(label="Aktualisieren")
        refresh_btn.connect("clicked", lambda w: self._refresh_budgets_tab())
        btn_box.pack_start(refresh_btn, False, False, 0)

        self._refresh_budgets_tab()
        return box

    def _refresh_budgets_tab(self):
        self.budget_store.clear()
        month_str = self._selected_calendar_month().strftime("%Y-%m")
        for r in self.store.budget_overview(month_str):
            limit_amount = r["limit_amount"]
            spent = r["spent"]
            label = f"{r['icon']} {r['category_name']}"
            if limit_amount is None:
                self.budget_store.append([
                    r["category_id"], label, "— kein Budget —",
                    fmt_amount(spent), "–", 0,
                ])
            else:
                remaining = limit_amount - spent
                fraction = int(min(100, max(0, (spent / limit_amount) * 100))) if limit_amount else 0
                self.budget_store.append([
                    r["category_id"], label, fmt_amount(limit_amount),
                    fmt_amount(spent), fmt_amount(remaining), fraction,
                ])

    def _on_set_budget(self, widget):
        selection = self.budget_view.get_selection()
        model, tree_iter = selection.get_selected()
        preselect_category_id = model.get_value(tree_iter, 0) if tree_iter else None

        dialog = BudgetDialog(self, self.store, self._selected_calendar_month(),
                               preselect_category_id)
        if dialog.run() == Gtk.ResponseType.OK:
            dialog.save()
        dialog.destroy()
        self._refresh_budgets_tab()

    # =====================================================================
    # Tab 3: Sparziele
    # =====================================================================

    def _build_goals_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(10)

        info = Gtk.Label(
            xalign=0,
            label="Die Reihenfolge hier legt fest, in welcher Priorität die "
                  "Finanzplanung-Empfehlung Startkapital/Sparbetrag auf die "
                  "Ziele verteilt (oben = zuerst befüllt). Mit „Nach oben“/"
                  "„Nach unten“ frei sortierbar.",
        )
        info.set_line_wrap(True)
        box.pack_start(info, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        box.pack_start(scroller, True, True, 0)

        # id, name, zielbetrag, angespart, zieldatum, fortschritt(0-100)
        self.goal_store = Gtk.ListStore(int, str, str, str, str, int)
        self.goal_view = Gtk.TreeView(model=self.goal_store)
        scroller.add(self.goal_view)

        for title, col_id in [("Priorität / Ziel", 1), ("Zielbetrag", 2), ("Angespart", 3),
                               ("Zieldatum", 4)]:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=col_id)
            self.goal_view.append_column(column)

        progress_renderer = Gtk.CellRendererProgress()
        progress_col = Gtk.TreeViewColumn("Fortschritt", progress_renderer, value=5)
        progress_col.set_expand(True)
        self.goal_view.append_column(progress_col)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_start(btn_box, False, False, 0)

        add_btn = Gtk.Button(label="Ziel hinzufügen")
        add_btn.connect("clicked", self._on_add_goal)
        btn_box.pack_start(add_btn, False, False, 0)

        contrib_btn = Gtk.Button(label="Einzahlen")
        contrib_btn.connect("clicked", self._on_add_contribution)
        btn_box.pack_start(contrib_btn, False, False, 0)

        del_btn = Gtk.Button(label="Ziel löschen")
        del_btn.connect("clicked", self._on_delete_goal)
        btn_box.pack_start(del_btn, False, False, 0)

        up_btn = Gtk.Button(label="▲ Nach oben")
        up_btn.connect("clicked", self._on_move_goal_priority, -1)
        btn_box.pack_start(up_btn, False, False, 0)

        down_btn = Gtk.Button(label="▼ Nach unten")
        down_btn.connect("clicked", self._on_move_goal_priority, 1)
        btn_box.pack_start(down_btn, False, False, 0)

        self._refresh_goals_tab()
        return box

    def _refresh_goals_tab(self):
        self.goal_store.clear()
        for i, g in enumerate(self.store.list_goals(), start=1):
            fraction = int(min(100, (g["current_amount"] / g["target_amount"]) * 100)) \
                if g["target_amount"] else 0
            self.goal_store.append([
                g["id"], f"{i}. {g['name']}", fmt_amount(g["target_amount"]),
                fmt_amount(g["current_amount"]), g["target_date"] or "–", fraction,
            ])

    def _on_move_goal_priority(self, widget, direction):
        selection = self.goal_view.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            return
        goal_id = model.get_value(tree_iter, 0)
        if self.store.move_goal_priority(goal_id, direction):
            self._refresh_goals_tab()
            # Die verschobene Zeile nach dem Neuaufbau wieder auswählen, damit
            # man mehrfach hintereinander verschieben kann, ohne neu klicken
            # zu müssen.
            for row in self.goal_store:
                if row[0] == goal_id:
                    self.goal_view.get_selection().select_iter(row.iter)
                    break

    def _on_add_goal(self, widget):
        dialog = GoalDialog(self)
        if dialog.run() == Gtk.ResponseType.OK:
            data = dialog.get_data()
            if data:
                self.store.add_goal(**data)
        dialog.destroy()
        self._refresh_goals_tab()

    def _on_add_contribution(self, widget):
        selection = self.goal_view.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            return
        goal_id = model.get_value(tree_iter, 0)
        goal_name = model.get_value(tree_iter, 1)

        dialog = ContributionDialog(self, goal_name)
        book_as_transaction = False
        if dialog.run() == Gtk.ResponseType.OK:
            amount = dialog.get_amount()
            book_as_transaction = dialog.get_book_as_transaction()
            if amount:
                self.store.add_contribution(
                    goal_id, datetime.date.today().isoformat(), amount,
                    create_transaction=book_as_transaction, goal_name=goal_name,
                )
        dialog.destroy()
        self._refresh_goals_tab()
        if book_as_transaction:
            self._after_transactions_changed()
            self._refresh_stats()

    def _on_delete_goal(self, widget):
        selection = self.goal_view.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter is not None:
            self.store.delete_goal(model.get_value(tree_iter, 0))
            self._refresh_goals_tab()

    # =====================================================================
    # Tab 4: Finanzplanung (Notgroschen + Anlage-Empfehlung)
    # =====================================================================

    def _build_planning_tab(self):
        outer = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_border_width(10)
        outer.add(box)

        # -- Abschnitt: Kontostand --
        balance_frame = Gtk.Frame(label="Kontostand")
        box.pack_start(balance_frame, False, False, 0)
        balance_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        balance_grid.set_border_width(8)
        balance_frame.add(balance_grid)

        balance_grid.attach(Gtk.Label(label="Stichtag (TT.MM.JJJJ):", xalign=0), 0, 0, 1, 1)
        existing_amount, existing_date = self.store.get_starting_balance()
        default_date = (datetime.date.fromisoformat(existing_date) if existing_date
                         else datetime.date.today())
        self.balance_date_entry = Gtk.Entry(text=default_date.strftime("%d.%m.%Y"))
        balance_grid.attach(self.balance_date_entry, 1, 0, 1, 1)

        balance_grid.attach(Gtk.Label(label="Kontostand an diesem Tag (€):", xalign=0), 0, 1, 1, 1)
        self.balance_amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=existing_amount or 0, lower=-1000000, upper=10000000,
                                       step_increment=10, page_increment=100),
            numeric=True, digits=2,
        )
        balance_grid.attach(self.balance_amount_spin, 1, 1, 1, 1)
        balance_grid.attach(_help_button(
            "Dein tatsächliches Kontoguthaben an einem bestimmten Tag (z. B. "
            "heute) – nicht nur die in Plutos erfassten Buchungen. Der "
            "aktuelle Kontostand wird daraus als Startguthaben + alle "
            "Buchungen ab diesem Stichtag berechnet, du musst also nicht "
            "jede einzelne Buchung seit Kontoeröffnung nacherfassen."
        ), 2, 1, 1, 1)

        save_balance_btn = Gtk.Button(label="Speichern")
        save_balance_btn.connect("clicked", self._on_save_starting_balance)
        balance_grid.attach(save_balance_btn, 0, 2, 2, 1)

        self.current_balance_label = Gtk.Label(xalign=0)
        self.current_balance_label.set_line_wrap(True)
        balance_grid.attach(self.current_balance_label, 0, 3, 3, 1)

        apply_balance_btn = Gtk.Button(
            label="Aktuellen Kontostand als Startkapital in der Empfehlung übernehmen")
        apply_balance_btn.connect("clicked", self._on_apply_balance_to_recommendation)
        balance_grid.attach(apply_balance_btn, 0, 4, 3, 1)

        balance_hint = Gtk.Label(
            xalign=0,
            label="Praktisch, wenn du gerade erst anfängst, für etwas zu sparen, "
                  "einen Notgroschen aufzubauen oder in ETFs zu investieren: "
                  "so zählt dein tatsächlich vorhandenes Geld, nicht nur das, "
                  "was du seit Nutzung von Plutos gebucht hast.",
        )
        balance_hint.set_line_wrap(True)
        balance_grid.attach(balance_hint, 0, 5, 3, 1)

        # -- Abschnitt A: Notgroschen einrichten --
        ng_frame = Gtk.Frame(label="Notgroschen einrichten (3–6 Monate Fixkosten)")
        box.pack_start(ng_frame, False, False, 0)
        ng_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        ng_grid.set_border_width(8)
        ng_frame.add(ng_grid)

        ng_grid.attach(Gtk.Label(label="Monatliche Fixkosten (€):", xalign=0), 0, 0, 1, 1)
        self.planning_fixed_costs_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=self.store.estimate_monthly_fixed_costs(),
                                       lower=0, upper=100000, step_increment=10,
                                       page_increment=100),
            numeric=True, digits=2,
        )
        self.planning_fixed_costs_spin.connect("value-changed",
                                                lambda w: self._update_notgroschen_preview())
        ng_grid.attach(self.planning_fixed_costs_spin, 1, 0, 1, 1)

        recalc_btn = Gtk.Button(label="Aus wiederkehrenden Ausgaben schätzen")
        recalc_btn.connect("clicked", self._on_recalc_fixed_costs)
        ng_grid.attach(recalc_btn, 2, 0, 1, 1)

        ng_grid.attach(Gtk.Label(label="Ziel: Monate an Fixkosten:", xalign=0), 0, 1, 1, 1)
        self.planning_months_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=4, lower=1, upper=12,
                                       step_increment=1, page_increment=1),
            numeric=True,
        )
        self.planning_months_spin.connect("value-changed",
                                           lambda w: self._update_notgroschen_preview())
        ng_grid.attach(self.planning_months_spin, 1, 1, 1, 1)
        ng_grid.attach(_help_button(
            "Wie viele Monate an Fixkosten der Notgroschen abdecken soll – "
            "eine Reserve für unerwartete Ausgaben oder Einkommensausfälle "
            "(z. B. Jobverlust, Reparaturen). 3 Monate gelten als absolutes "
            "Minimum, 6 Monate als komfortabel; bei unsicherem Einkommen "
            "(Selbstständigkeit) eher mehr."
        ), 2, 1, 1, 1)

        fixed_hint = Gtk.Label(
            xalign=0,
            label="Vorbelegt aus deinen laufenden wiederkehrenden Ausgaben-Vorlagen "
                  "(Miete, Versicherungen, …). Frei anpassbar, falls nicht alle "
                  "Fixkosten als wiederkehrende Buchung erfasst sind. Üblich sind "
                  "3–6 Monate: eher 3 bei sicherem Einkommen (z. B. Beamte), eher 6 "
                  "bei unsicherem Einkommen (z. B. Selbstständigkeit).",
        )
        fixed_hint.set_line_wrap(True)
        ng_grid.attach(fixed_hint, 0, 2, 3, 1)

        self.notgroschen_preview_label = Gtk.Label(xalign=0)
        self.notgroschen_preview_label.set_line_wrap(True)
        ng_grid.attach(self.notgroschen_preview_label, 0, 3, 3, 1)

        ng_create_btn = Gtk.Button(label="Notgroschen-Ziel anlegen/aktualisieren")
        ng_create_btn.connect("clicked", self._on_create_or_update_notgroschen)
        ng_grid.attach(ng_create_btn, 0, 4, 3, 1)

        # -- Abschnitt B: Anlage-Empfehlung --
        rec_frame = Gtk.Frame(label="Anlage-Empfehlung (einfache Faustregel)")
        box.pack_start(rec_frame, False, False, 0)
        rec_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        rec_grid.set_border_width(8)
        rec_frame.add(rec_grid)

        rec_grid.attach(Gtk.Label(label="Netto-Einkommen (monatlich, €):", xalign=0), 0, 0, 1, 1)
        self.planning_income_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=2500, lower=0, upper=1000000,
                                       step_increment=50, page_increment=200),
            numeric=True, digits=2,
        )
        rec_grid.attach(self.planning_income_spin, 1, 0, 1, 1)

        rec_grid.attach(Gtk.Label(label="Startkapital (€):", xalign=0), 0, 1, 1, 1)
        self.planning_capital_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=10000000,
                                       step_increment=100, page_increment=1000),
            numeric=True, digits=2,
        )
        rec_grid.attach(self.planning_capital_spin, 1, 1, 1, 1)

        rec_grid.attach(Gtk.Label(label="Freizeit-/Pufferbudget (% vom Netto):", xalign=0),
                         0, 2, 1, 1)
        self.planning_leisure_percent_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=10, lower=0, upper=50,
                                       step_increment=1, page_increment=5),
            numeric=True, digits=1,
        )
        rec_grid.attach(self.planning_leisure_percent_spin, 1, 2, 1, 1)
        rec_grid.attach(_help_button(
            "Anteil des Netto-Einkommens, der für Freizeit, Hobbys oder als "
            "spontaner finanzieller Puffer reserviert bleibt, statt komplett "
            "auf Notgroschen/Sparziele/ETF verteilt zu werden. Rein "
            "informativ – wird nirgends automatisch als Buchung angelegt."
        ), 2, 2, 1, 1)

        self.planning_include_goals_check = Gtk.CheckButton(
            label="Weitere Sparziele einbeziehen (Priorität siehe Sparziele-Tab)"
        )
        self.planning_include_goals_check.set_active(True)
        rec_grid.attach(self.planning_include_goals_check, 0, 3, 2, 1)

        # -- Optional: Risikoprofil/Anlagehorizont --
        self.planning_risk_check = Gtk.CheckButton(
            label="Risikoprofil/Anlagehorizont für den ETF-Anteil berücksichtigen (optional)"
        )
        self.planning_risk_check.connect("toggled", self._on_risk_toggle_changed)
        rec_grid.attach(self.planning_risk_check, 0, 4, 2, 1)

        risk_subgrid = Gtk.Grid(column_spacing=8, row_spacing=4)
        risk_subgrid.set_margin_start(20)
        rec_grid.attach(risk_subgrid, 0, 5, 2, 1)

        risk_subgrid.attach(Gtk.Label(label="Anlagehorizont (Jahre):", xalign=0), 0, 0, 1, 1)
        self.planning_horizon_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=10, lower=0, upper=60,
                                       step_increment=1, page_increment=5),
            numeric=True,
        )
        self.planning_horizon_spin.set_sensitive(False)
        risk_subgrid.attach(self.planning_horizon_spin, 1, 0, 1, 1)
        risk_subgrid.attach(_help_button(
            "Wie viele Jahre das Geld voraussichtlich investiert bleibt, bevor "
            "es gebraucht wird. Kurzer Horizont = höheres Risiko, dass ein "
            "Kurseinbruch sich nicht mehr erholt, bevor das Geld gebraucht "
            "wird – daher bei kurzem Horizont ein kleinerer ETF-Anteil."
        ), 2, 0, 1, 1)

        risk_subgrid.attach(Gtk.Label(label="Risikoprofil:", xalign=0), 0, 1, 1, 1)
        self.planning_risk_combo = Gtk.ComboBoxText()
        self.planning_risk_combo.append("konservativ", "Konservativ")
        self.planning_risk_combo.append("ausgewogen", "Ausgewogen")
        self.planning_risk_combo.append("offensiv", "Offensiv")
        self.planning_risk_combo.set_active_id("ausgewogen")
        self.planning_risk_combo.set_sensitive(False)
        risk_subgrid.attach(self.planning_risk_combo, 1, 1, 1, 1)
        risk_subgrid.attach(_help_button(
            "Wie viel Wertschwankung (und damit Verlustrisiko) du bereit bist "
            "einzugehen, um langfristig höhere Renditechancen zu haben. "
            "Konservativ = mehr Sicherheitsreserve, weniger ETF-Anteil; "
            "offensiv = mehr ETF-Anteil, mehr Schwankung."
        ), 2, 1, 1, 1)

        risk_hint = Gtk.Label(
            xalign=0,
            label="Grobe Faustregel: je kürzer der Horizont bzw. je konservativer "
                  "das Profil, desto mehr vom Investitionsbetrag als "
                  "Sicherheitsreserve (Tagesgeld) statt in den ETF-Sparplan. "
                  "Unter 3 Jahren Horizont wird ganz von Aktien-ETFs abgeraten, "
                  "da kurzfristige Kursschwankungen zu riskant wären.",
        )
        risk_hint.set_line_wrap(True)
        risk_subgrid.attach(risk_hint, 0, 2, 2, 1)

        calc_rec_btn = Gtk.Button(label="Empfehlung berechnen")
        calc_rec_btn.connect("clicked", self._on_calculate_recommendation)
        rec_grid.attach(calc_rec_btn, 0, 6, 2, 1)

        self.recommendation_label = Gtk.Label(xalign=0)
        self.recommendation_label.set_line_wrap(True)
        rec_grid.attach(self.recommendation_label, 0, 7, 2, 1)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        rec_grid.attach(action_box, 0, 8, 2, 1)

        apply_etf_btn = Gtk.Button(label="Monatliche ETF-Rate übernehmen")
        apply_etf_btn.connect("clicked", self._on_apply_recommendation_to_etf)
        action_box.pack_start(apply_etf_btn, False, False, 0)

        apply_capital_btn = Gtk.Button(label="Startkapital-Anteile als Fortschritt vormerken")
        apply_capital_btn.connect("clicked", self._on_apply_capital_to_notgroschen)
        action_box.pack_start(apply_capital_btn, False, False, 0)

        self.apply_capital_as_transaction_check = Gtk.CheckButton(
            label="Dabei auch als Buchung verbuchen (Kontostand sinkt entsprechend)"
        )
        self.apply_capital_as_transaction_check.set_active(True)
        rec_grid.attach(self.apply_capital_as_transaction_check, 0, 9, 2, 1)

        capital_hint = Gtk.Label(
            xalign=0,
            label="Wichtig: Ohne diese Buchung bleibt dein Kontostand oben "
                  "unverändert, obwohl die Sparziele-Fortschritte steigen – "
                  "dasselbe Geld würde dir beim nächsten Mal fälschlich "
                  "erneut als Startkapital angeboten. Häkchen nur entfernen, "
                  "wenn das eingegebene Startkapital NICHT aus deinem "
                  "hinterlegten Kontostand stammt (z. B. separates Erbe/"
                  "Depot, das dort nicht mitgezählt wird).",
        )
        capital_hint.set_line_wrap(True)
        rec_grid.attach(capital_hint, 0, 10, 2, 1)

        disclaimer = Gtk.Label(xalign=0)
        disclaimer.set_line_wrap(True)
        disclaimer.set_markup(
            "<small>Diese Aufteilung folgt der gängigen Faustregel „Notgroschen "
            "(und ggf. weitere Ziele) vor Investieren“ sowie einer einfachen "
            "Horizont-/Risiko-Faustregel für den ETF-Anteil. Beides sind "
            "transparente Modellrechnungen – KEINE individuelle Finanzberatung. "
            "Sie berücksichtigen weder Schulden noch Steuern noch deine "
            "tatsächliche persönliche Risikotragfähigkeit. Alle Werte lassen "
            "sich frei anpassen; für eine verbindliche Einschätzung wende dich "
            "an eine unabhängige Finanzberatung.</small>"
        )
        rec_grid.attach(disclaimer, 0, 11, 2, 1)

        self._current_recommendation = None
        self._update_notgroschen_preview()
        self._refresh_current_balance_display()
        return outer

    def _on_save_starting_balance(self, widget):
        try:
            date_obj = datetime.datetime.strptime(
                self.balance_date_entry.get_text().strip(), "%d.%m.%Y"
            ).date()
        except ValueError:
            date_obj = datetime.date.today()
        self.store.set_starting_balance(self.balance_amount_spin.get_value(), date_obj.isoformat())
        self._refresh_current_balance_display()

    def _refresh_current_balance_display(self):
        if not hasattr(self, "current_balance_label"):
            return
        balance = self.store.get_current_account_balance()
        if balance is None:
            self.current_balance_label.set_markup(
                "<i>Noch kein Kontostand hinterlegt – oben Stichtag und Betrag "
                "eintragen und speichern.</i>"
            )
        else:
            self.current_balance_label.set_markup(
                f"Aktueller Kontostand (berechnet): <b>{fmt_amount(balance)}</b>"
            )

    def _on_apply_balance_to_recommendation(self, widget):
        balance = self.store.get_current_account_balance()
        if balance is not None:
            self.planning_capital_spin.set_value(max(0.0, balance))

    def _on_recalc_fixed_costs(self, widget):
        self.planning_fixed_costs_spin.set_value(self.store.estimate_monthly_fixed_costs())

    def _update_notgroschen_preview(self):
        if not hasattr(self, "notgroschen_preview_label"):
            return
        fixed = self.planning_fixed_costs_spin.get_value()
        months = int(self.planning_months_spin.get_value())
        target = fixed * months
        existing = self.store.get_goal_by_name("Notgroschen")
        if existing:
            current = existing["current_amount"]
            status = (f"Bestehendes Sparziel „Notgroschen“: {fmt_amount(current)} von "
                      f"aktuell {fmt_amount(existing['target_amount'])} angespart.")
        else:
            status = "Noch kein Sparziel „Notgroschen“ angelegt."
        self.notgroschen_preview_label.set_markup(
            f"Zielbetrag bei {months} Monaten Fixkosten: <b>{fmt_amount(target)}</b>\n{status}"
        )

    def _on_create_or_update_notgroschen(self, widget):
        fixed = self.planning_fixed_costs_spin.get_value()
        months = int(self.planning_months_spin.get_value())
        target = fixed * months
        existing = self.store.get_goal_by_name("Notgroschen")
        if existing:
            self.store.update_goal_target(existing["id"], target)
        else:
            self.store.add_goal("Notgroschen", target, None)
        self._update_notgroschen_preview()
        self._refresh_goals_tab()

    def _on_risk_toggle_changed(self, widget):
        active = widget.get_active()
        self.planning_horizon_spin.set_sensitive(active)
        self.planning_risk_combo.set_sensitive(active)

    def _on_calculate_recommendation(self, widget):
        net_income = self.planning_income_spin.get_value()
        capital = self.planning_capital_spin.get_value()
        leisure = net_income * (self.planning_leisure_percent_spin.get_value() / 100)
        fixed = self.planning_fixed_costs_spin.get_value()
        months = int(self.planning_months_spin.get_value())
        ng_target = fixed * months

        if self.planning_include_goals_check.get_active():
            # Alle Sparziele in ihrer manuell im Sparziele-Tab festgelegten
            # Priorität übernehmen. Der Notgroschen-Zielbetrag wird dabei
            # immer live aus den Feldern oben berechnet (nicht aus dem
            # gespeicherten Ziel gelesen), damit sich Änderungen an den
            # Fixkosten/Zielmonaten sofort in der Vorschau widerspiegeln.
            all_goals = self.store.list_goals()
            goals_input = []
            has_notgroschen = any(g["name"] == "Notgroschen" for g in all_goals)
            if not has_notgroschen:
                # Noch kein Notgroschen-Ziel angelegt -> virtuell an erster
                # Stelle einplanen, damit die Empfehlung trotzdem sinnvoll ist.
                goals_input.append({"id": None, "name": "Notgroschen",
                                     "target_amount": ng_target, "current_amount": 0.0})
            for g in all_goals:
                target = ng_target if g["name"] == "Notgroschen" else g["target_amount"]
                goals_input.append({
                    "id": g["id"], "name": g["name"],
                    "target_amount": target, "current_amount": g["current_amount"],
                })
        else:
            # Nur Notgroschen berücksichtigen, unabhängig von seiner Priorität
            # unter den übrigen Zielen.
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

        if self.planning_risk_check.get_active():
            horizon = self.planning_horizon_spin.get_value()
            profile = self.planning_risk_combo.get_active_id()
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
            f"Freizeitbudget von {fmt_amount(leisure)}): <b>{fmt_amount(rec['monthly_available'])}</b>",
            f"Startkapital: <b>{fmt_amount(capital)}</b>",
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
                f"• <b>{g['name']}</b> (Ziel: {fmt_amount(g['target_amount'])}, "
                f"bereits {fmt_amount(g['current_amount'])} vorhanden): "
                f"{fmt_amount(g['capital_allocated'])} aus Startkapital, "
                f"{fmt_amount(g['monthly_allocated'])}/Monat – {status}"
            )

        lines.append("")
        if rec["risk_applied"]:
            lines.append(
                f"Rest zum Investieren – bei {int(self.planning_horizon_spin.get_value())} Jahren "
                f"Horizont, Profil „{self.planning_risk_combo.get_active_text()}“: empfohlener "
                f"ETF-Anteil <b>{rec['equity_share_percent']}%</b>, Rest als Sicherheitsreserve:"
            )
            lines.append(
                f"  → ETF-Sparplan: <b>{fmt_amount(rec['monthly_to_equity'])}</b>/Monat, "
                f"<b>{fmt_amount(rec['capital_to_equity'])}</b> Startkapital"
            )
            lines.append(
                f"  → Sicherheitsreserve (z. B. Tagesgeld): "
                f"<b>{fmt_amount(rec['monthly_to_safety'])}</b>/Monat, "
                f"<b>{fmt_amount(rec['capital_to_safety'])}</b> Startkapital"
            )
        else:
            lines.append(
                f"Rest zum Investieren (z. B. ETF-Sparplan): "
                f"<b>{fmt_amount(rec['monthly_to_etf'])}</b>/Monat, "
                f"<b>{fmt_amount(rec['capital_to_etf'])}</b> Startkapital"
            )

        self.recommendation_label.set_markup("\n".join(lines))

    def _on_apply_recommendation_to_etf(self, widget):
        if not self._current_recommendation:
            return
        rec = self._current_recommendation
        amount = rec["monthly_to_equity"] if rec.get("risk_applied") else rec["monthly_to_etf"]
        if amount <= 0:
            return
        self.etf_amount_spin.set_value(amount)
        self.notebook.set_current_page(self.notebook.page_num(self.etf_tab_page))

    def _on_apply_capital_to_notgroschen(self, widget):
        if not self._current_recommendation:
            return
        book_as_transaction = self.apply_capital_as_transaction_check.get_active()
        applied_any = False
        for g in self._current_recommendation["goals"]:
            amount = g["capital_allocated"]
            if amount <= 0:
                continue
            goal_id = g["id"]
            if goal_id is None:
                # Notgroschen-Ziel existierte noch nicht -> zuerst anlegen
                self._on_create_or_update_notgroschen(widget)
                created = self.store.get_goal_by_name("Notgroschen")
                goal_id = created["id"] if created else None
                if goal_id is None:
                    continue
            # Standardmäßig als echte Buchung verbucht (Checkbox), damit der
            # Kontostand oben entsprechend sinkt und dasselbe Geld nicht beim
            # nächsten Mal erneut als Startkapital angeboten wird. Nur ohne
            # Buchung, wenn das Startkapital nachweislich NICHT aus dem
            # hinterlegten Kontostand stammt.
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
        outer = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(10)
        outer.add(box)

        form = Gtk.Grid(column_spacing=8, row_spacing=6)
        box.pack_start(form, False, False, 0)

        row = 0
        form.attach(Gtk.Label(label="Name:", xalign=0), 0, row, 1, 1)
        self.etf_name_entry = Gtk.Entry(text="Mein ETF-Sparplan")
        form.attach(self.etf_name_entry, 1, row, 1, 1)

        row += 1
        form.attach(Gtk.Label(label="Monatliche Rate (€):", xalign=0), 0, row, 1, 1)
        self.etf_amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=100, lower=1, upper=100000,
                                       step_increment=10, page_increment=50),
            numeric=True, digits=2,
        )
        form.attach(self.etf_amount_spin, 1, row, 1, 1)

        row += 1
        form.attach(Gtk.Label(label="Erwartete jährl. Rendite (%):", xalign=0), 0, row, 1, 1)
        self.etf_return_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=6.0, lower=-20, upper=30,
                                       step_increment=0.5, page_increment=1),
            numeric=True, digits=2,
        )
        form.attach(self.etf_return_spin, 1, row, 1, 1)

        row += 1
        form.attach(Gtk.Label(label="Laufzeit (Jahre):", xalign=0), 0, row, 1, 1)
        self.etf_years_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=10, lower=1, upper=60,
                                       step_increment=1, page_increment=5),
            numeric=True,
        )
        form.attach(self.etf_years_spin, 1, row, 1, 1)

        row += 1
        form.attach(Gtk.Label(label="Jährliche Erhöhung der Sparrate (%):", xalign=0),
                    0, row, 1, 1)
        self.etf_increase_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=50,
                                       step_increment=0.5, page_increment=5),
            numeric=True, digits=2,
        )
        form.attach(self.etf_increase_spin, 1, row, 1, 1)
        form.attach(_help_button(
            "Erhöht die monatliche Sparrate jedes Jahr um diesen Prozentsatz, "
            "z. B. um eine erwartete Gehaltssteigerung nachzubilden. 0 % = die "
            "Sparrate bleibt über die gesamte Laufzeit konstant."
        ), 2, row, 1, 1)

        row += 1
        form.attach(Gtk.Label(label="Maximale Sparrate (€, 0 = kein Deckel):", xalign=0),
                    0, row, 1, 1)
        self.etf_cap_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=100000,
                                       step_increment=10, page_increment=50),
            numeric=True, digits=2,
        )
        form.attach(self.etf_cap_spin, 1, row, 1, 1)
        form.attach(_help_button(
            "Obergrenze für die Sparrate, falls sie sich durch die jährliche "
            "Erhöhung sonst unbegrenzt weiter steigern würde. 0 bedeutet: kein "
            "Deckel, die Rate wächst ungebremst weiter."
        ), 2, row, 1, 1)

        # -- Steuer-Einstellungen --
        tax_frame = Gtk.Frame(label="Deutsche Kapitalertragsteuer (vereinfacht, anpassbar)")
        box.pack_start(tax_frame, False, False, 0)
        tax_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        tax_grid.set_border_width(8)
        tax_frame.add(tax_grid)

        self.etf_vorab_check = Gtk.CheckButton(
            label="Jährliche Vorabpauschale simulieren (statt Einmalbesteuerung am Laufzeitende)"
        )
        self.etf_vorab_check.connect("toggled", self._on_vorab_toggled)
        tax_grid.attach(self.etf_vorab_check, 0, 0, 3, 1)

        tax_grid.attach(Gtk.Label(label="Basiszins (%, jährlich vom BMF festgelegt):", xalign=0),
                         0, 1, 1, 1)
        self.etf_basiszins_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=2.55, lower=0, upper=15,
                                       step_increment=0.1, page_increment=0.5),
            numeric=True, digits=2,
        )
        self.etf_basiszins_spin.set_sensitive(False)
        tax_grid.attach(self.etf_basiszins_spin, 1, 1, 1, 1)
        tax_grid.attach(_help_button(
            "Zinssatz, den das Bundesfinanzministerium jährlich für die "
            "Vorabpauschale-Berechnung festlegt (orientiert sich an "
            "langfristigen Bundesanleihen). Ändert sich jährlich – der "
            "voreingestellte Wert ist nur ein Richtwert, aktuellen Wert bei "
            "Bedarf nachschlagen."
        ), 2, 1, 1, 1)

        tax_grid.attach(Gtk.Label(label="Teilfreistellung (%):", xalign=0), 0, 2, 1, 1)
        self.etf_teilfreistellung_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=30, lower=0, upper=60,
                                       step_increment=5, page_increment=10),
            numeric=True, digits=1,
        )
        tax_grid.attach(self.etf_teilfreistellung_spin, 1, 2, 1, 1)
        tax_grid.attach(_help_button(
            "Anteil des Fondsgewinns, der steuerfrei bleibt (§20 InvStG), um "
            "die Vorbelastung durch Unternehmenssteuern auszugleichen. "
            "30 % ist der übliche Satz für Aktienfonds-ETFs mit mindestens "
            "51 % Aktienquote. Bei Anleihen-ETFs 0 %, bei Mischfonds meist "
            "15 %, bei Immobilienfonds 60–80 %."
        ), 2, 2, 1, 1)

        tax_grid.attach(Gtk.Label(label="Kapitalertragsteuer (%):", xalign=0), 0, 3, 1, 1)
        self.etf_kest_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=25, lower=0, upper=50,
                                       step_increment=1, page_increment=5),
            numeric=True, digits=2,
        )
        tax_grid.attach(self.etf_kest_spin, 1, 3, 1, 1)
        tax_grid.attach(_help_button(
            "Die pauschale Abgeltungsteuer auf Kapitalerträge in Deutschland, "
            "gesetzlich 25 %. In der Regel nicht anzupassen, außer für "
            "Was-wäre-wenn-Szenarien."
        ), 2, 3, 1, 1)

        tax_grid.attach(Gtk.Label(label="Solidaritätszuschlag (%):", xalign=0), 0, 4, 1, 1)
        self.etf_soli_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=5.5, lower=0, upper=20,
                                       step_increment=0.5, page_increment=1),
            numeric=True, digits=2,
        )
        tax_grid.attach(self.etf_soli_spin, 1, 4, 1, 1)
        tax_grid.attach(_help_button(
            "Zuschlag von 5,5 % auf die Kapitalertragsteuer (nicht auf den "
            "Gewinn selbst) – gesetzlich vorgegeben, in der Regel nicht "
            "anzupassen."
        ), 2, 4, 1, 1)

        tax_grid.attach(Gtk.Label(label="Sparerpauschbetrag (€/Jahr):", xalign=0), 0, 5, 1, 1)
        self.etf_pauschbetrag_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=1000, lower=0, upper=5000,
                                       step_increment=100, page_increment=500),
            numeric=True, digits=0,
        )
        tax_grid.attach(self.etf_pauschbetrag_spin, 1, 5, 1, 1)
        tax_grid.attach(_help_button(
            "Steuerfreibetrag auf Kapitalerträge: 1.000 € pro Jahr bei "
            "Einzelveranlagung, 2.000 € bei Zusammenveranlagung (Ehepaare, "
            "Stand 2023). Wird hier nur einmalig (ohne Vorabpauschale) bzw. "
            "jährlich (mit Vorabpauschale) angesetzt – in der Realität ist er "
            "über einen Freistellungsauftrag auf mehrere Banken/Depots "
            "aufteilbar."
        ), 2, 5, 1, 1)

        self.etf_tax_hint = Gtk.Label(xalign=0)
        self.etf_tax_hint.set_line_wrap(True)
        self._update_tax_hint()
        tax_grid.attach(self.etf_tax_hint, 0, 6, 3, 1)

        calc_btn = Gtk.Button(label="Berechnen & Speichern")
        calc_btn.connect("clicked", self._on_calculate_etf)
        box.pack_start(calc_btn, False, False, 0)

        self.etf_summary_label = Gtk.Label(label="", xalign=0)
        self.etf_summary_label.set_line_wrap(True)
        box.pack_start(self.etf_summary_label, False, False, 0)

        self.etf_result_store = Gtk.ListStore(int, str, str, str, str)
        # jahr, sparrate, eingezahlt, wert, gewinn
        self.etf_result_view = Gtk.TreeView(model=self.etf_result_store)
        self.etf_result_view.set_size_request(-1, 220)
        box.pack_start(self.etf_result_view, False, False, 0)
        for title, col_id in [("Jahr", 0), ("Sparrate", 1), ("Eingezahlt", 2),
                               ("Wert", 3), ("Gewinn", 4)]:
            renderer = Gtk.CellRendererText()
            renderer.set_property("xalign", 1.0 if col_id > 0 else 0.0)
            column = Gtk.TreeViewColumn(title, renderer, text=col_id)
            self.etf_result_view.append_column(column)

        plan_manage_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_start(plan_manage_box, False, False, 0)

        plan_manage_box.pack_start(Gtk.Label(label="Gespeicherter Plan:"), False, False, 0)
        self.etf_saved_plans_combo = Gtk.ComboBoxText()
        plan_manage_box.pack_start(self.etf_saved_plans_combo, True, True, 0)

        del_btn = Gtk.Button(label="Löschen")
        del_btn.connect("clicked", self._on_delete_etf_plan)
        plan_manage_box.pack_start(del_btn, False, False, 0)

        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 4)

        compare_label = Gtk.Label(
            xalign=0,
            label="Vergleich gespeicherter Sparpläne (Wertentwicklung, vor Steuern):",
        )
        box.pack_start(compare_label, False, False, 0)

        self.etf_compare_area = Gtk.DrawingArea()
        self.etf_compare_area.set_size_request(-1, 260)
        self.etf_compare_area.connect("draw", self._on_draw_etf_comparison)
        box.pack_start(self.etf_compare_area, False, False, 0)

        self._refresh_etf_plan_selector()
        self._refresh_etf_comparison()
        return outer

    def _on_vorab_toggled(self, widget):
        self.etf_basiszins_spin.set_sensitive(widget.get_active())
        self._update_tax_hint()

    def _update_tax_hint(self):
        if self.etf_vorab_check.get_active():
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
                    "Kirchensteuer bleibt unberücksichtigt. Standardwerte: 30 % "
                    "Teilfreistellung für Aktienfonds-ETFs, 25 % Kapitalertragsteuer, "
                    "5,5 % Soli, 1.000 € Sparerpauschbetrag (Einzelveranlagung).")
        self.etf_tax_hint.set_text(text)

    def _on_calculate_etf(self, widget):
        name = self.etf_name_entry.get_text().strip() or "ETF-Sparplan"
        monthly_amount = self.etf_amount_spin.get_value()
        annual_return = self.etf_return_spin.get_value()
        years = int(self.etf_years_spin.get_value())
        increase = self.etf_increase_spin.get_value()
        cap = self.etf_cap_spin.get_value()
        cap = cap if cap > 0 else None

        teilfreistellung = self.etf_teilfreistellung_spin.get_value()
        kest = self.etf_kest_spin.get_value()
        soli = self.etf_soli_spin.get_value()
        pauschbetrag = self.etf_pauschbetrag_spin.get_value()

        if self.etf_vorab_check.get_active():
            results, cumulative_pretaxed_gain = FinanceStore.project_etf_plan_with_vorabpauschale(
                monthly_amount, annual_return, years,
                annual_increase_percent=increase, max_monthly_amount=cap,
                basiszins_percent=self.etf_basiszins_spin.get_value(),
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
                f" Während der Laufzeit wurden bereits <b>{fmt_amount(total_vorab_tax_paid)}</b> "
                f"Steuern auf Vorabpauschalen gezahlt (im Endwert schon berücksichtigt); "
                f"davon <b>{fmt_amount(cumulative_pretaxed_gain)}</b> Gewinn wurden bei der "
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

        self.etf_result_store.clear()
        for r in results:
            self.etf_result_store.append([
                r["year"], fmt_amount(r["monthly_rate_amount"]),
                fmt_amount(r["invested"]), fmt_amount(r["value"]),
                fmt_amount(r["gain"]),
            ])

        value_after_tax = tax.get("value_after_tax")
        final_tax_amount = tax.get("final_tax", tax.get("tax"))
        self.etf_summary_label.set_markup(
            f"Nach <b>{years} Jahren</b> bei <b>{annual_return:.2f}% p.a.</b>: "
            f"eingezahlt <b>{fmt_amount(final['invested'])}</b>, "
            f"Endwert vor Abschluss-Steuer <b>{fmt_amount(final['value'])}</b>, "
            f"Gewinn <b>{fmt_amount(tax['gain'])}</b>.\n"
            f"Steuer bei (angenommenem) Verkauf: <b>{fmt_amount(final_tax_amount)}</b> "
            f"→ Endwert nach Steuern ca. <b>{fmt_amount(value_after_tax)}</b>."
            f"{vorab_note}"
        )

        self.current_etf_plan_id = self.store.add_etf_plan(
            name, monthly_amount, annual_return, datetime.date.today().isoformat(),
            years, annual_increase_percent=increase, max_monthly_amount=cap,
        )
        self._refresh_etf_plan_selector()
        self._refresh_etf_comparison()

    def _refresh_etf_plan_selector(self):
        """Befüllt die Auswahlliste mit ALLEN gespeicherten Plänen (nicht nur
        dem zuletzt berechneten), damit jeder einzeln ausgewählt und gelöscht
        werden kann."""
        self.etf_saved_plans_combo.remove_all()
        plans = self.store.list_etf_plans()
        for plan in plans:
            label = f"{plan['name']} ({plan['duration_years']} Jahre, {plan['start_date']})"
            self.etf_saved_plans_combo.append(str(plan["id"]), label)
        if plans:
            # Zuletzt berechneten/gespeicherten Plan vorauswählen, falls vorhanden
            active_id = str(self.current_etf_plan_id) if self.current_etf_plan_id else str(plans[-1]["id"])
            self.etf_saved_plans_combo.set_active_id(active_id)

    def _on_delete_etf_plan(self, widget):
        selected_id = self.etf_saved_plans_combo.get_active_id()
        if selected_id is None:
            return
        plan_id = int(selected_id)
        self.store.delete_etf_plan(plan_id)
        if self.current_etf_plan_id == plan_id:
            self.current_etf_plan_id = None
            self.etf_result_store.clear()
            self.etf_summary_label.set_text("")
        self._refresh_etf_plan_selector()
        self._refresh_etf_comparison()

    def _refresh_etf_comparison(self):
        self._etf_comparison_data = []
        for i, plan in enumerate(self.store.list_etf_plans()):
            results = FinanceStore.project_etf_plan(
                plan["monthly_amount"], plan["annual_return_percent"], plan["duration_years"],
                annual_increase_percent=plan["annual_increase_percent"] or 0,
                max_monthly_amount=plan["max_monthly_amount"],
            )
            self._etf_comparison_data.append({
                "name": plan["name"],
                "color": color_for_index(i),
                "points": [(r["year"], r["value"]) for r in results],
            })
        if hasattr(self, "etf_compare_area"):
            self.etf_compare_area.queue_draw()

    def _on_draw_etf_comparison(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        data = getattr(self, "_etf_comparison_data", [])
        fg = _widget_fg_color(widget)

        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(11)

        if not data:
            cr.set_source_rgba(*fg, 0.7)
            cr.move_to(20, height / 2)
            cr.show_text("Noch keine gespeicherten Sparpläne zum Vergleichen.")
            return False

        margin_left, margin_right = 70, 140
        margin_top, margin_bottom = 16, 30
        plot_w = max(10, width - margin_left - margin_right)
        plot_h = max(10, height - margin_top - margin_bottom)

        max_year = max(p[0] for plan in data for p in plan["points"])
        max_value = max(p[1] for plan in data for p in plan["points"]) or 1

        # Achsen
        cr.set_source_rgba(*fg, 0.4)
        cr.set_line_width(1)
        cr.move_to(margin_left, margin_top)
        cr.line_to(margin_left, height - margin_bottom)
        cr.line_to(width - margin_right, height - margin_bottom)
        cr.stroke()

        cr.set_source_rgba(*fg, 0.75)
        for fraction in (0, 0.5, 1.0):
            y = height - margin_bottom - fraction * plot_h
            cr.move_to(4, y + 4)
            cr.show_text(fmt_amount(max_value * fraction))
        for fraction in (0, 0.5, 1.0):
            x = margin_left + fraction * plot_w
            year = max(1, round(max_year * fraction))
            cr.move_to(x - 6, height - margin_bottom + 16)
            cr.show_text(f"J{year}")

        legend_y = margin_top
        for plan in data:
            points = plan["points"]
            cr.set_source_rgb(*plan["color"])
            cr.set_line_width(2)
            for i, (year, value) in enumerate(points):
                x = margin_left + (year / max_year) * plot_w if max_year else margin_left
                y = height - margin_bottom - (value / max_value) * plot_h if max_value else \
                    height - margin_bottom
                if i == 0:
                    cr.move_to(x, y)
                else:
                    cr.line_to(x, y)
            cr.stroke()

            legend_x = width - margin_right + 14
            cr.set_source_rgb(*plan["color"])
            cr.rectangle(legend_x, legend_y, 14, 4)
            cr.fill()
            cr.set_source_rgba(*fg, 0.9)
            final_value = points[-1][1] if points else 0
            cr.move_to(legend_x + 20, legend_y + 8)
            cr.show_text(f"{plan['name']}")
            cr.move_to(legend_x + 20, legend_y + 20)
            cr.show_text(fmt_amount(final_value))
            legend_y += 40

        return False

    # =====================================================================
    # Tab 6: Auswertungen (Kreisdiagramm, Trend, Sankey-Geldfluss)
    # =====================================================================

    def _build_stats_tab(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_border_width(10)

        switcher_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        root.pack_start(switcher_box, False, False, 0)
        switcher_box.pack_start(Gtk.Label(label="Ansicht:"), False, False, 0)

        self.stats_view_combo = Gtk.ComboBoxText()
        self.stats_view_combo.append("kategorien", "Ausgaben nach Kategorie (Kreisdiagramm)")
        self.stats_view_combo.append("trend", "Einnahmen/Ausgaben-Trend")
        self.stats_view_combo.append("fluss", "Geldfluss (Sankey-Diagramm)")
        self.stats_view_combo.set_active_id("kategorien")
        self.stats_view_combo.connect("changed", self._on_stats_view_changed)
        switcher_box.pack_start(self.stats_view_combo, False, False, 0)

        self.stats_stack = Gtk.Stack()
        self.stats_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        root.pack_start(self.stats_stack, True, True, 0)

        self.stats_stack.add_named(self._build_pie_section(), "kategorien")
        self.stats_stack.add_named(self._build_trend_section(), "trend")
        self.stats_stack.add_named(self._build_sankey_section(), "fluss")

        self._refresh_stats()
        return root

    def _on_stats_view_changed(self, combo):
        self.stats_stack.set_visible_child_name(combo.get_active_id())

    def _build_pie_section(self):
        pie_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        pie_nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        pie_section.pack_start(pie_nav, False, False, 0)
        pie_nav.pack_start(Gtk.Label(label="Ausgaben nach Kategorie –"), False, False, 0)

        prev_btn = _nav_button("◀", lambda w: self._shift_stats_month(-1))
        pie_nav.pack_start(prev_btn, False, False, 0)

        self.stats_month_label = Gtk.Label(label="")
        pie_nav.pack_start(self.stats_month_label, False, False, 0)

        next_btn = _nav_button("▶", lambda w: self._shift_stats_month(1))
        pie_nav.pack_start(next_btn, False, False, 0)

        self.pie_area = Gtk.DrawingArea()
        self.pie_area.set_size_request(-1, 380)
        self.pie_area.connect("draw", self._on_draw_pie)
        pie_section.pack_start(self.pie_area, True, True, 0)

        return pie_section

    def _build_trend_section(self):
        trend_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        trend_nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        trend_section.pack_start(trend_nav, False, False, 0)
        trend_nav.pack_start(Gtk.Label(label="Trend – letzte"), False, False, 0)

        self.trend_months_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=6, lower=2, upper=24,
                                       step_increment=1, page_increment=3),
            numeric=True,
        )
        self.trend_months_spin.connect("value-changed", self._on_trend_months_changed)
        trend_nav.pack_start(self.trend_months_spin, False, False, 0)
        trend_nav.pack_start(Gtk.Label(label="Monate (bezogen auf den gewählten Monat)"),
                              False, False, 0)

        legend_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        trend_nav.pack_end(legend_box, False, False, 0)
        income_swatch = Gtk.Label()
        income_swatch.set_markup('<span foreground="#1e8c3d">■</span>')
        legend_box.pack_start(income_swatch, False, False, 0)
        legend_box.pack_start(Gtk.Label(label="Einnahmen"), False, False, 0)
        expense_swatch = Gtk.Label()
        expense_swatch.set_markup('<span foreground="#bf3826">■</span>')
        legend_box.pack_start(expense_swatch, False, False, 6)
        legend_box.pack_start(Gtk.Label(label="Ausgaben"), False, False, 0)

        self.trend_area = Gtk.DrawingArea()
        self.trend_area.set_size_request(-1, 380)
        self.trend_area.connect("draw", self._on_draw_trend)
        trend_section.pack_start(self.trend_area, True, True, 0)

        return trend_section

    def _build_sankey_section(self):
        sankey_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        sankey_nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sankey_section.pack_start(sankey_nav, False, False, 0)
        sankey_nav.pack_start(Gtk.Label(label="Geldfluss –"), False, False, 0)

        prev_btn = _nav_button("◀", lambda w: self._shift_stats_month(-1))
        sankey_nav.pack_start(prev_btn, False, False, 0)

        self.sankey_month_label = Gtk.Label(label="")
        sankey_nav.pack_start(self.sankey_month_label, False, False, 0)

        next_btn = _nav_button("▶", lambda w: self._shift_stats_month(1))
        sankey_nav.pack_start(next_btn, False, False, 0)

        hint = Gtk.Label(xalign=0)

        hint.set_markup(
            '<b>Links</b> = Einnahmen nach Kategorie. '
            '<b>Rechts</b> = Ausgaben nach Kategorie sowie '
            '<span foreground="#4caf50"><b>Überschuss</b></span> / '
            '<span foreground="#e05245"><b>Fehlbetrag</b></span>, '
            'falls Einnahmen und Ausgaben nicht übereinstimmen.\n'
            'Die Bänder zeigen keine direkte 1:1-Zuordnung einzelner Euro, '
            'sondern die anteilige Verteilung über das monatliche Gesamtbudget.'
        )

        hint.set_line_wrap(True)

        sankey_section.pack_start(hint, False, False, 0)

        self.sankey_area = Gtk.DrawingArea()
        self.sankey_area.set_size_request(-1, 380)
        self.sankey_area.connect("draw", self._on_draw_sankey)
        sankey_section.pack_start(self.sankey_area, True, True, 0)

        return sankey_section

    def _shift_stats_month(self, delta):
        self.stats_month = add_months(self.stats_month, delta)
        self._refresh_stats()

    def _on_trend_months_changed(self, widget):
        self.trend_months = int(widget.get_value())
        self._refresh_stats()

    def _refresh_stats(self):
        self.stats_month_label.set_text(month_label(self.stats_month))
        self.sankey_month_label.set_text(month_label(self.stats_month))
        month_str = self.stats_month.strftime("%Y-%m")

        expense_rows = self.store.spending_by_category(month_str)
        self._pie_data = []
        for i, r in enumerate(expense_rows):
            self._pie_data.append((r["category_name"], r["icon"], r["total"], color_for_index(i)))
        self.pie_area.queue_draw()

        self._trend_data = self.store.monthly_trend(self.trend_months, end_month=month_str)
        self.trend_area.queue_draw()

        income_rows = self.store.income_by_category(month_str)
        left_nodes = [(r["category_name"], r["icon"], r["total"], color_for_index(i))
                      for i, r in enumerate(income_rows)]
        right_nodes = [(r["category_name"], r["icon"], r["total"], color_for_index(i))
                       for i, r in enumerate(expense_rows)]
        total_income = sum(n[2] for n in left_nodes)
        total_expense = sum(n[2] for n in right_nodes)

        if total_income > total_expense + 0.005:
            right_nodes.append(("Übrig/Gespart", "💰", total_income - total_expense,
                                 (0.12, 0.55, 0.24)))
        elif total_expense > total_income + 0.005:
            left_nodes.append(("Fehlbetrag", "⚠️", total_expense - total_income,
                                (0.75, 0.22, 0.17)))

        self._sankey_data = {
            "left": left_nodes, "right": right_nodes,
            "total": max(total_income, total_expense),
        }
        self.sankey_area.queue_draw()

    def _draw_text(self, cr, text, x, y, color, size=12, bold=False):
        """Zeichnet Text über Pango, damit Emoji-Fallback-Schriften funktionieren."""
        layout = PangoCairo.create_layout(cr)

        font = Pango.FontDescription()
        font.set_family("Sans")
        font.set_size(size * Pango.SCALE)

        if bold:
            font.set_weight(Pango.Weight.BOLD)
        else:
            font.set_weight(Pango.Weight.NORMAL)

        layout.set_font_description(font)
        layout.set_text(text, -1)

        cr.set_source_rgba(*color)
        cr.move_to(x, y)

        PangoCairo.show_layout(cr, layout)

        return layout


    def _on_draw_pie(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        data = getattr(self, "_pie_data", [])
        fg = _widget_fg_color(widget)

        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(13)

        if not data:
            cr.set_source_rgba(*fg, 0.7)
            cr.move_to(20, height / 2)
            cr.show_text("Keine Ausgaben in diesem Monat.")
            return False

        total = sum(v for _, _, v, _ in data)
        cx, cy = width * 0.30, height / 2
        radius = max(10, min(cx, cy) - 20)

        start_angle = -math.pi / 2
        for label, icon, value, color in data:
            fraction = value / total if total else 0
            angle = fraction * 2 * math.pi
            cr.set_source_rgb(*color)
            cr.move_to(cx, cy)
            cr.arc(cx, cy, radius, start_angle, start_angle + angle)
            cr.close_path()
            cr.fill()
            start_angle += angle

        legend_x = width * 0.58
        legend_y = 16
        line_h = 22
        for i, (label, icon, value, color) in enumerate(data):
            y = legend_y + i * line_h
            if y > height - 10:
                cr.set_source_rgba(*fg, 0.7)
                cr.move_to(legend_x, y)
                cr.show_text("…")
                break
            cr.set_source_rgb(*color)
            cr.rectangle(legend_x, y, 14, 14)
            cr.fill()
            cr.set_source_rgba(*fg, 0.9)

            pct = (value / total * 100) if total else 0

            self._draw_text(
                cr,
                f"{icon} {label}: {fmt_amount(value)} ({pct:.0f}%)",
                legend_x + 20,
                y - 1,
                fg,
                size=13
            )


        return False

    def _on_draw_trend(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        data = getattr(self, "_trend_data", [])
        fg = _widget_fg_color(widget)

        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(11)

        if not data:
            cr.set_source_rgba(*fg, 0.7)
            cr.move_to(20, height / 2)
            cr.show_text("Keine Daten.")
            return False

        margin_left, margin_right = 70, 20
        margin_top, margin_bottom = 20, 34
        plot_w = max(10, width - margin_left - margin_right)
        plot_h = max(10, height - margin_top - margin_bottom)

        max_val = max([d["income"] for d in data] + [d["expense"] for d in data] + [1])

        # Achsen
        cr.set_source_rgba(*fg, 0.4)
        cr.set_line_width(1)
        cr.move_to(margin_left, margin_top)
        cr.line_to(margin_left, height - margin_bottom)
        cr.line_to(width - margin_right, height - margin_bottom)
        cr.stroke()

        # Y-Achsen-Beschriftung (0, Mitte, Max)
        cr.set_source_rgba(*fg, 0.75)
        for fraction in (0, 0.5, 1.0):
            y = height - margin_bottom - fraction * plot_h
            value = max_val * fraction
            cr.move_to(4, y + 4)
            cr.show_text(fmt_amount(value))

        n = len(data)
        group_w = plot_w / n
        bar_w = group_w * 0.32

        for i, d in enumerate(data):
            x0 = margin_left + i * group_w + group_w * 0.12
            income_h = (d["income"] / max_val) * plot_h if max_val else 0
            expense_h = (d["expense"] / max_val) * plot_h if max_val else 0

            cr.set_source_rgb(0.12, 0.55, 0.24)
            cr.rectangle(x0, height - margin_bottom - income_h, bar_w, income_h)
            cr.fill()

            cr.set_source_rgb(0.75, 0.22, 0.17)
            cr.rectangle(x0 + bar_w + 3, height - margin_bottom - expense_h, bar_w, expense_h)
            cr.fill()

            cr.set_source_rgba(*fg, 0.9)
            label = datetime.datetime.strptime(d["month"], "%Y-%m").strftime("%m/%y")
            text_extents = cr.text_extents(label)
            cr.move_to(x0 + bar_w - text_extents.width / 2, height - margin_bottom + 16)
            cr.show_text(label)

        return False

    @staticmethod
    def _draw_flow_band(cr, x0, y0_top, y0_bottom, x1, y1_top, y1_bottom, color, alpha=0.55):
        """Zeichnet ein weiches, gebogenes 'Sankey'-Band zwischen zwei vertikalen
        Segmenten (x0/y0-Bereich -> x1/y1-Bereich)."""
        cx = (x0 + x1) / 2
        cr.move_to(x0, y0_top)
        cr.curve_to(cx, y0_top, cx, y1_top, x1, y1_top)
        cr.line_to(x1, y1_bottom)
        cr.curve_to(cx, y1_bottom, cx, y0_bottom, x0, y0_bottom)
        cr.close_path()
        cr.set_source_rgba(color[0], color[1], color[2], alpha)
        cr.fill()

    def _on_draw_sankey(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        data = getattr(self, "_sankey_data", None)
        fg = _widget_fg_color(widget)

        if not data or data["total"] <= 0:
            self._draw_text(
                cr,
                "Keine Buchungen in diesem Monat.",
                20,
                height / 2 - 8,
                fg,
                size=12
            )
            return False

        left_nodes = data["left"]
        right_nodes = data["right"]
        total = data["total"]

        margin_top = 24
        margin_bottom = 24

        plot_h = max(
            10,
            height - margin_top - margin_bottom
        )

        scale = plot_h / total

        bar_w = 18
        x_left = 8
        x_mid = width / 2 - bar_w / 2
        x_right = width - 8 - bar_w
        gap = 2

        # ---------------------------------------------------------
        # Label-Positionen berechnen
        # ---------------------------------------------------------
        def label_positions(nodes):
            positions = []
            y = margin_top

            min_gap = 20

            for name, icon, value, color in nodes:
                raw_h = value * scale

                positions.append(
                    y + raw_h / 2
                )

                y += raw_h

            # Mindestabstand zwischen Labels
            for i in range(1, len(positions)):
                positions[i] = max(
                    positions[i],
                    positions[i - 1] + min_gap
                )

            # Nach unten absichern
            if positions:
                max_y = height - margin_bottom - 8

                if positions[-1] > max_y:
                    shift = positions[-1] - max_y
                    positions = [
                        p - shift
                        for p in positions
                    ]

            # Nach oben absichern
            if positions:
                min_y = margin_top + 8

                if positions[0] < min_y:
                    shift = min_y - positions[0]
                    positions = [
                        p + shift
                        for p in positions
                    ]

            return positions

        left_labels = label_positions(left_nodes)
        right_labels = label_positions(right_nodes)

        # =========================================================
        # LABEL-TEXTE VORAB BERECHNEN
        # =========================================================

        left_label_data = []
        right_label_data = []

        font = Pango.FontDescription()
        font.set_family("Sans")
        font.set_size(12 * Pango.SCALE)

        # Linke Labels
        for i, (name, icon, value, color) in enumerate(left_nodes):
            label = f"{icon} {name}: {fmt_amount(value)}"

            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(font)
            layout.set_text(label, -1)

            _, logical_rect = layout.get_pixel_extents()

            left_label_data.append(
                (
                    label,
                    left_labels[i],
                    logical_rect.width,
                    logical_rect.height
                )
            )

        # Rechte Labels
        for i, (name, icon, value, color) in enumerate(right_nodes):
            label = f"{icon} {name}: {fmt_amount(value)}"

            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(font)
            layout.set_text(label, -1)

            _, logical_rect = layout.get_pixel_extents()

            right_label_data.append(
                (
                    label,
                    right_labels[i],
                    logical_rect.width,
                    logical_rect.height
                )
            )

        # =========================================================
        # LINKE SEITE – FLÄCHEN
        # =========================================================

        y = margin_top

        for i, (name, icon, value, color) in enumerate(left_nodes):

            raw_h = value * scale
            h = max(1.0, raw_h - gap)

            node_center = y + raw_h / 2

            # Band
            self._draw_flow_band(
                cr,
                x_left + bar_w,
                y,
                y + h,
                x_mid,
                y,
                y + h,
                color
            )

            # Balken
            cr.set_source_rgb(*color)

            cr.rectangle(
                x_left,
                y,
                bar_w,
                h
            )

            cr.fill()

            # Verbindungslinie wird ebenfalls vor den
            # Beschriftungen gezeichnet.
            label_y = left_labels[i]

            if abs(label_y - node_center) > 8:

                cr.set_source_rgba(
                    fg[0],
                    fg[1],
                    fg[2],
                    0.35
                )

                cr.set_line_width(1)

                cr.move_to(
                    x_left + bar_w,
                    node_center
                )

                cr.line_to(
                    x_left + bar_w + 4,
                    label_y
                )

                cr.stroke()

            y += raw_h

        # =========================================================
        # MITTE
        # =========================================================

        cr.set_source_rgba(
            fg[0],
            fg[1],
            fg[2],
            0.25
        )

        cr.rectangle(
            x_mid,
            margin_top,
            bar_w,
            plot_h
        )

        cr.fill()

        # "Gesamt"
        layout = PangoCairo.create_layout(cr)

        layout.set_font_description(font)
        layout.set_text("Gesamt", -1)

        _, logical_rect = layout.get_pixel_extents()

        text_width = logical_rect.width
        text_height = logical_rect.height

        self._draw_text(
            cr,
            "Gesamt",
            x_mid + bar_w / 2 - text_width / 2,
            margin_top - text_height - 4,
            fg,
            size=12
        )

        # =========================================================
        # RECHTE SEITE – FLÄCHEN
        # =========================================================

        y = margin_top

        for i, (name, icon, value, color) in enumerate(right_nodes):

            raw_h = value * scale
            h = max(1.0, raw_h - gap)

            node_center = y + raw_h / 2
            label_y = right_labels[i]

            # Band
            self._draw_flow_band(
                cr,
                x_mid + bar_w,
                y,
                y + h,
                x_right,
                y,
                y + h,
                color
            )

            # Balken
            cr.set_source_rgb(*color)

            cr.rectangle(
                x_right,
                y,
                bar_w,
                h
            )

            cr.fill()

            # Verbindungslinie
            if abs(label_y - node_center) > 8:

                cr.set_source_rgba(
                    fg[0],
                    fg[1],
                    fg[2],
                    0.35
                )

                cr.set_line_width(1)

                cr.move_to(
                    x_right,
                    node_center
                )

                cr.line_to(
                    x_right - 4,
                    label_y
                )

                cr.stroke()

            y += raw_h

        # =========================================================
        # BESCHRIFTUNGEN GANZ ZUM SCHLUSS ZEICHNEN
        #
        # Dadurch liegen die Texte garantiert über den
        # farbigen Sankey-Flächen.
        # =========================================================

        for label, label_y, text_width, text_height in left_label_data:

            self._draw_text(
                cr,
                label,
                x_left + bar_w + 6,
                label_y - 8,
                fg,
                size=12
            )

        for label, label_y, text_width, text_height in right_label_data:

            self._draw_text(
                cr,
                label,
                x_right - text_width - 6,
                label_y - 8,
                fg,
                size=12
            )

        return False



    # =====================================================================
    # Tab 7: Export / Import
    # =====================================================================

    def _build_export_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(10)

        csv_label = Gtk.Label(
            xalign=0,
            label="CSV-Export aller Buchungen – zum Öffnen/Weiterverarbeiten "
                  "in Excel oder LibreOffice Calc."
        )
        csv_label.set_line_wrap(True)
        box.pack_start(csv_label, False, False, 0)

        csv_btn = Gtk.Button(label="Buchungen als CSV exportieren…")
        csv_btn.connect("clicked", self._on_export_csv)
        box.pack_start(csv_btn, False, False, 0)

        csv_import_label = Gtk.Label(
            xalign=0,
            label="CSV-Import: Buchungen aus einer anderen Haushaltsbuch- oder "
                  "Banking-Software übernehmen. Trennzeichen (';' oder ',') sowie "
                  "deutsche/englische Zahlen- und Datumsformate werden automatisch "
                  "erkannt. Erwartet werden Spalten für Datum und Betrag (z. B. "
                  "'Datum'/'Date', 'Betrag'/'Amount'); Kategorie, Art und "
                  "Beschreibung sind optional – unbekannte Kategorien werden "
                  "automatisch angelegt."
        )
        csv_import_label.set_line_wrap(True)
        box.pack_start(csv_import_label, False, False, 0)

        csv_import_btn = Gtk.Button(label="Buchungen aus CSV importieren…")
        csv_import_btn.connect("clicked", self._on_import_csv)
        box.pack_start(csv_import_btn, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(sep, False, False, 8)

        json_label = Gtk.Label(
            xalign=0,
            label="Vollständiges Backup (JSON) – enthält alle Buchungen, Vorlagen, "
                  "Budgets, Sparziele, ETF-Pläne und Kategorien (inkl. Icons). Zum "
                  "Sichern oder Übertragen auf einen anderen Rechner mit diesem Programm."
        )
        json_label.set_line_wrap(True)
        box.pack_start(json_label, False, False, 0)

        export_json_btn = Gtk.Button(label="Backup als JSON exportieren…")
        export_json_btn.connect("clicked", self._on_export_json)
        box.pack_start(export_json_btn, False, False, 0)

        import_json_btn = Gtk.Button(label="Backup aus JSON importieren…")
        import_json_btn.connect("clicked", self._on_import_json)
        box.pack_start(import_json_btn, False, False, 0)

        self.export_status_label = Gtk.Label(label="", xalign=0)
        box.pack_start(self.export_status_label, False, False, 0)

        return box

    def _on_export_csv(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Buchungen als CSV exportieren", parent=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                            Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dialog.set_current_name("haushaltsbuch_export.csv")
        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            self.store.export_transactions_csv(path)
            self.export_status_label.set_text(f"CSV exportiert nach: {path}")
        dialog.destroy()

    def _on_import_csv(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Buchungen aus CSV importieren", parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                            Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        csv_filter = Gtk.FileFilter()
        csv_filter.set_name("CSV-Dateien")
        csv_filter.add_pattern("*.csv")
        dialog.add_filter(csv_filter)

        if dialog.run() != Gtk.ResponseType.OK:
            dialog.destroy()
            return
        path = dialog.get_filename()
        dialog.destroy()

        try:
            result = self.store.import_transactions_csv(path)
        except Exception as exc:
            _run_message_dialog(self, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                                 f"CSV konnte nicht gelesen werden:\n{exc}")
            return

        summary = f"{result['imported']} Buchung(en) importiert"
        if result["skipped"]:
            summary += f", {result['skipped']} übersprungen"
        self.export_status_label.set_text(f"CSV importiert von: {path} – {summary}.")

        message_type = Gtk.MessageType.INFO if not result["errors"] else Gtk.MessageType.WARNING
        detail_lines = "\n".join(result["errors"][:15])
        if len(result["errors"]) > 15:
            detail_lines += f"\n… und {len(result['errors']) - 15} weitere."
        _run_message_dialog(self, message_type, Gtk.ButtonsType.OK,
                             summary + (":" if detail_lines else "."), detail_lines or None)

        self.store.ensure_horizon(self._selected_calendar_month())
        self._after_transactions_changed()
        self._refresh_stats()

    def _on_export_json(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Backup als JSON exportieren", parent=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                            Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dialog.set_current_name("haushaltsbuch_backup.json")
        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            self.store.export_backup_json(path)
            self.export_status_label.set_text(f"Backup exportiert nach: {path}")
        dialog.destroy()

    def _on_import_json(self, widget):
        response = _run_message_dialog(
            self, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK_CANCEL,
            "Import ersetzt alle aktuellen Daten. Fortfahren?",
        )
        if response != Gtk.ResponseType.OK:
            return

        dialog = Gtk.FileChooserDialog(
            title="Backup importieren", parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                            Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            self.store.import_backup_json(path)
            self.store.ensure_horizon(self._selected_calendar_month())
            self.export_status_label.set_text(f"Backup importiert von: {path}")
            self._after_transactions_changed()
            self._refresh_goals_tab()
            self._refresh_stats()
        dialog.destroy()


# ---------------------------------------------------------------------------
# Dialoge
# ---------------------------------------------------------------------------

class FormDialog(Gtk.Dialog):
    """Basisklasse für einfache Abbrechen/OK-Eingabedialoge mit einem
    Gtk.Grid als Content-Bereich (self.grid). Bündelt die sonst in fast
    jedem Dialog wiederholte Boilerplate (Buttons, Grid-Aufbau,
    Innenabstände) – Unterklassen befüllen nur noch self.grid und lesen ihre
    Werte in einer eigenen save()/get_data()-Methode aus."""

    def __init__(self, parent, title):
        super().__init__(title=title, transient_for=parent, flags=0)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                          Gtk.STOCK_OK, Gtk.ResponseType.OK)
        area = self.get_content_area()
        area.set_spacing(8)
        area.set_border_width(10)
        self.grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        area.add(self.grid)

class TransactionDialog(FormDialog):
    """Dialog zum Hinzufügen ODER Bearbeiten einer Buchung.
    Wird `existing` übergeben (Zeile aus get_transaction), läuft der Dialog im
    Bearbeiten-Modus: Felder sind vorausgefüllt, die Option "wiederkehrend"
    ist ausgeblendet (bearbeitet wird immer nur die einzelne Buchung)."""

    def __init__(self, parent, store: FinanceStore, default_date, existing=None):
        title = "Buchung bearbeiten" if existing else "Buchung hinzufügen"
        super().__init__(parent, title)
        self.set_default_size(400, 320)
        self.store = store
        self.existing = existing
        grid = self.grid

        grid.attach(Gtk.Label(label="Art:", xalign=0), 0, 0, 1, 1)
        self.kind_combo = Gtk.ComboBoxText()
        self.kind_combo.append("ausgabe", "Ausgabe")
        self.kind_combo.append("einnahme", "Einnahme")
        default_kind = existing["kind"] if existing else "ausgabe"
        self.kind_combo.set_active_id(default_kind)
        self.kind_combo.connect("changed", lambda w: self._reload_categories())
        grid.attach(self.kind_combo, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Kategorie:", xalign=0), 0, 1, 1, 1)
        self.category_combo = Gtk.ComboBoxText()
        grid.attach(self.category_combo, 1, 1, 1, 1)
        self._reload_categories(preselect=existing["category_id"] if existing else None)

        grid.attach(Gtk.Label(label="Betrag (€):", xalign=0), 0, 2, 1, 1)
        initial_amount = abs(existing["amount"]) if existing else 0
        self.amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=initial_amount, lower=0, upper=1000000,
                                       step_increment=1, page_increment=10),
            numeric=True, digits=2,
        )
        grid.attach(self.amount_spin, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label="Datum (TT.MM.JJJJ):", xalign=0), 0, 3, 1, 1)
        if existing:
            initial_date = datetime.date.fromisoformat(existing["date"])
        else:
            initial_date = default_date
        self.date_entry = Gtk.Entry(text=initial_date.strftime("%d.%m.%Y"))
        grid.attach(self.date_entry, 1, 3, 1, 1)

        grid.attach(Gtk.Label(label="Beschreibung:", xalign=0), 0, 4, 1, 1)
        self.description_entry = Gtk.Entry(text=existing["description"] if existing else "")
        grid.attach(self.description_entry, 1, 4, 1, 1)

        if not existing:
            self.recurring_check = Gtk.CheckButton(label="Wiederkehrende Buchung")
            self.recurring_check.connect("toggled", self._on_recurring_toggled)
            grid.attach(self.recurring_check, 0, 5, 2, 1)

            self.frequency_combo = Gtk.ComboBoxText()
            self.frequency_combo.append("woechentlich", "Wöchentlich")
            self.frequency_combo.append("monatlich", "Monatlich")
            self.frequency_combo.append("jaehrlich", "Jährlich")
            self.frequency_combo.set_active_id("monatlich")
            self.frequency_combo.set_sensitive(False)
            grid.attach(self.frequency_combo, 0, 6, 2, 1)
        else:
            self.recurring_check = None
            if existing["recurring_template_id"] is not None:
                note = Gtk.Label(
                    xalign=0,
                    label="Diese Buchung stammt aus einer wiederkehrenden Vorlage. "
                          "Änderungen betreffen nur diese einzelne Buchung.",
                )
                note.set_line_wrap(True)
                grid.attach(note, 0, 5, 2, 1)

        self.show_all()

    def _reload_categories(self, preselect=None):
        kind = self.kind_combo.get_active_id()
        self.category_combo.remove_all()
        active_index = 0
        for i, cat in enumerate(self.store.list_categories(kind=kind)):
            self.category_combo.append(str(cat["id"]), f"{cat['icon']} {cat['name']}")
            if preselect and cat["id"] == preselect:
                active_index = i
        self.category_combo.set_active(active_index)

    def _on_recurring_toggled(self, widget):
        self.frequency_combo.set_sensitive(widget.get_active())

    def save(self):
        kind = self.kind_combo.get_active_id()
        category_id = int(self.category_combo.get_active_id())
        raw_amount = self.amount_spin.get_value()
        amount = raw_amount if kind == "einnahme" else -raw_amount
        description = self.description_entry.get_text().strip()

        try:
            date_obj = datetime.datetime.strptime(
                self.date_entry.get_text().strip(), "%d.%m.%Y"
            ).date()
        except ValueError:
            date_obj = datetime.date.today()

        if self.existing:
            self.store.update_transaction(
                self.existing["id"], date_obj.isoformat(), amount, category_id, description
            )
        elif self.recurring_check is not None and self.recurring_check.get_active():
            frequency = self.frequency_combo.get_active_id()
            self.store.add_recurring_template(
                category_id, amount, description, frequency, date_obj.isoformat()
            )
        else:
            self.store.add_transaction(
                date_obj.isoformat(), amount, category_id, description
            )


class RecurringTemplatesDialog(Gtk.Dialog):
    def __init__(self, parent, store: FinanceStore):
        super().__init__(title="Wiederkehrende Vorlagen", transient_for=parent, flags=0)
        self.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.set_default_size(650, 380)
        self.store = store

        area = self.get_content_area()
        area.set_border_width(10)

        info = Gtk.Label(
            xalign=0,
            label="Läuft eine Vorlage weiter, werden ihre Buchungen automatisch für "
                  "jeden Monat erzeugt, den du dir im Kalender ansiehst – unbegrenzt, "
                  "bis du sie hier löschst. Tipp: Doppelklick auf eine Vorlage öffnet "
                  "sie zum Bearbeiten.",
        )
        info.set_line_wrap(True)
        area.pack_start(info, False, False, 4)

        scroller = Gtk.ScrolledWindow()
        area.pack_start(scroller, True, True, 0)

        self.list_store = Gtk.ListStore(int, str, str, str, str, str)
        # id, kategorie, betrag, häufigkeit, start, ende
        self.tree_view = Gtk.TreeView(model=self.list_store)
        self.tree_view.connect("row-activated", self._on_edit)
        scroller.add(self.tree_view)

        for title, col_id in [("Kategorie", 1), ("Betrag", 2), ("Häufigkeit", 3),
                               ("Start", 4), ("Ende", 5)]:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=col_id)
            self.tree_view.append_column(column)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        area.pack_start(btn_box, False, False, 6)

        edit_btn = Gtk.Button(label="Bearbeiten")
        edit_btn.connect("clicked", self._on_edit)
        btn_box.pack_start(edit_btn, False, False, 0)

        del_btn = Gtk.Button(label="Löschen (inkl. künftiger Buchungen)")
        del_btn.connect("clicked", self._on_delete)
        btn_box.pack_start(del_btn, False, False, 0)

        self._refresh()
        self.show_all()

    def _refresh(self):
        self.list_store.clear()
        freq_names = {"woechentlich": "Wöchentlich", "monatlich": "Monatlich",
                      "jaehrlich": "Jährlich"}
        for t in self.store.list_recurring_templates():
            self.list_store.append([
                t["id"], f"{t['icon']} {t['category_name']}", fmt_amount(t["amount"]),
                freq_names.get(t["frequency"], t["frequency"]),
                t["start_date"], t["end_date"] or "läuft weiter",
            ])

    def _selected_template_id(self):
        selection = self.tree_view.get_selection()
        model, tree_iter = selection.get_selected()
        return model.get_value(tree_iter, 0) if tree_iter is not None else None

    def _on_edit(self, widget, *_args):
        # *_args fängt die zusätzlichen Argumente von "row-activated" ab
        # (path, column), die beim Klick über den Button nicht mitkommen.
        template_id = self._selected_template_id()
        if template_id is None:
            return
        template = self.store.get_recurring_template(template_id)
        dialog = RecurringTemplateEditDialog(self, self.store, template)
        if dialog.run() == Gtk.ResponseType.OK:
            dialog.save()
        dialog.destroy()
        self._refresh()

    def _on_delete(self, widget):
        template_id = self._selected_template_id()
        if template_id is None:
            return

        confirm = Gtk.MessageDialog(
            transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Wiederkehrende Vorlage löschen?",
            secondary_text="Zukünftige (heute oder später datierte) Buchungen dieser "
                            "Vorlage werden dabei immer entfernt.",
        )
        past_check = Gtk.CheckButton(
            label="Auch bereits vergangene Buchungen dieser Vorlage löschen"
        )
        content_area = confirm.get_content_area()
        content_area.pack_start(past_check, False, False, 6)
        content_area.show_all()

        response = confirm.run()
        delete_past = past_check.get_active()
        confirm.destroy()

        if response == Gtk.ResponseType.OK:
            self.store.delete_recurring_template(template_id, delete_past_transactions=delete_past)
            self._refresh()


class RecurringTemplateEditDialog(FormDialog):
    """Dialog zum Bearbeiten einer wiederkehrenden Vorlage. Änderungen wirken
    sich nur auf zukünftige Buchungen aus; bereits vergangene bleiben als
    historischer Stand unangetastet (siehe update_recurring_template in db.py)."""

    def __init__(self, parent, store: FinanceStore, template):
        super().__init__(parent, "Wiederkehrende Vorlage bearbeiten")
        self.store = store
        self.template = template
        grid = self.grid

        grid.attach(Gtk.Label(label="Art:", xalign=0), 0, 0, 1, 1)
        self.kind_combo = Gtk.ComboBoxText()
        self.kind_combo.append("ausgabe", "Ausgabe")
        self.kind_combo.append("einnahme", "Einnahme")
        self.kind_combo.set_active_id(template["kind"])
        self.kind_combo.connect("changed", lambda w: self._reload_categories())
        grid.attach(self.kind_combo, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Kategorie:", xalign=0), 0, 1, 1, 1)
        self.category_combo = Gtk.ComboBoxText()
        grid.attach(self.category_combo, 1, 1, 1, 1)
        self._reload_categories(preselect=template["category_id"])

        grid.attach(Gtk.Label(label="Betrag (€):", xalign=0), 0, 2, 1, 1)
        self.amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=abs(template["amount"]), lower=0, upper=1000000,
                                       step_increment=1, page_increment=10),
            numeric=True, digits=2,
        )
        grid.attach(self.amount_spin, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label="Beschreibung:", xalign=0), 0, 3, 1, 1)
        self.description_entry = Gtk.Entry(text=template["description"] or "")
        grid.attach(self.description_entry, 1, 3, 1, 1)

        grid.attach(Gtk.Label(label="Häufigkeit:", xalign=0), 0, 4, 1, 1)
        self.frequency_combo = Gtk.ComboBoxText()
        self.frequency_combo.append("woechentlich", "Wöchentlich")
        self.frequency_combo.append("monatlich", "Monatlich")
        self.frequency_combo.append("jaehrlich", "Jährlich")
        self.frequency_combo.set_active_id(template["frequency"])
        grid.attach(self.frequency_combo, 1, 4, 1, 1)

        grid.attach(Gtk.Label(label="Startdatum (TT.MM.JJJJ):", xalign=0), 0, 5, 1, 1)
        start_date = datetime.date.fromisoformat(template["start_date"])
        self.start_date_entry = Gtk.Entry(text=start_date.strftime("%d.%m.%Y"))
        grid.attach(self.start_date_entry, 1, 5, 1, 1)

        grid.attach(Gtk.Label(label="Enddatum (TT.MM.JJJJ, optional):", xalign=0), 0, 6, 1, 1)
        self.end_date_entry = Gtk.Entry()
        if template["end_date"]:
            end_date = datetime.date.fromisoformat(template["end_date"])
            self.end_date_entry.set_text(end_date.strftime("%d.%m.%Y"))
        self.end_date_entry.set_placeholder_text("leer = läuft unbegrenzt weiter")
        grid.attach(self.end_date_entry, 1, 6, 1, 1)

        note = Gtk.Label(
            xalign=0,
            label="Änderungen wirken standardmäßig nur auf zukünftige Buchungen "
                  "(ab heute) – bereits vergangene bleiben als historischer "
                  "Stand unverändert (z. B. sinnvoll bei einer "
                  "Gehaltserhöhung: alte Monate zeigen weiterhin den alten "
                  "Betrag).",
        )
        note.set_line_wrap(True)
        grid.attach(note, 0, 7, 2, 1)

        self.apply_to_past_check = Gtk.CheckButton(
            label="Änderungen auch auf bereits vergangene Buchungen anwenden "
                  "(überschreibt deren bisherige Werte rückwirkend)"
        )
        grid.attach(self.apply_to_past_check, 0, 8, 2, 1)

        self.show_all()

    def _reload_categories(self, preselect=None):
        kind = self.kind_combo.get_active_id()
        self.category_combo.remove_all()
        active_index = 0
        for i, cat in enumerate(self.store.list_categories(kind=kind)):
            self.category_combo.append(str(cat["id"]), f"{cat['icon']} {cat['name']}")
            if preselect and cat["id"] == preselect:
                active_index = i
        self.category_combo.set_active(active_index)

    def save(self):
        kind = self.kind_combo.get_active_id()
        category_id = int(self.category_combo.get_active_id())
        raw_amount = self.amount_spin.get_value()
        amount = raw_amount if kind == "einnahme" else -raw_amount
        description = self.description_entry.get_text().strip()
        frequency = self.frequency_combo.get_active_id()

        try:
            start_date = datetime.datetime.strptime(
                self.start_date_entry.get_text().strip(), "%d.%m.%Y"
            ).date()
        except ValueError:
            start_date = datetime.date.fromisoformat(self.template["start_date"])

        end_text = self.end_date_entry.get_text().strip()
        end_date = None
        if end_text:
            try:
                end_date = datetime.datetime.strptime(end_text, "%d.%m.%Y").date().isoformat()
            except ValueError:
                end_date = None

        self.store.update_recurring_template(
            self.template["id"], category_id, amount, description, frequency,
            start_date.isoformat(), end_date,
            apply_to_past=self.apply_to_past_check.get_active(),
        )


class BudgetDialog(FormDialog):
    def __init__(self, parent, store: FinanceStore, month, preselect_category_id=None):
        super().__init__(parent, "Budget setzen")
        self.store = store
        self.month = month
        grid = self.grid

        grid.attach(Gtk.Label(label="Kategorie:", xalign=0), 0, 0, 1, 1)
        self.category_combo = Gtk.ComboBoxText()
        active_index = 0
        for i, cat in enumerate(store.list_categories(kind="ausgabe")):
            self.category_combo.append(str(cat["id"]), f"{cat['icon']} {cat['name']}")
            if preselect_category_id and cat["id"] == preselect_category_id:
                active_index = i
        self.category_combo.set_active(active_index)
        grid.attach(self.category_combo, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label=f"Monatsbudget für {month_label(month)} (€):",
                               xalign=0), 0, 1, 1, 1)
        self.amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=1000000,
                                       step_increment=10, page_increment=50),
            numeric=True, digits=2,
        )
        grid.attach(self.amount_spin, 1, 1, 1, 1)

        self.show_all()

    def save(self):
        category_id = int(self.category_combo.get_active_id())
        amount = self.amount_spin.get_value()
        self.store.set_budget(category_id, self.month.strftime("%Y-%m"), amount)


class GoalDialog(FormDialog):
    def __init__(self, parent):
        super().__init__(parent, "Sparziel hinzufügen")
        grid = self.grid

        grid.attach(Gtk.Label(label="Name:", xalign=0), 0, 0, 1, 1)
        self.name_entry = Gtk.Entry()
        grid.attach(self.name_entry, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Zielbetrag (€):", xalign=0), 0, 1, 1, 1)
        self.amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=1000, lower=1, upper=10000000,
                                       step_increment=50, page_increment=500),
            numeric=True, digits=2,
        )
        grid.attach(self.amount_spin, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Zieldatum (TT.MM.JJJJ, optional):", xalign=0), 0, 2, 1, 1)
        self.date_entry = Gtk.Entry()
        self.date_entry.set_placeholder_text("z. B. 31.12.2027")
        grid.attach(self.date_entry, 1, 2, 1, 1)

        self.show_all()

    def get_data(self):
        name = self.name_entry.get_text().strip()
        if not name:
            return None
        target_amount = self.amount_spin.get_value()
        date_text = self.date_entry.get_text().strip()
        target_date = None
        if date_text:
            try:
                target_date = datetime.datetime.strptime(date_text, "%d.%m.%Y").date().isoformat()
            except ValueError:
                target_date = None
        return {"name": name, "target_amount": target_amount, "target_date": target_date}


class ContributionDialog(FormDialog):
    def __init__(self, parent, goal_name):
        super().__init__(parent, f"Einzahlen: {goal_name}")
        grid = self.grid

        grid.attach(Gtk.Label(label="Einzuzahlender Betrag (€):", xalign=0), 0, 0, 1, 1)
        self.amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=50, lower=0.01, upper=1000000,
                                       step_increment=10, page_increment=50),
            numeric=True, digits=2,
        )
        grid.attach(self.amount_spin, 1, 0, 1, 1)

        self.book_check = Gtk.CheckButton(
            label="Als Buchung im Haushaltsbuch verbuchen (Kategorie „Sparbeitrag“)"
        )
        self.book_check.set_active(True)
        grid.attach(self.book_check, 0, 1, 2, 1)

        hint = Gtk.Label(
            xalign=0,
            label="Damit taucht die Einzahlung als Ausgabe im Kalender, in Budgets "
                  "und Auswertungen auf – so wie das Geld tatsächlich vom Konto "
                  "abgeht. Zum rein informativen Vormerken (z. B. externes Depot) "
                  "kannst du das Häkchen entfernen.",
        )
        hint.set_line_wrap(True)
        grid.attach(hint, 0, 2, 2, 1)

        self.show_all()

    def get_book_as_transaction(self):
        return self.book_check.get_active()

    def get_amount(self):
        return self.amount_spin.get_value()


class CategoryManagerDialog(Gtk.Dialog):
    def __init__(self, parent, store: FinanceStore):
        super().__init__(title="Kategorien verwalten", transient_for=parent, flags=0)
        self.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.set_default_size(480, 400)
        self.store = store

        area = self.get_content_area()
        area.set_border_width(10)

        scroller = Gtk.ScrolledWindow()
        area.pack_start(scroller, True, True, 0)

        self.list_store = Gtk.ListStore(int, str, str, str)  # id, icon, name, art
        self.tree_view = Gtk.TreeView(model=self.list_store)
        scroller.add(self.tree_view)

        icon_renderer = Gtk.CellRendererText()
        self.tree_view.append_column(Gtk.TreeViewColumn("Icon", icon_renderer, text=1))
        name_renderer = Gtk.CellRendererText()
        self.tree_view.append_column(Gtk.TreeViewColumn("Name", name_renderer, text=2))
        kind_renderer = Gtk.CellRendererText()
        self.tree_view.append_column(Gtk.TreeViewColumn("Art", kind_renderer, text=3))

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        area.pack_start(btn_box, False, False, 6)

        add_btn = Gtk.Button(label="Hinzufügen")
        add_btn.connect("clicked", self._on_add)
        btn_box.pack_start(add_btn, False, False, 0)

        edit_btn = Gtk.Button(label="Bearbeiten")
        edit_btn.connect("clicked", self._on_edit)
        btn_box.pack_start(edit_btn, False, False, 0)

        del_btn = Gtk.Button(label="Löschen")
        del_btn.connect("clicked", self._on_delete)
        btn_box.pack_start(del_btn, False, False, 0)

        self._refresh()
        self.show_all()

    def _refresh(self):
        self.list_store.clear()
        for c in self.store.list_categories():
            self.list_store.append([
                c["id"], c["icon"], c["name"],
                "Einnahme" if c["kind"] == "einnahme" else "Ausgabe",
            ])

    def _on_add(self, widget):
        dialog = CategoryEditDialog(self)
        if dialog.run() == Gtk.ResponseType.OK:
            data = dialog.get_data()
            if data:
                self.store.add_category(data["name"], data["kind"], data["icon"])
        dialog.destroy()
        self._refresh()

    def _on_edit(self, widget):
        selection = self.tree_view.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            return
        category_id = model.get_value(tree_iter, 0)
        current_icon = model.get_value(tree_iter, 1)
        current_name = model.get_value(tree_iter, 2)

        dialog = CategoryEditDialog(self, name=current_name, icon=current_icon, edit_mode=True)
        if dialog.run() == Gtk.ResponseType.OK:
            data = dialog.get_data()
            if data:
                self.store.update_category(category_id, data["name"], data["icon"])
        dialog.destroy()
        self._refresh()

    def _on_delete(self, widget):
        selection = self.tree_view.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            return
        category_id = model.get_value(tree_iter, 0)
        name = model.get_value(tree_iter, 2)

        response = _run_message_dialog(
            self, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK_CANCEL,
            f'Kategorie "{name}" wirklich löschen?',
            "Achtung: Dabei werden auch ALLE Buchungen und wiederkehrenden "
            "Vorlagen dieser Kategorie unwiderruflich gelöscht.",
        )
        if response == Gtk.ResponseType.OK:
            self.store.delete_category(category_id)
            self._refresh()


class CategoryEditDialog(FormDialog):
    def __init__(self, parent, name="", icon="", edit_mode=False):
        title = "Kategorie bearbeiten" if edit_mode else "Kategorie hinzufügen"
        super().__init__(parent, title)
        self.set_default_size(380, 420)
        self.edit_mode = edit_mode
        grid = self.grid

        grid.attach(Gtk.Label(label="Icon:", xalign=0), 0, 0, 1, 1)
        icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.icon_entry = Gtk.Entry(text=icon or "💶")
        self.icon_entry.set_max_length(4)
        self.icon_entry.set_width_chars(4)
        icon_box.pack_start(self.icon_entry, False, False, 0)
        icon_box.pack_start(Gtk.Label(label="aktuell ausgewählt", xalign=0), False, False, 0)
        grid.attach(icon_box, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Icon auswählen:", xalign=0), 0, 1, 1, 1)
        picker_scroller = Gtk.ScrolledWindow()
        picker_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        picker_scroller.set_min_content_height(140)
        picker_scroller.set_max_content_height(140)
        grid.attach(picker_scroller, 0, 2, 2, 1)

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(8)
        flow.set_min_children_per_line(6)
        flow.set_row_spacing(4)
        flow.set_column_spacing(4)
        picker_scroller.add(flow)

        for emoji in ICON_PICKER_CHOICES:
            btn = Gtk.Button(label=emoji)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.connect("clicked", self._on_icon_picked, emoji)
            flow.add(btn)

        hint = Gtk.Label(xalign=0, label="Eigenes Emoji eintippen geht auch – z. B. über die "
                                          "Emoji-Tastatur mit Strg+.")
        hint.set_line_wrap(True)
        grid.attach(hint, 0, 3, 2, 1)

        grid.attach(Gtk.Label(label="Name:", xalign=0), 0, 4, 1, 1)
        self.name_entry = Gtk.Entry(text=name)
        grid.attach(self.name_entry, 1, 4, 1, 1)

        if not edit_mode:
            grid.attach(Gtk.Label(label="Art:", xalign=0), 0, 5, 1, 1)
            self.kind_combo = Gtk.ComboBoxText()
            self.kind_combo.append("ausgabe", "Ausgabe")
            self.kind_combo.append("einnahme", "Einnahme")
            self.kind_combo.set_active_id("ausgabe")
            grid.attach(self.kind_combo, 1, 5, 1, 1)
        else:
            self.kind_combo = None

        self.show_all()

    def _on_icon_picked(self, button, emoji):
        self.icon_entry.set_text(emoji)

    def get_data(self):
        name = self.name_entry.get_text().strip()
        icon = self.icon_entry.get_text().strip() or "💶"
        if not name:
            return None
        data = {"name": name, "icon": icon}
        if self.kind_combo is not None:
            data["kind"] = self.kind_combo.get_active_id()
        return data


def main():
    win = MainWindow()
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
