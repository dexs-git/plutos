"""
Plutos – Erscheinungsbild der GTK-Version: Farben (hell/dunkel), CSS für das
ganze Programm, schlichte Linien-Icons (mit Cairo gezeichnet, es wird also
kein SVG-Loader benötigt) und die kleinen selbst gezeichneten Bausteine der
Übersichtsseite.

Die Farbwerte entsprechen bewusst denen der Qt-Version (qt/theme.py), damit
beide Oberflächen zusammenpassen.
"""

import math

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, Gio, Pango

from i18n import tr

TOKENS = {
    "dark": {
        "bg": "#12161C", "sidebar": "#0D1116", "card": "#1A2029", "card_alt": "#222A36",
        "input": "#141A22", "border": "#2A3342", "text": "#E8EBF0", "muted": "#8E97A6",
        "accent": "#D4A64A", "accent_text": "#1A1406", "accent_soft": "#2A2415",
        "positive": "#4CB782", "negative": "#E5645A", "warn": "#E8883A",
        "hover": "#212935",
    },
    "light": {
        "bg": "#F4F5F7", "sidebar": "#E9ECF1", "card": "#FFFFFF", "card_alt": "#F0F2F5",
        "input": "#FFFFFF", "border": "#DDE1E8", "text": "#18202D", "muted": "#5F6B7E",
        "accent": "#8F6410", "accent_text": "#FFFFFF", "accent_soft": "#F3E8CF",
        "positive": "#197A50", "negative": "#C93C32", "warn": "#B35F10",
        "hover": "#E3E7ED",
    },
}

_current_name = "dark"
_provider = None


def current():
    """Farb-Rollen des aktiven Themes."""
    return TOKENS[_current_name]


def current_name():
    return _current_name


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def system_prefers_dark():
    """Versucht herauszufinden, ob das System ein dunkles Design nutzt."""
    try:
        source = Gio.SettingsSchemaSource.get_default()
        if source and source.lookup("org.gnome.desktop.interface", True):
            gsettings = Gio.Settings.new("org.gnome.desktop.interface")
            keys = gsettings.list_keys()
            if "color-scheme" in keys:
                scheme = gsettings.get_string("color-scheme")
                if scheme == "prefer-dark":
                    return True
                if scheme == "prefer-light":
                    return False
            if "gtk-theme" in keys and "dark" in gsettings.get_string("gtk-theme").lower():
                return True
    except Exception:
        pass
    settings = Gtk.Settings.get_default()
    try:
        if settings.get_property("gtk-application-prefer-dark-theme"):
            return True
        return "dark" in (settings.get_property("gtk-theme-name") or "").lower()
    except Exception:
        return False


