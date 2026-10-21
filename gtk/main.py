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
import re
import math

from db import FinanceStore, add_months
from i18n import tr, set_language, get_language, LANGUAGES, months, months_short, weekdays, weekdays_short

CURRENCY = "€"

CATEGORY_COLORS = [
    (0.20, 0.47, 0.75), (0.85, 0.37, 0.13), (0.17, 0.63, 0.34),
    (0.58, 0.20, 0.75), (0.90, 0.62, 0.00), (0.13, 0.59, 0.66),
    (0.75, 0.18, 0.36), (0.40, 0.40, 0.40), (0.35, 0.70, 0.90),
    (0.95, 0.80, 0.20),
]



def _localize_import_error(line):
    """Fehlertexte aus db.py sind deutsch; hier passend zur Sprache ausgeben."""
    m = re.match(r"^Zeile (\d+): Datum oder Betrag nicht lesbar, übersprungen\.$", line)
    if m:
        return tr("Zeile {0}: Datum oder Betrag nicht lesbar, übersprungen.").format(m.group(1))
    return line


def fmt_amount(value):
    return f"{value:,.2f} {CURRENCY}".replace(",", "X").replace(".", ",").replace("X", ".")


def color_for_index(i):
    return CATEGORY_COLORS[i % len(CATEGORY_COLORS)]



# Vorausgewählte Icons für den Klick-Picker in der Kategorienverwaltung.
ICON_PICKER_CHOICES = [
    "💶", "💼", "🏠", "🛒", "🍔", "☕", "🚌", "🚗", "⛽", "✈️",
    "🎉", "🎬", "🎮", "📱", "💻", "👕", "💊", "🏥", "🛡️", "📚",
    "🎓", "🐶", "🐱", "🎸", "⚽", "🏋️", "🎁", "💰", "📦", "➕",
]




def format_delta(row):
    """Text für die Veränderung einer Kategorie, z. B. '+34,20 € (+12 %)'."""
    if row["previous"] <= 0 and row["current"] > 0:
        return tr('+{0} (neu)').format(fmt_amount(row['diff']))
    if row["current"] <= 0 and row["previous"] > 0:
        return f"−{fmt_amount(-row['diff'])} (−100 %)"
    sign = "+" if row["diff"] > 0 else ("−" if row["diff"] < 0 else "±")
    pct = f"{abs(row['pct']):.0f} %" if row["pct"] is not None else "–"
    return f"{sign}{fmt_amount(abs(row['diff']))} ({sign}{pct})"


