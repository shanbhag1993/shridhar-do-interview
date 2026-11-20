from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from job_queue.domain.status import TaskStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Task:
    id: str
    task_type: str
    payload: dict[str, Any]
    priority: int = 0
    max_retries: int = 0
    timeout_seconds: float = 30.0
    status: TaskStatus = TaskStatus.QUEUED
    retry_count: int = 0
    result: Any | None = None
    error: str | None = None
    submitted_at: datetime = field(default_factory=utcnow)
    # Start of the most recent attempt, so duration_ms covers the attempt
    # that produced the final result and excludes retry backoff.
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def duration_ms(self) -> int | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return round((self.completed_at - self.started_at).total_seconds() * 1000)
