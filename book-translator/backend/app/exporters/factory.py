"""Exporter factory."""
from pathlib import Path

from app.models import BookStructure, OutputFormat
from app.exporters.epub_exporter import export_epub
from app.exporters.pdf_exporter import export_pdf


def export_book(book: BookStructure, output_format: OutputFormat, output_path: Path) -> Path:
    if output_format == OutputFormat.EPUB:
        return export_epub(book, output_path)
    if output_format == OutputFormat.PDF:
        return export_pdf(book, output_path)
    raise ValueError(f"Unsupported output format: {output_format}")
