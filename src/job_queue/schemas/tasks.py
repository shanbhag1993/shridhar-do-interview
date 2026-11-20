from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from job_queue.domain import Task, TaskStatus


class SubmitTaskRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=64)
    # Stored and echoed back. Ordering is FIFO regardless of priority in v1.
    priority: int = Field(default=0, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = Field(default=0, ge=0, le=10)
    timeout_seconds: float = Field(default=30, gt=0, le=3600)


class SubmitTaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    submitted_at: datetime
    poll_url: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    task_type: str
    priority: int
    submitted_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    retry_count: int
    result: Any | None
    error: str | None

    @classmethod
    def from_task(cls, task: Task) -> "TaskStatusResponse":
        return cls(
            task_id=task.id,
            status=task.status,
            task_type=task.task_type,
            priority=task.priority,
            submitted_at=task.submitted_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            duration_ms=task.duration_ms,
            retry_count=task.retry_count,
            result=task.result,
            error=task.error,
        )
