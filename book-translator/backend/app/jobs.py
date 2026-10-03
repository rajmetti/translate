"""Persistent JSONL job tracking."""
import asyncio
import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import JobStatus


class JobStore:
    def __init__(self, store_path: Path | None = None) -> None:
        self._jobs: dict[str, JobStatus] = {}
        self._lock = asyncio.Lock()
        self.store_path = store_path or settings.job_store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        with self.store_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    job = JobStatus(**data)
                    self._jobs[job.job_id] = job
                except Exception:
                    continue

    def _persist(self) -> None:
        with self.store_path.open("w", encoding="utf-8") as f:
            for job in self._jobs.values():
                f.write(json.dumps(job.model_dump(mode="json"), ensure_ascii=False) + "\n")

    async def create(self, job_id: str) -> JobStatus:
        async with self._lock:
            job = JobStatus(job_id=job_id, status="pending")
            self._jobs[job_id] = job
            self._persist()
            return job

    async def update(self, job_id: str, **kwargs: Any) -> JobStatus:
        async with self._lock:
            job = self._jobs[job_id]
            for key, value in kwargs.items():
                setattr(job, key, value)
            self._persist()
            return job

    async def get(self, job_id: str) -> JobStatus | None:
        async with self._lock:
            return self._jobs.get(job_id)


job_store = JobStore()
