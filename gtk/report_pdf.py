"""PDF-Monatsbericht für Plutos – ohne zusätzliche Bibliothek.

Schreibt ein schlichtes, mehrseitiges A4-PDF (Standardschrift Helvetica,
Balken als Rechtecke). Diese Datei ist in der GTK- und der Qt-Variante
identisch. Symbole/Emojis der Kategorien werden weggelassen, weil die
eingebauten PDF-Schriften sie nicht kennen.
"""

import datetime

PAGE_W, PAGE_H = 595.0, 842.0
MARGIN = 48.0

INK = (0.13, 0.15, 0.18)
MUTED = (0.42, 0.46, 0.52)
LINE = (0.84, 0.86, 0.89)
GREEN = (0.12, 0.55, 0.24)
RED = (0.75, 0.22, 0.15)
ORANGE = (0.85, 0.55, 0.05)
BLUE = (0.20, 0.47, 0.75)
BAR_BG = (0.93, 0.94, 0.96)

# Zeichenbreiten von Helvetica (1/1000 der Schriftgröße) für ASCII 32..126.
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
      556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
      1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
      667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
      333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
      556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_EXTRA = {"ä": 556, "ö": 556, "ü": 556, "Ä": 667, "Ö": 778, "Ü": 722, "ß": 611,
          "€": 556, "–": 556, "—": 1000, "·": 278, "•": 350, "„": 333, "“": 333, "”": 333}


def clean(text):
    """Nur Zeichen, die die Standardschrift (Windows-1252) kennt."""
    out = []
    for ch in str(text):
        try:
            ch.encode("cp1252")
        except UnicodeEncodeError:
            continue
        out.append(ch if ch >= " " else " ")
    return "".join(out)


def text_width(text, size, bold=False):
    total = 0
    for ch in text:
        o = ord(ch)
        total += _W[o - 32] if 32 <= o <= 126 else _EXTRA.get(ch, 556)
    return total * size / 1000.0 * (1.06 if bold else 1.0)


def fit_text(text, size, max_width, bold=False):
    """Kürzt mit „…“ (hier „...“), damit der Text in max_width passt."""
    text = clean(text)
    if text_width(text, size, bold) <= max_width:
        return text
    while text and text_width(text + "...", size, bold) > max_width:
        text = text[:-1]
    return text.rstrip() + "..."


