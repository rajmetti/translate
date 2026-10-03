"""Translation pipeline orchestration."""
import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from app.models import (
    BookStructure,
    ModelChoice,
    OutputFormat,
    TranslateRequest,
    TranslateScope,
    TranslationUnit,
)
from app.translator.foundry_client import FoundryClient

logger = logging.getLogger("book-translator.pipeline")


class TranslationPipeline:
    def __init__(self, client: FoundryClient | None = None):
        self.client = client or FoundryClient()

    def _select_units(
        self, book: BookStructure, request: TranslateRequest
    ) -> list[TranslationUnit]:
        scope = request.scope
        units = book.units
        if scope == TranslateScope.ALL:
            return units
        if scope == TranslateScope.CHAPTERS and request.selected_chapters:
            # For EPUB, selected_chapters are spine hrefs or item ids.
            selected = set(request.selected_chapters)
            return [u for u in units if u.source_path in selected]
        if scope == TranslateScope.PAGES:
            # For EPUBs produced by hocr-to-epub, page N is usually at spine index N+2
            # (nav=0, notice=1, page_0=2, page_1=3, ...). Try both the raw index and the mapped index.
            selected_raw = {int(p) for p in request.selected_chapters or []}
            selected_mapped = {p + 2 for p in selected_raw}
            selected = selected_raw | selected_mapped
            return [u for u in units if u.source_index in selected]
        if scope == TranslateScope.RANGE:
            start = (request.page_start or 0) + 2
            end = (request.page_end or max(u.source_index for u in units)) + 2
            return [u for u in units if start <= u.source_index <= end]
        return units

    async def extract_glossary(
        self, book: BookStructure, request: TranslateRequest
    ) -> dict[str, str]:
        if request.custom_glossary:
            return request.custom_glossary
        sample_units = book.units[: min(len(book.units), 20)]
        sample_text = "\n\n".join(u.text for u in sample_units)
        if not sample_text:
            return {}
        return await self.client.extract_glossary(
            sample_text, request.target_language, model=ModelChoice.GPT
        )

    async def translate(
        self,
        book: BookStructure,
        request: TranslateRequest,
        progress_callback: Any | None = None,
    ) -> BookStructure:
        units = self._select_units(book, request)
        glossary = await self.extract_glossary(book, request)

        previous_context = ""
        total = len(units)
        semaphore = asyncio.Semaphore(3)  # Limit concurrent Foundry calls.

        async def translate_one(index: int, unit: TranslationUnit) -> tuple[int, str]:
            async with semaphore:
                logger.info(
                    "[job:%s] Translating unit %d/%d (%s)",
                    request.job_id,
                    index + 1,
                    total,
                    unit.id,
                )
                translated = await self.client.translate_chunk(
                    model=request.model,
                    text=unit.text,
                    target_language=request.target_language,
                    glossary=glossary,
                    previous_context=previous_context,
                    mode=request.mode,
                )
                progress = int((index + 1) / total * 80) + 10  # 10-90% range
                if progress_callback:
                    await progress_callback(progress)
                return index, translated

        tasks = [translate_one(i, unit) for i, unit in enumerate(units)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, unit in enumerate(units):
            result = results[i]
            if isinstance(result, Exception):
                unit.translated_text = f"[TRANSLATION ERROR: {result}]"
            else:
                _, translated = result
                unit.translated_text = translated
                # Keep a sliding context window from successfully translated units.
                previous_context = translated[-500:]

        # Attach glossary to book metadata for export/debugging.
        book.metadata["glossary"] = glossary
        book.metadata["target_language"] = request.target_language
        book.metadata["model"] = request.model.value
        return book
