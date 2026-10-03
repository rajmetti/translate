"""EPUB re-assembly exporter."""
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from bs4 import BeautifulSoup

from app.models import BookStructure


class EpubExporter:
    def __init__(self, book: BookStructure):
        self.book = book
        self.content_dir = Path(book.metadata["content_dir"])
        self.opf_dir = book.metadata.get("opf_dir", "")

    def _resolve_href(self, href: str) -> Path:
        """Resolve a spine href relative to the OPF directory."""
        if self.opf_dir:
            return self.content_dir / self.opf_dir / href
        return self.content_dir / href

    def export(self, output_path: Path) -> Path:
        units_by_path: dict[str, dict[str, str]] = {}
        for unit in self.book.units:
            if unit.translated_text:
                units_by_path.setdefault(unit.source_path, {})[unit.id] = unit.translated_text

        for href, replacements in units_by_path.items():
            doc_path = self._resolve_href(href)
            if not doc_path.exists():
                continue
            soup = BeautifulSoup(doc_path.read_text(encoding="utf-8"), "html.parser")
            for elem_id, translated in replacements.items():
                elem = soup.find(id=elem_id)
                if elem:
                    elem.string = translated
            doc_path.write_text(str(soup), encoding="utf-8")

        # Update language metadata.
        opf_path = self._find_opf_path()
        if opf_path:
            self._update_opf_language(opf_path)

        self._create_epub(output_path)
        return output_path

    def _find_opf_path(self) -> Path | None:
        container = self.content_dir / "META-INF" / "container.xml"
        if not container.exists():
            return None
        soup = BeautifulSoup(container.read_text(encoding="utf-8"), "xml")
        rootfile = soup.find("rootfile")
        if rootfile and rootfile.get("full-path"):
            return self.content_dir / rootfile.get("full-path")
        return None

    def _update_opf_language(self, opf_path: Path) -> None:
        text = opf_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(text, "xml")
        lang = soup.find("dc:language")
        if lang:
            lang.string = self.book.metadata.get("target_language", "en")
        opf_path.write_text(str(soup), encoding="utf-8")

    def _create_epub(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output_path, "w", ZIP_DEFLATED) as zf:
            for path in self.content_dir.rglob("*"):
                if path.is_file():
                    arcname = path.relative_to(self.content_dir).as_posix()
                    zf.write(path, arcname)


def export_epub(book: BookStructure, output_path: Path) -> Path:
    return EpubExporter(book).export(output_path)