def month_label(date_obj):
    return f"{months()[date_obj.month - 1]} {date_obj.year}"


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
        set_language(self.store.get_setting("language", "de"))
        self.set_title(tr("Plutos – Das Haushaltsbuch"))
        self.store.ensure_horizon(datetime.date.today())
        try:  # tägliches automatisches Datenbank-Backup; darf den Start nie verhindern
            self.store.create_db_backup()
        except Exception as exc:
            print(f"Automatisches Backup fehlgeschlagen: {exc}")

        self.selected_day = datetime.date.today()
        self.stats_month = datetime.date.today().replace(day=1)
        self.trend_months = 6
        self.current_etf_plan_id = None

        notebook = Gtk.Notebook()
        self.add(notebook)
        self.notebook = notebook

        notebook.append_page(self._build_transactions_tab(), Gtk.Label(label=tr('Buchungen')))
        notebook.append_page(self._build_budgets_tab(), Gtk.Label(label=tr('Budgets')))
        notebook.append_page(self._build_goals_tab(), Gtk.Label(label=tr('Sparziele')))
        notebook.append_page(self._build_planning_tab(), Gtk.Label(label=tr('Finanzplanung')))
        self.etf_tab_page = self._build_etf_tab()
        notebook.append_page(self.etf_tab_page, Gtk.Label(label=tr('ETF-Sparplan')))
        notebook.append_page(self._build_stats_tab(), Gtk.Label(label=tr('Auswertungen')))
        notebook.append_page(self._build_search_tab(), Gtk.Label(label=tr('Suche')))
        notebook.append_page(self._build_export_tab(), Gtk.Label(label=tr('Export / Import')))

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
            tr('<b>{0}</b>').format(month_label(self.month_display_date))
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
                tr('<span foreground="#777777">{0:02d}</span>').format(kw)
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
                    tr('{0}\nEinnahmen: {1}\nAusgaben: {2}\nSaldo: {3}').format(d.strftime('%d.%m.%Y'), fmt_amount(income), fmt_amount(expense), fmt_amount(saldo))
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
            tr('Monatsansicht')
        )

        self.view_switcher_combo.append(
            "woche",
            tr('Wochenansicht')
        )

        self.view_switcher_combo.append(
            "jahr",
            tr('Jahresansicht')
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
            tr('<b>Monat</b>')
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
            label=tr('Heute')
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
            label=tr('KW')
        )

        kw_header.set_markup(
            tr('<span foreground="#777777"><b>KW</b></span>')
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

        weekday_names = weekdays_short()

        for col, name in enumerate(
            weekday_names,
            start=1
        ):

            label = Gtk.Label()

            label.set_markup(
                tr('<b>{0}</b>').format(name)
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
            tr('<b>Fett</b> = Buchung(en)\n<b>Klick</b> = Tagesbuchungen anzeigen\n<b>Doppelklick / Enter</b> = Neue Buchung')
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
            label=tr('Kategorien verwalten')
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
            tr('Kategorie'),
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
            tr('Art'),
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
            tr('Betrag'),
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
            tr('Beschreibung'),
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
            tr('Wiederk.'),
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
                tr('Tipp: Doppelklick auf eine Buchung öffnet sie zum Bearbeiten.')
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
            label=tr('Buchung hinzufügen')
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
            label=tr('Bearbeiten')
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
            label=tr('Löschen')
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
            label=tr('Wiederkehrende Vorlagen verwalten')
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

        # ------------------------------------------------
        # Zweite Reihe: Rückgängig, Vorlagen
        # ------------------------------------------------

        btn_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        right_box.pack_start(btn_box2, False, False, 0)

        self.undo_btn = Gtk.Button(label=tr('Rückgängig'))
        self.undo_btn.set_tooltip_text(tr('Zuletzt gelöschte Buchung wiederherstellen (Strg+Z)'))
        self.undo_btn.set_sensitive(False)
        self.undo_btn.connect("clicked", self._on_undo_delete)
        btn_box2.pack_start(self.undo_btn, False, False, 0)

        save_tpl_btn = Gtk.Button(label=tr('Als Vorlage speichern'))
        save_tpl_btn.set_tooltip_text(tr('Die markierte Buchung als Schnellbuchungs-Vorlage merken'))
        save_tpl_btn.connect("clicked", self._on_save_quick_template)
        btn_box2.pack_start(save_tpl_btn, False, False, 0)

        use_tpl_btn = Gtk.Button(label=tr('Aus Vorlage buchen…'))
        use_tpl_btn.connect("clicked", self._on_book_from_template)
        btn_box2.pack_start(use_tpl_btn, False, False, 0)

        self.connect("key-press-event", self._on_window_key_press)

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
            label=tr('Diese Woche')
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
            tr('<b>Klick auf einen Tag</b> = Buchungen des Tages rechts anzeigen.\nMonatsübersicht und Budgets folgen automatisch der angezeigten Woche.')
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

        weekday_names = weekdays_short()

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
                tr('<b>{0}{1}</b>\n{2}.{3}.\n<span foreground="{4}">{5}</span>').format(weekday_names[i], today_marker, d.day, d.month, color, saldo_text)
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
            tr('<b>Klick auf einen Monat</b> = wechselt in die Monatsansicht.')
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

            name = months()[i][:3]

            lbl.set_markup(
                tr('<b>{0}</b>\n<span foreground="{1}">{2}</span>').format(name, color, text)
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
            tr('<b>{0}</b>\nEinnahmen: {1}\nAusgaben: {2}\nSaldo: {3}{4}').format(month_label(month_start), fmt_amount(income), fmt_amount(expense), sign, fmt_amount(saldo))
        )


    def _refresh_day_list(self):

        weekday_names = weekdays()

        d = self.selected_day

        self.day_title_label.set_markup(
            tr('<b>{0}, {1}</b>').format(weekday_names[d.weekday()], d.strftime('%d.%m.%Y'))
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
                    tr('Keine Buchungen an diesem Tag.'),
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
                            tr('Einnahme')
                            if r["kind"] == "einnahme"
                            else tr('Ausgabe')
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

        saved = None
        if dialog.run() == Gtk.ResponseType.OK:
            dialog.save()
            saved = dialog.last_saved

        dialog.destroy()

        self._after_transactions_changed()
        self._warn_if_budget_crossed(saved, is_new=True)


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

        saved = None
        if dialog.run() == Gtk.ResponseType.OK:
            dialog.save()
            saved = dialog.last_saved

        dialog.destroy()

        self._after_transactions_changed()
        self._warn_if_budget_crossed(saved, is_new=False)


    def _on_delete_transaction(
        self,
        widget
    ):

        tx_id = self._selected_transaction_id()

        if tx_id is not None:

            self.store.delete_transaction(
                tx_id
            )

            self.undo_btn.set_sensitive(True)
            self._after_transactions_changed()

    def _on_undo_delete(self, widget=None):
        if not self.store.can_undo_delete():
            return
        restored = self.store.undo_delete_transaction()
        self.undo_btn.set_sensitive(False)
        if restored:
            self.store.ensure_horizon(datetime.date.fromisoformat(restored["date"]))
            self._after_transactions_changed()
            self._refresh_stats()

    def _on_window_key_press(self, widget, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if ctrl and event.keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            # Nicht stören, wenn gerade in einem Textfeld getippt wird.
            focus = self.get_focus()
            if not isinstance(focus, (Gtk.Entry, Gtk.TextView)):
                self._on_undo_delete()
                return True
        return False

    def _on_save_quick_template(self, widget):
        tx_id = self._selected_transaction_id()
        if tx_id is None:
            _run_message_dialog(self, Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
                                tr('Bitte zuerst in der Liste eine Buchung markieren.'))
            return
        tx = self.store.get_transaction(tx_id)
        dialog = Gtk.Dialog(title=tr('Als Vorlage speichern'), transient_for=self, flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                           Gtk.STOCK_OK, Gtk.ResponseType.OK)
        area = dialog.get_content_area()
        area.set_spacing(8)
        area.set_border_width(10)
        area.add(Gtk.Label(label=tr('Name der Vorlage:'), xalign=0))
        entry = Gtk.Entry()
        entry.set_text(tx["description"] or tr("Vorlage"))
        entry.set_activates_default(True)
        area.add(entry)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK and entry.get_text().strip():
            self.store.add_quick_template(entry.get_text(), tx["category_id"], tx["amount"],
                                          tx["description"])
        dialog.destroy()

    def _on_book_from_template(self, widget):
        dialog = QuickTemplatesDialog(self, self.store, self.selected_day)
        dialog.run()
        booked = dialog.booked
        dialog.destroy()
        if booked:
            self._after_transactions_changed()
            self._refresh_stats()
            for saved in booked:
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
        if after == before or after not in ("warn", "over"):
            return
        category = next((c for c in self.store.list_categories()
                         if c["id"] == saved["category_id"]), None)
        name = category["name"] if category else tr('Kategorie')
        percent = status["spent"] / status["limit"] * 100
        text = (tr('Budget „{0}“ ({1}/{2}): {3} von {4} ({5:.0f} %).').format(name, month[5:], month[:4], fmt_amount(status['spent']), fmt_amount(status['limit']), percent))
        if after == "over":
            _run_message_dialog(
                self, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK,
                tr('Budget überschritten'),
                text + tr('\nDas Budget ist um {0} überschritten.').format(fmt_amount(status['spent'] - status['limit'])))
        else:
            _run_message_dialog(self, Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
                                tr('Budget fast aufgebraucht'),
                                text + tr("\nDie 80-%-Marke ist erreicht."))


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
        self._reload_search_categories()
        self._run_search()

        self._refresh_day_list()


    def _after_transactions_changed(self):

        self._refresh_custom_calendar()
        self._refresh_day_list()
        self._refresh_month_balance()
        self._refresh_budgets_tab()
        self._refresh_week_view()
        self._refresh_year_view()
        self._refresh_current_balance_display()
        self._run_search()

    # =====================================================================
    # Tab 2: Budgets
    # =====================================================================

    def _build_budgets_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(10)

        info = Gtk.Label(label=tr('Budgets gelten für den im Buchungen-Tab im Kalender sichtbaren Monat.'), xalign=0)
        box.pack_start(info, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        box.pack_start(scroller, True, True, 0)

        # category_id, name(icon+name), limit_text, spent_text, remaining_text, fraction
        # + Textfarbe, Farbe-aktiv, Fortschrittstext
        self.budget_store = Gtk.ListStore(int, str, str, str, str, int, str, bool, str)
        self.budget_view = Gtk.TreeView(model=self.budget_store)
        scroller.add(self.budget_view)

        for title, col_id in [(tr('Kategorie'), 1), ("Budget", 2), ("Ausgegeben", 3),
                               ("Verbleibend", 4)]:
            renderer = Gtk.CellRendererText()
            if col_id in (3, 4):  # Warnfarbe bei ≥ 80 % bzw. ≥ 100 %
                column = Gtk.TreeViewColumn(tr(title), renderer, text=col_id,
                                            foreground=6, foreground_set=7)
            else:
                column = Gtk.TreeViewColumn(tr(title), renderer, text=col_id)
            self.budget_view.append_column(column)

        progress_renderer = Gtk.CellRendererProgress()
        progress_col = Gtk.TreeViewColumn(tr('Fortschritt'), progress_renderer, value=5, text=8)
        progress_col.set_expand(True)
        self.budget_view.append_column(progress_col)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_start(btn_box, False, False, 0)

        set_btn = Gtk.Button(label=tr('Budget setzen/ändern'))
        set_btn.connect("clicked", self._on_set_budget)
        btn_box.pack_start(set_btn, False, False, 0)

        refresh_btn = Gtk.Button(label=tr('Aktualisieren'))
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
                    r["category_id"], label, tr('— kein Budget —'),
                    fmt_amount(spent), "–", 0, "", False, "0 %",
                ])
            else:
                remaining = limit_amount - spent
                fraction = int(min(100, max(0, (spent / limit_amount) * 100))) if limit_amount else 0
                level = self.store.budget_level(spent, limit_amount)
                color = {"warn": "#e0a030", "over": "#e05245"}.get(level, "")
                percent = spent / limit_amount * 100 if limit_amount else 0
                marker = {"warn": "⚠ ", "over": "⛔ "}.get(level, "")
                self.budget_store.append([
                    r["category_id"], label, fmt_amount(limit_amount),
                    fmt_amount(spent), fmt_amount(remaining), fraction,
                    color or "#000000", bool(color), f"{marker}{percent:.0f} %",
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
            label=tr('Die Reihenfolge hier legt fest, in welcher Priorität die Finanzplanung-Empfehlung Startkapital/Sparbetrag auf die Ziele verteilt (oben = zuerst befüllt). Mit „Nach oben“/„Nach unten“ frei sortierbar.'),
        )
        info.set_line_wrap(True)
        box.pack_start(info, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        box.pack_start(scroller, True, True, 0)

        # id, name, zielbetrag, angespart, zieldatum, fortschritt(0-100)
        self.goal_store = Gtk.ListStore(int, str, str, str, str, int)
        self.goal_view = Gtk.TreeView(model=self.goal_store)
        scroller.add(self.goal_view)

        for title, col_id in [(tr('Priorität / Ziel'), 1), ("Zielbetrag", 2), ("Angespart", 3),
                               ("Zieldatum", 4)]:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(tr(title), renderer, text=col_id)
            self.goal_view.append_column(column)

        progress_renderer = Gtk.CellRendererProgress()
        progress_col = Gtk.TreeViewColumn(tr('Fortschritt'), progress_renderer, value=5)
        progress_col.set_expand(True)
        self.goal_view.append_column(progress_col)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_start(btn_box, False, False, 0)

        add_btn = Gtk.Button(label=tr('Ziel hinzufügen'))
        add_btn.connect("clicked", self._on_add_goal)
        btn_box.pack_start(add_btn, False, False, 0)

        contrib_btn = Gtk.Button(label=tr('Einzahlen'))
        contrib_btn.connect("clicked", self._on_add_contribution)
        btn_box.pack_start(contrib_btn, False, False, 0)

        del_btn = Gtk.Button(label=tr('Ziel löschen'))
        del_btn.connect("clicked", self._on_delete_goal)
        btn_box.pack_start(del_btn, False, False, 0)

        up_btn = Gtk.Button(label=tr('▲ Nach oben'))
        up_btn.connect("clicked", self._on_move_goal_priority, -1)
        btn_box.pack_start(up_btn, False, False, 0)

        down_btn = Gtk.Button(label=tr('▼ Nach unten'))
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
        balance_frame = Gtk.Frame(label=tr('Kontostand'))
        box.pack_start(balance_frame, False, False, 0)
        balance_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        balance_grid.set_border_width(8)
        balance_frame.add(balance_grid)

        balance_grid.attach(Gtk.Label(label=tr('Stichtag (TT.MM.JJJJ):'), xalign=0), 0, 0, 1, 1)
        existing_amount, existing_date = self.store.get_starting_balance()
        default_date = (datetime.date.fromisoformat(existing_date) if existing_date
                         else datetime.date.today())
        self.balance_date_entry = Gtk.Entry(text=default_date.strftime("%d.%m.%Y"))
        balance_grid.attach(self.balance_date_entry, 1, 0, 1, 1)

        balance_grid.attach(Gtk.Label(label=tr('Kontostand an diesem Tag (€):'), xalign=0), 0, 1, 1, 1)
        self.balance_amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=existing_amount or 0, lower=-1000000, upper=10000000,
                                       step_increment=10, page_increment=100),
            numeric=True, digits=2,
        )
        balance_grid.attach(self.balance_amount_spin, 1, 1, 1, 1)
        balance_grid.attach(_help_button(
            tr('Dein tatsächliches Kontoguthaben an einem bestimmten Tag (z. B. heute) – nicht nur die in Plutos erfassten Buchungen. Der aktuelle Kontostand wird daraus als Startguthaben + alle Buchungen ab diesem Stichtag berechnet, du musst also nicht jede einzelne Buchung seit Kontoeröffnung nacherfassen.')
        ), 2, 1, 1, 1)

        save_balance_btn = Gtk.Button(label=tr('Speichern'))
        save_balance_btn.connect("clicked", self._on_save_starting_balance)
        balance_grid.attach(save_balance_btn, 0, 2, 2, 1)

        self.current_balance_label = Gtk.Label(xalign=0)
        self.current_balance_label.set_line_wrap(True)
        balance_grid.attach(self.current_balance_label, 0, 3, 3, 1)

        self.pocket_check = Gtk.CheckButton(
            label=tr('Notgroschen als eigenes Unterkonto führen (z. B. Tagesgeld)'))
        self.pocket_check.set_active(self.store.notgroschen_pocket_enabled())
        self.pocket_check.connect("toggled", self._on_toggle_pocket)
        balance_grid.attach(self.pocket_check, 0, 5, 3, 1)

        apply_balance_btn = Gtk.Button(
            label=tr('Aktuellen Kontostand als Startkapital in der Empfehlung übernehmen'))
        apply_balance_btn.connect("clicked", self._on_apply_balance_to_recommendation)
        balance_grid.attach(apply_balance_btn, 0, 4, 3, 1)

        balance_hint = Gtk.Label(
            xalign=0,
            label=tr('Praktisch, wenn du gerade erst anfängst, für etwas zu sparen, einen Notgroschen aufzubauen oder in ETFs zu investieren: so zählt dein tatsächlich vorhandenes Geld, nicht nur das, was du seit Nutzung von Plutos gebucht hast.'),
        )
        balance_hint.set_line_wrap(True)
        balance_grid.attach(balance_hint, 0, 6, 3, 1)

        # -- Abschnitt A: Notgroschen einrichten --
        ng_frame = Gtk.Frame(label=tr('Notgroschen einrichten (3–6 Monate Fixkosten)'))
        box.pack_start(ng_frame, False, False, 0)
        ng_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        ng_grid.set_border_width(8)
        ng_frame.add(ng_grid)

        ng_grid.attach(Gtk.Label(label=tr('Monatliche Fixkosten (€):'), xalign=0), 0, 0, 1, 1)
        self.planning_fixed_costs_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=self.store.estimate_monthly_fixed_costs(),
                                       lower=0, upper=100000, step_increment=10,
                                       page_increment=100),
            numeric=True, digits=2,
        )
        self.planning_fixed_costs_spin.connect("value-changed",
                                                lambda w: self._update_notgroschen_preview())
        ng_grid.attach(self.planning_fixed_costs_spin, 1, 0, 1, 1)

        recalc_btn = Gtk.Button(label=tr('Aus wiederkehrenden Ausgaben schätzen'))
        recalc_btn.connect("clicked", self._on_recalc_fixed_costs)
        ng_grid.attach(recalc_btn, 2, 0, 1, 1)

        ng_grid.attach(Gtk.Label(label=tr('Ziel: Monate an Fixkosten:'), xalign=0), 0, 1, 1, 1)
        self.planning_months_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=4, lower=1, upper=12,
                                       step_increment=1, page_increment=1),
            numeric=True,
        )
        self.planning_months_spin.connect("value-changed",
                                           lambda w: self._update_notgroschen_preview())
        ng_grid.attach(self.planning_months_spin, 1, 1, 1, 1)
        ng_grid.attach(_help_button(
            tr('Wie viele Monate an Fixkosten der Notgroschen abdecken soll – eine Reserve für unerwartete Ausgaben oder Einkommensausfälle (z. B. Jobverlust, Reparaturen). 3 Monate gelten als absolutes Minimum, 6 Monate als komfortabel; bei unsicherem Einkommen (Selbstständigkeit) eher mehr.')
        ), 2, 1, 1, 1)

        fixed_hint = Gtk.Label(
            xalign=0,
            label=tr('Vorbelegt aus deinen laufenden wiederkehrenden Ausgaben-Vorlagen (Miete, Versicherungen, …). Frei anpassbar, falls nicht alle Fixkosten als wiederkehrende Buchung erfasst sind. Üblich sind 3–6 Monate: eher 3 bei sicherem Einkommen (z. B. Beamte), eher 6 bei unsicherem Einkommen (z. B. Selbstständigkeit).'),
        )
        fixed_hint.set_line_wrap(True)
        ng_grid.attach(fixed_hint, 0, 2, 3, 1)

        self.notgroschen_preview_label = Gtk.Label(xalign=0)
        self.notgroschen_preview_label.set_line_wrap(True)
        ng_grid.attach(self.notgroschen_preview_label, 0, 3, 3, 1)

        ng_create_btn = Gtk.Button(label=tr('Notgroschen-Ziel anlegen/aktualisieren'))
        ng_create_btn.connect("clicked", self._on_create_or_update_notgroschen)
        ng_grid.attach(ng_create_btn, 0, 4, 3, 1)

        # -- Abschnitt B: Anlage-Empfehlung --
        rec_frame = Gtk.Frame(label=tr('Anlage-Empfehlung (einfache Faustregel)'))
        box.pack_start(rec_frame, False, False, 0)
        rec_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        rec_grid.set_border_width(8)
        rec_frame.add(rec_grid)

        rec_grid.attach(Gtk.Label(label=tr('Netto-Einkommen (monatlich, €):'), xalign=0), 0, 0, 1, 1)
        self.planning_income_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=2500, lower=0, upper=1000000,
                                       step_increment=50, page_increment=200),
            numeric=True, digits=2,
        )
        rec_grid.attach(self.planning_income_spin, 1, 0, 1, 1)

        rec_grid.attach(Gtk.Label(label=tr('Startkapital (€):'), xalign=0), 0, 1, 1, 1)
        self.planning_capital_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=10000000,
                                       step_increment=100, page_increment=1000),
            numeric=True, digits=2,
        )
        rec_grid.attach(self.planning_capital_spin, 1, 1, 1, 1)

        rec_grid.attach(Gtk.Label(label=tr('Freizeit-/Pufferbudget (% vom Netto):'), xalign=0),
                         0, 2, 1, 1)
        self.planning_leisure_percent_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=10, lower=0, upper=50,
                                       step_increment=1, page_increment=5),
            numeric=True, digits=1,
        )
        rec_grid.attach(self.planning_leisure_percent_spin, 1, 2, 1, 1)
        rec_grid.attach(_help_button(
            tr('Anteil des Netto-Einkommens, der für Freizeit, Hobbys oder als spontaner finanzieller Puffer reserviert bleibt, statt komplett auf Notgroschen/Sparziele/ETF verteilt zu werden. Rein informativ – wird nirgends automatisch als Buchung angelegt.')
        ), 2, 2, 1, 1)

        self.planning_include_goals_check = Gtk.CheckButton(
            label=tr('Weitere Sparziele einbeziehen (Priorität siehe Sparziele-Tab)')
        )
        self.planning_include_goals_check.set_active(True)
        rec_grid.attach(self.planning_include_goals_check, 0, 3, 2, 1)

        # -- Optional: Risikoprofil/Anlagehorizont --
        self.planning_risk_check = Gtk.CheckButton(
            label=tr('Risikoprofil/Anlagehorizont für den ETF-Anteil berücksichtigen (optional)')
        )
        self.planning_risk_check.connect("toggled", self._on_risk_toggle_changed)
        rec_grid.attach(self.planning_risk_check, 0, 4, 2, 1)

        risk_subgrid = Gtk.Grid(column_spacing=8, row_spacing=4)
        risk_subgrid.set_margin_start(20)
        rec_grid.attach(risk_subgrid, 0, 5, 2, 1)

        risk_subgrid.attach(Gtk.Label(label=tr('Anlagehorizont (Jahre):'), xalign=0), 0, 0, 1, 1)
        self.planning_horizon_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=10, lower=0, upper=60,
                                       step_increment=1, page_increment=5),
            numeric=True,
        )
        self.planning_horizon_spin.set_sensitive(False)
        risk_subgrid.attach(self.planning_horizon_spin, 1, 0, 1, 1)
        risk_subgrid.attach(_help_button(
            tr('Wie viele Jahre das Geld voraussichtlich investiert bleibt, bevor es gebraucht wird. Kurzer Horizont = höheres Risiko, dass ein Kurseinbruch sich nicht mehr erholt, bevor das Geld gebraucht wird – daher bei kurzem Horizont ein kleinerer ETF-Anteil.')
        ), 2, 0, 1, 1)

        risk_subgrid.attach(Gtk.Label(label=tr('Risikoprofil:'), xalign=0), 0, 1, 1, 1)
        self.planning_risk_combo = Gtk.ComboBoxText()
        self.planning_risk_combo.append("konservativ", tr('Konservativ'))
        self.planning_risk_combo.append("ausgewogen", tr('Ausgewogen'))
        self.planning_risk_combo.append("offensiv", tr('Offensiv'))
        self.planning_risk_combo.set_active_id("ausgewogen")
        self.planning_risk_combo.set_sensitive(False)
        risk_subgrid.attach(self.planning_risk_combo, 1, 1, 1, 1)
        risk_subgrid.attach(_help_button(
            tr('Wie viel Wertschwankung (und damit Verlustrisiko) du bereit bist einzugehen, um langfristig höhere Renditechancen zu haben. Konservativ = mehr Sicherheitsreserve, weniger ETF-Anteil; offensiv = mehr ETF-Anteil, mehr Schwankung.')
        ), 2, 1, 1, 1)

        risk_hint = Gtk.Label(
            xalign=0,
            label=tr('Grobe Faustregel: je kürzer der Horizont bzw. je konservativer das Profil, desto mehr vom Investitionsbetrag als Sicherheitsreserve (Tagesgeld) statt in den ETF-Sparplan. Unter 3 Jahren Horizont wird ganz von Aktien-ETFs abgeraten, da kurzfristige Kursschwankungen zu riskant wären.'),
        )
        risk_hint.set_line_wrap(True)
        risk_subgrid.attach(risk_hint, 0, 2, 2, 1)

        calc_rec_btn = Gtk.Button(label=tr('Empfehlung berechnen'))
        calc_rec_btn.connect("clicked", self._on_calculate_recommendation)
        rec_grid.attach(calc_rec_btn, 0, 6, 2, 1)

        self.recommendation_label = Gtk.Label(xalign=0)
        self.recommendation_label.set_line_wrap(True)
        rec_grid.attach(self.recommendation_label, 0, 7, 2, 1)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        rec_grid.attach(action_box, 0, 8, 2, 1)

        apply_etf_btn = Gtk.Button(label=tr('Monatliche ETF-Rate übernehmen'))
        apply_etf_btn.connect("clicked", self._on_apply_recommendation_to_etf)
        action_box.pack_start(apply_etf_btn, False, False, 0)

        apply_capital_btn = Gtk.Button(label=tr('Startkapital-Anteile als Fortschritt vormerken'))
        apply_capital_btn.connect("clicked", self._on_apply_capital_to_notgroschen)
        action_box.pack_start(apply_capital_btn, False, False, 0)

        self.apply_capital_as_transaction_check = Gtk.CheckButton(
            label=tr('Dabei auch als Buchung verbuchen (Kontostand sinkt entsprechend)')
        )
        self.apply_capital_as_transaction_check.set_active(True)
        rec_grid.attach(self.apply_capital_as_transaction_check, 0, 9, 2, 1)

        capital_hint = Gtk.Label(
            xalign=0,
            label=tr('Wichtig: Ohne diese Buchung bleibt dein Kontostand oben unverändert, obwohl die Sparziele-Fortschritte steigen – dasselbe Geld würde dir beim nächsten Mal fälschlich erneut als Startkapital angeboten. Häkchen nur entfernen, wenn das eingegebene Startkapital NICHT aus deinem hinterlegten Kontostand stammt (z. B. separates Erbe/Depot, das dort nicht mitgezählt wird).'),
        )
        capital_hint.set_line_wrap(True)
        rec_grid.attach(capital_hint, 0, 10, 2, 1)

        disclaimer = Gtk.Label(xalign=0)
        disclaimer.set_line_wrap(True)
        disclaimer.set_markup(
            tr('<small>Diese Aufteilung folgt der gängigen Faustregel „Notgroschen (und ggf. weitere Ziele) vor Investieren“ sowie einer einfachen Horizont-/Risiko-Faustregel für den ETF-Anteil. Beides sind transparente Modellrechnungen – KEINE individuelle Finanzberatung. Sie berücksichtigen weder Schulden noch Steuern noch deine tatsächliche persönliche Risikotragfähigkeit. Alle Werte lassen sich frei anpassen; für eine verbindliche Einschätzung wende dich an eine unabhängige Finanzberatung.</small>')
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
                tr('<i>Noch kein Kontostand hinterlegt – oben Stichtag und Betrag eintragen und speichern.</i>')
            )
        else:
            bd = self.store.get_balance_breakdown()
            if bd and self.store.notgroschen_pocket_enabled():
                self.current_balance_label.set_markup(
                    tr('Girokonto: <b>{0}</b>\nNotgroschen-Unterkonto: <b>{1}</b>\nGesamt: <b>{2}</b>').format(fmt_amount(bd['giro']), fmt_amount(bd['pocket']), fmt_amount(bd['total']))
                )
            else:
                self.current_balance_label.set_markup(
                    tr('Aktueller Kontostand (berechnet): <b>{0}</b>').format(fmt_amount(balance))
                )

    def _on_toggle_pocket(self, widget):
        self.store.set_notgroschen_pocket(widget.get_active())
        self._refresh_current_balance_display()

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
            status = (tr('Bestehendes Sparziel „Notgroschen“: {0} von aktuell {1} angespart.').format(fmt_amount(current), fmt_amount(existing['target_amount'])))
        else:
            status = tr('Noch kein Sparziel „Notgroschen“ angelegt.')
        self.notgroschen_preview_label.set_markup(
            tr('Zielbetrag bei {0} Monaten Fixkosten: <b>{1}</b>\n{2}').format(months, fmt_amount(target), status)
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
            tr('Monatlich verfügbar (Netto abzüglich Fixkosten von {0} und Freizeitbudget von {1}): <b>{2}</b>').format(fmt_amount(fixed), fmt_amount(leisure), fmt_amount(rec['monthly_available'])),
            tr('Startkapital: <b>{0}</b>').format(fmt_amount(capital)),
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
                tr('• <b>{0}</b> (Ziel: {1}, bereits {2} vorhanden): {3} aus Startkapital, {4}/Monat – {5}').format(g['name'], fmt_amount(g['target_amount']), fmt_amount(g['current_amount']), fmt_amount(g['capital_allocated']), fmt_amount(g['monthly_allocated']), status)
            )

        lines.append("")
        if rec["risk_applied"]:
            lines.append(
                tr('Rest zum Investieren – bei {0} Jahren Horizont, Profil „{1}“: empfohlener ETF-Anteil <b>{2}%</b>, Rest als Sicherheitsreserve:').format(int(self.planning_horizon_spin.get_value()), self.planning_risk_combo.get_active_text(), rec['equity_share_percent'])
            )
            lines.append(
                tr('  → ETF-Sparplan: <b>{0}</b>/Monat, <b>{1}</b> Startkapital').format(fmt_amount(rec['monthly_to_equity']), fmt_amount(rec['capital_to_equity']))
            )
            lines.append(
                tr('  → Sicherheitsreserve (z. B. Tagesgeld): <b>{0}</b>/Monat, <b>{1}</b> Startkapital').format(fmt_amount(rec['monthly_to_safety']), fmt_amount(rec['capital_to_safety']))
            )
        else:
            lines.append(
                tr('Rest zum Investieren (z. B. ETF-Sparplan): <b>{0}</b>/Monat, <b>{1}</b> Startkapital').format(fmt_amount(rec['monthly_to_etf']), fmt_amount(rec['capital_to_etf']))
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
        form.attach(Gtk.Label(label=tr('Name:'), xalign=0), 0, row, 1, 1)
        self.etf_name_entry = Gtk.Entry(text="Mein ETF-Sparplan")
        form.attach(self.etf_name_entry, 1, row, 1, 1)

        row += 1
        form.attach(Gtk.Label(label=tr('Monatliche Rate (€):'), xalign=0), 0, row, 1, 1)
        self.etf_amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=100, lower=1, upper=100000,
                                       step_increment=10, page_increment=50),
            numeric=True, digits=2,
        )
        form.attach(self.etf_amount_spin, 1, row, 1, 1)

        row += 1
        form.attach(Gtk.Label(label=tr('Erwartete jährl. Rendite (%):'), xalign=0), 0, row, 1, 1)
        self.etf_return_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=6.0, lower=-20, upper=30,
                                       step_increment=0.5, page_increment=1),
            numeric=True, digits=2,
        )
        form.attach(self.etf_return_spin, 1, row, 1, 1)

        row += 1
        form.attach(Gtk.Label(label=tr('Laufzeit (Jahre):'), xalign=0), 0, row, 1, 1)
        self.etf_years_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=10, lower=1, upper=60,
                                       step_increment=1, page_increment=5),
            numeric=True,
        )
        form.attach(self.etf_years_spin, 1, row, 1, 1)

        row += 1
        form.attach(Gtk.Label(label=tr('Jährliche Erhöhung der Sparrate (%):'), xalign=0),
                    0, row, 1, 1)
        self.etf_increase_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=50,
                                       step_increment=0.5, page_increment=5),
            numeric=True, digits=2,
        )
        form.attach(self.etf_increase_spin, 1, row, 1, 1)
        form.attach(_help_button(
            tr('Erhöht die monatliche Sparrate jedes Jahr um diesen Prozentsatz, z. B. um eine erwartete Gehaltssteigerung nachzubilden. 0 % = die Sparrate bleibt über die gesamte Laufzeit konstant.')
        ), 2, row, 1, 1)

        row += 1
        form.attach(Gtk.Label(label=tr('Maximale Sparrate (€, 0 = kein Deckel):'), xalign=0),
                    0, row, 1, 1)
        self.etf_cap_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=100000,
                                       step_increment=10, page_increment=50),
            numeric=True, digits=2,
        )
        form.attach(self.etf_cap_spin, 1, row, 1, 1)
        form.attach(_help_button(
            tr('Obergrenze für die Sparrate, falls sie sich durch die jährliche Erhöhung sonst unbegrenzt weiter steigern würde. 0 bedeutet: kein Deckel, die Rate wächst ungebremst weiter.')
        ), 2, row, 1, 1)

        # -- Steuer-Einstellungen --
        tax_frame = Gtk.Frame(label=tr('Deutsche Kapitalertragsteuer (vereinfacht, anpassbar)'))
        box.pack_start(tax_frame, False, False, 0)
        tax_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        tax_grid.set_border_width(8)
        tax_frame.add(tax_grid)

        self.etf_vorab_check = Gtk.CheckButton(
            label=tr('Jährliche Vorabpauschale simulieren (statt Einmalbesteuerung am Laufzeitende)')
        )
        self.etf_vorab_check.connect("toggled", self._on_vorab_toggled)
        tax_grid.attach(self.etf_vorab_check, 0, 0, 3, 1)

        tax_grid.attach(Gtk.Label(label=tr('Basiszins (%, jährlich vom BMF festgelegt):'), xalign=0),
                         0, 1, 1, 1)
        self.etf_basiszins_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=2.55, lower=0, upper=15,
                                       step_increment=0.1, page_increment=0.5),
            numeric=True, digits=2,
        )
        self.etf_basiszins_spin.set_sensitive(False)
        tax_grid.attach(self.etf_basiszins_spin, 1, 1, 1, 1)
        tax_grid.attach(_help_button(
            tr('Zinssatz, den das Bundesfinanzministerium jährlich für die Vorabpauschale-Berechnung festlegt (orientiert sich an langfristigen Bundesanleihen). Ändert sich jährlich – der voreingestellte Wert ist nur ein Richtwert, aktuellen Wert bei Bedarf nachschlagen.')
        ), 2, 1, 1, 1)

        tax_grid.attach(Gtk.Label(label=tr('Teilfreistellung (%):'), xalign=0), 0, 2, 1, 1)
        self.etf_teilfreistellung_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=30, lower=0, upper=60,
                                       step_increment=5, page_increment=10),
            numeric=True, digits=1,
        )
        tax_grid.attach(self.etf_teilfreistellung_spin, 1, 2, 1, 1)
        tax_grid.attach(_help_button(
            tr('Anteil des Fondsgewinns, der steuerfrei bleibt (§20 InvStG), um die Vorbelastung durch Unternehmenssteuern auszugleichen. 30 % ist der übliche Satz für Aktienfonds-ETFs mit mindestens 51 % Aktienquote. Bei Anleihen-ETFs 0 %, bei Mischfonds meist 15 %, bei Immobilienfonds 60–80 %.')
        ), 2, 2, 1, 1)

        tax_grid.attach(Gtk.Label(label=tr('Kapitalertragsteuer (%):'), xalign=0), 0, 3, 1, 1)
        self.etf_kest_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=25, lower=0, upper=50,
                                       step_increment=1, page_increment=5),
            numeric=True, digits=2,
        )
        tax_grid.attach(self.etf_kest_spin, 1, 3, 1, 1)
        tax_grid.attach(_help_button(
            tr('Die pauschale Abgeltungsteuer auf Kapitalerträge in Deutschland, gesetzlich 25 %. In der Regel nicht anzupassen, außer für Was-wäre-wenn-Szenarien.')
        ), 2, 3, 1, 1)

        tax_grid.attach(Gtk.Label(label=tr('Solidaritätszuschlag (%):'), xalign=0), 0, 4, 1, 1)
        self.etf_soli_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=5.5, lower=0, upper=20,
                                       step_increment=0.5, page_increment=1),
            numeric=True, digits=2,
        )
        tax_grid.attach(self.etf_soli_spin, 1, 4, 1, 1)
        tax_grid.attach(_help_button(
            tr('Zuschlag von 5,5 % auf die Kapitalertragsteuer (nicht auf den Gewinn selbst) – gesetzlich vorgegeben, in der Regel nicht anzupassen.')
        ), 2, 4, 1, 1)

        tax_grid.attach(Gtk.Label(label=tr('Sparerpauschbetrag (€/Jahr):'), xalign=0), 0, 5, 1, 1)
        self.etf_pauschbetrag_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=1000, lower=0, upper=5000,
                                       step_increment=100, page_increment=500),
            numeric=True, digits=0,
        )
        tax_grid.attach(self.etf_pauschbetrag_spin, 1, 5, 1, 1)
        tax_grid.attach(_help_button(
            tr('Steuerfreibetrag auf Kapitalerträge: 1.000 € pro Jahr bei Einzelveranlagung, 2.000 € bei Zusammenveranlagung (Ehepaare, Stand 2023). Wird hier nur einmalig (ohne Vorabpauschale) bzw. jährlich (mit Vorabpauschale) angesetzt – in der Realität ist er über einen Freistellungsauftrag auf mehrere Banken/Depots aufteilbar.')
        ), 2, 5, 1, 1)

        self.etf_tax_hint = Gtk.Label(xalign=0)
        self.etf_tax_hint.set_line_wrap(True)
        self._update_tax_hint()
        tax_grid.attach(self.etf_tax_hint, 0, 6, 3, 1)

        calc_btn = Gtk.Button(label=tr('Berechnen & Speichern'))
        calc_btn.connect("clicked", self._on_calculate_etf)
        box.pack_start(calc_btn, False, False, 0)

        self.etf_summary_label = Gtk.Label(label="", xalign=0)
        self.etf_summary_label.set_line_wrap(True)
        box.pack_start(self.etf_summary_label, False, False, 0)

        scen_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_start(scen_box, False, False, 0)
        scen_label = Gtk.Label()
        scen_label.set_markup(tr('<b>Szenarien</b> – Rendite ±'))
        scen_box.pack_start(scen_label, False, False, 0)
        self.etf_spread_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=2.0, lower=0, upper=20,
                                       step_increment=0.5, page_increment=1),
            digits=1, numeric=True)
        scen_box.pack_start(self.etf_spread_spin, False, False, 0)
        scen_box.pack_start(Gtk.Label(label=tr('Prozentpunkte   Inflation:')), False, False, 0)
        self.etf_inflation_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=2.0, lower=0, upper=15,
                                       step_increment=0.5, page_increment=1),
            digits=1, numeric=True)
        scen_box.pack_start(self.etf_inflation_spin, False, False, 0)
        scen_box.pack_start(Gtk.Label(label=tr('% p.a.')), False, False, 0)
        scen_box.pack_start(_help_button(
            tr('Zeigt, wie stark das Ergebnis streuen kann, wenn die Rendite besser oder schlechter ausfällt als angenommen. „Kaufkraftbereinigt“ zieht die Inflation ab und gibt den Endwert nach Steuern in heutiger Kaufkraft an. Das sind Rechenbeispiele, keine Prognose und keine Anlageempfehlung.')),
            False, False, 0)

        # Szenario, Rendite, Endwert vor Steuern, nach Steuern, kaufkraftbereinigt
        self.etf_scenario_store = Gtk.ListStore(str, str, str, str, str)
        self.etf_scenario_view = Gtk.TreeView(model=self.etf_scenario_store)
        for i, title in enumerate(("Szenario", "Rendite p.a.", tr('Endwert vor Steuern'),
                                   tr('Endwert nach Steuern'), tr('nach Steuern, heutige Kaufkraft'))):
            renderer = Gtk.CellRendererText()
            renderer.set_property("xalign", 1.0 if i else 0.0)
            column = Gtk.TreeViewColumn(tr(title), renderer, text=i)
            column.set_expand(True)
            self.etf_scenario_view.append_column(column)
        box.pack_start(self.etf_scenario_view, False, False, 0)

        self.etf_result_store = Gtk.ListStore(int, str, str, str, str)
        # jahr, sparrate, eingezahlt, wert, gewinn
        self.etf_result_view = Gtk.TreeView(model=self.etf_result_store)
        self.etf_result_view.set_size_request(-1, 220)
        box.pack_start(self.etf_result_view, False, False, 0)
        for title, col_id in [(tr('Jahr'), 0), ("Sparrate", 1), ("Eingezahlt", 2),
                               ("Wert", 3), (tr('Gewinn'), 4)]:
            renderer = Gtk.CellRendererText()
            renderer.set_property("xalign", 1.0 if col_id > 0 else 0.0)
            column = Gtk.TreeViewColumn(tr(title), renderer, text=col_id)
            self.etf_result_view.append_column(column)

        plan_manage_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_start(plan_manage_box, False, False, 0)

        plan_manage_box.pack_start(Gtk.Label(label=tr('Gespeicherter Plan:')), False, False, 0)
        self.etf_saved_plans_combo = Gtk.ComboBoxText()
        plan_manage_box.pack_start(self.etf_saved_plans_combo, True, True, 0)

        del_btn = Gtk.Button(label=tr('Löschen'))
        del_btn.connect("clicked", self._on_delete_etf_plan)
        plan_manage_box.pack_start(del_btn, False, False, 0)

        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 4)

        compare_label = Gtk.Label(
            xalign=0,
            label=tr('Vergleich gespeicherter Sparpläne (Wertentwicklung, vor Steuern):'),
        )
        box.pack_start(compare_label, False, False, 0)

        self.etf_compare_area = Gtk.DrawingArea()
        self.etf_compare_area.set_size_request(-1, 260)
        self.etf_compare_area.connect("draw", self._on_draw_etf_comparison)
        box.pack_start(self.etf_compare_area, False, False, 0)

        self._refresh_etf_plan_selector()
        self._refresh_etf_comparison()

        for spin in (self.etf_amount_spin, self.etf_return_spin, self.etf_years_spin,
                     self.etf_increase_spin, self.etf_cap_spin, self.etf_basiszins_spin,
                     self.etf_teilfreistellung_spin, self.etf_kest_spin, self.etf_soli_spin,
                     self.etf_pauschbetrag_spin, self.etf_spread_spin, self.etf_inflation_spin):
            spin.connect("value-changed", self._refresh_etf_scenarios)
        self.etf_vorab_check.connect("toggled", self._refresh_etf_scenarios)
        self._refresh_etf_scenarios()
        return outer

    def _refresh_etf_scenarios(self, *_args):
        if not hasattr(self, "etf_scenario_store"):
            return
        cap = self.etf_cap_spin.get_value()
        scenarios = FinanceStore.etf_scenarios(
            self.etf_amount_spin.get_value(), self.etf_return_spin.get_value(),
            int(self.etf_years_spin.get_value()),
            annual_increase_percent=self.etf_increase_spin.get_value(),
            max_monthly_amount=cap if cap > 0 else None,
            spread_percent=self.etf_spread_spin.get_value(),
            inflation_percent=self.etf_inflation_spin.get_value(),
            use_vorabpauschale=self.etf_vorab_check.get_active(),
            basiszins_percent=self.etf_basiszins_spin.get_value(),
            teilfreistellung_percent=self.etf_teilfreistellung_spin.get_value(),
            kapitalertragsteuer_percent=self.etf_kest_spin.get_value(),
            soli_percent=self.etf_soli_spin.get_value(),
            sparerpauschbetrag=self.etf_pauschbetrag_spin.get_value(),
        )
        self.etf_scenario_store.clear()
        for sc in scenarios:
            self.etf_scenario_store.append([
                sc["label"], f"{sc['annual_return']:.2f} %", fmt_amount(sc["value"]),
                fmt_amount(sc["value_after_tax"]), fmt_amount(sc["real_value_after_tax"]),
            ])

    def _on_vorab_toggled(self, widget):
        self.etf_basiszins_spin.set_sensitive(widget.get_active())
        self._update_tax_hint()

    def _update_tax_hint(self):
        if self.etf_vorab_check.get_active():
            text = (tr('Hinweis: Simuliert die jährliche Vorabpauschale (Basisertrag = Wert zu Jahresbeginn × Basiszins × 70 %, gedeckelt auf den tatsächlichen Wertzuwachs). Der Sparerpauschbetrag steht dabei JÄHRLICH neu zur Verfügung. Bereits versteuerte Beträge werden bei der Steuer am Laufzeitende angerechnet (keine Doppelbesteuerung). Kirchensteuer bleibt unberücksichtigt.'))
        else:
            text = (tr('Hinweis: Vereinfachte Rechnung ohne jährliche Vorabpauschale – Steuer wird pauschal auf den Gesamtgewinn am Laufzeitende angesetzt, mit dem Sparerpauschbetrag nur EINMALIG am Ende. Kirchensteuer bleibt unberücksichtigt. Standardwerte: 30 % Teilfreistellung für Aktienfonds-ETFs, 25 % Kapitalertragsteuer, 5,5 % Soli, 1.000 € Sparerpauschbetrag (Einzelveranlagung).'))
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
                tr(' Während der Laufzeit wurden bereits <b>{0}</b> Steuern auf Vorabpauschalen gezahlt (im Endwert schon berücksichtigt); davon <b>{1}</b> Gewinn wurden bei der Steuer am Ende angerechnet.').format(fmt_amount(total_vorab_tax_paid), fmt_amount(cumulative_pretaxed_gain))
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
            tr('Nach <b>{0} Jahren</b> bei <b>{1:.2f}% p.a.</b>: eingezahlt <b>{2}</b>, Endwert vor Abschluss-Steuer <b>{3}</b>, Gewinn <b>{4}</b>.\nSteuer bei (angenommenem) Verkauf: <b>{5}</b> → Endwert nach Steuern ca. <b>{6}</b>.{7}').format(years, annual_return, fmt_amount(final['invested']), fmt_amount(final['value']), fmt_amount(tax['gain']), fmt_amount(final_tax_amount), fmt_amount(value_after_tax), vorab_note)
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
            label = tr('{0} ({1} Jahre, {2})').format(plan['name'], plan['duration_years'], plan['start_date'])
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
            cr.show_text(tr('Noch keine gespeicherten Sparpläne zum Vergleichen.'))
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
            cr.show_text(tr('J{0}').format(year))

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
        switcher_box.pack_start(Gtk.Label(label=tr('Ansicht:')), False, False, 0)

        self.stats_view_combo = Gtk.ComboBoxText()
        self.stats_view_combo.append("kategorien", tr('Ausgaben nach Kategorie (Kreisdiagramm)'))
        self.stats_view_combo.append("trend", tr('Einnahmen/Ausgaben-Trend'))
        self.stats_view_combo.append("fluss", tr('Geldfluss (Sankey-Diagramm)'))
        self.stats_view_combo.append("vergleich", tr('Kategorien vergleichen'))
        self.stats_view_combo.append("jahresvergleich", tr('Jahresübersicht (mit Vorjahr)'))
        self.stats_view_combo.set_active_id("kategorien")
        self.stats_view_combo.connect("changed", self._on_stats_view_changed)
        switcher_box.pack_start(self.stats_view_combo, False, False, 0)

        self.stats_stack = Gtk.Stack()
        self.stats_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        root.pack_start(self.stats_stack, True, True, 0)

        self.stats_stack.add_named(self._build_pie_section(), "kategorien")
        self.stats_stack.add_named(self._build_trend_section(), "trend")
        self.stats_stack.add_named(self._build_sankey_section(), "fluss")
        self.stats_stack.add_named(self._build_compare_section(), "vergleich")
        self.stats_stack.add_named(self._build_year_compare_section(), "jahresvergleich")

        self._refresh_stats()
        return root

    def _on_stats_view_changed(self, combo):
        self.stats_stack.set_visible_child_name(combo.get_active_id())

    def _build_pie_section(self):
        pie_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        pie_nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        pie_section.pack_start(pie_nav, False, False, 0)
        pie_nav.pack_start(Gtk.Label(label=tr('Ausgaben nach Kategorie –')), False, False, 0)

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
        trend_nav.pack_start(Gtk.Label(label=tr('Trend – letzte')), False, False, 0)

        self.trend_months_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=6, lower=2, upper=24,
                                       step_increment=1, page_increment=3),
            numeric=True,
        )
        self.trend_months_spin.connect("value-changed", self._on_trend_months_changed)
        trend_nav.pack_start(self.trend_months_spin, False, False, 0)
        trend_nav.pack_start(Gtk.Label(label=tr('Monate (bezogen auf den gewählten Monat)')),
                              False, False, 0)

        legend_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        trend_nav.pack_end(legend_box, False, False, 0)
        income_swatch = Gtk.Label()
        income_swatch.set_markup(tr('<span foreground="#1e8c3d">■</span>'))
        legend_box.pack_start(income_swatch, False, False, 0)
        legend_box.pack_start(Gtk.Label(label=tr('Einnahmen')), False, False, 0)
        expense_swatch = Gtk.Label()
        expense_swatch.set_markup(tr('<span foreground="#bf3826">■</span>'))
        legend_box.pack_start(expense_swatch, False, False, 6)
        legend_box.pack_start(Gtk.Label(label=tr('Ausgaben')), False, False, 0)

        self.trend_area = Gtk.DrawingArea()
        self.trend_area.set_size_request(-1, 380)
        self.trend_area.connect("draw", self._on_draw_trend)
        trend_section.pack_start(self.trend_area, True, True, 0)

        return trend_section

    def _build_sankey_section(self):
        sankey_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        sankey_nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sankey_section.pack_start(sankey_nav, False, False, 0)
        sankey_nav.pack_start(Gtk.Label(label=tr('Geldfluss –')), False, False, 0)

        prev_btn = _nav_button("◀", lambda w: self._shift_stats_month(-1))
        sankey_nav.pack_start(prev_btn, False, False, 0)

        self.sankey_month_label = Gtk.Label(label="")
        sankey_nav.pack_start(self.sankey_month_label, False, False, 0)

        next_btn = _nav_button("▶", lambda w: self._shift_stats_month(1))
        sankey_nav.pack_start(next_btn, False, False, 0)

        hint = Gtk.Label(xalign=0)

        hint.set_markup(
            tr('<b>Links</b> = Einnahmen nach Kategorie. <b>Rechts</b> = Ausgaben nach Kategorie sowie <span foreground="#4caf50"><b>Überschuss</b></span> / <span foreground="#e05245"><b>Fehlbetrag</b></span>, falls Einnahmen und Ausgaben nicht übereinstimmen.\nDie Bänder zeigen keine direkte 1:1-Zuordnung einzelner Euro, sondern die anteilige Verteilung über das monatliche Gesamtbudget.')
        )

        hint.set_line_wrap(True)

        sankey_section.pack_start(hint, False, False, 0)

        self.sankey_area = Gtk.DrawingArea()
        self.sankey_area.set_size_request(-1, 380)
        self.sankey_area.connect("draw", self._on_draw_sankey)
        sankey_section.pack_start(self.sankey_area, True, True, 0)

        return sankey_section

    def _build_compare_section(self):
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        section.pack_start(nav, False, False, 0)

        self.compare_mode_combo = Gtk.ComboBoxText()
        self.compare_mode_combo.append("monat", tr('Monat gegen Vormonat'))
        self.compare_mode_combo.append("jahr", tr('Jahresverlauf'))
        self.compare_mode_combo.set_active_id("monat")
        self.compare_mode_combo.connect("changed", lambda w: self._refresh_stats())
        nav.pack_start(self.compare_mode_combo, False, False, 0)

        nav.pack_start(_nav_button("◀", lambda w: self._shift_compare(-1)), False, False, 0)
        self.compare_label = Gtk.Label(label="")
        nav.pack_start(self.compare_label, False, False, 0)
        nav.pack_start(_nav_button("▶", lambda w: self._shift_compare(1)), False, False, 0)

        self.compare_category_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.compare_category_box.set_margin_start(16)
        nav.pack_start(self.compare_category_box, False, False, 0)
        self.compare_category_box.pack_start(Gtk.Label(label=tr('Kategorie:')), False, False, 0)
        self.compare_category_combo = Gtk.ComboBoxText()
        self.compare_category_combo.connect("changed", self._on_compare_category_changed)
        self.compare_category_box.pack_start(self.compare_category_combo, False, False, 0)
        # Kinder jetzt anzeigen und show_all() des Hauptfensters überspringen
        # lassen; die Box selbst wird nur im Jahresmodus eingeblendet.
        self.compare_category_box.show_all()
        self.compare_category_box.set_no_show_all(True)

        self.compare_area = Gtk.DrawingArea()
        self.compare_area.set_size_request(-1, 380)
        self.compare_area.connect("draw", self._on_draw_compare)
        section.pack_start(self.compare_area, True, True, 0)

        self.compare_summary = Gtk.Label(xalign=0)
        self.compare_summary.set_line_wrap(True)
        section.pack_start(self.compare_summary, False, False, 0)

        self._compare_rows = []
        self._compare_year_values = []
        self._compare_average = 0.0
        self._compare_future_from = 12
        self._updating_compare_combo = False
        return section

    def _on_compare_category_changed(self, combo):
        if not self._updating_compare_combo:
            self._refresh_stats()

    def _shift_compare(self, delta):
        step = 12 if self.compare_mode_combo.get_active_id() == "jahr" else 1
        self.stats_month = add_months(self.stats_month, delta * step)
        self._refresh_stats()

    def _refresh_compare(self, month_str):
        year_mode = self.compare_mode_combo.get_active_id() == "jahr"
        self.compare_category_box.set_visible(year_mode)

        if not year_mode:
            prev_month = add_months(self.stats_month, -1)
            self.compare_label.set_text(
                tr('{0} gegen {1}').format(month_label(self.stats_month), month_label(prev_month)))
            rows = self.store.category_comparison(month_str, prev_month.strftime("%Y-%m"))
            self._compare_rows = rows[:12]
            self._compare_labels = (month_label(self.stats_month), month_label(prev_month))
            total_cur = sum(r["current"] for r in rows)
            total_prev = sum(r["previous"] for r in rows)
            diff = total_cur - total_prev
            if rows:
                pct = f" ({diff / total_prev * 100:+.0f} %)" if total_prev > 0 else ""
                self.compare_summary.set_text(
                    tr('Gesamtausgaben: {0} gegenüber {1} im Vormonat – Veränderung {2}{3}. Rot = mehr ausgegeben, grün = weniger.').format(fmt_amount(total_cur), fmt_amount(total_prev), fmt_amount(diff), pct))
            else:
                self.compare_summary.set_text("")
            self.compare_area.queue_draw()
            return

        year = self.stats_month.year
        self.compare_label.set_text(tr('Jahr {0}').format(year))
        previous_choice = self.compare_category_combo.get_active_id()
        self._updating_compare_combo = True
        self.compare_category_combo.remove_all()
        self.compare_category_combo.append("__alle__", tr('Alle Ausgaben'))
        for r in self.store.expense_categories_in_year(year):
            self.compare_category_combo.append(r["category_name"],
                                               f"{r['icon']} {r['category_name']}")
        if not self.compare_category_combo.set_active_id(previous_choice or "__alle__"):
            self.compare_category_combo.set_active_id("__alle__")
        self._updating_compare_combo = False

        chosen = self.compare_category_combo.get_active_id()
        category = None if chosen in (None, "__alle__") else chosen
        values = self.store.category_year_series(year, category)

        # Durchschnitt nur über bereits begonnene Monate; spätere Monate
        # enthalten nur geplante Buchungen und werden blasser gezeichnet.
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
        self._compare_year_values = values
        self._compare_average = average
        self._compare_future_from = months_counted
        if total > 0:
            peak = max(range(12), key=lambda i: values[i])
            self.compare_summary.set_text(
                tr('Summe {0} (inkl. geplanter Buchungen): {1} · Ø pro Monat bisher: {2} · teuerster Monat: {3} ({4}). Rote Balken liegen über 120 % des Durchschnitts.').format(year, fmt_amount(total), fmt_amount(average), months()[peak], fmt_amount(values[peak])))
        else:
            self.compare_summary.set_text("")
        self.compare_area.queue_draw()

    @staticmethod
    def _text_width(cr, text, size=12):
        layout = PangoCairo.create_layout(cr)
        font = Pango.FontDescription()
        font.set_family("Sans")
        font.set_size(size * Pango.SCALE)
        layout.set_font_description(font)
        layout.set_text(text, -1)
        return layout.get_pixel_size()[0]

    def _on_draw_compare(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        fg = _widget_fg_color(widget)
        if self.compare_mode_combo.get_active_id() == "jahr":
            self._draw_compare_year(cr, width, height, fg)
        else:
            self._draw_compare_month(cr, width, height, fg)
        return False

    def _draw_category_rows(self, cr, width, height, fg, rows, labels):
        """Horizontale Balkenpaare je Kategorie (Vergleichswert grau, aktuell blau)."""
        if not rows:
            self._draw_text(cr, tr('Keine Ausgaben in diesen beiden Zeiträumen.'), 20, height / 2 - 8,
                            (*fg, 0.7))
            return
        prev_color, cur_color = (0.47, 0.53, 0.59), (0.20, 0.47, 0.75)
        label_w, delta_w, top = 170, 190, 30
        plot_x = label_w + 8
        plot_w = max(40, width - plot_x - delta_w - 70)
        row_h = (height - top - 6) / len(rows)
        bar_h = min(18.0, row_h * 0.36)
        max_val = max([r["current"] for r in rows] + [r["previous"] for r in rows] + [1])

        x = label_w
        for color, text in ((prev_color, labels[1]),
                            (cur_color, labels[0])):
            cr.set_source_rgb(*color)
            cr.rectangle(x, 8, 12, 12)
            cr.fill()
            self._draw_text(cr, text, x + 18, 5, (*fg, 1.0))
            x += 18 + self._text_width(cr, text) + 24

        for i, r in enumerate(rows):
            y = top + i * row_h
            mid = y + row_h / 2
            name = f"{r['icon']} {r['name']}"
            if self._text_width(cr, name) > label_w - 6:
                while len(name) > 3 and self._text_width(cr, name + "…") > label_w - 6:
                    name = name[:-1]
                name += "…"
            self._draw_text(cr, name, label_w - 6 - self._text_width(cr, name), mid - 9,
                            (*fg, 1.0))
            for k, (value, color) in enumerate(((r["previous"], prev_color),
                                                (r["current"], cur_color))):
                by = mid - bar_h - 1 if k == 0 else mid + 1
                bw = value / max_val * plot_w
                cr.set_source_rgb(*color)
                cr.rectangle(plot_x, by, max(bw, 1 if value > 0 else 0), bar_h)
                cr.fill()
                self._draw_text(cr, fmt_amount(value), plot_x + bw + 6, by + bar_h / 2 - 8,
                                (*fg, 0.8), size=11)
            if r["diff"] > 0.005:
                color = (0.88, 0.32, 0.27)
            elif r["diff"] < -0.005:
                color = (0.30, 0.69, 0.31)
            else:
                color = fg
            text = format_delta(r)
            self._draw_text(cr, text, width - 6 - self._text_width(cr, text), mid - 9,
                            (*color, 1.0))

    def _draw_compare_month(self, cr, width, height, fg):
        self._draw_category_rows(cr, width, height, fg, self._compare_rows, self._compare_labels)

    def _draw_compare_year(self, cr, width, height, fg):
        values = self._compare_year_values
        if not values or max(values) <= 0:
            self._draw_text(cr, tr('Keine Ausgaben in diesem Jahr.'), 20, height / 2 - 8,
                            (*fg, 0.7))
            return
        average = self._compare_average
        margin_left, margin_right, margin_top, margin_bottom = 70, 20, 26, 30
        plot_w = max(10, width - margin_left - margin_right)
        plot_h = max(10, height - margin_top - margin_bottom)
        max_val = max(max(values), average) * 1.08

        cr.set_source_rgba(*fg, 0.4)
        cr.set_line_width(1)
        cr.move_to(margin_left, margin_top)
        cr.line_to(margin_left, height - margin_bottom)
        cr.line_to(width - margin_right, height - margin_bottom)
        cr.stroke()
        for fraction in (0, 0.5, 1.0):
            y = height - margin_bottom - fraction * plot_h
            self._draw_text(cr, fmt_amount(max_val * fraction), 4, y - 8, (*fg, 0.75), size=11)

        group_w = plot_w / 12
        bar_w = group_w * 0.62
        for i, value in enumerate(values):
            x0 = margin_left + i * group_w + (group_w - bar_w) / 2
            h = value / max_val * plot_h
            high = average > 0 and value > average * 1.2
            r, g, b = (0.78, 0.25, 0.20) if high else (0.20, 0.47, 0.75)
            alpha = 0.35 if i >= self._compare_future_from else 1.0
            cr.set_source_rgba(r, g, b, alpha)
            cr.rectangle(x0, height - margin_bottom - h, bar_w, h)
            cr.fill()
            label_w = self._text_width(cr, months_short()[i], 11)
            self._draw_text(cr, months_short()[i], x0 + bar_w / 2 - label_w / 2,
                            height - margin_bottom + 6, (*fg, 0.9), size=11)
            if value > 0:
                txt = f"{value:,.0f}".replace(",", ".")
                self._draw_text(cr, txt, x0 + bar_w / 2 - self._text_width(cr, txt, 9) / 2,
                                height - margin_bottom - h - 16, (*fg, 0.9), size=9)

        if average > 0:
            y = height - margin_bottom - average / max_val * plot_h
            cr.set_source_rgb(0.90, 0.62, 0.0)
            cr.set_line_width(2)
            cr.set_dash([6, 4])
            cr.move_to(margin_left, y)
            cr.line_to(width - margin_right, y)
            cr.stroke()
            cr.set_dash([])
            self._draw_text(cr, tr('Ø {0}').format(fmt_amount(average)), margin_left + 6, y - 18,
                            (0.90, 0.62, 0.0, 1.0), size=11)

    def _build_year_compare_section(self):
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        section.pack_start(nav, False, False, 0)

        self.yearcmp_mode_combo = Gtk.ComboBoxText()
        self.yearcmp_mode_combo.append("monate", tr('Monate'))
        self.yearcmp_mode_combo.append("kategorien", tr('Nach Kategorie'))
        self.yearcmp_mode_combo.set_active_id("monate")
        self.yearcmp_mode_combo.connect("changed", lambda w: self._refresh_stats())
        nav.pack_start(self.yearcmp_mode_combo, False, False, 0)

        self.yearcmp_metric_combo = Gtk.ComboBoxText()
        self.yearcmp_metric_combo.append("expense", tr('Ausgaben'))
        self.yearcmp_metric_combo.append("income", tr('Einnahmen'))
        self.yearcmp_metric_combo.set_active_id("expense")
        self.yearcmp_metric_combo.connect("changed", lambda w: self._refresh_stats())
        nav.pack_start(self.yearcmp_metric_combo, False, False, 0)

        nav.pack_start(_nav_button("◀", lambda w: self._shift_yearcmp(-1)), False, False, 0)
        self.yearcmp_label = Gtk.Label(label="")
        nav.pack_start(self.yearcmp_label, False, False, 0)
        nav.pack_start(_nav_button("▶", lambda w: self._shift_yearcmp(1)), False, False, 0)

        self.yearcmp_area = Gtk.DrawingArea()
        self.yearcmp_area.set_size_request(-1, 380)
        self.yearcmp_area.connect("draw", self._on_draw_yearcmp)
        section.pack_start(self.yearcmp_area, True, True, 0)

        self.yearcmp_summary = Gtk.Label(xalign=0)
        self.yearcmp_summary.set_line_wrap(True)
        section.pack_start(self.yearcmp_summary, False, False, 0)

        self._yearcmp_months = []
        self._yearcmp_rows = []
        self._yearcmp_labels = ("", "")
        self._yearcmp_future_from = 12
        return section

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
        self.yearcmp_label.set_text(tr('{0} gegen {1}').format(year, year - 1))
        by_month = self.yearcmp_mode_combo.get_active_id() == "monate"
        self.yearcmp_metric_combo.set_visible(by_month)

        data = self.store.year_comparison(year)
        today = datetime.date.today()
        self._yearcmp_future_from = (12 if year < today.year
                                     else (today.month if year == today.year else 0))
        self._yearcmp_months = data["months"]
        self._yearcmp_rows = self.store.category_comparison(str(year), str(year - 1))[:12]
        self._yearcmp_labels = (str(year), str(year - 1))

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
            note = (tr(' Hinweis: Bei laufenden Jahren sind geplante, noch nicht erreichte Monate blass dargestellt und in den Summen enthalten.'))
        self.yearcmp_summary.set_text(" · ".join(parts) + "." + note)
        self.yearcmp_area.queue_draw()

    def _on_draw_yearcmp(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        fg = _widget_fg_color(widget)
        if self.yearcmp_mode_combo.get_active_id() == "kategorien":
            self._draw_category_rows(cr, width, height, fg, self._yearcmp_rows,
                                     self._yearcmp_labels)
        else:
            self._draw_year_months(cr, width, height, fg)
        return False

    def _draw_year_months(self, cr, width, height, fg):
        key = self.yearcmp_metric_combo.get_active_id() or "expense"
        prev_key = "prev_" + key
        months = self._yearcmp_months
        if not months or max([m[key] for m in months] + [m[prev_key] for m in months]) <= 0:
            self._draw_text(cr, tr('Keine Buchungen in diesen beiden Jahren.'), 20, height / 2 - 8,
                            (*fg, 0.7))
            return
        prev_color, cur_color = (0.47, 0.53, 0.59), (0.20, 0.47, 0.75)
        margin_left, margin_right, margin_top, margin_bottom = 70, 20, 34, 30
        plot_w = max(10, width - margin_left - margin_right)
        plot_h = max(10, height - margin_top - margin_bottom)
        max_val = max([m[key] for m in months] + [m[prev_key] for m in months]) * 1.05

        x = margin_left
        for color, text in ((prev_color, self._yearcmp_labels[1]),
                            (cur_color, self._yearcmp_labels[0])):
            cr.set_source_rgb(*color)
            cr.rectangle(x, 10, 12, 12)
            cr.fill()
            self._draw_text(cr, text, x + 18, 7, (*fg, 1.0))
            x += 18 + self._text_width(cr, text) + 24

        cr.set_source_rgba(*fg, 0.4)
        cr.set_line_width(1)
        cr.move_to(margin_left, margin_top)
        cr.line_to(margin_left, height - margin_bottom)
        cr.line_to(width - margin_right, height - margin_bottom)
        cr.stroke()
        for fraction in (0, 0.5, 1.0):
            y = height - margin_bottom - fraction * plot_h
            self._draw_text(cr, fmt_amount(max_val * fraction), 4, y - 8, (*fg, 0.75), size=11)

        group_w = plot_w / 12
        bar_w = group_w * 0.36
        for i, m in enumerate(months):
            x0 = margin_left + i * group_w + group_w * 0.12
            for k, (value, color) in enumerate(((m[prev_key], prev_color), (m[key], cur_color))):
                alpha = 0.35 if (k == 1 and i >= self._yearcmp_future_from) else 1.0
                h = value / max_val * plot_h
                cr.set_source_rgba(*color, alpha)
                cr.rectangle(x0 + k * (bar_w + 2), height - margin_bottom - h, bar_w, h)
                cr.fill()
            label = months_short()[i]
            self._draw_text(cr, label, x0 + bar_w - self._text_width(cr, label, 11) / 2 + 1,
                            height - margin_bottom + 6, (*fg, 0.9), size=11)

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
            right_nodes.append((tr('Übrig/Gespart'), "💰", total_income - total_expense,
                                 (0.12, 0.55, 0.24)))
        elif total_expense > total_income + 0.005:
            left_nodes.append((tr("Fehlbetrag"), "⚠️", total_expense - total_income,
                                (0.75, 0.22, 0.17)))

        self._sankey_data = {
            "left": left_nodes, "right": right_nodes,
            "total": max(total_income, total_expense),
        }
        self.sankey_area.queue_draw()
        self._refresh_compare(month_str)
        self._refresh_year_compare()

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
            cr.show_text(tr('Keine Ausgaben in diesem Monat.'))
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
            cr.show_text(tr('Keine Daten.'))
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
                tr('Keine Buchungen in diesem Monat.'),
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
        layout.set_text(tr('Gesamt'), -1)

        _, logical_rect = layout.get_pixel_extents()

        text_width = logical_rect.width
        text_height = logical_rect.height

        self._draw_text(
            cr,
            tr('Gesamt'),
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
    # Tab: Suche (alle Buchungen filtern)
    # =====================================================================

    def _build_search_tab(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_border_width(10)

        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        root.pack_start(row1, False, False, 0)
        self.search_text = Gtk.SearchEntry()
        self.search_text.set_placeholder_text(tr('Suchen in Beschreibung und Kategorie …'))
        self.search_text.connect("search-changed", self._run_search)
        row1.pack_start(self.search_text, True, True, 0)

        self.search_kind = Gtk.ComboBoxText()
        self.search_kind.append("", tr("Alle Arten"))
        self.search_kind.append("ausgabe", tr('Ausgaben'))
        self.search_kind.append("einnahme", tr('Einnahmen'))
        self.search_kind.set_active(0)
        self.search_kind.connect("changed", self._run_search)
        row1.pack_start(self.search_kind, False, False, 0)

        self.search_category = Gtk.ComboBoxText()
        self.search_category.connect("changed", self._run_search)
        row1.pack_start(self.search_category, False, False, 0)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        root.pack_start(row2, False, False, 0)
        row2.pack_start(Gtk.Label(label=tr('Zeitraum:')), False, False, 0)
        self.search_period = Gtk.ComboBoxText()
        for key, label in (("alle", tr("Alle")), ("monat", tr('Dieser Monat')),
                           ("3monate", tr('Letzte 3 Monate')), ("jahr", tr('Dieses Jahr')),
                           ("vorjahr", tr('Letztes Jahr')), ("eigen", tr("Eigener Zeitraum"))):
            self.search_period.append(key, label)
        self.search_period.set_active_id("alle")
        self.search_period.connect("changed", self._on_search_period_changed)
        row2.pack_start(self.search_period, False, False, 0)

        self.search_from = Gtk.Entry()
        self.search_to = Gtk.Entry()
        for entry in (self.search_from, self.search_to):
            entry.set_width_chars(11)
            entry.set_placeholder_text(tr('TT.MM.JJJJ'))
            entry.set_sensitive(False)
            entry.connect("changed", self._run_search)
        row2.pack_start(self.search_from, False, False, 0)
        row2.pack_start(Gtk.Label(label=tr('bis')), False, False, 0)
        row2.pack_start(self.search_to, False, False, 0)

        row2.pack_start(Gtk.Label(label=tr('   Betrag von')), False, False, 0)
        self.search_min = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=1000000,
                                       step_increment=10, page_increment=100),
            digits=2, numeric=True)
        self.search_max = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=1000000,
                                       step_increment=10, page_increment=100),
            digits=2, numeric=True)
        for spin in (self.search_min, self.search_max):
            spin.set_width_chars(8)
            spin.connect("value-changed", self._run_search)
        row2.pack_start(self.search_min, False, False, 0)
        row2.pack_start(Gtk.Label(label=tr('bis')), False, False, 0)
        row2.pack_start(self.search_max, False, False, 0)
        row2.pack_start(Gtk.Label(label=tr('€ (0 = egal)')), False, False, 0)

        self.search_future = Gtk.CheckButton(label=tr('auch geplante (zukünftige) Buchungen'))
        self.search_future.connect("toggled", self._run_search)
        root.pack_start(self.search_future, False, False, 0)

        # id, Datum, Kategorie, Art, Betrag, Betragsfarbe, Beschreibung
        self.search_store = Gtk.ListStore(int, str, str, str, str, str, str)
        self.search_view = Gtk.TreeView(model=self.search_store)
        for title, col in (("Datum", 1), (tr('Kategorie'), 2), ("Art", 3),
                           (tr('Betrag'), 4), ("Beschreibung", 6)):
            renderer = Gtk.CellRendererText()
            attrs = {"text": col}
            if title in ("Betrag", tr("Betrag")):
                renderer.set_property("xalign", 1.0)
                attrs["foreground"] = 5
            if title == "Beschreibung":
                renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            column = Gtk.TreeViewColumn(tr(title), renderer, **attrs)
            column.set_resizable(True)
            if title == "Beschreibung":
                column.set_expand(True)
            self.search_view.append_column(column)
        self.search_view.connect("row-activated", self._on_search_row_activated)
        scroller = Gtk.ScrolledWindow()
        scroller.set_shadow_type(Gtk.ShadowType.IN)
        scroller.add(self.search_view)
        root.pack_start(scroller, True, True, 0)

        self.search_summary = Gtk.Label(label="", xalign=0)
        root.pack_start(self.search_summary, False, False, 0)
        root.pack_start(Gtk.Label(
            label=tr('Doppelklick auf eine Zeile öffnet die Buchung zum Bearbeiten.'), xalign=0),
            False, False, 0)

        self._reload_search_categories()
        self._run_search()
        return root

    def _reload_search_categories(self):
        current = self.search_category.get_active_id()
        self.search_category.handler_block_by_func(self._run_search)
        self.search_category.remove_all()
        self.search_category.append("", tr('Alle Kategorien'))
        for c in self.store.list_categories():
            self.search_category.append(str(c["id"]), f"{c['icon']} {c['name']}")
        if not (current and self.search_category.set_active_id(current)):
            self.search_category.set_active(0)
        self.search_category.handler_unblock_by_func(self._run_search)

    @staticmethod
    def _parse_search_date(text):
        try:
            return datetime.datetime.strptime(text.strip(), "%d.%m.%Y").date().isoformat()
        except ValueError:
            return None

    def _on_search_period_changed(self, combo):
        key = combo.get_active_id()
        today = datetime.date.today()
        ranges = {
            "monat": (today.replace(day=1), today),
            "3monate": (add_months(today.replace(day=1), -2), today),
            "jahr": (today.replace(month=1, day=1), today),
            "vorjahr": (datetime.date(today.year - 1, 1, 1),
                        datetime.date(today.year - 1, 12, 31)),
        }
        custom = key == "eigen"
        self.search_from.set_sensitive(custom)
        self.search_to.set_sensitive(custom)
        if key in ranges:
            self.search_from.handler_block_by_func(self._run_search)
            self.search_to.handler_block_by_func(self._run_search)
            self.search_from.set_text(ranges[key][0].strftime("%d.%m.%Y"))
            self.search_to.set_text(ranges[key][1].strftime("%d.%m.%Y"))
            self.search_from.handler_unblock_by_func(self._run_search)
            self.search_to.handler_unblock_by_func(self._run_search)
        self._run_search()

    def _run_search(self, *_args):
        if not hasattr(self, "search_store"):
            return
        if self.search_period.get_active_id() == "alle":
            date_from = date_to = None
        else:
            date_from = self._parse_search_date(self.search_from.get_text())
            date_to = self._parse_search_date(self.search_to.get_text())
        category_id = self.search_category.get_active_id()
        rows, truncated = self.store.search_transactions(
            text=self.search_text.get_text() or None,
            category_id=int(category_id) if category_id else None,
            kind=self.search_kind.get_active_id() or None,
            date_from=date_from, date_to=date_to,
            min_amount=self.search_min.get_value() or None,
            max_amount=self.search_max.get_value() or None,
            include_future=self.search_future.get_active(),
        )
        self.search_store.clear()
        income = expense = 0.0
        for r in rows:
            d = datetime.date.fromisoformat(r["date"])
            self.search_store.append([
                r["id"], d.strftime("%d.%m.%Y"), f"{r['icon']} {r['category_name']}",
                tr('Einnahme') if r["kind"] == "einnahme" else tr('Ausgabe'),
                fmt_amount(r["amount"]),
                "#4caf50" if r["amount"] >= 0 else "#e05245",
                r["description"] or "",
            ])
            if r["amount"] >= 0:
                income += r["amount"]
            else:
                expense += -r["amount"]
        text = (tr('{0} Treffer · Einnahmen {1} · Ausgaben {2} · Saldo {3}').format(len(rows), fmt_amount(income), fmt_amount(expense), fmt_amount(income - expense)))
        if truncated:
            text += tr(' · nur die neuesten 2000 Treffer werden angezeigt – Filter enger setzen')
        self.search_summary.set_text(text)

    def _on_search_row_activated(self, tree_view, path, column):
        tx_id = self.search_store[path][0]
        existing = self.store.get_transaction(tx_id)
        if existing is None:
            return
        day = datetime.date.fromisoformat(existing["date"])
        dialog = TransactionDialog(self, self.store, day, existing=existing)
        if dialog.run() == Gtk.ResponseType.OK:
            dialog.save()
        dialog.destroy()
        self._after_transactions_changed()
        self._refresh_stats()

    # =====================================================================
    # Tab 7: Export / Import
    # =====================================================================

    def _build_export_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(10)

        csv_label = Gtk.Label(
            xalign=0,
            label=tr('CSV-Export aller Buchungen – zum Öffnen/Weiterverarbeiten in Excel oder LibreOffice Calc.')
        )
        csv_label.set_line_wrap(True)
        box.pack_start(csv_label, False, False, 0)

        csv_btn = Gtk.Button(label=tr('Buchungen als CSV exportieren…'))
        csv_btn.connect("clicked", self._on_export_csv)
        box.pack_start(csv_btn, False, False, 0)

        csv_import_label = Gtk.Label(
            xalign=0,
            label=tr("CSV-Import: Buchungen aus einer anderen Haushaltsbuch- oder Banking-Software übernehmen. Trennzeichen (';' oder ',') sowie deutsche/englische Zahlen- und Datumsformate werden automatisch erkannt. Erwartet werden Spalten für Datum und Betrag (z. B. 'Datum'/'Date', 'Betrag'/'Amount'); Kategorie, Art und Beschreibung sind optional – unbekannte Kategorien werden automatisch angelegt.")
        )
        csv_import_label.set_line_wrap(True)
        box.pack_start(csv_import_label, False, False, 0)

        csv_import_btn = Gtk.Button(label=tr('Buchungen aus CSV importieren…'))
        csv_import_btn.connect("clicked", self._on_import_csv)
        box.pack_start(csv_import_btn, False, False, 0)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        box.pack_start(sep, False, False, 8)

        json_label = Gtk.Label(
            xalign=0,
            label=tr('Vollständiges Backup (JSON) – enthält alle Buchungen, Vorlagen, Budgets, Sparziele, ETF-Pläne und Kategorien (inkl. Icons). Zum Sichern oder Übertragen auf einen anderen Rechner mit diesem Programm.')
        )
        json_label.set_line_wrap(True)
        box.pack_start(json_label, False, False, 0)

        export_json_btn = Gtk.Button(label=tr('Backup als JSON exportieren…'))
        export_json_btn.connect("clicked", self._on_export_json)
        box.pack_start(export_json_btn, False, False, 0)

        import_json_btn = Gtk.Button(label=tr('Backup aus JSON importieren…'))
        import_json_btn.connect("clicked", self._on_import_json)
        box.pack_start(import_json_btn, False, False, 0)

        backup_label = Gtk.Label(
            label=tr('Automatische Sicherung: Beim ersten Start eines Tages legt Plutos eine Kopie der Datenbank in {0} an (die letzten {1} bleiben erhalten).').format(self.store.backup_dir, self.store.BACKUP_KEEP),
            xalign=0)
        backup_label.set_line_wrap(True)
        box.pack_start(backup_label, False, False, 0)
        backup_btn = Gtk.Button(label=tr('Datenbank jetzt sichern'))
        backup_btn.connect("clicked", self._on_backup_now)
        box.pack_start(backup_btn, False, False, 0)

        lang_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lang_row.pack_start(Gtk.Label(label="Sprache / Language:", xalign=0), False, False, 0)
        self.language_combo = Gtk.ComboBoxText()
        for code, name in LANGUAGES.items():
            self.language_combo.append(code, name)
        self.language_combo.set_active_id(get_language())
        self.language_combo.connect("changed", self._on_language_changed)
        lang_row.pack_start(self.language_combo, False, False, 0)
        box.pack_start(lang_row, False, False, 0)

        self.export_status_label = Gtk.Label(label="", xalign=0)
        box.pack_start(self.export_status_label, False, False, 0)

        return box

    def _on_language_changed(self, combo):
        code = combo.get_active_id()
        if code:
            self.store.set_setting("language", code)
            self.export_status_label.set_text(
                "Neustart erforderlich, damit die Sprache wirksam wird. / "
                "Please restart Plutos to apply the language.")

    def _on_backup_now(self, widget):
        path = self.store.create_db_backup(force=True)
        self.export_status_label.set_text(tr('Datenbank gesichert: {0}').format(path))

    def _on_export_csv(self, widget):
        dialog = Gtk.FileChooserDialog(
            title=tr('Buchungen als CSV exportieren'), parent=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                            Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dialog.set_current_name("haushaltsbuch_export.csv")
        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            self.store.export_transactions_csv(path)
            self.export_status_label.set_text(tr('CSV exportiert nach: {0}').format(path))
        dialog.destroy()

    def _on_import_csv(self, widget):
        dialog = Gtk.FileChooserDialog(
            title=tr('Buchungen aus CSV importieren'), parent=self,
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
                                 tr('CSV konnte nicht gelesen werden:\n{0}').format(exc))
            return

        summary = tr('{0} Buchung(en) importiert').format(result['imported'])
        if result.get("duplicates"):
            summary += tr(', {0} bereits vorhanden (nicht doppelt angelegt)').format(result['duplicates'])
        if result["skipped"]:
            summary += tr(', {0} übersprungen').format(result['skipped'])
        self.export_status_label.set_text(tr('CSV importiert von: {0} – {1}.').format(path, summary))

        message_type = Gtk.MessageType.INFO if not result["errors"] else Gtk.MessageType.WARNING
        detail_lines = "\n".join(_localize_import_error(e) for e in result["errors"][:15])
        if len(result["errors"]) > 15:
            detail_lines += tr('\n… und {0} weitere.').format(len(result['errors']) - 15)
        _run_message_dialog(self, message_type, Gtk.ButtonsType.OK,
                             summary + (":" if detail_lines else "."), detail_lines or None)

        self.store.ensure_horizon(self._selected_calendar_month())
        self._after_transactions_changed()
        self._refresh_stats()

    def _on_export_json(self, widget):
        dialog = Gtk.FileChooserDialog(
            title=tr('Backup als JSON exportieren'), parent=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                            Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dialog.set_current_name("haushaltsbuch_backup.json")
        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            self.store.export_backup_json(path)
            self.export_status_label.set_text(tr('Backup exportiert nach: {0}').format(path))
        dialog.destroy()

    def _on_import_json(self, widget):
        response = _run_message_dialog(
            self, Gtk.MessageType.WARNING, Gtk.ButtonsType.OK_CANCEL,
            tr('Import ersetzt alle aktuellen Daten. Fortfahren?'),
        )
        if response != Gtk.ResponseType.OK:
            return

        dialog = Gtk.FileChooserDialog(
            title=tr('Backup importieren'), parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                            Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            self.store.import_backup_json(path)
            self.store.ensure_horizon(self._selected_calendar_month())
            self.export_status_label.set_text(tr('Backup importiert von: {0}').format(path))
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
        super().__init__(title=tr(title), transient_for=parent, flags=0)
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
        title = tr('Buchung bearbeiten') if existing else tr('Buchung hinzufügen')
        super().__init__(parent, title)
        self.set_default_size(400, 320)
        self.store = store
        self.existing = existing
        grid = self.grid

        grid.attach(Gtk.Label(label=tr('Art:'), xalign=0), 0, 0, 1, 1)
        self.kind_combo = Gtk.ComboBoxText()
        self.kind_combo.append("ausgabe", tr('Ausgabe'))
        self.kind_combo.append("einnahme", tr('Einnahme'))
        default_kind = existing["kind"] if existing else "ausgabe"
        self.kind_combo.set_active_id(default_kind)
        self.kind_combo.connect("changed", lambda w: self._reload_categories())
        grid.attach(self.kind_combo, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label=tr('Kategorie:'), xalign=0), 0, 1, 1, 1)
        self.category_combo = Gtk.ComboBoxText()
        grid.attach(self.category_combo, 1, 1, 1, 1)
        self._reload_categories(preselect=existing["category_id"] if existing else None)

        grid.attach(Gtk.Label(label=tr('Betrag (€):'), xalign=0), 0, 2, 1, 1)
        initial_amount = abs(existing["amount"]) if existing else 0
        self.amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=initial_amount, lower=0, upper=1000000,
                                       step_increment=1, page_increment=10),
            numeric=True, digits=2,
        )
        grid.attach(self.amount_spin, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label=tr('Datum (TT.MM.JJJJ):'), xalign=0), 0, 3, 1, 1)
        if existing:
            initial_date = datetime.date.fromisoformat(existing["date"])
        else:
            initial_date = default_date
        self.date_entry = Gtk.Entry(text=initial_date.strftime("%d.%m.%Y"))
        grid.attach(self.date_entry, 1, 3, 1, 1)

        grid.attach(Gtk.Label(label=tr('Beschreibung:'), xalign=0), 0, 4, 1, 1)
        self.description_entry = Gtk.Entry(text=existing["description"] if existing else "")
        grid.attach(self.description_entry, 1, 4, 1, 1)

        if not existing:
            self.recurring_check = Gtk.CheckButton(label=tr('Wiederkehrende Buchung'))
            self.recurring_check.connect("toggled", self._on_recurring_toggled)
            grid.attach(self.recurring_check, 0, 5, 2, 1)

            self.frequency_combo = Gtk.ComboBoxText()
            self.frequency_combo.append("woechentlich", tr('Wöchentlich'))
            self.frequency_combo.append("monatlich", tr('Monatlich'))
            self.frequency_combo.append("jaehrlich", tr('Jährlich'))
            self.frequency_combo.set_active_id("monatlich")
            self.frequency_combo.set_sensitive(False)
            grid.attach(self.frequency_combo, 0, 6, 2, 1)
        else:
            self.recurring_check = None
            if existing["recurring_template_id"] is not None:
                note = Gtk.Label(
                    xalign=0,
                    label=tr('Diese Buchung stammt aus einer wiederkehrenden Vorlage. Änderungen betreffen nur diese einzelne Buchung.'),
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

        # Für Hinweise nach dem Speichern (z. B. Budget-Warnung)
        self.last_saved = {"category_id": category_id, "date": date_obj.isoformat(),
                           "amount": amount}

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
        super().__init__(title=tr("Wiederkehrende Vorlagen"), transient_for=parent, flags=0)
        self.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.set_default_size(650, 380)
        self.store = store

        area = self.get_content_area()
        area.set_border_width(10)

        info = Gtk.Label(
            xalign=0,
            label=tr('Läuft eine Vorlage weiter, werden ihre Buchungen automatisch für jeden Monat erzeugt, den du dir im Kalender ansiehst – unbegrenzt, bis du sie hier löschst. Tipp: Doppelklick auf eine Vorlage öffnet sie zum Bearbeiten.'),
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

        for title, col_id in [(tr('Kategorie'), 1), (tr('Betrag'), 2), (tr('Häufigkeit'), 3),
                               ("Start", 4), ("Ende", 5)]:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(tr(title), renderer, text=col_id)
            self.tree_view.append_column(column)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        area.pack_start(btn_box, False, False, 6)

        edit_btn = Gtk.Button(label=tr('Bearbeiten'))
        edit_btn.connect("clicked", self._on_edit)
        btn_box.pack_start(edit_btn, False, False, 0)

        del_btn = Gtk.Button(label=tr('Löschen (inkl. künftiger Buchungen)'))
        del_btn.connect("clicked", self._on_delete)
        btn_box.pack_start(del_btn, False, False, 0)

        self._refresh()
        self.show_all()

    def _refresh(self):
        self.list_store.clear()
        freq_names = {"woechentlich": tr('Wöchentlich'), "monatlich": tr('Monatlich'),
                      "jaehrlich": tr('Jährlich')}
        for t in self.store.list_recurring_templates():
            self.list_store.append([
                t["id"], f"{t['icon']} {t['category_name']}", fmt_amount(t["amount"]),
                freq_names.get(t["frequency"], t["frequency"]),
                t["start_date"], t["end_date"] or tr('läuft weiter'),
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
            text=tr('Wiederkehrende Vorlage löschen?'),
            secondary_text=tr('Zukünftige (heute oder später datierte) Buchungen dieser Vorlage werden dabei immer entfernt.'),
        )
        past_check = Gtk.CheckButton(
            label=tr('Auch bereits vergangene Buchungen dieser Vorlage löschen')
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
        super().__init__(parent, tr("Wiederkehrende Vorlage bearbeiten"))
        self.store = store
        self.template = template
        grid = self.grid

        grid.attach(Gtk.Label(label=tr('Art:'), xalign=0), 0, 0, 1, 1)
        self.kind_combo = Gtk.ComboBoxText()
        self.kind_combo.append("ausgabe", tr('Ausgabe'))
        self.kind_combo.append("einnahme", tr('Einnahme'))
        self.kind_combo.set_active_id(template["kind"])
        self.kind_combo.connect("changed", lambda w: self._reload_categories())
        grid.attach(self.kind_combo, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label=tr('Kategorie:'), xalign=0), 0, 1, 1, 1)
        self.category_combo = Gtk.ComboBoxText()
        grid.attach(self.category_combo, 1, 1, 1, 1)
        self._reload_categories(preselect=template["category_id"])

        grid.attach(Gtk.Label(label=tr('Betrag (€):'), xalign=0), 0, 2, 1, 1)
        self.amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=abs(template["amount"]), lower=0, upper=1000000,
                                       step_increment=1, page_increment=10),
            numeric=True, digits=2,
        )
        grid.attach(self.amount_spin, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label=tr('Beschreibung:'), xalign=0), 0, 3, 1, 1)
        self.description_entry = Gtk.Entry(text=template["description"] or "")
        grid.attach(self.description_entry, 1, 3, 1, 1)

        grid.attach(Gtk.Label(label=tr('Häufigkeit:'), xalign=0), 0, 4, 1, 1)
        self.frequency_combo = Gtk.ComboBoxText()
        self.frequency_combo.append("woechentlich", tr('Wöchentlich'))
        self.frequency_combo.append("monatlich", tr('Monatlich'))
        self.frequency_combo.append("jaehrlich", tr('Jährlich'))
        self.frequency_combo.set_active_id(template["frequency"])
        grid.attach(self.frequency_combo, 1, 4, 1, 1)

        grid.attach(Gtk.Label(label=tr('Startdatum (TT.MM.JJJJ):'), xalign=0), 0, 5, 1, 1)
        start_date = datetime.date.fromisoformat(template["start_date"])
        self.start_date_entry = Gtk.Entry(text=start_date.strftime("%d.%m.%Y"))
        grid.attach(self.start_date_entry, 1, 5, 1, 1)

        grid.attach(Gtk.Label(label=tr('Enddatum (TT.MM.JJJJ, optional):'), xalign=0), 0, 6, 1, 1)
        self.end_date_entry = Gtk.Entry()
        if template["end_date"]:
            end_date = datetime.date.fromisoformat(template["end_date"])
            self.end_date_entry.set_text(end_date.strftime("%d.%m.%Y"))
        self.end_date_entry.set_placeholder_text(tr('leer = läuft unbegrenzt weiter'))
        grid.attach(self.end_date_entry, 1, 6, 1, 1)

        note = Gtk.Label(
            xalign=0,
            label=tr('Änderungen wirken standardmäßig nur auf zukünftige Buchungen (ab heute) – bereits vergangene bleiben als historischer Stand unverändert (z. B. sinnvoll bei einer Gehaltserhöhung: alte Monate zeigen weiterhin den alten Betrag).'),
        )
        note.set_line_wrap(True)
        grid.attach(note, 0, 7, 2, 1)

        self.apply_to_past_check = Gtk.CheckButton(
            label=tr('Änderungen auch auf bereits vergangene Buchungen anwenden (überschreibt deren bisherige Werte rückwirkend)')
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
        super().__init__(parent, tr("Budget setzen"))
        self.store = store
        self.month = month
        grid = self.grid

        grid.attach(Gtk.Label(label=tr('Kategorie:'), xalign=0), 0, 0, 1, 1)
        self.category_combo = Gtk.ComboBoxText()
        active_index = 0
        for i, cat in enumerate(store.list_categories(kind="ausgabe")):
            self.category_combo.append(str(cat["id"]), f"{cat['icon']} {cat['name']}")
            if preselect_category_id and cat["id"] == preselect_category_id:
                active_index = i
        self.category_combo.set_active(active_index)
        grid.attach(self.category_combo, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label=tr('Monatsbudget für {0} (€):').format(month_label(month)),
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
        super().__init__(parent, tr('Sparziel hinzufügen'))
        grid = self.grid

        grid.attach(Gtk.Label(label=tr('Name:'), xalign=0), 0, 0, 1, 1)
        self.name_entry = Gtk.Entry()
        grid.attach(self.name_entry, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label=tr('Zielbetrag (€):'), xalign=0), 0, 1, 1, 1)
        self.amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=1000, lower=1, upper=10000000,
                                       step_increment=50, page_increment=500),
            numeric=True, digits=2,
        )
        grid.attach(self.amount_spin, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label=tr('Zieldatum (TT.MM.JJJJ, optional):'), xalign=0), 0, 2, 1, 1)
        self.date_entry = Gtk.Entry()
        self.date_entry.set_placeholder_text(tr('z. B. 31.12.2027'))
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
        super().__init__(parent, tr('Einzahlen: {0}').format(goal_name))
        grid = self.grid

        grid.attach(Gtk.Label(label=tr('Einzuzahlender Betrag (€):'), xalign=0), 0, 0, 1, 1)
        self.amount_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=50, lower=0.01, upper=1000000,
                                       step_increment=10, page_increment=50),
            numeric=True, digits=2,
        )
        grid.attach(self.amount_spin, 1, 0, 1, 1)

        self.book_check = Gtk.CheckButton(
            label=tr('Als Buchung im Haushaltsbuch verbuchen (Kategorie „Sparbeitrag“)')
        )
        self.book_check.set_active(True)
        grid.attach(self.book_check, 0, 1, 2, 1)

        hint = Gtk.Label(
            xalign=0,
            label=tr('Damit taucht die Einzahlung als Ausgabe im Kalender, in Budgets und Auswertungen auf – so wie das Geld tatsächlich vom Konto abgeht. Zum rein informativen Vormerken (z. B. externes Depot) kannst du das Häkchen entfernen.'),
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
        super().__init__(title=tr('Kategorien verwalten'), transient_for=parent, flags=0)
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
        self.tree_view.append_column(Gtk.TreeViewColumn(tr('Icon'), icon_renderer, text=1))
        name_renderer = Gtk.CellRendererText()
        self.tree_view.append_column(Gtk.TreeViewColumn(tr('Name'), name_renderer, text=2))
        kind_renderer = Gtk.CellRendererText()
        self.tree_view.append_column(Gtk.TreeViewColumn(tr('Art'), kind_renderer, text=3))

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        area.pack_start(btn_box, False, False, 6)

        add_btn = Gtk.Button(label=tr('Hinzufügen'))
        add_btn.connect("clicked", self._on_add)
        btn_box.pack_start(add_btn, False, False, 0)

        edit_btn = Gtk.Button(label=tr('Bearbeiten'))
        edit_btn.connect("clicked", self._on_edit)
        btn_box.pack_start(edit_btn, False, False, 0)

        del_btn = Gtk.Button(label=tr('Löschen'))
        del_btn.connect("clicked", self._on_delete)
        btn_box.pack_start(del_btn, False, False, 0)

        self._refresh()
        self.show_all()

    def _refresh(self):
        self.list_store.clear()
        for c in self.store.list_categories():
            self.list_store.append([
                c["id"], c["icon"], c["name"],
                tr('Einnahme') if c["kind"] == "einnahme" else tr('Ausgabe'),
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
            tr('Kategorie "{0}" wirklich löschen?').format(name),
            tr('Achtung: Dabei werden auch ALLE Buchungen und wiederkehrenden Vorlagen dieser Kategorie unwiderruflich gelöscht.'),
        )
        if response == Gtk.ResponseType.OK:
            self.store.delete_category(category_id)
            self._refresh()


class CategoryEditDialog(FormDialog):
    def __init__(self, parent, name="", icon="", edit_mode=False):
        title = tr('Kategorie bearbeiten') if edit_mode else tr('Kategorie hinzufügen')
        super().__init__(parent, title)
        self.set_default_size(380, 420)
        self.edit_mode = edit_mode
        grid = self.grid

        grid.attach(Gtk.Label(label=tr('Icon:'), xalign=0), 0, 0, 1, 1)
        icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.icon_entry = Gtk.Entry(text=icon or "💶")
        self.icon_entry.set_max_length(4)
        self.icon_entry.set_width_chars(4)
        icon_box.pack_start(self.icon_entry, False, False, 0)
        icon_box.pack_start(Gtk.Label(label=tr('aktuell ausgewählt'), xalign=0), False, False, 0)
        grid.attach(icon_box, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label=tr('Icon auswählen:'), xalign=0), 0, 1, 1, 1)
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

        hint = Gtk.Label(xalign=0, label=tr('Eigenes Emoji eintippen geht auch – z. B. über die Emoji-Tastatur mit Strg+.'))
        hint.set_line_wrap(True)
        grid.attach(hint, 0, 3, 2, 1)

        grid.attach(Gtk.Label(label=tr('Name:'), xalign=0), 0, 4, 1, 1)
        self.name_entry = Gtk.Entry(text=name)
        grid.attach(self.name_entry, 1, 4, 1, 1)

        if not edit_mode:
            grid.attach(Gtk.Label(label=tr('Art:'), xalign=0), 0, 5, 1, 1)
            self.kind_combo = Gtk.ComboBoxText()
            self.kind_combo.append("ausgabe", tr('Ausgabe'))
            self.kind_combo.append("einnahme", tr('Einnahme'))
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


class QuickTemplatesDialog(Gtk.Dialog):
    """Liste gespeicherter Schnellbuchungs-Vorlagen: per Doppelklick oder
    "Jetzt buchen" wird daraus eine Buchung am gewählten Datum; Vorlagen lassen
    sich löschen. (Neue Vorlagen entstehen über "Als Vorlage speichern" in der
    Buchungsliste.)"""

    def __init__(self, parent, store: FinanceStore, booking_date):
        super().__init__(title=tr("Aus Vorlage buchen"), transient_for=parent, flags=0)
        self.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        self.set_default_size(480, 360)
        self.store = store
        self.booking_date = booking_date
        self.booked = []

        area = self.get_content_area()
        area.set_spacing(8)
        area.set_border_width(10)
        area.pack_start(Gtk.Label(
            label=tr('Buchungsdatum: {0}').format(booking_date.strftime('%d.%m.%Y')), xalign=0),
            False, False, 0)

        # id, Name, Kategorie, Betrag
        self.model = Gtk.ListStore(int, str, str, str)
        self.view = Gtk.TreeView(model=self.model)
        for i, title in enumerate(("Name", tr('Kategorie'), tr('Betrag')), start=1):
            renderer = Gtk.CellRendererText()
            if title in ("Betrag", tr("Betrag")):
                renderer.set_property("xalign", 1.0)
            column = Gtk.TreeViewColumn(tr(title), renderer, text=i)
            column.set_resizable(True)
            if title == "Name":
                column.set_expand(True)
            self.view.append_column(column)
        self.view.connect("row-activated", lambda *a: self._book())
        scroller = Gtk.ScrolledWindow()
        scroller.set_shadow_type(Gtk.ShadowType.IN)
        scroller.add(self.view)
        area.pack_start(scroller, True, True, 0)

        self.hint = Gtk.Label(label="", xalign=0)
        self.hint.set_line_wrap(True)
        area.pack_start(self.hint, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        area.pack_start(buttons, False, False, 0)
        book_btn = Gtk.Button(label=tr('Jetzt buchen'))
        book_btn.connect("clicked", lambda w: self._book())
        buttons.pack_start(book_btn, False, False, 0)
        delete_btn = Gtk.Button(label=tr('Vorlage löschen'))
        delete_btn.connect("clicked", lambda w: self._delete())
        buttons.pack_start(delete_btn, False, False, 0)

        self._reload()
        self.show_all()

    def _reload(self):
        self.model.clear()
        templates = self.store.list_quick_templates()
        for t in templates:
            self.model.append([t["id"], t["name"], f"{t['icon']} {t['category_name']}",
                               fmt_amount(t["amount"])])
        self.hint.set_text("" if templates else
                           tr('Noch keine Vorlagen. Wähle in der Buchungsliste eine Buchung und klicke auf „Als Vorlage speichern“.'))

    def _selected_id(self):
        model, tree_iter = self.view.get_selection().get_selected()
        return model.get_value(tree_iter, 0) if tree_iter else None

    def _book(self):
        template_id = self._selected_id()
        if template_id is None:
            return
        template = next(t for t in self.store.list_quick_templates() if t["id"] == template_id)
        self.store.book_quick_template(template_id, self.booking_date.isoformat())
        self.booked.append({"category_id": template["category_id"],
                            "date": self.booking_date.isoformat(),
                            "amount": template["amount"]})
        self.hint.set_text(tr('„{0}“ gebucht ({1}).').format(template['name'], fmt_amount(template['amount'])))

    def _delete(self):
        template_id = self._selected_id()
        if template_id is not None:
            self.store.delete_quick_template(template_id)
            self._reload()


def main():
    win = MainWindow()
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
