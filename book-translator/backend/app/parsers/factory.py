"""Parser factory."""
from pathlib import Path

from app.models import BookStructure, SourceFormat
from app.parsers.epub_parser import EpubParser
from app.parsers.pdf_parser import parse_pdf


def parse_book(file_path: Path) -> BookStructure:
    suffix = file_path.suffix.lower()
    if suffix == ".epub":
        parser = EpubParser(file_path)
        return parser.parse()
    if suffix == ".pdf":
        return parse_pdf(file_path)
    raise ValueError(f"Unsupported file format: {suffix}")
