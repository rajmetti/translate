"""EPUB parsing and structure extraction."""
import os
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
from ebooklib import epub

from app.models import BookStructure, SourceFormat, TranslationUnit


NAMESPACES = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": "http://www.idpf.org/2007/opf",
    "xhtml": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
}


def _ns(tag: str, prefix: str = "xhtml") -> str:
    return f"{{{NAMESPACES[prefix]}}}{tag}"


class EpubParser:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.book = epub.read_epub(str(file_path))
        self.content_dir = Path(file_path).parent / f"epub_{uuid.uuid4().hex}"
        self._maybe_extract_raw()
        self.opf_dir = self._find_opf_dir()

    def _maybe_extract_raw(self) -> None:
        """Extract raw EPUB for later re-assembly."""
        self.content_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(self.file_path, "r") as z:
            z.extractall(self.content_dir)

    def _find_opf_dir(self) -> str:
        """Return the directory containing content.opf relative to content_dir."""
        container = self.content_dir / "META-INF" / "container.xml"
        if container.exists():
            soup = BeautifulSoup(container.read_text(encoding="utf-8"), "xml")
            rootfile = soup.find("rootfile")
            if rootfile and rootfile.get("full-path"):
                opf_path = Path(rootfile.get("full-path"))
                return opf_path.parent.as_posix() if opf_path.parent.as_posix() != "." else ""
        return ""

    def parse(self) -> BookStructure:
        title = self._get_title()
        language = self._get_language()
        spine_items = self._build_spine()
        toc = self._build_toc(spine_items)
        units = self._extract_units(spine_items)

        return BookStructure(
            title=title,
            language=language,
            format=SourceFormat.EPUB,
            spine=spine_items,
            toc=toc,
            units=units,
            metadata={
                "content_dir": str(self.content_dir),
                "opf_dir": self.opf_dir,
                "original_file": str(self.file_path),
            },
        )

    def _get_title(self) -> str | None:
        for meta in self.book.get_metadata("DC", "title"):
            return meta[0]
        return None

    def _get_language(self) -> str:
        for meta in self.book.get_metadata("DC", "language"):
            return meta[0]
        return "en"

    def _build_spine(self) -> list[dict[str, Any]]:
        manifest = {item.get_id(): item.get_name() for item in self.book.get_items()}
        spine = []
        for item_id, linear in self.book.spine:
            href = manifest.get(item_id)
            if href:
                spine.append(
                    {
                        "id": item_id,
                        "href": href,
                        "linear": linear,
                    }
                )
        return spine

    def _build_toc(self, spine: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build TOC from NCX or nav.xhtml if available."""
        toc = []
        ncx_item = next(
            (i for i in self.book.get_items() if isinstance(i, epub.EpubNcx)), None
        )
        if ncx_item:
            soup = BeautifulSoup(ncx_item.get_content(), "xml")
            for point in soup.find_all("navPoint"):
                label_tag = point.find("navLabel")
                label = label_tag.get_text(strip=True) if label_tag else ""
                content = point.find("content")
                src = content.get("src") if content else ""
                toc.append({"label": label, "src": src})
            return toc

        # Fallback: scan nav document or headings in spine items.
        for idx, item in enumerate(spine):
            doc = self._read_spine_doc(item["href"])
            if not doc:
                continue
            for heading in doc.find_all(["h1", "h2", "h3"]):
                text = heading.get_text(strip=True)
                if text:
                    toc.append({"label": text, "src": f"{item['href']}#{heading.get('id', '')}"})
        return toc

    def _resolve_href(self, href: str) -> Path:
        """Resolve a spine href relative to the OPF directory."""
        if self.opf_dir:
            return self.content_dir / self.opf_dir / href
        return self.content_dir / href

    def _read_spine_doc(self, href: str) -> BeautifulSoup | None:
        full_path = self._resolve_href(href)
        if not full_path.exists():
            return None
        return BeautifulSoup(full_path.read_text(encoding="utf-8"), "html.parser")

    def _extract_units(self, spine: list[dict[str, Any]]) -> list[TranslationUnit]:
        units: list[TranslationUnit] = []
        for spine_index, item in enumerate(spine):
            doc = self._read_spine_doc(item["href"])
            if not doc:
                continue
            body = doc.find("body")
            if not body:
                continue

            for elem in body.find_all(string=False):
                if elem.name in ("script", "style", "nav", "header", "footer"):
                    continue
                text = elem.get_text(strip=True)
                if not text:
                    continue
                elem_id = elem.get("id") or f"{spine_index}_{uuid.uuid4().hex[:8]}"
                if not elem.get("id"):
                    elem["id"] = elem_id

                units.append(
                    TranslationUnit(
                        id=elem_id,
                        type=elem.name,
                        source_path=item["href"],
                        source_index=spine_index,
                        label=elem.name,
                        text=text,
                        context={
                            "classes": elem.get("class", []),
                            "attrs": {k: v for k, v in elem.attrs.items() if k != "class"},
                        },
                    )
                )
            # Write back id-stamped version for reassembly.
            self._write_spine_doc(item["href"], doc)
        return units

    def _write_spine_doc(self, href: str, doc: BeautifulSoup) -> None:
        full_path = self._resolve_href(href)
        full_path.write_text(str(doc), encoding="utf-8")

    def get_content_dir(self) -> Path:
        return self.content_dir
