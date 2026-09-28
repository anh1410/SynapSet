"""A deliberately small PDF writer for exam papers - no third-party dependency.

Uses the standard PDF base fonts (Helvetica, Helvetica-Bold, Courier), which
every PDF reader has built in, so nothing is embedded. Supports what an exam
paper needs: wrapped paragraphs, headings, right-aligned marks, monospace code
blocks, simple tables, rules, automatic page breaks and page numbers.
Text is Latin-1 (WinAnsi); common typographic characters are mapped to ASCII
equivalents and anything else becomes "?".
"""

from dataclasses import dataclass, field

PAGE_W, PAGE_H = 595.28, 841.89  # A4 in points
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 56.0, 60.0, 56.0

# Advance widths (per 1000 em) for ASCII 32..126, from the Adobe core-font AFMs.
_HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556,
         556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667,
         556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556,
         556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722,
         500, 500, 500, 334, 260, 334, 584]
_HELV_BOLD = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
              556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556,
              722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333,
              556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556,
              778, 556, 556, 500, 389, 280, 389, 584]
FONTS = {"regular": ("F1", "Helvetica", _HELV), "bold": ("F2", "Helvetica-Bold", _HELV_BOLD), "mono": ("F3", "Courier", None)}

_REPLACEMENTS = {
    "—": "-", "–": "-", "−": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", "≤": "<=", "≥": ">=", "≠": "!=", "→": "->", "←": "<-", "×": "x",
    "•": "-", " ": " ", "✓": "OK", "✗": "X", "∞": "inf", "≈": "~", "\t": "    ",
}


def sanitize(text: str) -> str:
    out = []
    for ch in text:
        ch = _REPLACEMENTS.get(ch, ch)
        out.append(ch if all(ord(c) < 256 for c in ch) else "?")
    return "".join(out)


def text_width(text: str, font: str, size: float) -> float:
    widths = FONTS[font][2]
    if widths is None:  # Courier: every glyph 600
        return len(text) * 600 * size / 1000
    total = 0
    for ch in text:
        o = ord(ch)
        total += widths[o - 32] if 32 <= o <= 126 else 556
    return total * size / 1000


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words, line = para.split(" "), ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if text_width(candidate, font, size) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            # Break a single over-long word (e.g. a URL) across lines.
            while text_width(word, font, size) > width and len(word) > 1:
                cut = len(word)
                while cut > 1 and text_width(word[:cut], font, size) > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


@dataclass
class _Page:
    ops: list[str] = field(default_factory=list)


