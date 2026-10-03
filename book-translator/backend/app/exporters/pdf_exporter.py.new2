"""PDF export via ReportLab with embedded Unicode TrueType fonts.

For simple scripts ReportLab's native drawString works. For Indic scripts
ReportLab does not shape text, so we use uharfbuzz + FreeType glyph outlines
as a fallback only when native rendering would produce broken marks.
"""
import re
from pathlib import Path
from typing import Any

import freetype
import uharfbuzz as hb
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont as RLTTFont
from reportlab.pdfgen import canvas

from app.models import BookStructure

_FONTS_DIR = Path(__file__).resolve().parent.parent.parent / "fonts"

_FONT_FILES = {
    "NotoSans": "NotoSans-Regular.ttf",
    "NotoSans-Bold": "NotoSans-Bold.ttf",
    "NotoSansTelugu": "NotoSansTelugu-Regular.ttf",
    "NotoSansDevanagari": "NotoSansDevanagari-Regular.ttf",
}

# Scripts that need shaping because ReportLab cannot position vowel signs etc.
_COMPLEX_RE = re.compile(r"[\u0900-\u097F\u0C00-\u0C7F]")


class _ShapedFont:
    """Wraps a TTF with HarfBuzz + FreeType for vector-outline rendering."""

    def __init__(self, path: Path) -> None:
        self.path = path
        blob = hb.Blob.from_file_path(str(path))
        self.face = hb.Face(blob)
        self.font = hb.Font(self.face)
        self.ft_face = freetype.Face(str(path))
        self.upem = self.face.upem

    def set_size(self, size: float) -> None:
        # HarfBuzz uses 16.16 fixed point; FreeType char size is in 1/64 points.
        self.font.scale = (int(size * 64), int(size * 64))
        self.ft_face.set_char_size(int(size * 64))

    def shape(self, text: str) -> tuple[list[dict[str, Any]], float]:
        buf = hb.Buffer()
        buf.cluster_level = hb.BufferClusterLevel.MONOTONE_CHARACTERS
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.font, buf)

        glyphs: list[dict[str, Any]] = []
        advance_x = 0.0
        scale = 1 / 64.0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            glyphs.append(
                {
                    "gid": info.codepoint,
                    "x_offset": pos.x_offset * scale,
                    "y_offset": pos.y_offset * scale,
                    "x_advance": pos.x_advance * scale,
                    "y_advance": pos.y_advance * scale,
                }
            )
            advance_x += pos.x_advance * scale
        return glyphs, advance_x

    def glyph_vector_paths(
        self,
        glyphs: list[dict[str, Any]],
        x: float,
        y: float,
        canvas_ref: canvas.Canvas,
    ) -> float:
        """Draw shaped glyphs as filled ReportLab paths. Returns total advance width."""
        total_advance = 0.0
        for g in glyphs:
            gid = g["gid"]
            xo = g["x_offset"]
            yo = g["y_offset"]
            self.ft_face.load_glyph(gid, freetype.FT_LOAD_NO_BITMAP | freetype.FT_LOAD_NO_HINTING)
            outline = self.ft_face.glyph.outline
            if not outline.points:
                x += g["x_advance"]
                total_advance += g["x_advance"]
                continue

            p = canvas_ref.beginPath()
            points = outline.points
            tags = outline.tags
            contours = outline.contours
            start = 0
            for contour_end in contours:
                contour_points = points[start : contour_end + 1]
                contour_tags = tags[start : contour_end + 1]
                if not contour_points:
                    start = contour_end + 1
                    continue
                px, py = contour_points[0]
                p.moveTo(x + xo + px, y + yo - py)
                i = 1
                n = len(contour_points)
                while i < n:
                    if contour_tags[i] & 1:
                        px, py = contour_points[i]
                        p.lineTo(x + xo + px, y + yo - py)
                        i += 1
                    else:
                        c1x, c1y = contour_points[i]
                        if (i + 1 < n) and not (contour_tags[i + 1] & 1):
                            c2x, c2y = contour_points[i + 1]
                            endx = (c1x + c2x) / 2.0
                            endy = (c1y + c2y) / 2.0
                            p.curveTo(
                                x + xo + c1x,
                                y + yo - c1y,
                                x + xo + c2x,
                                y + yo - c2y,
                                x + xo + endx,
                                y + yo - endy,
                            )
                            i += 2
                        else:
                            endx, endy = contour_points[(i + 1) % n]
                            p.curveTo(
                                x + xo + c1x,
                                y + yo - c1y,
                                x + xo + c1x,
                                y + yo - c1y,
                                x + xo + endx,
                                y + yo - endy,
                            )
                            i += 2
                p.close()
                start = contour_end + 1

            canvas_ref.drawPath(p, fill=0, stroke=1)
            x += g["x_advance"]
            total_advance += g["x_advance"]
        return total_advance


