"""Design-System der Qt-Version: Farben, Stylesheet, Icons und kleine
Bausteine (Karten, Kennzahlen, Fortschrittsbalken) für die Übersichtsseite.

Gestaltungsidee: ruhige, flache Flächen (Karten mit feiner Linie statt
Schatten), eine einzige Akzentfarbe in Messing – passend zu Plutos, dem Gott
des Reichtums – und die Signalfarben Grün/Rot/Orange nur dort, wo sie etwas
bedeuten (Einnahme, Ausgabe, Budget-Warnung). Hell und Dunkel teilen sich
dieselben Rollen (siehe TOKENS)."""
import datetime

from PySide6.QtCore import Qt, QRectF, QSize, QByteArray, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QPixmap, QIcon, QPalette, QFont, QFontMetrics,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QPushButton,
)

from i18n import tr

# ---------------------------------------------------------------------------
# Farb-Rollen
# ---------------------------------------------------------------------------

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


def current():
    """Farb-Rollen des aktiven Themes."""
    return TOKENS[_current_name]


def current_name():
    return _current_name


def system_prefers_dark(app):
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:  # ältere Qt-Versionen
        return app.palette().window().color().lightness() < 128


def _check_icon(t):
    """Schreibt das Häkchen-Icon für Checkboxen in den Cache-Ordner und gibt
    den Pfad (mit Schrägstrichen, wie QSS ihn braucht) zurück."""
    import os
    import tempfile
    path = os.path.join(tempfile.gettempdir(), f"plutos-check-{t['accent'].lstrip('#')}.svg")
    if not os.path.exists(path):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7" '
               f'fill="none" stroke="{t["accent_text"]}" stroke-width="2" stroke-linecap="round" '
               'stroke-linejoin="round"/></svg>')
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg)
        except OSError:
            pass
    return path.replace("\\", "/")


def _arrow_icon(t, direction):
    import os
    import tempfile
    path = os.path.join(tempfile.gettempdir(), f"plutos-arrow-{direction}-{t['muted'].lstrip('#')}.svg")
    if not os.path.exists(path):
        d = "M3 6l5 5 5-5" if direction == "down" else "M3 10l5-5 5 5"
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="%s" fill="none" '
               'stroke="%s" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
               % (d, t["muted"]))
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg)
        except OSError:
            pass
    return path.replace("\\", "/")