def build_css(t):
    return f"""
window, dialog, messagedialog, .background {{ background-color: {t['bg']}; color: {t['text']}; }}
label {{ color: {t['text']}; }}
label:disabled {{ color: {t['muted']}; }}
.muted {{ color: {t['muted']}; }}
.positive {{ color: {t['positive']}; }}
.negative {{ color: {t['negative']}; }}
.warn {{ color: {t['warn']}; }}
.page-title {{ font-size: 22px; font-weight: 700; }}
.section-title {{ color: {t['muted']}; font-weight: 600; font-size: 12px; }}
.card-title {{ color: {t['muted']}; font-weight: 600; font-size: 12px; }}
.kpi-value {{ font-size: 26px; font-weight: 600; }}
.kpi-sub {{ color: {t['muted']}; font-size: 12px; }}
.pace-amount {{ font-size: 18px; font-weight: 600; }}
.brand {{ font-size: 18px; font-weight: 700; }}

.sidebar {{ background-color: {t['sidebar']}; border-right: 1px solid {t['border']}; }}
.sidebar list, .sidebar row {{ background-color: transparent; }}
.nav row {{ padding: 8px 10px; margin: 1px 8px; border-radius: 8px; color: {t['text']};
           border: none; box-shadow: none; outline: none; }}
.nav row:hover {{ background-color: {t['hover']}; }}
.nav row:selected, .nav row:selected:hover {{ background-color: {t['accent_soft']}; }}
.nav row:selected label {{ color: {t['accent']}; font-weight: 600; }}

.card {{ background-color: {t['card']}; border: 1px solid {t['border']}; border-radius: 12px; }}
.card-inner {{ padding: 14px 18px 16px 18px; }}

button {{ background-image: none; background-color: {t['card_alt']}; color: {t['text']};
         border: 1px solid {t['border']}; border-radius: 8px; padding: 5px 14px;
         box-shadow: none; text-shadow: none; min-height: 22px; }}
button:hover {{ background-color: {t['hover']}; border-color: {t['muted']}; }}
button:active, button:checked {{ background-color: {t['accent_soft']}; border-color: {t['accent']}; }}
button:disabled {{ color: {t['muted']}; background-color: {t['card']}; }}
button label {{ color: inherit; }}
button.suggested-action, button.primary {{ background-color: {t['accent']}; color: {t['accent_text']};
         border-color: {t['accent']}; font-weight: 600; }}
button.suggested-action label, button.primary label {{ color: {t['accent_text']}; }}
button.suggested-action:hover, button.primary:hover {{ background-color: {t['accent']}; opacity: 0.9; }}
button.link-flat {{ background-color: transparent; border-color: transparent; color: {t['accent']};
         padding: 2px 4px; font-weight: 600; }}
button.link-flat label {{ color: {t['accent']}; }}
button.link-flat:hover {{ background-color: {t['accent_soft']}; }}
button.flat {{ background-color: transparent; border-color: transparent; }}
button.flat:hover {{ background-color: {t['hover']}; }}

entry, spinbutton, textview text, .view {{ background-color: {t['input']}; color: {t['text']}; }}
entry, spinbutton {{ border: 1px solid {t['border']}; border-radius: 8px; padding: 4px 8px;
         box-shadow: none; background-image: none; min-height: 22px; }}
entry:focus, spinbutton:focus {{ border-color: {t['accent']}; box-shadow: none; }}
entry:disabled, spinbutton:disabled {{ color: {t['muted']}; background-color: {t['card_alt']}; }}
spinbutton entry {{ border: none; padding: 0; min-height: 0; background-color: transparent; }}
spinbutton button {{ border: none; background-color: transparent; padding: 0 6px; min-height: 0;
         border-radius: 6px; }}
spinbutton button:hover {{ background-color: {t['hover']}; }}
combobox button.combo, combobox button {{ padding: 5px 10px; }}
combobox arrow {{ color: {t['muted']}; }}

treeview, treeview.view {{ background-color: {t['card']}; color: {t['text']}; }}
treeview.view:selected, treeview.view:selected:focus {{ background-color: {t['accent_soft']}; color: {t['text']}; }}
treeview.view:hover {{ background-color: {t['hover']}; }}
treeview.view header button {{ background-color: {t['bg']}; color: {t['muted']}; font-weight: 600;
         border: none; border-bottom: 1px solid {t['border']}; border-radius: 0; padding: 8px 10px; }}
treeview.view header button:hover {{ background-color: {t['hover']}; }}
flowboxchild {{ padding: 0; background-color: transparent; outline: none; }}
scrolledwindow.frame {{ border: 1px solid {t['border']}; border-radius: 10px; }}
scrolledwindow {{ border-color: {t['border']}; }}
separator {{ background-color: {t['border']}; min-height: 1px; min-width: 1px; }}

scrollbar {{ background-color: transparent; border: none; }}
scrollbar slider {{ background-color: {t['border']}; border-radius: 5px; min-width: 8px; min-height: 8px;
         border: 2px solid transparent; background-clip: padding-box; }}
scrollbar slider:hover {{ background-color: {t['muted']}; }}
scrollbar button {{ min-width: 0; min-height: 0; border: none; background: transparent; }}

check, radio {{ background-image: none; background-color: {t['input']}; border: 1px solid {t['border']};
         box-shadow: none; min-width: 18px; min-height: 18px; color: {t['accent_text']}; }}
check {{ border-radius: 5px; }}
radio {{ border-radius: 9px; }}
check:checked, radio:checked, check:indeterminate {{ background-color: {t['accent']}; border-color: {t['accent']}; }}
switch {{ background-color: {t['card_alt']}; border: 1px solid {t['border']}; color: {t['text']}; }}
switch:checked {{ background-color: {t['accent']}; color: {t['accent_text']}; }}
switch slider {{ background-color: {t['text']}; border: none; }}

frame > label {{ color: {t['muted']}; font-weight: 600; font-size: 12px; padding: 0 6px 8px 6px; }}
frame > border {{ background-color: {t['card']}; border: 1px solid {t['border']}; border-radius: 12px; }}
.trough, trough {{ background-color: {t['card_alt']}; background-image: none; border: none; border-radius: 4px; min-height: 8px; }}
.progressbar, progress, treeview.progressbar {{ background-color: {t['accent']}; background-image: none; border: none;
         border-radius: 4px; min-height: 8px; color: {t['text']}; }}
progressbar trough {{ background-color: {t['card_alt']}; border: none; border-radius: 4px; min-height: 8px; }}
progressbar progress {{ background-color: {t['accent']}; background-image: none; border: none;
         border-radius: 4px; min-height: 8px; }}
levelbar trough {{ background-color: {t['card_alt']}; border: none; border-radius: 4px; }}

menu, .popup, popover, popover.background {{ background-color: {t['card']}; color: {t['text']};
         border: 1px solid {t['border']}; border-radius: 8px; }}
menuitem {{ color: {t['text']}; padding: 5px 10px; }}
menuitem:hover {{ background-color: {t['hover']}; }}
tooltip, tooltip.background {{ background-color: {t['card_alt']}; color: {t['text']};
         border: 1px solid {t['border']}; border-radius: 6px; }}
tooltip label {{ color: {t['text']}; }}
notebook > header {{ background-color: {t['bg']}; border-color: {t['border']}; }}
notebook > header > tabs > tab {{ color: {t['muted']}; }}
notebook > header > tabs > tab:checked {{ color: {t['accent']}; }}
calendar {{ background-color: {t['card']}; color: {t['text']}; border-color: {t['border']}; }}
calendar:selected {{ background-color: {t['accent']}; color: {t['accent_text']}; }}
.help-button {{ border-radius: 13px; padding: 0; min-width: 26px; min-height: 26px;
         color: {t['muted']}; background-color: transparent; }}
"""


