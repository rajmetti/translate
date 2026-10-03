"""Pydantic models for API and internal data structures."""
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SourceFormat(str, Enum):
    EPUB = "epub"
    PDF = "pdf"


class OutputFormat(str, Enum):
    EPUB = "epub"
    PDF = "pdf"


class ModelChoice(str, Enum):
    GPT = "gpt"
    CLAUDE = "claude"
    KIMI = "kimi"
    GROK = "grok"


class TranslateScope(str, Enum):
    ALL = "all"
    CHAPTERS = "chapters"
    PAGES = "pages"
    RANGE = "range"


class TranslationUnit(BaseModel):
    id: str
    type: str
    source_path: str
    source_index: int
    label: str | None = None
    text: str
    context: dict[str, Any] = Field(default_factory=dict)
    translated_text: str | None = None


class BookStructure(BaseModel):
    title: str | None = None
    language: str = "en"
    format: SourceFormat
    spine: list[dict[str, Any]]
    toc: list[dict[str, Any]]
    units: list[TranslationUnit]
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_data: dict[str, Any] | None = None


class TranslateRequest(BaseModel):
    job_id: str
    target_language: str
    scope: TranslateScope
    model: ModelChoice = ModelChoice.CLAUDE
    output_format: OutputFormat = OutputFormat.EPUB
    selected_chapters: list[str] | None = None
    page_start: int | None = None
    page_end: int | None = None
    mode: str = "standard"  # standard, literary, technical, fast
    custom_glossary: dict[str, str] | None = None


class JobStatus(BaseModel):
    job_id: str
    status: str  # pending, parsing, extracting_glossary, translating, assembling, done, error
    progress_percent: int = 0
    message: str = ""
    output_file: Path | None = None
    error: str | None = None