class PdfDocument:
    def __init__(self, title: str, footer: str = ""):
        self.title = sanitize(title)
        self.footer = sanitize(footer)
        self.pages: list[_Page] = []
        self.y = 0.0
        self.content_width = PAGE_W - 2 * MARGIN_X
        self._new_page()

    # ----- layout primitives -----

    def _new_page(self) -> None:
        self.pages.append(_Page())
        self.y = PAGE_H - MARGIN_TOP

    def _ensure(self, height: float) -> None:
        if self.y - height < MARGIN_BOTTOM:
            self._new_page()

    def _text_op(self, x: float, y: float, text: str, font: str, size: float) -> None:
        name = FONTS[font][0]
        self.pages[-1].ops.append(f"BT /{name} {size:.2f} Tf {x:.2f} {y:.2f} Td ({_escape(text)}) Tj ET")

    def space(self, points: float) -> None:
        self.y -= points

    def paragraph(self, text: str, font: str = "regular", size: float = 10.5, indent: float = 0.0,
                  right_label: str | None = None, gap_after: float = 4.0, leading: float = 1.35,
                  align: str = "left") -> None:
        """Wrapped text; `right_label` (e.g. "[5 marks]") sits right-aligned on the first line."""
        text = sanitize(text)
        label = sanitize(right_label) if right_label else None
        label_w = text_width(label, "bold", size) + 12 if label else 0
        width = self.content_width - indent - label_w
        line_h = size * leading
        for i, line in enumerate(wrap(text, font, size, width) or [""]):
            self._ensure(line_h)
            self.y -= line_h
            x = MARGIN_X + indent
            if align == "center":
                x = MARGIN_X + (self.content_width - text_width(line, font, size)) / 2
            self._text_op(x, self.y, line, font, size)
            if i == 0 and label:
                self._text_op(PAGE_W - MARGIN_X - text_width(label, "bold", size), self.y, label, "bold", size)
        self.y -= gap_after

    def heading(self, text: str, size: float = 13, gap_before: float = 8, align: str = "left") -> None:
        self._ensure(size * 3)  # keep a heading with at least a line of what follows
        self.space(gap_before)
        self.paragraph(text, font="bold", size=size, gap_after=4, align=align)

    def code(self, text: str, indent: float = 18, size: float = 9) -> None:
        text = sanitize(text)
        line_h = size * 1.3
        width = self.content_width - indent - 8
        for raw in text.split("\n"):
            for line in wrap(raw, "mono", size, width) or [""]:
                self._ensure(line_h)
                self.y -= line_h
                self._text_op(MARGIN_X + indent + 4, self.y, line, "mono", size)
        self.y -= 6

    def rule(self, gap: float = 6) -> None:
        self._ensure(gap * 2)
        self.y -= gap
        self.pages[-1].ops.append(f"0.75 w 0.6 G {MARGIN_X:.2f} {self.y:.2f} m {PAGE_W - MARGIN_X:.2f} {self.y:.2f} l S 0 G")
        self.y -= gap

    def table(self, headers: list[str], rows: list[list[str]], col_widths: list[float], size: float = 9) -> None:
        """Simple left-to-right table; column widths are fractions of the content width."""
        xs, acc = [], MARGIN_X
        for w in col_widths:
            xs.append(acc)
            acc += w * self.content_width
        line_h = size * 1.45

        def draw(cells: list[str], font: str) -> None:
            wrapped = [
                wrap(sanitize(c), font, size, col_widths[i] * self.content_width - 6) or [""]
                for i, c in enumerate(cells)
            ]
            height = max(len(w) for w in wrapped) * line_h
            if self.y - height < MARGIN_BOTTOM:
                self._new_page()
                if font != "bold":
                    draw(headers, "bold")
            top = self.y
            for i, lines in enumerate(wrapped):
                y = top
                for line in lines:
                    y -= line_h
                    self._text_op(xs[i], y, line, font, size)
            self.y = top - height - 2

        draw(headers, "bold")
        self.pages[-1].ops.append(f"0.5 w 0.7 G {MARGIN_X:.2f} {self.y + 1:.2f} m {PAGE_W - MARGIN_X:.2f} {self.y + 1:.2f} l S 0 G")
        for row in rows:
            draw(row, "regular")
        self.y -= 6

    # ----- serialisation -----

    def to_bytes(self) -> bytes:
        objects: list[bytes] = []

        def add(body: str | bytes) -> int:
            objects.append(body.encode("latin-1") if isinstance(body, str) else body)
            return len(objects)

        catalog_id = add("")  # placeholder, filled below
        pages_id = add("")
        font_ids = {
            key: add(f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} /Encoding /WinAnsiEncoding >>")
            for key, (_, base, _) in FONTS.items()
        }
        font_res = " ".join(f"/{FONTS[k][0]} {oid} 0 R" for k, oid in font_ids.items())
        page_ids = []
        total = len(self.pages)
        for n, page in enumerate(self.pages, start=1):
            ops = list(page.ops)
            footer = f"{self.footer}    Page {n} of {total}" if self.footer else f"Page {n} of {total}"
            footer = sanitize(footer)
            ops.append(
                f"BT /F1 8.00 Tf {PAGE_W - MARGIN_X - text_width(footer, 'regular', 8):.2f} 30.00 Td ({_escape(footer)}) Tj ET"
            )
            stream = "\n".join(ops).encode("latin-1")
            content_id = add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
            page_ids.append(
                add(
                    f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                    f"/Resources << /Font << {font_res} >> >> /Contents {content_id} 0 R >>"
                )
            )
        objects[pages_id - 1] = (
            f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {total} >>"
        ).encode("latin-1")
        objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1")
        info_id = add(f"<< /Title ({_escape(self.title)}) /Producer (SynapSet) >>")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R /Info {info_id} 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
        return bytes(out)