def apply_theme(mode="system"):
    """mode: "system", "light" oder "dark". Setzt das CSS für das ganze
    Programm und teilt GTK mit, ob eingebaute Elemente (Dateidialog,
    Menüs …) dunkel gezeichnet werden sollen."""
    global _current_name, _provider
    dark = system_prefers_dark() if mode == "system" else mode == "dark"
    _current_name = "dark" if dark else "light"
    settings = Gtk.Settings.get_default()
    try:
        settings.set_property("gtk-application-prefer-dark-theme", dark)
    except Exception:
        pass
    screen = Gdk.Screen.get_default()
    if _provider is not None:
        Gtk.StyleContext.remove_provider_for_screen(screen, _provider)
    _provider = Gtk.CssProvider()
    _provider.load_from_data(build_css(current()).encode("utf-8"))
    Gtk.StyleContext.add_provider_for_screen(
        screen, _provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)


# ---------------------------------------------------------------------------
# Icons (mit Cairo gezeichnet; Raster 24 × 24)
# ---------------------------------------------------------------------------

def _rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _poly(cr, points):
    cr.move_to(*points[0])
    for p in points[1:]:
        cr.line_to(*p)


def _icon_overview(cr):
    for x, y in ((3, 3), (13.5, 3), (3, 13.5), (13.5, 13.5)):
        _rrect(cr, x, y, 7.5, 7.5, 2)


def _icon_bookings(cr):
    _rrect(cr, 3, 5, 18, 16, 3)
    _poly(cr, [(3, 10), (21, 10)])
    _poly(cr, [(8, 3), (8, 7)])
    _poly(cr, [(16, 3), (16, 7)])


def _icon_budgets(cr):
    cr.new_sub_path()
    cr.arc(12, 17, 8, math.pi, 2 * math.pi)
    _poly(cr, [(12, 17), (15.5, 12)])


def _icon_goals(cr):
    for r in (9, 5):
        cr.new_sub_path()
        cr.arc(12, 12, r, 0, 2 * math.pi)
    cr.new_sub_path()
    cr.arc(12, 12, 1.2, 0, 2 * math.pi)


def _icon_planning(cr):
    _poly(cr, [(3, 17), (9, 11), (13, 15), (21, 6)])
    _poly(cr, [(15, 6), (21, 6), (21, 12)])