def _load_fonts() -> dict[str, _ShapedFont]:
    fonts: dict[str, _ShapedFont] = {}
    for name, filename in _FONT_FILES.items():
        path = _FONTS_DIR / filename
        if path.exists():
            try:
                fonts[name] = _ShapedFont(path)
            except Exception:
                pass
    return fonts


_FONTS = _load_fonts()


def _detect_font(text: str, bold: bool = False) -> str:
    for ch in text:
        code = ord(ch)
        if 0x0C00 <= code <= 0x0C7F:
            return "NotoSansTelugu"
        if 0x0900 <= code <= 0x097F:
            return "NotoSansDevanagari"
    return "NotoSans-Bold" if bold else "NotoSans"


def _is_complex(text: str) -> bool:
    return bool(_COMPLEX_RE.search(text))


def _line_width(text: str, font_name: str, size: float) -> float:
    return pdfmetrics.stringWidth(text, font_name, size)


def _draw_text_line(
    c: canvas.Canvas,
    text: str,
    font_name: str,
    size: float,
    x: float,
    y: float,
    max_width: float,
) -> float:
    """Draw a line of text. Returns the line height consumed."""
    c.setFont(font_name, size)
    # For simple scripts, just draw the text natively; it is selectable.
    if not _is_complex(text):
        c.drawString(x, y, text)
        return size * 1.2

    # For complex scripts, try native drawString first; if the string width
    # matches HarfBuzz's shaped width closely, ReportLab is doing okay.
    shaped_font = _FONTS.get(font_name)
    if shaped_font is None:
        c.drawString(x, y, text)
        return size * 1.2

    shaped_font.set_size(size)
    glyphs, shaped_width = shaped_font.shape(text)
    native_width = pdfmetrics.stringWidth(text, font_name, size)
    # Tolerance: if native width is within 5% of shaped width, trust it.
    if shaped_width > 0 and abs(native_width - shaped_width) / shaped_width <= 0.05:
        c.drawString(x, y, text)
        return size * 1.2

    # Otherwise render vector outlines (unselectable but visually correct).
    width = shaped_font.glyph_vector_paths(glyphs, x, y, c)
    if width > max_width:
        scale = max_width / width
        c.saveState()
        c.translate(x, y)
        c.scale(scale, scale)
        c.translate(-x, -y)
        shaped_font.glyph_vector_paths(glyphs, x, y, c)
        c.restoreState()
        return size * scale * 1.2
    return size * 1.2


def export_pdf(book: BookStructure, output_path: Path) -> Path:
    """Build a paginated PDF with embedded Unicode fonts."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(output_path), pagesize=A4)
    width, height = A4
    margin = 72
    y = height - margin
    max_width = width - 2 * margin
    line_height = 18

    # Register embedded Unicode TrueType fonts.
    for name, filename in _FONT_FILES.items():
        path = _FONTS_DIR / filename
        if path.exists():
            try:
                pdfmetrics.registerFont(RLTTFont(name, str(path)))
            except Exception:
                pass

    def write_text(text: str, size: float = 11, bold: bool = False) -> None:
        nonlocal y
        font = _detect_font(text, bold=bold)
        words = text.split()
        current_line = ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if _line_width(test, font, size) <= max_width:
                current_line = test
            else:
                if y < margin + line_height:
                    c.showPage()
                    y = height - margin
                y -= _draw_text_line(c, current_line, font, size, margin, y, max_width)
                current_line = word
        if current_line:
            if y < margin + line_height:
                c.showPage()
                y = height - margin
            y -= _draw_text_line(c, current_line, font, size, margin, y, max_width)
            y -= size * 0.4

    if book.title:
        write_text(book.title, size=18, bold=True)
        y -= 12

    current_source = None
    for unit in book.units:
        if unit.translated_text is None:
            continue
        if unit.source_path != current_source:
            if current_source is not None:
                c.showPage()
                y = height - margin
            current_source = unit.source_path
        size = 14 if unit.type in ("h1", "h2") else 11
        bold = unit.type in ("h1", "h2")
        write_text(unit.translated_text, size=size, bold=bold)

    c.save()
    return output_path
