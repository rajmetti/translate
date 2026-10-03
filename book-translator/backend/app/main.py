"""FastAPI backend for Book Translator."""
import asyncio
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("book-translator")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.exporters.factory import export_book
from app.jobs import job_store
from app.models import (
    BookStructure,
    JobStatus,
    ModelChoice,
    OutputFormat,
    TranslateRequest,
    TranslateScope,
)
from app.parsers.factory import parse_book
from app.translator.pipeline import TranslationPipeline

app = FastAPI(title="Book Translator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    job_id = uuid.uuid4().hex
    ext = Path(file.filename or "book").suffix.lower()
    if ext not in (".epub", ".pdf"):
        raise HTTPException(400, "Only .epub and .pdf files are supported")

    upload_path = settings.upload_dir / f"{job_id}{ext}"
    with upload_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    await job_store.create(job_id)
    logger.info("[job:%s] Uploaded file %s -> %s", job_id, file.filename, upload_path)
    return JSONResponse({"job_id": job_id, "filename": file.filename, "path": str(upload_path)})


@app.get("/api/structure/{job_id}")
async def get_structure(job_id: str) -> dict:
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    book = _load_cached_structure(job_id)
    if not book:
        await job_store.update(job_id, status="parsing")
        upload_path = _find_upload(job_id)
        book = parse_book(upload_path)
        _cache_structure(job_id, book)
        await job_store.update(job_id, status="parsed")
    return book.model_dump()


@app.post("/api/translate/{job_id}")
async def translate(
    job_id: str,
    target_language: str = Form(...),
    scope: TranslateScope = Form(TranslateScope.ALL),
    model: ModelChoice = Form(ModelChoice.CLAUDE),
    output_format: OutputFormat = Form(OutputFormat.EPUB),
    selected_chapters: str = Form(""),
    page_start: int | None = Form(None),
    page_end: int | None = Form(None),
    mode: str = Form("standard"),
) -> JSONResponse:
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    book = _load_cached_structure(job_id)
    if not book:
        upload_path = _find_upload(job_id)
        await job_store.update(job_id, status="parsing")
        logger.info("[job:%s] Parsing %s", job_id, upload_path)
        book = parse_book(upload_path)
        _cache_structure(job_id, book)
        logger.info("[job:%s] Parsed %d units", job_id, len(book.units))

    selected = [c.strip() for c in selected_chapters.split(",") if c.strip()]
    request = TranslateRequest(
        job_id=job_id,
        target_language=target_language,
        scope=scope,
        model=model,
        output_format=output_format,
        selected_chapters=selected or None,
        page_start=page_start,
        page_end=page_end,
        mode=mode,
    )

    selected_units = TranslationPipeline()._select_units(book, request)
    logger.info(
        "[job:%s] Starting translation: lang=%s model=%s scope=%s units=%d output=%s",
        job_id,
        target_language,
        model.value,
        scope.value,
        len(selected_units),
        output_format.value,
    )

    async def progress(percent: int) -> None:
        await job_store.update(job_id, progress_percent=percent)
        logger.info("[job:%s] Translation progress %d%%", job_id, percent)

    # Run translation in background.
    asyncio.create_task(_run_translation(job_id, book, request, progress))
    return JSONResponse({"job_id": job_id, "status": "started"})


async def _run_translation(
    job_id: str, book: BookStructure, request: TranslateRequest, progress_callback
) -> None:
    try:
        await job_store.update(job_id, status="extracting_glossary", progress_percent=5)
        logger.info("[job:%s] Extracting glossary...", job_id)
        pipeline = TranslationPipeline()
        await job_store.update(job_id, status="translating", progress_percent=10)
        logger.info("[job:%s] Translating %d units...", job_id, len(pipeline._select_units(book, request)))
        translated = await pipeline.translate(book, request, progress_callback=progress_callback)
        await job_store.update(job_id, progress_percent=90)

        await job_store.update(job_id, status="assembling")
        logger.info("[job:%s] Assembling %s output...", job_id, request.output_format.value)
        output_path = settings.output_dir / f"{job_id}.{request.output_format.value}"
        export_book(translated, request.output_format, output_path)
        _cache_structure(job_id, translated)

        await job_store.update(
            job_id,
            status="done",
            progress_percent=100,
            output_file=str(output_path),
        )
        logger.info("[job:%s] Translation complete -> %s", job_id, output_path)
    except Exception as exc:
        logger.exception("[job:%s] Translation failed", job_id)
        await job_store.update(job_id, status="error", error=str(exc))


@app.get("/api/status/{job_id}")
async def status(job_id: str) -> JobStatus:
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/download/{job_id}")
async def download(job_id: str) -> FileResponse:
    job = await job_store.get(job_id)
    if not job or not job.output_file:
        raise HTTPException(404, "Output not ready")
    path = Path(job.output_file)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@app.get("/api/preview/{job_id}")
async def preview(job_id: str, page: int | None = None, limit: int = 3) -> JSONResponse:
    """Return translated text preview for a job (optionally filtered by spine/page index)."""
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    book = _load_cached_structure(job_id)
    if not book:
        raise HTTPException(404, "Book structure not cached; translate first")
    units = [u for u in book.units if u.translated_text is not None]
    if page is not None:
        units = [u for u in units if u.source_index == page]
    previews = [
        {
            "source_index": u.source_index,
            "source_path": u.source_path,
            "id": u.id,
            "original": u.text,
            "translated": u.translated_text,
        }
        for u in units[:limit]
    ]
    return JSONResponse({"job_id": job_id, "page": page, "previews": previews})


def _find_upload(job_id: str) -> Path:
    for ext in (".epub", ".pdf"):
        candidate = settings.upload_dir / f"{job_id}{ext}"
        if candidate.exists():
            return candidate
    raise HTTPException(404, "Uploaded file not found")


_structure_cache: dict[str, BookStructure] = {}


def _load_cached_structure(job_id: str) -> BookStructure | None:
    return _structure_cache.get(job_id)


def _cache_structure(job_id: str, book: BookStructure) -> None:
    _structure_cache[job_id] = book


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