def _icon_etf(cr):
    _rrect(cr, 4.5, 12, 3.5, 8, 1)
    _rrect(cr, 10.25, 8, 3.5, 12, 1)
    _rrect(cr, 16, 4, 3.5, 16, 1)


def _icon_stats(cr):
    cr.new_sub_path()
    cr.arc(12, 12, 9, 0, 2 * math.pi)
    _poly(cr, [(12, 3), (12, 12), (21, 12)])


def _icon_search(cr):
    cr.new_sub_path()
    cr.arc(11, 11, 6.5, 0, 2 * math.pi)
    _poly(cr, [(16, 16), (21, 21)])


def _icon_export(cr):
    _poly(cr, [(12, 4), (12, 15)])
    _poly(cr, [(8, 11), (12, 15), (16, 11)])
    _poly(cr, [(5, 20), (19, 20)])


ICONS = {
    "overview": _icon_overview, "bookings": _icon_bookings, "budgets": _icon_budgets,
    "goals": _icon_goals, "planning": _icon_planning, "etf": _icon_etf,
    "stats": _icon_stats, "search": _icon_search, "export": _icon_export,
}


def draw_icon(cr, name, rgb, size):
    cr.save()
    cr.scale(size / 24.0, size / 24.0)
    cr.set_source_rgb(*rgb)
    cr.set_line_width(1.8)
    cr.set_line_cap(1)   # ROUND
    cr.set_line_join(1)  # ROUND
    ICONS[name](cr)
    cr.stroke()
    cr.restore()


class NavIcon(Gtk.DrawingArea):
    """Icon einer Seitenleisten-Zeile; die Farbe folgt dem Zustand der Zeile."""

    def __init__(self, name, row, size=20):
        super().__init__()
        self.name = name
        self.row = row
        self.size = size
        self.set_size_request(size, size)
        self.connect("draw", self._on_draw)

    def _on_draw(self, widget, cr):
        t = current()
        key = "accent" if self.row.is_selected() else "muted"
        draw_icon(cr, self.name, hex_to_rgb(t[key]), self.size)
        return False


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------

def make_card(spacing=6):
    """Gibt (Rahmen, inneres Layout) zurück."""
    frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    frame.get_style_context().add_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    inner.get_style_context().add_class("card-inner")
    frame.pack_start(inner, True, True, 0)
    return frame, inner


def make_label(text, css_class=None, xalign=0.0, wrap=False):
    label = Gtk.Label(label=text, xalign=xalign)
    if css_class:
        label.get_style_context().add_class(css_class)
    if wrap:
        label.set_line_wrap(True)
        label.set_max_width_chars(10)
    return label


def make_link_button(text, callback):
    btn = Gtk.Button(label=text)
    btn.get_style_context().add_class("link-flat")
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.connect("clicked", lambda w: callback())
    return btn


def _rounded(cr, x, y, w, h, r):
    r = min(r, h / 2, w / 2)
    _rrect(cr, x, y, w, h, r)


class ProgressRow(Gtk.Box):
    """Eine Zeile „Name … Betrag“ mit schlankem Balken darunter."""

    def __init__(self, name, right_text, fraction, color):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.fraction = max(0.0, min(1.0, fraction))
        self.color = color
        row = Gtk.Box(spacing=8)
        left = Gtk.Label(label=name, xalign=0.0)
        left.set_ellipsize(Pango.EllipsizeMode.END)
        right = Gtk.Label(label=right_text, xalign=1.0)
        right.get_style_context().add_class("muted")
        row.pack_start(left, True, True, 0)
        row.pack_end(right, False, False, 0)
        self.pack_start(row, False, False, 0)
        self.bar = Gtk.DrawingArea()
        self.bar.set_size_request(-1, 6)
        self.bar.connect("draw", self._draw_bar)
        self.pack_start(self.bar, False, False, 2)

    def _draw_bar(self, widget, cr):
        t = current()
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        cr.set_source_rgb(*hex_to_rgb(t["card_alt"]))
        _rounded(cr, 0, 0, w, h, 3)
        cr.fill()
        if self.fraction > 0:
            cr.set_source_rgb(*hex_to_rgb(self.color))
            _rounded(cr, 0, 0, max(6.0, w * self.fraction), h, 3)
            cr.fill()
        return False


