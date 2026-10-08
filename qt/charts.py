"""
Eigene Diagramm-Widgets für die Qt-Variante von HaushaltsBuch.

Ersetzt die Cairo-Draw-Callbacks der GTK-Version durch QWidget.paintEvent()
mit QPainter. Die Farbpalette und Berechnungslogik (color_for_index,
fmt_amount) sind bewusst identisch zur GTK-Version gehalten, damit beide
Varianten optisch/inhaltlich gleich bleiben.
"""

import datetime

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath
from PySide6.QtCore import Qt, QRectF

CURRENCY = "€"

CATEGORY_COLORS = [
    QColor(51, 120, 191), QColor(217, 94, 33), QColor(43, 161, 87),
    QColor(148, 51, 191), QColor(230, 158, 0), QColor(33, 150, 168),
    QColor(191, 46, 92), QColor(102, 102, 102), QColor(89, 179, 230),
    QColor(242, 204, 51),
]

GREEN = QColor(30, 140, 61)
RED = QColor(191, 56, 38)


def fmt_amount(value):
    return f"{value:,.2f} {CURRENCY}".replace(",", "X").replace(".", ",").replace("X", ".")


def color_for_index(i):
    return CATEGORY_COLORS[i % len(CATEGORY_COLORS)]


class _BaseChart(QWidget):
    """Gemeinsame Basis: liefert die themen-adaptive Vordergrundfarbe (hell/
    dunkel) und eine "keine Daten"-Anzeige, damit das nicht in jedem Chart
    einzeln dupliziert werden muss."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def _fg_color(self):
        return self.palette().text().color()

    def _draw_empty_message(self, painter, text):
        painter.setPen(self._fg_color())
        painter.drawText(self.rect(), Qt.AlignCenter, text)


class PieChartWidget(_BaseChart):
    """Kreisdiagramm: Ausgaben nach Kategorie für einen Monat."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []  # Liste von (label, icon, value, QColor)

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.data:
            self._draw_empty_message(painter, "Keine Ausgaben in diesem Monat.")
            return

        width, height = self.width(), self.height()
        total = sum(v for _, _, v, _ in self.data)

        cx, cy = width * 0.30, height / 2
        radius = max(10, min(cx, cy) - 20)

        start_angle = 90 * 16  # Qt-Winkel in 1/16 Grad, Start oben (12 Uhr)
        for label, icon, value, color in self.data:
            fraction = value / total if total else 0
            span = -fraction * 360 * 16
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawPie(QRectF(cx - radius, cy - radius, radius * 2, radius * 2),
                             int(start_angle), int(span))
            start_angle += span

        legend_x = width * 0.58
        legend_y = 16
        line_h = 24
        fg = self._fg_color()
        for i, (label, icon, value, color) in enumerate(self.data):
            y = legend_y + i * line_h
            if y > height - 12:
                painter.setPen(fg)
                painter.drawText(int(legend_x), int(y), "…")
                break
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawRect(int(legend_x), int(y), 14, 14)
            painter.setPen(fg)
            pct = (value / total * 100) if total else 0
            painter.drawText(int(legend_x + 20), int(y + 12),
                              f"{icon} {label}: {fmt_amount(value)} ({pct:.0f}%)")


