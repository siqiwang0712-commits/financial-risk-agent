from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .domain import new_id, now_iso


@dataclass
class Job:
    organization_id: str
    kind: str
    idempotency_key: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: new_id("job"))
    status: str = "queued"
    attempts: int = 0
    max_attempts: int = 3
    error: str | None = None
    created_at: str = field(default_factory=now_iso)
    # `migrations/001` declares `jobs.updated_at` as NOT NULL, and the queue had no
    # equivalent field, so a job could not record when it last moved. Kept in step
    # with `status` below.
    updated_at: str = field(default_factory=now_iso)


class JobQueue:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.keys: dict[tuple[str, str], str] = {}

    def enqueue(self, job: Job) -> Job:
        identity = (job.organization_id, job.idempotency_key)
        if identity in self.keys:
            return self.jobs[self.keys[identity]]
        self.jobs[job.id] = job
        self.keys[identity] = job.id
        return job

    def claim(self) -> Job | None:
        for job in self.jobs.values():
            if job.status in {"queued", "retry"} and job.attempts < job.max_attempts:
                job.status = "running"
                job.attempts += 1
                job.updated_at = now_iso()
                return job
        return None

    def _get(self, job_id: str) -> Job:
        """The job, or a `KeyError` naming it.

        `self.jobs[job_id]` already raised, but the bare dict error gives no
        indication of which queue or which id was at fault when a worker reports
        an unknown job.
        """
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        return job

    def fail(self, job_id: str, error: str) -> None:
        job = self._get(job_id)
        job.error = error
        job.status = "retry" if job.attempts < job.max_attempts else "failed"
        job.updated_at = now_iso()

    def complete(self, job_id: str) -> None:
        job = self._get(job_id)
        job.status = "completed"
        job.updated_at = now_iso()
