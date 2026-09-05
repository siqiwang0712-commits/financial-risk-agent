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
                return job
        return None

    def fail(self, job_id: str, error: str) -> None:
        job = self.jobs[job_id]
        job.error = error
        job.status = "retry" if job.attempts < job.max_attempts else "failed"

    def complete(self, job_id: str) -> None:
        self.jobs[job_id].status = "completed"