def _text(cr, widget, text, size_px, rgb, x, y, align="left", width=0):
    layout = widget.create_pango_layout(text)
    desc = Pango.FontDescription()
    desc.set_absolute_size(size_px * Pango.SCALE)
    layout.set_font_description(desc)
    tw, th = layout.get_pixel_size()
    if align == "center":
        x = x + (width - tw) / 2
    elif align == "right":
        x = x + width - tw
    cr.set_source_rgb(*rgb)
    cr.move_to(x, y)
    from gi.repository import PangoCairo
    PangoCairo.show_layout(cr, layout)
    return tw, th


class PaceBar(Gtk.DrawingArea):
    """Ausgabentempo: wie viel vom üblichen Monatsbetrag ist ausgegeben,
    verglichen mit dem Stand des Monats (Marke „heute“)."""

    def __init__(self):
        super().__init__()
        self.spent_fraction = 0.0
        self.elapsed_fraction = 0.0
        self.set_size_request(-1, 46)
        self.connect("draw", self._draw)

    def set_values(self, spent_fraction, elapsed_fraction):
        self.spent_fraction = max(0.0, spent_fraction)
        self.elapsed_fraction = max(0.0, min(1.0, elapsed_fraction))
        self.queue_draw()

    def _draw(self, widget, cr):
        t = current()
        w = widget.get_allocated_width()
        bar_top, bar_h = 22, 14
        cr.set_source_rgb(*hex_to_rgb(t["card_alt"]))
        _rounded(cr, 0, bar_top, w, bar_h, 7)
        cr.fill()
        ratio = self.spent_fraction
        if ratio <= self.elapsed_fraction + 0.05:
            color = t["accent"]
        elif ratio <= 1.0:
            color = t["warn"]
        else:
            color = t["negative"]
        fill_w = min(1.0, ratio) * w
        if fill_w > 0:
            cr.set_source_rgb(*hex_to_rgb(color))
            _rounded(cr, 0, bar_top, max(14.0, fill_w), bar_h, 7)
            cr.fill()
        x = min(max(self.elapsed_fraction * w, 1.0), w - 1.0)
        cr.set_source_rgb(*hex_to_rgb(t["text"]))
        cr.set_line_width(2)
        cr.move_to(x, bar_top - 5)
        cr.line_to(x, bar_top + bar_h + 5)
        cr.stroke()
        label = tr("heute")
        layout = widget.create_pango_layout(label)
        desc = Pango.FontDescription()
        desc.set_absolute_size(11 * Pango.SCALE)
        layout.set_font_description(desc)
        lw, _lh = layout.get_pixel_size()
        _text(cr, widget, label, 11, hex_to_rgb(t["muted"]), min(max(x - lw / 2, 0), w - lw), 0)
        return False


class MiniTrend(Gtk.DrawingArea):
    """Einnahmen/Ausgaben der letzten Monate als schlanke Doppelbalken."""

    def __init__(self):
        super().__init__()
        self.rows = []  # (label, income, expense, is_current)
        self.set_size_request(-1, 150)
        self.set_vexpand(True)
        self.connect("draw", self._draw)

    def set_rows(self, rows):
        self.rows = rows
        self.queue_draw()

    def _draw(self, widget, cr):
        t = current()
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        if not self.rows or max(max(r[1], r[2]) for r in self.rows) <= 0:
            _text(cr, widget, tr("Noch keine Buchungen."), 12, hex_to_rgb(t["muted"]),
                  0, h / 2 - 8, "center", w)
            return False
        top_pad, bottom_pad = 8, 20
        plot_h = h - top_pad - bottom_pad
        peak = max(max(r[1], r[2]) for r in self.rows)
        slot = w / len(self.rows)
        bar_w = min(16.0, slot * 0.28)
        for i, (label, income, expense, is_current) in enumerate(self.rows):
            cx = slot * i + slot / 2
            for k, (value, color) in enumerate(((income, t["positive"]), (expense, t["accent"]))):
                bh = plot_h * value / peak
                x = cx - bar_w - 1 + k * (bar_w + 2)
                cr.set_source_rgba(*hex_to_rgb(color), 1.0 if is_current else 0.6)
                _rounded(cr, x, top_pad + plot_h - bh, bar_w, max(bh, 1.5), 3)
                cr.fill()
            _text(cr, widget, label, 11,
                  hex_to_rgb(t["text"] if is_current else t["muted"]),
                  slot * i, h - bottom_pad + 3, "center", slot)
        return False
