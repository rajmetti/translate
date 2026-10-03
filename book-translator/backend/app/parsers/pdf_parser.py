"""PDF parsing and structure extraction using pypdf."""
import uuid
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from app.models import BookStructure, SourceFormat, TranslationUnit


def parse_pdf(file_path: Path) -> BookStructure:
    reader = PdfReader(str(file_path))
    title = reader.metadata.title if reader.metadata else None
    if not title:
        title = file_path.stem

    units: list[TranslationUnit] = []
    for page_index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        for block_index, block in enumerate(text.split("\n\n")):
            block = block.strip()
            if not block:
                continue
            unit_id = f"p{page_index}_b{block_index}_{uuid.uuid4().hex[:8]}"
            units.append(
                TranslationUnit(
                    id=unit_id,
                    type="paragraph",
                    source_path=f"page_{page_index}",
                    source_index=page_index,
                    text=block,
                    context={},
                )
            )
    return BookStructure(
        title=title,
        language="en",
        format=SourceFormat.PDF,
        spine=[{"page": i} for i in range(len(reader.pages))],
        toc=[],
        units=units,
        metadata={
            "page_count": len(reader.pages),
            "original_file": str(file_path),
        },
    )