def build_stylesheet(t):
    return f"""
* {{ font-family: "Inter", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text",
     "Helvetica Neue", "Noto Sans", "Cantarell", sans-serif; }}
QMainWindow, QDialog {{ background: {t['bg']}; }}
QWidget {{ color: {t['text']}; font-size: 13px; }}
QWidget#pages, QTabWidget::pane {{ background: {t['bg']}; border: none; }}
QStackedWidget {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QToolTip {{ background: {t['card_alt']}; color: {t['text']}; border: 1px solid {t['border']};
            padding: 5px 8px; border-radius: 6px; }}

/* Seitenleiste */
QFrame#sidebar {{ background: {t['sidebar']}; border: none; }}
QLabel#brand {{ font-size: 18px; font-weight: 700; letter-spacing: 0.3px; color: {t['text']}; }}
QLabel#brandSub {{ font-size: 11px; color: {t['muted']}; }}
QListWidget#nav {{ background: transparent; border: none; outline: none; }}
QListWidget#nav::item {{ padding: 9px 12px; margin: 1px 0; border-radius: 9px;
                         color: {t['muted']}; }}
QListWidget#nav::item:hover {{ background: {t['hover']}; color: {t['text']}; }}
QListWidget#nav::item:selected {{ background: {t['accent_soft']}; color: {t['accent']};
                                  font-weight: 600; }}

/* Karten und Gruppen */
QFrame#card {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 12px; }}
QFrame#card QLabel {{ background: transparent; }}
QLabel#cardTitle {{ font-size: 12px; color: {t['muted']}; font-weight: 600; }}
QLabel#kpiValue {{ font-size: 26px; font-weight: 600; }}
QLabel#kpiSub {{ font-size: 12px; color: {t['muted']}; }}
QLabel#pageTitle {{ font-size: 22px; font-weight: 700; }}
QLabel#muted {{ color: {t['muted']}; font-size: 12px; }}
QLabel#positive {{ color: {t['positive']}; }}
QLabel#negative {{ color: {t['negative']}; }}

QGroupBox {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 12px;
             margin-top: 28px; padding: 10px 14px 12px 14px; font-weight: 400; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left;
                    left: 4px; top: 2px; padding: 0 2px; color: {t['text']};
                    font-size: 14px; font-weight: 600; }}
QGroupBox QLabel {{ background: transparent; }}

/* Eingabefelder */
QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QTextEdit, QPlainTextEdit {{
    background: {t['input']}; border: 1px solid {t['border']}; border-radius: 8px;
    padding: 5px 9px; min-height: 20px; selection-background-color: {t['accent']};
    selection-color: {t['accent_text']}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus {{
    border: 1px solid {t['accent']}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {t['muted']}; background: {t['card_alt']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{_arrow_icon(t, 'down')}"); width: 12px; height: 12px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{_arrow_icon(t, 'up')}"); width: 9px; height: 9px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{_arrow_icon(t, 'down')}"); width: 9px; height: 9px; }}
QSpinBox, QDoubleSpinBox, QDateEdit {{ min-width: 150px; max-width: 280px; qproperty-alignment: AlignCenter; }}
QComboBox QAbstractItemView {{ background: {t['card']}; border: 1px solid {t['border']};
    selection-background-color: {t['accent_soft']}; selection-color: {t['accent']};
    outline: none; padding: 4px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button,
QDoubleSpinBox::down-button, QDateEdit::up-button, QDateEdit::down-button {{
    width: 20px; border: none; background: transparent; }}

/* Buttons */
QPushButton {{ background: {t['card_alt']}; border: 1px solid {t['border']}; border-radius: 8px;
               padding: 6px 14px; min-height: 20px; }}
QPushButton:hover {{ border-color: {t['accent']}; }}
QPushButton:pressed {{ background: {t['hover']}; }}
QPushButton:disabled {{ color: {t['muted']}; background: transparent; }}
QPushButton:default {{ border-color: {t['accent']}; }}
QPushButton[primary="true"] {{ background: {t['accent']}; color: {t['accent_text']};
                               border: 1px solid {t['accent']}; font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {t['accent']}; border-color: {t['text']}; }}
QPushButton[link="true"] {{ background: transparent; border: none; color: {t['accent']};
                            padding: 2px 4px; font-weight: 600; }}
QPushButton[link="true"]:hover {{ text-decoration: underline; }}
QPushButton[nav="true"] {{ padding: 4px 10px; min-width: 18px; }}

/* Tabellen und Listen */
QTableWidget, QTableView, QListWidget, QTreeWidget {{
    background: {t['card']}; alternate-background-color: {t['card']};
    border: 1px solid {t['border']}; border-radius: 10px; gridline-color: {t['border']};
    selection-background-color: {t['accent_soft']}; selection-color: {t['text']};
    outline: none; }}
QTableWidget::item, QListWidget::item {{ padding: 5px 8px; border: none; }}
QTableWidget::item:selected, QListWidget::item:selected {{
    background: {t['accent_soft']}; color: {t['text']}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {t['card']}; color: {t['muted']}; border: none;
    border-bottom: 1px solid {t['border']}; padding: 7px 8px; font-weight: 600; font-size: 12px; }}
QTableCornerButton::section {{ background: {t['card']}; border: none; }}

/* Fortschrittsbalken */
QProgressBar {{ background: {t['card_alt']}; border: none; border-radius: 6px;
                text-align: center; min-height: 18px; color: {t['text']}; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 6px; }}

/* Checkboxen, Kalender */
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1.5px solid {t['muted']};
                        border-radius: 5px; background: {t['input']}; }}
QCheckBox::indicator:hover {{ border-color: {t['accent']}; }}
QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']};
                                image: url("{_check_icon(t)}"); }}
QCheckBox::indicator:disabled {{ border-color: {t['border']}; background: {t['card_alt']}; }}
QCalendarWidget QWidget {{ alternate-background-color: {t['card']}; }}
QCalendarWidget QAbstractItemView {{ background: {t['card']}; selection-background-color: {t['accent']};
    selection-color: {t['accent_text']}; outline: none; }}
QCalendarWidget QToolButton {{ background: transparent; border: none; border-radius: 8px;
    padding: 4px 10px; color: {t['text']}; font-weight: 600; }}
QCalendarWidget QToolButton:hover {{ background: {t['hover']}; }}
QCalendarWidget #qt_calendar_navigationbar {{ background: {t['card']}; }}

/* Scrollleisten */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t['muted']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['border']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {t['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QMessageBox {{ background: {t['bg']}; }}
"""


