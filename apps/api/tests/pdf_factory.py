"""Helpers that build small PDFs in memory for tests (reportlab, dev dependency)."""

from __future__ import annotations

import io
import textwrap

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

_WIDTH, _HEIGHT = A4


def _draw_text_page(c: canvas.Canvas, text: str) -> None:
    y = _HEIGHT - 72
    c.setFont("Helvetica", 11)
    for paragraph in text.split("\n"):
        lines = textwrap.wrap(paragraph, width=90) or [""]
        for line in lines:
            c.drawString(72, y, line)
            y -= 15
            if y < 72:
                return


def make_pdf(pages: list[str], *, encrypt_password: str | None = None) -> bytes:
    """Return PDF bytes with one page per string (empty string = blank page)."""
    buf = io.BytesIO()
    encrypt = (
        StandardEncryption(encrypt_password, canPrint=0) if encrypt_password is not None else None
    )
    c = canvas.Canvas(buf, pagesize=A4, encrypt=encrypt)
    for text in pages:
        if text:
            _draw_text_page(c, text)
        c.showPage()
    c.save()
    return buf.getvalue()


def _text_image(text: str) -> ImageReader:
    img = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), text, fill="black")
    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return ImageReader(out)


def make_pdf_with_image_page(pages: list[str | None]) -> bytes:
    """Like ``make_pdf`` but a ``None`` entry becomes an image-only page (no text layer),
    simulating a scanned page."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for text in pages:
        if text is None:
            c.drawImage(_text_image("SCANNED PAGE - text only in pixels"), 72, 400, 450, 150)
        elif text:
            _draw_text_page(c, text)
        c.showPage()
    c.save()
    return buf.getvalue()