def _esc(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class PdfDoc:
    """Minimaler PDF-Schreiber. Koordinaten: Ursprung oben links, Einheit pt."""

    def __init__(self, footer=""):
        self.pages = []
        self.footer = footer
        self.cur = None
        self.new_page()

    def new_page(self):
        self.cur = []
        self.pages.append(self.cur)
        return self.cur

    @staticmethod
    def _rgb(color):
        return "%.3f %.3f %.3f" % color

    def text(self, x, y, text, size=10, bold=False, color=INK, align="left"):
        text = clean(text)
        if align != "left":
            w = text_width(text, size, bold)
            x = x - w if align == "right" else x - w / 2
        self.cur.append("BT /%s %.1f Tf %s rg %.2f %.2f Td (%s) Tj ET" % (
            "F2" if bold else "F1", size, self._rgb(color), x, PAGE_H - y, _esc(text)))

    def rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        self.cur.append("%s rg %.2f %.2f %.2f %.2f re f" % (
            self._rgb(color), x, PAGE_H - y - h, w, h))

    def hline(self, x1, x2, y, color=LINE, width=0.6):
        self.cur.append("%s RG %.2f w %.2f %.2f m %.2f %.2f l S" % (
            self._rgb(color), width, x1, PAGE_H - y, x2, PAGE_H - y))

    def save(self, path):
        objects = []      # Bytes je Objekt (Nummer = Index + 1)

        def add(data):
            objects.append(data if isinstance(data, bytes) else data.encode("latin-1"))
            return len(objects)

        font1 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        font2 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        pages_ref = len(objects) + 1 + 2 * len(self.pages)   # Nummer des Pages-Objekts
        page_ids = []
        total = len(self.pages)
        for number, ops in enumerate(self.pages, 1):
            body = list(ops)
            if self.footer:
                label = "%s  -  %d / %d" % (clean(self.footer), number, total)
                body.append("BT /F1 8 Tf %s rg %.2f %.2f Td (%s) Tj ET" % (
                    self._rgb(MUTED), MARGIN, 28.0, _esc(label)))
            stream = "\n".join(body).encode("cp1252", "replace")
            content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
            page_ids.append(add(
                "<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
                "/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                % (pages_ref, PAGE_W, PAGE_H, font1, font2, content)))
        assert len(objects) + 1 == pages_ref
        add("<< /Type /Pages /Kids [%s] /Count %d >>"
            % (" ".join("%d 0 R" % i for i in page_ids), len(page_ids)))
        catalog = add("<< /Type /Catalog /Pages %d 0 R >>" % pages_ref)
        info = add("<< /Producer (Plutos) /Creator (Plutos) >>")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, data in enumerate(objects, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + data + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += (b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objects) + 1, catalog, info, xref))
        with open(path, "wb") as f:
            f.write(out)


# -- Monatsbericht ---------------------------------------------------------------

def build_month_report(data, path, tr, fmt, month_names, today=None):
    """Schreibt den Monatsbericht nach `path`.

    data: Ergebnis von FinanceStore.month_report_data(); tr: Übersetzungs-
    funktion; fmt: Betrag → Text; month_names: 12 Monatsnamen."""
    today = today or datetime.date.today()
    year, mon = int(data["month"][:4]), int(data["month"][5:7])
    s = data["summary"]
    doc = PdfDoc(footer=tr("Plutos – Das Haushaltsbuch"))
    left, right = MARGIN, PAGE_W - MARGIN
    width = right - left
    state = {"y": MARGIN}

    def ensure(height):
        if state["y"] + height > PAGE_H - 56:
            doc.new_page()
            state["y"] = MARGIN

    def heading(title):
        ensure(60)
        state["y"] += 14
        doc.text(left, state["y"], title, 12, bold=True)
        state["y"] += 6
        doc.hline(left, right, state["y"], INK, 0.8)
        state["y"] += 10

    # Kopf
    doc.text(left, state["y"] + 6, tr("Plutos – Monatsbericht"), 9, color=MUTED)
    doc.text(right, state["y"] + 6, tr("Erstellt am {0}").format(today.strftime("%d.%m.%Y")),
             9, color=MUTED, align="right")
    state["y"] += 36
    doc.text(left, state["y"], "%s %d" % (month_names[mon - 1], year), 26, bold=True)
    state["y"] += 28

    # Kennzahlen
    saved_color = GREEN if s["saved"] >= 0 else RED
    boxes = [(tr("Einnahmen"), fmt(s["income"]), GREEN),
             (tr("Ausgaben"), fmt(s["expense"]), RED),
             (tr("Gespart"), fmt(s["saved"]), saved_color),
             (tr("Sparquote"),
              "%.0f %%" % (s["saving_rate"] * 100) if s["saving_rate"] is not None else "-", INK)]
    gap = 10.0
    bw = (width - gap * 3) / 4
    for i, (label, value, color) in enumerate(boxes):
        x = left + i * (bw + gap)
        doc.rect(x, state["y"], bw, 56, BAR_BG)
        doc.text(x + 10, state["y"] + 18, label, 9, color=MUTED)
        doc.text(x + 10, state["y"] + 42, fit_text(value, 15, bw - 16, True), 15, bold=True, color=color)
    state["y"] += 72

    notes = []
    if s["expense_change"] is not None:
        notes.append(tr("Ausgaben {0:+.0f} % gegenüber dem Vormonat ({1}).").format(
            s["expense_change"] * 100, fmt(s["prev_expense"])))
    if data["balance_end"] is not None:
        notes.append(tr("Gesamtkontostand am Monatsende: {0}.").format(fmt(data["balance_end"])))
    notes.append(tr("{0} Buchungen in diesem Monat.").format(s["count"]))
    for line in notes:
        doc.text(left, state["y"], line, 10, color=MUTED)
        state["y"] += 15

    # Ausgaben nach Kategorie
    spending = data["spending"]
    if spending:
        heading(tr("Ausgaben nach Kategorie"))
        total = sum(r["total"] for r in spending) or 1.0
        top = spending[:12]
        rest = sum(r["total"] for r in spending[12:])
        rows = [(r["category_name"], r["total"]) for r in top]
        if rest > 0:
            rows.append((tr("Weitere Kategorien"), rest))
        biggest = max(v for _, v in rows) or 1.0
        bar_x, bar_w = left + 150, width - 150 - 150
        for name, value in rows:
            ensure(20)
            doc.text(left, state["y"] + 9, fit_text(name, 10, 140), 10)
            doc.rect(bar_x, state["y"] + 1, bar_w, 9, BAR_BG)
            doc.rect(bar_x, state["y"] + 1, bar_w * value / biggest, 9, BLUE)
            doc.text(right - 48, state["y"] + 9, fmt(value), 10, align="right")
            doc.text(right, state["y"] + 9, "%.0f %%" % (value / total * 100), 10,
                     color=MUTED, align="right")
            state["y"] += 18

    # Einnahmen
    income = data["income"]
    if income:
        heading(tr("Einnahmen nach Kategorie"))
        for r in income:
            ensure(18)
            doc.text(left, state["y"] + 9, fit_text(r["category_name"], 10, width - 120), 10)
            doc.text(right, state["y"] + 9, fmt(r["total"]), 10, color=GREEN, align="right")
            state["y"] += 17

    # Budgets
    budgets = data["budgets"]
    if budgets:
        heading(tr("Budgets"))
        bar_x, bar_w = left + 150, width - 150 - 190
        for r in budgets:
            ensure(20)
            spent, limit = r["spent"], r["limit_amount"]
            ratio = spent / limit if limit else 0.0
            color = RED if ratio > 1.0 else ORANGE if ratio >= 0.8 else GREEN
            doc.text(left, state["y"] + 9, fit_text(r["category_name"], 10, 140), 10)
            doc.rect(bar_x, state["y"] + 1, bar_w, 9, BAR_BG)
            doc.rect(bar_x, state["y"] + 1, bar_w * min(ratio, 1.0), 9, color)
            doc.text(right - 48, state["y"] + 9, "%s / %s" % (fmt(spent), fmt(limit)), 9, align="right")
            doc.text(right, state["y"] + 9, "%.0f %%" % (ratio * 100), 10, color=color, bold=True,
                     align="right")
            state["y"] += 18
        if s["budget_count"]:
            state["y"] += 2
            doc.text(left, state["y"] + 8, tr("{0} von {1} Budgets eingehalten.").format(
                s["budgets_ok"], s["budget_count"]), 9, color=MUTED)
            state["y"] += 14

    # Größte Ausgaben
    if data["biggest"]:
        heading(tr("Größte Ausgaben"))
        for r in data["biggest"]:
            ensure(18)
            day = datetime.date.fromisoformat(r["date"]).strftime("%d.%m.")
            label = (r["description"] or "").strip() or r["category_name"]
            doc.text(left, state["y"] + 9, day, 10, color=MUTED)
            doc.text(left + 44, state["y"] + 9, fit_text("%s  (%s)" % (label, r["category_name"])
                                                         if (r["description"] or "").strip() else label,
                                                         10, width - 160), 10)
            doc.text(right, state["y"] + 9, fmt(-r["amount"]), 10, align="right")
            state["y"] += 17

    doc.save(path)