class TrendChartWidget(_BaseChart):
    """Gruppiertes Balkendiagramm: Einnahmen (grün) vs. Ausgaben (rot) über
    mehrere Monate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []  # Liste von dicts {month, income, expense}

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.data:
            self._draw_empty_message(painter, "Keine Daten.")
            return

        width, height = self.width(), self.height()
        fg = self._fg_color()

        margin_left, margin_right = 70, 20
        margin_top, margin_bottom = 20, 34
        plot_w = max(10, width - margin_left - margin_right)
        plot_h = max(10, height - margin_top - margin_bottom)

        max_val = max([d["income"] for d in self.data] + [d["expense"] for d in self.data] + [1])

        pen = QPen(fg)
        pen.setColor(QColor(fg.red(), fg.green(), fg.blue(), 110))
        painter.setPen(pen)
        painter.drawLine(margin_left, margin_top, margin_left, height - margin_bottom)
        painter.drawLine(margin_left, height - margin_bottom, width - margin_right,
                          height - margin_bottom)

        label_pen = QPen(QColor(fg.red(), fg.green(), fg.blue(), 190))
        painter.setPen(label_pen)
        for fraction in (0, 0.5, 1.0):
            y = height - margin_bottom - fraction * plot_h
            painter.drawText(4, int(y + 4), fmt_amount(max_val * fraction))

        n = len(self.data)
        group_w = plot_w / n
        bar_w = group_w * 0.32

        for i, d in enumerate(self.data):
            x0 = margin_left + i * group_w + group_w * 0.12
            income_h = (d["income"] / max_val) * plot_h if max_val else 0
            expense_h = (d["expense"] / max_val) * plot_h if max_val else 0

            painter.setBrush(GREEN)
            painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(x0, height - margin_bottom - income_h, bar_w, income_h))

            painter.setBrush(RED)
            painter.drawRect(QRectF(x0 + bar_w + 3, height - margin_bottom - expense_h,
                                     bar_w, expense_h))

            painter.setPen(QColor(fg.red(), fg.green(), fg.blue(), 230))
            label = datetime.datetime.strptime(d["month"], "%Y-%m").strftime("%m/%y")
            text_width = painter.fontMetrics().horizontalAdvance(label)
            painter.drawText(int(x0 + bar_w - text_width / 2), int(height - margin_bottom + 16),
                              label)


class SankeyWidget(_BaseChart):
    """Sankey-Geldfluss: Einnahmen (links) -> Gesamt (Mitte) -> Ausgaben/
    Überschuss (rechts)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.left_nodes = []
        self.right_nodes = []
        self.total = 0.0

    def set_data(self, left_nodes, right_nodes, total):
        self.left_nodes = left_nodes
        self.right_nodes = right_nodes
        self.total = total
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if (not self.left_nodes and not self.right_nodes) or self.total <= 0:
            self._draw_empty_message(
                painter,
                "Keine Buchungen in diesem Monat."
            )
            return

        width, height = self.width(), self.height()
        fg = self._fg_color()

        margin_top, margin_bottom = 24, 24
        plot_h = max(10, height - margin_top - margin_bottom)
        scale = plot_h / self.total

        bar_w = 18
        x_left = 8
        x_mid = width / 2 - bar_w / 2
        x_right = width - 8 - bar_w
        gap = 2

        # -------------------------------------------------------------
        # Schrift für die Labels
        # -------------------------------------------------------------
        label_font = painter.font()
        label_font.setPointSize(10)
        painter.setFont(label_font)

        # -------------------------------------------------------------
        # Positionen der Labels berechnen
        # -------------------------------------------------------------
        left_label_y = self._layout_label_positions(
            self.left_nodes,
            scale,
            margin_top,
            plot_h,
            painter.fontMetrics().height()
        )

        right_label_y = self._layout_label_positions(
            self.right_nodes,
            scale,
            margin_top,
            plot_h,
            painter.fontMetrics().height()
        )

        # =============================================================
        # LINKE SEITE
        # =============================================================
        y = margin_top

        for index, (name, icon, value, color) in enumerate(self.left_nodes):
            raw_h = value * scale
            h = max(1.0, raw_h - gap)

            node_center = y + raw_h / 2
            label_center = left_label_y[index]

            # Flow
            self._draw_flow_band(
                painter,
                x_left + bar_w,
                y,
                y + h,
                x_mid,
                y,
                y + h,
                color
            )

            # Balken
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawRect(QRectF(x_left, y, bar_w, h))

            # Verbindungslinie wird vor den Beschriftungen gezeichnet.
            # Die Beschriftungen selbst werden erst NACH allen Sankey-Flächen
            # gezeichnet, damit ein nachfolgendes farbiges Band keinen zuvor
            # gezeichneten Text übermalen kann.
            if abs(label_center - node_center) > 5:
                painter.setPen(
                    QColor(fg.red(), fg.green(), fg.blue(), 100)
                )

                painter.drawLine(
                    int(x_left + bar_w + 2),
                    int(node_center),
                    int(x_left + bar_w + 5),
                    int(label_center)
                )

            y += raw_h

        # =============================================================
        # MITTE
        # =============================================================
        painter.setBrush(
            QColor(
                fg.red(),
                fg.green(),
                fg.blue(),
                60
            )
        )
        painter.setPen(Qt.NoPen)

        painter.drawRect(
            QRectF(
                x_mid,
                margin_top,
                bar_w,
                plot_h
            )
        )

        painter.setPen(fg)

        title = "Gesamt"
        title_w = painter.fontMetrics().horizontalAdvance(title)

        painter.drawText(
            int(x_mid + bar_w / 2 - title_w / 2),
            int(margin_top - 8),
            title
        )

        # =============================================================
        # RECHTE SEITE
        # =============================================================
        y = margin_top

        for index, (name, icon, value, color) in enumerate(self.right_nodes):
            raw_h = value * scale
            h = max(1.0, raw_h - gap)

            node_center = y + raw_h / 2
            label_center = right_label_y[index]

            # Flow
            self._draw_flow_band(
                painter,
                x_mid + bar_w,
                y,
                y + h,
                x_right,
                y,
                y + h,
                color
            )

            # Balken
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)

            painter.drawRect(
                QRectF(x_right, y, bar_w, h)
            )

            # Verbindungslinie wird vor den Beschriftungen gezeichnet.
            # Die Beschriftungen selbst werden erst NACH allen Sankey-Flächen
            # gezeichnet, damit kein späteres farbiges Band den Text übermalt.
            if abs(label_center - node_center) > 5:
                painter.setPen(
                    QColor(fg.red(), fg.green(), fg.blue(), 100)
                )

                painter.drawLine(
                    int(x_right - 2),
                    int(node_center),
                    int(x_right - 5),
                    int(label_center)
                )

            y += raw_h

        # =============================================================
        # BESCHRIFTUNGEN GANZ ZUM SCHLUSS
        # =============================================================
        # Wichtig: Erst jetzt werden die Texte gezeichnet. Dadurch können
        # die farbigen Flussbänder der nachfolgenden Kategorien die
        # Beschriftung einer vorherigen Kategorie nicht mehr übermalen.

        painter.setFont(label_font)
        painter.setPen(fg)

        for index, (name, icon, value, color) in enumerate(self.left_nodes):
            label = f"{icon} {name}: {fmt_amount(value)}"
            label_center = left_label_y[index]
            text_y = label_center + painter.fontMetrics().ascent() / 2

            painter.drawText(
                int(x_left + bar_w + 6),
                int(text_y),
                label
            )

        for index, (name, icon, value, color) in enumerate(self.right_nodes):
            label = f"{icon} {name}: {fmt_amount(value)}"
            label_center = right_label_y[index]
            text_w = painter.fontMetrics().horizontalAdvance(label)
            text_y = label_center + painter.fontMetrics().ascent() / 2

            painter.drawText(
                int(x_right - text_w - 6),
                int(text_y),
                label
            )

    @staticmethod
    def _layout_label_positions(
        nodes,
        scale,
        margin_top,
        plot_h,
        font_height
    ):
        """
        Berechnet Labelpositionen mit Mindestabstand.

        Die tatsächliche Position des Sankey-Knotens bleibt unverändert.
        Nur das Label wird bei kleinen Knoten verschoben.
        """

        if not nodes:
            return []

        # Mindestabstand zwischen zwei Beschriftungen
        min_gap = max(18, font_height + 3)

        # Natürliche Positionen
        positions = []
        y = margin_top

        for name, icon, value, color in nodes:
            raw_h = value * scale
            center = y + raw_h / 2

            positions.append(center)
            y += raw_h

        # -------------------------------------------------------------
        # Von oben nach unten Mindestabstand erzwingen
        # -------------------------------------------------------------
        for i in range(1, len(positions)):
            positions[i] = max(
                positions[i],
                positions[i - 1] + min_gap
            )

        # -------------------------------------------------------------
        # Falls wir unten aus dem Bereich laufen:
        # alles wieder nach oben schieben.
        # -------------------------------------------------------------
        max_y = margin_top + plot_h - font_height / 2

        if positions[-1] > max_y:
            shift = positions[-1] - max_y

            positions = [
                p - shift
                for p in positions
            ]

        # -------------------------------------------------------------
        # Oben absichern
        # -------------------------------------------------------------
        min_y = margin_top + font_height / 2

        if positions[0] < min_y:
            shift = min_y - positions[0]

            positions = [
                p + shift
                for p in positions
            ]

        return positions

    @staticmethod
    def _draw_flow_band(
        painter,
        x0,
        y0_top,
        y0_bottom,
        x1,
        y1_top,
        y1_bottom,
        color,
        alpha=140
    ):
        """Weiches, gebogenes Band zwischen zwei vertikalen Segmenten."""

        cx = (x0 + x1) / 2

        path = QPainterPath()

        path.moveTo(x0, y0_top)

        path.cubicTo(
            cx,
            y0_top,
            cx,
            y1_top,
            x1,
            y1_top
        )

        path.lineTo(x1, y1_bottom)

        path.cubicTo(
            cx,
            y1_bottom,
            cx,
            y0_bottom,
            x0,
            y0_bottom
        )

        path.closeSubpath()

        band_color = QColor(color)
        band_color.setAlpha(alpha)

        painter.setPen(Qt.NoPen)
        painter.setBrush(band_color)
        painter.drawPath(path)


