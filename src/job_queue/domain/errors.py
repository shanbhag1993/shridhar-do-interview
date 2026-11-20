from job_queue.domain.status import TaskStatus


class JobQueueError(Exception):
    """Base class for errors the API layer maps to HTTP responses."""


class QueueFullError(JobQueueError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("queue is at capacity")
        self.retry_after_seconds = retry_after_seconds


class ServiceShuttingDownError(JobQueueError):
    def __init__(self) -> None:
        super().__init__("service is shutting down")


class UnknownTaskTypeError(JobQueueError):
    def __init__(self, task_type: str) -> None:
        super().__init__(f"unknown task_type: {task_type!r}")
        self.task_type = task_type


class TaskNotFoundError(JobQueueError):
    def __init__(self, task_id: str) -> None:
        super().__init__(f"task {task_id!r} not found")
        self.task_id = task_id


class TaskNotCancellableError(JobQueueError):
    def __init__(self, task_id: str, status: TaskStatus) -> None:
        super().__init__(f"task {task_id!r} is {status.value}; only QUEUED tasks can be cancelled")
        self.task_id = task_id
        self.status = status