def apply_theme(app, mode="system"):
    """mode: "system", "light" oder "dark"."""
    global _current_name
    dark = system_prefers_dark(app) if mode == "system" else mode == "dark"
    _current_name = "dark" if dark else "light"
    t = current()
    app.setStyle("Fusion")
    pal = QPalette()
    for role, key in [
        (QPalette.Window, "bg"), (QPalette.WindowText, "text"), (QPalette.Base, "card"),
        (QPalette.AlternateBase, "card"), (QPalette.Text, "text"), (QPalette.Button, "card_alt"),
        (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "card_alt"),
        (QPalette.ToolTipText, "text"), (QPalette.Highlight, "accent"),
        (QPalette.HighlightedText, "accent_text"), (QPalette.Link, "accent"),
        (QPalette.PlaceholderText, "muted"),
    ]:
        pal.setColor(role, QColor(t[key]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(t["muted"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(t["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(build_stylesheet(t))


# ---------------------------------------------------------------------------
# Icons (eigene, schlichte Linien-Icons; Farbe folgt dem Theme)
# ---------------------------------------------------------------------------

_ICON_BODY = {
    "overview": '<rect x="3" y="3" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/>'
                '<rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2"/>',
    "bookings": '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "budgets": '<path d="M4 17a8 8 0 1 1 16 0"/><path d="M12 17l3.5-5"/>',
    "goals": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1" fill="currentColor"/>',
    "planning": '<path d="M3 17l6-6 4 4 8-9"/><path d="M15 6h6v6"/>',
    "etf": '<rect x="4.5" y="12" width="3.5" height="8" rx="1"/><rect x="10.25" y="8" width="3.5" height="12" rx="1"/>'
           '<rect x="16" y="4" width="3.5" height="16" rx="1"/>',
    "stats": '<circle cx="12" cy="12" r="9"/><path d="M12 3v9h9"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l5 5"/>',
    "export": '<path d="M12 4v11M8 11l4 4 4-4M5 20h14"/>',
}


def make_icon(name, color, size=20):
    body = _ICON_BODY[name].replace("currentColor", color)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    scale = 2  # scharf auf HiDPI
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------

def make_card(parent=None):
    frame = QFrame(parent)
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 14, 18, 16)
    layout.setSpacing(6)
    return frame, layout


def set_role(label, role):
    """Setzt die Rolle (Farbe) eines Labels über seinen objectName."""
    label.setObjectName(role)
    label.style().unpolish(label)
    label.style().polish(label)


def make_link_button(text, callback):
    btn = QPushButton(text)
    btn.setProperty("link", True)
    btn.setCursor(Qt.PointingHandCursor)
    btn.clicked.connect(callback)
    return btn


class ProgressRow(QWidget):
    """Eine Zeile "Name … Betrag" mit schlankem Balken darunter."""

    def __init__(self, name, right_text, fraction, color, parent=None):
        super().__init__(parent)
        self.fraction = max(0.0, min(1.0, fraction))
        self.color = QColor(color)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        left = QLabel(name)
        right = QLabel(right_text)
        right.setObjectName("muted")
        row.addWidget(left, 1)
        row.addWidget(right, 0)
        layout.addLayout(row)
        self.bar = QWidget()
        self.bar.setFixedHeight(6)
        self.bar.paintEvent = self._paint_bar
        layout.addWidget(self.bar)

    def _paint_bar(self, event):
        t = current()
        p = QPainter(self.bar)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.bar.width(), self.bar.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["card_alt"]))
        p.drawRoundedRect(r, 3, 3)
        if self.fraction > 0:
            p.setBrush(self.color)
            p.drawRoundedRect(QRectF(0, 0, max(6.0, r.width() * self.fraction), r.height()), 3, 3)
        p.end()


class PaceBar(QWidget):
    """Ausgabentempo: wie viel vom üblichen Monatsbetrag ist ausgegeben,
    verglichen mit dem Stand des Monats (Marke „heute“)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.spent_fraction = 0.0
        self.elapsed_fraction = 0.0
        self.setFixedHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_values(self, spent_fraction, elapsed_fraction):
        self.spent_fraction = max(0.0, spent_fraction)
        self.elapsed_fraction = max(0.0, min(1.0, elapsed_fraction))
        self.update()

    def paintEvent(self, event):
        t = current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        bar_top, bar_h = 22, 14
        track = QRectF(0, bar_top, w, bar_h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["card_alt"]))
        p.drawRoundedRect(track, 7, 7)
        ratio = self.spent_fraction
        if ratio <= self.elapsed_fraction + 0.05:
            color = QColor(t["accent"])
        elif ratio <= 1.0:
            color = QColor(t["warn"])
        else:
            color = QColor(t["negative"])
        fill_w = min(1.0, ratio) * w
        if fill_w > 0:
            p.setBrush(color)
            p.drawRoundedRect(QRectF(0, bar_top, max(14.0, fill_w), bar_h), 7, 7)
        # Marke für den heutigen Stand des Monats
        x = self.elapsed_fraction * w
        x = min(max(x, 1.0), w - 1.0)
        pen = QPen(QColor(t["text"]), 2)
        p.setPen(pen)
        p.drawLine(int(x), bar_top - 5, int(x), bar_top + bar_h + 5)
        font = QFont(self.font())
        font.setPixelSize(11)
        p.setFont(font)
        p.setPen(QColor(t["muted"]))
        label = tr("heute")
        fm = QFontMetrics(font)
        lw = fm.horizontalAdvance(label)
        lx = min(max(x - lw / 2, 0), w - lw)
        p.drawText(int(lx), 12, label)
        p.end()


class MiniTrend(QWidget):
    """Einnahmen/Ausgaben der letzten Monate als schlanke Doppelbalken."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []  # (label, income, expense, is_current)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_rows(self, rows):
        self.rows = rows
        self.update()

    def paintEvent(self, event):
        t = current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if not self.rows or max(max(r[1], r[2]) for r in self.rows) <= 0:
            p.setPen(QColor(t["muted"]))
            p.drawText(self.rect(), Qt.AlignCenter, tr("Noch keine Buchungen."))
            p.end()
            return
        top_pad, bottom_pad = 8, 20
        plot_h = h - top_pad - bottom_pad
        peak = max(max(r[1], r[2]) for r in self.rows)
        slot = w / len(self.rows)
        bar_w = min(16.0, slot * 0.28)
        font = QFont(self.font())
        font.setPixelSize(11)
        p.setFont(font)
        p.setPen(Qt.NoPen)
        for i, (label, income, expense, is_current) in enumerate(self.rows):
            cx = slot * i + slot / 2
            for k, (value, color) in enumerate(((income, t["positive"]), (expense, t["accent"]))):
                bh = plot_h * value / peak
                x = cx - bar_w - 1 + k * (bar_w + 2)
                c = QColor(color)
                if not is_current:
                    c.setAlpha(150)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(x, top_pad + plot_h - bh, bar_w, max(bh, 1.5)), 3, 3)
            p.setPen(QColor(t["text"] if is_current else t["muted"]))
            p.drawText(QRectF(slot * i, h - bottom_pad + 4, slot, 16), Qt.AlignCenter, label)
            p.setPen(Qt.NoPen)
        p.end()


class BarCell(QWidget):
    """Schlanker Fortschrittsbalken mit Prozentzahl für Tabellenzellen."""

    def __init__(self, percent, color, parent=None):
        super().__init__(parent)
        self.percent = max(0, min(100, percent))
        self.color = QColor(color)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(8)
        self.bar = QWidget()
        self.bar.setFixedHeight(6)
        self.bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.bar.paintEvent = self._paint_bar
        label = QLabel(f"{self.percent} %")
        label.setObjectName("muted")
        label.setFixedWidth(40)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.bar, 1, Qt.AlignVCenter)
        layout.addWidget(label)

    def _paint_bar(self, event):
        t = current()
        p = QPainter(self.bar)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.bar.width(), self.bar.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["card_alt"]))
        p.drawRoundedRect(r, 3, 3)
        if self.percent > 0:
            p.setBrush(self.color)
            p.drawRoundedRect(QRectF(0, 0, max(6.0, r.width() * self.percent / 100), r.height()), 3, 3)
        p.end()