class EtfComparisonWidget(_BaseChart):
    """Liniendiagramm: Wertentwicklung mehrerer gespeicherter ETF-Sparpläne
    übereinandergelegt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.plans = []  # Liste von dicts {name, color, points: [(jahr, wert), ...]}

    def set_data(self, plans):
        self.plans = plans
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.plans:
            self._draw_empty_message(painter, "Noch keine gespeicherten Sparpläne zum Vergleichen.")
            return

        width, height = self.width(), self.height()
        fg = self._fg_color()

        margin_left, margin_right = 70, 150
        margin_top, margin_bottom = 16, 30
        plot_w = max(10, width - margin_left - margin_right)
        plot_h = max(10, height - margin_top - margin_bottom)

        max_year = max(p[0] for plan in self.plans for p in plan["points"])
        max_value = max(p[1] for plan in self.plans for p in plan["points"]) or 1

        pen = QPen(QColor(fg.red(), fg.green(), fg.blue(), 110))
        painter.setPen(pen)
        painter.drawLine(margin_left, margin_top, margin_left, height - margin_bottom)
        painter.drawLine(margin_left, height - margin_bottom, width - margin_right,
                          height - margin_bottom)

        painter.setPen(QColor(fg.red(), fg.green(), fg.blue(), 190))
        for fraction in (0, 0.5, 1.0):
            y = height - margin_bottom - fraction * plot_h
            painter.drawText(4, int(y + 4), fmt_amount(max_value * fraction))
        for fraction in (0, 0.5, 1.0):
            x = margin_left + fraction * plot_w
            year = max(1, round(max_year * fraction))
            painter.drawText(int(x - 6), int(height - margin_bottom + 16), f"J{year}")

        legend_y = margin_top
        for plan in self.plans:
            points = plan["points"]
            pen = QPen(plan["color"])
            pen.setWidth(2)
            painter.setPen(pen)
            path = QPainterPath()
            for i, (year, value) in enumerate(points):
                x = margin_left + (year / max_year) * plot_w if max_year else margin_left
                y = height - margin_bottom - (value / max_value) * plot_h if max_value else \
                    height - margin_bottom
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.drawPath(path)

            legend_x = width - margin_right + 14
            painter.setBrush(plan["color"])
            painter.setPen(Qt.NoPen)
            painter.drawRect(int(legend_x), int(legend_y), 14, 4)
            painter.setPen(QColor(fg.red(), fg.green(), fg.blue(), 230))
            final_value = points[-1][1] if points else 0
            painter.drawText(int(legend_x + 20), int(legend_y + 8), plan["name"])
            painter.drawText(int(legend_x + 20), int(legend_y + 20), fmt_amount(final_value))
            legend_y += 40
